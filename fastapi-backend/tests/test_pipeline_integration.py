"""Integration tests for the Blair AI cognitive pipeline.

Tests verify key scenarios by testing node functions in sequence
with mocked LLM responses.

Scenarios:
- Simple greeting: intake -> understand(greeting) -> respond -> END (fast path)
- Tool calling: intake -> understand(info_query) -> explore -> explore_tools -> explore -> respond
- Clarification: intake -> understand(low confidence) -> clarify -> understand -> explore -> respond
- Complex query: intake -> understand(multi_step) -> explore -> synthesize -> respond
- Safety limits: MAX_TOOL_CALLS, MAX_LLM_CALLS, MAX_ITERATIONS
- Backward compat: _agent_node, _execute_tools, _route_after_agent still work
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.ai.agent.constants import (
    get_max_clarify_rounds,
    get_max_iterations,
    get_max_llm_calls,
    get_max_tool_calls,
)
from app.ai.agent.graph import _agent_node, _execute_tools, _route_after_agent
from app.ai.agent.nodes.clarify import clarify_node
from app.ai.agent.nodes.explore import explore_node, execute_tools
from app.ai.agent.nodes.understand import understand_node
from app.ai.agent.nodes.respond import respond_node
from app.ai.agent.nodes.synthesize import synthesize_node
from app.ai.agent.routing import (
    route_after_explore,
    route_after_respond,
    route_after_synthesize,
    route_after_understand,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_model(response: AIMessage | None = None):
    """Create a mock bound model."""
    if response is None:
        response = AIMessage(content="Hello!")
    model = AsyncMock()
    model.ainvoke = AsyncMock(return_value=response)
    return model


def _make_tool_node(result_messages=None):
    """Create a mock ToolNode that returns given messages."""
    mock = AsyncMock()
    mock.ainvoke = AsyncMock(return_value={"messages": result_messages or []})
    return mock


# ---------------------------------------------------------------------------
# Test: Greeting fast path (intake -> understand -> respond -> END)
# ---------------------------------------------------------------------------


class TestGreetingFastPath:
    async def test_greeting_fast_paths_to_respond(self):
        """A greeting classified with high confidence fast-paths to respond."""
        # Simulate understand node producing greeting classification
        classification_json = (
            '{"intent": "greeting", "confidence": 0.95, '
            '"data_sources": [], "entities": [], '
            '"clarification_questions": [], "complexity": "simple", '
            '"reasoning": "User said hello"}'
        )
        classify_model = _make_mock_model(AIMessage(content=classification_json))
        respond_model = _make_mock_model(AIMessage(content="Hello! I'm Blair, your AI copilot."))

        state = {
            "messages": [HumanMessage(content="Hi!")],
            "total_llm_calls": 0,
            "iteration_count": 0,
            "total_tool_calls": 0,
        }

        # 1. understand_node classifies as greeting
        understand_result = await understand_node(
            state,
            chat_model_cache=[classify_model],
            system_prompt_cache=["test"],
        )
        assert understand_result["classification"]["intent"] == "greeting"
        assert understand_result["fast_path"] is True
        assert understand_result["total_llm_calls"] == 1

        # 2. route_after_understand -> respond (fast path)
        merged = {**state, **understand_result}
        route = route_after_understand(merged)
        assert route == "respond"

        # 3. respond_node makes 1 LLM call (fast path)
        respond_result = await respond_node(
            merged,
            bound_model_cache=[respond_model],
            chat_model_cache=[respond_model],
            system_prompt_cache=["test"],
        )
        assert "Hello" in respond_result["messages"][0].content
        assert respond_result["total_llm_calls"] == 2  # understand(1) + respond(1)

        # 4. route_after_respond -> end (text-only, no tool_calls)
        final = {**merged, **respond_result, "messages": merged["messages"] + respond_result["messages"]}
        route = route_after_respond(final)
        assert route == "end"


# ---------------------------------------------------------------------------
# Test: Simple query (understand -> explore -> explore_tools -> explore -> respond)
# ---------------------------------------------------------------------------


class TestSimpleQuery:
    async def test_info_query_routes_through_explore(self):
        """An info query goes through explore -> explore_tools -> respond."""
        # First explore LLM call: request tool
        tool_request = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        # Second explore LLM call: summarize
        summary = AIMessage(content="Found 3 tasks in the project.")

        model = AsyncMock()
        model.ainvoke = AsyncMock(side_effect=[tool_request, summary])

        tool_result = ToolMessage(content="task data", tool_call_id="tc1", name="list_tasks")
        tool_node = _make_tool_node(result_messages=[tool_result])

        state = {
            "messages": [HumanMessage(content="Show tasks in Alpha")],
            "total_llm_calls": 1,  # after understand
            "total_tool_calls": 0,
            "iteration_count": 0,
            "classification": {
                "intent": "info_query",
                "confidence": 0.9,
                "data_sources": ["tasks"],
                "entities": [{"type": "project", "value": "Alpha"}],
                "clarification_questions": [],
                "complexity": "simple",
                "reasoning": "User wants tasks",
            },
            "fast_path": False,
        }

        # Step 1: explore_node -- LLM requests tool
        result1 = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )
        assert result1["total_llm_calls"] == 2
        merged = {**state, **result1, "messages": state["messages"] + result1["messages"]}

        # Route should be "explore_tools"
        assert route_after_explore(merged) == "explore_tools"

        # Step 2: execute_tools
        tools_result = await execute_tools(merged, tool_node=tool_node)
        assert tools_result["total_tool_calls"] == 1
        merged2 = {
            **merged,
            **tools_result,
            "messages": merged["messages"] + tools_result["messages"],
        }

        # Step 3: explore_node again -- LLM summarizes
        result2 = await explore_node(
            merged2,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )
        assert result2["total_llm_calls"] == 3
        assert "3 tasks" in result2["messages"][0].content

        # Route should be "respond" (text-only, simple complexity)
        final = {**merged2, **result2, "messages": merged2["messages"] + result2["messages"]}
        assert route_after_explore(final) == "respond"


# ---------------------------------------------------------------------------
# Test: Complex query (explore -> synthesize -> respond)
# ---------------------------------------------------------------------------


class TestComplexQuery:
    async def test_complex_query_routes_to_synthesize(self):
        """A complex/multi_step query routes through synthesize after explore."""
        state = {
            "messages": [
                HumanMessage(content="Compare Alpha and Beta projects"),
                AIMessage(content="Here is the comparison data."),
            ],
            "total_llm_calls": 4,
            "total_tool_calls": 5,
            "iteration_count": 3,
            "classification": {
                "intent": "multi_step",
                "confidence": 0.85,
                "data_sources": ["projects"],
                "entities": [],
                "clarification_questions": [],
                "complexity": "complex",
                "reasoning": "Comparison of two projects",
            },
            "fast_path": False,
        }

        # route_after_explore sees complex -> synthesize
        route = route_after_explore(state)
        assert route == "synthesize"

        # Synthesize node
        synth_model = _make_mock_model(AIMessage(content="| Metric | Alpha | Beta |\n..."))
        result = await synthesize_node(
            state,
            chat_model_cache=[synth_model],
        )
        assert result["total_llm_calls"] == 5
        assert result["current_phase"] == "synthesize"

        # route_after_synthesize -> respond (no user correction)
        final = {**state, **result, "messages": state["messages"] + result.get("messages", [])}
        route = route_after_synthesize(final)
        assert route == "respond"


# ---------------------------------------------------------------------------
# Test: Clarification flow (understand -> clarify -> understand -> explore)
# ---------------------------------------------------------------------------


class TestClarificationFlow:
    async def test_low_confidence_routes_to_clarify(self):
        """Low confidence classification routes to clarify node."""
        state = {
            "messages": [HumanMessage(content="Show me the project")],
            "total_llm_calls": 1,
            "total_tool_calls": 0,
            "iteration_count": 0,
            "classification": {
                "intent": "needs_clarification",
                "confidence": 0.3,
                "data_sources": ["projects"],
                "entities": [],
                "clarification_questions": ["Which project do you mean?"],
                "complexity": "simple",
                "reasoning": "Ambiguous reference",
            },
            "fast_path": False,
        }

        route = route_after_understand(state)
        assert route == "clarify"


# ---------------------------------------------------------------------------
# Test: Safety limits (backward compat with old functions)
# ---------------------------------------------------------------------------


class TestSafetyLimits:
    async def test_max_tool_calls_stops_execution(self):
        """execute_tools returns limit message when tool budget exhausted."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "t1", "args": {}, "id": "tc1"},
                {"name": "t2", "args": {}, "id": "tc2"},
            ],
        )
        tool_node = _make_tool_node()

        state = {
            "messages": [ai_msg],
            "total_tool_calls": get_max_tool_calls() - 1,  # one short, but 2 new calls > budget
        }

        result = await execute_tools(state, tool_node=tool_node)

        tool_node.ainvoke.assert_not_called()
        # TE-R3: Verify ToolMessage type (not AIMessage) to satisfy provider protocol
        # CR1-R3: Verify one ToolMessage per tool_call in the AIMessage
        assert len(result["messages"]) == 2
        for msg in result["messages"]:
            assert isinstance(msg, ToolMessage)
            assert "limit" in msg.content.lower()
        assert result["total_tool_calls"] == get_max_tool_calls()

    async def test_max_llm_calls_stops_explore(self):
        """explore_node returns limit message when LLM budget exhausted."""
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": get_max_llm_calls(),
            "iteration_count": 0,
        }
        model = _make_mock_model()

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=[""],
        )

        assert "processing limit" in result["messages"][0].content
        model.ainvoke.assert_not_awaited()

    async def test_max_iterations_stops_explore(self):
        """explore_node returns limit message when iteration budget exhausted."""
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 0,
            "iteration_count": get_max_iterations(),
        }
        model = _make_mock_model()

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=[""],
        )

        assert "processing limit" in result["messages"][0].content
        model.ainvoke.assert_not_awaited()

    async def test_route_blocks_at_any_limit(self):
        """route_after_explore returns 'respond' when any safety limit is reached."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}],
        )

        # LLM limit
        state_llm = {
            "messages": [ai_msg],
            "total_llm_calls": get_max_llm_calls(),
            "total_tool_calls": 0,
            "iteration_count": 0,
        }
        assert route_after_explore(state_llm) == "respond"

        # Tool limit
        state_tool = {
            "messages": [ai_msg],
            "total_llm_calls": 0,
            "total_tool_calls": get_max_tool_calls(),
            "iteration_count": 0,
        }
        assert route_after_explore(state_tool) == "respond"

        # Iteration limit
        state_iter = {
            "messages": [ai_msg],
            "total_llm_calls": 0,
            "total_tool_calls": 0,
            "iteration_count": get_max_iterations(),
        }
        assert route_after_explore(state_iter) == "respond"


# ---------------------------------------------------------------------------
# Test: Backward compatibility (old _agent_node, _execute_tools, _route_after_agent)
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    async def test_agent_node_wrapper_works(self):
        """_agent_node backward-compat wrapper delegates to explore_node."""
        model = _make_mock_model(AIMessage(content="Hello"))
        state = {
            "messages": [HumanMessage(content="Hi")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }

        result = await _agent_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )

        assert result["messages"][0].content == "Hello"
        assert result["total_llm_calls"] == 1

    async def test_execute_tools_wrapper_works(self):
        """_execute_tools backward-compat wrapper delegates to execute_tools."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        tool_msg = ToolMessage(content="result", tool_call_id="tc1", name="list_tasks")
        mock_tool_node = _make_tool_node(result_messages=[tool_msg])

        state = {"messages": [ai_msg], "total_tool_calls": 0}
        result = await _execute_tools(state, tool_node=mock_tool_node)

        assert result["total_tool_calls"] == 1

    def test_route_after_agent_maps_tools(self):
        """_route_after_agent maps explore_tools -> tools for backward compat."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}],
        )
        state = {"messages": [ai_msg], "total_llm_calls": 1, "total_tool_calls": 0, "iteration_count": 1}
        assert _route_after_agent(state) == "tools"

    def test_route_after_agent_maps_end(self):
        """_route_after_agent maps text-only to end."""
        state = {"messages": [AIMessage(content="done")]}
        assert _route_after_agent(state) == "end"


# ---------------------------------------------------------------------------
# Test: Misclassification recovery
# ---------------------------------------------------------------------------


class TestMisclassificationRecovery:
    async def test_fast_path_tool_calls_rerouted(self):
        """If fast-path respond node returns tool_calls, route to explore_tools."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        state = {
            "messages": [HumanMessage(content="Hi"), ai_msg],
            "fast_path": True,
        }

        route = route_after_respond(state)
        assert route == "explore_tools"

    async def test_normal_respond_routes_to_end(self):
        """Normal text response from respond routes to end."""
        state = {
            "messages": [HumanMessage(content="Hi"), AIMessage(content="Hello!")],
            "fast_path": True,
        }

        route = route_after_respond(state)
        assert route == "end"

    async def test_misclassification_clears_fast_path(self):
        """B5: When fast-path LLM returns tool_calls, fast_path is cleared."""
        tool_response = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        model = _make_mock_model(tool_response)

        state = {
            "messages": [HumanMessage(content="Show tasks")],
            "fast_path": True,
            "total_llm_calls": 1,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        assert result["fast_path"] is False


# ---------------------------------------------------------------------------
# Test: Full clarification loop (B8)
# ---------------------------------------------------------------------------


class TestClarificationFlowMockedInterrupt:
    """B8: End-to-end clarification flow integration test with mocked interrupt.

    Uses ``patch("...clarify.interrupt")`` to simulate the user responding
    without actually triggering LangGraph's interrupt/resume machinery.
    For real interrupt/resume, a full LangGraph integration test is needed.

    Flow: understand(low conf) -> clarify(mocked interrupt) -> understand(re-classify) -> explore -> respond
    """

    async def test_clarification_flow_with_mocked_interrupt(self):
        """Exercise the clarify -> re-classify -> explore -> respond pipeline with mocked interrupt."""
        # Step 1: understand_node returns low confidence -> needs_clarification
        low_conf_json = (
            '{"intent": "needs_clarification", "confidence": 0.3, '
            '"data_sources": ["projects"], "entities": [], '
            '"clarification_questions": ["Which project do you mean?"], '
            '"complexity": "simple", "reasoning": "Ambiguous reference"}'
        )
        classify_model_low = _make_mock_model(AIMessage(content=low_conf_json))

        state = {
            "messages": [HumanMessage(content="Show me the project")],
            "total_llm_calls": 0,
            "total_tool_calls": 0,
            "iteration_count": 0,
            "clarify_count": 0,
        }

        understand_result = await understand_node(
            state,
            chat_model_cache=[classify_model_low],
            system_prompt_cache=["test"],
        )
        assert understand_result["classification"]["intent"] == "needs_clarification"
        assert understand_result["classification"]["confidence"] == 0.3
        assert understand_result["fast_path"] is False

        # Verify routing -> clarify
        merged1 = {**state, **understand_result}
        route1 = route_after_understand(merged1)
        assert route1 == "clarify"

        # Step 2: clarify_node builds payload and interrupt fires
        # Mock interrupt to simulate user responding "Alpha"
        with patch("app.ai.agent.nodes.clarify.interrupt", return_value="Alpha"):
            clarify_result = await clarify_node(merged1)

        assert clarify_result["current_phase"] == "clarify"
        assert len(clarify_result["messages"]) == 1
        assert clarify_result["messages"][0].content == "Alpha"
        assert clarify_result["clarify_count"] == 1

        # Step 3: understand re-classifies with user answer -> high confidence
        high_conf_json = (
            '{"intent": "info_query", "confidence": 0.9, '
            '"data_sources": ["projects"], '
            '"entities": [{"type": "project", "value": "Alpha"}], '
            '"clarification_questions": [], "complexity": "simple", '
            '"reasoning": "User specified Alpha project"}'
        )
        classify_model_high = _make_mock_model(AIMessage(content=high_conf_json))

        merged2 = {
            **merged1,
            **clarify_result,
            "messages": merged1["messages"] + clarify_result["messages"],
        }

        understand_result2 = await understand_node(
            merged2,
            chat_model_cache=[classify_model_high],
            system_prompt_cache=["test"],
        )
        assert understand_result2["classification"]["intent"] == "info_query"
        assert understand_result2["classification"]["confidence"] == 0.9
        assert understand_result2["fast_path"] is False

        # Verify routing -> explore (not clarify)
        merged3 = {**merged2, **understand_result2}
        route2 = route_after_understand(merged3)
        assert route2 == "explore"

        # Step 4: explore_node calls tools
        tool_request = AIMessage(
            content="",
            tool_calls=[{"name": "get_project_details", "args": {"project": "Alpha"}, "id": "tc1"}],
        )
        explore_model = AsyncMock()
        explore_model.ainvoke = AsyncMock(
            side_effect=[
                tool_request,
                AIMessage(content="Alpha project has 15 tasks."),
            ]
        )

        explore_result = await explore_node(
            merged3,
            bound_model_cache=[explore_model],
            chat_model_cache=[explore_model],
            system_prompt_cache=["test"],
        )
        assert explore_result["messages"][0].tool_calls

        merged4 = {
            **merged3,
            **explore_result,
            "messages": merged3["messages"] + explore_result["messages"],
        }

        # Route -> explore_tools
        route3 = route_after_explore(merged4)
        assert route3 == "explore_tools"

        # Step 5: execute_tools
        tool_result_msg = ToolMessage(
            content="Project Alpha: 15 tasks, 3 completed",
            tool_call_id="tc1",
            name="get_project_details",
        )
        tool_node = _make_tool_node(result_messages=[tool_result_msg])

        tools_result = await execute_tools(merged4, tool_node=tool_node)

        merged5 = {
            **merged4,
            **tools_result,
            "messages": merged4["messages"] + tools_result["messages"],
        }

        # Step 6: explore_node again -> text response
        explore_result2 = await explore_node(
            merged5,
            bound_model_cache=[explore_model],
            chat_model_cache=[explore_model],
            system_prompt_cache=["test"],
        )
        assert "15 tasks" in explore_result2["messages"][0].content

        merged6 = {
            **merged5,
            **explore_result2,
            "messages": merged5["messages"] + explore_result2["messages"],
        }

        # Route -> respond (simple complexity, text-only)
        route4 = route_after_explore(merged6)
        assert route4 == "respond"

    async def test_clarify_limit_forces_explore(self):
        """B1: After MAX_CLARIFY_ROUNDS, the loop forces progress to explore."""
        low_conf_json = (
            '{"intent": "needs_clarification", "confidence": 0.3, '
            '"data_sources": [], "entities": [], '
            '"clarification_questions": ["What do you mean?"], '
            '"complexity": "simple", "reasoning": "Still ambiguous"}'
        )
        classify_model = _make_mock_model(AIMessage(content=low_conf_json))

        state = {
            "messages": [HumanMessage(content="Show me stuff")],
            "total_llm_calls": 0,
            "total_tool_calls": 0,
            "iteration_count": 0,
            "clarify_count": get_max_clarify_rounds(),  # Already at limit
        }

        understand_result = await understand_node(
            state,
            chat_model_cache=[classify_model],
            system_prompt_cache=["test"],
        )

        merged = {**state, **understand_result}
        route = route_after_understand(merged)
        # Should force explore despite low confidence
        assert route == "explore"

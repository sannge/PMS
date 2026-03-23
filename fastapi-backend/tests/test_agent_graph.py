"""Unit tests for AI agent graph (app.ai.agent.graph).

Tests cover:
- AgentState TypedDict structure (7-node pipeline fields)
- SYSTEM_PROMPT content
- _get_langchain_chat_model for openai, anthropic, ollama providers
- build_agent_graph returns compiled graph with 7 nodes (cognitive pipeline)
- get_checkpointer / set_checkpointer module-level accessors
- MAX_ITERATIONS, MAX_TOOL_CALLS, MAX_LLM_CALLS constants
- _route_after_agent backward-compatible routing
- _agent_node (explore_node wrapper) safety limits, empty cache, normal call
- _execute_tools counting, HITL interrupt, error handling, limit exceeded
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as langchain_tool

from app.ai.agent.constants import MAX_ITERATIONS, MAX_LLM_CALLS, MAX_TOOL_CALLS
from app.ai.agent.graph import (
    _agent_node,
    _execute_tools,
    _extract_clarification,
    _route_after_agent,
    _text_requests_user_input,
    build_agent_graph,
    get_checkpointer,
    set_checkpointer,
)
from app.ai.agent.prompts import SYSTEM_PROMPT
from app.ai.agent.state import AgentState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider_orm(provider_type: str, base_url: str | None = None) -> MagicMock:
    """Create a mock ORM provider object."""
    orm = MagicMock()
    orm.provider_type = provider_type
    orm.base_url = base_url
    return orm


def _make_model_orm(model_id: str = "gpt-4o") -> MagicMock:
    """Create a mock ORM model object."""
    orm = MagicMock()
    orm.model_id = model_id
    return orm


def _make_registry(provider_type: str, model_id: str = "gpt-4o", base_url: str | None = None) -> MagicMock:
    """Build a mock ProviderRegistry that resolves to a given provider."""
    provider_orm = _make_provider_orm(provider_type, base_url)
    model_orm = _make_model_orm(model_id)

    registry = MagicMock()
    registry._resolve_provider = AsyncMock(return_value=(provider_orm, model_orm))
    registry._decrypt_key = MagicMock(return_value="test-api-key")
    return registry


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_max_iterations_is_25(self):
        assert MAX_ITERATIONS == 25

    def test_max_tool_calls_is_50(self):
        assert MAX_TOOL_CALLS == 50

    def test_max_llm_calls_is_25(self):
        assert MAX_LLM_CALLS == 25

    def test_system_prompt_mentions_blair(self):
        assert "Blair" in SYSTEM_PROMPT

    def test_system_prompt_mentions_tool_guidance(self):
        assert "sql_query" in SYSTEM_PROMPT
        assert "search_knowledge" in SYSTEM_PROMPT

    def test_system_prompt_mentions_confirmation(self):
        assert "confirm" in SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# Tests: AgentState
# ---------------------------------------------------------------------------


class TestAgentState:
    def test_agent_state_has_messages_field(self):
        annotations = AgentState.__annotations__
        assert "messages" in annotations

    def test_agent_state_has_user_id_field(self):
        annotations = AgentState.__annotations__
        assert "user_id" in annotations

    def test_agent_state_has_accessible_app_ids_field(self):
        annotations = AgentState.__annotations__
        assert "accessible_app_ids" in annotations

    def test_agent_state_has_accessible_project_ids_field(self):
        annotations = AgentState.__annotations__
        assert "accessible_project_ids" in annotations

    def test_agent_state_has_safety_counters(self):
        annotations = AgentState.__annotations__
        assert "total_tool_calls" in annotations
        assert "total_llm_calls" in annotations
        assert "iteration_count" in annotations

    def test_agent_state_has_pipeline_fields(self):
        """7-node pipeline state has classification, research, fast_path, current_phase."""
        annotations = AgentState.__annotations__
        assert "classification" in annotations
        assert "research" in annotations
        assert "fast_path" in annotations
        assert "current_phase" in annotations
        # Loop guard counters (B1, B3)
        assert "clarify_count" in annotations
        assert "synthesize_count" in annotations
        # Old fields that were removed should NOT be present
        assert "respond_recovery_count" not in annotations


# ---------------------------------------------------------------------------
# Tests: Checkpointer accessors
# ---------------------------------------------------------------------------


class TestCheckpointerAccessors:
    def test_get_checkpointer_returns_none_initially(self):
        import app.ai.agent.graph as graph_mod

        original = graph_mod._checkpointer
        try:
            graph_mod._checkpointer = None
            assert get_checkpointer() is None
        finally:
            graph_mod._checkpointer = original

    def test_set_and_get_checkpointer(self):
        import app.ai.agent.graph as graph_mod

        original = graph_mod._checkpointer
        try:
            sentinel = MagicMock()
            set_checkpointer(sentinel)
            assert get_checkpointer() is sentinel
        finally:
            graph_mod._checkpointer = original


# ---------------------------------------------------------------------------
# Tests: _get_langchain_chat_model
# ---------------------------------------------------------------------------


class TestGetLangchainChatModel:
    @patch("app.ai.agent.graph.ChatOpenAI", create=True)
    async def test_openai_provider_returns_chat_openai(self, mock_cls):
        mock_cls.return_value = MagicMock()
        registry = _make_registry("openai", "gpt-4o", "https://api.openai.com/v1")
        db = AsyncMock()

        from app.ai.agent.graph import _get_langchain_chat_model

        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            result = await _get_langchain_chat_model(registry, db, None)

        mock_cls.assert_called_once_with(
            model="gpt-4o",
            api_key="test-api-key",
            base_url="https://api.openai.com/v1",
            temperature=0.1,
            max_tokens=4096,
            request_timeout=30,
        )
        assert result is mock_cls.return_value

    @patch.dict("sys.modules")
    async def test_anthropic_provider_returns_chat_anthropic(self):
        mock_cls = MagicMock()
        mock_cls.return_value = MagicMock()
        mock_anthropic_mod = MagicMock(ChatAnthropic=mock_cls)
        import sys

        sys.modules["langchain_anthropic"] = mock_anthropic_mod

        from app.ai.agent.graph import _get_langchain_chat_model

        registry = _make_registry("anthropic", "claude-sonnet-4-6")
        db = AsyncMock()

        result = await _get_langchain_chat_model(registry, db, None)

        mock_cls.assert_called_once_with(
            model="claude-sonnet-4-6",
            api_key="test-api-key",
            temperature=0.1,
            max_tokens=4096,
            timeout=30.0,
        )
        assert result is mock_cls.return_value

    @patch.dict("sys.modules")
    async def test_ollama_provider_returns_chat_openai_with_defaults(self):
        mock_cls = MagicMock()
        mock_cls.return_value = MagicMock()
        mock_openai_mod = MagicMock(ChatOpenAI=mock_cls)
        import sys

        sys.modules["langchain_openai"] = mock_openai_mod

        from app.ai.agent.graph import _get_langchain_chat_model

        registry = _make_registry("ollama", "llama3")
        registry._decrypt_key = MagicMock(return_value=None)
        db = AsyncMock()

        result = await _get_langchain_chat_model(registry, db, None)

        mock_cls.assert_called_once_with(
            model="llama3",
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            temperature=0.1,
            max_tokens=4096,
            request_timeout=30,
        )
        assert result is mock_cls.return_value

    async def test_unsupported_provider_raises_value_error(self):
        from app.ai.agent.graph import _get_langchain_chat_model

        registry = _make_registry("azure")
        db = AsyncMock()

        with pytest.raises(ValueError, match="Unsupported provider type"):
            await _get_langchain_chat_model(registry, db, None)


# ---------------------------------------------------------------------------
# Tests: build_agent_graph (3-node ReAct loop)
# ---------------------------------------------------------------------------


@langchain_tool
def _dummy_tool(query: str) -> str:
    """A dummy tool for testing graph compilation."""
    return "dummy result"


class TestBuildAgentGraph:
    def test_returns_compiled_graph(self):
        compiled = build_agent_graph(tools=[_dummy_tool])
        assert compiled is not None

    def test_compiled_graph_has_7_pipeline_nodes(self):
        """The cognitive pipeline has 7 nodes."""
        compiled = build_agent_graph(tools=[_dummy_tool])
        graph_repr = compiled.get_graph()
        node_ids = set(graph_repr.nodes)
        for node_name in [
            "intake",
            "understand",
            "clarify",
            "explore",
            "explore_tools",
            "synthesize",
            "respond",
        ]:
            assert node_name in node_ids, f"Missing node: {node_name}"

    def test_old_3_node_names_absent(self):
        """Old 3-node ReAct names (agent, tools) should NOT be present."""
        compiled = build_agent_graph(tools=[_dummy_tool])
        graph_repr = compiled.get_graph()
        node_ids = set(graph_repr.nodes)
        for old_name in ["agent", "tools"]:
            assert old_name not in node_ids, f"Old node still present: {old_name}"

    def test_accepts_checkpointer_true(self):
        compiled = build_agent_graph(tools=[_dummy_tool], checkpointer=True)
        assert compiled is not None

    def test_build_agent_graph_without_checkpointer_succeeds(self):
        """build_agent_graph works without a checkpointer (None default)."""
        compiled = build_agent_graph(tools=[_dummy_tool], checkpointer=None)
        assert compiled is not None

    def test_build_agent_graph_with_provider_and_factory(self):
        """build_agent_graph accepts provider_registry and db_session_factory."""
        registry = MagicMock()
        factory = MagicMock()
        compiled = build_agent_graph(
            tools=[_dummy_tool],
            provider_registry=registry,
            db_session_factory=factory,
        )
        assert compiled is not None


# ---------------------------------------------------------------------------
# Tests: _route_after_agent
# ---------------------------------------------------------------------------


class TestRouteAfterAgent:
    """Test _route_after_agent conditional edge."""

    def test_tool_calls_routes_to_tools(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        state = {"messages": [ai_msg], "total_llm_calls": 1, "total_tool_calls": 0, "iteration_count": 1}
        assert _route_after_agent(state) == "tools"

    def test_text_only_routes_to_end(self):
        ai_msg = AIMessage(content="Here is your answer.")
        state = {"messages": [ai_msg]}
        assert _route_after_agent(state) == "end"

    def test_empty_messages_routes_to_end(self):
        state = {"messages": []}
        assert _route_after_agent(state) == "end"

    def test_human_message_routes_to_end(self):
        state = {"messages": [HumanMessage(content="hello")]}
        assert _route_after_agent(state) == "end"

    def test_tool_calls_at_llm_limit_routes_to_end(self):
        """When LLM budget is exhausted, even with tool_calls, route to end."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_tasks", "args": {}, "id": "tc1"}],
        )
        state = {"messages": [ai_msg], "total_llm_calls": MAX_LLM_CALLS}
        assert _route_after_agent(state) == "end"

    def test_tool_calls_at_tool_limit_routes_to_end(self):
        """When tool budget is exhausted, even with tool_calls, route to end."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_tasks", "args": {}, "id": "tc1"}],
        )
        state = {"messages": [ai_msg], "total_tool_calls": MAX_TOOL_CALLS}
        assert _route_after_agent(state) == "end"

    def test_tool_calls_at_iteration_limit_routes_to_end(self):
        """When iteration budget is exhausted, even with tool_calls, route to end."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_tasks", "args": {}, "id": "tc1"}],
        )
        state = {"messages": [ai_msg], "iteration_count": MAX_ITERATIONS}
        assert _route_after_agent(state) == "end"

    def test_tool_calls_under_all_limits_routes_to_tools(self):
        """When all budgets have headroom, tool_calls route to tools."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_tasks", "args": {}, "id": "tc1"}],
        )
        state = {
            "messages": [ai_msg],
            "total_llm_calls": MAX_LLM_CALLS - 1,
            "total_tool_calls": MAX_TOOL_CALLS - 1,
            "iteration_count": MAX_ITERATIONS - 1,
        }
        assert _route_after_agent(state) == "tools"

    # TE-R2-010: missing counter fields default to 0
    def test_missing_counter_fields_default_to_zero(self):
        """State with missing counter fields defaults to 0, routes to tools."""
        ai_msg = AIMessage(content="", tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}])
        state = {"messages": [ai_msg]}  # No total_llm_calls, total_tool_calls, iteration_count
        assert _route_after_agent(state) == "tools"


# ---------------------------------------------------------------------------
# Tests: _agent_node
# ---------------------------------------------------------------------------


class TestAgentNode:
    """Test _agent_node — the core LLM call in the ReAct loop."""

    async def test_safety_limit_llm_returns_limit_message(self):
        """When total_llm_calls >= MAX_LLM_CALLS, returns limit message."""
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": MAX_LLM_CALLS,
            "iteration_count": 0,
        }
        result = await _agent_node(
            state, bound_model_cache=[MagicMock()], chat_model_cache=[], system_prompt_cache=[""]
        )
        assert "processing limit" in result["messages"][0].content
        # Should NOT increment counters
        assert "total_llm_calls" not in result

    async def test_safety_limit_iteration_returns_limit_message(self):
        """When iteration_count >= MAX_ITERATIONS, returns limit message."""
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 0,
            "iteration_count": MAX_ITERATIONS,
        }
        result = await _agent_node(
            state, bound_model_cache=[MagicMock()], chat_model_cache=[], system_prompt_cache=[""]
        )
        assert "processing limit" in result["messages"][0].content

    async def test_empty_cache_returns_error(self):
        """When bound_model_cache is empty, returns error message."""
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }
        result = await _agent_node(state, bound_model_cache=[], chat_model_cache=[], system_prompt_cache=[""])
        assert "not initialized" in result["messages"][0].content

    async def test_normal_call_returns_response_and_increments(self):
        """Normal LLM call returns response and increments counters."""
        mock_model = AsyncMock()
        response = AIMessage(content="Here are your tasks.")
        mock_model.ainvoke = AsyncMock(return_value=response)

        state = {
            "messages": [HumanMessage(content="Show tasks")],
            "total_llm_calls": 2,
            "iteration_count": 1,
        }
        result = await _agent_node(
            state, bound_model_cache=[mock_model], chat_model_cache=[], system_prompt_cache=["You are Blair."]
        )
        assert result["messages"][0].content == "Here are your tasks."
        assert result["total_llm_calls"] == 3
        assert result["iteration_count"] == 2

    async def test_llm_exception_returns_error_message(self):
        """When LLM call raises, returns graceful error message."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))

        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }
        result = await _agent_node(state, bound_model_cache=[mock_model], chat_model_cache=[], system_prompt_cache=[""])
        assert "error" in result["messages"][0].content.lower()
        assert result["total_llm_calls"] == 1
        assert result["iteration_count"] == 1

    # TE-R2-008: document that LLM errors still increment counters
    async def test_llm_error_still_increments_counters(self):
        """LLM errors always increment total_llm_calls and iteration_count.
        Unlike tool failures, LLM call attempts always count because we DID
        attempt the call (the error is from the provider, not our code)."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("provider 503"))

        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 5,
            "iteration_count": 3,
        }
        result = await _agent_node(state, bound_model_cache=[mock_model], chat_model_cache=[], system_prompt_cache=[""])

        # Error message returned
        assert "error" in result["messages"][0].content.lower()
        # Counters STILL incremented — the LLM call was attempted
        assert result["total_llm_calls"] == 6  # 5 + 1
        assert result["iteration_count"] == 4  # 3 + 1

    async def test_completed_tool_turns_stripped(self):
        """Two-stage context: completed tool turns are stripped before LLM call."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="done"))

        msgs = [
            HumanMessage(content="Hello"),
            # Completed turn: tool_call -> ToolMessage -> final AIMessage
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}]),
            ToolMessage(content="result", tool_call_id="tc1"),
            AIMessage(content="Based on results"),
            HumanMessage(content="Thanks"),
        ]
        state = {
            "messages": msgs,
            "total_llm_calls": 0,
            "iteration_count": 0,
        }
        await _agent_node(state, bound_model_cache=[mock_model], chat_model_cache=[], system_prompt_cache=["system"])

        call_args = mock_model.ainvoke.call_args[0][0]
        # First element is SystemMessage, then stripped messages
        passed_messages = call_args[1:]
        # Completed turn's AI(tool_calls) + ToolMessage stripped; closing AI + others kept
        assert len(passed_messages) == 3  # Human + closing AI + Human
        assert passed_messages[0].content == "Hello"
        assert passed_messages[1].content == "Based on results"
        assert passed_messages[2].content == "Thanks"

    async def test_orphaned_tool_calls_sanitized_in_agent_node(self):
        """Orphaned tool_calls (no matching ToolMessage) are sanitized before LLM call."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="done"))

        msgs = [
            HumanMessage(content="Do something"),
            AIMessage(
                content="Let me search",
                tool_calls=[{"name": "search", "args": {}, "id": "orphan_tc"}],
            ),
            # No matching ToolMessage for orphan_tc
            HumanMessage(content="Continue"),
        ]
        state = {
            "messages": msgs,
            "total_llm_calls": 0,
            "iteration_count": 0,
        }
        await _agent_node(state, bound_model_cache=[mock_model], chat_model_cache=[], system_prompt_cache=["system"])

        call_args = mock_model.ainvoke.call_args[0][0]
        passed_messages = call_args[1:]
        # The orphaned AI should have tool_calls stripped
        assert len(passed_messages) == 3
        orphaned_ai = passed_messages[1]
        assert isinstance(orphaned_ai, AIMessage)
        assert not getattr(orphaned_ai, "tool_calls", None)
        assert orphaned_ai.content == "Let me search"


# ---------------------------------------------------------------------------
# Tests: _execute_tools
# ---------------------------------------------------------------------------


class TestExecuteTools:
    """Test _execute_tools — tool execution with counting and HITL."""

    async def test_counts_tool_calls(self):
        """Tool calls are counted and added to total_tool_calls."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "list_tasks", "args": {}, "id": "tc1"},
                {"name": "get_project_details", "args": {}, "id": "tc2"},
            ],
        )
        tool_msg = ToolMessage(content="result", tool_call_id="tc1", name="list_tasks")
        mock_tool_node = AsyncMock()
        mock_tool_node.ainvoke = AsyncMock(return_value={"messages": [tool_msg]})

        state = {"messages": [ai_msg], "total_tool_calls": 5}

        result = await _execute_tools(state, tool_node=mock_tool_node)

        assert result["total_tool_calls"] == 7  # 5 + 2

    async def test_no_ai_message_returns_empty(self):
        """When last message is not AIMessage, returns empty dict."""
        mock_tool_node = AsyncMock()
        state = {"messages": [HumanMessage(content="hello")], "total_tool_calls": 3}

        result = await _execute_tools(state, tool_node=mock_tool_node)
        assert result == {}

    async def test_empty_messages_returns_empty(self):
        """Empty messages list returns empty dict."""
        mock_tool_node = AsyncMock()
        state = {"messages": [], "total_tool_calls": 0}

        result = await _execute_tools(state, tool_node=mock_tool_node)
        assert result == {}

    async def test_tool_call_limit_exceeded_returns_limit_message(self):
        """When current + new calls > MAX_TOOL_CALLS, returns ToolMessages (not AIMessage)."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "t1", "args": {}, "id": "tc1"},
                {"name": "t2", "args": {}, "id": "tc2"},
                {"name": "t3", "args": {}, "id": "tc3"},
            ],
        )
        mock_tool_node = AsyncMock()

        state = {"messages": [ai_msg], "total_tool_calls": 49}

        result = await _execute_tools(state, tool_node=mock_tool_node)

        mock_tool_node.ainvoke.assert_not_called()
        # DA-R4-004: returns ToolMessages (one per tool_call) to satisfy protocol
        assert len(result["messages"]) == 3
        for msg in result["messages"]:
            assert isinstance(msg, ToolMessage)
            assert "limit" in msg.content.lower()
        assert result["total_tool_calls"] == MAX_TOOL_CALLS

    async def test_tool_execution_error_returns_graceful_message(self):
        """When tool_node.ainvoke raises, returns ToolMessages with error text."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "t1", "args": {}, "id": "tc1"},
                {"name": "t2", "args": {}, "id": "tc2"},
            ],
        )
        mock_tool_node = AsyncMock()
        mock_tool_node.ainvoke = AsyncMock(side_effect=RuntimeError("tool crash"))

        state = {"messages": [ai_msg], "total_tool_calls": 5}

        result = await _execute_tools(state, tool_node=mock_tool_node)

        # DA-R4-004: returns ToolMessages (one per tool_call) to satisfy protocol
        assert len(result["messages"]) == 2
        for msg in result["messages"]:
            assert isinstance(msg, ToolMessage)
            assert "issue" in msg.content.lower()
        assert result["total_tool_calls"] == 7  # 5 + 2 (attempts always count)

    async def test_graph_interrupt_propagates(self):
        """GraphBubbleUp exceptions (from interrupt()) propagate — not caught as errors."""
        from langgraph.errors import GraphInterrupt
        from langgraph.types import Interrupt

        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "request_clarification", "args": {}, "id": "tc1"}],
        )
        mock_tool_node = AsyncMock()
        mock_tool_node.ainvoke = AsyncMock(
            side_effect=GraphInterrupt(
                interrupts=(Interrupt(value={"type": "clarification"}, resumable=True, ns=(), when="during"),)
            )
        )

        state = {"messages": [ai_msg], "total_tool_calls": 0}

        import pytest as _pytest

        with _pytest.raises(GraphInterrupt):
            await _execute_tools(state, tool_node=mock_tool_node)

    async def test_normal_tool_execution_succeeds(self):
        """Normal (non-interrupt) tool execution returns result and increments counter."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "sql_query", "args": {"q": "SELECT 1"}, "id": "tc1"}],
        )
        mock_tool_node = AsyncMock()
        mock_tool_node.ainvoke = AsyncMock(
            return_value={"messages": [ToolMessage(content="1", tool_call_id="tc1", name="sql_query")]}
        )

        state = {"messages": [ai_msg], "total_tool_calls": 0}

        result = await _execute_tools(state, tool_node=mock_tool_node)

        mock_tool_node.ainvoke.assert_called_once()
        assert result["total_tool_calls"] == 1

    # TE-R2-004: boundary tests for MAX_TOOL_CALLS pre-check
    @pytest.mark.parametrize(
        "current_total,new_calls,should_reject",
        [
            (49, 1, False),  # Exactly at limit (50) — should ALLOW
            (50, 1, True),  # Over limit (51) — should REJECT
            (48, 3, True),  # Over limit (51) — should REJECT
            (50, 0, False),  # At limit with 0 new — edge case, no tool_calls so returns {}
        ],
    )
    async def test_tool_call_limit_boundary(self, current_total, new_calls, should_reject):
        """Boundary conditions for MAX_TOOL_CALLS limit pre-check."""
        tool_calls = [{"name": f"t{i}", "args": {}, "id": f"tc{i}"} for i in range(new_calls)]
        # When new_calls=0, AIMessage has no tool_calls → early return {}
        ai_msg = AIMessage(content="", tool_calls=tool_calls) if tool_calls else AIMessage(content="done")
        mock_tool_node = AsyncMock()
        tool_msg = ToolMessage(content="ok", tool_call_id="tc0", name="t0")
        mock_tool_node.ainvoke = AsyncMock(return_value={"messages": [tool_msg]})

        state = {"messages": [ai_msg], "total_tool_calls": current_total}

        result = await _execute_tools(state, tool_node=mock_tool_node)

        if new_calls == 0:
            # No tool_calls on message → early return {}
            assert result == {}
            mock_tool_node.ainvoke.assert_not_called()
        elif should_reject:
            # Over limit → reject with ToolMessages, don't execute
            mock_tool_node.ainvoke.assert_not_called()
            assert result["total_tool_calls"] == MAX_TOOL_CALLS
            # DA-R4-004: returns ToolMessages (one per tool_call)
            assert len(result["messages"]) == new_calls
            for msg in result["messages"]:
                assert isinstance(msg, ToolMessage)
                assert "limit" in msg.content.lower()
        else:
            # Under or at limit → execute normally
            mock_tool_node.ainvoke.assert_called_once()
            assert result["total_tool_calls"] == current_total + new_calls


# ---------------------------------------------------------------------------
# Tests: _text_requests_user_input detection
# ---------------------------------------------------------------------------


class TestTextRequestsUserInput:
    """Test the question-detection helper."""

    @pytest.mark.parametrize(
        "text",
        [
            "Which project would you like to export?",
            "Please specify the data type.",
            "Let me know your preference.",
            "Would you like tasks or projects?",
            "Do you want to export members?",
            "Here are some things I can help with:\n- Export tasks\n- Show projects",
            "What should I do?\n- Option A\n- Option B",
            "Info.\n\nDo you prefer CSV or Excel?",
        ],
    )
    def test_detects_questions(self, text):
        assert _text_requests_user_input(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Here are the results from your project.",
            "Task PROJ-1 has been updated to Done.",
            "I found 3 tasks in the Web Redesign project.",
            "No matching documents found.",
            "",
            "OK",
            "Export completed successfully.",
            "I searched your projects and found 2 results.",
        ],
    )
    def test_does_not_detect_statements(self, text):
        assert _text_requests_user_input(text) is False


# ---------------------------------------------------------------------------
# Tests: _extract_clarification
# ---------------------------------------------------------------------------


class TestExtractClarification:
    def test_extracts_options_from_bullets(self):
        text = "What would you like to do?\n- Show tasks\n- Export data\n- Search docs"
        question, options = _extract_clarification(text)
        assert "What would you like to do?" in question
        assert options is not None
        assert len(options) == 3
        assert "Show tasks" in options

    def test_extracts_numbered_options(self):
        text = "Pick one:\n1. Tasks\n2. Projects\n3. Members"
        question, options = _extract_clarification(text)
        assert options is not None
        assert len(options) == 3
        assert "Tasks" in options

    def test_no_options_returns_none(self):
        text = "What project do you mean?"
        question, options = _extract_clarification(text)
        assert question == text
        assert options == []

    def test_caps_at_five_options(self):
        lines = ["Choose:\n"] + [f"- Option {i}" for i in range(10)]
        text = "\n".join(lines)
        _, options = _extract_clarification(text)
        assert len(options) > 0
        assert len(options) == 5


# ---------------------------------------------------------------------------
# Tests: auto-conversion in _agent_node
# ---------------------------------------------------------------------------


class TestAgentNodeAutoConvertQuestion:
    async def test_text_question_converted_to_tool_call(self):
        """When LLM responds with a text question, it's auto-converted to
        request_clarification tool call."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Which project would you like?"))

        state = {
            "messages": [HumanMessage(content="do something")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }

        result = await _agent_node(
            state,
            bound_model_cache=[mock_model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        response = result["messages"][0]
        assert isinstance(response, AIMessage)
        assert response.tool_calls
        assert response.tool_calls[0]["name"] == "request_clarification"
        assert "project" in response.tool_calls[0]["args"]["question"].lower()

    async def test_text_with_options_extracted(self):
        """Bullet-list options in the text are extracted into the tool call args."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="What would you like?\n- Show tasks\n- Export data")
        )

        state = {
            "messages": [HumanMessage(content="help")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }

        result = await _agent_node(
            state,
            bound_model_cache=[mock_model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        tc = result["messages"][0].tool_calls[0]
        assert tc["name"] == "request_clarification"
        assert "options" in tc["args"]
        assert "Show tasks" in tc["args"]["options"]

    async def test_normal_response_not_converted(self):
        """A normal text response without questions is left as-is."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="Here are your 3 tasks in the project."))

        state = {
            "messages": [HumanMessage(content="show tasks")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }

        result = await _agent_node(
            state,
            bound_model_cache=[mock_model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        response = result["messages"][0]
        assert response.content == "Here are your 3 tasks in the project."
        assert not getattr(response, "tool_calls", None)

    async def test_tool_calls_response_not_converted(self):
        """A response with tool_calls is never converted, even if content has '?'."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="Looking up your data?",
                tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
            )
        )

        state = {
            "messages": [HumanMessage(content="show tasks")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }

        result = await _agent_node(
            state,
            bound_model_cache=[mock_model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        response = result["messages"][0]
        assert response.tool_calls[0]["name"] == "list_tasks"

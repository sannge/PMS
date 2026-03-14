"""Unit tests for the explore node (app.ai.agent.nodes.explore).

Tests cover:
- Normal LLM call with classification context
- Safety limits (MAX_LLM_CALLS, MAX_ITERATIONS)
- Empty cache handling
- Auto-clarify conversion
- Context management (strip completed, sanitize orphaned)
- Explore suffix building from classification
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.ai.agent.constants import get_max_iterations, get_max_llm_calls
from app.ai.agent.nodes.explore import (
    _build_explore_suffix,
    _extract_clarification,
    _text_requests_user_input,
    execute_tools,
    explore_node,
)


# ---------------------------------------------------------------------------
# Tests: _build_explore_suffix
# ---------------------------------------------------------------------------


class TestBuildExploreSuffix:

    def test_builds_suffix_from_classification(self):
        state = {
            "classification": {
                "intent": "info_query",
                "complexity": "moderate",
                "data_sources": ["tasks", "projects"],
                "entities": [{"type": "project", "value": "Alpha"}],
            },
        }
        suffix = _build_explore_suffix(state)
        assert "info_query" in suffix
        assert "moderate" in suffix
        assert "tasks, projects" in suffix
        assert "project: Alpha" in suffix

    def test_no_classification_returns_empty(self):
        state = {}
        suffix = _build_explore_suffix(state)
        assert suffix == ""

    def test_empty_classification_uses_defaults(self):
        """Empty classification dict uses default values for all fields."""
        state = {"classification": {}}
        suffix = _build_explore_suffix(state)
        assert "unknown" in suffix
        assert "none specified" in suffix
        assert "none identified" in suffix

    def test_partial_classification_uses_defaults(self):
        """Classification with only some fields uses defaults for missing ones."""
        state = {"classification": {"intent": "info_query"}}
        suffix = _build_explore_suffix(state)
        assert "info_query" in suffix
        assert "none specified" in suffix  # no data_sources
        assert "none identified" in suffix  # no entities

    def test_uncertainty_note_when_clarify_exhausted(self):
        """DA-R3: When clarify rounds exhausted and confidence still low, adds uncertainty note."""
        from app.ai.agent.constants import MAX_CLARIFY_ROUNDS

        state = {
            "classification": {
                "intent": "needs_clarification",
                "confidence": 0.3,
                "data_sources": [],
                "entities": [],
            },
            "clarify_count": MAX_CLARIFY_ROUNDS,
        }
        suffix = _build_explore_suffix(state)
        assert "ambiguous" in suffix.lower()
        assert "assumptions" in suffix.lower()

    def test_no_uncertainty_note_when_clarify_not_exhausted(self):
        """No uncertainty note when clarify rounds are not exhausted."""
        state = {
            "classification": {
                "intent": "needs_clarification",
                "confidence": 0.3,
                "data_sources": [],
                "entities": [],
            },
            "clarify_count": 0,
        }
        suffix = _build_explore_suffix(state)
        assert "ambiguous" not in suffix.lower()

    def test_no_uncertainty_note_when_confidence_high(self):
        """No uncertainty note when confidence is above threshold (even with max clarify rounds)."""
        from app.ai.agent.constants import MAX_CLARIFY_ROUNDS

        state = {
            "classification": {
                "intent": "info_query",
                "confidence": 0.8,
                "data_sources": ["tasks"],
                "entities": [],
            },
            "clarify_count": MAX_CLARIFY_ROUNDS,
        }
        suffix = _build_explore_suffix(state)
        assert "ambiguous" not in suffix.lower()

    def test_no_uncertainty_note_when_max_clarify_rounds_zero(self):
        """DA3-HIGH-002: When MAX_CLARIFY_ROUNDS=0 (clarify disabled), no uncertainty note fires."""
        from unittest.mock import patch

        state = {
            "classification": {
                "intent": "needs_clarification",
                "confidence": 0.3,
                "data_sources": [],
                "entities": [],
            },
            "clarify_count": 0,  # No clarification was ever attempted
        }
        # Even with MAX_CLARIFY_ROUNDS=0, the note should NOT fire because
        # clarify_count=0 means clarification was never attempted.
        with patch("app.ai.agent.nodes.explore.get_max_clarify_rounds", return_value=0):
            suffix = _build_explore_suffix(state)
        assert "ambiguous" not in suffix.lower()


# ---------------------------------------------------------------------------
# Tests: explore_node
# ---------------------------------------------------------------------------


class TestExploreNode:

    async def test_normal_call_returns_response(self):
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Here are tasks."))

        state = {
            "messages": [HumanMessage(content="Show tasks")],
            "total_llm_calls": 1,
            "iteration_count": 0,
            "classification": {
                "intent": "info_query",
                "complexity": "simple",
                "data_sources": ["tasks"],
                "entities": [],
            },
        }

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )

        assert result["messages"][0].content == "Here are tasks."
        assert result["total_llm_calls"] == 2
        assert result["iteration_count"] == 1
        assert result["current_phase"] == "explore"

    async def test_safety_limit_llm(self):
        model = AsyncMock()
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": get_max_llm_calls(),
            "iteration_count": 0,
        }

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=[""],
        )

        assert "processing limit" in result["messages"][0].content
        model.ainvoke.assert_not_called()

    async def test_safety_limit_iteration(self):
        model = AsyncMock()
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 0,
            "iteration_count": get_max_iterations(),
        }

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=[""],
        )

        assert "processing limit" in result["messages"][0].content

    async def test_empty_cache_returns_error(self):
        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }

        result = await explore_node(
            state,
            bound_model_cache=[],
            chat_model_cache=[],
            system_prompt_cache=[""],
        )

        assert "not initialized" in result["messages"][0].content

    async def test_llm_error_returns_graceful_message(self):
        model = AsyncMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))

        state = {
            "messages": [HumanMessage(content="query")],
            "total_llm_calls": 0,
            "iteration_count": 0,
        }

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=[""],
        )

        assert "error" in result["messages"][0].content.lower()
        assert result["total_llm_calls"] == 1

    async def test_auto_clarify_converts_question(self):
        """Text question auto-converted to request_clarification tool call."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Which project would you like?")
        )

        state = {
            "messages": [HumanMessage(content="do something")],
            "total_llm_calls": 0,
            "iteration_count": 0,
            "auto_clarify_attempted": False,
        }

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        response = result["messages"][0]
        assert response.tool_calls
        assert response.tool_calls[0]["name"] == "request_clarification"
        assert result["auto_clarify_attempted"] is True

    async def test_auto_clarify_not_repeated(self):
        """Auto-clarify only fires once per turn (auto_clarify_attempted=True)."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(
            return_value=AIMessage(content="Which project would you like?")
        )

        state = {
            "messages": [HumanMessage(content="do something")],
            "total_llm_calls": 0,
            "iteration_count": 0,
            "auto_clarify_attempted": True,  # Already attempted
        }

        result = await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        # Should NOT convert -- just return the text as-is
        response = result["messages"][0]
        assert not getattr(response, "tool_calls", None)
        assert "project" in response.content.lower()

    async def test_classification_context_in_system_prompt(self):
        """explore_node appends classification context to the system prompt."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="done"))

        state = {
            "messages": [HumanMessage(content="Show tasks in Alpha")],
            "total_llm_calls": 0,
            "iteration_count": 0,
            "classification": {
                "intent": "info_query",
                "complexity": "simple",
                "data_sources": ["tasks"],
                "entities": [{"type": "project", "value": "Alpha"}],
            },
        }

        await explore_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=["You are Blair."],
        )

        # Check that the system prompt includes classification context
        call_args = model.ainvoke.call_args[0][0]
        system_msg = call_args[0]
        assert "info_query" in system_msg.content
        assert "tasks" in system_msg.content


# ---------------------------------------------------------------------------
# Tests: execute_tools
# ---------------------------------------------------------------------------


class TestExecuteToolsExplore:

    async def test_counts_tool_calls(self):
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

        result = await execute_tools(state, tool_node=mock_tool_node)

        assert result["total_tool_calls"] == 7  # 5 + 2

    async def test_graph_interrupt_propagates(self):
        from langgraph.errors import GraphInterrupt
        from langgraph.types import Interrupt

        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "create_task", "args": {}, "id": "tc1"}],
        )
        mock_tool_node = AsyncMock()
        mock_tool_node.ainvoke = AsyncMock(
            side_effect=GraphInterrupt(
                interrupts=(Interrupt(value={"type": "confirmation"}, resumable=True, ns=(), when="during"),)
            )
        )

        state = {"messages": [ai_msg], "total_tool_calls": 0}

        with pytest.raises(GraphInterrupt):
            await execute_tools(state, tool_node=mock_tool_node)


# ---------------------------------------------------------------------------
# Tests: _text_requests_user_input (moved from graph.py)
# ---------------------------------------------------------------------------


class TestTextRequestsUserInput:

    @pytest.mark.parametrize("text", [
        "Which project would you like to export?",
        "Please specify the data type.",
        "Let me know your preference.",
    ])
    def test_detects_questions(self, text):
        assert _text_requests_user_input(text) is True

    @pytest.mark.parametrize("text", [
        "Here are the results.",
        "Task updated.",
        "",
        "OK",
    ])
    def test_does_not_detect_statements(self, text):
        assert _text_requests_user_input(text) is False


# ---------------------------------------------------------------------------
# Tests: _extract_clarification (moved from graph.py)
# ---------------------------------------------------------------------------


class TestExtractClarification:

    def test_extracts_bullet_options(self):
        text = "What would you like to do?\n- Show tasks\n- Export data"
        question, options = _extract_clarification(text)
        assert "What would you like to do?" in question
        assert len(options) == 2

    def test_no_options_returns_empty(self):
        text = "What project do you mean?"
        question, options = _extract_clarification(text)
        assert question == text
        assert options == []

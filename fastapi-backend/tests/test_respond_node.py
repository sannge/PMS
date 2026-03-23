"""Unit tests for the respond node (app.ai.agent.nodes.respond).

Tests cover:
- Fast-path (greeting): 1 LLM call, returns response
- Non-fast-path (post-explore): 0 LLM calls, returns immediately with just current_phase
- Empty bound_model_cache fallback to chat_model_cache
- Both caches empty: error message
- LLM exception: graceful error message
- GraphBubbleUp propagation (not caught)
- fast_path=False skips LLM call
- Misclassification recovery: tool_calls -> sets fast_path=False (B5)
- Counter increment only on fast-path LLM call
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai.agent.nodes.respond import respond_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_model(response: AIMessage | None = None):
    """Create a mock model."""
    if response is None:
        response = AIMessage(content="Hello!")
    model = AsyncMock()
    model.ainvoke = AsyncMock(return_value=response)
    return model


# ---------------------------------------------------------------------------
# Tests: respond_node
# ---------------------------------------------------------------------------


class TestRespondNodeFastPath:
    """Test fast-path (greeting/follow-up) behavior."""

    async def test_fast_path_greeting_makes_llm_call(self):
        """Fast-path request makes 1 LLM call and returns response."""
        model = _make_mock_model(AIMessage(content="Hello! I'm Blair."))

        state = {
            "messages": [HumanMessage(content="Hi!")],
            "fast_path": True,
            "total_llm_calls": 1,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )

        assert result["messages"][0].content == "Hello! I'm Blair."
        assert result["total_llm_calls"] == 2  # 1 (understand) + 1 (respond)
        assert result["current_phase"] == "respond"
        model.ainvoke.assert_called_once()

    async def test_fast_path_counter_incremented(self):
        """Fast-path LLM call increments total_llm_calls."""
        model = _make_mock_model(AIMessage(content="Sure!"))

        state = {
            "messages": [HumanMessage(content="Thanks")],
            "fast_path": True,
            "total_llm_calls": 5,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )

        assert result["total_llm_calls"] == 6


class TestRespondNodePostExplore:
    """Test non-fast-path (post-explore/post-synthesize) behavior."""

    async def test_non_fast_path_skips_llm_call(self):
        """Post-explore: 0 LLM calls, returns just current_phase."""
        model = _make_mock_model()

        state = {
            "messages": [
                HumanMessage(content="Show tasks"),
                AIMessage(content="Here are 3 tasks."),
            ],
            "fast_path": False,
            "total_llm_calls": 4,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )

        assert result == {"current_phase": "respond"}
        model.ainvoke.assert_not_called()

    async def test_fast_path_false_skips_llm_call(self):
        """fast_path=False explicitly skips the LLM call."""
        model = _make_mock_model()

        state = {
            "messages": [AIMessage(content="Done.")],
            "fast_path": False,
            "total_llm_calls": 3,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )

        assert result == {"current_phase": "respond"}
        model.ainvoke.assert_not_called()

    async def test_missing_fast_path_defaults_false(self):
        """Missing fast_path in state defaults to False (post-explore path)."""
        model = _make_mock_model()

        state = {
            "messages": [AIMessage(content="Results.")],
            "total_llm_calls": 2,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[model],
            system_prompt_cache=["test"],
        )

        assert result == {"current_phase": "respond"}
        model.ainvoke.assert_not_called()


class TestRespondNodeCacheFallback:
    """Test model cache fallback behavior."""

    async def test_empty_bound_model_falls_back_to_chat_model(self):
        """When bound_model_cache is empty, falls back to chat_model_cache."""
        chat_model = _make_mock_model(AIMessage(content="Fallback response."))

        state = {
            "messages": [HumanMessage(content="Hi")],
            "fast_path": True,
            "total_llm_calls": 0,
        }

        result = await respond_node(
            state,
            bound_model_cache=[],
            chat_model_cache=[chat_model],
            system_prompt_cache=["test"],
        )

        assert result["messages"][0].content == "Fallback response."
        chat_model.ainvoke.assert_called_once()

    async def test_both_caches_empty_returns_error(self):
        """When both caches are empty, returns an error message."""
        state = {
            "messages": [HumanMessage(content="Hi")],
            "fast_path": True,
            "total_llm_calls": 0,
        }

        result = await respond_node(
            state,
            bound_model_cache=[],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        assert "not initialized" in result["messages"][0].content
        assert result["current_phase"] == "respond"


class TestRespondNodeErrors:
    """Test error handling."""

    async def test_llm_exception_returns_graceful_error(self):
        """When LLM call raises, returns a graceful error message."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("provider timeout"))

        state = {
            "messages": [HumanMessage(content="Hi")],
            "fast_path": True,
            "total_llm_calls": 0,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        assert "error" in result["messages"][0].content.lower()
        assert result["current_phase"] == "respond"
        assert result["total_llm_calls"] == 1

    async def test_graph_bubble_up_propagates(self):
        """GraphBubbleUp exceptions propagate (not caught as errors)."""
        from langgraph.errors import GraphInterrupt
        from langgraph.types import Interrupt

        model = AsyncMock()
        model.ainvoke = AsyncMock(
            side_effect=GraphInterrupt(interrupts=(Interrupt(value={}, resumable=True, ns=(), when="during"),))
        )

        state = {
            "messages": [HumanMessage(content="Hi")],
            "fast_path": True,
            "total_llm_calls": 0,
        }

        with pytest.raises(GraphInterrupt):
            await respond_node(
                state,
                bound_model_cache=[model],
                chat_model_cache=[],
                system_prompt_cache=["test"],
            )


class TestRespondNodeMisclassification:
    """Test misclassification recovery (B5)."""

    async def test_tool_calls_sets_fast_path_false(self):
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
        assert result["messages"][0].tool_calls
        assert result["total_llm_calls"] == 2

    async def test_normal_text_response_no_fast_path_clear(self):
        """Normal text response does NOT set fast_path in result."""
        model = _make_mock_model(AIMessage(content="Hello!"))

        state = {
            "messages": [HumanMessage(content="Hi")],
            "fast_path": True,
            "total_llm_calls": 1,
        }

        result = await respond_node(
            state,
            bound_model_cache=[model],
            chat_model_cache=[],
            system_prompt_cache=["test"],
        )

        # fast_path should NOT be in the result for normal responses
        assert "fast_path" not in result
        assert result["messages"][0].content == "Hello!"

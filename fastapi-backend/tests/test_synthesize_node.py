"""Unit tests for the synthesize node (app.ai.agent.nodes.synthesize).

Tests cover:
- Normal synthesis from research context
- Empty cache handling
- LLM error handling
- Counter increments
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.ai.agent.nodes.synthesize import synthesize_node


# ---------------------------------------------------------------------------
# Tests: synthesize_node
# ---------------------------------------------------------------------------


class TestSynthesizeNode:

    async def test_normal_synthesis(self):
        model = AsyncMock()
        model.ainvoke = AsyncMock(
            return_value=AIMessage(content="| Metric | Alpha | Beta |\n| Tasks | 12 | 8 |")
        )

        state = {
            "messages": [
                HumanMessage(content="Compare Alpha and Beta"),
                AIMessage(content="Alpha has 12 tasks."),
                AIMessage(content="Beta has 8 tasks."),
            ],
            "total_llm_calls": 4,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["current_phase"] == "synthesize"
        assert result["total_llm_calls"] == 5
        assert len(result["messages"]) == 1
        assert "Alpha" in result["messages"][0].content

    async def test_empty_cache_no_crash(self):
        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 3,
        }

        result = await synthesize_node(state, chat_model_cache=[])

        assert result["current_phase"] == "synthesize"
        assert result["total_llm_calls"] == 3  # Not incremented (no call made)
        assert "messages" not in result
        # DA-R3: synthesize_count NOT incremented on empty cache
        assert "synthesize_count" not in result

    async def test_llm_error_handled(self):
        model = AsyncMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))

        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 3,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["current_phase"] == "synthesize"
        assert result["total_llm_calls"] == 4  # Incremented (call attempted)
        assert "messages" not in result
        # DA-R3: synthesize_count NOT incremented on LLM error
        assert "synthesize_count" not in result

    async def test_empty_response_no_message(self):
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content=""))

        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 3,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["total_llm_calls"] == 4
        assert result["messages"] == []

    async def test_no_research_context(self):
        """When there are no assistant messages to synthesize, still works."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="No data available."))

        state = {
            "messages": [HumanMessage(content="Compare things")],
            "total_llm_calls": 2,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["total_llm_calls"] == 3
        assert len(result["messages"]) == 1

    async def test_increments_from_existing_counter(self):
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="summary"))

        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 10,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["total_llm_calls"] == 11

    async def test_synthesize_count_incremented(self):
        """B3: synthesize_count is incremented in the result."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="summary"))

        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 3,
            "synthesize_count": 0,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["synthesize_count"] == 1

    async def test_synthesize_count_incremented_from_existing(self):
        """B3: synthesize_count increments from existing state value."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="summary"))

        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 3,
            "synthesize_count": 1,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["synthesize_count"] == 2

    async def test_graph_bubble_up_propagates(self):
        """GraphBubbleUp exceptions propagate (not caught as errors).

        Uses GraphInterrupt which is a subclass of GraphBubbleUp.
        The isinstance(exc, GraphBubbleUp) check in synthesize_node
        correctly catches and re-raises all GraphBubbleUp subclasses.
        """
        from langgraph.errors import GraphInterrupt
        from langgraph.types import Interrupt

        model = AsyncMock()
        model.ainvoke = AsyncMock(
            side_effect=GraphInterrupt(
                interrupts=(Interrupt(value={}, resumable=True, ns=(), when="during"),)
            )
        )

        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 3,
        }

        with pytest.raises(GraphInterrupt):
            await synthesize_node(state, chat_model_cache=[model])

    async def test_synthesize_count_not_incremented_on_error(self):
        """DA-R3: synthesize_count NOT incremented on LLM error."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))

        state = {
            "messages": [AIMessage(content="data")],
            "total_llm_calls": 3,
            "synthesize_count": 1,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        # synthesize_count should NOT be in result (not incremented)
        assert "synthesize_count" not in result

    async def test_uses_research_accumulator(self):
        """DA-R3: synthesize_node prefers research.tool_results accumulator over messages."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Synthesized."))

        state = {
            "messages": [HumanMessage(content="Compare projects")],
            "total_llm_calls": 3,
            "research": {
                "tool_results": [
                    {"tool": "list_projects", "result": "Alpha: 12 tasks"},
                    {"tool": "get_project_details", "result": "Beta: 8 tasks"},
                ],
            },
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        # Verify the model was called with context from the accumulator
        call_args = model.ainvoke.call_args[0][0]
        human_msg = call_args[1]  # Second message is HumanMessage with research
        assert "list_projects" in human_msg.content
        assert "Alpha: 12 tasks" in human_msg.content
        assert "get_project_details" in human_msg.content

    async def test_falls_back_to_messages_when_no_accumulator(self):
        """DA-R3: Falls back to message scan when research.tool_results is empty."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Synthesized."))

        state = {
            "messages": [
                HumanMessage(content="Compare projects"),
                AIMessage(content="", tool_calls=[{"name": "list_projects", "args": {}, "id": "tc1"}]),
                ToolMessage(content="Project Alpha: 12 tasks", tool_call_id="tc1", name="list_projects"),
            ],
            "total_llm_calls": 3,
            "research": {},  # Empty accumulator
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        # Should still find tool content from messages
        call_args = model.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        assert "list_projects" in human_msg.content
        assert "Project Alpha" in human_msg.content

    async def test_research_none_falls_back_to_messages(self):
        """DA3-HIGH-001: When research is not a dict (None), falls back to message scan."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Synthesized."))

        state = {
            "messages": [
                ToolMessage(content="Some data", tool_call_id="tc1", name="list_tasks"),
            ],
            "total_llm_calls": 3,
            "research": None,  # Not a dict
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        # Should fall back to message scan and find the ToolMessage
        call_args = model.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        assert "list_tasks" in human_msg.content

    async def test_research_tool_results_none_falls_back(self):
        """DA3-HIGH-001: When research.tool_results is None, falls back to message scan."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Synthesized."))

        state = {
            "messages": [
                ToolMessage(content="Some data", tool_call_id="tc1", name="list_tasks"),
            ],
            "total_llm_calls": 3,
            "research": {"tool_results": None},  # Explicitly None
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        call_args = model.ainvoke.call_args[0][0]
        human_msg = call_args[1]
        assert "list_tasks" in human_msg.content

    async def test_tool_message_content_included(self):
        """B4: ToolMessage content is included in research context."""
        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Synthesized with tool data."))

        state = {
            "messages": [
                HumanMessage(content="Compare projects"),
                AIMessage(content="", tool_calls=[{"name": "list_projects", "args": {}, "id": "tc1"}]),
                ToolMessage(content="Project Alpha: 12 tasks", tool_call_id="tc1", name="list_projects"),
                AIMessage(content="Alpha has 12 tasks."),
            ],
            "total_llm_calls": 4,
        }

        result = await synthesize_node(state, chat_model_cache=[model])

        assert result["total_llm_calls"] == 5
        # Verify the model was called with context that includes tool results
        call_args = model.ainvoke.call_args[0][0]
        human_msg = call_args[1]  # Second message is HumanMessage with research
        assert "list_projects" in human_msg.content
        assert "Project Alpha" in human_msg.content

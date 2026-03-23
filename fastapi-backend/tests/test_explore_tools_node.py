"""Unit tests for _execute_tools (app.ai.agent.graph).

NOTE (TE-R4-005): This file overlaps with test_agent_graph.py::TestExecuteTools.
Both test _execute_tools but from different angles: test_agent_graph covers the
full graph module (routing, agent_node, execute_tools), while this file focuses
on tool execution edge cases (HITL, pre-check, error handling). The overlap is
intentional — each file is self-contained for its test scope.

Tests cover:
- tool_node.ainvoke called with correct state
- new_calls counter increments from AIMessage.tool_calls
- last message not AIMessage -> empty result
- Tool call limit pre-check (returns limit message)
- HITL interrupt for write tools
- Exception handling in tool execution
- Source accumulator drain on empty tool_results (DA2-F6)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.ai.agent.graph import _execute_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_node(result_messages=None):
    """Create a mock ToolNode that returns given messages."""
    mock = AsyncMock()
    mock.ainvoke = AsyncMock(return_value={"messages": result_messages or []})
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecuteTools:
    async def test_tool_node_invoked_with_state(self):
        """tool_node.ainvoke is called with the correct state."""
        tool_node = _make_tool_node()
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        state = {"messages": [ai_msg], "total_tool_calls": 0}

        await _execute_tools(state, tool_node=tool_node)

        tool_node.ainvoke.assert_called_once_with(state)

    async def test_new_calls_counter_from_tool_calls(self):
        """new_calls counts the tool_calls in the last AIMessage."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "list_tasks", "args": {}, "id": "tc1"},
                {"name": "get_project_details", "args": {}, "id": "tc2"},
            ],
        )
        tool_msg = ToolMessage(content="result", tool_call_id="tc1", name="list_tasks")
        tool_node = _make_tool_node(result_messages=[tool_msg])

        state = {"messages": [ai_msg], "total_tool_calls": 5}

        result = await _execute_tools(state, tool_node=tool_node)

        # 5 existing + 2 new calls
        assert result["total_tool_calls"] == 7

    async def test_no_ai_message_returns_empty(self):
        """When last message is not AIMessage, returns empty dict."""
        tool_node = _make_tool_node()
        state = {"messages": [HumanMessage(content="hello")], "total_tool_calls": 3}

        result = await _execute_tools(state, tool_node=tool_node)

        assert result == {}

    async def test_empty_messages_returns_empty(self):
        """Empty messages list -> returns empty dict."""
        tool_node = _make_tool_node()
        state = {"messages": [], "total_tool_calls": 0}

        result = await _execute_tools(state, tool_node=tool_node)

        assert result == {}


# ---------------------------------------------------------------------------
# Tests: tool call limit pre-check
# ---------------------------------------------------------------------------


class TestExecuteToolsLimitPreCheck:
    async def test_tool_calls_exceed_limit_skips_execution(self):
        """State with total_tool_calls=49 + 3 tool_calls (>50) -> tool_node NOT called."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "t1", "args": {}, "id": "tc1"},
                {"name": "t2", "args": {}, "id": "tc2"},
                {"name": "t3", "args": {}, "id": "tc3"},
            ],
        )
        tool_node = _make_tool_node()

        state = {"messages": [ai_msg], "total_tool_calls": 49}

        result = await _execute_tools(state, tool_node=tool_node)

        # tool_node.ainvoke should NOT be called
        tool_node.ainvoke.assert_not_called()
        # DA-R4-004: returns ToolMessages (one per tool_call) to satisfy protocol
        assert len(result["messages"]) == 3
        for msg in result["messages"]:
            assert isinstance(msg, ToolMessage)
            assert "limit" in msg.content.lower()
        # total_tool_calls set to MAX_TOOL_CALLS (50)
        assert result["total_tool_calls"] == 50


# ---------------------------------------------------------------------------
# Tests: exception handling
# ---------------------------------------------------------------------------


class TestExecuteToolsExceptionHandling:
    async def test_tool_node_runtime_error_returns_graceful_message(self):
        """When tool_node.ainvoke raises RuntimeError, returns ToolMessages with error."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "t1", "args": {}, "id": "tc1"},
                {"name": "t2", "args": {}, "id": "tc2"},
            ],
        )
        tool_node = AsyncMock()
        tool_node.ainvoke = AsyncMock(side_effect=RuntimeError("tool crash"))

        state = {"messages": [ai_msg], "total_tool_calls": 5}

        result = await _execute_tools(state, tool_node=tool_node)

        # DA-R4-004: returns ToolMessages (one per tool_call) to satisfy protocol
        assert len(result["messages"]) == 2
        for msg in result["messages"]:
            assert isinstance(msg, ToolMessage)
            assert "issue" in msg.content.lower() or "error" in msg.content.lower()
        # Failed tool call attempts always count toward limit
        assert result["total_tool_calls"] == 7


# ---------------------------------------------------------------------------
# Tests: HITL interrupt for write tools
# ---------------------------------------------------------------------------


class TestExecuteToolsHITL:
    async def test_graph_interrupt_propagates_not_caught(self):
        """GraphInterrupt from tools (e.g. request_clarification) propagates."""
        import pytest as _pytest
        from langgraph.errors import GraphInterrupt
        from langgraph.types import Interrupt

        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "request_clarification", "args": {}, "id": "tc1"}],
        )
        tool_node = AsyncMock()
        tool_node.ainvoke = AsyncMock(
            side_effect=GraphInterrupt(
                interrupts=(Interrupt(value={"type": "clarification"}, resumable=True, ns=(), when="during"),)
            )
        )
        state = {"messages": [ai_msg], "total_tool_calls": 0}

        with _pytest.raises(GraphInterrupt):
            await _execute_tools(state, tool_node=tool_node)

    async def test_read_tool_no_interrupt(self):
        """Read-only tools execute normally without interrupt."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "sql_query", "args": {"q": "SELECT 1"}, "id": "tc1"}],
        )
        tool_msg = ToolMessage(content="1", tool_call_id="tc1", name="sql_query")
        tool_node = _make_tool_node(result_messages=[tool_msg])

        state = {"messages": [ai_msg], "total_tool_calls": 0}

        result = await _execute_tools(state, tool_node=tool_node)

        tool_node.ainvoke.assert_called_once()
        assert result["total_tool_calls"] == 1


# ---------------------------------------------------------------------------
# Tests: source accumulator drain (DA2-F6)
# ---------------------------------------------------------------------------


class TestExecuteToolsSourceDrain:
    async def test_sources_populated_when_tool_results_empty(self):
        """DA2-F6: drain_accumulated_sources populates research["sources"]
        even when tool_results is empty (no ToolMessages returned)."""
        from app.ai.agent.nodes.explore import execute_tools
        from app.ai.agent.source_references import reset_source_accumulator, _source_accumulator

        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "side_effect_tool", "args": {}, "id": "tc1"}],
        )
        # Tool node returns NO ToolMessages (empty result)
        tool_node = _make_tool_node(result_messages=[])

        state = {"messages": [ai_msg], "total_tool_calls": 0}

        # Pre-populate the source accumulator as if a tool pushed sources
        reset_source_accumulator()
        fake_source = {
            "document_id": "doc1",
            "document_title": "Test Doc",
            "document_type": "document",
            "heading_context": None,
            "chunk_text": "test content",
            "chunk_index": 0,
            "score": 0.9,
            "source_type": "semantic",
        }
        _source_accumulator.get([]).append(fake_source)

        result = await execute_tools(state, tool_node=tool_node)

        # research["sources"] should be populated even with no tool_results
        assert "research" in result
        assert "sources" in result["research"]
        assert len(result["research"]["sources"]) == 1
        assert result["research"]["sources"][0]["document_id"] == "doc1"

        # Clean up
        _source_accumulator.set([])

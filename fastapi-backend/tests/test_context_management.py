"""Unit tests for context management functions in graph.py.

Tests cover:
- _strip_completed_tool_messages: single completed group, multiple groups,
  in-progress preserved, short messages (<=3), knowledge tool preservation
- _sanitize_orphaned_tool_calls: orphaned IDs removed, matched IDs kept, mixed
- _maybe_summarize: under threshold returns unchanged, over threshold summarizes,
  timeout returns unchanged, exception returns unchanged, GraphBubbleUp propagates,
  short messages (<=recent_window) returns unchanged
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.ai.agent.graph import (
    _maybe_summarize,
    _sanitize_orphaned_tool_calls,
    _strip_completed_tool_messages,
)


# ---------------------------------------------------------------------------
# Tests: _strip_completed_tool_messages
# ---------------------------------------------------------------------------


class TestStripCompletedToolMessages:

    def test_single_completed_group_stripped(self):
        """A single completed tool turn (AI+tool_calls -> ToolMessages -> AI+content)
        has the AI+tool_calls and ToolMessages stripped, but closing AI kept."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}]),
            ToolMessage(content="result", tool_call_id="tc1"),
            AIMessage(content="Based on results"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Based on results"

    def test_multiple_completed_groups_stripped(self):
        """Multiple completed tool groups are all stripped."""
        messages = [
            HumanMessage(content="Hello"),
            # Group 1
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "t1", "args": {}}]),
            ToolMessage(content="r1", tool_call_id="tc1"),
            AIMessage(content="Summary 1"),
            # Group 2
            AIMessage(content="", tool_calls=[{"id": "tc2", "name": "t2", "args": {}}]),
            ToolMessage(content="r2", tool_call_id="tc2"),
            AIMessage(content="Summary 2"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 3
        assert result[0].content == "Hello"
        assert result[1].content == "Summary 1"
        assert result[2].content == "Summary 2"

    def test_in_progress_turn_preserved(self):
        """An in-progress turn (AI+tool_calls -> ToolMessages with no closing AI)
        is fully preserved."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}]),
            ToolMessage(content="result", tool_call_id="tc1"),
            # No closing AI message -- in progress
        ]
        # 3 messages is the short-circuit threshold
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 3

    def test_in_progress_turn_preserved_longer(self):
        """In-progress turn preserved when messages > 3."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="preamble"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}]),
            ToolMessage(content="result", tool_call_id="tc1"),
            # No closing AI message -- in progress
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 4  # All preserved

    def test_short_messages_returned_as_is(self):
        """3 or fewer messages are returned unchanged."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 2

    def test_exactly_three_messages_returned_as_is(self):
        """Exactly 3 messages returned as-is (boundary)."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "t1", "args": {}}]),
            ToolMessage(content="r1", tool_call_id="tc1"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 3

    def test_empty_messages(self):
        """Empty list returns empty list."""
        result = _strip_completed_tool_messages([])
        assert result == []

    def test_multiple_tool_messages_in_group(self):
        """A tool group with multiple ToolMessages is stripped correctly."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="", tool_calls=[
                {"id": "tc1", "name": "t1", "args": {}},
                {"id": "tc2", "name": "t2", "args": {}},
            ]),
            ToolMessage(content="r1", tool_call_id="tc1"),
            ToolMessage(content="r2", tool_call_id="tc2"),
            AIMessage(content="Combined results"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Combined results"

    # -- Knowledge tool preservation --

    def test_knowledge_tool_results_preserved_in_closing_message(self):
        """search_knowledge results should be appended to closing AIMessage."""
        messages = [
            HumanMessage(content="Find docs about X"),
            AIMessage(content="", tool_calls=[{"name": "search_knowledge", "id": "tc1", "args": {}}]),
            ToolMessage(content="Found: Document A about X...", name="search_knowledge", tool_call_id="tc1"),
            AIMessage(content="Based on the search, here is what I found..."),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 2  # HumanMessage + closing AIMessage
        assert "[search_knowledge]" in result[1].content
        assert "Document A about X" in result[1].content

    def test_non_knowledge_tool_results_still_stripped(self):
        """Non-knowledge tools should be stripped without preservation."""
        messages = [
            HumanMessage(content="List tasks"),
            AIMessage(content="", tool_calls=[{"name": "list_tasks", "id": "tc1", "args": {}}]),
            ToolMessage(content="Task 1, Task 2, Task 3", name="list_tasks", tool_call_id="tc1"),
            AIMessage(content="Here are your tasks..."),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 2
        assert "Task 1" not in result[1].content
        assert "[Previous knowledge search results]" not in result[1].content

    def test_knowledge_tool_result_truncated_at_limit(self):
        """KB results should be truncated at _KB_RESULT_MAX_CHARS."""
        long_content = "x" * 5000
        messages = [
            HumanMessage(content="Search"),
            AIMessage(content="", tool_calls=[{"name": "search_knowledge", "id": "tc1", "args": {}}]),
            ToolMessage(content=long_content, name="search_knowledge", tool_call_id="tc1"),
            AIMessage(content="Done"),
        ]
        result = _strip_completed_tool_messages(messages)
        # The preserved content should be truncated
        preserved = result[1].content
        assert len(preserved) < len(long_content)

    def test_multiple_knowledge_tools_in_same_turn(self):
        """Multiple KB tools in same group should all be preserved."""
        messages = [
            HumanMessage(content="Research"),
            AIMessage(content="", tool_calls=[
                {"name": "search_knowledge", "id": "tc1", "args": {}},
                {"name": "read_document", "id": "tc2", "args": {}},
            ]),
            ToolMessage(content="Search result A", name="search_knowledge", tool_call_id="tc1"),
            ToolMessage(content="Document content B", name="read_document", tool_call_id="tc2"),
            AIMessage(content="Here is what I found"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert "[search_knowledge]" in result[1].content
        assert "[read_document]" in result[1].content

    def test_empty_knowledge_tool_result_not_preserved(self):
        """KB tool with empty content should not produce a preservation entry."""
        messages = [
            HumanMessage(content="Search"),
            AIMessage(content="", tool_calls=[{"name": "search_knowledge", "id": "tc1", "args": {}}]),
            ToolMessage(content="", name="search_knowledge", tool_call_id="tc1"),
            AIMessage(content="Nothing found"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert "[Previous knowledge search results]" not in result[1].content


# ---------------------------------------------------------------------------
# Tests: _sanitize_orphaned_tool_calls
# ---------------------------------------------------------------------------


class TestSanitizeOrphanedToolCalls:

    def test_orphaned_ids_removed(self):
        """AI messages with tool_calls that have no matching ToolMessage
        are sanitized (tool_calls stripped, content kept)."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(
                content="Let me search",
                tool_calls=[{"name": "search", "args": {}, "id": "orphan_tc"}],
            ),
            HumanMessage(content="Continue"),
        ]
        result = _sanitize_orphaned_tool_calls(messages)
        assert len(result) == 3
        orphaned_ai = result[1]
        assert isinstance(orphaned_ai, AIMessage)
        assert not getattr(orphaned_ai, "tool_calls", None)
        assert orphaned_ai.content == "Let me search"

    def test_matched_ids_kept(self):
        """AI messages with tool_calls that have matching ToolMessages are kept."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"name": "search", "args": {}, "id": "tc1"}],
            ),
            ToolMessage(content="result", tool_call_id="tc1"),
        ]
        result = _sanitize_orphaned_tool_calls(messages)
        assert len(result) == 2
        assert result[0].tool_calls  # Kept
        assert isinstance(result[1], ToolMessage)

    def test_mixed_orphaned_and_matched(self):
        """Mixed: one matched, one orphaned."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}],
            ),
            ToolMessage(content="r1", tool_call_id="tc1"),
            AIMessage(
                content="Let me try",
                tool_calls=[{"name": "t2", "args": {}, "id": "orphan"}],
            ),
        ]
        result = _sanitize_orphaned_tool_calls(messages)
        assert len(result) == 3
        assert result[0].tool_calls  # tc1 matched
        assert isinstance(result[1], ToolMessage)
        assert not getattr(result[2], "tool_calls", None)  # orphan stripped
        assert result[2].content == "Let me try"

    def test_no_tool_calls_unchanged(self):
        """Messages without tool_calls pass through unchanged."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]
        result = _sanitize_orphaned_tool_calls(messages)
        assert len(result) == 2

    def test_empty_messages(self):
        """Empty list returns empty list."""
        result = _sanitize_orphaned_tool_calls([])
        assert result == []


# ---------------------------------------------------------------------------
# Tests: _maybe_summarize
# ---------------------------------------------------------------------------


class TestMaybeSummarize:

    async def test_under_threshold_returns_unchanged(self):
        """Messages under the context threshold are returned unchanged."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]
        model = AsyncMock()
        state = {}

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        assert result_msgs == messages
        assert summary is None
        model.ainvoke.assert_not_called()

    async def test_short_messages_under_recent_window_unchanged(self):
        """Messages <= recent_window are returned unchanged even if chars are high."""
        from app.ai.agent.constants import get_recent_window

        # Create RECENT_WINDOW messages with short content
        messages = [HumanMessage(content=f"msg {i}") for i in range(get_recent_window())]
        model = AsyncMock()
        state = {}

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        assert result_msgs == messages
        assert summary is None

    @patch("app.ai.config_service.get_agent_config")
    async def test_over_threshold_summarizes(self, mock_cfg):
        """Messages over the threshold trigger summarization."""
        # Mock config for low threshold
        cfg_instance = MagicMock()
        cfg_instance.get_int.side_effect = lambda k, d: {
            "agent.context_window": 100,
            "agent.summary_timeout": 30,
        }.get(k, d)
        cfg_instance.get_float.side_effect = lambda k, d: d
        mock_cfg.return_value = cfg_instance

        # Create enough messages to exceed the threshold
        # With context_window=100 and threshold=0.9, threshold=90 tokens
        # Fixed overhead is 40000, so we need messages that push past it
        # Actually let's use a different approach -- mock the char calculation
        messages = [
            HumanMessage(content="Initial question about something"),
            AIMessage(content="Let me check that for you"),
            HumanMessage(content="Thanks"),
            AIMessage(content="Here is what I found"),
        ] + [
            HumanMessage(content="x" * 100000),  # Very large message
        ] + [
            HumanMessage(content=f"Recent msg {i}") for i in range(15)
        ]

        model = AsyncMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Summary of conversation"))
        state = {}

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        # Should have summarized -- model was called
        model.ainvoke.assert_called_once()
        assert summary == "Summary of conversation"
        # First message should be a SystemMessage with summary
        assert isinstance(result_msgs[0], SystemMessage)
        assert "CONVERSATION SUMMARY" in result_msgs[0].content

    @patch("app.ai.config_service.get_agent_config")
    async def test_timeout_returns_unchanged(self, mock_cfg):
        """Timeout during summarization returns messages unchanged."""
        cfg_instance = MagicMock()
        cfg_instance.get_int.side_effect = lambda k, d: {
            "agent.context_window": 100,
            "agent.summary_timeout": 0,  # 0 second timeout -- will always time out
        }.get(k, d)
        cfg_instance.get_float.side_effect = lambda k, d: d
        mock_cfg.return_value = cfg_instance

        messages = [
            HumanMessage(content="x" * 100000),
        ] + [HumanMessage(content=f"msg {i}") for i in range(15)]

        async def slow_invoke(_):
            await asyncio.sleep(10)
            return AIMessage(content="Should not reach here")

        model = AsyncMock()
        model.ainvoke = slow_invoke
        state = {}

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        assert summary is None

    @patch("app.ai.config_service.get_agent_config")
    async def test_exception_returns_unchanged(self, mock_cfg):
        """Non-GraphBubbleUp exception returns messages unchanged."""
        cfg_instance = MagicMock()
        cfg_instance.get_int.side_effect = lambda k, d: {
            "agent.context_window": 100,
            "agent.summary_timeout": 30,
        }.get(k, d)
        cfg_instance.get_float.side_effect = lambda k, d: d
        mock_cfg.return_value = cfg_instance

        messages = [
            HumanMessage(content="x" * 100000),
        ] + [HumanMessage(content=f"msg {i}") for i in range(15)]

        model = AsyncMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))
        state = {}

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        assert summary is None

    @patch("app.ai.config_service.get_agent_config")
    async def test_graph_bubble_up_propagates(self, mock_cfg):
        """GraphBubbleUp exceptions propagate (not swallowed)."""
        from langgraph.errors import GraphInterrupt
        from langgraph.types import Interrupt

        cfg_instance = MagicMock()
        cfg_instance.get_int.side_effect = lambda k, d: {
            "agent.context_window": 100,
            "agent.summary_timeout": 30,
        }.get(k, d)
        cfg_instance.get_float.side_effect = lambda k, d: d
        mock_cfg.return_value = cfg_instance

        messages = [
            HumanMessage(content="x" * 100000),
        ] + [HumanMessage(content=f"msg {i}") for i in range(15)]

        model = AsyncMock()
        model.ainvoke = AsyncMock(
            side_effect=GraphInterrupt(
                interrupts=(Interrupt(value={}, resumable=True, ns=(), when="during"),)
            )
        )
        state = {}

        with pytest.raises(GraphInterrupt):
            await _maybe_summarize(messages, model, state)

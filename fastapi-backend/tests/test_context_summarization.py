"""Unit tests for two-stage context management (context summarization).

Tests cover:
1. _strip_completed_tool_messages — completed turns stripped, current turn preserved
2. _maybe_summarize under threshold — messages not modified
3. _maybe_summarize at threshold — summarization triggered
4. Summary preserves recent window
5. Summary does not split tool_call/ToolMessage pairs
6. Cumulative re-summarization (existing summary + new messages)
7. Edge case: huge single message (recent alone > threshold)
8. _sanitize_orphaned_tool_calls after summarization
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.ai.agent.graph import (
    _maybe_summarize,
    _sanitize_orphaned_tool_calls,
    _strip_completed_tool_messages,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**overrides) -> dict:
    """Build a minimal AgentState-like dict for testing."""
    base = {
        "messages": [],
        "user_id": "test-user",
        "accessible_app_ids": [],
        "accessible_project_ids": [],
        "total_tool_calls": 0,
        "total_llm_calls": 0,
        "iteration_count": 0,
    }
    base.update(overrides)
    return base


def _mock_bound_model(summary_text: str = "This is a summary.") -> MagicMock:
    """Build a mock LLM model that returns a canned summary."""
    model = AsyncMock()
    model.ainvoke = AsyncMock(
        return_value=AIMessage(content=summary_text)
    )
    return model


# ---------------------------------------------------------------------------
# Test 1: _strip_completed_tool_messages
# ---------------------------------------------------------------------------


class TestStripCompletedToolMessages:

    def test_completed_turns_stripped_current_preserved(self):
        """Completed tool turns are stripped; in-progress turn is preserved."""
        messages = [
            HumanMessage(content="Hello"),
            # Completed turn: tool_call -> ToolMessage -> final AIMessage
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}]),
            ToolMessage(content="result1", tool_call_id="tc1"),
            AIMessage(content="Based on the search results..."),
            # Second user turn
            HumanMessage(content="Tell me more"),
            # In-progress turn: tool_call -> ToolMessage (no closing AIMessage yet)
            AIMessage(content="", tool_calls=[{"id": "tc2", "name": "lookup", "args": {}}]),
            ToolMessage(content="result2", tool_call_id="tc2"),
        ]

        result = _strip_completed_tool_messages(messages)

        # The completed turn's AIMessage(tool_calls) and ToolMessage should be gone
        # The closing AIMessage(content) should remain
        assert len(result) == 5  # Human + closing AI + Human + AI(tool_calls) + ToolMessage

        # First message is the original HumanMessage
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hello"

        # Closing AIMessage from completed turn kept
        assert isinstance(result[1], AIMessage)
        assert result[1].content == "Based on the search results..."

        # Second HumanMessage
        assert isinstance(result[2], HumanMessage)
        assert result[2].content == "Tell me more"

        # In-progress turn preserved
        assert isinstance(result[3], AIMessage)
        assert result[3].tool_calls
        assert isinstance(result[4], ToolMessage)

    def test_no_tool_calls_unchanged(self):
        """Messages with no tool calls pass through unchanged."""
        messages = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello!"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 2

    def test_short_messages_unchanged(self):
        """3 or fewer messages are returned as-is."""
        messages = [
            HumanMessage(content="Hi"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "x", "args": {}}]),
            ToolMessage(content="ok", tool_call_id="tc1"),
        ]
        result = _strip_completed_tool_messages(messages)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Test 2: No trim under threshold
# ---------------------------------------------------------------------------


class TestNoTrimUnderThreshold:

    @pytest.mark.asyncio
    async def test_messages_under_threshold_not_modified(self):
        """Messages under the token threshold are returned unchanged."""
        messages = [
            HumanMessage(content="Short message"),
            AIMessage(content="Short reply"),
        ]
        model = _mock_bound_model()
        state = _make_state(messages=messages)

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        assert summary is None
        assert len(result_msgs) == 2
        # LLM should NOT have been called
        model.ainvoke.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Summarize at threshold
# ---------------------------------------------------------------------------


class TestSummarizeAtThreshold:

    @pytest.mark.asyncio
    async def test_messages_at_threshold_trigger_summarization(self):
        """Messages exceeding the token threshold trigger summarization."""
        # Create messages with enough chars to exceed threshold
        # threshold = 128000 * 0.90 = 115200 tokens
        # With FIXED_OVERHEAD=40000, estimated tokens = chars/4 + 40000
        big_content = "x" * 200000  # 50000 tokens from this alone
        messages = [
            HumanMessage(content=big_content),
            AIMessage(content=big_content),
        ] + [
            HumanMessage(content=f"msg {i}") for i in range(15)
        ]

        model = _mock_bound_model("Summarized conversation about X.")
        state = _make_state(messages=messages)

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        assert summary == "Summarized conversation about X."
        # First message should be the summary SystemMessage
        assert isinstance(result_msgs[0], SystemMessage)
        assert "[CONVERSATION SUMMARY]" in result_msgs[0].content
        # LLM was called for summarization
        model.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: Summary preserves recent window
# ---------------------------------------------------------------------------


class TestSummaryPreservesRecentWindow:

    @pytest.mark.asyncio
    async def test_last_n_messages_kept_verbatim(self):
        """The last RECENT_WINDOW messages are kept verbatim after summarization."""
        from app.ai.agent.constants import get_recent_window

        big_content = "x" * 200000
        old_messages = [
            HumanMessage(content=big_content),
            AIMessage(content=big_content),
        ]
        recent_messages = [
            HumanMessage(content=f"recent {i}") for i in range(get_recent_window())
        ]
        all_messages = old_messages + recent_messages

        model = _mock_bound_model("Summary of old stuff.")
        state = _make_state(messages=all_messages)

        result_msgs, summary = await _maybe_summarize(all_messages, model, state)

        assert summary is not None
        # Recent messages should be at the end, verbatim
        for i, msg in enumerate(result_msgs[-get_recent_window():]):
            assert isinstance(msg, HumanMessage)
            assert msg.content == f"recent {i}"


# ---------------------------------------------------------------------------
# Test 5: Summary does not split tool pairs
# ---------------------------------------------------------------------------


class TestSummaryDoesNotSplitToolPairs:

    @pytest.mark.asyncio
    async def test_tool_call_and_tool_message_stay_together(self):
        """Split point walks backward to avoid breaking tool_call/ToolMessage pairs."""
        from app.ai.agent.constants import get_recent_window

        big_content = "x" * 200000
        old_messages = [
            HumanMessage(content=big_content),
            AIMessage(content=big_content),
        ]
        # Place a tool pair right at the potential split boundary
        boundary_messages = [
            AIMessage(content="", tool_calls=[{"id": "tc_boundary", "name": "search", "args": {}}]),
            ToolMessage(content="boundary result", tool_call_id="tc_boundary"),
        ]
        recent_messages = [
            HumanMessage(content=f"recent {i}") for i in range(get_recent_window() - 2)
        ]
        all_messages = old_messages + boundary_messages + recent_messages

        model = _mock_bound_model("Summary.")
        state = _make_state(messages=all_messages)

        result_msgs, summary = await _maybe_summarize(all_messages, model, state)

        # Verify no ToolMessage or AIMessage(tool_calls) appears without its pair
        for i, msg in enumerate(result_msgs):
            if isinstance(msg, ToolMessage):
                # The preceding message must be AIMessage with matching tool_calls
                assert i > 0
                prev = result_msgs[i - 1]
                assert isinstance(prev, AIMessage)
                assert getattr(prev, "tool_calls", None)
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                # Must have matching ToolMessages following
                tc_ids = {tc["id"] for tc in msg.tool_calls}
                following_ids = {
                    m.tool_call_id for m in result_msgs[i + 1:]
                    if isinstance(m, ToolMessage)
                }
                assert tc_ids.issubset(following_ids), (
                    f"AIMessage tool_calls {tc_ids} not matched by following ToolMessages {following_ids}"
                )


# ---------------------------------------------------------------------------
# Test 6: Cumulative re-summarization
# ---------------------------------------------------------------------------


class TestCumulativeResummarization:

    @pytest.mark.asyncio
    async def test_existing_summary_plus_new_messages_updated(self):
        """An existing [CONVERSATION SUMMARY] message gets re-summarized with new content."""
        big_content = "y" * 200000
        messages = [
            SystemMessage(content="[CONVERSATION SUMMARY]\nPrevious summary about tasks."),
            HumanMessage(content=big_content),
            AIMessage(content=big_content),
            HumanMessage(content="new question"),
            AIMessage(content="new answer"),
        ] + [HumanMessage(content=f"extra {i}") for i in range(10)]

        model = _mock_bound_model("Updated summary including previous context and new tasks.")
        state = _make_state(messages=messages)

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        assert summary is not None
        assert "Updated summary" in summary
        # The old summary SystemMessage should be replaced
        summary_msgs = [m for m in result_msgs if isinstance(m, SystemMessage) and "[CONVERSATION SUMMARY]" in str(m.content)]
        assert len(summary_msgs) == 1


# ---------------------------------------------------------------------------
# Test 7: Edge case — huge single message
# ---------------------------------------------------------------------------


class TestEdgeCaseHugeSingleMessage:

    @pytest.mark.asyncio
    async def test_falls_back_if_recent_alone_exceeds_threshold(self):
        """If the recent window alone exceeds the threshold, fall back gracefully."""
        from app.ai.agent.constants import get_recent_window

        # All messages are within the recent window
        huge = "z" * 500000
        messages = [HumanMessage(content=huge)] * get_recent_window()

        model = _mock_bound_model()
        state = _make_state(messages=messages)

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        # Should return messages as-is without summarization
        assert summary is None
        assert len(result_msgs) == get_recent_window()
        model.ainvoke.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8: Orphaned tool_calls sanitized after summarization
# ---------------------------------------------------------------------------


class TestOrphanedToolCallsSanitized:

    def test_orphaned_tool_calls_cleaned(self):
        """AIMessages with tool_calls lacking matching ToolMessages are sanitized."""
        messages = [
            HumanMessage(content="Do something"),
            AIMessage(
                content="Let me search",
                tool_calls=[{"id": "orphan_tc", "name": "search", "args": {}}],
            ),
            # No matching ToolMessage for orphan_tc
            AIMessage(content="Here is the answer."),
        ]

        result = _sanitize_orphaned_tool_calls(messages)

        assert len(result) == 3
        # The orphaned AIMessage should have its tool_calls removed
        orphaned = result[1]
        assert isinstance(orphaned, AIMessage)
        assert not getattr(orphaned, "tool_calls", None)
        assert orphaned.content == "Let me search"

    def test_valid_tool_calls_preserved(self):
        """AIMessages with matching ToolMessages are not modified."""
        messages = [
            HumanMessage(content="Search"),
            AIMessage(
                content="",
                tool_calls=[{"id": "valid_tc", "name": "search", "args": {}}],
            ),
            ToolMessage(content="found it", tool_call_id="valid_tc"),
            AIMessage(content="Here are the results."),
        ]

        result = _sanitize_orphaned_tool_calls(messages)

        assert len(result) == 4
        # The AIMessage with tool_calls should be preserved with tool_calls intact
        ai_with_tc = result[1]
        assert isinstance(ai_with_tc, AIMessage)
        assert len(ai_with_tc.tool_calls) == 1


# ---------------------------------------------------------------------------
# Test 9: Summarization timeout returns original messages
# ---------------------------------------------------------------------------


class TestSummarizationTimeout:

    @pytest.mark.asyncio
    async def test_summarization_timeout_returns_original_messages(self):
        """If the summarization LLM call times out, return messages unchanged."""
        import asyncio as _asyncio

        # Create messages that exceed the threshold so summarization is triggered
        big_content = "x" * 200000
        messages = [
            HumanMessage(content=big_content),
            AIMessage(content=big_content),
        ] + [
            HumanMessage(content=f"msg {i}") for i in range(15)
        ]

        # Mock the model's ainvoke to raise asyncio.TimeoutError
        model = AsyncMock()
        model.ainvoke = AsyncMock(side_effect=_asyncio.TimeoutError())

        state = _make_state(messages=messages)

        result_msgs, summary = await _maybe_summarize(messages, model, state)

        # Verify: returned messages == original messages, summary is None
        assert summary is None
        assert result_msgs == messages
        model.ainvoke.assert_called_once()

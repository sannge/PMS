"""Unit tests for read-only Blair AI agent tools (app.ai.agent.tools).

Tests cover:
- set_tool_context / clear_tool_context lifecycle
- _check_app_access / _check_project_access RBAC helpers
- _resolve_application / _resolve_project fuzzy name resolvers
- _truncate output limiter
- _format_date with date, datetime, None
- _relative_time relative time formatting
- _days_overdue positive result, None when not overdue
- ALL_READ_TOOLS contains 24 tools
- query_knowledge — access denied on invalid app_id, name resolution
- sql_query — wraps sql_query_tool
- get_projects — access denied, name resolution, returns markdown table
- get_tasks — access denied, name resolution on invalid project_id
- get_task_detail — RBAC check, not found case
- get_applications — lists accessible applications
- browse_knowledge — lists documents and folders in a scope
- request_clarification — calls interrupt()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.ai.agent.tools.context import (
    _check_app_access,
    _check_project_access,
    _tool_context,
    clear_tool_context,
    set_tool_context,
)
from app.ai.agent.tools.helpers import (
    _days_overdue,
    _format_date,
    _relative_time,
    _resolve_application,
    _resolve_project,
    _truncate,
)
from app.ai.agent.tools import ALL_READ_TOOLS
from app.ai.agent_tools import MAX_TOOL_OUTPUT_CHARS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_context(**overrides):
    """Populate tool context with sensible defaults + overrides."""
    ctx = {
        "user_id": str(uuid4()),
        "accessible_app_ids": [],
        "accessible_project_ids": [],
        "db_session_factory": MagicMock(),
        "provider_registry": MagicMock(),
    }
    ctx.update(overrides)
    set_tool_context(
        **{
            k: ctx[k]
            for k in (
                "user_id",
                "accessible_app_ids",
                "accessible_project_ids",
                "db_session_factory",
                "provider_registry",
            )
        }
    )
    return ctx


def _clear():
    clear_tool_context()


# ---------------------------------------------------------------------------
# Context lifecycle
# ---------------------------------------------------------------------------


class TestToolContext:
    def test_set_tool_context_populates_dict(self):
        _clear()
        uid = str(uuid4())
        factory = MagicMock()
        registry = MagicMock()

        set_tool_context(
            user_id=uid,
            accessible_app_ids=["a1"],
            accessible_project_ids=["p1"],
            db_session_factory=factory,
            provider_registry=registry,
        )

        assert _tool_context["user_id"] == uid
        assert _tool_context["accessible_app_ids"] == ["a1"]
        assert _tool_context["accessible_project_ids"] == ["p1"]
        assert _tool_context["db_session_factory"] is factory
        assert _tool_context["provider_registry"] is registry
        _clear()

    def test_clear_tool_context_empties_dict(self):
        _setup_context()
        assert len(_tool_context) > 0
        clear_tool_context()
        assert len(_tool_context) == 0


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------


class TestRBACHelpers:
    def test_check_app_access_granted(self):
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[app_id])
        assert _check_app_access(app_id) is True
        _clear()

    def test_check_app_access_denied(self):
        _setup_context(accessible_app_ids=[str(uuid4())])
        assert _check_app_access(str(uuid4())) is False
        _clear()

    def test_check_project_access_granted(self):
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])
        assert _check_project_access(proj_id) is True
        _clear()

    def test_check_project_access_denied(self):
        _setup_context(accessible_project_ids=[])
        assert _check_project_access(str(uuid4())) is False
        _clear()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_text_unchanged(self):
        text = "hello"
        assert _truncate(text) == text

    def test_long_text_truncated(self):
        text = "x" * (MAX_TOOL_OUTPUT_CHARS + 100)
        result = _truncate(text)
        assert len(result) < len(text)
        assert result.endswith("... (output truncated)")

    def test_exact_length_not_truncated(self):
        text = "y" * MAX_TOOL_OUTPUT_CHARS
        assert _truncate(text) == text


class TestEstimateWords:
    """TE-R2-001: Test _estimate_words helper."""

    def test_none_returns_zero(self):
        from app.ai.agent.tools.knowledge_tools import _estimate_words

        assert _estimate_words(None) == 0

    def test_zero_chars_returns_zero(self):
        from app.ai.agent.tools.knowledge_tools import _estimate_words

        assert _estimate_words(0) == 0

    def test_typical_chars(self):
        from app.ai.agent.tools.knowledge_tools import _estimate_words

        assert _estimate_words(500) == 100

    def test_small_count_rounds_down(self):
        from app.ai.agent.tools.knowledge_tools import _estimate_words

        assert _estimate_words(3) == 0


class TestEscapeMd:
    """TE-R2-002: Test _escape_md helper."""

    def test_no_special_chars_unchanged(self):
        from app.ai.agent.tools.knowledge_tools import _escape_md

        assert _escape_md("hello world") == "hello world"

    def test_pipe_escaped(self):
        from app.ai.agent.tools.knowledge_tools import _escape_md

        assert _escape_md("col1 | col2") == "col1 \\| col2"

    def test_multiple_pipes_escaped(self):
        from app.ai.agent.tools.knowledge_tools import _escape_md

        assert _escape_md("a|b|c") == "a\\|b\\|c"

    def test_newlines_replaced_with_space(self):
        from app.ai.agent.tools.knowledge_tools import _escape_md

        assert _escape_md("line1\nline2") == "line1 line2"

    def test_carriage_return_stripped(self):
        from app.ai.agent.tools.knowledge_tools import _escape_md

        assert _escape_md("line1\r\nline2") == "line1 line2"

    def test_combined_pipe_and_newline(self):
        from app.ai.agent.tools.knowledge_tools import _escape_md

        assert _escape_md("a|b\nc|d") == "a\\|b c\\|d"


class TestFormatDate:
    def test_none_returns_dash(self):
        assert _format_date(None) == "\u2014"

    def test_date_returns_iso(self):
        d = date(2026, 1, 15)
        assert _format_date(d) == "2026-01-15"

    def test_datetime_returns_formatted(self):
        dt = datetime(2026, 3, 1, 14, 30, tzinfo=timezone.utc)
        assert _format_date(dt) == "2026-03-01 14:30"


class TestDaysOverdue:
    def test_none_due_date_returns_none(self):
        assert _days_overdue(None) is None

    def test_future_date_returns_none(self):
        future = date(2099, 12, 31)
        assert _days_overdue(future) is None

    def test_past_date_returns_positive_int(self):
        past = date(2020, 1, 1)
        result = _days_overdue(past)
        assert result is not None
        assert result > 0


# ---------------------------------------------------------------------------
# create_read_tools factory
# ---------------------------------------------------------------------------


class TestAllReadTools:
    def test_returns_25_tools(self):
        assert len(ALL_READ_TOOLS) == 25

    def test_tool_names(self):
        names = {t.name for t in ALL_READ_TOOLS}
        expected = {
            # Identity (2)
            "get_my_profile",
            "get_my_workload",
            # Application (3)
            "list_applications",
            "get_application_details",
            "get_application_members",
            # Project (5)
            "list_projects",
            "get_project_details",
            "get_project_members",
            "get_project_timeline",
            "get_overdue_tasks",
            # Task (4)
            "list_tasks",
            "get_task_detail",
            "get_task_comments",
            "get_blocked_tasks",
            # Knowledge (5)
            "search_knowledge",
            "browse_folders",
            "get_document_details",
            "list_recent_documents",
            "get_my_notes",
            # Utility (3)
            "sql_query",
            "understand_image",
            "request_clarification",
            # Web (2)
            "web_search",
            "scrape_url",
            # Capabilities (1)
            "list_capabilities",
        }
        assert names == expected


# ---------------------------------------------------------------------------
# query_knowledge tool
# ---------------------------------------------------------------------------


class TestSearchKnowledge:
    async def test_access_denied_on_invalid_app_id(self):
        """search_knowledge returns not-found when app_id is not accessible."""
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        app_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[], db_session_factory=mock_db_factory)

        result = await search_knowledge.ainvoke({"query": "test", "application": app_id})
        assert "No application found" in result
        _clear()

    async def test_access_denied_on_invalid_project_id(self):
        """search_knowledge returns not-found when project_id is not accessible."""
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        proj_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[], db_session_factory=mock_db_factory)

        result = await search_knowledge.ainvoke({"query": "test", "project": proj_id})
        assert "No project found" in result
        _clear()

    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_pushes_sources_to_accumulator(self, mock_rag):
        """search_knowledge pushes structured sources into the ContextVar accumulator."""
        from app.ai.agent.source_references import (
            get_accumulated_sources,
            reset_source_accumulator,
        )
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        app_id = str(uuid4())
        doc_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        mock_rag.return_value = ToolResult(
            success=True,
            data="[1] Test Doc [Intro] (score: 0.9500, source: semantic)\nhello world\n",
            metadata={
                "result_count": 1,
                "documents": [
                    {
                        "document_id": doc_id,
                        "title": "Test Doc",
                        "score": 0.95,
                        "source": "semantic",
                        "heading_context": "Intro",
                        "chunk_text": "hello world",
                        "application_id": app_id,
                        "chunk_index": 0,
                    }
                ],
            },
        )

        _setup_context(
            accessible_app_ids=[app_id],
            db_session_factory=mock_db_factory,
            provider_registry=MagicMock(),
        )

        reset_source_accumulator()
        await search_knowledge.ainvoke({"query": "test"})

        sources = get_accumulated_sources()
        assert len(sources) == 1
        assert sources[0]["document_id"] == doc_id
        assert sources[0]["application_id"] == app_id
        assert sources[0]["heading_context"] == "Intro"
        assert sources[0]["chunk_text"] == "hello world"
        _clear()

    # -----------------------------------------------------------------------
    # Selection interrupt tests (search_knowledge with 5+ results)
    # -----------------------------------------------------------------------

    @staticmethod
    def _make_docs_meta(count: int) -> list[dict]:
        """Generate mock document metadata dicts for testing."""
        return [
            {
                "document_id": str(uuid4()),
                "title": f"Doc {i + 1}",
                "score": round(0.95 - i * 0.02, 4),
                "source": "semantic",
                "heading_context": f"Section {i + 1}" if i % 2 == 0 else "",
                "chunk_text": f"Content of document {i + 1}. " * 3,
                "application_id": str(uuid4()),
                "chunk_index": i,
            }
            for i in range(count)
        ]

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_below_threshold_no_interrupt(self, mock_rag, mock_interrupt):
        """Below 5 results: no interrupt, returns all chunks normally."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(3)
        mock_rag.return_value = ToolResult(
            success=True,
            data="[1] Doc 1\ncontent\n",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        mock_interrupt.assert_not_called()
        assert "Doc 1" in result
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_above_threshold_triggers_interrupt(self, mock_rag, mock_interrupt):
        """8 results triggers interrupt with type=selection and 8 items."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(8)
        mock_interrupt.return_value = {"selected_indices": list(range(1, 9))}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        await search_knowledge.ainvoke({"query": "auth"})

        mock_interrupt.assert_called_once()
        payload = mock_interrupt.call_args[0][0]
        assert payload["type"] == "selection"
        assert len(payload["items"]) == 8
        for item in payload["items"]:
            assert "index" in item
            assert "title" in item
            assert "snippet" in item
            assert "score" in item
            assert "document_id" in item
        _clear()

    @patch("app.ai.agent.source_references.push_sources")
    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_selection_filters_chunks(self, mock_rag, mock_interrupt, mock_push):
        """Selection of indices [1, 3] returns only those 2 chunks."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(5)
        mock_interrupt.return_value = {"selected_indices": [1, 3]}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        assert "Doc 1" in result
        assert "Doc 3" in result
        assert "Doc 2" not in result
        assert "Doc 4" not in result
        assert "Doc 5" not in result
        # Verify only 2 sources pushed
        mock_push.assert_called_once()
        pushed_sources = mock_push.call_args[0][0]
        assert len(pushed_sources) == 2
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_all_selected_returns_all(self, mock_rag, mock_interrupt):
        """All indices selected returns all chunks."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_interrupt.return_value = {"selected_indices": [1, 2, 3, 4, 5, 6]}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        for i in range(1, 7):
            assert f"Doc {i}" in result
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_skip_returns_rephrase_message(self, mock_rag, mock_interrupt):
        """Skip response returns rephrase message."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(7)
        mock_interrupt.return_value = {"skipped": True}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        assert "rephrase" in result.lower()
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_cap_at_20_items(self, mock_rag, mock_interrupt):
        """25 results caps selection items at 20."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(25)
        mock_interrupt.return_value = {"selected_indices": list(range(1, 21))}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        await search_knowledge.ainvoke({"query": "test"})

        payload = mock_interrupt.call_args[0][0]
        assert len(payload["items"]) == 20
        _clear()

    # -----------------------------------------------------------------------
    # selected_indices validation
    # -----------------------------------------------------------------------

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_non_list_selected_indices_treated_as_empty(self, mock_rag, mock_interrupt):
        """Non-list selected_indices (string, int) is normalised to empty list."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        for bad_value in ("all", 42, True):
            mock_interrupt.return_value = {"selected_indices": bad_value}
            _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
            result = await search_knowledge.ainvoke({"query": "test"})
            assert "deselected all" in result.lower(), f"Failed for selected_indices={bad_value!r}"
            _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_non_integer_items_in_selected_indices_skipped(self, mock_rag, mock_interrupt):
        """List items that cannot be cast to int are silently skipped."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )
        # Only index 2 is valid; "foo", None, 3.5 should be skipped or cast
        mock_interrupt.return_value = {"selected_indices": ["foo", None, 2]}

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        # "foo" and None fail int(), so only Doc 2 should appear
        assert "Doc 2" in result
        assert "Doc 1" not in result
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_out_of_range_indices_ignored(self, mock_rag, mock_interrupt):
        """Indices 0, negative, and > max are silently ignored."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(5)
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )
        # Valid range is 1..5; 0, -1, 99 are all out of range; only 3 is valid
        mock_interrupt.return_value = {"selected_indices": [0, -1, 99, 3]}

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        assert "Doc 3" in result
        assert "Doc 1" not in result
        assert "Doc 5" not in result
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_valid_indices_pass_through(self, mock_rag, mock_interrupt):
        """Valid integer indices within range produce correct filtered output."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )
        mock_interrupt.return_value = {"selected_indices": [2, 4, 6]}

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        assert "Doc 2" in result
        assert "Doc 4" in result
        assert "Doc 6" in result
        assert "Doc 1" not in result
        assert "Doc 3" not in result
        assert "Doc 5" not in result
        _clear()

    # -----------------------------------------------------------------------
    # Empty selection fallthrough
    # -----------------------------------------------------------------------

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_empty_selection_returns_deselected_message(self, mock_rag, mock_interrupt):
        """Empty selected_indices list returns 'deselected all' message."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )
        mock_interrupt.return_value = {"selected_indices": []}

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})

        assert "deselected all" in result.lower()
        _clear()

    # -----------------------------------------------------------------------
    # GraphBubbleUp re-raise
    # -----------------------------------------------------------------------

    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_graph_bubble_up_propagates(self, mock_rag):
        """GraphBubbleUp exceptions must re-raise, not be swallowed."""
        import pytest
        from langgraph.errors import GraphBubbleUp
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        mock_rag.side_effect = GraphBubbleUp()

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)

        with pytest.raises(GraphBubbleUp):
            await search_knowledge.ainvoke({"query": "test"})
        _clear()

    # -----------------------------------------------------------------------
    # Query truncation in interrupt prompt
    # -----------------------------------------------------------------------

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_long_query_truncated_in_prompt(self, mock_rag, mock_interrupt):
        """Queries > 100 chars are truncated with '...' in the interrupt prompt."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_interrupt.return_value = {"selected_indices": [1]}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        long_query = "a" * 150

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        await search_knowledge.ainvoke({"query": long_query})

        payload = mock_interrupt.call_args[0][0]
        prompt = payload["prompt"]
        # Should contain the first 100 chars followed by "..."
        assert "a" * 100 + "..." in prompt
        # Should NOT contain the full 150-char query
        assert "a" * 150 not in prompt
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_short_query_not_truncated_in_prompt(self, mock_rag, mock_interrupt):
        """Queries <= 100 chars appear verbatim in the interrupt prompt."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_interrupt.return_value = {"selected_indices": [1]}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        short_query = "find authentication docs"

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        await search_knowledge.ainvoke({"query": short_query})

        payload = mock_interrupt.call_args[0][0]
        prompt = payload["prompt"]
        assert f"'{short_query}'" in prompt
        assert "..." not in prompt
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_non_dict_response_returns_error(self, mock_rag, mock_interrupt):
        """TE-R2-006: Non-dict interrupt response returns error message."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_interrupt.return_value = "unexpected string response"
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})
        assert "Unexpected response format" in result
        _clear()

    @patch("app.ai.agent.tools.knowledge_tools.interrupt")
    @patch("app.ai.agent_tools.rag_search_tool", new_callable=AsyncMock)
    async def test_malformed_dict_response_returns_error(self, mock_rag, mock_interrupt):
        """TE-R2-006: Dict without skipped or selected_indices returns error."""
        from app.ai.agent_tools import ToolResult
        from app.ai.agent.tools.knowledge_tools import search_knowledge

        docs = self._make_docs_meta(6)
        mock_interrupt.return_value = {"something_else": True}
        mock_rag.return_value = ToolResult(
            success=True,
            data="formatted",
            metadata={"documents": docs},
        )

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(provider_registry=MagicMock(), db_session_factory=mock_db_factory)
        result = await search_knowledge.ainvoke({"query": "test"})
        assert "Unexpected response format" in result
        _clear()


# ---------------------------------------------------------------------------
# _build_sources helper
# ---------------------------------------------------------------------------


class TestBuildSources:
    def test_basic_source_reference_fields(self):
        """_build_sources produces SourceReference objects with correct fields."""
        from app.ai.agent.tools.knowledge_tools import _build_sources

        doc_id = str(uuid4())
        app_id = str(uuid4())
        docs_meta = [
            {
                "document_id": doc_id,
                "title": "My Doc",
                "heading_context": "Introduction",
                "chunk_text": "Hello world",
                "chunk_index": 3,
                "score": 0.87,
                "source": "keyword",
                "application_id": app_id,
            }
        ]

        sources = _build_sources(docs_meta)
        assert len(sources) == 1
        s = sources[0]
        assert s.document_id == doc_id
        assert s.document_title == "My Doc"
        assert s.document_type == "document"
        assert s.heading_context == "Introduction"
        assert s.chunk_text == "Hello world"
        assert s.chunk_index == 3
        assert s.score == 0.87
        assert s.source_type == "keyword"
        assert s.application_id == app_id

    def test_missing_fields_use_defaults(self):
        """Missing keys in docs_meta dict fall back to sensible defaults."""
        from app.ai.agent.tools.knowledge_tools import _build_sources

        docs_meta = [{}]
        sources = _build_sources(docs_meta)
        assert len(sources) == 1
        s = sources[0]
        assert s.document_id == ""
        assert s.document_title == ""
        assert s.document_type == "document"
        assert s.heading_context is None  # empty string becomes None
        assert s.chunk_text == ""
        assert s.chunk_index == 0
        assert s.score == 0.0
        assert s.source_type == "semantic"
        assert s.application_id is None

    def test_none_heading_context_becomes_none(self):
        """Explicit None heading_context is preserved as None."""
        from app.ai.agent.tools.knowledge_tools import _build_sources

        docs_meta = [{"heading_context": None}]
        sources = _build_sources(docs_meta)
        assert sources[0].heading_context is None

    def test_empty_string_heading_becomes_none(self):
        """Empty-string heading_context is normalised to None."""
        from app.ai.agent.tools.knowledge_tools import _build_sources

        docs_meta = [{"heading_context": ""}]
        sources = _build_sources(docs_meta)
        assert sources[0].heading_context is None

    def test_multiple_docs_produce_multiple_sources(self):
        """_build_sources maps each dict to a corresponding SourceReference."""
        from app.ai.agent.tools.knowledge_tools import _build_sources

        docs_meta = [{"document_id": str(uuid4()), "title": f"Doc {i}", "score": 0.9 - i * 0.1} for i in range(4)]
        sources = _build_sources(docs_meta)
        assert len(sources) == 4
        assert sources[0].document_title == "Doc 0"
        assert sources[3].document_title == "Doc 3"

    def test_none_application_id_becomes_none(self):
        """None or missing application_id results in None on the SourceReference."""
        from app.ai.agent.tools.knowledge_tools import _build_sources

        docs_meta = [{"application_id": None}]
        sources = _build_sources(docs_meta)
        assert sources[0].application_id is None

    def test_empty_application_id_becomes_none(self):
        """Empty-string application_id is normalised to None via 'or None'."""
        from app.ai.agent.tools.knowledge_tools import _build_sources

        docs_meta = [{"application_id": ""}]
        sources = _build_sources(docs_meta)
        assert sources[0].application_id is None


# ---------------------------------------------------------------------------
# sql_query tool
# ---------------------------------------------------------------------------


class TestSqlQueryTool:
    @patch("app.ai.agent_tools.sql_query_tool", new_callable=AsyncMock)
    async def test_sql_query_wraps_sql_query_tool(self, mock_sql):
        """sql_query delegates to agent_tools.sql_query_tool."""
        from app.ai.agent.tools.utility_tools import sql_query

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        uid = str(uuid4())
        _setup_context(user_id=uid, db_session_factory=mock_db_factory, provider_registry=MagicMock())

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = "col1\n---\nval1"
        mock_sql.return_value = mock_result

        result = await sql_query.ainvoke({"question": "How many users?"})

        mock_sql.assert_awaited_once()
        assert "val1" in result
        _clear()


# ---------------------------------------------------------------------------
# get_projects tool
# ---------------------------------------------------------------------------


class TestListProjects:
    async def test_access_denied_on_invalid_app_id(self):
        """list_projects returns not-found when app_id is not accessible."""
        from app.ai.agent.tools.project_tools import list_projects

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[], db_session_factory=mock_db_factory)

        result = await list_projects.ainvoke({"app": str(uuid4())})
        assert "No application found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_tasks tool
# ---------------------------------------------------------------------------


class TestListTasks:
    async def test_access_denied_on_invalid_project_id(self):
        """list_tasks returns not-found when project_id is not accessible."""
        from app.ai.agent.tools.task_tools import list_tasks

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[], db_session_factory=mock_db_factory)

        result = await list_tasks.ainvoke({"project": str(uuid4())})
        assert "No project found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_task_detail tool
# ---------------------------------------------------------------------------


class TestGetTaskDetail:
    async def test_task_not_found(self):
        """get_task_detail returns not-found message for missing task."""
        from app.ai.agent.tools.task_tools import get_task_detail

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(db_session_factory=mock_db_factory)

        task_id = str(uuid4())
        result = await get_task_detail.ainvoke({"task": task_id})
        assert "no task found" in result.lower()
        _clear()

    async def test_rbac_denied(self):
        """get_task_detail returns not-found when project not accessible (avoids leaking existence)."""
        from app.ai.agent.tools.task_tools import get_task_detail

        # Set up context with NO accessible projects — _resolve_task returns
        # "No task found matching ..." immediately.
        _setup_context(accessible_project_ids=[])

        result = await get_task_detail.ainvoke({"task": str(uuid4())})
        assert "no task found" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# request_clarification tool
# ---------------------------------------------------------------------------


class TestRequestClarification:
    @patch("app.ai.agent.tools.utility_tools.interrupt")
    async def test_calls_interrupt_and_returns_answer(self, mock_interrupt):
        """request_clarification calls interrupt() and extracts the answer."""
        from app.ai.agent.tools.utility_tools import request_clarification

        mock_interrupt.return_value = {"answer": "Option B"}

        _setup_context()
        result = await request_clarification.ainvoke({"question": "Which option?", "options": ["A", "B"]})

        mock_interrupt.assert_called_once()
        payload = mock_interrupt.call_args[0][0]
        assert payload["type"] == "clarification"
        assert payload["question"] == "Which option?"
        assert "[USER CONTENT START]" in result
        assert "Option B" in result
        assert "[USER CONTENT END]" in result
        _clear()

    @patch("app.ai.agent.tools.utility_tools.interrupt")
    async def test_returns_string_response_as_fallback(self, mock_interrupt):
        """request_clarification handles plain string interrupt responses."""
        from app.ai.agent.tools.utility_tools import request_clarification

        mock_interrupt.return_value = "plain text answer"

        _setup_context()
        result = await request_clarification.ainvoke({"question": "What?"})
        assert "[USER CONTENT START]" in result
        assert "plain text answer" in result
        assert "[USER CONTENT END]" in result
        _clear()


# ---------------------------------------------------------------------------
# get_project_status tool
# ---------------------------------------------------------------------------


class TestGetProjectDetails:
    async def test_access_denied(self):
        """get_project_details returns not-found when project is not accessible."""
        from app.ai.agent.tools.project_tools import get_project_details

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[], db_session_factory=mock_db_factory)

        result = await get_project_details.ainvoke({"project": str(uuid4())})
        assert "No project found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_overdue_tasks tool
# ---------------------------------------------------------------------------


class TestGetOverdueTasks:
    async def test_returns_no_accessible_projects_message(self):
        """get_overdue_tasks returns message when user has no accessible projects."""
        from app.ai.agent.tools.project_tools import get_overdue_tasks

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[], db_session_factory=mock_db_factory)

        result = await get_overdue_tasks.ainvoke({})
        assert "no accessible projects" in result.lower() or "no overdue" in result.lower()
        _clear()

    async def test_access_denied_for_application_scope(self):
        """get_overdue_tasks returns not-found for inaccessible application."""
        from app.ai.agent.tools.project_tools import get_overdue_tasks

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_app_ids=[],
            accessible_project_ids=[str(uuid4())],
            db_session_factory=mock_db_factory,
        )

        result = await get_overdue_tasks.ainvoke({"scope": str(uuid4())})
        assert "No application found" in result
        _clear()


# ---------------------------------------------------------------------------
# get_team_members tool
# ---------------------------------------------------------------------------


class TestGetApplicationMembers:
    async def test_access_denied(self):
        """get_application_members returns not-found when app is not accessible."""
        from app.ai.agent.tools.application_tools import get_application_members

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[], db_session_factory=mock_db_factory)

        result = await get_application_members.ainvoke({"app": str(uuid4())})
        assert "No application found" in result
        _clear()


# ---------------------------------------------------------------------------
# understand_image tool
# ---------------------------------------------------------------------------


class TestUnderstandImage:
    async def test_attachment_not_found(self):
        """understand_image returns not-found when attachment doesn't exist."""
        from app.ai.agent.tools.utility_tools import understand_image

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(db_session_factory=mock_db_factory)

        att_id = str(uuid4())
        result = await understand_image.ainvoke({"attachment_id": att_id})
        assert "not found" in result.lower()
        _clear()

    async def test_returns_result_for_image(self):
        """understand_image returns vision analysis result when given a valid image attachment."""
        from app.ai.agent.tools.utility_tools import understand_image

        att_id = uuid4()
        task_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "diagram.png"
        mock_attachment.minio_bucket = "uploads"
        mock_attachment.minio_key = "abc/diagram.png"

        mock_session = AsyncMock()

        # execute() is called twice in the first db session:
        # 1st: attachment lookup, 2nd: task.project_id RBAC lookup
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = project_id
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        call_count = 0

        @asynccontextmanager
        async def mock_db_factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: attachment lookup + RBAC check
                yield mock_session
            else:
                # Second call: vision provider lookup
                yield AsyncMock()

        mock_registry = MagicMock()
        mock_vision_provider = AsyncMock()
        mock_vision_provider.describe_image = AsyncMock(return_value="A flowchart showing the deployment process.")
        mock_registry.get_vision_provider = AsyncMock(return_value=(mock_vision_provider, "gpt-4o"))

        _setup_context(
            user_id=str(uuid4()),
            accessible_project_ids=[str(project_id)],
            db_session_factory=mock_db_factory,
            provider_registry=mock_registry,
        )

        with patch("app.services.minio_service.MinIOService") as mock_minio_cls:
            mock_minio_svc = MagicMock()
            mock_minio_svc.download_file.return_value = b"\x89PNG\x00"
            mock_minio_cls.return_value = mock_minio_svc

            result = await understand_image.ainvoke({"attachment_id": str(att_id), "question": "What is this diagram?"})

        assert "flowchart" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# get_projects — happy-path data formatting
# ---------------------------------------------------------------------------


class TestListProjectsHappyPath:
    async def test_returns_project_data(self):
        """list_projects returns project names in results."""
        from app.ai.agent.tools.project_tools import list_projects

        app_id = str(uuid4())
        proj1_id = uuid4()
        proj2_id = uuid4()

        # Create mock project rows (the new list_projects uses different query patterns)
        mock_row1 = MagicMock()
        mock_row1.id = proj1_id
        mock_row1.name = "Alpha Project"
        mock_row1.archived_at = None
        mock_derived1 = MagicMock()
        mock_derived1.name = "In Progress"
        mock_row1.derived_status = mock_derived1
        mock_row1.member_count = 3
        mock_row1.task_count = 10
        mock_row1.done_count = 3

        mock_row2 = MagicMock()
        mock_row2.id = proj2_id
        mock_row2.name = "Beta Project"
        mock_row2.archived_at = None
        mock_derived2 = MagicMock()
        mock_derived2.name = "Done"
        mock_row2.derived_status = mock_derived2
        mock_row2.member_count = 2
        mock_row2.task_count = 5
        mock_row2.done_count = 5

        mock_session = AsyncMock()

        # The new list_projects may use different query patterns
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = [mock_row1, mock_row2]
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_result.all.return_value = [mock_row1, mock_row2]

        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[app_id], db_session_factory=mock_db_factory)

        result = await list_projects.ainvoke({"app": app_id})

        # Verify project names appear
        assert "Alpha Project" in result
        assert "Beta Project" in result
        _clear()


# ---------------------------------------------------------------------------
# get_task_detail — happy-path data formatting
# ---------------------------------------------------------------------------


class TestGetTaskDetailHappyPath:
    async def test_returns_formatted_task_with_metadata(self):
        """get_task_detail returns a formatted task with title and status."""
        from app.ai.agent.tools.task_tools import get_task_detail

        task_uuid = uuid4()
        proj_id = uuid4()

        mock_task = MagicMock()
        mock_task.id = task_uuid
        mock_task.task_key = "PROJ-42"
        mock_task.title = "Implement Search"
        mock_task.project_id = proj_id
        mock_task.priority = "high"
        mock_task.task_type = "story"
        mock_task.due_date = None
        mock_task.story_points = 5
        mock_task.description = "Add full-text search to the knowledge base"
        mock_task.created_at = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
        mock_task.updated_at = datetime(2026, 2, 20, 14, 30, tzinfo=timezone.utc)
        mock_task.parent = None

        # Mock status
        mock_status = MagicMock()
        mock_status.name = "In Progress"
        mock_task.task_status = mock_status

        # Mock assignee
        mock_assignee = MagicMock()
        mock_assignee.display_name = "Alice Dev"
        mock_task.assignee = mock_assignee

        # Mock reporter
        mock_reporter = MagicMock()
        mock_reporter.display_name = "Bob PM"
        mock_task.reporter = mock_reporter

        # Mock project
        mock_project = MagicMock()
        mock_project.name = "Search Project"
        mock_task.project = mock_project

        # Mock checklists
        mock_item1 = MagicMock()
        mock_item1.is_done = True
        mock_item1.content = "Write unit tests"
        mock_item2 = MagicMock()
        mock_item2.is_done = False
        mock_item2.content = "Add integration tests"
        mock_checklist = MagicMock()
        mock_checklist.title = "Testing Checklist"
        mock_checklist.completed_items = 1
        mock_checklist.total_items = 2
        mock_checklist.items = [mock_item1, mock_item2]
        mock_task.checklists = [mock_checklist]

        # Mock comments, subtasks, attachments
        mock_task.comments = []
        mock_task.subtasks = []
        mock_task.attachments = []

        mock_session = AsyncMock()

        # _resolve_task UUID fast path: returns task_uuid
        resolve_result = MagicMock()
        resolve_result.scalar_one_or_none.return_value = task_uuid

        # get_task_detail full load: returns the mock task
        detail_result = MagicMock()
        detail_result.scalar_one_or_none.return_value = mock_task

        mock_session.execute = AsyncMock(
            side_effect=[
                resolve_result,  # _resolve_task UUID lookup
                detail_result,  # get_task_detail full load
            ]
        )

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_project_ids=[str(proj_id)],
            db_session_factory=mock_db_factory,
        )

        result = await get_task_detail.ainvoke({"task": str(task_uuid)})

        # Verify key fields
        assert "Implement Search" in result
        assert "In Progress" in result
        assert "Alice Dev" in result
        _clear()


# ---------------------------------------------------------------------------
# _relative_time helper
# ---------------------------------------------------------------------------


class TestRelativeTime:
    def test_none_returns_unknown(self):
        assert _relative_time(None) == "unknown"

    def test_today(self):
        now = datetime.now(timezone.utc)
        assert _relative_time(now) == "today"

    def test_yesterday(self):
        from datetime import timedelta

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        assert _relative_time(yesterday) == "yesterday"

    def test_days_ago(self):
        from datetime import timedelta

        three_days = datetime.now(timezone.utc) - timedelta(days=3)
        assert _relative_time(three_days) == "3 days ago"

    def test_weeks_ago(self):
        from datetime import timedelta

        two_weeks = datetime.now(timezone.utc) - timedelta(days=14)
        assert _relative_time(two_weeks) == "2 weeks ago"

    def test_old_date_falls_back_to_format_date(self):
        from datetime import timedelta

        old = datetime.now(timezone.utc) - timedelta(days=60)
        result = _relative_time(old)
        # Should fall back to _format_date which returns YYYY-MM-DD HH:MM
        assert len(result) > 0
        assert result != "unknown"


# ---------------------------------------------------------------------------
# _resolve_application tests
# ---------------------------------------------------------------------------


class TestResolveApplication:
    async def test_valid_uuid_with_access(self):
        """Resolves immediately when identifier is a valid UUID with access."""
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[app_id])
        db = AsyncMock()

        resolved, error = await _resolve_application(app_id, db)
        assert resolved == app_id
        assert error is None
        # No DB query needed for UUID fast path
        db.execute.assert_not_awaited()
        _clear()

    async def test_valid_uuid_without_access(self):
        """Returns not-found for valid UUID without access (avoids leaking existence)."""
        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[])
        db = AsyncMock()

        resolved, error = await _resolve_application(app_id, db)
        assert resolved is None
        assert "No application found" in error
        _clear()

    async def test_name_single_match(self):
        """Resolves name to UUID when exactly one match."""
        app_id = uuid4()
        _setup_context(accessible_app_ids=[str(app_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "PMS Application"
        mock_result.all.return_value = [mock_row]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("PMS", db)
        assert resolved == str(app_id)
        assert error is None
        _clear()

    async def test_name_no_match(self):
        """Returns error when no applications match the name."""
        app_id = uuid4()
        _setup_context(accessible_app_ids=[str(app_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("NonExistent", db)
        assert resolved is None
        assert "No application found" in error
        _clear()

    async def test_name_multiple_matches(self):
        """Returns disambiguation error when multiple apps match."""
        app1 = uuid4()
        app2 = uuid4()
        _setup_context(accessible_app_ids=[str(app1), str(app2)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row1 = MagicMock()
        mock_row1.id = app1
        mock_row1.name = "PM System"
        mock_row2 = MagicMock()
        mock_row2.id = app2
        mock_row2.name = "PM Suite"
        mock_result.all.return_value = [mock_row1, mock_row2]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("PM", db)
        assert resolved is None
        assert "Multiple applications" in error
        assert "PM System" in error
        assert "PM Suite" in error
        _clear()

    async def test_no_accessible_apps(self):
        """Returns error when user has no accessible apps."""
        _setup_context(accessible_app_ids=[])
        db = AsyncMock()

        resolved, error = await _resolve_application("anything", db)
        assert resolved is None
        assert "No application found" in error
        _clear()


# ---------------------------------------------------------------------------
# _resolve_project tests
# ---------------------------------------------------------------------------


class TestResolveProject:
    async def test_valid_uuid_with_access(self):
        """Resolves immediately when identifier is a valid UUID with access."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[proj_id])
        db = AsyncMock()

        resolved, error = await _resolve_project(proj_id, db)
        assert resolved == proj_id
        assert error is None
        db.execute.assert_not_awaited()
        _clear()

    async def test_valid_uuid_without_access(self):
        """Returns not-found for valid UUID without access (avoids leaking existence)."""
        proj_id = str(uuid4())
        _setup_context(accessible_project_ids=[])
        db = AsyncMock()

        resolved, error = await _resolve_project(proj_id, db)
        assert resolved is None
        assert "No project found" in error
        _clear()

    async def test_name_single_match(self):
        """Resolves name to UUID when exactly one match."""
        proj_id = uuid4()
        _setup_context(accessible_project_ids=[str(proj_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = proj_id
        mock_row.name = "Backend API"
        mock_result.all.return_value = [mock_row]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_project("Backend", db)
        assert resolved == str(proj_id)
        assert error is None
        _clear()

    async def test_name_no_match(self):
        """Returns error when no projects match the name."""
        proj_id = uuid4()
        _setup_context(accessible_project_ids=[str(proj_id)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        resolved, error = await _resolve_project("NonExistent", db)
        assert resolved is None
        assert "No project found" in error
        _clear()

    async def test_name_multiple_matches(self):
        """Returns disambiguation error when multiple projects match."""
        proj1 = uuid4()
        proj2 = uuid4()
        _setup_context(accessible_project_ids=[str(proj1), str(proj2)])

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row1 = MagicMock()
        mock_row1.id = proj1
        mock_row1.name = "API v1"
        mock_row2 = MagicMock()
        mock_row2.id = proj2
        mock_row2.name = "API v2"
        mock_result.all.return_value = [mock_row1, mock_row2]
        db.execute.return_value = mock_result

        resolved, error = await _resolve_project("API", db)
        assert resolved is None
        assert "Multiple projects" in error
        assert "API v1" in error
        assert "API v2" in error
        _clear()


# ---------------------------------------------------------------------------
# get_applications tool
# ---------------------------------------------------------------------------


class TestListApplications:
    async def test_no_accessible_apps(self):
        """list_applications returns message when user has no apps."""
        from app.ai.agent.tools.application_tools import list_applications

        _setup_context(accessible_app_ids=[])

        result = await list_applications.ainvoke({})
        assert "no accessible applications" in result.lower() or "no applications" in result.lower()
        _clear()

    async def test_lists_applications(self):
        """list_applications returns app names in results."""
        from app.ai.agent.tools.application_tools import list_applications

        app_id = uuid4()
        user_id = str(uuid4())

        mock_app = MagicMock()
        mock_app.id = app_id
        mock_app.name = "My App"
        mock_app.description = "Test application"
        mock_app.owner_id = uuid4()
        mock_app.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        # list_applications returns (app, member_count, project_count) tuples
        mock_result.all.return_value = [(mock_app, 3, 2)]
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            user_id=user_id,
            accessible_app_ids=[str(app_id)],
            db_session_factory=mock_db_factory,
        )

        result = await list_applications.ainvoke({})
        assert "My App" in result
        _clear()


# ---------------------------------------------------------------------------
# browse_knowledge tool
# ---------------------------------------------------------------------------


class TestBrowseFolders:
    async def test_invalid_scope(self):
        """browse_folders rejects invalid scope values."""
        from app.ai.agent.tools.knowledge_tools import browse_folders

        _setup_context()

        result = await browse_folders.ainvoke({"scope": "global"})
        assert "scope must be" in result.lower() or "invalid" in result.lower()
        _clear()

    async def test_application_scope_missing_scope_id(self):
        """browse_folders requires scope_id for application scope."""
        from app.ai.agent.tools.knowledge_tools import browse_folders

        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(db_session_factory=mock_db_factory)

        result = await browse_folders.ainvoke({"scope": "application"})
        assert "scope_id" in result.lower()
        _clear()

    async def test_access_denied_for_inaccessible_app(self):
        """browse_folders returns not-found for inaccessible application."""
        from app.ai.agent.tools.knowledge_tools import browse_folders

        app_id = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[], db_session_factory=mock_db_factory)

        result = await browse_folders.ainvoke(
            {
                "scope": "application",
                "scope_id": app_id,
            }
        )
        assert "No application found" in result
        _clear()

    async def test_personal_scope(self):
        """browse_folders lists personal documents."""
        from app.ai.agent.tools.knowledge_tools import browse_folders

        user_id = str(uuid4())
        mock_session = AsyncMock()

        # Folder query (empty) — column projection returns .all() not .scalars().all()
        folder_result = MagicMock()
        folder_result.all.return_value = []

        # Doc query (empty)
        doc_result = MagicMock()
        doc_result.all.return_value = []

        # Total docs count
        total_docs_result = MagicMock()
        total_docs_result.scalar.return_value = 0

        # Total folders count
        total_folders_result = MagicMock()
        total_folders_result.scalar.return_value = 0

        mock_session.execute = AsyncMock(
            side_effect=[
                folder_result,
                doc_result,
                total_docs_result,
                total_folders_result,
            ]
        )

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(user_id=user_id, db_session_factory=mock_db_factory)

        result = await browse_folders.ainvoke({"scope": "personal"})
        assert "Personal" in result or "personal" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# get_projects with name resolution
# ---------------------------------------------------------------------------


class TestGetProjectsNameResolution:
    async def test_resolves_app_by_name(self):
        """list_projects resolves application name and returns projects."""
        from app.ai.agent.tools.project_tools import list_projects

        app_id = uuid4()
        proj_id = uuid4()

        # Resolver query returns 1 match
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "My App"
        resolver_result.all.return_value = [mock_row]

        # Project query
        mock_proj = MagicMock()
        mock_proj.id = proj_id
        mock_proj.name = "Alpha"
        mock_proj.key = "ALP"
        mock_proj.archived_at = None
        mock_proj.due_date = None
        mock_proj.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_derived = MagicMock()
        mock_derived.name = "In Progress"
        mock_proj.derived_status = mock_derived

        proj_result = MagicMock()
        proj_scalars = MagicMock()
        proj_unique = MagicMock()
        proj_unique.all.return_value = [mock_proj]
        proj_scalars.unique.return_value = proj_unique
        proj_result.scalars.return_value = proj_scalars

        # Aggregation query
        mock_agg = MagicMock()
        mock_agg.project_id = proj_id
        mock_agg.total_tasks = 5
        mock_agg.done_tasks = 2
        agg_result = MagicMock()
        agg_scalars = MagicMock()
        agg_scalars.all.return_value = [mock_agg]
        agg_result.scalars.return_value = agg_scalars

        # Member counts query
        mem_result = MagicMock()
        mem_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                resolver_result,
                proj_result,
                agg_result,
                mem_result,
            ]
        )

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[str(app_id)], db_session_factory=mock_db_factory)

        result = await list_projects.ainvoke({"app": "My App"})
        assert "Alpha" in result
        assert "2/5" in result
        _clear()


# ---------------------------------------------------------------------------
# get_tasks with name resolution
# ---------------------------------------------------------------------------


class TestGetTasksNameResolution:
    async def test_resolves_project_by_name(self):
        """list_tasks resolves project name and returns tasks."""
        from app.ai.agent.tools.task_tools import list_tasks

        proj_id = uuid4()

        # Resolver query returns 1 match
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = proj_id
        mock_row.name = "Backend API"
        resolver_result.all.return_value = [mock_row]

        # Task query
        mock_task = MagicMock()
        mock_task.task_key = "BE-1"
        mock_task.title = "Fix bug"
        mock_task.priority = "high"
        mock_task.due_date = None
        mock_task.checklists = []
        mock_status = MagicMock()
        mock_status.name = "Todo"
        mock_status.category = "Todo"
        mock_task.task_status = mock_status
        mock_task.assignee = None

        task_result = MagicMock()
        task_scalars = MagicMock()
        task_unique = MagicMock()
        task_unique.all.return_value = [mock_task]
        task_scalars.unique.return_value = task_unique
        task_result.scalars.return_value = task_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                resolver_result,
                task_result,
            ]
        )

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_project_ids=[str(proj_id)], db_session_factory=mock_db_factory)

        result = await list_tasks.ainvoke({"project": "Backend"})
        assert "BE-1" in result
        assert "Fix bug" in result
        _clear()


# ---------------------------------------------------------------------------
# Resolver edge case tests (Round 1 review gaps)
# ---------------------------------------------------------------------------


class TestResolverEdgeCases:
    async def test_resolve_application_empty_string(self):
        """Empty string identifier is rejected."""
        _setup_context(accessible_app_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_application("", db)
        assert resolved is None
        assert "cannot be empty" in error
        _clear()

    async def test_resolve_project_empty_string(self):
        """Empty string identifier is rejected."""
        _setup_context(accessible_project_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_project("", db)
        assert resolved is None
        assert "cannot be empty" in error
        _clear()

    async def test_resolve_application_whitespace_only(self):
        """Whitespace-only identifier is rejected."""
        _setup_context(accessible_app_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_application("   ", db)
        assert resolved is None
        assert "cannot be empty" in error
        _clear()

    async def test_resolve_application_too_long(self):
        """Identifier exceeding 255 chars is rejected."""
        _setup_context(accessible_app_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_application("A" * 256, db)
        assert resolved is None
        assert "too long" in error
        _clear()

    async def test_resolve_project_too_long(self):
        """Identifier exceeding 255 chars is rejected."""
        _setup_context(accessible_project_ids=[str(uuid4())])
        db = AsyncMock()
        resolved, error = await _resolve_project("A" * 256, db)
        assert resolved is None
        assert "too long" in error
        _clear()

    async def test_resolve_application_wildcard_escaped(self):
        """Percent and underscore are escaped before ILIKE query."""
        app_id = uuid4()
        _setup_context(accessible_app_ids=[str(app_id)])
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute.return_value = mock_result

        resolved, error = await _resolve_application("test%100_app", db)
        assert resolved is None
        # Ensure db was queried (ILIKE search + available names fallback)
        assert db.execute.await_count >= 1
        _clear()

    async def test_resolve_project_no_accessible(self):
        """Returns error when user has no accessible projects (name path)."""
        _setup_context(accessible_project_ids=[])
        db = AsyncMock()
        resolved, error = await _resolve_project("anything", db)
        assert resolved is None
        assert "No project found" in error
        db.execute.assert_not_awaited()
        _clear()


# ---------------------------------------------------------------------------
# get_task_detail — invalid UUID
# ---------------------------------------------------------------------------


class TestGetTaskDetailInvalidUuid:
    async def test_invalid_uuid_returns_error(self):
        """get_task_detail returns user-friendly error for non-UUID identifier."""
        from app.ai.agent.tools.task_tools import get_task_detail

        mock_session = AsyncMock()

        # _resolve_task skips UUID path (ValueError), does:
        # 1. task_key exact match (scalar_one_or_none -> None)
        # 2. title ILIKE search (all -> [])
        key_result = MagicMock()
        key_result.scalar_one_or_none.return_value = None
        title_result = MagicMock()
        title_result.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[key_result, title_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_project_ids=[str(uuid4())],
            db_session_factory=mock_db_factory,
        )

        result = await get_task_detail.ainvoke({"task": "not-a-uuid"})
        assert "no task found" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# browse_knowledge — with folders and documents
# ---------------------------------------------------------------------------


class TestBrowseKnowledgeFormatting:
    async def test_with_folders_and_documents(self):
        """browse_folders formats folders and documents correctly."""
        from app.ai.agent.tools.knowledge_tools import browse_folders

        app_id = uuid4()
        folder_id = uuid4()
        doc_id = uuid4()

        mock_session = AsyncMock()

        # Resolver query
        resolver_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = app_id
        mock_row.name = "Test App"
        resolver_result.all.return_value = [mock_row]

        # App name query
        app_name_result = MagicMock()
        app_name_result.scalar_one_or_none.return_value = "Test App"

        # Folder scope check (for folder_id validation)
        folder_check_result = MagicMock()
        mock_folder_check = MagicMock()
        mock_folder_check.id = folder_id
        folder_check_result.scalar_one_or_none.return_value = mock_folder_check

        # Folder query (1 subfolder)
        mock_subfolder = MagicMock()
        mock_subfolder.id = uuid4()
        mock_subfolder.name = "Architecture"
        folder_result = MagicMock()
        folder_result.all.return_value = [mock_subfolder]

        # Doc count per folder
        doc_count_result = MagicMock()
        doc_count_result.all.return_value = [(mock_subfolder.id, 3)]

        # Doc query (1 document) — DB-005: column projection uses .all() not .scalars()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.title = "Setup Guide"
        mock_doc.updated_at = datetime.now(timezone.utc)
        doc_result = MagicMock()
        doc_result.all.return_value = [mock_doc]

        # Total docs count
        total_docs_result = MagicMock()
        total_docs_result.scalar.return_value = 4

        # Total folders count
        total_folders_result = MagicMock()
        total_folders_result.scalar.return_value = 1

        mock_session.execute = AsyncMock(
            side_effect=[
                resolver_result,  # resolver
                app_name_result,  # app name
                folder_check_result,  # folder scope check
                folder_result,  # subfolder list
                doc_count_result,  # doc counts
                doc_result,  # document list
                total_docs_result,  # total docs
                total_folders_result,  # total folders
            ]
        )

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(accessible_app_ids=[str(app_id)], db_session_factory=mock_db_factory)

        result = await browse_folders.ainvoke(
            {
                "scope": "application",
                "scope_id": "Test App",
                "folder_id": str(folder_id),
            }
        )
        assert "Test App" in result
        assert "Architecture" in result
        assert "Setup Guide" in result
        assert "4 document(s)" in result
        _clear()

    async def test_invalid_folder_id(self):
        """browse_folders rejects invalid folder_id."""
        from app.ai.agent.tools.knowledge_tools import browse_folders

        mock_session = AsyncMock()

        # App name query
        app_name_result = MagicMock()
        app_name_result.scalar_one_or_none.return_value = "Test App"
        mock_session.execute = AsyncMock(return_value=app_name_result)

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        app_id = str(uuid4())
        _setup_context(accessible_app_ids=[app_id], db_session_factory=mock_db_factory)

        result = await browse_folders.ainvoke(
            {
                "scope": "application",
                "scope_id": app_id,
                "folder_id": "not-a-uuid",
            }
        )
        assert "Invalid folder_id" in result
        _clear()

    async def test_personal_scope_wrong_user_denied(self):
        """browse_folders denies access to another user's personal scope."""
        from app.ai.agent.tools.knowledge_tools import browse_folders

        user_id = str(uuid4())
        other_user = str(uuid4())
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(user_id=user_id, db_session_factory=mock_db_factory)

        result = await browse_folders.ainvoke(
            {
                "scope": "personal",
                "scope_id": other_user,
            }
        )
        assert "Access denied" in result
        _clear()


# ---------------------------------------------------------------------------
# get_applications — owner role
# ---------------------------------------------------------------------------


class TestGetApplicationsOwnerRole:
    async def test_shows_owner_role(self):
        """list_applications shows 'owner' role when user is the app owner."""
        from app.ai.agent.tools.application_tools import list_applications

        user_id = str(uuid4())
        app_id = uuid4()

        mock_app = MagicMock()
        mock_app.id = app_id
        mock_app.name = "My Owned App"
        mock_app.description = "Test"
        mock_app.owner_id = UUID(user_id)  # Same as current user
        mock_app.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        # list_applications returns (app, member_count, project_count) tuples
        mock_result.all.return_value = [(mock_app, 3, 2)]
        mock_session.execute.return_value = mock_result

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            user_id=user_id,
            accessible_app_ids=[str(app_id)],
            db_session_factory=mock_db_factory,
        )

        result = await list_applications.ainvoke({})
        assert "owner" in result
        assert "My Owned App" in result
        _clear()


# ---------------------------------------------------------------------------
# understand_image — error branch tests (TE R2 gaps 1 & 2)
# ---------------------------------------------------------------------------


class TestUnderstandImageErrorBranches:
    async def test_non_image_file_rejected(self):
        """understand_image rejects non-image file types."""
        from app.ai.agent.tools.utility_tools import understand_image

        att_id = uuid4()
        task_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "application/pdf"
        mock_attachment.file_name = "report.pdf"

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = project_id
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_project_ids=[str(project_id)],
            db_session_factory=mock_db_factory,
        )

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "not an image" in result.lower()
        assert "application/pdf" in result
        _clear()

    async def test_no_storage_reference(self):
        """understand_image rejects attachment with no minio bucket/key."""
        from app.ai.agent.tools.utility_tools import understand_image

        att_id = uuid4()
        task_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "photo.png"
        mock_attachment.minio_bucket = None
        mock_attachment.minio_key = None

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = project_id
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_project_ids=[str(project_id)],
            db_session_factory=mock_db_factory,
        )

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "no storage reference" in result.lower()
        _clear()

    async def test_orphaned_comment_attachment_denied(self):
        """understand_image denies access when comment has no task_id."""
        from app.ai.agent.tools.utility_tools import understand_image

        att_id = uuid4()
        comment_id = uuid4()
        project_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = None
        mock_attachment.comment_id = comment_id
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "orphan.png"

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        # comment lookup returns None task_id (orphaned comment)
        comment_result = MagicMock()
        comment_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(side_effect=[att_result, comment_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_project_ids=[str(project_id)],
            db_session_factory=mock_db_factory,
        )

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "access denied" in result.lower()
        _clear()

    async def test_null_project_id_on_task_attachment_denied(self):
        """understand_image denies access when task has no project_id (deleted task)."""
        from app.ai.agent.tools.utility_tools import understand_image

        att_id = uuid4()
        task_id = uuid4()

        mock_attachment = MagicMock()
        mock_attachment.id = att_id
        mock_attachment.task_id = task_id
        mock_attachment.comment_id = None
        mock_attachment.file_type = "image/png"
        mock_attachment.file_name = "ghost.png"

        mock_session = AsyncMock()
        att_result = MagicMock()
        att_result.scalar_one_or_none.return_value = mock_attachment
        # Task project_id query returns None (task deleted or no project)
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(side_effect=[att_result, task_result])

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_project_ids=[str(uuid4())],
            db_session_factory=mock_db_factory,
        )

        result = await understand_image.ainvoke({"attachment_id": str(att_id)})
        assert "access denied" in result.lower()
        _clear()


class TestGetTasksAssigneeEmailFallback:
    async def test_assignee_name_search_includes_email(self):
        """list_tasks assignee filter resolves user by name/email."""
        from app.ai.agent.tools.task_tools import list_tasks

        proj_id = str(uuid4())
        user_id = uuid4()

        # DB-007: _resolve_user combined email OR display_name query (single execute)
        user_result = MagicMock()
        user_result.all.return_value = [MagicMock(id=user_id, display_name="John Doe", email="john@example.com")]

        # Task query returns empty (no matching tasks)
        task_result = MagicMock()
        task_scalars = MagicMock()
        task_unique = MagicMock()
        task_unique.all.return_value = []
        task_scalars.unique.return_value = task_unique
        task_result.scalars.return_value = task_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                user_result,  # _resolve_user combined query
                task_result,  # list_tasks query
            ]
        )

        @asynccontextmanager
        async def mock_db_factory():
            yield mock_session

        _setup_context(
            accessible_project_ids=[proj_id],
            db_session_factory=mock_db_factory,
        )

        result = await list_tasks.ainvoke(
            {
                "project": proj_id,
                "assignee": "john",
            }
        )

        assert "no tasks found" in result.lower()
        _clear()

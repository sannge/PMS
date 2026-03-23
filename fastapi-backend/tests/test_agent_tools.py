"""Unit tests for AI agent tools (app.ai.agent_tools).

Tests cover:
- sql_query_tool: success path, generation failure, execution failure
- rag_search_tool: results found, no results, exception handling
- export_to_excel_tool: success path, exception handling
- All tools return ToolResult with correct success/error fields
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.ai.agent_tools import (
    export_to_excel_tool,
    rag_search_tool,
    sql_query_tool,
)
from app.schemas.sql_query import ToolResult

# Pre-import lazy modules so @patch can resolve them
import app.ai.sql_generator  # noqa: F401
import app.ai.sql_executor  # noqa: F401


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_db() -> AsyncMock:
    return AsyncMock()


def _mock_registry() -> MagicMock:
    return MagicMock()


@dataclass
class MockRetrievalResult:
    """Mimics the shape returned by HybridRetrievalService.retrieve."""

    document_id: UUID
    document_title: str
    snippet: str
    score: float
    source: str
    chunk_text: str = "Default chunk text for testing."
    heading_context: str | None = None
    chunk_type: str = "text"
    chunk_index: int | None = 0
    application_id: UUID | None = None
    source_type: str = "document"
    file_id: UUID | None = None


@dataclass
class MockGeneratedQuery:
    """Mimics the return value of sql_generator.generate_query."""

    sql: str
    explanation: str
    tables_used: list[str]
    duration_ms: int


@dataclass
class MockQueryResult:
    """Mimics the return value of sql_executor.execute."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    execution_ms: int

    def to_text(self) -> str:
        header = " | ".join(self.columns)
        lines = [header]
        for row in self.rows:
            lines.append(" | ".join(str(row.get(c, "")) for c in self.columns))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests: sql_query_tool
# ---------------------------------------------------------------------------


class TestSqlQueryTool:
    @patch("app.ai.sql_executor.execute")
    @patch("app.ai.sql_generator.generate_query")
    async def test_success_returns_tool_result(self, mock_gen, mock_exec):
        mock_gen.return_value = MockGeneratedQuery(
            sql="SELECT name FROM v_users LIMIT 10",
            explanation="List user names",
            tables_used=["v_users"],
            duration_ms=50,
        )
        mock_exec.return_value = MockQueryResult(
            columns=["name"],
            rows=[{"name": "Alice"}, {"name": "Bob"}],
            row_count=2,
            truncated=False,
            execution_ms=10,
        )

        result = await sql_query_tool(
            question="Who are the users?",
            user_id=uuid4(),
            db=_mock_db(),
            provider_registry=_mock_registry(),
        )

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.data is not None
        assert "Alice" in result.data
        assert result.metadata is not None
        assert result.metadata["sql"] == "SELECT name FROM v_users LIMIT 10"
        assert result.metadata["row_count"] == 2
        assert result.error is None

    @patch("app.ai.sql_generator.generate_query", side_effect=ValueError("Cannot generate"))
    async def test_generation_failure_returns_error(self, _mock_gen):
        result = await sql_query_tool(
            question="bad question",
            user_id=uuid4(),
            db=_mock_db(),
            provider_registry=_mock_registry(),
        )

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.error is not None
        assert "Cannot generate" in result.error

    @patch("app.ai.sql_executor.execute", side_effect=RuntimeError("timeout"))
    @patch("app.ai.sql_generator.generate_query")
    async def test_execution_failure_returns_error(self, mock_gen, _mock_exec):
        mock_gen.return_value = MockGeneratedQuery(
            sql="SELECT 1",
            explanation="test",
            tables_used=[],
            duration_ms=5,
        )

        result = await sql_query_tool(
            question="query",
            user_id=uuid4(),
            db=_mock_db(),
            provider_registry=_mock_registry(),
        )

        assert result.success is False
        assert "timeout" in result.error


# ---------------------------------------------------------------------------
# Tests: rag_search_tool
# ---------------------------------------------------------------------------


class TestRagSearchTool:
    @patch("app.ai.agent_tools.HybridRetrievalService")
    @patch("app.ai.agent_tools.EmbeddingNormalizer")
    async def test_returns_formatted_results(self, _mock_norm, mock_svc_cls):
        mock_svc = AsyncMock()
        mock_svc_cls.return_value = mock_svc

        doc_id = uuid4()
        mock_svc.retrieve.return_value = [
            MockRetrievalResult(
                document_id=doc_id,
                document_title="Getting Started",
                snippet="This document explains how to get started.",
                score=0.92,
                source="semantic",
            ),
        ]

        result = await rag_search_tool(
            query="how to start",
            user_id=uuid4(),
            db=_mock_db(),
            provider_registry=_mock_registry(),
        )

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "Getting Started" in result.data
        assert result.metadata is not None
        assert result.metadata["result_count"] == 1
        assert result.error is None

    @patch("app.ai.agent_tools.HybridRetrievalService")
    @patch("app.ai.agent_tools.EmbeddingNormalizer")
    async def test_no_results_returns_empty_message(self, _mock_norm, mock_svc_cls):
        mock_svc = AsyncMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.retrieve.return_value = []

        result = await rag_search_tool(
            query="nonexistent topic",
            user_id=uuid4(),
            db=_mock_db(),
            provider_registry=_mock_registry(),
        )

        assert result.success is True
        assert result.data == "No relevant documents found."
        assert result.metadata["result_count"] == 0

    @patch("app.ai.agent_tools.HybridRetrievalService")
    @patch("app.ai.agent_tools.EmbeddingNormalizer")
    async def test_exception_returns_error(self, _mock_norm, mock_svc_cls):
        mock_svc = AsyncMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.retrieve.side_effect = ConnectionError("embedding service down")

        result = await rag_search_tool(
            query="anything",
            user_id=uuid4(),
            db=_mock_db(),
            provider_registry=_mock_registry(),
        )

        assert result.success is False
        assert "embedding service down" in result.error

    @patch("app.ai.agent_tools.HybridRetrievalService")
    @patch("app.ai.agent_tools.EmbeddingNormalizer")
    async def test_passes_scope_filters(self, _mock_norm, mock_svc_cls):
        mock_svc = AsyncMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.retrieve.return_value = []

        app_id = uuid4()
        proj_id = uuid4()

        await rag_search_tool(
            query="scoped search",
            user_id=uuid4(),
            db=_mock_db(),
            provider_registry=_mock_registry(),
            application_id=app_id,
            project_id=proj_id,
        )

        call_kwargs = mock_svc.retrieve.call_args.kwargs
        assert call_kwargs["application_id"] == app_id
        assert call_kwargs["project_id"] == proj_id


# ---------------------------------------------------------------------------
# Tests: export_to_excel_tool
# ---------------------------------------------------------------------------


class TestExportToExcelTool:
    @patch("app.ai.excel_export.export_to_excel")
    async def test_success_returns_download_url(self, mock_export):
        from app.ai.excel_export import ExportResult as _ER

        mock_export.return_value = _ER(
            filename="report_abc12345.xlsx",
            download_url="/api/ai/export/report_abc12345.xlsx",
            row_count=5,
        )

        result = await export_to_excel_tool(
            columns=["a", "b"],
            rows=[{"a": 1, "b": 2}],
            title="Report",
            user_id=uuid4(),
        )

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "/api/ai/export/report_abc12345.xlsx" in result.data
        assert result.metadata["filename"] == "report_abc12345.xlsx"
        assert result.metadata["row_count"] == 5
        assert result.error is None

    @patch("app.ai.excel_export.export_to_excel", side_effect=OSError("disk full"))
    async def test_failure_returns_error(self, _mock_export):
        result = await export_to_excel_tool(
            columns=["a"],
            rows=[{"a": 1}],
            title="Fail",
            user_id=uuid4(),
        )

        assert result.success is False
        assert "disk full" in result.error


# ---------------------------------------------------------------------------
# Cross-cutting: success flag consistency
# ---------------------------------------------------------------------------


class TestToolResultConsistency:
    @patch("app.ai.sql_executor.execute")
    @patch("app.ai.sql_generator.generate_query")
    async def test_sql_tool_success_flag(self, mock_gen, mock_exec):
        mock_gen.return_value = MockGeneratedQuery(
            sql="SELECT 1",
            explanation="",
            tables_used=[],
            duration_ms=1,
        )
        mock_exec.return_value = MockQueryResult(
            columns=["x"],
            rows=[{"x": 1}],
            row_count=1,
            truncated=False,
            execution_ms=1,
        )

        result = await sql_query_tool("q", uuid4(), _mock_db(), _mock_registry())
        assert result.success is True
        assert result.error is None

    @patch("app.ai.agent_tools.HybridRetrievalService")
    @patch("app.ai.agent_tools.EmbeddingNormalizer")
    async def test_rag_tool_success_flag(self, _n, mock_cls):
        mock_cls.return_value = AsyncMock(retrieve=AsyncMock(return_value=[]))
        result = await rag_search_tool("q", uuid4(), _mock_db(), _mock_registry())
        assert result.success is True
        assert result.error is None

    @patch("app.ai.excel_export.export_to_excel")
    async def test_export_tool_success_flag(self, mock_exp):
        from app.ai.excel_export import ExportResult as _ER

        mock_exp.return_value = _ER(
            filename="f.xlsx",
            download_url="/api/ai/export/f.xlsx",
            row_count=0,
        )
        result = await export_to_excel_tool([], [], "t", uuid4())
        assert result.success is True
        assert result.error is None

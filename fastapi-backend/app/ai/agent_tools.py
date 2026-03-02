"""Agent tools interface for Phase 4 LangGraph agent.

Provides three tools:
1. sql_query_tool -- NL question -> SQL generation -> validation -> execution
2. rag_search_tool -- Wraps Phase 2 HybridRetrievalService
3. export_to_excel_tool -- Query results -> Excel file -> download URL
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.sql_query import ToolResult
from .embedding_normalizer import EmbeddingNormalizer
from .provider_registry import ProviderRegistry
from .retrieval_service import HybridRetrievalService

logger = logging.getLogger(__name__)

# Max characters for tool output text to prevent token budget overflow
MAX_TOOL_OUTPUT_CHARS = 8000
# Knowledge search returns more content for LLM re-ranking (top-20 chunks)
MAX_KNOWLEDGE_OUTPUT_CHARS = 16000

# Module-level singleton — EmbeddingNormalizer is stateless
_embedding_normalizer = EmbeddingNormalizer()


async def sql_query_tool(
    question: str,
    user_id: UUID,
    db: AsyncSession,
    provider_registry: ProviderRegistry,
    db_factory: Any = None,
) -> ToolResult:
    """Generate SQL from a natural-language question, validate, and execute.

    Pipeline: question -> LLM SQL generation -> sqlglot validation ->
    scoped view execution -> formatted text result.

    Args:
        question: Natural-language question from the user.
        user_id: UUID of the requesting user (for RBAC scoping).
        db: Async database session (used for SQL generation/provider resolution).
        provider_registry: For resolving the chat LLM provider.
        db_factory: Optional async session factory. When provided, execution
            uses a fresh session so SET TRANSACTION READ ONLY succeeds
            (it must be the first statement in a transaction).

    Returns:
        ToolResult with formatted query results or error details.
    """
    from .sql_generator import generate_query
    from .sql_executor import execute as execute_sql

    try:
        # Step 1: Generate SQL from NL question
        # (This may query the DB to resolve the AI provider, which starts
        # the transaction on `db`.)
        generated = await generate_query(question, db, provider_registry)

        # Step 2: Execute the validated SQL in a FRESH session so that
        # SET TRANSACTION READ ONLY is the first statement in the transaction.
        # Falls back to the same session if no factory is provided.
        if db_factory is not None:
            async with db_factory() as exec_db:
                query_result = await execute_sql(generated.sql, user_id, exec_db)
        else:
            query_result = await execute_sql(generated.sql, user_id, db)

        # Step 3: Format results as text for LLM consumption (truncate if huge)
        text_output = query_result.to_text()
        if len(text_output) > MAX_TOOL_OUTPUT_CHARS:
            text_output = text_output[:MAX_TOOL_OUTPUT_CHARS] + "\n\n... (output truncated)"
        metadata: dict[str, Any] = {
            "sql": generated.sql,
            "explanation": generated.explanation,
            "tables_used": generated.tables_used,
            "columns": query_result.columns,
            "row_count": query_result.row_count,
            "truncated": query_result.truncated,
            "generation_ms": generated.duration_ms,
            "execution_ms": query_result.execution_ms,
        }

        return ToolResult(
            success=True,
            data=text_output,
            metadata=metadata,
        )

    except Exception as e:
        logger.warning("sql_query_tool failed: %s: %s", type(e).__name__, e)
        return ToolResult(success=False, error=str(e))


async def rag_search_tool(
    query: str,
    user_id: UUID,
    db: AsyncSession,
    provider_registry: ProviderRegistry,
    application_id: UUID | None = None,
    project_id: UUID | None = None,
    query_embedding_cache: dict[str, list[float]] | None = None,
) -> ToolResult:
    """Search knowledge-base documents using Phase 2 hybrid retrieval.

    Combines semantic (pgvector), keyword (Meilisearch), and fuzzy (pg_trgm)
    search, all RBAC-scoped to the requesting user.

    Args:
        query: Search query string.
        user_id: UUID of the requesting user (for RBAC scoping).
        db: Async database session.
        provider_registry: For generating query embeddings.
        application_id: Optional scope filter.
        project_id: Optional scope filter.

    Returns:
        ToolResult with formatted search results or error details.
    """
    try:
        service = HybridRetrievalService(
            provider_registry=provider_registry,
            normalizer=_embedding_normalizer,
            db=db,
        )

        # Check embedding cache for this query
        cached_embedding: list[float] | None = None
        if query_embedding_cache is not None:
            cached_embedding = query_embedding_cache.get(query)

        results = await service.retrieve(
            query=query,
            user_id=user_id,
            limit=20,
            application_id=application_id,
            project_id=project_id,
            query_embedding=cached_embedding,
        )

        if not results:
            return ToolResult(
                success=True,
                data="No relevant documents found.",
                metadata={"result_count": 0},
            )

        # Format results as text for LLM consumption
        # Use full chunk_text (not truncated snippet) so the agent can answer
        # questions from the actual document content.
        lines: list[str] = []
        for i, r in enumerate(results, 1):
            heading = f" [{r.heading_context}]" if r.heading_context else ""
            type_tag = " [image description]" if r.chunk_type == "image" else ""
            lines.append(f"[{i}] {r.document_title}{heading} (score: {r.score:.4f}, source: {r.source}){type_tag}")
            lines.append(r.chunk_text.strip())
            lines.append("")

        formatted = "\n".join(lines)
        if len(formatted) > MAX_KNOWLEDGE_OUTPUT_CHARS:
            formatted = formatted[:MAX_KNOWLEDGE_OUTPUT_CHARS] + "\n\n... (output truncated)"

        return ToolResult(
            success=True,
            data=formatted,
            metadata={
                "result_count": len(results),
                "documents": [
                    {
                        "document_id": str(r.document_id),
                        "title": r.document_title,
                        "score": r.score,
                        "source": r.source,
                        "heading_context": r.heading_context or "",
                        "chunk_text": r.chunk_text[:200] if r.chunk_text else "",
                        "application_id": str(r.application_id) if r.application_id else "",
                        "chunk_index": r.chunk_index if r.chunk_index is not None else 0,
                    }
                    for r in results
                ],
            },
        )

    except Exception as e:
        logger.warning("rag_search_tool failed: %s: %s", type(e).__name__, e)
        return ToolResult(success=False, error=str(e))


async def export_to_excel_tool(
    columns: list[str],
    rows: list[dict[str, Any]],
    title: str,
    user_id: UUID,
) -> ToolResult:
    """Export query results to an Excel file for download.

    Creates an .xlsx workbook with formatted headers and auto-sized columns,
    then returns a download URL.

    Args:
        columns: Column headers for the spreadsheet.
        rows: List of row dicts (column_name -> value).
        title: Title for the spreadsheet/filename.
        user_id: UUID of the requesting user (for file scoping).

    Returns:
        ToolResult with download URL or error details.
    """
    from .excel_export import export_to_excel

    try:
        export_result = await export_to_excel(
            columns=columns,
            rows=rows,
            title=title,
            user_id=user_id,
        )

        return ToolResult(
            success=True,
            data=f"Excel file ready for download: {export_result.download_url}",
            metadata={
                "filename": export_result.filename,
                "download_url": export_result.download_url,
                "row_count": export_result.row_count,
            },
        )

    except Exception as e:
        logger.warning("export_to_excel_tool failed: %s: %s", type(e).__name__, e)
        return ToolResult(success=False, error=str(e))

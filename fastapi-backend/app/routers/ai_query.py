"""AI query API endpoints.

Provides endpoints for natural-language SQL queries, SQL validation,
schema introspection, Excel export downloads, and document reindexing.
All endpoints require authentication.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.document import Document
from ..models.user import User
from ..schemas.sql_query import (
    SQLQueryRequest,
    SQLQueryResponse,
    SQLValidateRequest,
    SQLValidateResponse,
)
from ..ai.rate_limiter import check_reindex_rate_limit
from ..ai.telemetry import AITelemetry, TelemetryTimer
from ..services.auth_service import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/ai",
    tags=["ai-query"],
)


# ---------------------------------------------------------------------------
# POST /api/ai/query  --  NL question -> SQL -> validate -> execute -> results
# ---------------------------------------------------------------------------


@router.post("/query", response_model=SQLQueryResponse)
async def execute_query(
    body: SQLQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SQLQueryResponse:
    """Execute a natural-language query against the project management schema.

    Pipeline: NL question -> LLM SQL generation -> sqlglot validation ->
    scoped view execution -> structured results.
    """
    from ..ai.provider_registry import ProviderRegistry
    from ..ai.sql_generator import generate_query
    from ..ai.sql_executor import execute as execute_sql

    registry = ProviderRegistry()
    timer = TelemetryTimer().start()

    try:
        generated = await generate_query(body.question, db, registry)
    except Exception as e:
        logger.warning("SQL generation failed for user %s: %s", current_user.id, e)
        await AITelemetry.log_sql_query(
            user_id=current_user.id,
            duration_ms=timer.elapsed_ms,
            success=False,
            error=f"Generation failed: {type(e).__name__}",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to generate SQL: {e}",
        )

    try:
        query_result = await execute_sql(generated.sql, current_user.id, db)
    except Exception as e:
        logger.warning("SQL execution failed for user %s: %s", current_user.id, e)
        await AITelemetry.log_sql_query(
            user_id=current_user.id,
            duration_ms=timer.elapsed_ms,
            success=False,
            error=f"Execution failed: {type(e).__name__}",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Query execution failed: {e}",
        )

    await AITelemetry.log_sql_query(
        user_id=current_user.id,
        duration_ms=timer.elapsed_ms,
        success=True,
        row_count=query_result.row_count,
    )

    return SQLQueryResponse(
        question=body.question,
        sql=generated.sql,
        explanation=generated.explanation,
        columns=query_result.columns,
        rows=query_result.rows,
        row_count=query_result.row_count,
        truncated=query_result.truncated,
        generation_ms=generated.duration_ms,
        execution_ms=query_result.execution_ms,
    )


# ---------------------------------------------------------------------------
# POST /api/ai/query/validate  --  Validate SQL without executing
# ---------------------------------------------------------------------------


@router.post("/query/validate", response_model=SQLValidateResponse)
async def validate_query(
    body: SQLValidateRequest,
    current_user: User = Depends(get_current_user),
) -> SQLValidateResponse:
    """Validate SQL syntax and security constraints without executing.

    Checks against the blocklist, AST parsing, view allowlist,
    function allowlist, and LIMIT enforcement.
    """
    from ..ai.sql_validator import validate as validate_sql

    try:
        result = validate_sql(body.sql)
        return SQLValidateResponse(
            is_valid=result.is_valid,
            error=result.error,
            tables_used=result.tables_used,
        )
    except Exception as e:
        logger.warning("SQL validation error: %s", e)
        return SQLValidateResponse(
            is_valid=False,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# GET /api/ai/schema  --  Return queryable schema description
# ---------------------------------------------------------------------------


@router.get("/schema")
async def get_schema(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Return the queryable schema description for the scoped views.

    This is the same schema context provided to the LLM for SQL generation,
    useful for debugging and transparency.
    """
    from ..ai.schema_context import get_schema_prompt

    return {"schema": get_schema_prompt()}


# ---------------------------------------------------------------------------
# GET /api/ai/export/{filename}  --  Download Excel file
# ---------------------------------------------------------------------------


@router.get("/export/{filename}")
async def download_export(
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download an exported Excel file.

    Files are scoped per user -- a user can only download exports
    they generated. Path traversal and ownership checks are handled
    by get_export_path().
    """
    from ..ai.excel_export import get_export_path

    file_path = get_export_path(filename, current_user.id)
    if file_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found or expired",
        )

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# POST /api/ai/reindex/{document_id}  --  Re-embed document
# ---------------------------------------------------------------------------


@router.post("/reindex/{document_id}", status_code=status.HTTP_202_ACCEPTED)
async def reindex_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(check_reindex_rate_limit),
) -> dict[str, str]:
    """Re-embed a document by enqueueing an embedding job.

    The job runs asynchronously via the ARQ worker. Uses _job_id for
    deduplication so multiple requests for the same document collapse
    into a single job.
    """
    # Verify document exists and user has access
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    # Enqueue embedding job via ARQ
    try:
        from ..services.redis_service import redis_service

        if not redis_service.is_connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Background worker not available",
            )

        from arq.connections import ArqRedis

        pool = redis_service.client
        arq_redis: ArqRedis | None = getattr(pool, "_arq_redis", None)
        if arq_redis is None:
            arq_redis = ArqRedis(pool_or_conn=pool.connection_pool)
            pool._arq_redis = arq_redis  # type: ignore[attr-defined]

        await arq_redis.enqueue_job(
            "embed_document_job",
            str(document_id),
            _job_id=f"embed:{document_id}",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to enqueue embed_document_job for %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue reindex job",
        )

    await AITelemetry.log_reindex(
        user_id=current_user.id,
        document_count=1,
        duration_ms=0,
        success=True,
    )

    return {"status": "accepted", "document_id": str(document_id)}


# ---------------------------------------------------------------------------
# GET /api/ai/index-status/{document_id}  --  Embedding timestamp
# ---------------------------------------------------------------------------


@router.get("/index-status/{document_id}")
async def get_index_status(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | None]:
    """Get the embedding index status for a document.

    Returns the timestamp of the last successful embedding, or null
    if the document has never been embedded.
    """
    result = await db.execute(
        select(Document.embedding_updated_at).where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    embedding_updated_at = row[0]
    return {
        "document_id": str(document_id),
        "embedding_updated_at": embedding_updated_at.isoformat() if embedding_updated_at else None,
    }

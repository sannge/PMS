"""Document search API endpoints.

Provides full-text search via Meilisearch with PostgreSQL FTS fallback,
Redis-backed rate limiting, and RBAC scope filtering.
"""

import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..services.auth_service import get_current_user
from ..services.redis_service import RedisService, get_redis
from ..services.search_service import (
    sanitize_search_query,
    get_cached_scope_filter,
    search_documents,
    search_documents_pg_fallback,
    check_search_health,
    CONTROL_CHAR_RE,
    get_fallback_scope_ids,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["search"])

# Rate limiting: 30 searches per minute per user
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30


@router.get("/search")
async def search_documents_endpoint(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisService = Depends(get_redis),
):
    """Search documents with RBAC filtering via Meilisearch.

    Falls back to PostgreSQL FTS when Meilisearch is unavailable.
    """
    # 1. Sanitize query
    q_clean = sanitize_search_query(q)
    if CONTROL_CHAR_RE.search(q_clean) or len(q_clean) < 2:
        raise HTTPException(400, "Query contains invalid characters or is too short")

    # 2. Rate limiting (Redis-backed, skip if Redis unavailable)
    try:
        rate_key = f"ratelimit:search:{current_user.id}"
        allowed, current_count = await redis.rate_limit_check(
            rate_key, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW
        )
        if not allowed:
            logger.warning(
                "Search rate limit hit: user_id=%s, count=%d",
                current_user.id, current_count,
            )
            raise HTTPException(
                429,
                "Too many search requests. Please wait.",
                headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
            )
    except HTTPException:
        raise  # Re-raise 429
    except Exception:
        logger.warning("Redis unavailable for rate limiting, skipping rate limit check")

    # 3. Get RBAC filter (cached in Redis for 30s)
    filter_expr = await get_cached_scope_filter(redis, db, current_user.id)

    # 4. Try Meilisearch first, fall back to PostgreSQL FTS
    fallback = False
    try:
        results = await search_documents(q_clean, filter_expr, limit, offset)
    except Exception as exc:
        logger.warning("Meilisearch search failed, falling back to PostgreSQL FTS: %s", exc)
        fallback = True

        # Fallback: PostgreSQL FTS
        try:
            app_ids, project_ids = await get_fallback_scope_ids(db, current_user.id)
            results = await search_documents_pg_fallback(
                db, q_clean, app_ids, project_ids, current_user.id, limit, offset
            )
        except Exception as pg_exc:
            logger.error("PostgreSQL FTS fallback also failed: %s", pg_exc)
            raise HTTPException(503, "Search temporarily unavailable")

    # 5. Log successful search
    logger.info(
        "Search: query=%r user_id=%s hits=%d processingTimeMs=%s fallback=%s",
        q_clean,
        current_user.id,
        len(results.get("hits", [])),
        results.get("processingTimeMs", "N/A"),
        fallback,
    )

    return results


@router.get("/search/health")
async def search_health_endpoint(
    current_user: User = Depends(get_current_user),
):
    """Health check for Meilisearch integration. Requires authentication."""
    result = await check_search_health()
    if result["status"] != "healthy":
        return JSONResponse(status_code=503, content=result)
    return result


@router.post("/search/reindex")
async def reindex_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin endpoint to rebuild the entire search index.
    Uses index swap pattern (zero downtime).
    Currently disabled pending admin role implementation.
    """
    raise HTTPException(
        status_code=403,
        detail="Admin access required - not yet implemented",
    )

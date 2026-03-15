"""Redis health gate dependency.

Returns 503 for Redis-critical endpoints when Redis is unavailable.
Skipped entirely when ``redis_required=False`` (single-worker dev mode).
"""

from fastapi import HTTPException, status

from ..config import settings
from ..services.redis_service import redis_service


async def require_redis() -> None:
    """Raise 503 if Redis is required but currently disconnected.

    Applied via ``dependencies=[Depends(require_redis)]`` on routers
    that cannot function without Redis (e.g. document_locks).
    """
    if not settings.redis_required:
        return
    if not redis_service.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Distributed features temporarily unavailable",
            headers={"Retry-After": "10"},
        )

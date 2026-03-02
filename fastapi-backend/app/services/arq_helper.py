"""Helper for obtaining an ArqRedis instance from the shared Redis connection.

Eliminates repeated boilerplate across routers that enqueue ARQ jobs.
Caches the ArqRedis wrapper on the redis_service client object so it
is created once per process.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


async def get_arq_redis() -> Any:
    """Return a cached ArqRedis wrapping the global redis_service client.

    Returns:
        An ``ArqRedis`` instance ready for ``enqueue_job`` calls.

    Raises:
        RuntimeError: If Redis is not connected.
    """
    from .redis_service import redis_service

    if not redis_service.is_connected:
        raise RuntimeError("Redis is not connected — cannot enqueue ARQ jobs")

    from arq.connections import ArqRedis

    pool = redis_service.client
    arq_redis: ArqRedis | None = getattr(pool, "_arq_redis", None)
    if arq_redis is None:
        arq_redis = ArqRedis(pool_or_conn=pool.connection_pool)
        pool._arq_redis = arq_redis  # type: ignore[attr-defined]
    return arq_redis


async def is_embed_job_pending(document_id: UUID | str) -> bool:
    """Check if an embed job is pending or in-progress for a document.

    Returns False if Redis is not connected (graceful degradation).
    """
    from .redis_service import redis_service

    if not redis_service.is_connected:
        return False

    try:
        return bool(await redis_service.client.exists(f"arq:job:embed:{document_id}"))
    except Exception:
        return False


async def batch_embed_jobs_pending(document_ids: list[UUID | str]) -> set[UUID]:
    """Batch-check which documents have pending embed jobs.

    Uses a single Redis pipeline for all checks (1 round-trip).
    Returns a set of document UUIDs that have pending jobs.
    """
    from .redis_service import redis_service

    if not document_ids or not redis_service.is_connected:
        return set()

    try:
        pipe = redis_service.client.pipeline(transaction=False)
        for doc_id in document_ids:
            pipe.exists(f"arq:job:embed:{doc_id}")
        results = await pipe.execute()
        return {
            UUID(str(doc_id)) if not isinstance(doc_id, UUID) else doc_id
            for doc_id, exists in zip(document_ids, results)
            if exists
        }
    except Exception:
        return set()

"""Helper for obtaining an ArqRedis instance from the shared Redis connection.

Eliminates repeated boilerplate across routers that enqueue ARQ jobs.
Uses a module-level asyncio.Lock to safely initialize the cached instance.
"""

from __future__ import annotations

import asyncio
from typing import Any

_cached_arq_redis: Any | None = None
_arq_init_lock = asyncio.Lock()


async def get_arq_redis() -> Any:
    """Return a cached ArqRedis wrapping the global redis_service client.

    Thread-safe: uses asyncio.Lock to prevent race conditions during
    first initialization.

    Returns:
        An ``ArqRedis`` instance ready for ``enqueue_job`` calls.

    Raises:
        RuntimeError: If Redis is not connected.
    """
    global _cached_arq_redis

    if _cached_arq_redis is not None:
        return _cached_arq_redis

    async with _arq_init_lock:
        # Double-check after acquiring lock
        if _cached_arq_redis is not None:
            return _cached_arq_redis

        from .redis_service import redis_service

        if not redis_service.is_connected:
            raise RuntimeError("Redis is not connected — cannot enqueue ARQ jobs")

        from arq.connections import ArqRedis

        pool = redis_service.client
        _cached_arq_redis = ArqRedis(pool_or_conn=pool.connection_pool)
        return _cached_arq_redis

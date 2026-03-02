"""Redis-based rate limiting for AI endpoints.

Uses a sliding window counter pattern backed by Redis sorted sets.
Each request is stored as a member (timestamp) in a sorted set keyed by
``ratelimit:{endpoint}:{scope_id}:{window}``. Expired entries are pruned
on each check, giving accurate per-window counts.

A Lua script executes the check-and-increment atomically in Redis, avoiding
TOCTOU race conditions that could occur with pipelined commands.

Fallback: when Redis is unavailable, an in-memory counter with a generous
limit (2x normal) is used.  This prevents complete bypass while tolerating
brief Redis outages.  A warning is logged on each fallback hit.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from ..models.user import User
from ..services.auth_service import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Redis Lua scripts (executed atomically on the server)
# ---------------------------------------------------------------------------

# Check-and-increment: prune expired, check limit, add only if under limit.
# Returns new count on success, -1 if rate limit exceeded.
_CHECK_AND_INCREMENT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    redis.call('EXPIRE', key, ttl)
    return -1
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return count + 1
"""

# Increment-only: prune expired, add member, return count.
_INCREMENT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local member = ARGV[3]
local ttl = tonumber(ARGV[4])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return redis.call('ZCARD', key)
"""

# Check-only: prune expired, return current count.
_CHECK_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
redis.call('EXPIRE', key, ttl)
return redis.call('ZCARD', key)
"""


# ---------------------------------------------------------------------------
# In-memory fallback counter (used when Redis is unavailable)
# ---------------------------------------------------------------------------

_inmemory_lock = asyncio.Lock()
# { key: [(timestamp, ...)] }  -- list of request timestamps within window
_inmemory_counters: dict[str, list[float]] = {}
# Multiplier for in-memory limits (more generous since less accurate)
_INMEMORY_LIMIT_MULTIPLIER = 2
# Safety limit: clear the entire dict if it grows beyond this many keys
_INMEMORY_MAX_KEYS = 10_000


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class RateLimitResult(BaseModel):
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_at: datetime
    limit: int
    reset_seconds: int


# ---------------------------------------------------------------------------
# Rate limit configuration (env-overridable via Settings)
# ---------------------------------------------------------------------------

# (limit, window_seconds) per endpoint
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "ai_chat": (30, 60),
    "ai_query": (30, 60),
    "ai_embed": (100, 60),
    "ai_import": (10, 3600),
    "ai_reindex": (20, 3600),
    "ai_test": (10, 60),
}


def _load_rate_limits() -> dict[str, tuple[int, int]]:
    """Load rate limits, allowing env-var overrides.

    Environment variables follow the pattern:
        RATE_LIMIT_AI_CHAT=30,60
        RATE_LIMIT_AI_EMBED=100,60
        RATE_LIMIT_AI_IMPORT=10,3600
        RATE_LIMIT_AI_REINDEX=20,3600

    Falls back to ``RATE_LIMITS`` defaults when not set.

    .. note::
        Called once at module import time.  Changes to env vars take
        effect only after a server restart.
    """
    import os

    limits = dict(RATE_LIMITS)
    for key in limits:
        env_key = f"RATE_LIMIT_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val:
            try:
                parts = env_val.split(",")
                limits[key] = (int(parts[0].strip()), int(parts[1].strip()))
            except (IndexError, ValueError):
                logger.warning(
                    "Invalid rate limit env var %s=%s, using default", env_key, env_val
                )
    return limits


# ---------------------------------------------------------------------------
# Core rate limiter
# ---------------------------------------------------------------------------


class AIRateLimiter:
    """Redis-based sliding window rate limiter for AI endpoints.

    Key format: ``ratelimit:{endpoint}:{scope_id}:{window}``

    When Redis is unavailable, falls back to an in-memory counter with
    a generous limit (2x normal) to prevent complete bypass during outages.
    """

    def __init__(self, redis: Any) -> None:
        self.redis = redis
        # Register Lua scripts once per instance (cheap, idempotent)
        if redis is not None:
            self._check_and_inc = redis.register_script(_CHECK_AND_INCREMENT_SCRIPT)
            self._inc = redis.register_script(_INCREMENT_SCRIPT)
            self._check = redis.register_script(_CHECK_SCRIPT)
        else:
            self._check_and_inc = None
            self._inc = None
            self._check = None

    @staticmethod
    async def _inmemory_count_and_add(
        key: str, window_seconds: int, *, add: bool = False
    ) -> int:
        """Return current count in window using in-memory fallback.

        If *add* is True, also records a new request timestamp.
        Prunes expired entries on each call.  If the dict grows beyond
        ``_INMEMORY_MAX_KEYS``, evicts expired entries first, then the
        oldest 25% of remaining keys.
        """
        now = time.time()
        cutoff = now - window_seconds

        async with _inmemory_lock:
            # Safety valve: prevent unbounded memory growth
            if len(_inmemory_counters) > _INMEMORY_MAX_KEYS:
                # BE-P9: Evict expired entries first, then oldest 25%
                expired_keys = [
                    k for k, ts_list in _inmemory_counters.items()
                    if not any(ts > cutoff for ts in ts_list)
                ]
                for k in expired_keys:
                    del _inmemory_counters[k]

                # If still over limit, evict oldest 25%
                if len(_inmemory_counters) > _INMEMORY_MAX_KEYS:
                    evict_count = max(1, len(_inmemory_counters) // 4)
                    sorted_keys = sorted(
                        _inmemory_counters.keys(),
                        key=lambda k: max(_inmemory_counters[k]) if _inmemory_counters[k] else 0,
                    )
                    for k in sorted_keys[:evict_count]:
                        del _inmemory_counters[k]

                logger.warning(
                    "In-memory rate limit counter evicted entries, now %d keys",
                    len(_inmemory_counters),
                )

            timestamps = _inmemory_counters.get(key, [])
            # Prune expired entries
            timestamps = [ts for ts in timestamps if ts > cutoff]
            if add:
                timestamps.append(now)
            _inmemory_counters[key] = timestamps
            return len(timestamps)

    async def _fallback_result(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        *,
        add: bool,
    ) -> RateLimitResult:
        """Build a RateLimitResult from in-memory counters.

        Uses ``_INMEMORY_LIMIT_MULTIPLIER`` times the normal limit as the
        threshold, providing a safety net while being more forgiving than
        the Redis-backed limit (since in-memory counts are per-process).
        """
        fallback_limit = limit * _INMEMORY_LIMIT_MULTIPLIER
        count = await self._inmemory_count_and_add(key, window_seconds, add=add)
        allowed = count <= fallback_limit
        remaining = max(0, fallback_limit - count)
        now = time.time()
        reset_at = datetime.fromtimestamp(now + window_seconds, tz=timezone.utc)

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=fallback_limit,
            reset_seconds=window_seconds,
        )

    async def check_rate_limit(
        self,
        endpoint: str,
        scope_id: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check whether a request is within the rate limit.

        Returns a :class:`RateLimitResult` with ``allowed=True`` if the
        caller has not exceeded *limit* requests in the current sliding
        *window_seconds*.  Uses a Lua script for atomic prune + count.
        """
        key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        ttl = window_seconds + 1

        try:
            current_count: int = await self._check(
                keys=[key], args=[now, window_seconds, ttl]
            )
        except Exception as exc:
            logger.warning("Rate limit Redis unavailable, using in-memory fallback: %s", exc)
            return await self._fallback_result(key, limit, window_seconds, add=False)

        remaining = max(0, limit - current_count)
        allowed = current_count < limit
        reset_at = datetime.fromtimestamp(now + window_seconds, tz=timezone.utc)

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=limit,
            reset_seconds=window_seconds,
        )

    async def check_and_increment(
        self,
        endpoint: str,
        scope_id: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Atomically record a request and check whether it exceeds the limit.

        Uses a Lua script that prunes expired entries, checks the current
        count, and only adds the new member if under the limit -- all in a
        single atomic Redis EVAL.  Returns ``allowed=False`` when the limit
        is reached (the member is NOT added in that case).

        Returns a :class:`RateLimitResult` with ``allowed=True`` if the
        caller (including this request) has not exceeded *limit* in the
        current sliding *window_seconds*.
        """
        key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        ttl = window_seconds + 1

        try:
            result: int = await self._check_and_inc(
                keys=[key], args=[now, window_seconds, limit, member, ttl]
            )
        except Exception as exc:
            logger.warning("Rate limit Redis unavailable, using in-memory fallback: %s", exc)
            return await self._fallback_result(key, limit, window_seconds, add=True)

        if result == -1:
            # Limit exceeded -- member was NOT added
            reset_at = datetime.fromtimestamp(now + window_seconds, tz=timezone.utc)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                limit=limit,
                reset_seconds=window_seconds,
            )

        current_count = result
        remaining = max(0, limit - current_count)
        reset_at = datetime.fromtimestamp(now + window_seconds, tz=timezone.utc)

        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_at=reset_at,
            limit=limit,
            reset_seconds=window_seconds,
        )

    async def increment(
        self,
        endpoint: str,
        scope_id: str,
        window_seconds: int,
    ) -> int:
        """Record a request and return the current count in the window.

        Uses a Lua script for atomic prune + add + count.

        .. note::
            Prefer :meth:`check_and_increment` for rate-limiting middleware
            to avoid TOCTOU race conditions.
        """
        key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        ttl = window_seconds + 1

        try:
            count: int = await self._inc(
                keys=[key], args=[now, window_seconds, member, ttl]
            )
            return count
        except Exception as exc:
            logger.warning("Rate limit Redis unavailable, using in-memory fallback: %s", exc)
            return await self._inmemory_count_and_add(key, window_seconds, add=True)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_rate_limiter() -> AIRateLimiter:
    """FastAPI dependency that provides an :class:`AIRateLimiter` instance.

    Uses the global ``redis_service`` singleton.  When Redis is not
    connected, returns a limiter whose Redis attribute is ``None`` — the
    limiter methods will catch the resulting exceptions and fail open.
    """
    from ..services.redis_service import redis_service

    client = redis_service.client if redis_service.is_connected else None
    return AIRateLimiter(client)


# ---------------------------------------------------------------------------
# Endpoint-specific middleware dependencies
# ---------------------------------------------------------------------------


_limits = _load_rate_limits()


def _raise_rate_limit(result: RateLimitResult, detail_prefix: str) -> None:
    """Raise HTTP 429 with standard rate limit headers."""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"{detail_prefix}. Try again in {result.reset_seconds}s.",
        headers={
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": str(result.remaining),
            "X-RateLimit-Reset": str(int(result.reset_at.timestamp())),
        },
    )


async def check_chat_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for AI chat endpoints -- 30 req/min per user."""
    limit, window = _limits["ai_chat"]
    result = await rate_limiter.check_and_increment(
        endpoint="ai_chat",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Rate limit exceeded")


async def check_embedding_rate_limit(
    application_id: str,
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for embedding endpoints -- 100 docs/min per application.

    **RBAC note:** ``application_id`` is taken from the path/body parameter.
    The calling router MUST validate that the current user has access to this
    application (via ``get_current_user`` + membership check) *before* this
    dependency runs.  This dependency only enforces rate limits, not access
    control.
    """
    limit, window = _limits["ai_embed"]
    result = await rate_limiter.check_and_increment(
        endpoint="ai_embed",
        scope_id=application_id,
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Embedding rate limit exceeded")


async def check_import_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for document import -- 10 files/hr per user."""
    limit, window = _limits["ai_import"]
    result = await rate_limiter.check_and_increment(
        endpoint="ai_import",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Import rate limit exceeded")


async def check_query_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for AI SQL query endpoints -- 30 req/min per user."""
    limit, window = _limits["ai_query"]
    result = await rate_limiter.check_and_increment(
        endpoint="ai_query",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Query rate limit exceeded")


async def check_reindex_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for manual reindex -- 20 req/hr per user."""
    limit, window = _limits["ai_reindex"]
    result = await rate_limiter.check_and_increment(
        endpoint="ai_reindex",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Reindex rate limit exceeded")


async def check_test_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for provider/capability test endpoints -- 10 req/min per user."""
    limit, window = _limits["ai_test"]
    result = await rate_limiter.check_and_increment(
        endpoint="ai_test",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Test rate limit exceeded")

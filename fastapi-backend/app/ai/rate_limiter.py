"""Redis-based rate limiting for AI endpoints.

Uses a sliding window counter pattern backed by Redis sorted sets.
Each request is stored as a member (timestamp) in a sorted set keyed by
``ratelimit:{endpoint}:{scope_id}:{window}``. Expired entries are pruned
on each check, giving accurate per-window counts.

Fail-open: when Redis is unavailable all requests are allowed and a
warning is logged.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from ..models.user import User
from ..services.auth_service import get_current_user

logger = logging.getLogger(__name__)


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
    "ai_embed": (100, 60),
    "ai_import": (10, 3600),
    "ai_reindex": (20, 3600),
}


def _load_rate_limits() -> dict[str, tuple[int, int]]:
    """Load rate limits, allowing env-var overrides.

    Environment variables follow the pattern:
        RATE_LIMIT_AI_CHAT=30,60
        RATE_LIMIT_AI_EMBED=100,60
        RATE_LIMIT_AI_IMPORT=10,3600
        RATE_LIMIT_AI_REINDEX=20,3600

    Falls back to ``RATE_LIMITS`` defaults when not set.
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
    """

    def __init__(self, redis: Any) -> None:
        self.redis = redis

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
        *window_seconds*.
        """
        key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self.redis.pipeline(transaction=False)
            # Remove entries older than the window
            pipe.zremrangebyscore(key, "-inf", window_start)
            # Count remaining entries in the window
            pipe.zcard(key)
            results = await pipe.execute()
            current_count: int = results[1]
        except Exception as exc:
            logger.warning("Rate limit check failed (fail-open): %s", exc)
            reset_at = datetime.fromtimestamp(now + window_seconds, tz=timezone.utc)
            return RateLimitResult(
                allowed=True,
                remaining=limit,
                reset_at=reset_at,
                limit=limit,
                reset_seconds=window_seconds,
            )

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

    async def increment(
        self,
        endpoint: str,
        scope_id: str,
        window_seconds: int,
    ) -> int:
        """Record a request and return the current count in the window.

        Uses ZADD + ZREMRANGEBYSCORE + EXPIRE in a pipeline for atomicity.
        """
        key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        window_start = now - window_seconds
        # Use timestamp as both score and member for uniqueness
        member = f"{now}"

        try:
            pipe = self.redis.pipeline(transaction=False)
            pipe.zadd(key, {member: now})
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.expire(key, window_seconds + 1)
            pipe.zcard(key)
            results = await pipe.execute()
            return results[3]
        except Exception as exc:
            logger.warning("Rate limit increment failed (fail-open): %s", exc)
            return 0


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


async def check_chat_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for AI chat endpoints — 30 req/min per user."""
    limit, window = _limits["ai_chat"]
    result = await rate_limiter.check_rate_limit(
        endpoint="ai_chat",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result.reset_seconds}s.",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_at.timestamp())),
            },
        )
    # Increment after check so the current request is counted
    await rate_limiter.increment("ai_chat", str(current_user.id), window)


async def check_embedding_rate_limit(
    application_id: str,
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for embedding endpoints — 100 docs/min per application."""
    limit, window = _limits["ai_embed"]
    result = await rate_limiter.check_rate_limit(
        endpoint="ai_embed",
        scope_id=application_id,
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Embedding rate limit exceeded. Try again in {result.reset_seconds}s.",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_at.timestamp())),
            },
        )
    await rate_limiter.increment("ai_embed", application_id, window)


async def check_import_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for document import — 10 files/hr per user."""
    limit, window = _limits["ai_import"]
    result = await rate_limiter.check_rate_limit(
        endpoint="ai_import",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Import rate limit exceeded. Try again in {result.reset_seconds}s.",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_at.timestamp())),
            },
        )
    await rate_limiter.increment("ai_import", str(current_user.id), window)


async def check_reindex_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for manual reindex — 20 req/hr per user."""
    limit, window = _limits["ai_reindex"]
    result = await rate_limiter.check_rate_limit(
        endpoint="ai_reindex",
        scope_id=str(current_user.id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Reindex rate limit exceeded. Try again in {result.reset_seconds}s.",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_at.timestamp())),
            },
        )
    await rate_limiter.increment("ai_reindex", str(current_user.id), window)

"""Redis-based rate limiting for AI endpoints.

Uses a sliding window counter pattern backed by Redis INCR counters.
Each fixed time window gets its own counter key. The effective request count
is estimated by blending the current and previous window counts:

    effective = current_count + previous_count * (1 - elapsed_fraction)

This gives sliding-window precision while using O(1) Redis operations
(GET + INCR + EXPIRE) instead of the O(log N) sorted-set approach.

Key format:
    ``ratelimit:{endpoint}:{scope_id}:{window}:{window_number}``

Each endpoint+scope uses at most 2 Redis keys (current window + previous
window), regardless of request volume. At 5,000 users this means ~10,000
keys total -- compared to 150,000 sorted-set members under the old scheme.

A Lua script executes the check-and-increment atomically in Redis, avoiding
TOCTOU race conditions that could occur with pipelined commands.

Fallback: when Redis is unavailable, an in-memory counter with the same
limit is used per-worker.  This prevents complete bypass while tolerating
brief Redis outages.  A CRITICAL log is emitted on each fallback hit so
operators can detect and resolve Redis connectivity issues quickly.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from ..models.user import User
from ..services.auth_service import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Redis Lua scripts (executed atomically on the server)
# ---------------------------------------------------------------------------

# Sliding window counter: check limit, increment current window if under limit.
# Uses 2 keys: KEYS[1] = current window counter, KEYS[2] = previous window counter.
# Returns effective count on success, -1 if rate limit exceeded.
_CHECK_AND_INCREMENT_SCRIPT = """
local curr_key = KEYS[1]
local prev_key = KEYS[2]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Calculate window boundaries
local curr_window = math.floor(now / window)
local curr_start = curr_window * window
local elapsed = now - curr_start
local weight = 1 - (elapsed / window)

-- Get counts
local curr_count = tonumber(redis.call('GET', curr_key) or '0')
local prev_count = tonumber(redis.call('GET', prev_key) or '0')

-- Sliding estimate (use math.floor for consistent integer comparison)
local estimate = curr_count + math.floor(prev_count * weight)

if estimate >= limit then
    return -1  -- Rate limited
end

-- Increment current window
local new_count = redis.call('INCR', curr_key)
-- Set TTL to 2 windows (current + buffer for next window's prev lookup)
redis.call('EXPIRE', curr_key, window * 2)
-- Ensure prev_key also has a TTL so stale keys don't persist indefinitely
redis.call('EXPIRE', prev_key, window * 2)

return new_count + math.floor(prev_count * weight)
"""

# Sliding window counter: increment current window unconditionally, return count.
# Uses 2 keys: KEYS[1] = current window counter, KEYS[2] = previous window counter.
_INCREMENT_SCRIPT = """
local curr_key = KEYS[1]
local prev_key = KEYS[2]
local window = tonumber(ARGV[1])
local now = tonumber(ARGV[2])

local curr_window = math.floor(now / window)
local curr_start = curr_window * window
local elapsed = now - curr_start
local weight = 1 - (elapsed / window)

local prev_count = tonumber(redis.call('GET', prev_key) or '0')

-- Increment current window
local new_count = redis.call('INCR', curr_key)
redis.call('EXPIRE', curr_key, window * 2)
-- Ensure prev_key also has a TTL so stale keys don't persist indefinitely
redis.call('EXPIRE', prev_key, window * 2)

return new_count + math.floor(prev_count * weight)
"""

# Check-only: read current + previous window counts, return sliding estimate.
# Uses 2 keys: KEYS[1] = current window counter, KEYS[2] = previous window counter.
_CHECK_SCRIPT = """
local curr_key = KEYS[1]
local prev_key = KEYS[2]
local window = tonumber(ARGV[1])
local now = tonumber(ARGV[2])

local curr_window = math.floor(now / window)
local curr_start = curr_window * window
local elapsed = now - curr_start
local weight = 1 - (elapsed / window)

local curr_count = tonumber(redis.call('GET', curr_key) or '0')
local prev_count = tonumber(redis.call('GET', prev_key) or '0')

return curr_count + math.floor(prev_count * weight)
"""


# ---------------------------------------------------------------------------
# In-memory fallback counter (used when Redis is unavailable)
# ---------------------------------------------------------------------------

# Per-key locks to avoid serializing all fallback checks behind one lock.
# The dict is capped at _INMEMORY_LOCK_MAX_KEYS to prevent unbounded growth;
# stale entries are pruned when the cap is hit.
_inmemory_locks: dict[str, asyncio.Lock] = {}
_INMEMORY_LOCK_MAX_KEYS = 20_000

# Backward-compatible alias: tests import ``_inmemory_lock`` by name.
# This is no longer used internally but kept so existing test imports work.
_inmemory_lock = asyncio.Lock()


def _get_key_lock(key: str) -> asyncio.Lock:
    """Return a per-key asyncio.Lock, creating one if needed.

    When the lock dict exceeds ``_INMEMORY_LOCK_MAX_KEYS``, removes all
    entries whose corresponding counter key has already been evicted from
    ``_inmemory_counters``, then trims the oldest half if still over limit.
    """
    if key not in _inmemory_locks:
        # Cleanup when dict grows too large
        if len(_inmemory_locks) >= _INMEMORY_LOCK_MAX_KEYS:
            # Remove locks for keys no longer in the counter dict
            stale = [k for k in _inmemory_locks if k not in _inmemory_counters]
            for k in stale:
                del _inmemory_locks[k]
            # If still over limit, drop the oldest half (arbitrary but bounded)
            if len(_inmemory_locks) >= _INMEMORY_LOCK_MAX_KEYS:
                to_remove = list(_inmemory_locks.keys())[: len(_inmemory_locks) // 2]
                for k in to_remove:
                    del _inmemory_locks[k]
        _inmemory_locks[key] = asyncio.Lock()
    return _inmemory_locks[key]


# { key: count }  -- per-window counter (key includes window number)
_inmemory_counters: dict[str, int] = {}
# HIGH-3 fix: use same limit as Redis (1x) -- previously 2x which multiplied
# by worker count, allowing far more requests than intended during outages.
_INMEMORY_LIMIT_MULTIPLIER = 1
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
    "session_crud": (120, 60),
    "session_summarize": (5, 60),
    "web_search": (20, 60),  # 20 searches per 60s per user
    "web_scrape": (10, 60),  # 10 scrapes per 60s per user
    "auth_login": (10, 60),
    "auth_register": (5, 60),
    "auth_verify": (10, 60),
    "auth_reset": (5, 60),
    "file_upload": (20, 60),  # 20 uploads per 60s per user
}


def _load_rate_limits() -> dict[str, tuple[int, int]]:
    """Load rate limits with priority: env var > DB config > hardcoded default.

    Environment variables follow the pattern:
        RATE_LIMIT_AI_CHAT=30,60
        RATE_LIMIT_AI_EMBED=100,60
        RATE_LIMIT_AI_IMPORT=10,3600
        RATE_LIMIT_AI_REINDEX=20,3600

    DB config keys follow the pattern: rate_limit.ai_chat -> "30,60"

    Falls back to ``RATE_LIMITS`` hardcoded defaults when neither is set.

    .. note::
        Called once at module import time.  Changes to env vars take
        effect only after a server restart.
    """
    import os

    from .config_service import get_agent_config

    cfg = get_agent_config()
    limits = dict(RATE_LIMITS)

    for key in limits:
        # Priority 1: Environment variable
        env_key = f"RATE_LIMIT_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val:
            try:
                parts = env_val.split(",")
                limits[key] = (int(parts[0].strip()), int(parts[1].strip()))
                continue
            except (IndexError, ValueError):
                logger.warning("Invalid rate limit env var %s=%s, using default", env_key, env_val)

        # Priority 2: DB config (AgentConfigurations table)
        config_key = f"rate_limit.{key}"
        db_val = cfg.get_rate_limit(config_key, limits[key])
        if db_val != limits[key]:
            limits[key] = db_val

    return limits


# ---------------------------------------------------------------------------
# Core rate limiter
# ---------------------------------------------------------------------------


class AIRateLimiter:
    """Redis-based sliding window rate limiter for AI endpoints.

    Key format: ``ratelimit:{endpoint}:{scope_id}:{window}``

    When Redis is unavailable, falls back to an in-memory counter with
    the same limit to prevent bypass during outages.  A CRITICAL log is
    emitted on each fallback so operators can detect Redis issues.
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
    async def _inmemory_count_and_add(key: str, window_seconds: int, *, add: bool = False) -> int:
        """Return sliding window estimate using in-memory fallback counters.

        Uses the same two-window counter approach as the Redis Lua scripts:
        the key is split into ``{key}:{window_number}`` counters, and the
        effective count blends the current and previous windows.

        If *add* is True, increments the current window counter.

        Uses a per-key lock so concurrent requests to different keys
        do not serialize behind a single global lock.
        """
        now = time.time()
        curr_window = int(now // window_seconds)
        curr_start = curr_window * window_seconds
        elapsed = now - curr_start
        weight = 1 - (elapsed / window_seconds)

        curr_key = f"{key}:{curr_window}"
        prev_key = f"{key}:{curr_window - 1}"

        async with _get_key_lock(key):
            # Safety valve: prevent unbounded memory growth
            if len(_inmemory_counters) > _INMEMORY_MAX_KEYS:
                # Evict keys from old windows (window number < curr_window - 1)
                stale_keys = []
                for k in _inmemory_counters:
                    try:
                        parts = k.rsplit(":", 1)
                        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
                            win_num = int(parts[1])
                            # Key is from 2+ windows ago -- safe to evict
                            if win_num < curr_window - 1:
                                stale_keys.append(k)
                    except (ValueError, IndexError):
                        stale_keys.append(k)
                for k in stale_keys:
                    del _inmemory_counters[k]

                # If still over limit, evict oldest 25%
                if len(_inmemory_counters) > _INMEMORY_MAX_KEYS:
                    evict_count = max(1, len(_inmemory_counters) // 4)
                    sorted_keys = sorted(_inmemory_counters.keys())
                    for k in sorted_keys[:evict_count]:
                        del _inmemory_counters[k]

                logger.warning(
                    "In-memory rate limit counter evicted entries, now %d keys",
                    len(_inmemory_counters),
                )

            prev_count = _inmemory_counters.get(prev_key, 0)
            curr_count = _inmemory_counters.get(curr_key, 0)

            if add:
                curr_count += 1
                _inmemory_counters[curr_key] = curr_count

            return curr_count + math.floor(prev_count * weight)

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
        threshold.  With the multiplier set to 1, this enforces the same
        limit as Redis but per-worker (not globally shared).
        """
        fallback_limit = limit * _INMEMORY_LIMIT_MULTIPLIER
        count = await self._inmemory_count_and_add(key, window_seconds, add=add)
        # Use strict '<' to match Redis behavior (block at exactly limit, not limit+1)
        allowed = count < fallback_limit
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
        *window_seconds*.  Uses a Lua script for atomic read of the
        current and previous window counters.
        """
        base_key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        curr_window = int(now // window_seconds)
        curr_key = f"{base_key}:{curr_window}"
        prev_key = f"{base_key}:{curr_window - 1}"

        try:
            current_count: int = await self._check(
                keys=[curr_key, prev_key],
                args=[window_seconds, now],
            )
        except Exception as exc:
            logger.critical(
                "Rate limit fallback: Redis unavailable, using in-memory counters (per-worker): %s",
                exc,
            )
            return await self._fallback_result(base_key, limit, window_seconds, add=False)

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

        Uses a Lua script that reads the current and previous window
        counters, computes the sliding estimate, and only increments the
        current window counter if under the limit -- all in a single
        atomic Redis EVAL.  Returns ``allowed=False`` when the limit
        is reached (the counter is NOT incremented in that case).

        Returns a :class:`RateLimitResult` with ``allowed=True`` if the
        caller (including this request) has not exceeded *limit* in the
        current sliding *window_seconds*.
        """
        base_key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        curr_window = int(now // window_seconds)
        curr_key = f"{base_key}:{curr_window}"
        prev_key = f"{base_key}:{curr_window - 1}"

        try:
            result: int = await self._check_and_inc(
                keys=[curr_key, prev_key],
                args=[window_seconds, limit, now],
            )
        except Exception as exc:
            logger.critical(
                "Rate limit fallback: Redis unavailable, using in-memory counters (per-worker): %s",
                exc,
            )
            return await self._fallback_result(base_key, limit, window_seconds, add=True)

        if result == -1:
            # Limit exceeded -- counter was NOT incremented
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
        """Record a request and return the current sliding window count.

        Uses a Lua script for atomic increment + sliding count.

        .. note::
            Prefer :meth:`check_and_increment` for rate-limiting middleware
            to avoid TOCTOU race conditions.
        """
        base_key = f"ratelimit:{endpoint}:{scope_id}:{window_seconds}"
        now = time.time()
        curr_window = int(now // window_seconds)
        curr_key = f"{base_key}:{curr_window}"
        prev_key = f"{base_key}:{curr_window - 1}"

        try:
            count: int = await self._inc(
                keys=[curr_key, prev_key],
                args=[window_seconds, now],
            )
            return count
        except Exception as exc:
            logger.critical(
                "Rate limit fallback: Redis unavailable, using in-memory counters (per-worker): %s",
                exc,
            )
            return await self._inmemory_count_and_add(base_key, window_seconds, add=True)


# ---------------------------------------------------------------------------
# FastAPI dependency (singleton-cached)
# ---------------------------------------------------------------------------

_cached_rate_limiter: AIRateLimiter | None = None
_cached_redis_client: Any = None


def get_rate_limiter() -> AIRateLimiter:
    """FastAPI dependency that provides an :class:`AIRateLimiter` instance.

    Uses the global ``redis_service`` singleton.  The limiter is cached as
    a module-level singleton and only recreated when the underlying Redis
    client changes (e.g. reconnection).  When Redis is not connected,
    returns a limiter whose Redis attribute is ``None`` -- the limiter
    methods will catch the resulting exceptions and fall back to in-memory.
    """
    global _cached_rate_limiter, _cached_redis_client

    from ..services.redis_service import redis_service

    client = redis_service.client if redis_service.is_connected else None
    if _cached_rate_limiter is None or client is not _cached_redis_client:
        _cached_rate_limiter = AIRateLimiter(client)
        _cached_redis_client = client
    return _cached_rate_limiter


# ---------------------------------------------------------------------------
# Endpoint-specific middleware dependencies
# ---------------------------------------------------------------------------


_limits: dict[str, tuple[int, int]] | None = None


def _get_limits() -> dict[str, tuple[int, int]]:
    """Lazy accessor for rate limits -- defers loading until first use.

    This avoids the problem of ``_load_rate_limits()`` being called at
    import time before the config cache (AgentConfigService) has been
    loaded from the database.  The first call after ``config.load_all()``
    completes will populate the limits; subsequent calls return the
    cached dict.

    Call ``reload_rate_limits()`` after startup to force a refresh.
    """
    global _limits
    if _limits is None:
        _limits = _load_rate_limits()
    return _limits


def reload_rate_limits() -> None:
    """Force a reload of rate limits from config/env.

    Should be called from ``main.py`` lifespan after
    ``AgentConfigService.load_all()`` completes, so that DB-configured
    rate limits take effect.
    """
    global _limits
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


# ---------------------------------------------------------------------------
# Factory helpers (HIGH-18: eliminate near-identical boilerplate)
# ---------------------------------------------------------------------------


def _make_user_rate_limit_dep(key_suffix: str, detail_prefix: str) -> Any:
    """Factory for user-scoped rate limit dependencies.

    Returns an async callable suitable for use with ``Depends()``.
    Reads limit/window from ``_get_limits()`` at call time (not at
    import time) so that reloaded config takes effect without restart.
    """

    async def _check(
        current_user: User = Depends(get_current_user),
        rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
    ) -> None:
        limit, window = _get_limits()[key_suffix]
        result = await rate_limiter.check_and_increment(
            endpoint=key_suffix,
            scope_id=str(current_user.id),
            limit=limit,
            window_seconds=window,
        )
        if not result.allowed:
            _raise_rate_limit(result, f"{detail_prefix}: rate limit exceeded")

    # Preserve a useful name for debugging / introspection
    _check.__name__ = f"check_{key_suffix}_rate_limit"
    _check.__qualname__ = f"check_{key_suffix}_rate_limit"
    return _check


def _make_ip_rate_limit_dep(key_suffix: str, detail_prefix: str) -> Any:
    """Factory for IP-scoped rate limit dependencies.

    Returns an async callable suitable for use with ``Depends()``.
    Reads limit/window from ``_get_limits()`` at call time (not at
    import time) so that reloaded config takes effect without restart.
    """

    async def _check(
        request: Request,
        rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
    ) -> None:
        # M11: Extract real client IP from X-Forwarded-For only when behind
        # a trusted proxy (checked via settings).  Falls back to direct connection IP.
        # R2-7: Use rightmost non-trusted-proxy IP to prevent XFF spoofing.
        from ..config import settings as _rl_settings

        _xff = request.headers.get("x-forwarded-for", "")
        if _xff and getattr(_rl_settings, "trusted_proxy_ips", ""):
            _conn_ip = request.client.host if request.client else ""
            _trusted = {ip.strip() for ip in _rl_settings.trusted_proxy_ips.split(",") if ip.strip()}
            if _conn_ip in _trusted:
                # Use the rightmost non-trusted-proxy IP (first untrusted hop)
                _parts = [p.strip() for p in _xff.split(",")]
                client_ip = next(
                    (p for p in reversed(_parts) if p not in _trusted),
                    _parts[0],
                )
            else:
                client_ip = _conn_ip or "unknown"
        else:
            client_ip = request.client.host if request.client else "unknown"
        limit, window = _get_limits()[key_suffix]
        result = await rate_limiter.check_and_increment(
            endpoint=key_suffix,
            scope_id=client_ip,
            limit=limit,
            window_seconds=window,
        )
        if not result.allowed:
            _raise_rate_limit(result, f"{detail_prefix}: rate limit exceeded")

    _check.__name__ = f"check_{key_suffix}_rate_limit"
    _check.__qualname__ = f"check_{key_suffix}_rate_limit"
    return _check


# ---------------------------------------------------------------------------
# User-scoped rate limit dependencies
# ---------------------------------------------------------------------------

check_chat_rate_limit = _make_user_rate_limit_dep("ai_chat", "AI chat")

check_query_rate_limit = _make_user_rate_limit_dep("ai_query", "AI query")

check_import_rate_limit = _make_user_rate_limit_dep("ai_import", "Import")

check_reindex_rate_limit = _make_user_rate_limit_dep("ai_reindex", "Reindex")

check_test_rate_limit = _make_user_rate_limit_dep("ai_test", "Test")

check_session_crud_rate_limit = _make_user_rate_limit_dep("session_crud", "Session CRUD")

check_summarize_rate_limit = _make_user_rate_limit_dep("session_summarize", "Summarize")


# ---------------------------------------------------------------------------
# Embedding rate limit (HIGH-4: keyed by user_id, not application_id)
# ---------------------------------------------------------------------------


async def check_embedding_rate_limit(
    user_id: str,
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Dependency for embedding endpoints -- 100 docs/min per user.

    Rate-limits by ``user_id`` rather than ``application_id`` to avoid
    trusting an unvalidated path/body parameter for rate limiting.  The
    caller should pass the authenticated user's ID (from ``get_current_user``
    or the worker context) to ensure the limit is applied correctly.
    """
    limit, window = _get_limits()["ai_embed"]
    result = await rate_limiter.check_and_increment(
        endpoint="ai_embed",
        scope_id=str(user_id),
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Embedding rate limit exceeded")


# ---------------------------------------------------------------------------
# IP-based rate limits for auth endpoints (no authenticated user)
# ---------------------------------------------------------------------------

check_auth_login_rate_limit = _make_ip_rate_limit_dep("auth_login", "Too many login attempts")

check_auth_register_rate_limit = _make_ip_rate_limit_dep("auth_register", "Too many registration attempts")

check_auth_verify_rate_limit = _make_ip_rate_limit_dep("auth_verify", "Too many verification attempts")

check_auth_reset_rate_limit = _make_ip_rate_limit_dep("auth_reset", "Too many reset attempts")

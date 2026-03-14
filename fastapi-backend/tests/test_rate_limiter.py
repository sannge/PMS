"""Unit tests for AI rate limiter (Phase 7 -- 7.1-7.2).

Tests the AIRateLimiter class, RateLimitResult model, rate limit
configuration loading, the FastAPI middleware dependencies, and the
in-memory fallback counter used when Redis is unavailable.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.rate_limiter import (
    AIRateLimiter,
    RATE_LIMITS,
    RateLimitResult,
    _INMEMORY_LIMIT_MULTIPLIER,
    _INMEMORY_MAX_KEYS,
    _inmemory_counters,
    _inmemory_lock,
    _load_rate_limits,
    check_chat_rate_limit,
    check_embedding_rate_limit,
    check_import_rate_limit,
    check_reindex_rate_limit,
    get_rate_limiter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_redis(check_return: int = 0, inc_return: int = 1, check_and_inc_return: int = 1) -> MagicMock:
    """Create a mock Redis client with Lua script support.

    ``check_return`` controls what the check-only script returns.
    ``inc_return`` controls what the increment-only script returns.
    ``check_and_inc_return`` controls what check_and_increment script returns
    (-1 means rate limited).
    """
    mock_check_script = AsyncMock(return_value=check_return)
    mock_inc_script = AsyncMock(return_value=inc_return)
    mock_check_and_inc_script = AsyncMock(return_value=check_and_inc_return)

    mock_redis = MagicMock()
    # register_script is called 3 times in __init__: check_and_inc, inc, check
    mock_redis.register_script = MagicMock(
        side_effect=[mock_check_and_inc_script, mock_inc_script, mock_check_script]
    )

    return mock_redis


def _make_failing_redis() -> MagicMock:
    """Create a mock Redis whose Lua scripts raise ConnectionError (fallback testing)."""
    error = ConnectionError("Redis down")
    mock_check_script = AsyncMock(side_effect=error)
    mock_inc_script = AsyncMock(side_effect=error)
    mock_check_and_inc_script = AsyncMock(side_effect=error)

    mock_redis = MagicMock()
    mock_redis.register_script = MagicMock(
        side_effect=[mock_check_and_inc_script, mock_inc_script, mock_check_script]
    )

    return mock_redis


# ---------------------------------------------------------------------------
# RateLimitResult model
# ---------------------------------------------------------------------------


class TestRateLimitResult:
    def test_model_fields(self):
        result = RateLimitResult(
            allowed=True,
            remaining=29,
            reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            limit=30,
            reset_seconds=60,
        )
        assert result.allowed is True
        assert result.remaining == 29
        assert result.limit == 30
        assert result.reset_seconds == 60

    def test_model_blocked(self):
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            limit=30,
            reset_seconds=60,
        )
        assert result.allowed is False
        assert result.remaining == 0


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------


class TestRateLimitConfig:
    def test_defaults(self):
        assert RATE_LIMITS["ai_chat"] == (30, 60)
        assert RATE_LIMITS["ai_embed"] == (100, 60)
        assert RATE_LIMITS["ai_import"] == (10, 3600)
        assert RATE_LIMITS["ai_reindex"] == (20, 3600)

    def test_env_override(self):
        with patch.dict("os.environ", {"RATE_LIMIT_AI_CHAT": "50,120"}):
            limits = _load_rate_limits()
            assert limits["ai_chat"] == (50, 120)
            # Others unchanged
            assert limits["ai_import"] == (10, 3600)

    def test_invalid_env_value_keeps_default(self):
        with patch.dict("os.environ", {"RATE_LIMIT_AI_CHAT": "invalid"}):
            limits = _load_rate_limits()
            assert limits["ai_chat"] == (30, 60)


# ---------------------------------------------------------------------------
# AIRateLimiter.check_rate_limit (read-only check)
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_under_limit_allowed(self):
        redis = _make_mock_redis(check_return=5)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 25
        assert result.limit == 30

    @pytest.mark.asyncio
    async def test_at_limit_blocked(self):
        redis = _make_mock_redis(check_return=30)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is False
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self):
        redis = _make_mock_redis(check_return=35)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is False
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_empty_window_allowed(self):
        redis = _make_mock_redis(check_return=0)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 30

    @pytest.mark.asyncio
    async def test_reset_at_is_future(self):
        redis = _make_mock_redis(check_return=0)
        limiter = AIRateLimiter(redis)

        before = time.time()
        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)
        after = time.time()

        # reset_at should be ~60s from now
        assert result.reset_at.timestamp() >= before + 59
        assert result.reset_at.timestamp() <= after + 61

    @pytest.mark.asyncio
    async def test_redis_failure_uses_inmemory_fallback(self):
        """When Redis is unavailable, in-memory fallback is used."""
        _inmemory_counters.clear()
        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        # check_rate_limit does not increment, so remaining equals full fallback limit
        assert result.limit == 30 * _INMEMORY_LIMIT_MULTIPLIER
        assert result.remaining == 30 * _INMEMORY_LIMIT_MULTIPLIER

    @pytest.mark.asyncio
    async def test_none_redis_uses_inmemory_fallback(self):
        """When Redis is None (not connected), in-memory fallback is used."""
        _inmemory_counters.clear()
        limiter = AIRateLimiter(None)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.limit == 30 * _INMEMORY_LIMIT_MULTIPLIER


# ---------------------------------------------------------------------------
# AIRateLimiter.check_and_increment (atomic check + increment)
# ---------------------------------------------------------------------------


class TestCheckAndIncrement:
    @pytest.mark.asyncio
    async def test_under_limit_allowed(self):
        """Request count below limit: allowed with correct remaining."""
        # Lua script returns new count (5) on success
        redis = _make_mock_redis(check_and_inc_return=5)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 25
        assert result.limit == 30

    @pytest.mark.asyncio
    async def test_at_limit_allowed(self):
        """Request that hits exactly the limit: allowed (count == limit)."""
        # Lua script returns 30 (added successfully as the 30th entry)
        redis = _make_mock_redis(check_and_inc_return=30)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self):
        """Request that exceeds limit: blocked (Lua returns -1)."""
        # Lua script returns -1 when count >= limit (request NOT added)
        redis = _make_mock_redis(check_and_inc_return=-1)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is False
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        """First request in empty window: allowed with full remaining."""
        redis = _make_mock_redis(check_and_inc_return=1)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 29

    @pytest.mark.asyncio
    async def test_redis_failure_uses_inmemory_fallback(self):
        """When Redis is unavailable, in-memory fallback is used."""
        _inmemory_counters.clear()
        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.limit == 30 * _INMEMORY_LIMIT_MULTIPLIER
        # One request recorded
        assert result.remaining == 30 * _INMEMORY_LIMIT_MULTIPLIER - 1

    @pytest.mark.asyncio
    async def test_none_redis_uses_inmemory_fallback(self):
        """When Redis is None (not connected), in-memory fallback is used."""
        _inmemory_counters.clear()
        limiter = AIRateLimiter(None)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.limit == 30 * _INMEMORY_LIMIT_MULTIPLIER

    @pytest.mark.asyncio
    async def test_reset_at_is_future(self):
        redis = _make_mock_redis(check_and_inc_return=1)
        limiter = AIRateLimiter(redis)

        before = time.time()
        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)
        after = time.time()

        assert result.reset_at.timestamp() >= before + 59
        assert result.reset_at.timestamp() <= after + 61

    @pytest.mark.asyncio
    async def test_lua_script_called_with_correct_args(self):
        """Verify Lua script is called with keys and args."""
        redis = _make_mock_redis(check_and_inc_return=3)
        limiter = AIRateLimiter(redis)

        await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        # The check_and_inc script should have been called once
        limiter._check_and_inc.assert_awaited_once()
        call_kwargs = limiter._check_and_inc.call_args
        assert call_kwargs[1]["keys"] == ["ratelimit:ai_chat:user-1:60"]
        args = call_kwargs[1]["args"]
        # args: [now, window_seconds, limit, member, ttl]
        assert len(args) == 5
        assert args[1] == 60  # window_seconds
        assert args[2] == 30  # limit
        assert args[4] == 61  # ttl = window + 1


# ---------------------------------------------------------------------------
# AIRateLimiter.increment (standalone)
# ---------------------------------------------------------------------------


class TestIncrement:
    @pytest.mark.asyncio
    async def test_first_request(self):
        redis = _make_mock_redis(inc_return=1)
        limiter = AIRateLimiter(redis)

        count = await limiter.increment("ai_chat", "user-1", 60)

        assert count == 1

    @pytest.mark.asyncio
    async def test_subsequent_request(self):
        redis = _make_mock_redis(inc_return=5)
        limiter = AIRateLimiter(redis)

        count = await limiter.increment("ai_chat", "user-1", 60)

        assert count == 5

    @pytest.mark.asyncio
    async def test_redis_failure_uses_inmemory_fallback(self):
        """When Redis fails, increment uses in-memory fallback."""
        _inmemory_counters.clear()
        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)

        count = await limiter.increment("ai_chat", "user-1", 60)

        assert count == 1  # First request recorded in fallback

    @pytest.mark.asyncio
    async def test_lua_script_called_with_correct_args(self):
        """Verify Lua increment script is called with keys and args."""
        redis = _make_mock_redis(inc_return=3)
        limiter = AIRateLimiter(redis)

        await limiter.increment("ai_chat", "user-1", 60)

        limiter._inc.assert_awaited_once()
        call_kwargs = limiter._inc.call_args
        assert call_kwargs[1]["keys"] == ["ratelimit:ai_chat:user-1:60"]
        args = call_kwargs[1]["args"]
        # args: [now, window_seconds, member, ttl]
        assert len(args) == 4
        assert args[1] == 60  # window_seconds
        assert args[3] == 61  # ttl = window + 1


# ---------------------------------------------------------------------------
# In-memory fallback counter
# ---------------------------------------------------------------------------


class TestInMemoryFallback:
    """Tests for the in-memory fallback when Redis is unavailable."""

    def setup_method(self):
        """Clear in-memory counters before each test."""
        _inmemory_counters.clear()

    @pytest.mark.asyncio
    async def test_check_and_increment_fallback_allowed(self):
        """When Redis fails, in-memory fallback allows requests under 2x limit."""
        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        # Fallback limit is 2x normal
        assert result.limit == 30 * _INMEMORY_LIMIT_MULTIPLIER
        assert result.remaining == 30 * _INMEMORY_LIMIT_MULTIPLIER - 1

    @pytest.mark.asyncio
    async def test_check_and_increment_fallback_blocked(self):
        """When in-memory count exceeds 2x limit, requests are blocked."""
        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)
        limit = 5
        fallback_limit = limit * _INMEMORY_LIMIT_MULTIPLIER  # 10

        # Fill up the fallback counter
        for _ in range(fallback_limit):
            await limiter.check_and_increment("ai_chat", "user-1", limit, 60)

        # Next request should be blocked
        result = await limiter.check_and_increment("ai_chat", "user-1", limit, 60)
        assert result.allowed is False
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_fallback_no_increment(self):
        """check_rate_limit fallback should not add a counter entry."""
        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        # Should not have incremented counter
        key = "ratelimit:ai_chat:user-1:60"
        async with _inmemory_lock:
            assert len(_inmemory_counters.get(key, [])) == 0

    @pytest.mark.asyncio
    async def test_increment_fallback_returns_count(self):
        """increment() fallback should record and return count."""
        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)

        count1 = await limiter.increment("ai_chat", "user-1", 60)
        count2 = await limiter.increment("ai_chat", "user-1", 60)

        assert count1 == 1
        assert count2 == 2

    @pytest.mark.asyncio
    async def test_fallback_prunes_expired_entries(self):
        """Expired entries should be pruned from in-memory counters."""
        key = "ratelimit:ai_chat:user-1:60"
        # Manually insert an old entry
        old_ts = time.time() - 120  # 2 minutes ago, outside 60s window
        async with _inmemory_lock:
            _inmemory_counters[key] = [old_ts]

        redis = _make_failing_redis()
        limiter = AIRateLimiter(redis)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        # Old entry pruned, only the new one remains
        assert result.allowed is True
        async with _inmemory_lock:
            assert len(_inmemory_counters[key]) == 1

    @pytest.mark.asyncio
    async def test_none_redis_uses_fallback(self):
        """When Redis is None, should use in-memory fallback."""
        limiter = AIRateLimiter(None)

        result = await limiter.check_and_increment("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.limit == 30 * _INMEMORY_LIMIT_MULTIPLIER

    @pytest.mark.asyncio
    async def test_max_keys_safety_clears_counters(self):
        """When in-memory dict exceeds _INMEMORY_MAX_KEYS, it gets cleared."""
        # Fill with fake keys beyond the limit
        for i in range(_INMEMORY_MAX_KEYS + 1):
            _inmemory_counters[f"fake-key-{i}"] = [time.time()]

        # Next call should trigger the safety clear
        count = await AIRateLimiter._inmemory_count_and_add(
            "new-key", 60, add=True
        )

        # After eviction, the new entry should exist
        assert count == 1
        assert "new-key" in _inmemory_counters


# ---------------------------------------------------------------------------
# get_rate_limiter dependency
# ---------------------------------------------------------------------------


class TestGetRateLimiter:
    def test_returns_limiter_when_connected(self):
        mock_redis_service = MagicMock()
        mock_redis_service.is_connected = True
        mock_client = MagicMock()
        mock_redis_service.client = mock_client

        with patch("app.services.redis_service.redis_service", mock_redis_service):
            limiter = get_rate_limiter()

        assert isinstance(limiter, AIRateLimiter)
        assert limiter.redis is mock_client
        # Lua scripts should be registered
        assert mock_client.register_script.call_count == 3

    def test_returns_limiter_with_none_when_disconnected(self):
        mock_redis_service = MagicMock()
        mock_redis_service.is_connected = False

        with patch("app.services.redis_service.redis_service", mock_redis_service):
            limiter = get_rate_limiter()

        assert isinstance(limiter, AIRateLimiter)
        assert limiter.redis is None
        assert limiter._check_and_inc is None
        assert limiter._inc is None
        assert limiter._check is None


# ---------------------------------------------------------------------------
# Middleware dependencies (now use check_and_increment atomically)
# ---------------------------------------------------------------------------


class TestChatRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_under_limit_passes(self):
        """Under limit: no exception raised."""
        mock_user = MagicMock()
        mock_user.id = "user-123"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_and_increment = AsyncMock(
            return_value=RateLimitResult(
                allowed=True,
                remaining=29,
                reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                limit=30,
                reset_seconds=60,
            )
        )

        # Should not raise
        await check_chat_rate_limit(
            current_user=mock_user,
            rate_limiter=mock_limiter,
        )

        mock_limiter.check_and_increment.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        """Over limit: HTTPException 429 with rate limit headers."""
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-123"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_and_increment = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                limit=30,
                reset_seconds=60,
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await check_chat_rate_limit(
                current_user=mock_user,
                rate_limiter=mock_limiter,
            )

        assert exc_info.value.status_code == 429
        assert "X-RateLimit-Limit" in exc_info.value.headers
        assert exc_info.value.headers["X-RateLimit-Limit"] == "30"
        assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"


class TestEmbeddingRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_under_limit_passes(self):
        """Under limit: no exception raised, scoped by application_id."""
        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_and_increment = AsyncMock(
            return_value=RateLimitResult(
                allowed=True,
                remaining=99,
                reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                limit=100,
                reset_seconds=60,
            )
        )

        await check_embedding_rate_limit(
            user_id="user-123",
            rate_limiter=mock_limiter,
        )

        mock_limiter.check_and_increment.assert_awaited_once()
        call_kwargs = mock_limiter.check_and_increment.call_args
        assert call_kwargs[1]["scope_id"] == "user-123"
        assert call_kwargs[1]["endpoint"] == "ai_embed"

    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        from fastapi import HTTPException

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_and_increment = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                limit=100,
                reset_seconds=60,
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await check_embedding_rate_limit(
                user_id="user-456",
                rate_limiter=mock_limiter,
            )

        assert exc_info.value.status_code == 429
        assert "Embedding rate limit" in exc_info.value.detail


class TestImportRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-456"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_and_increment = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                limit=10,
                reset_seconds=3600,
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await check_import_rate_limit(
                current_user=mock_user,
                rate_limiter=mock_limiter,
            )

        assert exc_info.value.status_code == 429
        assert "Import: rate limit exceeded" in exc_info.value.detail


class TestReindexRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-789"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_and_increment = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                limit=20,
                reset_seconds=3600,
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await check_reindex_rate_limit(
                current_user=mock_user,
                rate_limiter=mock_limiter,
            )

        assert exc_info.value.status_code == 429
        assert "Reindex: rate limit exceeded" in exc_info.value.detail

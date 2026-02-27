"""Unit tests for AI rate limiter (Phase 7 — 7.1-7.2).

Tests the AIRateLimiter class, RateLimitResult model, rate limit
configuration loading, and the FastAPI middleware dependencies.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.rate_limiter import (
    AIRateLimiter,
    RATE_LIMITS,
    RateLimitResult,
    _load_rate_limits,
    check_chat_rate_limit,
    check_import_rate_limit,
    check_reindex_rate_limit,
    get_rate_limiter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_redis(card_value: int = 0) -> AsyncMock:
    """Create a mock Redis client with pipeline support.

    ``card_value`` controls what ZCARD returns (simulating current count).
    """
    mock_pipe = AsyncMock()
    mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
    mock_pipe.zcard = MagicMock(return_value=mock_pipe)
    mock_pipe.zadd = MagicMock(return_value=mock_pipe)
    mock_pipe.expire = MagicMock(return_value=mock_pipe)
    # Pipeline execute returns results in order of queued commands
    mock_pipe.execute = AsyncMock(return_value=[0, card_value])

    mock_redis = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)

    return mock_redis


def _make_increment_redis(new_count: int = 1) -> AsyncMock:
    """Create a mock Redis client for increment pipeline (ZADD+ZREM+EXPIRE+ZCARD)."""
    mock_pipe = AsyncMock()
    mock_pipe.zadd = MagicMock(return_value=mock_pipe)
    mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
    mock_pipe.expire = MagicMock(return_value=mock_pipe)
    mock_pipe.zcard = MagicMock(return_value=mock_pipe)
    mock_pipe.execute = AsyncMock(return_value=[1, 0, True, new_count])

    mock_redis = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)

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
# AIRateLimiter.check_rate_limit
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_under_limit_allowed(self):
        redis = _make_mock_redis(card_value=5)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 25
        assert result.limit == 30

    @pytest.mark.asyncio
    async def test_at_limit_blocked(self):
        redis = _make_mock_redis(card_value=30)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is False
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self):
        redis = _make_mock_redis(card_value=35)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is False
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_empty_window_allowed(self):
        redis = _make_mock_redis(card_value=0)
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 30

    @pytest.mark.asyncio
    async def test_reset_at_is_future(self):
        redis = _make_mock_redis(card_value=0)
        limiter = AIRateLimiter(redis)

        before = time.time()
        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)
        after = time.time()

        # reset_at should be ~60s from now
        assert result.reset_at.timestamp() >= before + 59
        assert result.reset_at.timestamp() <= after + 61

    @pytest.mark.asyncio
    async def test_redis_failure_fail_open(self):
        """When Redis is unavailable, all requests should be allowed."""
        redis = AsyncMock()
        redis.pipeline = MagicMock(side_effect=ConnectionError("Redis down"))
        limiter = AIRateLimiter(redis)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True
        assert result.remaining == 30

    @pytest.mark.asyncio
    async def test_none_redis_fail_open(self):
        """When Redis is None (not connected), should fail open."""
        limiter = AIRateLimiter(None)

        result = await limiter.check_rate_limit("ai_chat", "user-1", 30, 60)

        assert result.allowed is True


# ---------------------------------------------------------------------------
# AIRateLimiter.increment
# ---------------------------------------------------------------------------


class TestIncrement:
    @pytest.mark.asyncio
    async def test_first_request(self):
        redis = _make_increment_redis(new_count=1)
        limiter = AIRateLimiter(redis)

        count = await limiter.increment("ai_chat", "user-1", 60)

        assert count == 1

    @pytest.mark.asyncio
    async def test_subsequent_request(self):
        redis = _make_increment_redis(new_count=5)
        limiter = AIRateLimiter(redis)

        count = await limiter.increment("ai_chat", "user-1", 60)

        assert count == 5

    @pytest.mark.asyncio
    async def test_redis_failure_returns_zero(self):
        redis = AsyncMock()
        redis.pipeline = MagicMock(side_effect=ConnectionError("Redis down"))
        limiter = AIRateLimiter(redis)

        count = await limiter.increment("ai_chat", "user-1", 60)

        assert count == 0

    @pytest.mark.asyncio
    async def test_pipeline_commands_called(self):
        """Verify the correct pipeline commands are issued."""
        mock_pipe = AsyncMock()
        mock_pipe.zadd = MagicMock(return_value=mock_pipe)
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[1, 0, True, 3])

        redis = AsyncMock()
        redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = AIRateLimiter(redis)
        await limiter.increment("ai_chat", "user-1", 60)

        # ZADD, ZREMRANGEBYSCORE, EXPIRE, ZCARD should all be called
        mock_pipe.zadd.assert_called_once()
        mock_pipe.zremrangebyscore.assert_called_once()
        mock_pipe.expire.assert_called_once()
        mock_pipe.zcard.assert_called_once()
        mock_pipe.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_rate_limiter dependency
# ---------------------------------------------------------------------------


class TestGetRateLimiter:
    def test_returns_limiter_when_connected(self):
        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_client = MagicMock()
        mock_redis.client = mock_client

        with patch("app.services.redis_service.redis_service", mock_redis):
            limiter = get_rate_limiter()

        assert isinstance(limiter, AIRateLimiter)
        assert limiter.redis is mock_client

    def test_returns_limiter_with_none_when_disconnected(self):
        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with patch("app.services.redis_service.redis_service", mock_redis):
            limiter = get_rate_limiter()

        assert isinstance(limiter, AIRateLimiter)
        assert limiter.redis is None


# ---------------------------------------------------------------------------
# Middleware dependencies
# ---------------------------------------------------------------------------


class TestChatRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_under_limit_passes(self):
        """Under limit: no exception raised."""
        mock_user = MagicMock()
        mock_user.id = "user-123"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_rate_limit = AsyncMock(
            return_value=RateLimitResult(
                allowed=True,
                remaining=29,
                reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                limit=30,
                reset_seconds=60,
            )
        )
        mock_limiter.increment = AsyncMock(return_value=1)

        # Should not raise
        await check_chat_rate_limit(
            current_user=mock_user,
            rate_limiter=mock_limiter,
        )

        mock_limiter.increment.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        """Over limit: HTTPException 429 with rate limit headers."""
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-123"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_rate_limit = AsyncMock(
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


class TestImportRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-456"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_rate_limit = AsyncMock(
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
        assert "Import rate limit" in exc_info.value.detail


class TestReindexRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-789"

        mock_limiter = AsyncMock(spec=AIRateLimiter)
        mock_limiter.check_rate_limit = AsyncMock(
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
        assert "Reindex rate limit" in exc_info.value.detail

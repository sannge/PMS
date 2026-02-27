"""Unit tests for AI health check sub-section (Phase 7 -- 7.8).

Tests the _build_ai_health() function from app.main, covering:
- All providers healthy (connected=True)
- One provider timeout (returns degraded default)
- All providers failing (all return disconnected defaults)
- Document chunk count and pending job count
"""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Default "disconnected" values returned by _safe_check on error/timeout
DEFAULT_EMBEDDING = {"name": None, "model": None, "connected": False}
DEFAULT_CHAT = {"name": None, "model": None, "connected": False}
DEFAULT_SQL = {"scoped_views_count": 0, "last_query_at": None}


def _make_mock_session(execute_return=None, execute_side_effect=None):
    """Create a mock async session that works as an async context manager."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    if execute_side_effect:
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    elif execute_return is not None:
        mock_session.execute = AsyncMock(return_value=execute_return)
    return mock_session


@contextmanager
def _patch_health_deps(
    mock_registry=None,
    mock_session=None,
    mock_redis=None,
    valid_views=None,
):
    """Patch all dependencies used by _build_ai_health in one place."""
    if mock_session is None:
        mock_session = _make_mock_session()
    mock_maker = MagicMock(return_value=mock_session)

    if mock_redis is None:
        mock_redis = MagicMock()
        mock_redis.is_connected = False

    if mock_registry is None:
        mock_registry = AsyncMock()
        mock_registry.get_embedding_provider = AsyncMock(
            side_effect=Exception("not configured")
        )
        mock_registry.get_chat_provider = AsyncMock(
            side_effect=Exception("not configured")
        )

    if valid_views is None:
        valid_views = []

    with patch("app.database.async_session_maker", mock_maker), \
         patch("app.main.redis_service", mock_redis), \
         patch(
             "app.ai.provider_registry.ProviderRegistry",
             return_value=mock_registry,
         ), \
         patch("app.ai.schema_context.VALID_VIEW_NAMES", valid_views):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildAiHealthAllPass:
    """All AI sub-checks succeed."""

    @pytest.mark.asyncio
    async def test_all_providers_healthy(self):
        """When both providers connect, result shows connected=True."""
        mock_embedding_provider = AsyncMock()
        mock_embedding_provider.generate_embedding = AsyncMock(return_value=[0.1] * 768)
        mock_embedding_provider.__class__.__name__ = "OpenaiProvider"

        mock_chat_provider = AsyncMock()
        mock_chat_provider.chat_completion = AsyncMock(return_value=MagicMock())
        type(mock_chat_provider).__name__ = "OpenaiProvider"

        mock_registry = AsyncMock()
        mock_registry.get_embedding_provider = AsyncMock(
            return_value=(mock_embedding_provider, "text-embedding-3-small")
        )
        mock_registry.get_chat_provider = AsyncMock(
            return_value=(mock_chat_provider, "gpt-5")
        )

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        mock_session = _make_mock_session(execute_return=mock_result)

        with _patch_health_deps(
            mock_registry=mock_registry,
            mock_session=mock_session,
            valid_views=["v_tasks", "v_projects", "v_users"],
        ):
            from app.main import _build_ai_health
            result = await _build_ai_health()

        assert result["embedding_provider"]["connected"] is True
        assert result["embedding_provider"]["model"] == "text-embedding-3-small"
        assert result["chat_provider"]["connected"] is True
        assert result["chat_provider"]["model"] == "gpt-5"
        assert result["sql_access"]["scoped_views_count"] == 3
        assert result["document_chunks_count"] == 42


class TestBuildAiHealthOneTimeout:
    """One provider times out while the other succeeds."""

    @pytest.mark.asyncio
    async def test_embedding_timeout_chat_ok(self):
        """Embedding provider timeout returns degraded, chat still OK."""

        mock_chat_provider = AsyncMock()
        mock_chat_provider.chat_completion = AsyncMock(return_value=MagicMock())
        type(mock_chat_provider).__name__ = "AnthropicProvider"

        mock_registry = AsyncMock()

        async def slow_embedding(*args, **kwargs):
            await asyncio.sleep(10)  # Will be timed out by _safe_check

        mock_registry.get_embedding_provider = slow_embedding
        mock_registry.get_chat_provider = AsyncMock(
            return_value=(mock_chat_provider, "claude-sonnet-4-6")
        )

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_session = _make_mock_session(execute_return=mock_result)

        with _patch_health_deps(
            mock_registry=mock_registry,
            mock_session=mock_session,
            valid_views=["v_tasks"],
        ):
            from app.main import _build_ai_health
            result = await _build_ai_health()

        # Embedding timed out -> degraded default
        assert result["embedding_provider"] == DEFAULT_EMBEDDING
        # Chat still connected
        assert result["chat_provider"]["connected"] is True
        assert result["chat_provider"]["model"] == "claude-sonnet-4-6"


class TestBuildAiHealthAllFail:
    """All AI sub-checks fail or error out."""

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """When all providers fail, all return disconnected defaults."""
        from app.ai.provider_registry import ConfigurationError

        mock_registry = AsyncMock()
        mock_registry.get_embedding_provider = AsyncMock(
            side_effect=ConfigurationError("No embedding provider configured")
        )
        mock_registry.get_chat_provider = AsyncMock(
            side_effect=ConfigurationError("No chat provider configured")
        )

        mock_session = _make_mock_session(
            execute_side_effect=Exception("Database connection failed")
        )

        with _patch_health_deps(
            mock_registry=mock_registry,
            mock_session=mock_session,
            valid_views=[],
        ):
            from app.main import _build_ai_health
            result = await _build_ai_health()

        assert result["embedding_provider"] == DEFAULT_EMBEDDING
        assert result["chat_provider"] == DEFAULT_CHAT
        assert result["document_chunks_count"] == 0
        assert result["pending_embedding_jobs"] == 0


class TestBuildAiHealthPendingJobs:
    """Pending embedding jobs counter from Redis."""

    @pytest.mark.asyncio
    async def test_pending_jobs_redis_connected(self):
        """When Redis is connected, returns the ARQ queue depth."""
        mock_redis_client = AsyncMock()
        mock_redis_client.zcard = AsyncMock(return_value=7)

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.client = mock_redis_client

        mock_session = _make_mock_session(
            execute_side_effect=Exception("no db")
        )

        with _patch_health_deps(
            mock_session=mock_session,
            mock_redis=mock_redis,
            valid_views=[],
        ):
            from app.main import _build_ai_health
            result = await _build_ai_health()

        assert result["pending_embedding_jobs"] == 7

    @pytest.mark.asyncio
    async def test_pending_jobs_redis_disconnected(self):
        """When Redis is disconnected, returns 0."""
        mock_redis = MagicMock()
        mock_redis.is_connected = False

        mock_session = _make_mock_session(
            execute_side_effect=Exception("no db")
        )

        with _patch_health_deps(
            mock_session=mock_session,
            mock_redis=mock_redis,
            valid_views=[],
        ):
            from app.main import _build_ai_health
            result = await _build_ai_health()

        assert result["pending_embedding_jobs"] == 0

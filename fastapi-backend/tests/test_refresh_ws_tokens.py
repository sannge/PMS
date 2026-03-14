"""Tests for JWT refresh tokens and WebSocket connection tokens.

Covers:
- create_refresh_token: generates valid JWT with type=refresh claim
- validate_refresh_token: decodes and validates type claim
- rotate_refresh_token: blacklists old token and issues new pair
- create_ws_connection_token: stores opaque token in Redis
- validate_ws_connection_token: atomic GETDEL single-use consumption
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    rotate_refresh_token,
    validate_refresh_token,
    create_ws_connection_token,
    validate_ws_connection_token,
)


# ---------------------------------------------------------------------------
# JWT Refresh Tokens
# ---------------------------------------------------------------------------


class TestCreateRefreshToken:
    """Tests for create_refresh_token()."""

    def test_returns_nonempty_string(self):
        token = create_refresh_token("user-123", "test@example.com")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_has_refresh_type_claim(self):
        token = create_refresh_token("user-123", "test@example.com")
        data = validate_refresh_token(token)
        assert data is not None
        assert data.user_id == "user-123"
        assert data.email == "test@example.com"

    def test_token_has_jti_claim(self):
        token = create_refresh_token("user-123", "test@example.com")
        data = validate_refresh_token(token)
        assert data is not None
        assert data.jti is not None
        assert len(data.jti) > 0

    def test_token_has_future_expiration(self):
        token = create_refresh_token("user-123", "test@example.com")
        data = validate_refresh_token(token)
        assert data is not None
        assert data.exp is not None
        assert data.exp > datetime.now(timezone.utc)

    def test_two_tokens_have_different_jtis(self):
        t1 = create_refresh_token("user-123", "a@b.com")
        t2 = create_refresh_token("user-123", "a@b.com")
        d1 = validate_refresh_token(t1)
        d2 = validate_refresh_token(t2)
        assert d1.jti != d2.jti


class TestValidateRefreshToken:
    """Tests for validate_refresh_token()."""

    def test_valid_token_returns_token_data(self):
        token = create_refresh_token("user-abc", "x@y.com")
        data = validate_refresh_token(token)
        assert data is not None
        assert data.user_id == "user-abc"
        assert data.email == "x@y.com"

    def test_access_token_rejected(self):
        """Access tokens must NOT validate as refresh tokens."""
        access = create_access_token(data={"sub": "user-1", "email": "a@b.com"})
        result = validate_refresh_token(access)
        assert result is None

    def test_garbage_token_returns_none(self):
        result = validate_refresh_token("not.a.real.token")
        assert result is None

    def test_empty_string_returns_none(self):
        result = validate_refresh_token("")
        assert result is None

    def test_expired_token_returns_none(self):
        """Manually create an expired refresh token and verify rejection."""
        import jose.jwt as jwt
        from app.config import settings
        from app.services.auth_service import _refresh_secret

        expired_payload = {
            "sub": "user-1",
            "email": "a@b.com",
            "type": "refresh",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "jti": "expired-jti",
        }
        expired_token = jwt.encode(
            expired_payload,
            _refresh_secret(),
            algorithm=settings.jwt_algorithm,
        )
        result = validate_refresh_token(expired_token)
        assert result is None

    def test_wrong_type_claim_rejected(self):
        """Token with type != 'refresh' must be rejected."""
        import jose.jwt as jwt
        from app.config import settings
        from app.services.auth_service import _refresh_secret

        payload = {
            "sub": "user-1",
            "email": "a@b.com",
            "type": "access",  # wrong type
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
            "jti": "some-jti",
        }
        token = jwt.encode(
            payload,
            _refresh_secret(),
            algorithm=settings.jwt_algorithm,
        )
        result = validate_refresh_token(token)
        assert result is None


class TestRotateRefreshToken:
    """Tests for rotate_refresh_token()."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_new_pair(self):
        old_token = create_refresh_token("user-1", "a@b.com")
        with patch(
            "app.services.auth_service.is_token_blacklisted",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.services.auth_service.blacklist_token",
            new_callable=AsyncMock,
        ) as mock_blacklist:
            result = await rotate_refresh_token(old_token)

        assert result is not None
        new_access, new_refresh = result
        assert isinstance(new_access, str) and len(new_access) > 0
        assert isinstance(new_refresh, str) and len(new_refresh) > 0
        # Old token's JTI was blacklisted
        mock_blacklist.assert_called_once()

    @pytest.mark.asyncio
    async def test_blacklisted_token_returns_none(self):
        old_token = create_refresh_token("user-1", "a@b.com")
        with patch(
            "app.services.auth_service.is_token_blacklisted",
            new_callable=AsyncMock,
            return_value=True,  # already blacklisted
        ):
            result = await rotate_refresh_token(old_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        result = await rotate_refresh_token("garbage-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_new_refresh_token_is_different(self):
        old_token = create_refresh_token("user-1", "a@b.com")
        with patch(
            "app.services.auth_service.is_token_blacklisted",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.services.auth_service.blacklist_token",
            new_callable=AsyncMock,
        ):
            result = await rotate_refresh_token(old_token)

        assert result is not None
        _, new_refresh = result
        assert new_refresh != old_token

    @pytest.mark.asyncio
    async def test_new_refresh_token_is_valid(self):
        old_token = create_refresh_token("user-1", "a@b.com")
        with patch(
            "app.services.auth_service.is_token_blacklisted",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.services.auth_service.blacklist_token",
            new_callable=AsyncMock,
        ):
            result = await rotate_refresh_token(old_token)

        assert result is not None
        _, new_refresh = result
        data = validate_refresh_token(new_refresh)
        assert data is not None
        assert data.user_id == "user-1"


# ---------------------------------------------------------------------------
# WebSocket Connection Tokens
# ---------------------------------------------------------------------------


class TestCreateWsConnectionToken:
    """Tests for create_ws_connection_token()."""

    @pytest.mark.asyncio
    async def test_returns_hex_string(self):
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            token = await create_ws_connection_token("user-123")

        assert isinstance(token, str)
        assert len(token) == 64  # token_hex(32) = 64 hex chars

    @pytest.mark.asyncio
    async def test_stores_in_redis_with_30s_ttl(self):
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            token = await create_ws_connection_token("user-456")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        # Positional: key, value; keyword: ttl
        assert call_args[0][0] == f"ws_conn_token:{token}"
        assert call_args[0][1] == "user-456"
        assert call_args[1]["ttl"] == 30

    @pytest.mark.asyncio
    async def test_two_calls_return_different_tokens(self):
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            t1 = await create_ws_connection_token("user-1")
            t2 = await create_ws_connection_token("user-1")

        assert t1 != t2


class TestValidateWsConnectionToken:
    """Tests for validate_ws_connection_token()."""

    @staticmethod
    def _make_pipeline_mock(execute_return):
        """Create a mock Redis client whose pipeline().execute() returns the given list."""
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.delete = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=execute_return)

        mock_client = MagicMock()
        mock_client.pipeline = MagicMock(return_value=mock_pipe)
        # Support async context manager
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.client = mock_client
        return mock_redis, mock_pipe

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_id(self):
        mock_redis, mock_pipe = self._make_pipeline_mock([b"user-789", 1])
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            result = await validate_ws_connection_token("abc123")

        assert result == "user-789"
        mock_pipe.get.assert_called_once_with("ws_conn_token:abc123")
        mock_pipe.delete.assert_called_once_with("ws_conn_token:abc123")

    @pytest.mark.asyncio
    async def test_missing_token_returns_none(self):
        mock_redis, _ = self._make_pipeline_mock([None, 0])
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            result = await validate_ws_connection_token("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_redis_disconnected_returns_none(self):
        mock_redis = MagicMock()
        mock_redis.is_connected = False
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            result = await validate_ws_connection_token("any-token")

        assert result is None

    @pytest.mark.asyncio
    async def test_redis_error_returns_none(self):
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.delete = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=Exception("Redis error"))
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.client = mock_client
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            result = await validate_ws_connection_token("some-token")

        assert result is None

    @pytest.mark.asyncio
    async def test_single_use_via_getdel(self):
        """Pipeline GET+DELETE ensures the token is consumed atomically on first use."""
        # First call returns value, second returns None (already deleted)
        mock_redis1, _ = self._make_pipeline_mock([b"user-1", 1])
        mock_redis2, _ = self._make_pipeline_mock([None, 0])
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis1,
        ):
            first = await validate_ws_connection_token("token-xyz")
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis2,
        ):
            second = await validate_ws_connection_token("token-xyz")

        assert first == "user-1"
        assert second is None

    @pytest.mark.asyncio
    async def test_string_return_value(self):
        """When Redis returns a string (not bytes), it is returned as-is."""
        mock_redis, _ = self._make_pipeline_mock(["user-str", 1])
        with patch(
            "app.services.redis_service.redis_service",
            mock_redis,
        ):
            result = await validate_ws_connection_token("tok")

        assert result == "user-str"

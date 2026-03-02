"""Integration tests for OAuth flow endpoints.

Tests /api/ai/config/me/oauth/* endpoints (initiate, callback, disconnect, status),
token encryption, auto-model creation, and callback validation.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as fastapi_app
from app.models.ai_model import AiModel
from app.models.ai_provider import AiProvider
from app.models.user import User
from app.routers.ai_oauth import _check_oauth_initiate_rate_limit
from app.utils.timezone import utc_now


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Ensure AI encryption key is set for all tests in this module."""
    monkeypatch.setattr("app.config.settings.ai_encryption_key", TEST_ENCRYPTION_KEY)


@pytest.fixture(autouse=True)
def set_oauth_client_ids(monkeypatch):
    """Set OAuth client IDs for test runs."""
    monkeypatch.setattr("app.config.settings.openai_oauth_client_id", "test-openai-client")
    monkeypatch.setattr("app.config.settings.anthropic_oauth_client_id", "test-anthropic-client")
    monkeypatch.setattr("app.config.settings.oauth_state_ttl_seconds", 600)


@pytest.fixture
def mock_redis():
    """Provide a mock Redis service for state management.

    Sets get() to return None by default so token blacklist checks
    don't false-positive (is_token_blacklisted treats truthy result as blacklisted).
    """
    mock = AsyncMock()
    mock.is_connected = True
    mock.get = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_rate_limiter():
    """Mock rate limiter to allow all requests."""
    result = MagicMock()
    result.allowed = True
    result.remaining = 5
    result.reset_at = None
    return result


# ============================================================================
# Initiate endpoint
# ============================================================================


@pytest.mark.asyncio
class TestInitiateOAuth:
    """Tests for POST /api/ai/config/me/oauth/initiate."""

    async def test_initiate_returns_auth_url(
        self, client: AsyncClient, auth_headers: dict, test_user: User, mock_redis
    ):
        """Initiate returns 200 with auth_url and state."""
        mock_redis.set = AsyncMock()

        fastapi_app.dependency_overrides[_check_oauth_initiate_rate_limit] = lambda: None
        try:
            with patch("app.services.redis_service.redis_service", mock_redis):
                response = await client.post(
                    "/api/ai/config/me/oauth/initiate",
                    headers=auth_headers,
                    json={
                        "provider_type": "openai",
                        "redirect_uri": "http://localhost:3000/callback",
                    },
                )
        finally:
            fastapi_app.dependency_overrides.pop(_check_oauth_initiate_rate_limit, None)

        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "state" in data
        assert "auth.openai.com" in data["auth_url"]
        assert data["expires_in"] == 600

    async def test_initiate_requires_auth(self, client: AsyncClient):
        """401 without authentication token."""
        response = await client.post(
            "/api/ai/config/me/oauth/initiate",
            json={
                "provider_type": "openai",
                "redirect_uri": "http://localhost:3000/callback",
            },
        )
        assert response.status_code == 401

    async def test_initiate_invalid_provider(
        self, client: AsyncClient, auth_headers: dict
    ):
        """422 for unknown provider_type (schema validation)."""
        response = await client.post(
            "/api/ai/config/me/oauth/initiate",
            headers=auth_headers,
            json={
                "provider_type": "azure",
                "redirect_uri": "http://localhost:3000/callback",
            },
        )
        assert response.status_code == 422


# ============================================================================
# Callback endpoint
# ============================================================================


@pytest.mark.asyncio
class TestOAuthCallback:
    """Tests for POST /api/ai/config/me/oauth/callback."""

    async def _do_callback(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
        *,
        provider_type: str = "openai",
        code: str = "auth-code-xyz",
        state: str = "valid-state",
    ):
        """Helper to perform callback with mocked external dependencies."""
        import json as _json

        # Mock Redis: state lookup returns valid data (atomic GETDEL)
        state_data = _json.dumps({
            "user_id": str(test_user.id),
            "code_verifier": "test-verifier",
            "provider_type": provider_type,
        })
        mock_redis.client.getdel = AsyncMock(return_value=state_data)

        # Mock token exchange
        mock_exchange = AsyncMock(return_value={
            "access_token": "at-test-token",
            "refresh_token": "rt-test-token",
            "expires_in": 3600,
            "scope": "openai.chat openai.models.read",
        })

        # Mock registry refresh
        mock_refresh = AsyncMock()

        with (
            patch("app.services.redis_service.redis_service", mock_redis),
            patch.object(
                __import__("app.ai.oauth_service", fromlist=["OAuthService"]).OAuthService,
                "exchange_code_for_tokens",
                mock_exchange,
            ),
            patch("app.routers.ai_oauth.refresh_provider_cache", mock_refresh),
        ):
            return await client.post(
                "/api/ai/config/me/oauth/callback",
                headers=auth_headers,
                json={
                    "provider_type": provider_type,
                    "code": code,
                    "state": state,
                    "redirect_uri": "http://localhost:3000/callback",
                },
            )

    async def test_callback_stores_encrypted_tokens(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
        db_session: AsyncSession,
    ):
        """Callback stores Fernet-encrypted tokens in the database."""
        response = await self._do_callback(
            client, auth_headers, test_user, mock_redis
        )
        assert response.status_code == 200

        # Verify tokens are encrypted in DB
        result = await db_session.execute(
            select(AiProvider).where(
                AiProvider.user_id == test_user.id,
                AiProvider.auth_method == "oauth",
            )
        )
        provider = result.scalar_one()
        assert provider.oauth_access_token is not None
        assert provider.oauth_access_token != "at-test-token"

        # Verify we can decrypt back
        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())
        decrypted = fernet.decrypt(provider.oauth_access_token.encode()).decode()
        assert decrypted == "at-test-token"

    async def test_callback_creates_oauth_provider(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
        db_session: AsyncSession,
    ):
        """Callback creates an AiProvider with auth_method='oauth'."""
        response = await self._do_callback(
            client, auth_headers, test_user, mock_redis
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(AiProvider).where(
                AiProvider.user_id == test_user.id,
                AiProvider.scope == "user",
            )
        )
        provider = result.scalar_one()
        assert provider.auth_method == "oauth"
        assert provider.provider_type == "openai"
        assert provider.is_enabled is True

    async def test_callback_auto_creates_model(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
        db_session: AsyncSession,
    ):
        """Callback auto-creates an AiModel(capability='chat') under the provider."""
        response = await self._do_callback(
            client, auth_headers, test_user, mock_redis
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(AiModel)
            .join(AiProvider)
            .where(
                AiProvider.user_id == test_user.id,
                AiProvider.auth_method == "oauth",
            )
        )
        model = result.scalar_one()
        assert model.capability == "chat"
        assert model.is_default is True
        assert model.model_id == "gpt-4o"

    async def test_callback_invalid_state(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
    ):
        """Callback with bad state returns 400."""
        mock_redis.client.getdel = AsyncMock(return_value=None)

        with patch("app.services.redis_service.redis_service", mock_redis):
            response = await client.post(
                "/api/ai/config/me/oauth/callback",
                headers=auth_headers,
                json={
                    "provider_type": "openai",
                    "code": "auth-code",
                    "state": "invalid-state",
                    "redirect_uri": "http://localhost:3000/callback",
                },
            )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower() or "expired" in response.json()["detail"].lower()

    async def test_callback_expired_state(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
    ):
        """Callback with expired state (Redis returns None) returns 400."""
        mock_redis.client.getdel = AsyncMock(return_value=None)

        with patch("app.services.redis_service.redis_service", mock_redis):
            response = await client.post(
                "/api/ai/config/me/oauth/callback",
                headers=auth_headers,
                json={
                    "provider_type": "openai",
                    "code": "auth-code",
                    "state": "expired-state-token",
                    "redirect_uri": "http://localhost:3000/callback",
                },
            )

        assert response.status_code == 400

    async def test_callback_updates_existing(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
        db_session: AsyncSession,
    ):
        """Re-connecting updates existing provider, no duplicates."""
        # First callback
        await self._do_callback(client, auth_headers, test_user, mock_redis)

        # Second callback (re-connect)
        await self._do_callback(client, auth_headers, test_user, mock_redis)

        # Should have exactly one OAuth provider for this user
        result = await db_session.execute(
            select(AiProvider).where(
                AiProvider.user_id == test_user.id,
                AiProvider.scope == "user",
                AiProvider.auth_method == "oauth",
            )
        )
        providers = result.scalars().all()
        assert len(providers) == 1


# ============================================================================
# Disconnect endpoint
# ============================================================================


@pytest.mark.asyncio
class TestOAuthDisconnect:
    """Tests for DELETE /api/ai/config/me/oauth/disconnect."""

    async def test_disconnect_removes_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Disconnect clears OAuth columns and deletes the provider."""
        # Create an OAuth provider
        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())
        provider = AiProvider(
            name=f"openai-oauth-{test_user.id}",
            display_name="OpenAI (OAuth)",
            provider_type="openai",
            auth_method="oauth",
            oauth_access_token=fernet.encrypt(b"at-test").decode(),
            oauth_refresh_token=fernet.encrypt(b"rt-test").decode(),
            oauth_token_expires_at=utc_now() + timedelta(hours=1),
            scope="user",
            user_id=test_user.id,
            is_enabled=True,
        )
        db_session.add(provider)
        await db_session.commit()

        with (
            patch("app.routers.ai_oauth.refresh_provider_cache", AsyncMock()),
            patch(
                "app.ai.oauth_service.OAuthService.revoke_tokens",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.delete(
                "/api/ai/config/me/oauth/disconnect",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["disconnected"] is True
        assert data["fallback"] == "company_default"

        # Verify provider is gone
        result = await db_session.execute(
            select(AiProvider).where(
                AiProvider.user_id == test_user.id,
                AiProvider.auth_method == "oauth",
            )
        )
        assert result.scalar_one_or_none() is None


# ============================================================================
# Status endpoint
# ============================================================================


@pytest.mark.asyncio
class TestOAuthStatus:
    """Tests for GET /api/ai/config/me/oauth/status."""

    async def test_status_connected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Status returns connected=True with provider info when connected."""
        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())
        provider = AiProvider(
            name=f"openai-oauth-{test_user.id}",
            display_name="OpenAI (OAuth)",
            provider_type="openai",
            auth_method="oauth",
            oauth_access_token=fernet.encrypt(b"at-test").decode(),
            oauth_token_expires_at=utc_now() + timedelta(hours=1),
            oauth_scope="openai.chat openai.models.read",
            scope="user",
            user_id=test_user.id,
            is_enabled=True,
        )
        db_session.add(provider)
        await db_session.commit()

        response = await client.get(
            "/api/ai/config/me/oauth/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["provider_type"] == "openai"
        assert data["auth_method"] == "oauth"
        assert "openai.chat" in data["scopes"]

    async def test_status_not_connected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
    ):
        """Status returns connected=False when no OAuth connection exists."""
        response = await client.get(
            "/api/ai/config/me/oauth/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    async def test_status_no_tokens_returned(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Status response never contains access_token or refresh_token."""
        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())
        provider = AiProvider(
            name=f"openai-oauth-{test_user.id}",
            display_name="OpenAI (OAuth)",
            provider_type="openai",
            auth_method="oauth",
            oauth_access_token=fernet.encrypt(b"at-secret").decode(),
            oauth_refresh_token=fernet.encrypt(b"rt-secret").decode(),
            oauth_token_expires_at=utc_now() + timedelta(hours=1),
            scope="user",
            user_id=test_user.id,
            is_enabled=True,
        )
        db_session.add(provider)
        await db_session.commit()

        response = await client.get(
            "/api/ai/config/me/oauth/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" not in data
        assert "refresh_token" not in data
        assert "oauth_access_token" not in data
        assert "oauth_refresh_token" not in data


# ============================================================================
# Additional security and edge case tests (Round 3 QE findings)
# ============================================================================


@pytest.mark.asyncio
class TestOAuthEdgeCases:
    """Additional tests for security and edge cases identified in Round 3 review."""

    async def test_disconnect_no_provider_returns_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
    ):
        """Disconnect when no OAuth provider exists returns 404."""
        with patch("app.routers.ai_oauth.refresh_provider_cache", AsyncMock()):
            response = await client.delete(
                "/api/ai/config/me/oauth/disconnect",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert "No OAuth connection found" in response.json()["detail"]

    async def test_initiate_rejects_non_localhost_redirect(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        mock_redis,
    ):
        """Initiate rejects redirect_uri that doesn't target localhost."""
        mock_redis.set = AsyncMock()

        fastapi_app.dependency_overrides[_check_oauth_initiate_rate_limit] = lambda: None
        try:
            with patch("app.services.redis_service.redis_service", mock_redis):
                response = await client.post(
                    "/api/ai/config/me/oauth/initiate",
                    headers=auth_headers,
                    json={
                        "provider_type": "openai",
                        "redirect_uri": "https://evil.com/callback",
                    },
                )
        finally:
            fastapi_app.dependency_overrides.pop(_check_oauth_initiate_rate_limit, None)

        assert response.status_code == 400
        assert "redirect_uri must target localhost" in response.json()["detail"]

    async def test_callback_rejects_non_localhost_redirect(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
    ):
        """Callback rejects redirect_uri that doesn't target localhost."""
        response = await client.post(
            "/api/ai/config/me/oauth/callback",
            headers=auth_headers,
            json={
                "provider_type": "openai",
                "code": "auth-code",
                "state": "valid-state",
                "redirect_uri": "https://evil.com/callback",
            },
        )

        assert response.status_code == 400
        assert "redirect_uri must target localhost" in response.json()["detail"]

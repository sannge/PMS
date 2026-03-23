"""Unit tests for CodexProvider and ProviderRegistry OAuth resolution.

Tests CodexProvider initialization with OAuth access token, chat completion
success and auth error handling, and ProviderRegistry resolution of OAuth
providers including automatic token refresh.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.codex_provider import CodexProvider
from app.ai.exceptions import ProviderAuthError
from app.models.ai_model import AiModel
from app.models.ai_provider import AiProvider
from app.models.user import User
from app.utils.timezone import utc_now


# ---------------------------------------------------------------------------
# Encryption key fixture
# ---------------------------------------------------------------------------

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Ensure AI encryption key is set for all tests in this module."""
    monkeypatch.setattr("app.config.settings.ai_encryption_key", TEST_ENCRYPTION_KEY)


# ============================================================================
# CodexProvider unit tests
# ============================================================================


@pytest.mark.asyncio
class TestCodexProvider:
    """Tests for CodexProvider (OpenAI OAuth adapter)."""

    async def test_codex_uses_access_token(self):
        """CodexProvider initializes AsyncOpenAI with api_key=access_token."""
        with patch("app.ai.codex_provider.AsyncOpenAI") as mock_openai:
            CodexProvider(access_token="oauth-access-token-123")
            mock_openai.assert_called_once_with(api_key="oauth-access-token-123")

    async def test_codex_chat_success(self):
        """CodexProvider.chat_completion returns content from OpenAI response."""
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello from Codex!"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.ai.codex_provider.AsyncOpenAI", return_value=mock_client):
            provider = CodexProvider(access_token="test-token")
            result = await provider.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                model="gpt-4o",
            )
            assert result == "Hello from Codex!"

    async def test_codex_401_expired_token(self):
        """CodexProvider raises ProviderAuthError on AuthenticationError."""
        import openai

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Invalid token",
            response=MagicMock(status_code=401),
            body={"error": {"message": "Invalid token"}},
        )

        with patch("app.ai.codex_provider.AsyncOpenAI", return_value=mock_client):
            provider = CodexProvider(access_token="expired-token")
            with pytest.raises(ProviderAuthError) as exc_info:
                await provider.chat_completion(
                    messages=[{"role": "user", "content": "Hello"}],
                    model="gpt-4o",
                )
            assert exc_info.value.provider == "openai"
            assert exc_info.value.recoverable is True


# ============================================================================
# Provider registry resolution
# ============================================================================


@pytest.mark.asyncio
class TestRegistryOAuthResolution:
    """Tests for ProviderRegistry with OAuth providers."""

    async def test_registry_resolves_codex(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Registry builds CodexProvider for an OpenAI OAuth provider."""
        from app.ai.provider_registry import ProviderRegistry

        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())

        provider = AiProvider(
            name=f"openai-oauth-{test_user.id}",
            display_name="OpenAI (OAuth)",
            provider_type="openai",
            auth_method="oauth",
            oauth_access_token=fernet.encrypt(b"at-token").decode(),
            oauth_token_expires_at=utc_now() + timedelta(hours=1),
            scope="user",
            user_id=test_user.id,
            is_enabled=True,
        )
        db_session.add(provider)
        await db_session.flush()

        model = AiModel(
            provider_id=provider.id,
            model_id="gpt-4o",
            display_name="GPT-4o",
            provider_type="openai",
            capability="chat",
            is_default=True,
            is_enabled=True,
        )
        db_session.add(model)
        await db_session.commit()

        # Instantiate a fresh registry (bypass singleton for test isolation)
        registry = ProviderRegistry.__new__(ProviderRegistry)
        registry._cache = {}

        with patch("app.ai.codex_provider.AsyncOpenAI"):
            adapter, model_id = await registry.get_chat_provider(db_session, user_id=test_user.id)

        assert isinstance(adapter, CodexProvider)
        assert model_id == "gpt-4o"

    async def test_registry_auto_refresh(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Registry triggers token refresh when token is near expiry."""
        from app.ai.provider_registry import ProviderRegistry

        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())

        # Token expires in 2 minutes (within the 5-minute buffer)
        provider = AiProvider(
            name=f"openai-oauth-{test_user.id}",
            display_name="OpenAI (OAuth)",
            provider_type="openai",
            auth_method="oauth",
            oauth_access_token=fernet.encrypt(b"at-old").decode(),
            oauth_refresh_token=fernet.encrypt(b"rt-valid").decode(),
            oauth_token_expires_at=utc_now() + timedelta(minutes=2),
            scope="user",
            user_id=test_user.id,
            is_enabled=True,
        )
        db_session.add(provider)
        await db_session.flush()

        model = AiModel(
            provider_id=provider.id,
            model_id="gpt-4o",
            display_name="GPT-4o",
            provider_type="openai",
            capability="chat",
            is_default=True,
            is_enabled=True,
        )
        db_session.add(model)
        await db_session.commit()

        # Mock the refresh to succeed
        mock_refresh = AsyncMock(
            return_value={
                "access_token": "at-new-refreshed",
                "refresh_token": "rt-new-refreshed",
                "expires_in": 3600,
            }
        )

        registry = ProviderRegistry.__new__(ProviderRegistry)
        registry._cache = {}

        with (
            patch("app.ai.codex_provider.AsyncOpenAI"),
            patch(
                "app.ai.oauth_service.OAuthService.refresh_tokens",
                mock_refresh,
            ),
        ):
            adapter, model_id = await registry.get_chat_provider(db_session, user_id=test_user.id)

        # Refresh should have been called
        mock_refresh.assert_called_once()
        assert isinstance(adapter, CodexProvider)

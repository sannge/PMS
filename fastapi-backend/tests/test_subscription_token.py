"""Unit tests for subscription token feature.

Tests cover:
- _validate_token helper: success/auth-error/permission-error/timeout per provider
- ProviderRegistry._build_adapter with auth_method='session_token'
- SubscriptionTokenRequest Pydantic validation (length, provider_type, chars, whitespace)
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.ai_oauth import _validate_token
from app.schemas.oauth import SubscriptionTokenRequest
from app.ai.provider_registry import ConfigurationError, ProviderRegistry


# ---------------------------------------------------------------------------
# TestValidateToken
# ---------------------------------------------------------------------------


class TestValidateToken:
    """Test the _validate_token helper function directly."""

    @pytest.mark.asyncio
    async def test_openai_success(self):
        """OpenAI token validated via models.list() succeeding."""
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=MagicMock())

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("openai", "sk-test-valid-key-1234")

        assert success is True
        assert "validated" in message.lower() or "success" in message.lower()
        assert isinstance(latency, int)
        assert latency >= 0
        assert token_mode == "apikey"

    @pytest.mark.asyncio
    async def test_anthropic_success_bearer(self):
        """Anthropic token validated via messages.create() with auth_token (bearer) path."""
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=MagicMock())

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("anthropic", "oauth-long-lived-token-1234")

        assert success is True
        assert "validated" in message.lower() or "success" in message.lower()
        assert isinstance(latency, int)
        assert latency >= 0
        # Bearer is tried first, so non-sk-ant tokens succeed as bearer
        assert token_mode == "bearer"

    @pytest.mark.asyncio
    async def test_anthropic_success_apikey_fallback(self):
        """Anthropic token falls back to api_key mode when bearer fails."""
        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("bearer auth failed")
            return MagicMock()

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=side_effect)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("anthropic", "sk-ant-test-valid-key-1234")

        assert success is True
        assert token_mode == "apikey"

    @pytest.mark.asyncio
    async def test_openai_auth_error(self):
        """OpenAI AuthenticationError returns (False, 'Invalid token', latency)."""
        from openai import AuthenticationError as OpenAIAuthError

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        auth_err = OpenAIAuthError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )
        mock_client.models.list = AsyncMock(side_effect=auth_err)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("openai", "sk-bad-key-12345")

        assert success is False
        assert "invalid" in message.lower() or "auth" in message.lower()
        assert isinstance(latency, int)

    @pytest.mark.asyncio
    async def test_anthropic_auth_error(self):
        """Anthropic AuthenticationError returns (False, 'Invalid token', latency)."""
        from anthropic import AuthenticationError as AnthropicAuthError

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.is_closed = True
        auth_err = AnthropicAuthError(
            message="Invalid x-api-key",
            response=mock_response,
            body={"error": {"message": "Invalid x-api-key"}},
        )
        # Both bearer and apikey paths raise the same auth error
        mock_client.messages.create = AsyncMock(side_effect=auth_err)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("anthropic", "sk-ant-bad-key-1234")

        assert success is False
        assert "invalid" in message.lower() or "auth" in message.lower()
        assert isinstance(latency, int)

    @pytest.mark.asyncio
    async def test_openai_permission_error(self):
        """OpenAI PermissionDeniedError returns (False, 'lacks permissions', latency)."""
        from openai import PermissionDeniedError as OpenAIPermError

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {}
        perm_err = OpenAIPermError(
            message="Insufficient permissions",
            response=mock_response,
            body={"error": {"message": "Insufficient permissions"}},
        )
        mock_client.models.list = AsyncMock(side_effect=perm_err)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("openai", "sk-noperm-key-12345")

        assert success is False
        assert "permission" in message.lower()
        assert isinstance(latency, int)

    @pytest.mark.asyncio
    async def test_unsupported_provider(self):
        """Unsupported provider returns (False, 'Unsupported', None)."""
        success, message, latency, token_mode = await _validate_token("ollama", "some-token-value")

        assert success is False
        assert "unsupported" in message.lower()
        assert latency is None

    @pytest.mark.asyncio
    async def test_generic_error(self):
        """Generic Exception returns (False, 'Validation failed: ...', latency)."""
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(side_effect=RuntimeError("Connection reset by peer"))

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("openai", "sk-test-generic-err")

        assert success is False
        assert "validation failed" in message.lower() or "RuntimeError" in message
        assert isinstance(latency, int)

    @pytest.mark.asyncio
    async def test_timeout(self):
        """asyncio.TimeoutError is caught and returns a friendly message."""
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            success, message, latency, token_mode = await _validate_token("openai", "sk-test-timeout-key")

        assert success is False
        assert "timed out" in message.lower() or "timeout" in message.lower()
        assert isinstance(latency, int)


# ---------------------------------------------------------------------------
# TestProviderRegistrySessionToken
# ---------------------------------------------------------------------------


class TestProviderRegistrySessionToken:
    """Test ProviderRegistry._build_adapter with auth_method='session_token'."""

    def _make_provider(self, **overrides) -> MagicMock:
        """Create a mock AiProvider with session_token defaults."""
        provider = MagicMock()
        provider.name = overrides.get("name", "test-provider")
        provider.auth_method = overrides.get("auth_method", "session_token")
        provider.provider_type = overrides.get("provider_type", "openai")
        provider.oauth_access_token = overrides.get("oauth_access_token", "encrypted-token")
        provider.api_key_encrypted = overrides.get("api_key_encrypted", None)
        provider.base_url = overrides.get("base_url", None)
        provider.oauth_scope = overrides.get("oauth_scope", "apikey")
        return provider

    def test_session_token_openai_returns_codex(self):
        """session_token + openai creates CodexProvider."""
        provider = self._make_provider(provider_type="openai")
        registry = ProviderRegistry()

        with patch("app.ai.provider_registry.ApiKeyEncryption") as MockEnc:
            MockEnc.return_value.decrypt.return_value = "decrypted-access-token"
            adapter = registry._build_adapter(provider, api_key=None)

        from app.ai.codex_provider import CodexProvider

        assert isinstance(adapter, CodexProvider)

    def test_session_token_anthropic_returns_anthropic(self):
        """session_token + anthropic creates AnthropicProvider."""
        provider = self._make_provider(provider_type="anthropic")
        registry = ProviderRegistry()

        with patch("app.ai.provider_registry.ApiKeyEncryption") as MockEnc:
            MockEnc.return_value.decrypt.return_value = "decrypted-access-token"
            adapter = registry._build_adapter(provider, api_key=None)

        from app.ai.anthropic_provider import AnthropicProvider

        assert isinstance(adapter, AnthropicProvider)

    def test_session_token_anthropic_bearer_mode(self):
        """session_token + anthropic + oauth_scope='bearer' uses auth_token param."""
        provider = self._make_provider(
            provider_type="anthropic",
            oauth_scope="bearer",
        )
        registry = ProviderRegistry()

        with patch("app.ai.provider_registry.ApiKeyEncryption") as MockEnc:
            MockEnc.return_value.decrypt.return_value = "decrypted-bearer-token"
            adapter = registry._build_adapter(provider, api_key=None)

        from app.ai.anthropic_provider import AnthropicProvider

        assert isinstance(adapter, AnthropicProvider)

    def test_session_token_no_access_token_raises(self):
        """session_token with no access token raises ConfigurationError."""
        provider = self._make_provider(
            provider_type="openai",
            oauth_access_token=None,
        )
        registry = ProviderRegistry()

        with pytest.raises(ConfigurationError, match="no access token"):
            registry._build_adapter(provider, api_key=None)

    def test_session_token_unsupported_type_raises(self):
        """session_token + ollama raises ConfigurationError."""
        provider = self._make_provider(
            provider_type="ollama",
            oauth_access_token="encrypted-token",
        )
        registry = ProviderRegistry()

        with patch("app.ai.provider_registry.ApiKeyEncryption") as MockEnc:
            MockEnc.return_value.decrypt.return_value = "decrypted-access-token"
            with pytest.raises(ConfigurationError, match="not supported"):
                registry._build_adapter(provider, api_key=None)

    def test_session_token_corrupt_token_raises(self):
        """session_token with corrupt encrypted token raises ConfigurationError."""
        provider = self._make_provider(provider_type="openai")
        registry = ProviderRegistry()

        with patch("app.ai.provider_registry.ApiKeyEncryption") as MockEnc:
            MockEnc.return_value.decrypt.side_effect = Exception("InvalidToken")
            with pytest.raises(ConfigurationError, match="corrupt"):
                registry._build_adapter(provider, api_key=None)

    def test_token_needs_refresh_false_for_session_token(self):
        """Session tokens don't have a refresh flow, so returns False."""
        provider = self._make_provider(auth_method="session_token")
        registry = ProviderRegistry()

        assert registry._token_needs_refresh(provider) is False


# ---------------------------------------------------------------------------
# TestSubscriptionTokenSchemas
# ---------------------------------------------------------------------------


class TestSubscriptionTokenSchemas:
    """Test Pydantic validation for SubscriptionTokenRequest."""

    def test_token_too_short(self):
        """Token shorter than min_length=10 raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SubscriptionTokenRequest(
                provider_type="openai",
                token="short",
            )

    def test_token_too_long(self):
        """Token longer than max_length=4096 raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SubscriptionTokenRequest(
                provider_type="openai",
                token="x" * 4097,
            )

    def test_invalid_provider_type(self):
        """Invalid provider_type raises ValidationError (Literal constraint)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SubscriptionTokenRequest(
                provider_type="azure",
                token="valid-token-at-least-10",
            )

    def test_preferred_model_too_long(self):
        """preferred_model exceeding max_length=100 raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SubscriptionTokenRequest(
                provider_type="openai",
                token="valid-token-at-least-10",
                preferred_model="m" * 101,
            )

    def test_preferred_model_invalid_chars(self):
        """preferred_model with special characters raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="invalid characters"):
            SubscriptionTokenRequest(
                provider_type="openai",
                token="valid-token-at-least-10",
                preferred_model="gpt-4o; DROP TABLE",
            )

    def test_token_whitespace_stripped(self):
        """Token with leading/trailing whitespace is stripped."""
        req = SubscriptionTokenRequest(
            provider_type="openai",
            token="  sk-valid-test-token-1234567890  ",
        )
        assert req.token == "sk-valid-test-token-1234567890"

    def test_token_blank_after_strip_rejected(self):
        """Token that is only whitespace raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="blank"):
            SubscriptionTokenRequest(
                provider_type="openai",
                token="              ",  # 14 spaces (passes min_length but blank)
            )

    def test_valid_request_openai(self):
        """Valid OpenAI request passes validation."""
        req = SubscriptionTokenRequest(
            provider_type="openai",
            token="sk-valid-test-token-1234567890",
            preferred_model="gpt-4o",
        )
        assert req.provider_type == "openai"
        assert req.token == "sk-valid-test-token-1234567890"
        assert req.preferred_model == "gpt-4o"

    def test_valid_request_anthropic(self):
        """Valid Anthropic request passes validation."""
        req = SubscriptionTokenRequest(
            provider_type="anthropic",
            token="sk-ant-valid-test-token-1234567890",
        )
        assert req.provider_type == "anthropic"
        assert req.preferred_model is None

    def test_valid_request_no_model(self):
        """Request without preferred_model defaults to None."""
        req = SubscriptionTokenRequest(
            provider_type="openai",
            token="sk-test-token-at-least-ten-chars",
        )
        assert req.preferred_model is None

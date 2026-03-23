"""Unit tests for OAuthService: PKCE generation, state management, and token exchange.

Tests PKCE pair generation (length, charset, S256 correctness, no padding, uniqueness),
Redis state storage/retrieval/expiry/single-use, auth URL generation for each provider,
token exchange success/failure, and refresh success/failure.
"""

import base64
import hashlib
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from app.ai.exceptions import OAuthError
from app.ai.oauth_service import OAuthService


# ---------------------------------------------------------------------------
# PKCE pair generation
# ---------------------------------------------------------------------------


class TestPKCEGeneration:
    """Tests for OAuthService.generate_pkce_pair."""

    def test_code_verifier_length(self):
        """code_verifier is 43-128 characters per RFC 7636."""
        verifier, _ = OAuthService.generate_pkce_pair()
        assert 43 <= len(verifier) <= 128

    def test_code_verifier_url_safe(self):
        """code_verifier contains only unreserved characters [A-Za-z0-9\\-._~]."""
        verifier, _ = OAuthService.generate_pkce_pair()
        assert re.fullmatch(r"[A-Za-z0-9\-._~]+", verifier), f"Verifier contains invalid characters: {verifier}"

    def test_code_challenge_s256(self):
        """code_challenge equals BASE64URL(SHA256(code_verifier))."""
        verifier, challenge = OAuthService.generate_pkce_pair()

        # Manually compute expected challenge
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        assert challenge == expected

    def test_code_challenge_no_padding(self):
        """code_challenge has no '=' padding characters."""
        _, challenge = OAuthService.generate_pkce_pair()
        assert "=" not in challenge

    def test_pkce_pair_unique(self):
        """Each call produces a different PKCE pair."""
        pair1 = OAuthService.generate_pkce_pair()
        pair2 = OAuthService.generate_pkce_pair()
        assert pair1[0] != pair2[0], "code_verifiers should differ"
        assert pair1[1] != pair2[1], "code_challenges should differ"


# ---------------------------------------------------------------------------
# State management (Redis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStateManagement:
    """Tests for Redis-backed OAuth state tokens."""

    async def test_state_stored_in_redis(self):
        """_store_state calls Redis SET with the correct key and TTL."""
        user_id = uuid4()
        mock_redis = AsyncMock()

        with (
            patch("app.services.redis_service.redis_service", mock_redis),
            patch("app.ai.oauth_service.settings") as mock_settings,
        ):
            mock_settings.oauth_state_ttl_seconds = 600
            mock_settings.openai_oauth_client_id = "test-client"

            svc = OAuthService()
            state = await svc._store_state(user_id, "verifier123", "openai")

            # Verify Redis was called
            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            key = call_args[0][0]
            stored_data = json.loads(call_args[0][1])
            ttl = call_args[1].get("ttl") or call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("ttl")

            assert key == f"oauth_state:{state}"
            assert stored_data["user_id"] == str(user_id)
            assert stored_data["code_verifier"] == "verifier123"
            assert stored_data["provider_type"] == "openai"
            assert ttl == 600

    async def test_state_expires_after_ttl(self):
        """State returns None after TTL expires (simulated by Redis returning None)."""
        user_id = uuid4()
        mock_redis = AsyncMock()
        mock_redis.client.getdel = AsyncMock(return_value=None)

        with patch("app.services.redis_service.redis_service", mock_redis):
            svc = OAuthService()
            result = await svc._validate_state("expired-state", user_id)
            assert result is None

    async def test_state_single_use(self):
        """State is deleted after first read; second read returns None (atomic GETDEL)."""
        user_id = uuid4()
        state_data = json.dumps(
            {
                "user_id": str(user_id),
                "code_verifier": "verifier123",
                "provider_type": "openai",
            }
        )

        call_count = 0

        async def mock_getdel(key):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return state_data
            return None  # Already consumed

        mock_redis = AsyncMock()
        mock_redis.client.getdel = AsyncMock(side_effect=mock_getdel)

        with patch("app.services.redis_service.redis_service", mock_redis):
            svc = OAuthService()

            # First read succeeds (atomically gets and deletes)
            result1 = await svc._validate_state("test-state", user_id)
            assert result1 is not None
            assert result1 == ("verifier123", "openai")

            # Second read fails (state consumed by GETDEL)
            result2 = await svc._validate_state("test-state", user_id)
            assert result2 is None

    async def test_invalid_state_fails(self):
        """Unknown state token returns None."""
        mock_redis = AsyncMock()
        mock_redis.client.getdel = AsyncMock(return_value=None)

        with patch("app.services.redis_service.redis_service", mock_redis):
            svc = OAuthService()
            result = await svc._validate_state("unknown-token", uuid4())
            assert result is None


# ---------------------------------------------------------------------------
# Auth URL generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuthUrlGeneration:
    """Tests for generate_auth_url."""

    async def test_openai_auth_url(self):
        """OpenAI auth URL includes client_id, code_challenge, S256, state, scopes."""
        user_id = uuid4()
        mock_redis = AsyncMock()

        with (
            patch("app.services.redis_service.redis_service", mock_redis),
            patch("app.ai.oauth_service.settings") as mock_settings,
        ):
            mock_settings.oauth_state_ttl_seconds = 600
            mock_settings.openai_oauth_client_id = "oi-client-id-123"
            mock_settings.anthropic_oauth_client_id = ""

            svc = OAuthService()
            auth_url, state = await svc.generate_auth_url(
                provider_type="openai",
                redirect_uri="http://localhost:3000/callback",
                user_id=user_id,
            )

            parsed = urlparse(auth_url)
            params = parse_qs(parsed.query)

            assert parsed.netloc == "auth.openai.com"
            assert params["client_id"] == ["oi-client-id-123"]
            assert params["code_challenge_method"] == ["S256"]
            assert "code_challenge" in params
            assert params["state"] == [state]
            assert params["scope"] == ["openai.chat openai.models.read"]
            assert params["response_type"] == ["code"]

    async def test_anthropic_auth_url(self):
        """Anthropic auth URL has correct params and host."""
        user_id = uuid4()
        mock_redis = AsyncMock()

        with (
            patch("app.services.redis_service.redis_service", mock_redis),
            patch("app.ai.oauth_service.settings") as mock_settings,
        ):
            mock_settings.oauth_state_ttl_seconds = 600
            mock_settings.openai_oauth_client_id = ""
            mock_settings.anthropic_oauth_client_id = "an-client-id-456"

            svc = OAuthService()
            auth_url, state = await svc.generate_auth_url(
                provider_type="anthropic",
                redirect_uri="http://localhost:3000/callback",
                user_id=user_id,
            )

            parsed = urlparse(auth_url)
            params = parse_qs(parsed.query)

            assert parsed.netloc == "claude.ai"
            assert params["client_id"] == ["an-client-id-456"]
            assert params["code_challenge_method"] == ["S256"]
            assert params["scope"] == ["claude.chat claude.models.read"]


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenExchange:
    """Tests for exchange_code_for_tokens."""

    async def test_exchange_openai_success(self):
        """Successful OpenAI code exchange returns tokens."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "at-openai-123",
            "refresh_token": "rt-openai-456",
            "expires_in": 3600,
            "scope": "openai.chat openai.models.read",
        }

        with (
            patch("app.ai.oauth_service.settings") as mock_settings,
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
        ):
            mock_settings.openai_oauth_client_id = "oi-client"
            mock_settings.anthropic_oauth_client_id = ""

            svc = OAuthService()
            tokens = await svc.exchange_code_for_tokens(
                provider_type="openai",
                code="auth-code-xyz",
                redirect_uri="http://localhost:3000/callback",
                code_verifier="verifier123",
            )

            assert tokens["access_token"] == "at-openai-123"
            assert tokens["refresh_token"] == "rt-openai-456"
            assert tokens["expires_in"] == 3600
            assert tokens["scope"] == "openai.chat openai.models.read"

    async def test_exchange_anthropic_success(self):
        """Successful Anthropic code exchange returns tokens."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "at-anthropic-789",
            "refresh_token": "rt-anthropic-012",
            "expires_in": 7200,
            "scope": "claude.chat claude.models.read",
        }

        with (
            patch("app.ai.oauth_service.settings") as mock_settings,
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
        ):
            mock_settings.openai_oauth_client_id = ""
            mock_settings.anthropic_oauth_client_id = "an-client"

            svc = OAuthService()
            tokens = await svc.exchange_code_for_tokens(
                provider_type="anthropic",
                code="auth-code-abc",
                redirect_uri="http://localhost:3000/callback",
                code_verifier="verifier456",
            )

            assert tokens["access_token"] == "at-anthropic-789"
            assert tokens["refresh_token"] == "rt-anthropic-012"
            assert tokens["expires_in"] == 7200

    async def test_exchange_invalid_code(self):
        """Exchange with invalid code raises OAuthError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "invalid_grant"}'

        with (
            patch("app.ai.oauth_service.settings") as mock_settings,
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
        ):
            mock_settings.openai_oauth_client_id = "oi-client"

            svc = OAuthService()
            with pytest.raises(OAuthError, match="Token exchange failed"):
                await svc.exchange_code_for_tokens(
                    provider_type="openai",
                    code="bad-code",
                    redirect_uri="http://localhost:3000/callback",
                    code_verifier="verifier123",
                )


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenRefresh:
    """Tests for refresh_tokens."""

    async def test_refresh_success(self):
        """Successful refresh returns new access token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "at-new-refreshed",
            "refresh_token": "rt-new-refreshed",
            "expires_in": 3600,
        }

        with (
            patch("app.ai.oauth_service.settings") as mock_settings,
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
        ):
            mock_settings.openai_oauth_client_id = "oi-client"

            svc = OAuthService()
            tokens = await svc.refresh_tokens(
                provider_type="openai",
                refresh_token="rt-old-token",
            )

            assert tokens["access_token"] == "at-new-refreshed"
            assert tokens["refresh_token"] == "rt-new-refreshed"
            assert tokens["expires_in"] == 3600

    async def test_refresh_revoked(self):
        """Refresh with revoked token raises OAuthError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "invalid_grant", "error_description": "Token revoked"}'

        with (
            patch("app.ai.oauth_service.settings") as mock_settings,
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
        ):
            mock_settings.openai_oauth_client_id = "oi-client"

            svc = OAuthService()
            with pytest.raises(OAuthError, match="Token refresh failed"):
                await svc.refresh_tokens(
                    provider_type="openai",
                    refresh_token="revoked-refresh-token",
                )

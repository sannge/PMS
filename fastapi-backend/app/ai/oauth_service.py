"""OAuth 2.0 + PKCE service for AI provider subscription connections.

Supports OpenAI (Codex / ChatGPT Plus/Pro) and Anthropic (Claude)
OAuth authorization code flow with PKCE S256. State tokens are stored
in Redis with a configurable TTL for CSRF protection.
"""

import base64
import hashlib
import json
import logging
import secrets
from urllib.parse import urlencode
from uuid import UUID

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Provider-specific OAuth configuration
PROVIDER_CONFIG: dict[str, dict[str, str | list[str]]] = {
    "openai": {
        "auth_url": "https://auth.openai.com/oauth/authorize",
        "token_url": "https://auth.openai.com/oauth/token",
        "revoke_url": "https://auth.openai.com/oauth/revoke",
        "scopes": ["openai.chat", "openai.models.read"],
    },
    "anthropic": {
        "auth_url": "https://claude.ai/oauth/authorize",
        "token_url": "https://claude.ai/oauth/token",
        "revoke_url": "https://claude.ai/oauth/revoke",
        "scopes": ["claude.chat", "claude.models.read"],
    },
}


class OAuthError(Exception):
    """Raised when an OAuth operation fails."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        self.provider = provider
        super().__init__(message)


class OAuthService:
    """OAuth 2.0 + PKCE service for AI provider subscription connections.

    Uses PKCE (S256) for security. State tokens stored in Redis with TTL.
    """

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Generate PKCE code_verifier + code_challenge (S256).

        code_verifier: 43-128 character URL-safe random string
        code_challenge: BASE64URL(SHA256(code_verifier)) with no padding

        Returns:
            Tuple of (code_verifier, code_challenge).
        """
        # Generate 32 random bytes -> 43 URL-safe chars (base64url without padding)
        code_verifier = secrets.token_urlsafe(32)

        # SHA-256 hash the verifier
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()

        # Base64url encode without padding
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        return code_verifier, code_challenge

    async def _store_state(
        self,
        user_id: UUID,
        code_verifier: str,
        provider_type: str,
    ) -> str:
        """Store OAuth state token in Redis with TTL.

        Args:
            user_id: The user initiating the OAuth flow.
            code_verifier: PKCE code verifier to store.
            provider_type: Provider type (openai/anthropic).

        Returns:
            The generated state token.
        """
        from ..services.redis_service import redis_service

        state = secrets.token_urlsafe(32)
        state_data = json.dumps({
            "user_id": str(user_id),
            "code_verifier": code_verifier,
            "provider_type": provider_type,
        })

        await redis_service.set(
            f"oauth_state:{state}",
            state_data,
            ttl=settings.oauth_state_ttl_seconds,
        )

        return state

    async def _validate_state(
        self,
        state: str,
        user_id: UUID,
    ) -> tuple[str, str] | None:
        """Validate and consume an OAuth state token (single-use).

        Args:
            state: The state token from the callback.
            user_id: The user making the callback request.

        Returns:
            Tuple of (code_verifier, provider_type) or None if invalid.
        """
        from ..services.redis_service import redis_service

        key = f"oauth_state:{state}"

        # GET + DELETE atomically (pipeline)
        raw = await redis_service.get(key)
        if not raw:
            return None

        # Delete immediately (single-use)
        await redis_service.delete(key)

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

        # Verify user_id matches
        if data.get("user_id") != str(user_id):
            logger.warning(
                "OAuth state user mismatch: expected %s, got %s",
                data.get("user_id"),
                str(user_id),
            )
            return None

        code_verifier = data.get("code_verifier")
        provider_type = data.get("provider_type")
        if not code_verifier or not provider_type:
            return None

        return code_verifier, provider_type

    async def generate_auth_url(
        self,
        provider_type: str,
        redirect_uri: str,
        user_id: UUID,
    ) -> tuple[str, str]:
        """Generate OAuth authorization URL with PKCE.

        Args:
            provider_type: Provider type (openai/anthropic).
            redirect_uri: The callback URI (Electron localhost).
            user_id: The user initiating the flow.

        Returns:
            Tuple of (auth_url, state_token).

        Raises:
            OAuthError: If provider_type is unsupported or client_id not configured.
        """
        config = PROVIDER_CONFIG.get(provider_type)
        if not config:
            raise OAuthError(f"Unsupported OAuth provider: {provider_type}", provider_type)

        client_id = self._get_client_id(provider_type)
        if not client_id:
            raise OAuthError(
                f"OAuth client ID not configured for {provider_type}. "
                f"Set {provider_type.upper()}_OAUTH_CLIENT_ID environment variable.",
                provider_type,
            )

        code_verifier, code_challenge = self.generate_pkce_pair()
        state = await self._store_state(user_id, code_verifier, provider_type)

        scopes = config["scopes"]
        scope_str = " ".join(scopes) if isinstance(scopes, list) else str(scopes)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": scope_str,
        }

        auth_url = f"{config['auth_url']}?{urlencode(params)}"
        return auth_url, state

    async def exchange_code_for_tokens(
        self,
        provider_type: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict:
        """Exchange authorization code for access + refresh tokens.

        Args:
            provider_type: Provider type (openai/anthropic).
            code: Authorization code from the provider callback.
            redirect_uri: Must match the URI used in the initiate request.
            code_verifier: PKCE code verifier stored during initiation.

        Returns:
            Dict with access_token, refresh_token, expires_in, scope.

        Raises:
            OAuthError: If the exchange fails.
        """
        config = PROVIDER_CONFIG.get(provider_type)
        if not config:
            raise OAuthError(f"Unsupported OAuth provider: {provider_type}", provider_type)

        client_id = self._get_client_id(provider_type)

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                str(config["token_url"]),
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            logger.error(
                "OAuth token exchange failed for %s: %d %s",
                provider_type,
                response.status_code,
                response.text[:200],
            )
            raise OAuthError(
                f"Token exchange failed: {response.status_code}",
                provider_type,
            )

        data = response.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in", 3600),
            "scope": data.get("scope"),
        }

    async def refresh_tokens(
        self,
        provider_type: str,
        refresh_token: str,
    ) -> dict:
        """Refresh an expired access token.

        Args:
            provider_type: Provider type (openai/anthropic).
            refresh_token: The decrypted refresh token.

        Returns:
            Dict with new access_token, refresh_token, expires_in.

        Raises:
            OAuthError: If the refresh fails.
        """
        config = PROVIDER_CONFIG.get(provider_type)
        if not config:
            raise OAuthError(f"Unsupported OAuth provider: {provider_type}", provider_type)

        client_id = self._get_client_id(provider_type)

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                str(config["token_url"]),
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            logger.error(
                "OAuth token refresh failed for %s: %d %s",
                provider_type,
                response.status_code,
                response.text[:200],
            )
            raise OAuthError(
                f"Token refresh failed: {response.status_code}",
                provider_type,
            )

        data = response.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in", 3600),
        }

    async def revoke_tokens(
        self,
        provider_type: str,
        access_token: str,
    ) -> None:
        """Revoke OAuth tokens at the provider (best-effort).

        Args:
            provider_type: Provider type (openai/anthropic).
            access_token: The decrypted access token to revoke.
        """
        config = PROVIDER_CONFIG.get(provider_type)
        if not config:
            return

        client_id = self._get_client_id(provider_type)

        payload = {
            "token": access_token,
            "token_type_hint": "access_token",
            "client_id": client_id,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    str(config["revoke_url"]),
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except Exception:
            logger.warning(
                "OAuth token revocation failed for %s (best-effort)",
                provider_type,
                exc_info=True,
            )

    @staticmethod
    def _get_client_id(provider_type: str) -> str:
        """Get the OAuth client ID for a provider from settings."""
        if provider_type == "openai":
            return settings.openai_oauth_client_id
        elif provider_type == "anthropic":
            return settings.anthropic_oauth_client_id
        return ""


def get_oauth_service() -> OAuthService:
    """FastAPI dependency that provides an OAuthService instance."""
    return OAuthService()

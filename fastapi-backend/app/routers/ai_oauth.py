"""AI OAuth subscription connection endpoints.

Provides endpoints for connecting, disconnecting, and checking the status
of OAuth-based AI provider subscriptions (OpenAI Codex, Anthropic Claude).
All tokens are Fernet-encrypted before database storage and never returned
in API responses.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..ai.encryption import ApiKeyEncryption
from ..ai.exceptions import OAuthError
from ..ai.oauth_service import OAuthService, get_oauth_service
from ..ai.provider_registry import refresh_provider_cache
from ..ai.rate_limiter import AIRateLimiter, get_rate_limiter, _raise_rate_limit
from ..config import settings
from ..database import get_db
from ..models.ai_model import AiModel
from ..models.ai_provider import AiProvider
from ..models.user import User
from ..schemas.oauth import (
    OAuthCallbackRequest,
    OAuthConnectionStatus,
    OAuthDisconnectResponse,
    OAuthInitiateRequest,
    OAuthInitiateResponse,
)
from ..services.auth_service import get_current_user
from ..utils.timezone import utc_now

logger = logging.getLogger(__name__)

_ALLOWED_REDIRECT_PREFIXES = ("http://localhost:", "http://127.0.0.1:")


def _validate_redirect_uri(redirect_uri: str) -> None:
    """Reject redirect URIs that don't target localhost (Electron app)."""
    if not redirect_uri.startswith(_ALLOWED_REDIRECT_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri must target localhost (http://localhost:... or http://127.0.0.1:...)",
        )


router = APIRouter(
    prefix="/api/ai/config/me/oauth",
    tags=["AI OAuth"],
)


async def _check_oauth_initiate_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Rate limit POST /initiate: 5/min per user."""
    result = await rate_limiter.check_and_increment(
        endpoint="oauth_initiate",
        scope_id=str(current_user.id),
        limit=5,
        window_seconds=60,
    )
    if not result.allowed:
        _raise_rate_limit(result, "OAuth initiation rate limit exceeded")


@router.post(
    "/initiate",
    response_model=OAuthInitiateResponse,
    dependencies=[Depends(_check_oauth_initiate_rate_limit)],
    summary="Initiate OAuth flow with provider",
    responses={
        200: {"description": "Authorization URL generated"},
        400: {"description": "Provider not supported or not configured"},
    },
)
async def initiate_oauth(
    body: OAuthInitiateRequest,
    current_user: User = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthInitiateResponse:
    """Generate OAuth authorization URL with PKCE for a provider.

    Returns an auth URL that the Electron app opens in a BrowserWindow.
    The state token is stored in Redis for callback validation.
    """
    _validate_redirect_uri(body.redirect_uri)

    try:
        auth_url, state = await oauth_service.generate_auth_url(
            provider_type=body.provider_type,
            redirect_uri=body.redirect_uri,
            user_id=current_user.id,
        )
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return OAuthInitiateResponse(
        auth_url=auth_url,
        state=state,
        expires_in=settings.oauth_state_ttl_seconds,
    )


@router.post(
    "/callback",
    response_model=OAuthConnectionStatus,
    summary="Handle OAuth callback",
    responses={
        200: {"description": "OAuth connection established"},
        400: {"description": "Invalid state, expired, or exchange failed"},
    },
)
async def oauth_callback(
    body: OAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
    db: AsyncSession = Depends(get_db),
) -> OAuthConnectionStatus:
    """Exchange authorization code for tokens and store the connection.

    1. Validates redirect_uri and state token (CSRF protection, single-use)
    2. Exchanges code for tokens via provider
    3. Encrypts tokens with Fernet before storage
    4. Creates/updates user-scoped AiProvider with auth_method='oauth'
    5. Auto-creates chat AiModel entry
    6. Returns connection status (never includes tokens)
    """
    _validate_redirect_uri(body.redirect_uri)

    # Validate state token
    state_data = await oauth_service._validate_state(body.state, current_user.id)
    if state_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state token",
        )

    code_verifier, stored_provider_type = state_data

    # Verify provider_type matches
    if stored_provider_type != body.provider_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider type mismatch",
        )

    # Exchange code for tokens
    try:
        tokens = await oauth_service.exchange_code_for_tokens(
            provider_type=body.provider_type,
            code=body.code,
            redirect_uri=body.redirect_uri,
            code_verifier=code_verifier,
        )
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Encrypt tokens
    encryption = ApiKeyEncryption(settings.ai_encryption_key)
    encrypted_access = encryption.encrypt(tokens["access_token"])
    encrypted_refresh = (
        encryption.encrypt(tokens["refresh_token"])
        if tokens.get("refresh_token")
        else None
    )

    # Calculate token expiry
    token_expires_at = utc_now() + timedelta(seconds=tokens.get("expires_in", 3600))

    # Find or create user-scoped provider
    result = await db.execute(
        select(AiProvider)
        .where(
            AiProvider.user_id == current_user.id,
            AiProvider.scope == "user",
            AiProvider.provider_type == body.provider_type,
        )
        .options(selectinload(AiProvider.models))
    )
    provider = result.scalar_one_or_none()

    if provider:
        # Update existing OAuth provider
        provider.auth_method = "oauth"
        provider.oauth_access_token = encrypted_access
        provider.oauth_refresh_token = encrypted_refresh
        provider.oauth_token_expires_at = token_expires_at
        provider.oauth_scope = tokens.get("scope")
        provider.api_key_encrypted = None  # Clear any existing API key
        provider.is_enabled = True
    else:
        # Create new user-scoped OAuth provider
        display_name = "OpenAI" if body.provider_type == "openai" else "Anthropic"
        provider = AiProvider(
            name=f"{body.provider_type}-oauth-{current_user.id}",
            display_name=f"{display_name} (OAuth)",
            provider_type=body.provider_type,
            auth_method="oauth",
            oauth_access_token=encrypted_access,
            oauth_refresh_token=encrypted_refresh,
            oauth_token_expires_at=token_expires_at,
            oauth_scope=tokens.get("scope"),
            scope="user",
            user_id=current_user.id,
            is_enabled=True,
        )
        db.add(provider)
        await db.flush()

        # Auto-create chat model
        default_model = (
            "gpt-4o" if body.provider_type == "openai" else "claude-sonnet-4-20250514"
        )
        chat_model = AiModel(
            provider_id=provider.id,
            model_id=default_model,
            display_name=default_model,
            provider_type=body.provider_type,
            capability="chat",
            is_default=True,
            is_enabled=True,
        )
        db.add(chat_model)

    await db.commit()
    await db.refresh(provider)

    # Refresh provider registry cache
    await refresh_provider_cache()

    # Build status response (never include tokens)
    scopes = (
        tokens.get("scope", "").split() if tokens.get("scope") else []
    )
    return OAuthConnectionStatus(
        connected=True,
        provider_type=body.provider_type,
        auth_method="oauth",
        provider_user_id=provider.oauth_provider_user_id,
        connected_at=provider.created_at,
        token_expires_at=token_expires_at,
        scopes=scopes,
    )


@router.delete(
    "/disconnect",
    response_model=OAuthDisconnectResponse,
    summary="Disconnect OAuth provider",
    responses={
        200: {"description": "OAuth connection removed"},
        404: {"description": "No OAuth connection found"},
    },
)
async def disconnect_oauth(
    provider_type: str | None = None,
    current_user: User = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
    db: AsyncSession = Depends(get_db),
) -> OAuthDisconnectResponse:
    """Disconnect OAuth provider and revoke tokens.

    1. Finds user-scoped OAuth provider (optionally filtered by provider_type)
    2. Revokes tokens at the provider (best-effort)
    3. Deletes the user-scoped AiProvider + cascade to AiModel
    4. User falls back to company default
    """
    query = select(AiProvider).where(
        AiProvider.user_id == current_user.id,
        AiProvider.scope == "user",
        AiProvider.auth_method == "oauth",
    )
    if provider_type:
        query = query.where(AiProvider.provider_type == provider_type)
    result = await db.execute(query)
    provider = result.scalars().first()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OAuth connection found",
        )

    # Best-effort token revocation (both access and refresh tokens)
    encryption = ApiKeyEncryption(settings.ai_encryption_key)
    for token_col in (provider.oauth_access_token, provider.oauth_refresh_token):
        if token_col:
            try:
                decrypted_token = encryption.decrypt(token_col)
                await oauth_service.revoke_tokens(
                    provider_type=provider.provider_type,
                    access_token=decrypted_token,
                )
            except Exception:
                logger.warning(
                    "Failed to revoke OAuth token for user %s (best-effort)",
                    current_user.id,
                    exc_info=True,
                )

    # Delete the provider (cascades to models)
    await db.delete(provider)
    await db.commit()

    # Refresh provider registry cache
    await refresh_provider_cache()

    return OAuthDisconnectResponse(
        disconnected=True,
        fallback="company_default",
    )


@router.get(
    "/status",
    response_model=OAuthConnectionStatus,
    summary="Get OAuth connection status",
    responses={
        200: {"description": "Connection status returned"},
    },
)
async def oauth_status(
    provider_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthConnectionStatus:
    """Get current OAuth connection status. Never returns actual tokens."""
    query = select(AiProvider).where(
        AiProvider.user_id == current_user.id,
        AiProvider.scope == "user",
        AiProvider.auth_method == "oauth",
    )
    if provider_type:
        query = query.where(AiProvider.provider_type == provider_type)
    result = await db.execute(query)
    provider = result.scalars().first()

    if not provider:
        return OAuthConnectionStatus(connected=False)

    scopes = provider.oauth_scope.split() if provider.oauth_scope else []

    return OAuthConnectionStatus(
        connected=True,
        provider_type=provider.provider_type,
        auth_method="oauth",
        provider_user_id=provider.oauth_provider_user_id,
        connected_at=provider.created_at,
        token_expires_at=provider.oauth_token_expires_at,
        scopes=scopes,
    )



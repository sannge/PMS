"""AI subscription token connection endpoints.

Provides endpoints for saving, testing, disconnecting, and checking the
status of subscription-based AI provider connections. Users obtain a session
token from their provider's CLI (e.g. ``claude setup-token``) and paste it
into the app. Tokens are Fernet-encrypted before database storage and never
returned in API responses.

Also preserves the legacy OAuth status/disconnect endpoints for backwards
compatibility.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..ai.encryption import ApiKeyEncryption
from ..ai.provider_registry import refresh_provider_cache
from ..ai.rate_limiter import AIRateLimiter, get_rate_limiter, _raise_rate_limit
from ..config import settings
from ..database import get_db
from ..models.ai_model import AiModel
from ..models.ai_provider import AiProvider
from ..models.user import User
from ..schemas.oauth import (
    OAuthConnectionStatus,
    OAuthDisconnectResponse,
    SubscriptionTokenRequest,
    SubscriptionTokenStatus,
    SubscriptionTokenTestResult,
)
from ..services.auth_service import get_current_user

# SDK exception types — imported at module level to avoid fragile re-imports
try:
    from openai import AuthenticationError as OpenAIAuthError
    from openai import PermissionDeniedError as OpenAIPermError
except ImportError:
    OpenAIAuthError = type(None)  # type: ignore[misc, assignment]
    OpenAIPermError = type(None)  # type: ignore[misc, assignment]
try:
    from anthropic import AuthenticationError as AnthropicAuthError
    from anthropic import PermissionDeniedError as AnthropicPermError
except ImportError:
    AnthropicAuthError = type(None)  # type: ignore[misc, assignment]
    AnthropicPermError = type(None)  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ai/config/me",
    tags=["AI Subscription"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _subscription_token_query(user_id, *, with_models: bool = False):
    """Build query for finding a user's subscription token provider only."""
    q = select(AiProvider).where(
        AiProvider.user_id == user_id,
        AiProvider.scope == "user",
        AiProvider.auth_method == "session_token",
    )
    if with_models:
        q = q.options(selectinload(AiProvider.models))
    return q


def _user_token_query(user_id, *, with_models: bool = False):
    """Build query for finding a user's token-based provider (legacy: session_token + oauth)."""
    q = select(AiProvider).where(
        AiProvider.user_id == user_id,
        AiProvider.scope == "user",
        AiProvider.auth_method.in_(["session_token", "oauth"]),
    )
    if with_models:
        q = q.options(selectinload(AiProvider.models))
    return q


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


async def _check_token_rate_limit(
    current_user: User = Depends(get_current_user),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> None:
    """Rate limit token save/disconnect: 5/min per user."""
    result = await rate_limiter.check_and_increment(
        endpoint="subscription_token",
        scope_id=str(current_user.id),
        limit=5,
        window_seconds=60,
    )
    if not result.allowed:
        _raise_rate_limit(result, "Subscription token rate limit exceeded")


# ---------------------------------------------------------------------------
# Token validation helper
# ---------------------------------------------------------------------------

_VALIDATE_TIMEOUT = 15.0  # seconds


async def _validate_token(provider_type: str, token: str) -> tuple[bool, str, int | None, str]:
    """Test a subscription token by making a minimal API call.

    For Anthropic, tries ``auth_token`` (bearer/OAuth) first, then falls
    back to ``api_key``. This handles both OAuth long-lived tokens and
    standard API keys regardless of prefix.

    Returns:
        Tuple of (success, message, latency_ms, token_mode).
        ``token_mode`` is ``"bearer"`` or ``"apikey"`` for Anthropic,
        ``"apikey"`` for OpenAI.
    """
    # SDK timeout is 1s shorter than asyncio.wait_for so SDK raises its own
    # typed exception before the hard asyncio ceiling fires.
    _sdk_timeout = _VALIDATE_TIMEOUT - 1

    start = time.monotonic()
    try:
        if provider_type == "openai":
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=token, timeout=_sdk_timeout)
            await asyncio.wait_for(client.models.list(), timeout=_VALIDATE_TIMEOUT)
            latency = int((time.monotonic() - start) * 1000)
            return True, "Token validated successfully", latency, "apikey"

        elif provider_type == "anthropic":
            from anthropic import AsyncAnthropic

            # Try auth_token (bearer/OAuth) first, then api_key.
            # OAuth long-lived tokens can also start with "sk-ant-"
            # so prefix detection is unreliable.
            # Use messages.create (not models.list) — OAuth tokens may
            # lack /v1/models access but can still call messages.
            for mode, kwargs in [
                ("bearer", {"auth_token": token}),
                ("apikey", {"api_key": token}),
            ]:
                try:
                    client = AsyncAnthropic(timeout=_sdk_timeout, **kwargs)
                    await asyncio.wait_for(
                        client.messages.create(
                            model="claude-haiku-4-5-20251001",
                            max_tokens=1,
                            messages=[{"role": "user", "content": "hi"}],
                        ),
                        timeout=_VALIDATE_TIMEOUT,
                    )
                    latency = int((time.monotonic() - start) * 1000)
                    return True, "Token validated successfully", latency, mode
                except Exception:
                    continue
            # Both methods failed
            latency = int((time.monotonic() - start) * 1000)
            return False, "Invalid token — authentication failed", latency, "apikey"

        else:
            return False, f"Unsupported provider: {provider_type}", None, "apikey"

    except asyncio.TimeoutError:
        latency = int((time.monotonic() - start) * 1000)
        return False, "Validation timed out — please try again", latency, "apikey"
    except Exception as e:
        latency = int((time.monotonic() - start) * 1000)

        if isinstance(e, (OpenAIAuthError, AnthropicAuthError)):
            return False, "Invalid token — authentication failed", latency, "apikey"
        if isinstance(e, (OpenAIPermError, AnthropicPermError)):
            return False, "Token lacks required permissions", latency, "apikey"

        logger.warning(
            "Token validation error for %s: %s (details suppressed)",
            provider_type,
            type(e).__name__,
        )
        return False, f"Validation failed: {type(e).__name__}", latency, "apikey"


# ---------------------------------------------------------------------------
# Subscription Token Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/subscription-token",
    response_model=SubscriptionTokenStatus,
    dependencies=[Depends(_check_token_rate_limit)],
    summary="Save subscription token",
    responses={
        200: {"description": "Token saved and validated"},
        400: {"description": "Invalid token"},
    },
)
async def save_subscription_token(
    body: SubscriptionTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionTokenStatus:
    """Save a subscription session token for an AI provider.

    1. Validates the token by making a test API call
    2. Encrypts the token with Fernet before storage
    3. Creates/updates user-scoped AiProvider with auth_method='session_token'
    4. Auto-creates chat AiModel entry
    5. Returns connection status (never includes the token)
    """
    # Validate the token first
    valid, message, _latency, token_mode = await _validate_token(body.provider_type, body.token)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Encrypt token
    encryption = ApiKeyEncryption(settings.ai_encryption_key)
    encrypted_token = encryption.encrypt(body.token)

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

    # Determine model ID
    model_id = body.preferred_model
    if not model_id:
        model_id = "gpt-4o" if body.provider_type == "openai" else "claude-sonnet-4-20250514"

    if provider:
        # Update existing provider to use session token
        provider.auth_method = "session_token"
        provider.oauth_access_token = encrypted_token
        provider.oauth_refresh_token = None
        provider.oauth_token_expires_at = None
        provider.oauth_scope = token_mode  # "bearer" or "apikey"
        provider.api_key_encrypted = None
        provider.is_enabled = True

        # Update model if specified
        if body.preferred_model:
            chat_model = next(
                (m for m in provider.models if m.capability == "chat"),
                None,
            )
            if chat_model:
                chat_model.model_id = model_id
                chat_model.display_name = model_id
    else:
        # Create new user-scoped provider
        display_name = "OpenAI" if body.provider_type == "openai" else "Anthropic"
        provider = AiProvider(
            name=f"{body.provider_type}-token-{current_user.id}",
            display_name=f"{display_name} (Subscription)",
            provider_type=body.provider_type,
            auth_method="session_token",
            oauth_access_token=encrypted_token,
            oauth_scope=token_mode,  # "bearer" or "apikey"
            scope="user",
            user_id=current_user.id,
            is_enabled=True,
        )
        db.add(provider)
        await db.flush()

        # Auto-create chat model
        chat_model_obj = AiModel(
            provider_id=provider.id,
            model_id=model_id,
            display_name=model_id,
            provider_type=body.provider_type,
            capability="chat",
            is_default=True,
            is_enabled=True,
        )
        db.add(chat_model_obj)

    await db.commit()
    await db.refresh(provider, ["models", "updated_at"])

    # Read actual chat model from DB after commit
    chat_model = next((m for m in provider.models if m.capability == "chat"), None)

    # Refresh provider registry cache (non-fatal)
    try:
        await refresh_provider_cache()
    except Exception:
        logger.debug("Provider cache refresh failed after save (non-fatal)")

    return SubscriptionTokenStatus(
        connected=True,
        provider_type=body.provider_type,
        auth_method="session_token",
        connected_at=provider.updated_at,
        model_id=chat_model.model_id if chat_model else model_id,
    )


@router.get(
    "/subscription-token/status",
    response_model=SubscriptionTokenStatus,
    summary="Get subscription token status",
)
async def subscription_token_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionTokenStatus:
    """Get current subscription token connection status. Never returns the token."""
    result = await db.execute(_subscription_token_query(current_user.id, with_models=True))
    provider = result.scalars().first()

    if not provider:
        return SubscriptionTokenStatus(connected=False)

    chat_model = next(
        (m for m in provider.models if m.capability == "chat"),
        None,
    )

    return SubscriptionTokenStatus(
        connected=True,
        provider_type=provider.provider_type,
        auth_method=provider.auth_method,
        connected_at=provider.updated_at,
        model_id=chat_model.model_id if chat_model else None,
    )


@router.post(
    "/subscription-token/test",
    response_model=SubscriptionTokenTestResult,
    dependencies=[Depends(_check_token_rate_limit)],
    summary="Test subscription token",
)
async def test_subscription_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionTokenTestResult:
    """Test the stored subscription token by making a minimal API call."""
    result = await db.execute(_subscription_token_query(current_user.id))
    provider = result.scalars().first()

    if not provider or not provider.oauth_access_token:
        return SubscriptionTokenTestResult(
            success=False,
            message="No subscription token configured",
        )

    # Decrypt and test — catch corrupt/rotated tokens
    encryption = ApiKeyEncryption(settings.ai_encryption_key)
    try:
        token = encryption.decrypt(provider.oauth_access_token)
    except Exception:
        return SubscriptionTokenTestResult(
            success=False,
            message="Stored token is corrupt or encryption key changed",
        )

    valid, message, latency, _mode = await _validate_token(provider.provider_type, token)
    return SubscriptionTokenTestResult(
        success=valid,
        message=message,
        latency_ms=latency,
    )


@router.delete(
    "/subscription-token",
    response_model=OAuthDisconnectResponse,
    dependencies=[Depends(_check_token_rate_limit)],
    summary="Remove subscription token",
)
async def remove_subscription_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthDisconnectResponse:
    """Remove the subscription token and fall back to company default."""
    result = await db.execute(_subscription_token_query(current_user.id))
    provider = result.scalars().first()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription token found",
        )

    # Delete the provider (cascades to models)
    await db.delete(provider)
    await db.commit()

    # Refresh provider registry cache (non-fatal)
    try:
        await refresh_provider_cache()
    except Exception:
        logger.debug("Provider cache refresh failed after delete (non-fatal)")

    return OAuthDisconnectResponse(
        disconnected=True,
        fallback="company_default",
    )


# ---------------------------------------------------------------------------
# Legacy OAuth endpoints (backwards compatibility)
# ---------------------------------------------------------------------------


@router.get(
    "/oauth/status",
    response_model=OAuthConnectionStatus,
    summary="Get OAuth connection status (legacy)",
)
async def oauth_status(
    provider_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthConnectionStatus:
    """Get current OAuth/subscription connection status. Never returns tokens."""
    query = _user_token_query(current_user.id)
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
        auth_method=provider.auth_method,
        provider_user_id=provider.oauth_provider_user_id,
        connected_at=provider.created_at,
        token_expires_at=provider.oauth_token_expires_at,
        scopes=scopes,
    )


@router.delete(
    "/oauth/disconnect",
    response_model=OAuthDisconnectResponse,
    dependencies=[Depends(_check_token_rate_limit)],
    summary="Disconnect OAuth/subscription (legacy)",
)
async def disconnect_oauth(
    provider_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthDisconnectResponse:
    """Disconnect OAuth/subscription provider. Legacy endpoint."""
    query = _user_token_query(current_user.id)
    if provider_type:
        query = query.where(AiProvider.provider_type == provider_type)
    result = await db.execute(query)
    provider = result.scalars().first()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OAuth/subscription connection found",
        )

    await db.delete(provider)
    await db.commit()

    try:
        await refresh_provider_cache()
    except Exception:
        logger.debug("Provider cache refresh failed after OAuth disconnect (non-fatal)")

    return OAuthDisconnectResponse(
        disconnected=True,
        fallback="company_default",
    )

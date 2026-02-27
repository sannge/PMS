"""AI configuration API endpoints.

Provides admin endpoints for managing global AI providers and models,
and user endpoints for personal API key overrides. All API keys are
encrypted at rest and never returned in responses.
"""

import ipaddress
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import UUID

if TYPE_CHECKING:
    from ..ai.encryption import ApiKeyEncryption

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import get_db
from ..models.ai_model import AiModel
from ..models.ai_provider import AiProvider
from ..models.application import Application
from ..models.user import User
from ..schemas.ai_config import (
    AiConfigSummary,
    AiModelCreate,
    AiModelResponse,
    AiModelUpdate,
    AiProviderCreate,
    AiProviderResponse,
    AiProviderUpdate,
    CapabilityConfig,
    CapabilityTestResult,
    EffectiveChatConfig,
    UserProviderOverride,
)
from ..services.auth_service import get_current_user
from ..utils.timezone import utc_now

logger = logging.getLogger(__name__)


async def _refresh_provider_cache() -> None:
    """Refresh the provider registry cache after configuration changes."""
    try:
        from ..ai.provider_registry import ProviderRegistry
        registry = ProviderRegistry()
        await registry.refresh()
    except Exception:
        logger.debug("Provider registry refresh skipped (not yet initialized)")



# ---------------------------------------------------------------------------
# URL validation helper (SSRF prevention for Ollama)
# ---------------------------------------------------------------------------

_ALLOWED_PRIVATE_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
]


def _validate_base_url(base_url: str | None, provider_type: str) -> None:
    """Validate base_url to prevent SSRF, especially for Ollama providers.

    Ollama providers should only point to localhost or private network IPs.
    Non-private URLs are rejected for Ollama; other providers allow any URL
    since they connect to known cloud APIs.
    """
    if not base_url or provider_type != "ollama":
        return

    try:
        parsed = urlparse(base_url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Invalid URL: no hostname")

        # Allow "localhost" explicitly
        if hostname in ("localhost",):
            return

        # Check if the hostname is an IP address in a private range
        try:
            addr = ipaddress.ip_address(hostname)
            if any(addr in net for net in _ALLOWED_PRIVATE_RANGES):
                return
        except ValueError:
            pass  # hostname is a DNS name, not an IP literal

        # Non-localhost, non-private-IP hostname for Ollama: warn and reject
        raise ValueError(
            f"Ollama base_url must be localhost or a private network address, "
            f"got: {hostname}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# Encryption helper (lazy import to tolerate parallel creation)
# ---------------------------------------------------------------------------


def _get_encryption() -> "ApiKeyEncryption":
    """Return an ApiKeyEncryption instance using the configured key."""
    from ..ai.encryption import ApiKeyEncryption

    return ApiKeyEncryption(settings.ai_encryption_key)


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------


async def require_developer(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the current user to be a developer.

    Developers have access to global AI configuration (provider CRUD,
    model CRUD, system prompt). This replaces the former require_ai_admin
    which checked application ownership.
    """
    if not current_user.is_developer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Developer access required for AI configuration",
        )
    return current_user


# Keep for backward compatibility until all references are migrated
async def require_ai_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require the current user to be an owner of at least one application."""
    result = await db.execute(
        select(
            exists().where(Application.owner_id == current_user.id)
        )
    )
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI admin access requires application ownership",
        )
    return current_user


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/ai/config",
    tags=["ai-config"],
)


# ============================================================================
# Admin: Provider CRUD
# ============================================================================


@router.get("/providers", response_model=list[AiProviderResponse])
async def list_providers(
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> list[AiProviderResponse]:
    """List all global AI providers with their registered models."""
    result = await db.execute(
        select(AiProvider)
        .where(AiProvider.scope == "global")
        .options(selectinload(AiProvider.models))
        .order_by(AiProvider.created_at.asc())
    )
    providers = result.scalars().all()
    return [AiProviderResponse.model_validate(p) for p in providers]


@router.post(
    "/providers",
    response_model=AiProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    body: AiProviderCreate,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> AiProviderResponse:
    """Create a new global AI provider. API key is encrypted before storage."""
    _validate_base_url(body.base_url, body.provider_type)

    encrypted_key = None
    if body.api_key:
        encrypted_key = _get_encryption().encrypt(body.api_key)

    provider = AiProvider(
        name=body.name,
        display_name=body.display_name,
        provider_type=body.provider_type,
        base_url=body.base_url,
        api_key_encrypted=encrypted_key,
        is_enabled=body.is_enabled,
        scope="global",
        user_id=None,
    )
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    await _refresh_provider_cache()
    return AiProviderResponse.model_validate(provider)


@router.put("/providers/{provider_id}", response_model=AiProviderResponse)
async def update_provider(
    provider_id: UUID,
    body: AiProviderUpdate,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> AiProviderResponse:
    """Update a global AI provider. Omit api_key to keep existing key."""
    result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider_id, AiProvider.scope == "global")
        .options(selectinload(AiProvider.models))
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global provider {provider_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Validate base_url if being updated
    new_base_url = update_data.get("base_url", provider.base_url)
    new_provider_type = update_data.get("provider_type", provider.provider_type)
    _validate_base_url(new_base_url, new_provider_type)

    # Handle api_key separately: encrypt if provided, keep existing if absent
    if "api_key" in update_data:
        raw_key = update_data.pop("api_key")
        if raw_key is not None:
            provider.api_key_encrypted = _get_encryption().encrypt(raw_key)
        # If raw_key is None, keep existing encrypted key

    for field, value in update_data.items():
        setattr(provider, field, value)

    provider.updated_at = utc_now()
    await db.flush()
    await db.refresh(provider)
    await _refresh_provider_cache()
    return AiProviderResponse.model_validate(provider)


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_provider(
    provider_id: UUID,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a global AI provider. Cascades to its models."""
    result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider_id, AiProvider.scope == "global")
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global provider {provider_id} not found",
        )
    await db.delete(provider)
    await db.flush()
    await _refresh_provider_cache()


@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: UUID,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Test connectivity for a global AI provider."""
    result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider_id, AiProvider.scope == "global")
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global provider {provider_id} not found",
        )
    return await _test_provider_connectivity(provider)


# ============================================================================
# Admin: Model CRUD
# ============================================================================


@router.get("/models", response_model=list[AiModelResponse])
async def list_models(
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> list[AiModelResponse]:
    """List all AI models across all global providers."""
    result = await db.execute(
        select(AiModel)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .where(AiProvider.scope == "global")
        .options(selectinload(AiModel.provider))
        .order_by(AiModel.created_at.asc())
    )
    models = result.scalars().all()
    return [AiModelResponse.model_validate(m) for m in models]


@router.post(
    "/models",
    response_model=AiModelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model(
    body: AiModelCreate,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> AiModelResponse:
    """Register a new AI model under a global provider."""
    # Verify provider exists and is global
    prov_result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == body.provider_id, AiProvider.scope == "global")
    )
    if prov_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global provider {body.provider_id} not found",
        )

    model = AiModel(
        provider_id=body.provider_id,
        model_id=body.model_id,
        display_name=body.display_name,
        provider_type=body.provider_type,
        capability=body.capability,
        embedding_dimensions=body.embedding_dimensions,
        max_tokens=body.max_tokens,
        is_default=body.is_default,
        is_enabled=body.is_enabled,
    )
    db.add(model)
    await db.flush()

    # Reload with provider relationship for response
    result = await db.execute(
        select(AiModel)
        .where(AiModel.id == model.id)
        .options(selectinload(AiModel.provider))
    )
    model = result.scalar_one()
    return AiModelResponse.model_validate(model)


@router.put("/models/{model_id}", response_model=AiModelResponse)
async def update_model(
    model_id: UUID,
    body: AiModelUpdate,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> AiModelResponse:
    """Update an AI model entry."""
    result = await db.execute(
        select(AiModel)
        .where(AiModel.id == model_id)
        .options(selectinload(AiModel.provider))
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(model, field, value)

    model.updated_at = utc_now()
    await db.flush()
    await db.refresh(model)
    return AiModelResponse.model_validate(model)


@router.delete(
    "/models/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_model(
    model_id: UUID,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an AI model entry."""
    result = await db.execute(
        select(AiModel).where(AiModel.id == model_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found",
        )
    await db.delete(model)
    await db.flush()


@router.get("/summary", response_model=AiConfigSummary)
async def get_config_summary(
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> AiConfigSummary:
    """Get AI configuration summary with default models per capability."""
    # Providers
    prov_result = await db.execute(
        select(AiProvider)
        .where(AiProvider.scope == "global")
        .options(selectinload(AiProvider.models))
        .order_by(AiProvider.created_at.asc())
    )
    providers = prov_result.scalars().all()

    # Default models
    defaults: dict[str, AiModelResponse | None] = {
        "chat": None,
        "embedding": None,
        "vision": None,
    }
    for cap in defaults:
        result = await db.execute(
            select(AiModel)
            .join(AiProvider, AiModel.provider_id == AiProvider.id)
            .where(
                AiProvider.scope == "global",
                AiModel.capability == cap,
                AiModel.is_default.is_(True),
                AiModel.is_enabled.is_(True),
            )
            .options(selectinload(AiModel.provider))
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model:
            defaults[cap] = AiModelResponse.model_validate(model)

    return AiConfigSummary(
        providers=[AiProviderResponse.model_validate(p) for p in providers],
        default_chat_model=defaults["chat"],
        default_embedding_model=defaults["embedding"],
        default_vision_model=defaults["vision"],
    )


# ============================================================================
# Per-Capability Configuration (Developer Settings Panel)
# ============================================================================


VALID_CAPABILITIES = {"chat", "embedding", "vision"}


@router.put("/capability/{capability}", response_model=AiProviderResponse)
async def save_capability_config(
    capability: str,
    body: CapabilityConfig,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> AiProviderResponse:
    """Save provider + model configuration for a single capability.

    Creates or updates the global AiProvider for the given provider_type,
    then sets the specified model as the default for that capability.
    """
    if capability not in VALID_CAPABILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability '{capability}'. Must be one of: {', '.join(sorted(VALID_CAPABILITIES))}",
        )

    _validate_base_url(body.base_url, body.provider_type)

    # Find or create global provider for this provider_type
    result = await db.execute(
        select(AiProvider).where(
            AiProvider.scope == "global",
            AiProvider.provider_type == body.provider_type,
        )
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        encrypted_key = None
        if body.api_key:
            encrypted_key = _get_encryption().encrypt(body.api_key)
        provider = AiProvider(
            name=body.provider_type,
            display_name=body.provider_type.title(),
            provider_type=body.provider_type,
            base_url=body.base_url,
            api_key_encrypted=encrypted_key,
            is_enabled=True,
            scope="global",
        )
        db.add(provider)
        await db.flush()
    else:
        # Update existing provider
        if body.api_key:
            provider.api_key_encrypted = _get_encryption().encrypt(body.api_key)
        if body.base_url is not None:
            provider.base_url = body.base_url
        provider.is_enabled = True
        provider.updated_at = utc_now()
        await db.flush()

    # Clear any existing default for this capability (across all providers)
    existing_defaults = (await db.execute(
        select(AiModel)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .where(
            AiProvider.scope == "global",
            AiModel.capability == capability,
            AiModel.is_default.is_(True),
        )
    )).scalars().all()
    for m in existing_defaults:
        m.is_default = False

    # Find or create the model entry for this provider + model_id + capability
    model_result = await db.execute(
        select(AiModel).where(
            AiModel.provider_id == provider.id,
            AiModel.model_id == body.model_id,
            AiModel.capability == capability,
        )
    )
    model = model_result.scalar_one_or_none()
    if model is None:
        model = AiModel(
            provider_id=provider.id,
            model_id=body.model_id,
            display_name=body.model_id,
            provider_type=body.provider_type,
            capability=capability,
            is_default=True,
            is_enabled=True,
        )
        db.add(model)
    else:
        model.is_default = True
        model.is_enabled = True
        model.updated_at = utc_now()

    await db.flush()

    # Reload with models for response
    reload_result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider.id)
        .options(selectinload(AiProvider.models))
    )
    provider = reload_result.scalar_one()
    await _refresh_provider_cache()
    return AiProviderResponse.model_validate(provider)


@router.post("/test/{capability}", response_model=CapabilityTestResult)
async def test_capability(
    capability: str,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> CapabilityTestResult:
    """Test the currently configured provider+model for a capability.

    - Chat: sends "Say hello in 5 words" and returns response text + latency
    - Embedding: embeds the word "test" and returns dimension count + latency
    - Vision: sends a 1x1 white pixel and returns description + latency
    """
    if capability not in VALID_CAPABILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability '{capability}'",
        )

    # Find the default model for this capability
    result = await db.execute(
        select(AiModel)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .where(
            AiProvider.scope == "global",
            AiModel.capability == capability,
            AiModel.is_default.is_(True),
            AiModel.is_enabled.is_(True),
        )
        .options(selectinload(AiModel.provider))
        .limit(1)
    )
    model = result.scalar_one_or_none()
    if model is None:
        return CapabilityTestResult(
            success=False,
            message=f"No default {capability} model configured",
        )

    provider = model.provider
    return await _test_capability_provider(provider, model, capability)


@router.get("/models/available", response_model=list[AiModelResponse])
async def list_available_models(
    provider_type: str | None = None,
    capability: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AiModelResponse]:
    """List available models from the seed data, filtered by provider_type and/or capability.

    This endpoint is public (no auth required) since the model list is not sensitive.
    Used by frontend dropdowns to populate model options.
    """
    query = (
        select(AiModel)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .where(AiProvider.scope == "global")
        .options(selectinload(AiModel.provider))
    )
    if provider_type:
        query = query.where(AiModel.provider_type == provider_type)
    if capability:
        query = query.where(AiModel.capability == capability)

    query = query.where(AiModel.is_enabled.is_(True))
    query = query.order_by(AiModel.display_name.asc())

    result = await db.execute(query)
    models = result.scalars().all()
    return [AiModelResponse.model_validate(m) for m in models]


# ============================================================================
# User Override Endpoints (/me)
# ============================================================================


@router.get("/me/effective", response_model=EffectiveChatConfig)
async def get_effective_chat_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EffectiveChatConfig:
    """Get the effective chat configuration for the current user.

    Resolves user override vs global fallback and returns which is active.
    """
    # Check for user override first
    override_result = await db.execute(
        select(AiProvider)
        .where(
            AiProvider.scope == "user",
            AiProvider.user_id == current_user.id,
            AiProvider.is_enabled.is_(True),
        )
        .options(selectinload(AiProvider.models))
    )
    user_providers = override_result.scalars().all()

    for provider in user_providers:
        for model in provider.models:
            if model.capability == "chat" and model.is_enabled:
                return EffectiveChatConfig(
                    source="override",
                    provider_type=provider.provider_type,
                    model_id=model.model_id,
                    display_name=model.display_name,
                )

    # Fall back to global default
    global_result = await db.execute(
        select(AiModel)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .where(
            AiProvider.scope == "global",
            AiModel.capability == "chat",
            AiModel.is_default.is_(True),
            AiModel.is_enabled.is_(True),
        )
        .options(selectinload(AiModel.provider))
        .limit(1)
    )
    default_model = global_result.scalar_one_or_none()
    if default_model:
        return EffectiveChatConfig(
            source="global",
            provider_type=default_model.provider.provider_type,
            model_id=default_model.model_id,
            display_name=default_model.display_name,
        )

    # No configuration at all
    return EffectiveChatConfig(
        source="global",
        provider_type=None,
        model_id=None,
        display_name=None,
    )


@router.get("/me/providers", response_model=list[AiProviderResponse])
async def list_user_overrides(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AiProviderResponse]:
    """List current user's provider overrides."""
    result = await db.execute(
        select(AiProvider)
        .where(
            AiProvider.scope == "user",
            AiProvider.user_id == current_user.id,
        )
        .options(selectinload(AiProvider.models))
        .order_by(AiProvider.created_at.asc())
    )
    providers = result.scalars().all()
    return [AiProviderResponse.model_validate(p) for p in providers]


@router.post(
    "/me/providers",
    response_model=AiProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_override(
    body: UserProviderOverride,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AiProviderResponse:
    """Create a user-scoped provider override with a personal API key.

    User overrides are restricted to chat capability only. A chat AiModel
    is auto-created under the new provider using body.preferred_model.
    """
    _validate_base_url(body.base_url, body.provider_type)

    # Check for duplicate override
    dup_result = await db.execute(
        select(
            exists().where(
                AiProvider.scope == "user",
                AiProvider.user_id == current_user.id,
                AiProvider.provider_type == body.provider_type,
            )
        )
    )
    if dup_result.scalar():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Override for provider type '{body.provider_type}' already exists",
        )

    encrypted_key = _get_encryption().encrypt(body.api_key)

    provider = AiProvider(
        name=f"{body.provider_type}-user-override",
        display_name=f"{body.provider_type.title()} (Personal)",
        provider_type=body.provider_type,
        base_url=body.base_url,
        api_key_encrypted=encrypted_key,
        is_enabled=True,
        scope="user",
        user_id=current_user.id,
    )
    db.add(provider)
    await db.flush()

    # Auto-create a chat model under the user's provider
    chat_model = AiModel(
        provider_id=provider.id,
        model_id=body.preferred_model,
        display_name=body.preferred_model,
        provider_type=body.provider_type,
        capability="chat",
        is_default=True,
        is_enabled=True,
    )
    db.add(chat_model)
    await db.flush()

    # Reload with models relationship for response
    result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider.id)
        .options(selectinload(AiProvider.models))
    )
    provider = result.scalar_one()
    await _refresh_provider_cache()
    return AiProviderResponse.model_validate(provider)


@router.put("/me/providers/{provider_type}", response_model=AiProviderResponse)
async def update_user_override(
    provider_type: str,
    body: UserProviderOverride,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AiProviderResponse:
    """Update a user's provider override.

    Also updates the auto-created chat model to match preferred_model.
    """
    result = await db.execute(
        select(AiProvider).where(
            AiProvider.scope == "user",
            AiProvider.user_id == current_user.id,
            AiProvider.provider_type == provider_type,
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No override found for provider type '{provider_type}'",
        )

    provider.api_key_encrypted = _get_encryption().encrypt(body.api_key)
    if body.base_url is not None:
        _validate_base_url(body.base_url, body.provider_type)
        provider.base_url = body.base_url
    provider.updated_at = utc_now()

    # Update the chat model to match new preferred_model
    model_result = await db.execute(
        select(AiModel).where(
            AiModel.provider_id == provider.id,
            AiModel.capability == "chat",
        )
    )
    existing_model = model_result.scalar_one_or_none()
    if existing_model:
        existing_model.model_id = body.preferred_model
        existing_model.display_name = body.preferred_model
        existing_model.provider_type = body.provider_type
        existing_model.updated_at = utc_now()
    else:
        # Create if missing (migration from old data)
        chat_model = AiModel(
            provider_id=provider.id,
            model_id=body.preferred_model,
            display_name=body.preferred_model,
            provider_type=body.provider_type,
            capability="chat",
            is_default=True,
            is_enabled=True,
        )
        db.add(chat_model)

    await db.flush()

    # Reload with models relationship for response
    reload_result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider.id)
        .options(selectinload(AiProvider.models))
    )
    provider = reload_result.scalar_one()
    await _refresh_provider_cache()
    return AiProviderResponse.model_validate(provider)


@router.delete(
    "/me/providers/{provider_type}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_override(
    provider_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user's provider override."""
    result = await db.execute(
        select(AiProvider).where(
            AiProvider.scope == "user",
            AiProvider.user_id == current_user.id,
            AiProvider.provider_type == provider_type,
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No override found for provider type '{provider_type}'",
        )
    await db.delete(provider)
    await db.flush()
    await _refresh_provider_cache()


@router.post("/me/providers/{provider_type}/test")
async def test_user_override(
    provider_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Test connectivity for a user's provider override."""
    result = await db.execute(
        select(AiProvider).where(
            AiProvider.scope == "user",
            AiProvider.user_id == current_user.id,
            AiProvider.provider_type == provider_type,
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No override found for provider type '{provider_type}'",
        )
    return await _test_provider_connectivity(provider)


@router.get("/me/summary", response_model=AiConfigSummary)
async def get_user_effective_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AiConfigSummary:
    """Get effective AI configuration for the current user.

    For each provider type, user overrides take precedence over global providers.
    """
    # Fetch global providers
    global_result = await db.execute(
        select(AiProvider)
        .where(AiProvider.scope == "global", AiProvider.is_enabled.is_(True))
        .options(selectinload(AiProvider.models))
    )
    global_providers = global_result.scalars().all()

    # Fetch user overrides
    user_result = await db.execute(
        select(AiProvider)
        .where(
            AiProvider.scope == "user",
            AiProvider.user_id == current_user.id,
        )
        .options(selectinload(AiProvider.models))
    )
    user_providers = user_result.scalars().all()

    # Build effective provider list: user override wins per provider_type
    user_types = {p.provider_type for p in user_providers}
    effective: list[AiProvider] = list(user_providers)
    for gp in global_providers:
        if gp.provider_type not in user_types:
            effective.append(gp)

    # Default models (from global config only)
    defaults: dict[str, AiModelResponse | None] = {
        "chat": None,
        "embedding": None,
        "vision": None,
    }
    for cap in defaults:
        result = await db.execute(
            select(AiModel)
            .join(AiProvider, AiModel.provider_id == AiProvider.id)
            .where(
                AiProvider.scope == "global",
                AiModel.capability == cap,
                AiModel.is_default.is_(True),
                AiModel.is_enabled.is_(True),
            )
            .options(selectinload(AiModel.provider))
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model:
            defaults[cap] = AiModelResponse.model_validate(model)

    return AiConfigSummary(
        providers=[AiProviderResponse.model_validate(p) for p in effective],
        default_chat_model=defaults["chat"],
        default_embedding_model=defaults["embedding"],
        default_vision_model=defaults["vision"],
    )


# ============================================================================
# Test connectivity helper
# ============================================================================


async def _test_provider_connectivity(provider: AiProvider) -> dict[str, object]:
    """Test connectivity for a provider by calling its API.

    Decrypts the stored API key and makes a lightweight API call to verify
    the key is valid and the service is reachable.
    """
    api_key: str | None = None
    if provider.api_key_encrypted:
        try:
            api_key = _get_encryption().decrypt(provider.api_key_encrypted)
        except Exception:
            return {"success": False, "error": "Failed to decrypt API key"}

    base_url = provider.base_url

    try:
        if provider.provider_type == "openai":
            return await _test_openai(api_key, base_url)
        elif provider.provider_type == "anthropic":
            return await _test_anthropic(api_key, base_url)
        elif provider.provider_type == "ollama":
            return await _test_ollama(base_url)
        else:
            return {"success": False, "error": f"Unknown provider type: {provider.provider_type}"}
    except Exception as exc:
        logger.warning("Provider connectivity test failed for %s: %s", provider.id, exc)
        # Return a generic error to prevent leaking API keys or sensitive details.
        # The full exception is logged server-side for debugging.
        error_msg = f"Connection failed: {type(exc).__name__}"
        return {"success": False, "error": error_msg}


async def _test_openai(api_key: str | None, base_url: str | None) -> dict[str, object]:
    """Test OpenAI API connectivity by listing models."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return {"success": False, "error": "openai package not installed"}

    kwargs: dict = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    client = AsyncOpenAI(**kwargs)
    try:
        await client.models.list()
        return {"success": True, "message": "OpenAI API connection successful"}
    finally:
        await client.close()


async def _test_anthropic(api_key: str | None, base_url: str | None) -> dict[str, object]:
    """Test Anthropic API connectivity with a minimal message call."""
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return {"success": False, "error": "anthropic package not installed"}

    kwargs: dict = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    client = AsyncAnthropic(**kwargs)
    try:
        await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return {"success": True, "message": "Anthropic API connection successful"}
    finally:
        await client.close()


async def _test_ollama(base_url: str | None) -> dict[str, object]:
    """Test Ollama connectivity by fetching the model list."""
    import httpx

    url = (base_url or "http://localhost:11434").rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{url}/api/tags")
        resp.raise_for_status()
    return {"success": True, "message": "Ollama connection successful"}


# ============================================================================
# Capability-specific test helper
# ============================================================================


async def _test_capability_provider(
    provider: AiProvider,
    model: AiModel,
    capability: str,
) -> CapabilityTestResult:
    """Test a specific capability using its configured provider + model.

    - Chat: sends "Say hello in 5 words"
    - Embedding: embeds "test" and returns dimension count
    - Vision: sends a 1x1 white pixel
    """
    import time

    api_key: str | None = None
    if provider.api_key_encrypted:
        try:
            api_key = _get_encryption().decrypt(provider.api_key_encrypted)
        except Exception:
            return CapabilityTestResult(
                success=False,
                message="Failed to decrypt API key",
            )

    base_url = provider.base_url
    start = time.monotonic()

    try:
        if capability == "chat":
            result = await _test_chat_capability(
                provider.provider_type, api_key, base_url, model.model_id,
            )
        elif capability == "embedding":
            result = await _test_embedding_capability(
                provider.provider_type, api_key, base_url, model.model_id,
            )
        elif capability == "vision":
            result = await _test_vision_capability(
                provider.provider_type, api_key, base_url, model.model_id,
            )
        else:
            return CapabilityTestResult(
                success=False, message=f"Unknown capability: {capability}"
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        result.latency_ms = latency_ms
        return result
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Capability test failed for %s: %s", capability, exc)
        error_msg = f"Connection failed: {type(exc).__name__}"
        return CapabilityTestResult(
            success=False, message=error_msg, latency_ms=latency_ms,
        )


async def _test_chat_capability(
    provider_type: str,
    api_key: str | None,
    base_url: str | None,
    model_id: str,
) -> CapabilityTestResult:
    """Test chat capability by sending a short prompt."""
    if provider_type == "openai":
        from openai import AsyncOpenAI

        kwargs: dict = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)
        try:
            resp = await client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Say hello in 5 words"}],
                max_tokens=20,
            )
            text = resp.choices[0].message.content or ""
            return CapabilityTestResult(success=True, message=text.strip())
        finally:
            await client.close()

    elif provider_type == "anthropic":
        from anthropic import AsyncAnthropic

        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncAnthropic(**kwargs)
        try:
            resp = await client.messages.create(
                model=model_id,
                max_tokens=20,
                messages=[{"role": "user", "content": "Say hello in 5 words"}],
            )
            text = resp.content[0].text if resp.content else ""
            return CapabilityTestResult(success=True, message=text.strip())
        finally:
            await client.close()

    elif provider_type == "ollama":
        import httpx

        url = (base_url or "http://localhost:11434").rstrip("/")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/api/chat",
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Say hello in 5 words"}],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            text = resp.json().get("message", {}).get("content", "")
            return CapabilityTestResult(success=True, message=text.strip())

    return CapabilityTestResult(success=False, message=f"Unknown provider: {provider_type}")


async def _test_embedding_capability(
    provider_type: str,
    api_key: str | None,
    base_url: str | None,
    model_id: str,
) -> CapabilityTestResult:
    """Test embedding capability by embedding the word 'test'."""
    if provider_type == "openai":
        from openai import AsyncOpenAI

        kwargs: dict = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)
        try:
            resp = await client.embeddings.create(
                model=model_id,
                input="test",
            )
            dims = len(resp.data[0].embedding)
            return CapabilityTestResult(
                success=True, message=f"{dims} dimensions",
            )
        finally:
            await client.close()

    elif provider_type == "ollama":
        import httpx

        url = (base_url or "http://localhost:11434").rstrip("/")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/api/embed",
                json={"model": model_id, "input": "test"},
            )
            resp.raise_for_status()
            embeddings = resp.json().get("embeddings", [[]])
            dims = len(embeddings[0]) if embeddings else 0
            return CapabilityTestResult(
                success=True, message=f"{dims} dimensions",
            )

    return CapabilityTestResult(
        success=False,
        message=f"Embedding not supported for provider: {provider_type}",
    )


async def _test_vision_capability(
    provider_type: str,
    api_key: str | None,
    base_url: str | None,
    model_id: str,
) -> CapabilityTestResult:
    """Test vision capability by sending a 1x1 white pixel."""
    import base64

    # 1x1 white pixel PNG (67 bytes)
    white_pixel = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    b64_pixel = base64.b64encode(white_pixel).decode()

    if provider_type == "openai":
        from openai import AsyncOpenAI

        kwargs: dict = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)
        try:
            resp = await client.chat.completions.create(
                model=model_id,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image in 10 words or less."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_pixel}"},
                        },
                    ],
                }],
                max_tokens=30,
            )
            text = resp.choices[0].message.content or ""
            return CapabilityTestResult(success=True, message=text.strip())
        finally:
            await client.close()

    elif provider_type == "anthropic":
        from anthropic import AsyncAnthropic

        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncAnthropic(**kwargs)
        try:
            resp = await client.messages.create(
                model=model_id,
                max_tokens=30,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_pixel,
                            },
                        },
                        {"type": "text", "text": "Describe this image in 10 words or less."},
                    ],
                }],
            )
            text = resp.content[0].text if resp.content else ""
            return CapabilityTestResult(success=True, message=text.strip())
        finally:
            await client.close()

    elif provider_type == "ollama":
        import httpx

        url = (base_url or "http://localhost:11434").rstrip("/")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/api/chat",
                json={
                    "model": model_id,
                    "messages": [{
                        "role": "user",
                        "content": "Describe this image in 10 words or less.",
                        "images": [b64_pixel],
                    }],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            text = resp.json().get("message", {}).get("content", "")
            return CapabilityTestResult(success=True, message=text.strip())

    return CapabilityTestResult(
        success=False, message=f"Vision not supported for provider: {provider_type}",
    )

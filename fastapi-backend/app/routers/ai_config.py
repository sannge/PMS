"""AI configuration API endpoints.

Provides admin endpoints for managing global AI providers and models,
and user endpoints for personal API key overrides. All API keys are
encrypted at rest and never returned in responses.
"""

import ipaddress
import logging
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import UUID

if TYPE_CHECKING:
    from ..ai.encryption import ApiKeyEncryption

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import get_db
from ..models.ai_model import AiModel
from ..models.ai_provider import AiProvider
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
    CapabilityConfigResponse,
    CapabilityTestRequest,
    CapabilityTestResult,
    EffectiveChatConfig,
    SystemPromptResponse,
    SystemPromptUpdate,
    UserProviderOverride,
)
from ..ai.provider_registry import refresh_provider_cache
from ..ai.rate_limiter import check_test_rate_limit
from ..services.auth_service import get_current_user
from ..utils.timezone import utc_now

logger = logging.getLogger(__name__)



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


_DANGEROUS_RANGES = [
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_base_url(base_url: str | None, provider_type: str) -> None:
    """Validate base_url to prevent SSRF.

    All provider types: block metadata/link-local IPs (169.254.0.0/16, fe80::/10).
    Ollama only: additionally restrict to localhost/private network IPs.
    """
    if not base_url:
        return

    try:
        parsed = urlparse(base_url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Invalid URL: no hostname")

        # Enforce http/https scheme only
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"base_url must use http or https scheme, got: {parsed.scheme}"
            )

        # Block dangerous IPs for ALL provider types
        def _check_dangerous(ip_str: str) -> None:
            resolved_addr = ipaddress.ip_address(ip_str)
            # Also check IPv6-mapped IPv4 (e.g. ::ffff:169.254.169.254)
            addrs_to_check = [resolved_addr]
            if hasattr(resolved_addr, "ipv4_mapped") and resolved_addr.ipv4_mapped:
                addrs_to_check.append(resolved_addr.ipv4_mapped)
            for addr in addrs_to_check:
                if any(addr in net for net in _DANGEROUS_RANGES):
                    raise ValueError(
                        f"base_url hostname '{hostname}' resolves to "
                        f"dangerous IP {ip_str} (metadata/link-local). "
                        f"This is not allowed."
                    )

        # Check direct IP address
        try:
            addr = ipaddress.ip_address(hostname)
        except ValueError:
            pass  # hostname is a DNS name, not an IP literal — resolve below
        else:
            _check_dangerous(str(addr))
            if provider_type != "ollama":
                return  # non-Ollama: only metadata check needed for IP literals
            # Ollama: continue to private range check
            if any(addr in net for net in _ALLOWED_PRIVATE_RANGES):
                return

        # Allow "localhost" explicitly
        if hostname in ("localhost",):
            return

        # Resolve DNS names and check for dangerous IPs
        try:
            addrinfos = socket.getaddrinfo(hostname, None)
            resolved_ips = {info[4][0] for info in addrinfos}
            for ip_str in resolved_ips:
                _check_dangerous(ip_str)

            if provider_type != "ollama":
                return  # non-Ollama: metadata check done, allow public URLs

            # Ollama: verify resolved IPs are private or localhost
            for ip_str in resolved_ips:
                resolved_addr = ipaddress.ip_address(ip_str)
                if any(resolved_addr in net for net in _ALLOWED_PRIVATE_RANGES):
                    return  # At least one resolved IP is private — allow
        except socket.gaierror:
            if provider_type != "ollama":
                return  # non-Ollama: allow unresolvable hostnames
            # Ollama: DNS resolution failed — fall through to reject

        if provider_type == "ollama":
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
    if current_user.is_developer is None:
        # Stale cache entry from before the is_developer field was added.
        # Invalidate the cache so the next request re-fetches from DB.
        from ..services.user_cache_service import invalidate_user, publish_user_cache_invalidation
        from ..utils.tasks import fire_and_forget

        logger.warning(
            "User %s has is_developer=None (stale cache); invalidating",
            current_user.id,
        )
        invalidate_user(current_user.id)
        fire_and_forget(
            publish_user_cache_invalidation(user_id=str(current_user.id)),
            name="ai-config-stale-cache-invalidation",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Developer access required for AI configuration",
        )
    if not current_user.is_developer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Developer access required for AI configuration",
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
# System Prompt Endpoints (require_developer)
# ============================================================================


@router.get(
    "/system-prompt",
    response_model=SystemPromptResponse,
    summary="Get the custom system prompt",
    responses={
        200: {"description": "System prompt returned"},
        403: {"description": "Not a developer"},
    },
)
async def get_system_prompt(
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> SystemPromptResponse:
    """Get the custom AI system prompt.

    Returns the stored custom prompt, or an empty string if none is set
    (meaning the hardcoded default is in use).
    """
    from ..models.ai_system_prompt import AiSystemPrompt

    result = await db.execute(select(AiSystemPrompt).limit(1))
    row = result.scalar_one_or_none()
    if row:
        return SystemPromptResponse(prompt=row.prompt)
    return SystemPromptResponse(prompt="")


@router.put(
    "/system-prompt",
    response_model=SystemPromptResponse,
    summary="Update the custom system prompt",
    responses={
        200: {"description": "System prompt updated"},
        403: {"description": "Not a developer"},
        422: {"description": "Prompt exceeds 2000 characters"},
    },
)
async def update_system_prompt(
    body: SystemPromptUpdate,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> SystemPromptResponse:
    """Update the AI system prompt.

    Non-empty prompt: upserts the row and returns the saved value.
    Empty prompt: deletes the row (reset to default) and returns empty string.
    """
    from ..models.ai_system_prompt import AiSystemPrompt

    result = await db.execute(select(AiSystemPrompt).limit(1))
    existing = result.scalar_one_or_none()

    if not body.prompt.strip():
        # Empty prompt: reset to default by deleting the row
        if existing:
            await db.delete(existing)
            await db.commit()
        return SystemPromptResponse(prompt="")

    if existing:
        existing.prompt = body.prompt
    else:
        row = AiSystemPrompt(prompt=body.prompt)
        db.add(row)

    await db.commit()
    return SystemPromptResponse(prompt=body.prompt)


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
    await db.commit()
    await db.refresh(provider)
    await refresh_provider_cache()
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
    await db.commit()
    await db.refresh(provider)
    await refresh_provider_cache()
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
    await db.commit()
    await refresh_provider_cache()


@router.post("/providers/{provider_id}/test", dependencies=[Depends(check_test_rate_limit)])
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
    provider_type: str | None = None,
    capability: str | None = None,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> list[AiModelResponse]:
    """List all AI models across all global providers.

    Optionally filter by ``provider_type`` and/or ``capability``.
    """
    query = (
        select(AiModel)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .where(AiProvider.scope == "global")
        .options(selectinload(AiModel.provider))
    )
    if provider_type is not None:
        query = query.where(AiModel.provider_type == provider_type)
    if capability is not None:
        query = query.where(AiModel.capability == capability)
    query = query.order_by(AiModel.created_at.asc())

    result = await db.execute(query)
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
    prov = prov_result.scalar_one_or_none()
    if prov is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Global provider {body.provider_id} not found",
        )
    if prov.provider_type != body.provider_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"provider_type '{body.provider_type}' does not match provider's type '{prov.provider_type}'",
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
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model '{body.model_id}' with capability '{body.capability}' already exists for this provider",
        )

    await db.commit()

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
    """Update an AI model entry (global scope only)."""
    result = await db.execute(
        select(AiModel)
        .join(AiProvider)
        .where(AiModel.id == model_id, AiProvider.scope == "global")
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
    await db.commit()
    # Re-query with selectinload to ensure provider relationship is available
    result = await db.execute(
        select(AiModel)
        .where(AiModel.id == model.id)
        .options(selectinload(AiModel.provider))
    )
    model = result.scalar_one()
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
    """Delete an AI model entry (global scope only)."""
    result = await db.execute(
        select(AiModel)
        .join(AiProvider)
        .where(AiModel.id == model_id, AiProvider.scope == "global")
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found",
        )
    await db.delete(model)
    await db.commit()


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


@router.get("/capability/{capability}", response_model=CapabilityConfigResponse)
async def get_capability_config(
    capability: str,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> CapabilityConfigResponse:
    """Get the current default provider + model configuration for a capability.

    Returns the default model (``is_default=True``, global scope) and its
    provider information.  When no default is configured, all optional
    fields are ``None``.
    """
    if capability not in VALID_CAPABILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability '{capability}'. Must be one of: {', '.join(sorted(VALID_CAPABILITIES))}",
        )

    result = await db.execute(
        select(AiModel)
        .join(AiProvider, AiModel.provider_id == AiProvider.id)
        .where(
            AiProvider.scope == "global",
            AiModel.capability == capability,
            AiModel.is_default.is_(True),
        )
        .options(selectinload(AiModel.provider))
        .limit(1)
    )
    model = result.scalar_one_or_none()

    if model is None:
        return CapabilityConfigResponse(capability=capability)

    provider = model.provider
    return CapabilityConfigResponse(
        capability=capability,
        provider_id=provider.id,
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        model_id=model.model_id,
        model_display_name=model.display_name,
        has_api_key=provider.api_key_encrypted is not None,
    )


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

    await db.commit()

    # Reload with models for response
    reload_result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider.id)
        .options(selectinload(AiProvider.models))
    )
    provider = reload_result.scalar_one()
    await refresh_provider_cache()
    return AiProviderResponse.model_validate(provider)


@router.post("/test/{capability}", response_model=CapabilityTestResult, dependencies=[Depends(check_test_rate_limit)])
async def test_capability(
    capability: str,
    body: CapabilityTestRequest | None = None,
    current_user: User = Depends(require_developer),
    db: AsyncSession = Depends(get_db),
) -> CapabilityTestResult:
    """Test a provider+model for a capability.

    When a request body is provided, tests inline using the supplied values
    (no database lookup). When no body is provided, tests the currently
    saved default configuration.

    - Chat: sends "Say hello in 5 words" and returns response text + latency
    - Embedding: embeds the word "test" and returns dimension count + latency
    - Vision: sends a small test image and returns description + latency
    """
    if capability not in VALID_CAPABILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid capability '{capability}'",
        )

    if body is not None:
        # Inline test: use the provided values directly without DB lookup.
        # If an api_key is provided, use it. Otherwise, look up the existing
        # provider's key ONLY if the base_url matches (to prevent credential
        # exfiltration via a custom base_url pointing to an attacker's server).
        api_key = body.api_key

        # Validate base_url for ALL provider types (SSRF prevention).
        # For Ollama: full private-range check. For others: block metadata IPs only.
        if body.base_url:
            _validate_base_url(body.base_url, body.provider_type)

        decrypt_failed = False
        if not api_key:
            # Only reuse stored key if base_url matches the saved provider's URL
            existing = await db.execute(
                select(AiProvider).where(
                    AiProvider.scope == "global",
                    AiProvider.provider_type == body.provider_type,
                )
            )
            existing_provider = existing.scalar_one_or_none()
            if existing_provider and existing_provider.api_key_encrypted:
                # Security: refuse to send stored key to a different base_url
                saved_url = (existing_provider.base_url or "").rstrip("/")
                request_url = (body.base_url or "").rstrip("/")
                if saved_url == request_url or not body.base_url:
                    try:
                        api_key = _get_encryption().decrypt(
                            existing_provider.api_key_encrypted
                        )
                    except Exception:
                        decrypt_failed = True
                elif body.base_url:
                    return CapabilityTestResult(
                        success=False,
                        message="API key required when using a custom base URL",
                    )

        if not api_key and body.provider_type != "ollama":
            if decrypt_failed:
                return CapabilityTestResult(
                    success=False,
                    message="Saved key found but decryption failed — try providing a new key",
                )
            return CapabilityTestResult(
                success=False,
                message="No API key provided and no saved key found",
            )

        return await _test_inline_capability(
            body.provider_type, api_key, body.base_url, body.model_id, capability,
        )

    # Fallback: test the saved default configuration
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
    await db.commit()

    # Reload with models relationship for response
    result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider.id)
        .options(selectinload(AiProvider.models))
    )
    provider = result.scalar_one()
    await refresh_provider_cache()
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

    await db.commit()

    # Reload with models relationship for response
    reload_result = await db.execute(
        select(AiProvider)
        .where(AiProvider.id == provider.id)
        .options(selectinload(AiProvider.models))
    )
    provider = reload_result.scalar_one()
    await refresh_provider_cache()
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
    await db.commit()
    await refresh_provider_cache()


@router.post("/me/providers/{provider_type}/test", dependencies=[Depends(check_test_rate_limit)])
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
        logger.warning("Provider connectivity test failed for %s: %s", provider.id, type(exc).__name__)
        # Return a user-friendly error to prevent leaking exception class names
        # or sensitive details. The full exception is logged server-side for debugging.
        exc_type = type(exc).__name__.lower()
        if "auth" in exc_type or "permission" in exc_type:
            error_msg = "Authentication failed — check your API key"
        elif "timeout" in exc_type:
            error_msg = "Connection timed out — check your network and provider URL"
        elif "connection" in exc_type or "network" in exc_type:
            error_msg = "Connection failed — check your network and provider URL"
        else:
            error_msg = "Provider test failed — check your configuration"
        return {"success": False, "error": error_msg}


async def _test_openai(api_key: str | None, base_url: str | None) -> dict[str, object]:
    """Test OpenAI API connectivity by listing models."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return {"success": False, "error": "openai package not installed"}
    import httpx as _httpx

    kwargs: dict = {"timeout": _httpx.Timeout(30.0)}
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
    import httpx as _httpx

    kwargs: dict = {"timeout": _httpx.Timeout(30.0)}
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


async def _test_inline_capability(
    provider_type: str,
    api_key: str | None,
    base_url: str | None,
    model_id: str,
    capability: str,
) -> CapabilityTestResult:
    """Test a capability using raw config values (no DB models required)."""
    import time

    start = time.monotonic()
    try:
        if capability == "chat":
            result = await _test_chat_capability(
                provider_type, api_key, base_url, model_id,
            )
        elif capability == "embedding":
            result = await _test_embedding_capability(
                provider_type, api_key, base_url, model_id,
            )
        elif capability == "vision":
            result = await _test_vision_capability(
                provider_type, api_key, base_url, model_id,
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
        logger.warning(
            "Inline capability test failed for %s: %s: %s",
            capability, type(exc).__name__, exc,
        )
        exc_type = type(exc).__name__.lower()
        exc_msg = str(exc).lower()
        if "auth" in exc_type or "permission" in exc_type:
            error_msg = "Authentication failed — check your API key"
        elif "timeout" in exc_type:
            error_msg = "Connection timed out — check your network and provider URL"
        elif "connection" in exc_type or "network" in exc_type:
            error_msg = "Connection failed — check your network and provider URL"
        elif "bad" in exc_type and "request" in exc_type:
            if "max_tokens" in exc_msg or "max_completion_tokens" in exc_msg:
                error_msg = "Invalid token parameter — model may require max_completion_tokens"
            else:
                # Surface the API's own error message for bad-request errors
                error_msg = f"Bad request — {exc}"
        elif "notfound" in exc_type:
            error_msg = f"Model not found — check the model ID is correct ({model_id})"
        elif "rate" in exc_type and "limit" in exc_type:
            error_msg = "Rate limited — try again in a few seconds"
        else:
            error_msg = "Provider test failed — check your configuration"
        return CapabilityTestResult(
            success=False, message=error_msg, latency_ms=latency_ms,
        )


async def _test_capability_provider(
    provider: AiProvider,
    model: AiModel,
    capability: str,
) -> CapabilityTestResult:
    """Test a specific capability using its configured provider + model.

    Decrypts the provider's API key and delegates to _test_inline_capability.
    """
    api_key: str | None = None
    if provider.api_key_encrypted:
        try:
            api_key = _get_encryption().decrypt(provider.api_key_encrypted)
        except Exception:
            return CapabilityTestResult(
                success=False,
                message="Failed to decrypt API key",
            )

    return await _test_inline_capability(
        provider.provider_type, api_key, provider.base_url, model.model_id, capability,
    )


async def _test_chat_capability(
    provider_type: str,
    api_key: str | None,
    base_url: str | None,
    model_id: str,
) -> CapabilityTestResult:
    """Test chat capability by sending a short prompt."""
    import httpx as _httpx

    if provider_type == "openai":
        from openai import AsyncOpenAI

        kwargs: dict = {"timeout": _httpx.Timeout(30.0)}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)
        try:
            resp = await client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Say hello in 5 words"}],
                max_completion_tokens=20,
            )
            text = resp.choices[0].message.content or ""
            return CapabilityTestResult(success=True, message=text.strip())
        finally:
            await client.close()

    elif provider_type == "anthropic":
        from anthropic import AsyncAnthropic

        kwargs = {"timeout": _httpx.Timeout(30.0)}
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
    import httpx as _httpx

    if provider_type == "openai":
        from openai import AsyncOpenAI

        kwargs: dict = {"timeout": _httpx.Timeout(30.0)}
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
    """Test vision capability by sending a small test image."""
    import httpx as _httpx

    # 64x64 solid red square PNG (168 bytes, base64-encoded).
    # OpenAI rejects 1x1 images as "unsupported"; 64x64 is safely above minimum.
    b64_pixel = (
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAb0lEQVR4nO3P"
        "AQkAAAyEwO9feoshgnABdLep8QUNyPEFDcjxBQ3I8QUNyPEFDcjxBQ3I8QUN"
        "yPEFDcjxBQ3I8QUNyPEFDcjxBQ3I8QUNyPEFDcjxBQ3I8QUNyPEFDcjxBQ3I"
        "8QUNyPEFDcjxBQ3IPanc8OLDQitxAAAAAElFTkSuQmCC"
    )

    if provider_type == "openai":
        from openai import AsyncOpenAI

        kwargs: dict = {"timeout": _httpx.Timeout(30.0)}
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
                max_completion_tokens=30,
            )
            text = resp.choices[0].message.content or ""
            return CapabilityTestResult(success=True, message=text.strip())
        finally:
            await client.close()

    elif provider_type == "anthropic":
        from anthropic import AsyncAnthropic

        kwargs = {"timeout": _httpx.Timeout(30.0)}
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

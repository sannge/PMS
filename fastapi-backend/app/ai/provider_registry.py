"""Provider registry for resolving and caching AI provider instances."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models.ai_model import AiModel
from ..models.ai_provider import AiProvider
from .anthropic_provider import AnthropicProvider
from .encryption import ApiKeyEncryption
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .provider_interface import LLMProvider, LLMProviderError, VisionProvider

logger = logging.getLogger(__name__)


class ConfigurationError(LLMProviderError):
    """Raised when AI provider configuration is missing or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, provider="registry")


_PROVIDER_FACTORIES: dict[str, type] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
}


class ProviderRegistry:
    """Singleton registry that resolves and caches AI provider instances.

    Resolution order for chat and vision providers:
    1. User-specific provider (scope='user', user_id matches) if user_id given
    2. Global provider (scope='global', is_enabled=True)
    3. Raises ConfigurationError if none found

    Embedding providers are always resolved globally (never user-overridable).

    The registry caches instantiated provider objects keyed by provider ID.
    Call ``refresh()`` to clear the cache after configuration changes.

    Note: This is a per-process singleton. In multi-worker deployments (e.g.
    gunicorn with multiple uvicorn workers), each worker maintains its own
    cache. Configuration changes made via the admin API will take effect in
    the requesting worker immediately (via ``refresh()``), but other workers
    will continue using cached providers until their cache is refreshed or
    the worker is restarted. User overrides also work independently per
    worker. This is acceptable for the target scale.
    """

    _instance: "ProviderRegistry | None" = None

    def __new__(cls) -> "ProviderRegistry":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._cache = {}
            cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        # Only initialize _cache if it doesn't already exist (singleton)
        if not hasattr(self, "_cache"):
            self._cache: dict[str, LLMProvider | VisionProvider] = {}

    def _build_adapter(self, provider: AiProvider, api_key: str | None) -> LLMProvider | VisionProvider:
        """Instantiate a provider adapter from its DB record.

        Args:
            provider: AiProvider ORM instance.
            api_key: Decrypted API key (may be None for Ollama).

        Returns:
            An instantiated provider adapter.

        Raises:
            ConfigurationError: If the provider_type is unknown.
        """
        factory = _PROVIDER_FACTORIES.get(provider.provider_type)
        if factory is None:
            raise ConfigurationError(
                f"Unknown provider type: {provider.provider_type}"
            )

        if provider.provider_type == "ollama":
            return factory(api_key=api_key, base_url=provider.base_url)
        else:
            if not api_key:
                raise ConfigurationError(
                    f"Provider '{provider.name}' ({provider.provider_type}) "
                    f"requires an API key but none is configured."
                )
            return factory(api_key=api_key, base_url=provider.base_url)

    def _decrypt_key(self, provider: AiProvider) -> str | None:
        """Decrypt provider's API key, returning None if not set."""
        if not provider.api_key_encrypted:
            return None
        encryption = ApiKeyEncryption(settings.ai_encryption_key)
        return encryption.decrypt(provider.api_key_encrypted)

    async def _resolve_provider(
        self,
        db: AsyncSession,
        capability: str,
        user_id: UUID | None = None,
    ) -> tuple[AiProvider, AiModel]:
        """Resolve the best provider and default model for a capability.

        Args:
            db: Active database session.
            capability: One of 'chat', 'embedding', 'vision'.
            user_id: Optional user ID for user-specific override lookup.

        Returns:
            Tuple of (AiProvider, AiModel) for the resolved default.

        Raises:
            ConfigurationError: If no suitable provider is found.
        """
        # Try user-specific provider first
        if user_id is not None:
            user_provider = await self._find_provider_for_capability(
                db, capability, scope="user", user_id=user_id
            )
            if user_provider is not None:
                return user_provider

        # Fall back to global provider
        global_provider = await self._find_provider_for_capability(
            db, capability, scope="global"
        )
        if global_provider is not None:
            return global_provider

        raise ConfigurationError(
            f"No enabled AI provider configured for '{capability}'. "
            f"Please configure a provider in Admin > AI Settings."
        )

    async def _find_provider_for_capability(
        self,
        db: AsyncSession,
        capability: str,
        scope: str,
        user_id: UUID | None = None,
    ) -> tuple[AiProvider, AiModel] | None:
        """Find an enabled provider with a default model for the given capability.

        Returns:
            Tuple of (AiProvider, AiModel) or None if not found.
        """
        query = (
            select(AiModel)
            .join(AiProvider, AiModel.provider_id == AiProvider.id)
            .options(selectinload(AiModel.provider))
            .where(
                AiModel.capability == capability,
                AiModel.is_default.is_(True),
                AiModel.is_enabled.is_(True),
                AiProvider.is_enabled.is_(True),
                AiProvider.scope == scope,
            )
        )
        if scope == "user" and user_id is not None:
            query = query.where(AiProvider.user_id == user_id)

        result = await db.execute(query)
        model = result.scalar_one_or_none()
        if model is None:
            return None

        return model.provider, model

    async def get_chat_provider(
        self,
        db: AsyncSession,
        user_id: UUID | None = None,
    ) -> tuple[LLMProvider, str]:
        """Resolve the chat provider and default model.

        Args:
            db: Active database session.
            user_id: Optional user ID for user-specific override.

        Returns:
            Tuple of (LLMProvider instance, default model ID string).
        """
        provider, model = await self._resolve_provider(db, "chat", user_id)
        cache_key = f"chat:{provider.id}"

        if cache_key not in self._cache:
            api_key = self._decrypt_key(provider)
            self._cache[cache_key] = self._build_adapter(provider, api_key)

        return self._cache[cache_key], model.model_id  # type: ignore[return-value]

    async def get_embedding_provider(
        self,
        db: AsyncSession,
    ) -> tuple[LLMProvider, str]:
        """Resolve the embedding provider and default model.

        Embeddings are always global (never user-overridable) to ensure
        consistent vector dimensions across the application.

        Args:
            db: Active database session.

        Returns:
            Tuple of (LLMProvider instance, default model ID string).
        """
        provider, model = await self._resolve_provider(db, "embedding")
        cache_key = f"embedding:{provider.id}"

        if cache_key not in self._cache:
            api_key = self._decrypt_key(provider)
            self._cache[cache_key] = self._build_adapter(provider, api_key)

        return self._cache[cache_key], model.model_id  # type: ignore[return-value]

    async def get_vision_provider(
        self,
        db: AsyncSession,
        user_id: UUID | None = None,
    ) -> tuple[VisionProvider, str]:
        """Resolve the vision provider and default model.

        Args:
            db: Active database session.
            user_id: Optional user ID for user-specific override.

        Returns:
            Tuple of (VisionProvider instance, default model ID string).
        """
        provider, model = await self._resolve_provider(db, "vision", user_id)
        cache_key = f"vision:{provider.id}"

        if cache_key not in self._cache:
            api_key = self._decrypt_key(provider)
            adapter = self._build_adapter(provider, api_key)
            if not isinstance(adapter, VisionProvider):
                raise ConfigurationError(
                    f"Provider '{provider.name}' ({provider.provider_type}) "
                    f"does not support vision capabilities."
                )
            self._cache[cache_key] = adapter

        return self._cache[cache_key], model.model_id  # type: ignore[return-value]

    async def refresh(self) -> None:
        """Clear all cached provider instances.

        Call after provider configuration changes (add/update/delete
        providers, rotate API keys, etc.).
        """
        # Close any Ollama clients that hold open connections
        for adapter in self._cache.values():
            if isinstance(adapter, OllamaProvider):
                await adapter.close()
        self._cache.clear()
        logger.info("Provider registry cache cleared")

"""Pydantic schemas for AI provider and model configuration."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Validators (reused across schemas)
# ---------------------------------------------------------------------------

VALID_PROVIDER_TYPES = {"openai", "anthropic", "ollama"}
VALID_CAPABILITIES = {"chat", "embedding", "vision"}


def _validate_provider_type(v: str) -> str:
    if v not in VALID_PROVIDER_TYPES:
        raise ValueError(
            f"provider_type must be one of: {', '.join(sorted(VALID_PROVIDER_TYPES))}"
        )
    return v


def _validate_capability(v: str) -> str:
    if v not in VALID_CAPABILITIES:
        raise ValueError(
            f"capability must be one of: {', '.join(sorted(VALID_CAPABILITIES))}"
        )
    return v


# ---------------------------------------------------------------------------
# AiModel schemas
# ---------------------------------------------------------------------------


class AiModelCreate(BaseModel):
    """Schema for creating a new AI model entry."""

    provider_id: UUID = Field(
        ...,
        description="ID of the parent AI provider",
    )
    model_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Provider's model identifier (e.g. 'gpt-4o')",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable model name",
    )
    provider_type: str = Field(
        ...,
        description="Provider type: openai, anthropic, or ollama",
    )
    capability: str = Field(
        ...,
        description="Model capability: chat, embedding, or vision",
    )
    embedding_dimensions: Optional[int] = Field(
        None,
        ge=1,
        description="Output dimensions for embedding models",
    )
    max_tokens: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum token limit for the model",
    )
    is_default: bool = Field(
        False,
        description="Whether this is the default model for its capability",
    )
    is_enabled: bool = Field(
        True,
        description="Whether model is active",
    )

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        return _validate_provider_type(v)

    @field_validator("capability")
    @classmethod
    def validate_capability(cls, v: str) -> str:
        return _validate_capability(v)


class AiModelUpdate(BaseModel):
    """Schema for updating an AI model entry. All fields optional."""

    model_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
    )
    display_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
    )
    provider_type: Optional[str] = None
    capability: Optional[str] = None
    embedding_dimensions: Optional[int] = Field(None, ge=1)
    max_tokens: Optional[int] = Field(None, ge=1)
    is_default: Optional[bool] = None
    is_enabled: Optional[bool] = None

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_provider_type(v)
        return v

    @field_validator("capability")
    @classmethod
    def validate_capability(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_capability(v)
        return v


class AiModelResponse(BaseModel):
    """Schema for AI model response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    model_id: str
    display_name: str
    provider_type: str
    capability: str
    embedding_dimensions: Optional[int] = None
    max_tokens: Optional[int] = None
    is_default: bool = False
    is_enabled: bool = True
    created_at: datetime
    updated_at: datetime
    provider_name: str = ""

    @model_validator(mode="before")
    @classmethod
    def extract_provider_name(cls, data: object) -> object:
        """Populate provider_name from the related provider object."""
        if hasattr(data, "provider") and data.provider is not None:
            # ORM object with eagerly loaded provider relationship
            if not isinstance(data, dict):
                obj_dict: dict = {}
                for field_name in cls.model_fields:
                    if field_name == "provider_name":
                        obj_dict["provider_name"] = data.provider.name
                    elif hasattr(data, field_name):
                        obj_dict[field_name] = getattr(data, field_name)
                return obj_dict
        if isinstance(data, dict) and "provider_name" not in data:
            provider = data.get("provider")
            if provider and hasattr(provider, "name"):
                data["provider_name"] = provider.name
        return data


# ---------------------------------------------------------------------------
# AiProvider schemas
# ---------------------------------------------------------------------------


class AiProviderCreate(BaseModel):
    """Schema for creating a new AI provider."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Internal provider name",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable provider name",
    )
    provider_type: str = Field(
        ...,
        description="Provider backend type: openai, anthropic, or ollama",
    )
    base_url: Optional[str] = Field(
        None,
        description="Custom API endpoint URL",
    )
    api_key: Optional[str] = Field(
        None,
        description="API key (will be encrypted before storage)",
    )
    is_enabled: bool = Field(
        True,
        description="Whether provider is active",
    )

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        return _validate_provider_type(v)


class UserProviderOverride(BaseModel):
    """Schema for a user overriding a provider with their own API key.

    User overrides are restricted to chat capability only. Embedding and
    vision always resolve from the global (developer-configured) provider.
    """

    provider_type: str = Field(
        ...,
        description="Provider type to override: openai or anthropic",
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="User's personal API key",
    )
    base_url: Optional[str] = Field(
        None,
        description="Custom API endpoint URL",
    )
    preferred_model: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Preferred chat model ID (e.g. 'claude-sonnet-4-6')",
    )

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        return _validate_provider_type(v)


class AiProviderUpdate(BaseModel):
    """Schema for updating an AI provider. All fields optional."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
    )
    display_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
    )
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_enabled: Optional[bool] = None

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_provider_type(v)
        return v


class AiProviderResponse(BaseModel):
    """Schema for AI provider response. Never exposes api_key_encrypted."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str
    provider_type: str
    base_url: Optional[str] = None
    is_enabled: bool = True
    scope: str = "global"
    user_id: Optional[UUID] = None
    has_api_key: bool = False
    created_at: datetime
    updated_at: datetime
    models: list[AiModelResponse] = []

    @model_validator(mode="before")
    @classmethod
    def compute_has_api_key(cls, data: object) -> object:
        """Compute has_api_key from api_key_encrypted presence on the ORM object."""
        if hasattr(data, "api_key_encrypted"):
            # ORM object: check if the encrypted key column is set
            if not isinstance(data, dict):
                # Create a mutable copy we can work with — Pydantic will
                # read attributes from the original ORM object, but we need
                # to inject has_api_key. Convert to dict for mutation.
                obj_dict: dict = {}
                for field_name in cls.model_fields:
                    if field_name == "has_api_key":
                        obj_dict["has_api_key"] = data.api_key_encrypted is not None
                    elif hasattr(data, field_name):
                        obj_dict[field_name] = getattr(data, field_name)
                return obj_dict
        if isinstance(data, dict):
            encrypted = data.pop("api_key_encrypted", None)
            if "has_api_key" not in data:
                data["has_api_key"] = encrypted is not None
        return data


# ---------------------------------------------------------------------------
# Summary schema
# ---------------------------------------------------------------------------


class AiConfigSummary(BaseModel):
    """Summary of AI configuration with defaults."""

    providers: list[AiProviderResponse] = []
    default_chat_model: Optional[AiModelResponse] = None
    default_embedding_model: Optional[AiModelResponse] = None
    default_vision_model: Optional[AiModelResponse] = None


# ---------------------------------------------------------------------------
# Per-capability configuration (developer settings panel)
# ---------------------------------------------------------------------------


class CapabilityConfig(BaseModel):
    """Schema for saving per-capability provider + model configuration."""

    provider_type: str = Field(
        ...,
        description="Provider type: openai, anthropic, or ollama",
    )
    api_key: Optional[str] = Field(
        None,
        description="API key (will be encrypted). Omit to keep existing key.",
    )
    model_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Model ID to set as default for this capability",
    )
    base_url: Optional[str] = Field(
        None,
        description="Custom API endpoint URL (Ollama only)",
    )

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        return _validate_provider_type(v)


class CapabilityTestResult(BaseModel):
    """Result from testing a capability's provider+model."""

    success: bool
    message: str
    latency_ms: Optional[int] = None


class EffectiveChatConfig(BaseModel):
    """Effective chat configuration for the current user."""

    source: str = Field(
        ...,
        description="'override' if using personal key, 'global' if using company default",
    )
    provider_type: Optional[str] = None
    model_id: Optional[str] = None
    display_name: Optional[str] = None

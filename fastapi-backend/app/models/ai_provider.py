"""AiProvider SQLAlchemy model for AI provider configuration.

Stores AI provider connections (OpenAI, Anthropic, Ollama) with encrypted
API keys. Providers can be scoped globally (shared across all users) or
per-user (personal API key overrides). Each provider has a one-to-many
relationship to AiModel entries that define available models.
"""

import uuid
from typing import TYPE_CHECKING

from ..utils.timezone import utc_now

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .ai_model import AiModel
    from .user import User


class AiProvider(Base):
    """
    AI provider configuration model.

    Stores connection details for AI service providers. Supports global
    providers (admin-configured, shared) and user-scoped providers
    (personal API key overrides). API keys are stored encrypted.

    Attributes:
        id: Unique identifier (UUID)
        name: Internal provider name (unique within scope)
        display_name: Human-readable provider name
        provider_type: Provider backend type (openai/anthropic/ollama)
        base_url: Custom API endpoint URL (nullable, for self-hosted)
        api_key_encrypted: Encrypted API key (nullable, e.g. Ollama needs none)
        is_enabled: Whether provider is active
        scope: Provider scope - 'global' or 'user'
        user_id: FK to Users (set when scope='user')
        created_at: Timestamp when provider was created
        updated_at: Timestamp when provider was last updated
    """

    __tablename__ = "AiProviders"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Provider identity
    name = Column(
        String(100),
        nullable=False,
    )

    display_name = Column(
        String(255),
        nullable=False,
    )

    provider_type = Column(
        String(50),
        nullable=False,
        index=True,
    )

    # Connection details
    base_url = Column(
        Text,
        nullable=True,
    )

    api_key_encrypted = Column(
        Text,
        nullable=True,
    )

    # Status
    is_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    # Scoping
    scope = Column(
        String(20),
        nullable=False,
        default="global",
        server_default="global",
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "provider_type IN ('openai', 'anthropic', 'ollama')",
            name="ck_ai_providers_provider_type",
        ),
        CheckConstraint(
            "scope IN ('global', 'user')",
            name="ck_ai_providers_scope",
        ),
    )

    # Relationships
    models = relationship(
        "AiModel",
        back_populates="provider",
        lazy="selectin",
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of AiProvider."""
        return f"<AiProvider(id={self.id}, name={self.name}, type={self.provider_type})>"

"""AiModel SQLAlchemy model for AI model configuration.

Stores available AI models per provider with capability tags (chat, embedding,
vision). Each model belongs to exactly one provider and has a unique constraint
on (provider_id, model_id, capability) to allow the same model ID to be
registered for different capabilities.
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
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .ai_provider import AiProvider


class AiModel(Base):
    """
    AI model configuration model.

    Represents a specific AI model available through a provider. Models
    are tagged with a capability (chat, embedding, vision) and can be
    marked as the default for that capability. The unique constraint on
    (provider_id, model_id, capability) allows registering the same
    underlying model for multiple capabilities.

    Attributes:
        id: Unique identifier (UUID)
        provider_id: FK to AiProviders
        model_id: Provider's model identifier (e.g. 'gpt-4o', 'claude-sonnet-4-20250514')
        display_name: Human-readable model name
        capability: Model capability type (chat/embedding/vision)
        embedding_dimensions: Output dimensions for embedding models
        max_tokens: Maximum token limit for the model
        is_default: Whether this is the default model for its capability
        is_enabled: Whether model is active
        created_at: Timestamp when model was created
        updated_at: Timestamp when model was last updated
    """

    __tablename__ = "AiModels"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Provider association
    provider_id = Column(
        UUID(as_uuid=True),
        ForeignKey("AiProviders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Model identity
    model_id = Column(
        String(255),
        nullable=False,
        index=True,
    )

    display_name = Column(
        String(255),
        nullable=False,
    )

    # Provider type (denormalized for filtering without join)
    provider_type = Column(
        String(50),
        nullable=False,
        index=True,
    )

    # Capability
    capability = Column(
        String(50),
        nullable=False,
        index=True,
    )

    # Model parameters
    embedding_dimensions = Column(
        Integer,
        nullable=True,
    )

    max_tokens = Column(
        Integer,
        nullable=True,
    )

    # Status
    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    is_enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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
        UniqueConstraint(
            "provider_id", "model_id", "capability",
            name="uq_ai_models_provider_model_capability",
        ),
        CheckConstraint(
            "capability IN ('chat', 'embedding', 'vision')",
            name="ck_ai_models_capability",
        ),
        CheckConstraint(
            "provider_type IN ('openai', 'anthropic', 'ollama')",
            name="ck_ai_models_provider_type",
        ),
    )

    # Relationships
    provider = relationship(
        "AiProvider",
        back_populates="models",
    )

    def __repr__(self) -> str:
        """String representation of AiModel."""
        return f"<AiModel(id={self.id}, model_id={self.model_id}, capability={self.capability})>"

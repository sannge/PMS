"""AiSystemPrompt SQLAlchemy model for global AI system prompt configuration.

Stores a single-row system prompt override for the AI agent.
When populated, the agent uses this prompt instead of the hardcoded default.
"""

import uuid

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from ..database import Base


class AiSystemPrompt(Base):
    """Single-row table storing the AI agent system prompt override.

    Attributes:
        id: Unique identifier (UUID)
        prompt: The system prompt text
        updated_at: When the prompt was last updated
    """

    __tablename__ = "ai_system_prompts"
    __allow_unmapped__ = True

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
        nullable=False,
    )

    prompt = Column(
        Text,
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        """String representation of AiSystemPrompt."""
        return f"<AiSystemPrompt(id={self.id}, prompt_len={len(self.prompt) if self.prompt else 0})>"

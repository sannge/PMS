"""ChatMessage model for persistent AI chat messages."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class ChatMessage(Base):
    __tablename__ = "ChatMessages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_chatmessages_session_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ChatSessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    sources: Mapped[Any] = mapped_column(JSONB, nullable=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_error: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    session: Mapped["ChatSession"] = relationship(  # noqa: F821
        "ChatSession", back_populates="messages"
    )

"""Note SQLAlchemy model for OneNote-style note-taking."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .application import Application
    from .user import User


class Note(Base):
    """
    Note model representing OneNote-style notes within an application.

    Notes support hierarchical organization through parent-child relationships
    and multi-tab interface through tab_order.

    Attributes:
        id: Unique identifier (UUID)
        application_id: FK to parent application
        parent_id: FK to parent note (for hierarchy/sections)
        title: Note title
        content: Rich text content (HTML or JSON)
        tab_order: Order of the note in tab bar
        created_by: FK to user who created the note
        created_at: Timestamp when note was created
        updated_at: Timestamp when note was last updated
    """

    __tablename__ = "Notes"
    __allow_unmapped__ = True

    # Primary key - UUID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Foreign keys
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Notes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Note details
    title = Column(
        String(255),
        nullable=False,
        index=True,
    )
    content = Column(
        Text,
        nullable=True,
    )
    tab_order = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    application = relationship(
        "Application",
        back_populates="notes",
        lazy="joined",
    )
    creator = relationship(
        "User",
        back_populates="created_notes",
        lazy="joined",
    )
    parent = relationship(
        "Note",
        remote_side=[id],
        back_populates="children",
        lazy="joined",
    )
    children = relationship(
        "Note",
        back_populates="parent",
        lazy="dynamic",
    )
    attachments = relationship(
        "Attachment",
        back_populates="note",
        cascade="all, delete-orphan",
        lazy="dynamic",
        foreign_keys="Attachment.note_id",
    )

    def __repr__(self) -> str:
        """String representation of Note."""
        return f"<Note(id={self.id}, title={self.title[:30] if self.title else ''})>"

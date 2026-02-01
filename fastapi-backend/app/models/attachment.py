"""Attachment SQLAlchemy model for file attachments stored in MinIO."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .task import Task
    from .user import User


class Attachment(Base):
    """
    Attachment model representing files stored in MinIO object storage.

    Attachments use a polymorphic association pattern to link to different
    entity types (tasks, comments). Files are stored in MinIO and
    referenced by bucket and key.

    Attributes:
        id: Unique identifier (UUID)
        file_name: Original file name
        file_type: MIME type of the file
        file_size: File size in bytes
        minio_bucket: MinIO bucket name
        minio_key: MinIO object key (path within bucket)
        uploaded_by: FK to user who uploaded the file
        entity_type: Type of entity this is attached to ('task', 'comment')
        entity_id: ID of the entity this is attached to
        task_id: Direct FK to task (when entity_type is 'task')
        created_at: Timestamp when attachment was created
    """

    __tablename__ = "Attachments"
    __allow_unmapped__ = True

    # Primary key - UUID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # File metadata
    file_name = Column(
        String(255),
        nullable=False,
    )
    file_type = Column(
        String(100),
        nullable=True,
    )
    file_size = Column(
        BigInteger,
        nullable=True,
    )

    # MinIO storage reference
    minio_bucket = Column(
        String(100),
        nullable=True,
    )
    minio_key = Column(
        String(500),
        nullable=True,
    )

    # Polymorphic association fields
    entity_type = Column(
        String(50),
        nullable=True,
        index=True,
    )
    entity_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Direct foreign keys for common entity types
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    comment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    uploaded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    task = relationship(
        "Task",
        back_populates="attachments",
        lazy="joined",
    )
    comment = relationship(
        "Comment",
        back_populates="attachments",
        lazy="joined",
        foreign_keys=[comment_id],
    )
    uploader = relationship(
        "User",
        back_populates="uploaded_attachments",
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of Attachment."""
        return f"<Attachment(id={self.id}, file_name={self.file_name})>"

"""Document SQLAlchemy model for the knowledge base.

Documents store rich text content in three formats: TipTap JSON (editor),
Markdown (AI consumption), and plain text (search indexing). Each document
belongs to exactly one scope (application, project, or personal/user)
enforced by a CHECK constraint. Supports soft delete via deleted_at and
optimistic concurrency via row_version.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .document_folder import DocumentFolder
    from .document_tag import DocumentTagAssignment
    from .user import User


class Document(Base):
    """
    Document model representing a knowledge base document.

    Documents are the core content unit of the knowledge base. They can
    exist in any of three scopes (application, project, personal) and
    optionally belong to a folder. Content is stored in three formats
    for different consumers: JSON for the TipTap editor, Markdown for
    AI tools, and plain text for full-text search.

    Attributes:
        id: Unique identifier (UUID)
        application_id: FK to Applications (scope - exactly one scope FK must be set)
        project_id: FK to Projects (scope)
        user_id: FK to Users (personal scope)
        folder_id: FK to DocumentFolder (nullable - null means unfiled)
        title: Document title
        content_json: TipTap JSON content (editor format)
        content_markdown: Markdown content (AI format)
        content_plain: Plain text content (search indexing)
        sort_order: Position within folder or unfiled list
        created_by: FK to user who created the document
        row_version: Optimistic concurrency version counter
        schema_version: TipTap schema version for content evolution
        deleted_at: Soft delete timestamp (null = active)
        created_at: Timestamp when document was created
        updated_at: Timestamp when document was last updated
    """

    __tablename__ = "Documents"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Scope foreign keys (exactly one must be non-null)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Applications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Folder association (null = unfiled)
    folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("DocumentFolders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Document details
    title = Column(
        String(255),
        nullable=False,
        index=True,
    )

    # Content in three formats
    content_json = Column(
        Text,
        nullable=True,
    )

    content_markdown = Column(
        Text,
        nullable=True,
    )

    content_plain = Column(
        Text,
        nullable=True,
    )

    # Ordering
    sort_order = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # Audit
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Concurrency and versioning
    row_version = Column(
        Integer,
        nullable=False,
        default=1,
    )

    schema_version = Column(
        Integer,
        nullable=False,
        default=1,
    )

    # Soft delete
    deleted_at = Column(
        DateTime,
        nullable=True,
        index=True,
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

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_documents_exactly_one_scope",
        ),
        Index("ix_documents_app_folder", "application_id", "folder_id"),
        Index("ix_documents_project_folder", "project_id", "folder_id"),
    )

    # Relationships
    folder = relationship(
        "DocumentFolder",
        back_populates="documents",
        lazy="joined",
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="joined",
    )

    tags = relationship(
        "DocumentTagAssignment",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        """String representation of Document."""
        return f"<Document(id={self.id}, title={self.title[:30] if self.title else ''})>"

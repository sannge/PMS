"""DocumentTag and DocumentTagAssignment SQLAlchemy models for the knowledge base tag system.

Tags provide cross-cutting organization for documents. Each tag is scoped to either
an application (usable by application-level and project-level documents within that
application) or a user (usable by personal documents only). The DocumentTagAssignment
model implements the many-to-many relationship between documents and tags.
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
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .document import Document


class DocumentTag(Base):
    """
    Tag definition scoped to an application or a user's personal namespace.

    Tags are named labels with optional color for UI display. Each tag belongs
    to exactly one scope: an application (shared across all projects in that
    application) or a user (for personal documents only). Duplicate tag names
    within the same scope are prevented by partial unique indexes.

    Attributes:
        id: Unique identifier (UUID)
        name: Tag display name (max 100 chars)
        color: Optional hex color code for UI (e.g. "#FF5733")
        application_id: FK to Applications (scope - exactly one of application_id/user_id must be set)
        user_id: FK to Users (personal scope)
        created_at: Timestamp when tag was created
    """

    __tablename__ = "DocumentTags"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Tag details
    name = Column(
        String(100),
        nullable=False,
    )

    color = Column(
        String(7),
        nullable=True,
    )

    # Scope foreign keys (exactly one must be non-null)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Applications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_document_tags_exactly_one_scope",
        ),
        # Partial unique indexes: no duplicate tag names within a scope
        Index(
            "uq_document_tags_app_name",
            "application_id",
            "name",
            unique=True,
            postgresql_where="application_id IS NOT NULL",
        ),
        Index(
            "uq_document_tags_user_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where="user_id IS NOT NULL",
        ),
    )

    # Relationships
    assignments = relationship(
        "DocumentTagAssignment",
        back_populates="tag",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        """String representation of DocumentTag."""
        return f"<DocumentTag(id={self.id}, name={self.name})>"


class DocumentTagAssignment(Base):
    """
    Many-to-many join table linking documents to tags.

    Each assignment represents a single tag applied to a single document.
    Duplicate assignments (same document + tag) are prevented by a unique
    constraint. Cascading deletes ensure assignments are cleaned up when
    either the document or the tag is deleted.

    Attributes:
        id: Unique identifier (UUID)
        document_id: FK to Documents
        tag_id: FK to DocumentTags
        created_at: Timestamp when assignment was created
    """

    __tablename__ = "DocumentTagAssignments"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Foreign keys
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tag_id = Column(
        UUID(as_uuid=True),
        ForeignKey("DocumentTags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("document_id", "tag_id", name="uq_document_tag_assignments_doc_tag"),
    )

    # Relationships
    document = relationship(
        "Document",
        back_populates="tags",
        lazy="joined",
    )

    tag = relationship(
        "DocumentTag",
        back_populates="assignments",
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of DocumentTagAssignment."""
        return f"<DocumentTagAssignment(document_id={self.document_id}, tag_id={self.tag_id})>"

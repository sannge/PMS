"""DocumentFolder SQLAlchemy model for hierarchical folder organization within knowledge base.

Folders use a materialized path pattern for efficient tree queries. Each folder
belongs to exactly one scope (application, project, or personal/user) enforced
by a CHECK constraint.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .document import Document


class DocumentFolder(Base):
    """
    DocumentFolder model for organizing documents into a tree hierarchy.

    Folders support nesting up to 5 levels deep. Each folder belongs to
    exactly one scope: application, project, or personal (user). The
    materialized_path column stores the full ancestry path for efficient
    tree queries without recursive CTEs.

    Attributes:
        id: Unique identifier (UUID)
        parent_id: FK to parent folder (self-referential, nullable for root folders)
        materialized_path: Full path string e.g. "/{ancestor-uuid}/{self-uuid}/"
        depth: Nesting depth (0 = root, max 5)
        name: Folder display name
        sort_order: Position within siblings
        application_id: FK to Applications (scope - exactly one scope FK must be set)
        project_id: FK to Projects (scope)
        user_id: FK to Users (personal scope)
        created_by: FK to user who created the folder
        created_at: Timestamp when folder was created
        updated_at: Timestamp when folder was last updated
    """

    __tablename__ = "DocumentFolders"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Self-referential parent
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("DocumentFolders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Materialized path for efficient tree queries
    materialized_path = Column(
        String(4000),
        nullable=False,
        default="/",
        index=True,
    )

    # Nesting depth (0 = root)
    depth = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # Folder details
    name = Column(
        String(255),
        nullable=False,
    )

    sort_order = Column(
        Integer,
        nullable=False,
        default=0,
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

    # Audit
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_document_folders_exactly_one_scope",
        ),
    )

    # Relationships
    parent = relationship(
        "DocumentFolder",
        remote_side=[id],
        back_populates="children",
        lazy="joined",
    )

    children: List["DocumentFolder"] = relationship(
        "DocumentFolder",
        back_populates="parent",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    documents: List["Document"] = relationship(
        "Document",
        back_populates="folder",
        lazy="dynamic",
        passive_deletes=True,
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of DocumentFolder."""
        return f"<DocumentFolder(id={self.id}, name={self.name}, depth={self.depth})>"

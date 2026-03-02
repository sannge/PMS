"""ImportJob SQLAlchemy model for document import tracking.

Tracks PDF/DOCX/PPTX file imports through the Docling conversion pipeline.
Each job records the original file metadata, processing status, progress,
and links to the resulting Document on successful completion.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
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
from ..utils.timezone import utc_now

if TYPE_CHECKING:
    from .document import Document
    from .user import User


class ImportJob(Base):
    """Model representing a document import job.

    Tracks the lifecycle of importing an external file (PDF, DOCX, PPTX)
    into the knowledge base via the Docling conversion pipeline.

    Attributes:
        id: Unique identifier (UUID).
        user_id: FK to the user who initiated the import.
        file_name: Original filename of the uploaded file.
        file_type: File format ('pdf', 'docx', 'pptx').
        file_size: File size in bytes.
        title: Optional display title (derived from filename if not provided).
        status: Current job status ('pending', 'processing', 'completed', 'failed').
        progress_pct: Completion percentage (0-100).
        document_id: FK to the resulting Document (set on successful completion).
        scope: Target scope ('application', 'project', 'personal').
        scope_id: UUID of the application, project, or user for the target scope.
        folder_id: Optional target folder UUID.
        error_message: Error details (set on failure).
        created_at: Timestamp when the job was created.
        completed_at: Timestamp when the job finished (success or failure).
    """

    __tablename__ = "ImportJobs"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Who initiated the import
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # File metadata
    file_name = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    title = Column(String(255), nullable=True)

    # Job status and progress
    status = Column(String(50), nullable=False, default="pending")
    progress_pct = Column(Integer, nullable=False, default=0)

    # Result link (set on successful completion)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Target scope
    scope = Column(String(20), nullable=False)
    # scope_id is a polymorphic FK: references Applications.id, Projects.id, or
    # Users.id depending on the value of `scope`. A single SQL FK constraint is
    # not possible; use validate_scope() for runtime validation.
    scope_id = Column(UUID(as_uuid=True), nullable=False)
    folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("DocumentFolders.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Temp file path for worker to locate uploaded file
    temp_file_path = Column(String(1000), nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "file_type IN ('pdf', 'docx', 'pptx')",
            name="ck_import_jobs_file_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_import_jobs_status",
        ),
        CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100",
            name="ck_import_jobs_progress_pct",
        ),
        CheckConstraint(
            "scope IN ('application', 'project', 'personal')",
            name="ck_import_jobs_scope",
        ),
        Index("idx_import_jobs_user", "user_id"),
        Index("idx_import_jobs_status", "status"),
    )

    # Relationships (default lazy loading -- use selectinload/joinedload at query site)
    user = relationship(
        "User",
        foreign_keys=[user_id],
    )

    document = relationship(
        "Document",
        foreign_keys=[document_id],
    )

    @classmethod
    async def validate_scope(cls, db, scope: str, scope_id) -> bool:
        """Validate that scope_id references an existing entity for the given scope.

        Since scope_id is a polymorphic FK (points to Applications, Projects, or
        Users depending on scope), a single SQL FK constraint cannot enforce this.
        Call this method before creating an ImportJob to ensure referential integrity.

        Returns True if the referenced entity exists, False otherwise.
        """
        from sqlalchemy import select as sa_select

        if scope == "application":
            from .application import Application
            result = await db.execute(
                sa_select(Application.id).where(Application.id == scope_id)
            )
        elif scope == "project":
            from .project import Project
            result = await db.execute(
                sa_select(Project.id).where(Project.id == scope_id)
            )
        elif scope == "personal":
            from .user import User
            result = await db.execute(
                sa_select(User.id).where(User.id == scope_id)
            )
        else:
            return False

        return result.scalar_one_or_none() is not None

    def __repr__(self) -> str:
        """String representation of ImportJob."""
        return (
            f"<ImportJob(id={self.id}, file_name={self.file_name}, "
            f"status={self.status})>"
        )

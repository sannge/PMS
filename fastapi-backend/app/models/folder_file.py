"""FolderFile SQLAlchemy model for uploaded files within document folders.

FolderFiles store file metadata and extraction results for files uploaded
into the knowledge base folder hierarchy. Each file belongs to exactly one
scope (application, project, or personal/user) enforced by a CHECK
constraint, mirroring the Documents and DocumentFolders pattern. Supports
soft delete via deleted_at and optimistic concurrency via row_version.
"""

import uuid
from typing import TYPE_CHECKING, List

from ..utils.timezone import utc_now

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .document_chunk import DocumentChunk
    from .document_folder import DocumentFolder
    from .user import User


class FolderFile(Base):
    """
    FolderFile model representing an uploaded file in a knowledge base folder.

    Files are uploaded into document folders and can have their text content
    extracted for search and AI embedding. Each file belongs to exactly one
    scope: application, project, or personal (user). Content extraction
    runs asynchronously via background worker jobs.

    TODO(DA-ARCH-4): When a file is moved across scopes (e.g. from one
    application's folder to another), the associated DocumentChunks retain
    the original scope FKs (application_id/project_id/user_id). The
    update_file router endpoint must migrate chunk scope FKs when the
    file's scope changes.

    Attributes:
        id: Unique identifier (UUID)
        folder_id: FK to DocumentFolder (optional - nullable for unfiled scope-root files)
        application_id: FK to Applications (scope - exactly one scope FK must be set)
        project_id: FK to Projects (scope)
        user_id: FK to Users (personal scope)
        original_name: Original filename as uploaded by the user
        display_name: Editable display name shown in the UI
        mime_type: MIME type of the file
        file_size: File size in bytes
        file_extension: File extension (e.g. "pdf", "docx")
        storage_bucket: MinIO bucket name where the file is stored
        storage_key: MinIO object key for the file
        thumbnail_key: MinIO object key for the thumbnail (nullable)
        extraction_status: Text extraction pipeline status
        extraction_error: Error message if extraction failed
        content_plain: Extracted plain text content for search
        extracted_metadata: JSONB metadata extracted from the file
        embedding_status: AI embedding sync status
        embedding_updated_at: When embeddings were last updated
        sha256_hash: SHA-256 hash of the file content for dedup
        sort_order: Position within folder
        created_by: FK to user who uploaded the file
        row_version: Optimistic concurrency version counter
        deleted_at: Soft delete timestamp (null = active)
        created_at: Timestamp when file was uploaded
        updated_at: Timestamp when file was last updated
    """

    __tablename__ = "FolderFiles"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Folder association (nullable — files can be unfiled at scope root)
    folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("DocumentFolders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    # File details
    original_name = Column(
        String(255),
        nullable=False,
    )

    display_name = Column(
        String(255),
        nullable=False,
    )

    mime_type = Column(
        String(255),
        nullable=False,
        default="application/octet-stream",
    )

    file_size = Column(
        BigInteger,
        nullable=False,
    )

    file_extension = Column(
        String(20),
        nullable=False,
    )

    # Storage location
    storage_bucket = Column(
        String(100),
        nullable=False,
    )

    storage_key = Column(
        String(500),
        nullable=False,
    )

    thumbnail_key = Column(
        String(500),
        nullable=True,
    )

    # Content extraction
    extraction_status = Column(
        String(12),
        nullable=False,
        default="pending",
    )

    extraction_error = Column(
        Text,
        nullable=True,
    )

    content_plain = Column(
        Text,
        nullable=True,
    )

    extracted_metadata = Column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # AI embedding
    embedding_status = Column(
        String(8),
        nullable=False,
        default="none",
    )

    embedding_updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Deduplication
    sha256_hash = Column(
        String(64),
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
    )

    # Concurrency
    row_version = Column(
        Integer,
        nullable=False,
        default=1,
    )

    # Soft delete
    deleted_at = Column(
        DateTime(timezone=True),
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

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_folder_files_exactly_one_scope",
        ),
        CheckConstraint(
            "extraction_status IN ('pending', 'processing', 'completed', 'failed', 'unsupported')",
            name="ck_folder_files_extraction_status",
        ),
        CheckConstraint(
            "embedding_status IN ('none', 'stale', 'syncing', 'synced', 'failed')",
            name="ck_folder_files_embedding_status",
        ),
        # Unique display_name per folder (case-insensitive, excludes soft-deleted).
        # skip_autogenerate prevents Alembic from re-emitting the functional index
        # on every autogenerate run; the actual migration uses raw SQL.
        Index(
            "uq_folder_files_name",
            "folder_id",
            func.lower(Column("display_name")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        # Partial unique indexes for unfiled files (folder_id IS NULL).
        # PostgreSQL treats NULL != NULL so (folder_id, lower(display_name))
        # does not prevent duplicates among unfiled files in the same scope.
        Index(
            "uq_folder_files_unfiled_app_name",
            "application_id",
            func.lower(Column("display_name")),
            unique=True,
            postgresql_where=text("folder_id IS NULL AND deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        Index(
            "uq_folder_files_unfiled_proj_name",
            "project_id",
            func.lower(Column("display_name")),
            unique=True,
            postgresql_where=text("folder_id IS NULL AND deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        Index(
            "uq_folder_files_unfiled_user_name",
            "user_id",
            func.lower(Column("display_name")),
            unique=True,
            postgresql_where=text("folder_id IS NULL AND deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        # Composite indexes for unfiled file listing queries.
        Index(
            "ix_folder_files_unfiled_app_sort",
            "application_id",
            "sort_order",
            postgresql_where=text("folder_id IS NULL AND deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        Index(
            "ix_folder_files_unfiled_proj_sort",
            "project_id",
            "sort_order",
            postgresql_where=text("folder_id IS NULL AND deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        Index(
            "ix_folder_files_unfiled_user_sort",
            "user_id",
            "sort_order",
            postgresql_where=text("folder_id IS NULL AND deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        # Composite index for list_files query: WHERE deleted_at IS NULL AND folder_id = ? ORDER BY sort_order
        Index(
            "ix_folder_files_folder_sort",
            "folder_id",
            "sort_order",
            postgresql_where=text("deleted_at IS NULL"),
            info={"skip_autogenerate": True},
        ),
        # Partial index for batch embedding jobs on stale/none/failed files.
        # NOTE: This index is created for a planned batch_embed_stale_files cron job.
        # Currently unused — remove if the batch job is not implemented by the next migration cleanup.
        Index(
            "ix_folder_files_embedding_stale",
            "embedding_status",
            postgresql_where=text("deleted_at IS NULL AND embedding_status IN ('stale', 'none', 'failed')"),
            info={"skip_autogenerate": True},
        ),
    )

    # Relationships (default lazy loading -- use selectinload/joinedload at query site)
    folder = relationship(
        "DocumentFolder",
        back_populates="files",
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
    )

    chunks: List["DocumentChunk"] = relationship(
        "DocumentChunk",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation of FolderFile."""
        return f"<FolderFile(id={self.id}, display_name={self.display_name[:30] if self.display_name else ''})>"

"""Add FolderFiles table and extend DocumentChunks for file-based chunks.

Creates the FolderFiles table for storing uploaded files within document
folders, with the same three-scope constraint pattern as Documents and
DocumentFolders. Also extends DocumentChunks to support file-sourced
chunks alongside document-sourced chunks.

Revision ID: 20260311_add_folder_files
Revises: 20260310_fix_seed_drift
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260311_add_folder_files"
down_revision = "20260310_fix_seed_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ========================================================================
    # 1. Create FolderFiles table
    # ========================================================================
    op.create_table(
        "FolderFiles",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("folder_id", UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(255),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_extension", sa.String(20), nullable=False),
        sa.Column("storage_bucket", sa.String(100), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("thumbnail_key", sa.String(500), nullable=True),
        sa.Column(
            "extraction_status",
            sa.String(12),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("content_plain", sa.Text(), nullable=True),
        sa.Column("extracted_metadata", JSONB(), server_default="{}"),
        sa.Column(
            "embedding_status",
            sa.String(8),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "embedding_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("sha256_hash", sa.String(64), nullable=True),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "row_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Primary key
        sa.PrimaryKeyConstraint("id"),
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["folder_id"], ["DocumentFolders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["Applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["Projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["Users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["Users.id"], ondelete="SET NULL"
        ),
        # Constraints
        sa.CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_folder_files_exactly_one_scope",
        ),
        sa.CheckConstraint(
            "extraction_status IN ('pending', 'processing', 'completed',"
            " 'failed', 'unsupported')",
            name="ck_folder_files_extraction_status",
        ),
        sa.CheckConstraint(
            "embedding_status IN ('none', 'stale', 'syncing', 'synced',"
            " 'failed')",
            name="ck_folder_files_embedding_status",
        ),
    )

    # ========================================================================
    # 2. Create indexes on FolderFiles
    # ========================================================================

    # Unique display_name per folder (case-insensitive, excludes soft-deleted)
    op.execute(
        'CREATE UNIQUE INDEX uq_folder_files_name '
        'ON "FolderFiles" (folder_id, LOWER(display_name)) '
        'WHERE deleted_at IS NULL'
    )

    # FK lookup indexes
    op.create_index(
        "ix_folder_files_folder_id", "FolderFiles", ["folder_id"]
    )
    op.create_index(
        "ix_folder_files_application_id", "FolderFiles", ["application_id"]
    )
    op.create_index(
        "ix_folder_files_project_id", "FolderFiles", ["project_id"]
    )
    op.create_index(
        "ix_folder_files_user_id", "FolderFiles", ["user_id"]
    )

    # Status and soft-delete indexes for background jobs and queries
    op.create_index(
        "ix_folder_files_extraction_status",
        "FolderFiles",
        ["extraction_status"],
    )
    op.create_index(
        "ix_folder_files_deleted_at", "FolderFiles", ["deleted_at"]
    )

    # ========================================================================
    # 3. Extend DocumentChunks for file-sourced chunks
    # ========================================================================

    # Add source_type column with backfill
    op.add_column(
        "DocumentChunks",
        sa.Column(
            "source_type",
            sa.String(10),
            nullable=False,
            server_default="document",
        ),
    )

    # Backfill existing rows (all current chunks are document-sourced)
    op.execute(
        """UPDATE "DocumentChunks" SET source_type = 'document' WHERE source_type IS NULL"""
    )

    # Add file_id FK column (nullable — only set for file-sourced chunks)
    op.add_column(
        "DocumentChunks",
        sa.Column("file_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_chunks_file_id",
        "DocumentChunks",
        "FolderFiles",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Make document_id nullable (file chunks have no document_id)
    op.alter_column(
        "DocumentChunks",
        "document_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )

    # Exactly one source: either document_id or file_id, not both, not neither
    op.create_check_constraint(
        "ck_chunks_exactly_one_source",
        "DocumentChunks",
        "(document_id IS NOT NULL AND file_id IS NULL)"
        " OR (document_id IS NULL AND file_id IS NOT NULL)",
    )

    # Partial unique index for file-sourced chunks (mirrors idx_document_chunks_doc_idx)
    op.execute(
        'CREATE UNIQUE INDEX idx_document_chunks_file_idx '
        'ON "DocumentChunks" (file_id, chunk_index) '
        'WHERE file_id IS NOT NULL'
    )


def downgrade() -> None:
    # ========================================================================
    # 1. Revert DocumentChunks extensions
    # ========================================================================

    # Drop the file chunk unique index
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_file_idx')

    # Drop the exactly-one-source check constraint
    op.drop_constraint(
        "ck_chunks_exactly_one_source", "DocumentChunks", type_="check"
    )

    # Delete file-sourced chunks (document_id IS NULL) so ALTER NOT NULL succeeds
    op.execute(
        'DELETE FROM "DocumentChunks" WHERE document_id IS NULL'
    )

    # Make document_id NOT NULL again
    op.alter_column(
        "DocumentChunks",
        "document_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )

    # Drop file_id FK and column
    op.drop_constraint(
        "fk_document_chunks_file_id", "DocumentChunks", type_="foreignkey"
    )
    op.drop_column("DocumentChunks", "file_id")

    # Drop source_type column
    op.drop_column("DocumentChunks", "source_type")

    # ========================================================================
    # 2. Drop FolderFiles table (indexes are dropped implicitly via CASCADE)
    # ========================================================================
    op.execute('DROP INDEX IF EXISTS uq_folder_files_name')
    op.drop_table("FolderFiles")

"""Make FolderFiles.folder_id nullable for unfiled uploads.

Files can now exist at scope root without belonging to a folder,
mirroring how Documents support folder_id=NULL (unfiled).

Revision ID: 20260313_nullable_folder
Revises: 20260311_add_folder_files
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260313_nullable_folder"
down_revision = "20260311_add_folder_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make folder_id nullable
    op.alter_column(
        "FolderFiles",
        "folder_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )

    # Change FK ondelete from CASCADE to SET NULL (don't delete files when folder is deleted)
    op.drop_constraint("FolderFiles_folder_id_fkey", "FolderFiles", type_="foreignkey")
    op.create_foreign_key(
        "FolderFiles_folder_id_fkey",
        "FolderFiles",
        "DocumentFolders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # Partial unique indexes for unfiled files (folder_id IS NULL).
    # PostgreSQL treats NULL != NULL so the existing uq_folder_files_name
    # index on (folder_id, lower(display_name)) does not prevent
    # duplicate display_names among unfiled files in the same scope.
    # ------------------------------------------------------------------
    op.execute(
        "CREATE UNIQUE INDEX uq_folder_files_unfiled_app_name "
        'ON "FolderFiles" (application_id, LOWER(display_name)) '
        "WHERE folder_id IS NULL AND deleted_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_folder_files_unfiled_proj_name "
        'ON "FolderFiles" (project_id, LOWER(display_name)) '
        "WHERE folder_id IS NULL AND deleted_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_folder_files_unfiled_user_name "
        'ON "FolderFiles" (user_id, LOWER(display_name)) '
        "WHERE folder_id IS NULL AND deleted_at IS NULL"
    )

    # ------------------------------------------------------------------
    # Composite indexes for unfiled file listing queries (sorted by
    # sort_order within each scope).
    # ------------------------------------------------------------------
    op.execute(
        "CREATE INDEX ix_folder_files_unfiled_app_sort "
        'ON "FolderFiles" (application_id, sort_order) '
        "WHERE folder_id IS NULL AND deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_folder_files_unfiled_proj_sort "
        'ON "FolderFiles" (project_id, sort_order) '
        "WHERE folder_id IS NULL AND deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_folder_files_unfiled_user_sort "
        'ON "FolderFiles" (user_id, sort_order) '
        "WHERE folder_id IS NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    # Drop partial unique indexes for unfiled files
    op.execute("DROP INDEX IF EXISTS uq_folder_files_unfiled_app_name")
    op.execute("DROP INDEX IF EXISTS uq_folder_files_unfiled_proj_name")
    op.execute("DROP INDEX IF EXISTS uq_folder_files_unfiled_user_name")

    # Drop composite indexes for unfiled file queries
    op.execute("DROP INDEX IF EXISTS ix_folder_files_unfiled_app_sort")
    op.execute("DROP INDEX IF EXISTS ix_folder_files_unfiled_proj_sort")
    op.execute("DROP INDEX IF EXISTS ix_folder_files_unfiled_user_sort")

    # WARNING: Deleting unfiled files - this is destructive and irreversible.
    # Any FolderFiles with folder_id IS NULL will be permanently removed
    # because the NOT NULL constraint on folder_id cannot be restored
    # while NULL rows exist.
    import sys

    print("WARNING: Downgrade will DELETE all unfiled FolderFiles (folder_id IS NULL)", file=sys.stderr)
    op.execute('DELETE FROM "FolderFiles" WHERE folder_id IS NULL')

    # Restore FK ondelete to CASCADE
    op.drop_constraint("FolderFiles_folder_id_fkey", "FolderFiles", type_="foreignkey")
    op.create_foreign_key(
        "FolderFiles_folder_id_fkey",
        "FolderFiles",
        "DocumentFolders",
        ["folder_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Make folder_id non-nullable again
    op.alter_column(
        "FolderFiles",
        "folder_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )

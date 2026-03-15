"""Add composite and partial indexes to FolderFiles.

Adds:
- ix_folder_files_folder_sort: composite index on (folder_id, sort_order)
  WHERE deleted_at IS NULL for the list_files query.
- ix_folder_files_embedding_stale: partial index on (embedding_status)
  WHERE deleted_at IS NULL AND embedding_status IN ('stale', 'none', 'failed')
  for batch embedding jobs.

Revision ID: 20260314_folder_file_idx
Revises: 20260314_doc_embed_failed
Create Date: 2026-03-14
"""
from alembic import op

revision = "20260314_folder_file_idx"
down_revision = "20260314_doc_embed_failed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_folder_files_folder_sort '
        'ON "FolderFiles" (folder_id, sort_order) '
        'WHERE deleted_at IS NULL'
    )
    op.execute(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_folder_files_embedding_stale '
        'ON "FolderFiles" (embedding_status) '
        "WHERE deleted_at IS NULL AND embedding_status IN ('stale', 'none', 'failed')"
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_folder_files_embedding_stale')
    op.execute('DROP INDEX IF EXISTS ix_folder_files_folder_sort')

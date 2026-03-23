"""Add GIN trigram index on projects.name for fast ILIKE search.

The pg_trgm extension was already enabled in 20260225_add_pgvector_pgtrgm.py.
This migration adds a GIN index using gin_trgm_ops on lower(name) to support
fast ILIKE searches without full table scans.

Revision ID: 20260314_proj_name_trgm
Revises: 20260314_folder_file_idx
Create Date: 2026-03-14
"""

from alembic import op

revision = "20260314_proj_name_trgm"
down_revision = "20260314_folder_file_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CONCURRENTLY requires running outside a transaction
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_projects_name_trgm "
        'ON "Projects" USING gin (lower(name) gin_trgm_ops)'
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_projects_name_trgm")

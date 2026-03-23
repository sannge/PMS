"""Add embedding_status column to Documents.

Revision ID: 20260302_add_embedding_status
Revises: 20260301_add_chunk_type
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260302_add_embedding_status"
down_revision = "20260301_chunk_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "Documents",
        sa.Column(
            "embedding_status",
            sa.String(8),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_check_constraint(
        "ck_documents_embedding_status",
        "Documents",
        "embedding_status IN ('none', 'stale', 'syncing', 'synced')",
    )
    # Backfill existing rows
    op.execute("UPDATE \"Documents\" SET embedding_status = 'synced' WHERE embedding_updated_at IS NOT NULL")
    op.execute(
        "UPDATE \"Documents\" SET embedding_status = 'stale' WHERE embedding_updated_at IS NULL AND content_json IS NOT NULL"
    )
    op.create_index("ix_documents_embedding_status", "Documents", ["embedding_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_embedding_status", table_name="Documents")
    op.drop_constraint("ck_documents_embedding_status", "Documents", type_="check")
    op.drop_column("Documents", "embedding_status")

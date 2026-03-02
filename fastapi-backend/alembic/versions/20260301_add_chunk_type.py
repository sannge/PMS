"""Add chunk_type column to DocumentChunks.

Adds a `chunk_type` VARCHAR(20) column (default 'text') to distinguish
text chunks from image-described chunks. Existing rows with chunk_text
starting with '[Image' are backfilled as 'image'.

Revision ID: 20260301_chunk_type
Revises: 20260228_perf_indexes
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260301_chunk_type"
down_revision = "20260228_oauth_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column with server default so existing rows get 'text'
    op.add_column(
        "DocumentChunks",
        sa.Column(
            "chunk_type",
            sa.String(20),
            nullable=False,
            server_default="text",
        ),
    )

    # Backfill: rows whose chunk_text starts with '[Image' are image chunks
    op.execute(
        """
        UPDATE "DocumentChunks"
        SET chunk_type = 'image'
        WHERE chunk_text LIKE '[Image%'
        """
    )

    # Drop the server default after backfill (app code sets it explicitly)
    op.alter_column("DocumentChunks", "chunk_type", server_default=None)


def downgrade() -> None:
    op.drop_column("DocumentChunks", "chunk_type")

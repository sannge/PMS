"""add generated tsvector column for PostgreSQL FTS fallback

Revision ID: d3e4f5g6h7i8
Revises: c2d3e4f5g6h7
Create Date: 2026-02-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d3e4f5g6h7i8"
down_revision: Union[str, None] = "c2d3e4f5g6h7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add generated tsvector column and GIN index for full-text search fallback."""
    op.execute("""
        ALTER TABLE "Documents" ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(content_plain, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX idx_documents_search_vector
        ON "Documents" USING GIN(search_vector)
    """)


def downgrade() -> None:
    """Remove search_vector column and GIN index."""
    op.execute('DROP INDEX IF EXISTS idx_documents_search_vector')
    op.execute('ALTER TABLE "Documents" DROP COLUMN IF EXISTS search_vector')

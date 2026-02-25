"""Add pgvector and pg_trgm extensions.

Enables PostgreSQL extensions required for Phase 2 (Vector Embeddings):
- vector: pgvector for embedding storage and similarity search
- pg_trgm: trigram-based fuzzy text matching on document titles

Revision ID: 20260225_pgvector_ext
Revises: 20260224_ai_config
Create Date: 2026-02-25
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260225_pgvector_ext"
down_revision: Union[str, None] = "20260224_ai_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable pgvector and pg_trgm extensions."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    """Remove pg_trgm and pgvector extensions."""
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")

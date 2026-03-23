"""Drop Knowledge Graph column from Documents.

Phase 3 (Knowledge Graph) has been replaced by Phase 3.1 (Agent SQL Access).
This migration removes the graph_ingested_at tracking column that was added
in the document chunks migration.

Revision ID: 20260226_drop_kg
Revises: 20260225_doc_chunks
Create Date: 2026-02-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260226_drop_kg"
down_revision: Union[str, None] = "20260225_doc_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop graph_ingested_at column from Documents."""
    op.drop_column("Documents", "graph_ingested_at")


def downgrade() -> None:
    """Re-add graph_ingested_at column to Documents."""
    op.add_column(
        "Documents",
        sa.Column("graph_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )

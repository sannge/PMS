"""Add partial index on Tasks.completed_at for dashboard queries

Revision ID: dash_completed_idx
Revises: d3e4f5g6h7i8
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "dash_completed_idx"
down_revision: Union[str, None] = "d3e4f5g6h7i8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction
    op.execute("COMMIT")
    op.execute(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_Tasks_completed_at_partial '
        'ON "Tasks" (completed_at) WHERE completed_at IS NOT NULL'
    )


def downgrade() -> None:
    op.execute("COMMIT")
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS ix_Tasks_completed_at_partial')

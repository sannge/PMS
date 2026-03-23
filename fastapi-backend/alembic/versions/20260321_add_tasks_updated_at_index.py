"""Add composite index on Tasks(project_id, updated_at DESC) for pagination.

This index accelerates the common list_tasks query which orders by updated_at
DESC and filters by project_id, with a partial index excluding archived tasks.

Revision ID: 20260321_tasks_updated_idx
Revises: 20260320_backfill_completed_at
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa

from sqlalchemy import text

from alembic import op

revision: str = "20260321_tasks_updated_idx"
down_revision: Union[str, None] = "20260320_backfill_completed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard: skip if Tasks table doesn't exist (fresh/empty database)
    conn = op.get_bind()
    table_exists = conn.execute(
        text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'Tasks'
            )
        """)
    ).scalar()
    if not table_exists:
        return

    op.create_index(
        "ix_tasks_project_updated_at",
        "Tasks",
        ["project_id", sa.text("updated_at DESC")],
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_project_updated_at", table_name="Tasks")

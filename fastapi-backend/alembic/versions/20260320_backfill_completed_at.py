"""Backfill completed_at for Done tasks that have NULL completed_at.

The original migration (20260126_add_task_completed_at) had a bug in
its backfill query: it referenced a non-existent 'status' column
instead of joining via task_status_id → TaskStatuses. This left Done
tasks with completed_at = NULL, which prevents the auto-archive system
from ever archiving them (the archive query requires completed_at IS
NOT NULL).

Additionally, the AI agent's update_task_status tool was not setting
completed_at when moving tasks to Done, creating more NULL rows.

This migration fixes both issues by backfilling completed_at = updated_at
for all Done tasks where completed_at is still NULL.

Revision ID: 20260320_backfill_completed_at
Revises: 20260315_audit_indexes
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260320_backfill_completed_at"
down_revision: Union[str, None] = "20260315_audit_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill completed_at for Done tasks missing it."""
    op.execute("""
        UPDATE "Tasks" t
        SET completed_at = t.updated_at
        FROM "TaskStatuses" ts
        WHERE t.task_status_id = ts.id
          AND ts.category = 'Done'
          AND t.completed_at IS NULL
    """)


def downgrade() -> None:
    """No safe downgrade — cannot distinguish backfilled from legitimately set."""
    pass

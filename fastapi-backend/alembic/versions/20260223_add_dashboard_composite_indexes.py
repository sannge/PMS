"""Add composite indexes for dashboard queries.

Revision ID: 20260223_dashboard_indexes
Revises: dash_completed_idx
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260223_dashboard_indexes"
down_revision: Union[str, None] = "dash_completed_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction
    op.execute("COMMIT")

    # Composite index for active tasks query (assignee + project + archived)
    op.execute(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_Tasks_assignee_project_archived '
        'ON "Tasks" (assignee_id, project_id) '
        'WHERE archived_at IS NULL'
    )

    # Composite partial index for due date queries (overdue/upcoming)
    op.execute(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_Tasks_project_duedate '
        'ON "Tasks" (project_id, due_date) '
        'WHERE due_date IS NOT NULL AND archived_at IS NULL'
    )

    # Composite index for project health query ordering
    op.execute(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_Projects_app_updated '
        'ON "Projects" (application_id, updated_at DESC) '
        'WHERE archived_at IS NULL'
    )


def downgrade() -> None:
    op.execute("COMMIT")
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS ix_Tasks_assignee_project_archived')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS ix_Tasks_project_duedate')
    op.execute('DROP INDEX CONCURRENTLY IF EXISTS ix_Projects_app_updated')

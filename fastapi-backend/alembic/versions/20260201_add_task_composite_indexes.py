"""add composite indexes for task queries

Revision ID: b0c1d2e3f4g5
Revises: a9b8c7d6e5f4
Create Date: 2026-02-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4g5"
down_revision: Union[str, None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite indexes for common task query patterns."""
    # Most common query: list_tasks filters by (project_id, archived_at IS NULL)
    op.create_index(
        "ix_Tasks_project_archived",
        "Tasks",
        ["project_id", "archived_at"],
    )

    # Status + archived filter: tasks in a specific status that aren't archived
    op.create_index(
        "ix_Tasks_status_archived",
        "Tasks",
        ["task_status_id", "archived_at"],
    )


def downgrade() -> None:
    """Remove composite indexes."""
    op.drop_index("ix_Tasks_status_archived", table_name="Tasks")
    op.drop_index("ix_Tasks_project_archived", table_name="Tasks")

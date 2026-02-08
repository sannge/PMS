"""backfill task_status_id and make NOT NULL

Revision ID: f1a2b3c4d5e6
Revises: e3440224ad17
Create Date: 2026-02-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e3440224ad17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mapping from legacy status values to TaskStatus name values
LEGACY_STATUS_TO_STATUS_NAME = {
    "todo": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "issue": "Issue",
    "blocked": "Issue",
    "done": "Done",
}


def upgrade() -> None:
    conn = op.get_bind()

    # Get all projects that have TaskStatuses
    projects = conn.execute(
        sa.text('SELECT DISTINCT id FROM "Projects"')
    ).fetchall()

    for (project_id,) in projects:
        # Get TaskStatuses for this project
        statuses = conn.execute(
            sa.text('SELECT id, name FROM "TaskStatuses" WHERE project_id = :pid'),
            {"pid": project_id},
        ).fetchall()

        status_name_to_id = {name: sid for sid, name in statuses}

        if not status_name_to_id:
            # Project has no TaskStatuses — skip (shouldn't happen in normal data)
            continue

        # Backfill tasks that have NULL task_status_id
        tasks = conn.execute(
            sa.text(
                'SELECT id, status FROM "Tasks" '
                'WHERE project_id = :pid AND task_status_id IS NULL'
            ),
            {"pid": project_id},
        ).fetchall()

        for task_id, legacy_status in tasks:
            status_name = LEGACY_STATUS_TO_STATUS_NAME.get(legacy_status, "Todo")
            target_status_id = status_name_to_id.get(status_name)

            if target_status_id is None:
                # Fallback to Todo if mapping not found
                target_status_id = status_name_to_id.get("Todo")

            if target_status_id is not None:
                conn.execute(
                    sa.text(
                        'UPDATE "Tasks" SET task_status_id = :sid WHERE id = :tid'
                    ),
                    {"sid": target_status_id, "tid": task_id},
                )

    # Now make task_status_id NOT NULL
    op.alter_column(
        'Tasks',
        'task_status_id',
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
    )

    # Change ondelete from SET NULL to RESTRICT
    op.drop_constraint('Tasks_task_status_id_fkey', 'Tasks', type_='foreignkey')
    op.create_foreign_key(
        'Tasks_task_status_id_fkey',
        'Tasks',
        'TaskStatuses',
        ['task_status_id'],
        ['id'],
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    # Revert FK to SET NULL
    op.drop_constraint('Tasks_task_status_id_fkey', 'Tasks', type_='foreignkey')
    op.create_foreign_key(
        'Tasks_task_status_id_fkey',
        'Tasks',
        'TaskStatuses',
        ['task_status_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # Revert to nullable
    op.alter_column(
        'Tasks',
        'task_status_id',
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
    )

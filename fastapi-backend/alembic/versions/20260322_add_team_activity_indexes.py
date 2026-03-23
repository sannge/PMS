"""Add performance indexes for Team Activity feature.

Adds partial and composite indexes to support the aggregation queries
used by the Team Activity dashboard (Overview KPIs, trends, member stats):

- ix_tasks_completed_project: Task completion lookups by project, filtered
  to only completed tasks for KPI and trend queries.

- ix_tasks_overdue: Overdue task lookups — active (non-archived, non-completed)
  tasks filtered by project and due_date.

- ix_tasks_assignee_project: Task aggregation by assignee across projects,
  filtered to assigned tasks only.

- ix_documents_creator_app: Document activity by creator scoped to application,
  excluding soft-deleted documents.

- ix_documents_creator_project: Document activity by creator scoped to project,
  excluding soft-deleted documents where project_id is set.

- ix_comments_author_created: Comment activity by author with created_at for
  time-range aggregation, excluding soft-deleted comments.

Revision ID: 20260322_team_activity_indexes
Revises: 20260321_tasks_updated_idx
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260322_team_activity_indexes"
down_revision: Union[str, None] = "20260321_tasks_updated_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Task completion lookups (Overview KPIs, trends, member stats).
    # Covers: WHERE project_id = ? AND completed_at IS NOT NULL
    #         ORDER BY completed_at
    op.create_index(
        "ix_tasks_completed_project",
        "Tasks",
        ["project_id", "completed_at"],
        postgresql_where="completed_at IS NOT NULL",
    )

    # Overdue task lookups.
    # Covers: WHERE project_id = ? AND due_date < now()
    #         AND archived_at IS NULL AND completed_at IS NULL
    op.create_index(
        "ix_tasks_overdue",
        "Tasks",
        ["project_id", "due_date"],
        postgresql_where="archived_at IS NULL AND completed_at IS NULL",
    )

    # Task assignee aggregation.
    # Covers: WHERE assignee_id = ? GROUP BY project_id
    op.create_index(
        "ix_tasks_assignee_project",
        "Tasks",
        ["assignee_id", "project_id"],
        postgresql_where="assignee_id IS NOT NULL",
    )

    # Document activity by creator (application scope).
    # Covers: WHERE created_by = ? AND application_id = ?
    #         ORDER BY created_at
    op.create_index(
        "ix_documents_creator_app",
        "Documents",
        ["created_by", "application_id", "created_at"],
        postgresql_where="deleted_at IS NULL",
    )

    # Document activity by creator (project scope).
    # Covers: WHERE created_by = ? AND project_id = ?
    #         ORDER BY created_at
    op.create_index(
        "ix_documents_creator_project",
        "Documents",
        ["created_by", "project_id", "created_at"],
        postgresql_where="deleted_at IS NULL AND project_id IS NOT NULL",
    )

    # Comment activity by author.
    # Covers: WHERE author_id = ? AND created_at BETWEEN ? AND ?
    op.create_index(
        "ix_comments_author_created",
        "Comments",
        ["author_id", "created_at"],
        postgresql_where="is_deleted = false",
    )


def downgrade() -> None:
    op.drop_index("ix_comments_author_created", table_name="Comments")
    op.drop_index("ix_documents_creator_project", table_name="Documents")
    op.drop_index("ix_documents_creator_app", table_name="Documents")
    op.drop_index("ix_tasks_assignee_project", table_name="Tasks")
    op.drop_index("ix_tasks_overdue", table_name="Tasks")
    op.drop_index("ix_tasks_completed_project", table_name="Tasks")

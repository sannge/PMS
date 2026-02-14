"""recalculate all project task status aggregations

Revision ID: c2d3e4f5g6h7
Revises: b0c1d2e3f4g5
Create Date: 2026-02-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5g6h7"
down_revision: Union[str, None] = "b0c1d2e3f4g5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Recalculate all ProjectTaskStatusAgg rows from actual task data.

    This fixes stale aggregation counters caused by the legacy status migration.
    For each project, counts tasks by their TaskStatus name and updates the
    corresponding counter columns. Also updates the project's derived_status_id.
    """
    conn = op.get_bind()

    # Step 1: Recalculate all existing aggregation rows from actual task data.
    conn.execute(sa.text("""
        UPDATE "ProjectTaskStatusAgg" AS agg
        SET
            total_tasks = COALESCE(counts.total_tasks, 0),
            todo_tasks = COALESCE(counts.todo_tasks, 0),
            active_tasks = COALESCE(counts.active_tasks, 0),
            review_tasks = COALESCE(counts.review_tasks, 0),
            issue_tasks = COALESCE(counts.issue_tasks, 0),
            done_tasks = COALESCE(counts.done_tasks, 0),
            updated_at = NOW() AT TIME ZONE 'UTC'
        FROM (
            SELECT
                t.project_id,
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN ts.name = 'Todo' THEN 1 ELSE 0 END) AS todo_tasks,
                SUM(CASE WHEN ts.name = 'In Progress' THEN 1 ELSE 0 END) AS active_tasks,
                SUM(CASE WHEN ts.name = 'In Review' THEN 1 ELSE 0 END) AS review_tasks,
                SUM(CASE WHEN ts.name = 'Issue' THEN 1 ELSE 0 END) AS issue_tasks,
                SUM(CASE WHEN ts.name = 'Done' THEN 1 ELSE 0 END) AS done_tasks
            FROM "Tasks" t
            INNER JOIN "TaskStatuses" ts ON t.task_status_id = ts.id
            WHERE t.archived_at IS NULL
            GROUP BY t.project_id
        ) counts
        WHERE agg.project_id = counts.project_id
    """))

    # Step 1b: Zero out aggregations for projects with no active tasks
    conn.execute(sa.text("""
        UPDATE "ProjectTaskStatusAgg" AS agg
        SET
            total_tasks = 0,
            todo_tasks = 0,
            active_tasks = 0,
            review_tasks = 0,
            issue_tasks = 0,
            done_tasks = 0,
            updated_at = NOW() AT TIME ZONE 'UTC'
        WHERE NOT EXISTS (
            SELECT 1 FROM "Tasks" t
            WHERE t.project_id = agg.project_id
              AND t.archived_at IS NULL
        )
    """))

    # Step 2: Insert aggregation rows for projects that don't have one yet
    conn.execute(sa.text("""
        INSERT INTO "ProjectTaskStatusAgg"
            (project_id, total_tasks, todo_tasks, active_tasks, review_tasks, issue_tasks, done_tasks, updated_at)
        SELECT
            p.id,
            COALESCE(counts.total_tasks, 0),
            COALESCE(counts.todo_tasks, 0),
            COALESCE(counts.active_tasks, 0),
            COALESCE(counts.review_tasks, 0),
            COALESCE(counts.issue_tasks, 0),
            COALESCE(counts.done_tasks, 0),
            NOW() AT TIME ZONE 'UTC'
        FROM "Projects" p
        LEFT JOIN "ProjectTaskStatusAgg" agg ON p.id = agg.project_id
        LEFT JOIN (
            SELECT
                t.project_id,
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN ts.name = 'Todo' THEN 1 ELSE 0 END) AS todo_tasks,
                SUM(CASE WHEN ts.name = 'In Progress' THEN 1 ELSE 0 END) AS active_tasks,
                SUM(CASE WHEN ts.name = 'In Review' THEN 1 ELSE 0 END) AS review_tasks,
                SUM(CASE WHEN ts.name = 'Issue' THEN 1 ELSE 0 END) AS issue_tasks,
                SUM(CASE WHEN ts.name = 'Done' THEN 1 ELSE 0 END) AS done_tasks
            FROM "Tasks" t
            INNER JOIN "TaskStatuses" ts ON t.task_status_id = ts.id
            WHERE t.archived_at IS NULL
            GROUP BY t.project_id
        ) counts ON p.id = counts.project_id
        WHERE agg.project_id IS NULL
          AND p.archived_at IS NULL
    """))

    # Step 3: Update derived_status_id for all projects based on recalculated aggregation.
    # Priority: Done > Issue > In Progress > Todo

    # 3a: Projects where all tasks are done
    conn.execute(sa.text("""
        UPDATE "Projects" AS p
        SET derived_status_id = ts.id
        FROM "ProjectTaskStatusAgg" agg, "TaskStatuses" ts
        WHERE agg.project_id = p.id
          AND ts.project_id = p.id
          AND ts.name = 'Done'
          AND agg.total_tasks > 0
          AND agg.done_tasks = agg.total_tasks
    """))

    # 3b: Projects with any issue tasks (and not all done)
    conn.execute(sa.text("""
        UPDATE "Projects" AS p
        SET derived_status_id = ts.id
        FROM "ProjectTaskStatusAgg" agg, "TaskStatuses" ts
        WHERE agg.project_id = p.id
          AND ts.project_id = p.id
          AND ts.name = 'Issue'
          AND agg.issue_tasks > 0
          AND NOT (agg.total_tasks > 0 AND agg.done_tasks = agg.total_tasks)
    """))

    # 3c: Projects with active or review tasks (no issues, not all done)
    conn.execute(sa.text("""
        UPDATE "Projects" AS p
        SET derived_status_id = ts.id
        FROM "ProjectTaskStatusAgg" agg, "TaskStatuses" ts
        WHERE agg.project_id = p.id
          AND ts.project_id = p.id
          AND ts.name = 'In Progress'
          AND (agg.active_tasks > 0 OR agg.review_tasks > 0)
          AND agg.issue_tasks = 0
          AND NOT (agg.total_tasks > 0 AND agg.done_tasks = agg.total_tasks)
    """))

    # 3d: Projects with only todo tasks (or empty)
    conn.execute(sa.text("""
        UPDATE "Projects" AS p
        SET derived_status_id = ts.id
        FROM "ProjectTaskStatusAgg" agg, "TaskStatuses" ts
        WHERE agg.project_id = p.id
          AND ts.project_id = p.id
          AND ts.name = 'Todo'
          AND agg.active_tasks = 0
          AND agg.review_tasks = 0
          AND agg.issue_tasks = 0
          AND NOT (agg.total_tasks > 0 AND agg.done_tasks = agg.total_tasks)
    """))


def downgrade() -> None:
    """No downgrade needed - this is a data-only recalculation."""
    pass

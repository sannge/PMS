"""Project-domain tools for Blair AI agent.

Tools for listing projects, inspecting details, members, timelines,
and finding overdue tasks.  All tools are read-only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ....models.project import Project
from ....models.project_member import ProjectMember
from ....models.project_task_status_agg import ProjectTaskStatusAgg
from ....models.task import Task
from ....models.task_status import TaskStatus
from ....models.user import User
from .context import _get_ctx
from .helpers import (
    _days_overdue,
    _format_date,
    _get_tool_session,
    _resolve_application,
    _resolve_project,
    _truncate,
)

logger = logging.getLogger(__name__)


@tool
async def list_projects(
    app: str,
    status: str | None = None,
    include_archived: bool = False,
) -> str:
    """List projects in an application with completion percentage and details.

    Use this when the user asks about project status or wants an overview
    of projects within an application.

    Args:
        app: Application UUID or name (partial match supported).
        status: Optional filter -- "active", "completed", or "archived".
        include_archived: If true, also show archived projects. Defaults to false.
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_application(app, db)
            if error:
                return error
            app_id = resolved_id
            app_uuid = UUID(app_id)  # type: ignore[arg-type]

            query = (
                select(Project)
                .where(Project.application_id == app_uuid)
                .options(selectinload(Project.derived_status))
                .order_by(Project.name)
            )

            # Apply status filter (only join ProjectTaskStatusAgg when needed)
            if status == "completed":
                query = query.outerjoin(
                    ProjectTaskStatusAgg,
                    ProjectTaskStatusAgg.project_id == Project.id,
                ).where(
                    ProjectTaskStatusAgg.total_tasks == ProjectTaskStatusAgg.done_tasks,
                )
            elif status == "archived":
                query = query.where(Project.archived_at.isnot(None))
            elif status == "active":
                query = query.where(Project.archived_at.is_(None))
            elif not include_archived:
                query = query.where(Project.archived_at.is_(None))

            result = await db.execute(query)
            projects = result.scalars().unique().all()

            if not projects:
                return "No projects found in this application."

            # Fetch aggregation data in one query
            agg_result = await db.execute(
                select(ProjectTaskStatusAgg).where(
                    ProjectTaskStatusAgg.project_id.in_([p.id for p in projects])
                )
            )
            agg_map: dict[UUID, ProjectTaskStatusAgg] = {
                a.project_id: a for a in agg_result.scalars().all()
            }

            # Fetch member counts
            mem_counts = await db.execute(
                select(
                    ProjectMember.project_id,
                    func.count(ProjectMember.id).label("cnt"),
                )
                .where(ProjectMember.project_id.in_([p.id for p in projects]))
                .group_by(ProjectMember.project_id)
            )
            mem_map = {str(row.project_id): row.cnt for row in mem_counts.all()}

        # Format
        lines: list[str] = []
        lines.append(
            "| Project | Key | Status | Tasks (done/total) | % | Members | Due | Created |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")

        for proj in projects:
            agg = agg_map.get(proj.id)
            total = agg.total_tasks if agg else 0
            done = agg.done_tasks if agg else 0
            pct = int((done / total) * 100) if total > 0 else 0

            derived = proj.derived_status
            status_name = derived.name if derived else "No tasks"
            mem_count = mem_map.get(str(proj.id), 0)

            lines.append(
                f"| {proj.name} | {proj.key} | {status_name} | "
                f"{done}/{total} | {pct}% | {mem_count} | "
                f"{_format_date(proj.due_date)} | {_format_date(proj.created_at)} |"
            )

        lines.append(f"\n*{len(projects)} project(s) found.*")
        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning("list_projects failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving projects. Please try again."


@tool
async def get_project_details(project: str) -> str:
    """Get detailed information about a specific project.

    Returns name, key, description, members, status breakdown, recent
    tasks, and document count.

    Args:
        project: Project UUID or name (partial match supported).
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_project(project, db)
            if error:
                return error
            proj_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # Project
            result = await db.execute(
                select(Project)
                .options(selectinload(Project.derived_status))
                .where(Project.id == proj_uuid)
            )
            proj = result.scalar_one_or_none()
            if not proj:
                return f"Project '{project}' not found."

            # Aggregation
            agg_result = await db.execute(
                select(ProjectTaskStatusAgg).where(
                    ProjectTaskStatusAgg.project_id == proj_uuid
                )
            )
            agg = agg_result.scalar_one_or_none()

            # Members
            mem_result = await db.execute(
                select(ProjectMember)
                .options(selectinload(ProjectMember.user))
                .where(ProjectMember.project_id == proj_uuid)
            )
            members = mem_result.scalars().all()

            # Recent 5 tasks
            task_result = await db.execute(
                select(Task)
                .options(
                    selectinload(Task.task_status),
                    selectinload(Task.assignee),
                )
                .where(
                    Task.project_id == proj_uuid,
                    Task.archived_at.is_(None),
                )
                .order_by(Task.updated_at.desc())
                .limit(5)
            )
            recent_tasks = task_result.scalars().all()

            # Document count
            from ....models.document import Document

            doc_count_result = await db.execute(
                select(func.count(Document.id)).where(
                    Document.project_id == proj_uuid,
                    Document.deleted_at.is_(None),
                )
            )
            doc_count = doc_count_result.scalar() or 0

        # Format
        total = agg.total_tasks if agg else 0
        done = agg.done_tasks if agg else 0
        pct = int((done / total) * 100) if total > 0 else 0
        derived = proj.derived_status
        status_name = derived.name if derived else "No tasks"

        lines = [
            f"## {proj.name} ({proj.key})",
            "",
            f"- **ID**: `{proj.id}`",
            f"- **Description**: {proj.description or '\u2014'}",
            f"- **Status**: {status_name} ({pct}% complete)",
            f"- **Due Date**: {_format_date(proj.due_date)}",
            f"- **Created**: {_format_date(proj.created_at)}",
            f"- **Documents**: {doc_count}",
            "",
        ]

        # Status breakdown
        if agg:
            lines.append("### Task Breakdown")
            lines.append(
                f"- Todo: {agg.todo_tasks} | In Progress: {agg.active_tasks} "
                f"| In Review: {agg.review_tasks} | Issue: {agg.issue_tasks} "
                f"| Done: {agg.done_tasks} | **Total: {agg.total_tasks}**"
            )
            lines.append("")

        # Members
        lines.append(f"### Members ({len(members)})")
        if members:
            lines.append("| Name | Email | Role |")
            lines.append("| --- | --- | --- |")
            for m in members:
                user = m.user
                name = user.display_name or "\u2014" if user else "\u2014"
                email = user.email if user else "\u2014"
                lines.append(f"| {name} | {email} | {m.role} |")
        lines.append("")

        # Recent tasks
        if recent_tasks:
            lines.append("### Recent Tasks (last 5 updated)")
            lines.append("| Key | Title | Status | Assignee | Updated |")
            lines.append("| --- | --- | --- | --- | --- |")
            for t in recent_tasks:
                assignee = t.assignee.display_name if t.assignee else "Unassigned"
                st = t.task_status.name if t.task_status else "\u2014"
                lines.append(
                    f"| {t.task_key} | {t.title} | {st} | "
                    f"{assignee} | {_format_date(t.updated_at)} |"
                )
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning(
            "get_project_details failed: %s: %s", type(exc).__name__, exc
        )
        return "Error retrieving project details. Please try again."


@tool
async def get_project_members(project: str) -> str:
    """Get members of a project with their roles and task statistics.

    Args:
        project: Project UUID or name (partial match supported).
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_project(project, db)
            if error:
                return error
            proj_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # Project name
            proj_result = await db.execute(
                select(Project.name).where(Project.id == proj_uuid)
            )
            proj_name = proj_result.scalar_one_or_none()
            if not proj_name:
                return f"Project '{project}' not found."

            # Members
            mem_result = await db.execute(
                select(ProjectMember)
                .options(selectinload(ProjectMember.user))
                .where(ProjectMember.project_id == proj_uuid)
            )
            members = mem_result.scalars().all()

            if not members:
                return f"No members found for project '{proj_name}'."

            # Task counts per assignee
            task_stats = await db.execute(
                select(
                    Task.assignee_id,
                    func.count(Task.id).label("total"),
                    func.count(Task.id).filter(
                        TaskStatus.category == "Done"
                    ).label("done"),
                )
                .join(TaskStatus, Task.task_status_id == TaskStatus.id)
                .where(
                    Task.project_id == proj_uuid,
                    Task.archived_at.is_(None),
                )
                .group_by(Task.assignee_id)
            )
            stats_map: dict[str, tuple[int, int]] = {}
            for row in task_stats.all():
                if row.assignee_id:
                    stats_map[str(row.assignee_id)] = (row.total, row.done)

        # Format
        lines = [
            f"## Members of {proj_name}",
            "",
            f"*{len(members)} member(s)*",
            "",
            "| Name | Email | Role | Tasks | Completion |",
            "| --- | --- | --- | --- | --- |",
        ]

        for m in members:
            user = m.user
            name = user.display_name or "\u2014" if user else "\u2014"
            email = user.email if user else "\u2014"
            uid = str(m.user_id)
            total, done = stats_map.get(uid, (0, 0))
            pct = int((done / total) * 100) if total > 0 else 0
            lines.append(
                f"| {name} | {email} | {m.role} | "
                f"{done}/{total} | {pct}% |"
            )

        lines.append("")
        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning(
            "get_project_members failed: %s: %s", type(exc).__name__, exc
        )
        return "Error retrieving project members. Please try again."


@tool
async def get_project_timeline(project: str) -> str:
    """Get a timeline view of recent activity in a project.

    Shows the last 20 tasks ordered by update time, and a summary of
    tasks created per week.

    Args:
        project: Project UUID or name (partial match supported).
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_project(project, db)
            if error:
                return error
            proj_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # Project name
            proj_result = await db.execute(
                select(Project.name).where(Project.id == proj_uuid)
            )
            proj_name = proj_result.scalar_one_or_none()
            if not proj_name:
                return f"Project '{project}' not found."

            # Last 20 tasks by update time
            task_result = await db.execute(
                select(Task)
                .options(
                    selectinload(Task.task_status),
                    selectinload(Task.assignee),
                )
                .where(
                    Task.project_id == proj_uuid,
                    Task.archived_at.is_(None),
                )
                .order_by(Task.updated_at.desc())
                .limit(20)
            )
            tasks = task_result.scalars().all()

            # Tasks created per week (last 8 weeks)
            eight_weeks_ago = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            from datetime import timedelta

            eight_weeks_ago -= timedelta(weeks=8)

            weekly_result = await db.execute(
                select(
                    func.date_trunc("week", Task.created_at).label("week"),
                    func.count(Task.id).label("cnt"),
                )
                .where(
                    Task.project_id == proj_uuid,
                    Task.created_at >= eight_weeks_ago,
                )
                .group_by(func.date_trunc("week", Task.created_at))
                .order_by(func.date_trunc("week", Task.created_at))
            )
            weekly = weekly_result.all()

            # Overdue count
            today = datetime.now(timezone.utc).date()
            overdue_result = await db.execute(
                select(func.count(Task.id))
                .join(TaskStatus, Task.task_status_id == TaskStatus.id)
                .where(
                    Task.project_id == proj_uuid,
                    Task.due_date < today,
                    Task.archived_at.is_(None),
                    TaskStatus.category != "Done",
                )
            )
            overdue_count = overdue_result.scalar() or 0

        # Format
        lines = [
            f"## Timeline: {proj_name}",
            "",
            f"- **Overdue tasks**: {overdue_count}",
            "",
        ]

        # Recent activity
        if tasks:
            lines.append("### Recent Activity (last 20 updated)")
            lines.append("| Key | Title | Status | Assignee | Updated |")
            lines.append("| --- | --- | --- | --- | --- |")
            for t in tasks:
                assignee = t.assignee.display_name if t.assignee else "Unassigned"
                st = t.task_status.name if t.task_status else "\u2014"
                lines.append(
                    f"| {t.task_key} | {t.title} | {st} | "
                    f"{assignee} | {_format_date(t.updated_at)} |"
                )
            lines.append("")

        # Weekly creation trend
        if weekly:
            lines.append("### Tasks Created Per Week (last 8 weeks)")
            lines.append("| Week Starting | Tasks Created |")
            lines.append("| --- | --- |")
            for row in weekly:
                week_date = row.week
                if isinstance(week_date, datetime):
                    week_str = week_date.strftime("%Y-%m-%d")
                else:
                    week_str = str(week_date)
                lines.append(f"| {week_str} | {row.cnt} |")
            lines.append("")
        else:
            lines.append("_No tasks created in the last 8 weeks._")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning(
            "get_project_timeline failed: %s: %s", type(exc).__name__, exc
        )
        return "Error retrieving project timeline. Please try again."


@tool
async def get_overdue_tasks(scope: str = "") -> str:
    """Get all tasks that are past their due date across accessible projects.

    Use this when the user asks about deadlines, late work, or
    overdue items.

    Args:
        scope: Optional application UUID or name to narrow scope (partial match
               supported). Leave empty for all accessible projects.
    """
    try:
        accessible_project_ids = _get_ctx().get("accessible_project_ids", [])
        if not accessible_project_ids:
            return "You have no accessible projects."

        project_uuids = [UUID(pid) for pid in accessible_project_ids]
        today = datetime.now(timezone.utc).date()

        async with _get_tool_session() as db:
            # Resolve application scope if provided
            application_id: str | None = None
            if scope and scope.strip():
                resolved_id, error = await _resolve_application(scope, db)
                if error:
                    return error
                application_id = resolved_id

            query = (
                select(Task)
                .join(TaskStatus, Task.task_status_id == TaskStatus.id)
                .join(Project, Task.project_id == Project.id)
                .where(
                    Task.project_id.in_(project_uuids),
                    Task.due_date < today,
                    Task.archived_at.is_(None),
                    TaskStatus.category != "Done",
                )
                .options(
                    selectinload(Task.task_status),
                    selectinload(Task.assignee),
                    selectinload(Task.project),
                )
                .order_by(Task.due_date.asc())
                .limit(200)
            )

            # Narrow to specific application if requested
            if application_id:
                query = query.where(
                    Project.application_id == UUID(application_id)
                )

            result = await db.execute(query)
            tasks = result.scalars().unique().all()

        if not tasks:
            scope_desc = "this application" if application_id else "your accessible projects"
            return f"No overdue tasks found in {scope_desc}."

        # Group by project
        grouped: dict[str, list] = {}
        for t in tasks:
            proj_name = t.project.name if t.project else "Unknown"
            grouped.setdefault(proj_name, []).append(t)

        parts: list[str] = []
        parts.append(f"## Overdue Tasks ({len(tasks)} total)")
        parts.append("")

        for proj_name, proj_tasks in grouped.items():
            parts.append(f"### {proj_name}")
            parts.append("| Key | Title | Due Date | Days Overdue | Assignee |")
            parts.append("| --- | --- | --- | --- | --- |")

            for t in proj_tasks:
                assignee_name = (
                    t.assignee.display_name if t.assignee else "Unassigned"
                )
                overdue_days = _days_overdue(t.due_date) or 0
                parts.append(
                    f"| {t.task_key} | {t.title} "
                    f"| {_format_date(t.due_date)} | {overdue_days} "
                    f"| {assignee_name} |"
                )
            parts.append("")

        if len(tasks) >= 200:
            parts.append("*Showing first 200 overdue tasks. Use scope filter to narrow results.*")

        return _truncate("\n".join(parts))

    except Exception as exc:
        logger.warning(
            "get_overdue_tasks failed: %s: %s", type(exc).__name__, exc
        )
        return "Error retrieving overdue tasks. Please try again."

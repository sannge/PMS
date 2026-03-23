"""Identity tools for Blair AI agent.

Tools for the agent to learn about the current user's profile, roles,
and workload without modifying any data.
"""

from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ....models.application import Application
from ....models.application_member import ApplicationMember
from ....models.project import Project
from ....models.task import Task
from ....models.task_status import TaskStatus
from ....models.user import User
from .context import _get_ctx, _get_user_id
from .helpers import _days_overdue, _format_date, _get_tool_session, _truncate

logger = logging.getLogger(__name__)


@tool
async def get_my_profile() -> str:
    """Get the current user's profile including name, email, and application memberships.

    Use this when the user asks about themselves, their roles, or which
    applications they belong to.  No arguments required.
    """
    try:
        user_id = _get_user_id()

        async with _get_tool_session() as db:
            # Fetch user
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return "Error: Could not find your user profile."

            # Owned applications
            owned_result = await db.execute(
                select(Application.id, Application.name).where(Application.owner_id == user_id)
            )
            owned_apps = owned_result.all()

            # Member applications (via ApplicationMember) — includes all memberships
            member_result = await db.execute(
                select(
                    ApplicationMember.role,
                    Application.id,
                    Application.name,
                )
                .join(Application, ApplicationMember.application_id == Application.id)
                .where(
                    ApplicationMember.user_id == user_id,
                )
            )
            member_apps = member_result.all()

            # Deduplicate: apps appearing in both owned and member lists
            owned_ids = {app.id for app in owned_apps}

            # Total unique apps
            member_only = [m for m in member_apps if m.id not in owned_ids]
            total_apps = len(owned_apps) + len(member_only)

            # Format output
            lines = [
                "## My Profile",
                "",
                f"- **Name**: {user.display_name or '\u2014'}",
                f"- **Email**: {user.email}",
                f"- **Applications**: {total_apps} total",
                "",
            ]

            if owned_apps:
                lines.append("### Owned Applications")
                for app in owned_apps:
                    lines.append(f"- **{app.name}** (`{app.id}`) \u2014 Owner")
                lines.append("")

            if member_only:
                lines.append("### Member Applications")
                for mem in member_only:
                    lines.append(f"- **{mem.name}** (`{mem.id}`) \u2014 {mem.role}")
                lines.append("")

            if not owned_apps and not member_only:
                lines.append("_No application memberships found._")

        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning("get_my_profile failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving your profile. Please try again."


@tool
async def get_my_workload() -> str:
    """Get tasks assigned to the current user, grouped by project and status.

    Use this to understand what the user is currently working on, what is
    overdue, and how their tasks are distributed.  No arguments required.
    """
    try:
        user_id = _get_user_id()
        accessible_project_ids = _get_ctx().get("accessible_project_ids", [])

        async with _get_tool_session() as db:
            query = (
                select(Task)
                .options(
                    selectinload(Task.task_status),
                    selectinload(Task.project),
                )
                .where(
                    Task.assignee_id == user_id,
                    Task.archived_at.is_(None),
                )
            )
            # RBAC: only show tasks from projects the user still has access to
            if accessible_project_ids:
                from uuid import UUID as _UUID

                proj_uuids = [_UUID(pid) for pid in accessible_project_ids]
                query = query.where(Task.project_id.in_(proj_uuids))
            else:
                return "You have no accessible projects."

            from app.ai.config_service import get_agent_config

            _WORKLOAD_LIMIT = get_agent_config().get_int("agent_tool.workload_limit", 200)
            query = query.limit(_WORKLOAD_LIMIT)
            result = await db.execute(query)
            tasks = result.scalars().all()

            if not tasks:
                return "You have no tasks currently assigned to you."

            # Group by project -> status
            by_project: dict[str, dict[str, list]] = {}
            overdue_count = 0

            for t in tasks:
                proj_name = t.project.name if t.project else "Unknown Project"
                status_name = t.task_status.name if t.task_status else "Unknown"

                if proj_name not in by_project:
                    by_project[proj_name] = {}
                if status_name not in by_project[proj_name]:
                    by_project[proj_name][status_name] = []

                overdue = _days_overdue(t.due_date)
                if overdue:
                    overdue_count += 1

                by_project[proj_name][status_name].append(
                    {
                        "key": t.task_key,
                        "title": t.title,
                        "priority": t.priority,
                        "due_date": _format_date(t.due_date),
                        "overdue": overdue,
                    }
                )

            # Format output
            lines = [
                "## My Workload",
                "",
                f"- **Total tasks**: {len(tasks)}",
                f"- **Overdue**: {overdue_count}",
                "",
            ]

            for proj_name in sorted(by_project):
                lines.append(f"### {proj_name}")
                statuses = by_project[proj_name]
                for status_name in statuses:
                    lines.append(f"**{status_name}** ({len(statuses[status_name])})")
                    for t_info in statuses[status_name]:
                        overdue_marker = f" **OVERDUE {t_info['overdue']}d**" if t_info["overdue"] else ""
                        lines.append(
                            f"- `{t_info['key']}` {t_info['title']} "
                            f"[{t_info['priority']}] due {t_info['due_date']}{overdue_marker}"
                        )
                    lines.append("")

            if len(tasks) >= _WORKLOAD_LIMIT:
                lines.append(f"*(Showing first {_WORKLOAD_LIMIT} tasks. Use list_tasks with filters for more.)*")

        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning("get_my_workload failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving your workload. Please try again."

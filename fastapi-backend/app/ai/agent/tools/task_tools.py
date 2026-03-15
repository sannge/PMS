"""Task-domain tools for Blair AI agent.

Tools for listing, inspecting, and analysing tasks.  All tools are
read-only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ....models.attachment import Attachment
from ....models.checklist import Checklist
from ....models.comment import Comment
from ....models.project import Project
from ....models.task import Task
from ....models.task_status import TaskStatus
from ....models.user import User
from .context import _check_project_access, _get_ctx
from .helpers import (
    _days_overdue,
    _format_date,
    _get_tool_session,
    _resolve_project,
    _resolve_task,
    _resolve_user,
    _truncate,
    _wrap_user_content,
)

logger = logging.getLogger(__name__)


@tool
async def list_tasks(
    project: str,
    status: str = "",
    assignee: str = "",
    priority: str = "",
    overdue_only: bool = False,
    include_archived: bool = False,
) -> str:
    """List tasks in a project with optional filters.

    Use this when the user asks about specific tasks or task status
    within a project.

    Args:
        project: Project UUID or name (partial match supported).
        status: Optional filter -- "todo", "in_progress", "in_review", "issue", or "done".
        assignee: Optional filter -- user display name, email, or UUID.
        priority: Optional filter -- "lowest", "low", "medium", "high", "highest".
        overdue_only: If true, only return tasks past their due date.
        include_archived: If true, include archived tasks.
    """
    status_map = {
        "todo": "Todo",
        "in_progress": "In Progress",
        "in_review": "In Review",
        "issue": "Issue",
        "done": "Done",
    }

    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_project(project, db)
            if error:
                return error
            proj_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            query = (
                select(Task)
                .join(TaskStatus, Task.task_status_id == TaskStatus.id)
                .outerjoin(User, Task.assignee_id == User.id)
                .where(Task.project_id == proj_uuid)
                .options(
                    selectinload(Task.task_status),
                    selectinload(Task.assignee),
                    # Task.checklists uses lazy="dynamic" which is incompatible
                    # with selectinload. Use denormalized checklist_total/checklist_done instead.
                )
                .order_by(TaskStatus.rank, Task.task_rank)
            )

            if not include_archived:
                query = query.where(Task.archived_at.is_(None))

            # Status filter
            if status and status.strip():
                mapped = status_map.get(status.strip().lower())
                if mapped:
                    query = query.where(TaskStatus.name == mapped)
                else:
                    return (
                        f"Invalid status '{status}'. "
                        f"Use one of: {', '.join(status_map.keys())}."
                    )

            # Priority filter
            valid_priorities = {"lowest", "low", "medium", "high", "highest"}
            if priority and priority.strip():
                p = priority.strip().lower()
                if p not in valid_priorities:
                    return (
                        f"Invalid priority '{priority}'. "
                        f"Use one of: {', '.join(sorted(valid_priorities))}."
                    )
                query = query.where(Task.priority == p)

            # Assignee filter
            if assignee and assignee.strip():
                user_id, user_err = await _resolve_user(
                    assignee, db, scope_project_id=resolved_id
                )
                if user_err:
                    return user_err
                query = query.where(Task.assignee_id == UUID(user_id))  # type: ignore[arg-type]

            # Overdue filter
            if overdue_only:
                today = datetime.now(timezone.utc).date()
                query = query.where(
                    Task.due_date < today,
                    TaskStatus.category != "Done",
                )

            from app.ai.config_service import get_agent_config
            _LIST_TASKS_LIMIT = get_agent_config().get_int("agent_tool.list_tasks_limit", 200)
            query = query.limit(_LIST_TASKS_LIMIT)
            result = await db.execute(query)
            tasks = result.scalars().unique().all()

        if not tasks:
            return "No tasks found matching your filters."

        # Format
        lines: list[str] = []
        lines.append(
            "| Key | Title | Status | Priority | Assignee | Due | Checklist |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")

        for t in tasks:
            st = t.task_status.name if t.task_status else "\u2014"
            assignee_name = t.assignee.display_name if t.assignee else "Unassigned"
            due = _format_date(t.due_date)
            overdue = _days_overdue(t.due_date)
            if overdue:
                due += f" (**{overdue}d overdue**)"

            # Checklist progress (denormalized columns — avoids lazy="dynamic" query)
            cl_done = t.checklist_done or 0
            cl_total = t.checklist_total or 0
            cl_text = f"{cl_done}/{cl_total}" if cl_total > 0 else "\u2014"

            lines.append(
                f"| {t.task_key} | {t.title} | {st} | "
                f"{t.priority} | {assignee_name} | {due} | {cl_text} |"
            )

        if len(tasks) >= _LIST_TASKS_LIMIT:
            lines.append(f"\n*Showing first {_LIST_TASKS_LIMIT} tasks. Use filters to narrow results.*")
        else:
            lines.append(f"\n*{len(tasks)} task(s) found.*")
        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning("list_tasks failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving tasks. Please try again."


@tool
async def get_task_detail(task: str) -> str:
    """Get full details for a specific task including checklists, comments,
    attachments, subtasks, and metadata.

    Use this when the user asks for detailed information about a single task.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match).
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_task(task, db)
            if error:
                return error
            task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # Load task with eagerly-loaded relationships.
            # Task.subtasks, .attachments, .checklists, .comments all use
            # lazy="dynamic" which is incompatible with selectinload —
            # query them separately below.
            result = await db.execute(
                select(Task)
                .where(Task.id == task_uuid)
                .options(
                    selectinload(Task.task_status),
                    selectinload(Task.assignee),
                    selectinload(Task.reporter),
                    selectinload(Task.project),
                    selectinload(Task.parent),
                )
            )
            t = result.scalar_one_or_none()
            if t is None:
                return f"Task not found: {task}"

            # RBAC check on loaded task
            if not _check_project_access(str(t.project_id)):
                return f"Task not found: {task}"

            # Separate queries for dynamic relationships
            _subtasks_result = await db.execute(
                select(Task)
                .where(Task.parent_id == task_uuid)
                .options(selectinload(Task.task_status))
            )
            _subtasks = _subtasks_result.scalars().all()

            _attachments_result = await db.execute(
                select(Attachment)
                .where(Attachment.task_id == task_uuid)
            )
            _attachments = _attachments_result.scalars().all()

            checklists_result = await db.execute(
                select(Checklist)
                .where(Checklist.task_id == task_uuid)
                .options(selectinload(Checklist.items))
            )
            _checklists = checklists_result.scalars().all()

            comments_result = await db.execute(
                select(Comment)
                .where(Comment.task_id == task_uuid)
                .options(selectinload(Comment.author))
            )
            _comments = comments_result.scalars().all()

        # Build output
        parts: list[str] = []
        parts.append(f"## {t.task_key}: {t.title}")
        parts.append("")

        status_text = t.task_status.name if t.task_status else "\u2014"
        assignee_name = t.assignee.display_name if t.assignee else "Unassigned"
        reporter_name = t.reporter.display_name if t.reporter else "\u2014"
        project_name = t.project.name if t.project else "\u2014"

        parts.append(f"- **Project**: {project_name}")
        parts.append(f"- **Status**: {status_text}")
        parts.append(f"- **Priority**: {t.priority}")
        parts.append(f"- **Type**: {t.task_type}")
        parts.append(f"- **Assignee**: {assignee_name}")
        parts.append(f"- **Reporter**: {reporter_name}")
        parts.append(f"- **Due date**: {_format_date(t.due_date)}")
        if t.story_points is not None:
            parts.append(f"- **Story points**: {t.story_points}")
        parts.append(f"- **Created**: {_format_date(t.created_at)}")
        parts.append(f"- **Updated**: {_format_date(t.updated_at)}")

        # Parent task
        if t.parent:
            parts.append(f"- **Parent**: {t.parent.task_key} - {t.parent.title}")
        parts.append("")

        # Description
        if t.description:
            parts.append("### Description")
            parts.append(_wrap_user_content(t.description))
            parts.append("")

        # Subtasks
        subtasks = _subtasks
        if subtasks:
            parts.append(f"### Subtasks ({len(subtasks)})")
            for st in subtasks:
                st_status = st.task_status.name if st.task_status else "\u2014"
                parts.append(f"- `{st.task_key}` {st.title} [{st_status}]")
            parts.append("")

        # Checklists
        checklists = _checklists
        if checklists:
            parts.append("### Checklists")
            for cl in checklists:
                parts.append(
                    f"**{cl.title}** ({cl.completed_items}/{cl.total_items})"
                )
                items = list(cl.items)
                for item in items:
                    check = "[x]" if item.is_done else "[ ]"
                    parts.append(f"  - {check} {item.content}")
            parts.append("")

        # Attachments
        attachments = _attachments
        if attachments:
            parts.append(f"### Attachments ({len(attachments)})")
            for att in attachments:
                size_kb = (att.file_size or 0) / 1024
                parts.append(
                    f"- {att.file_name} ({att.file_type}, {size_kb:.1f} KB)"
                )
            parts.append("")

        # Comments (last 5 non-deleted)
        non_deleted = [c for c in _comments if not c.is_deleted]
        comments = sorted(
            non_deleted,
            key=lambda c: c.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:5]
        if comments:
            parts.append("### Recent Comments")
            for c in comments:
                author = c.author.display_name if c.author else "Unknown"
                timestamp = _format_date(c.created_at)
                body = c.body_text or "(no text)"
                if len(body) > 300:
                    body = body[:300] + "..."
                parts.append(f"**{author}** ({timestamp}):")
                parts.append(f"> {_wrap_user_content(body)}")
                parts.append("")

        return _truncate("\n".join(parts))

    except Exception as exc:
        logger.warning("get_task_detail failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving task details. Please try again."


@tool
async def get_task_comments(task: str) -> str:
    """Get all comments on a specific task.

    Returns comments with author name, timestamp, and body text,
    ordered by creation date.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match).
    """
    from app.ai.config_service import get_agent_config
    _COMMENTS_LIMIT = get_agent_config().get_int("agent_tool.comments_limit", 200)

    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_task(task, db)
            if error:
                return error
            task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # RBAC check
            task_check = await db.execute(
                select(Task.project_id, Task.task_key, Task.title).where(
                    Task.id == task_uuid
                )
            )
            row = task_check.one_or_none()
            if not row:
                return f"Task not found: {task}"
            if not _check_project_access(str(row.project_id)):
                return f"Task not found: {task}"

            # Fetch comments
            result = await db.execute(
                select(Comment)
                .options(selectinload(Comment.author))
                .where(
                    Comment.task_id == task_uuid,
                    Comment.is_deleted.is_(False),
                )
                .order_by(Comment.created_at.asc())
                .limit(_COMMENTS_LIMIT)
            )
            comments = result.scalars().all()

        if not comments:
            return f"No comments on task {row.task_key}."

        parts: list[str] = [
            f"## Comments on {row.task_key}: {row.title}",
            "",
            f"*{len(comments)} comment(s)*",
            "",
        ]

        for c in comments:
            author = c.author.display_name if c.author else "Unknown"
            timestamp = _format_date(c.created_at)
            body = c.body_text or "(no text)"
            parts.append(f"**{author}** ({timestamp}):")
            parts.append(f"> {_wrap_user_content(body)}")
            parts.append("")

        if len(comments) >= _COMMENTS_LIMIT:
            parts.append(f"*Showing first {_COMMENTS_LIMIT} comments.*")

        return _truncate("\n".join(parts))

    except Exception as exc:
        logger.warning("get_task_comments failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving task comments. Please try again."


@tool
async def get_blocked_tasks(project: str = "") -> str:
    """Get tasks that are blocked (Issue status) or overdue across accessible projects.

    Args:
        project: Optional project UUID or name to narrow scope (partial match
                 supported). Leave empty for all accessible projects.
    """
    try:
        return await _get_blocked_tasks_inner(project)
    except Exception as exc:
        logger.warning("get_blocked_tasks failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving blocked tasks. Please try again."


async def _get_blocked_tasks_inner(project: str) -> str:
    accessible_project_ids = _get_ctx().get("accessible_project_ids", [])
    if not accessible_project_ids:
        return "You have no accessible projects."

    project_uuids = [UUID(pid) for pid in accessible_project_ids]
    today = datetime.now(timezone.utc).date()

    async with _get_tool_session() as db:
        # Optional project scope
        if project and project.strip():
            resolved_id, error = await _resolve_project(project, db)
            if error:
                return error
            project_uuids = [UUID(resolved_id)]  # type: ignore[arg-type]

        # Tasks with Issue status OR overdue (not Done)
        query = (
            select(Task)
            .join(TaskStatus, Task.task_status_id == TaskStatus.id)
            .where(
                Task.project_id.in_(project_uuids),
                Task.archived_at.is_(None),
            )
            .where(
                (TaskStatus.name == "Issue")
                | (
                    (Task.due_date < today)
                    & (TaskStatus.category != "Done")
                )
            )
            .options(
                selectinload(Task.task_status),
                selectinload(Task.assignee),
                selectinload(Task.project),
            )
            .order_by(Task.due_date.asc().nullslast())
            .limit(200)
        )

        result = await db.execute(query)
        tasks = result.scalars().unique().all()

    if not tasks:
        return "No blocked or overdue tasks found."

    # Group by project
    grouped: dict[str, list] = {}
    for t in tasks:
        proj_name = t.project.name if t.project else "Unknown"
        grouped.setdefault(proj_name, []).append(t)

    parts: list[str] = [
        f"## Blocked & Overdue Tasks ({len(tasks)} total)",
        "",
    ]

    for proj_name, proj_tasks in grouped.items():
        parts.append(f"### {proj_name}")
        parts.append("| Key | Title | Reason | Assignee | Due | Days Overdue |")
        parts.append("| --- | --- | --- | --- | --- | --- |")

        for t in proj_tasks:
            assignee_name = t.assignee.display_name if t.assignee else "Unassigned"
            st = t.task_status.name if t.task_status else "\u2014"
            overdue = _days_overdue(t.due_date)

            if st == "Issue" and overdue:
                reason = f"Issue + {overdue}d overdue"
            elif st == "Issue":
                reason = "Issue"
            else:
                reason = f"{overdue}d overdue"

            parts.append(
                f"| {t.task_key} | {t.title} | {reason} | "
                f"{assignee_name} | {_format_date(t.due_date)} | "
                f"{overdue or '\u2014'} |"
            )
        parts.append("")

    if len(tasks) >= 200:
        parts.append("*Showing first 200 blocked/overdue tasks. Use project filter to narrow results.*")

    return _truncate("\n".join(parts))

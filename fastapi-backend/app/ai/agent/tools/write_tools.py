"""Write tools for Blair AI agent -- all require HITL confirmation via interrupt().

Tools that modify data in the PM Desktop system:
1. create_task -- Create a new task in a project
2. update_task_status -- Change a task's status
3. assign_task -- Assign or reassign a task to a team member
4. create_document -- Create a new knowledge base document
5. export_to_excel -- Export data to an Excel file for download
6. update_document -- Update an existing document's title or content
7. delete_document -- Soft-delete a document (creator only)
8. export_document_pdf -- Export a document as PDF for download
9. update_task -- Update task fields (title, description, priority, due_date, task_type)
10. add_task_comment -- Add a comment to a task with optional @mentions
11. delete_task -- Permanently delete a task and its associated data

All tools:
- Check RBAC BEFORE calling interrupt() (never confirm then deny)
- Use LangGraph interrupt() to pause and request user confirmation
- Use existing SQLAlchemy models for mutations
- Return human-readable confirmation text on success
- Return clear cancellation messages on rejection
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from ....models.application import Application
from ....models.application_member import ApplicationMember
from ....models.comment import Comment
from ....models.document import Document
from ....models.document_folder import DocumentFolder
from ....models.mention import Mention
from ....models.notification import Notification
from ....models.project import Project
from ....models.project_member import ProjectMember
from ....models.project_task_status_agg import ProjectTaskStatusAgg
from ....models.task import Task
from ....models.task_status import TaskStatus
from ....models.user import User
from ....websocket.handlers import (
    UpdateAction,
    handle_comment_added,
    handle_task_update,
)
from ....websocket.manager import MessageType, manager
from .context import _check_app_access, _check_project_access, _get_user_id
from .helpers import (
    _get_tool_session,
    _parse_uuid,
    _resolve_application,
    _resolve_document,
    _resolve_project,
    _resolve_task,
    _resolve_user,
    _strip_markdown,
    _truncate,
)

from ....utils.tasks import fire_and_forget

logger = logging.getLogger(__name__)


async def _broadcast_doc_event(
    message_type: MessageType,
    doc_id: str,
    application_id: UUID | None,
    project_id: UUID | None,
    user_id: UUID | None,
    actor_id: UUID | None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Broadcast document event to scope room(s).

    Uses ``source: "blair"`` so the frontend knows this is an AI-initiated
    change and always refetches (unlike manual editor saves which skip
    own-action refetch).
    """
    from ....utils.timezone import utc_now

    # Derive scope/scope_id — frontend needs these for cache invalidation
    if application_id:
        scope, scope_id = "application", str(application_id)
    elif project_id:
        scope, scope_id = "project", str(project_id)
    elif user_id:
        scope, scope_id = "personal", str(user_id)
    else:
        return  # No scope — nothing to broadcast

    data: dict[str, Any] = {
        "document_id": doc_id,
        "scope": scope,
        "scope_id": scope_id,
        "actor_id": str(actor_id) if actor_id else None,
        "source": "blair",
        "timestamp": utc_now().isoformat(),
    }
    if extra:
        data.update(extra)
    message = {"type": message_type.value, "data": data}

    if application_id:
        await manager.broadcast_to_room(f"application:{application_id}", message)
    elif project_id:
        await manager.broadcast_to_room(f"project:{project_id}", message)
    elif user_id:
        await manager.broadcast_to_room(f"user:{user_id}", message)

# ---------------------------------------------------------------------------
# Status name mapping: tool input (lowercase/snake_case) -> DB value
# ---------------------------------------------------------------------------

_STATUS_NAME_MAP: dict[str, str] = {
    "todo": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "issue": "Issue",
    "done": "Done",
}


# ---------------------------------------------------------------------------
# Tool 1: create_task
# ---------------------------------------------------------------------------


@tool
async def create_task(
    project: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
) -> str:
    """Create a new task in a project. Requires user confirmation before executing.

    Use this when the user wants to create a new task, story, or work item.
    The task will be created with 'Todo' status by default.

    Args:
        project: Project UUID or name (partial match supported)
        title: Task title (1-500 characters)
        description: Optional detailed task description
        priority: Optional priority - "lowest", "low", "medium", "high", "highest"
        assignee: Optional user UUID, email, or display name to assign the task to
    """
    # Validate inputs
    if not title or len(title.strip()) == 0:
        return "Error: Task title is required."
    if len(title) > 500:
        return "Error: Task title must be 500 characters or fewer."

    if description and len(description) > 50_000:
        return "Error: Task description too large. Maximum is 50,000 characters."

    valid_priorities = {"lowest", "low", "medium", "high", "highest"}
    if priority and priority.lower() not in valid_priorities:
        return f"Error: Invalid priority '{priority}'. Must be one of: {', '.join(sorted(valid_priorities))}."
    priority_value = (priority or "medium").lower()

    # Resolve project (supports UUID or name) and check RBAC
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_project(project, db)
        if error:
            return error
        proj_uuid = UUID(resolved_id)  # type: ignore[arg-type]
        project_id = resolved_id

        result = await db.execute(
            select(Project).where(Project.id == proj_uuid)
        )
        proj = result.scalar_one_or_none()
        if not proj:
            return f"Error: Project '{project}' not found."

        project_name = proj.name
        project_key = proj.key

        # Resolve assignee if provided
        assignee_name: str | None = None
        assignee_uuid: UUID | None = None
        if assignee and assignee.strip():
            user_id_str, user_err = await _resolve_user(
                assignee, db, scope_project_id=resolved_id
            )
            if user_err:
                return user_err

            assignee_uuid = UUID(user_id_str)  # type: ignore[arg-type]
            assignee_result = await db.execute(
                select(User).where(User.id == assignee_uuid)
            )
            assignee_user = assignee_result.scalar_one_or_none()
            if not assignee_user:
                return f"Error: Assignee user '{assignee}' not found."
            assignee_name = assignee_user.display_name or assignee_user.email

            # Validate assignee is a project member
            member_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == proj_uuid,
                    ProjectMember.user_id == assignee_uuid,
                )
            )
            if not member_result.scalar_one_or_none():
                return (
                    f"Error: User '{assignee_name}' is not a member of project "
                    f"'{project_name}'. They must be added as a project member first."
                )

    # Build confirmation payload
    details: dict[str, Any] = {
        "project_id": project_id,
        "project_name": project_name,
        "title": title,
        "priority": priority_value,
    }
    if description:
        details["description"] = description[:200] + ("..." if len(description) > 200 else "")
    if assignee_name:
        details["assignee"] = assignee_name
        details["assignee_id"] = str(assignee_uuid)

    summary = f"Create task '{title}' in {project_name}"
    if assignee_name:
        summary += f" (assigned to {assignee_name})"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "create_task",
        "summary": summary,
        "details": details,
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task creation cancelled by user."

    # DA-R2-004: Re-check RBAC + execute write in single session (TOCTOU mitigation)
    _broadcast_data: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == UUID(project_id),
                    ProjectMember.user_id == user_uuid_check,
                ).limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this project."

            # Re-fetch project to get current key (may have changed during HITL pause)
            proj_row = await db.execute(
                select(Project.key).where(Project.id == UUID(project_id))
            )
            project_key = proj_row.scalar_one_or_none()
            if project_key is None:
                return "Error: Project no longer exists."

            # Get default Todo status for the project
            status_result = await db.execute(
                select(TaskStatus).where(
                    TaskStatus.project_id == proj_uuid,
                    TaskStatus.name == "Todo",
                )
            )
            default_status = status_result.scalar_one_or_none()
            if not default_status:
                return "Error: Project has no default 'Todo' status configured."

            # Generate task key with atomic counter increment
            key_result = await db.execute(
                text("""
                    UPDATE "Projects"
                    SET next_task_number = next_task_number + 1
                    WHERE id = :project_id
                    RETURNING next_task_number - 1 AS task_number
                """),
                {"project_id": proj_uuid},
            )
            key_row = key_result.fetchone()
            if key_row is None:
                return f"Error: Could not generate task key for project '{project_name}'."
            task_key = f"{project_key}-{key_row[0]}"

            # Set reporter to current user
            user_id = _get_user_id()

            # Create the task
            task = Task(
                project_id=proj_uuid,
                task_key=task_key,
                title=title.strip(),
                description=description,
                task_type="story",
                priority=priority_value,
                assignee_id=assignee_uuid,
                reporter_id=user_id,
                task_status_id=default_status.id,
            )

            db.add(task)
            await db.flush()

            _broadcast_data = {
                "project_id": str(proj_uuid),
                "task_id": str(task.id),
                "task_key": task_key,
                "title": title.strip(),
                "priority": priority_value,
                "task_status_id": str(default_status.id),
                "assignee_id": str(assignee_uuid) if assignee_uuid else None,
                "user_id": str(user_id),
            }
            result_msg = f"Task '{title}' created in {project_name} (key: {task_key})."
            if assignee_name:
                result_msg += f" Assigned to {assignee_name}."

        except Exception as e:
            logger.exception("create_task failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback

    # Broadcast AFTER commit (block exit committed)
    if _broadcast_data:
        fire_and_forget(handle_task_update(
            project_id=_broadcast_data["project_id"],
            task_id=_broadcast_data["task_id"],
            action=UpdateAction.CREATED,
            task_data=_broadcast_data,
            user_id=_broadcast_data["user_id"],
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 2: update_task_status
# ---------------------------------------------------------------------------


@tool
async def update_task_status(
    task: str,
    new_status: str,
) -> str:
    """Change a task's status. Requires user confirmation before executing.

    Use this when the user wants to move a task to a different status column
    (e.g., from Todo to In Progress, or from In Review to Done).

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
        new_status: Target status - "todo", "in_progress", "in_review", "issue", "done"
    """
    status_key = new_status.lower().strip()
    target_status_name = _STATUS_NAME_MAP.get(status_key)
    if not target_status_name:
        valid = ", ".join(sorted(_STATUS_NAME_MAP.keys()))
        return f"Error: Invalid status '{new_status}'. Must be one of: {valid}."

    # Load task and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_task(task, db)
        if error:
            return error
        task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        task_title = task_obj.title
        project_id = task_obj.project_id

        # Get current status name
        current_status_result = await db.execute(
            select(TaskStatus).where(TaskStatus.id == task_obj.task_status_id)
        )
        current_status = current_status_result.scalar_one_or_none()
        current_status_name = current_status.name if current_status else "Unknown"

        # Verify the target status exists for this project
        target_status_result = await db.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == project_id,
                TaskStatus.name == target_status_name,
            )
        )
        target_status = target_status_result.scalar_one_or_none()
        if not target_status:
            return (
                f"Error: Status '{target_status_name}' not found for this project."
            )

        # Check if already in the target status
        if task_obj.task_status_id == target_status.id:
            return (
                f"Task {task_key} is already in '{current_status_name}' status. "
                "No change needed."
            )

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "update_task_status",
        "summary": (
            f"Move '{task_key}: {task_title}' "
            f"from {current_status_name} to {target_status_name}"
        ),
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "title": task_title,
            "current_status": current_status_name,
            "new_status": target_status_name,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task status update cancelled by user."

    # DA-R2-004: Re-check RBAC + execute write in single session (TOCTOU mitigation)
    _broadcast_data: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == UUID(str(project_id)),
                    ProjectMember.user_id == user_uuid_check,
                ).limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this task's project."

            # Re-load task to get fresh state
            result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task_obj = result.scalar_one_or_none()
            if not task_obj:
                return f"Error: Task '{task}' no longer exists."

            # Re-resolve current and target status post-interrupt (TOCTOU mitigation)
            current_status_result_fresh = await db.execute(
                select(TaskStatus).where(TaskStatus.id == task_obj.task_status_id)
            )
            current_status_fresh = current_status_result_fresh.scalar_one_or_none()

            target_status_result = await db.execute(
                select(TaskStatus).where(
                    TaskStatus.project_id == task_obj.project_id,
                    TaskStatus.name == target_status_name,
                )
            )
            target_status = target_status_result.scalar_one_or_none()
            if not target_status:
                return f"Error: Status '{target_status_name}' no longer exists for this project."

            task_obj.task_status_id = target_status.id

            # Update completed_at based on status change (mirrors tasks.py logic)
            from ....utils.timezone import utc_now as _utc_now
            new_is_done = target_status.category == "Done"
            old_was_done = current_status_fresh.category == "Done" if current_status_fresh else False
            if new_is_done and not old_was_done:
                task_obj.completed_at = _utc_now()
            elif old_was_done and not new_is_done:
                task_obj.completed_at = None

            await db.flush()

            _broadcast_data = {
                "project_id": str(project_id),
                "task_id": str(task_uuid),
                "task_key": task_key,
                "title": task_title,
                "task_status_id": str(target_status.id),
                "user_id": str(user_uuid_check),
            }
            result_msg = (
                f"Task {task_key} status updated: "
                f"{current_status_name} -> {target_status_name}."
            )

        except Exception as e:
            logger.exception("update_task_status failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback

    # Broadcast AFTER commit (block exit committed)
    if _broadcast_data:
        fire_and_forget(handle_task_update(
            project_id=_broadcast_data["project_id"],
            task_id=_broadcast_data["task_id"],
            action=UpdateAction.STATUS_CHANGED,
            task_data=_broadcast_data,
            user_id=_broadcast_data["user_id"],
            old_status=current_status_name,
            new_status=target_status_name,
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 3: assign_task
# ---------------------------------------------------------------------------


@tool
async def assign_task(
    task: str,
    user: str,
) -> str:
    """Assign or reassign a task to a team member. Requires user confirmation.

    Use this when the user wants to assign a task to someone, or change
    the current assignee of a task.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
        user: User UUID, email, or display name of the assignee
    """
    # Resolve task
    async with _get_tool_session() as db:
        resolved_task_id, task_err = await _resolve_task(task, db)
        if task_err:
            return task_err
        task_uuid = UUID(resolved_task_id)  # type: ignore[arg-type]

        # Load task
        result = await db.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        task_title = task_obj.title
        project_id = task_obj.project_id

        # Resolve assignee
        resolved_user_id, user_err = await _resolve_user(
            user, db, scope_project_id=str(project_id)
        )
        if user_err:
            return user_err
        assignee_uuid = UUID(resolved_user_id)  # type: ignore[arg-type]

        # Load assignee user
        assignee_result = await db.execute(
            select(User).where(User.id == assignee_uuid)
        )
        assignee_user = assignee_result.scalar_one_or_none()
        if not assignee_user:
            return f"Error: User '{user}' not found."
        assignee_name = assignee_user.display_name or assignee_user.email

        # Validate assignee is a project member
        member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == assignee_uuid,
            )
        )
        if not member_result.scalar_one_or_none():
            proj_result = await db.execute(
                select(Project.name).where(Project.id == project_id)
            )
            proj_name = proj_result.scalar_one_or_none() or "this project"
            return (
                f"Error: User '{assignee_name}' is not a member of project "
                f"'{proj_name}'. They must be added as a project member first."
            )

        # Get current assignee name
        current_assignee_name: str | None = None
        if task_obj.assignee_id:
            current_result = await db.execute(
                select(User).where(User.id == task_obj.assignee_id)
            )
            current_assignee = current_result.scalar_one_or_none()
            if current_assignee:
                current_assignee_name = (
                    current_assignee.display_name or current_assignee.email
                )

        # Check if already assigned to this person
        if task_obj.assignee_id == assignee_uuid:
            return (
                f"Task {task_key} is already assigned to {assignee_name}. "
                "No change needed."
            )

    # Build confirmation
    if current_assignee_name:
        summary = (
            f"Reassign '{task_key}: {task_title}' "
            f"from {current_assignee_name} to {assignee_name}"
        )
    else:
        summary = f"Assign '{task_key}: {task_title}' to {assignee_name}"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "assign_task",
        "summary": summary,
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "title": task_title,
            "assignee_id": str(assignee_uuid),
            "assignee_name": assignee_name,
            "previous_assignee": current_assignee_name,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task assignment cancelled by user."

    # DA-R2-004: Re-check RBAC + execute write in single session (TOCTOU mitigation)
    _broadcast_data: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == UUID(str(project_id)),
                    ProjectMember.user_id == user_uuid_check,
                ).limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this task's project."

            # Re-load task to get fresh state
            result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task_obj = result.scalar_one_or_none()
            if not task_obj:
                return f"Error: Task '{task}' no longer exists."

            task_obj.assignee_id = assignee_uuid
            await db.flush()

            _broadcast_data = {
                "project_id": str(project_id),
                "task_id": str(task_uuid),
                "task_key": task_key,
                "title": task_title,
                "assignee_id": str(assignee_uuid),
                "user_id": str(user_uuid_check),
            }
            result_msg = f"Task {task_key} assigned to {assignee_name}."

        except Exception as e:
            logger.exception("assign_task failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback

    # Broadcast AFTER commit (block exit committed)
    if _broadcast_data:
        fire_and_forget(handle_task_update(
            project_id=_broadcast_data["project_id"],
            task_id=_broadcast_data["task_id"],
            action=UpdateAction.UPDATED,
            task_data=_broadcast_data,
            user_id=_broadcast_data["user_id"],
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 4: create_document
# ---------------------------------------------------------------------------


@tool
async def create_document(
    title: str,
    content: str,
    scope: str,
    scope_id: str,
    folder_id: str | None = None,
    doc_type: str = "general",
) -> str:
    """Create a new knowledge base document. Requires user confirmation.

    Use this when the user wants to create a new document, specification,
    meeting notes, or any written content in the knowledge base.

    Args:
        title: Document title
        content: Document content in markdown format
        scope: Document scope - "application", "project", or "personal"
        scope_id: Application/project UUID or name (partial match supported),
                  or user UUID for personal scope
        folder_id: Optional target folder UUID to place the document in
        doc_type: Type of document to create. Determines writing style:
            - "training" -- Step-by-step learning material
              (Objective -> Prerequisites -> Steps -> Summary -> Assessment)
            - "research" -- Evidence and analysis
              (Executive Summary -> Findings -> Recommendations)
            - "documentation" -- Reference material
              (Overview -> Quick Start -> Detailed -> Troubleshooting)
            - "notes" -- Meeting notes
              (Summary -> Attendees -> Discussion -> Decisions -> Action Items)
            - "general" -- Default clear professional writing
    """
    # Validate inputs
    if not title or len(title.strip()) == 0:
        return "Error: Document title is required."
    if len(title) > 255:
        return "Error: Document title must be 255 characters or fewer."
    if not content or len(content.strip()) == 0:
        return "Error: Document content is required."
    if len(content) > 100_000:
        return f"Error: Document content too large ({len(content):,} chars). Maximum is 100,000 characters."

    scope_lower = scope.lower().strip()
    if scope_lower not in ("application", "project", "personal"):
        return "Error: Scope must be 'application', 'project', or 'personal'."

    folder_uuid: UUID | None = None
    if folder_id:
        try:
            folder_uuid = _parse_uuid(folder_id, "folder_id")
        except ValueError as e:
            return str(e)

    user_uuid = _get_user_id()

    # RBAC check BEFORE interrupt
    scope_display: str = ""
    scope_uuid: UUID | None = None
    async with _get_tool_session() as db:
        if scope_lower == "application":
            resolved_id, error = await _resolve_application(scope_id, db)
            if error:
                return error
            scope_uuid = UUID(resolved_id)  # type: ignore[arg-type]
            app_result = await db.execute(
                select(Application).where(Application.id == scope_uuid)
            )
            app = app_result.scalar_one_or_none()
            if not app:
                return f"Error: Application '{scope_id}' not found."
            scope_display = f"application '{app.name}'"

        elif scope_lower == "project":
            resolved_id, error = await _resolve_project(scope_id, db)
            if error:
                return error
            scope_uuid = UUID(resolved_id)  # type: ignore[arg-type]
            proj_result = await db.execute(
                select(Project).where(Project.id == scope_uuid)
            )
            proj = proj_result.scalar_one_or_none()
            if not proj:
                return f"Error: Project '{scope_id}' not found."
            scope_display = f"project '{proj.name}'"

        elif scope_lower == "personal":
            try:
                scope_uuid = _parse_uuid(scope_id, "scope_id")
            except ValueError as e:
                return str(e)
            if scope_uuid != user_uuid:
                return "Access denied: personal documents can only be created for yourself."
            scope_display = "your personal space"

        # Resolve folder if provided
        folder_display: str = ""
        if folder_uuid:
            folder_where = [DocumentFolder.id == folder_uuid]
            if scope_lower == "application":
                folder_where.append(DocumentFolder.application_id == scope_uuid)
            elif scope_lower == "project":
                folder_where.append(DocumentFolder.project_id == scope_uuid)
            elif scope_lower == "personal":
                folder_where.append(DocumentFolder.user_id == scope_uuid)

            folder_result = await db.execute(
                select(DocumentFolder).where(*folder_where)
            )
            folder = folder_result.scalar_one_or_none()
            if not folder:
                return f"Error: Folder '{folder_id}' not found in this scope."
            folder_display = f" in folder '{folder.name}'"

    if scope_uuid is None:
        return "Error: could not determine scope. Please provide a valid scope_id."

    # Build confirmation
    content_preview = content[:150] + ("..." if len(content) > 150 else "")

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "create_document",
        "summary": f"Create document '{title}' in {scope_display}{folder_display}",
        "details": {
            "title": title,
            "scope": scope_lower,
            "scope_id": scope_id,
            "scope_display": scope_display,
            "content_preview": content_preview,
        },
    }
    if folder_id:
        confirmation["details"]["folder_id"] = folder_id

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Document creation cancelled by user."

    # DA-R4-008 / SA-R4-001: Re-check RBAC after interrupt AND execute write
    # in a SINGLE session to eliminate TOCTOU gap (CRIT-5)
    _doc_broadcast: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()

            if scope_lower == "project":
                membership = await db.execute(
                    select(ProjectMember.id).where(
                        ProjectMember.project_id == scope_uuid,
                        ProjectMember.user_id == user_uuid_check,
                    ).limit(1)
                )
                if membership.scalar_one_or_none() is None:
                    return "Access denied: you no longer have access to this project."
            elif scope_lower == "application":
                membership = await db.execute(
                    select(ApplicationMember.id).where(
                        ApplicationMember.application_id == scope_uuid,
                        ApplicationMember.user_id == user_uuid_check,
                    ).limit(1)
                )
                if membership.scalar_one_or_none() is None:
                    return "Access denied: you no longer have access to this application."

            application_id: UUID | None = None
            project_id: UUID | None = None
            doc_user_id: UUID | None = None

            if scope_lower == "application":
                application_id = scope_uuid
            elif scope_lower == "project":
                project_id = scope_uuid
            elif scope_lower == "personal":
                doc_user_id = scope_uuid

            import json as _json

            from ....worker import markdown_to_tiptap_json

            content_plain = _strip_markdown(content)

            document = Document(
                title=title.strip(),
                content_json=_json.dumps(markdown_to_tiptap_json(content)),
                content_markdown=content,
                content_plain=content_plain,
                application_id=application_id,
                project_id=project_id,
                user_id=doc_user_id,
                folder_id=folder_uuid,
                created_by=user_uuid,
            )

            db.add(document)
            await db.flush()

            doc_id = str(document.id)

            # Trigger embedding job
            try:
                from datetime import timedelta

                from ....services.arq_helper import get_arq_redis

                arq_redis = await get_arq_redis()
                await arq_redis.enqueue_job(
                    "embed_document_job",
                    doc_id,
                    _job_id=f"embed:{doc_id}",
                    _defer_by=timedelta(seconds=120),
                )
            except Exception:
                logger.warning(
                    "Failed to enqueue embedding job for document %s",
                    doc_id,
                    exc_info=True,
                )

            _doc_broadcast = {
                "doc_id": doc_id,
                "application_id": application_id,
                "project_id": project_id,
                "user_id": doc_user_id,
                "actor_id": user_uuid,
                "title": title.strip(),
            }
            result_msg = (
                f"Document '{title}' created in {scope_display}{folder_display} "
                f"(id: {doc_id})."
            )

        except Exception as e:
            logger.exception("create_document failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback

    # Broadcast AFTER commit (block exit committed)
    if _doc_broadcast:
        fire_and_forget(_broadcast_doc_event(
            message_type=MessageType.DOCUMENT_CREATED,
            doc_id=_doc_broadcast["doc_id"],
            application_id=_doc_broadcast["application_id"],
            project_id=_doc_broadcast["project_id"],
            user_id=_doc_broadcast["user_id"],
            actor_id=_doc_broadcast["actor_id"],
            extra={"title": _doc_broadcast["title"]},
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 5: export_to_excel
# ---------------------------------------------------------------------------


@tool
async def export_to_excel(
    data_type: str,
    scope: str,
    filters: str = "",
) -> str:
    """Export project data to an Excel file for download. Requires user confirmation.

    Use this when the user wants to download or export data as a spreadsheet.

    Args:
        data_type: What to export -- "tasks", "projects", or "members".
        scope: Application or project UUID or name to export from (partial match supported).
        filters: Optional filter description in natural language (e.g., "overdue tasks only").
    """
    from ...agent_tools import export_to_excel_tool

    user_id = _get_user_id()

    valid_types = {"tasks", "projects", "members"}
    data_type_lower = data_type.lower().strip()
    if data_type_lower not in valid_types:
        return f"Error: data_type must be one of: {', '.join(sorted(valid_types))}."

    # RBAC: resolve scope BEFORE interrupt (never confirm then deny)
    resolved_scope_id: str | None = None
    resolved_scope_type: str | None = None  # "project" or "application"


    async with _get_tool_session() as db:
        if data_type_lower == "tasks":
            # Try project first, then application
            resolved_id, error = await _resolve_project(scope, db)
            if error:
                resolved_app_id, app_error = await _resolve_application(scope, db)
                if app_error:
                    return error
                resolved_scope_id = resolved_app_id
                resolved_scope_type = "application"
            else:
                resolved_scope_id = resolved_id
                resolved_scope_type = "project"
        elif data_type_lower in ("projects", "members"):
            resolved_app_id, error = await _resolve_application(scope, db)
            if error:
                return error
            resolved_scope_id = resolved_app_id
            resolved_scope_type = "application"

    # Build confirmation
    summary = f"Export {data_type_lower} from '{scope}'"
    if filters:
        summary += f" (filter: {filters})"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "export_to_excel",
        "summary": summary,
        "details": {
            "data_type": data_type_lower,
            "scope": scope,
            "filters": filters,
        },
    }

    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Export cancelled by user."

    # SA-R4-002: Re-check RBAC + gather data in single session (TOCTOU mitigation)
    async with _get_tool_session() as db:
        try:
            # RBAC re-check
            user_uuid_check = _get_user_id()
            if resolved_scope_type == "project":
                membership = await db.execute(
                    select(ProjectMember.id).where(
                        ProjectMember.project_id == UUID(resolved_scope_id),
                        ProjectMember.user_id == user_uuid_check,
                    ).limit(1)
                )
                if membership.scalar_one_or_none() is None:
                    return "Access denied: you no longer have access to this project."
            elif resolved_scope_type == "application":
                membership = await db.execute(
                    select(ApplicationMember.id).where(
                        ApplicationMember.application_id == UUID(resolved_scope_id),
                        ApplicationMember.user_id == user_uuid_check,
                    ).limit(1)
                )
                if membership.scalar_one_or_none() is None:
                    return "Access denied: you no longer have access to this application."

            columns: list[str] = []
            rows: list[dict[str, Any]] = []
            scope_uuid = UUID(resolved_scope_id)  # type: ignore[arg-type]

            if data_type_lower == "tasks":
                if resolved_scope_type == "application":
                    # Get tasks from all projects in the app
                    proj_result = await db.execute(
                        select(Project.id).where(
                            Project.application_id == scope_uuid,
                            Project.archived_at.is_(None),
                        )
                    )
                    proj_ids = [row[0] for row in proj_result.all()]
                    if not proj_ids:
                        return "No projects found in this application."

                    task_result = await db.execute(
                        select(Task)
                        .options(
                            selectinload(Task.task_status),
                            selectinload(Task.assignee),
                            selectinload(Task.project),
                        )
                        .where(
                            Task.project_id.in_(proj_ids),
                            Task.archived_at.is_(None),
                        )
                        .order_by(Task.task_key)
                        .limit(2000)
                    )
                else:
                    task_result = await db.execute(
                        select(Task)
                        .options(
                            selectinload(Task.task_status),
                            selectinload(Task.assignee),
                            selectinload(Task.project),
                        )
                        .where(
                            Task.project_id == scope_uuid,
                            Task.archived_at.is_(None),
                        )
                        .order_by(Task.task_key)
                        .limit(2000)
                    )

                tasks = task_result.scalars().all()
                columns = ["Key", "Title", "Project", "Status", "Priority", "Assignee", "Due Date"]
                rows = [
                    {
                        "Key": t.task_key,
                        "Title": t.title,
                        "Project": t.project.name if t.project else "",
                        "Status": t.task_status.name if t.task_status else "",
                        "Priority": t.priority or "",
                        "Assignee": (t.assignee.display_name or t.assignee.email) if t.assignee else "",
                        "Due Date": str(t.due_date) if t.due_date else "",
                    }
                    for t in tasks
                ]

            elif data_type_lower == "projects":
                proj_result = await db.execute(
                    select(Project)
                    .where(
                        Project.application_id == scope_uuid,
                        Project.archived_at.is_(None),
                    )
                    .order_by(Project.name)
                )
                projects = proj_result.scalars().all()
                columns = ["Name", "Key", "Due Date", "Created"]
                rows = [
                    {
                        "Name": p.name,
                        "Key": p.key,
                        "Due Date": str(p.due_date) if p.due_date else "",
                        "Created": str(p.created_at.date()) if p.created_at else "",
                    }
                    for p in projects
                ]

            elif data_type_lower == "members":
                mem_result = await db.execute(
                    select(ApplicationMember)
                    .options(selectinload(ApplicationMember.user))
                    .where(
                        ApplicationMember.application_id == scope_uuid
                    )
                )
                members = mem_result.scalars().all()
                columns = ["Name", "Email", "Role"]
                rows = [
                    {
                        "Name": m.user.display_name or "" if m.user else "",
                        "Email": m.user.email if m.user else "",
                        "Role": m.role,
                    }
                    for m in members
                ]

            if not rows:
                return f"No {data_type_lower} data found to export."

            title = f"{data_type_lower.capitalize()} Export - {scope}"
            result = await export_to_excel_tool(
                columns=columns,
                rows=rows,
                title=title,
                user_id=user_id,
            )

            if not result.success:
                return f"Export failed: {result.error}"

            return _truncate(result.data or "Export completed.")

        except Exception as e:
            logger.exception("export_to_excel failed: %s", e)
            return "Error exporting data. Please try again or contact support."


# ---------------------------------------------------------------------------
# Tool 6: update_document
# ---------------------------------------------------------------------------


@tool
async def update_document(
    doc: str,
    title: str = "",
    content: str = "",
) -> str:
    """Update an existing document's title and/or content. Requires user confirmation.

    Use this when the user wants to edit, rename, or rewrite a document.

    Args:
        doc: Document UUID or title (partial match supported)
        title: New title for the document (1-200 chars). Leave empty to keep current.
        content: New content in markdown format (max 100,000 chars). Leave empty to keep current.
    """
    # Validate: at least one field provided
    has_title = bool(title and title.strip())
    has_content = bool(content and content.strip())
    if not has_title and not has_content:
        return "Error: At least one of 'title' or 'content' must be provided."
    if has_title and (len(title.strip()) < 1 or len(title.strip()) > 200):
        return "Error: Document title must be between 1 and 200 characters."
    if has_content and len(content) > 100_000:
        return (
            f"Error: Document content too large ({len(content):,} chars). "
            "Maximum is 100,000 characters."
        )

    user_uuid = _get_user_id()

    # Resolve document and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_document(doc, db)
        if error:
            return error
        doc_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(
            select(Document).where(
                Document.id == doc_uuid,
                Document.deleted_at.is_(None),
            )
        )
        document = result.scalar_one_or_none()
        if not document:
            return f"Error: Document '{doc}' not found."

        doc_title = document.title

        # RBAC: scope-based access check
        if document.user_id is not None:
            # Personal scope: creator only
            if document.created_by != user_uuid:
                return "Access denied: you can only update your own personal documents."
        elif document.application_id is not None:
            # Application scope: app owner or editor
            if not _check_app_access(str(document.application_id)):
                return "Access denied: you do not have access to this application."
        elif document.project_id is not None:
            # Project scope: app owner/editor or project member
            if not _check_project_access(str(document.project_id)):
                return "Access denied: you do not have access to this project."

    # Check document lock — refuse if ANY user holds the lock (including self).
    # Blair writes directly to DB, bypassing the editor. Updating while the
    # editor is open would cause conflicts (editor overwrites Blair's changes
    # on next save, or Blair overwrites unsaved edits).
    try:
        from ....services.document_lock_service import get_lock_service

        lock_svc = get_lock_service()
        lock_holder = await lock_svc.get_lock_holder(str(doc_uuid))
        if lock_holder:
            holder_name = lock_holder.get("user_name", "someone")
            is_self = str(lock_holder.get("user_id")) == str(user_uuid)
            if is_self:
                return (
                    f"Error: Document '{doc_title}' is currently open in the editor. "
                    "Please close or save the document first, then retry."
                )
            return (
                f"Error: Document '{doc_title}' is currently locked by "
                f"{holder_name}. Please wait until they finish editing."
            )
    except Exception:
        logger.warning("Lock check failed for document %s", doc_uuid, exc_info=True)

    # Build confirmation
    changes: list[str] = []
    if has_title:
        changes.append(f"title -> '{title.strip()}'")
    if has_content:
        changes.append(f"content ({len(content):,} chars)")

    summary = f"Update document '{doc_title}': {', '.join(changes)}"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "update_document",
        "summary": summary,
        "details": {
            "document_id": str(doc_uuid),
            "document_title": doc_title,
            "changes": changes,
        },
    }

    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Document update cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
    _doc_broadcast: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            result = await db.execute(
                select(Document).where(
                    Document.id == doc_uuid,
                    Document.deleted_at.is_(None),
                )
            )
            document = result.scalar_one_or_none()
            if not document:
                return f"Error: Document '{doc}' no longer exists."

            recheck_user = _get_user_id()
            if document.user_id is not None:
                if document.created_by != recheck_user:
                    return "Access denied: you can no longer update this document."
            elif document.application_id is not None:
                if not _check_app_access(str(document.application_id)):
                    return "Access denied: you no longer have access to this application."
            elif document.project_id is not None:
                if not _check_project_access(str(document.project_id)):
                    return "Access denied: you no longer have access to this project."

            if has_title:
                document.title = title.strip()
            if has_content:
                import json as _json

                from ....worker import markdown_to_tiptap_json

                content_plain = _strip_markdown(content)
                document.content_json = _json.dumps(
                    markdown_to_tiptap_json(content)
                )
                document.content_markdown = content
                document.content_plain = content_plain
                document.embedding_status = "stale"

            await db.flush()

            doc_id = str(document.id)
            final_title = document.title

            # Trigger re-embedding job if content changed
            if has_content:
                try:
                    from datetime import timedelta

                    from ....services.arq_helper import get_arq_redis

                    arq_redis = await get_arq_redis()
                    await arq_redis.enqueue_job(
                        "embed_document_job",
                        doc_id,
                        _job_id=f"embed:{doc_id}",
                        _defer_by=timedelta(seconds=120),
                    )
                except Exception:
                    logger.warning(
                        "Failed to enqueue embedding job for document %s",
                        doc_id,
                        exc_info=True,
                    )

            _doc_broadcast = {
                "doc_id": doc_id,
                "application_id": document.application_id,
                "project_id": document.project_id,
                "user_id": document.user_id,
                "actor_id": recheck_user,
                "title": final_title,
            }
            result_msg = f"Updated document '{final_title}' (id: {doc_id})."

        except Exception as e:
            logger.exception("update_document failed: %s", e)
            raise

    # Broadcast AFTER commit (block exit committed)
    if _doc_broadcast:
        fire_and_forget(_broadcast_doc_event(
            message_type=MessageType.DOCUMENT_UPDATED,
            doc_id=_doc_broadcast["doc_id"],
            application_id=_doc_broadcast["application_id"],
            project_id=_doc_broadcast["project_id"],
            user_id=_doc_broadcast["user_id"],
            actor_id=_doc_broadcast["actor_id"],
            extra={"title": _doc_broadcast["title"]},
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 7: delete_document
# ---------------------------------------------------------------------------


@tool
async def delete_document(
    doc: str,
) -> str:
    """Delete a document (soft delete). Requires user confirmation.

    Only the document creator can delete a document. The document is
    soft-deleted (marked with deleted_at timestamp) and removed from
    search index.

    Args:
        doc: Document UUID or title (partial match supported)
    """
    user_uuid = _get_user_id()

    # Resolve document and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_document(doc, db)
        if error:
            return error
        doc_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(
            select(Document).where(
                Document.id == doc_uuid,
                Document.deleted_at.is_(None),
            )
        )
        document = result.scalar_one_or_none()
        if not document:
            return f"Error: Document '{doc}' not found."

        # RBAC: creator only
        if document.created_by != user_uuid:
            return "Access denied: only the document creator can delete a document."

        doc_title = document.title

    # Check document lock — refuse if ANY user holds the lock
    try:
        from ....services.document_lock_service import get_lock_service

        lock_svc = get_lock_service()
        lock_holder = await lock_svc.get_lock_holder(str(doc_uuid))
        if lock_holder:
            holder_name = lock_holder.get("user_name", "someone")
            is_self = str(lock_holder.get("user_id")) == str(user_uuid)
            if is_self:
                return (
                    f"Error: Document '{doc_title}' is currently open in the editor. "
                    "Please close the document first, then retry."
                )
            return (
                f"Error: Document '{doc_title}' is currently locked by "
                f"{holder_name}. Cannot delete while someone is editing."
            )
    except Exception:
        logger.warning("Lock check failed for document %s", doc_uuid, exc_info=True)

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "delete_document",
        "summary": f"Delete document '{doc_title}'",
        "details": {
            "document_id": str(doc_uuid),
            "document_title": doc_title,
        },
    }

    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Document deletion cancelled by user."

    # Re-check RBAC + execute soft delete in single session (TOCTOU mitigation)
    _doc_broadcast: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            result = await db.execute(
                select(Document).where(
                    Document.id == doc_uuid,
                    Document.deleted_at.is_(None),
                )
            )
            document = result.scalar_one_or_none()
            if not document:
                return f"Error: Document '{doc}' no longer exists or was already deleted."

            recheck_user = _get_user_id()
            if document.created_by != recheck_user:
                return "Access denied: you can no longer delete this document."

            # Capture broadcast data before mutation
            _doc_broadcast = {
                "doc_id": str(doc_uuid),
                "application_id": document.application_id,
                "project_id": document.project_id,
                "user_id": document.user_id,
                "actor_id": recheck_user,
                "title": doc_title,
            }

            document.deleted_at = datetime.now(timezone.utc)
            await db.flush()

            # Remove from Meilisearch index (fire-and-forget)
            try:
                from ....services.search_service import index_document_soft_delete

                await index_document_soft_delete(doc_uuid)
            except Exception:
                logger.warning(
                    "Failed to update search index for deleted document %s",
                    doc_uuid,
                    exc_info=True,
                )

            result_msg = f"Deleted document '{doc_title}' (id: {doc_uuid})."

        except Exception as e:
            logger.exception("delete_document failed: %s", e)
            raise

    # Broadcast AFTER commit (block exit committed)
    if _doc_broadcast:
        fire_and_forget(_broadcast_doc_event(
            message_type=MessageType.DOCUMENT_DELETED,
            doc_id=_doc_broadcast["doc_id"],
            application_id=_doc_broadcast["application_id"],
            project_id=_doc_broadcast["project_id"],
            user_id=_doc_broadcast["user_id"],
            actor_id=_doc_broadcast["actor_id"],
            extra={"title": _doc_broadcast["title"]},
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 8: export_document_pdf
# ---------------------------------------------------------------------------


@tool
async def export_document_pdf(
    doc: str,
) -> str:
    """Export a document as a PDF file for download. Requires user confirmation.

    Use this when the user wants to download a document as PDF.

    Args:
        doc: Document UUID or title (partial match supported)
    """
    user_uuid = _get_user_id()

    # Resolve document and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_document(doc, db)
        if error:
            return error
        doc_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(
            select(Document).where(
                Document.id == doc_uuid,
                Document.deleted_at.is_(None),
            )
        )
        document = result.scalar_one_or_none()
        if not document:
            return f"Error: Document '{doc}' not found."

        # RBAC: must have view access to document's scope
        if document.user_id is not None:
            if document.created_by != user_uuid:
                return "Access denied: you do not have access to this document."
        elif document.application_id is not None:
            if not _check_app_access(str(document.application_id)):
                return "Access denied: you do not have access to this application."
        elif document.project_id is not None:
            if not _check_project_access(str(document.project_id)):
                return "Access denied: you do not have access to this project."

        doc_title = document.title
        doc_content_md = document.content_markdown or ""
        doc_content_plain = document.content_plain or ""

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "export_document_pdf",
        "summary": f"Export '{doc_title}' as PDF for download",
        "details": {
            "document_id": str(doc_uuid),
            "document_title": doc_title,
        },
    }

    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "PDF export cancelled by user."

    # Generate PDF
    try:
        from ....ai.pdf_export import generate_pdf, save_pdf_export

        import asyncio as _asyncio
        pdf_bytes = await _asyncio.to_thread(generate_pdf, doc_title, doc_content_md or doc_content_plain)
        export_result = await save_pdf_export(
            pdf_bytes=pdf_bytes,
            title=doc_title,
            user_id=user_uuid,
        )

        return (
            f"Exported '{doc_title}' as PDF ({len(pdf_bytes):,} bytes). "
            f"[Download {export_result.filename}]({export_result.download_url})"
        )

    except Exception as e:
        logger.exception("export_document_pdf failed: %s", e)
        return "Error exporting document as PDF. Please try again."


# ---------------------------------------------------------------------------
# Tool 9: update_task
# ---------------------------------------------------------------------------


@tool
async def update_task(
    task: str,
    title: str = "",
    description: str = "",
    priority: str = "",
    due_date: str = "",
    task_type: str = "",
) -> str:
    """Update one or more fields on a task. Requires user confirmation before executing.

    Use this when the user wants to change a task's title, description,
    priority, due date, or type.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
        title: New task title (1-500 chars). Leave empty to keep current.
        description: New description (max 5000 chars). Leave empty to keep current.
        priority: New priority - "lowest", "low", "medium", "high", "highest". Leave empty to keep current.
        due_date: New due date in ISO format (e.g., "2026-04-01"). Leave empty to keep current.
        task_type: New type - "story", "bug", "epic", "subtask", "task". Leave empty to keep current.
    """
    # Validate at least one field provided
    if not any([title, description, priority, due_date, task_type]):
        return "Error: At least one field must be provided to update (title, description, priority, due_date, task_type)."

    # Validate individual fields
    if title and len(title.strip()) == 0:
        return "Error: Title cannot be empty when provided."
    if title and len(title) > 500:
        return "Error: Task title must be 500 characters or fewer."

    if description and len(description) > 5000:
        return "Error: Task description must be 5,000 characters or fewer."

    valid_priorities = {"lowest", "low", "medium", "high", "highest"}
    if priority and priority.lower() not in valid_priorities:
        return f"Error: Invalid priority '{priority}'. Must be one of: {', '.join(sorted(valid_priorities))}."

    if due_date:
        try:
            datetime.fromisoformat(due_date)
        except ValueError:
            return f"Error: Invalid due_date '{due_date}'. Must be in ISO format (e.g., '2026-04-01')."

    valid_task_types = {"story", "bug", "epic", "subtask", "task"}
    if task_type and task_type.lower() not in valid_task_types:
        return f"Error: Invalid task_type '{task_type}'. Must be one of: {', '.join(sorted(valid_task_types))}."

    # Resolve task and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_task(task, db)
        if error:
            return error
        task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        task_title = task_obj.title
        project_id = task_obj.project_id

    # Build change summary for confirmation
    changes: list[str] = []
    if title:
        changes.append(f"title -> '{title.strip()}'")
    if description:
        preview = description[:100] + ("..." if len(description) > 100 else "")
        changes.append(f"description -> '{preview}'")
    if priority:
        changes.append(f"priority -> {priority.lower()}")
    if due_date:
        changes.append(f"due_date -> {due_date}")
    if task_type:
        changes.append(f"task_type -> {task_type.lower()}")

    summary = f"Update {task_key} '{task_title}': {', '.join(changes)}"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "update_task",
        "summary": summary,
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "title": task_title,
            "changes": changes,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task update cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
    _broadcast_data: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == UUID(str(project_id)),
                    ProjectMember.user_id == user_uuid_check,
                ).limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this task's project."

            result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task_obj = result.scalar_one_or_none()
            if not task_obj:
                return f"Error: Task '{task}' no longer exists."

            # Apply partial updates
            if title:
                task_obj.title = title.strip()
            if description:
                task_obj.description = description
            if priority:
                task_obj.priority = priority.lower()
            if due_date:
                from datetime import date as date_type

                task_obj.due_date = date_type.fromisoformat(due_date)
            if task_type:
                task_obj.task_type = task_type.lower()

            await db.flush()

            _broadcast_data = {
                "project_id": str(project_id),
                "task_id": str(task_uuid),
                "task_key": task_key,
                "title": task_obj.title,
                "priority": task_obj.priority,
                "user_id": str(user_uuid_check),
            }
            result_msg = f"Updated task {task_key} '{task_obj.title}'."

        except Exception as e:
            logger.exception("update_task failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback

    # Broadcast AFTER commit (block exit committed)
    if _broadcast_data:
        fire_and_forget(handle_task_update(
            project_id=_broadcast_data["project_id"],
            task_id=_broadcast_data["task_id"],
            action=UpdateAction.UPDATED,
            task_data=_broadcast_data,
            user_id=_broadcast_data["user_id"],
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 10: add_task_comment
# ---------------------------------------------------------------------------


@tool
async def add_task_comment(
    task: str,
    content: str,
    mentions: str = "",
) -> str:
    """Add a comment to a task, optionally mentioning other users. Requires user confirmation.

    Use this when the user wants to add a comment, note, or discussion
    entry on a task. Mentioned users will receive notifications.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
        content: Comment text (1-5000 characters)
        mentions: Optional comma-separated list of user emails or names to @mention
    """
    # Validate inputs
    if not content or len(content.strip()) == 0:
        return "Error: Comment content is required."
    if len(content) > 5000:
        return "Error: Comment content must be 5,000 characters or fewer."

    # Resolve task
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_task(task, db)
        if error:
            return error
        task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: any application member can comment (just need project access)
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        task_title = task_obj.title
        project_id = task_obj.project_id

        # Resolve mentions if provided
        mention_users: list[tuple[UUID, str]] = []  # (user_id, display_name)
        if mentions and mentions.strip():
            for mention_str in mentions.split(","):
                mention_str = mention_str.strip()
                if not mention_str:
                    continue
                user_id_str, user_err = await _resolve_user(
                    mention_str, db, scope_project_id=str(project_id)
                )
                if user_err:
                    return f"Error resolving mention '{mention_str}': {user_err}"

                user_result = await db.execute(
                    select(User).where(User.id == UUID(user_id_str))  # type: ignore[arg-type]
                )
                mention_user = user_result.scalar_one_or_none()
                if mention_user:
                    display = mention_user.display_name or mention_user.email
                    mention_users.append((UUID(user_id_str), display))  # type: ignore[arg-type]

    # Build confirmation
    summary = f"Add comment to {task_key}"
    if mention_users:
        names = ", ".join(name for _, name in mention_users)
        summary += f" (mentioning {names})"

    content_preview = content[:200] + ("..." if len(content) > 200 else "")

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "add_task_comment",
        "summary": summary,
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "title": task_title,
            "content_preview": content_preview,
        },
    }
    if mention_users:
        confirmation["details"]["mentions"] = [name for _, name in mention_users]

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Comment cancelled by user."

    # User approved -- execute the write
    _comment_broadcast: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            user_id = _get_user_id()

            # TOCTOU re-check: verify user still has access after interrupt
            proj_result = await db.execute(
                select(Project.application_id).where(Project.id == project_id).limit(1)
            )
            app_id = proj_result.scalar_one_or_none()
            if app_id is not None:
                membership = await db.execute(
                    select(ApplicationMember.id).where(
                        ApplicationMember.application_id == app_id,
                        ApplicationMember.user_id == user_id,
                    ).limit(1)
                )
                if not membership.scalar_one_or_none():
                    return "Access denied: your permissions have changed since confirmation."

            comment = Comment(
                task_id=task_uuid,
                author_id=user_id,
                body_text=content.strip(),
            )
            db.add(comment)
            await db.flush()

            # Create Mention records and Notifications
            for mention_uid, mention_name in mention_users:
                mention = Mention(
                    comment_id=comment.id,
                    user_id=mention_uid,
                )
                db.add(mention)

                notification = Notification(
                    user_id=mention_uid,
                    type="mention",
                    title=f"You were mentioned in a comment on {task_key}",
                    message=content[:500],
                    entity_type="task",
                    entity_id=task_uuid,
                )
                db.add(notification)

            await db.flush()

            _comment_broadcast = {
                "task_id": str(task_uuid),
                "comment_id": str(comment.id),
                "author_id": str(user_id),
                "body_text": content.strip(),
                "mentioned_user_ids": [uid for uid, _ in mention_users],
            }
            result_msg = f"Added comment to {task_key} '{task_title}'."

        except Exception as e:
            logger.exception("add_task_comment failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback

    # Broadcast AFTER commit (block exit committed)
    if _comment_broadcast:
        comment_data = {
            "id": _comment_broadcast["comment_id"],
            "task_id": _comment_broadcast["task_id"],
            "author_id": _comment_broadcast["author_id"],
            "body_text": _comment_broadcast["body_text"],
        }
        fire_and_forget(handle_comment_added(
            task_id=_comment_broadcast["task_id"],
            comment_data=comment_data,
            mentioned_user_ids=_comment_broadcast["mentioned_user_ids"],
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool 11: delete_task
# ---------------------------------------------------------------------------


@tool
async def delete_task(
    task: str,
) -> str:
    """Permanently delete a task and all its associated data. Requires user confirmation.

    WARNING: This action is irreversible. All comments, checklists, and
    attachments associated with the task will also be deleted.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
    """
    # Resolve task and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_task(task, db)
        if error:
            return error
        task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: Owner/Editor + ProjectMember (same as create_task)
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        task_title = task_obj.title
        project_id = task_obj.project_id
        task_status_id = task_obj.task_status_id

        # Get status name for agg counter update
        status_result = await db.execute(
            select(TaskStatus).where(TaskStatus.id == task_status_id)
        )
        status_obj = status_result.scalar_one_or_none()
        task_status_name = status_obj.name if status_obj else None

    # Build confirmation with extra warning
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "delete_task",
        "summary": (
            f"DELETE task {task_key} '{task_title}' (irreversible). "
            "This will permanently delete the task and all its comments, "
            "checklists, and attachments."
        ),
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "title": task_title,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task deletion cancelled by user."

    # Re-check RBAC + execute delete in single session (TOCTOU mitigation)
    _broadcast_data: dict[str, Any] | None = None
    result_msg: str = ""
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == UUID(str(project_id)),
                    ProjectMember.user_id == user_uuid_check,
                ).limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this task's project."

            # Re-load task to get fresh state
            result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task_obj = result.scalar_one_or_none()
            if not task_obj:
                return f"Error: Task '{task}' no longer exists."

            # Update ProjectTaskStatusAgg counters
            if task_status_name:
                from ....services.status_derivation_service import (
                    update_aggregation_on_task_delete,
                )

                agg_result = await db.execute(
                    select(ProjectTaskStatusAgg).where(
                        ProjectTaskStatusAgg.project_id == project_id
                    )
                )
                agg = agg_result.scalar_one_or_none()
                if agg:
                    update_aggregation_on_task_delete(agg, task_status_name)

            # Delete the task (CASCADE handles comments/checklists/attachments)
            await db.delete(task_obj)
            await db.flush()

            _broadcast_data = {
                "project_id": str(project_id),
                "task_id": str(task_uuid),
                "task_key": task_key,
                "title": task_title,
                "user_id": str(user_uuid_check),
            }
            result_msg = f"Deleted task {task_key} '{task_title}'."

        except Exception as e:
            logger.exception("delete_task failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback

    # Broadcast AFTER commit (block exit committed)
    if _broadcast_data:
        fire_and_forget(handle_task_update(
            project_id=_broadcast_data["project_id"],
            task_id=_broadcast_data["task_id"],
            action=UpdateAction.DELETED,
            task_data=_broadcast_data,
            user_id=_broadcast_data["user_id"],
        ))
    return result_msg


# ---------------------------------------------------------------------------
# Tool registry -- all write tools exported for graph binding
# ---------------------------------------------------------------------------

WRITE_TOOLS = [
    create_task,
    update_task_status,
    assign_task,
    create_document,
    export_to_excel,
    update_document,
    delete_document,
    export_document_pdf,
    update_task,
    add_task_comment,
    delete_task,
]

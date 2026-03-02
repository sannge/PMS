"""Write tools for Blair AI agent — all require HITL confirmation via interrupt().

Four write tools that modify data in the PM Desktop system:
1. create_task — Create a new task in a project
2. update_task_status — Change a task's status
3. assign_task — Assign or reassign a task to a team member
4. create_document — Create a new knowledge base document

All tools:
- Check RBAC BEFORE calling interrupt() (never confirm then deny)
- Use LangGraph interrupt() to pause and request user confirmation
- Use existing SQLAlchemy models for mutations
- Return human-readable confirmation text on success
- Return clear cancellation messages on rejection
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.application import Application
from ...models.document import Document
from ...models.project import Project
from ...models.project_member import ProjectMember
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...models.user import User
from .tools_read import (
    _check_project_access,
    _get_ctx,
    _resolve_application,
    _resolve_project,
)

logger = logging.getLogger(__name__)

# _tool_context is a module-level dict populated at agent setup time.
# Shared with tools_read.py — write tools access user scope and DB session factory.
#
# Keys:
#   user_id: str                      — Current user's UUID
#   accessible_app_ids: list[str]     — UUIDs of accessible applications
#   accessible_project_ids: list[str] — UUIDs of accessible projects
#   db_session_factory: callable      — async_session_maker for creating DB sessions
#   provider_registry: ProviderRegistry — LLM provider registry

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
# Helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: str, label: str) -> UUID:
    """Parse a string to UUID, raising a clear error on failure."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid {label}: '{value}' is not a valid UUID.")


def _strip_markdown(text: str) -> str:
    """Strip markdown formatting to produce plain text for search indexing."""
    # Remove headings
    result = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic
    result = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", result)
    result = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", result)
    # Remove strikethrough
    result = re.sub(r"~~(.+?)~~", r"\1", result)
    # Remove inline code
    result = re.sub(r"`(.+?)`", r"\1", result)
    # Remove links, keep text
    result = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", result)
    # Remove images
    result = re.sub(r"!\[.*?\]\(.+?\)", "", result)
    # Remove horizontal rules
    result = re.sub(r"^---+$", "", result, flags=re.MULTILINE)
    # Remove list markers
    result = re.sub(r"^[\s]*[-*+]\s+", "", result, flags=re.MULTILINE)
    result = re.sub(r"^[\s]*\d+\.\s+", "", result, flags=re.MULTILINE)
    # Remove blockquote markers
    result = re.sub(r"^>\s?", "", result, flags=re.MULTILINE)
    return result.strip()


def _get_db_session() -> AsyncSession:
    """Create a raw database session.

    Callers are responsible for commit/rollback/close.  Prefer
    ``_get_tool_session()`` context manager for automatic lifecycle.
    Kept for backward compatibility with tests that mock this function.
    """
    from ...database import async_session_maker

    return async_session_maker()


@asynccontextmanager
async def _get_tool_session() -> AsyncIterator[AsyncSession]:
    """Provide a database session with automatic rollback on exception, and close.

    Usage::

        async with _get_tool_session() as db:
            ...  # queries
            await db.commit()  # only if needed
    """
    session = _get_db_session()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Tool 1: create_task
# ---------------------------------------------------------------------------


@tool
async def create_task(
    project_id: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    assignee_id: str | None = None,
) -> str:
    """Create a new task in a project. Requires user confirmation before executing.

    Use this when the user wants to create a new task, story, or work item.
    The task will be created with 'Todo' status by default.

    Args:
        project_id: Project UUID or name (partial match supported)
        title: Task title (1-500 characters)
        description: Optional detailed task description
        priority: Optional priority - "lowest", "low", "medium", "high", "highest"
        assignee_id: Optional user UUID to assign the task to
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
        resolved_id, error = await _resolve_project(project_id, db)
        if error:
            return error
        proj_uuid = UUID(resolved_id)
        project_id = resolved_id

        result = await db.execute(
            select(Project).where(Project.id == proj_uuid)
        )
        project = result.scalar_one_or_none()
        if not project:
            return f"Error: Project '{project_id}' not found."

        project_name = project.name
        project_key = project.key

        # Resolve assignee name if provided
        assignee_name: str | None = None
        assignee_uuid: UUID | None = None
        if assignee_id:
            try:
                assignee_uuid = _parse_uuid(assignee_id, "assignee_id")
            except ValueError as e:
                return str(e)

            assignee_result = await db.execute(
                select(User).where(User.id == assignee_uuid)
            )
            assignee_user = assignee_result.scalar_one_or_none()
            if not assignee_user:
                return f"Error: Assignee user '{assignee_id}' not found."
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
        details["assignee_id"] = assignee_id

    summary = f"Create task '{title}' in {project_name}"
    if assignee_name:
        summary += f" (assigned to {assignee_name})"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "create_task",
        "summary": summary,
        "details": details,
    }

    # Pause graph — wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task creation cancelled by user."

    # User approved — execute the write
    async with _get_tool_session() as db:
        try:
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
            user_id = UUID(_get_ctx()["user_id"])

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
            await db.commit()

            result_msg = f"Task '{title}' created in {project_name} (key: {task_key})."
            if assignee_name:
                result_msg += f" Assigned to {assignee_name}."
            return result_msg

        except Exception as e:
            await db.rollback()
            logger.exception("create_task failed: %s", e)
            return "Error creating task. Please try again or contact support."


# ---------------------------------------------------------------------------
# Tool 2: update_task_status
# ---------------------------------------------------------------------------


@tool
async def update_task_status(
    task_id: str,
    new_status: str,
) -> str:
    """Change a task's status. Requires user confirmation before executing.

    Use this when the user wants to move a task to a different status column
    (e.g., from Todo to In Progress, or from In Review to Done).

    Args:
        task_id: The task UUID
        new_status: Target status - "todo", "in_progress", "in_review", "issue", "done"
    """
    # Validate inputs
    try:
        task_uuid = _parse_uuid(task_id, "task_id")
    except ValueError as e:
        return str(e)

    status_key = new_status.lower().strip()
    target_status_name = _STATUS_NAME_MAP.get(status_key)
    if not target_status_name:
        valid = ", ".join(sorted(_STATUS_NAME_MAP.keys()))
        return f"Error: Invalid status '{new_status}'. Must be one of: {valid}."

    # Load task and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        result = await db.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task = result.scalar_one_or_none()
        if not task:
            return f"Error: Task '{task_id}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task.task_key
        task_title = task.title
        project_id = task.project_id

        # Get current status name
        current_status_result = await db.execute(
            select(TaskStatus).where(TaskStatus.id == task.task_status_id)
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
        if task.task_status_id == target_status.id:
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
            "task_id": task_id,
            "task_key": task_key,
            "title": task_title,
            "current_status": current_status_name,
            "new_status": target_status_name,
        },
    }

    # Pause graph — wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task status update cancelled by user."

    # User approved — execute the write
    async with _get_tool_session() as db:
        try:
            # Re-load task to get fresh state (avoid stale data)
            result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task = result.scalar_one_or_none()
            if not task:
                return f"Error: Task '{task_id}' no longer exists."

            # C3: Re-resolve target status post-interrupt (may have changed)
            target_status_result = await db.execute(
                select(TaskStatus).where(
                    TaskStatus.project_id == task.project_id,
                    TaskStatus.name == target_status_name,
                )
            )
            target_status = target_status_result.scalar_one_or_none()
            if not target_status:
                return f"Error: Status '{target_status_name}' no longer exists for this project."

            task.task_status_id = target_status.id
            await db.flush()
            await db.commit()

            return (
                f"Task {task_key} status updated: "
                f"{current_status_name} -> {target_status_name}."
            )

        except Exception as e:
            await db.rollback()
            logger.exception("update_task_status failed: %s", e)
            return "Error updating task status. Please try again or contact support."


# ---------------------------------------------------------------------------
# Tool 3: assign_task
# ---------------------------------------------------------------------------


@tool
async def assign_task(
    task_id: str,
    assignee_id: str,
) -> str:
    """Assign or reassign a task to a team member. Requires user confirmation.

    Use this when the user wants to assign a task to someone, or change
    the current assignee of a task.

    Args:
        task_id: The task UUID
        assignee_id: The user UUID to assign the task to
    """
    # Validate inputs
    try:
        task_uuid = _parse_uuid(task_id, "task_id")
        assignee_uuid = _parse_uuid(assignee_id, "assignee_id")
    except ValueError as e:
        return str(e)

    # Load task, assignee, and validate RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        # Load task
        result = await db.execute(
            select(Task).where(Task.id == task_uuid)
        )
        task = result.scalar_one_or_none()
        if not task:
            return f"Error: Task '{task_id}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task.task_key
        task_title = task.title
        project_id = task.project_id

        # Load assignee user
        assignee_result = await db.execute(
            select(User).where(User.id == assignee_uuid)
        )
        assignee_user = assignee_result.scalar_one_or_none()
        if not assignee_user:
            return f"Error: User '{assignee_id}' not found."
        assignee_name = assignee_user.display_name or assignee_user.email

        # Validate assignee is a project member
        member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == assignee_uuid,
            )
        )
        if not member_result.scalar_one_or_none():
            # Load project name for a better error message
            proj_result = await db.execute(
                select(Project.name).where(Project.id == project_id)
            )
            proj_name = proj_result.scalar_one_or_none() or "this project"
            return (
                f"Error: User '{assignee_name}' is not a member of project "
                f"'{proj_name}'. They must be added as a project member first."
            )

        # Get current assignee name for confirmation message
        current_assignee_name: str | None = None
        if task.assignee_id:
            current_result = await db.execute(
                select(User).where(User.id == task.assignee_id)
            )
            current_assignee = current_result.scalar_one_or_none()
            if current_assignee:
                current_assignee_name = (
                    current_assignee.display_name or current_assignee.email
                )

        # Check if already assigned to this person
        if task.assignee_id == assignee_uuid:
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
            "task_id": task_id,
            "task_key": task_key,
            "title": task_title,
            "assignee_id": assignee_id,
            "assignee_name": assignee_name,
            "previous_assignee": current_assignee_name,
        },
    }

    # Pause graph — wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Task assignment cancelled by user."

    # User approved — execute the write
    async with _get_tool_session() as db:
        try:
            # Re-load task to get fresh state
            result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task = result.scalar_one_or_none()
            if not task:
                return f"Error: Task '{task_id}' no longer exists."

            task.assignee_id = assignee_uuid
            await db.flush()
            await db.commit()

            return f"Task {task_key} assigned to {assignee_name}."

        except Exception as e:
            await db.rollback()
            logger.exception("assign_task failed: %s", e)
            return "Error assigning task. Please try again or contact support."


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
) -> str:
    """Create a new knowledge base document. Requires user confirmation.

    Use this when the user wants to create a new document, specification,
    meeting notes, or any written content in the knowledge base.

    Args:
        title: Document title
        content: Document content in markdown format
        scope: Document scope - "application", "project", or "personal"
        scope_id: Application/project UUID or name (partial match supported), or user UUID for personal scope
        folder_id: Optional target folder UUID to place the document in
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

    user_id_str = _get_ctx()["user_id"]
    user_uuid = UUID(user_id_str)

    # RBAC check BEFORE interrupt — based on scope
    scope_display: str = ""
    scope_uuid: UUID | None = None
    async with _get_tool_session() as db:
        if scope_lower == "application":
            resolved_id, error = await _resolve_application(scope_id, db)
            if error:
                return error
            scope_uuid = UUID(resolved_id)
            # Resolve application name for display
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
            scope_uuid = UUID(resolved_id)
            # Resolve project name for display
            proj_result = await db.execute(
                select(Project).where(Project.id == scope_uuid)
            )
            proj = proj_result.scalar_one_or_none()
            if not proj:
                return f"Error: Project '{scope_id}' not found."
            scope_display = f"project '{proj.name}'"

        elif scope_lower == "personal":
            # Personal scope: scope_id must be a valid UUID matching current user
            try:
                scope_uuid = _parse_uuid(scope_id, "scope_id")
            except ValueError as e:
                return str(e)
            if scope_uuid != user_uuid:
                return "Access denied: personal documents can only be created for yourself."
            scope_display = "your personal space"

        # Resolve folder name if provided, validating it belongs to the same scope
        folder_display: str = ""
        if folder_uuid:
            from ...models.document_folder import DocumentFolder

            folder_where = [DocumentFolder.id == folder_uuid]
            if scope_lower == "application":
                folder_where.append(
                    DocumentFolder.application_id == scope_uuid
                )
            elif scope_lower == "project":
                folder_where.append(
                    DocumentFolder.project_id == scope_uuid
                )
            elif scope_lower == "personal":
                folder_where.append(
                    DocumentFolder.user_id == scope_uuid
                )

            folder_result = await db.execute(
                select(DocumentFolder).where(*folder_where)
            )
            folder = folder_result.scalar_one_or_none()
            if not folder:
                return f"Error: Folder '{folder_id}' not found in this scope."
            folder_display = f" in folder '{folder.name}'"

    # Safety: scope_uuid must always be set by one of the branches above.
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

    # Pause graph — wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Document creation cancelled by user."

    # User approved — execute the write
    async with _get_tool_session() as db:
        try:
            # Build scope columns
            application_id: UUID | None = None
            project_id: UUID | None = None
            doc_user_id: UUID | None = None

            if scope_lower == "application":
                application_id = scope_uuid
            elif scope_lower == "project":
                project_id = scope_uuid
            elif scope_lower == "personal":
                doc_user_id = scope_uuid

            # Convert markdown to plain text for search indexing
            content_plain = _strip_markdown(content)

            # Create the document
            document = Document(
                title=title.strip(),
                content_json=None,
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

            await db.commit()

            # H6: Trigger embedding job so the document is searchable
            try:
                from datetime import timedelta

                from ...services.arq_helper import get_arq_redis

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

            result_msg = (
                f"Document '{title}' created in {scope_display}{folder_display} "
                f"(id: {doc_id})."
            )
            return result_msg

        except Exception as e:
            await db.rollback()
            logger.exception("create_document failed: %s", e)
            return "Error creating document. Please try again or contact support."


# ---------------------------------------------------------------------------
# Tool registry — all write tools exported for graph binding
# ---------------------------------------------------------------------------

WRITE_TOOLS = [create_task, update_task_status, assign_task, create_document]

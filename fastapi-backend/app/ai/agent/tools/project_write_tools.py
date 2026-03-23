"""Project write tools for Blair AI agent -- all require HITL confirmation via interrupt().

Tools that modify Project data in the PM Desktop system:
1. create_project -- Create a new project in an application
2. update_project -- Update project name, description, or due_date
3. delete_project -- Delete a project and all its contents (cascade)

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
from datetime import date, datetime
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import select

from ....models.application import Application
from ....models.application_member import ApplicationMember
from ....models.project import Project
from ....models.project_member import ProjectMember
from ....models.task_status import TaskStatus
from .context import _get_user_id
from .helpers import (
    _get_tool_session,
    _resolve_application,
    _resolve_project,
)

logger = logging.getLogger(__name__)

# Key format: 2-10 chars, starts with letter, uppercase alphanumeric
_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


# ---------------------------------------------------------------------------
# Tool 1: create_project
# ---------------------------------------------------------------------------


@tool
async def create_project(
    app: str,
    name: str,
    key: str,
    description: str = "",
    due_date: str = "",
) -> str:
    """Create a new project in an application. Requires user confirmation before executing.

    Use this when the user wants to create a new project within an application.
    The project will be initialized with 5 default task statuses (Todo, In Progress,
    In Review, Issue, Done) and the creating user will be added as project admin.

    Args:
        app: Application UUID or name (partial match supported)
        name: Project name (1-100 characters)
        key: Project key, uppercase alphanumeric, 2-10 chars (e.g., "SPRINT1")
        description: Optional project description
        due_date: Optional due date in ISO format (YYYY-MM-DD)
    """
    # Validate inputs
    if not name or len(name.strip()) == 0:
        return "Error: Project name is required."
    if len(name) > 100:
        return "Error: Project name must be 100 characters or fewer."

    if not key or len(key.strip()) == 0:
        return "Error: Project key is required."
    key_upper = key.strip().upper()
    if not _KEY_PATTERN.match(key_upper):
        return (
            f"Error: Invalid project key '{key}'. "
            "Key must be 2-10 uppercase alphanumeric characters starting with a letter "
            "(e.g., 'SP', 'PROJ1')."
        )

    if description and len(description) > 50_000:
        return "Error: Description too large. Maximum is 50,000 characters."

    parsed_due_date: date | None = None
    if due_date and due_date.strip():
        try:
            parsed_due_date = datetime.fromisoformat(due_date.strip()).date()
        except ValueError:
            return f"Error: Invalid due_date '{due_date}'. Must be ISO format (YYYY-MM-DD)."

    # Resolve application and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_app_id, error = await _resolve_application(app, db)
        if error:
            return error
        app_uuid = UUID(resolved_app_id)  # type: ignore[arg-type]

        # Load application for display name
        app_result = await db.execute(select(Application).where(Application.id == app_uuid))
        application = app_result.scalar_one_or_none()
        if not application:
            return f"Error: Application '{app}' not found."
        app_name = application.name

        # RBAC: Must be App Owner or Editor
        user_uuid = _get_user_id()
        member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == user_uuid,
            )
        )
        app_member = member_result.scalar_one_or_none()
        if not app_member or app_member.role not in ("owner", "editor"):
            return "Access denied: you must be an application Owner or Editor to create projects."

        # Validate key uniqueness within application
        key_result = await db.execute(
            select(Project.id).where(
                Project.application_id == app_uuid,
                Project.key == key_upper,
            )
        )
        if key_result.scalar_one_or_none() is not None:
            return f"Error: Project key '{key_upper}' already exists in application '{app_name}'."

    # Build confirmation
    summary = f"Create project '{name.strip()}' ({key_upper}) in '{app_name}'"
    details: dict[str, Any] = {
        "application_id": str(app_uuid),
        "application_name": app_name,
        "name": name.strip(),
        "key": key_upper,
    }
    if description:
        details["description"] = description[:200] + ("..." if len(description) > 200 else "")
    if parsed_due_date:
        details["due_date"] = str(parsed_due_date)
        summary += f", due {parsed_due_date}"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "create_project",
        "summary": summary,
        "details": details,
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Project creation cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == user_uuid_check,
                )
            )
            app_member_check = membership.scalar_one_or_none()
            if not app_member_check or app_member_check.role not in ("owner", "editor"):
                return "Access denied: you no longer have permission to create projects in this application."

            # Re-check key uniqueness post-interrupt
            key_check = await db.execute(
                select(Project.id).where(
                    Project.application_id == app_uuid,
                    Project.key == key_upper,
                )
            )
            if key_check.scalar_one_or_none() is not None:
                return f"Error: Project key '{key_upper}' was taken while waiting for confirmation."

            user_id = _get_user_id()

            # Create the project
            project = Project(
                application_id=app_uuid,
                name=name.strip(),
                key=key_upper,
                description=description if description else None,
                due_date=parsed_due_date,
                created_by=user_id,
                project_owner_user_id=user_id,
            )
            db.add(project)
            await db.flush()

            # Create 5 default TaskStatus records
            statuses = TaskStatus.create_default_statuses(project.id)
            for status in statuses:
                db.add(status)
            await db.flush()

            # Create ProjectMember for the creating user as admin
            pm = ProjectMember(
                project_id=project.id,
                user_id=user_id,
                role="admin",
                added_by_user_id=user_id,
            )
            db.add(pm)
            await db.flush()

            return (
                f"Project '{name.strip()}' created in '{app_name}' "
                f"(key: {key_upper}, id: {project.id}). "
                f"5 default statuses and admin membership configured."
            )

        except Exception as e:
            logger.exception("create_project failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 2: update_project
# ---------------------------------------------------------------------------


@tool
async def update_project(
    project: str,
    name: str = "",
    description: str = "",
    due_date: str = "",
) -> str:
    """Update a project's details. Requires user confirmation before executing.

    Use this when the user wants to change a project's name, description, or due date.
    Only provided (non-empty) fields will be updated.

    Args:
        project: Project UUID or name (partial match supported)
        name: New project name (1-100 characters, leave empty to skip)
        description: New description (leave empty to skip)
        due_date: New due date in ISO format, or "clear" to remove (leave empty to skip)
    """
    # Validate at least one field provided
    if not name.strip() and not description.strip() and not due_date.strip():
        return "Error: At least one field (name, description, due_date) must be provided."

    if name and len(name) > 100:
        return "Error: Project name must be 100 characters or fewer."

    if description and len(description) > 50_000:
        return "Error: Description too large. Maximum is 50,000 characters."

    parsed_due_date: date | None = None
    clear_due_date = False
    if due_date and due_date.strip():
        if due_date.strip().lower() == "clear":
            clear_due_date = True
        else:
            try:
                parsed_due_date = datetime.fromisoformat(due_date.strip()).date()
            except ValueError:
                return f"Error: Invalid due_date '{due_date}'. Must be ISO format (YYYY-MM-DD) or 'clear'."

    # Resolve project and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_project(project, db)
        if error:
            return error
        proj_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(select(Project).where(Project.id == proj_uuid))
        proj = result.scalar_one_or_none()
        if not proj:
            return f"Error: Project '{project}' not found."

        project_name = proj.name
        app_id = proj.application_id

        # RBAC: Must be App Owner or Editor
        user_uuid = _get_user_id()
        member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == user_uuid,
            )
        )
        app_member = member_result.scalar_one_or_none()
        if not app_member or app_member.role not in ("owner", "editor"):
            return "Access denied: you must be an application Owner or Editor to update projects."

    # Build confirmation
    changes: list[str] = []
    if name.strip():
        changes.append(f"name -> '{name.strip()}'")
    if description.strip():
        changes.append(f"description -> '{description[:80]}{'...' if len(description) > 80 else ''}'")
    if clear_due_date:
        changes.append("due_date -> (cleared)")
    elif parsed_due_date:
        changes.append(f"due_date -> {parsed_due_date}")

    summary = f"Update project '{project_name}': {', '.join(changes)}"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "update_project",
        "summary": summary,
        "details": {
            "project_id": str(proj_uuid),
            "project_name": project_name,
            "changes": changes,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Project update cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            member_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_id,
                    ApplicationMember.user_id == user_uuid_check,
                )
            )
            app_member_check = member_result.scalar_one_or_none()
            if not app_member_check or app_member_check.role not in ("owner", "editor"):
                return "Access denied: you no longer have permission to update this project."

            result = await db.execute(select(Project).where(Project.id == proj_uuid))
            proj = result.scalar_one_or_none()
            if not proj:
                return f"Error: Project '{project}' no longer exists."

            if name.strip():
                proj.name = name.strip()
            if description.strip():
                proj.description = description.strip()
            if clear_due_date:
                proj.due_date = None
            elif parsed_due_date:
                proj.due_date = parsed_due_date

            await db.flush()

            return f"Project '{project_name}' updated: {', '.join(changes)}."

        except Exception as e:
            logger.exception("update_project failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 3: delete_project
# ---------------------------------------------------------------------------


@tool
async def delete_project(
    project: str,
) -> str:
    """Delete a project and all its contents. Requires user confirmation before executing.

    WARNING: This is irreversible. All tasks, checklists, comments, documents,
    and other data within the project will be permanently deleted via cascade.

    Args:
        project: Project UUID or name (partial match supported)
    """
    # Resolve project and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_project(project, db)
        if error:
            return error
        proj_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(select(Project).where(Project.id == proj_uuid))
        proj = result.scalar_one_or_none()
        if not proj:
            return f"Error: Project '{project}' not found."

        project_name = proj.name
        project_key = proj.key
        app_id = proj.application_id

        # RBAC: Must be App Owner OR Project Admin
        user_uuid = _get_user_id()

        # Check ApplicationMember role
        app_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == user_uuid,
            )
        )
        app_member = app_member_result.scalar_one_or_none()
        is_app_owner = app_member is not None and app_member.role == "owner"

        # Check ProjectMember role
        proj_member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj_uuid,
                ProjectMember.user_id == user_uuid,
            )
        )
        proj_member = proj_member_result.scalar_one_or_none()
        is_project_admin = proj_member is not None and proj_member.role == "admin"

        if not is_app_owner and not is_project_admin:
            return "Access denied: you must be an application Owner or project Admin to delete projects."

    # Build confirmation with extra cascade warning
    summary = f"DELETE project '{project_name}' ({project_key}) and all its contents (irreversible)"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "delete_project",
        "summary": summary,
        "details": {
            "project_id": str(proj_uuid),
            "project_name": project_name,
            "project_key": project_key,
            "warning": (
                "This will permanently delete all tasks, checklists, comments, "
                "documents, and other data within this project."
            ),
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Project deletion cancelled by user."

    # Re-check RBAC + execute delete in single session (TOCTOU mitigation)
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()

            app_member_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_id,
                    ApplicationMember.user_id == user_uuid_check,
                )
            )
            app_member_check = app_member_result.scalar_one_or_none()
            is_app_owner_check = app_member_check is not None and app_member_check.role == "owner"

            proj_member_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == proj_uuid,
                    ProjectMember.user_id == user_uuid_check,
                )
            )
            proj_member_check = proj_member_result.scalar_one_or_none()
            is_project_admin_check = proj_member_check is not None and proj_member_check.role == "admin"

            if not is_app_owner_check and not is_project_admin_check:
                return "Access denied: you no longer have permission to delete this project."

            result = await db.execute(select(Project).where(Project.id == proj_uuid))
            proj = result.scalar_one_or_none()
            if not proj:
                return f"Error: Project '{project}' no longer exists."

            await db.delete(proj)
            await db.flush()

            return f"Project '{project_name}' ({project_key}) and all its contents have been permanently deleted."

        except Exception as e:
            logger.exception("delete_project failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool registry -- all project write tools exported for graph binding
# ---------------------------------------------------------------------------

PROJECT_WRITE_TOOLS = [
    create_project,
    update_project,
    delete_project,
]

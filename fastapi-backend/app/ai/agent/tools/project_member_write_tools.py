"""Project member write tools for Blair AI agent -- all require HITL confirmation.

Tools that modify ProjectMember data in the PM Desktop system:
1. add_project_member -- Add a user to a project team
2. update_project_member_role -- Change a member's role (admin/member)
3. remove_project_member -- Remove a user from a project team

All tools:
- Check RBAC BEFORE calling interrupt() (never confirm then deny)
- Use LangGraph interrupt() to pause and request user confirmation
- Use existing SQLAlchemy models for mutations
- Return human-readable confirmation text on success
- Return clear cancellation messages on rejection
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import func, select

from ....models.application_member import ApplicationMember
from ....models.project import Project
from ....models.project_member import ProjectMember
from ....models.task import Task
from ....models.task_status import TaskStatus
from ....models.user import User
from .context import _get_user_id
from .helpers import (
    _get_tool_session,
    _resolve_project,
    _resolve_user,
)

logger = logging.getLogger(__name__)

_VALID_PROJECT_ROLES = {"admin", "member"}


# ---------------------------------------------------------------------------
# Tool 1: add_project_member
# ---------------------------------------------------------------------------


@tool
async def add_project_member(
    project: str,
    user: str,
    role: str = "member",
) -> str:
    """Add a user to a project team. Requires user confirmation before executing.

    Use this when the user wants to add someone to a project. The target user
    must already be a member of the parent application (Owner or Editor role).

    Args:
        project: Project UUID or name (partial match supported)
        user: User UUID, email, or display name of the person to add
        role: Project role - "admin" or "member" (default: "member")
    """
    # Validate role
    role_lower = role.strip().lower()
    if role_lower not in _VALID_PROJECT_ROLES:
        return f"Error: Invalid role '{role}'. Must be 'admin' or 'member'."

    # Resolve project and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_proj_id, error = await _resolve_project(project, db)
        if error:
            return error
        proj_uuid = UUID(resolved_proj_id)  # type: ignore[arg-type]

        # Load project
        proj_result = await db.execute(select(Project).where(Project.id == proj_uuid))
        proj = proj_result.scalar_one_or_none()
        if not proj:
            return f"Error: Project '{project}' not found."

        project_name = proj.name
        app_id = proj.application_id

        # RBAC: Must be App Owner or Project Admin
        current_user_uuid = _get_user_id()

        app_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == current_user_uuid,
            )
        )
        app_member = app_member_result.scalar_one_or_none()
        is_app_owner = app_member is not None and app_member.role == "owner"

        proj_member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj_uuid,
                ProjectMember.user_id == current_user_uuid,
            )
        )
        proj_member = proj_member_result.scalar_one_or_none()
        is_project_admin = proj_member is not None and proj_member.role == "admin"

        if not is_app_owner and not is_project_admin:
            return "Access denied: you must be an application Owner or project Admin to add project members."

        # Resolve target user
        resolved_user_id, user_err = await _resolve_user(user, db, scope_app_id=str(app_id))
        if user_err:
            return user_err
        target_uuid = UUID(resolved_user_id)  # type: ignore[arg-type]

        # Load target user for display
        user_result = await db.execute(select(User).where(User.id == target_uuid))
        target_user = user_result.scalar_one_or_none()
        if not target_user:
            return f"Error: User '{user}' not found."
        target_name = target_user.display_name or target_user.email

        # Validate: target must be an app member (Owner or Editor)
        target_app_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == target_uuid,
            )
        )
        target_app_member = target_app_member_result.scalar_one_or_none()
        if not target_app_member or target_app_member.role not in ("owner", "editor"):
            return (
                f"Error: User '{target_name}' must be an application Owner or Editor "
                f"before they can be added to a project."
            )

        # Validate: not already a project member
        existing_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj_uuid,
                ProjectMember.user_id == target_uuid,
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            return f"Error: User '{target_name}' is already a member of project '{project_name}'."

    # Build confirmation
    summary = f"Add {target_name} as {role_lower} to project '{project_name}'"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "add_project_member",
        "summary": summary,
        "details": {
            "project_id": str(proj_uuid),
            "project_name": project_name,
            "user_id": str(target_uuid),
            "user_name": target_name,
            "role": role_lower,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Add project member cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
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
                return "Access denied: you no longer have permission to manage project members."

            # Re-check not already a member post-interrupt
            existing_check = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == proj_uuid,
                    ProjectMember.user_id == target_uuid,
                )
            )
            if existing_check.scalar_one_or_none() is not None:
                return (
                    f"Error: User '{target_name}' was added to project '{project_name}' while waiting for confirmation."
                )

            current_user_id = _get_user_id()

            pm = ProjectMember(
                project_id=proj_uuid,
                user_id=target_uuid,
                role=role_lower,
                added_by_user_id=current_user_id,
            )
            db.add(pm)
            await db.flush()

            return f"{target_name} added as {role_lower} to project '{project_name}'."

        except Exception as e:
            logger.exception("add_project_member failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 2: update_project_member_role
# ---------------------------------------------------------------------------


@tool
async def update_project_member_role(
    project: str,
    user: str,
    new_role: str,
) -> str:
    """Change a project member's role. Requires user confirmation before executing.

    Use this when the user wants to promote or demote someone in a project
    (e.g., change from member to admin, or admin to member).

    Args:
        project: Project UUID or name (partial match supported)
        user: User UUID, email, or display name of the member
        new_role: New role - "admin" or "member"
    """
    # Validate role
    role_lower = new_role.strip().lower()
    if role_lower not in _VALID_PROJECT_ROLES:
        return f"Error: Invalid role '{new_role}'. Must be 'admin' or 'member'."

    # Resolve project and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_proj_id, error = await _resolve_project(project, db)
        if error:
            return error
        proj_uuid = UUID(resolved_proj_id)  # type: ignore[arg-type]

        # Load project
        proj_result = await db.execute(select(Project).where(Project.id == proj_uuid))
        proj = proj_result.scalar_one_or_none()
        if not proj:
            return f"Error: Project '{project}' not found."

        project_name = proj.name
        app_id = proj.application_id

        # RBAC: Must be App Owner or Project Admin
        current_user_uuid = _get_user_id()

        app_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == current_user_uuid,
            )
        )
        app_member = app_member_result.scalar_one_or_none()
        is_app_owner = app_member is not None and app_member.role == "owner"

        proj_member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj_uuid,
                ProjectMember.user_id == current_user_uuid,
            )
        )
        current_proj_member = proj_member_result.scalar_one_or_none()
        is_project_admin = current_proj_member is not None and current_proj_member.role == "admin"

        if not is_app_owner and not is_project_admin:
            return "Access denied: you must be an application Owner or project Admin to change member roles."

        # Resolve target user
        resolved_user_id, user_err = await _resolve_user(user, db, scope_project_id=str(proj_uuid))
        if user_err:
            return user_err
        target_uuid = UUID(resolved_user_id)  # type: ignore[arg-type]

        # Load target user for display
        user_result = await db.execute(select(User).where(User.id == target_uuid))
        target_user = user_result.scalar_one_or_none()
        if not target_user:
            return f"Error: User '{user}' not found."
        target_name = target_user.display_name or target_user.email

        # Find their ProjectMember record
        target_pm_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj_uuid,
                ProjectMember.user_id == target_uuid,
            )
        )
        target_pm = target_pm_result.scalar_one_or_none()
        if not target_pm:
            return f"Error: User '{target_name}' is not a member of project '{project_name}'."

        current_role = target_pm.role

        if current_role == role_lower:
            return (
                f"User '{target_name}' already has the '{role_lower}' role in "
                f"project '{project_name}'. No change needed."
            )

    # Build confirmation
    summary = f"Change {target_name}'s role to {role_lower} in project '{project_name}'"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "update_project_member_role",
        "summary": summary,
        "details": {
            "project_id": str(proj_uuid),
            "project_name": project_name,
            "user_id": str(target_uuid),
            "user_name": target_name,
            "current_role": current_role,
            "new_role": role_lower,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Role update cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
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
                return "Access denied: you no longer have permission to manage project members."

            # Re-load the ProjectMember record
            target_pm_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == proj_uuid,
                    ProjectMember.user_id == target_uuid,
                )
            )
            target_pm = target_pm_result.scalar_one_or_none()
            if not target_pm:
                return f"Error: User '{target_name}' is no longer a member of project '{project_name}'."

            target_pm.role = role_lower
            await db.flush()

            return f"{target_name}'s role updated to {role_lower} in project '{project_name}'."

        except Exception as e:
            logger.exception("update_project_member_role failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 3: remove_project_member
# ---------------------------------------------------------------------------


@tool
async def remove_project_member(
    project: str,
    user: str,
) -> str:
    """Remove a user from a project team. Requires user confirmation before executing.

    Use this when the user wants to remove someone from a project. The removal
    will be blocked if the target user has active tasks (not Done or Archived)
    in the project.

    Args:
        project: Project UUID or name (partial match supported)
        user: User UUID, email, or display name of the member to remove
    """
    # Resolve project and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_proj_id, error = await _resolve_project(project, db)
        if error:
            return error
        proj_uuid = UUID(resolved_proj_id)  # type: ignore[arg-type]

        # Load project
        proj_result = await db.execute(select(Project).where(Project.id == proj_uuid))
        proj = proj_result.scalar_one_or_none()
        if not proj:
            return f"Error: Project '{project}' not found."

        project_name = proj.name
        app_id = proj.application_id

        # RBAC: Must be App Owner or Project Admin
        current_user_uuid = _get_user_id()

        app_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == current_user_uuid,
            )
        )
        app_member = app_member_result.scalar_one_or_none()
        is_app_owner = app_member is not None and app_member.role == "owner"

        proj_member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj_uuid,
                ProjectMember.user_id == current_user_uuid,
            )
        )
        current_proj_member = proj_member_result.scalar_one_or_none()
        is_project_admin = current_proj_member is not None and current_proj_member.role == "admin"

        if not is_app_owner and not is_project_admin:
            return "Access denied: you must be an application Owner or project Admin to remove project members."

        # Resolve target user
        resolved_user_id, user_err = await _resolve_user(user, db, scope_project_id=str(proj_uuid))
        if user_err:
            return user_err
        target_uuid = UUID(resolved_user_id)  # type: ignore[arg-type]

        # Load target user for display
        user_result = await db.execute(select(User).where(User.id == target_uuid))
        target_user = user_result.scalar_one_or_none()
        if not target_user:
            return f"Error: User '{user}' not found."
        target_name = target_user.display_name or target_user.email

        # Verify they are a project member
        target_pm_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == proj_uuid,
                ProjectMember.user_id == target_uuid,
            )
        )
        target_pm = target_pm_result.scalar_one_or_none()
        if not target_pm:
            return f"Error: User '{target_name}' is not a member of project '{project_name}'."

        # Block if user has active tasks (not Done/Archived)
        # Active = tasks where status is not "Done" and task is not archived
        done_status_subq = select(TaskStatus.id).where(
            TaskStatus.project_id == proj_uuid,
            TaskStatus.name == "Done",
        )
        active_task_count_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == proj_uuid,
                Task.assignee_id == target_uuid,
                Task.archived_at.is_(None),
                Task.task_status_id.notin_(done_status_subq),
            )
        )
        active_count = active_task_count_result.scalar() or 0

        if active_count > 0:
            return (
                f"Error: Cannot remove '{target_name}' from project '{project_name}'. "
                f"They have {active_count} active task(s) (not Done/Archived). "
                f"Please reassign or complete their tasks first."
            )

    # Build confirmation
    summary = f"Remove {target_name} from project '{project_name}'"

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "remove_project_member",
        "summary": summary,
        "details": {
            "project_id": str(proj_uuid),
            "project_name": project_name,
            "user_id": str(target_uuid),
            "user_name": target_name,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Member removal cancelled by user."

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
                return "Access denied: you no longer have permission to manage project members."

            # Re-load the ProjectMember record
            target_pm_result = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == proj_uuid,
                    ProjectMember.user_id == target_uuid,
                )
            )
            target_pm = target_pm_result.scalar_one_or_none()
            if not target_pm:
                return f"Error: User '{target_name}' is no longer a member of project '{project_name}'."

            await db.delete(target_pm)
            await db.flush()

            return f"{target_name} removed from project '{project_name}'."

        except Exception as e:
            logger.exception("remove_project_member failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool registry -- all project member write tools exported for graph binding
# ---------------------------------------------------------------------------

PROJECT_MEMBER_WRITE_TOOLS = [
    add_project_member,
    update_project_member_role,
    remove_project_member,
]

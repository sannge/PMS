"""Member write tools for Blair AI agent -- all require HITL confirmation via interrupt().

Tools that modify application membership data:
1. add_application_member -- Add a user to an application
2. update_application_member_role -- Change a member's role
3. remove_application_member -- Remove a member from an application

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
from sqlalchemy import func, or_, select

from ....models.application import Application
from ....models.application_member import ApplicationMember
from ....models.project import Project
from ....models.project_member import ProjectMember
from ....models.task import Task
from ....models.task_status import TaskStatus
from ....models.user import User
from .context import _get_user_id
from .helpers import (
    _escape_ilike,
    _get_tool_session,
    _resolve_application,
)

logger = logging.getLogger(__name__)

# Valid application member roles
_VALID_ROLES = {"owner", "editor", "viewer"}

# Roles that each actor role can assign
_ASSIGNABLE_ROLES: dict[str, set[str]] = {
    "owner": {"owner", "editor", "viewer"},
    "editor": {"editor", "viewer"},
}


# ---------------------------------------------------------------------------
# Tool 1: add_application_member
# ---------------------------------------------------------------------------


@tool
async def add_application_member(
    app: str,
    email: str,
    role: str,
) -> str:
    """Add a user to an application as a member. Requires user confirmation.

    Use this when the user wants to add someone to an application team.
    The target user must already have an account (use the invitation system
    for external users).

    Args:
        app: Application UUID or name (partial match supported)
        email: Email address of the user to add
        role: Role to assign - "owner", "editor", or "viewer"
    """
    # Validate role
    role_lower = role.lower().strip()
    if role_lower not in _VALID_ROLES:
        return f"Error: Invalid role '{role}'. Must be one of: owner, editor, viewer."

    if not email or not email.strip():
        return "Error: Email address is required."

    user_id = _get_user_id()

    # Resolve application and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_application(app, db)
        if error:
            return error
        app_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        # Load application
        result = await db.execute(
            select(Application).where(Application.id == app_uuid)
        )
        app_obj = result.scalar_one_or_none()
        if not app_obj:
            return f"Error: Application '{app}' not found."

        app_name = app_obj.name

        # RBAC: check actor's role
        actor_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == user_id,
            )
        )
        actor_member = actor_result.scalar_one_or_none()
        if not actor_member:
            return "Access denied: you are not a member of this application."

        actor_role = actor_member.role
        if actor_role == "viewer":
            return "You don't have permission to add members. Only owners and editors can add members."

        # Check role hierarchy
        if role_lower not in _ASSIGNABLE_ROLES.get(actor_role, set()):
            return (
                f"Access denied: as an {actor_role}, you cannot add members "
                f"with the '{role_lower}' role."
            )

        # Look up target user by email
        target_result = await db.execute(
            select(User).where(User.email == email.strip().lower())
        )
        target_user = target_result.scalar_one_or_none()
        if not target_user:
            return (
                f"No user found with email '{email}'. "
                "Use the invitation system to invite external users."
            )

        target_user_id = target_user.id
        target_display = target_user.display_name or target_user.email

        # Check if already a member
        existing_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == target_user_id,
            )
        )
        if existing_result.scalar_one_or_none():
            return (
                f"User '{target_display}' is already a member of '{app_name}'. "
                "Use update_application_member_role to change their role."
            )

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "add_application_member",
        "summary": f"Add {email} as {role_lower.capitalize()} to '{app_name}'",
        "details": {
            "application_id": str(app_uuid),
            "application_name": app_name,
            "email": email,
            "user_name": target_display,
            "role": role_lower,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Member addition cancelled by user."

    # TOCTOU: Re-check RBAC + execute write in single session
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            actor_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == user_uuid_check,
                )
            )
            actor_member = actor_result.scalar_one_or_none()
            if not actor_member:
                return "Access denied: you are no longer a member of this application."
            if actor_member.role == "viewer":
                return "Access denied: you no longer have permission to add members."
            if role_lower not in _ASSIGNABLE_ROLES.get(actor_member.role, set()):
                return "Access denied: your role has changed and you can no longer assign this role."

            # Re-check user not already a member (TOCTOU)
            existing_result = await db.execute(
                select(ApplicationMember.id).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == target_user_id,
                )
            )
            if existing_result.scalar_one_or_none():
                return f"User '{target_display}' was added to '{app_name}' while waiting for approval."

            member = ApplicationMember(
                application_id=app_uuid,
                user_id=target_user_id,
                role=role_lower,
            )
            db.add(member)
            await db.flush()

            return f"Added {target_display} as {role_lower.capitalize()} to '{app_name}'."

        except Exception as e:
            logger.exception("add_application_member failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 2: update_application_member_role
# ---------------------------------------------------------------------------


@tool
async def update_application_member_role(
    app: str,
    user: str,
    new_role: str,
) -> str:
    """Change a member's role in an application. Requires user confirmation.

    Use this when the user wants to promote or demote someone's access level
    within an application.

    Args:
        app: Application UUID or name (partial match supported)
        user: User UUID, email, or display name of the member
        new_role: New role - "owner", "editor", or "viewer"
    """
    # Validate role
    role_lower = new_role.lower().strip()
    if role_lower not in _VALID_ROLES:
        return f"Error: Invalid role '{new_role}'. Must be one of: owner, editor, viewer."

    if not user or not user.strip():
        return "Error: User identifier is required."

    user_id = _get_user_id()

    # Resolve application and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_application(app, db)
        if error:
            return error
        app_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        # Load application
        result = await db.execute(
            select(Application).where(Application.id == app_uuid)
        )
        app_obj = result.scalar_one_or_none()
        if not app_obj:
            return f"Error: Application '{app}' not found."

        app_name = app_obj.name

        # RBAC: check actor's role
        actor_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == user_id,
            )
        )
        actor_member = actor_result.scalar_one_or_none()
        if not actor_member:
            return "Access denied: you are not a member of this application."

        actor_role = actor_member.role
        if actor_role == "viewer":
            return "Access denied: viewers cannot change member roles."

        # Resolve target user by UUID, email, or display name
        target_user_obj: User | None = None

        # Try UUID first
        try:
            target_uuid = UUID(user)
            target_result = await db.execute(
                select(User).where(User.id == target_uuid)
            )
            target_user_obj = target_result.scalar_one_or_none()
        except (ValueError, AttributeError):
            pass

        # Try email/display name
        if target_user_obj is None:
            escaped = _escape_ilike(user)
            target_result = await db.execute(
                select(User).where(
                    or_(
                        User.email.ilike(f"%{escaped}%", escape="\\"),
                        User.display_name.ilike(f"%{escaped}%", escape="\\"),
                    )
                ).limit(10)
            )
            matches = target_result.scalars().all()
            if len(matches) == 1:
                target_user_obj = matches[0]
            elif len(matches) == 0:
                return f"No user found matching '{user}'."
            else:
                names = ", ".join(
                    f"'{m.display_name or m.email}'" for m in matches[:5]
                )
                return f"Multiple users match '{user}': {names}. Please be more specific."

        if target_user_obj is None:
            return f"No user found matching '{user}'."

        target_user_id = target_user_obj.id
        target_display = target_user_obj.display_name or target_user_obj.email

        # Find target's membership
        target_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == target_user_id,
            )
        )
        target_member = target_member_result.scalar_one_or_none()
        if not target_member:
            return f"User '{target_display}' is not a member of '{app_name}'."

        current_role = target_member.role

        # Check if already in target role
        if current_role == role_lower:
            return (
                f"User '{target_display}' is already a {role_lower.capitalize()} "
                f"in '{app_name}'. No change needed."
            )

        # Editor restrictions
        if actor_role == "editor":
            # Editors can only change viewer -> editor
            if not (current_role == "viewer" and role_lower == "editor"):
                return (
                    "Access denied: as an editor, you can only promote viewers to editors."
                )

        # Last owner protection
        if current_role == "owner" and role_lower != "owner":
            owner_count_result = await db.execute(
                select(func.count(ApplicationMember.id)).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.role == "owner",
                )
            )
            owner_count = owner_count_result.scalar() or 0
            if owner_count <= 1:
                return (
                    f"Cannot change role: '{target_display}' is the last owner of "
                    f"'{app_name}'. Promote another member to owner first."
                )

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "update_application_member_role",
        "summary": (
            f"Change {target_display}'s role from {current_role.capitalize()} "
            f"to {role_lower.capitalize()} in '{app_name}'"
        ),
        "details": {
            "application_id": str(app_uuid),
            "application_name": app_name,
            "user_id": str(target_user_id),
            "user_name": target_display,
            "current_role": current_role,
            "new_role": role_lower,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Role update cancelled by user."

    # TOCTOU: Re-check RBAC + execute write in single session
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            actor_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == user_uuid_check,
                )
            )
            actor_member = actor_result.scalar_one_or_none()
            if not actor_member:
                return "Access denied: you are no longer a member of this application."
            if actor_member.role == "viewer":
                return "Access denied: your role has changed and you can no longer update member roles."

            target_member_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == target_user_id,
                )
            )
            target_member = target_member_result.scalar_one_or_none()
            if not target_member:
                return f"User '{target_display}' is no longer a member of '{app_name}'."

            # Re-check last owner protection post-interrupt
            if target_member.role == "owner" and role_lower != "owner":
                owner_count_result = await db.execute(
                    select(func.count(ApplicationMember.id)).where(
                        ApplicationMember.application_id == app_uuid,
                        ApplicationMember.role == "owner",
                    )
                )
                owner_count = owner_count_result.scalar() or 0
                if owner_count <= 1:
                    return (
                        f"Cannot change role: '{target_display}' is the last owner of "
                        f"'{app_name}'. Promote another member to owner first."
                    )

            target_member.role = role_lower
            await db.flush()

            return (
                f"Changed {target_display}'s role from {current_role.capitalize()} "
                f"to {role_lower.capitalize()} in '{app_name}'."
            )

        except Exception as e:
            logger.exception("update_application_member_role failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 3: remove_application_member
# ---------------------------------------------------------------------------


@tool
async def remove_application_member(
    app: str,
    user: str,
) -> str:
    """Remove a member from an application. Requires user confirmation.

    Use this when the user wants to remove someone from an application team.
    Only owners can remove other members (any member can remove themselves).

    Args:
        app: Application UUID or name (partial match supported)
        user: User UUID, email, or display name of the member to remove
    """
    if not user or not user.strip():
        return "Error: User identifier is required."

    user_id = _get_user_id()

    # Resolve application and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_application(app, db)
        if error:
            return error
        app_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        # Load application
        result = await db.execute(
            select(Application).where(Application.id == app_uuid)
        )
        app_obj = result.scalar_one_or_none()
        if not app_obj:
            return f"Error: Application '{app}' not found."

        app_name = app_obj.name

        # RBAC: check actor's role
        actor_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == user_id,
            )
        )
        actor_member = actor_result.scalar_one_or_none()
        if not actor_member:
            return "Access denied: you are not a member of this application."

        actor_role = actor_member.role

        # Resolve target user by UUID, email, or display name
        target_user_obj: User | None = None

        # Try UUID first
        try:
            target_uuid = UUID(user)
            target_result = await db.execute(
                select(User).where(User.id == target_uuid)
            )
            target_user_obj = target_result.scalar_one_or_none()
        except (ValueError, AttributeError):
            pass

        # Try email/display name
        if target_user_obj is None:
            escaped = _escape_ilike(user)
            target_result = await db.execute(
                select(User).where(
                    or_(
                        User.email.ilike(f"%{escaped}%", escape="\\"),
                        User.display_name.ilike(f"%{escaped}%", escape="\\"),
                    )
                ).limit(10)
            )
            matches = target_result.scalars().all()
            if len(matches) == 1:
                target_user_obj = matches[0]
            elif len(matches) == 0:
                return f"No user found matching '{user}'."
            else:
                names = ", ".join(
                    f"'{m.display_name or m.email}'" for m in matches[:5]
                )
                return f"Multiple users match '{user}': {names}. Please be more specific."

        if target_user_obj is None:
            return f"No user found matching '{user}'."

        target_user_id = target_user_obj.id
        target_display = target_user_obj.display_name or target_user_obj.email
        is_self_removal = target_user_id == user_id

        # RBAC: owner only (except self-removal)
        if not is_self_removal and actor_role != "owner":
            return "Access denied: only owners can remove other members."

        # Find target's membership
        target_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == target_user_id,
            )
        )
        target_member = target_member_result.scalar_one_or_none()
        if not target_member:
            return f"User '{target_display}' is not a member of '{app_name}'."

        # Cannot remove last owner
        if target_member.role == "owner":
            owner_count_result = await db.execute(
                select(func.count(ApplicationMember.id)).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.role == "owner",
                )
            )
            owner_count = owner_count_result.scalar() or 0
            if owner_count <= 1:
                return (
                    f"Cannot remove '{target_display}': they are the last owner of "
                    f"'{app_name}'. Transfer ownership to another member first."
                )

        # Check for active tasks in any project within the app
        project_ids_result = await db.execute(
            select(Project.id).where(
                Project.application_id == app_uuid,
                Project.archived_at.is_(None),
            )
        )
        project_ids = [row[0] for row in project_ids_result.all()]

        if project_ids:
            # Find "Done" status IDs for these projects
            done_status_result = await db.execute(
                select(TaskStatus.id).where(
                    TaskStatus.project_id.in_(project_ids),
                    TaskStatus.name == "Done",
                )
            )
            done_status_ids = [row[0] for row in done_status_result.all()]

            # Count active tasks (not archived, not done) assigned to the user
            active_task_query = select(func.count(Task.id)).where(
                Task.project_id.in_(project_ids),
                Task.assignee_id == target_user_id,
                Task.archived_at.is_(None),
            )
            if done_status_ids:
                active_task_query = active_task_query.where(
                    Task.task_status_id.notin_(done_status_ids),
                )
            active_count_result = await db.execute(active_task_query)
            active_count = active_count_result.scalar() or 0

            if active_count > 0:
                return (
                    f"Cannot remove '{target_display}' from '{app_name}': "
                    f"they have {active_count} active task{'s' if active_count > 1 else ''} "
                    f"in projects within this application. Reassign or complete those tasks first."
                )

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "remove_application_member",
        "summary": f"Remove {target_display} from '{app_name}'",
        "details": {
            "application_id": str(app_uuid),
            "application_name": app_name,
            "user_id": str(target_user_id),
            "user_name": target_display,
            "role": target_member.role,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Member removal cancelled by user."

    # TOCTOU: Re-check RBAC + execute delete in single session
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            # For self-removal, just check membership exists
            if is_self_removal:
                actor_result = await db.execute(
                    select(ApplicationMember.id).where(
                        ApplicationMember.application_id == app_uuid,
                        ApplicationMember.user_id == user_uuid_check,
                    )
                )
                if actor_result.scalar_one_or_none() is None:
                    return "You are no longer a member of this application."
            else:
                actor_result = await db.execute(
                    select(ApplicationMember).where(
                        ApplicationMember.application_id == app_uuid,
                        ApplicationMember.user_id == user_uuid_check,
                    )
                )
                actor_member = actor_result.scalar_one_or_none()
                if not actor_member or actor_member.role != "owner":
                    return "Access denied: you are no longer an owner of this application."

            # Re-fetch target membership
            target_member_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == target_user_id,
                )
            )
            target_member = target_member_result.scalar_one_or_none()
            if not target_member:
                return f"User '{target_display}' is no longer a member of '{app_name}'."

            # Re-check last owner protection
            if target_member.role == "owner":
                owner_count_result = await db.execute(
                    select(func.count(ApplicationMember.id)).where(
                        ApplicationMember.application_id == app_uuid,
                        ApplicationMember.role == "owner",
                    )
                )
                owner_count = owner_count_result.scalar() or 0
                if owner_count <= 1:
                    return (
                        f"Cannot remove '{target_display}': they are the last owner of "
                        f"'{app_name}'. Transfer ownership first."
                    )

            # Delete the membership
            await db.delete(target_member)

            # Cascade: remove ProjectMember records for the user in all app projects
            project_ids_result = await db.execute(
                select(Project.id).where(Project.application_id == app_uuid)
            )
            project_ids = [row[0] for row in project_ids_result.all()]

            if project_ids:
                pm_result = await db.execute(
                    select(ProjectMember).where(
                        ProjectMember.project_id.in_(project_ids),
                        ProjectMember.user_id == target_user_id,
                    )
                )
                for pm in pm_result.scalars().all():
                    await db.delete(pm)

            await db.flush()

            return f"Removed {target_display} from '{app_name}'."

        except Exception as e:
            logger.exception("remove_application_member failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

MEMBER_WRITE_TOOLS = [
    add_application_member,
    update_application_member_role,
    remove_application_member,
]

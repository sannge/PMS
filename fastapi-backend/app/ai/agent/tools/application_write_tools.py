"""Application write tools for Blair AI agent -- all require HITL confirmation via interrupt().

Tools that modify application data:
1. create_application -- Create a new application
2. update_application -- Update an existing application's name/description
3. delete_application -- Delete an application and all its contents

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
from sqlalchemy import select

from ....models.application import Application
from ....models.application_member import ApplicationMember
from .context import _get_user_id
from .helpers import (
    _get_tool_session,
    _resolve_application,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool 1: create_application
# ---------------------------------------------------------------------------


@tool
async def create_application(
    name: str,
    description: str = "",
) -> str:
    """Create a new application. Requires user confirmation before executing.

    Use this when the user wants to create a new application (top-level container
    for projects and tasks).

    Args:
        name: Application name (1-100 characters)
        description: Optional description (max 500 characters)
    """
    # Validate inputs
    if not name or len(name.strip()) == 0:
        return "Error: Application name is required."
    if len(name) > 100:
        return "Error: Application name must be 100 characters or fewer."
    if description and len(description) > 500:
        return "Error: Application description must be 500 characters or fewer."

    user_id = _get_user_id()

    # Build confirmation payload
    details: dict[str, Any] = {
        "name": name.strip(),
    }
    if description:
        details["description"] = description

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "create_application",
        "summary": f"Create application '{name.strip()}'",
        "details": details,
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Application creation cancelled by user."

    # User approved -- execute the write
    async with _get_tool_session() as db:
        try:
            app = Application(
                name=name.strip(),
                description=description or None,
                owner_id=user_id,
            )
            db.add(app)
            await db.flush()

            # Create owner membership for the creating user
            member = ApplicationMember(
                application_id=app.id,
                user_id=user_id,
                role="owner",
            )
            db.add(member)
            await db.flush()

            return f"Created application '{name.strip()}' (ID: {app.id})"

        except Exception as e:
            logger.exception("create_application failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 2: update_application
# ---------------------------------------------------------------------------


@tool
async def update_application(
    app: str,
    name: str = "",
    description: str = "",
) -> str:
    """Update an existing application's name or description. Requires user confirmation.

    Use this when the user wants to rename an application or change its description.

    Args:
        app: Application UUID or name (partial match supported)
        name: New application name (1-100 characters, empty to keep current)
        description: New description (max 500 characters, empty to keep current)
    """
    # Validate at least one field provided
    if not name.strip() and not description.strip():
        return "Error: At least one of 'name' or 'description' must be provided."
    if name and len(name) > 100:
        return "Error: Application name must be 100 characters or fewer."
    if description and len(description) > 500:
        return "Error: Application description must be 500 characters or fewer."

    user_id = _get_user_id()

    # Resolve application and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_application(app, db)
        if error:
            return error
        app_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        # Load application
        result = await db.execute(select(Application).where(Application.id == app_uuid))
        app_obj = result.scalar_one_or_none()
        if not app_obj:
            return f"Error: Application '{app}' not found."

        app_name = app_obj.name

        # RBAC: must be owner or editor
        member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == user_id,
            )
        )
        member = member_result.scalar_one_or_none()
        if not member or member.role not in ("owner", "editor"):
            return "Access denied: you must be an owner or editor to update this application."

    # Build confirmation
    changes: list[str] = []
    if name:
        changes.append(f"name -> '{name.strip()}'")
    if description:
        changes.append(f"description -> '{description[:100]}{'...' if len(description) > 100 else ''}'")

    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "update_application",
        "summary": f"Update application '{app_name}': {', '.join(changes)}",
        "details": {
            "application_id": str(app_uuid),
            "application_name": app_name,
        },
    }
    if name:
        confirmation["details"]["new_name"] = name.strip()
    if description:
        confirmation["details"]["new_description"] = description

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Application update cancelled by user."

    # TOCTOU: Re-check RBAC + execute write in single session
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            member_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == user_uuid_check,
                )
            )
            member = member_result.scalar_one_or_none()
            if not member or member.role not in ("owner", "editor"):
                return "Access denied: you no longer have permission to update this application."

            result = await db.execute(select(Application).where(Application.id == app_uuid))
            app_obj = result.scalar_one_or_none()
            if not app_obj:
                return "Error: Application no longer exists."

            if name:
                app_obj.name = name.strip()
            if description:
                app_obj.description = description

            await db.flush()

            return f"Updated application '{app_name}'."

        except Exception as e:
            logger.exception("update_application failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool 3: delete_application
# ---------------------------------------------------------------------------


@tool
async def delete_application(
    app: str,
) -> str:
    """Delete an application and all its contents. Requires user confirmation.

    WARNING: This permanently deletes all projects, tasks, documents, and members
    within the application. This action is irreversible.

    Args:
        app: Application UUID or name (partial match supported)
    """
    user_id = _get_user_id()

    # Resolve application and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_application(app, db)
        if error:
            return error
        app_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        # Load application
        result = await db.execute(select(Application).where(Application.id == app_uuid))
        app_obj = result.scalar_one_or_none()
        if not app_obj:
            return f"Error: Application '{app}' not found."

        app_name = app_obj.name

        # RBAC: must be owner
        member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_uuid,
                ApplicationMember.user_id == user_id,
            )
        )
        member = member_result.scalar_one_or_none()
        if not member or member.role != "owner":
            return "Access denied: only the application owner can delete an application."

    # Build confirmation with extra warning
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "delete_application",
        "summary": (f"DELETE application '{app_name}' and all its contents (irreversible)"),
        "details": {
            "application_id": str(app_uuid),
            "application_name": app_name,
            "warning": "This will permanently delete all projects, tasks, documents, and members",
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Application deletion cancelled by user."

    # TOCTOU: Re-check RBAC + execute delete in single session
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            member_result = await db.execute(
                select(ApplicationMember).where(
                    ApplicationMember.application_id == app_uuid,
                    ApplicationMember.user_id == user_uuid_check,
                )
            )
            member = member_result.scalar_one_or_none()
            if not member or member.role != "owner":
                return "Access denied: you are no longer the owner of this application."

            result = await db.execute(select(Application).where(Application.id == app_uuid))
            app_obj = result.scalar_one_or_none()
            if not app_obj:
                return "Error: Application no longer exists."

            await db.delete(app_obj)
            await db.flush()

            return f"Deleted application '{app_name}' and all its contents."

        except Exception as e:
            logger.exception("delete_application failed: %s", e)
            raise  # Let get_tool_db context manager handle rollback


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

APPLICATION_WRITE_TOOLS = [
    create_application,
    update_application,
    delete_application,
]

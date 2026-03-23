"""Application-domain tools for Blair AI agent.

Tools for listing, inspecting, and exploring applications and their
members.  All tools are read-only.
"""

from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ....models.application import Application
from ....models.application_member import ApplicationMember
from ....models.document import Document
from ....models.document_folder import DocumentFolder
from ....models.project import Project
from ....models.project_member import ProjectMember
from ....models.user import User
from .context import _check_app_access, _get_ctx
from .helpers import (
    _format_date,
    _get_tool_session,
    _resolve_application,
    _truncate,
)

logger = logging.getLogger(__name__)


@tool
async def list_applications(include_archived: bool = False) -> str:
    """List all applications you have access to with details.

    Use this to discover available applications, find application IDs
    for other tools, or when the user asks about their applications.

    Args:
        include_archived: If true, include archived projects in project counts.
                          Defaults to false.
    """
    accessible_ids = _get_ctx().get("accessible_app_ids", [])
    if not accessible_ids:
        return "You have no accessible applications."

    app_uuids = [UUID(aid) for aid in accessible_ids]
    user_id_str = _get_ctx().get("user_id", "")

    try:
        async with _get_tool_session() as db:
            # Member count subquery (scoped to accessible apps)
            member_count_sq = (
                select(
                    ApplicationMember.application_id,
                    func.count(ApplicationMember.id).label("member_count"),
                )
                .where(ApplicationMember.application_id.in_(app_uuids))
                .group_by(ApplicationMember.application_id)
                .subquery()
            )

            # Project count subquery
            proj_count_q = select(
                Project.application_id,
                func.count(Project.id).label("project_count"),
            ).where(Project.application_id.in_(app_uuids))

            if not include_archived:
                proj_count_q = proj_count_q.where(Project.archived_at.is_(None))

            proj_count_sq = proj_count_q.group_by(Project.application_id).subquery()

            # Main query
            result = await db.execute(
                select(
                    Application,
                    member_count_sq.c.member_count,
                    proj_count_sq.c.project_count,
                )
                .outerjoin(
                    member_count_sq,
                    Application.id == member_count_sq.c.application_id,
                )
                .outerjoin(
                    proj_count_sq,
                    Application.id == proj_count_sq.c.application_id,
                )
                .where(Application.id.in_(app_uuids))
                .order_by(Application.name)
            )
            rows = result.all()

        if not rows:
            return "You have no accessible applications."

        lines: list[str] = []
        lines.append("| Application | ID | Members | Projects | Role | Created |")
        lines.append("| --- | --- | --- | --- | --- | --- |")

        for app, member_count, project_count in rows:
            try:
                is_owner = UUID(str(app.owner_id)) == UUID(user_id_str)
            except (ValueError, AttributeError):
                is_owner = False
            role = "owner" if is_owner else "member"
            lines.append(
                f"| {app.name} | {app.id} | "
                f"{member_count or 0} | {project_count or 0} | "
                f"{role} | {_format_date(app.created_at)} |"
            )

        lines.append(f"\n*{len(rows)} application(s).*")
        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning("list_applications failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving applications. Please try again."


@tool
async def get_application_details(app: str) -> str:
    """Get detailed information about a specific application.

    Returns the application's name, description, owner, members, projects,
    and document/folder counts.

    Args:
        app: Application UUID or name (partial match supported).
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_application(app, db)
            if error:
                return error
            app_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # Fetch application with owner
            result = await db.execute(
                select(Application).options(selectinload(Application.owner)).where(Application.id == app_uuid)
            )
            application = result.scalar_one_or_none()
            if not application:
                return f"Application '{app}' not found."

            # Members
            mem_result = await db.execute(
                select(ApplicationMember)
                .options(selectinload(ApplicationMember.user))
                .where(ApplicationMember.application_id == app_uuid)
            )
            members = mem_result.scalars().all()

            # Projects
            proj_result = await db.execute(
                select(Project)
                .where(
                    Project.application_id == app_uuid,
                    Project.archived_at.is_(None),
                )
                .order_by(Project.name)
            )
            projects = proj_result.scalars().all()

            # Document and folder counts
            doc_count_result = await db.execute(
                select(func.count(Document.id)).where(
                    Document.application_id == app_uuid,
                    Document.deleted_at.is_(None),
                )
            )
            doc_count = doc_count_result.scalar() or 0

            folder_count_result = await db.execute(
                select(func.count(DocumentFolder.id)).where(
                    DocumentFolder.application_id == app_uuid,
                )
            )
            folder_count = folder_count_result.scalar() or 0

        # Format output
        owner = application.owner
        owner_info = f"{owner.display_name or owner.email} ({owner.email})" if owner else "\u2014"

        lines = [
            f"## {application.name}",
            "",
            f"- **ID**: `{application.id}`",
            f"- **Description**: {application.description or '\u2014'}",
            f"- **Owner**: {owner_info}",
            f"- **Created**: {_format_date(application.created_at)}",
            f"- **Documents**: {doc_count} | **Folders**: {folder_count}",
            "",
        ]

        # Members section
        lines.append(f"### Members ({len(members)})")
        if members:
            lines.append("| Name | Email | Role | Manager |")
            lines.append("| --- | --- | --- | --- |")
            for m in members:
                user = m.user
                name = user.display_name or "\u2014" if user else "\u2014"
                email = user.email if user else "\u2014"
                is_owner = str(m.user_id) == str(application.owner_id)
                role = "owner" if is_owner else m.role
                mgr = "Yes" if m.is_manager else "No"
                lines.append(f"| {name} | {email} | {role} | {mgr} |")
        lines.append("")

        # Projects section
        lines.append(f"### Projects ({len(projects)})")
        if projects:
            lines.append("| Project | Key | ID |")
            lines.append("| --- | --- | --- |")
            for p in projects:
                lines.append(f"| {p.name} | {p.key} | `{p.id}` |")
        lines.append("")

        return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning("get_application_details failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving application details. Please try again."


@tool
async def get_application_members(app: str) -> str:
    """Get all members of an application with their roles and project assignments.

    Args:
        app: Application UUID or name (partial match supported).
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_application(app, db)
            if error:
                return error
            app_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # Get app name
            app_result = await db.execute(
                select(Application.name, Application.owner_id).where(Application.id == app_uuid)
            )
            app_row = app_result.one_or_none()
            if not app_row:
                return f"Application '{app}' not found."
            app_name = app_row.name
            owner_id = app_row.owner_id

            # Members with user info
            mem_result = await db.execute(
                select(ApplicationMember)
                .options(selectinload(ApplicationMember.user))
                .where(ApplicationMember.application_id == app_uuid)
            )
            members = mem_result.scalars().all()

            if not members:
                return f"No members found for application '{app_name}'."

            # Get projects in this app
            proj_result = await db.execute(
                select(Project.id, Project.name).where(
                    Project.application_id == app_uuid,
                    Project.archived_at.is_(None),
                )
            )
            projects = {str(row.id): row.name for row in proj_result.all()}

            # Get project memberships for all members in this app's projects
            proj_mem_result = await db.execute(
                select(ProjectMember.user_id, ProjectMember.project_id).where(
                    ProjectMember.project_id.in_([UUID(pid) for pid in projects])
                )
            )
            # Build user -> project names map
            user_projects: dict[str, list[str]] = {}
            for pm_row in proj_mem_result.all():
                uid = str(pm_row.user_id)
                pid = str(pm_row.project_id)
                proj_name = projects.get(pid, "Unknown")
                user_projects.setdefault(uid, []).append(proj_name)

            # Format
            lines = [
                f"## Members of {app_name}",
                "",
                f"*{len(members)} member(s)*",
                "",
                "| Name | Email | Role | Manager | Projects |",
                "| --- | --- | --- | --- | --- |",
            ]

            for m in members:
                user = m.user
                name = user.display_name or "\u2014" if user else "\u2014"
                email = user.email if user else "\u2014"
                is_owner = str(m.user_id) == str(owner_id)
                role = "owner" if is_owner else m.role
                mgr = "Yes" if m.is_manager else "No"
                uid = str(m.user_id)
                projs = ", ".join(sorted(user_projects.get(uid, []))) or "\u2014"
                lines.append(f"| {name} | {email} | {role} | {mgr} | {projs} |")

            lines.append("")
            return _truncate("\n".join(lines))

    except Exception as exc:
        logger.warning("get_application_members failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving application members. Please try again."

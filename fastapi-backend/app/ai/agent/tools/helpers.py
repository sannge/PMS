"""Shared helper functions for Blair AI agent tools.

Includes entity resolvers (application, project, task, user, document),
formatting utilities, and the ``_get_tool_session`` DB context manager.
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Callable
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models.application import Application
from ....models.application_member import ApplicationMember
from ....models.document import Document
from ....models.project import Project
from ....models.project_member import ProjectMember
from ....models.task import Task
from ....models.user import User
from ...agent_tools import MAX_TOOL_OUTPUT_CHARS
from .context import (
    _check_app_access,
    _check_project_access,
    _get_ctx,
    _get_user_id,
    _tool_context_var,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UUID parsing
# ---------------------------------------------------------------------------


def _parse_uuid(value: str, label: str) -> UUID:
    """Parse a string to UUID, raising a clear error on failure."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid {label}: '{value}' is not a valid UUID.")


# ---------------------------------------------------------------------------
# ILIKE escaping
# ---------------------------------------------------------------------------


def _escape_ilike(value: str) -> str:
    """Escape special characters for PostgreSQL ILIKE with backslash escape.

    Must be used with ``.ilike(..., escape="\\\\")``.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------------------
# Database session helpers
# ---------------------------------------------------------------------------


def _get_db_session() -> AsyncSession:
    """Create a raw database session from the global session maker.

    Callers are responsible for commit/rollback/close.  Prefer
    ``_get_tool_session()`` context manager for automatic lifecycle,
    which uses the injected factory when available.
    """
    from ....database import async_session_maker

    return async_session_maker()


@asynccontextmanager
async def _get_tool_session() -> AsyncIterator[AsyncSession]:
    """Provide a database session with automatic rollback on exception, and close.

    Prefers the injected ``db_session_factory`` from tool context (set by
    ``set_tool_context`` in ``ai_chat.py``).  Falls back to the global
    ``async_session_maker`` only when no factory is available (e.g.
    standalone test usage).

    Contract: callers must explicitly ``await db.commit()`` if performing
    write operations.  Neither the injected-factory path nor the fallback
    path auto-commits — this is intentional to keep read-only tool calls
    lightweight and avoid accidental persistence.

    Usage::

        async with _get_tool_session() as db:
            ...  # queries
            await db.commit()  # only if needed
    """
    # Read from ContextVar directly (not _get_ctx) to avoid RuntimeError
    # when tool context hasn't been set (e.g. in tests).
    ctx = _tool_context_var.get()
    factory = ctx.get("db_session_factory") if ctx else None

    if factory is not None:
        # Injected factory is an async context manager (e.g. get_tool_db)
        async with factory() as session:
            yield session
            return

    # Fallback: raw session from global maker
    session = _get_db_session()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Entity resolvers — all return tuple[str | None, str | None]
#   (resolved_id, None) on success
#   (None, error_message) on failure
# ---------------------------------------------------------------------------


async def _resolve_entity(
    identifier: str,
    db: AsyncSession,
    *,
    model_class: type,
    accessible_ids: list[str],
    entity_name: str,
    check_access_fn: Callable[[str], bool],
    name_column: Any = None,
) -> tuple[str | None, str | None]:
    """Generic entity resolver by UUID or partial name.

    Resolution order:
    1. Validate empty/length
    2. UUID fast path with access check
    3. Name ILIKE search scoped to accessible IDs
    4. List available names on miss
    5. Format ambiguity error

    Args:
        identifier: Entity UUID or name (partial match supported).
        db: Active async database session.
        model_class: SQLAlchemy model class (must have ``id`` attribute).
        accessible_ids: List of UUID strings the user can access.
        entity_name: Human-readable entity name for error messages.
        check_access_fn: Function that checks if a UUID string is accessible.
        name_column: SQLAlchemy column for name matching. Defaults to
            ``model_class.name``.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.
    """
    if not identifier or not identifier.strip():
        return (None, f"Error: {entity_name} identifier cannot be empty.")
    if len(identifier) > 255:
        return (None, "Error: name search term too long (max 255 characters).")

    if name_column is None:
        name_column = model_class.name

    # Fast path: valid UUID -> check access list.
    # NOTE (MED-10): The UUID fast path only checks the in-memory access list,
    # not DB existence. This is acceptable because the access list is populated
    # from a DB query at request start (in ai_chat.py) and is valid for the
    # duration of the request.
    try:
        UUID(identifier)
        if check_access_fn(identifier):
            return (identifier, None)
        # UUID is valid but not in accessible set — could be non-existent or
        # inaccessible.  Report "not found" to avoid leaking existence info.
        return (None, f"No {entity_name} found matching '{identifier}'.")
    except (ValueError, AttributeError):
        pass

    # Name resolution: fuzzy match against accessible entities
    if not accessible_ids:
        return (
            None,
            f"No {entity_name} found matching '{identifier}'. "
            f"You do not have access to any {entity_name}s. "
            f"Try searching without the {entity_name} filter.",
        )

    entity_uuids = [UUID(eid) for eid in accessible_ids]
    escaped = _escape_ilike(identifier)

    from app.ai.config_service import get_agent_config

    _MATCH_LIMIT = get_agent_config().get_int("agent_tool.match_limit", 20)
    result = await db.execute(
        select(model_class.id, name_column)
        .where(
            model_class.id.in_(entity_uuids),
            name_column.ilike(f"%{escaped}%", escape="\\"),
        )
        .limit(_MATCH_LIMIT)
    )
    matches = result.all()

    if len(matches) == 1:
        return (str(matches[0].id), None)
    elif len(matches) == 0:
        # List available entities so the LLM can retry with the right name
        all_result = await db.execute(
            select(name_column).where(model_class.id.in_(entity_uuids)).order_by(name_column).limit(10)
        )
        available_names = [r[0] for r in all_result.all()]
        if available_names:
            return (
                None,
                f"No {entity_name} found matching '{identifier}'. "
                f"Available {entity_name}s: {', '.join(available_names)}. "
                f"Try searching without the {entity_name} filter, or use one of the available names.",
            )
        return (
            None,
            f"No {entity_name} found matching '{identifier}'. Try searching without the {entity_name} filter.",
        )
    else:
        names = ", ".join(f"'{m.name}'" for m in matches[:5])
        extra = " (and more)" if len(matches) > 5 else ""
        return (
            None,
            f"Multiple {entity_name}s match '{identifier}': {names}{extra}. Please be more specific.",
        )


async def _resolve_application(identifier: str, db: AsyncSession) -> tuple[str | None, str | None]:
    """Resolve an application by UUID or partial name.

    Args:
        identifier: Application UUID or name (partial match supported).
        db: Active async database session.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.
    """
    return await _resolve_entity(
        identifier,
        db,
        model_class=Application,
        accessible_ids=_get_ctx().get("accessible_app_ids", []),
        entity_name="application",
        check_access_fn=_check_app_access,
    )


async def _resolve_project(identifier: str, db: AsyncSession) -> tuple[str | None, str | None]:
    """Resolve a project by UUID or partial name.

    Args:
        identifier: Project UUID or name (partial match supported).
        db: Active async database session.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.
    """
    return await _resolve_entity(
        identifier,
        db,
        model_class=Project,
        accessible_ids=_get_ctx().get("accessible_project_ids", []),
        entity_name="project",
        check_access_fn=_check_project_access,
    )


async def _resolve_task(identifier: str, db: AsyncSession) -> tuple[str | None, str | None]:
    """Resolve a task by UUID, task_key, or partial title.

    Resolution order:
    1. UUID direct lookup (scoped to accessible projects)
    2. task_key exact match (e.g., ``PROJ-123``)
    3. Title ILIKE search (scoped to accessible projects)

    Args:
        identifier: Task UUID, task_key, or title (partial match supported).
        db: Active async database session.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.
    """
    if not identifier or not identifier.strip():
        return (None, "Error: task identifier cannot be empty.")
    if len(identifier) > 500:
        return (None, "Error: search term too long (max 500 characters).")

    accessible_project_ids = _get_ctx().get("accessible_project_ids", [])
    if not accessible_project_ids:
        return (None, f"No task found matching '{identifier}'.")

    proj_uuids = [UUID(pid) for pid in accessible_project_ids]

    # 1. Fast path: valid UUID
    try:
        task_uuid = UUID(identifier)
        result = await db.execute(
            select(Task.id).where(
                Task.id == task_uuid,
                Task.project_id.in_(proj_uuids),
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return (str(row), None)
        return (None, f"No task found matching '{identifier}'.")
    except (ValueError, AttributeError):
        pass

    # 2. task_key exact match — use direct comparison with .upper() on the
    #    Python side so the existing B-tree index on task_key can be used.
    #    Task keys are generated uppercase (e.g., "PROJ-123"), so this is safe.
    #    (DB-006: avoids func.upper() which prevents index usage)
    result = await db.execute(
        select(Task.id).where(
            Task.task_key == identifier.upper(),
            Task.project_id.in_(proj_uuids),
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return (str(row), None)

    # 3. Title ILIKE search (limit to 10 to prevent unbounded results)
    escaped = _escape_ilike(identifier)
    result = await db.execute(
        select(Task.id, Task.title)
        .where(
            Task.project_id.in_(proj_uuids),
            Task.title.ilike(f"%{escaped}%", escape="\\"),
        )
        .limit(10)
    )
    matches = result.all()

    if len(matches) == 1:
        return (str(matches[0].id), None)
    elif len(matches) == 0:
        return (None, f"No task found matching '{identifier}'.")
    else:
        titles = ", ".join(f"'{m.title}'" for m in matches[:5])
        extra = f" (and {len(matches) - 5} more)" if len(matches) > 5 else ""
        return (
            None,
            f"Multiple tasks match '{identifier}': {titles}{extra}. "
            "Please be more specific or use the task key (e.g., PROJ-123).",
        )


async def _resolve_user(
    identifier: str,
    db: AsyncSession,
    scope_app_id: str | None = None,
    scope_project_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve a user by UUID, email, or display name.

    Resolution order:
    1. UUID direct lookup
    2. Email ILIKE search
    3. display_name ILIKE search

    Results are scoped to members of the given application or project.
    If no scope is provided, searches across all accessible applications.

    Args:
        identifier: User UUID, email, or display name (partial match).
        db: Active async database session.
        scope_app_id: Optional application UUID to scope search.
        scope_project_id: Optional project UUID to scope search.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.
    """
    if not identifier or not identifier.strip():
        return (None, "Error: user identifier cannot be empty.")
    if len(identifier) > 255:
        return (None, "Error: search term too long (max 255 characters).")

    # Build scope subquery for user IDs — used as a subquery to reduce
    # round trips (DB-007: combine user resolution into fewer queries).
    if scope_project_id:
        scope_subquery = select(ProjectMember.user_id).where(ProjectMember.project_id == UUID(scope_project_id))
    elif scope_app_id:
        scope_subquery = select(ApplicationMember.user_id).where(ApplicationMember.application_id == UUID(scope_app_id))
    else:
        # All accessible apps
        accessible_app_ids = _get_ctx().get("accessible_app_ids", [])
        if not accessible_app_ids:
            return (None, f"No user found matching '{identifier}'.")
        app_uuids = [UUID(aid) for aid in accessible_app_ids]
        scope_subquery = (
            select(ApplicationMember.user_id).where(ApplicationMember.application_id.in_(app_uuids)).distinct()
        )

    # 1. UUID direct lookup — single query with scope check
    try:
        user_uuid = UUID(identifier)
        result = await db.execute(
            select(User.id).where(
                User.id == user_uuid,
                User.id.in_(scope_subquery),
            )
        )
        if result.scalar_one_or_none() is not None:
            return (str(user_uuid), None)
        return (None, f"No user found matching '{identifier}'.")
    except (ValueError, AttributeError):
        pass

    # 2+3. Combined email OR display_name ILIKE in a single query (DB-007)
    escaped = _escape_ilike(identifier)
    result = await db.execute(
        select(User.id, User.email, User.display_name)
        .where(
            User.id.in_(scope_subquery),
            or_(
                User.email.ilike(f"%{escaped}%", escape="\\"),
                User.display_name.ilike(f"%{escaped}%", escape="\\"),
            ),
        )
        .limit(10)
    )
    matches = result.all()

    if len(matches) == 1:
        return (str(matches[0].id), None)
    elif len(matches) == 0:
        return (None, f"No user found matching '{identifier}'.")
    else:
        names = ", ".join(f"'{m.display_name or m.email}'" for m in matches[:5])
        extra = f" (and {len(matches) - 5} more)" if len(matches) > 5 else ""
        return (
            None,
            f"Multiple users match '{identifier}': {names}{extra}. Please be more specific.",
        )


async def _resolve_document(identifier: str, db: AsyncSession) -> tuple[str | None, str | None]:
    """Resolve a document by UUID or partial title.

    Results are scoped to documents in the user's accessible applications,
    accessible projects, or owned personally.

    Args:
        identifier: Document UUID or title (partial match supported).
        db: Active async database session.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.
    """
    if not identifier or not identifier.strip():
        return (None, "Error: document identifier cannot be empty.")
    if len(identifier) > 255:
        return (None, "Error: search term too long (max 255 characters).")

    ctx = _get_ctx()
    accessible_app_ids = ctx.get("accessible_app_ids", [])
    accessible_project_ids = ctx.get("accessible_project_ids", [])
    user_id = ctx.get("user_id")

    # Build scope filter: app-scoped OR project-scoped OR personal
    scope_filters = []
    if accessible_app_ids:
        app_uuids = [UUID(aid) for aid in accessible_app_ids]
        scope_filters.append(Document.application_id.in_(app_uuids))
    if accessible_project_ids:
        proj_uuids = [UUID(pid) for pid in accessible_project_ids]
        scope_filters.append(Document.project_id.in_(proj_uuids))
    if user_id:
        scope_filters.append(Document.user_id == UUID(user_id))

    if not scope_filters:
        return (None, f"No document found matching '{identifier}'.")

    scope_clause = or_(*scope_filters)
    active_clause = Document.deleted_at.is_(None)

    # 1. UUID direct lookup
    try:
        doc_uuid = UUID(identifier)
        result = await db.execute(
            select(Document.id).where(
                Document.id == doc_uuid,
                scope_clause,
                active_clause,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return (str(row), None)
        return (None, f"No document found matching '{identifier}'.")
    except (ValueError, AttributeError):
        pass

    # 2. Title ILIKE search
    escaped = _escape_ilike(identifier)
    result = await db.execute(
        select(Document.id, Document.title)
        .where(
            scope_clause,
            active_clause,
            Document.title.ilike(f"%{escaped}%", escape="\\"),
        )
        .limit(20)
    )
    matches = result.all()

    if len(matches) == 1:
        return (str(matches[0].id), None)
    elif len(matches) == 0:
        return (None, f"No document found matching '{identifier}'.")
    else:
        titles = ", ".join(f"'{m.title}'" for m in matches[:5])
        extra = f" (and {len(matches) - 5} more)" if len(matches) > 5 else ""
        return (
            None,
            f"Multiple documents match '{identifier}': {titles}{extra}. "
            "Please be more specific or use the document UUID.",
        )


# ---------------------------------------------------------------------------
# Formatting / truncation helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate text to fit within the tool output budget."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n... (output truncated)"


def _format_date(d: date | datetime | None) -> str:
    """Format a date or datetime for display."""
    if d is None:
        return "\u2014"
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d %H:%M")
    return d.isoformat()


def _days_overdue(due: date | None) -> int | None:
    """Return positive int of days overdue, or None if not overdue/no date."""
    if due is None:
        return None
    today = datetime.now(timezone.utc).date()
    delta = (today - due).days
    return delta if delta > 0 else None


def _serialize(value: Any) -> str:
    """Safely convert a value to string for output."""
    if value is None:
        return "\u2014"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return _format_date(value)
    return str(value)


def _relative_time(dt: datetime | None) -> str:
    """Format a datetime as relative time (e.g., '2 days ago')."""
    if dt is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    if delta.days == 0:
        return "today"
    elif delta.days == 1:
        return "yesterday"
    elif delta.days < 7:
        return f"{delta.days} days ago"
    elif delta.days < 30:
        weeks = delta.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    else:
        return _format_date(dt)


def _wrap_user_content(text: str) -> str:
    """Wrap user-generated content with demarcation tags for prompt injection safety.

    SA-010: Strips existing delimiter tags from the input before wrapping
    to prevent users from breaking out of the content boundary.
    """
    sanitized = re.sub(r"\[USER\s+CONTENT\s+(START|END)\]", "", text, flags=re.IGNORECASE)
    return f"[USER CONTENT START]\n{sanitized}\n[USER CONTENT END]"


# ---------------------------------------------------------------------------
# TOCTOU re-check helpers -- post-interrupt RBAC verification
# ---------------------------------------------------------------------------


async def _recheck_app_access(
    app_id: UUID,
    required_roles: set[str],
) -> str | None:
    """Post-interrupt RBAC re-check for application-scoped tools.

    Returns an error string if access is denied, or ``None`` if the user
    still has the required role.
    """
    async with _get_tool_session() as db:
        result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == _get_user_id(),
            )
        )
        member = result.scalar_one_or_none()
        if not member or member.role not in required_roles:
            return "Access denied: your permissions have changed since confirmation."
    return None


async def _recheck_project_access(
    project_id: UUID,
) -> str | None:
    """Post-interrupt RBAC re-check for project-scoped tools.

    Returns an error string if access is denied, or ``None`` if the user
    is still a project member.
    """
    async with _get_tool_session() as db:
        result = await db.execute(
            select(ProjectMember.id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == _get_user_id(),
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is None:
            return "Access denied: you no longer have access to this project."
    return None


async def _recheck_project_admin_or_app_owner(
    project_id: UUID,
    app_id: UUID,
) -> str | None:
    """Post-interrupt RBAC re-check for tools requiring App Owner OR Project Admin.

    Returns an error string if access is denied, or ``None`` if the user
    has the required role.
    """
    async with _get_tool_session() as db:
        user_id = _get_user_id()

        app_member_result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == app_id,
                ApplicationMember.user_id == user_id,
            )
        )
        app_member = app_member_result.scalar_one_or_none()
        is_app_owner = app_member is not None and app_member.role == "owner"

        proj_member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        proj_member = proj_member_result.scalar_one_or_none()
        is_project_admin = proj_member is not None and proj_member.role == "admin"

        if not is_app_owner and not is_project_admin:
            return "Access denied: you no longer have the required permissions."
    return None


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

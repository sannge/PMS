"""Read-only tools for Blair AI agent.

Provides 12 tools that never modify data and do not require user confirmation:
1. query_knowledge   -- Hybrid search over knowledge base documents
2. sql_query         -- NL question -> SQL -> execute against scoped views
3. get_projects      -- List projects in an application with completion %
4. get_tasks         -- List tasks in a project with optional filters
5. get_task_detail   -- Full task details including checklists/comments
6. get_project_status -- Aggregated project metrics dashboard
7. get_overdue_tasks -- Overdue tasks across accessible scope
8. get_team_members  -- Application members and project assignments
9. understand_image  -- Vision AI analysis of an attachment image
10. request_clarification -- Ask user for clarification (uses interrupt)
11. get_applications -- List accessible applications with IDs and names
12. browse_knowledge -- Browse documents and folders in a scope

All tools are created via a factory function ``create_read_tools`` which
injects database access and provider registry. Tools access user context
(user_id, accessible_app_ids, accessible_project_ids) via a per-request
``ContextVar`` that is set before each graph invocation.
"""

from __future__ import annotations

import contextvars
import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...models.application import Application
from ...models.application_member import ApplicationMember
from ...models.attachment import Attachment
from ...models.checklist import Checklist
from ...models.comment import Comment
from ...models.project import Project
from ...models.project_member import ProjectMember
from ...models.project_task_status_agg import ProjectTaskStatusAgg
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...models.user import User
from ..agent_tools import MAX_TOOL_OUTPUT_CHARS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-request context — uses contextvars for async/concurrency safety
# ---------------------------------------------------------------------------
_tool_context_var: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "tool_context", default={}
)

class _ContextVarSyncDict(dict):
    """Dict that mirrors writes to ``_tool_context_var`` for test compat.

    Tests import ``_tool_context`` and call ``.update()`` / ``.clear()``
    directly.  This thin subclass keeps the ContextVar in sync so that
    ``_get_ctx()`` — which reads only from the ContextVar — always sees
    the latest values.
    """

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        super().update(*args, **kwargs)
        _tool_context_var.set(dict(self))

    def clear(self) -> None:
        super().clear()
        _tool_context_var.set({})

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        _tool_context_var.set(dict(self))

    def __delitem__(self, key: Any) -> None:
        super().__delitem__(key)
        _tool_context_var.set(dict(self))


# Module-level alias for backward compatibility (tests, write tools import this).
# All mutations are mirrored to the ContextVar via _ContextVarSyncDict.
_tool_context: dict[str, Any] = _ContextVarSyncDict()


def set_tool_context(
    user_id: str,
    accessible_app_ids: list[str],
    accessible_project_ids: list[str],
    db_session_factory: Any,
    provider_registry: Any,
) -> None:
    """Configure the per-request context used by all tools.

    Uses ``contextvars.ContextVar`` for async-safe isolation between
    concurrent requests. Must be called before invoking the agent graph.

    Args:
        user_id: UUID string of the requesting user.
        accessible_app_ids: List of application UUID strings the user can access.
        accessible_project_ids: List of project UUID strings the user can access.
        db_session_factory: Async context manager that yields an AsyncSession.
        provider_registry: ProviderRegistry singleton for AI providers.
    """
    ctx = {
        "user_id": user_id,
        "accessible_app_ids": accessible_app_ids,
        "accessible_project_ids": accessible_project_ids,
        "db_session_factory": db_session_factory,
        "provider_registry": provider_registry,
    }
    # Update module-level dict first (for backward compatibility),
    # then set the authoritative ContextVar.
    _tool_context.clear()
    _tool_context.update(ctx)
    _tool_context_var.set(ctx)


def clear_tool_context() -> None:
    """Clear the tool context after graph execution."""
    _tool_context_var.set({})
    _tool_context.clear()


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

def _get_ctx() -> dict[str, Any]:
    """Return the current request's tool context (async-safe).

    Always reads from the ContextVar — never falls back to the
    module-level ``_tool_context`` dict.  The module-level dict is
    only kept for test backward compatibility (tests that do
    ``_tool_context.update(...)``), but production code reads
    exclusively from the ContextVar to avoid cross-request races.

    Raises:
        RuntimeError: If the context is empty (set_tool_context not called).
    """
    ctx = _tool_context_var.get()
    if not ctx:
        raise RuntimeError(
            "Tool context is empty — call set_tool_context() before invoking agent tools. "
            "This usually means the agent graph was invoked without proper RBAC setup."
        )
    return ctx


def _get_user_id() -> UUID:
    """Return the current user's UUID from tool context.

    Raises:
        RuntimeError: If tool context has not been set.
    """
    uid = _get_ctx().get("user_id")
    if uid is None:
        raise RuntimeError("Tool context not set — call set_tool_context() first")
    return UUID(uid)


def _check_app_access(app_id: str) -> bool:
    """Check whether the current user has access to an application."""
    return app_id in _get_ctx().get("accessible_app_ids", [])


def _check_project_access(project_id: str) -> bool:
    """Check whether the current user has access to a project."""
    return project_id in _get_ctx().get("accessible_project_ids", [])



async def _resolve_application(
    identifier: str, db: AsyncSession
) -> tuple[str | None, str | None]:
    """Resolve an application by UUID or partial name.

    Accepts a UUID string (direct lookup with access check) or a name
    fragment (case-insensitive ILIKE search scoped to the user's
    accessible applications).

    Args:
        identifier: Application UUID or name (partial match supported).
        db: Active async database session.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.

    Note:
        Name resolution searches across all accessible applications.
        Pass a UUID for precise targeting.
    """
    if not identifier or not identifier.strip():
        return (None, "Error: application identifier cannot be empty.")
    if len(identifier) > 255:
        return (None, "Error: name search term too long (max 255 characters).")

    # Fast path: valid UUID → check access list
    try:
        UUID(identifier)
        if _check_app_access(identifier):
            return (identifier, None)
        # UUID is valid but not in accessible set — could be non-existent or
        # inaccessible.  Report "not found" to avoid leaking existence info.
        return (None, f"No application found matching '{identifier}'.")
    except (ValueError, AttributeError):
        pass

    # Name resolution: fuzzy match against accessible applications
    accessible_ids = _get_ctx().get("accessible_app_ids", [])
    if not accessible_ids:
        return (None, f"No application found matching '{identifier}'.")

    app_uuids = [UUID(aid) for aid in accessible_ids]
    escaped = identifier.replace("%", r"\%").replace("_", r"\_")

    result = await db.execute(
        select(Application.id, Application.name).where(
            Application.id.in_(app_uuids),
            Application.name.ilike(f"%{escaped}%"),
        )
    )
    matches = result.all()

    if len(matches) == 1:
        return (str(matches[0].id), None)
    elif len(matches) == 0:
        return (None, f"No application found matching '{identifier}'.")
    else:
        names = ", ".join(f"'{m.name}'" for m in matches)
        return (
            None,
            f"Multiple applications match '{identifier}': {names}. "
            "Please be more specific.",
        )


async def _resolve_project(
    identifier: str, db: AsyncSession
) -> tuple[str | None, str | None]:
    """Resolve a project by UUID or partial name.

    Accepts a UUID string (direct lookup with access check) or a name
    fragment (case-insensitive ILIKE search scoped to the user's
    accessible projects).

    Args:
        identifier: Project UUID or name (partial match supported).
        db: Active async database session.

    Returns:
        ``(uuid_str, None)`` on success, ``(None, error_message)`` on failure.

    Note:
        Name resolution searches across all accessible projects.
        Pass a UUID for precise targeting.
    """
    if not identifier or not identifier.strip():
        return (None, "Error: project identifier cannot be empty.")
    if len(identifier) > 255:
        return (None, "Error: name search term too long (max 255 characters).")

    # Fast path: valid UUID → check access list
    try:
        UUID(identifier)
        if _check_project_access(identifier):
            return (identifier, None)
        # UUID is valid but not in accessible set — could be non-existent or
        # inaccessible.  Report "not found" to avoid leaking existence info.
        return (None, f"No project found matching '{identifier}'.")
    except (ValueError, AttributeError):
        pass

    # Name resolution: fuzzy match against accessible projects
    accessible_ids = _get_ctx().get("accessible_project_ids", [])
    if not accessible_ids:
        return (None, f"No project found matching '{identifier}'.")

    proj_uuids = [UUID(pid) for pid in accessible_ids]
    escaped = identifier.replace("%", r"\%").replace("_", r"\_")

    result = await db.execute(
        select(Project.id, Project.name).where(
            Project.id.in_(proj_uuids),
            Project.name.ilike(f"%{escaped}%"),
        )
    )
    matches = result.all()

    if len(matches) == 1:
        return (str(matches[0].id), None)
    elif len(matches) == 0:
        return (None, f"No project found matching '{identifier}'.")
    else:
        names = ", ".join(f"'{m.name}'" for m in matches)
        return (
            None,
            f"Multiple projects match '{identifier}': {names}. "
            "Please be more specific.",
        )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate text to fit within the tool output budget."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n... (output truncated)"


def _format_date(d: date | datetime | None) -> str:
    """Format a date or datetime for display."""
    if d is None:
        return "—"
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
        return "—"
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


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def create_read_tools(
    db_session_factory: Any,
    provider_registry: Any,
) -> list:
    """Create all read tools with injected dependencies.

    The returned tools are ``@tool``-decorated async functions suitable for
    use with LangGraph's ``ToolNode``.  They access the shared
    ``_tool_context`` for user identity and RBAC scope.

    Args:
        db_session_factory: Async context manager yielding ``AsyncSession``.
        provider_registry: ``ProviderRegistry`` singleton.

    Returns:
        List of LangChain tool objects.
    """

    # ------------------------------------------------------------------
    # 1. query_knowledge
    # ------------------------------------------------------------------
    @tool
    async def query_knowledge(
        query: str,
        application_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Search the knowledge base for relevant documents and content.

        Use this when the user asks about documentation, specifications,
        meeting notes, or any written content stored in the knowledge base.

        Args:
            query: The search query in natural language.
            application_id: Optional application UUID or name (partial match supported).
            project_id: Optional project UUID or name (partial match supported).
        """
        from ..agent_tools import rag_search_tool

        user_id = _get_user_id()

        from .source_references import SourceReference, ToolResultWithSources, push_sources

        try:
            async with db_session_factory() as db:
                # Resolve scopes (supports UUID or name)
                if application_id:
                    resolved_app, err = await _resolve_application(application_id, db)
                    if err:
                        return err
                    application_id = resolved_app
                if project_id:
                    resolved_proj, err = await _resolve_project(project_id, db)
                    if err:
                        return err
                    project_id = resolved_proj

                result = await rag_search_tool(
                    query=query,
                    user_id=user_id,
                    db=db,
                    provider_registry=provider_registry,
                    application_id=UUID(application_id) if application_id else None,
                    project_id=UUID(project_id) if project_id else None,
                )

            if not result.success:
                return f"Knowledge search failed: {result.error}"

            formatted_text = result.data or "No results found."

            # Build structured sources from metadata when available
            docs_meta = (result.metadata or {}).get("documents", [])
            if docs_meta:
                sources = [
                    SourceReference(
                        document_id=d.get("document_id", ""),
                        document_title=d.get("title", ""),
                        document_type="document",
                        heading_context=d.get("heading_context", "") or None,
                        chunk_text=d.get("chunk_text", ""),
                        chunk_index=d.get("chunk_index", 0),
                        score=d.get("score", 0.0),
                        source_type=d.get("source", "semantic"),
                        application_id=d.get("application_id", "") or None,
                    )
                    for d in docs_meta
                ]
                tool_result = ToolResultWithSources(
                    text=formatted_text, sources=sources
                )
                # Push structured sources into the per-request accumulator
                # so ai_chat.py can include them in the run_finished SSE event.
                push_sources(sources)
                return _truncate(tool_result.format_for_llm())

            return _truncate(formatted_text)

        except Exception as exc:
            logger.warning("query_knowledge failed: %s: %s", type(exc).__name__, exc)
            return "Error searching knowledge base. Please try again."

    # ------------------------------------------------------------------
    # 2. sql_query
    # ------------------------------------------------------------------
    @tool
    async def sql_query(question: str) -> str:
        """Query the project database to answer structural questions about
        applications, projects, tasks, users, assignments, and other
        relational data.

        Use this when the user asks about who owns what, task counts,
        project status, team members, or any question answerable from
        the relational schema.

        Args:
            question: Natural language question (will be converted to SQL).
        """
        from ..agent_tools import sql_query_tool

        user_id = _get_user_id()

        try:
            async with db_session_factory() as db:
                result = await sql_query_tool(
                    question=question,
                    user_id=user_id,
                    db=db,
                    provider_registry=provider_registry,
                    db_factory=db_session_factory,
                )

            if not result.success:
                return f"SQL query failed: {result.error}"

            return _truncate(result.data or "Query returned no data.")

        except Exception as exc:
            logger.warning("sql_query failed: %s: %s", type(exc).__name__, exc)
            return "Error executing query. Please try again."

    # ------------------------------------------------------------------
    # 3. get_projects
    # ------------------------------------------------------------------
    @tool
    async def get_projects(
        application_id: str,
        status: str | None = None,
    ) -> str:
        """List projects in an application with their completion percentage.

        Use this when the user asks about project status or wants an overview
        of projects within an application.

        Args:
            application_id: Application UUID or name (partial match supported).
            status: Optional filter — "active", "completed", or "archived".
        """
        try:
            async with db_session_factory() as db:
                resolved_id, error = await _resolve_application(application_id, db)
                if error:
                    return error
                application_id = resolved_id
                query = (
                    select(Project)
                    .outerjoin(
                        ProjectTaskStatusAgg,
                        ProjectTaskStatusAgg.project_id == Project.id,
                    )
                    .where(
                        Project.application_id == UUID(application_id),
                    )
                    .options(
                        selectinload(Project.derived_status),
                    )
                    .order_by(Project.name)
                )

                # Apply status filter
                if status == "completed":
                    # Projects where all tasks are done (or no tasks)
                    query = query.where(
                        ProjectTaskStatusAgg.total_tasks == ProjectTaskStatusAgg.done_tasks,
                    )
                elif status == "archived":
                    query = query.where(Project.archived_at.isnot(None))
                elif status == "active":
                    query = query.where(Project.archived_at.is_(None))

                result = await db.execute(query)
                projects = result.scalars().unique().all()

                if not projects:
                    return "No projects found in this application."

                # Fetch aggregation data for all projects in one query
                agg_result = await db.execute(
                    select(ProjectTaskStatusAgg).where(
                        ProjectTaskStatusAgg.project_id.in_(
                            [p.id for p in projects]
                        )
                    )
                )
                agg_map: dict[UUID, ProjectTaskStatusAgg] = {
                    a.project_id: a for a in agg_result.scalars().all()
                }

            # Format as markdown table
            lines: list[str] = []
            lines.append("| Project | Status | Tasks (done/total) | % Complete |")
            lines.append("| --- | --- | --- | --- |")

            for proj in projects:
                agg = agg_map.get(proj.id)
                total = agg.total_tasks if agg else 0
                done = agg.done_tasks if agg else 0
                pct = int((done / total) * 100) if total > 0 else 0

                derived = proj.derived_status
                status_name = derived.name if derived else "No tasks"

                lines.append(
                    f"| {proj.name} | {status_name} | {done}/{total} | {pct}% |"
                )

            lines.append(f"\n*{len(projects)} project(s) found.*")
            return _truncate("\n".join(lines))

        except Exception as exc:
            logger.warning("get_projects failed: %s: %s", type(exc).__name__, exc)
            return "Error retrieving projects. Please try again."

    # ------------------------------------------------------------------
    # 4. get_tasks
    # ------------------------------------------------------------------
    @tool
    async def get_tasks(
        project_id: str,
        status: str | None = None,
        assignee: str | None = None,
        overdue_only: bool = False,
    ) -> str:
        """List tasks in a project with optional filters.

        Use this when the user asks about specific tasks or task status
        within a project.

        Args:
            project_id: Project UUID or name (partial match supported).
            status: Optional filter — "todo", "in_progress", "in_review", "issue", or "done".
            assignee: Optional filter — user display name or user UUID.
            overdue_only: If true, only return tasks past their due date.
        """
        try:
            async with db_session_factory() as db:
                resolved_id, error = await _resolve_project(project_id, db)
                if error:
                    return error
                project_id = resolved_id
                query = (
                    select(Task)
                    .join(TaskStatus, Task.task_status_id == TaskStatus.id)
                    .outerjoin(User, Task.assignee_id == User.id)
                    .where(
                        Task.project_id == UUID(project_id),
                        Task.archived_at.is_(None),
                    )
                    .options(
                        selectinload(Task.task_status),
                        selectinload(Task.assignee),
                    )
                    .order_by(TaskStatus.rank, Task.task_rank)
                )

                # Status filter — match against TaskStatus.name (case-insensitive)
                from .tools_write import _STATUS_NAME_MAP

                if status:
                    mapped = _STATUS_NAME_MAP.get(status.lower(), status)
                    query = query.where(
                        func.lower(TaskStatus.name) == func.lower(mapped)
                    )

                # Assignee filter — match by display name (ILIKE) or UUID
                if assignee and assignee.strip():
                    if len(assignee) > 255:
                        return "Error: assignee filter too long (max 255 characters)."
                    try:
                        assignee_uuid = UUID(assignee)
                        query = query.where(Task.assignee_id == assignee_uuid)
                    except ValueError:
                        from sqlalchemy import or_

                        _escaped = assignee.replace("%", r"\%").replace("_", r"\_")
                        query = query.where(
                            or_(
                                User.display_name.ilike(f"%{_escaped}%"),
                                User.email.ilike(f"%{_escaped}%"),
                            )
                        )

                # Overdue filter
                if overdue_only:
                    today = datetime.now(timezone.utc).date()
                    query = query.where(
                        Task.due_date < today,
                        TaskStatus.category != "Done",
                    )

                result = await db.execute(query)
                tasks = result.scalars().unique().all()

                if not tasks:
                    return "No tasks found matching your criteria."

            # Format as markdown table
            lines: list[str] = []
            lines.append("| Key | Title | Status | Assignee | Priority | Due Date |")
            lines.append("| --- | --- | --- | --- | --- | --- |")

            for t in tasks:
                assignee_name = t.assignee.display_name if t.assignee else "Unassigned"
                status_text = t.task_status.name if t.task_status else "—"
                due_text = _format_date(t.due_date)
                overdue_marker = ""
                overdue_days = _days_overdue(t.due_date)
                if overdue_days and t.task_status and t.task_status.category != "Done":
                    overdue_marker = f" ({overdue_days}d overdue)"

                lines.append(
                    f"| {t.task_key} | {t.title} | {status_text} "
                    f"| {assignee_name} | {t.priority} | {due_text}{overdue_marker} |"
                )

            lines.append(f"\n*{len(tasks)} task(s) found.*")
            return _truncate("\n".join(lines))

        except Exception as exc:
            logger.warning("get_tasks failed: %s: %s", type(exc).__name__, exc)
            return "Error retrieving tasks. Please try again."

    # ------------------------------------------------------------------
    # 5. get_task_detail
    # ------------------------------------------------------------------
    @tool
    async def get_task_detail(task_id: str) -> str:
        """Get full details for a specific task including checklists,
        comments, and metadata.

        Use this when the user asks for detailed information about a
        single task.

        Args:
            task_id: The task UUID.
        """
        try:
            task_uuid = UUID(task_id)
        except (ValueError, AttributeError):
            return f"Error: '{task_id}' is not a valid task UUID."

        try:
            async with db_session_factory() as db:
                # H1: Check RBAC before loading full task data
                task_check = await db.execute(
                    select(Task.project_id).where(Task.id == task_uuid)
                )
                project_id = task_check.scalar_one_or_none()

                if project_id is None:
                    return f"Task not found: {task_id}"

                if not _check_project_access(str(project_id)):
                    return f"Task not found: {task_id}"

                # Full load with eager loading (RBAC passed)
                result = await db.execute(
                    select(Task)
                    .where(Task.id == task_uuid)
                    .options(
                        selectinload(Task.task_status),
                        selectinload(Task.assignee),
                        selectinload(Task.reporter),
                        selectinload(Task.project),
                        selectinload(Task.checklists).selectinload(
                            Checklist.items
                        ),
                        selectinload(Task.comments).selectinload(
                            Comment.author
                        ),
                    )
                )
                task = result.scalar_one_or_none()

                if task is None:
                    return f"Task not found: {task_id}"

                # Build detail output
                parts: list[str] = []
                parts.append(f"## {task.task_key}: {task.title}")
                parts.append("")

                # Metadata table
                status_text = task.task_status.name if task.task_status else "—"
                assignee_name = task.assignee.display_name if task.assignee else "Unassigned"
                reporter_name = task.reporter.display_name if task.reporter else "—"
                project_name = task.project.name if task.project else "—"

                parts.append(f"- **Project**: {project_name}")
                parts.append(f"- **Status**: {status_text}")
                parts.append(f"- **Priority**: {task.priority}")
                parts.append(f"- **Type**: {task.task_type}")
                parts.append(f"- **Assignee**: {assignee_name}")
                parts.append(f"- **Reporter**: {reporter_name}")
                parts.append(f"- **Due date**: {_format_date(task.due_date)}")
                if task.story_points is not None:
                    parts.append(f"- **Story points**: {task.story_points}")
                parts.append(f"- **Created**: {_format_date(task.created_at)}")
                parts.append(f"- **Updated**: {_format_date(task.updated_at)}")
                parts.append("")

                # Description
                if task.description:
                    parts.append("### Description")
                    parts.append(task.description)
                    parts.append("")

                # Checklists
                checklists = list(task.checklists)
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

                # Comments (last 5 non-deleted, most recent first)
                non_deleted = [c for c in task.comments if not c.is_deleted]
                comments = sorted(
                    non_deleted,
                    key=lambda c: c.created_at or datetime.min.replace(
                        tzinfo=timezone.utc
                    ),
                    reverse=True,
                )[:5]
                if comments:
                    parts.append("### Recent Comments")
                    for c in comments:
                        author = c.author.display_name if c.author else "Unknown"
                        timestamp = _format_date(c.created_at)
                        body = c.body_text or "(no text)"
                        # Truncate long comment bodies
                        if len(body) > 300:
                            body = body[:300] + "..."
                        parts.append(f"**{author}** ({timestamp}):")
                        parts.append(f"> {body}")
                        parts.append("")

            return _truncate("\n".join(parts))

        except Exception as exc:
            logger.warning("get_task_detail failed: %s: %s", type(exc).__name__, exc)
            return "Error retrieving task details. Please try again."

    # ------------------------------------------------------------------
    # 6. get_project_status
    # ------------------------------------------------------------------
    @tool
    async def get_project_status(project_id: str) -> str:
        """Get aggregated project metrics: task counts by status,
        completion percentage, overdue count, and recent activity.

        Use this when the user asks for a project dashboard or summary.

        Args:
            project_id: Project UUID or name (partial match supported).
        """
        try:
            async with db_session_factory() as db:
                resolved_id, error = await _resolve_project(project_id, db)
                if error:
                    return error
                project_id = resolved_id
                pid = UUID(project_id)

                # Fetch project with derived status
                proj_result = await db.execute(
                    select(Project)
                    .where(Project.id == pid)
                    .options(selectinload(Project.derived_status))
                )
                project = proj_result.scalar_one_or_none()
                if project is None:
                    return f"Project not found: {project_id}"

                # Fetch aggregation
                agg_result = await db.execute(
                    select(ProjectTaskStatusAgg).where(
                        ProjectTaskStatusAgg.project_id == pid
                    )
                )
                agg = agg_result.scalar_one_or_none()

                # Count overdue tasks
                today = datetime.now(timezone.utc).date()
                overdue_result = await db.execute(
                    select(func.count())
                    .select_from(Task)
                    .join(TaskStatus, Task.task_status_id == TaskStatus.id)
                    .where(
                        Task.project_id == pid,
                        Task.due_date < today,
                        Task.archived_at.is_(None),
                        TaskStatus.category != "Done",
                    )
                )
                overdue_count = overdue_result.scalar() or 0

                # Recent task updates (last 5)
                recent_result = await db.execute(
                    select(Task)
                    .where(
                        Task.project_id == pid,
                        Task.archived_at.is_(None),
                    )
                    .options(
                        selectinload(Task.task_status),
                        selectinload(Task.assignee),
                    )
                    .order_by(Task.updated_at.desc())
                    .limit(5)
                )
                recent_tasks = recent_result.scalars().unique().all()

            # Build dashboard output
            parts: list[str] = []
            parts.append(f"## Project: {project.name}")
            parts.append("")

            derived = project.derived_status
            parts.append(
                f"**Overall Status**: {derived.name if derived else 'No tasks'}"
            )
            parts.append("")

            if agg:
                total = agg.total_tasks
                done = agg.done_tasks
                pct = int((done / total) * 100) if total > 0 else 0

                parts.append("### Task Distribution")
                parts.append("| Category | Count |")
                parts.append("| --- | --- |")
                parts.append(f"| Todo | {agg.todo_tasks} |")
                parts.append(f"| In Progress / In Review | {agg.active_tasks + agg.review_tasks} |")
                parts.append(f"| Issues | {agg.issue_tasks} |")
                parts.append(f"| Done | {agg.done_tasks} |")
                parts.append(f"| **Total** | **{total}** |")
                parts.append("")
                parts.append(f"**Completion**: {pct}% ({done}/{total} tasks done)")
            else:
                parts.append("No tasks in this project yet.")

            if overdue_count > 0:
                parts.append(f"**Overdue**: {overdue_count} task(s) past due date")
            else:
                parts.append("**Overdue**: None")
            parts.append("")

            if recent_tasks:
                parts.append("### Recent Activity")
                for t in recent_tasks:
                    assignee_name = (
                        t.assignee.display_name if t.assignee else "Unassigned"
                    )
                    status_text = t.task_status.name if t.task_status else "—"
                    parts.append(
                        f"- **{t.task_key}** {t.title} "
                        f"[{status_text}] ({assignee_name}) "
                        f"— updated {_format_date(t.updated_at)}"
                    )

            return _truncate("\n".join(parts))

        except Exception as exc:
            logger.warning(
                "get_project_status failed: %s: %s", type(exc).__name__, exc
            )
            return "Error retrieving project status. Please try again."

    # ------------------------------------------------------------------
    # 7. get_overdue_tasks
    # ------------------------------------------------------------------
    @tool
    async def get_overdue_tasks(application_id: str | None = None) -> str:
        """Get all tasks that are past their due date across accessible projects.

        Use this when the user asks about deadlines, late work, or
        overdue items.

        Args:
            application_id: Optional application UUID or name (partial match supported).
        """
        try:
            accessible_project_ids = _get_ctx().get("accessible_project_ids", [])
            if not accessible_project_ids:
                return "You have no accessible projects."

            project_uuids = [UUID(pid) for pid in accessible_project_ids]
            today = datetime.now(timezone.utc).date()

            async with db_session_factory() as db:
                # Resolve application scope if provided
                if application_id:
                    resolved_id, error = await _resolve_application(application_id, db)
                    if error:
                        return error
                    application_id = resolved_id
                query = (
                    select(Task)
                    .join(TaskStatus, Task.task_status_id == TaskStatus.id)
                    .join(Project, Task.project_id == Project.id)
                    .where(
                        Task.project_id.in_(project_uuids),
                        Task.due_date < today,
                        Task.archived_at.is_(None),
                        TaskStatus.category != "Done",
                    )
                    .options(
                        selectinload(Task.task_status),
                        selectinload(Task.assignee),
                        selectinload(Task.project),
                    )
                    .order_by(Task.due_date.asc())
                )

                # Narrow to specific application if requested
                if application_id:
                    query = query.where(
                        Project.application_id == UUID(application_id)
                    )

                result = await db.execute(query)
                tasks = result.scalars().unique().all()

            if not tasks:
                scope = "this application" if application_id else "your accessible projects"
                return f"No overdue tasks found in {scope}."

            # Group by project
            grouped: dict[str, list[Task]] = {}
            for t in tasks:
                proj_name = t.project.name if t.project else "Unknown"
                grouped.setdefault(proj_name, []).append(t)

            parts: list[str] = []
            parts.append(f"## Overdue Tasks ({len(tasks)} total)")
            parts.append("")

            for proj_name, proj_tasks in grouped.items():
                parts.append(f"### {proj_name}")
                parts.append("| Key | Title | Due Date | Days Overdue | Assignee |")
                parts.append("| --- | --- | --- | --- | --- |")

                for t in proj_tasks:
                    assignee_name = (
                        t.assignee.display_name if t.assignee else "Unassigned"
                    )
                    overdue_days = _days_overdue(t.due_date) or 0
                    parts.append(
                        f"| {t.task_key} | {t.title} "
                        f"| {_format_date(t.due_date)} | {overdue_days} "
                        f"| {assignee_name} |"
                    )
                parts.append("")

            return _truncate("\n".join(parts))

        except Exception as exc:
            logger.warning(
                "get_overdue_tasks failed: %s: %s", type(exc).__name__, exc
            )
            return "Error retrieving overdue tasks. Please try again."

    # ------------------------------------------------------------------
    # 8. get_team_members
    # ------------------------------------------------------------------
    @tool
    async def get_team_members(application_id: str) -> str:
        """List members of an application and their project assignments.

        Use this when the user asks about team composition or who works
        on what.

        Args:
            application_id: Application UUID or name (partial match supported).
        """
        try:
            async with db_session_factory() as db:
                resolved_id, error = await _resolve_application(application_id, db)
                if error:
                    return error
                application_id = resolved_id
                app_uuid = UUID(application_id)
                # Fetch application with owner
                app_result = await db.execute(
                    select(Application)
                    .where(Application.id == app_uuid)
                    .options(selectinload(Application.owner))
                )
                app = app_result.scalar_one_or_none()
                if app is None:
                    return f"Application not found: {application_id}"

                # Fetch all application members
                members_result = await db.execute(
                    select(ApplicationMember)
                    .where(ApplicationMember.application_id == app_uuid)
                    .options(selectinload(ApplicationMember.user))
                )
                app_members = members_result.scalars().all()

                # Collect all user IDs (owner + members)
                user_map: dict[UUID, dict[str, Any]] = {}

                # Add owner
                if app.owner:
                    user_map[app.owner_id] = {
                        "name": app.owner.display_name or app.owner.email,
                        "role": "owner",
                        "projects": [],
                    }

                # Add members
                for m in app_members:
                    if m.user_id not in user_map:
                        user_map[m.user_id] = {
                            "name": (
                                m.user.display_name or m.user.email
                                if m.user
                                else str(m.user_id)
                            ),
                            "role": m.role,
                            "projects": [],
                        }

                # Fetch projects in this application
                proj_result = await db.execute(
                    select(Project.id, Project.name).where(
                        Project.application_id == app_uuid,
                        Project.archived_at.is_(None),
                    )
                )
                projects = proj_result.all()
                project_name_map = {row.id: row.name for row in projects}

                if projects:
                    # Fetch project members for all projects in the app
                    pm_result = await db.execute(
                        select(ProjectMember).where(
                            ProjectMember.project_id.in_(
                                [p.id for p in projects]
                            )
                        )
                    )
                    project_members = pm_result.scalars().all()

                    for pm in project_members:
                        if pm.user_id in user_map:
                            proj_name = project_name_map.get(
                                pm.project_id, "Unknown"
                            )
                            user_map[pm.user_id]["projects"].append(
                                f"{proj_name} ({pm.role})"
                            )

            # Format output
            parts: list[str] = []
            parts.append(f"## Team: {app.name}")
            parts.append("")
            parts.append("| Member | App Role | Project Assignments |")
            parts.append("| --- | --- | --- |")

            for uid, info in sorted(user_map.items(), key=lambda x: x[1]["name"]):
                projects_str = ", ".join(info["projects"]) if info["projects"] else "None"
                parts.append(
                    f"| {info['name']} | {info['role']} | {projects_str} |"
                )

            parts.append(f"\n*{len(user_map)} team member(s).*")
            return _truncate("\n".join(parts))

        except Exception as exc:
            logger.warning(
                "get_team_members failed: %s: %s", type(exc).__name__, exc
            )
            return "Error retrieving team members. Please try again."

    # ------------------------------------------------------------------
    # 9. understand_image
    # ------------------------------------------------------------------
    @tool
    async def understand_image(
        attachment_id: str,
        question: str | None = None,
    ) -> str:
        """Analyze an image attachment using vision AI.

        Use this when the user asks about a diagram, screenshot, chart,
        or any image stored as an attachment in their documents or tasks.

        Args:
            attachment_id: The attachment UUID.
            question: Optional specific question about the image.
        """
        from ...services.minio_service import MinIOService

        try:
            async with db_session_factory() as db:
                # Load attachment record
                att_result = await db.execute(
                    select(Attachment).where(
                        Attachment.id == UUID(attachment_id)
                    )
                )
                attachment = att_result.scalar_one_or_none()

                if attachment is None:
                    return f"Attachment not found: {attachment_id}"

                # H2: RBAC — check that user can access the entity
                # the attachment belongs to.
                if attachment.task_id:
                    task_result = await db.execute(
                        select(Task.project_id).where(
                            Task.id == attachment.task_id
                        )
                    )
                    project_id = task_result.scalar_one_or_none()
                    if not project_id or not _check_project_access(str(project_id)):
                        return "Access denied: you do not have access to this attachment's project."
                elif attachment.comment_id is not None:
                    # Comments belong to tasks — resolve through comment
                    comment_result = await db.execute(
                        select(Comment.task_id).where(
                            Comment.id == attachment.comment_id
                        )
                    )
                    comment_task_id = comment_result.scalar_one_or_none()
                    if not comment_task_id:
                        return "Access denied: unable to verify access permissions for this attachment."
                    task_result = await db.execute(
                        select(Task.project_id).where(
                            Task.id == comment_task_id
                        )
                    )
                    project_id = task_result.scalar_one_or_none()
                    if not project_id or not _check_project_access(str(project_id)):
                        return "Access denied: you do not have access to this attachment's project."
                else:
                    return "Access denied: unable to verify access permissions for this attachment."

                # Validate it is an image
                file_type = attachment.file_type or ""
                if not file_type.startswith("image/"):
                    return (
                        f"Attachment '{attachment.file_name}' is not an image "
                        f"(type: {file_type}). Vision analysis requires an image file."
                    )

                # Download from MinIO
                bucket = attachment.minio_bucket
                key = attachment.minio_key

                if not bucket or not key:
                    return (
                        "Attachment has no storage reference. "
                        "The file may not have been uploaded successfully."
                    )

            # Download outside the db session
            minio_svc = MinIOService()
            image_bytes = minio_svc.download_file(bucket, key)

            # Get vision provider
            async with db_session_factory() as db:
                vision_provider, model_id = await provider_registry.get_vision_provider(
                    db, _get_user_id()
                )

            # Build prompt
            prompt = question or (
                "Describe this image in detail. If it contains a diagram, "
                "flowchart, or chart, describe its structure and data."
            )

            # Call vision provider
            description = await vision_provider.describe_image(
                image_bytes=image_bytes,
                prompt=prompt,
                model=model_id,
            )

            return _truncate(description)

        except Exception as exc:
            logger.warning(
                "understand_image failed: %s: %s", type(exc).__name__, exc
            )
            return "Error analyzing image. Please try again."

    # ------------------------------------------------------------------
    # 10. request_clarification
    # ------------------------------------------------------------------
    @tool
    async def request_clarification(
        question: str,
        options: list[str] | None = None,
        context: str | None = None,
    ) -> str:
        """Ask the user a clarifying question when you need more information
        to provide a good answer.

        Use this when:
        - The request is ambiguous (e.g., "the project" but multiple exist)
        - Search results are insufficient and you need the user to narrow scope
        - Multiple valid interpretations exist and you want the user to pick one
        - You need specific details before performing a write action

        Do NOT use this for general conversation — only when ambiguity would
        lead to a wrong or unhelpful response.

        Args:
            question: The clarifying question to ask the user.
            options: Optional list of suggested answers (shown as clickable
                     buttons). Keep to 2-4 options.
            context: Optional context explaining why you are asking
                     (shown as subtitle).
        """
        clarification = {
            "type": "clarification",
            "question": question,
            "options": options,
            "context": context,
        }
        response = interrupt(clarification)

        # response is expected to be a dict with an "answer" key
        if isinstance(response, dict):
            return response.get("answer", "")
        # Fallback: if the user responded with a plain string
        return str(response)

    # ------------------------------------------------------------------
    # 11. get_applications
    # ------------------------------------------------------------------
    @tool
    async def get_applications() -> str:
        """List all applications you have access to with their IDs and names.

        Use this to discover available applications, find application IDs
        for other tools, or when the user asks about their applications.
        """
        accessible_ids = _get_ctx().get("accessible_app_ids", [])
        if not accessible_ids:
            return "You have no accessible applications."

        app_uuids = [UUID(aid) for aid in accessible_ids]

        try:
            async with db_session_factory() as db:
                result = await db.execute(
                    select(Application)
                    .where(Application.id.in_(app_uuids))
                    .order_by(Application.name)
                )
                apps = result.scalars().unique().all()

            if not apps:
                return "You have no accessible applications."

            user_id_str = _get_ctx().get("user_id", "")

            lines: list[str] = []
            lines.append("| Application | ID | Description | Role |")
            lines.append("| --- | --- | --- | --- |")

            for app in apps:
                desc = ((app.description or "—")[:80])
                try:
                    is_owner = UUID(str(app.owner_id)) == UUID(user_id_str)
                except (ValueError, AttributeError):
                    is_owner = False
                role = "owner" if is_owner else "member"
                lines.append(f"| {app.name} | {app.id} | {desc} | {role} |")

            lines.append(f"\n*{len(apps)} application(s).*")
            return _truncate("\n".join(lines))

        except Exception as exc:
            logger.warning(
                "get_applications failed: %s: %s", type(exc).__name__, exc
            )
            return "Error retrieving applications. Please try again."

    # ------------------------------------------------------------------
    # 12. browse_knowledge
    # ------------------------------------------------------------------
    @tool
    async def browse_knowledge(
        scope: str,
        scope_id: str | None = None,
        folder_id: str | None = None,
    ) -> str:
        """Browse documents and folders in a knowledge base scope.

        Use this to list, count, or explore documents and folders. Unlike
        query_knowledge (which searches content), this tool enumerates items
        by their folder structure.

        Args:
            scope: "application", "project", or "personal".
            scope_id: Application or project UUID or name (partial match
                supported). Required for application/project scope.
            folder_id: Optional folder UUID to drill into a specific folder.
        """
        from ...models.document import Document
        from ...models.document_folder import DocumentFolder

        user_id = _get_user_id()
        scope_lower = scope.lower().strip()

        if scope_lower not in ("application", "project", "personal"):
            return "Error: scope must be 'application', 'project', or 'personal'."

        scope_display = ""
        scope_uuid: UUID | None = None

        try:
            async with db_session_factory() as db:
                # Resolve scope
                if scope_lower == "application":
                    if not scope_id:
                        return "Error: scope_id is required for application scope."
                    resolved_id, error = await _resolve_application(scope_id, db)
                    if error:
                        return error
                    scope_uuid = UUID(resolved_id)
                    app_result = await db.execute(
                        select(Application.name).where(
                            Application.id == scope_uuid
                        )
                    )
                    scope_display = app_result.scalar_one_or_none() or "Application"

                elif scope_lower == "project":
                    if not scope_id:
                        return "Error: scope_id is required for project scope."
                    resolved_id, error = await _resolve_project(scope_id, db)
                    if error:
                        return error
                    scope_uuid = UUID(resolved_id)
                    proj_result = await db.execute(
                        select(Project.name).where(
                            Project.id == scope_uuid
                        )
                    )
                    scope_display = proj_result.scalar_one_or_none() or "Project"

                elif scope_lower == "personal":
                    if scope_id and scope_id.strip():
                        try:
                            given_uuid = UUID(scope_id)
                        except (ValueError, AttributeError):
                            return "Error: invalid scope_id for personal scope."
                        if given_uuid != user_id:
                            return "Access denied: you can only browse your own personal knowledge."
                    scope_uuid = user_id
                    scope_display = "Personal"

                # Build scope filter conditions
                if scope_lower == "application":
                    folder_scope = DocumentFolder.application_id == scope_uuid
                    doc_scope = Document.application_id == scope_uuid
                elif scope_lower == "project":
                    folder_scope = DocumentFolder.project_id == scope_uuid
                    doc_scope = Document.project_id == scope_uuid
                else:
                    folder_scope = DocumentFolder.user_id == scope_uuid
                    doc_scope = Document.user_id == scope_uuid

                # Resolve folder_id if given and verify it belongs to this scope
                folder_uuid: UUID | None = None
                if folder_id:
                    try:
                        folder_uuid = UUID(folder_id)
                    except (ValueError, AttributeError):
                        return f"Error: Invalid folder_id '{folder_id}'."

                    # Verify the folder belongs to the resolved scope
                    folder_check = await db.execute(
                        select(DocumentFolder.id).where(
                            DocumentFolder.id == folder_uuid,
                            folder_scope,
                        )
                    )
                    if folder_check.scalar_one_or_none() is None:
                        return f"Error: Folder '{folder_id}' not found in this scope."

                # Query folders
                folder_query = (
                    select(DocumentFolder)
                    .where(folder_scope)
                    .order_by(DocumentFolder.sort_order, DocumentFolder.name)
                    .limit(50)
                )
                if folder_uuid:
                    folder_query = folder_query.where(
                        DocumentFolder.parent_id == folder_uuid
                    )
                else:
                    folder_query = folder_query.where(
                        DocumentFolder.parent_id.is_(None)
                    )

                folder_result = await db.execute(folder_query)
                folders = folder_result.scalars().all()

                # Count docs per folder
                doc_counts: dict[UUID, int] = {}
                if folders:
                    count_result = await db.execute(
                        select(
                            Document.folder_id,
                            func.count(Document.id),
                        )
                        .where(
                            doc_scope,
                            Document.deleted_at.is_(None),
                            Document.folder_id.in_([f.id for f in folders]),
                        )
                        .group_by(Document.folder_id)
                    )
                    doc_counts = dict(count_result.all())

                # Query documents (unfiled or in target folder)
                # Always show at least 20 documents even if many folders
                remaining = max(20, 50 - len(folders))
                doc_query = (
                    select(Document)
                    .where(
                        doc_scope,
                        Document.deleted_at.is_(None),
                    )
                    .order_by(Document.sort_order, Document.title)
                    .limit(remaining)
                )
                if folder_uuid:
                    doc_query = doc_query.where(
                        Document.folder_id == folder_uuid
                    )
                else:
                    doc_query = doc_query.where(Document.folder_id.is_(None))

                doc_result = await db.execute(doc_query)
                documents = doc_result.scalars().all()

                # Total counts for the scope
                total_docs_result = await db.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(doc_scope, Document.deleted_at.is_(None))
                )
                total_docs = total_docs_result.scalar() or 0

                total_folders_result = await db.execute(
                    select(func.count())
                    .select_from(DocumentFolder)
                    .where(folder_scope)
                )
                total_folders = total_folders_result.scalar() or 0

            # Format output
            parts: list[str] = []
            scope_label = scope_lower.capitalize()
            parts.append(f"## Knowledge: {scope_display} ({scope_label})")
            parts.append("")

            if folders:
                parts.append("### Folders")
                for f in folders:
                    count = doc_counts.get(f.id, 0)
                    parts.append(
                        f"- \U0001f4c1 {f.name} ({count} docs) \u2014 id: {f.id}"
                    )
                parts.append("")

            doc_label = "Documents" if not folder_uuid else "Documents in folder"
            if documents:
                parts.append(f"### {doc_label}")
                for d in documents:
                    updated = _relative_time(d.updated_at)
                    parts.append(
                        f"- {d.title} (updated {updated}) \u2014 id: {d.id}"
                    )
                parts.append("")

            if not folders and not documents:
                parts.append("No documents or folders found in this scope.")
                parts.append("")

            total_shown = len(folders) + len(documents)
            parts.append(
                f"**Total**: {total_docs} document(s), {total_folders} folder(s)"
            )
            folder_limit_hit = len(folders) >= 50
            doc_limit_hit = len(documents) >= remaining
            if folder_limit_hit or doc_limit_hit:
                parts.append(
                    f"*(Showing {total_shown} items at this level; more may exist. "
                    "Use folder_id to drill into folders.)*"
                )

            return _truncate("\n".join(parts))

        except Exception as exc:
            logger.warning(
                "browse_knowledge failed: %s: %s", type(exc).__name__, exc
            )
            return "Error browsing knowledge base. Please try again."

    # ------------------------------------------------------------------
    # Return all tools
    # ------------------------------------------------------------------
    return [
        query_knowledge,
        sql_query,
        get_projects,
        get_tasks,
        get_task_detail,
        get_project_status,
        get_overdue_tasks,
        get_team_members,
        understand_image,
        request_clarification,
        get_applications,
        browse_knowledge,
    ]

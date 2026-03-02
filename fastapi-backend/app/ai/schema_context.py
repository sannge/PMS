"""Schema context provider for AI SQL generation.

Provides static descriptions of all scoped PostgreSQL views
(v_*) with column types, relationships, and query hints for LLM
SQL generation prompts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ColumnDescription:
    """Description of a single view column."""

    name: str
    type: str
    nullable: bool
    description: str
    enum_values: list[str] | None = None


@dataclass
class ViewDescription:
    """Description of a single scoped view."""

    name: str
    description: str
    columns: list[ColumnDescription] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Static view descriptions — verified against SQLAlchemy models 2026-02-26
# ---------------------------------------------------------------------------

VIEW_DESCRIPTIONS: list[ViewDescription] = [
    ViewDescription(
        name="v_applications",
        description="Top-level containers that group projects together.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("name", "varchar(255)", False, "Application name"),
            ColumnDescription("description", "text", True, "Optional description"),
            ColumnDescription("owner_id", "uuid", True, "FK to v_users — application owner"),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", False, "Last-update timestamp"),
        ],
        relationships=[
            "v_projects.application_id -> v_applications.id",
            "v_application_members.application_id -> v_applications.id",
            "v_documents.application_id -> v_applications.id (app-scoped docs)",
            "v_document_folders.application_id -> v_applications.id (app-scoped folders)",
        ],
        notes=[
            "Applications do NOT have a 'key' column — use v_projects.key for short codes.",
        ],
    ),
    ViewDescription(
        name="v_projects",
        description="Projects within an application; contain tasks and statuses.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("application_id", "uuid", False, "FK to v_applications"),
            ColumnDescription("name", "varchar(255)", False, "Project name"),
            ColumnDescription("key", "varchar(10)", False, "Short code used in task keys (e.g. PROJ)"),
            ColumnDescription("description", "text", True, "Optional project description"),
            ColumnDescription(
                "project_type", "varchar(20)", False, "Type of project",
                enum_values=["scrum", "kanban"],
            ),
            ColumnDescription("due_date", "date", True, "Project due date"),
            ColumnDescription("created_by", "uuid", True, "FK to v_users — user who created the project"),
            ColumnDescription("project_owner_user_id", "uuid", True, "FK to v_users — project owner"),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", False, "Last-update timestamp"),
        ],
        relationships=[
            "v_projects.application_id -> v_applications.id",
            "v_tasks.project_id -> v_projects.id",
            "v_task_statuses.project_id -> v_projects.id",
            "v_project_members.project_id -> v_projects.id",
            "v_project_assignments.project_id -> v_projects.id",
        ],
    ),
    ViewDescription(
        name="v_tasks",
        description="Issues/tasks within a project — stories, bugs, epics, subtasks.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("project_id", "uuid", False, "FK to v_projects"),
            ColumnDescription("task_key", "varchar(20)", False, "Unique key e.g. PROJ-123"),
            ColumnDescription("title", "varchar(500)", False, "Task title/summary"),
            ColumnDescription("description", "text", True, "Detailed task description (may be large)"),
            ColumnDescription(
                "task_type", "varchar(50)", False, "Type of work item",
                enum_values=["story", "task", "bug", "epic", "subtask"],
            ),
            ColumnDescription(
                "priority", "varchar(20)", False, "Priority level (default: medium)",
                enum_values=["highest", "high", "medium", "low", "lowest"],
            ),
            ColumnDescription("assignee_id", "uuid", True, "FK to v_users — assigned user"),
            ColumnDescription("reporter_id", "uuid", True, "FK to v_users — reporting user"),
            ColumnDescription("parent_id", "uuid", True, "FK to v_tasks — parent task (for subtasks)"),
            ColumnDescription("task_status_id", "uuid", False, "FK to v_task_statuses"),
            ColumnDescription("story_points", "integer", True, "Story point estimate"),
            ColumnDescription("due_date", "date", True, "Due date (date only, no time)"),
            ColumnDescription("completed_at", "timestamptz", True, "When the task was marked Done"),
            ColumnDescription("checklist_total", "integer", True, "Total checklist items (denormalized)"),
            ColumnDescription("checklist_done", "integer", True, "Completed checklist items (denormalized)"),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", False, "Last-update timestamp"),
        ],
        relationships=[
            "v_tasks.project_id -> v_projects.id",
            "v_tasks.task_status_id -> v_task_statuses.id",
            "v_tasks.assignee_id -> v_users.id",
            "v_tasks.reporter_id -> v_users.id",
            "v_tasks.parent_id -> v_tasks.id (self-referential for subtasks)",
            "v_comments.task_id -> v_tasks.id",
            "v_attachments.task_id -> v_tasks.id",
            "v_checklists.task_id -> v_tasks.id",
        ],
        notes=[
            "Join v_task_statuses on task_status_id to get status name and category.",
            "due_date is a DATE column (not timestamptz).",
        ],
    ),
    ViewDescription(
        name="v_task_statuses",
        description="Per-project task statuses with category groupings for derivation.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("project_id", "uuid", False, "FK to v_projects"),
            ColumnDescription("name", "varchar(50)", False, "Status display name (e.g. Todo, In Progress)"),
            ColumnDescription(
                "category", "varchar(20)", False, "Category for aggregation",
                enum_values=["Todo", "Active", "Issue", "Done"],
            ),
            ColumnDescription("rank", "integer", False, "Sort order for Kanban column display"),
        ],
        relationships=[
            "v_task_statuses.project_id -> v_projects.id",
            "v_tasks.task_status_id -> v_task_statuses.id",
        ],
        notes=[
            "Default statuses per project: Todo, In Progress, In Review, Issue, Done.",
            "Categories: Todo -> Todo, In Progress/In Review -> Active, Issue -> Issue, Done -> Done.",
            "Column is 'rank' (not sort_order).",
        ],
    ),
    ViewDescription(
        name="v_documents",
        description="Knowledge base documents scoped to application, project, or personal.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("application_id", "uuid", True, "FK to v_applications (app-scoped)"),
            ColumnDescription("project_id", "uuid", True, "FK to v_projects (project-scoped)"),
            ColumnDescription("user_id", "uuid", True, "FK to v_users (personal-scoped)"),
            ColumnDescription("folder_id", "uuid", True, "FK to v_document_folders (null = unfiled)"),
            ColumnDescription("title", "varchar(255)", False, "Document title"),
            ColumnDescription("content_plain", "text", True, "Plain text content for search"),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", False, "Last-update timestamp"),
        ],
        relationships=[
            "v_documents.application_id -> v_applications.id",
            "v_documents.project_id -> v_projects.id",
            "v_documents.user_id -> v_users.id",
            "v_documents.folder_id -> v_document_folders.id",
        ],
        notes=[
            "Exactly one of application_id, project_id, user_id is non-null (scope).",
            "content_plain may be large — use substring() or length() if you only need metadata.",
        ],
    ),
    ViewDescription(
        name="v_document_folders",
        description="Hierarchical folders for organizing documents within a scope.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("application_id", "uuid", True, "FK to v_applications (app-scoped)"),
            ColumnDescription("project_id", "uuid", True, "FK to v_projects (project-scoped)"),
            ColumnDescription("user_id", "uuid", True, "FK to v_users (personal-scoped)"),
            ColumnDescription("parent_id", "uuid", True, "FK to v_document_folders (null = root)"),
            ColumnDescription("name", "varchar(255)", False, "Folder display name"),
            ColumnDescription("sort_order", "integer", False, "Position within siblings"),
        ],
        relationships=[
            "v_document_folders.parent_id -> v_document_folders.id (self-referential)",
            "v_documents.folder_id -> v_document_folders.id",
        ],
        notes=[
            "Exactly one of application_id, project_id, user_id is non-null (scope).",
            "Max nesting depth is 5.",
        ],
    ),
    ViewDescription(
        name="v_comments",
        description="Task comments with plain text content for search.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("task_id", "uuid", False, "FK to v_tasks"),
            ColumnDescription("author_id", "uuid", False, "FK to v_users"),
            ColumnDescription("body_text", "text", True, "Plain text comment content"),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", True, "Last-update timestamp"),
        ],
        relationships=[
            "v_comments.task_id -> v_tasks.id",
            "v_comments.author_id -> v_users.id",
        ],
        notes=[
            "Soft-deleted comments (is_deleted=true) are excluded from the view.",
        ],
    ),
    ViewDescription(
        name="v_application_members",
        description="User membership and roles within an application.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("application_id", "uuid", False, "FK to v_applications"),
            ColumnDescription("user_id", "uuid", False, "FK to v_users"),
            ColumnDescription(
                "role", "varchar(50)", False, "User role in the application",
                enum_values=["owner", "editor", "viewer"],
            ),
            ColumnDescription("is_manager", "boolean", False, "Whether user is a manager"),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", True, "Last-update timestamp"),
        ],
        relationships=[
            "v_application_members.application_id -> v_applications.id",
            "v_application_members.user_id -> v_users.id",
        ],
    ),
    ViewDescription(
        name="v_project_members",
        description="Project-level team membership for task edit permissions.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("project_id", "uuid", False, "FK to v_projects"),
            ColumnDescription("user_id", "uuid", False, "FK to v_users"),
            ColumnDescription(
                "role", "varchar(20)", False, "Member role in the project",
                enum_values=["admin", "member"],
            ),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", True, "Last-update timestamp"),
        ],
        relationships=[
            "v_project_members.project_id -> v_projects.id",
            "v_project_members.user_id -> v_users.id",
        ],
        notes=[
            "ProjectMembers gate who can create/edit/move tasks (separate from assignments).",
        ],
    ),
    ViewDescription(
        name="v_project_assignments",
        description="Which users are assigned to work on a project.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("project_id", "uuid", False, "FK to v_projects"),
            ColumnDescription("user_id", "uuid", False, "FK to v_users"),
        ],
        relationships=[
            "v_project_assignments.project_id -> v_projects.id",
            "v_project_assignments.user_id -> v_users.id",
        ],
        notes=[
            "Tracks work assignments — different from v_project_members (permissions).",
        ],
    ),
    ViewDescription(
        name="v_users",
        description="Application users — NO password hashes or secrets exposed.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("email", "varchar(255)", False, "Email address (unique)"),
            ColumnDescription("display_name", "varchar(100)", True, "Display name"),
            ColumnDescription("avatar_url", "varchar(500)", True, "Avatar image URL"),
            ColumnDescription("created_at", "timestamptz", False, "Creation timestamp"),
            ColumnDescription("updated_at", "timestamptz", False, "Last-update timestamp"),
        ],
        notes=[
            "password_hash is deliberately excluded from this view.",
        ],
    ),
    ViewDescription(
        name="v_attachments",
        description="File attachments on tasks.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("task_id", "uuid", True, "FK to v_tasks"),
            ColumnDescription("file_name", "varchar(255)", False, "Original file name"),
            ColumnDescription("file_size", "bigint", True, "File size in bytes"),
            ColumnDescription("file_type", "varchar(100)", True, "MIME type of the file"),
            ColumnDescription("uploaded_by", "uuid", True, "FK to v_users — who uploaded the file"),
            ColumnDescription("created_at", "timestamptz", False, "Upload timestamp"),
        ],
        relationships=[
            "v_attachments.task_id -> v_tasks.id",
            "v_attachments.uploaded_by -> v_users.id",
        ],
        notes=[
            "Column is 'file_type' (not mime_type).",
        ],
    ),
    ViewDescription(
        name="v_checklists",
        description="Named checklist containers belonging to a task.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("task_id", "uuid", False, "FK to v_tasks"),
            ColumnDescription("title", "varchar(255)", False, "Checklist name"),
            ColumnDescription("rank", "varchar(50)", False, "Lexorank string for ordering within task"),
        ],
        relationships=[
            "v_checklists.task_id -> v_tasks.id",
            "v_checklist_items.checklist_id -> v_checklists.id",
        ],
        notes=[
            "Column is 'rank' (lexorank string), not sort_order.",
        ],
    ),
    ViewDescription(
        name="v_checklist_items",
        description="Individual items within a checklist.",
        columns=[
            ColumnDescription("id", "uuid", False, "Primary key"),
            ColumnDescription("checklist_id", "uuid", False, "FK to v_checklists"),
            ColumnDescription("content", "text", False, "Item text content"),
            ColumnDescription("is_done", "boolean", False, "Whether item is checked/completed"),
            ColumnDescription("rank", "varchar(50)", False, "Lexorank string for ordering within checklist"),
        ],
        relationships=[
            "v_checklist_items.checklist_id -> v_checklists.id",
        ],
        notes=[
            "Column is 'is_done' (not is_checked).",
            "Column is 'content' (not title).",
            "Column is 'rank' (lexorank string), not sort_order.",
        ],
    ),
]

# Build a lookup dict for fast access by view name
_VIEW_MAP: dict[str, ViewDescription] = {v.name: v for v in VIEW_DESCRIPTIONS}

# All valid view names
VALID_VIEW_NAMES: frozenset[str] = frozenset(_VIEW_MAP.keys())


def _format_view(view: ViewDescription) -> str:
    """Format a single ViewDescription into a text block for an LLM prompt."""
    lines: list[str] = []
    lines.append(f"### {view.name}")
    lines.append(f"-- {view.description}")
    lines.append("")

    # Columns
    for col in view.columns:
        nullable = "NULL" if col.nullable else "NOT NULL"
        enum_part = ""
        if col.enum_values:
            enum_part = f"  -- enum: {', '.join(col.enum_values)}"
        lines.append(f"  {col.name:<25} {col.type:<20} {nullable:<10} -- {col.description}{enum_part}")

    # Relationships
    if view.relationships:
        lines.append("")
        lines.append("  Relationships:")
        for rel in view.relationships:
            lines.append(f"    {rel}")

    # Notes
    if view.notes:
        lines.append("")
        lines.append("  Notes:")
        for note in view.notes:
            lines.append(f"    - {note}")

    lines.append("")
    return "\n".join(lines)


def get_schema_prompt() -> str:
    """Return the full schema text for all 13 scoped views.

    Formatted for inclusion in LLM system prompts. Target <8000 tokens.

    Returns:
        Multi-line string describing all views, columns, relationships, and notes.
    """
    parts: list[str] = [
        "# Database Schema — Scoped Read-Only Views",
        "",
        "You can query ONLY the following v_* views. All are read-only.",
        "Generate PostgreSQL-compatible SELECT statements only.",
        "LIMIT is capped at 100 rows.",
        "",
    ]
    for view in VIEW_DESCRIPTIONS:
        parts.append(_format_view(view))
    return "\n".join(parts)


def get_schema_prompt_for_views(view_names: list[str]) -> str:
    """Return schema text for a subset of views.

    Args:
        view_names: List of view names to include (e.g. ["v_tasks", "v_users"]).

    Returns:
        Multi-line string describing only the requested views.

    Raises:
        ValueError: If any view name is not recognized.
    """
    unknown = [n for n in view_names if n not in _VIEW_MAP]
    if unknown:
        raise ValueError(f"Unknown view names: {unknown}. Valid: {sorted(VALID_VIEW_NAMES)}")

    parts: list[str] = [
        "# Database Schema — Selected Scoped Views",
        "",
        "You can query ONLY the following v_* views. All are read-only.",
        "Generate PostgreSQL-compatible SELECT statements only.",
        "LIMIT is capped at 100 rows.",
        "",
    ]
    for name in view_names:
        parts.append(_format_view(_VIEW_MAP[name]))
    return "\n".join(parts)


async def validate_schema_against_db(db: AsyncSession) -> list[str]:
    """Compare static view descriptions against live database metadata.

    Queries information_schema.columns for all v_* views and reports any
    discrepancies (missing views, missing/extra columns, type mismatches).

    Args:
        db: An async SQLAlchemy session.

    Returns:
        List of warning strings. Empty list means all views match.
    """
    warnings: list[str] = []

    # Fetch all columns for v_* views from information_schema
    result = await db.execute(
        text(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name LIKE 'v\\_%' "
            "ORDER BY table_name, ordinal_position"
        )
    )
    rows = result.fetchall()

    # Build a dict: {view_name: {col_name: (data_type, is_nullable)}}
    db_views: dict[str, dict[str, tuple[str, str]]] = {}
    for table_name, column_name, data_type, is_nullable in rows:
        db_views.setdefault(table_name, {})[column_name] = (data_type, is_nullable)

    # Check each static view description against DB
    for view in VIEW_DESCRIPTIONS:
        if view.name not in db_views:
            warnings.append(f"View '{view.name}' not found in database.")
            continue

        db_cols = db_views[view.name]
        static_col_names = {col.name for col in view.columns}
        db_col_names = set(db_cols.keys())

        # Missing from DB
        for missing in sorted(static_col_names - db_col_names):
            warnings.append(
                f"View '{view.name}': column '{missing}' in static schema but not in DB."
            )

        # Extra in DB
        for extra in sorted(db_col_names - static_col_names):
            warnings.append(
                f"View '{view.name}': column '{extra}' in DB but not in static schema."
            )

        # Type/nullability checks for matching columns
        for col in view.columns:
            if col.name not in db_cols:
                continue
            db_type, db_nullable = db_cols[col.name]
            expected_nullable = "YES" if col.nullable else "NO"
            if db_nullable != expected_nullable:
                warnings.append(
                    f"View '{view.name}.{col.name}': nullable mismatch — "
                    f"static={expected_nullable}, db={db_nullable}."
                )

    # Check for DB views not in static schema
    for db_view_name in sorted(db_views.keys()):
        if db_view_name not in _VIEW_MAP:
            warnings.append(
                f"View '{db_view_name}' exists in DB but not in static schema."
            )

    if warnings:
        logger.warning("Schema validation found %d discrepancies.", len(warnings))
    else:
        logger.info("Schema validation passed — all views match.")

    return warnings

"""Blair AI agent tools package.

Exposes all read and write tools, context management functions, and
the backward-compatible ``_tool_context`` dict for test compatibility.

Usage::

    from app.ai.agent.tools import (
        ALL_READ_TOOLS,
        ALL_WRITE_TOOLS,
        set_tool_context,
        clear_tool_context,
    )
"""

from __future__ import annotations

# -- Context management (public API) ----------------------------------------
from .context import (
    _check_app_access,
    _check_project_access,
    _get_ctx,
    _get_user_id,
    _tool_context,  # noqa: F401  (kept for test backward compat, not in __all__)
    _tool_context_var,
    clear_tool_context,
    set_tool_context,
)

# -- Helpers (re-export commonly used ones for backward compat) --------------
from .helpers import (
    _format_date,
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

# -- Identity tools ----------------------------------------------------------
from .identity_tools import get_my_profile, get_my_workload

# -- Application tools -------------------------------------------------------
from .application_tools import (
    get_application_details,
    get_application_members,
    list_applications,
)

# -- Project tools -----------------------------------------------------------
from .project_tools import (
    get_overdue_tasks,
    get_project_details,
    get_project_members,
    get_project_timeline,
    list_projects,
)

# -- Task tools --------------------------------------------------------------
from .task_tools import (
    get_blocked_tasks,
    get_task_comments,
    get_task_detail,
    list_tasks,
)

# -- Knowledge tools ---------------------------------------------------------
from .knowledge_tools import (
    browse_folders,
    get_document_details,
    get_my_notes,
    list_recent_documents,
    read_document,
    search_knowledge,
)

# -- Utility tools -----------------------------------------------------------
from .utility_tools import list_capabilities, request_clarification, sql_query, understand_image

# -- Web tools ---------------------------------------------------------------
from .web_tools import WEB_TOOLS, scrape_url, web_search

# -- Write tools -------------------------------------------------------------
from .write_tools import (
    WRITE_TOOLS,
    add_task_comment,
    assign_task,
    create_document,
    create_task,
    delete_document,
    delete_task,
    export_document_pdf,
    export_to_excel,
    update_document,
    update_task,
    update_task_status,
)

# -- Application write tools ------------------------------------------------
from .application_write_tools import (
    APPLICATION_WRITE_TOOLS,
    create_application,
    delete_application,
    update_application,
)

# -- Member write tools ------------------------------------------------------
from .member_write_tools import (
    MEMBER_WRITE_TOOLS,
    add_application_member,
    remove_application_member,
    update_application_member_role,
)

# -- Project write tools -----------------------------------------------------
from .project_write_tools import (
    PROJECT_WRITE_TOOLS,
    create_project,
    delete_project,
    update_project,
)

# -- Project member write tools ----------------------------------------------
from .project_member_write_tools import (
    PROJECT_MEMBER_WRITE_TOOLS,
    add_project_member,
    remove_project_member,
    update_project_member_role,
)

# -- Checklist write tools ---------------------------------------------------
from .checklist_write_tools import (
    CHECKLIST_WRITE_TOOLS,
    add_checklist,
    add_checklist_item,
    toggle_checklist_item,
)

# ---------------------------------------------------------------------------
# Aggregated tool lists
# ---------------------------------------------------------------------------

ALL_READ_TOOLS = [
    # Identity (2)
    get_my_profile,
    get_my_workload,
    # Application (3)
    list_applications,
    get_application_details,
    get_application_members,
    # Project (5)
    list_projects,
    get_project_details,
    get_project_members,
    get_project_timeline,
    get_overdue_tasks,
    # Task (4)
    list_tasks,
    get_task_detail,
    get_task_comments,
    get_blocked_tasks,
    # Knowledge (6)
    search_knowledge,
    browse_folders,
    get_document_details,
    read_document,
    list_recent_documents,
    get_my_notes,
    # Utility (4)
    sql_query,
    understand_image,
    request_clarification,
    list_capabilities,
    # Web (2)
    web_search,
    scrape_url,
]

ALL_WRITE_TOOLS = (
    WRITE_TOOLS
    + APPLICATION_WRITE_TOOLS
    + MEMBER_WRITE_TOOLS
    + PROJECT_WRITE_TOOLS
    + PROJECT_MEMBER_WRITE_TOOLS
    + CHECKLIST_WRITE_TOOLS
)

__all__ = [
    # Context
    "set_tool_context",
    "clear_tool_context",
    "_tool_context_var",
    "_get_ctx",
    "_get_user_id",
    "_check_app_access",
    "_check_project_access",
    # Tool lists
    "ALL_READ_TOOLS",
    "ALL_WRITE_TOOLS",
    "WRITE_TOOLS",
    # All individual tools
    "get_my_profile",
    "get_my_workload",
    "list_applications",
    "get_application_details",
    "get_application_members",
    "list_projects",
    "get_project_details",
    "get_project_members",
    "get_project_timeline",
    "get_overdue_tasks",
    "list_tasks",
    "get_task_detail",
    "get_task_comments",
    "get_blocked_tasks",
    "search_knowledge",
    "browse_folders",
    "get_document_details",
    "read_document",
    "list_recent_documents",
    "get_my_notes",
    "sql_query",
    "understand_image",
    "request_clarification",
    "list_capabilities",
    "create_task",
    "update_task",
    "update_task_status",
    "assign_task",
    "add_task_comment",
    "delete_task",
    "create_document",
    "update_document",
    "delete_document",
    "export_document_pdf",
    "export_to_excel",
    # Application write
    "APPLICATION_WRITE_TOOLS",
    "create_application",
    "update_application",
    "delete_application",
    # Member write
    "MEMBER_WRITE_TOOLS",
    "add_application_member",
    "update_application_member_role",
    "remove_application_member",
    # Project write
    "PROJECT_WRITE_TOOLS",
    "create_project",
    "update_project",
    "delete_project",
    # Project member write
    "PROJECT_MEMBER_WRITE_TOOLS",
    "add_project_member",
    "update_project_member_role",
    "remove_project_member",
    # Checklist write
    "CHECKLIST_WRITE_TOOLS",
    "add_checklist",
    "add_checklist_item",
    "toggle_checklist_item",
    # Web
    "WEB_TOOLS",
    "web_search",
    "scrape_url",
    # Helpers (re-exported for backward compat)
    "_format_date",
    "_get_tool_session",
    "_parse_uuid",
    "_resolve_application",
    "_resolve_document",
    "_resolve_project",
    "_resolve_task",
    "_resolve_user",
    "_strip_markdown",
    "_truncate",
]

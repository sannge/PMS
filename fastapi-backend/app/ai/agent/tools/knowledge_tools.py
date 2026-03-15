"""Knowledge-base tools for Blair AI agent.

Tools for searching, browsing, and inspecting documents in the
knowledge base.  All tools are read-only.
"""

from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import func, or_, select

from ....models.application import Application
from ....models.document import Document
from ....models.document_folder import DocumentFolder
from ....models.project import Project
from ....models.user import User
from .context import _get_ctx, _get_user_id
from ..constants import get_selection_max_items, get_selection_threshold
from .helpers import (
    _format_date,
    _get_tool_session,
    _relative_time,
    _resolve_application,
    _resolve_document,
    _resolve_project,
    _truncate,
    _wrap_user_content,
)

logger = logging.getLogger(__name__)

_CHARS_PER_WORD = 5


def _estimate_words(char_count: int | None) -> int:
    """Estimate word count from character count (~5 chars per word)."""
    return (char_count or 0) // _CHARS_PER_WORD


def _escape_md(s: str) -> str:
    """Escape pipe and newline characters in user-authored strings for Markdown."""
    return s.replace("\r", "").replace("\n", " ").replace("|", "\\|")


def _build_sources(docs_meta: list[dict]) -> list:
    """Build SourceReference list from docs_meta dicts."""
    from ..source_references import SourceReference

    return [
        SourceReference(
            document_id=d.get("file_id") or d.get("document_id", ""),
            document_title=d.get("title", ""),
            document_type="file" if d.get("source_type") == "file" else "document",
            heading_context=d.get("heading_context", "") or None,
            chunk_text=d.get("chunk_text", ""),
            chunk_index=d.get("chunk_index", 0),
            score=d.get("score", 0.0),
            source_type=d.get("source", "semantic"),
            application_id=d.get("application_id", "") or None,
        )
        for d in docs_meta
    ]


@tool
async def search_knowledge(
    query: str,
    application: str = "",
    project: str = "",
) -> str:
    """Search the knowledge base for relevant documents and content.

    Use this when the user asks about documentation, specifications,
    meeting notes, or any written content stored in the knowledge base.

    Args:
        query: The search query in natural language.
        application: Optional application UUID or name (partial match supported).
        project: Optional project UUID or name (partial match supported).
    """
    from ...agent_tools import rag_search_tool
    from ..source_references import ToolResultWithSources, push_sources

    user_id = _get_user_id()

    try:
        async with _get_tool_session() as db:
            # Resolve scopes (supports UUID or name)
            application_id: str | None = None
            project_id: str | None = None

            if application and application.strip():
                resolved_app, err = await _resolve_application(application, db)
                if err:
                    return err
                application_id = resolved_app
            if project and project.strip():
                resolved_proj, err = await _resolve_project(project, db)
                if err:
                    return err
                project_id = resolved_proj

            # Get provider_registry from context
            ctx = _get_ctx()
            provider_registry = ctx.get("provider_registry")

            result = await rag_search_tool(
                query=query,
                user_id=user_id,
                db=db,
                provider_registry=provider_registry,
                application_id=UUID(application_id) if application_id else None,
                project_id=UUID(project_id) if project_id else None,
            )

        if not result.success:
            logger.warning("rag_search_tool error: %s", result.error)
            return "Knowledge search returned no results. Please try again."

        formatted_text = result.data or "No results found."

        # Build structured sources from metadata when available
        docs_meta = (result.metadata or {}).get("documents", [])

        # Floor at 2: never show selection UI for fewer than 2 results
        _SELECTION_MIN_RESULTS = 2
        if len(docs_meta) >= max(_SELECTION_MIN_RESULTS, get_selection_threshold()):
            # Build selection items (cap at get_selection_max_items())
            capped_meta = docs_meta[:get_selection_max_items()]
            items = []
            for i, d in enumerate(capped_meta, start=1):  # 1-based indices
                if not d.get("document_id"):
                    continue  # Skip chunks without document_id
                chunk_text = d.get("chunk_text", "")
                snippet = chunk_text[:120] + ("..." if len(chunk_text) > 120 else "")
                items.append({
                    "index": i,
                    "title": d.get("title", "Untitled"),
                    "heading": d.get("heading_context", "") or None,
                    "snippet": snippet,
                    "score": round(d.get("score", 0.0), 4),
                    "document_id": d.get("document_id", ""),
                })

            display_query = _escape_md(query[:100] + "..." if len(query) > 100 else query)
            response = interrupt({
                "type": "selection",
                "prompt": f"I found {len(items)} results for '{display_query}'. Uncheck any irrelevant ones:",
                "items": items,
            })

            # Type guard: interrupt response must be a dict
            if not isinstance(response, dict):
                logger.warning("search_knowledge: unexpected interrupt response type %s", type(response))
                return "Unexpected response format. Please try the search again."

            # Handle skip
            if response.get("skipped"):
                return "User indicated none of these results are relevant. Ask them to rephrase their query."

            # Handle selection — validate and filter to selected indices
            selected: set[int] = set()
            if "selected_indices" in response:
                raw = response["selected_indices"]
                if not isinstance(raw, list):
                    raw = []
                raw = raw[:get_selection_max_items()]
                valid_range = range(1, len(capped_meta) + 1)
                for idx in raw:
                    # bool is a subclass of int in Python; exclude it explicitly
                    if not isinstance(idx, int) or isinstance(idx, bool):
                        continue
                    if idx in valid_range:
                        selected.add(idx)
            else:
                # Malformed response (no skipped AND no selected_indices)
                return "Unexpected response format. Please try the search again."

            if not selected:
                return "User deselected all results. Ask if they want to refine their search query."

            filtered_meta = [
                d for i, d in enumerate(capped_meta, start=1)
                if i in selected
            ]
            sources = _build_sources(filtered_meta)
            lines: list[str] = []
            for idx, d in enumerate(filtered_meta, start=1):
                title = _escape_md(d.get("title", "Untitled"))
                heading = _escape_md(d.get("heading_context", ""))
                score = d.get("score", 0.0)
                source = _escape_md(d.get("source", "semantic"))
                chunk = d.get("chunk_text", "")
                header = f"[{idx}] {title}"
                if heading:
                    header += f" [{heading}]"
                header += f" (score: {score:.4f}, source: {source})"
                lines.append(header)
                lines.append(_wrap_user_content(chunk))
                lines.append("")
            filtered_text = "\n".join(lines)
            tool_result = ToolResultWithSources(
                text=filtered_text, sources=sources
            )
            push_sources(sources)
            # H4: Use 16K cap to match RAG output budget (avoid double truncation)
            return _truncate(tool_result.format_for_llm(), max_len=16000)

        elif docs_meta:
            sources = _build_sources(docs_meta)
            tool_result = ToolResultWithSources(
                text=formatted_text, sources=sources
            )
            push_sources(sources)
            # H4: Use 16K cap to match RAG output budget (avoid double truncation)
            return _truncate(tool_result.format_for_llm(), max_len=16000)

        return _truncate(formatted_text, max_len=16000)

    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning("search_knowledge failed: %s: %s", type(exc).__name__, exc)
        return "Error searching knowledge base. Please try again."


@tool
async def read_document(document_id: str) -> str:
    """Read the full content of a specific document.

    Returns the plain-text content of the document, capped at 12,000
    characters.  Use this when you need the actual content of a document
    (not just search snippets).

    Args:
        document_id: The document UUID.
    """
    _MAX_READ_CHARS = 12_000

    try:
        user_id = _get_user_id()
        doc_uuid: UUID
        try:
            doc_uuid = UUID(document_id)
        except (ValueError, AttributeError):
            return f"Error: Invalid document_id '{document_id}'."

        async with _get_tool_session() as db:
            # Fetch document with RBAC check
            from ....services.permission_service import PermissionService

            result = await db.execute(
                select(
                    Document.id,
                    Document.title,
                    Document.content_plain,
                    Document.application_id,
                    Document.project_id,
                    Document.user_id,
                ).where(
                    Document.id == doc_uuid,
                    Document.deleted_at.is_(None),
                )
            )
            row = result.one_or_none()
            if not row:
                return f"Document '{document_id}' not found."

            # RBAC: check the user can view this document's scope
            perm_service = PermissionService(db)
            scope_type: str
            scope_id: UUID | None
            if row.application_id:
                scope_type = "application"
                scope_id = row.application_id
            elif row.project_id:
                scope_type = "project"
                scope_id = row.project_id
            else:
                scope_type = "personal"
                scope_id = row.user_id

            # R2-14: Guard against personal-scope docs with NULL user_id
            if scope_type == "personal" and scope_id is None:
                return "Access denied: you do not have permission to read this document."

            if not await perm_service.check_can_view_knowledge(
                user_id, scope_type, scope_id
            ):
                return "Access denied: you do not have permission to read this document."

            content = row.content_plain or ""
            title = _escape_md(row.title or "Untitled")

            if not content.strip():
                return f"## {title}\n\n(This document has no text content.)"

            if len(content) > _MAX_READ_CHARS:
                content = content[:_MAX_READ_CHARS] + "\n\n... (content truncated)"

            return f"## {title}\n\n{content}"

    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning(
            "read_document failed: %s: %s", type(exc).__name__, exc
        )
        return "Error reading document. Please try again."


@tool
async def browse_folders(
    scope: str,
    scope_id: str = "",
    folder_id: str = "",
) -> str:
    """Browse documents and folders in a knowledge base scope.

    Use this to list, count, or explore documents and folders. Unlike
    search_knowledge (which searches content), this tool enumerates items
    by their folder structure.

    Args:
        scope: "application", "project", or "personal".
        scope_id: Application or project UUID or name (partial match
            supported). Required for application/project scope.
        folder_id: Optional folder UUID to drill into a specific folder.
    """
    user_id = _get_user_id()
    scope_lower = scope.lower().strip()

    if scope_lower not in ("application", "project", "personal"):
        return "Error: scope must be 'application', 'project', or 'personal'."

    scope_display = ""
    scope_uuid: UUID | None = None

    try:
        async with _get_tool_session() as db:
            # Resolve scope
            if scope_lower == "application":
                if not scope_id or not scope_id.strip():
                    return "Error: scope_id is required for application scope."
                resolved_id, error = await _resolve_application(scope_id, db)
                if error:
                    return error
                scope_uuid = UUID(resolved_id)  # type: ignore[arg-type]
                app_result = await db.execute(
                    select(Application.name).where(Application.id == scope_uuid)
                )
                scope_display = app_result.scalar_one_or_none() or "Application"

            elif scope_lower == "project":
                if not scope_id or not scope_id.strip():
                    return "Error: scope_id is required for project scope."
                resolved_id, error = await _resolve_project(scope_id, db)
                if error:
                    return error
                scope_uuid = UUID(resolved_id)  # type: ignore[arg-type]
                proj_result = await db.execute(
                    select(Project.name).where(Project.id == scope_uuid)
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

            # Resolve folder_id if given
            folder_uuid: UUID | None = None
            if folder_id and folder_id.strip():
                try:
                    folder_uuid = UUID(folder_id)
                except (ValueError, AttributeError):
                    return f"Error: Invalid folder_id '{folder_id}'."

                folder_check = await db.execute(
                    select(DocumentFolder.id).where(
                        DocumentFolder.id == folder_uuid,
                        folder_scope,
                    )
                )
                if folder_check.scalar_one_or_none() is None:
                    return f"Error: Folder '{folder_id}' not found in this scope."

            # Query folders — select only needed columns (DB-R2-001)
            folder_query = (
                select(DocumentFolder.id, DocumentFolder.name)
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
            folders = folder_result.all()

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

            # Query documents — select only needed columns (DB-005)
            remaining = max(20, 50 - len(folders))
            doc_query = (
                select(
                    Document.id,
                    Document.title,
                    Document.updated_at,
                    Document.sort_order,
                )
                .where(
                    doc_scope,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.sort_order, Document.title)
                .limit(remaining)
            )
            if folder_uuid:
                doc_query = doc_query.where(Document.folder_id == folder_uuid)
            else:
                doc_query = doc_query.where(Document.folder_id.is_(None))

            doc_result = await db.execute(doc_query)
            documents = doc_result.all()

            # Total counts
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
        parts.append(f"## Knowledge: {_escape_md(scope_display)} ({scope_label})")
        parts.append("")

        if folders:
            parts.append("### Folders")
            for f in folders:
                count = doc_counts.get(f.id, 0)
                parts.append(
                    f"- \U0001f4c1 {_escape_md(f.name)} ({count} docs) \u2014 id: {f.id}"
                )
            parts.append("")

        doc_label = "Documents" if not folder_uuid else "Documents in folder"
        if documents:
            parts.append(f"### {doc_label}")
            for d in documents:
                updated = _relative_time(d.updated_at)
                parts.append(
                    f"- {_escape_md(d.title)} (updated {updated}) \u2014 id: {d.id}"
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
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning(
            "browse_folders failed: %s: %s", type(exc).__name__, exc
        )
        return "Error browsing knowledge base. Please try again."


@tool
async def get_document_details(doc: str) -> str:
    """Get detailed information about a specific document.

    Returns title, scope, folder path, creator, timestamps, word count,
    and embedding status.

    Args:
        doc: Document UUID or title (partial match supported).
    """
    try:
        async with _get_tool_session() as db:
            resolved_id, error = await _resolve_document(doc, db)
            if error:
                return error
            doc_uuid = UUID(resolved_id)  # type: ignore[arg-type]

            # Single query with outerjoins for creator, folder, app, and project.
            # Use column projection to avoid loading heavy content_json and
            # content_markdown columns (DB-013).  Use func.length() for word
            # count estimation instead of loading the full content_plain.
            from sqlalchemy.orm import aliased

            CreatorUser = aliased(User)

            result = await db.execute(
                select(
                    Document.id,
                    Document.title,
                    Document.application_id,
                    Document.project_id,
                    Document.created_at,
                    Document.updated_at,
                    Document.embedding_status,
                    func.length(Document.content_plain).label("char_count"),
                    CreatorUser.display_name.label("creator_display_name"),
                    DocumentFolder.name.label("folder_name"),
                    Application.name.label("app_name"),
                    Project.name.label("project_name"),
                )
                .outerjoin(CreatorUser, Document.created_by == CreatorUser.id)
                .outerjoin(DocumentFolder, Document.folder_id == DocumentFolder.id)
                .outerjoin(Application, Document.application_id == Application.id)
                .outerjoin(Project, Document.project_id == Project.id)
                .where(Document.id == doc_uuid)
            )
            row = result.one_or_none()
            if not row:
                return f"Document '{doc}' not found."

            creator_name = _escape_md(row.creator_display_name or "Unknown user")
            folder_name = _escape_md(row.folder_name or "\u2014")

            # Scope info
            scope_info = "Personal"
            if row.application_id and row.app_name:
                scope_info = f"Application: {_escape_md(row.app_name)}"
            elif row.project_id and row.project_name:
                scope_info = f"Project: {_escape_md(row.project_name)}"

        word_count = _estimate_words(row.char_count)

        lines = [
            f"## {row.title}",
            "",
            f"- **ID**: `{row.id}`",
            f"- **Scope**: {scope_info}",
            f"- **Folder**: {folder_name}",
            f"- **Created by**: {creator_name}",
            f"- **Created**: {_format_date(row.created_at)}",
            f"- **Updated**: {_format_date(row.updated_at)}",
            f"- **Word count**: {word_count:,}",
            f"- **Embedding status**: {row.embedding_status or 'none'}",
            "",
        ]

        return _truncate("\n".join(lines))

    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning(
            "get_document_details failed: %s: %s", type(exc).__name__, exc
        )
        return "Error retrieving document details. Please try again."


@tool
async def list_recent_documents(scope: str = "", limit: int = 10) -> str:
    """List recently modified documents ordered by update time.

    Args:
        scope: Optional scope filter -- "application", "project", or "personal".
               Leave empty for all accessible documents.
        limit: Maximum number of documents to return (1-50, default 10).
    """
    try:
        limit = max(1, min(50, limit))
        ctx = _get_ctx()
        accessible_app_ids = ctx.get("accessible_app_ids", [])
        accessible_project_ids = ctx.get("accessible_project_ids", [])
        user_id_str = ctx.get("user_id")

        async with _get_tool_session() as db:
            # Build scope filter
            scope_filters = []
            scope_lower = scope.lower().strip() if scope else ""

            if scope_lower == "application":
                if accessible_app_ids:
                    app_uuids = [UUID(aid) for aid in accessible_app_ids]
                    scope_filters.append(Document.application_id.in_(app_uuids))
            elif scope_lower == "project":
                if accessible_project_ids:
                    proj_uuids = [UUID(pid) for pid in accessible_project_ids]
                    scope_filters.append(Document.project_id.in_(proj_uuids))
            elif scope_lower == "personal":
                if user_id_str:
                    scope_filters.append(Document.user_id == UUID(user_id_str))
            else:
                # All accessible scopes
                if accessible_app_ids:
                    app_uuids = [UUID(aid) for aid in accessible_app_ids]
                    scope_filters.append(Document.application_id.in_(app_uuids))
                if accessible_project_ids:
                    proj_uuids = [UUID(pid) for pid in accessible_project_ids]
                    scope_filters.append(Document.project_id.in_(proj_uuids))
                if user_id_str:
                    scope_filters.append(Document.user_id == UUID(user_id_str))

            if not scope_filters:
                return "No accessible documents found."

            # Select only needed columns + char_count for word estimate (DB-003)
            result = await db.execute(
                select(
                    Document.id,
                    Document.title,
                    Document.application_id,
                    Document.project_id,
                    Document.user_id,
                    Document.updated_at,
                    func.length(Document.content_plain).label("char_count"),
                )
                .where(
                    or_(*scope_filters),
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.updated_at.desc())
                .limit(limit)
            )
            documents = result.all()

        if not documents:
            return "No documents found."

        lines = [
            "## Recent Documents",
            "",
            "| Title | Scope | Updated | Words |",
            "| --- | --- | --- | --- |",
        ]

        for d in documents:
            if d.application_id:
                scope_label = "App"
            elif d.project_id:
                scope_label = "Project"
            else:
                scope_label = "Personal"

            word_count = _estimate_words(d.char_count)
            lines.append(
                f"| {_escape_md(d.title)} | {scope_label} | "
                f"{_relative_time(d.updated_at)} | {word_count:,} |"
            )

        lines.append(f"\n*{len(documents)} document(s) shown.*")
        return _truncate("\n".join(lines))

    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning(
            "list_recent_documents failed: %s: %s", type(exc).__name__, exc
        )
        return "Error retrieving recent documents. Please try again."


@tool
async def get_my_notes() -> str:
    """Get your personal knowledge base documents.

    Returns all non-deleted documents in your personal scope, organized
    by folder.  No arguments required.
    """
    try:
        user_id = _get_user_id()

        async with _get_tool_session() as db:
            # Folders — select only needed columns (DB-R2-003)
            folder_result = await db.execute(
                select(DocumentFolder.id, DocumentFolder.name)
                .where(DocumentFolder.user_id == user_id)
                .order_by(DocumentFolder.sort_order, DocumentFolder.name)
                .limit(200)
            )
            folders = folder_result.all()
            folder_map = {f.id: f.name for f in folders}

            # Documents — select only needed columns + char_count (DB-004)
            doc_result = await db.execute(
                select(
                    Document.id,
                    Document.title,
                    Document.folder_id,
                    Document.updated_at,
                    func.length(Document.content_plain).label("char_count"),
                )
                .where(
                    Document.user_id == user_id,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.updated_at.desc())
                .limit(100)
            )
            documents = doc_result.all()

        if not documents:
            return "You have no personal notes."

        # Group by folder
        by_folder: dict[str, list] = {}
        for d in documents:
            folder_name = folder_map.get(d.folder_id, "Unfiled") if d.folder_id else "Unfiled"
            by_folder.setdefault(folder_name, []).append(d)

        lines = [
            "## My Notes",
            "",
            f"*{len(documents)} document(s) total*",
            "",
        ]

        for folder_name in sorted(by_folder):
            docs = by_folder[folder_name]
            lines.append(f"### {_escape_md(folder_name)} ({len(docs)})")
            for d in docs:
                word_count = _estimate_words(d.char_count)
                lines.append(
                    f"- {_escape_md(d.title)} ({word_count:,} words, updated {_relative_time(d.updated_at)}) "
                    f"\u2014 id: {d.id}"
                )
            lines.append("")

        if len(documents) >= 100:
            lines.append("*(Showing first 100 notes. More may exist.)*")

        return _truncate("\n".join(lines))

    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning("get_my_notes failed: %s: %s", type(exc).__name__, exc)
        return "Error retrieving your notes. Please try again."

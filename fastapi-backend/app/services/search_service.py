"""Full-text document search via Meilisearch with PostgreSQL FTS fallback.

Provides:
- Meilisearch client management (init, get index/client)
- Query sanitization
- RBAC scope-based filter construction (cached in Redis)
- Fire-and-forget document indexing (create/update/soft-delete/restore)
- Synchronous index removal (hard delete)
- PostgreSQL FTS fallback when Meilisearch is unavailable
- Health check and consistency checker
- Full reindex with atomic index swap
"""

import html as html_mod
import json
import logging
import re
import time
from datetime import datetime, timezone
from uuid import UUID

from meilisearch_python_sdk import AsyncClient
from meilisearch_python_sdk.index import AsyncIndex
from meilisearch_python_sdk.models.settings import TypoTolerance, MinWordSizeForTypos
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application
from app.models.application_member import ApplicationMember
from app.models.document import Document
from app.models.project import Project

from ..ai.config_service import get_agent_config

logger = logging.getLogger(__name__)

_cfg = get_agent_config()

# Control character pattern
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Meilisearch highlight tag constants
_MARK_OPEN = "<mark>"
_MARK_CLOSE = "</mark>"

MAX_OCCURRENCES_PER_DOC = 5  # cap occurrences per document to avoid huge lists


# Runtime config getters (NOT frozen module-level constants)
def _get_max_content_length() -> int:
    return get_agent_config().get_int("search.max_content_length", 300_000)


def _get_scope_cache_ttl() -> int:
    return get_agent_config().get_int("search.scope_cache_ttl", 30)


def _get_snippet_context_chars() -> int:
    return get_agent_config().get_int("search.snippet_context_chars", 60)

# Index settings (configure BEFORE adding documents)
MEILISEARCH_INDEX_SETTINGS = {
    "searchableAttributes": [
        "title",           # Highest priority -- title matches rank first
        "file_name",       # File names also searchable
        "content_plain",   # Main body text
    ],
    "filterableAttributes": [
        "application_id",
        "project_id",
        "user_id",
        "folder_id",
        "content_type",
        "mime_type",
        "deleted_at",
    ],
    "sortableAttributes": [
        "updated_at",
        "title",
    ],
    # content_plain is included so the backend can extract per-occurrence
    # snippets.  It is stripped from the response before sending to the client.
    "displayedAttributes": [
        "id",
        "title",
        "file_name",
        "content_plain",
        "content_type",
        "mime_type",
        "application_id",
        "project_id",
        "user_id",
        "folder_id",
        "updated_at",
        "created_by",
    ],
    "rankingRules": [
        "words",
        "typo",
        "proximity",
        "attribute",
        "sort",
        "exactness",
        "updated_at:desc",   # Custom: prefer recently updated docs
    ],
    "typoTolerance": TypoTolerance(
        enabled=True,
        min_word_size_for_typos=MinWordSizeForTypos(one_typo=5, two_typos=9),
        disable_on_numbers=True,
    ),
}


# ---- Circuit Breaker for Meilisearch ----

_meili_failure_count: int = 0
_meili_circuit_open_until: float = 0.0  # Unix timestamp when circuit closes
def _get_meili_failure_threshold() -> int:
    return get_agent_config().get_int("search.circuit_failure_threshold", 3)


def _get_meili_circuit_open_seconds() -> int:
    return get_agent_config().get_int("search.circuit_open_seconds", 30)


def _meili_circuit_is_open() -> bool:
    """Check if the Meilisearch circuit breaker is open (service considered down)."""
    if _meili_failure_count < _get_meili_failure_threshold():
        return False
    return time.time() < _meili_circuit_open_until


def _meili_record_success() -> None:
    """Record a successful Meilisearch call, closing the circuit."""
    global _meili_failure_count, _meili_circuit_open_until
    _meili_failure_count = 0
    _meili_circuit_open_until = 0.0


def _meili_record_failure() -> None:
    """Record a Meilisearch failure. Opens circuit after threshold consecutive failures."""
    global _meili_failure_count, _meili_circuit_open_until
    _meili_failure_count += 1
    if _meili_failure_count >= _get_meili_failure_threshold():
        _meili_circuit_open_until = time.time() + _get_meili_circuit_open_seconds()
        logger.warning(
            "Meilisearch circuit breaker OPEN after %d failures (will retry in %ds)",
            _meili_failure_count,
            _get_meili_circuit_open_seconds(),
        )


# ---- Client Management ----

_meili_client: AsyncClient | None = None
_meili_index: AsyncIndex | None = None


async def init_meilisearch() -> None:
    """Initialize Meilisearch client and configure index. Called during app lifespan startup."""
    global _meili_client, _meili_index

    if not settings.meilisearch_api_key:
        logger.warning(
            "meilisearch_api_key is empty -- Meilisearch is unauthenticated. "
            "Set MEILISEARCH_API_KEY in production."
        )

    _meili_client = AsyncClient(
        url=settings.meilisearch_url,
        api_key=settings.meilisearch_api_key,
        timeout=settings.meilisearch_timeout,
    )

    # Create index if it doesn't exist
    try:
        _meili_index = await _meili_client.get_index(settings.meilisearch_index_name)
    except Exception:
        _meili_index = await _meili_client.create_index(
            settings.meilisearch_index_name, primary_key="id"
        )

    # Configure index settings (wait for each task to complete before proceeding)
    task_info = await _meili_index.update_searchable_attributes(
        MEILISEARCH_INDEX_SETTINGS["searchableAttributes"]
    )
    await _meili_client.wait_for_task(task_info.task_uid)

    task_info = await _meili_index.update_filterable_attributes(
        MEILISEARCH_INDEX_SETTINGS["filterableAttributes"]
    )
    await _meili_client.wait_for_task(task_info.task_uid)

    task_info = await _meili_index.update_sortable_attributes(
        MEILISEARCH_INDEX_SETTINGS["sortableAttributes"]
    )
    await _meili_client.wait_for_task(task_info.task_uid)

    task_info = await _meili_index.update_displayed_attributes(
        MEILISEARCH_INDEX_SETTINGS["displayedAttributes"]
    )
    await _meili_client.wait_for_task(task_info.task_uid)

    task_info = await _meili_index.update_ranking_rules(
        MEILISEARCH_INDEX_SETTINGS["rankingRules"]
    )
    await _meili_client.wait_for_task(task_info.task_uid)

    task_info = await _meili_index.update_typo_tolerance(
        MEILISEARCH_INDEX_SETTINGS["typoTolerance"]
    )
    await _meili_client.wait_for_task(task_info.task_uid)

    logger.info("Meilisearch initialized: index=%s", settings.meilisearch_index_name)


def get_meili_index() -> AsyncIndex:
    """Get the Meilisearch index instance."""
    if _meili_index is None:
        raise RuntimeError("Meilisearch not initialized")
    return _meili_index


def get_meili_client() -> AsyncClient:
    """Get the Meilisearch client instance."""
    if _meili_client is None:
        raise RuntimeError("Meilisearch not initialized")
    return _meili_client


# ---- Query Sanitization ----

def sanitize_search_query(q: str) -> str:
    """Sanitize search query: strip control characters, collapse whitespace."""
    q = CONTROL_CHAR_RE.sub('', q)
    q = ' '.join(q.split())
    return q.strip()


# ---- RBAC Filter Construction ----

async def _get_user_application_ids(
    db: AsyncSession, user_id: UUID
) -> list[UUID]:
    """Single query: all applications where user is a member OR owner."""
    result = await db.execute(
        select(ApplicationMember.application_id)
        .where(ApplicationMember.user_id == user_id)
        .union(
            select(Application.id).where(Application.owner_id == user_id)
        )
    )
    return list(result.scalars().all())


async def _get_projects_in_applications(
    db: AsyncSession, app_ids: list[UUID]
) -> list[UUID]:
    """Batch query: all project IDs belonging to the given applications.

    A user who is an application member can view ALL project-scoped documents
    in that application, regardless of direct project membership.
    (permission_service.py check_can_view_knowledge line 226-230)
    """
    if not app_ids:
        return []
    result = await db.execute(
        select(Project.id)
        .where(Project.application_id.in_(app_ids))
    )
    return list(result.scalars().all())


async def get_fallback_scope_ids(
    db: AsyncSession, user_id: UUID
) -> tuple[list[UUID], list[UUID]]:
    """Public helper: return (app_ids, project_ids) for a user's RBAC scope.

    Used by the PG FTS fallback in document_search.py to avoid importing
    private helper functions.
    """
    app_ids = await _get_user_application_ids(db, user_id)
    project_ids = await _get_projects_in_applications(db, app_ids)
    return app_ids, project_ids


async def build_search_filter(
    db: AsyncSession, user_id: UUID
) -> list[list[str] | str]:
    """Build Meilisearch RBAC filter using array syntax (no string interpolation).

    Returns array-of-arrays filter:
    - Outer array = AND
    - Inner arrays = OR

    Always includes deleted_at IS NULL.

    Security: All IDs come from DB queries, validated via UUID() constructor.
    Never put user-controlled values in filter strings.
    Uses Meilisearch IN operator for batch filtering to reduce filter size.
    """
    app_ids = await _get_user_application_ids(db, user_id)
    project_ids = await _get_projects_in_applications(db, app_ids)

    # Build OR filter for scope access using IN operator for batch filtering
    scope_filters: list[str] = []

    if app_ids:
        app_id_list = ", ".join(f"'{UUID(str(aid))}'" for aid in app_ids)
        scope_filters.append(f"application_id IN [{app_id_list}]")

    if project_ids:
        proj_id_list = ", ".join(f"'{UUID(str(pid))}'" for pid in project_ids)
        scope_filters.append(f"project_id IN [{proj_id_list}]")

    # Personal documents
    scope_filters.append(f"user_id = '{UUID(str(user_id))}'")

    if not scope_filters:
        # User has no access to anything -- return impossible filter
        scope_filters.append("user_id = 'no-access'")

    # Array syntax: [[scope_or_filters], "deleted_at IS NULL"]
    return [scope_filters, "deleted_at IS NULL"]


async def get_cached_scope_filter(
    redis_service, db: AsyncSession, user_id: UUID
) -> list[list[str] | str]:
    """Get or compute the user's RBAC search filter with Redis caching (30s TTL).

    Falls back to uncached filter if Redis is unavailable.

    Args:
        redis_service: RedisService instance
        db: Database session
        user_id: User UUID
    """
    cache_key = f"search:scope:{user_id}"

    # Try Redis cache first, fall back to uncached if Redis fails
    try:
        cached = await redis_service.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Corrupted scope cache for user %s, deleting key", user_id)
                try:
                    await redis_service.delete(cache_key)
                except Exception:
                    pass
    except Exception:
        logger.warning("Redis unavailable for scope cache, building filter without cache")
        return await build_search_filter(db, user_id)

    filter_expr = await build_search_filter(db, user_id)

    try:
        await redis_service.set(cache_key, json.dumps(filter_expr), ttl=_get_scope_cache_ttl())
    except Exception:
        logger.warning("Failed to cache scope filter in Redis")

    return filter_expr


# ---- Document Indexing ----

def build_search_doc_data(
    doc: Document,
    project_application_id: UUID | None = None,
) -> dict:
    """Extract all fields needed for search indexing from an ORM object.

    Call this BEFORE db.commit() while ORM attributes are still loaded.
    The returned dict can safely be passed to index_document_from_data()
    after commit without risk of expired attribute access.

    Args:
        doc: Document ORM instance (attributes must be loaded).
        project_application_id: For project-scoped docs, the parent application_id.

    Returns:
        Plain dict ready for Meilisearch indexing.
    """
    application_id = doc.application_id
    if application_id is None and doc.project_id is not None and project_application_id is not None:
        application_id = project_application_id

    return {
        "id": str(doc.id),
        "title": doc.title,
        "content_plain": (doc.content_plain or "")[:_get_max_content_length()],
        "application_id": str(application_id) if application_id else None,
        "project_id": str(doc.project_id) if doc.project_id else None,
        "user_id": str(doc.user_id) if doc.user_id else None,
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "created_by": str(doc.created_by) if doc.created_by else None,
        "updated_at": int(doc.updated_at.timestamp()),
        "deleted_at": None,
    }


async def index_document_from_data(data: dict) -> None:
    """Fire-and-forget document indexing from a pre-built dict.

    Use build_search_doc_data() to create the dict BEFORE db.commit(),
    then pass it here AFTER commit. This avoids SQLAlchemy expired-attribute
    errors (MissingGreenlet) that occur when accessing ORM attributes after commit.

    Args:
        data: Dict with keys matching Meilisearch document schema.
    """
    if _meili_circuit_is_open():
        logger.debug("Skipping index for doc %s: circuit breaker open", data.get("id"))
        return
    try:
        index = get_meili_index()
        await index.update_documents([data])
        _meili_record_success()
    except Exception as exc:
        _meili_record_failure()
        logger.error("Failed to index document %s: %s", data.get("id"), exc)
        # Document save still succeeds -- consistency checker will catch this


async def index_document(
    doc: Document,
    project_application_id: UUID | None = None,
) -> None:
    """Fire-and-forget document indexing. Does NOT fail the document save.

    DEPRECATED: Prefer build_search_doc_data() + index_document_from_data()
    to avoid expired ORM attribute access after commit.

    Args:
        doc: Document ORM instance.
        project_application_id: If doc is project-scoped (application_id is None,
            project_id is set), pass the project's application_id so that the
            indexed record includes it for scope filtering.
    """
    data = build_search_doc_data(doc, project_application_id)
    await index_document_from_data(data)


async def index_document_soft_delete(doc_id: UUID) -> None:
    """Update deleted_at in Meilisearch for soft-deleted document (fire-and-forget).

    The document stays in the index but is excluded by 'deleted_at IS NULL' filter.
    This allows restore without full re-indexing.
    """
    try:
        index = get_meili_index()
        await index.update_documents([{
            "id": str(doc_id),
            "deleted_at": int(time.time()),
        }])
    except Exception as exc:
        logger.error("Failed to update deleted_at for doc %s: %s", doc_id, exc)


async def index_document_restore(doc_id: UUID) -> None:
    """Clear deleted_at in Meilisearch for a restored document. Fire-and-forget.

    Args:
        doc_id: UUID of the restored document.
    """
    try:
        index = get_meili_index()
        await index.update_documents([{
            "id": str(doc_id),
            "deleted_at": None,
        }])
    except Exception as exc:
        logger.error("Failed to restore index for doc %s: %s", doc_id, exc)


async def remove_document_from_index(doc_id: UUID) -> None:
    """Synchronously remove document from Meilisearch (for hard deletes).

    Uses synchronous call with timeout because ghost results pointing to
    non-existent documents are worse than a slightly slower hard delete.
    """
    try:
        index = get_meili_index()
        task = await index.delete_document(str(doc_id))
        # Wait for completion with timeout
        client = get_meili_client()
        await client.wait_for_task(task.task_uid, timeout_in_ms=5000)
    except Exception as exc:
        logger.warning(
            "Failed to remove doc %s from search index (will be caught by consistency checker): %s",
            doc_id, exc
        )


# ---- File Indexing ----

def build_search_file_data(
    ff,
    project_application_id: UUID | None = None,
) -> dict:
    """Extract all fields needed for search indexing from a FolderFile ORM object.

    Call this BEFORE db.commit() while ORM attributes are still loaded.
    The returned dict can safely be passed to index_document_from_data()
    after commit.

    The Meilisearch document id is prefixed with "file_" to distinguish
    file entries from document entries in the shared index.

    Args:
        ff: FolderFile ORM instance (attributes must be loaded).
        project_application_id: For project-scoped files, the parent application_id.

    Returns:
        Plain dict ready for Meilisearch indexing.
    """
    application_id = ff.application_id
    if application_id is None and ff.project_id is not None and project_application_id is not None:
        application_id = project_application_id

    return {
        "id": f"file_{ff.id}",
        "title": ff.display_name,
        "file_name": ff.display_name,
        "content_plain": (ff.content_plain or "")[:_get_max_content_length()],
        "content_type": "file",
        "mime_type": ff.mime_type,
        "application_id": str(application_id) if application_id else None,
        "project_id": str(ff.project_id) if ff.project_id else None,
        "user_id": str(ff.user_id) if ff.user_id else None,
        "folder_id": str(ff.folder_id) if ff.folder_id else None,
        "created_by": str(ff.created_by) if ff.created_by else None,
        "updated_at": int(ff.updated_at.timestamp()),
        "deleted_at": None,
    }


async def index_file_from_data(data: dict) -> None:
    """Fire-and-forget file indexing from a pre-built dict.

    Same as index_document_from_data but for files.

    Args:
        data: Dict with keys matching Meilisearch document schema (id prefixed with "file_").
    """
    await index_document_from_data(data)


async def remove_file_from_index(file_id: UUID) -> None:
    """Remove a file from the Meilisearch index.

    Uses the "file_" prefixed ID to match the indexed document.
    """
    try:
        index = get_meili_index()
        task = await index.delete_document(f"file_{file_id}")
        client = get_meili_client()
        await client.wait_for_task(task.task_uid, timeout_in_ms=5000)
    except Exception as exc:
        logger.warning(
            "Failed to remove file %s from search index: %s",
            file_id, exc,
        )


# ---- Search ----


def _pg_extract_snippet(text: str, start: int, length: int) -> str:
    """Extract a snippet around a match position and wrap the match in <mark>.

    Used only by the PostgreSQL FTS fallback path.

    Returns an HTML string with the matched portion inside <mark> tags
    and surrounding context trimmed to word boundaries.
    """
    ctx = _get_snippet_context_chars()
    snippet_start = max(0, start - ctx)
    snippet_end = min(len(text), start + length + ctx)

    # Expand to word boundaries
    if snippet_start > 0:
        space = text.rfind(' ', snippet_start - 20, snippet_start)
        if space != -1:
            snippet_start = space + 1
    if snippet_end < len(text):
        space = text.find(' ', snippet_end, snippet_end + 20)
        if space != -1:
            snippet_end = space

    before = html_mod.escape(text[snippet_start:start])
    match = html_mod.escape(text[start:start + length])
    after = html_mod.escape(text[start + length:snippet_end])

    prefix = "..." if snippet_start > 0 else ""
    suffix = "..." if snippet_end < len(text) else ""

    return f"{prefix}{before}<mark>{match}</mark>{after}{suffix}"


def _highlight_terms_in_window(content: str, start: int, length: int, terms: set[str]) -> str:
    """Extract a window around a position and highlight matched terms via regex.

    Used for additional occurrences (occurrenceIndex > 0) where Meilisearch
    only provides the best-match crop for the first occurrence.
    """
    ctx = _get_snippet_context_chars()
    window_start = max(0, start - ctx)
    window_end = min(len(content), start + length + ctx)

    # Expand to word boundaries
    if window_start > 0:
        space = content.rfind(' ', max(0, window_start - 20), window_start)
        if space != -1:
            window_start = space + 1
    if window_end < len(content):
        space = content.find(' ', window_end, min(len(content), window_end + 20))
        if space != -1:
            window_end = space

    window = content[window_start:window_end]
    # Escape HTML first
    window = html_mod.escape(window)

    prefix = "..." if window_start > 0 else ""
    suffix = "..." if window_end < len(content) else ""

    # Drop single-character terms — they highlight random characters everywhere
    highlight_terms = {t for t in terms if len(t) >= 2}
    if not highlight_terms:
        return f"{prefix}{window}{suffix}"

    # Build one combined pattern (longest first to avoid partial overlap)
    sorted_terms = sorted(highlight_terms, key=len, reverse=True)
    combined_pattern = "|".join(re.escape(html_mod.escape(t)) for t in sorted_terms)
    compiled = re.compile(f"(?i)({combined_pattern})")
    window = compiled.sub(r"<mark>\1</mark>", window)

    return f"{prefix}{window}{suffix}"


def _sanitize_meili_snippet(html: str) -> str:
    """Strip all HTML except <mark>/<mark> from a Meilisearch formatted snippet.

    Meilisearch inserts <mark> around matches but does not escape the
    original content. This function escapes everything except the exact
    <mark> and </mark> tags that Meilisearch inserts.
    """
    if not html:
        return html
    # Split on <mark> and </mark>, escape each text segment, rejoin with tags
    result: list[str] = []
    remaining = html
    while remaining:
        # Find next <mark> or </mark>
        mark_open_pos = remaining.find(_MARK_OPEN)
        mark_close_pos = remaining.find(_MARK_CLOSE)

        # Determine which tag comes first
        if mark_open_pos == -1 and mark_close_pos == -1:
            # No more tags — escape the rest
            result.append(html_mod.escape(remaining))
            break

        if mark_close_pos == -1 or (mark_open_pos != -1 and mark_open_pos < mark_close_pos):
            # <mark> comes first
            result.append(html_mod.escape(remaining[:mark_open_pos]))
            result.append(_MARK_OPEN)
            remaining = remaining[mark_open_pos + len(_MARK_OPEN):]
        else:
            # </mark> comes first
            result.append(html_mod.escape(remaining[:mark_close_pos]))
            result.append(_MARK_CLOSE)
            remaining = remaining[mark_close_pos + len(_MARK_CLOSE):]

    return "".join(result)


def _byte_to_char_offset(encoded: bytes, byte_offset: int) -> int:
    """Convert a UTF-8 byte offset to a Python character offset.

    Meilisearch _matchesPosition returns byte offsets, but Python strings
    use character offsets. For ASCII-only content they're identical, but
    documents with multi-byte chars (box-drawing, emoji, CJK, PDF extracted
    text) will have diverging offsets.

    Args:
        encoded: Pre-encoded UTF-8 bytes of the text (cached per hit to
                 avoid re-encoding on every position).
        byte_offset: Byte offset from Meilisearch.
    """
    byte_offset = min(byte_offset, len(encoded))
    return len(encoded[:byte_offset].decode("utf-8", errors="replace"))


def _expand_hits(hits: list[dict]) -> list[dict]:
    """Expand search hits into multiple entries per document.

    First entry uses Meilisearch's native crop+highlight. Additional entries
    use regex highlighting in windows around each match position, with
    byte-to-char offset conversion for multi-byte content (PDF, DOCX, etc.).

    Each entry carries ``matchCount`` (total matches in the document) and
    ``occurrenceIndex`` (0-based position of this entry).
    """
    expanded: list[dict] = []

    for hit in hits:
        content = hit.get("content_plain") or ""
        positions = (hit.get("_matchesPosition") or {}).get("content_plain", [])
        formatted = hit.get("_formatted") or {}

        # Base fields (exclude content_plain and internal Meilisearch keys)
        base = {
            k: v for k, v in hit.items()
            if k not in ("content_plain", "_matchesPosition", "_formatted",
                         "_rankingScore", "_rankingScoreDetails")
        }
        hit_id = hit.get("id", "")
        if isinstance(hit_id, str) and hit_id.startswith("file_"):
            base["content_type"] = "file"
            base["file_name"] = hit.get("file_name") or hit.get("title", "")
        base["_formatted"] = {"title": formatted.get("title", hit.get("title", ""))}

        # Collect matched terms from title (byte-to-char converted for Unicode safety)
        title_positions = (hit.get("_matchesPosition") or {}).get("title", [])
        title_text = hit.get("title") or ""
        title_encoded = title_text.encode("utf-8") if title_text else b""
        matched_terms_set: set[str] = set()
        for p in title_positions:
            if p.get("length", 0) > 1:
                cs = _byte_to_char_offset(title_encoded, p.get("start", 0))
                ce = _byte_to_char_offset(title_encoded, p.get("start", 0) + p.get("length", 0))
                if cs < len(title_text):
                    matched_terms_set.add(title_text[cs:ce].lower())

        # Pre-encode content once per hit for byte-to-char offset conversion
        content_encoded = content.encode("utf-8") if content else b""

        # Collect content terms using byte-to-char conversion
        for pos in positions:
            byte_start = pos.get("start", 0)
            byte_length = pos.get("length", 0)
            if byte_length > 1:
                char_start = _byte_to_char_offset(content_encoded, byte_start)
                char_end = _byte_to_char_offset(content_encoded, byte_start + byte_length)
                if char_start < len(content):
                    matched_terms_set.add(content[char_start:char_end].lower())

        valid_positions = [p for p in positions if p.get("length", 0) > 0]
        total_matches = len(valid_positions) or (1 if title_positions else 0)

        if not positions:
            # Title-only match
            formatted_snippet = formatted.get("content_plain", "")
            if not formatted_snippet and content:
                truncated = content[:200]
                space = truncated.rfind(' ', 150)
                if space > 0:
                    truncated = truncated[:space]
                formatted_snippet = html_mod.escape(truncated) + "..."
            base["snippet"] = _sanitize_meili_snippet(formatted_snippet) if formatted_snippet else ""
            base["occurrenceIndex"] = 0
            base["matchCount"] = total_matches
            base["matchedTerms"] = list(matched_terms_set)
            expanded.append(base)
            continue

        doc_start_idx = len(expanded)

        # Deduplicate and expand up to MAX_OCCURRENCES_PER_DOC
        seen_char_starts: set[int] = set()
        occ_idx = 0
        for pos in positions:
            if occ_idx >= MAX_OCCURRENCES_PER_DOC:
                break
            byte_start = pos.get("start", 0)
            byte_length = pos.get("length", 0)
            if byte_length == 0:
                continue

            char_start = _byte_to_char_offset(content_encoded, byte_start)
            char_length = _byte_to_char_offset(content_encoded, byte_start + byte_length) - char_start

            if char_start in seen_char_starts or char_start >= len(content):
                continue
            seen_char_starts.add(char_start)

            entry = {**base}
            if occ_idx == 0:
                formatted_snippet = formatted.get("content_plain", "")
                if formatted_snippet:
                    entry["snippet"] = _sanitize_meili_snippet(formatted_snippet)
                elif content and matched_terms_set:
                    entry["snippet"] = _highlight_terms_in_window(
                        content, char_start, char_length, matched_terms_set,
                    )
                else:
                    entry["snippet"] = ""
            else:
                entry["snippet"] = _highlight_terms_in_window(
                    content, char_start, char_length, matched_terms_set,
                )
            entry["occurrenceIndex"] = occ_idx
            entry["matchCount"] = total_matches
            expanded.append(entry)
            occ_idx += 1

        unique_terms = list(matched_terms_set)
        for entry in expanded[doc_start_idx:]:
            entry["matchedTerms"] = unique_terms

    return expanded


async def search_documents(
    query: str,
    filter_expr: list,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Execute search against Meilisearch with RBAC filter and highlighting.

    Returns a plain dict with camelCase keys matching the frontend contract.
    Each document hit is expanded into one entry per content match occurrence.

    Raises RuntimeError if the circuit breaker is open so the caller can
    fall back to PostgreSQL FTS.
    """
    if _meili_circuit_is_open():
        raise RuntimeError("Meilisearch circuit breaker is open")

    # Drop single-character words — they match everywhere and pollute results
    # (e.g. "pm d" → "pm" instead of matching every "d" in every document).
    words = [w for w in query.split() if len(w) >= 2]
    if not words:
        # All words were single chars — use original query as-is (prefix search)
        words = query.split()
    query = " ".join(words)

    # Use "all" for short queries (1-2 words) to require every term,
    # "last" for longer queries so partial matches still surface results.
    strategy = "all" if len(words) <= 2 else "last"

    try:
        index = get_meili_index()
        results = await index.search(
            query,
            filter=filter_expr,
            limit=limit,
            offset=offset,
            matching_strategy=strategy,
            attributes_to_highlight=["title", "content_plain"],   # Fix 1: add content_plain
            attributes_to_crop=["content_plain"],                 # Fix 1: crop around match
            crop_length=30,                                       # ~30 words context
            crop_marker="...",                                    # ellipsis at crop boundary
            highlight_pre_tag="<mark>",
            highlight_post_tag="</mark>",
            show_ranking_score=False,
            show_matches_position=True,   # keep for occurrence counting + matchedTerms extraction
        )
        _meili_record_success()
    except RuntimeError:
        # Re-raise RuntimeError (from get_meili_index or circuit breaker)
        raise
    except Exception:
        _meili_record_failure()
        raise

    expanded = _expand_hits(results.hits)
    return {
        "hits": expanded,
        "estimatedTotalHits": results.estimated_total_hits,
        "hitsBeforeExpansion": len(results.hits),
        "processingTimeMs": results.processing_time_ms,
        "query": results.query,
    }


# ---- PostgreSQL FTS Fallback ----

async def search_documents_pg_fallback(
    db: AsyncSession,
    query: str,
    accessible_app_ids: list[UUID],
    project_ids: list[UUID],
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
    scope_application_id: str | None = None,
    scope_project_id: str | None = None,
) -> dict:
    """PostgreSQL FTS fallback when Meilisearch is unavailable.

    Uses tsvector + ts_headline for full-text search with highlighting.
    Lacks prefix search and per-word typo tolerance, but provides ~80%
    of search functionality.

    Optional scope_application_id / scope_project_id narrow results to a
    specific application or project (still within RBAC bounds).
    """
    from sqlalchemy import text

    # Validate scope IDs as UUIDs to prevent SQL injection via f-string interpolation
    from uuid import UUID as _UUID
    if scope_application_id:
        try:
            _UUID(scope_application_id)
        except (ValueError, AttributeError):
            return {"documents": [], "files": [], "total_count": 0}
    if scope_project_id:
        try:
            _UUID(scope_project_id)
        except (ValueError, AttributeError):
            return {"documents": [], "files": [], "total_count": 0}

    all_scope_ids = [str(uid) for uid in accessible_app_ids]
    all_project_ids = [str(uid) for uid in project_ids]

    # Build optional scope narrowing clause
    # For application scope: include both direct app docs AND project-scoped docs
    # under that application (project docs have application_id=NULL in DB but
    # belong to a project whose application_id matches).
    scope_clause = ""
    scope_params: dict[str, str] = {}
    if scope_application_id:
        scope_clause += (
            " AND (d.application_id = :scope_app_id"
            " OR d.project_id IN ("
            '   SELECT p.id FROM "Projects" p WHERE p.application_id = :scope_app_id'
            " ))"
        )
        scope_params["scope_app_id"] = scope_application_id
    if scope_project_id:
        scope_clause += " AND d.project_id = :scope_proj_id"
        scope_params["scope_proj_id"] = scope_project_id

    base_params = {
        "query": query,
        "app_ids": all_scope_ids,
        "project_ids": all_project_ids,
        "user_id": str(user_id),
        **scope_params,
    }

    # --- Query 1: Documents (indexed via search_vector) ---
    doc_sql = text(f"""
        SELECT
            d.id,
            d.title,
            d.application_id,
            d.project_id,
            d.user_id,
            d.folder_id,
            d.updated_at,
            d.created_by,
            ts_headline(
                'english', d.title, plainto_tsquery('english', :query),
                'StartSel=<mark>, StopSel=</mark>, MaxWords=20, MinWords=10'
            ) AS title_highlighted,
            ts_headline(
                'english', COALESCE(d.content_plain, ''), plainto_tsquery('english', :query),
                'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=20'
            ) AS snippet,
            ts_rank(
                d.search_vector,
                plainto_tsquery('english', :query)
            ) AS rank,
            COUNT(*) OVER() AS total_count
        FROM "Documents" d
        WHERE
            d.deleted_at IS NULL
            AND (
                d.application_id = ANY(:app_ids)
                OR d.project_id = ANY(:project_ids)
                OR d.user_id = :user_id
            )
            AND d.search_vector @@ plainto_tsquery('english', :query)
            {scope_clause}
        ORDER BY rank DESC
        LIMIT :limit OFFSET :offset
    """)

    doc_result = await db.execute(doc_sql, {**base_params, "limit": limit, "offset": offset})
    doc_rows = doc_result.fetchall()

    # --- Query 2: FolderFiles (no search_vector — use inline tsvector) ---
    file_scope_clause = ""
    file_scope_params: dict[str, str] = {}
    if scope_application_id:
        file_scope_clause += (
            " AND (f.application_id = :scope_app_id"
            " OR f.project_id IN ("
            '   SELECT p.id FROM "Projects" p WHERE p.application_id = :scope_app_id'
            " ))"
        )
        file_scope_params["scope_app_id"] = scope_application_id
    if scope_project_id:
        file_scope_clause += " AND f.project_id = :scope_proj_id"
        file_scope_params["scope_proj_id"] = scope_project_id

    file_sql = text(f"""
        SELECT
            f.id,
            f.display_name AS title,
            f.application_id,
            f.project_id,
            f.user_id,
            f.folder_id,
            f.updated_at,
            f.created_by,
            ts_headline(
                'english', f.display_name, plainto_tsquery('english', :query),
                'StartSel=<mark>, StopSel=</mark>, MaxWords=20, MinWords=10'
            ) AS title_highlighted,
            ts_headline(
                'english', COALESCE(f.content_plain, ''), plainto_tsquery('english', :query),
                'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=20'
            ) AS snippet,
            ts_rank(
                to_tsvector('english', COALESCE(f.display_name, '') || ' ' || COALESCE(f.content_plain, '')),
                plainto_tsquery('english', :query)
            ) AS rank,
            COUNT(*) OVER() AS total_count
        FROM "FolderFiles" f
        WHERE
            f.deleted_at IS NULL
            AND f.content_plain IS NOT NULL
            AND (
                f.application_id = ANY(:app_ids)
                OR f.project_id = ANY(:project_ids)
                OR f.user_id = :user_id
            )
            AND to_tsvector('english', COALESCE(f.display_name, '') || ' ' || COALESCE(f.content_plain, ''))
                @@ plainto_tsquery('english', :query)
            {file_scope_clause}
        ORDER BY rank DESC
        LIMIT :limit OFFSET :offset
    """)

    file_result = await db.execute(file_sql, {**base_params, **file_scope_params, "limit": limit, "offset": offset})
    file_rows = file_result.fetchall()

    # --- Merge results by rank, cap at limit ---
    hits = []
    doc_total = doc_rows[0].total_count if doc_rows else 0
    file_total = file_rows[0].total_count if file_rows else 0
    total_count = doc_total + file_total

    def _row_to_hit(row, content_type: str, id_prefix: str = "") -> dict:
        return {
            "id": f"{id_prefix}{row.id}",
            "title": row.title,
            "content_type": content_type,
            "application_id": str(row.application_id) if row.application_id else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "folder_id": str(row.folder_id) if row.folder_id else None,
            "updated_at": int(row.updated_at.timestamp()) if row.updated_at else None,
            "created_by": str(row.created_by) if row.created_by else None,
            "_formatted": {
                "title": _sanitize_meili_snippet(row.title_highlighted) if row.title_highlighted else "",
                "content_plain": _sanitize_meili_snippet(row.snippet) if row.snippet else "",
            },
            "snippet": _sanitize_meili_snippet(row.snippet) if row.snippet else "",
            "occurrenceIndex": 0,
            "matchCount": 1,
            "matchedTerms": [t for t in query.lower().split() if len(t) >= 2],
        }

    # Interleave by rank descending
    di, fi = 0, 0
    while len(hits) < limit and (di < len(doc_rows) or fi < len(file_rows)):
        d_rank = doc_rows[di].rank if di < len(doc_rows) else -1
        f_rank = file_rows[fi].rank if fi < len(file_rows) else -1
        if d_rank >= f_rank:
            hits.append(_row_to_hit(doc_rows[di], "document"))
            di += 1
        else:
            hits.append(_row_to_hit(file_rows[fi], "file", "file_"))
            fi += 1

    return {
        "hits": hits,
        "estimatedTotalHits": total_count,
        "processingTimeMs": 0,
        "query": query,
        "fallback": True,
    }


# ---- Health Check ----

async def check_search_health() -> dict:
    """Check Meilisearch availability and return stats.

    Returns only status and document count -- no error details exposed to clients.
    """
    try:
        client = get_meili_client()
        await client.health()
        index = get_meili_index()
        stats = await index.get_stats()
        return {
            "status": "healthy",
            "documents_indexed": stats.number_of_documents,
        }
    except Exception as e:
        logger.warning("Meilisearch health check failed: %s", e)
        return {
            "status": "degraded",
        }


# ---- Consistency Checker (arq background job) ----

async def check_search_index_consistency(ctx: dict) -> None:
    """Compare PostgreSQL documents with Meilisearch index.
    Re-index any documents where updated_at > last_indexed_at.
    Runs every 5 minutes via arq.
    """
    global _meili_index

    from sqlalchemy import func as sa_func
    from app.database import async_session_maker
    from app.services.redis_service import redis_service as app_redis_service

    # Lazy re-init: if Meilisearch was unavailable during worker startup,
    # attempt to initialize now so transient outages don't permanently
    # disable the consistency checker.
    if _meili_index is None:
        try:
            await init_meilisearch()
            logger.info("Meilisearch lazy-initialized by consistency checker")
        except Exception as exc:
            logger.warning("Consistency check skipped: Meilisearch init failed: %s", exc)
            return

    # Use redis from ctx if available, otherwise use the app-level redis_service
    redis = ctx.get("redis") or (app_redis_service if app_redis_service.is_connected else None)

    if redis is None:
        logger.error("Consistency check skipped: redis unavailable")
        return

    # Create our own db session since arq worker doesn't provide one
    db = ctx.get("db")
    own_session = False
    if db is None:
        db = async_session_maker()
        own_session = True

    try:
        index = get_meili_index()
        stats = await index.get_stats()
        meili_count = stats.number_of_documents

        # Meilisearch count includes soft-deleted docs (deleted_at != NULL),
        # so compare against total PG docs (active + soft-deleted) for drift detection
        result = await db.execute(select(sa_func.count(Document.id)))
        pg_total_count = result.scalar() or 0

        # Also count active files (Meilisearch index contains both docs and files)
        from app.models.folder_file import FolderFile as FF
        file_count_result = await db.execute(
            select(sa_func.count(FF.id)).where(FF.deleted_at.is_(None))
        )
        pg_active_file_count = file_count_result.scalar() or 0

        # Compare total indexed (docs + soft-deleted docs + files) against Meilisearch
        expected_meili_count = pg_total_count + pg_active_file_count
        if abs(expected_meili_count - meili_count) > 10:  # tolerance for in-flight indexing
            logger.warning(
                "Search index drift: expected=%d (docs=%d, files=%d), Meilisearch=%d",
                expected_meili_count, pg_total_count, pg_active_file_count, meili_count,
            )

        # Find documents updated since last check (DB-012: keyset pagination).
        # Track the maximum updated_at actually processed rather than wall
        # clock time, so no documents are missed if the job runs slowly or
        # the clock drifts.
        last_check_key = "search:last_consistency_check"
        since_raw = await redis.get(last_check_key)
        since = float(since_raw) if since_raw else 0

        since_dt = datetime.fromtimestamp(since, tz=timezone.utc)

        # Keyset pagination: process batches of 500 ordered by updated_at
        # to avoid skipping documents when there are >1000 stale rows.
        batch_size = 500
        total_reindexed = 0
        max_updated_at = since_dt

        while True:
            result = await db.execute(
                select(
                    Document.id,
                    Document.title,
                    Document.content_plain,
                    Document.application_id,
                    Document.project_id,
                    Document.user_id,
                    Document.folder_id,
                    Document.created_by,
                    Document.updated_at,
                    Document.deleted_at,
                    Project.application_id.label("project_app_id"),
                )
                .outerjoin(Project, Document.project_id == Project.id)
                .where(Document.updated_at > max_updated_at)
                .order_by(Document.updated_at.asc())
                .limit(batch_size)
            )
            stale_rows = result.all()

            if not stale_rows:
                break

            # Circuit breaker check before sending batches
            if _meili_circuit_is_open():
                logger.info("Consistency check: circuit breaker open, skipping Meilisearch writes")
                break  # exit the while loop, don't advance cursor

            reindex_batch: list[dict] = []
            soft_delete_batch: list[dict] = []
            batch_max_updated_at = max_updated_at  # tentative max for this batch

            for row in stale_rows:
                if row.deleted_at:
                    soft_delete_batch.append({
                        "id": str(row.id),
                        "deleted_at": int(row.deleted_at.timestamp()),
                    })
                else:
                    app_id = row.application_id or row.project_app_id
                    reindex_batch.append({
                        "id": str(row.id),
                        "title": row.title,
                        "content_plain": (row.content_plain or "")[:_get_max_content_length()],
                        "application_id": str(app_id) if app_id else None,
                        "project_id": str(row.project_id) if row.project_id else None,
                        "user_id": str(row.user_id) if row.user_id else None,
                        "folder_id": str(row.folder_id) if row.folder_id else None,
                        "created_by": str(row.created_by) if row.created_by else None,
                        "updated_at": int(row.updated_at.timestamp()),
                        "deleted_at": None,
                    })

                if row.updated_at and row.updated_at > batch_max_updated_at:
                    batch_max_updated_at = row.updated_at

            # Send batches -- only advance cursor on SUCCESS
            batch_ok = True
            if reindex_batch:
                try:
                    idx = get_meili_index()
                    await idx.update_documents(reindex_batch)
                    _meili_record_success()
                except Exception as exc:
                    _meili_record_failure()
                    logger.error("Batch document reindex failed (%d docs): %s", len(reindex_batch), exc)
                    batch_ok = False
            if soft_delete_batch:
                try:
                    idx = get_meili_index()
                    await idx.update_documents(soft_delete_batch)
                    _meili_record_success()
                except Exception as exc:
                    _meili_record_failure()
                    logger.error("Batch soft-delete failed (%d docs): %s", len(soft_delete_batch), exc)
                    batch_ok = False

            if batch_ok:
                max_updated_at = batch_max_updated_at
            # else: cursor stays, same batch retried next run

            total_reindexed += len(stale_rows)

            # Safety cap: don't process more than 5000 per run
            if total_reindexed >= 5000:
                logger.warning(
                    "Consistency check hit 5000-row safety cap, will continue next run"
                )
                break

            # If we got fewer than batch_size, we've processed everything
            if len(stale_rows) < batch_size:
                break

        if total_reindexed:
            logger.info("Re-indexed %d stale documents", total_reindexed)

        # Store the max updated_at timestamp we actually processed
        await redis.set(last_check_key, str(max_updated_at.timestamp()))

        # MED-15: Also scan FolderFiles for consistency
        try:
            from app.models.folder_file import FolderFile

            file_last_check_key = "search:last_file_consistency_check"
            file_since_raw = await redis.get(file_last_check_key)
            file_since = float(file_since_raw) if file_since_raw else 0
            file_since_dt = datetime.fromtimestamp(file_since, tz=timezone.utc)

            file_total_reindexed = 0
            file_max_updated_at = file_since_dt

            while True:
                # Circuit breaker check before sending batches
                if _meili_circuit_is_open():
                    logger.info("Consistency check: circuit breaker open, skipping file Meilisearch writes")
                    break

                file_result = await db.execute(
                    select(
                        FolderFile.id,
                        FolderFile.display_name,
                        FolderFile.content_plain,
                        FolderFile.mime_type,
                        FolderFile.application_id,
                        FolderFile.project_id,
                        FolderFile.user_id,
                        FolderFile.folder_id,
                        FolderFile.created_by,
                        FolderFile.updated_at,
                        FolderFile.deleted_at,
                        Project.application_id.label("project_app_id"),
                    )
                    .outerjoin(Project, FolderFile.project_id == Project.id)
                    .where(FolderFile.updated_at > file_max_updated_at)
                    .order_by(FolderFile.updated_at.asc())
                    .limit(batch_size)
                )
                stale_files = file_result.all()

                if not stale_files:
                    break

                file_delete_ids: list[str] = []
                file_reindex_batch: list[dict] = []
                file_batch_max_updated_at = file_max_updated_at  # tentative max

                for row in stale_files:
                    if row.deleted_at:
                        file_delete_ids.append(f"file_{row.id}")
                    else:
                        app_id = row.application_id or row.project_app_id
                        file_reindex_batch.append({
                            "id": f"file_{row.id}",
                            "title": row.display_name,
                            "file_name": row.display_name,
                            "content_plain": (row.content_plain or "")[:_get_max_content_length()],
                            "content_type": "file",
                            "mime_type": row.mime_type,
                            "application_id": str(app_id) if app_id else None,
                            "project_id": str(row.project_id) if row.project_id else None,
                            "user_id": str(row.user_id) if row.user_id else None,
                            "folder_id": str(row.folder_id) if row.folder_id else None,
                            "created_by": str(row.created_by) if row.created_by else None,
                            "updated_at": int(row.updated_at.timestamp()),
                            "deleted_at": None,
                        })

                    if row.updated_at and row.updated_at > file_batch_max_updated_at:
                        file_batch_max_updated_at = row.updated_at

                # Send batches -- only advance cursor on SUCCESS
                file_batch_ok = True
                if file_delete_ids:
                    try:
                        await index.delete_documents(file_delete_ids)
                        _meili_record_success()
                    except Exception as exc:
                        _meili_record_failure()
                        logger.error("Batch file delete failed: %s", exc)
                        file_batch_ok = False
                if file_reindex_batch:
                    try:
                        await index.update_documents(file_reindex_batch)
                        _meili_record_success()
                    except Exception as exc:
                        _meili_record_failure()
                        logger.error("Batch file reindex failed: %s", exc)
                        file_batch_ok = False

                if file_batch_ok:
                    file_max_updated_at = file_batch_max_updated_at
                # else: cursor stays, same batch retried next run

                file_total_reindexed += len(stale_files)
                if file_total_reindexed >= 2000 or len(stale_files) < batch_size:
                    break

            if file_total_reindexed:
                logger.info("Re-indexed %d stale files", file_total_reindexed)
            await redis.set(file_last_check_key, str(file_max_updated_at.timestamp()))
        except Exception as file_exc:
            logger.warning("File consistency check failed: %s", file_exc)

    except Exception as exc:
        logger.error("Consistency check failed: %s", exc)
    finally:
        if own_session:
            await db.close()


# ---- Full Reindex (Admin) ----

async def full_reindex(db: AsyncSession) -> dict:
    """Rebuild entire Meilisearch index using index swap pattern.

    Creates a temporary index, populates it, then atomically swaps.
    Eliminates the empty-index window during re-indexing.
    Estimated time: ~1 minute per 10,000 documents.
    """
    client = get_meili_client()
    temp_index_name = f"{settings.meilisearch_index_name}_rebuild"

    # 1. Create temporary index
    await client.delete_index_if_exists(temp_index_name)
    temp_index = await client.create_index(temp_index_name, primary_key="id")

    # 2. Configure settings on temp index (wait for each task)
    task_info = await temp_index.update_searchable_attributes(
        MEILISEARCH_INDEX_SETTINGS["searchableAttributes"]
    )
    await client.wait_for_task(task_info.task_uid)

    task_info = await temp_index.update_filterable_attributes(
        MEILISEARCH_INDEX_SETTINGS["filterableAttributes"]
    )
    await client.wait_for_task(task_info.task_uid)

    task_info = await temp_index.update_sortable_attributes(
        MEILISEARCH_INDEX_SETTINGS["sortableAttributes"]
    )
    await client.wait_for_task(task_info.task_uid)

    task_info = await temp_index.update_displayed_attributes(
        MEILISEARCH_INDEX_SETTINGS["displayedAttributes"]
    )
    await client.wait_for_task(task_info.task_uid)

    task_info = await temp_index.update_ranking_rules(
        MEILISEARCH_INDEX_SETTINGS["rankingRules"]
    )
    await client.wait_for_task(task_info.task_uid)

    task_info = await temp_index.update_typo_tolerance(
        MEILISEARCH_INDEX_SETTINGS["typoTolerance"]
    )
    await client.wait_for_task(task_info.task_uid)

    # 3. Batch-load all active documents (select only needed columns, 1000 per batch).
    # Uses keyset pagination (WHERE id > last_id ORDER BY id) instead of OFFSET
    # to avoid O(N*batch) scan degradation on large tables.
    # Outerjoin Project to resolve application_id for project-scoped docs.
    batch_size = 1000
    last_id = None
    total = 0

    while True:
        query = (
            select(
                Document.id,
                Document.title,
                Document.content_plain,
                Document.application_id,
                Document.project_id,
                Document.user_id,
                Document.folder_id,
                Document.created_by,
                Document.updated_at,
                Project.application_id.label("project_app_id"),
            )
            .outerjoin(Project, Document.project_id == Project.id)
            .where(Document.deleted_at.is_(None))
        )
        if last_id is not None:
            query = query.where(Document.id > last_id)
        query = query.order_by(Document.id).limit(batch_size)

        result = await db.execute(query)
        rows = result.all()
        if not rows:
            break

        last_id = rows[-1].id

        batch = [{
            "id": str(row.id),
            "title": row.title,
            "content_plain": (row.content_plain or "")[:_get_max_content_length()],
            "application_id": str(row.application_id or row.project_app_id) if (row.application_id or row.project_app_id) else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "folder_id": str(row.folder_id) if row.folder_id else None,
            "created_by": str(row.created_by) if row.created_by else None,
            "updated_at": int(row.updated_at.timestamp()),
            "deleted_at": None,
        } for row in rows]

        await temp_index.add_documents(batch)
        total += len(rows)

    # 3b. Batch-load all active files with extracted content
    from app.models.folder_file import FolderFile

    file_last_id = None
    file_total = 0
    while True:
        file_query = (
            select(
                FolderFile.id,
                FolderFile.display_name,
                FolderFile.content_plain,
                FolderFile.mime_type,
                FolderFile.application_id,
                FolderFile.project_id,
                FolderFile.user_id,
                FolderFile.folder_id,
                FolderFile.created_by,
                FolderFile.updated_at,
                Project.application_id.label("project_app_id"),
            )
            .outerjoin(Project, FolderFile.project_id == Project.id)
            .where(FolderFile.deleted_at.is_(None))
        )
        if file_last_id is not None:
            file_query = file_query.where(FolderFile.id > file_last_id)
        file_query = file_query.order_by(FolderFile.id).limit(batch_size)

        file_result = await db.execute(file_query)
        file_rows = file_result.all()
        if not file_rows:
            break

        file_last_id = file_rows[-1].id

        file_batch = [{
            "id": f"file_{row.id}",
            "title": row.display_name,
            "file_name": row.display_name,
            "content_plain": (row.content_plain or "")[:_get_max_content_length()],
            "content_type": "file",
            "mime_type": row.mime_type,
            "application_id": str(row.application_id or row.project_app_id) if (row.application_id or row.project_app_id) else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "folder_id": str(row.folder_id) if row.folder_id else None,
            "created_by": str(row.created_by) if row.created_by else None,
            "updated_at": int(row.updated_at.timestamp()),
            "deleted_at": None,
        } for row in file_rows]

        await temp_index.add_documents(file_batch)
        file_total += len(file_rows)

    # 4. Atomic swap
    task = await client.swap_indexes([
        (settings.meilisearch_index_name, temp_index_name)
    ])
    await client.wait_for_task(task.task_uid)

    # 5. Delete old index (now named temp)
    await client.delete_index_if_exists(temp_index_name)

    # 6. Refresh global reference
    global _meili_index
    _meili_index = await client.get_index(settings.meilisearch_index_name)

    logger.info("Full reindex completed: %d documents, %d files", total, file_total)
    return {"status": "reindex_completed", "document_count": total, "file_count": file_total}

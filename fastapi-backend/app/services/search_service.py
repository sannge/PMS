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

import gc
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

logger = logging.getLogger(__name__)

# Control character pattern
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Content size limit for indexing (~50K words)
MAX_CONTENT_LENGTH = 300_000

# RBAC scope cache TTL
SCOPE_CACHE_TTL = 30  # seconds

# Snippet extraction settings
SNIPPET_CONTEXT_CHARS = 60   # chars of context on each side of a match
MAX_OCCURRENCES_PER_DOC = 5  # cap occurrences per document to avoid huge lists

# Index settings (configure BEFORE adding documents)
MEILISEARCH_INDEX_SETTINGS = {
    "searchableAttributes": [
        "title",           # Highest priority -- title matches rank first
        "content_plain",   # Main body text
    ],
    "filterableAttributes": [
        "application_id",
        "project_id",
        "user_id",
        "folder_id",
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
        "content_plain",
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
    """Batch query: all applications where user is a member OR owner."""
    result = await db.execute(
        select(ApplicationMember.application_id)
        .where(ApplicationMember.user_id == user_id)
    )
    member_app_ids = set(result.scalars().all())

    result2 = await db.execute(
        select(Application.id)
        .where(Application.owner_id == user_id)
    )
    owner_app_ids = set(result2.scalars().all())

    return list(member_app_ids | owner_app_ids)


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
        await redis_service.set(cache_key, json.dumps(filter_expr), ttl=SCOPE_CACHE_TTL)
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
        "content_plain": (doc.content_plain or "")[:MAX_CONTENT_LENGTH],
        "application_id": str(application_id) if application_id else None,
        "project_id": str(doc.project_id) if doc.project_id else None,
        "user_id": str(doc.user_id) if doc.user_id else None,
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "created_by": str(doc.created_by) if doc.created_by else None,
        "updated_at": int(doc.updated_at.replace(tzinfo=timezone.utc).timestamp()),
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
    try:
        index = get_meili_index()
        await index.update_documents([data])
    except Exception as exc:
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


# ---- Search ----


def _extract_snippet(text: str, start: int, length: int) -> str:
    """Extract a snippet around a match position and wrap the match in <mark>.

    Returns an HTML string with the matched portion inside <mark> tags
    and surrounding context trimmed to word boundaries.
    """
    ctx = SNIPPET_CONTEXT_CHARS
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


def _expand_hits(hits: list[dict]) -> list[dict]:
    """Expand search hits so each content match becomes a separate entry.

    Each hit from Meilisearch may have multiple match positions in
    content_plain.  This function creates one entry per occurrence,
    each with its own ``snippet`` field containing a short context
    window around the matched text.

    Title-only matches (no content matches) produce a single entry
    with an empty snippet.  The full ``content_plain`` is stripped
    from every returned entry to keep the payload small.
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
        base["_formatted"] = {"title": formatted.get("title", hit.get("title", ""))}

        # Collect actual matched text from title positions too
        title_positions = (hit.get("_matchesPosition") or {}).get("title", [])
        title_text = hit.get("title") or ""
        title_matched = {
            title_text[p.get("start", 0):p.get("start", 0) + p.get("length", 0)].lower()
            for p in title_positions
            if p.get("length", 0) > 0
        }

        if not positions:
            # Title-only match -- single entry with the formatted content snippet
            base["snippet"] = formatted.get("content_plain", "")
            base["occurrenceIndex"] = 0
            base["matchedTerms"] = list(title_matched) if title_matched else []
            expanded.append(base)
            continue

        # Track where this document's entries start in the expanded list
        doc_start_idx = len(expanded)

        # Deduplicate overlapping positions and cap at MAX_OCCURRENCES_PER_DOC
        seen_starts: set[int] = set()
        matched_terms_set: set[str] = set(title_matched)
        occ_idx = 0
        for pos in positions:
            if occ_idx >= MAX_OCCURRENCES_PER_DOC:
                break
            start = pos.get("start", 0)
            length = pos.get("length", 0)
            if start in seen_starts or length == 0 or start >= len(content):
                continue
            seen_starts.add(start)

            matched_terms_set.add(content[start:start + length].lower())
            entry = {**base}
            entry["snippet"] = _extract_snippet(content, start, length)
            entry["occurrenceIndex"] = occ_idx
            expanded.append(entry)
            occ_idx += 1

        # Attach matched terms only to entries from this document
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
    """
    index = get_meili_index()
    results = await index.search(
        query,
        filter=filter_expr,
        limit=limit,
        offset=offset,
        attributes_to_highlight=["title"],
        highlight_pre_tag="<mark>",
        highlight_post_tag="</mark>",
        show_ranking_score=False,
        show_matches_position=True,
    )
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

    sql = text(f"""
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

    result = await db.execute(sql, {
        "query": query,
        "app_ids": all_scope_ids,
        "project_ids": all_project_ids,
        "user_id": str(user_id),
        "limit": limit,
        "offset": offset,
        **scope_params,
    })

    rows = result.fetchall()
    hits = []
    total_count = 0
    for row in rows:
        total_count = row.total_count  # Same for all rows (window function)
        hits.append({
            "id": str(row.id),
            "title": row.title,
            "application_id": str(row.application_id) if row.application_id else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "folder_id": str(row.folder_id) if row.folder_id else None,
            "updated_at": int(row.updated_at.replace(tzinfo=timezone.utc).timestamp()) if row.updated_at else None,
            "created_by": str(row.created_by) if row.created_by else None,
            "_formatted": {
                "title": row.title_highlighted,
                "content_plain": row.snippet,
            },
            "snippet": row.snippet,
            "occurrenceIndex": 0,
            "matchedTerms": [t for t in query.lower().split() if len(t) >= 2],
        })

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

        # Count active documents in PostgreSQL using func.count() (not loading all IDs)
        result = await db.execute(
            select(sa_func.count(Document.id)).where(Document.deleted_at.is_(None))
        )
        pg_active_count = result.scalar() or 0

        # Meilisearch count includes soft-deleted docs (deleted_at != NULL),
        # so compare against total PG docs (active + soft-deleted) for drift detection
        result = await db.execute(select(sa_func.count(Document.id)))
        pg_total_count = result.scalar() or 0

        if pg_total_count != meili_count:
            logger.warning(
                "Search index drift: PostgreSQL(total)=%d, Meilisearch=%d (active PG=%d)",
                pg_total_count, meili_count, pg_active_count,
            )

        # Find documents updated since last check
        last_check_key = "search:last_consistency_check"
        since_raw = await redis.get(last_check_key)
        since = float(since_raw) if since_raw else 0

        since_dt = datetime.fromtimestamp(since, tz=timezone.utc)

        # Only select needed columns, limit to 1000 per run to bound memory.
        # Outerjoin Project to resolve application_id for project-scoped docs.
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
            .where(Document.updated_at > since_dt)
            .limit(1000)
        )
        stale_rows = result.all()

        if stale_rows:
            logger.info("Re-indexing %d stale documents", len(stale_rows))
            for row in stale_rows:
                if row.deleted_at:
                    await index_document_soft_delete(row.id)
                else:
                    # Resolve application_id: use direct or fall back to project's app
                    app_id = row.application_id or row.project_app_id
                    try:
                        idx = get_meili_index()
                        await idx.update_documents([{
                            "id": str(row.id),
                            "title": row.title,
                            "content_plain": (row.content_plain or "")[:MAX_CONTENT_LENGTH],
                            "application_id": str(app_id) if app_id else None,
                            "project_id": str(row.project_id) if row.project_id else None,
                            "user_id": str(row.user_id) if row.user_id else None,
                            "folder_id": str(row.folder_id) if row.folder_id else None,
                            "created_by": str(row.created_by) if row.created_by else None,
                            "updated_at": int(row.updated_at.replace(tzinfo=timezone.utc).timestamp()),
                            "deleted_at": None,
                        }])
                    except Exception as exc:
                        logger.error("Failed to re-index document %s: %s", row.id, exc)

        await redis.set(last_check_key, str(time.time()))

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
    # Outerjoin Project to resolve application_id for project-scoped docs.
    batch_size = 1000
    offset_val = 0
    total = 0

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
                Project.application_id.label("project_app_id"),
            )
            .outerjoin(Project, Document.project_id == Project.id)
            .where(Document.deleted_at.is_(None))
            .offset(offset_val)
            .limit(batch_size)
        )
        rows = result.all()
        if not rows:
            break

        batch = [{
            "id": str(row.id),
            "title": row.title,
            "content_plain": (row.content_plain or "")[:MAX_CONTENT_LENGTH],
            "application_id": str(row.application_id or row.project_app_id) if (row.application_id or row.project_app_id) else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "folder_id": str(row.folder_id) if row.folder_id else None,
            "created_by": str(row.created_by) if row.created_by else None,
            "updated_at": int(row.updated_at.replace(tzinfo=timezone.utc).timestamp()),
            "deleted_at": None,
        } for row in rows]

        await temp_index.add_documents(batch)
        total += len(rows)
        offset_val += batch_size
        gc.collect()  # Free memory between batches

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

    logger.info("Full reindex completed: %d documents", total)
    return {"status": "reindex_completed", "document_count": total}

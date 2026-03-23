"""Hybrid retrieval service with Reciprocal Rank Fusion.

Multi-source retrieval combining:
1. pgvector cosine similarity (semantic search)
2. Meilisearch keyword search (existing infrastructure)
3. pg_trgm fuzzy title matching

All sources filtered by user's RBAC scope. Results merged and deduplicated
using Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.search_service import (
    _get_projects_in_applications,
    _get_user_application_ids,
    get_meili_index,
    sanitize_search_query,
)
from .embedding_normalizer import EmbeddingNormalizer
from .provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result with source attribution."""

    document_id: UUID
    document_title: str
    chunk_text: str
    heading_context: str | None
    score: float
    source: str  # "semantic", "keyword", "fuzzy", "semantic+keyword", etc.
    application_id: UUID | None
    project_id: UUID | None
    snippet: str
    chunk_type: str = "text"  # "text" or "image"
    chunk_index: int | None = None
    source_type: str = "document"  # "document" or "file"
    file_id: UUID | None = None


@dataclass
class _RankedResult:
    """Internal per-source result with rank position."""

    document_id: UUID
    document_title: str
    chunk_text: str
    heading_context: str | None
    chunk_index: int | None
    rank: int  # 1-based rank within source
    raw_score: float
    source: str
    application_id: UUID | None = None
    project_id: UUID | None = None
    chunk_type: str = "text"
    source_type: str = "document"  # "document" or "file"
    file_id: UUID | None = None


class HybridRetrievalService:
    """Multi-source retrieval with Reciprocal Rank Fusion.

    Combines semantic (pgvector), keyword (Meilisearch), and fuzzy (pg_trgm)
    search results. Respects RBAC boundaries — users only see documents
    from their accessible applications.

    Args:
        provider_registry: For generating query embeddings.
        normalizer: For normalizing query embeddings.
        db: Async database session.
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        normalizer: EmbeddingNormalizer,
        db: AsyncSession,
    ) -> None:
        self.provider_registry = provider_registry
        self.normalizer = normalizer
        self.db = db

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        limit: int = 10,
        application_id: UUID | None = None,
        project_id: UUID | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievalResult]:
        """Main retrieval method combining all search sources.

        1. Resolve user's accessible scope (RBAC)
        2. Run searches in parallel (semantic, keyword, fuzzy)
        3. Merge with Reciprocal Rank Fusion
        4. Deduplicate and sort
        5. Return top results with snippets

        Args:
            query: Search query string.
            user_id: UUID of the searching user (for RBAC).
            limit: Maximum results to return (default 10).
            application_id: Optional scope filter to specific application.
            project_id: Optional scope filter to specific project.

        Returns:
            List of RetrievalResult sorted by RRF score descending.
        """
        if not query or not query.strip():
            return []

        query = sanitize_search_query(query)
        if not query:
            return []

        # Step 1: Resolve user's RBAC scope (M8: cached in Redis for 30s)
        # Don't early-return on empty app_ids — user may have personal-scope docs
        app_ids: list[UUID] = []
        project_ids: list[UUID] = []
        _rbac_cached = False
        _rbac_rs = None
        _cache_key = f"rbac_scope:{user_id}"
        import json as _json

        try:
            from ..services.redis_service import redis_service as _rbac_rs

            if _rbac_rs.is_connected:
                _raw = await _rbac_rs.get(_cache_key)
                if _raw:
                    _cached = _json.loads(_raw)
                    app_ids = [UUID(a) for a in _cached.get("app_ids", [])]
                    project_ids = [UUID(p) for p in _cached.get("project_ids", [])]
                    _rbac_cached = True
        except Exception:
            pass

        if not _rbac_cached:
            app_ids = await _get_user_application_ids(self.db, user_id)
            project_ids = await _get_projects_in_applications(self.db, app_ids) if app_ids else []
            try:
                if _rbac_rs is not None and _rbac_rs.is_connected:
                    await _rbac_rs.set(
                        _cache_key,
                        _json.dumps(
                            {
                                "app_ids": [str(a) for a in app_ids],
                                "project_ids": [str(p) for p in project_ids],
                            }
                        ),
                        ttl=30,
                    )
            except Exception:
                pass

        # Apply optional scope narrowing
        if application_id is not None:
            if application_id not in app_ids:
                return []  # User doesn't have access to this application
            app_ids = [application_id]
            # Re-resolve projects for narrowed app
            project_ids = await _get_projects_in_applications(self.db, app_ids)

        if project_id is not None:
            if project_id not in project_ids:
                return []  # User doesn't have access to this project
            project_ids = [project_id]

        scope_ids = {
            "app_ids": app_ids,
            "project_ids": project_ids,
            "user_id": user_id,
        }

        # Step 2: Run searches — semantic and fuzzy share the DB session so
        # they must run sequentially; keyword search uses Meilisearch (HTTP)
        # and can run in parallel with the DB searches.
        keyword_task = asyncio.ensure_future(self._keyword_search(query, scope_ids, limit=20))

        # Run DB-backed searches sequentially to avoid concurrent access
        # on the same AsyncSession (not safe with asyncpg).
        try:
            semantic_results: list | Exception = await self._semantic_search(
                query,
                scope_ids,
                limit=20,
                query_embedding=query_embedding,
            )
        except Exception as exc:
            semantic_results = exc

        try:
            fuzzy_results: list | Exception = await self._fuzzy_title_search(query, scope_ids, limit=10)
        except Exception as exc:
            fuzzy_results = exc

        # Await the Meilisearch keyword search
        try:
            keyword_results: list | Exception = await keyword_task
        except Exception as exc:
            keyword_results = exc

        # Handle exceptions gracefully — don't fail if one source is unavailable
        ranked_lists: list[list[_RankedResult]] = []

        if isinstance(semantic_results, list):
            ranked_lists.append(semantic_results)
        else:
            logger.warning("Semantic search failed: %s", type(semantic_results).__name__)

        if isinstance(keyword_results, list):
            ranked_lists.append(keyword_results)
        else:
            logger.warning("Keyword search failed: %s", type(keyword_results).__name__)

        if isinstance(fuzzy_results, list):
            ranked_lists.append(fuzzy_results)
        else:
            logger.warning("Fuzzy search failed: %s", type(fuzzy_results).__name__)

        if not ranked_lists:
            return []

        # Step 3: RRF merge
        merged = self._reciprocal_rank_fusion(*ranked_lists, k=60)

        # Step 4: Sort and limit
        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:limit]

    async def _semantic_search(
        self,
        query: str,
        scope_ids: dict,
        limit: int = 20,
        query_embedding: list[float] | None = None,
    ) -> list[_RankedResult]:
        """pgvector cosine similarity search.

        Embeds the query string, then searches DocumentChunks using
        pgvector's <=> operator for cosine distance.

        Args:
            query: Search query text.
            scope_ids: Dict with app_ids, project_ids, user_id.
            limit: Maximum results.
            query_embedding: Pre-computed embedding to skip generation.

        Returns:
            List of _RankedResult with source="semantic".
        """
        if query_embedding is not None:
            # Use pre-computed embedding (from cache)
            pass
        else:
            try:
                provider, model_id = await self.provider_registry.get_embedding_provider(self.db)
                raw_embedding = await provider.generate_embedding(query, model_id)
                query_embedding = self.normalizer.normalize(raw_embedding)
            except Exception as e:
                logger.warning("Semantic search embedding failed: %s", type(e).__name__)
                return []

        app_ids = scope_ids["app_ids"]
        project_ids = scope_ids.get("project_ids", [])
        user_id = scope_ids["user_id"]

        # Build scope filter SQL
        # Format embedding as pgvector-compatible string (no spaces after commas)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        scope_conditions: list[str] = []
        params: dict = {"query_embedding": embedding_str, "limit": limit}

        if app_ids:
            scope_conditions.append("dc.application_id = ANY(:app_ids)")
            params["app_ids"] = [str(aid) for aid in app_ids]

        if project_ids:
            scope_conditions.append("dc.project_id = ANY(:project_ids)")
            params["project_ids"] = [str(pid) for pid in project_ids]

        # Personal-scope: only match docs where application_id AND project_id
        # are NULL (truly personal docs), not all docs created by this user.
        scope_conditions.append("dc.application_id IS NULL AND dc.project_id IS NULL AND dc.user_id = :user_id")
        params["user_id"] = str(user_id)

        scope_filter = " OR ".join(f"({c})" for c in scope_conditions)

        # SET LOCAL scopes ef_search to this transaction only, improving recall
        # at a modest latency cost. Must be a separate execute() call because
        # asyncpg does not support multi-statement prepared statements.
        await self.db.execute(text("SET LOCAL hnsw.ef_search = 100"))

        # Columns in the WHERE clause are safe against SQL injection because
        # they are built from hardcoded strings above, not user input.
        # The scope_filter uses parameterized :app_ids, :project_ids, :user_id.
        # LEFT JOIN both Documents and FolderFiles to support both source types.
        sql = text(f"""
            SELECT
                dc.document_id,
                dc.file_id,
                dc.source_type,
                dc.chunk_text,
                dc.heading_context,
                dc.chunk_index,
                dc.chunk_type,
                dc.application_id,
                dc.project_id,
                COALESCE(d.title, ff.display_name) AS document_title,
                1 - (dc.embedding <=> CAST(:query_embedding AS vector)) AS similarity
            FROM "DocumentChunks" dc
            LEFT JOIN "Documents" d ON d.id = dc.document_id
            LEFT JOIN "FolderFiles" ff ON ff.id = dc.file_id
            WHERE (
                (dc.document_id IS NOT NULL AND d.deleted_at IS NULL)
                OR (dc.file_id IS NOT NULL AND ff.deleted_at IS NULL)
              )
              AND ({scope_filter})
            ORDER BY dc.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        ranked: list[_RankedResult] = []
        for rank_pos, row in enumerate(rows, 1):
            # Determine the effective ID for dedup
            effective_id = row.document_id or row.file_id
            ranked.append(
                _RankedResult(
                    document_id=effective_id,
                    document_title=row.document_title or "",
                    chunk_text=row.chunk_text or "",
                    heading_context=row.heading_context,
                    chunk_index=row.chunk_index,
                    rank=rank_pos,
                    raw_score=float(row.similarity),
                    source="semantic",
                    application_id=row.application_id,
                    project_id=row.project_id,
                    chunk_type=row.chunk_type or "text",
                    source_type=row.source_type or "document",
                    file_id=row.file_id,
                )
            )

        return ranked

    async def _keyword_search(
        self,
        query: str,
        scope_ids: dict,
        limit: int = 20,
    ) -> list[_RankedResult]:
        """Meilisearch keyword search.

        Reuses existing Meilisearch infrastructure from search_service.py.

        Args:
            query: Search query text.
            scope_ids: Dict with app_ids, project_ids, user_id.
            limit: Maximum results.

        Returns:
            List of _RankedResult with source="keyword".
        """
        try:
            index = get_meili_index()
        except RuntimeError:
            logger.warning("Meilisearch not initialized, skipping keyword search")
            return []

        # Build scope filter matching search_service.py pattern
        app_ids = scope_ids["app_ids"]
        project_ids = scope_ids.get("project_ids", [])
        user_id = scope_ids["user_id"]

        scope_filters: list[str] = []
        if app_ids:
            app_id_list = ", ".join(f"'{UUID(str(aid))}'" for aid in app_ids)
            scope_filters.append(f"application_id IN [{app_id_list}]")
        if project_ids:
            proj_id_list = ", ".join(f"'{UUID(str(pid))}'" for pid in project_ids)
            scope_filters.append(f"project_id IN [{proj_id_list}]")
        scope_filters.append(f"user_id = '{UUID(str(user_id))}'")

        filter_expr = [scope_filters, "deleted_at IS NULL"]

        try:
            results = await index.search(
                query,
                filter=filter_expr,
                limit=limit,
                show_matches_position=False,
            )
        except Exception as e:
            logger.warning("Meilisearch keyword search failed: %s", type(e).__name__)
            return []

        ranked: list[_RankedResult] = []
        for rank_pos, hit in enumerate(results.hits, 1):
            doc_id = hit.get("id", "")
            if not doc_id:
                continue

            # Handle file_ prefixed IDs from Meilisearch
            is_file = isinstance(doc_id, str) and doc_id.startswith("file_")
            if is_file:
                real_id = UUID(doc_id[5:])  # Strip "file_" prefix
                source_type = "file"
                file_id = real_id
            else:
                real_id = UUID(doc_id)
                source_type = "document"
                file_id = None

            ranked.append(
                _RankedResult(
                    document_id=real_id,
                    document_title=hit.get("title", ""),
                    chunk_text=hit.get("content_plain", "")[:500],
                    heading_context=None,
                    chunk_index=None,
                    rank=rank_pos,
                    raw_score=1.0 / rank_pos,  # Approximate relevance from rank
                    source="keyword",
                    application_id=UUID(hit["application_id"]) if hit.get("application_id") else None,
                    project_id=UUID(hit["project_id"]) if hit.get("project_id") else None,
                    source_type=source_type,
                    file_id=file_id,
                )
            )

        return ranked

    async def _fuzzy_title_search(
        self,
        query: str,
        scope_ids: dict,
        threshold: float = 0.3,
        limit: int = 10,
    ) -> list[_RankedResult]:
        """pg_trgm fuzzy title matching.

        Uses PostgreSQL's similarity() function with the GIN trigram index
        for fuzzy title matching. Searches both Documents and FolderFiles
        (HIGH-14) via UNION ALL.

        Args:
            query: Search query text.
            scope_ids: Dict with app_ids, project_ids, user_id.
            threshold: Minimum similarity score (default 0.3).
            limit: Maximum results.

        Returns:
            List of _RankedResult with source="fuzzy".
        """
        # Skip very short queries that produce noisy trigram matches
        if len(query.strip()) < 3:
            return []

        app_ids = scope_ids["app_ids"]
        project_ids = scope_ids.get("project_ids", [])
        user_id = scope_ids["user_id"]

        # Build scope conditions for Documents
        doc_scope_conditions: list[str] = []
        params: dict = {
            "query": query,
            "threshold": threshold,
            "limit": limit,
        }

        if app_ids:
            doc_scope_conditions.append("d.application_id = ANY(:app_ids)")
            params["app_ids"] = [str(aid) for aid in app_ids]

        if project_ids:
            doc_scope_conditions.append("d.project_id = ANY(:project_ids)")
            params["project_ids"] = [str(pid) for pid in project_ids]

        # Personal-scope: only match docs with no app/project assignment
        doc_scope_conditions.append("d.application_id IS NULL AND d.project_id IS NULL AND d.user_id = :user_id")
        params["user_id"] = str(user_id)

        doc_scope_filter = " OR ".join(f"({c})" for c in doc_scope_conditions)

        # Build scope conditions for FolderFiles (HIGH-14)
        file_scope_conditions: list[str] = []
        if app_ids:
            file_scope_conditions.append("ff.application_id = ANY(:app_ids)")
        if project_ids:
            file_scope_conditions.append("ff.project_id = ANY(:project_ids)")
        file_scope_conditions.append("ff.application_id IS NULL AND ff.project_id IS NULL AND ff.user_id = :user_id")
        file_scope_filter = " OR ".join(f"({c})" for c in file_scope_conditions)

        # HIGH-14: UNION ALL Documents + FolderFiles for fuzzy search
        sql = text(f"""
            SELECT id, title, application_id, project_id, content_plain, sim,
                   source_type, file_id
            FROM (
                SELECT
                    d.id,
                    d.title,
                    d.application_id,
                    d.project_id,
                    COALESCE(d.content_plain, '') AS content_plain,
                    similarity(d.title, :query) AS sim,
                    'document' AS source_type,
                    CAST(NULL AS uuid) AS file_id
                FROM "Documents" d
                WHERE similarity(d.title, :query) > :threshold
                  AND d.deleted_at IS NULL
                  AND ({doc_scope_filter})

                UNION ALL

                SELECT
                    ff.id,
                    ff.display_name AS title,
                    ff.application_id,
                    ff.project_id,
                    COALESCE(ff.content_plain, '') AS content_plain,
                    similarity(ff.display_name, :query) AS sim,
                    'file' AS source_type,
                    ff.id AS file_id
                FROM "FolderFiles" ff
                WHERE similarity(ff.display_name, :query) > :threshold
                  AND ff.deleted_at IS NULL
                  AND ({file_scope_filter})
            ) combined
            ORDER BY sim DESC
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        ranked: list[_RankedResult] = []
        for rank_pos, row in enumerate(rows, 1):
            ranked.append(
                _RankedResult(
                    document_id=row.id,
                    document_title=row.title or "",
                    chunk_text=row.content_plain[:500] if row.content_plain else "",
                    heading_context=None,
                    chunk_index=None,
                    rank=rank_pos,
                    raw_score=float(row.sim),
                    source="fuzzy",
                    application_id=row.application_id,
                    project_id=row.project_id,
                    source_type=row.source_type or "document",
                    file_id=row.file_id,
                )
            )

        return ranked

    def _reciprocal_rank_fusion(
        self,
        *ranked_lists: list[_RankedResult],
        k: int = 60,
    ) -> list[RetrievalResult]:
        """Merge multiple ranked lists using Reciprocal Rank Fusion.

        RRF score: rrf_score(d) = sum over lists: 1 / (k + rank(d))

        Deduplicates by (source_type, document_id, chunk_index) so that
        multiple chunks from the same document survive.  Cross-source hits
        (semantic chunk vs keyword hit) for the *same* chunk still merge.
        A per-document cap of 3 chunks (by RRF score) prevents any single
        document from dominating the result set.

        Args:
            ranked_lists: Variable number of ranked result lists.
            k: RRF parameter (default 60, from original RRF paper).

        Returns:
            Merged and deduplicated list of RetrievalResult.
        """
        # Key: (source_type, document_id, chunk_index) — preserves multiple
        # chunks from the same document while merging cross-source hits for
        # the *same* chunk.  A per-document cap of 3 (applied after scoring)
        # prevents any single document from dominating the result set.
        _MAX_CHUNKS_PER_DOC = 3
        merged: dict[tuple[str, UUID, int | None], dict] = {}

        for ranked_list in ranked_lists:
            for result in ranked_list:
                key = (result.source_type, result.document_id, result.chunk_index)

                if key not in merged:
                    merged[key] = {
                        "document_id": result.document_id,
                        "document_title": result.document_title,
                        "chunk_text": result.chunk_text,
                        "heading_context": result.heading_context,
                        "chunk_type": result.chunk_type,
                        "chunk_index": result.chunk_index,
                        "best_rank": result.rank,
                        "rrf_score": 0.0,
                        "sources": set(),
                        "application_id": result.application_id,
                        "project_id": result.project_id,
                        "source_type": result.source_type,
                        "file_id": result.file_id,
                    }

                merged[key]["rrf_score"] += 1.0 / (k + result.rank)
                merged[key]["sources"].add(result.source)

                # Keep chunk text from the highest-ranked entry (most relevant)
                if result.rank < merged[key]["best_rank"]:
                    merged[key]["chunk_text"] = result.chunk_text
                    merged[key]["heading_context"] = result.heading_context
                    merged[key]["chunk_type"] = result.chunk_type
                    merged[key]["chunk_index"] = result.chunk_index
                    merged[key]["best_rank"] = result.rank

        # Per-document cap: keep only the top _MAX_CHUNKS_PER_DOC chunks
        # per (source_type, document_id) by RRF score.
        from collections import defaultdict

        _doc_counts: dict[tuple[str, UUID], int] = defaultdict(int)
        _sorted_entries = sorted(merged.values(), key=lambda e: e["rrf_score"], reverse=True)
        _capped_entries: list[dict] = []
        for entry in _sorted_entries:
            doc_key = (entry["source_type"], entry["document_id"])
            if _doc_counts[doc_key] < _MAX_CHUNKS_PER_DOC:
                _doc_counts[doc_key] += 1
                _capped_entries.append(entry)

        # Convert to RetrievalResult
        results: list[RetrievalResult] = []
        for entry in _capped_entries:
            source_str = "+".join(sorted(entry["sources"]))
            snippet = self._generate_snippet(entry["heading_context"], entry["chunk_text"])
            results.append(
                RetrievalResult(
                    document_id=entry["document_id"],
                    document_title=entry["document_title"],
                    chunk_text=entry["chunk_text"],
                    heading_context=entry["heading_context"],
                    score=entry["rrf_score"],
                    source=source_str,
                    application_id=entry["application_id"],
                    project_id=entry["project_id"],
                    snippet=snippet,
                    chunk_type=entry.get("chunk_type", "text"),
                    chunk_index=entry.get("chunk_index"),
                    source_type=entry.get("source_type", "document"),
                    file_id=entry.get("file_id"),
                )
            )

        return results

    def _generate_snippet(
        self,
        heading_context: str | None,
        chunk_text: str,
        max_length: int = 200,
    ) -> str:
        """Generate a readable text excerpt for display.

        Combines heading context with truncated chunk text.

        Args:
            heading_context: Optional heading context string.
            chunk_text: Full chunk text.
            max_length: Maximum snippet length.

        Returns:
            Readable snippet string.
        """
        parts: list[str] = []
        if heading_context:
            parts.append(f"[{heading_context}]")

        text = chunk_text.strip()
        if len(text) > max_length:
            text = text[:max_length].rsplit(" ", 1)[0] + "..."

        if text:
            parts.append(text)
        return " ".join(parts)

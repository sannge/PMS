"""Hybrid retrieval service with Reciprocal Rank Fusion.

Multi-source retrieval combining:
1. pgvector cosine similarity (semantic search)
2. Meilisearch keyword search (existing infrastructure)
3. pg_trgm fuzzy title matching
4. (Phase 3 will add PostgreSQL knowledge graph entity search)

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

        # Step 1: Resolve user's RBAC scope
        # Don't early-return on empty app_ids — user may have personal-scope docs
        app_ids = await _get_user_application_ids(self.db, user_id)
        project_ids = await _get_projects_in_applications(self.db, app_ids) if app_ids else []

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

        # Step 2: Run searches in parallel
        semantic_task = self._semantic_search(query, scope_ids, limit=20)
        keyword_task = self._keyword_search(query, scope_ids, limit=20)
        fuzzy_task = self._fuzzy_title_search(query, scope_ids, limit=10)

        semantic_results, keyword_results, fuzzy_results = await asyncio.gather(
            semantic_task, keyword_task, fuzzy_task,
            return_exceptions=True,
        )

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
    ) -> list[_RankedResult]:
        """pgvector cosine similarity search.

        Embeds the query string, then searches DocumentChunks using
        pgvector's <=> operator for cosine distance.

        Args:
            query: Search query text.
            scope_ids: Dict with app_ids, project_ids, user_id.
            limit: Maximum results.

        Returns:
            List of _RankedResult with source="semantic".
        """
        try:
            provider, model_id = await self.provider_registry.get_embedding_provider(
                self.db
            )
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
            scope_conditions.append('dc.application_id = ANY(:app_ids)')
            params["app_ids"] = [str(aid) for aid in app_ids]

        if project_ids:
            scope_conditions.append('dc.project_id = ANY(:project_ids)')
            params["project_ids"] = [str(pid) for pid in project_ids]

        # Personal-scope: only match docs where application_id AND project_id
        # are NULL (truly personal docs), not all docs created by this user.
        scope_conditions.append(
            'dc.application_id IS NULL AND dc.project_id IS NULL AND dc.user_id = :user_id'
        )
        params["user_id"] = str(user_id)

        scope_filter = " OR ".join(f"({c})" for c in scope_conditions)

        # SET LOCAL scopes ef_search to this transaction only, improving recall
        # at a modest latency cost. Must be a separate execute() call because
        # asyncpg does not support multi-statement prepared statements.
        await self.db.execute(text("SET LOCAL hnsw.ef_search = 100"))

        # Columns in the WHERE clause are safe against SQL injection because
        # they are built from hardcoded strings above, not user input.
        # The scope_filter uses parameterized :app_ids, :project_ids, :user_id.
        sql = text(f"""
            SELECT
                dc.document_id,
                dc.chunk_text,
                dc.heading_context,
                dc.chunk_index,
                dc.application_id,
                dc.project_id,
                d.title AS document_title,
                1 - (dc.embedding <=> :query_embedding::vector) AS similarity
            FROM "DocumentChunks" dc
            JOIN "Documents" d ON d.id = dc.document_id
            WHERE d.deleted_at IS NULL
              AND ({scope_filter})
            ORDER BY dc.embedding <=> :query_embedding::vector
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        ranked: list[_RankedResult] = []
        for rank_pos, row in enumerate(rows, 1):
            ranked.append(_RankedResult(
                document_id=row.document_id,
                document_title=row.document_title or "",
                chunk_text=row.chunk_text or "",
                heading_context=row.heading_context,
                chunk_index=row.chunk_index,
                rank=rank_pos,
                raw_score=float(row.similarity),
                source="semantic",
                application_id=row.application_id,
                project_id=row.project_id,
            ))

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
            ranked.append(_RankedResult(
                document_id=UUID(doc_id),
                document_title=hit.get("title", ""),
                chunk_text=hit.get("content_plain", "")[:500],
                heading_context=None,
                chunk_index=None,
                rank=rank_pos,
                raw_score=1.0 / rank_pos,  # Approximate relevance from rank
                source="keyword",
                application_id=UUID(hit["application_id"]) if hit.get("application_id") else None,
                project_id=UUID(hit["project_id"]) if hit.get("project_id") else None,
            ))

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
        for fuzzy title matching.

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

        scope_conditions: list[str] = []
        params: dict = {
            "query": query,
            "threshold": threshold,
            "limit": limit,
        }

        if app_ids:
            scope_conditions.append('d.application_id = ANY(:app_ids)')
            params["app_ids"] = [str(aid) for aid in app_ids]

        if project_ids:
            scope_conditions.append('d.project_id = ANY(:project_ids)')
            params["project_ids"] = [str(pid) for pid in project_ids]

        # Personal-scope: only match docs with no app/project assignment
        scope_conditions.append(
            'd.application_id IS NULL AND d.project_id IS NULL AND d.user_id = :user_id'
        )
        params["user_id"] = str(user_id)

        scope_filter = " OR ".join(f"({c})" for c in scope_conditions)

        sql = text(f"""
            SELECT
                d.id,
                d.title,
                d.application_id,
                d.project_id,
                COALESCE(d.content_plain, '') AS content_plain,
                similarity(d.title, :query) AS sim
            FROM "Documents" d
            WHERE similarity(d.title, :query) > :threshold
              AND d.deleted_at IS NULL
              AND ({scope_filter})
            ORDER BY sim DESC
            LIMIT :limit
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        ranked: list[_RankedResult] = []
        for rank_pos, row in enumerate(rows, 1):
            ranked.append(_RankedResult(
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
            ))

        return ranked

    def _reciprocal_rank_fusion(
        self,
        *ranked_lists: list[_RankedResult],
        k: int = 60,
    ) -> list[RetrievalResult]:
        """Merge multiple ranked lists using Reciprocal Rank Fusion.

        RRF score: rrf_score(d) = sum over lists: 1 / (k + rank(d))

        Deduplicates by document_id so that the same document from
        different sources (semantic chunk vs keyword hit) merges correctly.
        When multiple chunks from the same document appear, the chunk from
        the highest-ranked entry (lowest rank number) is preserved.

        Args:
            ranked_lists: Variable number of ranked result lists.
            k: RRF parameter (default 60, from original RRF paper).

        Returns:
            Merged and deduplicated list of RetrievalResult.
        """
        # Key: document_id — ensures cross-source dedup (semantic chunk_index=0
        # vs keyword chunk_index=None merge for the same document). Within a
        # single source, duplicate chunks from the same doc accumulate RRF score
        # but the highest-ranked chunk's text is preserved.
        merged: dict[UUID, dict] = {}

        for ranked_list in ranked_lists:
            for result in ranked_list:
                key = result.document_id

                if key not in merged:
                    merged[key] = {
                        "document_id": result.document_id,
                        "document_title": result.document_title,
                        "chunk_text": result.chunk_text,
                        "heading_context": result.heading_context,
                        "best_rank": result.rank,
                        "rrf_score": 0.0,
                        "sources": set(),
                        "application_id": result.application_id,
                        "project_id": result.project_id,
                    }

                merged[key]["rrf_score"] += 1.0 / (k + result.rank)
                merged[key]["sources"].add(result.source)

                # Keep chunk text from the highest-ranked entry (most relevant)
                if result.rank < merged[key]["best_rank"]:
                    merged[key]["chunk_text"] = result.chunk_text
                    merged[key]["heading_context"] = result.heading_context
                    merged[key]["best_rank"] = result.rank

        # Convert to RetrievalResult
        results: list[RetrievalResult] = []
        for entry in merged.values():
            source_str = "+".join(sorted(entry["sources"]))
            snippet = self._generate_snippet(
                entry["heading_context"], entry["chunk_text"]
            )
            results.append(RetrievalResult(
                document_id=entry["document_id"],
                document_title=entry["document_title"],
                chunk_text=entry["chunk_text"],
                heading_context=entry["heading_context"],
                score=entry["rrf_score"],
                source=source_str,
                application_id=entry["application_id"],
                project_id=entry["project_id"],
                snippet=snippet,
            ))

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

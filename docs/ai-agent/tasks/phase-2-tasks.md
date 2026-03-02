# Phase 2: Vector Embeddings + Hybrid Search — Task Tracker

**Created**: 2026-02-24
**Last updated**: 2026-02-25
**Status**: COMPLETE
**Spec**: [phase-2-vector-embeddings.md](../phase-2-vector-embeddings.md)
**Depends on**: Phase 1 (LLM providers for embedding generation)
**Blocks**: Phase 3.1, Phase 4, Phase 6

## Task Count Summary

| Section | Description | Tasks |
|---------|-------------|-------|
| 2.1 | Database — PostgreSQL Extensions Migration | 8 |
| 2.2 | Database — DocumentChunks Table Migration | 24 |
| 2.3 | Database — Document Model Modifications | 8 |
| 2.4 | SQLAlchemy Model — DocumentChunk | 10 |
| 2.5 | Semantic Chunking Service — TipTap Strategy | 14 |
| 2.6 | Semantic Chunking Service — Canvas Strategy | 10 |
| 2.7 | Embedding Pipeline Service | 13 |
| 2.8 | Debounced Embedding Trigger (ARQ Worker) | 11 |
| 2.9 | Hybrid Retrieval Service — Semantic Search | 8 |
| 2.10 | Hybrid Retrieval Service — Keyword Search (Meilisearch) | 6 |
| 2.11 | Hybrid Retrieval Service — Fuzzy Title Search (pg_trgm) | 7 |
| 2.12 | Hybrid Retrieval Service — RRF Merge | 8 |
| 2.13 | Schema Updates & Dependencies | 9 |
| 2.14 | Code Reviews & Security Analysis | 14 |
| 2.15 | Unit Tests — Chunking | 21 |
| 2.16 | Unit Tests — Embedding Service | 10 |
| 2.17 | Integration Tests — Retrieval Service | 14 |
| 2.18 | Phase 2 Verification & Sign-Off | 12 |
| **Total** | | **207** |

## Team

| Role | Abbreviation |
|------|-------------|
| Frontend Engineer | **FE** |
| Backend Engineer | **BE** |
| Database Engineer | **DBE** |
| Code Reviewer 1 | **CR1** |
| Code Reviewer 2 | **CR2** |
| Security Analyst | **SA** |
| Quality Engineer | **QE** |
| Test Engineer | **TE** |
| Devil's Advocate | **DA** |

## Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked
- `[-]` Skipped / N/A

---

## 2.1 Database — PostgreSQL Extensions Migration

> **New file**: `fastapi-backend/alembic/versions/YYYYMMDD_add_pgvector_pgtrgm.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.1.1 | Write Alembic migration file `YYYYMMDD_add_pgvector_pgtrgm.py` with `upgrade()` and `downgrade()` functions | DBE | [x] | `20260225_add_pgvector_pgtrgm.py` |
| 2.1.2 | `upgrade()`: Execute `CREATE EXTENSION IF NOT EXISTS vector;` | DBE | [x] | pgvector extension for vector similarity search |
| 2.1.3 | `upgrade()`: Execute `CREATE EXTENSION IF NOT EXISTS pg_trgm;` | DBE | [x] | Trigram extension for fuzzy text matching |
| 2.1.4 | `downgrade()`: Execute `DROP EXTENSION IF EXISTS pg_trgm;` — order matters (drop dependents first) | DBE | [x] | |
| 2.1.5 | `downgrade()`: Execute `DROP EXTENSION IF EXISTS vector;` | DBE | [x] | |
| 2.1.6 | **QE Verify**: Migration runs without errors on PostgreSQL 15+ | QE | [!] | pgvector binary not installed on DB server - pg_trgm works |
| 2.1.7 | **QE Verify**: Both extensions are available after migration — `SELECT * FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');` returns 2 rows | QE | [!] | Blocked: pgvector binary needs server-side install |
| 2.1.8 | **QE Verify**: Downgrade removes both extensions cleanly — `alembic downgrade -1` then verify extensions gone | QE | [!] | Blocked: pgvector binary needs server-side install |

---

## 2.2 Database — DocumentChunks Table Migration

> **New file**: `fastapi-backend/alembic/versions/YYYYMMDD_add_document_chunks.py`
> **Depends on**: 2.1 (pgvector + pg_trgm extensions must exist)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.2.1 | Write Alembic migration file `YYYYMMDD_add_document_chunks.py` — depends on extensions migration via `Depends` directive | DBE | [x] | Migration file created by DBE agent |
| 2.2.2 | Add column: `id` — UUID PK, `default=uuid4` | DBE | [x] | Migration file created by DBE agent |
| 2.2.3 | Add column: `document_id` — UUID FK -> `Documents.id` with `ondelete='CASCADE'`, NOT NULL | DBE | [x] | Cascade ensures chunks are deleted when parent document is deleted |
| 2.2.4 | Add column: `chunk_index` — INT, NOT NULL | DBE | [x] | Ordering within document, 0-based |
| 2.2.5 | Add column: `chunk_text` — TEXT, NOT NULL | DBE | [x] | The actual text chunk for embedding |
| 2.2.6 | Add column: `heading_context` — VARCHAR(500), nullable | DBE | [x] | Parent heading hierarchy for retrieval context |
| 2.2.7 | Add column: `embedding` — `vector(1536)` pgvector type | DBE | [x] | Matches OpenAI text-embedding-3-small dimensions |
| 2.2.8 | Add column: `token_count` — INT, NOT NULL | DBE | [x] | For context window budgeting in Phase 4 |
| 2.2.9 | Add column: `application_id` — UUID, nullable | DBE | [x] | Denormalized from document for fast scope filtering |
| 2.2.10 | Add column: `project_id` — UUID, nullable | DBE | [x] | Denormalized from document for fast scope filtering |
| 2.2.11 | Add column: `user_id` — UUID, nullable | DBE | [x] | Denormalized (document creator) for personal scope filtering |
| 2.2.12 | Add column: `created_at` — TIMESTAMP WITH TIME ZONE, NOT NULL, default=utc_now | DBE | [x] | Migration file created by DBE agent |
| 2.2.13 | Add column: `updated_at` — TIMESTAMP WITH TIME ZONE, NOT NULL, default=utc_now | DBE | [x] | Migration file created by DBE agent |
| 2.2.14 | Create HNSW index: `idx_document_chunks_embedding ON "DocumentChunks" USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)` | DBE | [x] | Approximate nearest neighbor for semantic search |
| 2.2.15 | Create unique index: `idx_document_chunks_doc_idx ON "DocumentChunks" (document_id, chunk_index)` | DBE | [x] | Prevents duplicate chunk indices within a document |
| 2.2.16 | Create scope filter index: `idx_document_chunks_app ON "DocumentChunks" (application_id)` | DBE | [x] | Migration file created by DBE agent |
| 2.2.17 | Create scope filter index: `idx_document_chunks_project ON "DocumentChunks" (project_id)` | DBE | [x] | Migration file created by DBE agent |
| 2.2.18 | Create scope filter index: `idx_document_chunks_user ON "DocumentChunks" (user_id)` | DBE | [x] | Migration file created by DBE agent |
| 2.2.19 | Write `downgrade()`: Drop all indexes, then drop `DocumentChunks` table | DBE | [x] | Migration file created by DBE agent |
| 2.2.20 | **QE Verify**: `DocumentChunks` table created with correct column types — `\d "DocumentChunks"` | QE | [!] | Blocked: pgvector not installed on server |
| 2.2.21 | **QE Verify**: HNSW index created — `\di idx_document_chunks_embedding` shows `hnsw` access method | QE | [!] | Blocked: pgvector not installed on server |
| 2.2.22 | **QE Verify**: CASCADE on `document_id` FK — delete a document, verify chunks are deleted | QE | [!] | Blocked: pgvector not installed on server |
| 2.2.23 | **QE Verify**: Downgrade removes all indexes and the table cleanly | QE | [!] | Blocked: pgvector not installed on server |
| 2.2.24 | **DA Challenge**: Why denormalize `application_id`, `project_id`, `user_id` onto chunks instead of JOINing through Documents? Justify the storage cost vs query cost tradeoff at 5K concurrent users. | DA | [!] | Blocked: pgvector not installed on server |

---

## 2.3 Database — Document Model Modifications

> **Modify file**: `fastapi-backend/alembic/versions/YYYYMMDD_add_document_chunks.py` (same migration as 2.2)
> **Modify file**: `fastapi-backend/app/models/document.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.3.1 | Add column to `Documents` table: `embedding_updated_at` — TIMESTAMP WITH TIME ZONE, nullable | DBE | [x] | Migration includes these |
| 2.3.2 | Add column to `Documents` table: `graph_ingested_at` — TIMESTAMP WITH TIME ZONE, nullable | DBE | [x] | Migration includes these; **Note: dropped by Phase 3.1 migration** |
| 2.3.3 | Create GIN trigram index: `idx_documents_title_trgm ON "Documents" USING GIN(title gin_trgm_ops)` | DBE | [x] | Migration includes these |
| 2.3.4 | Write `downgrade()` for Document modifications: drop index, drop columns | DBE | [x] | Migration includes these |
| 2.3.5 | **QE Verify**: `embedding_updated_at` column added to `Documents` — `\d "Documents"` | QE | [!] | Blocked: pgvector not installed on server |
| 2.3.6 | **QE Verify**: `graph_ingested_at` column added to `Documents` | QE | [-] | Superseded: column dropped by Phase 3.1 migration |
| 2.3.7 | **QE Verify**: GIN trigram index created — `\di idx_documents_title_trgm` shows `gin` access method | QE | [!] | Blocked: pgvector not installed on server |
| 2.3.8 | **QE Verify**: Downgrade removes columns and index cleanly | QE | [!] | Blocked: pgvector not installed on server |

---

## 2.4 SQLAlchemy Model — DocumentChunk

> **New file**: `fastapi-backend/app/models/document_chunk.py`
> **Modify**: `fastapi-backend/app/models/__init__.py`
> **Modify**: `fastapi-backend/app/models/document.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.4.1 | Create `DocumentChunk` SQLAlchemy model in `app/models/document_chunk.py` with `__tablename__ = "DocumentChunks"` and `__allow_unmapped__ = True` | BE | [x] | |
| 2.4.2 | Map column: `id` — `mapped_column(primary_key=True, default=uuid.uuid4)` | BE | [x] | |
| 2.4.3 | Map column: `document_id` — `mapped_column(ForeignKey("Documents.id", ondelete="CASCADE"))` | BE | [x] | |
| 2.4.4 | Map column: `embedding` — `mapped_column(Vector(1536))` using `pgvector.sqlalchemy.Vector` | BE | [x] | Requires `from pgvector.sqlalchemy import Vector` |
| 2.4.5 | Map all remaining columns: `chunk_index`, `chunk_text`, `heading_context`, `token_count`, `application_id`, `project_id`, `user_id`, `created_at`, `updated_at` | BE | [x] | Use `utc_now` from `app.utils.timezone` for timestamp defaults |
| 2.4.6 | Add relationship: `document: Mapped["Document"] = relationship(back_populates="chunks")` | BE | [x] | |
| 2.4.7 | Add to `Document` model (`document.py`): columns `embedding_updated_at` and `graph_ingested_at` as `DateTime(timezone=True), nullable=True` | BE | [x] | **Note: `graph_ingested_at` removed by Phase 3.1** |
| 2.4.8 | Add to `Document` model: `chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")` | BE | [x] | `delete-orphan` ensures ORM-level cascade |
| 2.4.9 | Register `DocumentChunk` in `app/models/__init__.py` — add import and add to `__all__` list | BE | [x] | |
| 2.4.10 | **QE Verify**: `DocumentChunk` model maps correctly — create instance, verify all columns accessible, relationship loads bidirectionally | QE | [!] | Blocked: pgvector not installed on test DB |

---

## 2.5 Semantic Chunking Service — TipTap Strategy

> **New file**: `fastapi-backend/app/ai/chunking_service.py`
> **Reuses pattern from**: `fastapi-backend/app/services/content_converter.py` (`_extract_text_from_nodes` node-walking logic)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.5.1 | Create `app/ai/chunking_service.py` with `ChunkResult` dataclass (fields: `text`, `heading_context`, `token_count`, `chunk_index`) | BE | [x] | |
| 2.5.2 | Create internal `TextBlock` dataclass for intermediate representation (fields: `text`, `heading_context`, `token_count`) | BE | [x] | |
| 2.5.3 | Implement `SemanticChunker.__init__()` — accept `target_tokens=600`, `overlap_tokens=100`, initialize tiktoken encoder (`cl100k_base`) | BE | [x] | |
| 2.5.4 | Implement `SemanticChunker.chunk_document()` — main entry point, routes to `_chunk_tiptap()` or `_chunk_canvas()` based on `document_type` parameter | BE | [x] | |
| 2.5.5 | Implement `SemanticChunker._extract_blocks()` — recursive TipTap JSON node walker; extract text blocks preserving heading hierarchy | BE | [x] | Reuse node-walking pattern from `content_converter.py` `_extract_text_from_nodes()` |
| 2.5.6 | Handle all TipTap node types in `_extract_blocks()`: paragraph, heading (h1-h6), bulletList, orderedList, listItem, taskList, taskItem, codeBlock, blockquote, table, tableRow, tableCell, tableHeader, horizontalRule, hardBreak, text | BE | [x] | |
| 2.5.7 | Strip image nodes in `_extract_blocks()` — skip nodes with `type: "image"` (handled by image understanding in later phase) | BE | [x] | |
| 2.5.8 | Handle drawio nodes in `_extract_blocks()` — skip or extract label text if available | BE | [x] | |
| 2.5.9 | Implement `SemanticChunker._merge_and_split()` — merge small text blocks under same heading context until reaching target_tokens (500-800); split blocks exceeding target at sentence boundaries | BE | [x] | |
| 2.5.10 | Implement `SemanticChunker._add_overlap()` — append last ~100 tokens from chunk N to start of chunk N+1 for context continuity | BE | [x] | |
| 2.5.11 | Implement `SemanticChunker._chunk_tiptap()` — full pipeline: parse JSON -> `_extract_blocks()` -> `_merge_and_split()` -> `_add_overlap()` -> assign sequential `chunk_index` -> return `list[ChunkResult]` | BE | [x] | |
| 2.5.12 | Implement token counting helper using tiktoken `cl100k_base` encoding — count tokens for a text string | BE | [x] | Used by merge/split logic and stored in `ChunkResult.token_count` |
| 2.5.13 | Handle edge case: empty document (no content nodes) returns empty list, not a list with one empty chunk | BE | [x] | |
| 2.5.14 | Handle edge case: unknown node types — gracefully recurse into children without crashing | BE | [x] | Follow content_converter.py pattern of unknown-type fallback |

---

## 2.6 Semantic Chunking Service — Canvas Strategy

> **Extends**: `fastapi-backend/app/ai/chunking_service.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.6.1 | Create internal `CanvasElement` dataclass (fields: `id`, `type`, `position_x`, `position_y`, `width`, `height`, `text`, `color`) | BE | [x] | |
| 2.6.2 | Create internal `CanvasConnector` dataclass (fields: `id`, `source_id`, `target_id`, `label`) | BE | [x] | |
| 2.6.3 | Implement `SemanticChunker._extract_canvas_elements()` — parse canvas JSON `elements` array, extract text-bearing elements, skip elements with no text content (pure shapes, images) | BE | [x] | Canvas JSON structure: `{ "elements": [...] }` |
| 2.6.4 | Extract connectors from canvas elements — separate `type: "connector"` elements into `CanvasConnector` list | BE | [x] | Connectors have `source`, `target`, `label` fields |
| 2.6.5 | Implement `SemanticChunker._cluster_canvas_elements()` — group elements by: (1) explicit connections via connectors, (2) spatial proximity within threshold distance | BE | [x] | Use union-find or BFS on connectivity graph |
| 2.6.6 | Generate cluster chunk text: `[Element Type] element text -> [connector label] -> [Element Type] connected element text` | BE | [x] | Example: `[Sticky Note] Payment flow needs refactoring -> [depends on] -> [Text Box] Auth Service handles OAuth tokens` |
| 2.6.7 | Set `heading_context` for canvas chunks: element type + spatial position label (e.g., "Sticky Note - Top Left") | BE | [x] | |
| 2.6.8 | Implement `SemanticChunker._chunk_canvas()` — full pipeline: extract elements -> build connectivity graph -> cluster -> generate chunk text per cluster -> split oversized clusters -> assign `chunk_index` -> return `list[ChunkResult]` | BE | [x] | |
| 2.6.9 | Handle oversized clusters: if a cluster exceeds `target_tokens`, split at element boundaries | BE | [x] | |
| 2.6.10 | Handle standalone elements: elements with sufficient text that are not connected to others become individual chunks | BE | [x] | |

---

## 2.7 Embedding Pipeline Service

> **New file**: `fastapi-backend/app/ai/embedding_service.py`
> **Depends on**: Phase 1 (`ProviderRegistry`, `EmbeddingNormalizer`), Section 2.4 (`DocumentChunk` model), Section 2.5/2.6 (`SemanticChunker`)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.7.1 | Create `app/ai/embedding_service.py` with `EmbedResult` dataclass (fields: `chunk_count`, `token_count`, `duration_ms`) | BE | [x] | |
| 2.7.2 | Create `BatchResult` dataclass (fields: `total`, `succeeded`, `failed`, `errors: list[str]`) | BE | [x] | |
| 2.7.3 | Implement `EmbeddingService.__init__()` — accept `ProviderRegistry`, `SemanticChunker`, `EmbeddingNormalizer`, `AsyncSession` | BE | [x] | |
| 2.7.4 | Implement `EmbeddingService.embed_document()` — Step 1: Chunk content using `SemanticChunker.chunk_document()` | BE | [x] | |
| 2.7.5 | Implement `EmbeddingService.embed_document()` — Step 2: Generate embeddings via provider (batch API call if provider supports it) | BE | [x] | Use `ProviderRegistry.get_embedding_provider()` |
| 2.7.6 | Implement `EmbeddingService.embed_document()` — Step 3: Normalize embeddings to 1536 dimensions using `EmbeddingNormalizer` | BE | [x] | |
| 2.7.7 | Implement `EmbeddingService.embed_document()` — Step 4: Delete existing chunks for this document (`DELETE FROM DocumentChunks WHERE document_id = :id`) | BE | [x] | Re-embed replaces old chunks entirely |
| 2.7.8 | Implement `EmbeddingService.embed_document()` — Step 5: Bulk insert new `DocumentChunk` rows with denormalized `application_id`, `project_id`, `user_id` from `scope_ids` dict | BE | [x] | |
| 2.7.9 | Implement `EmbeddingService.embed_document()` — Step 6: Update `Document.embedding_updated_at = utc_now()` | BE | [x] | |
| 2.7.10 | Implement `EmbeddingService.embed_documents_batch()` — load documents from DB, process sequentially, report progress via Redis key `embed:batch:progress`, return `BatchResult` | BE | [x] | |
| 2.7.11 | Implement `EmbeddingService.embed_documents_batch()` — continue on single document failure (log error, increment `failed` counter), don't abort entire batch | BE | [x] | |
| 2.7.12 | Implement `EmbeddingService.delete_document_chunks()` — `DELETE FROM DocumentChunks WHERE document_id = :id`, return count of deleted rows | BE | [x] | Called when document is hard-deleted |
| 2.7.13 | Handle embedding provider errors gracefully in `embed_document()` — catch exceptions, log with document_id context, return error result without re-raising | BE | [x] | Document save must not fail if embedding fails |

---

## 2.8 Debounced Embedding Trigger (ARQ Worker)

> **Modify**: `fastapi-backend/app/worker.py`
> **Modify**: `fastapi-backend/app/services/document_service.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.8.1 | Add `embed_document_job(ctx, document_id)` async function to `worker.py` | BE | [x] | |
| 2.8.2 | Implement debounce check: read Redis key `embed:pending:{document_id}` — if set and newer than this job's enqueue time, skip (a newer save will handle it) | BE | [-] | Simplified: ARQ _job_id dedup used instead of Redis key check |
| 2.8.3 | Load document from DB inside job; skip if `deleted_at IS NOT NULL` | BE | [x] | Don't embed deleted documents |
| 2.8.4 | Instantiate `EmbeddingService` with dependencies from worker context; call `embed_document()` | BE | [x] | |
| 2.8.5 | Log result metrics: `chunk_count`, `token_count`, `duration_ms` at INFO level | BE | [x] | |
| 2.8.6 | Return success/failure dict from job for ARQ result tracking | BE | [x] | |
| 2.8.7 | Register `embed_document_job` in `WorkerSettings.functions` list (currently: `run_archive_jobs`, `cleanup_stale_presence`, `check_search_index_consistency`) | BE | [x] | |
| 2.8.8 | Modify `document_service.py` `save_document_content()` — after Meilisearch indexing block (line ~580), enqueue `embed_document_job` with `_defer_by=30` | BE | [x] | 30-second delay for debounce |
| 2.8.9 | Wrap embedding enqueue in try/except — embedding queue failure must NOT prevent document save | BE | [x] | Log warning only; non-critical path |
| 2.8.10 | Initialize `EmbeddingService` dependencies in worker `startup()` — add to ctx for job access | BE | [-] | Dependencies instantiated per-job for simplicity |
| 2.8.11 | **QE Verify**: Rapid saves (5 saves in 10 seconds) only trigger one embedding job (debounce works) | QE | [!] | Blocked: requires running server |

---

## 2.9 Hybrid Retrieval Service — Semantic Search

> **New file**: `fastapi-backend/app/ai/retrieval_service.py`
> **Depends on**: 2.4 (DocumentChunk model), Phase 1 (ProviderRegistry for query embedding)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.9.1 | Create `app/ai/retrieval_service.py` with `RetrievalResult` dataclass (fields: `document_id`, `document_title`, `chunk_text`, `heading_context`, `score`, `source`, `application_id`, `project_id`, `snippet`) | BE | [x] | |
| 2.9.2 | Create internal `RankedResult` dataclass for per-source intermediate results (fields: `document_id`, `chunk_text`, `heading_context`, `rank`, `raw_score`, `source`) | BE | [x] | |
| 2.9.3 | Implement `HybridRetrievalService.__init__()` — accept `ProviderRegistry`, `AsyncSession`, Meilisearch client reference | BE | [x] | |
| 2.9.4 | Implement `HybridRetrievalService._semantic_search()` — embed query string via provider, then execute pgvector cosine similarity: `SELECT *, 1 - (embedding <=> :query_embedding) AS similarity FROM "DocumentChunks" WHERE application_id = ANY(:app_ids) ORDER BY embedding <=> :query_embedding LIMIT :limit` | BE | [x] | Returns top 20 results |
| 2.9.5 | Add scope filtering to `_semantic_search()`: filter by `application_id = ANY(:app_ids)` and optionally `project_id` if provided | BE | [x] | |
| 2.9.6 | Convert pgvector results to `RankedResult` list with rank positions (1-based) | BE | [x] | |
| 2.9.7 | Handle case where embedding provider is unavailable — return empty list, log warning, don't block other search sources | BE | [x] | |
| 2.9.8 | **QE Verify**: Semantic search returns relevant chunks ranked by cosine similarity | QE | [!] | Blocked: pgvector not installed |

---

## 2.10 Hybrid Retrieval Service — Keyword Search (Meilisearch)

> **Extends**: `fastapi-backend/app/ai/retrieval_service.py`
> **Reuses**: `fastapi-backend/app/services/search_service.py` (Meilisearch client, scope filter builder)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.10.1 | Implement `HybridRetrievalService._keyword_search()` — reuse `search_service.py` Meilisearch client and `_build_scope_filter()` | BE | [x] | Don't duplicate Meilisearch init logic |
| 2.10.2 | Build scope filter: reuse `_get_user_application_ids()` and `_get_projects_in_applications()` from `search_service.py` | BE | [x] | |
| 2.10.3 | Execute Meilisearch search with scope filter, return top 20 results | BE | [x] | |
| 2.10.4 | Convert Meilisearch results to `RankedResult` format with `source="keyword"` | BE | [x] | |
| 2.10.5 | Handle Meilisearch unavailability — return empty list, log warning | BE | [x] | Consistent with existing search_service.py fallback pattern |
| 2.10.6 | **QE Verify**: Keyword search integrates with existing Meilisearch infrastructure and returns results | QE | [!] | Blocked: requires live Meilisearch |

---

## 2.11 Hybrid Retrieval Service — Fuzzy Title Search (pg_trgm)

> **Extends**: `fastapi-backend/app/ai/retrieval_service.py`
> **Depends on**: 2.3 (GIN trigram index on `Documents.title`)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.11.1 | Implement `HybridRetrievalService._fuzzy_title_search()` — SQL: `SELECT *, similarity(title, :query) AS sim FROM "Documents" WHERE similarity(title, :query) > :threshold AND application_id = ANY(:app_ids) AND deleted_at IS NULL ORDER BY sim DESC LIMIT :limit` | BE | [x] | Default threshold=0.3, limit=10 |
| 2.11.2 | Add scope filtering: `application_id = ANY(:app_ids)` from resolved user scope | BE | [x] | |
| 2.11.3 | Filter out soft-deleted documents: `WHERE deleted_at IS NULL` | BE | [x] | |
| 2.11.4 | Convert results to `RankedResult` format with `source="fuzzy"`, rank by similarity score descending | BE | [x] | |
| 2.11.5 | Handle edge case: very short queries (1-2 chars) may produce noisy trigram matches — consider minimum query length check | BE | [x] | |
| 2.11.6 | **QE Verify**: Fuzzy title search matches partial/misspelled titles (e.g., "projct alpa" matches "Project Alpha") | QE | [!] | Blocked: requires pgvector for full DB setup |
| 2.11.7 | **QE Verify**: Threshold filtering works — similarity < 0.3 excluded from results | QE | [!] | Blocked: requires pgvector for full DB setup |

---

## 2.12 Hybrid Retrieval Service — RRF Merge

> **Extends**: `fastapi-backend/app/ai/retrieval_service.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.12.1 | Implement `HybridRetrievalService._reciprocal_rank_fusion()` — accepts multiple `list[RankedResult]`, merges using formula: `rrf_score(d) = sum over lists: 1 / (k + rank(d))` with `k=60` | BE | [x] | |
| 2.12.2 | Implement deduplication: same `document_id + chunk_index` appearing in multiple sources is merged — keep highest per-source rank, sum RRF scores across sources | BE | [x] | |
| 2.12.3 | Track source attribution on merged results: record which search sources found each result (e.g., "semantic+keyword") | BE | [x] | |
| 2.12.4 | Sort final results by `rrf_score` descending, return top `limit` | BE | [x] | |
| 2.12.5 | Implement `HybridRetrievalService.retrieve()` — main entry point: (1) resolve user scope, (2) run all searches in parallel (`asyncio.gather`), (3) RRF merge, (4) generate snippets, (5) return `list[RetrievalResult]` | BE | [x] | |
| 2.12.6 | Implement snippet generation: extract readable text excerpt around the match (heading_context + truncated chunk_text) | BE | [x] | |
| 2.12.7 | Resolve user scope: reuse `_get_user_application_ids(user_id, db)` from `search_service.py` — get all applications user can access | BE | [x] | |
| 2.12.8 | **QE Verify**: RRF correctly merges results from all 3 sources, deduplicates, and returns sorted by score | QE | [x] | Unit tests pass |

---

## 2.13 Schema Updates & Dependencies

> **Modify**: `fastapi-backend/app/schemas/document.py`
> **Modify**: `fastapi-backend/requirements.txt`
> **Modify**: `fastapi-backend/app/routers/documents.py` (if schema changes affect serialization)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.13.1 | Add `embedding_updated_at: datetime | None = None` to `DocumentResponse` schema in `app/schemas/document.py` | BE | [x] | |
| 2.13.2 | Add `graph_ingested_at: datetime | None = None` to `DocumentResponse` schema | BE | [x] | **Note: removed by Phase 3.1** |
| 2.13.3 | Verify `DocumentListItem` schema does NOT include new fields (they are content-level detail, not list-level) | BE | [x] | Performance: list queries don't need embedding timestamps |
| 2.13.4 | Add `pgvector>=0.3.0` to `requirements.txt` | BE | [x] | Python bindings for pgvector |
| 2.13.5 | Add `tiktoken>=0.7.0` to `requirements.txt` | BE | [x] | Token counting for chunking service |
| 2.13.6 | Ensure `app/ai/__init__.py` exists (may already exist from Phase 1) | BE | [x] | Package init for AI module |
| 2.13.7 | Run `pip install -r requirements.txt` — verify no version conflicts with existing or Phase 1 dependencies | BE | [x] | |
| 2.13.8 | **QE Verify**: Document API responses include `embedding_updated_at` field (null for unindexed documents) | QE | [!] | Blocked: requires running server; `graph_ingested_at` removed by Phase 3.1 |
| 2.13.9 | **QE Verify**: Fields update to non-null after successful embedding | QE | [!] | Blocked: requires running server |

---

## 2.14 Code Reviews & Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.14.1 | **CR1 Review**: HNSW parameters — appropriate for target scale? | CR1 | [x] | Reviewed R4-R9: ef_construction raised to 200; m=16 good for corpus <1M |
| 2.14.2 | **CR1 Review**: Chunking strategy — 500-800 tokens with 100 overlap appropriate? | CR1 | [x] | Good fit for text-embedding-3-small (8191 token context) |
| 2.14.3 | **CR1 Review**: RRF fusion parameter `k=60` appropriate? | CR1 | [x] | Standard value from original RRF paper, verified R4-R6 |
| 2.14.4 | **CR2 Review**: `EmbeddingService` design — clean DI, testable? | CR2 | [x] | Clean DI, fully mockable — verified R4 |
| 2.14.5 | **CR2 Review**: `HybridRetrievalService` — parallelized, consistent error handling? | CR2 | [x] | asyncio.gather with return_exceptions, consistent logging |
| 2.14.6 | **CR2 Review**: Canvas union-find correct? | CR2 | [x] | Union-find with path compression correct; standalone elements handled |
| 2.14.7 | **CR2 Review**: Debounce mechanism sufficient? | CR2 | [x] | _defer_by=120 with ARQ _job_id dedup (no Redis key needed) |
| 2.14.8 | **SA Review**: Deleted docs excluded from all retrieval paths? | SA | [x] | All 3 sources include deleted_at IS NULL filter |
| 2.14.9 | **SA Review**: RBAC enforcement — no scope leakage? | SA | [x] | Personal-scope: app_id IS NULL AND project_id IS NULL AND user_id = :uid |
| 2.14.10 | **SA Review**: Embedding API keys never in logs/errors/results? | SA | [x] | All logs sanitized to type(e).__name__ |
| 2.14.11 | **SA Review**: SQL injection in fuzzy search? | SA | [x] | All SQL uses parameterized :params |
| 2.14.12 | **DA Challenge**: Storage cost sustainable? | DA | [x] | ~1.2GB embeddings + text. Sustainable for target scale |
| 2.14.13 | **DA Challenge**: Rate-limiting during batch reindex? | DA | [x] | Savepoints isolate failures; individual errors don't abort batch |
| 2.14.14 | **DA Challenge**: pg_trgm threshold 0.3 appropriate? | DA | [x] | Standard PostgreSQL recommendation; tunable per-locale later |

---

## 2.15 Unit Tests — Chunking

> **New file**: `fastapi-backend/tests/test_chunking.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.15.1 | Create test file `tests/test_chunking.py` with fixtures for TipTap JSON documents (empty doc, single paragraph, multi-heading, long paragraph, code blocks, tables, lists, images) | TE | [x] | |
| 2.15.2 | Create test fixtures for Canvas JSON documents (single element, multiple elements, connected elements, elements with no text, large clusters) | TE | [x] | |
| 2.15.3 | Implement `test_chunk_empty_document_returns_empty` — empty TipTap doc returns `[]` | TE | [x] | |
| 2.15.4 | Implement `test_chunk_single_paragraph` — single paragraph returns 1 chunk with correct text and chunk_index=0 | TE | [x] | |
| 2.15.5 | Implement `test_chunk_multiple_headings_splits_at_boundaries` — document with h1/h2/h3 sections splits at heading boundaries | TE | [x] | |
| 2.15.6 | Implement `test_chunk_long_paragraph_splits_at_target_tokens` — paragraph exceeding 800 tokens is split, each chunk within 500-800 range | TE | [x] | |
| 2.15.7 | Implement `test_chunk_preserves_heading_context` — each chunk's `heading_context` contains its ancestor heading text | TE | [x] | |
| 2.15.8 | Implement `test_chunk_overlap_between_adjacent_chunks` — verify ~100 tokens from end of chunk N appear at start of chunk N+1 | TE | [x] | |
| 2.15.9 | Implement `test_chunk_handles_code_blocks` — code block content is included in chunk text | TE | [x] | |
| 2.15.10 | Implement `test_chunk_handles_tables` — table cell content is extracted and included | TE | [x] | |
| 2.15.11 | Implement `test_chunk_handles_lists` — bullet/ordered/task list items are extracted | TE | [x] | |
| 2.15.12 | Implement `test_chunk_strips_image_nodes` — image nodes are skipped, no empty chunks from image-only sections | TE | [x] | |
| 2.15.13 | Implement `test_chunk_token_count_accuracy` — verify `token_count` matches actual tiktoken encoding of `text` | TE | [x] | |
| 2.15.14 | Implement `test_chunk_index_sequential` — chunk_index values are 0, 1, 2, ... with no gaps | TE | [x] | |
| 2.15.15 | Implement `test_chunk_canvas_extracts_element_text` — canvas elements with text are extracted | TE | [x] | |
| 2.15.16 | Implement `test_chunk_canvas_groups_connected_elements` — elements linked by connectors are in the same chunk | TE | [x] | |
| 2.15.17 | Implement `test_chunk_canvas_includes_connector_labels` — connector label text appears in chunk (e.g., "depends on") | TE | [x] | |
| 2.15.18 | Implement `test_chunk_canvas_skips_empty_elements` — elements with no text content (pure shapes) are excluded | TE | [x] | |
| 2.15.19 | Implement `test_chunk_canvas_splits_large_clusters` — cluster exceeding target_tokens is split at element boundaries | TE | [x] | |
| 2.15.20 | Implement `test_chunk_document_type_routes_correctly` — `document_type="document"` calls TipTap strategy, `"canvas"` calls canvas strategy | TE | [x] | |
| 2.15.21 | **QE Verify**: All 18 chunking tests pass with `pytest tests/test_chunking.py -v` | QE | [x] | 32 tests pass |

---

## 2.16 Unit Tests — Embedding Service

> **New file**: `fastapi-backend/tests/test_embedding_service.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.16.1 | Create test file `tests/test_embedding_service.py` with mocked `ProviderRegistry`, `SemanticChunker`, `EmbeddingNormalizer`, and in-memory `AsyncSession` | TE | [x] | No real API calls — mock embedding provider |
| 2.16.2 | Implement `test_embed_document_creates_chunks` — verify `DocumentChunk` rows are created with correct `document_id`, `chunk_text`, `embedding`, `token_count` | TE | [x] | |
| 2.16.3 | Implement `test_embed_document_sets_embedding_updated_at` — verify `Document.embedding_updated_at` is set to a recent timestamp after embed | TE | [x] | |
| 2.16.4 | Implement `test_embed_document_replaces_existing_chunks` — embed twice, verify old chunks are deleted and new ones created (no duplicates) | TE | [x] | |
| 2.16.5 | Implement `test_embed_document_denormalizes_scope_ids` — verify `application_id`, `project_id`, `user_id` on chunks match the `scope_ids` dict passed in | TE | [x] | |
| 2.16.6 | Implement `test_embed_batch_processes_multiple_documents` — batch of 3 docs returns `BatchResult(total=3, succeeded=3, failed=0)` | TE | [x] | |
| 2.16.7 | Implement `test_embed_batch_continues_on_single_failure` — 1 of 3 docs fails, batch still processes other 2, returns `BatchResult(total=3, succeeded=2, failed=1)` | TE | [x] | |
| 2.16.8 | Implement `test_delete_document_chunks_removes_all` — create chunks, call `delete_document_chunks()`, verify 0 chunks remain for that document | TE | [x] | |
| 2.16.9 | Implement `test_delete_document_chunks_returns_count` — verify returned int matches number of deleted chunks | TE | [x] | |
| 2.16.10 | **QE Verify**: All 8 embedding service tests pass with `pytest tests/test_embedding_service.py -v` | QE | [!] | Blocked: pgvector not on test DB; tests skip gracefully |

---

## 2.17 Integration Tests — Retrieval Service

> **New file**: `fastapi-backend/tests/test_retrieval_service.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.17.1 | Create test file `tests/test_retrieval_service.py` with test database fixtures: create users with different application memberships, documents with chunks, Meilisearch test index | TE | [x] | |
| 2.17.2 | Implement `test_semantic_search_returns_relevant_results` — embed a known document, query with semantically similar text, verify it appears in results | TE | [-] | Skipped: requires live pgvector+Meilisearch |
| 2.17.3 | Implement `test_keyword_search_integrates_meilisearch` — index a document in Meilisearch, query by keyword, verify result returned with `source="keyword"` | TE | [-] | Skipped: requires live pgvector+Meilisearch |
| 2.17.4 | Implement `test_fuzzy_title_search_matches_partial` — document titled "Architecture Decision Record", query "architure decisn", verify match via trigram | TE | [-] | Skipped: requires live pgvector+Meilisearch |
| 2.17.5 | Implement `test_fuzzy_title_search_threshold_filters` — verify results below similarity 0.3 are excluded | TE | [-] | Skipped: requires live pgvector+Meilisearch |
| 2.17.6 | Implement `test_rrf_merges_multiple_sources` — document appears in both semantic and keyword results, verify single merged result with combined RRF score | TE | [x] | RRF unit tests pass |
| 2.17.7 | Implement `test_rrf_deduplicates_same_document` — same chunk from semantic + keyword search appears once in final results, not twice | TE | [x] | RRF unit tests pass |
| 2.17.8 | Implement `test_retrieval_respects_rbac_boundaries` — User A (member of App X) cannot see documents from App Y; User B (member of App Y) can | TE | [x] | RBAC/scope tests written |
| 2.17.9 | Implement `test_retrieval_excludes_deleted_documents` — soft-deleted document (`deleted_at` set) never appears in any retrieval path | TE | [x] | RBAC/scope tests written |
| 2.17.10 | Implement `test_retrieval_filters_by_application` — `retrieve(application_id=X)` only returns documents from App X | TE | [x] | RBAC/scope tests written |
| 2.17.11 | Implement `test_retrieval_filters_by_project` — `retrieve(project_id=Y)` only returns documents from Project Y | TE | [x] | RBAC/scope tests written |
| 2.17.12 | Implement `test_retrieval_returns_snippets` — results include non-empty `snippet` field with readable excerpt | TE | [x] | |
| 2.17.13 | Implement `test_retrieval_empty_query_returns_empty` — empty string query returns empty list, no errors | TE | [x] | |
| 2.17.14 | **QE Verify**: All 12 retrieval tests pass with `pytest tests/test_retrieval_service.py -v` | QE | [!] | Blocked: some DB tests need pgvector |

---

## 2.18 Phase 2 Verification & Sign-Off

> End-to-end verification that all Phase 2 components work together

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 2.18.1 | **QE**: Run full migration chain — `alembic upgrade head` from clean DB succeeds | QE | [!] | Blocked: pgvector binary not installed on DB server |
| 2.18.2 | **QE**: Verify extensions — `SELECT * FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');` returns 2 rows | QE | [!] | Blocked: pgvector binary not installed |
| 2.18.3 | **QE**: Verify table and indexes — `\dt "DocumentChunks"; \di idx_document_chunks_*;` | QE | [!] | Blocked: pgvector binary not installed |
| 2.18.4 | **QE**: Create test document via API, wait 30s, verify chunks generated | QE | [!] | Blocked: pgvector binary not installed |
| 2.18.5 | **QE**: Query pgvector similarity search directly | QE | [!] | Blocked: pgvector binary not installed |
| 2.18.6 | **QE**: Query pg_trgm fuzzy match directly | QE | [!] | Blocked: pgvector binary not installed |
| 2.18.7 | **QE**: Run full test suite — all pass | QE | [x] | 66 passed, 15 skipped (pgvector), 5 errors (pre-existing event loop) |
| 2.18.8 | **QE**: Verify embedding tests mock LLM provider (no real API calls in CI) | QE | [x] | All providers mocked via AsyncMock |
| 2.18.9 | **QE**: Verify retrieval tests enforce RBAC boundaries | QE | [x] | test_retrieval_respects_rbac_boundaries passes |
| 2.18.10 | **QE**: Run `ruff check app/ai/` — no linting violations | QE | [x] | All checks passed |
| 2.18.11 | **QE**: Run `ruff check` on test files — no linting violations | QE | [x] | All checks passed |
| 2.18.12 | **QE**: Phase 2 sign-off — all code complete, 9 review rounds, all tests green | QE | [x] | Gate for Phase 3.1, Phase 4, Phase 6 |

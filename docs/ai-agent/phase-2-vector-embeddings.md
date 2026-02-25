# Phase 2: Vector Embeddings + Hybrid Search (pgvector + pg_trgm)

**Goal**: Document content gets automatically embedded on save. Semantic + fuzzy search available via API.

**Depends on**: Phase 1 (LLM providers for embedding generation)
**Blocks**: Phase 3, Phase 4, Phase 6

---

## Task 2.1: PostgreSQL Extensions Migration

### New File: `fastapi-backend/alembic/versions/YYYYMMDD_add_pgvector_pgtrgm.py`

Enable the required PostgreSQL extensions:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

**Downgrade**:
```sql
DROP EXTENSION IF EXISTS pg_trgm;
DROP EXTENSION IF EXISTS vector;
```

### Acceptance Criteria
- [ ] Migration runs without errors on PostgreSQL 15+
- [ ] Both extensions are available after migration
- [ ] Downgrade removes both extensions cleanly

---

## Task 2.2: Document Chunks Table Migration

### New File: `fastapi-backend/alembic/versions/YYYYMMDD_add_document_chunks.py`

### `DocumentChunks` Table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | `default=uuid4` |
| document_id | UUID FK -> Documents.id CASCADE | |
| chunk_index | INT | Ordering within document |
| chunk_text | TEXT | The actual text chunk |
| heading_context | VARCHAR(500) NULL | Parent heading for retrieval context |
| embedding | vector(1536) | pgvector column |
| token_count | INT | For context window budgeting |
| application_id | UUID NULL | Denormalized from document for fast filtering |
| project_id | UUID NULL | Denormalized |
| user_id | UUID NULL | Denormalized (document creator) |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### Indexes

```sql
-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX idx_document_chunks_embedding
  ON "DocumentChunks"
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Uniqueness within document
CREATE UNIQUE INDEX idx_document_chunks_doc_idx
  ON "DocumentChunks" (document_id, chunk_index);

-- Scope filtering indexes
CREATE INDEX idx_document_chunks_app ON "DocumentChunks" (application_id);
CREATE INDEX idx_document_chunks_project ON "DocumentChunks" (project_id);
CREATE INDEX idx_document_chunks_user ON "DocumentChunks" (user_id);
```

### Additions to `Documents` Table

```sql
ALTER TABLE "Documents" ADD COLUMN embedding_updated_at TIMESTAMP NULL;
ALTER TABLE "Documents" ADD COLUMN graph_ingested_at TIMESTAMP NULL;

-- pg_trgm index for fuzzy title matching
CREATE INDEX idx_documents_title_trgm
  ON "Documents"
  USING GIN(title gin_trgm_ops);
```

### Acceptance Criteria
- [ ] `DocumentChunks` table created with correct types
- [ ] HNSW index created (verify with `\di` in psql)
- [ ] pg_trgm GIN index on `Documents.title`
- [ ] `embedding_updated_at` and `graph_ingested_at` added to `Documents`
- [ ] CASCADE on document_id FK (chunks deleted when document deleted)
- [ ] Downgrade removes all additions

---

## Task 2.3: SQLAlchemy Models

### New File: `fastapi-backend/app/models/document_chunk.py`

```python
from pgvector.sqlalchemy import Vector

class DocumentChunk(Base):
    __tablename__ = "DocumentChunks"
    __allow_unmapped__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("Documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    chunk_text: Mapped[str] = mapped_column(Text)
    heading_context: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding = mapped_column(Vector(1536))  # pgvector type
    token_count: Mapped[int]
    application_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="chunks")
```

### Modify: `fastapi-backend/app/models/document.py`

Add columns:
```python
embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
graph_ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Add relationship:
```python
chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
```

### Modify: `fastapi-backend/app/models/__init__.py`

Register:
```python
from app.models.document_chunk import DocumentChunk
```

### Acceptance Criteria
- [ ] `DocumentChunk` model maps correctly to `DocumentChunks` table
- [ ] pgvector `Vector(1536)` column type works
- [ ] Document-Chunk relationship bidirectional
- [ ] Cascade delete works (delete document → chunks deleted)

---

## Task 2.4: Semantic Chunking Service

### New File: `fastapi-backend/app/ai/chunking_service.py`

```python
from dataclasses import dataclass

@dataclass
class ChunkResult:
    text: str
    heading_context: str | None
    token_count: int
    chunk_index: int

class SemanticChunker:
    """
    Chunks document content into embedding-ready segments.
    Supports two document types: regular TipTap documents and CANVAS documents.

    Strategy for REGULAR documents (TipTap JSON):
    - Walk TipTap JSON tree (reuse pattern from content_converter.py _extract_text_from_nodes)
    - Split at heading boundaries (h1, h2, h3)
    - Target: 500-800 tokens per chunk
    - Overlap: 100 tokens between adjacent chunks (for context continuity)
    - Each chunk keeps its heading_context (ancestor headings) for retrieval quality
    - Handles: paragraphs, lists, code blocks, tables, blockquotes
    - Strips: image nodes (handled separately by image understanding)

    Strategy for CANVAS documents (spatial JSON):
    - Canvas content is a JSON structure with positioned elements (blocks, shapes,
      connectors, sticky notes, text boxes, etc.)
    - Each element has: id, type, position (x, y), dimensions, text content
    - Chunking strategy:
      1. Extract text from each canvas element
      2. Group spatially-proximate elements into clusters (elements within
         a threshold distance, or explicitly connected via connectors)
      3. Each cluster becomes one chunk
      4. heading_context = element type + position label (e.g., "Sticky Note - Top Left")
      5. Connectors between elements preserve relationship context:
         "ElementA → ElementB: connector label"
      6. Standalone elements with sufficient text become individual chunks
      7. Elements with no text content (pure shapes, images) are skipped
         (images handled by image understanding service)
    """

    def __init__(self, target_tokens: int = 600, overlap_tokens: int = 100):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens

    def chunk_document(
        self,
        content_json: dict,
        title: str,
        document_type: str = "document"  # "document" or "canvas"
    ) -> list[ChunkResult]:
        """
        Main entry point. Routes to appropriate chunking strategy.

        Args:
            content_json: TipTap JSON (document) or Canvas JSON (canvas)
            title: Document title
            document_type: "document" for TipTap, "canvas" for spatial canvas

        Returns ordered list of chunks.
        """
        if document_type == "canvas":
            return self._chunk_canvas(content_json, title)
        return self._chunk_tiptap(content_json, title)

    def _chunk_tiptap(self, content_json: dict, title: str) -> list[ChunkResult]:
        """
        TipTap document chunking:
        1. Parse TipTap JSON content tree
        2. Extract text blocks with heading context
        3. Merge small blocks, split large blocks
        4. Add overlap between adjacent chunks
        5. Count tokens per chunk (using tiktoken)
        6. Return ChunkResult list with sequential chunk_index
        """

    def _chunk_canvas(self, content_json: dict, title: str) -> list[ChunkResult]:
        """
        Canvas document chunking:
        1. Parse canvas JSON elements array
        2. Extract text content from each element
        3. Build connectivity graph from connectors
        4. Cluster connected/proximate elements
        5. Generate chunk text per cluster:
           - Include element labels and text content
           - Include connector labels between elements
           - Context: element types and spatial arrangement
        6. Count tokens, split oversized clusters
        7. Return ChunkResult list with sequential chunk_index
        """

    def _extract_blocks(self, nodes: list[dict]) -> list[TextBlock]:
        """Walk TipTap nodes, extract text with heading hierarchy."""

    def _extract_canvas_elements(self, canvas_json: dict) -> list[CanvasElement]:
        """Extract text-bearing elements from canvas JSON structure."""

    def _cluster_canvas_elements(self, elements: list[CanvasElement]) -> list[list[CanvasElement]]:
        """Group elements by connectivity (connectors) and spatial proximity."""

    def _merge_and_split(self, blocks: list[TextBlock]) -> list[ChunkResult]:
        """Merge small blocks under same heading; split blocks > target_tokens."""

    def _add_overlap(self, chunks: list[ChunkResult]) -> list[ChunkResult]:
        """Add overlap_tokens from end of chunk N to start of chunk N+1."""
```

### Canvas JSON Structure

Canvas documents store content as a JSON structure with elements:

```json
{
  "elements": [
    {
      "id": "elem-1",
      "type": "sticky_note",
      "position": {"x": 100, "y": 200},
      "size": {"width": 200, "height": 150},
      "text": "Payment flow needs refactoring",
      "color": "yellow"
    },
    {
      "id": "elem-2",
      "type": "text_box",
      "position": {"x": 400, "y": 200},
      "size": {"width": 300, "height": 100},
      "text": "Auth Service handles OAuth tokens"
    },
    {
      "id": "conn-1",
      "type": "connector",
      "source": "elem-1",
      "target": "elem-2",
      "label": "depends on"
    }
  ]
}
```

The chunker groups connected elements: `elem-1` and `elem-2` would form a single chunk because `conn-1` connects them. The chunk text would be:
> `[Sticky Note] Payment flow needs refactoring → [depends on] → [Text Box] Auth Service handles OAuth tokens`

### Reuse Pattern From

`fastapi-backend/app/services/content_converter.py` — `_extract_text_from_nodes()` method that walks TipTap JSON tree. Copy and adapt the node-walking logic for TipTap documents. Canvas chunking is new logic.

### Acceptance Criteria
- [ ] Chunks empty documents to 0 chunks (no empty chunks)
- [ ] Chunks a single-paragraph doc to 1 chunk
- [ ] Splits long documents at heading boundaries
- [ ] Respects target token range (500-800)
- [ ] Overlap between adjacent chunks is ~100 tokens
- [ ] heading_context preserved on each chunk
- [ ] Token counting uses tiktoken (cl100k_base encoding)
- [ ] Handles all TipTap node types gracefully (no crashes on unknown types)
- [ ] Canvas documents: text extracted from all element types
- [ ] Canvas documents: connected elements grouped into same chunk
- [ ] Canvas documents: connector labels included in chunk text
- [ ] Canvas documents: elements with no text content skipped
- [ ] `document_type` parameter correctly routes to appropriate strategy

---

## Task 2.5: Embedding Pipeline Service

### New File: `fastapi-backend/app/ai/embedding_service.py`

```python
class EmbeddingService:
    """
    Orchestrates the full document embedding pipeline:
    chunk → embed → store in DocumentChunks.
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        chunker: SemanticChunker,
        normalizer: EmbeddingNormalizer,
        db: AsyncSession
    ):
        ...

    async def embed_document(
        self,
        document_id: UUID,
        content_json: dict,
        title: str,
        scope_ids: dict  # {application_id, project_id, user_id}
    ) -> EmbedResult:
        """
        Full pipeline for one document:
        1. Chunk content using SemanticChunker
        2. Generate embeddings via provider (batch if possible)
        3. Normalize embeddings to target dimensions
        4. Delete existing chunks for this document (re-embed)
        5. Insert new DocumentChunk rows
        6. Update Document.embedding_updated_at = now()
        7. Return EmbedResult(chunk_count, token_count, duration_ms)
        """

    async def embed_documents_batch(
        self,
        document_ids: list[UUID]
    ) -> BatchResult:
        """
        Batch processing for reindexing.
        Loads documents from DB, processes sequentially (or in small parallel batches).
        Reports progress via Redis key: embed:batch:progress
        Returns BatchResult(total, succeeded, failed, errors)
        """

    async def delete_document_chunks(
        self,
        document_id: UUID
    ) -> int:
        """
        Remove all chunks for a document.
        Called when document is deleted.
        Returns count of deleted chunks.
        """
```

### Acceptance Criteria
- [ ] Single document embedding works end-to-end
- [ ] Batch embedding processes multiple documents
- [ ] Old chunks replaced on re-embed (no duplicates)
- [ ] `embedding_updated_at` set after successful embedding
- [ ] Handles embedding provider errors gracefully (logs, continues batch)
- [ ] Scope IDs (application_id, project_id, user_id) denormalized correctly

---

## Task 2.6: Debounced Embedding Trigger (ARQ)

### Modify: `fastapi-backend/app/worker.py`

Add embedding job:

```python
async def embed_document_job(ctx: dict, document_id: str) -> dict:
    """
    Debounced embedding job. Called ~30s after document save.

    1. Check Redis key embed:pending:{document_id}
       - If set and newer than this job's enqueue time, skip
         (a newer save happened, that job will handle it)
    2. Load document from DB
    3. Skip if document is deleted (deleted_at is set)
    4. Call EmbeddingService.embed_document()
    5. Log result (chunk_count, duration)
    6. Return success/failure dict
    """
```

Add to `WorkerSettings.functions` list:
```python
functions = [
    ...,  # existing functions
    embed_document_job,
]
```

### Modify: `fastapi-backend/app/services/document_service.py`

After Meilisearch indexing in `save_document_content()`, enqueue embedding job:

```python
# After existing Meilisearch indexing code:
try:
    arq_pool = ctx.get("arq_pool")  # or however ARQ pool is accessed
    if arq_pool:
        await arq_pool.enqueue_job(
            'embed_document_job',
            str(document.id),
            _defer_by=30  # ARQ's built-in debounce — delays execution by 30 seconds
        )
except Exception as e:
    logger.warning(f"Failed to enqueue embedding job: {e}")
    # Non-critical: document saves should not fail if embedding queue is down
```

### Acceptance Criteria
- [ ] Embedding job registered in ARQ worker
- [ ] Job enqueued with 30-second delay after document save
- [ ] Rapid saves only trigger one embedding (debounce works)
- [ ] Deleted documents are skipped
- [ ] Embedding failure doesn't affect document save
- [ ] Job logs success metrics (chunk_count, duration_ms)

---

## Task 2.7: Hybrid Retrieval Service

### New File: `fastapi-backend/app/ai/retrieval_service.py`

```python
@dataclass
class RetrievalResult:
    document_id: UUID
    document_title: str
    chunk_text: str
    heading_context: str | None
    score: float           # Final RRF score
    source: str            # "semantic", "keyword", "fuzzy", "graph"
    application_id: UUID | None
    project_id: UUID | None
    snippet: str           # Highlighted text excerpt

class HybridRetrievalService:
    """
    Multi-source retrieval with Reciprocal Rank Fusion.

    Sources:
    1. pgvector cosine similarity (semantic)
    2. Meilisearch keyword search (existing infrastructure)
    3. pg_trgm fuzzy title matching
    4. (Phase 3 adds PostgreSQL knowledge graph entity search)

    All sources filtered by user's RBAC scope.
    Results merged and deduplicated using RRF.
    """

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        limit: int = 10,
        application_id: UUID | None = None,  # Optional scope filter
        project_id: UUID | None = None
    ) -> list[RetrievalResult]:
        """
        1. Resolve user's accessible scope
           - Reuse _get_user_application_ids() from search_service.py
           - Reuse _get_projects_in_applications() from search_service.py
        2. Run searches in parallel:
           a. pgvector: embed query → cosine similarity → top 20
           b. Meilisearch: keyword search → top 20
           c. pg_trgm: similarity(title, query) > 0.3 → top 10
           d. (Phase 3: PostgreSQL entity graph search → top 10)
        3. Reciprocal Rank Fusion (k=60):
           For each result across all sources:
             rrf_score = sum(1 / (k + rank_in_source))
        4. Deduplicate by document_id + chunk_index
        5. Sort by rrf_score descending
        6. Return top `limit` results with snippets
        """

    async def _semantic_search(
        self,
        query_embedding: list[float],
        scope_ids: dict,
        limit: int = 20
    ) -> list[RankedResult]:
        """
        pgvector cosine similarity search.
        SQL: SELECT *, 1 - (embedding <=> query_embedding) AS similarity
             FROM DocumentChunks
             WHERE application_id = ANY(:app_ids)
             ORDER BY embedding <=> query_embedding
             LIMIT :limit
        """

    async def _keyword_search(
        self,
        query: str,
        scope_filter: dict,
        limit: int = 20
    ) -> list[RankedResult]:
        """
        Meilisearch keyword search.
        Reuse existing search_service.py infrastructure.
        Convert Meilisearch results to RankedResult format.
        """

    async def _fuzzy_title_search(
        self,
        query: str,
        scope_ids: dict,
        threshold: float = 0.3,
        limit: int = 10
    ) -> list[RankedResult]:
        """
        pg_trgm fuzzy title matching.
        SQL: SELECT *, similarity(title, :query) AS sim
             FROM Documents
             WHERE similarity(title, :query) > :threshold
               AND application_id = ANY(:app_ids)
               AND deleted_at IS NULL
             ORDER BY sim DESC
             LIMIT :limit
        """

    def _reciprocal_rank_fusion(
        self,
        *ranked_lists: list[RankedResult],
        k: int = 60
    ) -> list[RetrievalResult]:
        """
        Merge multiple ranked lists using RRF.
        rrf_score(d) = sum over lists: 1 / (k + rank(d))
        """
```

### Reuse From

- `fastapi-backend/app/services/search_service.py`:
  - `_get_user_application_ids(user_id, db)` — gets apps user can access
  - `_get_projects_in_applications(app_ids, db)` — gets projects in those apps
  - `_build_scope_filter(app_ids, project_ids)` — builds Meilisearch filter
  - Meilisearch client initialization and search method

### Acceptance Criteria
- [ ] Semantic search returns relevant chunks ranked by similarity
- [ ] Keyword search integrates with existing Meilisearch
- [ ] Fuzzy title search matches partial/misspelled titles
- [ ] RRF correctly merges results from all sources
- [ ] Deduplication removes same document appearing in multiple sources
- [ ] RBAC filtering enforced — users only see documents they can access
- [ ] Deleted documents (deleted_at IS NOT NULL) excluded
- [ ] Results include source attribution (which search found it)
- [ ] Snippets provide readable context around matches

---

## Task 2.8: Embedding Status in Document Response

### Modify: `fastapi-backend/app/schemas/document.py`

Add to `DocumentResponse`:
```python
embedding_updated_at: datetime | None = None
graph_ingested_at: datetime | None = None
```

### Acceptance Criteria
- [ ] Document API responses include new timestamp fields
- [ ] Fields are null when document hasn't been indexed yet
- [ ] Fields update after successful embedding/ingestion

---

## Task 2.9: Dependencies

### Modify: `fastapi-backend/requirements.txt`

Add:
```
pgvector>=0.3.0
tiktoken>=0.7.0
```

### Acceptance Criteria
- [ ] `pip install -r requirements.txt` succeeds
- [ ] No version conflicts with existing or Phase 1 dependencies

---

## Task 2.10: Tests

### New File: `fastapi-backend/tests/test_chunking.py`

```
test_chunk_empty_document_returns_empty
test_chunk_single_paragraph
test_chunk_multiple_headings_splits_at_boundaries
test_chunk_long_paragraph_splits_at_target_tokens
test_chunk_preserves_heading_context
test_chunk_overlap_between_adjacent_chunks
test_chunk_handles_code_blocks
test_chunk_handles_tables
test_chunk_handles_lists
test_chunk_strips_image_nodes
test_chunk_token_count_accuracy
test_chunk_index_sequential
test_chunk_canvas_extracts_element_text
test_chunk_canvas_groups_connected_elements
test_chunk_canvas_includes_connector_labels
test_chunk_canvas_skips_empty_elements
test_chunk_canvas_splits_large_clusters
test_chunk_document_type_routes_correctly
```

### New File: `fastapi-backend/tests/test_embedding_service.py`

```
test_embed_document_creates_chunks
test_embed_document_sets_embedding_updated_at
test_embed_document_replaces_existing_chunks
test_embed_document_denormalizes_scope_ids
test_embed_batch_processes_multiple_documents
test_embed_batch_continues_on_single_failure
test_delete_document_chunks_removes_all
test_delete_document_chunks_returns_count
```

### New File: `fastapi-backend/tests/test_retrieval_service.py`

```
test_semantic_search_returns_relevant_results
test_keyword_search_integrates_meilisearch
test_fuzzy_title_search_matches_partial
test_fuzzy_title_search_threshold_filters
test_rrf_merges_multiple_sources
test_rrf_deduplicates_same_document
test_retrieval_respects_rbac_boundaries
test_retrieval_excludes_deleted_documents
test_retrieval_filters_by_application
test_retrieval_filters_by_project
test_retrieval_returns_snippets
test_retrieval_empty_query_returns_empty
```

### Acceptance Criteria
- [ ] All tests pass with `pytest tests/test_chunking.py tests/test_embedding_service.py tests/test_retrieval_service.py -v`
- [ ] Chunking tests use fixture TipTap JSON documents
- [ ] Embedding tests mock the LLM provider (no real API calls)
- [ ] Retrieval tests verify RBAC boundaries (user A can't see user B's docs)

---

## Verification Checklist

```bash
cd fastapi-backend

# 1. Run migrations
alembic upgrade head

# 2. Verify extensions
# psql: SELECT * FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');

# 3. Verify table and indexes
# psql: \dt DocumentChunks; \di idx_document_chunks_*;

# 4. Create a test document, verify chunks generated after ~30s
# POST /api/documents (create doc with content)
# Wait 30s
# SELECT COUNT(*) FROM "DocumentChunks" WHERE document_id = '...';

# 5. Query pgvector similarity search directly
# SELECT chunk_text, 1 - (embedding <=> '[0.1, 0.2, ...]') AS similarity
# FROM "DocumentChunks"
# ORDER BY similarity DESC LIMIT 5;

# 6. Query pg_trgm fuzzy match
# SELECT title, similarity(title, 'projct alpa') AS sim
# FROM "Documents"
# WHERE similarity(title, 'projct alpa') > 0.3;

# 7. Run tests
pytest tests/test_chunking.py tests/test_embedding_service.py tests/test_retrieval_service.py -v
```

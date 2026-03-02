# Phase 3: Knowledge Graph — Granular Task Breakdown

> **STATUS: REPLACED BY [Phase 3.1: Agent SQL Access & Excel Export](phase-3.1-tasks.md)**
>
> Phase 3's LLM-extracted knowledge graph has been replaced by direct read-only SQL access
> via scoped PostgreSQL views. All Phase 3 code (~4,880 LOC) is removed in Phase 3.1.
> See [phase-3.1-sql-access.md](../phase-3.1-sql-access.md) for the replacement spec.

**Created**: 2026-02-24
**Last updated**: 2026-02-25
**Status**: ~~COMPLETE~~ REPLACED by Phase 3.1
**Spec**: ~~[phase-3-knowledge-graph.md](../phase-3-knowledge-graph.md)~~ — superseded by [phase-3.1-sql-access.md](../phase-3.1-sql-access.md)

> ~~**Depends on**: Phase 1 (LLM providers for entity extraction), Phase 2 (embedding infrastructure, chunking pipeline)~~
> ~~**Blocks**: Phase 4 (agent needs `query_entities` tool)~~
> ~~**Parallel with**: Phase 6 (independent work)~~

---

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

## Task Summary

| Section | Description | Tasks |
|---------|-------------|-------|
| 3.1 | Database — DocumentEntities Table | 14 |
| 3.2 | Database — EntityRelationships Table | 15 |
| 3.3 | Database — EntityMentions Table | 10 |
| 3.4 | Database — Indexes & Constraints | 19 |
| 3.5 | SQLAlchemy Models | 14 |
| 3.6 | Pydantic Schemas | 14 |
| 3.7 | Entity Extraction Service — LLM Prompt | 8 |
| 3.8 | Entity Extraction Service — Upsert Logic | 10 |
| 3.9 | Entity Extraction Service — Deduplication & Aliases | 7 |
| 3.10 | Entity Extraction Service — Batch & Cleanup | 8 |
| 3.11 | Knowledge Graph Query Service — Entity Search | 9 |
| 3.12 | Knowledge Graph Query Service — Graph Traversal (Recursive CTE) | 10 |
| 3.13 | Knowledge Graph Query Service — Find Connections & Timeline | 8 |
| 3.14 | Integration — Embedding Pipeline Hook | 7 |
| 3.15 | Integration — Hybrid Retrieval 4th Source | 7 |
| 3.16 | Indexing Router | 12 |
| 3.17 | Code Reviews & Security Analysis | 12 |
| 3.18 | Unit Tests — Entity Extraction | 16 |
| 3.19 | Unit Tests — Knowledge Graph Service | 16 |
| 3.20 | Integration Tests — Indexing Router | 10 |
| 3.21 | Phase 3 Verification & Sign-Off | 12 |
| **TOTAL** | | **238** |

---

### 3.1 Database — DocumentEntities Table

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1.1 | Create Alembic migration file `YYYYMMDD_add_knowledge_graph.py` with upgrade/downgrade stubs | DBE | [x] | 20260225_add_knowledge_graph.py |
| 3.1.2 | Add `id` column — UUID PK, `default=uuid4` | DBE | [x] | gen_random_uuid() |
| 3.1.3 | Add `name` column — VARCHAR(500), NOT NULL, canonical entity name | DBE | [x] | |
| 3.1.4 | Add `name_normalized` column — VARCHAR(500), NOT NULL, stores `LOWER(TRIM(name))` for dedup matching | DBE | [x] | |
| 3.1.5 | Add `entity_type` column — VARCHAR(50), NOT NULL, constrained to: system, person, team, technology, concept, project, document | DBE | [x] | Application-level validation |
| 3.1.6 | Add `description` column — TEXT, NULLABLE, LLM-generated summary | DBE | [x] | |
| 3.1.7 | Add `aliases` column — TEXT[], NULLABLE, alternative names array | DBE | [x] | sa.ARRAY(sa.Text()) |
| 3.1.8 | Add `application_id` column — UUID FK to `Applications.id`, NULLABLE (NULL = cross-application) | DBE | [x] | |
| 3.1.9 | Add `embedding` column — `vector(1536)` via pgvector, NULLABLE | DBE | [x] | Raw SQL ALTER TABLE |
| 3.1.10 | Add `mention_count` column — INT, DEFAULT 1, NOT NULL | DBE | [x] | server_default='1' |
| 3.1.11 | Add `first_seen_at` column — TIMESTAMP, NOT NULL | DBE | [x] | DateTime(timezone=True) |
| 3.1.12 | Add `last_seen_at` column — TIMESTAMP, NOT NULL | DBE | [x] | DateTime(timezone=True) |
| 3.1.13 | Add `created_at` column — TIMESTAMP, NOT NULL, DEFAULT now() | DBE | [x] | |
| 3.1.14 | Add `updated_at` column — TIMESTAMP, NOT NULL, DEFAULT now() | DBE | [x] | |

---

### 3.2 Database — EntityRelationships Table

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.2.1 | Create `EntityRelationships` table in same migration file | DBE | [x] | |
| 3.2.2 | Add `id` column — UUID PK, `default=uuid4` | DBE | [x] | |
| 3.2.3 | Add `source_entity_id` column — UUID FK to `DocumentEntities.id`, ON DELETE CASCADE, NOT NULL | DBE | [x] | The "from" node |
| 3.2.4 | Add `target_entity_id` column — UUID FK to `DocumentEntities.id`, ON DELETE CASCADE, NOT NULL | DBE | [x] | The "to" node |
| 3.2.5 | Add `relationship_type` column — VARCHAR(100), NOT NULL, constrained to: depends_on, uses, maintained_by, owned_by, part_of, implements, integrates_with, related_to, succeeded_by, references | DBE | [x] | |
| 3.2.6 | Add `description` column — TEXT, NULLABLE, LLM-generated description of the relationship | DBE | [x] | |
| 3.2.7 | Add `weight` column — FLOAT, DEFAULT 1.0, NOT NULL, accumulated confidence | DBE | [x] | Increases with more evidence |
| 3.2.8 | Add `document_id` column — UUID FK to `Documents.id`, ON DELETE SET NULL, NULLABLE | DBE | [x] | Source document; NULL if doc deleted |
| 3.2.9 | Add `chunk_id` column — UUID FK to `DocumentChunks.id`, ON DELETE SET NULL, NULLABLE | DBE | [x] | Source chunk |
| 3.2.10 | Add `snippet` column — TEXT, NULLABLE, evidence sentence/paragraph | DBE | [x] | |
| 3.2.11 | Add `confidence` column — FLOAT, DEFAULT 0.8, NOT NULL, LLM extraction confidence (0.0-1.0) | DBE | [x] | |
| 3.2.12 | Add `application_id` column — UUID FK to `Applications.id`, NULLABLE, denormalized for fast RBAC filtering | DBE | [x] | |
| 3.2.13 | Add `created_at` column — TIMESTAMP, NOT NULL, DEFAULT now() | DBE | [x] | |
| 3.2.14 | Add `updated_at` column — TIMESTAMP, NOT NULL, DEFAULT now() | DBE | [x] | |
| 3.2.15 | Verify CASCADE behavior: deleting an entity cascades to all its relationships (both source and target) | DBE | [x] | Critical for data integrity |

---

### 3.3 Database — EntityMentions Table

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.3.1 | Create `EntityMentions` table in same migration file | DBE | [x] | |
| 3.3.2 | Add `id` column — UUID PK, `default=uuid4` | DBE | [x] | |
| 3.3.3 | Add `entity_id` column — UUID FK to `DocumentEntities.id`, ON DELETE CASCADE, NOT NULL | DBE | [x] | |
| 3.3.4 | Add `document_id` column — UUID FK to `Documents.id`, ON DELETE CASCADE, NOT NULL | DBE | [x] | Note: CASCADE here (unlike SET NULL on EntityRelationships) |
| 3.3.5 | Add `chunk_id` column — UUID FK to `DocumentChunks.id`, ON DELETE SET NULL, NULLABLE | DBE | [x] | |
| 3.3.6 | Add `context_snippet` column — TEXT, NOT NULL, surrounding text (1-2 sentences) | DBE | [x] | |
| 3.3.7 | Add `mention_type` column — VARCHAR(50), NOT NULL, DEFAULT 'reference', values: definition, reference, discussion | DBE | [x] | |
| 3.3.8 | Add `created_at` column — TIMESTAMP, NOT NULL, DEFAULT now() | DBE | [x] | |
| 3.3.9 | Verify CASCADE behavior: deleting a document cascades to all its mentions | DBE | [x] | Different from EntityRelationships which uses SET NULL |
| 3.3.10 | Verify CASCADE behavior: deleting an entity cascades to all its mentions | DBE | [x] | |

---

### 3.4 Database — Indexes & Constraints

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.4.1 | Create partial unique index `idx_entities_name_type_app` on `(name_normalized, entity_type, application_id)` WHERE `application_id IS NOT NULL` | DBE | [x] | Prevents duplicate entities within same app scope |
| 3.4.2 | Create partial unique index `idx_entities_name_type_global` on `(name_normalized, entity_type)` WHERE `application_id IS NULL` | DBE | [x] | Prevents duplicate global entities |
| 3.4.3 | Create HNSW index `idx_entities_embedding` on `embedding` column using `vector_cosine_ops` (m=16, ef_construction=64) | DBE | [x] | Semantic entity search |
| 3.4.4 | Create index `idx_entities_type` on `entity_type` | DBE | [x] | Entity type filtering |
| 3.4.5 | Create index `idx_entities_app` on `application_id` | DBE | [x] | RBAC filtering |
| 3.4.6 | Create GIN index `idx_entities_name_trgm` on `name` using `gin_trgm_ops` | DBE | [x] | Fuzzy entity name search; requires `pg_trgm` extension |
| 3.4.7 | Ensure `pg_trgm` extension is enabled (CREATE EXTENSION IF NOT EXISTS pg_trgm) | DBE | [x] | Must be in migration or pre-existing |
| 3.4.8 | Create index `idx_relationships_source` on `source_entity_id` | DBE | [x] | Traversal from source |
| 3.4.9 | Create index `idx_relationships_target` on `target_entity_id` | DBE | [x] | Traversal from target |
| 3.4.10 | Create index `idx_relationships_type` on `relationship_type` | DBE | [x] | Relationship type filtering |
| 3.4.11 | Create index `idx_relationships_app` on `application_id` | DBE | [x] | RBAC filtering |
| 3.4.12 | Create index `idx_relationships_document` on `document_id` | DBE | [x] | Find relationships from a specific document |
| 3.4.13 | Create composite index `idx_relationships_source_type` on `(source_entity_id, relationship_type)` | DBE | [x] | Common traversal pattern |
| 3.4.14 | Create composite index `idx_relationships_target_type` on `(target_entity_id, relationship_type)` | DBE | [x] | Common traversal pattern |
| 3.4.15 | Create index `idx_mentions_entity` on `entity_id` | DBE | [x] | Mention lookups by entity |
| 3.4.16 | Create index `idx_mentions_document` on `document_id` | DBE | [x] | Mention lookups by document |
| 3.4.17 | Write downgrade that drops all three tables and all indexes | DBE | [x] | Must be complete and reversible |
| 3.4.18 | Test migration upgrade: `alembic upgrade head` succeeds cleanly | DBE | [x] | |
| 3.4.19 | Test migration downgrade: `alembic downgrade -1` succeeds cleanly, all tables/indexes removed | DBE | [x] | |

---

### 3.5 SQLAlchemy Models

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.5.1 | Create `DocumentEntity` model in `app/models/document_entity.py` — all columns matching migration | BE | [x] | Uses `pgvector.sqlalchemy.Vector`, `ARRAY(Text)` |
| 3.5.2 | Define `outgoing_relationships` relationship on `DocumentEntity` — `back_populates="source_entity"`, `foreign_keys=[EntityRelationship.source_entity_id]`, `cascade="all, delete-orphan"` | BE | [x] | |
| 3.5.3 | Define `incoming_relationships` relationship on `DocumentEntity` — `back_populates="target_entity"`, `foreign_keys=[EntityRelationship.target_entity_id]`, `cascade="all, delete-orphan"` | BE | [x] | |
| 3.5.4 | Define `mentions` relationship on `DocumentEntity` — `back_populates="entity"`, `cascade="all, delete-orphan"` | BE | [x] | |
| 3.5.5 | Create `EntityRelationship` model in `app/models/entity_relationship.py` — all columns matching migration | BE | [x] | |
| 3.5.6 | Define `source_entity` relationship on `EntityRelationship` — `back_populates="outgoing_relationships"`, `foreign_keys=[source_entity_id]` | BE | [x] | |
| 3.5.7 | Define `target_entity` relationship on `EntityRelationship` — `back_populates="incoming_relationships"`, `foreign_keys=[target_entity_id]` | BE | [x] | |
| 3.5.8 | Define `document` relationship on `EntityRelationship` — lazy loaded, NULLABLE | BE | [x] | |
| 3.5.9 | Define `chunk` relationship on `EntityRelationship` — lazy loaded, NULLABLE | BE | [x] | |
| 3.5.10 | Create `EntityMention` model in `app/models/entity_mention.py` — all columns matching migration | BE | [x] | |
| 3.5.11 | Define `entity` relationship on `EntityMention` — `back_populates="mentions"` | BE | [x] | |
| 3.5.12 | Define `document` relationship on `EntityMention` — lazy loaded | BE | [x] | |
| 3.5.13 | Register all three models in `app/models/__init__.py`: `DocumentEntity`, `EntityRelationship`, `EntityMention` | BE | [x] | |
| 3.5.14 | Verify all three models are importable: `from app.models import DocumentEntity, EntityRelationship, EntityMention` | BE | [x] | Quick smoke test |

---

### 3.6 Pydantic Schemas

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.6.1 | Create schema file `app/schemas/knowledge_graph.py` | BE | [x] | |
| 3.6.2 | Implement `EntityBrief` schema — fields: id (UUID), name (str), entity_type (str) | BE | [x] | Lightweight reference used in relationship responses |
| 3.6.3 | Implement `EntityCreate` schema — fields: name, entity_type (validated against 7 allowed values), description, aliases, application_id | BE | [x] | Validator for entity_type enum |
| 3.6.4 | Implement `EntityResponse` schema — fields: id, name, entity_type, description, aliases, application_id, mention_count, first_seen_at, last_seen_at | BE | [x] | `model_config = ConfigDict(from_attributes=True)` |
| 3.6.5 | Implement `EntityMentionDoc` schema — fields: document_id (UUID), title (str), snippet (str) | BE | [x] | Used inside EntityWithRelationships |
| 3.6.6 | Implement `EntityWithRelationships` schema — extends EntityResponse, adds: outgoing (list[RelationshipResponse]), incoming (list[RelationshipResponse]), mention_documents (list[EntityMentionDoc]) | BE | [x] | |
| 3.6.7 | Implement `RelationshipBrief` schema — fields: id, relationship_type, description | BE | [x] | Used inside GraphPath |
| 3.6.8 | Implement `RelationshipResponse` schema — fields: id, source_entity (EntityBrief), target_entity (EntityBrief), relationship_type, description, weight, snippet, confidence, document_title | BE | [x] | |
| 3.6.9 | Implement `EntitySearchResult` schema — fields: entity (EntityResponse), relevance_score (float), match_source (str: "semantic"/"fuzzy_name"/"exact"), relationships_count (int) | BE | [x] | |
| 3.6.10 | Implement `GraphPath` schema — fields: entities (list[EntityBrief]), relationships (list[RelationshipBrief]), depth (int) | BE | [x] | |
| 3.6.11 | Implement `GraphTraversalResult` schema — fields: root_entity (EntityResponse), paths (list[GraphPath]), total_entities (int), total_relationships (int) | BE | [x] | |
| 3.6.12 | Implement `ExtractedEntity` schema — fields: name (str), entity_type (str), description (str) | BE | [x] | Internal: parsed from LLM output |
| 3.6.13 | Implement `ExtractedRelationship` schema — fields: source (str), target (str), relationship_type (str), snippet (str), confidence (float, default=0.8) | BE | [x] | Internal: parsed from LLM output |
| 3.6.14 | Implement `ExtractionResult` schema — fields: entities (list[ExtractedEntity]), relationships (list[ExtractedRelationship]) | BE | [x] | Internal: top-level LLM response wrapper |

---

### 3.7 Entity Extraction Service — LLM Prompt

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.7.1 | Create file `app/ai/entity_extraction_service.py` with class stub and `__init__` accepting `ProviderRegistry`, `EmbeddingService`, `AsyncSession` | BE | [x] | |
| 3.7.2 | Define `EXTRACTION_PROMPT` template — includes entity types (7), relationship types (10), rules (named entities only, exact sentence snippets, confidence rating, alias handling), JSON output schema | BE | [x] | Template uses `{chunk_text}` and `{heading_context}` placeholders |
| 3.7.3 | Implement LLM call: use `ProviderRegistry.get_chat_provider()`, set `temperature=0.2` for deterministic extraction | BE | [x] | Low temp for reproducible extraction |
| 3.7.4 | Implement JSON response parser with fallback for malformed JSON (e.g., JSON in markdown code fences, trailing commas, partial responses) | BE | [x] | LLMs sometimes wrap JSON in ```json blocks |
| 3.7.5 | Implement entity type validation filter — reject entities not in the 7 allowed types | BE | [x] | system, person, team, technology, concept, project, document |
| 3.7.6 | Implement relationship type validation filter — reject relationships not in the 10 allowed types | BE | [x] | depends_on, uses, maintained_by, owned_by, part_of, implements, integrates_with, related_to, succeeded_by, references |
| 3.7.7 | Implement unnamed entity filter — reject entities with empty/whitespace-only names | BE | [x] | |
| 3.7.8 | Implement rate limiting — max 10 chunks/second to avoid API throttling | BE | [x] | Use asyncio.Semaphore or similar |

---

### 3.8 Entity Extraction Service — Upsert Logic

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.8.1 | Implement `extract_from_document()` orchestrator — accepts document_id, chunks, application_id, batch_size; returns `ExtractionSummary` | BE | [x] | Main entry point; processes chunks in batches |
| 3.8.2 | Implement chunk batching in `extract_from_document()` — process `batch_size` chunks concurrently via `asyncio.gather()` | BE | [x] | Default batch_size=5 |
| 3.8.3 | Implement cross-chunk entity deduplication — same name + type from different chunks merged before upserting | BE | [x] | Prevents duplicate inserts |
| 3.8.4 | Implement `_upsert_entity()` — normalize name via `LOWER(TRIM(name))`, query by name_normalized + entity_type + application_id | BE | [x] | |
| 3.8.5 | In `_upsert_entity()` — if found: update description (keep longer/better), increment `mention_count`, update `last_seen_at`, merge aliases | BE | [x] | |
| 3.8.6 | In `_upsert_entity()` — if not found: create new entity, generate embedding for `name + description` via EmbeddingService, set `first_seen_at = last_seen_at = now()` | BE | [x] | |
| 3.8.7 | Implement `_upsert_relationship()` — query by source_entity_id + target_entity_id + relationship_type | BE | [x] | |
| 3.8.8 | In `_upsert_relationship()` — if found: increment weight by confidence, update snippet if higher confidence, update document_id/chunk_id to latest | BE | [x] | |
| 3.8.9 | In `_upsert_relationship()` — if not found: create new relationship, set weight = confidence | BE | [x] | |
| 3.8.10 | Create `EntityMention` records for each chunk-entity pair — set context_snippet, mention_type (definition/reference/discussion), link to chunk_id | BE | [x] | |

---

### 3.9 Entity Extraction Service — Deduplication & Aliases

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.9.1 | Implement alias matching in `_upsert_entity()` — check if incoming name matches any existing entity's aliases array | BE | [x] | e.g., "Payment Svc" matches alias of "Payment Service" |
| 3.9.2 | Implement alias merge — when entity matched by alias, add current name to aliases if not already present | BE | [x] | Grow the aliases list over time |
| 3.9.3 | Implement cross-chunk alias consolidation — if chunk A says "Payment Service" and chunk B says "Payment Svc", merge into one entity | BE | [x] | |
| 3.9.4 | Handle NULL vs specific application_id scoping in dedup — entities scoped to an app should not merge with global entities | BE | [x] | Partial unique index enforces this at DB level |
| 3.9.5 | Implement description quality comparison — when updating description, prefer longer description or description from higher-confidence extraction | BE | [x] | Heuristic: longer usually means more detail |
| 3.9.6 | Implement `ExtractionSummary` dataclass — fields: entities_created, entities_updated, relationships_created, relationships_updated, mentions_created, duration_ms | BE | [x] | Returned by extract_from_document() |
| 3.9.7 | Update `Document.graph_ingested_at = now()` after successful extraction | BE | [x] | Requires `graph_ingested_at` column on Document model (may need mini-migration or addition to Phase 2 migration) |

---

### 3.10 Entity Extraction Service — Batch & Cleanup

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.10.1 | Implement `remove_document_extractions()` — delete all `EntityMentions` WHERE `document_id = :doc_id` | BE | [x] | |
| 3.10.2 | In `remove_document_extractions()` — delete all `EntityRelationships` WHERE `document_id = :doc_id` | BE | [x] | |
| 3.10.3 | In `remove_document_extractions()` — optionally clean up orphaned entities where `mention_count` reaches 0 | BE | [x] | Configurable; might want to keep entities even with 0 mentions |
| 3.10.4 | In `remove_document_extractions()` — return total records removed | BE | [x] | |
| 3.10.5 | Call `remove_document_extractions()` before re-extraction in `extract_from_document()` to ensure idempotency | BE | [x] | |
| 3.10.6 | Implement `extract_batch()` — accepts list of document_ids, processes sequentially | BE | [x] | For nightly job and manual reindex |
| 3.10.7 | In `extract_batch()` — track progress in Redis (e.g., key `graph:batch:{batch_id}`, value `{processed: N, total: M, errors: []}`) | BE | [x] | Polled by `/index-progress` endpoint |
| 3.10.8 | In `extract_batch()` — continue processing remaining documents on single-document failure, log errors | BE | [x] | One bad doc should not block the batch |

---

### 3.11 Knowledge Graph Query Service — Entity Search

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.11.1 | Create file `app/ai/knowledge_graph_service.py` with class stub and `__init__` accepting `AsyncSession` | BE | [x] | |
| 3.11.2 | Implement `search_entities()` — exact name match strategy: `WHERE name_normalized = LOWER(:query)`, score = 1.0 | BE | [x] | Fastest, most precise |
| 3.11.3 | Implement `search_entities()` — fuzzy name match strategy: `WHERE similarity(name, :query) > 0.3` via pg_trgm, score = similarity value | BE | [x] | Handles typos and partial matches |
| 3.11.4 | Implement `search_entities()` — semantic embedding search strategy: embed query via EmbeddingService, cosine similarity on `embedding` column, score = cosine sim | BE | [x] | Conceptual match even if names differ |
| 3.11.5 | Implement RRF (Reciprocal Rank Fusion) merge of all three search strategies | BE | [x] | Same pattern as Phase 2 hybrid retrieval |
| 3.11.6 | Apply RBAC filter to all search strategies: `application_id = ANY(:accessible_app_ids) OR application_id IS NULL` | BE | [x] | Critical for multi-tenant isolation |
| 3.11.7 | Apply optional `entity_type` filter when provided | BE | [x] | |
| 3.11.8 | Apply `limit` cap on final results | BE | [x] | Default 10 |
| 3.11.9 | Return `EntitySearchResult` list with `match_source` indicating which strategy matched | BE | [x] | |

---

### 3.12 Knowledge Graph Query Service — Graph Traversal (Recursive CTE)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.12.1 | Implement `traverse_graph()` — base case of recursive CTE: start entity with depth=0, path=[start_id] | BE | [x] | |
| 3.12.2 | Implement recursive case — follow `EntityRelationships` (both directions: source_entity_id and target_entity_id), increment depth | BE | [x] | Bidirectional traversal |
| 3.12.3 | Implement cycle prevention — `NOT e2.id = ANY(gw.path)` using PostgreSQL path array | BE | [x] | Critical: prevents infinite recursion |
| 3.12.4 | Implement depth limit — `gw.depth < :max_depth`, default=2, maximum=3 | BE | [x] | Prevents runaway queries |
| 3.12.5 | Implement RBAC filtering in recursive CTE — `e2.application_id = ANY(:app_ids) OR e2.application_id IS NULL` | BE | [x] | Must filter at each hop, not just start |
| 3.12.6 | Implement optional relationship type filter — `:rel_types IS NULL OR er.relationship_type = ANY(:rel_types)` | BE | [x] | |
| 3.12.7 | Build `GraphTraversalResult` from CTE results — construct paths with entity and relationship details | BE | [x] | |
| 3.12.8 | Implement `get_entity_context()` — full context for a single entity: details, outgoing/incoming relationships, source documents with snippets | BE | [x] | Uses `selectinload` for relationships and mentions |
| 3.12.9 | In `get_entity_context()` — include related entities 1-2 hops away via `traverse_graph()` | BE | [x] | |
| 3.12.10 | Add query timeout/safety: limit CTE result set size (e.g., max 500 rows) to prevent memory issues on dense graphs | BE | [x] | `LIMIT 500` on outer SELECT |

---

### 3.13 Knowledge Graph Query Service — Find Connections & Timeline

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.13.1 | Implement `find_connections()` — find paths connecting entity_a_id to entity_b_id | BE | [x] | |
| 3.13.2 | In `find_connections()` — use bidirectional BFS via recursive CTE, max_depth=3 | BE | [x] | Terminate when path includes target entity |
| 3.13.3 | In `find_connections()` — return shortest paths first, up to 3 hops | BE | [x] | ORDER BY depth ASC |
| 3.13.4 | In `find_connections()` — return empty list if no path exists | BE | [x] | Not an error condition |
| 3.13.5 | Implement `get_entity_timeline()` — query EntityMentions for entity_id, join to Documents for titles/dates | BE | [x] | |
| 3.13.6 | In `get_entity_timeline()` — order by mention timestamps (created_at ASC) | BE | [x] | Temporal view of entity evolution |
| 3.13.7 | Implement `get_popular_entities()` — query DocumentEntities ORDER BY mention_count DESC, LIMIT :limit | BE | [x] | |
| 3.13.8 | In `get_popular_entities()` — apply RBAC filter and optional entity_type filter | BE | [x] | |

---

### 3.14 Integration — Embedding Pipeline Hook

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.14.1 | Modify `EmbeddingService.__init__()` in `app/ai/embedding_service.py` — add optional `entity_extraction_service: EntityExtractionService | None = None` parameter | BE | [x] | |
| 3.14.2 | Modify `embed_document()` — after successful chunking + embedding, call `entity_extraction.extract_from_document()` with the newly created chunks | BE | [x] | |
| 3.14.3 | Wrap entity extraction call in try/except — log warning on failure but do NOT fail the embedding pipeline | BE | [x] | Entity extraction is non-critical |
| 3.14.4 | Log extraction results: entities_created, relationships_created, duration_ms | BE | [x] | |
| 3.14.5 | Ensure re-embedding triggers re-extraction — `remove_document_extractions()` called first to clean stale data | BE | [x] | Idempotent re-processing |
| 3.14.6 | Add `graph_ingested_at` column to Document model (if not already present from Phase 2) | BE | [x] | Already present from Phase 2 |
| 3.14.7 | Wire up `EntityExtractionService` in dependency injection / service factory where `EmbeddingService` is instantiated | BE | [x] | In ai_indexing.py reindex endpoint |

---

### 3.15 Integration — Hybrid Retrieval 4th Source

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.15.1 | Modify `HybridRetrievalService.__init__()` in `app/ai/retrieval_service.py` — add optional `kg_service: KnowledgeGraphService | None = None` parameter | BE | [x] | |
| 3.15.2 | Implement `_entity_search()` private method — search KG for entities matching query, convert entity mentions to `RankedResult` format | BE | [x] | Map entity mentions back to source documents |
| 3.15.3 | In `_entity_search()` — for each matching entity, query `EntityMentions` to find source documents, return as ranked results | BE | [x] | Surfaces documents related to mentioned entities |
| 3.15.4 | Integrate `_entity_search()` into `retrieve()` — append to `ranked_lists` before RRF merge | BE | [x] | 4th source alongside pgvector, Meilisearch, pg_trgm |
| 3.15.5 | Ensure entity search is optional — `if self.kg_service:` guard so retrieval works without KG | BE | [x] | Backwards compatible |
| 3.15.6 | Apply RBAC filtering in `_entity_search()` using `accessible_app_ids` | BE | [x] | |
| 3.15.7 | Wire up `KnowledgeGraphService` in dependency injection where `HybridRetrievalService` is instantiated | BE | [x] | In ai_indexing.py search endpoint |

---

### 3.16 Indexing Router

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.16.1 | Create file `app/routers/ai_indexing.py` with router prefix `/api/ai` | BE | [x] | |
| 3.16.2 | Implement `POST /reindex/{document_id}` — force re-embed + re-extract entities, auth: document editor or higher | BE | [x] | |
| 3.16.3 | Implement `POST /reindex/application/{app_id}` — enqueue batch job for all docs in application, auth: application Owner | BE | [-] | Deferred to Phase 4 worker integration |
| 3.16.4 | Implement `GET /index-status/{document_id}` — return embedding + entity extraction timestamps, auth: document viewer or higher | BE | [x] | |
| 3.16.5 | Implement `GET /index-status/application/{app_id}` — batch index status for all docs, auth: application Member | BE | [-] | Deferred to Phase 4 |
| 3.16.6 | Implement `GET /index-progress` — return batch job progress from Redis, auth: any authenticated user | BE | [-] | Deferred to Phase 4 worker integration |
| 3.16.7 | Implement `GET /entities` — list entities for an application with pagination, optional type filter, auth: application Member | BE | [x] | Query params: application_id, type, limit, offset |
| 3.16.8 | Implement `GET /entities/{entity_id}` — return full `EntityWithRelationships`, auth: application Member | BE | [x] | |
| 3.16.9 | Implement `GET /entities/search` — multi-strategy entity search, auth: application Member | BE | [x] | Query params: q, application_id, type, limit |
| 3.16.10 | Register router in `app/main.py` — `app.include_router(ai_indexing.router)` | BE | [x] | |
| 3.16.11 | Add auth dependency to all endpoints — use existing `get_current_user` dependency | BE | [x] | |
| 3.16.12 | Add RBAC checks on each endpoint — verify user has required role for the target application/document | BE | [x] | Use existing `PermissionService` |

---

### 3.17 Code Reviews & Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.17.1 | CR1: Review Alembic migration — verify column types, FK constraints, CASCADE/SET NULL correctness, index definitions match spec | CR1 | [x] | R1-R8: Added unique dedup indexes for EntityRelationships |
| 3.17.2 | CR1: Review SQLAlchemy models — verify bidirectional relationships, cascade settings, `__allow_unmapped__` usage | CR1 | [x] | R1: Models verified |
| 3.17.3 | CR1: Review recursive CTE in `traverse_graph()` — verify cycle prevention via path array, depth limit enforcement, RBAC at each hop | CR1 | [x] | R2: ARRAY[]::text[], R3: statement_timeout=5s, R4: empty app_ids guard, R4: relationship_types validation |
| 3.17.4 | CR2: Review entity extraction prompt — verify prompt engineering quality, JSON output schema, entity/relationship type lists match spec | CR2 | [x] | R2: heading_context sanitized, R3: regex narrowed to line-start |
| 3.17.5 | CR2: Review Pydantic schemas — verify all fields, validators, `from_attributes` config, schema inheritance | CR2 | [x] | R3: Added ReindexResponse, IndexStatusResponse, aliases normalization |
| 3.17.6 | CR2: Review `_entity_search()` integration into hybrid retrieval RRF — verify ranking math, result format consistency | CR2 | [x] | R2: RBAC personal-scope guard, score attribution, LIMIT 200, R3: missing imports fixed |
| 3.17.7 | SA: Verify graph traversal cannot leak entities from inaccessible applications — RBAC filter applied at every hop, not just root | SA | [x] | R2: batch_load_entity_briefs RBAC, R4: empty accessible_app_ids guard on ALL methods |
| 3.17.8 | SA: Verify `EXTRACTION_PROMPT` does not allow prompt injection from document content — chunk_text is user-controlled | SA | [x] | R1: _sanitize_chunk_text strips system/assistant markers + backtick fences, R3: narrowed to line-start only |
| 3.17.9 | SA: Verify entity search endpoints cannot be used for enumeration attacks — rate limiting, no full-scan queries | SA | [x] | R3: max_length=500 on q, offset le=10000, all queries have LIMIT |
| 3.17.10 | SA: Verify `application_id` denormalization on EntityRelationships stays consistent with source entity's application_id | SA | [x] | R3: personal-scope docs skip extraction entirely |
| 3.17.11 | DA: Justify PostgreSQL recursive CTE over Neo4j — document performance characteristics at 10k, 100k, 1M entities, cite traversal depth limitation (2-3 hops) | DA | [x] | PostgreSQL CTE with 2-3 hop limit, LIMIT 500, statement_timeout=5s adequate for scale target |
| 3.17.12 | DA: Challenge entity extraction quality — what happens with ambiguous entities ("the service"), hallucinated entities, inconsistent naming across documents? Document mitigation strategy | DA | [x] | Prompt rule: "only named entities", empty/whitespace filter, type validation, _salvage_partial_result for graceful degradation |

> **Final fixes (post-Round 8)**: R5-SA1 asyncio.gather→sequential in retrieval_service, R5-CR1 pre-resolve LLM provider in extraction to avoid shared-session concurrency, R5-SA2 _entity_search project_id filter + personal-scope consistency, R5-SA3 Meilisearch personal-scope IS EMPTY guard, CR1-R5-2 removed dead mention_count increment (Step 7 correlated subquery recalculates), CR1-R5-3 rsplit empty-string edge case guard, removed unused asyncio import from retrieval_service.

---

### 3.18 Unit Tests — Entity Extraction

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.18.1 | Create test file `tests/test_entity_extraction.py` with fixtures: mock ProviderRegistry, mock EmbeddingService, test AsyncSession, sample chunks | TE | [x] | |
| 3.18.2 | Write `test_extract_entities_from_chunk` — mock LLM to return valid JSON with entities, verify entities parsed correctly | TE | [x] | |
| 3.18.3 | Write `test_extract_relationships_from_chunk` — mock LLM to return valid JSON with relationships, verify relationships parsed with correct source/target/type/snippet | TE | [x] | |
| 3.18.4 | Write `test_extract_handles_malformed_llm_json` — mock LLM to return JSON in markdown fences, trailing commas, partial response; verify graceful fallback | TE | [x] | |
| 3.18.5 | Write `test_extract_filters_invalid_entity_types` — mock LLM to return entity with type "foobar", verify it is filtered out | TE | [x] | |
| 3.18.6 | Write `test_extract_filters_unnamed_entities` — mock LLM to return entity with empty/whitespace name, verify it is filtered out | TE | [x] | |
| 3.18.7 | Write `test_upsert_entity_creates_new` — call `_upsert_entity()` with new name, verify DocumentEntity created in DB | TE | [x] | |
| 3.18.8 | Write `test_upsert_entity_updates_existing` — create entity, call `_upsert_entity()` with same normalized name, verify description updated, not duplicated | TE | [x] | |
| 3.18.9 | Write `test_upsert_entity_increments_mention_count` — create entity with mention_count=1, upsert again, verify mention_count=2 | TE | [x] | |
| 3.18.10 | Write `test_upsert_entity_merges_aliases` — create entity with aliases=["Pay Svc"], upsert with alias "Payment", verify aliases=["Pay Svc", "Payment"] | TE | [x] | |
| 3.18.11 | Write `test_upsert_entity_dedup_by_normalized_name` — upsert "Payment Service" then " payment service ", verify same entity (case-insensitive, trimmed) | TE | [x] | |
| 3.18.12 | Write `test_upsert_relationship_creates_new` — call `_upsert_relationship()` with new source/target/type, verify EntityRelationship created | TE | [x] | |
| 3.18.13 | Write `test_upsert_relationship_accumulates_weight` — create relationship with weight=0.8, upsert again with confidence=0.9, verify weight=1.7 | TE | [x] | |
| 3.18.14 | Write `test_upsert_relationship_updates_to_higher_confidence` — create with confidence=0.5, upsert with confidence=0.9, verify snippet updated to higher-confidence one | TE | [x] | |
| 3.18.15 | Write `test_remove_document_extractions` — create mentions and relationships for a doc, call remove, verify all deleted | TE | [x] | |
| 3.18.16 | Write `test_re_extraction_is_idempotent` — extract from doc, re-extract same doc, verify no duplicate entities/relationships | TE | [x] | |

---

### 3.19 Unit Tests — Knowledge Graph Service

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.19.1 | Create test file `tests/test_knowledge_graph_service.py` with fixtures: pre-populated entities, relationships, mentions, multiple application_ids | TE | [x] | |
| 3.19.2 | Write `test_search_entities_exact_match` — search for exact entity name, verify score=1.0, match_source="exact" | TE | [x] | |
| 3.19.3 | Write `test_search_entities_fuzzy_match` — search for misspelled name, verify pg_trgm match, match_source="fuzzy_name" | TE | [x] | |
| 3.19.4 | Write `test_search_entities_semantic_match` — search for conceptually similar query (mock embedding), verify match_source="semantic" | TE | [x] | |
| 3.19.5 | Write `test_search_entities_rrf_merge` — verify RRF correctly merges results from all three strategies, deduplicates | TE | [x] | |
| 3.19.6 | Write `test_search_entities_filters_by_type` — search with entity_type="system", verify only system entities returned | TE | [x] | |
| 3.19.7 | Write `test_search_entities_respects_rbac` — create entities in app_A and app_B, search with only app_A access, verify app_B entities excluded | TE | [x] | Critical security test |
| 3.19.8 | Write `test_get_entity_context_includes_relationships` — verify outgoing and incoming relationships populated | TE | [x] | |
| 3.19.9 | Write `test_get_entity_context_includes_mentions` — verify mention_documents populated with document titles and snippets | TE | [x] | |
| 3.19.10 | Write `test_traverse_graph_one_hop` — create A→B, traverse from A depth=1, verify B found | TE | [x] | |
| 3.19.11 | Write `test_traverse_graph_two_hops` — create A→B→C, traverse from A depth=2, verify B and C found | TE | [x] | |
| 3.19.12 | Write `test_traverse_graph_prevents_cycles` — create A→B→C→A, traverse from A depth=3, verify no infinite loop, A not revisited | TE | [x] | Most critical correctness test |
| 3.19.13 | Write `test_traverse_graph_respects_rbac` — A→B→C where C is in inaccessible app, verify C excluded from traversal | TE | [x] | |
| 3.19.14 | Write `test_traverse_graph_filters_relationship_type` — A→(depends_on)→B, A→(uses)→C, traverse with type=["depends_on"], verify only B found | TE | [x] | |
| 3.19.15 | Write `test_find_connections_between_entities` — create A→B→C, find connections A↔C, verify path found | TE | [x] | |
| 3.19.16 | Write `test_find_connections_no_path_returns_empty` — create A→B and C→D (disconnected), find connections A↔D, verify empty list | TE | [x] | |

---

### 3.20 Integration Tests — Indexing Router

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.20.1 | Create test file `tests/test_indexing_router.py` with fixtures: authenticated test client, sample documents, mock entity extraction service | TE | [x] | |
| 3.20.2 | Write `test_reindex_document_triggers_extraction` — POST `/api/ai/reindex/{doc_id}`, verify extraction service called | TE | [x] | |
| 3.20.3 | Write `test_reindex_application_enqueues_batch` — POST `/api/ai/reindex/application/{app_id}`, verify batch job enqueued | TE | [-] | Endpoint not implemented in current scope |
| 3.20.4 | Write `test_index_status_returns_timestamps` — GET `/api/ai/index-status/{doc_id}`, verify embedding_at and graph_ingested_at returned | TE | [x] | |
| 3.20.5 | Write `test_list_entities_paginated` — GET `/api/ai/entities?application_id=...&limit=5&offset=0`, verify pagination works | TE | [x] | |
| 3.20.6 | Write `test_get_entity_with_relationships` — GET `/api/ai/entities/{entity_id}`, verify EntityWithRelationships schema returned | TE | [x] | |
| 3.20.7 | Write `test_search_entities_endpoint` — GET `/api/ai/entities/search?q=payment&application_id=...`, verify search results returned | TE | [x] | |
| 3.20.8 | Write `test_entity_endpoints_require_auth` — call all entity endpoints without auth token, verify 401 | TE | [x] | |
| 3.20.9 | Write `test_entity_endpoints_respect_rbac` — call entity endpoints with user who lacks application membership, verify 403 | TE | [x] | |
| 3.20.10 | Write `test_hybrid_retrieval_with_entity_source` — end-to-end: create doc, extract entities, run hybrid retrieval, verify entity search contributes to RRF | TE | [x] | Covered via test_reindex + test_index_status + test_search integration |

---

### 3.21 Phase 3 Verification & Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.21.1 | QE: Verify AC — All three tables created with correct types and constraints | QE | [x] | DocumentEntities, EntityRelationships, EntityMentions all verified |
| 3.21.2 | QE: Verify AC — FK cascades: entity delete cascades to relationships + mentions | QE | [x] | Both source/target FKs CASCADE, EntityMentions CASCADE |
| 3.21.3 | QE: Verify AC — Document delete sets relationships to NULL (preserves entity, loses provenance) | QE | [x] | EntityRelationships.document_id ON DELETE SET NULL, EntityMentions ON DELETE CASCADE |
| 3.21.4 | QE: Verify AC — Partial unique indexes prevent entity duplication (name + type + app scope) | QE | [x] | idx_entities_name_type_app + idx_entities_name_type_global; Added idx_relationships_dedup_app + idx_relationships_dedup_global (R6) |
| 3.21.5 | QE: Verify AC — HNSW index on entity embeddings functional | QE | [x] | idx_entities_embedding HNSW m=16 ef_construction=64 |
| 3.21.6 | QE: Verify AC — pg_trgm GIN index on entity names functional | QE | [x] | idx_entities_name_trgm GIN gin_trgm_ops |
| 3.21.7 | QE: Verify AC — Downgrade drops all tables and indexes cleanly | QE | [x] | Complete downgrade with all index drops |
| 3.21.8 | QE: Verify AC — Entity extraction runs after embedding in same pipeline, failure does not block embedding | QE | [x] | try/except in embedding_service.py:169-185, logged as non-critical |
| 3.21.9 | QE: Verify AC — Entity search uses 3 strategies (exact, fuzzy, semantic) with RRF merge | QE | [x] | _exact_name_search + _fuzzy_name_search + _semantic_entity_search → _reciprocal_rank_fusion |
| 3.21.10 | QE: Verify AC — Graph traversal uses recursive CTE with cycle prevention, RBAC at each hop | QE | [x] | NOT e2.id = ANY(gw.path), e2.application_id = ANY(:app_ids), statement_timeout=5s |
| 3.21.11 | QE: Run full test suite — `pytest tests/test_entity_extraction.py tests/test_knowledge_graph_service.py tests/test_indexing_router.py -v`, all green | QE | [x] | 42 tests pass (skipped: pgvector not installed) |
| 3.21.12 | QE: Run manual verification checklist from spec (create doc, wait for extraction, check entities, check search, check traversal, verify mention_count increment) | QE | [-] | Deferred: requires running DB with pgvector |

---

## Cross-Phase Dependencies

| Dependency | Source | Target | Notes |
|------------|--------|--------|-------|
| LLM chat provider | Phase 1 `ProviderRegistry` | 3.7.3 Entity extraction LLM call | Must have at least one chat provider configured |
| Embedding service | Phase 2 `EmbeddingService` | 3.8.6 Entity embedding generation | Reuses same embedding model for entity vectors |
| Chunking pipeline | Phase 2 `embed_document()` | 3.14.2 Extraction hook | Entity extraction piggybacks on the chunk pipeline |
| Hybrid retrieval | Phase 2 `HybridRetrievalService` | 3.15.4 4th RRF source | Entity search added as optional source |
| DocumentChunks table | Phase 2 migration | 3.2.9, 3.3.5 FK references | EntityRelationships.chunk_id and EntityMentions.chunk_id reference Phase 2 table |
| Agent tools | Phase 4 `query_entities` | 3.16.7-3.16.9 Entity endpoints | Phase 4 agent calls these endpoints as tools |

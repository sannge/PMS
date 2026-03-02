# Phase 3: Knowledge Graph (PostgreSQL)

> **STATUS: REPLACED BY [Phase 3.1: Agent SQL Access & Excel Export](phase-3.1-sql-access.md)**
>
> The LLM-extracted knowledge graph has been replaced by direct read-only SQL access
> via scoped PostgreSQL views. The relational schema already models entities and relationships
> explicitly (Users, Projects, Tasks, etc. with FK relationships), making LLM extraction redundant.
> All Phase 3 code (~4,880 LOC) is removed in Phase 3.1.

~~**Goal**: Entity extraction from documents stored as a lightweight knowledge graph in PostgreSQL. Graph-based entity retrieval added to hybrid pipeline and exposed as a dedicated agent tool.~~

~~**Depends on**: Phase 1 (LLM providers for entity extraction), Phase 2 (embedding infrastructure, chunking pipeline)~~
~~**Blocks**: Phase 4 (agent needs `query_entities` tool)~~
~~**Parallel with**: Phase 6 (independent work)~~

---

## Design Decision: PostgreSQL over Neo4j

A dedicated graph database (Neo4j) was considered but rejected for this project:

| Concern | PostgreSQL graph | Neo4j |
|---------|-----------------|-------|
| Infrastructure | Already have it — zero new services | New server to deploy, backup, monitor |
| RBAC | Same `application_id` column, same FK joins | Separate namespace system (group_ids) |
| Backups | Single backup covers everything | Two databases to coordinate |
| Joins with documents | Native FK joins to Documents, DocumentChunks | Cross-database correlation |
| Traversal depth | 2-3 hops fine with recursive CTE | Built for 10+ hops (not needed here) |
| Entity extraction | Simple LLM prompt per chunk | Graphiti's multi-call pipeline (heavier, costlier) |
| Transactions | ACID with rest of the data | Eventually consistent across DBs |
| Dependencies | 0 new Python packages | `graphiti-core`, `neo4j` packages |
| Cost | $0 extra | Neo4j license + server |

**Why 2-3 hops is enough**: In a PM app, entity queries are shallow — "What do we know about Payment Service?" (1 hop from entity to relationships), "How are Payment Service and Auth Service related?" (2 hops through relationships), "Who works on systems that depend on the API Gateway?" (3 hops max). Deep graph algorithms (PageRank, community detection, centrality) aren't needed.

---

## Data Model

### Entity-Relationship Diagram

```
┌─────────────────────┐         ┌──────────────────────────┐
│   DocumentEntities  │         │   EntityRelationships    │
├─────────────────────┤         ├──────────────────────────┤
│ id (UUID PK)        │◄───┐    │ id (UUID PK)             │
│ name (VARCHAR)      │    │    │ source_entity_id (FK) ───┼──► DocumentEntities.id
│ entity_type (VARCHAR)│    │    │ target_entity_id (FK) ───┼──► DocumentEntities.id
│ description (TEXT)   │    │    │ relationship_type (VARCHAR)│
│ aliases (TEXT[])     │    │    │ description (TEXT)        │
│ application_id (FK) │    │    │ weight (FLOAT)            │
│ embedding (vector)  │    └────┤ document_id (FK) ─────────┼──► Documents.id
│ mention_count (INT) │         │ chunk_id (FK) ────────────┼──► DocumentChunks.id
│ first_seen_at (TS)  │         │ snippet (TEXT)            │
│ last_seen_at (TS)   │         │ confidence (FLOAT)        │
│ created_at (TS)     │         │ application_id (FK)       │
│ updated_at (TS)     │         │ created_at (TS)           │
└─────────────────────┘         │ updated_at (TS)           │
                                └──────────────────────────┘

                                ┌──────────────────────────┐
                                │    EntityMentions         │
                                ├──────────────────────────┤
                                │ id (UUID PK)             │
                                │ entity_id (FK) ──────────┼──► DocumentEntities.id
                                │ document_id (FK) ────────┼──► Documents.id
                                │ chunk_id (FK) ────────────┼──► DocumentChunks.id
                                │ context_snippet (TEXT)    │
                                │ mention_type (VARCHAR)    │
                                │ created_at (TS)           │
                                └──────────────────────────┘
```

### Why Three Tables?

- **DocumentEntities**: The nodes — people, systems, technologies, concepts extracted from documents. Each entity has an embedding for semantic entity search ("find entities similar to API Gateway").
- **EntityRelationships**: The edges — directed relationships between entities with provenance (which document, which chunk, what snippet). Weight accumulates across multiple mentions of the same relationship.
- **EntityMentions**: The evidence — tracks every place an entity is mentioned, enabling "show me all documents that mention Service X" without a full-text search.

### Entity Types

| Type | Examples | Extraction Cue |
|------|----------|-----------------|
| `system` | "Payment Service", "API Gateway", "Auth Module" | Named software components, services, modules |
| `person` | "John Doe", "Sarah Chen" | Named individuals (not job titles) |
| `team` | "Backend Team", "Platform Squad" | Named groups of people |
| `technology` | "PostgreSQL", "React", "OAuth 2.0" | Named technologies, frameworks, protocols |
| `concept` | "Microservices", "Event Sourcing", "RBAC" | Architecture patterns, methodologies |
| `project` | "Project Alpha", "Q2 Migration" | Named projects (supplements explicit Project model) |
| `document` | "API Spec v2", "Sprint 12 Retro Notes" | Referenced documents (cross-references) |

### Relationship Types

| Type | Example | Direction |
|------|---------|-----------|
| `depends_on` | Payment Service → Auth Service | source depends on target |
| `uses` | API Gateway → Redis | source uses target |
| `maintained_by` | Payment Service → Backend Team | source maintained by target |
| `owned_by` | Project Alpha → Sarah Chen | source owned by target |
| `part_of` | Auth Module → Payment Service | source is part of target |
| `implements` | Auth Module → OAuth 2.0 | source implements target |
| `integrates_with` | Payment Service → Stripe API | source integrates with target |
| `related_to` | Microservices → Event Sourcing | general association |
| `succeeded_by` | API v1 → API v2 | versioning/temporal |
| `references` | Sprint 12 Notes → API Spec v2 | document cross-reference |

---

## Task 3.1: Knowledge Graph Migration

### New File: `fastapi-backend/alembic/versions/YYYYMMDD_add_knowledge_graph.py`

### `DocumentEntities` Table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | `default=uuid4` |
| name | VARCHAR(500) | Canonical entity name |
| name_normalized | VARCHAR(500) | `LOWER(TRIM(name))` for dedup matching |
| entity_type | VARCHAR(50) | "system", "person", "team", "technology", "concept", "project", "document" |
| description | TEXT NULL | LLM-generated summary, updated as more mentions found |
| aliases | TEXT[] NULL | Alternative names (e.g., ["Payment Svc", "pay-service"]) |
| application_id | UUID FK NULL | Scoped to application for RBAC. NULL = cross-application. |
| embedding | vector(1536) | For semantic entity search |
| mention_count | INT DEFAULT 1 | Popularity signal — incremented on each new mention |
| first_seen_at | TIMESTAMP | When entity first appeared in any document |
| last_seen_at | TIMESTAMP | When entity was most recently mentioned |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### `EntityRelationships` Table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | `default=uuid4` |
| source_entity_id | UUID FK -> DocumentEntities.id CASCADE | |
| target_entity_id | UUID FK -> DocumentEntities.id CASCADE | |
| relationship_type | VARCHAR(100) | "depends_on", "uses", "maintained_by", etc. |
| description | TEXT NULL | LLM-generated description of the relationship |
| weight | FLOAT DEFAULT 1.0 | Accumulated confidence — increases with more evidence |
| document_id | UUID FK -> Documents.id SET NULL | Source document (NULL if doc deleted) |
| chunk_id | UUID FK -> DocumentChunks.id SET NULL | Source chunk |
| snippet | TEXT NULL | The sentence/paragraph that evidences this relationship |
| confidence | FLOAT DEFAULT 0.8 | LLM extraction confidence (0.0-1.0) |
| application_id | UUID FK NULL | Denormalized for fast RBAC filtering |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### `EntityMentions` Table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | `default=uuid4` |
| entity_id | UUID FK -> DocumentEntities.id CASCADE | |
| document_id | UUID FK -> Documents.id CASCADE | |
| chunk_id | UUID FK -> DocumentChunks.id SET NULL | |
| context_snippet | TEXT | Surrounding text (1-2 sentences) for context |
| mention_type | VARCHAR(50) | "definition", "reference", "discussion" |
| created_at | TIMESTAMP | |

### Indexes

```sql
-- Entity lookup
CREATE UNIQUE INDEX idx_entities_name_type_app
  ON "DocumentEntities" (name_normalized, entity_type, application_id)
  WHERE application_id IS NOT NULL;
CREATE UNIQUE INDEX idx_entities_name_type_global
  ON "DocumentEntities" (name_normalized, entity_type)
  WHERE application_id IS NULL;

-- Entity semantic search (find entities similar to a query)
CREATE INDEX idx_entities_embedding
  ON "DocumentEntities"
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Entity type filtering
CREATE INDEX idx_entities_type ON "DocumentEntities" (entity_type);

-- RBAC filtering
CREATE INDEX idx_entities_app ON "DocumentEntities" (application_id);

-- Relationship traversal
CREATE INDEX idx_relationships_source ON "EntityRelationships" (source_entity_id);
CREATE INDEX idx_relationships_target ON "EntityRelationships" (target_entity_id);
CREATE INDEX idx_relationships_type ON "EntityRelationships" (relationship_type);
CREATE INDEX idx_relationships_app ON "EntityRelationships" (application_id);
CREATE INDEX idx_relationships_document ON "EntityRelationships" (document_id);

-- Composite for common traversal pattern: "all relationships for entity X"
CREATE INDEX idx_relationships_source_type
  ON "EntityRelationships" (source_entity_id, relationship_type);
CREATE INDEX idx_relationships_target_type
  ON "EntityRelationships" (target_entity_id, relationship_type);

-- Mention lookups
CREATE INDEX idx_mentions_entity ON "EntityMentions" (entity_id);
CREATE INDEX idx_mentions_document ON "EntityMentions" (document_id);

-- pg_trgm for fuzzy entity name search
CREATE INDEX idx_entities_name_trgm
  ON "DocumentEntities"
  USING GIN(name gin_trgm_ops);
```

### Acceptance Criteria
- [ ] All three tables created with correct types and constraints
- [ ] FK cascades: entity delete → relationships + mentions deleted
- [ ] Document delete → relationships set NULL (don't lose entity, just provenance)
- [ ] Partial unique indexes for entity dedup (name + type + app scope)
- [ ] HNSW index on entity embeddings
- [ ] pg_trgm GIN index on entity names
- [ ] All traversal indexes present
- [ ] Downgrade drops all three tables and indexes

---

## Task 3.2: SQLAlchemy Models

### New File: `fastapi-backend/app/models/document_entity.py`

```python
from pgvector.sqlalchemy import Vector

class DocumentEntity(Base):
    __tablename__ = "DocumentEntities"
    __allow_unmapped__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(500))
    name_normalized: Mapped[str] = mapped_column(String(500))
    entity_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("Applications.id"), nullable=True
    )
    embedding = mapped_column(Vector(1536), nullable=True)
    mention_count: Mapped[int] = mapped_column(default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    outgoing_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="source_entity",
        foreign_keys="EntityRelationship.source_entity_id",
        cascade="all, delete-orphan"
    )
    incoming_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="target_entity",
        foreign_keys="EntityRelationship.target_entity_id",
        cascade="all, delete-orphan"
    )
    mentions: Mapped[list["EntityMention"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
```

### New File: `fastapi-backend/app/models/entity_relationship.py`

```python
class EntityRelationship(Base):
    __tablename__ = "EntityRelationships"
    __allow_unmapped__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("DocumentEntities.id", ondelete="CASCADE")
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("DocumentEntities.id", ondelete="CASCADE")
    )
    relationship_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(default=1.0)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("Documents.id", ondelete="SET NULL"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("DocumentChunks.id", ondelete="SET NULL"), nullable=True
    )
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(default=0.8)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("Applications.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    source_entity: Mapped["DocumentEntity"] = relationship(
        back_populates="outgoing_relationships",
        foreign_keys=[source_entity_id]
    )
    target_entity: Mapped["DocumentEntity"] = relationship(
        back_populates="incoming_relationships",
        foreign_keys=[target_entity_id]
    )
    document: Mapped["Document | None"] = relationship()
    chunk: Mapped["DocumentChunk | None"] = relationship()
```

### New File: `fastapi-backend/app/models/entity_mention.py`

```python
class EntityMention(Base):
    __tablename__ = "EntityMentions"
    __allow_unmapped__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("DocumentEntities.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("Documents.id", ondelete="CASCADE")
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("DocumentChunks.id", ondelete="SET NULL"), nullable=True
    )
    context_snippet: Mapped[str] = mapped_column(Text)
    mention_type: Mapped[str] = mapped_column(String(50), default="reference")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    entity: Mapped["DocumentEntity"] = relationship(back_populates="mentions")
    document: Mapped["Document"] = relationship()
```

### Modify: `fastapi-backend/app/models/__init__.py`

Register all three:
```python
from app.models.document_entity import DocumentEntity
from app.models.entity_relationship import EntityRelationship
from app.models.entity_mention import EntityMention
```

### Acceptance Criteria
- [ ] All three models importable from `app.models`
- [ ] Bidirectional relationships: entity ↔ relationships (incoming + outgoing)
- [ ] Entity → mentions cascade delete
- [ ] Relationship → document/chunk SET NULL on delete (preserve entity, lose provenance)
- [ ] Vector column on entity for semantic search
- [ ] ARRAY column for aliases

---

## Task 3.3: Pydantic Schemas

### New File: `fastapi-backend/app/schemas/knowledge_graph.py`

```python
# --- Entity Schemas ---

class EntityCreate(BaseModel):
    name: str
    entity_type: str  # Validated: system, person, team, technology, concept, project, document
    description: str | None = None
    aliases: list[str] | None = None
    application_id: UUID | None = None

class EntityResponse(BaseModel):
    id: UUID
    name: str
    entity_type: str
    description: str | None
    aliases: list[str] | None
    application_id: UUID | None
    mention_count: int
    first_seen_at: datetime
    last_seen_at: datetime

class EntityWithRelationships(EntityResponse):
    outgoing: list["RelationshipResponse"]
    incoming: list["RelationshipResponse"]
    mention_documents: list[EntityMentionDoc]  # {document_id, title, snippet}

# --- Relationship Schemas ---

class RelationshipResponse(BaseModel):
    id: UUID
    source_entity: EntityBrief  # {id, name, entity_type}
    target_entity: EntityBrief
    relationship_type: str
    description: str | None
    weight: float
    snippet: str | None
    confidence: float
    document_title: str | None  # Joined from document

# --- Search/Query Schemas ---

class EntitySearchResult(BaseModel):
    entity: EntityResponse
    relevance_score: float
    match_source: str  # "semantic", "fuzzy_name", "exact"
    relationships_count: int

class GraphTraversalResult(BaseModel):
    """Result of a multi-hop graph traversal."""
    root_entity: EntityResponse
    paths: list[GraphPath]  # Each path is a sequence of entity → relationship → entity
    total_entities: int
    total_relationships: int

class GraphPath(BaseModel):
    entities: list[EntityBrief]
    relationships: list[RelationshipBrief]
    depth: int

# --- Extraction Schemas (internal, used by extraction service) ---

class ExtractedEntity(BaseModel):
    name: str
    entity_type: str
    description: str

class ExtractedRelationship(BaseModel):
    source: str       # Entity name
    target: str       # Entity name
    relationship_type: str
    snippet: str      # Evidence sentence

class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]
```

### Acceptance Criteria
- [ ] All schemas validate correctly
- [ ] `EntityWithRelationships` includes both directions (outgoing + incoming)
- [ ] `GraphTraversalResult` represents multi-hop paths
- [ ] Extraction schemas match LLM output format
- [ ] Entity type validated against allowed values

---

## Task 3.4: Entity Extraction Service

### New File: `fastapi-backend/app/ai/entity_extraction_service.py`

This is the core of the knowledge graph — it extracts entities and relationships from document chunks using LLM.

```python
EXTRACTION_PROMPT = """Extract entities and relationships from the following text.

Entity types: system, person, team, technology, concept, project, document

Relationship types: depends_on, uses, maintained_by, owned_by, part_of,
implements, integrates_with, related_to, succeeded_by, references

Rules:
- Only extract entities that are specifically named (not generic terms like "the database")
- Each entity must have a clear type
- Each relationship needs a source and target entity, both named in the text
- Include the exact sentence as the snippet that evidences each relationship
- Rate your confidence for each relationship (0.0-1.0)
- If an entity has been mentioned before with a different name, include it as an alias

Return JSON:
{
  "entities": [
    {"name": "Payment Service", "type": "system", "description": "Handles payment processing and billing"}
  ],
  "relationships": [
    {
      "source": "Payment Service",
      "target": "Auth Service",
      "type": "depends_on",
      "snippet": "The Payment Service authenticates requests through the Auth Service.",
      "confidence": 0.9
    }
  ]
}

Text:
{chunk_text}

Context (document title and heading):
{heading_context}
"""


class EntityExtractionService:
    """
    Extracts entities and relationships from document chunks using LLM,
    then upserts into PostgreSQL knowledge graph tables.

    Called during the embedding pipeline (Phase 2) — after chunks are created,
    each chunk is also processed for entity extraction.
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        embedding_service: EmbeddingService,  # For entity embeddings
        db: AsyncSession
    ):
        ...

    async def extract_from_document(
        self,
        document_id: UUID,
        chunks: list[DocumentChunk],
        application_id: UUID | None,
        batch_size: int = 5
    ) -> ExtractionSummary:
        """
        Extract entities and relationships from all chunks in a document.

        1. Process chunks in batches of `batch_size` (to limit concurrent LLM calls)
        2. For each chunk:
           a. Send chunk_text + heading_context to LLM with EXTRACTION_PROMPT
           b. Parse JSON response into ExtractedEntity/ExtractedRelationship
           c. Validate extracted data (filter invalid types, empty names)
        3. Deduplicate entities across chunks (same name + type → merge)
        4. Upsert entities via _upsert_entity()
        5. Upsert relationships via _upsert_relationship()
        6. Create EntityMention records for each chunk-entity pair
        7. Remove stale mentions (from previous extraction of same document)
        8. Update Document.graph_ingested_at = now()

        Returns:
        ExtractionSummary(
            entities_created: int,
            entities_updated: int,
            relationships_created: int,
            relationships_updated: int,
            mentions_created: int,
            duration_ms: int
        )
        """

    async def _upsert_entity(
        self,
        name: str,
        entity_type: str,
        description: str,
        application_id: UUID | None
    ) -> DocumentEntity:
        """
        Find-or-create entity by normalized name + type + application scope.

        1. Normalize name: LOWER(TRIM(name))
        2. Query: SELECT FROM DocumentEntities
                  WHERE name_normalized = :normalized
                    AND entity_type = :type
                    AND (application_id = :app_id OR application_id IS NULL)
        3. If found:
           a. Update description if new one is longer/better
           b. Increment mention_count
           c. Update last_seen_at
           d. Merge aliases
        4. If not found:
           a. Create new entity
           b. Generate embedding for entity name + description
           c. Set first_seen_at = last_seen_at = now()

        Also check aliases: if "Payment Svc" matches an alias of "Payment Service",
        merge into existing entity.
        """

    async def _upsert_relationship(
        self,
        source_entity_id: UUID,
        target_entity_id: UUID,
        relationship_type: str,
        document_id: UUID,
        chunk_id: UUID,
        snippet: str,
        confidence: float
    ) -> EntityRelationship:
        """
        Find-or-create relationship.

        1. Query: SELECT FROM EntityRelationships
                  WHERE source_entity_id = :source
                    AND target_entity_id = :target
                    AND relationship_type = :type
        2. If found:
           a. Increment weight by confidence (accumulates evidence)
           b. Update snippet if confidence is higher
           c. Update document_id/chunk_id to latest evidence
        3. If not found:
           a. Create new relationship
           b. Set weight = confidence
        """

    async def remove_document_extractions(
        self,
        document_id: UUID
    ) -> int:
        """
        Remove all mentions and relationships sourced from a specific document.
        Called before re-extraction (idempotent) or on document deletion.

        1. Delete EntityMentions WHERE document_id = :doc_id
        2. Delete EntityRelationships WHERE document_id = :doc_id
        3. Clean up orphaned entities (mention_count reaches 0) - optional
        4. Return total records removed
        """

    async def extract_batch(
        self,
        document_ids: list[UUID]
    ) -> BatchExtractionResult:
        """
        Batch extraction for multiple documents.
        Used by nightly job and manual reindex.
        Processes sequentially with progress tracking in Redis.
        """
```

### LLM Call Details

- Uses `ProviderRegistry.get_chat_provider()` to get the configured chat LLM
- Sends extraction prompt with `temperature=0.2` (deterministic extraction)
- Parses JSON response (with fallback for malformed JSON)
- One LLM call per chunk (not per document — chunks are already right-sized)
- Rate-limited: max 10 chunks/second to avoid API throttling

### Acceptance Criteria
- [ ] Entities extracted with correct types
- [ ] Relationships extracted with evidence snippets
- [ ] Entity deduplication by normalized name + type + scope
- [ ] Alias matching merges entities ("Payment Svc" → "Payment Service")
- [ ] Mention count incremented on re-encounters
- [ ] Relationship weight accumulates across multiple evidence sources
- [ ] Stale extractions removed on re-processing (idempotent)
- [ ] Entity embeddings generated for semantic entity search
- [ ] Handles malformed LLM JSON responses gracefully
- [ ] `graph_ingested_at` updated on document after extraction

---

## Task 3.5: Knowledge Graph Query Service

### New File: `fastapi-backend/app/ai/knowledge_graph_service.py`

```python
class KnowledgeGraphService:
    """
    Query interface for the PostgreSQL knowledge graph.
    Provides entity search, relationship traversal, and context retrieval.
    All queries filtered by user's accessible application_ids (RBAC).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_entities(
        self,
        query: str,
        accessible_app_ids: list[UUID],
        entity_type: str | None = None,
        limit: int = 10
    ) -> list[EntitySearchResult]:
        """
        Multi-strategy entity search:

        1. Exact name match (case-insensitive):
           WHERE name_normalized = LOWER(:query)
           → Score: 1.0

        2. Fuzzy name match (pg_trgm):
           WHERE similarity(name, :query) > 0.3
           → Score: similarity value

        3. Semantic embedding search (pgvector):
           Embed query → cosine similarity on entity embeddings
           → Score: cosine similarity

        All filtered by:
           application_id = ANY(:accessible_app_ids) OR application_id IS NULL

        Merge results using RRF, return top `limit`.
        """

    async def get_entity_context(
        self,
        entity_id: UUID,
        accessible_app_ids: list[UUID],
        max_depth: int = 2
    ) -> EntityWithRelationships:
        """
        Full context for a single entity:
        - Entity details (name, type, description, aliases)
        - All outgoing relationships (entity → ?)
        - All incoming relationships (? → entity)
        - Source documents where mentioned (with snippets)
        - Related entities (1-2 hops away)

        Uses recursive CTE for multi-hop traversal.
        """

    async def traverse_graph(
        self,
        start_entity_id: UUID,
        accessible_app_ids: list[UUID],
        max_depth: int = 2,
        relationship_types: list[str] | None = None
    ) -> GraphTraversalResult:
        """
        Multi-hop graph traversal using recursive CTE.

        SQL:
        WITH RECURSIVE graph_walk AS (
            -- Base case: start entity
            SELECT
                e.id, e.name, e.entity_type,
                0 AS depth,
                ARRAY[e.id] AS path
            FROM "DocumentEntities" e
            WHERE e.id = :start_id
              AND (e.application_id = ANY(:app_ids) OR e.application_id IS NULL)

            UNION ALL

            -- Recursive case: follow relationships
            SELECT
                e2.id, e2.name, e2.entity_type,
                gw.depth + 1,
                gw.path || e2.id
            FROM graph_walk gw
            JOIN "EntityRelationships" er
              ON er.source_entity_id = gw.id OR er.target_entity_id = gw.id
            JOIN "DocumentEntities" e2
              ON e2.id = CASE
                  WHEN er.source_entity_id = gw.id THEN er.target_entity_id
                  ELSE er.source_entity_id
                END
            WHERE gw.depth < :max_depth
              AND NOT e2.id = ANY(gw.path)  -- Prevent cycles
              AND (e2.application_id = ANY(:app_ids) OR e2.application_id IS NULL)
              AND (:rel_types IS NULL OR er.relationship_type = ANY(:rel_types))
        )
        SELECT DISTINCT * FROM graph_walk;

        Builds GraphTraversalResult with paths and entity details.
        """

    async def find_connections(
        self,
        entity_a_id: UUID,
        entity_b_id: UUID,
        accessible_app_ids: list[UUID],
        max_depth: int = 3
    ) -> list[GraphPath]:
        """
        Find paths connecting two entities.
        Uses bidirectional BFS via recursive CTE.
        Returns shortest paths (up to 3 hops).
        """

    async def get_entity_timeline(
        self,
        entity_id: UUID,
        accessible_app_ids: list[UUID]
    ) -> list[TimelineEntry]:
        """
        Temporal view: when was this entity first mentioned,
        how has its description evolved, what relationships changed.
        Ordered by mention timestamps.
        """

    async def get_popular_entities(
        self,
        accessible_app_ids: list[UUID],
        entity_type: str | None = None,
        limit: int = 20
    ) -> list[EntityResponse]:
        """
        Most-mentioned entities across accessible documents.
        ORDER BY mention_count DESC.
        Useful for "What are the main systems/people in our docs?"
        """
```

### Acceptance Criteria
- [ ] Entity search uses 3 strategies (exact, fuzzy, semantic) with RRF merge
- [ ] Graph traversal uses recursive CTE with cycle prevention
- [ ] RBAC filtering on all queries (application_id check)
- [ ] `find_connections` finds paths between two entities
- [ ] `get_entity_timeline` shows temporal evolution
- [ ] `get_popular_entities` returns most-mentioned entities
- [ ] Max depth prevents runaway queries (default 2, max 3)
- [ ] Path array prevents infinite cycles in recursive CTE

---

## Task 3.6: Integrate Extraction into Embedding Pipeline

### Modify: `fastapi-backend/app/ai/embedding_service.py`

After embedding chunks, also extract entities:

```python
class EmbeddingService:
    def __init__(self, ..., entity_extraction_service: EntityExtractionService | None = None):
        self.entity_extraction = entity_extraction_service

    async def embed_document(self, document_id, content_json, title, scope_ids) -> EmbedResult:
        # ... existing chunking + embedding logic (unchanged) ...

        # NEW: Entity extraction (piggybacked on embedding pipeline)
        if self.entity_extraction:
            try:
                extraction_result = await self.entity_extraction.extract_from_document(
                    document_id=document_id,
                    chunks=new_chunks,  # The chunks we just created
                    application_id=scope_ids.get("application_id")
                )
                logger.info(
                    f"Entity extraction: {extraction_result.entities_created} entities, "
                    f"{extraction_result.relationships_created} relationships"
                )
            except Exception as e:
                # Non-critical: embedding succeeded even if extraction fails
                logger.warning(f"Entity extraction failed for {document_id}: {e}")

        return embed_result
```

### Acceptance Criteria
- [ ] Entity extraction runs after embedding (same pipeline, same debounced trigger)
- [ ] Extraction failure doesn't fail the embedding
- [ ] No separate nightly job needed (extraction is part of embed pipeline)
- [ ] Re-embedding re-extracts (old extractions cleaned up)

---

## Task 3.7: Extend Hybrid Retrieval with Entity Search

### Modify: `fastapi-backend/app/ai/retrieval_service.py`

Add entity search as 4th source in RRF merge:

```python
class HybridRetrievalService:
    def __init__(self, ..., kg_service: KnowledgeGraphService | None = None):
        self.kg_service = kg_service

    async def retrieve(self, query, user_id, limit=10, **kwargs):
        ranked_lists = []

        # Existing sources:
        # 1. pgvector semantic search → ranked_lists.append(...)
        # 2. Meilisearch keyword search → ranked_lists.append(...)
        # 3. pg_trgm fuzzy title match → ranked_lists.append(...)

        # NEW: 4. Knowledge graph entity search
        if self.kg_service:
            entity_results = await self._entity_search(query, accessible_app_ids)
            if entity_results:
                ranked_lists.append(entity_results)

        return self._reciprocal_rank_fusion(*ranked_lists)

    async def _entity_search(
        self,
        query: str,
        accessible_app_ids: list[UUID],
        limit: int = 10
    ) -> list[RankedResult]:
        """
        Search knowledge graph for relevant entities.
        For each matching entity, find its source documents via EntityMentions.
        Convert to RankedResult format for RRF merge.

        This surfaces documents that might not match the query text directly
        but are related to entities the query mentions.
        """
```

### Acceptance Criteria
- [ ] Entity search integrated into RRF merge as 4th source
- [ ] Entity search is optional (works without knowledge graph)
- [ ] Entity results linked back to source documents
- [ ] RBAC filtering applied

---

## Task 3.8: Reindex Endpoints

### New File: `fastapi-backend/app/routers/ai_indexing.py`

**Prefix**: `/api/ai`

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/reindex/{document_id}` | POST | Force re-embed + re-extract entities for a document | Document editor or higher |
| `/reindex/application/{app_id}` | POST | Re-process all docs in an application (batch job) | Application Owner |
| `/index-status/{document_id}` | GET | Embedding + entity extraction timestamps | Document viewer or higher |
| `/index-status/application/{app_id}` | GET | Batch index status for all docs | Application Member |
| `/index-progress` | GET | Batch job progress (from Redis) | Any authenticated user |
| `/entities` | GET | List entities for an application | Application Member |
| `/entities/{entity_id}` | GET | Get full entity context with relationships | Application Member |
| `/entities/search` | GET | Search entities by name/type | Application Member |

### Entity Endpoints Detail

**`GET /entities?application_id=...&type=...&limit=20`**:
Returns paginated entity list with mention counts. Optionally filtered by type.

**`GET /entities/{entity_id}`**:
Returns full `EntityWithRelationships` — all relationships (in + out) and source documents.

**`GET /entities/search?q=...&application_id=...`**:
Multi-strategy entity search (exact + fuzzy + semantic). Returns `EntitySearchResult` list.

### Modify: `fastapi-backend/app/main.py`

Mount the router:
```python
from app.routers import ai_indexing
app.include_router(ai_indexing.router)
```

### Acceptance Criteria
- [ ] Reindex triggers both embedding and entity extraction
- [ ] Entity endpoints return properly scoped data
- [ ] Entity search works with fuzzy matching
- [ ] Auth checked on all endpoints
- [ ] Router mounted

---

## Task 3.9: Tests

### New File: `fastapi-backend/tests/test_entity_extraction.py`

```
# Extraction
test_extract_entities_from_chunk
test_extract_relationships_from_chunk
test_extract_handles_malformed_llm_json
test_extract_filters_invalid_entity_types
test_extract_filters_unnamed_entities

# Upsert / Dedup
test_upsert_entity_creates_new
test_upsert_entity_updates_existing
test_upsert_entity_increments_mention_count
test_upsert_entity_merges_aliases
test_upsert_entity_dedup_by_normalized_name
test_upsert_relationship_creates_new
test_upsert_relationship_accumulates_weight
test_upsert_relationship_updates_to_higher_confidence

# Cleanup
test_remove_document_extractions
test_re_extraction_is_idempotent

# Batch
test_extract_batch_processes_all
test_extract_batch_continues_on_failure
test_extract_batch_tracks_progress
```

### New File: `fastapi-backend/tests/test_knowledge_graph_service.py`

```
# Search
test_search_entities_exact_match
test_search_entities_fuzzy_match
test_search_entities_semantic_match
test_search_entities_rrf_merge
test_search_entities_filters_by_type
test_search_entities_respects_rbac

# Traversal
test_get_entity_context_includes_relationships
test_get_entity_context_includes_mentions
test_traverse_graph_one_hop
test_traverse_graph_two_hops
test_traverse_graph_prevents_cycles
test_traverse_graph_respects_rbac
test_traverse_graph_filters_relationship_type
test_find_connections_between_entities
test_find_connections_no_path_returns_empty

# Timeline & Popular
test_get_entity_timeline_ordered_by_date
test_get_popular_entities_ordered_by_mentions
test_get_popular_entities_filters_by_type

# Integration
test_entity_search_in_hybrid_retrieval_rrf
test_hybrid_retrieval_without_kg_still_works
```

### New File: `fastapi-backend/tests/test_indexing_router.py`

```
test_reindex_document_triggers_extraction
test_reindex_application_enqueues_batch
test_index_status_returns_timestamps
test_list_entities_paginated
test_get_entity_with_relationships
test_search_entities_endpoint
test_entity_endpoints_require_auth
test_entity_endpoints_respect_rbac
```

### Acceptance Criteria
- [ ] All tests pass
- [ ] LLM calls mocked (no real API calls)
- [ ] Entity dedup logic thoroughly tested
- [ ] Graph traversal cycle prevention verified
- [ ] RBAC boundary tests verify app isolation
- [ ] Integration tests verify entity search in hybrid pipeline

---

## Verification Checklist

```bash
cd fastapi-backend

# 1. Run migration
alembic upgrade head

# 2. Verify tables
# psql: \dt DocumentEntities; \dt EntityRelationships; \dt EntityMentions;

# 3. Verify indexes
# psql: \di idx_entities_*; \di idx_relationships_*; \di idx_mentions_*;

# 4. Create a document with rich content mentioning systems/people
# POST /api/documents (create doc)
# Wait ~30s (embedding + extraction pipeline)

# 5. Check extracted entities
# GET /api/ai/entities?application_id=...
# Should see entities like "Payment Service", "John Doe", etc.

# 6. Check entity context
# GET /api/ai/entities/{entity_id}
# Should see relationships and source documents

# 7. Search entities
# GET /api/ai/entities/search?q=payment&application_id=...
# Should find "Payment Service" via exact/fuzzy/semantic

# 8. Create a second document referencing same entities
# Wait ~30s
# GET /api/ai/entities/{entity_id}
# mention_count should have increased
# New relationships should appear

# 9. Test graph traversal via agent (Phase 4)
# "How are Payment Service and Auth Service related?"
# Should find path through relationships

# 10. Run tests
pytest tests/test_entity_extraction.py tests/test_knowledge_graph_service.py tests/test_indexing_router.py -v
```

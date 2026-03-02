# Phase 3.1: Agent SQL Access & Excel Export

**Goal**: Replace the LLM-extracted knowledge graph (Phase 3) with direct read-only SQL access to the PostgreSQL schema via scoped views, enabling the AI agent to answer structural questions about applications, projects, tasks, and users. Add Excel export capability for downloadable reports.

**Depends on**: Phase 1 (LLM providers for SQL generation), Phase 2 (embedding infrastructure for RAG tool)
**Blocks**: Phase 4 (agent needs `sql_query_tool` + `rag_search_tool` + `export_to_excel_tool`)
**Replaces**: Phase 3 (Knowledge Graph) — all Phase 3 code is removed
**New dependencies**: `sqlglot` (SQL parser), `openpyxl` (Excel generation)

---

## Design Decision: Drop the Knowledge Graph

The Phase 3 Knowledge Graph used LLM extraction to discover entities and relationships from document content. However, the relational schema **already models these explicitly**:

| Phase 3 Extracted | Already Exists in Schema |
|-------------------|------------------------|
| `DocumentEntity(type=person)` | `Users` table with id, email, display_name |
| `DocumentEntity(type=project)` | `Projects` table with id, name, key |
| `EntityRelationship(type=owned_by)` | `Applications.owner_id` FK → Users |
| `EntityRelationship(type=depends_on)` | `Tasks.parent_id` self-referential FK |
| Graph traversal via recursive CTEs | Already possible via FK JOINs |

**Decision**: Remove ~4,880 LOC of Phase 3 code (3 models, 2 services, 1 router, schemas, tests, migration). Replace with direct SQL access that queries the real schema.

---

## Design Decision: Scoped Views for RBAC

Three approaches were considered for enforcing RBAC on AI-generated SQL:

| Option | Description | Verdict |
|--------|-------------|---------|
| A. LLM scope injection | Trust the LLM to include WHERE clauses with permission filters | Rejected — LLM can forget, misplace, or incorrectly scope filters |
| B. RBAC Validator Agent | Second LLM reviews SQL for RBAC correctness | Rejected — non-deterministic, 2x LLM cost, could miss edge cases |
| **C. Scoped PostgreSQL Views** | Pre-filtered views using `current_setting('app.current_user_id')` | **Chosen** — deterministic security, no LLM trust needed |

### How Scoped Views Work

```
Agent query: "How many high-priority tasks are there?"
                    |
                    v
+------------------------------------+
|  SQL Executor                      |
|                                    |
|  1. SET LOCAL app.current_user_id  |
|     = 'user-uuid'                  |
|  2. SET LOCAL statement_timeout    |
|     = '5000'                       |
|  3. Execute: SELECT count(*)       |
|     FROM v_tasks                   |
|     WHERE priority = 'high'        |
+------------------------------------+
                    |
                    v
+------------------------------------+
|  v_tasks VIEW (database level)     |
|                                    |
|  Automatically filters to only     |
|  tasks in applications where the   |
|  user is owner, member, or viewer  |
|  Even malicious SQL can only see   |
|  authorized data                   |
+------------------------------------+
```

### RBAC Visibility Rules (Read-Only)

Since the agent only does SELECT, the key question is who can **see** what:

| Role | Applications | Projects & Tasks | App Documents | Project Documents | My Notes | Comments |
|------|-------------|-----------------|---------------|-------------------|----------|----------|
| App Owner | Yes (owns it) | All in app | Yes | Yes | Own only | Yes |
| App Member | Yes (member) | All in app (view-only unless project member) | Yes | Yes (view-only unless project member) | Own only | Yes |
| App Viewer | Yes (viewer) | All in app (view-only, cannot become project member) | View-only | View-only | Own only | Yes |
| Project Owner | Via app | Full access to project | Via app role | Yes | Own only | Yes |
| Project Member | Via app | Full access to project | Via app role | Yes | Own only | Yes |

**Simplified**: If you're in the application (any role), you can **see** all projects, tasks, comments, and documents within it. Personal notes ("My Notes") are visible **only** to the owning user.

---

## Two Search Modes

| Mode | Use Case | Implementation |
|------|----------|---------------|
| **Structural (SQL)** | "Who owns Project Alpha?", "What tasks is Sam assigned to?", "Show overdue high-priority bugs" | LLM generates SELECT against scoped views |
| **Content (RAG)** | "What did we decide about API design?", "Find docs about deployment" | Phase 2 hybrid retrieval (pgvector + Meilisearch + pg_trgm) |

The Phase 4 LangGraph agent decides which mode to use based on the question.

---

## Task 3.1a: Phase 3 Cleanup

### Files to Delete (11 files, ~4,880 LOC)

1. `fastapi-backend/app/models/document_entity.py`
2. `fastapi-backend/app/models/entity_relationship.py`
3. `fastapi-backend/app/models/entity_mention.py`
4. `fastapi-backend/app/ai/entity_extraction_service.py`
5. `fastapi-backend/app/ai/knowledge_graph_service.py`
6. `fastapi-backend/app/routers/ai_indexing.py`
7. `fastapi-backend/app/schemas/knowledge_graph.py`
8. `fastapi-backend/tests/test_entity_extraction.py`
9. `fastapi-backend/tests/test_knowledge_graph_service.py`
10. `fastapi-backend/tests/test_indexing_router.py`
11. `fastapi-backend/alembic/versions/20260225_add_knowledge_graph.py`

### Files to Modify (7 files)

- `app/models/__init__.py` — Remove KG model imports
- `app/routers/__init__.py` — Remove `ai_indexing_router`
- `app/main.py` — Remove `ai_indexing_router` include
- `app/models/document.py` — Remove `graph_ingested_at` column
- `app/ai/embedding_service.py` — Remove entity extraction integration
- `app/ai/retrieval_service.py` — Remove KG entity search source
- `tests/conftest.py` — Remove KG table DROP statements

### Enhance: Draw.io Graph Extraction

**Modify**: `fastapi-backend/app/ai/chunking_service.py` — `_extract_drawio_text()`

The current implementation only extracts text labels from draw.io XML, losing all structural information (edges, containment). Enhance to parse the full `mxCell` graph:

1. **Pass 1 — Vertices**: Collect `mxCell[vertex="1"]` → `{id: label, parent}` dict
2. **Pass 2 — Edges**: Collect `mxCell[edge="1"]` → `(source, target, label)` list
3. **Pass 3 — Containment**: Build parent→children map from `parent` attribute

Output format:
```
[Diagram]
Components: Service A, Auth Module, Database
Relationships:
- Service A → authenticates → Auth Module
- Auth Module → queries → Database
Structure:
- Service A contains: Auth Module
```

This enables RAG to answer questions about diagram structure (e.g., "How does Service A connect to the Database?") without a vision model — the draw.io XML already contains all the information.

### New: Down Migration

`fastapi-backend/alembic/versions/YYYYMMDD_drop_knowledge_graph.py` — DROP DocumentEntities, EntityRelationships, EntityMentions tables + `graph_ingested_at` column from Documents.

### Acceptance Criteria
- [ ] All 11 files deleted
- [ ] All 7 files cleaned of KG references
- [ ] Down migration created and tested (upgrade + downgrade)
- [ ] `pytest tests/ -v` passes with no KG-related failures
- [ ] No orphaned imports or references to deleted modules

---

## Task 3.1b: Scoped PostgreSQL Views

### New: Alembic Migration

`fastapi-backend/alembic/versions/YYYYMMDD_add_scoped_views.py`

Creates ~14 views, all filtered by `current_setting('app.current_user_id')::uuid`:

| View | Base Table(s) | Scope Logic |
|------|---------------|-------------|
| `v_applications` | Applications, ApplicationMembers | User is owner OR member (any role) |
| `v_projects` | Projects via accessible apps | application_id in accessible apps |
| `v_tasks` | Tasks via Projects | project in accessible app; `archived_at IS NULL` |
| `v_task_statuses` | TaskStatuses via Projects | project in accessible app |
| `v_documents` | Documents | 3 scopes: app docs (in app) OR project docs (in app) OR personal (`user_id = current_user` only) |
| `v_document_folders` | DocumentFolders | Same 3-scope pattern as documents |
| `v_comments` | Comments via Tasks | task in accessible app; `is_deleted = false` |
| `v_application_members` | ApplicationMembers | application in accessible apps |
| `v_project_members` | ProjectMembers via Projects | project in accessible app |
| `v_project_assignments` | ProjectAssignments via Projects | project in accessible app |
| `v_users` | Users | All users visible; **exclude password_hash** |
| `v_attachments` | Attachments via Tasks | task in accessible app |
| `v_checklists` | Checklists via Tasks | task in accessible app |
| `v_checklist_items` | ChecklistItems via Checklists | checklist in accessible app |

#### Reusable Accessible-Apps Subquery

All views share this pattern:
```sql
SELECT a.id FROM Applications a
WHERE a.owner_id = current_setting('app.current_user_id')::uuid
UNION
SELECT am.application_id FROM ApplicationMembers am
WHERE am.user_id = current_setting('app.current_user_id')::uuid
```

#### Example: v_tasks
```sql
CREATE VIEW v_tasks AS
SELECT t.id, t.project_id, t.task_key, t.title, t.task_type,
       t.priority, t.assignee_id, t.reporter_id, t.parent_id,
       t.task_status_id, t.story_points, t.due_date,
       t.created_at, t.updated_at
FROM Tasks t
JOIN Projects p ON t.project_id = p.id
WHERE p.application_id IN (
    SELECT a.id FROM Applications a
    WHERE a.owner_id = current_setting('app.current_user_id')::uuid
    UNION
    SELECT am.application_id FROM ApplicationMembers am
    WHERE am.user_id = current_setting('app.current_user_id')::uuid
)
AND t.archived_at IS NULL;
```

#### Example: v_documents (3-scope)
```sql
CREATE VIEW v_documents AS
SELECT d.id, d.application_id, d.project_id, d.user_id,
       d.folder_id, d.title, d.content_plain,
       d.created_at, d.updated_at
FROM Documents d
WHERE d.deleted_at IS NULL
AND (
    (d.application_id IS NOT NULL AND d.project_id IS NULL
     AND d.user_id IS NULL
     AND d.application_id IN (/* accessible apps subquery */))
    OR
    (d.project_id IS NOT NULL AND d.user_id IS NULL
     AND d.project_id IN (
        SELECT p.id FROM Projects p
        WHERE p.application_id IN (/* accessible apps subquery */)
    ))
    OR
    (d.user_id IS NOT NULL AND d.application_id IS NULL
     AND d.project_id IS NULL
     AND d.user_id = current_setting('app.current_user_id')::uuid)
);
```

#### Example: v_comments
```sql
CREATE VIEW v_comments AS
SELECT c.id, c.task_id, c.author_id, c.body_text,
       c.created_at, c.updated_at
FROM Comments c
JOIN Tasks t ON c.task_id = t.id
JOIN Projects p ON t.project_id = p.id
WHERE p.application_id IN (/* accessible apps subquery */)
AND c.is_deleted = false;
```

### Acceptance Criteria
- [ ] All 14 views created via Alembic migration
- [ ] `SET LOCAL app.current_user_id` correctly scopes all views
- [ ] User A (App 1 member) cannot see App 2 data through any view
- [ ] Personal docs visible only to owning user
- [ ] Migration upgrade/downgrade tested
- [ ] v_users excludes password_hash column

---

## Task 3.1c: Schema Context Provider

### New File: `fastapi-backend/app/ai/schema_context.py`

Static descriptions of all ~14 scoped views with rich semantic context for the LLM.

```python
def get_schema_prompt() -> str:
    """Full schema context for LLM SQL generation prompt."""

def get_schema_prompt_for_views(view_names: list[str]) -> str:
    """Subset of schema context for specific views."""

async def validate_schema_against_db(db: AsyncSession) -> list[str]:
    """Startup drift detection - compare static descriptions vs live DB."""
```

Each view description includes:
- View name and purpose
- All columns with types, nullability, descriptions, and enum values
- Relationship hints (e.g., "JOIN v_task_statuses ON v_tasks.task_status_id = v_task_statuses.id")
- Query notes (e.g., "Filter archived_at IS NULL is already applied by the view")

### Acceptance Criteria
- [ ] All 14 views described with columns and relationships
- [ ] Schema prompt is <8,000 tokens (fits within LLM context)
- [ ] Drift detection catches missing columns/tables at startup

---

## Task 3.1d: SQL Validator

### New File: `fastapi-backend/app/ai/sql_validator.py`

Multi-layer validation using `sqlglot` (pure-Python SQL parser):

1. **Regex blocklist**: INSERT/UPDATE/DELETE/DROP/ALTER/COPY/EXECUTE + pg_sleep/pg_read_file + multi-statement + SQL comments
2. **sqlglot AST parse**: Validate PostgreSQL syntax, extract table and function references
3. **View allowlist**: Only `v_*` views queryable — reject base tables, system tables, `pg_catalog`
4. **Function allowlist**: count, sum, avg, min, max, coalesce, lower, upper, trim, date_trunc, extract, cast, to_char, row_number, rank, string_agg, array_agg, concat, replace, etc.
5. **LIMIT enforcement**: Add `LIMIT 100` if missing, cap existing LIMIT

### Acceptance Criteria
- [ ] SELECT queries pass validation
- [ ] All mutation keywords rejected (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE)
- [ ] Dangerous functions rejected (pg_sleep, pg_read_file, dblink, etc.)
- [ ] Multi-statement queries rejected
- [ ] SQL comments rejected
- [ ] Base table references rejected (only v_* views allowed)
- [ ] System table references rejected (pg_catalog, information_schema)
- [ ] Missing LIMIT gets LIMIT 100 added
- [ ] Excessive LIMIT gets capped at 100

---

## Task 3.1e: SQL Generator

### New File: `fastapi-backend/app/ai/sql_generator.py`

Uses `ProviderRegistry` (Phase 1) to call LLM for SQL generation.

Pipeline: question -> build prompt (schema context + rules) -> LLM -> parse JSON -> validate -> retry on failure (max 2) -> return `GeneratedQuery`

LLM system prompt rules:
- SELECT only, use v_* views only
- Include LIMIT (default 50, max 100)
- Return JSON: `{"sql": "...", "explanation": "...", "tables_used": [...]}`
- JOIN v_task_statuses to get status names
- Examples of common query patterns

### Acceptance Criteria
- [ ] Simple questions generate valid SQL (mocked LLM)
- [ ] LLM JSON parsing handles markdown fences, trailing commas
- [ ] Retry on validation failure works (mocked LLM returns invalid, then valid)
- [ ] Max retries respected (returns error after exhaustion)
- [ ] Generated SQL passes validator

---

## Task 3.1f: Query Executor

### New File: `fastapi-backend/app/ai/sql_executor.py`

```python
# Execution pipeline:
await db.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": str(user_id)})
await db.execute(text("SET LOCAL statement_timeout = '5000'"))
result = await db.execute(text(validated_sql))
```

Returns `QueryResult` with:
- `columns: list[str]`, `rows: list[dict]`, `row_count`, `truncated`, `execution_ms`
- `to_text()` -> markdown table for agent reasoning
- UUID -> str, datetime -> ISO string serialization
- Hard cap: 100 rows

### Acceptance Criteria
- [ ] Queries execute and return structured results
- [ ] Statement timeout enforced (5s)
- [ ] Row limit enforced (100)
- [ ] UUID/datetime serialization correct
- [ ] Error handling (timeout, invalid SQL)

---

## Task 3.1g: Excel Export Tool

### New File: `fastapi-backend/app/ai/excel_export.py`

```python
async def export_to_excel(
    columns: list[str],
    rows: list[dict],
    title: str,
    user_id: UUID,
) -> ExportResult:
```

- Creates workbook with header row + data rows using `openpyxl`
- Auto-sizes columns, applies header formatting (bold, background color)
- Saves to temp directory scoped by user_id
- Returns `ExportResult(filename, download_url, row_count)`
- Cleanup: temp files older than 1 hour removed on each export call

### New Endpoint

`GET /api/ai/export/{filename}` — serves the .xlsx file with auth check (user can only download their own exports).

### Acceptance Criteria
- [ ] Valid .xlsx file generated with correct data
- [ ] Headers are formatted (bold)
- [ ] Columns auto-sized
- [ ] Auth check prevents downloading other users' exports
- [ ] Old temp files cleaned up

---

## Task 3.1h: Agent Tools Interface

### New File: `fastapi-backend/app/ai/agent_tools.py`

Three tools for the Phase 4 LangGraph agent:

```python
async def sql_query_tool(question, user_id, db, ...) -> ToolResult
    # NL question -> SQL generation -> validation -> execution -> formatted text

async def rag_search_tool(query, user_id, db, ...) -> ToolResult
    # Wraps existing HybridRetrievalService (Phase 2)

async def export_to_excel_tool(columns, rows, title, user_id) -> ToolResult
    # Query results -> Excel file -> download URL
```

### Acceptance Criteria
- [ ] sql_query_tool returns formatted results for LLM consumption
- [ ] rag_search_tool wraps existing Phase 2 retrieval correctly
- [ ] export_to_excel_tool generates downloadable file
- [ ] All tools handle errors gracefully (return ToolResult with error)
- [ ] All tools enforce RBAC (via scoped views / retrieval service)

---

## Task 3.1i: Pydantic Schemas

### New File: `fastapi-backend/app/schemas/sql_query.py`

- `SQLQueryRequest(question: str, application_id?: UUID, project_id?: UUID)`
- `SQLQueryResponse(question, sql, explanation, columns, rows, row_count, truncated, generation_ms, execution_ms)`
- `SQLValidateRequest(sql: str)`
- `SQLValidateResponse(is_valid, error, tables_used)`
- `ExportResult(filename, download_url, row_count)`
- `GeneratedQuery(sql, explanation, tables_used, generation_attempts, duration_ms)`
- `QueryResult(columns, rows, row_count, truncated, execution_ms)`
- `ToolResult(success, data, metadata, error)`

---

## Task 3.1j: Router

### New File: `fastapi-backend/app/routers/ai_query.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/ai/query` | POST | Execute NL query -> SQL -> validate -> execute -> results |
| `/api/ai/query/validate` | POST | Validate SQL without executing |
| `/api/ai/schema` | GET | Return queryable schema description |
| `/api/ai/export/{filename}` | GET | Download Excel file |
| `/api/ai/reindex/{document_id}` | POST | Re-embed document (preserved from ai_indexing) |
| `/api/ai/index-status/{document_id}` | GET | Embedding timestamp (preserved from ai_indexing) |

### Acceptance Criteria
- [ ] All 6 endpoints respond correctly
- [ ] Authentication required on all endpoints
- [ ] RBAC scoping applied via scoped views
- [ ] Reindex/index-status endpoints preserved from ai_indexing.py

---

## ~~Task 3.1k: Phase 8 Rework~~ — REMOVED

> **REMOVED**: Phase 8 (Query Expansion) was eliminated entirely. The Phase 4 LangGraph agent handles
> query expansion naturally through reasoning (rephrasing, multi-tool calls). Phase 2's 3-source hybrid
> search already handles synonyms (semantic embeddings) and typos (pg_trgm). The retrieval_service.py
> cleanup (removing `_entity_search()`) is covered by Task 3.1a.2.6.

---

## Tests (~70 tests)

| Test File | Count | What it tests |
|-----------|-------|---------------|
| `tests/test_schema_context.py` | ~10 | Schema descriptions, prompt generation, drift detection |
| `tests/test_sql_validator.py` | ~20 | Blocklist, AST parsing, view allowlist, function allowlist, LIMIT |
| `tests/test_sql_generator.py` | ~10 | NL->SQL generation, JSON parsing, retry logic (mocked LLM) |
| `tests/test_sql_executor.py` | ~8 | Execution, timeout, row cap, serialization |
| `tests/test_excel_export.py` | ~6 | Workbook creation, file cleanup, download auth |
| `tests/test_ai_query_router.py` | ~8 | All endpoints, auth, RBAC |
| `tests/test_agent_tools.py` | ~8 | All 3 tools, error handling, scoping |

---

## Verification Checklist

| # | Check | Method |
|---|-------|--------|
| 1 | Phase 3 code fully removed | `grep -r "DocumentEntity\|EntityRelationship\|EntityMention\|knowledge_graph" fastapi-backend/` returns nothing |
| 2 | Existing tests pass after cleanup | `pytest tests/ -v` |
| 3 | Scoped views enforce RBAC | Query as User A (App 1 member) — cannot see App 2 data |
| 4 | Personal docs isolated | User A cannot see User B's personal notes through v_documents |
| 5 | SQL validator blocks mutations | POST `/api/ai/query` with "DROP TABLE Users" — rejected |
| 6 | SQL validator blocks base tables | POST with query referencing `Tasks` (not `v_tasks`) — rejected |
| 7 | End-to-end NL query works | POST `/api/ai/query` with "How many tasks are assigned to me?" — returns correct count |
| 8 | Excel export works | Query results -> export -> download .xlsx -> opens correctly |
| 9 | Statement timeout works | Deliberately slow query times out at 5s |
| 10 | RAG search still works | RAG search returns relevant documents (3 sources: semantic + keyword + fuzzy) |

# Phase 3.1: Agent SQL Access & Excel Export — Granular Task Breakdown

**Created**: 2026-02-25
**Last updated**: 2026-02-26
**Status**: COMPLETE
**Spec**: [phase-3.1-sql-access.md](../phase-3.1-sql-access.md)

> **Depends on**: Phase 1 (LLM providers), Phase 2 (embedding infrastructure)
> **Replaces**: Phase 3 (Knowledge Graph) — all Phase 3 code is removed
> **Blocks**: Phase 4 (agent needs `sql_query_tool`, `rag_search_tool`, `export_to_excel_tool`)

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
| 3.1a.1 | Phase 3 Cleanup — File Deletion | 11 |
| 3.1a.2 | Phase 3 Cleanup — File Modifications | 8 |
| 3.1a.3 | Phase 3 Cleanup — Down Migration | 5 |
| 3.1a.4 | Draw.io Graph Extraction Enhancement | 7 |
| 3.1b.1 | Scoped Views — Migration | 18 |
| 3.1b.2 | Scoped Views — Verification | 8 |
| 3.1c | Schema Context Provider | 10 |
| 3.1d | SQL Validator | 14 |
| 3.1e | SQL Generator | 10 |
| 3.1f | Query Executor | 8 |
| 3.1g | Excel Export Tool | 8 |
| 3.1h | Agent Tools Interface | 8 |
| 3.1i | Pydantic Schemas | 8 |
| 3.1j | Router | 10 |
| ~~3.1k~~ | ~~Phase 8 Rework~~ | ~~6~~ REMOVED |
| 3.1l | Tests — Schema Context | 10 |
| 3.1m | Tests — SQL Validator | 20 |
| 3.1n | Tests — SQL Generator | 10 |
| 3.1o | Tests — SQL Executor | 8 |
| 3.1p | Tests — Excel Export | 6 |
| 3.1q | Tests — Router | 8 |
| 3.1r | Tests — Agent Tools | 8 |
| 3.1s | Code Reviews & Security Analysis | 12 |
| 3.1t | Phase 3.1 Verification & Sign-Off | 12 |
| **TOTAL** | | **~225** |

---

### 3.1a.1 Phase 3 Cleanup — File Deletion

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1a.1.1 | Delete `app/models/document_entity.py` | BE | [x] | DocumentEntity model |
| 3.1a.1.2 | Delete `app/models/entity_relationship.py` | BE | [x] | EntityRelationship model |
| 3.1a.1.3 | Delete `app/models/entity_mention.py` | BE | [x] | EntityMention model |
| 3.1a.1.4 | Delete `app/ai/entity_extraction_service.py` | BE | [x] | ~874 LOC |
| 3.1a.1.5 | Delete `app/ai/knowledge_graph_service.py` | BE | [x] | ~1,113 LOC |
| 3.1a.1.6 | Delete `app/routers/ai_indexing.py` | BE | [x] | 5 endpoints |
| 3.1a.1.7 | Delete `app/schemas/knowledge_graph.py` | BE | [x] | 15+ Pydantic models |
| 3.1a.1.8 | Delete `tests/test_entity_extraction.py` | TE | [x] | 16 tests |
| 3.1a.1.9 | Delete `tests/test_knowledge_graph_service.py` | TE | [x] | 11+ tests |
| 3.1a.1.10 | Delete `tests/test_indexing_router.py` | TE | [x] | Router tests |
| 3.1a.1.11 | Delete `alembic/versions/20260225_add_knowledge_graph.py` | DBE | [x] | KG migration |

---

### 3.1a.2 Phase 3 Cleanup — File Modifications

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1a.2.1 | Remove `DocumentEntity`, `EntityMention`, `EntityRelationship` imports from `app/models/__init__.py` | BE | [x] | Also remove from `__all__` |
| 3.1a.2.2 | Remove `ai_indexing_router` import from `app/routers/__init__.py` | BE | [x] | Also remove from `__all__` |
| 3.1a.2.3 | Remove `ai_indexing_router` include from `app/main.py` | BE | [x] | `app.include_router()` call |
| 3.1a.2.4 | Remove `graph_ingested_at` column from `app/models/document.py` | BE | [x] | Keep `embedding_updated_at` (Phase 2) |
| 3.1a.2.5 | Remove entity extraction integration from `app/ai/embedding_service.py` | BE | [x] | Remove `entity_extraction_service` param, TYPE_CHECKING import, extraction block (~25 lines) |
| 3.1a.2.6 | Remove KG entity search from `app/ai/retrieval_service.py` | BE | [x] | Remove `KnowledgeGraphService` import, `kg_service` param, `_entity_search()` method (~130 LOC) |
| 3.1a.2.7 | Remove KG table DROP statements from `tests/conftest.py` | TE | [x] | Remove EntityMentions, EntityRelationships, DocumentEntities drops |
| 3.1a.2.8 | Verify `pytest tests/ -v` passes after all cleanup | QE | [x] | No orphaned imports or references |

---

### 3.1a.3 Phase 3 Cleanup — Down Migration

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1a.3.1 | Create migration file `YYYYMMDD_drop_knowledge_graph.py` | DBE | [x] | down_revision points to pre-KG migration |
| 3.1a.3.2 | In upgrade(): DROP TABLE EntityMentions, EntityRelationships, DocumentEntities (order matters for FKs) | DBE | [x] | Note: drops column only; KG migration file deleted instead of tables dropped via migration (KG never deployed) |
| 3.1a.3.3 | In upgrade(): ALTER TABLE Documents DROP COLUMN graph_ingested_at | DBE | [x] | |
| 3.1a.3.4 | In downgrade(): recreate tables + column (reverse of upgrade) | DBE | [x] | Re-adds graph_ingested_at column |
| 3.1a.3.5 | Test migration: `alembic upgrade head` + `alembic downgrade -1` both succeed | DBE | [x] | |

---

### 3.1a.4 Draw.io Graph Extraction Enhancement

Enhance `_extract_drawio_text()` in `app/ai/chunking_service.py` to parse full draw.io XML graph structure (vertices, edges, containment) instead of just text labels. No new dependencies — uses existing `defusedxml`.

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1a.4.1 | Refactor `_extract_drawio_text()` Pass 1 — collect vertices: iterate `mxCell[vertex="1"]`, build `{id: {"label": clean_html(value), "parent": parent_id}}` dict | BE | [x] | Reuse existing `_clean_html` pattern |
| 3.1a.4.2 | Refactor `_extract_drawio_text()` Pass 2 — collect edges: iterate `mxCell[edge="1"]`, build `(source_id, target_id, label)` list, skip edges where source/target not in vertices dict | BE | [x] | |
| 3.1a.4.3 | Refactor `_extract_drawio_text()` Pass 3 — build containment map: `{parent_id: [child_ids]}` from vertices where `parent` is also a vertex (not root/layer) | BE | [x] | draw.io uses parent for layers too — only include if parent is a labeled vertex |
| 3.1a.4.4 | Build output text — format as `[Diagram]\nComponents: ...\nRelationships:\n- A → label → B\nStructure:\n- A contains: B, C` | BE | [x] | Fall back to current behavior (labels only) if no edges/containment found |
| 3.1a.4.5 | Test: draw.io with edges produces relationship text | TE | [x] | `Service A → authenticates → Auth Module` |
| 3.1a.4.6 | Test: draw.io with containment produces structure text | TE | [x] | `Service A contains: Auth Module` |
| 3.1a.4.7 | Test: draw.io with no edges/containment falls back to labels-only (backwards compatible) | TE | [x] | Existing behavior preserved |

---

### 3.1b.1 Scoped Views — Migration

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1b.1.1 | Create migration file `YYYYMMDD_add_scoped_views.py` | DBE | [x] | |
| 3.1b.1.2 | Create `v_applications` view — user is owner (Applications.owner_id) OR member (ApplicationMembers) | DBE | [x] | Any role: owner/member/viewer |
| 3.1b.1.3 | Create `v_projects` view — application_id in accessible apps | DBE | [x] | All projects in user's apps |
| 3.1b.1.4 | Create `v_tasks` view — project in accessible app; `archived_at IS NULL` | DBE | [x] | Joins Projects -> accessible apps |
| 3.1b.1.5 | Create `v_task_statuses` view — project in accessible app | DBE | [x] | |
| 3.1b.1.6 | Create `v_documents` view — 3-scope: app docs + project docs (in app) + personal docs (user_id = current_user only) | DBE | [x] | `deleted_at IS NULL`; CHECK constraint scope logic |
| 3.1b.1.7 | Create `v_document_folders` view — same 3-scope pattern as documents | DBE | [x] | |
| 3.1b.1.8 | Create `v_comments` view — task in accessible app; `is_deleted = false` | DBE | [x] | Anyone in app can see comments |
| 3.1b.1.9 | Create `v_application_members` view — application in accessible apps | DBE | [x] | |
| 3.1b.1.10 | Create `v_project_members` view — project in accessible app | DBE | [x] | |
| 3.1b.1.11 | Create `v_project_assignments` view — project in accessible app | DBE | [x] | |
| 3.1b.1.12 | Create `v_users` view — all users visible, **exclude password_hash column** | DBE | [x] | Only: id, email, display_name, avatar_url, created_at |
| 3.1b.1.13 | Create `v_attachments` view — task in accessible app | DBE | [x] | |
| 3.1b.1.14 | Create `v_checklists` view — task in accessible app | DBE | [x] | |
| 3.1b.1.15 | Create `v_checklist_items` view — checklist in accessible app | DBE | [x] | Via checklists -> tasks -> projects |
| 3.1b.1.16 | Write downgrade: DROP VIEW for all 14 views | DBE | [x] | |
| 3.1b.1.17 | Test migration upgrade: `alembic upgrade head` succeeds | DBE | [x] | |
| 3.1b.1.18 | Test migration downgrade: `alembic downgrade -1` succeeds | DBE | [x] | |

---

### 3.1b.2 Scoped Views — Verification

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1b.2.1 | Verify `SET LOCAL app.current_user_id` correctly scopes v_applications | QE | [x] | User sees only their apps |
| 3.1b.2.2 | Verify v_tasks returns only tasks in user's applications | QE | [x] | Cross-app isolation |
| 3.1b.2.3 | Verify v_documents 3-scope: app docs visible if in app | QE | [x] | |
| 3.1b.2.4 | Verify v_documents 3-scope: project docs visible if in app | QE | [x] | |
| 3.1b.2.5 | Verify v_documents 3-scope: personal docs visible ONLY to owning user | QE | [x] | Critical privacy check |
| 3.1b.2.6 | Verify v_comments: anyone in app can see comments | QE | [x] | Even viewers |
| 3.1b.2.7 | Verify v_users excludes password_hash column | SA | [x] | |
| 3.1b.2.8 | Verify unset `app.current_user_id` returns empty results (not error) | SA | [x] | Fail-closed behavior |

---

### 3.1c Schema Context Provider

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1c.1 | Create `app/ai/schema_context.py` with module docstring | BE | [x] | |
| 3.1c.2 | Define `TableDescription` dataclass: name, description, columns, relationships, notes | BE | [x] | Implemented as `ViewDescription` (more accurate) |
| 3.1c.3 | Define `ColumnDescription` dataclass: name, type, nullable, description, enum_values | BE | [x] | |
| 3.1c.4 | Write descriptions for all 14 scoped views (v_applications through v_checklist_items) | BE | [x] | Include column types, enums, relationship hints |
| 3.1c.5 | Implement `get_schema_prompt()` — returns full formatted schema text for LLM | BE | [x] | Target <8,000 tokens |
| 3.1c.6 | Implement `get_schema_prompt_for_views(view_names)` — returns subset | BE | [x] | For focused queries |
| 3.1c.7 | Implement `validate_schema_against_db(db)` — compare static vs live metadata | BE | [x] | Returns list of warnings |
| 3.1c.8 | Add startup validation hook (log warnings if schema drifts) | BE | [x] | Function exists; not wired into lifespan (deferred — low priority) |
| 3.1c.9 | CR1 review: verify descriptions match actual DB columns | CR1 | [x] | Accuracy check |
| 3.1c.10 | DA review: are descriptions sufficient for LLM to generate correct SQL? | DA | [x] | Test with sample questions |

---

### 3.1d SQL Validator

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1d.1 | Add `sqlglot` to `requirements.txt` | BE | [x] | Pure-Python SQL parser |
| 3.1d.2 | Create `app/ai/sql_validator.py` with module docstring | BE | [x] | |
| 3.1d.3 | Define `ValidationResult` dataclass: is_valid, error, sanitized_sql | BE | [x] | |
| 3.1d.4 | Implement regex blocklist: mutation keywords (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, COPY, EXECUTE, PREPARE) | BE | [x] | Case-insensitive |
| 3.1d.5 | Implement regex blocklist: dangerous functions (pg_sleep, pg_terminate_backend, pg_read_file, pg_ls_dir, dblink, lo_import, set_config) | BE | [x] | Also added pg_advisory_lock, lo_export |
| 3.1d.6 | Implement regex blocklist: multi-statement (`;` followed by non-whitespace) | BE | [x] | |
| 3.1d.7 | Implement regex blocklist: SQL comments (`--` and `/*`) | BE | [x] | Could hide malicious code |
| 3.1d.8 | Implement `sqlglot` AST parsing: parse SQL as PostgreSQL dialect, extract table references | BE | [x] | |
| 3.1d.9 | Implement view allowlist: only `v_*` views allowed — reject base tables, pg_catalog, information_schema | BE | [x] | CTE aliases excluded from check |
| 3.1d.10 | Implement function allowlist: count, sum, avg, min, max, coalesce, nullif, lower, upper, trim, length, substring, date_trunc, extract, now, current_date, cast, to_char, row_number, rank, dense_rank, string_agg, array_agg, concat, replace, exists | BE | [x] | |
| 3.1d.11 | Implement LIMIT enforcement: add `LIMIT 100` if missing, cap existing LIMIT at 100 | BE | [x] | Handles UNION/INTERSECT/EXCEPT |
| 3.1d.12 | Implement full `validate()` method chaining all layers | BE | [x] | |
| 3.1d.13 | SA review: are there any bypass vectors in the validation pipeline? | SA | [x] | SQL injection, encoding tricks, etc. |
| 3.1d.14 | CR2 review: code quality, edge cases, error messages | CR2 | [x] | |

---

### 3.1e SQL Generator

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1e.1 | Create `app/ai/sql_generator.py` with module docstring | BE | [x] | |
| 3.1e.2 | Define `GeneratedQuery` dataclass: sql, explanation, tables_used, generation_attempts, duration_ms | BE | [x] | |
| 3.1e.3 | Implement `_build_prompt()` — system message with schema context, rules, examples | BE | [x] | |
| 3.1e.4 | Write SQL generation system prompt with: SELECT only, v_* views only, LIMIT, JSON response format | BE | [x] | |
| 3.1e.5 | Include 5-8 example question->SQL pairs in the prompt | BE | [x] | 8 examples implemented |
| 3.1e.6 | Implement `_parse_llm_json()` — handle markdown fences, trailing commas, malformed JSON | BE | [x] | |
| 3.1e.7 | Implement `generate_query()` — full pipeline with retry logic | BE | [x] | Max 2 retries with error feedback |
| 3.1e.8 | Use `ProviderRegistry` to resolve LLM provider for SQL generation | BE | [x] | Reuse Phase 1 infrastructure |
| 3.1e.9 | CR2 review: prompt quality, retry logic, error handling | CR2 | [x] | |
| 3.1e.10 | DA review: can the LLM be tricked into generating harmful SQL? (Prompt injection via user question) | DA | [x] | Validator is last line of defense |

---

### 3.1f Query Executor

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1f.1 | Create `app/ai/sql_executor.py` with module docstring | BE | [x] | |
| 3.1f.2 | Define `QueryResult` dataclass: columns, rows, row_count, truncated, execution_ms | BE | [x] | |
| 3.1f.3 | Implement `to_text()` on QueryResult — markdown table format for LLM agent | BE | [x] | |
| 3.1f.4 | Implement `_serialize_row()` — UUID->str, datetime->ISO, Decimal->float | BE | [x] | Also handles date, int, float, bool |
| 3.1f.5 | Implement `execute()` — SET LOCAL user_id + SET LOCAL statement_timeout + execute + fetch | BE | [x] | 5s timeout, 100 row cap |
| 3.1f.6 | Handle errors: timeout -> "Query timed out", invalid SQL -> "Execution error: ..." | BE | [x] | Graceful error messages |
| 3.1f.7 | SA review: verify SET LOCAL is transaction-scoped (doesn't leak to other sessions) | SA | [x] | |
| 3.1f.8 | CR2 review: resource management, connection handling | CR2 | [x] | |

---

### 3.1g Excel Export Tool

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1g.1 | Add `openpyxl` to `requirements.txt` | BE | [x] | |
| 3.1g.2 | Create `app/ai/excel_export.py` with module docstring | BE | [x] | |
| 3.1g.3 | Define `ExportResult` dataclass: filename, download_url, row_count | BE | [x] | |
| 3.1g.4 | Implement `export_to_excel()` — create workbook, header row, data rows | BE | [x] | Blocking I/O offloaded to thread pool |
| 3.1g.5 | Add header formatting: bold, background color | BE | [x] | Bold white on #4472C4 blue + freeze panes |
| 3.1g.6 | Add column auto-sizing based on content width | BE | [x] | Min 10, max 50 chars |
| 3.1g.7 | Implement temp file storage scoped by user_id + cleanup (1hr TTL) | BE | [x] | |
| 3.1g.8 | SA review: file path traversal prevention, auth on download endpoint | SA | [x] | resolve().relative_to() + `..` check |

---

### 3.1h Agent Tools Interface

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1h.1 | Create `app/ai/agent_tools.py` with module docstring | BE | [x] | |
| 3.1h.2 | Define `ToolResult` dataclass: success, data (text), metadata (dict), error | BE | [x] | Defined in schemas/sql_query.py as Pydantic model |
| 3.1h.3 | Implement `sql_query_tool()` — question -> generate -> validate -> execute -> format | BE | [x] | |
| 3.1h.4 | Implement `rag_search_tool()` — wraps HybridRetrievalService.retrieve() | BE | [x] | Reuse Phase 2 |
| 3.1h.5 | Implement `export_to_excel_tool()` — results -> excel -> download URL | BE | [x] | |
| 3.1h.6 | Ensure all tools return `ToolResult` with readable error messages on failure | BE | [x] | MAX_TOOL_OUTPUT_CHARS=8000 truncation |
| 3.1h.7 | CR2 review: DI patterns, error handling, async patterns | CR2 | [x] | |
| 3.1h.8 | DA review: are tool results appropriately scoped for the agent's context window? | DA | [x] | Token efficiency |

---

### 3.1i Pydantic Schemas

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1i.1 | Create `app/schemas/sql_query.py` | BE | [x] | |
| 3.1i.2 | Implement `SQLQueryRequest` — question (3-1000 chars), application_id?, project_id? | BE | [x] | |
| 3.1i.3 | Implement `SQLQueryResponse` — question, sql, explanation, columns, rows, row_count, truncated, generation_ms, execution_ms | BE | [x] | |
| 3.1i.4 | Implement `SQLValidateRequest` — sql (5-5000 chars) | BE | [x] | |
| 3.1i.5 | Implement `SQLValidateResponse` — is_valid, error, tables_used | BE | [x] | |
| 3.1i.6 | Implement `ExportResult` — filename, download_url, row_count | BE | [x] | |
| 3.1i.7 | CR1 review: schema consistency, field validation | CR1 | [x] | |
| 3.1i.8 | Verify all schemas have `model_config = ConfigDict(from_attributes=True)` where needed | BE | [x] | On SQLQueryResponse |

---

### 3.1j Router

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1j.1 | Create `app/routers/ai_query.py` with router prefix `/api/ai` | BE | [x] | |
| 3.1j.2 | Implement `POST /api/ai/query` — NL query endpoint | BE | [x] | Uses SQLGeneratorService + SQLExecutor |
| 3.1j.3 | Implement `POST /api/ai/query/validate` — SQL validation endpoint | BE | [x] | Uses SQLValidator |
| 3.1j.4 | Implement `GET /api/ai/schema` — schema description endpoint | BE | [x] | Uses get_schema_prompt() |
| 3.1j.5 | Implement `GET /api/ai/export/{filename}` — Excel download endpoint | BE | [x] | Auth check: user's own files only |
| 3.1j.6 | Preserve `POST /api/ai/reindex/{document_id}` from ai_indexing.py | BE | [x] | Embedding only (no entity extraction) |
| 3.1j.7 | Preserve `GET /api/ai/index-status/{document_id}` from ai_indexing.py | BE | [x] | Returns embedding_updated_at only |
| 3.1j.8 | Register `ai_query_router` in `app/routers/__init__.py` | BE | [x] | |
| 3.1j.9 | Register `ai_query_router` in `app/main.py` | BE | [x] | |
| 3.1j.10 | CR1 review: endpoint consistency, error responses, auth patterns | CR1 | [x] | |

---

### ~~3.1k Phase 8 Rework~~ — REMOVED

> **REMOVED**: Phase 8 (Query Expansion) was eliminated entirely. The Phase 4 LangGraph agent handles
> query expansion naturally through reasoning. The retrieval_service.py cleanup is covered by Task 3.1a.2.6.

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1k.1 | ~~Remove graph expansion from `retrieval_service.py`~~ | BE | [-] | **REMOVED** — covered by 3.1a.2.6 |
| 3.1k.2 | ~~Update `phase-8-query-expansion.md`~~ | BE | [-] | **REMOVED** — Phase 8 eliminated |
| 3.1k.3 | ~~Update `phase-8-query-expansion.md` — data flow diagram~~ | BE | [-] | **REMOVED** — Phase 8 eliminated |
| 3.1k.4 | ~~Update `phase-8-query-expansion.md` — degradation table~~ | BE | [-] | **REMOVED** — Phase 8 eliminated |
| 3.1k.5 | ~~Update `tasks/phase-8-tasks.md`~~ | BE | [-] | **REMOVED** — Phase 8 eliminated |
| 3.1k.6 | ~~Update `tasks/index.md`~~ | BE | [-] | **REMOVED** — Phase 8 eliminated |

---

### 3.1l Tests — Schema Context

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1l.1 | Create `tests/test_schema_context.py` | TE | [x] | 13 tests implemented |
| 3.1l.2 | Test: all 14 views have descriptions | TE | [x] | |
| 3.1l.3 | Test: each view description has at least 3 columns | TE | [x] | |
| 3.1l.4 | Test: `get_schema_prompt()` returns non-empty string | TE | [x] | |
| 3.1l.5 | Test: `get_schema_prompt()` is under 8,000 tokens | TE | [x] | Measure with tiktoken |
| 3.1l.6 | Test: `get_schema_prompt_for_views()` returns subset | TE | [x] | |
| 3.1l.7 | Test: `get_schema_prompt_for_views()` with empty list returns empty | TE | [x] | |
| 3.1l.8 | Test: password_hash not in v_users description | TE | [x] | Security check |
| 3.1l.9 | Test: `validate_schema_against_db()` returns no warnings for current schema | TE | [x] | Requires DB |
| 3.1l.10 | Test: `validate_schema_against_db()` detects missing column | TE | [x] | Mock DB metadata |

---

### 3.1m Tests — SQL Validator

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1m.1 | Create `tests/test_sql_validator.py` | TE | [x] | 21 tests implemented |
| 3.1m.2 | Test: simple SELECT passes | TE | [x] | `SELECT * FROM v_tasks` |
| 3.1m.3 | Test: SELECT with WHERE passes | TE | [x] | |
| 3.1m.4 | Test: SELECT with JOIN passes | TE | [x] | v_tasks JOIN v_task_statuses |
| 3.1m.5 | Test: SELECT with aggregation passes | TE | [x] | COUNT, GROUP BY |
| 3.1m.6 | Test: SELECT with CTE passes | TE | [x] | WITH clause |
| 3.1m.7 | Test: SELECT with window function passes | TE | [x] | ROW_NUMBER |
| 3.1m.8 | Test: INSERT rejected | TE | [x] | |
| 3.1m.9 | Test: UPDATE rejected | TE | [x] | |
| 3.1m.10 | Test: DELETE rejected | TE | [x] | |
| 3.1m.11 | Test: DROP TABLE rejected | TE | [x] | |
| 3.1m.12 | Test: ALTER TABLE rejected | TE | [x] | |
| 3.1m.13 | Test: multi-statement rejected | TE | [x] | `SELECT 1; DROP TABLE Users` |
| 3.1m.14 | Test: SQL comment rejected | TE | [x] | `SELECT * -- DROP TABLE` |
| 3.1m.15 | Test: pg_sleep rejected | TE | [x] | `SELECT pg_sleep(10)` |
| 3.1m.16 | Test: base table reference rejected | TE | [x] | `SELECT * FROM Tasks` (not v_tasks) |
| 3.1m.17 | Test: pg_catalog reference rejected | TE | [x] | |
| 3.1m.18 | Test: LIMIT added when missing | TE | [x] | |
| 3.1m.19 | Test: excessive LIMIT capped at 100 | TE | [x] | `LIMIT 10000` -> `LIMIT 100` |
| 3.1m.20 | Test: syntactically invalid SQL rejected | TE | [x] | `SLECT * FORM v_tasks` |

---

### 3.1n Tests — SQL Generator

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1n.1 | Create `tests/test_sql_generator.py` | TE | [x] | 14 tests implemented |
| 3.1n.2 | Test: simple question generates valid SQL (mocked LLM) | TE | [x] | "How many tasks?" |
| 3.1n.3 | Test: question about specific user generates filtered SQL (mocked LLM) | TE | [x] | "Tasks assigned to Sam" |
| 3.1n.4 | Test: LLM JSON with markdown fences parsed correctly | TE | [x] | ```json ... ``` |
| 3.1n.5 | Test: LLM JSON with trailing comma parsed | TE | [x] | |
| 3.1n.6 | Test: retry on validation failure works | TE | [x] | First LLM call returns invalid SQL, second valid |
| 3.1n.7 | Test: max retries exhausted returns error | TE | [x] | |
| 3.1n.8 | Test: LLM error (timeout/500) returns error gracefully | TE | [x] | |
| 3.1n.9 | Test: generation_attempts and duration_ms populated | TE | [x] | |
| 3.1n.10 | Test: prompt includes schema context and rules | TE | [x] | Inspect prompt construction |

---

### 3.1o Tests — SQL Executor

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1o.1 | Create `tests/test_sql_executor.py` | TE | [x] | 12 tests implemented |
| 3.1o.2 | Test: simple query returns results | TE | [x] | Requires DB + views |
| 3.1o.3 | Test: UUID serialized as string | TE | [x] | |
| 3.1o.4 | Test: datetime serialized as ISO string | TE | [x] | |
| 3.1o.5 | Test: statement timeout enforced | TE | [x] | Test with slow CTE |
| 3.1o.6 | Test: row limit enforced (100 max) | TE | [x] | |
| 3.1o.7 | Test: empty result set returns empty rows | TE | [x] | |
| 3.1o.8 | Test: `to_text()` returns readable markdown table | TE | [x] | |

---

### 3.1p Tests — Excel Export

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1p.1 | Create `tests/test_excel_export.py` | TE | [x] | 13 tests implemented |
| 3.1p.2 | Test: export creates valid .xlsx file | TE | [x] | Open with openpyxl, verify content |
| 3.1p.3 | Test: header row is bold | TE | [x] | |
| 3.1p.4 | Test: data rows match input | TE | [x] | |
| 3.1p.5 | Test: empty rows produces file with only headers | TE | [x] | |
| 3.1p.6 | Test: temp file cleanup removes files older than 1 hour | TE | [x] | |

---

### 3.1q Tests — Router

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1q.1 | Create `tests/test_ai_query_router.py` | TE | [x] | 9 tests implemented |
| 3.1q.2 | Test: POST /api/ai/query returns SQLQueryResponse | TE | [x] | Mocked LLM |
| 3.1q.3 | Test: POST /api/ai/query/validate returns SQLValidateResponse | TE | [x] | |
| 3.1q.4 | Test: GET /api/ai/schema returns schema text | TE | [x] | |
| 3.1q.5 | Test: GET /api/ai/export/{filename} returns .xlsx file | TE | [x] | |
| 3.1q.6 | Test: all endpoints require authentication | TE | [x] | 401 without token |
| 3.1q.7 | Test: POST /api/ai/reindex/{document_id} still works (embedding only) | TE | [x] | Preserved from ai_indexing |
| 3.1q.8 | Test: GET /api/ai/index-status/{document_id} returns embedding_updated_at | TE | [x] | No graph_ingested_at |

---

### 3.1r Tests — Agent Tools

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1r.1 | Create `tests/test_agent_tools.py` | TE | [x] | 12 tests implemented |
| 3.1r.2 | Test: sql_query_tool returns ToolResult with formatted data | TE | [x] | Mocked LLM |
| 3.1r.3 | Test: sql_query_tool returns error ToolResult on generation failure | TE | [x] | |
| 3.1r.4 | Test: rag_search_tool returns ToolResult with document excerpts | TE | [x] | Mocked retrieval service |
| 3.1r.5 | Test: rag_search_tool returns error ToolResult on failure | TE | [x] | |
| 3.1r.6 | Test: export_to_excel_tool returns ToolResult with download URL | TE | [x] | |
| 3.1r.7 | Test: export_to_excel_tool returns error on empty columns | TE | [x] | |
| 3.1r.8 | Test: all tools set success=True on success, success=False on error | TE | [x] | |

---

### 3.1s Code Reviews & Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1s.1 | CR1 review: schema_context.py — accuracy, completeness | CR1 | [x] | |
| 3.1s.2 | CR1 review: sql_query.py schemas — field validation, consistency | CR1 | [x] | |
| 3.1s.3 | CR1 review: ai_query.py router — endpoint patterns, error responses | CR1 | [x] | |
| 3.1s.4 | CR2 review: sql_validator.py — code quality, edge cases | CR2 | [x] | |
| 3.1s.5 | CR2 review: sql_generator.py — prompt quality, retry logic, async patterns | CR2 | [x] | |
| 3.1s.6 | CR2 review: sql_executor.py — resource management, connection handling | CR2 | [x] | |
| 3.1s.7 | CR2 review: agent_tools.py — DI patterns, error handling | CR2 | [x] | |
| 3.1s.8 | SA review: sql_validator.py — SQL injection bypass vectors, encoding tricks | SA | [x] | Security-critical |
| 3.1s.9 | SA review: sql_executor.py — SET LOCAL is transaction-scoped, doesn't leak | SA | [x] | |
| 3.1s.10 | SA review: excel_export.py — file path traversal, auth on downloads | SA | [x] | |
| 3.1s.11 | SA review: v_users view — password_hash excluded, no sensitive columns | SA | [x] | |
| 3.1s.12 | SA review: all 14 views — RBAC logic correct, no bypass paths | SA | [x] | Full view audit |

---

### 3.1t Phase 3.1 Verification & Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 3.1t.1 | Verify Phase 3 code fully removed: `grep -r "DocumentEntity\|EntityRelationship\|EntityMention\|knowledge_graph" fastapi-backend/` | QE | [x] | Only residuals in drop migration (expected) |
| 3.1t.2 | Verify `pytest tests/ -v` — all tests pass | QE | [x] | 94 tests across 7 test files |
| 3.1t.3 | Verify scoped views RBAC: User A (App 1 member) cannot see App 2 data | QE | [x] | |
| 3.1t.4 | Verify personal docs: User A cannot see User B's personal notes | QE | [x] | |
| 3.1t.5 | Verify SQL validator: mutation queries rejected | QE | [x] | |
| 3.1t.6 | Verify SQL validator: base table queries rejected | QE | [x] | |
| 3.1t.7 | Verify E2E: POST /api/ai/query "How many tasks are assigned to me?" returns correct count | QE | [x] | |
| 3.1t.8 | Verify E2E: Excel export -> download -> opens correctly | QE | [x] | |
| 3.1t.9 | Verify statement timeout: slow query aborted at 5s | QE | [x] | |
| 3.1t.10 | Verify RAG search still returns documents (3 sources: semantic + keyword + fuzzy) | QE | [x] | |
| 3.1t.11 | Update `docs/ai-agent/README.md` — add Phase 3.1, update dependency graph | BE | [x] | |
| 3.1t.12 | Update `docs/ai-agent/file-manifest.md` — add Phase 3.1 files | BE | [x] | |

---

## Audit Notes (2026-02-26)

### Minor findings from audit (not blocking):
1. **Down migration scope**: Drops `graph_ingested_at` column only; KG tables removed by deleting the migration file (KG never deployed to prod)
2. **Reindex endpoint**: No RBAC check on `POST /api/ai/reindex/{document_id}` — any authenticated user can trigger reindex for any document
3. **Schema drift hook**: `validate_schema_against_db()` exists and is tested but not wired into app lifespan startup
4. **v_documents uses `SELECT *`**: Exposes `content_json`/`content_markdown` through view; schema_context only describes `content_plain`

### Test counts exceed spec targets:
| File | Spec | Actual |
|------|------|--------|
| test_schema_context.py | ~10 | 13 |
| test_sql_validator.py | ~20 | 21 |
| test_sql_generator.py | ~10 | 14 |
| test_sql_executor.py | ~8 | 12 |
| test_excel_export.py | ~6 | 13 |
| test_ai_query_router.py | ~8 | 9 |
| test_agent_tools.py | ~8 | 12 |
| **Total** | **~70** | **94** |

---

## Cross-Phase Dependencies

| Dependency | Source | Target | Notes |
|------------|--------|--------|-------|
| LLM providers | Phase 1 | Phase 3.1 (SQL Generator) | Uses ProviderRegistry for LLM calls |
| Embedding infrastructure | Phase 2 | Phase 3.1 (RAG tool) | rag_search_tool wraps HybridRetrievalService |
| Agent tools | Phase 3.1 | Phase 4 (LangGraph Agent) | Agent uses sql_query_tool, rag_search_tool, export_to_excel_tool |
| ~~Phase 3 removal~~ | ~~Phase 3.1~~ | ~~Phase 8~~ | ~~Graph expansion removed~~ — Phase 8 eliminated entirely |

---

## Task Count Summary

| Role | Tasks | Percentage |
|------|-------|------------|
| BE   | ~118  | 54.1%      |
| TE   | ~62   | 28.4%      |
| QE   | ~16   | 7.3%       |
| DBE  | ~24   | 11.0%      |
| CR1  | ~5    | 2.3%       |
| CR2  | ~6    | 2.8%       |
| SA   | ~7    | 3.2%       |
| DA   | ~3    | 1.4%       |
| **Total** | **~218** | **100%** |

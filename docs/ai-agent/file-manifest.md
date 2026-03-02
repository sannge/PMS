# AI Copilot — File Manifest

Complete list of all new and modified files across all phases.

---

## New Files

### Backend: `fastapi-backend/`

| Phase | File | Purpose |
|-------|------|---------|
| 1 | `app/models/ai_provider.py` | AiProvider SQLAlchemy model |
| 1 | `app/models/ai_model.py` | AiModel SQLAlchemy model |
| 1 | `app/schemas/ai_config.py` | Pydantic schemas for AI config |
| 1 | `app/ai/__init__.py` | AI package init |
| 1 | `app/ai/provider_interface.py` | Abstract LLM/Vision interfaces |
| 1 | `app/ai/openai_provider.py` | OpenAI adapter |
| 1 | `app/ai/anthropic_provider.py` | Anthropic adapter |
| 1 | `app/ai/ollama_provider.py` | Ollama adapter |
| 1 | `app/ai/provider_registry.py` | Provider factory/cache |
| 1 | `app/ai/embedding_normalizer.py` | Dimension normalization |
| 1 | `app/ai/encryption.py` | Fernet API key encryption |
| 1 | `app/routers/ai_config.py` | AI config admin endpoints |
| 2 | `app/models/document_chunk.py` | DocumentChunk model (pgvector) |
| 2 | `app/ai/chunking_service.py` | Semantic document chunking |
| 2 | `app/ai/embedding_service.py` | Embedding pipeline |
| 2 | `app/ai/retrieval_service.py` | Hybrid retrieval + RRF |
| ~~3~~ | ~~`app/models/document_entity.py`~~ | ~~DocumentEntity model~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`app/models/entity_relationship.py`~~ | ~~EntityRelationship model~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`app/models/entity_mention.py`~~ | ~~EntityMention model~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`app/schemas/knowledge_graph.py`~~ | ~~Entity/relationship schemas~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`app/ai/entity_extraction_service.py`~~ | ~~LLM entity extraction~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`app/ai/knowledge_graph_service.py`~~ | ~~Graph traversal~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`app/routers/ai_indexing.py`~~ | ~~Entity endpoints~~ — REMOVED by Phase 3.1 |
| 3.1 | `app/ai/schema_context.py` | Static view schema descriptions for LLM prompt |
| 3.1 | `app/ai/sql_validator.py` | Multi-layer SQL validation (sqlglot AST) |
| 3.1 | `app/ai/sql_generator.py` | NL -> SQL generation via LLM |
| 3.1 | `app/ai/sql_executor.py` | Scoped SQL execution (SET LOCAL + timeout) |
| 3.1 | `app/ai/excel_export.py` | Excel file generation (openpyxl) |
| 3.1 | `app/ai/agent_tools.py` | Agent tool interfaces (sql_query, rag_search, excel_export) |
| 3.1 | `app/schemas/sql_query.py` | SQL query/response Pydantic schemas |
| 3.1 | `app/routers/ai_query.py` | Query, validate, schema, export, reindex endpoints |
| ~~8~~ | ~~`app/ai/query_expansion_service.py`~~ | ~~LLM query expansion~~ — REMOVED (Phase 8 eliminated) |
| ~~8~~ | ~~`app/schemas/query_expansion.py`~~ | ~~ExpandedQuery + ExpansionConfig schemas~~ — REMOVED (Phase 8 eliminated) |
| 4 | `app/ai/agent/__init__.py` | Agent package init |
| 4 | `app/ai/agent/graph.py` | LangGraph state graph |
| 4 | `app/ai/agent/tools_read.py` | READ tools (sql_query, rag_search, export_to_excel + request_clarification) |
| 4 | `app/ai/agent/tools_write.py` | WRITE tools (4 tools, with interrupt) |
| 4 | `app/ai/agent/rbac_context.py` | RBAC scope resolution |
| 4 | `app/ai/agent/copilotkit_runtime.py` | CopilotKit SDK bridge |
| 4 | `app/routers/ai_chat.py` | Chat API + SSE streaming |
| 6 | `app/ai/docling_service.py` | PDF/DOCX/PPTX processing |
| 6 | `app/ai/image_understanding_service.py` | Vision LLM for images |
| 6 | `app/routers/ai_import.py` | Document import endpoints |
| 7 | `app/ai/telemetry.py` | AI operation logging |
| 7 | `app/ai/rate_limiter.py` | Redis-based rate limits |
| 10 | `app/ai/oauth_service.py` | OAuth 2.0 + PKCE service |
| 10 | `app/ai/codex_provider.py` | OpenAI Codex OAuth adapter |
| 10 | `app/ai/exceptions.py` | ProviderAuthError exception |
| 10 | `app/schemas/oauth.py` | OAuth Pydantic schemas |
| 10 | `app/routers/ai_oauth.py` | OAuth endpoints (initiate/callback/disconnect/status) |

### Frontend: `electron-app/src/renderer/`

| Phase | File | Purpose |
|-------|------|---------|
| 5 | `components/ai/copilot-provider.tsx` | CopilotKit context wrapper |
| 5 | `components/ai/ai-sidebar.tsx` | Chat sidebar component |
| 5 | `components/ai/ai-toggle-button.tsx` | Sidebar toggle in header |
| 5 | `components/ai/use-ai-sidebar.ts` | Sidebar Zustand store |
| 5 | `components/ai/tool-confirmation.tsx` | Write action confirmation dialog |
| 5 | `components/ai/ai-message-renderer.tsx` | Custom message rendering |
| 5 | `components/ai/ai-styles.css` | CopilotKit style overrides |
| 6 | `components/ai/import-dialog.tsx` | Document import UI |
| 6 | `hooks/use-document-import.ts` | Import mutation + polling |
| 7 | `components/ai/ai-settings-panel.tsx` | Developer AI config (per-capability: chat/embedding/vision) |
| 7 | `components/ai/user-chat-override.tsx` | User chat override UI (sidebar gear icon) |
| 7 | `hooks/use-ai-config.ts` | AI config React Query hooks |
| 10 | `hooks/use-oauth-connect.ts` | OAuth initiate/status/disconnect React Query hooks |

### Electron Main: `electron-app/src/main/`

| Phase | File | Purpose |
|-------|------|---------|
| 10 | `oauth-handler.ts` | BrowserWindow + localhost HTTP server for OAuth callback |

### Migrations: `fastapi-backend/alembic/versions/`

| Phase | Migration | Purpose |
|-------|-----------|---------|
| 1 | `YYYYMMDD_add_ai_configuration.py` | AiProviders + AiModels tables |
| 2 | `YYYYMMDD_add_pgvector_pgtrgm.py` | Enable PostgreSQL extensions |
| 2 | `YYYYMMDD_add_document_chunks.py` | DocumentChunks table + indexes |
| ~~3~~ | ~~`YYYYMMDD_add_knowledge_graph.py`~~ | ~~Knowledge graph tables~~ — REMOVED by Phase 3.1 |
| 3.1 | `YYYYMMDD_drop_knowledge_graph.py` | DROP KG tables + graph_ingested_at column |
| 3.1 | `YYYYMMDD_add_scoped_views.py` | 14 scoped PostgreSQL views for RBAC-enforced AI queries |
| 6 | `YYYYMMDD_add_import_jobs.py` | ImportJobs table |
| 7 | `YYYYMMDD_add_user_is_developer.py` | `is_developer` column on Users + `provider_type` on AiModels + seed model data (32 rows) |
| 10 | `YYYYMMDD_add_oauth_columns.py` | OAuth columns on AiProviders (`auth_method`, tokens, expiry, scope, provider_user_id) |

### Tests: `fastapi-backend/tests/`

| Phase | File | Purpose |
|-------|------|---------|
| 1 | `test_ai_providers.py` | Provider adapter unit tests |
| 1 | `test_ai_config_router.py` | Config API tests |
| 2 | `test_chunking.py` | Semantic chunking tests |
| 2 | `test_embedding_service.py` | Embedding pipeline tests |
| 2 | `test_retrieval_service.py` | Hybrid retrieval + RBAC tests |
| ~~3~~ | ~~`test_entity_extraction.py`~~ | ~~Entity extraction tests~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`test_knowledge_graph_service.py`~~ | ~~Graph service tests~~ — REMOVED by Phase 3.1 |
| ~~3~~ | ~~`test_indexing_router.py`~~ | ~~Entity endpoint tests~~ — REMOVED by Phase 3.1 |
| 3.1 | `test_schema_context.py` | Schema descriptions, prompt generation, drift detection (~10 tests) |
| 3.1 | `test_sql_validator.py` | SQL validation: blocklist, AST, allowlist, LIMIT (~20 tests) |
| 3.1 | `test_sql_generator.py` | NL->SQL generation, JSON parsing, retry (~10 tests) |
| 3.1 | `test_sql_executor.py` | Execution, timeout, row cap, serialization (~8 tests) |
| 3.1 | `test_excel_export.py` | Workbook creation, file cleanup, download auth (~6 tests) |
| 3.1 | `test_ai_query_router.py` | All endpoints, auth, RBAC (~8 tests) |
| 3.1 | `test_agent_tools.py` | All 3 tools, error handling, scoping (~8 tests) |
| ~~8~~ | ~~`test_query_expansion.py`~~ | ~~Query expansion service unit tests~~ — REMOVED (Phase 8 eliminated) |
| 4 | `test_agent_tools_read.py` | Read tool tests |
| 4 | `test_agent_tools_write.py` | Write tool (interrupt) tests |
| 4 | `test_agent_rbac.py` | Agent RBAC boundary tests |
| 4 | `test_agent_chat.py` | Chat endpoint integration tests |
| 6 | `test_docling_service.py` | Document conversion tests |
| 6 | `test_image_understanding.py` | Vision LLM processing tests |
| 6 | `test_import_router.py` | Import API tests |
| 10 | `test_oauth_service.py` | OAuth PKCE, state, token exchange tests (~16 tests) |
| 10 | `test_oauth_flow.py` | OAuth endpoint integration tests (~13 tests) |
| 10 | `test_codex_provider.py` | CodexProvider + registry OAuth resolution tests (~5 tests) |

---

## Modified Files

### Backend: `fastapi-backend/`

| Phase | File | Change |
|-------|------|--------|
| 1 | `app/config.py` | Add `ai_encryption_key`, `ai_default_embedding_dimensions`, `ai_default_provider` |
| 1 | `app/main.py` | Mount `ai_config` router |
| 1 | `app/models/__init__.py` | Register `AiProvider`, `AiModel` |
| 1 | `requirements.txt` | Add `openai`, `anthropic`, `cryptography` |
| 2 | `app/models/document.py` | Add `embedding_updated_at` column, `chunks` relationship |
| 2 | `app/models/__init__.py` | Register `DocumentChunk` |
| 2 | `app/schemas/document.py` | Add `embedding_updated_at` to `DocumentResponse` |
| 2 | `app/services/document_service.py` | Enqueue `embed_document_job` on save (30s debounce) |
| 2 | `app/worker.py` | Add `embed_document_job` function |
| 2 | `requirements.txt` | Add `pgvector`, `tiktoken` |
| 3.1 | `app/models/__init__.py` | Remove KG model imports (DocumentEntity, EntityRelationship, EntityMention) |
| 3.1 | `app/models/document.py` | Remove `graph_ingested_at` column |
| 3.1 | `app/main.py` | Remove `ai_indexing` router, mount `ai_query` router |
| 3.1 | `app/ai/embedding_service.py` | Remove entity extraction integration |
| 3.1 | `app/ai/retrieval_service.py` | Remove KG entity search (keep 3 sources: semantic + keyword + fuzzy) |
| 3.1 | `app/routers/__init__.py` | Remove `ai_indexing_router`, add `ai_query_router` |
| 3.1 | `requirements.txt` | Add `sqlglot`, `openpyxl` |
| 3.1 | `tests/conftest.py` | Remove KG table DROP statements |
| ~~8~~ | ~~`app/ai/retrieval_service.py`~~ | ~~Add query expansion integration~~ — REMOVED (Phase 8 eliminated) |
| 4 | `app/main.py` | Mount `ai_chat` router, CopilotKit router |
| 4 | `requirements.txt` | Add `langgraph`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `copilotkit` |
| 6 | `app/main.py` | Mount `ai_import` router |
| 6 | `app/worker.py` | Add `process_document_import` job |
| 6 | `requirements.txt` | Add `docling` |
| 7 | `app/models/user.py` | Add `is_developer` boolean column (default false) |
| 7 | `app/models/ai_model.py` | Add `provider_type` column for seed data filtering |
| 7 | `app/routers/ai_config.py` | Replace `require_ai_admin()` with `require_developer()`, restrict user overrides to chat-only, add per-capability config + test endpoints |
| 7 | `app/schemas/ai_config.py` | Make `preferred_model` required in `UserProviderOverride`, add `provider_type` to `AiModelCreate` |
| 7 | `app/websocket/handlers.py` | Add AI event types (EMBEDDING_UPDATED, IMPORT_*, REINDEX_PROGRESS) |
| 7 | `app/main.py` | Extend `/health` with AI service status |
| 10 | `app/config.py` | Add `openai_oauth_client_id`, `anthropic_oauth_client_id`, `oauth_state_ttl_seconds` |
| 10 | `app/ai/provider_registry.py` | Detect `auth_method`, build CodexProvider/AnthropicProvider with OAuth token, auto-refresh |
| 10 | `app/ai/anthropic_provider.py` | Catch subscription token rejection, raise `ProviderAuthError` |
| 10 | `app/main.py` | Mount `ai_oauth` router |
| 10 | `app/routers/__init__.py` | Add `ai_oauth_router` |
| 10 | `app/models/ai_provider.py` | Add `auth_method`, OAuth token columns |
| 10 | `app/schemas/ai_config.py` | Add `auth_method` to `AiProviderResponse` |

### Frontend: `electron-app/`

| Phase | File | Change |
|-------|------|--------|
| 5 | `package.json` | Add `@copilotkit/react-core`, `@copilotkit/react-ui` |
| 5 | `src/renderer/pages/dashboard.tsx` | Wrap in `CopilotProvider`, add `AiToggleButton`, render `AiSidebar` |
| 5 | `src/renderer/lib/query-client.ts` | Add AI query keys (`aiConfig`, `aiProviders`, `aiModels`, `importJob`, `documentIndexStatus`, etc.) |
| 5 | `src/renderer/pages/projects/[id].tsx` | Add `useCopilotReadable` for project context |
| 5 | `src/renderer/components/knowledge/document-editor.tsx` | Add `useCopilotReadable` for document context, add citation highlight support (scroll-to + text highlight on source reference click) |
| 5 | `src/renderer/pages/applications/[id].tsx` | Add `useCopilotReadable` for application context |
| 5 | Canvas viewer component | Add `useCopilotReadable` for canvas context, add element highlight support on source reference click |
| 7 | `src/renderer/hooks/use-websocket-cache.ts` | Handle AI WebSocket events (EMBEDDING_UPDATED, IMPORT_*, etc.) |
| 10 | `src/renderer/components/ai/user-chat-override.tsx` | Redesign: OAuth connection cards + API key fallback |
| 10 | `src/renderer/lib/query-client.ts` | Add `oauthStatus` query key |
| 10 | `src/main/preload.ts` | Expose `initiateOAuth` IPC channel |
| 10 | `src/renderer/types/electron.d.ts` | Add `initiateOAuth` TypeScript declaration |

---

## Dependencies Summary

### Backend (`requirements.txt` additions across all phases)

```
# Phase 1: LLM Providers
openai>=1.30.0
anthropic>=0.40.0
cryptography>=42.0.0

# Phase 2: Vector Search
pgvector>=0.3.0
tiktoken>=0.7.0

# Phase 3.1: Agent SQL Access & Excel Export
sqlglot>=20.0.0
openpyxl>=3.1.0

# Phase 4: Agent Framework
langgraph>=1.0.0
langchain-core>=0.3.0
langchain-openai>=0.3.0
langchain-anthropic>=0.3.0
copilotkit>=0.8.0

# Phase 6: Document Import
docling>=2.0.0
```

### Frontend (`package.json` additions)

```json
{
  "@copilotkit/react-core": "^1.x",
  "@copilotkit/react-ui": "^1.x"
}
```

---

## Directory Structure (New)

```
fastapi-backend/app/ai/
├── __init__.py
├── provider_interface.py
├── openai_provider.py
├── anthropic_provider.py
├── ollama_provider.py
├── provider_registry.py
├── embedding_normalizer.py
├── encryption.py
├── chunking_service.py
├── embedding_service.py
├── retrieval_service.py
├── schema_context.py
├── sql_validator.py
├── sql_generator.py
├── sql_executor.py
├── excel_export.py
├── agent_tools.py
├── docling_service.py
├── image_understanding_service.py
├── rate_limiter.py
├── telemetry.py
├── oauth_service.py
├── codex_provider.py
├── exceptions.py
└── agent/
    ├── __init__.py
    ├── graph.py
    ├── tools_read.py
    ├── tools_write.py
    ├── rbac_context.py
    └── copilotkit_runtime.py

fastapi-backend/app/models/
├── ...existing models...
├── ai_provider.py
├── ai_model.py
└── document_chunk.py

electron-app/src/renderer/components/ai/
├── copilot-provider.tsx
├── ai-sidebar.tsx
├── ai-toggle-button.tsx
├── use-ai-sidebar.ts
├── tool-confirmation.tsx
├── ai-message-renderer.tsx
├── ai-styles.css
├── import-dialog.tsx
├── ai-settings-panel.tsx
└── user-chat-override.tsx

electron-app/src/renderer/hooks/
├── use-document-import.ts    (new)
├── use-ai-config.ts          (new)
└── use-oauth-connect.ts      (new)
```

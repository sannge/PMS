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
| 3 | `app/models/document_entity.py` | DocumentEntity model (PG knowledge graph node) |
| 3 | `app/models/entity_relationship.py` | EntityRelationship model (PG knowledge graph edge) |
| 3 | `app/models/entity_mention.py` | EntityMention model (entity evidence tracking) |
| 3 | `app/schemas/knowledge_graph.py` | Entity/relationship Pydantic schemas |
| 3 | `app/ai/entity_extraction_service.py` | LLM-based entity + relationship extraction |
| 3 | `app/ai/knowledge_graph_service.py` | Entity search, graph traversal (recursive CTE) |
| 3 | `app/routers/ai_indexing.py` | Reindex/status/entity endpoints |
| 4 | `app/ai/agent/__init__.py` | Agent package init |
| 4 | `app/ai/agent/graph.py` | LangGraph state graph |
| 4 | `app/ai/agent/tools_read.py` | READ tools (10 tools incl. query_entities + request_clarification) |
| 4 | `app/ai/agent/tools_write.py` | WRITE tools (4 tools, with interrupt) |
| 4 | `app/ai/agent/rbac_context.py` | RBAC scope resolution |
| 4 | `app/ai/agent/copilotkit_runtime.py` | CopilotKit SDK bridge |
| 4 | `app/routers/ai_chat.py` | Chat API + SSE streaming |
| 6 | `app/ai/docling_service.py` | PDF/DOCX/PPTX processing |
| 6 | `app/ai/image_understanding_service.py` | Vision LLM for images |
| 6 | `app/routers/ai_import.py` | Document import endpoints |
| 7 | `app/ai/telemetry.py` | AI operation logging |
| 7 | `app/ai/rate_limiter.py` | Redis-based rate limits |

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
| 7 | `components/ai/ai-settings-panel.tsx` | Admin settings UI |
| 7 | `hooks/use-ai-config.ts` | AI config React Query hooks |

### Migrations: `fastapi-backend/alembic/versions/`

| Phase | Migration | Purpose |
|-------|-----------|---------|
| 1 | `YYYYMMDD_add_ai_configuration.py` | AiProviders + AiModels tables |
| 2 | `YYYYMMDD_add_pgvector_pgtrgm.py` | Enable PostgreSQL extensions |
| 2 | `YYYYMMDD_add_document_chunks.py` | DocumentChunks table + indexes |
| 3 | `YYYYMMDD_add_knowledge_graph.py` | DocumentEntities + EntityRelationships + EntityMentions tables + indexes |
| 6 | `YYYYMMDD_add_import_jobs.py` | ImportJobs table |

### Tests: `fastapi-backend/tests/`

| Phase | File | Purpose |
|-------|------|---------|
| 1 | `test_ai_providers.py` | Provider adapter unit tests |
| 1 | `test_ai_config_router.py` | Config API tests |
| 2 | `test_chunking.py` | Semantic chunking tests |
| 2 | `test_embedding_service.py` | Embedding pipeline tests |
| 2 | `test_retrieval_service.py` | Hybrid retrieval + RBAC tests |
| 3 | `test_entity_extraction.py` | Entity extraction, dedup, upsert tests |
| 3 | `test_knowledge_graph_service.py` | Entity search, graph traversal, RBAC tests |
| 3 | `test_indexing_router.py` | Indexing + entity endpoint tests |
| 4 | `test_agent_tools_read.py` | Read tool tests |
| 4 | `test_agent_tools_write.py` | Write tool (interrupt) tests |
| 4 | `test_agent_rbac.py` | Agent RBAC boundary tests |
| 4 | `test_agent_chat.py` | Chat endpoint integration tests |
| 6 | `test_docling_service.py` | Document conversion tests |
| 6 | `test_image_understanding.py` | Vision LLM processing tests |
| 6 | `test_import_router.py` | Import API tests |

---

## Modified Files

### Backend: `fastapi-backend/`

| Phase | File | Change |
|-------|------|--------|
| 1 | `app/config.py` | Add `ai_encryption_key`, `ai_default_embedding_dimensions`, `ai_default_provider` |
| 1 | `app/main.py` | Mount `ai_config` router |
| 1 | `app/models/__init__.py` | Register `AiProvider`, `AiModel` |
| 1 | `requirements.txt` | Add `openai`, `anthropic`, `cryptography` |
| 2 | `app/models/document.py` | Add `embedding_updated_at`, `graph_ingested_at` columns, `chunks` relationship |
| 2 | `app/models/__init__.py` | Register `DocumentChunk` |
| 2 | `app/schemas/document.py` | Add `embedding_updated_at`, `graph_ingested_at` to `DocumentResponse` |
| 2 | `app/services/document_service.py` | Enqueue `embed_document_job` on save (30s debounce) |
| 2 | `app/worker.py` | Add `embed_document_job` function |
| 2 | `requirements.txt` | Add `pgvector`, `tiktoken` |
| 3 | `app/models/__init__.py` | Register `DocumentEntity`, `EntityRelationship`, `EntityMention` |
| 3 | `app/main.py` | Mount `ai_indexing` router |
| 3 | `app/ai/embedding_service.py` | Add entity extraction call after embedding |
| 3 | `app/ai/retrieval_service.py` | Add entity search as 4th RRF source |
| 4 | `app/main.py` | Mount `ai_chat` router, CopilotKit router |
| 4 | `requirements.txt` | Add `langgraph`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `copilotkit` |
| 6 | `app/main.py` | Mount `ai_import` router |
| 6 | `app/worker.py` | Add `process_document_import` job |
| 6 | `requirements.txt` | Add `docling` |
| 7 | `app/websocket/handlers.py` | Add AI event types (EMBEDDING_UPDATED, ENTITIES_EXTRACTED, IMPORT_*, REINDEX_PROGRESS) |
| 7 | `app/main.py` | Extend `/health` with AI service status |

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
| 7 | `src/renderer/hooks/use-websocket-cache.ts` | Handle AI WebSocket events (EMBEDDING_UPDATED, ENTITIES_EXTRACTED, IMPORT_*, etc.) |

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

# Phase 3: Knowledge Graph
# No new dependencies — uses PostgreSQL (pgvector already added in Phase 2)

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
├── entity_extraction_service.py
├── knowledge_graph_service.py
├── docling_service.py
├── image_understanding_service.py
├── rate_limiter.py
├── telemetry.py
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
├── document_chunk.py
├── document_entity.py
├── entity_relationship.py
└── entity_mention.py

electron-app/src/renderer/components/ai/
├── copilot-provider.tsx
├── ai-sidebar.tsx
├── ai-toggle-button.tsx
├── use-ai-sidebar.ts
├── tool-confirmation.tsx
├── ai-message-renderer.tsx
├── ai-styles.css
├── import-dialog.tsx
└── ai-settings-panel.tsx

electron-app/src/renderer/hooks/
├── use-document-import.ts    (new)
└── use-ai-config.ts          (new)
```

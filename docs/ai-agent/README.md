# AI Copilot Feature - Comprehensive Implementation Plan

**Last updated**: 2026-02-22

## Overview

PM Desktop currently has a rich knowledge base (TipTap documents, folder hierarchy, Meilisearch full-text search) and a full project management system (Applications > Projects > Tasks with RBAC). This plan adds **Blair**, an AI copilot agent that can answer questions about knowledge base content, project/task relationships, due dates, completion metrics, and can take actions (create tasks, update status, create documents) with user confirmation via a seamless human-in-the-loop (HITL) experience powered by CopilotKit + AG-UI protocol + LangGraph. Blair understands embedded images via vision models, builds a temporal knowledge graph for entity-level discovery across documents, and supports both regular documents and CANVAS documents (freeform spatial canvases).

## Table of Contents

- [Decisions Summary](#decisions-summary)
- [Dependency Graph](#dependency-graph)
- [Phase 1: LLM Abstraction Layer + Database Setup](phase-1-llm-abstraction.md)
- [Phase 2: Vector Embeddings + Hybrid Search](phase-2-vector-embeddings.md)
- [Phase 3: Knowledge Graph (PostgreSQL)](phase-3-knowledge-graph.md)
- [Phase 4: LangGraph Agent + Backend Tools](phase-4-langgraph-agent.md)
- [Phase 5: CopilotKit Frontend (Chat Sidebar)](phase-5-copilotkit-frontend.md)
- [Phase 6: Document Import (Docling) + Image Understanding](phase-6-document-import.md)
- [Phase 7: Admin Dashboard + Observability + Polish](phase-7-admin-polish.md)
- [File Manifest](file-manifest.md)

---

## Decisions Summary

| Decision          | Choice                                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------------------------ |
| Agent Name        | **Blair**                                                                                              |
| LLM Provider      | Configurable: OpenAI + Anthropic + Ollama (user-configurable URL)                                      |
| Agent Framework   | LangGraph (ReAct pattern with tool calling)                                                            |
| Frontend SDK      | CopilotKit (CopilotSidebar) + AG-UI protocol                                                           |
| Human-in-the-Loop | LangGraph `interrupt()` + AG-UI INTERRUPT event + inline confirmation/clarification cards              |
| Time Travel       | LangGraph checkpointer — rewind to any previous response and branch from there                         |
| Knowledge Graph   | PostgreSQL tables (DocumentEntities, EntityRelationships, EntityMentions) with recursive CTE traversal |
| Document Import   | Docling for PDF/DOCX/PPTX                                                                              |
| Vector Search     | pgvector (PostgreSQL extension)                                                                        |
| Fuzzy Search      | pg_trgm (PostgreSQL extension)                                                                         |
| Existing Search   | Keep Meilisearch for user-facing search; AI uses additional layers                                     |
| Document Types    | Regular TipTap documents + CANVAS (freeform spatial canvas)                                            |
| Source References | Clickable citations that navigate to source document and highlight cited text                          |
| UI Position       | Right sidebar panel (collapsible)                                                                      |
| RBAC              | AI respects existing RBAC; users see knowledge across all accessible applications                      |
| API Keys          | Global (admin-set) with per-user override (users bring their own key)                                  |
| Chat History      | Session-only in Zustand (survives sidebar close, clears on app close/logout/reset)                     |
| AI Personality    | Blair: Friendly & helpful with suggestions                                                             |
| Indexing          | Debounced embeddings + entity extraction (~30s) + manual reindex button                                |
| Background Jobs   | Existing ARQ worker (`fastapi-backend/app/worker.py`)                                                  |

---

## Dependency Graph

```
Phase 1 (LLM Layer)
    |
    v
Phase 2 (pgvector + Hybrid Search)
    |         \
    v          v
Phase 3      Phase 6 (Docling + Images)
(PG Graph)      |
    |          /
    v         v
Phase 4 (LangGraph Agent)
    |
    v
Phase 5 (CopilotKit Frontend)
    |
    v
Phase 7 (Admin + Polish)
```

Phases 3 and 6 can run in parallel after Phase 2.
Phase 3 shares the same PostgreSQL database — no new infrastructure needed.

---

## Infrastructure Requirements

| Service     | Version | Purpose                                                | Notes                    |
| ----------- | ------- | ------------------------------------------------------ | ------------------------ |
| PostgreSQL  | 15+     | pgvector + pg_trgm extensions + knowledge graph tables | Existing, add extensions |
| Redis       | 7+      | ARQ jobs, caching, rate limiting                       | Existing                 |
| Meilisearch | 1.x     | Full-text search (existing)                            | Keep unchanged           |
| MinIO       | Latest  | File storage (existing)                                | Keep unchanged           |
| Ollama      | Latest  | Local LLM (optional)                                   | User-configurable URL    |

No new infrastructure services required. Knowledge graph uses PostgreSQL tables with recursive CTEs for traversal.

---

## Key Patterns to Reuse

| Pattern                     | Source File                                                                                     | Used In                                   |
| --------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------- |
| RBAC scope resolution       | `services/search_service.py` (`_get_user_application_ids()`, `_get_projects_in_applications()`) | Agent RBAC context, retrieval filtering   |
| TipTap JSON tree walking    | `services/content_converter.py`                                                                 | Semantic chunking                         |
| ARQ job pattern             | `worker.py` lines 51-83, 395-429                                                                | Embedding, entity extraction, import jobs |
| Redis rate limiting         | `services/redis_service.py`                                                                     | AI endpoint rate limits                   |
| WebSocket broadcast         | `websocket/handlers.py` (`broadcast_to_target_users()`)                                         | AI status events                          |
| Meilisearch integration     | `services/search_service.py`                                                                    | Hybrid retrieval keyword source           |
| Permission checks           | `services/permission_service.py`                                                                | Agent tool RBAC validation                |
| MinIO file download         | `services/minio_service.py`                                                                     | Image understanding pipeline              |
| Document soft delete        | `models/document.py` (`deleted_at` pattern)                                                     | Filter deleted docs from RAG              |
| Existing query keys pattern | `lib/query-client.ts` lines 64-150                                                              | New AI query keys                         |

## Testing

**_Please make sure to create tables start of the session and drop/rollback transaction at the end of sessions. Do not create and drop for each test since it's very wasteful. _**

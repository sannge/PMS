# AI Copilot Feature - Comprehensive Implementation Plan

**Last updated**: 2026-02-28

## Overview

PM Desktop currently has a rich knowledge base (TipTap documents, folder hierarchy, Meilisearch full-text search) and a full project management system (Applications > Projects > Tasks with RBAC). This plan adds **Blair**, an AI copilot agent that can answer questions about knowledge base content, project/task relationships, due dates, completion metrics, and can take actions (create tasks, update status, create documents) with user confirmation via a seamless human-in-the-loop (HITL) experience powered by CopilotKit + AG-UI protocol + LangGraph. Blair understands embedded images via vision models, queries the relational schema directly via scoped PostgreSQL views for structural questions, uses hybrid RAG (pgvector + Meilisearch + pg_trgm) for content questions, and supports both regular documents and CANVAS documents (freeform spatial canvases).

## Table of Contents

- [Decisions Summary](#decisions-summary)
- [Dependency Graph](#dependency-graph)
- [Phase 1: LLM Abstraction Layer + Database Setup](phase-1-llm-abstraction.md)
- [Phase 2: Vector Embeddings + Hybrid Search](phase-2-vector-embeddings.md)
- ~~[Phase 3: Knowledge Graph (PostgreSQL)](phase-3-knowledge-graph.md)~~ — REPLACED by Phase 3.1
- [Phase 3.1: Agent SQL Access & Excel Export](phase-3.1-sql-access.md)
- [Phase 4: LangGraph Agent + Backend Tools](phase-4-langgraph-agent.md)
- [Phase 5: CopilotKit Frontend (Chat Sidebar)](phase-5-copilotkit-frontend.md)
- [Phase 6: Document Import (Docling) + Image Understanding](phase-6-document-import.md)
- [Phase 7: Admin Dashboard + Observability + Polish](phase-7-admin-polish.md)
- ~~[Phase 8: Query Expansion](phase-8-query-expansion.md)~~ — REMOVED (agent handles expansion naturally)
- [Phase 9: Safety, Cost Controls & Embedding Quality](phase-9-safety-embedding-quality.md)
- [Phase 10: OAuth Subscription Connect](phase-10-oauth-subscription-connect.md)
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
| ~~Knowledge Graph~~ | ~~PostgreSQL tables with recursive CTE traversal~~ — REPLACED by Agent SQL Access |
| Agent SQL Access   | Scoped PostgreSQL views (`v_*`) + sqlglot validator for read-only AI queries |
| RBAC Enforcement   | Scoped views with `current_setting('app.current_user_id')` — deterministic, no LLM trust |
| Excel Export       | openpyxl as agent tool for downloadable reports |
| Document Import   | Docling for PDF/DOCX/PPTX                                                                              |
| Vector Search     | pgvector (PostgreSQL extension)                                                                        |
| Fuzzy Search      | pg_trgm (PostgreSQL extension)                                                                         |
| Existing Search   | Keep Meilisearch for user-facing search; AI uses additional layers                                     |
| Document Types    | Regular TipTap documents + CANVAS (freeform spatial canvas)                                            |
| Source References | Clickable citations that navigate to source document and highlight cited text                          |
| UI Position       | Right sidebar panel (collapsible)                                                                      |
| RBAC              | AI respects existing RBAC; users see knowledge across all accessible applications                      |
| AI Admin Access   | `is_developer` column on Users (manual DB update) — developers configure embedding/vision/chat globally |
| API Keys          | Developer-set global keys + per-user chat override (users bring their own OpenAI/Anthropic key)        |
| User Chat Override | Any user can override chat provider with personal API key (OpenAI or Anthropic only, not Ollama)      |
| Chat History      | Session-only in Zustand (survives sidebar close, clears on app close/logout/reset)                     |
| AI Personality    | Blair: Concise & professional — direct answers, bullet points over prose, no filler                    |
| ~~Query Expansion~~ | ~~Standalone `QueryExpansionService`~~ — REMOVED (agent handles expansion naturally; semantic search handles synonyms) |
| Indexing          | Debounced embeddings (~30s) + manual reindex button                                                    |
| Background Jobs   | Existing ARQ worker (`fastapi-backend/app/worker.py`)                                                  |
| OAuth Protocol     | OAuth 2.0 + PKCE (S256) for user subscription connections (OpenAI Codex, Anthropic Claude)            |
| OAuth Token Storage | Fernet-encrypted in AiProviders (reuse existing encryption)                                           |
| OAuth Token Refresh | Automatic in provider registry before API calls (5-min buffer)                                        |
| Electron OAuth     | Temporary localhost HTTP server + BrowserWindow with session partition                                 |
| Anthropic Warning  | Amber banner — Anthropic may block third-party subscription tokens                                     |
| OAuth Backward Compat | `auth_method` column defaults to `'api_key'`, existing overrides unchanged                          |

---

## Dependency Graph

```
Phase 1 (LLM Layer) --- 244 tasks
    |
    v
Phase 2 (pgvector + Hybrid Search) --- 207 tasks
    |              \
    v               v
Phase 3.1          Phase 6 (Docling + Images) --- 221 tasks
(SQL Access)            |
--- ~218 tasks         /
    |                 /
    v                v
Phase 4 (LangGraph Agent) --- 204 tasks
    |
    v
Phase 5 (CopilotKit Frontend) --- 238 tasks
    |
    v
Phase 7 (Admin + Polish + Integration) --- 203 tasks
    |              \
    v               v
Phase 9            Phase 10 (OAuth Subscription Connect) --- 151 tasks
(Safety + Quality)
--- 168 tasks
```

Phases 3.1 and 6 can run in parallel after Phase 2.
Phase 4 depends on Phase 3.1 (agent tools) + Phase 6.
Phase 3.1 uses scoped PostgreSQL views — no new infrastructure needed. New deps: `sqlglot`, `openpyxl`.
Phases 9 and 10 can run in parallel after Phase 7.
Phase 8 (Query Expansion) was REMOVED — agent handles expansion naturally via reasoning + multi-tool calls.
Phase 9 hardens AI pipelines against cost explosions and fixes chunking quality for tables, slides, and canvas containers.
Phase 10 replaces API key user overrides with OAuth subscription connections (OpenAI Codex, Anthropic Claude).

---

## Infrastructure Requirements

| Service     | Version | Purpose                                                | Notes                    |
| ----------- | ------- | ------------------------------------------------------ | ------------------------ |
| PostgreSQL  | 15+     | pgvector + pg_trgm extensions + scoped views           | Existing, add extensions |
| Redis       | 7+      | ARQ jobs, caching, rate limiting                       | Existing                 |
| Meilisearch | 1.x     | Full-text search (existing)                            | Keep unchanged           |
| MinIO       | Latest  | File storage (existing)                                | Keep unchanged           |
| Ollama      | Latest  | Local LLM (optional)                                   | User-configurable URL    |

No new infrastructure services required. Agent SQL access uses scoped PostgreSQL views for RBAC-enforced read-only queries.

---

## Key Patterns to Reuse

| Pattern                     | Source File                                                                                     | Used In                                   |
| --------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------- |
| RBAC scope resolution       | `services/search_service.py` (`_get_user_application_ids()`, `_get_projects_in_applications()`) | Agent RBAC context, retrieval filtering   |
| TipTap JSON tree walking    | `services/content_converter.py`                                                                 | Semantic chunking                         |
| ARQ job pattern             | `worker.py` lines 51-83, 395-429                                                                | Embedding, import jobs                    |
| Redis rate limiting         | `services/redis_service.py`                                                                     | AI endpoint rate limits                   |
| WebSocket broadcast         | `websocket/handlers.py` (`broadcast_to_target_users()`)                                         | AI status events                          |
| Meilisearch integration     | `services/search_service.py`                                                                    | Hybrid retrieval keyword source           |
| Permission checks           | `services/permission_service.py`                                                                | Agent tool RBAC validation                |
| MinIO file download         | `services/minio_service.py`                                                                     | Image understanding pipeline              |
| Document soft delete        | `models/document.py` (`deleted_at` pattern)                                                     | Filter deleted docs from RAG              |
| Existing query keys pattern | `lib/query-client.ts` lines 64-150                                                              | New AI query keys                         |

## Testing

**_Please make sure to create tables start of the session and drop/rollback transaction at the end of sessions. Do not create and drop for each test since it's very wasteful. _**

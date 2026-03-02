## Testing

**_Please make sure to create tables start of the session and drop/rollback transaction at the end of sessions. Do not create and drop for each test since it's very wasteful. _**

# Blair AI Copilot — Master Task Index

**Created**: 2026-02-24
**Last updated**: 2026-02-28
**Project**: Blair AI Copilot for PM Desktop
**Spec**: [../README.md](../README.md)

---

## Team Roster

| Abbreviation | Role              | Responsibility                                               |
| ------------ | ----------------- | ------------------------------------------------------------ |
| **FE**       | Frontend Engineer | React/TypeScript components, hooks, stores, styles           |
| **BE**       | Backend Engineer  | FastAPI services, routers, schemas, LangGraph agent          |
| **DBE**      | Database Engineer | Alembic migrations, SQLAlchemy models, indexes, extensions   |
| **CR1**      | Code Reviewer 1   | Data layer reviews (migrations, models, schemas, queries)    |
| **CR2**      | Code Reviewer 2   | Logic layer reviews (services, agent, async patterns, DI)    |
| **SA**       | Security Analyst  | RBAC enforcement, encryption, injection, auth, file security |
| **QE**       | Quality Engineer  | Acceptance criteria verification, manual testing scenarios   |
| **TE**       | Test Engineer     | Unit tests, integration tests, E2E test implementation       |
| **DA**       | Devil's Advocate  | Challenge assumptions, question design decisions, edge cases |

---

## Task Legend

| Symbol | Meaning       |
| ------ | ------------- |
| `[ ]`  | Not started   |
| `[~]`  | In progress   |
| `[x]`  | Completed     |
| `[!]`  | Blocked       |
| `[—]`  | Skipped / N/A |

---

## Phase Summary

| Phase | Spec | Task File | Tasks | Status | Depends On |
| ----- | ---- | --------- | ----- | ------ | ---------- |
| **Phase 1** | [LLM Abstraction Layer](../phase-1-llm-abstraction.md) | [phase-1-tasks.md](phase-1-tasks.md) | **244** | COMPLETE | — |
| **Phase 2** | [Vector Embeddings + Hybrid Search](../phase-2-vector-embeddings.md) | [phase-2-tasks.md](phase-2-tasks.md) | **207** | COMPLETE | Phase 1 |
| ~~Phase 3~~ | ~~[Knowledge Graph](../phase-3-knowledge-graph.md)~~ | ~~[phase-3-tasks.md](phase-3-tasks.md)~~ | ~~238~~ | REPLACED by 3.1 | ~~Phase 2~~ |
| **Phase 3.1** | [Agent SQL Access & Excel Export](../phase-3.1-sql-access.md) | [phase-3.1-tasks.md](phase-3.1-tasks.md) | **~225** | COMPLETE | Phase 1, Phase 2 |
| **Phase 4** | [LangGraph Agent + Backend Tools](../phase-4-langgraph-agent.md) | [phase-4-tasks.md](phase-4-tasks.md) | **204** | NOT STARTED | Phase 3.1 + Phase 6 |
| **Phase 5** | [CopilotKit Frontend](../phase-5-copilotkit-frontend.md) | [phase-5-tasks.md](phase-5-tasks.md) | **238** | NOT STARTED | Phase 4 |
| **Phase 6** | [Document Import + Image Understanding](../phase-6-document-import.md) | [phase-6-tasks.md](phase-6-tasks.md) | **221** | NOT STARTED | Phase 2 |
| **Phase 7** | [Admin Dashboard + Observability](../phase-7-admin-polish.md) | [phase-7-tasks.md](phase-7-tasks.md) | **229** | NOT STARTED | Phase 5 |
| ~~Phase 8~~ | ~~[Query Expansion](../phase-8-query-expansion.md)~~ | ~~[phase-8-tasks.md](phase-8-tasks.md)~~ | ~~~100~~ | REMOVED | ~~Phase 2~~ |
| **Phase 9** | [Safety, Cost Controls & Embedding Quality](../phase-9-safety-embedding-quality.md) | [phase-9-tasks.md](phase-9-tasks.md) | **206** | NOT STARTED | Phase 7 |
| **Phase 10** | [OAuth Subscription Connect](../phase-10-oauth-subscription-connect.md) | [phase-10-tasks.md](phase-10-tasks.md) | **151** | NOT STARTED | Phase 7 |
|             |                                                                        |                                      | **~1,887** |             |                   |

> Phase 7 includes 38 cross-phase integration tasks (INT.x.x) in addition to 192 phase-specific tasks. Includes `is_developer` migration, per-capability developer config, user chat override UI.
> Phase 3 (Knowledge Graph) replaced by Phase 3.1 (Agent SQL Access) — ~4,880 LOC removed, replaced with scoped views + SQL tools.
> Phase 8 (Query Expansion) REMOVED — agent handles expansion naturally; semantic search handles synonyms implicitly.
> Phase 9 addresses cost/safety bugs, embedding quality issues, and AI config panel fixes. 9 cost/safety fixes + 5 embedding quality fixes + 2 config items + 6 AI config panel fixes.
> Phase 10 replaces API key user overrides with OAuth subscription connections (OpenAI Codex, Anthropic Claude). Can run in parallel with Phase 9.

---

## Dependency Graph

```
Phase 1 (LLM Layer) ─── 244 tasks
    │
    v
Phase 2 (pgvector + Hybrid Search) ─── 207 tasks
    │              \
    v               v
Phase 3.1          Phase 6 (Docling + Images) ─── 221 tasks
(SQL Access)            │
─── ~218 tasks         /
    │                 /
    v                v
Phase 4 (LangGraph Agent) ─── 204 tasks
    │
    v
Phase 5 (CopilotKit Frontend) ─── 238 tasks
    │
    v
Phase 7 (Admin + Polish + Integration) ─── 203 tasks
    │              \
    v               v
Phase 9            Phase 10 (OAuth Subscription Connect) ─── 151 tasks
(Safety + Quality)
─── 206 tasks
```

> Phases 3.1 and 6 can run **in parallel** after Phase 2 completes.
> Phase 4 depends on Phase 3.1 (agent tools: `sql_query_tool`, `rag_search_tool`, `export_to_excel_tool`) + Phase 6.
> Phases 9 and 10 can run **in parallel** after Phase 7 completes.
> Phase 8 (Query Expansion) was REMOVED — agent handles expansion naturally.

---

## Task Distribution by Role

| Role | Phase 1 | Phase 2 | Phase 3.1 | Phase 4 | Phase 5 | Phase 6 | Phase 7 | Total |
| ---- | ------- | ------- | --------- | ------- | ------- | ------- | ------- | ----- |
| FE   | —       | —       | —         | —       | ~140    | ~40     | ~60     | ~240  |
| BE   | ~90     | ~70     | ~118      | ~100    | ~10     | ~60     | ~50     | ~498  |
| DBE  | ~20     | ~30     | ~24       | —       | —       | ~10     | ~5      | ~89   |
| CR1  | ~15     | ~8      | ~5        | ~6      | ~4      | ~6      | ~6      | ~50   |
| CR2  | ~15     | ~6      | ~6        | ~6      | ~4      | ~6      | ~6      | ~49   |
| SA   | ~15     | ~6      | ~7        | ~10     | ~4      | ~12     | ~6      | ~60   |
| QE   | ~40     | ~30     | ~16       | ~15     | ~30     | ~20     | ~20     | ~171  |
| TE   | ~35     | ~40     | ~62       | ~35     | ~23     | ~30     | ~20     | ~245  |
| DA   | ~14     | ~8      | ~3        | ~8      | ~5      | ~6      | ~6      | ~50   |

> Numbers are approximate. See individual phase files for exact assignments.

---

## How to Use This Tracker

### Starting Work on a Task

1. Find the task in the relevant phase file
2. Change `[ ]` to `[~]` and add your initials in the Notes column
3. When complete, change `[~]` to `[x]` with date (e.g., `2026-02-25`)

### Updating Phase Status

When all tasks in a phase section are `[x]`:

1. Update the section status to COMPLETED
2. Update the phase summary table above
3. Notify downstream phases that their dependency is cleared

### Blocking Issues

- Mark the task `[!]` and add blocker description in Notes
- Create a new row below with the unblocking task if needed
- Notify the team lead

### Cross-Phase Integration Testing

After Phase 5, the Phase 7 file contains integration tasks (INT.x.x) that verify end-to-end flows across all phases. These should only begin after their prerequisite phases are all complete.

---

## Key Technical Decisions Reference

| Decision        | Choice                                                               | Relevant Phases |
| --------------- | -------------------------------------------------------------------- | --------------- |
| Embedding Model | `text-embedding-3-small` (1536d, configurable)                       | 1, 2            |
| Vector Storage  | pgvector with HNSW index                                             | 2               |
| Fuzzy Search    | pg_trgm extension                                                    | 2               |
| ~~Knowledge Graph~~ | ~~PostgreSQL tables + recursive CTEs~~ — REPLACED                | ~~3~~           |
| Agent SQL Access | Scoped PostgreSQL views + sqlglot validator                         | 3.1             |
| RBAC Enforcement | Scoped views with `current_setting('app.current_user_id')`          | 3.1             |
| Excel Export    | openpyxl as agent tool                                               | 3.1             |
| Agent Framework | LangGraph (ReAct pattern)                                            | 4               |
| Frontend SDK    | CopilotKit + AG-UI protocol                                         | 5               |
| Document Import | Docling (PDF/DOCX/PPTX)                                             | 6               |
| Background Jobs | ARQ worker (existing)                                                | 2, 6            |
| HITL Pattern    | LangGraph `interrupt()` + AG-UI INTERRUPT event                      | 4, 5            |
| Chat History    | Session-only (Zustand)                                               | 5               |
| AI Admin Access | `is_developer` column on Users (manual DB), per-capability config    | 7               |
| User Chat Override | Any user overrides chat provider with personal key (OpenAI/Anthropic) | 7            |
| Model Seed Data | AiModels table with `provider_type`, new models added via DB INSERT  | 7               |
| ~~Query Expansion~~ | ~~Standalone service (LLM only, no graph), Redis-cached~~ — REMOVED | ~~8~~           |
| OAuth Protocol  | OAuth 2.0 + PKCE (S256) for user subscription connections               | 10              |
| OAuth Token Storage | Fernet-encrypted in AiProviders, auto-refresh in registry             | 10              |
| Electron OAuth  | Temporary localhost HTTP server + BrowserWindow                          | 10              |
| Anthropic Warning | Amber banner — may block third-party subscription tokens               | 10              |

---

## File References

- [File Manifest](../file-manifest.md) — Complete listing of all new/modified files
- [README](../README.md) — Project overview, decisions, infrastructure
- [Phase Specs](../) — Detailed specifications for each phase

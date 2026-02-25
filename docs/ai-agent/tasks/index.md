## Testing

**_Please make sure to create tables start of the session and drop/rollback transaction at the end of sessions. Do not create and drop for each test since it's very wasteful. _**

# Blair AI Copilot — Master Task Index

**Created**: 2026-02-24
**Last updated**: 2026-02-24
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

| Phase       | Spec                                                                   | Task File                            | Tasks     | Status      | Depends On        |
| ----------- | ---------------------------------------------------------------------- | ------------------------------------ | --------- | ----------- | ----------------- |
| **Phase 1** | [LLM Abstraction Layer](../phase-1-llm-abstraction.md)                 | [phase-1-tasks.md](phase-1-tasks.md) | **244**   | NOT STARTED | — (foundation)    |
| **Phase 2** | [Vector Embeddings + Hybrid Search](../phase-2-vector-embeddings.md)   | [phase-2-tasks.md](phase-2-tasks.md) | **207**   | NOT STARTED | Phase 1           |
| **Phase 3** | [Knowledge Graph (PostgreSQL)](../phase-3-knowledge-graph.md)          | [phase-3-tasks.md](phase-3-tasks.md) | **238**   | NOT STARTED | Phase 2           |
| **Phase 4** | [LangGraph Agent + Backend Tools](../phase-4-langgraph-agent.md)       | [phase-4-tasks.md](phase-4-tasks.md) | **204**   | NOT STARTED | Phase 3 + Phase 6 |
| **Phase 5** | [CopilotKit Frontend](../phase-5-copilotkit-frontend.md)               | [phase-5-tasks.md](phase-5-tasks.md) | **238**   | NOT STARTED | Phase 4           |
| **Phase 6** | [Document Import + Image Understanding](../phase-6-document-import.md) | [phase-6-tasks.md](phase-6-tasks.md) | **221**   | NOT STARTED | Phase 2           |
| **Phase 7** | [Admin Dashboard + Observability](../phase-7-admin-polish.md)          | [phase-7-tasks.md](phase-7-tasks.md) | **203**   | NOT STARTED | Phase 5           |
|             |                                                                        |                                      | **1,555** |             |                   |

> Phase 7 includes 37 cross-phase integration tasks (INT.x.x) in addition to 166 phase-specific tasks.

---

## Dependency Graph

```
Phase 1 (LLM Layer) ─── 244 tasks
    │
    v
Phase 2 (pgvector + Hybrid Search) ─── 207 tasks
    │              \
    v               v
Phase 3            Phase 6 (Docling + Images) ─── 221 tasks
(PG Graph)              │
─── 238 tasks           │
    │              /
    v             v
Phase 4 (LangGraph Agent) ─── 204 tasks
    │
    v
Phase 5 (CopilotKit Frontend) ─── 238 tasks
    │
    v
Phase 7 (Admin + Polish + Integration) ─── 203 tasks
```

> Phases 3 and 6 can run **in parallel** after Phase 2 completes.

---

## Task Distribution by Role

| Role | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 | Phase 7 | Total |
| ---- | ------- | ------- | ------- | ------- | ------- | ------- | ------- | ----- |
| FE   | —       | —       | —       | —       | ~140    | ~40     | ~60     | ~240  |
| BE   | ~90     | ~70     | ~80     | ~100    | ~10     | ~60     | ~50     | ~460  |
| DBE  | ~20     | ~30     | ~30     | —       | —       | ~10     | ~5      | ~95   |
| CR1  | ~15     | ~8      | ~6      | ~6      | ~4      | ~6      | ~6      | ~51   |
| CR2  | ~15     | ~6      | ~6      | ~6      | ~4      | ~6      | ~6      | ~49   |
| SA   | ~15     | ~6      | ~6      | ~10     | ~4      | ~12     | ~6      | ~59   |
| QE   | ~40     | ~30     | ~25     | ~15     | ~30     | ~20     | ~20     | ~180  |
| TE   | ~35     | ~40     | ~35     | ~35     | ~23     | ~30     | ~20     | ~218  |
| DA   | ~14     | ~8      | ~6      | ~8      | ~5      | ~6      | ~6      | ~53   |

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

| Decision        | Choice                                          | Relevant Phases |
| --------------- | ----------------------------------------------- | --------------- |
| Embedding Model | `text-embedding-3-small` (1536d, configurable)  | 1, 2            |
| Vector Storage  | pgvector with HNSW index                        | 2               |
| Fuzzy Search    | pg_trgm extension                               | 2               |
| Knowledge Graph | PostgreSQL tables + recursive CTEs              | 3               |
| Agent Framework | LangGraph (ReAct pattern)                       | 4               |
| Frontend SDK    | CopilotKit + AG-UI protocol                     | 5               |
| Document Import | Docling (PDF/DOCX/PPTX)                         | 6               |
| Background Jobs | ARQ worker (existing)                           | 2, 3, 6         |
| HITL Pattern    | LangGraph `interrupt()` + AG-UI INTERRUPT event | 4, 5            |
| Chat History    | Session-only (Zustand)                          | 5               |

---

## File References

- [File Manifest](../file-manifest.md) — Complete listing of all new/modified files
- [README](../README.md) — Project overview, decisions, infrastructure
- [Phase Specs](../) — Detailed specifications for each phase

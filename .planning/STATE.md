# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-31)

**Core value:** Teams can create, organize, and find internal documentation without leaving their project management tool.
**Current focus:** Phase 2 in progress - Notes Screen Shell & Folder Navigation.

## Current Position

Phase: 2 of 10 (Notes Screen Shell & Folder Navigation)
Plan: 2 of 3 in current phase
Status: In progress
Last activity: 2026-01-31 -- Completed 02-02-PLAN.md (Folder Tree & Context Menu)

Progress: [██████░░░░] ~17%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: ~8 min
- Total execution time: ~0.8 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4/4 | ~34 min | ~9 min |
| 02 | 2/3 | ~15 min | ~8 min |

**Recent Trend:**
- Last 5 plans: 01-03 (~7 min), 01-04 (~7 min), 02-01 (~11 min), 02-02 (~4 min)
- Trend: stable at ~4-11 min

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Lock-based editing over CRDT -- simpler architecture, sufficient for team sizes
- [Roadmap]: TipTap v2 stay-put -- avoid v3 migration complexity during feature work
- [Roadmap]: PostgreSQL FTS for v1 search -- Meilisearch deferred to v1.x
- [Roadmap]: Three-format content storage (JSON + Markdown + plain text) for editor, AI, and search
- [Revision]: Remove Zustand entirely -- all state management via React Context + TanStack Query (auth-store, notes-store, notification-ui-store migrated in Phase 1)
- [Revision]: IndexedDB for knowledge base caching -- draft persistence (Phase 4), document content and folder tree caching (Phase 2) via existing per-query-persister infrastructure
- [01-02]: useRef pattern for auth state in WebSocket callbacks replaces Zustand getState()
- [01-03]: Materialized path pattern for folder tree queries (no recursive CTEs)
- [01-03]: Cursor pagination with base64-encoded JSON cursor (created_at + id)
- [01-03]: DocumentSnapshot table as empty placeholder for Phase 4+ version history
- [01-04]: Tags scoped per application (shared across app + project docs) or per user (personal docs only)
- [01-04]: Partial unique indexes for tag name uniqueness within scope
- [02-01]: Backend folder endpoint uses PUT for rename+move combined -- hooks map to PUT not PATCH
- [02-01]: Document mutations invalidate both document list and folder tree queries (folder document_count)
- [02-01]: KnowledgeBaseContext is UI-only state (useReducer), data fetching via TanStack Query hooks
- [02-02]: Document rename uses row_version=1 default; API 409 handles stale conflicts

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: TipTap JSON-to-Markdown conversion edge cases (nested lists, tables, code blocks) need testing in Phase 4
- [Research]: Electron-specific auto-save edge cases (force-quit, sleep/wake) need testing in Phase 4
- [Research]: Permission cache invalidation latency (60s Redis TTL) may surprise users -- consider WebSocket push
- ~~[Revision]: Zustand store migration scope -- auth-store and notification-ui-store are used across the app (not just knowledge base), so migration must not break existing features~~ RESOLVED in 01-02: all 27 files updated, zero store references remain
- [02-01]: ESLint configuration missing for ESLint 9.x (pre-existing) -- lint script fails, typecheck used as primary verification

## Session Continuity

Last session: 2026-01-31
Stopped at: Completed 02-02-PLAN.md (Folder Tree & Context Menu)
Resume file: None

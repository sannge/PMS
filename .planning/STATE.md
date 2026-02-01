# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-31)

**Core value:** Teams can create, organize, and find internal documentation without leaving their project management tool.
**Current focus:** Phase 4 in progress - Auto-Save & Content Pipeline.

## Current Position

Phase: 4 of 10 (Auto-Save & Content Pipeline)
Plan: 2 of 4 in current phase
Status: In progress
Last activity: 2026-02-01 -- Completed 04-02-PLAN.md (IndexedDB draft persistence + useDraft hook)

Progress: [█████████████░] ~39%

## Performance Metrics

**Velocity:**
- Total plans completed: 12
- Average duration: ~6 min
- Total execution time: ~1.11 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4/4 | ~34 min | ~9 min |
| 02 | 3/3 | ~19 min | ~6 min |
| 03 | 4/4 | ~14 min | ~4 min |
| 04 | 1/4 | ~2 min | ~2 min |

**Recent Trend:**
- Last 5 plans: 03-02 (~2 min), 03-03 (~3 min), 03-04 (~3 min), 04-02 (~2 min)
- Trend: stable at ~2-3 min

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
- [02-03]: Composite string encoding (application:id, project:id) for Radix Select single-value constraint
- [02-03]: Per-application ProjectItems components for lazy project fetching in scope dropdown
- [03-01]: Extension factory pattern -- all TipTap extensions configured in createDocumentExtensions(), toolbar plans only add UI
- [03-01]: JSON content format -- editor emits getJSON() not getHTML() for three-format storage strategy
- [03-01]: lowlight v3 syntax with createLowlight(common) for code block highlighting
- [03-02]: Heading dropdown uses Radix Popover (not Select) for richer preview rendering
- [03-02]: HeadingOption data-driven pattern with level + className for DRY heading list
- [03-03]: Composite icon pattern (base + overlay) for table add/remove column/row actions
- [03-03]: Toggle header row included as contextual table control
- [03-04]: Link popover uses Popover component (consistent with heading/font dropdowns)
- [03-04]: useEditorState reads characterCount storage for reactive status bar updates
- [04-02]: Cleanup runs inside getDraftDB() with flag guard -- simpler than separate App.tsx useEffect
- [04-02]: restoreDraft does NOT delete from IndexedDB -- draft persists until clearDraftAfterSave after successful server save

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: TipTap JSON-to-Markdown conversion edge cases (nested lists, tables, code blocks) need testing in Phase 4
- [Research]: Electron-specific auto-save edge cases (force-quit, sleep/wake) need testing in Phase 4
- [Research]: Permission cache invalidation latency (60s Redis TTL) may surprise users -- consider WebSocket push
- ~~[Revision]: Zustand store migration scope -- auth-store and notification-ui-store are used across the app (not just knowledge base), so migration must not break existing features~~ RESOLVED in 01-02: all 27 files updated, zero store references remain
- [02-01]: ESLint configuration missing for ESLint 9.x (pre-existing) -- lint script fails, typecheck used as primary verification

## Session Continuity

Last session: 2026-02-01
Stopped at: Completed 04-02-PLAN.md (draft persistence)
Resume file: None

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-31)

**Core value:** Teams can create, organize, and find internal documentation without leaving their project management tool.
**Current focus:** Phase 02.1 gap closure (fixing editor and autosave blockers).

## Current Position

Phase: 02.1 of 10 (OneNote-Style Knowledge Tree Redesign)
Plan: 6 of 7 in phase 02.1 (gap closure plans added)
Status: In progress
Last activity: 2026-02-03 -- Completed 02.1-06-PLAN.md

Progress: [████████████████████████] ~76%

## Performance Metrics

**Velocity:**
- Total plans completed: 25
- Average duration: ~5 min
- Total execution time: ~2.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4/4 | ~34 min | ~9 min |
| 02 | 3/3 | ~19 min | ~6 min |
| 03 | 4/4 | ~14 min | ~4 min |
| 04 | 4/4 | ~12 min | ~3 min |
| 05 | 2/2 | ~10 min | ~5 min |
| 04.1 | 2/2 | ~6 min | ~3 min |
| 02.1 | 6/7 | ~29 min | ~5 min |

**Recent Trend:**
- Last 5 plans: 02.1-03 (~2 min), 02.1-04 (~4 min), 02.1-05 (~6 min), 02.1-06 (~8 min)
- Trend: stable at ~2-8 min

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
- [04-01]: Content markdown/plain set to empty placeholders during auto-save -- real conversion deferred to Plan 04-04
- [04-01]: useAutoSave uses refs (not state) for lastSaved, timer, saving mutex, rowVersion to avoid re-renders
- [04-01]: SaveStatus exported as discriminated union type for reuse by save indicator and save-on-navigate
- [04-02]: Cleanup runs inside getDraftDB() with flag guard -- simpler than separate App.tsx useEffect
- [04-02]: restoreDraft does NOT delete from IndexedDB -- draft persists until clearDraftAfterSave after successful server save
- [04-04]: textStyle/highlight marks are presentation-only -- skipped in Markdown output
- [04-04]: codeBlock with 'plaintext'/empty/null language renders bare ``` fences (no language annotation)
- [04-04]: underline renders as <u>text</u> in Markdown (HTML is valid Markdown)
- [04-03]: useSaveOnUnmount uses ref to capture latest saveNow -- avoids stale closure
- [04-03]: useSaveOnQuit calls confirmQuitSave in .finally() -- ensures quit proceeds even if save throws
- [04-03]: SaveStatus uses setTick counter state to force re-render every second for live time display
- [05-01]: Lua scripts for all ownership-checked lock operations (release, heartbeat, force-take)
- [05-01]: 45s TTL with heartbeat extension; personal docs block force-take (no app context)
- [05-02]: documentLock query key added to centralized queryKeys for cache management
- [05-02]: Lock integration in DocumentEditor is gracefully optional (inactive without documentId)
- [04.1-01]: Only Document.tags lazy changed to selectin; other models left as-is (only confirmed broken relationship)
- [04.1-02]: ScopePickerDialog is pure selection UI -- returns scope to parent, does not call createDocument itself
- [04.1-02]: ProjectItems in scope picker lazily loads projects per application (consistent with scope-filter pattern)
- [02.1-01]: Storage key prefix pattern (buildStorageKeys) for multi-instance KnowledgeBaseProvider isolation
- [02.1-01]: Tab value encoding: 'personal' for personal scope, 'app:{id}' for application scope, derived via deriveFromTab()
- [02.1-01]: Legacy 'all' scope removed from ScopeType; stored 'all' in localStorage migrates to 'personal'
- [02.1-02]: KnowledgeTabBar is controlled (value+onValueChange) with no TabsContent -- content managed by sidebar
- [02.1-02]: Lock indicator uses span wrapper for tooltip (Lucide icons don't accept title prop)
- [02.1-02]: Quick creation buttons resolve scope from activeTab encoding (personal or app:{id})
- [02.1-04]: Project sections lazy-load by passing null scopeId when collapsed (useFolderTree disabled condition)
- [02.1-04]: Rename/delete endpoints are ID-based, so app-scope mutations work for project items too
- [02.1-04]: Global search toggle is local state with optional onGlobalToggle callback for parent
- [02.1-05]: KnowledgePanel wraps in KnowledgeBaseProvider with scoped storagePrefix for localStorage isolation
- [02.1-05]: Application detail replaces showArchive boolean with activeView union type (projects/archive/knowledge)
- [02.1-05]: Content save in KnowledgePanel uses useSaveDocumentContent with 2s debounce (useAutoSave requires editor instance)
- [02.1-06]: currentDoc variable rename to avoid shadowing global document object
- [02.1-06]: SaveStatus indicator in dedicated header bar above editor
- [02.1-06]: EditorPanel pattern: useDocument + debounced save + rowVersionRef + SaveStatus

### Roadmap Evolution

- Phase 4.1 inserted after Phase 4: Document Creation Bug Fixes (URGENT) — duplicate icons, 422 errors on All Documents/My Notes, 500 errors on Application/Project (tags lazy loading), no error feedback

### Pending Todos

None yet.

### Blockers/Concerns

- ~~[Research]: TipTap JSON-to-Markdown conversion edge cases (nested lists, tables, code blocks) need testing in Phase 4~~ RESOLVED in 04-04: 49 test cases covering all node types
- [Research]: Electron-specific auto-save edge cases (force-quit, sleep/wake) need testing in Phase 4
- [Research]: Permission cache invalidation latency (60s Redis TTL) may surprise users -- consider WebSocket push
- ~~[Revision]: Zustand store migration scope -- auth-store and notification-ui-store are used across the app (not just knowledge base), so migration must not break existing features~~ RESOLVED in 01-02: all 27 files updated, zero store references remain
- [02-01]: ESLint configuration missing for ESLint 9.x (pre-existing) -- lint script fails, typecheck used as primary verification

## Session Continuity

Last session: 2026-02-03
Stopped at: Completed 02.1-06-PLAN.md. Editor and autosave gaps fixed.
Resume file: None

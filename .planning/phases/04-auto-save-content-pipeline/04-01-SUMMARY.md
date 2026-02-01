---
phase: 04-auto-save-content-pipeline
plan: 01
subsystem: api, ui
tags: [auto-save, debounce, optimistic-concurrency, row-version, tiptap, tanstack-query]

# Dependency graph
requires:
  - phase: 01-migration-and-data-foundation
    provides: Document model with row_version, content_json, content_markdown, content_plain columns
  - phase: 03-rich-text-editor-core
    provides: TipTap editor integration with getJSON() output
provides:
  - PUT /documents/{id}/content endpoint with optimistic concurrency (row_version)
  - DocumentContentUpdate Pydantic schema
  - save_document_content service function
  - useSaveDocumentContent TanStack Query mutation
  - useAutoSave hook with 10s debounce, dirty tracking, saveNow()
  - SaveStatus type for UI display
affects:
  - 04-02 (save status indicator uses SaveStatus type)
  - 04-03 (save-on-navigate/close reuses saveNow())
  - 04-04 (content pipeline converter extends save_document_content)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Content auto-save via debounced editor update listener"
    - "Optimistic concurrency with row_version check and HTTP 409"
    - "Ref-based dirty tracking (JSON stringify comparison) to skip redundant saves"
    - "Mutex ref pattern to prevent concurrent saves"

key-files:
  created:
    - electron-app/src/renderer/hooks/use-auto-save.ts
  modified:
    - fastapi-backend/app/schemas/document.py
    - fastapi-backend/app/services/document_service.py
    - fastapi-backend/app/routers/documents.py
    - electron-app/src/renderer/hooks/use-queries.ts

key-decisions:
  - "Content markdown/plain set to empty string placeholders -- real conversion in Plan 04-04"
  - "useAutoSave uses refs (not state) for lastSaved, timer, saving mutex, rowVersion to avoid re-renders"
  - "SaveStatus exported as union type for Plan 02 save indicator and Plan 03 save-on-navigate"

patterns-established:
  - "Auto-save debounce pattern: editor.on('update') -> clearTimeout -> setTimeout(10s) -> saveNow()"
  - "Content save mutation pattern: PUT with content_json + row_version, 409 on conflict"

# Metrics
duration: 4min
completed: 2026-02-01
---

# Phase 4 Plan 1: Auto-Save Endpoint and Hook Summary

**PUT /documents/{id}/content with row_version concurrency, useAutoSave hook with 10s debounce and dirty tracking**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-01T03:24:25Z
- **Completed:** 2026-02-01T03:28:25Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Backend PUT endpoint with optimistic concurrency (row_version check, 409 on mismatch)
- save_document_content service function with content update and version increment
- useAutoSave hook with 10-second inactivity debounce, JSON dirty tracking, and concurrent save mutex
- useSaveDocumentContent mutation wired to PUT endpoint
- Imperative saveNow() exported for reuse by save-on-navigate/close (Plan 03)

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend auto-save endpoint with optimistic concurrency** - `8a35fc0` (feat)
2. **Task 2: Frontend useAutoSave hook with 10s debounce and dirty tracking** - `2204912` (feat)

## Files Created/Modified
- `fastapi-backend/app/schemas/document.py` - Added DocumentContentUpdate schema (content_json + row_version)
- `fastapi-backend/app/services/document_service.py` - Added save_document_content with row_version check
- `fastapi-backend/app/routers/documents.py` - Added PUT /documents/{id}/content endpoint
- `electron-app/src/renderer/hooks/use-auto-save.ts` - Created useAutoSave hook with debounce, dirty tracking, saveNow()
- `electron-app/src/renderer/hooks/use-queries.ts` - Added useSaveDocumentContent mutation

## Decisions Made
- Content markdown/plain set to empty string placeholders during auto-save -- real TipTap-to-Markdown/plain-text conversion deferred to Plan 04-04
- useAutoSave tracks all mutable state in refs (lastSaved, timer, saving mutex, rowVersion) to avoid unnecessary re-renders; only saveStatus uses useState for UI display
- SaveStatus type exported as a discriminated union for reuse by save indicator (Plan 02) and save-on-navigate (Plan 03)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Save endpoint and hook ready for Plan 02 (save status UI indicator)
- saveNow() ready for Plan 03 (save-on-navigate/close)
- save_document_content ready for Plan 04 (content pipeline with markdown/plain text conversion)

---
*Phase: 04-auto-save-content-pipeline*
*Completed: 2026-02-01*

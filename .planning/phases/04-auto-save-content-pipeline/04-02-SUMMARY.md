# Phase 4 Plan 02: IndexedDB Draft Persistence Summary

## One-liner
IndexedDB draft store with 2-second debounced auto-buffering and crash recovery via useDraft hook

## What Was Done

### Task 1: IndexedDB draft store (draft-db.ts)
- Created `draft-db.ts` with separate `pm-drafts-db` database (not reusing query cache)
- `DraftEntry` interface: documentId, contentJson, title, serverUpdatedAt, draftedAt
- `DraftDBSchema` with `drafts` object store (keyPath: documentId) and `by-drafted-at` index
- Singleton `getDraftDB()` following existing `query-cache-db.ts` pattern
- CRUD: `saveDraft`, `getDraft`, `deleteDraft`
- `cleanupOldDrafts(maxAgeDays)` uses cursor on `by-drafted-at` index for efficient deletion
- Auto-cleanup on first DB open (guarded by `cleanupRan` flag)
- **Commit:** efac17e

### Task 2: useDraft hook for auto-buffering and restore prompt
- Created `use-draft.ts` with `useDraft` hook
- Auto-buffers editor content to IndexedDB every 2 seconds of inactivity via `editor.on('update')` with debounce
- On-mount check: loads draft, compares draftedAt vs serverUpdatedAt
  - Newer draft with different content: sets `pendingDraft` for restore/discard UI
  - Newer draft with same content: silently deletes
  - Older draft: silently deletes
- `restoreDraft()`: returns parsed JSON content, clears pendingDraft state (keeps in IDB for safety)
- `discardDraft()`: deletes from IndexedDB, clears pendingDraft state
- `clearDraftAfterSave()`: deletes draft after successful server save (for auto-save integration)
- Uses refs for stable callback values (documentTitle, serverUpdatedAt)
- **Commit:** 9aa67fa

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Cleanup runs inside getDraftDB() with flag guard | Simpler than separate App.tsx useEffect; runs once regardless of which component opens DB first |
| Editor type from @tiptap/core (not @tiptap/react) | Core type is the base interface, consistent with document-editor.tsx pattern |
| restoreDraft does NOT delete from IndexedDB | Draft persists until clearDraftAfterSave is called after successful server save -- extra safety |

## Key Files

| File | Purpose |
|------|---------|
| `electron-app/src/renderer/lib/draft-db.ts` | IndexedDB pm-drafts-db store with CRUD and cleanup |
| `electron-app/src/renderer/hooks/use-draft.ts` | useDraft hook for auto-buffering and crash recovery |

## Verification Results

- TypeScript compiles without errors (no draft-db or use-draft errors)
- pm-drafts-db is separate from pm-query-cache-db
- All exports present: getDraftDB, saveDraft, getDraft, deleteDraft, cleanupOldDrafts, DraftEntry, useDraft

## Next Phase Readiness

Plan 04-03 (auto-save with three-format storage) can integrate with:
- `useDraft.clearDraftAfterSave()` to clean up drafts after successful server save
- The debounced auto-buffer pattern provides a foundation for the auto-save debounce

## Duration
~2 minutes (2026-02-01T03:25:02Z to 2026-02-01T03:27:30Z)

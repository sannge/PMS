---
phase: 05-document-locking
plan: 02
subsystem: frontend-editor
tags: [react, hooks, websocket, tiptap, document-locking, ui]
dependency-graph:
  requires: ["05-01"]
  provides: ["useDocumentLock hook", "LockBanner component", "editor lock integration"]
  affects: ["06-xx (knowledge page wiring)", "07-xx (presence/collaboration)"]
tech-stack:
  added: []
  patterns: ["useQuery + useMutation for lock state", "WebSocket cache update via setQueryData", "ref-based timers for heartbeat/inactivity"]
key-files:
  created:
    - electron-app/src/renderer/hooks/use-document-lock.ts
    - electron-app/src/renderer/components/knowledge/LockBanner.tsx
  modified:
    - electron-app/src/renderer/lib/websocket.ts
    - electron-app/src/renderer/lib/query-client.ts
    - electron-app/src/renderer/hooks/index.ts
    - electron-app/src/renderer/components/knowledge/editor-types.ts
    - electron-app/src/renderer/components/knowledge/document-editor.tsx
decisions:
  - "documentLock query key added to centralized queryKeys for cache management"
  - "userName parameter kept in options interface for future use (prefixed with _ to suppress lint)"
metrics:
  duration: "~6 min"
  completed: "2026-02-01"
---

# Phase 5 Plan 2: Frontend Lock Hook, Banner, and Editor Integration Summary

**One-liner:** useDocumentLock hook with heartbeat/inactivity/WebSocket, LockBanner component, and editor read-only toggle

## What Was Built

### Task 1: WebSocket Message Types + useDocumentLock Hook
- Added `DOCUMENT_LOCKED`, `DOCUMENT_UNLOCKED`, `DOCUMENT_FORCE_TAKEN` to the `MessageType` enum in `websocket.ts`
- Added `documentLock` query key to centralized `queryKeys` in `query-client.ts`
- Created `useDocumentLock` hook with:
  - **Lock status query** via `GET /api/documents/{id}/lock` with 30s fallback poll
  - **Acquire mutation** via `POST /api/documents/{id}/lock` (handles 409 conflict)
  - **Release mutation** via `DELETE /api/documents/{id}/lock` (calls onBeforeRelease first)
  - **Force-take mutation** via `POST /api/documents/{id}/lock/force-take`
  - **Heartbeat** at 10s intervals while lock is held (detects 409 lock-lost)
  - **Inactivity timer** checking every 5s, auto-releases after 30s of no activity (saves first)
  - **WebSocket subscription** for real-time lock state updates (setQueryData for instant UI)
  - **Unmount cleanup** with fire-and-forget release and timer cleanup
- Exported hook and types from `hooks/index.ts`

### Task 2: LockBanner Component + Editor Integration
- Created `LockBanner` component with three states:
  - **Locked by me:** Blue banner with Lock icon, "You are editing this document", "Stop editing" button
  - **Locked by other:** Amber banner with Unlock icon, "Being edited by {name}", optional "Take over editing" for owners
  - **Unlocked:** Returns null (no banner)
- Extended `DocumentEditorProps` with `documentId`, `userId`, `userName`, `userRole`, `onSaveNow`
- Integrated `useDocumentLock` into `DocumentEditor`:
  - Computes `effectiveEditable = editable && !lock.isLockedByOther`
  - Syncs editor `setEditable()` on lock state changes
  - Renders LockBanner between toolbar and EditorContent
  - Lock integration is gracefully optional (inactive when documentId not provided)

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- TypeScript strict mode compilation passes (zero new errors in changed files)
- All pre-existing errors are in unrelated files (member-list, comments, etc.)

## Commits

| Hash | Message |
|------|---------|
| 2d7a53c | feat(05-02): useDocumentLock hook with WebSocket message types |
| a82e09f | feat(05-02): LockBanner component and editor lock integration |

## Next Phase Readiness

Phase 5 (Document Locking) is now complete:
- Backend: Redis-backed lock service with Lua scripts, REST endpoints, WebSocket broadcast (Plan 01)
- Frontend: Lock hook, banner UI, editor integration (Plan 02)

Ready for Phase 6+ which will wire the lock into the knowledge page, passing documentId/userId/userRole props down to DocumentEditor from the page-level component.

---
phase: 01-migration-and-data-foundation
plan: 02
subsystem: ui
tags: [react-context, zustand-removal, import-migration, tsconfig]

# Dependency graph
requires:
  - phase: 01-migration-and-data-foundation (plan 01)
    provides: Notes store removed, auth-store and notification-ui-store shims isolated
provides:
  - Zero Zustand references in entire codebase
  - All auth imports point directly to @/contexts/auth-context
  - All notification-ui imports point directly to @/contexts/notification-ui-context
  - stores/ directory removed, @/stores path alias removed
affects: [02-backend-api, 03-frontend-core, 04-editor-and-content]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "React Context + useRef for accessing state in event callbacks (replaces Zustand getState())"

key-files:
  created: []
  modified:
    - electron-app/src/renderer/hooks/use-auth.ts
    - electron-app/src/renderer/hooks/use-queries.ts
    - electron-app/src/renderer/hooks/use-websocket-cache.ts
    - electron-app/src/renderer/pages/dashboard.tsx
    - electron-app/tsconfig.json

key-decisions:
  - "useRef pattern for auth state in WebSocket callbacks replaces Zustand getState()"

patterns-established:
  - "Context + ref pattern: When accessing auth state in event callbacks outside React render cycle, use useRef to hold current value"

# Metrics
duration: 8min
completed: 2026-01-31
---

# Phase 1 Plan 2: Remove Store Shims Summary

**Eliminated all Zustand store shims by redirecting 27 files to React Context imports and removing stores/ directory + tsconfig alias**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-01T00:19:29Z
- **Completed:** 2026-02-01T00:27:47Z
- **Tasks:** 2
- **Files modified:** 28

## Accomplishments
- Redirected 25 auth-store imports and 2 notification-ui-store imports directly to their Context sources
- Fixed 2 instances of Zustand's `.getState()` pattern (dashboard.tsx, use-websocket-cache.ts) with React hook + useRef
- Removed @/stores/* path alias from tsconfig.json
- Verified zero @/stores imports, zero zustand package imports, stores/ directory deleted

## Task Commits

Each task was committed atomically:

1. **Task 1: Update all auth-store imports to auth-context** - `e960255` (refactor)
2. **Task 2: Delete store shims, remove stores directory, clean up** - `37ef63c` (chore)

## Files Created/Modified
- `electron-app/src/renderer/hooks/use-auth.ts` - Import path updated (2 locations)
- `electron-app/src/renderer/hooks/use-queries.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-websocket-cache.ts` - Import path + getState() fix with useRef
- `electron-app/src/renderer/pages/dashboard.tsx` - Import path + getState() fix with hook selector
- `electron-app/src/renderer/hooks/use-websocket.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-notifications.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-members.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-invitations.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-comments.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-checklists.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-attachments.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-task-viewers.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-presence.ts` - Import path updated
- `electron-app/src/renderer/hooks/use-websocket-cache.ts` - Import path updated
- `electron-app/src/renderer/pages/projects/[id].tsx` - Import path updated
- `electron-app/src/renderer/pages/applications/[id].tsx` - Import path updated
- `electron-app/src/renderer/components/tasks/task-detail.tsx` - Import path updated
- `electron-app/src/renderer/components/tasks/task-kanban-board.tsx` - Import path updated
- `electron-app/src/renderer/components/projects/project-board.tsx` - Import path updated
- `electron-app/src/renderer/components/projects/ProjectMemberPanel.tsx` - Import path updated
- `electron-app/src/renderer/components/projects/ProjectStatusOverride.tsx` - Import path updated
- `electron-app/src/renderer/components/kanban/KanbanBoard.tsx` - Import path updated
- `electron-app/src/renderer/components/invitations/invitation-modal.tsx` - Import path updated
- `electron-app/src/renderer/components/editor/RichTextEditor.tsx` - Import path updated
- `electron-app/src/renderer/components/comments/CommentThread.tsx` - Import path updated
- `electron-app/src/renderer/components/comments/CommentItem.tsx` - Import path updated
- `electron-app/src/renderer/components/layout/notification-panel.tsx` - Import paths updated (auth + notification-ui)
- `electron-app/src/renderer/components/layout/sidebar.tsx` - Import path updated
- `electron-app/tsconfig.json` - Removed @/stores/* path alias

## Decisions Made
- Replaced `useAuthStore.getState().user?.id` (Zustand pattern) with React hook + useRef in use-websocket-cache.ts for accessing auth state in WebSocket event callbacks
- Replaced `useAuthStore.getState().user?.id` with direct hook selector in dashboard.tsx (callback already had closure access)
- zustand package was already absent from package.json, no removal needed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed useAuthStore.getState() calls breaking with React Context**
- **Found during:** Task 1 (import updates)
- **Issue:** Two files (dashboard.tsx, use-websocket-cache.ts) called `useAuthStore.getState()` which is a Zustand-specific API not available on React Context hooks
- **Fix:** In use-websocket-cache.ts, added `currentUserRef` (useRef) updated via useEffect, used in callback. In dashboard.tsx, extracted `currentUser` via hook selector and used in callback closure.
- **Files modified:** dashboard.tsx, use-websocket-cache.ts
- **Verification:** TypeScript compilation passes for these files
- **Committed in:** e960255 (Task 1 commit)

**2. [Rule 3 - Blocking] Store file deletions were picked up by concurrent 01-03 commit**
- **Found during:** Task 2 (store deletion)
- **Issue:** The `git rm` commands ran between Task 1 commit and the concurrent 01-03 commit, which absorbed the store file deletions
- **Fix:** Task 2 commit focused on the remaining tsconfig.json cleanup. Store files confirmed deleted regardless.
- **Files modified:** tsconfig.json only (store deletions in 900c1ff)
- **Verification:** stores/ directory does not exist, no @/stores references remain

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered
- Pre-existing TypeScript errors (52 errors unrelated to stores migration) exist in the codebase. Our changes reduced this from 54 to 52 by fixing the `.getState()` type errors.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Zustand completely eliminated from codebase
- All state management now via React Context (auth, notification-ui) and TanStack Query (data fetching)
- Ready for Plan 01-03 (database models) and Plan 01-04 (remaining migration work)

---
*Phase: 01-migration-and-data-foundation*
*Completed: 2026-01-31*

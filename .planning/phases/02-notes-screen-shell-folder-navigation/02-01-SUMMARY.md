---
phase: 02-notes-screen-shell-folder-navigation
plan: 01
subsystem: ui
tags: [react, tanstack-query, context, indexeddb, tiptap, sidebar]

# Dependency graph
requires:
  - phase: 01-migration-and-data-foundation
    provides: Document, DocumentFolder, DocumentTag models and CRUD APIs
provides:
  - KnowledgeBaseContext for shared UI state (scope, selection, search, tags)
  - TanStack Query hooks for documents, folders, and tags (CRUD operations)
  - Notes page shell with sidebar + content layout
  - Query key definitions and IndexedDB hydration priority for knowledge base
affects:
  - 02-02 (folder tree rendering depends on useFolderTree hook and KnowledgeBaseContext)
  - 02-03 (scope filter and tag filter use KnowledgeBaseContext and useDocumentTags)
  - 03 (editor core will use useDocument hook and KnowledgeBaseContext selection state)
  - 04 (auto-save will use useDocument and mutation hooks)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "KnowledgeBaseContext: useReducer + useCallback pattern for UI-only state (no data fetching)"
    - "Debounced search: local state + useEffect timeout for 300ms debounce"
    - "Scope resolution: frontend 'personal' mapped to API 'personal' + userId"

key-files:
  created:
    - electron-app/src/renderer/contexts/knowledge-base-context.tsx
    - electron-app/src/renderer/hooks/use-document-folders.ts
    - electron-app/src/renderer/hooks/use-documents.ts
    - electron-app/src/renderer/hooks/use-document-tags.ts
    - electron-app/src/renderer/pages/notes/index.tsx
    - electron-app/src/renderer/components/knowledge/knowledge-sidebar.tsx
    - electron-app/src/renderer/components/knowledge/search-bar.tsx
  modified:
    - electron-app/src/renderer/lib/query-client.ts
    - electron-app/src/renderer/lib/cache-config.ts
    - electron-app/src/renderer/pages/dashboard.tsx
    - electron-app/src/renderer/components/layout/sidebar.tsx

key-decisions:
  - "Folder mutations (rename, move, delete) accept scope+scopeId params for targeted cache invalidation"
  - "Document mutations invalidate both document and folder queries (folder document_count changes)"
  - "Backend uses PUT for folder update (rename + move combined) -- hooks map to PUT not PATCH"
  - "Notes page removes padding from main content area for edge-to-edge sidebar layout"

patterns-established:
  - "Knowledge base hooks: separate files per entity (folders, documents, tags) following use-queries.ts conventions"
  - "Scope resolution helper: resolveScope() maps frontend scope types to API scope + scope_id"
  - "KnowledgeBaseProvider accepts optional initialScope/initialScopeId for dashboard integration"

# Metrics
duration: 11min
completed: 2026-01-31
---

# Phase 2 Plan 1: Notes Screen Foundation Summary

**TanStack Query hooks for document/folder/tag CRUD, KnowledgeBaseContext for UI state, Notes page shell with collapsible sidebar and debounced search**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-01T01:11:33Z
- **Completed:** 2026-02-01T01:22:55Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Three TanStack Query hook files providing all document, folder, and tag data fetching with proper cache invalidation
- Query keys registered in query-client.ts with IndexedDB hydration priority (deferred for folders, on-demand for documents/tags)
- KnowledgeBaseContext managing scope, sidebar state, folder expansion, document selection, search, and tag filters with localStorage persistence
- Notes page accessible from sidebar with collapsible sidebar layout and placeholder content area

## Task Commits

Each task was committed atomically:

1. **Task 1: Query keys, cache config, and TanStack Query hooks** - `9f8df26` (feat)
2. **Task 2: KnowledgeBaseContext, Notes page shell, sidebar, search bar** - `a9ad9c4` (feat)

## Files Created/Modified
- `electron-app/src/renderer/lib/query-client.ts` - Added documents, documentFolders, document, documentTags query keys
- `electron-app/src/renderer/lib/cache-config.ts` - Updated HYDRATION_PRIORITY with knowledge base entries
- `electron-app/src/renderer/hooks/use-document-folders.ts` - useFolderTree, useCreateFolder, useRenameFolder, useMoveFolder, useDeleteFolder
- `electron-app/src/renderer/hooks/use-documents.ts` - useDocuments, useDocument, useCreateDocument, useRenameDocument, useMoveDocument, useDeleteDocument
- `electron-app/src/renderer/hooks/use-document-tags.ts` - useDocumentTags
- `electron-app/src/renderer/contexts/knowledge-base-context.tsx` - KnowledgeBaseProvider, useKnowledgeBase
- `electron-app/src/renderer/pages/notes/index.tsx` - Notes page shell with sidebar + content layout
- `electron-app/src/renderer/components/knowledge/knowledge-sidebar.tsx` - Sidebar with collapse toggle, search, and placeholder sections
- `electron-app/src/renderer/components/knowledge/search-bar.tsx` - Debounced search input (300ms)
- `electron-app/src/renderer/pages/dashboard.tsx` - Added notes case routing with applicationId prop
- `electron-app/src/renderer/components/layout/sidebar.tsx` - Added 'notes' NavItem with FileText icon

## Decisions Made
- Backend folder endpoint uses PUT (not PATCH) for updates that include both rename and move -- hooks use `window.electronAPI.put` accordingly
- Document mutations invalidate both document list and folder tree queries since folder document_count can change
- Notes page removes main content padding (`p-0 overflow-hidden`) for edge-to-edge sidebar rendering
- Added 'notes' to sidebar NavItem type and nav items list (required for dashboard routing, not explicitly in plan but necessary)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added 'notes' NavItem to sidebar component**
- **Found during:** Task 2 (Dashboard integration)
- **Issue:** NavItem type did not include 'notes', so dashboard routing to notes case would fail
- **Fix:** Added 'notes' to NavItem union type and added FileText icon nav entry in sidebar.tsx
- **Files modified:** electron-app/src/renderer/components/layout/sidebar.tsx
- **Committed in:** a9ad9c4 (Task 2 commit)

**2. [Rule 3 - Blocking] Removed main content padding for notes view**
- **Found during:** Task 2 (Notes page layout)
- **Issue:** Dashboard main area has p-4 padding which would break sidebar's edge-to-edge h-full layout
- **Fix:** Added conditional class `activeItem === 'notes' && "p-0 overflow-hidden"` to main element
- **Files modified:** electron-app/src/renderer/pages/dashboard.tsx
- **Committed in:** a9ad9c4 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes required for the Notes page to render correctly. No scope creep.

## Issues Encountered
- ESLint configuration not found (eslint.config.js missing for ESLint 9.x) -- pre-existing issue, not introduced by this plan. Typecheck used as primary verification.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- KnowledgeBaseContext ready for Plan 02 folder tree to consume (expandedFolderIds, toggleFolder, selectFolder)
- useFolderTree hook ready for Plan 02 to call and render
- KnowledgeSidebar has clearly marked placeholder sections for Plan 02 (folder tree) and Plan 03 (scope filter, tag filter)
- SearchBar debounced search updates context which Plan 02 folder tree can filter by

---
*Phase: 02-notes-screen-shell-folder-navigation*
*Completed: 2026-01-31*

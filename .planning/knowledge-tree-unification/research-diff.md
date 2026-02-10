# Knowledge Tree Component Diff Analysis

Exhaustive line-by-line comparison of three tree components used in the knowledge base feature.

**Files compared:**
- `KnowledgeTree` (KT) - `knowledge-tree.tsx` (~1041 lines)
- `ApplicationTree` (AT) - `application-tree.tsx` (~1263 lines)
- `FolderTree` (FT) - `folder-tree.tsx` (~807 lines)

**Shared utilities:**
- `dnd-utils.ts` (71 lines) - `makeSortableId`, `parseSortableId`, `parsePrefixToScope`, `ScopeInfo`
- `tree-utils.ts` (57 lines) - `matchesSearch`, `filterFolderTree`, `findFolderById`, `isDescendantOf`

---

## 1. Component Props

| Component | Props Interface | Details |
|-----------|----------------|---------|
| **KT** | `KnowledgeTreeProps` | `applicationId?: string` (optional) |
| **AT** | `ApplicationTreeProps` | `applicationId: string` (required) |
| **FT** | None (no props) | Uses scope/scopeId entirely from `useKnowledgeBase()` context |

**Key observation:** KT is designed as a unified component that can operate in either "application" or "personal/context" mode based on whether `applicationId` prop is provided. AT always operates in application scope. FT always reads scope from context.

---

## 2. Imports

### Identical across all three:
- `useState, useCallback, useMemo, useEffect` from React
- `toast` from `sonner`
- `DndContext, DragEndEvent, DragOverEvent, DragOverlay, DragStartEvent, PointerSensor, useSensor, useSensors, closestCenter` from `@dnd-kit/core`
- `SortableContext` from `@dnd-kit/sortable`
- `useQueryClient` from `@tanstack/react-query`
- `cn` from `@/lib/utils`
- `queryKeys` from `@/lib/query-client`
- `useFolderTree, useCreateFolder, useRenameFolder, useDeleteFolder, useMoveFolder, type FolderTreeNode` from `@/hooks/use-document-folders`
- `useDocuments, useCreateDocument, useRenameDocument, useDeleteDocument, useMoveDocument, type Document, type DocumentListItem, type DocumentListResponse` from `@/hooks/use-documents`
- `useActiveLocks` from `@/hooks/use-document-lock`
- `FolderTreeItem` from `./folder-tree-item`
- `FolderDocuments` from `./folder-documents`
- `RootDropZone, ROOT_DROP_ZONE_ID` from `./root-drop-zone`
- `FolderContextMenu` from `./folder-context-menu`
- `CreateDialog` from `./create-dialog`
- `DeleteDialog` from `./delete-dialog`
- `matchesSearch, filterFolderTree, findFolderById, isDescendantOf` from `./tree-utils`

### Differences:

| Import | KT | AT | FT |
|--------|----|----|-----|
| **Lucide icons** | `FilePlus, Folder, FileText, FolderKanban, ChevronRight` | `FilePlus, Folder, FileText, FolderKanban, ChevronRight, Loader2` | `FilePlus, Folder, FileText` |
| **`useAuthStore`** | YES | NO | YES |
| **`useKnowledgeBase`** | YES | YES | YES |
| **`useProjects, type Project`** | YES | YES | NO |
| **`useProjectsWithContent`** | YES (from `use-documents`) | YES (from `use-documents`) | NO |
| **`TreeSkeleton`** | YES | YES | YES |
| **`ProjectContentSkeleton`** | YES | YES | NO |
| **`parseSortableId`** | YES | YES | YES |
| **`parsePrefixToScope, type ScopeInfo`** | YES | YES | NO |

**AT-only imports:** `Loader2` (for background refresh spinner)
**KT and FT imports:** `useAuthStore` (for personal scope userId resolution)
**AT and KT imports:** `useProjects`, `useProjectsWithContent`, `ProjectContentSkeleton`, `parsePrefixToScope`, `ScopeInfo`
**FT-only missing:** No project-related imports at all, no `parsePrefixToScope`/`ScopeInfo`

---

## 3. Type Definitions

### ContextMenuTarget

| Field | KT | AT | FT |
|-------|----|----|-----|
| `id` | `string` | `string` | `string` |
| `type` | `'folder' \| 'document'` | `'folder' \| 'document'` | `'folder' \| 'document'` |
| `name` | `string` | `string` | `string` |
| `x` | `number` | `number` | `number` |
| `y` | `number` | `number` | `number` |
| `scope` | `'application' \| 'project' \| 'personal'` | `'application' \| 'project'` | `string` |
| `scopeId` | `string` | `string` | `string` |

**Key diff:** KT allows `'personal'` scope. AT only `'application' | 'project'`. FT uses generic `string`.

### ActiveDragItem

| Field | KT | AT | FT |
|-------|----|----|-----|
| `id` | `string` | `string` | `string` |
| `type` | `'folder' \| 'document'` | `'folder' \| 'document'` | `'folder' \| 'document'` |
| `name` | `string` | `string` | `string` |
| `scope` | `string` | `string` | **MISSING** |
| `folderId` | `string \| null` | `string \| null` | `string \| null` |

**Key diff:** FT's `ActiveDragItem` does NOT have a `scope` field - it operates in a single-scope context.

---

## 4. ProjectSection Component

Both **KT** and **AT** have an internal `ProjectSection` component. **FT** does not have one.

### ProjectSectionProps

| Prop | KT | AT |
|------|----|----|
| `project` | `Project` | `Project` |
| `expandedFolderIds` | `Set<string>` | `Set<string>` |
| `selectedDocumentId` | `string \| null` | `string \| null` |
| `renamingItemId` | `string \| null` | `string \| null` |
| `activeItem` | `ActiveDragItem \| null` | `ActiveDragItem \| null` |
| `dropTargetFolderId` | `string \| null` | `string \| null` |
| `contextMenuFolderId` | `string \| null` | `string \| null` |
| **`hideIfEmpty`** | **NO** | **YES** (`hideIfEmpty?: boolean`, default `false`) |
| `onToggleFolder` | `(folderId: string) => void` | `(folderId: string) => void` |
| `onSelectDocument` | `(documentId: string) => void` | `(documentId: string) => void` |
| `onContextMenu` | 6 params (scope includes `'personal'`) | 6 params (scope `'application' \| 'project'` only) |
| `onRenameSubmit` | `(newName: string) => void` | `(newName: string) => void` |
| `onRenameCancel` | `() => void` | `() => void` |

### ProjectSection Function

| Aspect | KT | AT |
|--------|----|----|
| **Return type** | `JSX.Element` | `JSX.Element \| null` |
| **isEmpty check** | NO | YES - has `isEmpty` useMemo + conditional `return null` when `hideIfEmpty && isExpanded && isEmpty && !isLoading` |
| **toggleExpanded** | `setIsExpanded((prev) => !prev)` (identical) | Same |
| **Hooks** | Identical set: `useFolderTree`, `useDocuments`, `useActiveLocks`, `useMemo` for sortableItems, `useCallback` for noReorderStrategy/renderFolderNode/renderDocumentItem | Same, plus `useMemo` for `isEmpty` |
| **Render output** | Identical JSX structure | Identical JSX structure |
| **onContextMenu scope param** | `'application' \| 'project' \| 'personal'` | `'application' \| 'project'` |

### ProjectSection renderFolderNode and renderDocumentItem

These are **functionally identical** between KT and AT. The only differences are the scope type in the `onContextMenu` callback signature.

---

## 5. Main Component Hooks

### Context hooks

| Hook | KT | AT | FT |
|------|----|----|-----|
| `useKnowledgeBase()` destructured | `scope, scopeId, expandedFolderIds, selectedDocumentId, searchQuery, toggleFolder, expandFolder, selectDocument` | `expandedFolderIds, selectedDocumentId, searchQuery, toggleFolder, expandFolder, selectDocument` | `scope, scopeId, expandedFolderIds, selectedDocumentId, searchQuery, toggleFolder, expandFolder, selectDocument` |
| `useAuthStore()` | YES - `userId = useAuthStore((s) => s.user?.id ?? null)` | NO | YES - `userId = useAuthStore((s) => s.user?.id ?? null)` |

**Key diff:** AT does NOT read `scope`/`scopeId` from context - it hardcodes `'application'` scope. KT reads them but may override with `applicationId` prop. FT reads them directly.

### Scope Resolution

| Component | Logic |
|-----------|-------|
| **KT** | `isApplicationScope = !!applicationId`; `scope = isApplicationScope ? 'application' : contextScope`; `scopeId = isApplicationScope ? applicationId : contextScopeId`; `effectiveScopeId = scope === 'personal' ? userId : scopeId` |
| **AT** | Always `'application'` scope, always `applicationId` as scopeId. No resolution needed. |
| **FT** | Uses `scope` and `scopeId` directly from `useKnowledgeBase()` context. Has `userId` for personal scope resolution in `handleCreateSubmit`. |

### Data Queries

| Query | KT | AT | FT |
|-------|----|----|-----|
| `useFolderTree` | `(scope, effectiveScopeId)` | `('application', applicationId)` + destructures `isFetching: isFoldersFetching` | `(scope, scopeId)` |
| `useDocuments` | `(scope, effectiveScopeId, { includeUnfiled: true })` | `('application', applicationId, { includeUnfiled: true })` | `(scope, scopeId, { includeUnfiled: true })` |
| `useActiveLocks` | `(scope, effectiveScopeId)` | `('application', applicationId)` | `(scope, scopeId)` |
| `useProjects` | `isApplicationScope ? applicationId : undefined` | `applicationId` | **NOT USED** |
| `useProjectsWithContent` | `isApplicationScope ? applicationId! : null` | `applicationId` + destructures `isLoading: isProjectsContentLoading` | **NOT USED** |

**AT-only:** Destructures `isFetching: isFoldersFetching` from `useFolderTree` (used for background refresh indicator). Also destructures `isLoading: isProjectsContentLoading` from `useProjectsWithContent`.

### Mutation Hooks

All three use the exact same set of mutation hooks:
- `useCreateFolder()`
- `useCreateDocument()`
- `useRenameFolder()`
- `useRenameDocument()`
- `useDeleteFolder()`
- `useDeleteDocument()`
- `useMoveFolder()`
- `useMoveDocument()`
- `useQueryClient()`

---

## 6. Cache Lookup Functions

### `findDocInCache`

| Component | Signature | Logic |
|-----------|-----------|-------|
| **KT** | `(documentId: string): DocumentListItem \| null` | Searches ALL document query caches broadly: `queryKey: ['documents'], exact: false`. Single-pass search across all scopes. |
| **AT** | `(documentId: string, docScope?: string, docScopeId?: string): DocumentListItem \| null` | Searches specific scope first (if provided), then falls back to application scope. Uses `queryKeys.documents(s, sid)` for scoped search. Two-pass strategy. |
| **FT** | `(documentId: string): DocumentListItem \| null` | Searches only the current scope: `queryKey: queryKeys.documents(scope, scopeId ?? ''), exact: false`. Single scope only. |

**Analysis:** This is a significant functional difference:
- KT does a global search across all caches (broadest)
- AT searches a specific scope then falls back to app scope (two-tier)
- FT only searches within its own scope (narrowest)

### `getDocRowVersion`

| Component | Signature | Logic |
|-----------|-----------|-------|
| **KT** | `(documentId: string): number \| null` | Gets from document detail cache, falls back to `findDocInCache(documentId)` |
| **AT** | `(documentId: string, docScope?: string, docScopeId?: string): number \| null` | Gets from document detail cache, falls back to `findDocInCache(documentId, docScope, docScopeId)` |
| **FT** | `(documentId: string): number \| null` | Gets from document detail cache, falls back to `findDocInCache(documentId)` |

**Diff:** AT passes extra scope parameters through; KT and FT use simpler signature.

### `getScopeFromPrefix`

| Component | Present? | Logic |
|-----------|----------|-------|
| **KT** | YES | `parsePrefixToScope(prefix)` -> fallback `{ scope, scopeId: effectiveScopeId ?? '' }` |
| **AT** | YES | `parsePrefixToScope(prefix)` -> fallback `{ scope: 'application', scopeId: applicationId }` |
| **FT** | NO | Not needed - single scope, uses `scope`/`scopeId` directly |

---

## 7. DnD State and Handlers

### State

| State | KT | AT | FT |
|-------|----|----|-----|
| `activeItem` | `ActiveDragItem \| null` (has `scope`) | `ActiveDragItem \| null` (has `scope`) | `ActiveDragItem \| null` (**no `scope`**) |
| `dropTargetFolderId` | `string \| null` | `string \| null` | `string \| null` |

### `getFolderTree` helper

| Component | Present? | Logic |
|-----------|----------|-------|
| **KT** | YES | Parses prefix, returns main `folders` for non-project, looks up project folder tree from cache for `project:{id}` prefix |
| **AT** | NO (inline) | In `handleDragEnd` and `handleDragOver`: resolves `isProjectScope` from prefix, looks up project folder tree from cache inline |
| **FT** | NO | Single scope - always uses local `folders` directly |

### Sortable Items

| Component | Variable Name | Prefix Logic |
|-----------|--------------|--------------|
| **KT** | `sortableItems` | `isApplicationScope ? 'app' : 'personal'` |
| **AT** | `appLevelSortableItems` | Always `'app'` |
| **FT** | `sortableItems` | Uses `scope` directly (e.g. `'application'`, `'personal'`, `'project'`) |

### `validPrefixes`

| Component | Value |
|-----------|-------|
| **KT** | `[dndPrefix]` where `dndPrefix = isApplicationScope ? 'app' : 'personal'` |
| **AT** | `['app']` |
| **FT** | `[scope]` |

### `handleDragStart`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| Name resolution | Checks `parsed.prefix === dndPrefix` before searching folders/docs | Checks `parsed.prefix === 'app'` before searching | No prefix check - always searches (single scope) |
| folderId lookup | `findDocInCache(parsed.itemId)?.folder_id` (no scope params) | `findDocInCache(parsed.itemId, docScope, docScopeId)` with project scope awareness | `findDocInCache(parsed.itemId)?.folder_id` (no scope params) |
| setActiveItem | Includes `scope: parsed.prefix` | Includes `scope: parsed.prefix` | **No `scope` field** |

### `handleDragOver`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| parentFolder lookup | `findDocInCache(overParsed.itemId)?.folder_id` (no scope params) | `findDocInCache(overParsed.itemId, docScope, docScopeId)` with project scope | `findDocInCache(overParsed.itemId)?.folder_id` (no scope params) |
| descendant check | `isDescendantOf(getFolderTree(activeParsed.prefix), ...)` | `isDescendantOf(relevantFolders, ...)` where `relevantFolders` is inline resolved | `isDescendantOf(folders, ...)` using local folders directly |
| Dependencies | `[parse, findDocInCache, getFolderTree, activeItem]` | `[parse, findDocInCache, folders, applicationId, queryClient, activeItem]` | `[parse, findDocInCache, folders, activeItem]` |

### `isRootFolder`

| Component | Logic |
|-----------|-------|
| **KT** | Checks main `folders`, ALSO searches all `['documentFolders']` caches (cross-scope) |
| **AT** | Checks main `folders`, ALSO searches all `['documentFolders']` caches (cross-scope) |
| **FT** | Only checks main `folders` (single scope) |

### `isRootDocument`

| Component | Logic |
|-----------|-------|
| **KT** | Checks `unfiledDocs`, then uses `findDocInCache` (broad search) |
| **AT** | Checks `unfiledDocs`, then searches ALL `['documents']` caches with `queryClient.getQueriesData` |
| **FT** | Only checks `unfiledDocs` (single scope) |

### `moveItemToRoot`

| Component | Signature | Scope handling |
|-----------|-----------|---------------|
| **KT** | `(parsed: { prefix, type, itemId })` | Uses `getScopeFromPrefix(parsed.prefix)` |
| **AT** | `(parsed: { prefix, type, itemId })` | Uses `getScopeFromPrefix(parsed.prefix)` |
| **FT** | `(parsed: { type, itemId })` | Uses `scope`/`scopeId` directly (no prefix) |

### `handleDragEnd`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| Cross-scope check | `activeParsed.prefix !== overParsed.prefix` - returns early | `activeParsed.prefix !== overParsed.prefix` - returns early | **No cross-scope check** (single scope) |
| Folder tree for descendant check | `getFolderTree(activeParsed.prefix)` | Inline resolution: `isProjectScope ? queryClient.getQueryData(...) : folders` | `folders` (local) |
| findDocInCache calls | No scope params | With `docScope, docScopeId` params | No scope params |
| getDocRowVersion calls | No scope params | With `docScope, docScopeId` params | No scope params |
| Mutation scope params | `...itemScope` from `getScopeFromPrefix` | `...itemScope` from `getScopeFromPrefix` | `scope, scopeId: scopeId ?? ''` directly |

---

## 8. Context Menu Handlers

### `handleContextMenu`

| Component | Signature | Scope handling |
|-----------|-----------|---------------|
| **KT** | `(e, id, type, name, menuScope = scope as cast, menuScopeId = effectiveScopeId ?? '')` | 6 params with defaults. Sets `scope: menuScope, scopeId: menuScopeId` on target. |
| **AT** | `(e, id, type, name, scope = 'application', scopeId = '')` | 6 params with `'application'` default. Sets `scopeId: scopeId \|\| applicationId` on target. |
| **FT** | `(e, id, type, name)` | **4 params only.** Sets `scope, scopeId: scopeId ?? ''` from context. |

**Key diff:** FT has a simpler 4-param signature because it doesn't need to handle project sub-scopes.

---

## 9. CRUD Handlers

### `handleNewFolder` / `handleNewDocument`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| Scope capture | From `contextMenuTarget?.scope` with fallback to `scope as cast` | From `contextMenuTarget?.scope` with fallback to `'application'` | **No scope capture** - no `createScope`/`createScopeId` state |
| State set | `setCreateScope(...)`, `setCreateScopeId(...)` | `setCreateScope(...)`, `setCreateScopeId(...)` | Only `setCreateType`, `setCreateParentId` |

### `handleCreateSubmit`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| Scope resolution | `resolvedScopeId = createScope === 'personal' ? (userId ?? '') : createScopeId` | Uses `createScope` and `createScopeId` directly | `resolvedScopeId = scope === 'personal' ? (userId ?? '') : (scopeId ?? '')` |
| Mutation params scope | `scope: createScope, scope_id: resolvedScopeId` | `scope: createScope, scope_id: createScopeId` | `scope, scope_id: resolvedScopeId` |

### `handleRename` / `handleRenameSubmit` / `handleRenameCancel`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| Scope tracking state | `renamingItemScope`, `renamingItemScopeId` | `renamingItemScope`, `renamingItemScopeId` | **NONE** |
| `handleRename` sets | `setRenamingItemScope(contextMenuTarget?.scope)`, `setRenamingItemScopeId(contextMenuTarget?.scopeId)` | Same | Only `setRenamingItemId`, `setRenamingItemType` |
| `handleRenameSubmit` scope | `itemScope = renamingItemScope ?? scope`, `itemScopeId = renamingItemScopeId ?? effectiveScopeId ?? ''` | `itemScope = renamingItemScope ?? 'application'`, `itemScopeId = renamingItemScopeId ?? applicationId` | Uses `scope, scopeId: scopeId ?? ''` directly |
| `handleRenameCancel` | Resets 3 states | Resets 3 states | Resets 1 state (`renamingItemId`) |

### `handleDelete` / `handleDeleteConfirm`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| `deleteTarget` type | `{ id, type, name, scope: string \| null, scopeId: string \| null }` | `{ id, type, name, scope: 'application' \| 'project', scopeId: string }` | `{ id, type, name }` (no scope) |
| Scope capture in handleDelete | From `contextMenuTarget?.scope/scopeId` with null fallback | From `contextMenuTarget?.scope/scopeId` with `'application'`/`applicationId` fallback | **No scope capture** |
| `handleDeleteConfirm` scope | `itemScope = deleteTarget.scope ?? scope`, `itemScopeId = deleteTarget.scopeId ?? effectiveScopeId ?? ''` | `itemScope = deleteTarget.scope ?? 'application'`, `itemScopeId = deleteTarget.scopeId ?? applicationId` | Uses `scope, scopeId: scopeId ?? ''` directly |

---

## 10. UI State

### Complete state variable list

| State Variable | KT | AT | FT |
|----------------|----|----|-----|
| `activeItem` | YES (with `scope`) | YES (with `scope`) | YES (no `scope`) |
| `dropTargetFolderId` | YES | YES | YES |
| `renamingItemId` | YES | YES | YES |
| `renamingItemType` | YES | YES | YES |
| `renamingItemScope` | YES | YES | **NO** |
| `renamingItemScopeId` | YES | YES | **NO** |
| `contextMenuTarget` | YES | YES | YES |
| `createDialogOpen` | YES | YES | YES |
| `createType` | YES | YES | YES |
| `createParentId` | YES | YES | YES |
| `createScope` | YES (`'application' \| 'project' \| 'personal'`) | YES (`'application' \| 'project'`) | **NO** |
| `createScopeId` | YES (`string`, default `''`) | YES (`string`, default `applicationId`) | **NO** |
| `deleteDialogOpen` | YES | YES | YES |
| `deleteTarget` | YES (with `scope`, `scopeId` nullable) | YES (with `scope`, `scopeId` typed) | YES (no `scope`/`scopeId`) |

**Summary:** FT has 4 fewer state variables because it doesn't track per-item scope.

---

## 11. Loading / Skeleton Logic

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| Initial load variable | `isInitialLoad = (isFoldersLoading \|\| isUnfiledLoading) && !hasAnyData` (uses `hasAnyData` which checks `folders.length > 0 \|\| unfiledDocs.length > 0`) | `isLoading = (isFoldersLoading \|\| isUnfiledLoading \|\| isProjectsContentLoading) && folders.length === 0 && unfiledDocs.length === 0` | `isLoading = (isFoldersLoading \|\| isUnfiledLoading) && folders.length === 0 && unfiledDocs.length === 0` |
| Includes projects loading? | NO | YES (`isProjectsContentLoading`) | NO (no projects) |
| Background refresh indicator | NO | YES (`isFoldersFetching && !isFoldersLoading` -> `Loader2` spinner) | NO |

---

## 12. Search Filtering

### `filteredFolders` / `filteredDocs`

Identical across all three: `filterFolderTree(folders, searchQuery)` and `unfiledDocs.filter(doc => matchesSearch(doc.title, searchQuery))`.

### `filteredProjects`

| Component | Logic |
|-----------|-------|
| **KT** | If `!isApplicationScope`, returns `[]`. If `searchQuery`, filters by name match. Otherwise, filters by `projectIdsWithContent`. |
| **AT** | If `searchQuery`, filters by name match. Otherwise, filters by `projectIdsWithContent`. |
| **FT** | **No project filtering at all.** |

### Auto-expand effect

Identical across all three: `useEffect` that calls `expandFolder` on nodes with children in `filteredFolders` when `searchQuery` is non-empty.

---

## 13. Render Functions

### `renderFolderNode`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| `isDragging` check | `activeItem?.scope === prefix` (uses computed prefix) | `activeItem?.scope === 'app'` (hardcoded) | `activeItem?.id === node.id && activeItem?.type === 'folder'` (no scope check) |
| `sortableId` prefix | Computed `prefix` (`'app'` or `'personal'`) | `'app'` hardcoded | `scope` from context |
| `scope` prop on FolderDocuments | `scope` (computed) | `'application'` hardcoded | `scope` from context |
| `scopeId` prop on FolderDocuments | `effectiveScopeId` | `applicationId` | `scopeId` from context |
| `sortableIdPrefix` prop | `prefix` (computed) | `'app'` hardcoded | `scope` from context |
| `onContextMenu` on FolderTreeItem | `handleContextMenu(e, node.id, 'folder', node.name)` (4 params, no scope) | `handleContextMenu(e, node.id, 'folder', node.name, 'application', applicationId)` (6 params, explicit scope) | `handleContextMenu(e, node.id, 'folder', node.name)` (4 params) |
| `onContextMenu` on FolderDocuments | `handleContextMenu` (4 params passed through) | Wrapper `(e, id, type, name) => handleContextMenu(e, id, type, name, 'application', applicationId)` (wraps to add scope) | `handleContextMenu` (4 params passed through) |
| Dependencies | 16 deps including `isApplicationScope, scope, effectiveScopeId` | 14 deps including `applicationId` | 14 deps including `scope, scopeId` |

### `renderDocumentItem`

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| `isDragging` check | `activeItem?.scope === prefix` | `activeItem?.scope === 'app'` | `activeItem?.id === doc.id && activeItem?.type === 'document'` (no scope) |
| `sortableId` prefix | `prefix` | `'app'` | `scope` |
| `onContextMenu` | `handleContextMenu(e, doc.id, 'document', doc.title)` (4 params) | `handleContextMenu(e, doc.id, 'document', doc.title, 'application', applicationId)` (6 params) | `handleContextMenu(e, doc.id, 'document', doc.title)` (4 params) |
| Dependencies | 10 deps | 10 deps | 10 deps |

---

## 14. JSX Render Output

### hasNoData check

| Component | Check |
|-----------|-------|
| **KT** | `folders.length === 0 && unfiledDocs.length === 0 && (isApplicationScope ? projectIdsWithContent.size === 0 : true)` |
| **AT** | `folders.length === 0 && unfiledDocs.length === 0 && projectIdsWithContent.size === 0` |
| **FT** | `folders.length === 0 && unfiledDocs.length === 0` |

### hasNoResults check

| Component | Check |
|-----------|-------|
| **KT** | `filteredFolders.length === 0 && filteredDocs.length === 0 && filteredProjects.length === 0` |
| **AT** | `filteredFolders.length === 0 && filteredDocs.length === 0 && filteredProjects.length === 0` |
| **FT** | `filteredFolders.length === 0 && filteredDocs.length === 0` |

### Main tree structure

| Aspect | KT | AT | FT |
|--------|----|----|-----|
| Outer element | `<DndContext>` wraps `<div role="tree">` wrapping `<SortableContext>` then project sections then `<RootDropZone>` | Same structure but with extra background refresh `<Loader2>` indicator, app-level sections wrapped in `<>` fragments with length checks | `<DndContext>` wraps `<SortableContext>` wraps `<div role="tree">` (different nesting!) |
| Background refresh indicator | NO | YES - `{isFoldersFetching && !isFoldersLoading && <Loader2>}` | NO |
| Folder rendering | `filteredFolders.map(node => renderFolderNode(node, 0))` directly | `{filteredFolders.length > 0 && <>{filteredFolders.map(...)}</>}` (wrapped in conditional fragment) | `filteredFolders.map(node => renderFolderNode(node, 0))` directly |
| Doc rendering | `filteredDocs.map(doc => renderDocumentItem(doc, 0))` directly | `{filteredDocs.length > 0 && <>{filteredDocs.map(...)}</>}` (wrapped in conditional fragment) | `{filteredDocs.length > 0 && <>{filteredDocs.map(...)}</>}` (wrapped in conditional fragment) |
| Project sections | YES (conditional on `isApplicationScope`) | YES | NO |
| `hideIfEmpty` on ProjectSection | Not passed (not in KT's props) | Passed as `{false}` | N/A |
| RootDropZone | `{activeItem && <RootDropZone />}` inside tree div | Same | Same |
| DragOverlay | Outside tree div, inside DndContext | Same | Same |
| SortableContext nesting | Inside `<div role="tree">` | Inside `<div role="tree">` | **Wraps** `<div role="tree">` |

### `handleCreateFirstDocument`

| Component | Scope set |
|-----------|-----------|
| **KT** | `setCreateScope(scope as cast)`, `setCreateScopeId(effectiveScopeId ?? '')` |
| **AT** | `setCreateScope('application')`, `setCreateScopeId(applicationId)` |
| **FT** | No scope state - only `setCreateType` and `setCreateParentId` |

---

## 15. Export

| Component | Named export | Default export |
|-----------|-------------|----------------|
| **KT** | `export function KnowledgeTree` | `export default KnowledgeTree` |
| **AT** | `export function ApplicationTree` | `export default ApplicationTree` |
| **FT** | `export function FolderTree` | `export default FolderTree` |

---

## 16. Features Unique to Each Component

### KnowledgeTree Only
- **Personal scope support** with `useAuthStore` for `userId` resolution
- **Dual-mode operation** via optional `applicationId` prop (personal vs application)
- `effectiveScopeId` resolution (`scope === 'personal' ? userId : scopeId`)
- Scope casting with `as 'application' | 'project' | 'personal'`
- `isApplicationScope` boolean flag that gates project-related logic

### ApplicationTree Only
- **Background refresh indicator** (`Loader2` spinner when `isFoldersFetching && !isFoldersLoading`)
- **`hideIfEmpty` prop** on `ProjectSection` (plus `isEmpty` useMemo and `return null` logic in ProjectSection)
- **Scoped `findDocInCache`** - two-tier search with specific scope + fallback
- **Scoped `getDocRowVersion`** - passes scope params through
- **`isProjectsContentLoading`** included in main loading check
- Inline project folder tree resolution in DnD handlers (no `getFolderTree` helper)
- More detailed `isRootDocument` - searches all document list caches via `queryClient.getQueriesData`
- Conditional fragment wrappers around folder/doc rendering (`{filteredFolders.length > 0 && ...}`)

### FolderTree Only
- **Simplest implementation** - no project awareness at all
- **No scope tracking state** (`renamingItemScope`, `renamingItemScopeId`, `createScope`, `createScopeId` all absent)
- **No `scope` field in `ActiveDragItem`** - DnD is purely single-scope
- **4-param `handleContextMenu`** (no scope params)
- **Simplest `findDocInCache`** - only searches current scope
- **Simplest `isRootFolder`/`isRootDocument`** - only checks local data
- **Simplest `moveItemToRoot`** - no prefix param, uses scope/scopeId directly
- **No cross-scope DnD check** in `handleDragEnd`
- **`SortableContext` wraps `div[role=tree]`** (different nesting order from KT/AT)
- CACHE-03 loading behavior documented in file header comment

---

## 17. Dependency Lists Summary

Total `useCallback`/`useMemo` hooks per component:

| Hook Type | KT | AT | FT |
|-----------|----|----|-----|
| `useState` | 14 | 14 | 10 |
| `useCallback` | ~18 | ~18 | ~16 |
| `useMemo` | ~7 | ~6 | ~4 |
| `useEffect` | 1 | 1 | 1 |
| Custom hooks | ~13 | ~12 | ~11 |

---

## 18. Summary of Unification Considerations

### KnowledgeTree is already 90% of the unified solution
KT was designed as the unified component and handles both application and personal scopes. However, it lacks some features from AT:

1. **Background refresh indicator** (AT's `Loader2` spinner) - not in KT
2. **`hideIfEmpty` on ProjectSection** - not in KT
3. **Scoped cache lookups** (AT's 2-param `findDocInCache`) - KT uses a broad search instead
4. **`isProjectsContentLoading` in loading check** - not in KT
5. **AT's more thorough `isRootDocument`** that searches all document caches

### FolderTree should be replaceable by KnowledgeTree
FT is a simplified single-scope version. KT with no `applicationId` prop should function identically when `scope` is read from context.

### Differences that need resolution
- Cache lookup strategies (broad vs scoped vs single-scope)
- `ActiveDragItem.scope` field (present in KT/AT, absent in FT)
- `handleContextMenu` signature (6 params with defaults in KT/AT, 4 params in FT)
- `deleteTarget` type (nullable scope in KT, typed in AT, no scope in FT)
- `SortableContext` nesting (KT/AT: inside div, FT: wraps div)
- Loading condition (KT: `isInitialLoad` vs AT: `isLoading` with `isProjectsContentLoading`)

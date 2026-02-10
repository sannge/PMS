# Research: Tree Component Consumers and Integration Points

## 1. KnowledgeTree Consumers

### KnowledgeSidebar (`knowledge-sidebar.tsx`)

**Location**: `electron-app/src/renderer/components/knowledge/knowledge-sidebar.tsx`

**How it uses KnowledgeTree**:
```tsx
<KnowledgeTree
  applicationId={activeTab.startsWith('app:') ? activeTab.slice(4) : undefined}
/>
```

**Context values consumed from `useKnowledgeBase()`**:
- `isSidebarCollapsed` -- controls sidebar width (collapsed = 40px)
- `toggleSidebar` -- callback to toggle collapsed state
- `activeTab` -- determines scope: `'personal'` or `'app:{uuid}'`
- `selectedFolderId` -- used to create docs/folders in selected folder

**Other hooks/state**:
- `useAuthStore((s) => s.user?.id)` -- for personal scope resolution
- `useCreateDocument()` -- quick doc creation via sidebar button
- `useCreateFolder()` -- quick folder creation via sidebar button
- Local state: `createDialogOpen`, `createType`, `sidebarWidth`, `isResizing`
- Persists sidebar width to `localStorage` key `'knowledge-sidebar-width'`

**Sub-components rendered by KnowledgeSidebar**:
- `KnowledgeTree` (the tree)
- `TagFilterList` (tag filtering below tree)
- `CreateDialog` (create doc/folder dialog)
- `ScrollArea` (wraps tree)

**Layout**: Resizable sidebar with collapse toggle, create buttons, tree in scroll area, tag filter at bottom, resize handle on right edge.

---

### NotesPage (`pages/notes/index.tsx`)

**Location**: `electron-app/src/renderer/pages/notes/index.tsx`

**How it uses KnowledgeSidebar (which uses KnowledgeTree)**:
```tsx
<KnowledgeBaseProvider>
  <NotesPageContent />
</KnowledgeBaseProvider>
```

**NotesPageContent layout**:
1. `SearchBar` -- top full-width search bar
2. `KnowledgeTabBar` -- tab bar for personal/application tabs
3. `KnowledgeSidebar` -- left sidebar containing KnowledgeTree
4. `EditorPanel` -- right panel with document editor

**Provider setup**: `<KnowledgeBaseProvider>` with NO props (uses defaults: `storagePrefix='kb-'`)

**Context values consumed in NotesPageContent**:
- `activeTab` -- for WebSocket room joining
- `setActiveTab` -- passed to KnowledgeTabBar
- `selectedDocumentId` -- for EditorPanel
- `selectDocument` -- for WS document deletion events

**Hooks used in NotesPage**:
- `useApplicationsWithDocs()` -- for tab bar scope data
- `useAuthStore((s) => s.user?.id)` -- for WS room construction
- `useWebSocket()` -- for WS room join/leave and subscriptions
- `useEditMode({ documentId, userRole: null })` -- edit state machine
- `useQueryClient()` -- for invalidation on WS DOCUMENT_UPDATED events

---

## 2. KnowledgePanel Consumers

### KnowledgePanel (`knowledge-panel.tsx`)

**Location**: `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Props interface**:
```typescript
export interface KnowledgePanelProps {
  scope: ScopeType           // 'personal' | 'application' | 'project'
  scopeId: string            // UUID of the scope entity
  showProjectFolders?: boolean  // For application scope: show project sub-folders
  className?: string
}
```

**Provider setup**:
```tsx
<KnowledgeBaseProvider
  initialScope={scope}
  initialScopeId={scopeId}
  storagePrefix={`kb-${scope}-${scopeId}-`}
>
  <InnerPanel ... />
</KnowledgeBaseProvider>
```

**Tree selection logic** (line 217-222):
```tsx
{scope === 'application' && showProjectFolders ? (
  <ApplicationTree applicationId={scopeId} />
) : (
  <FolderTree />
)}
```

**InnerPanel context values consumed**:
- `selectedDocumentId` -- for editor panel
- `selectDocument` -- for document creation callback

**InnerPanel hooks**:
- `useEditMode({ documentId: selectedDocumentId, userRole: null })`
- `useCreateDocument()`
- `useCreateFolder()`

**InnerPanel layout**: Two-panel resizable layout:
- Left: SearchBar + create buttons + tree (ApplicationTree or FolderTree) in ScrollArea
- Resize handle (1px divider, draggable)
- Right: DocumentEditor with action bar, or empty state

**InnerPanel local state**: `treeWidth` (resizable, 200-500px, default 280)

---

### ApplicationDetailPage (`pages/applications/[id].tsx`)

**Usage** (lines 1083-1088):
```tsx
<KnowledgePanel
  scope="application"
  scopeId={applicationId}
  showProjectFolders
  className="flex-1"
/>
```

**Context**: Rendered when `activeView === 'knowledge'` (one of the view tabs on the application detail page). The page has a view switcher between 'projects', 'archive', and 'knowledge' views.

---

### ProjectDetailPage (`pages/projects/[id].tsx`)

**Usage** (lines 914-918):
```tsx
<KnowledgePanel
  scope="project"
  scopeId={project.id}
  className="h-full"
/>
```

**Context**: Rendered when the project detail page is showing the knowledge/notes view (not the board view). No `showProjectFolders` prop, so FolderTree is used (not ApplicationTree).

---

## 3. KnowledgeBase Context

**Location**: `electron-app/src/renderer/contexts/knowledge-base-context.tsx`

### ScopeType
```typescript
export type ScopeType = 'personal' | 'application' | 'project'
```

### KnowledgeBaseUIState (internal reducer state)
```typescript
interface KnowledgeBaseUIState {
  scope: ScopeType
  scopeId: string | null
  activeTab: string                    // 'personal' | 'app:{uuid}'
  isSidebarCollapsed: boolean
  expandedFolderIds: Set<string>
  selectedDocumentId: string | null
  selectedFolderId: string | null
  searchQuery: string
  activeTagIds: string[]
}
```

### NavigationGuard type
```typescript
export type NavigationGuard = (
  targetDocId: string | null,
  proceed: () => void
) => boolean
```

### KnowledgeBaseContextValue (full public interface)
```typescript
interface KnowledgeBaseContextValue extends KnowledgeBaseUIState {
  setScope: (scope: ScopeType, scopeId: string | null) => void
  setActiveTab: (tab: string) => void
  toggleSidebar: () => void
  toggleFolder: (folderId: string) => void
  expandFolder: (folderId: string) => void
  collapseFolder: (folderId: string) => void
  selectDocument: (documentId: string | null) => void
  selectFolder: (folderId: string | null) => void
  setSearch: (query: string) => void
  toggleTag: (tagId: string) => void
  clearTags: () => void
  resetSelection: () => void
  registerNavigationGuard: (guard: NavigationGuard) => void
  unregisterNavigationGuard: () => void
}
```

### KnowledgeBaseProvider props
```typescript
interface KnowledgeBaseProviderProps {
  children: ReactNode
  initialScope?: ScopeType          // Default: loaded from localStorage
  initialScopeId?: string | null    // Default: loaded from localStorage
  storagePrefix?: string            // Default: 'kb-'
}
```

### StoragePrefix scoping

The `storagePrefix` parameter prefixes all localStorage keys:
- `{prefix}sidebar-collapsed`
- `{prefix}expanded-folders`
- `{prefix}scope`
- `{prefix}scope-id`
- `{prefix}active-tab`

**NotesPage** uses default prefix `'kb-'`, resulting in keys like `kb-sidebar-collapsed`.

**KnowledgePanel** uses `kb-{scope}-{scopeId}-` (e.g., `kb-application-abc123-sidebar-collapsed`), so multiple instances do not share localStorage state.

### Context values used by each tree component

| Context Value | KnowledgeTree | FolderTree | ApplicationTree |
|---|---|---|---|
| `scope` | Yes (contextScope) | Yes | No (uses `'application'` directly) |
| `scopeId` | Yes (contextScopeId) | Yes | No (uses `applicationId` prop) |
| `expandedFolderIds` | Yes | Yes | Yes |
| `selectedDocumentId` | Yes | Yes | Yes |
| `searchQuery` | Yes | Yes | Yes |
| `toggleFolder` | Yes | Yes | Yes |
| `expandFolder` | Yes | Yes | Yes |
| `selectDocument` | Yes | Yes | Yes |
| `isSidebarCollapsed` | No | No | No |
| `toggleSidebar` | No | No | No |
| `activeTab` | No | No | No |
| `selectedFolderId` | No | No | No |
| `setSearch` | No | No | No |
| `activeTagIds` | No | No | No |

---

## 4. Shared Sub-Component Props Interfaces

### FolderTreeItem (`folder-tree-item.tsx`)

```typescript
export interface FolderTreeItemProps {
  node: FolderTreeNode | DocumentListItem
  type: 'folder' | 'document'
  depth: number
  isExpanded?: boolean
  isSelected: boolean
  isRenaming: boolean
  isDragging?: boolean
  isDropTarget?: boolean
  sortableId?: string
  lockInfo?: ActiveLockInfo
  onToggleExpand?: () => void
  onSelect: () => void
  onContextMenu: (e: React.MouseEvent) => void
  onRenameSubmit: (newName: string) => void
  onRenameCancel: () => void
}
```

**Internal sub-component**:
```typescript
interface DocumentLockIndicatorProps {
  lockInfo: ActiveLockInfo | undefined
  hidden?: boolean
}
```

### FolderDocuments (`folder-documents.tsx`)

```typescript
export interface FolderDocumentsProps {
  scope: string
  scopeId: string | null
  folderId: string
  depth: number
  selectedDocumentId: string | null
  renamingItemId: string | null
  sortableIdPrefix: string
  activeItemId: string | null
  activeLocks: Map<string, ActiveLockInfo>
  onSelectDocument: (documentId: string) => void
  onContextMenu: (e: React.MouseEvent, id: string, type: 'folder' | 'document', name: string) => void
  onRenameSubmit: (newName: string) => void
  onRenameCancel: () => void
}
```

**Internal hook**: `useDocuments(scope, scopeId, { folderId })` -- lazy-loads documents per folder.

### TreeSkeletons (`tree-skeletons.tsx`)

```typescript
// TreeItemSkeleton
{ depth?: number; widthPercent?: number }

// TreeSkeleton -- no props
// ProjectContentSkeleton -- no props
```

### RootDropZone (`root-drop-zone.tsx`)

```typescript
// No props. Uses useDroppable({ id: ROOT_DROP_ZONE_ID })
export const ROOT_DROP_ZONE_ID = '__root-drop-zone__'
```

### FolderContextMenu (`folder-context-menu.tsx`)

```typescript
export interface FolderContextMenuProps {
  target: {
    id: string
    type: 'folder' | 'document'
    name: string
  }
  position: { x: number; y: number }
  onClose: () => void
  onNewFolder: (parentId: string) => void
  onNewDocument: (folderId: string) => void
  onRename: (id: string) => void
  onDelete: (id: string, type: 'folder' | 'document') => void
}
```

### CreateDialog (`create-dialog.tsx`)

```typescript
export interface CreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  type: 'document' | 'folder'
  onSubmit: (name: string) => Promise<void>
}
```

### DeleteDialog (`delete-dialog.tsx`)

```typescript
export interface DeleteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  itemName: string
  itemType: 'document' | 'folder'
  onConfirm: () => Promise<void>
}
```

### SearchBar (`search-bar.tsx`)

```typescript
export interface SearchBarProps {
  className?: string
}
```

**Internal hooks**: `useKnowledgeBase()` for `searchQuery` and `setSearch`.

---

## 5. Hook Dependencies

### `useFolderTree(scope, scopeId)` (`use-document-folders.ts`)

```typescript
export function useFolderTree(
  scope: string,
  scopeId: string | null
): UseQueryResult<FolderTreeNode[], Error>
```

- Query key: `queryKeys.documentFolders(scope, effectiveScopeId)`
- For personal scope: uses `userId` as `effectiveScopeId`
- `select` transform: sorts tree case-insensitively at every level
- `refetchOnWindowFocus: false`
- `gcTime: 24h`

### `useCreateFolder()` (`use-document-folders.ts`)

```typescript
export function useCreateFolder(): UseMutationResult<DocumentFolder, Error, CreateFolderParams>

interface CreateFolderParams {
  name: string
  parent_id?: string | null
  scope: string
  scope_id: string
}
```

Optimistic update: adds temp folder to tree, replaces with real data on success.

### `useRenameFolder()` (`use-document-folders.ts`)

```typescript
export function useRenameFolder(): UseMutationResult<DocumentFolder, Error, RenameFolderParams>

interface RenameFolderParams {
  folderId: string
  name: string
  scope: string
  scopeId: string
}
```

### `useMoveFolder()` (`use-document-folders.ts`)

```typescript
export function useMoveFolder(): UseMutationResult<DocumentFolder, Error, MoveFolderParams>

interface MoveFolderParams {
  folderId: string
  parent_id: string | null
  scope: string
  scopeId: string
}
```

### `useDeleteFolder()` (`use-document-folders.ts`)

```typescript
export function useDeleteFolder(): UseMutationResult<void, Error, {
  folderId: string;
  scope: string;
  scopeId: string
}>
```

### `useReorderFolder(scope, scopeId)` (`use-document-folders.ts`)

```typescript
export function useReorderFolder(
  scope: string,
  scopeId: string
): UseMutationResult<DocumentFolder, Error, ReorderFolderParams>

interface ReorderFolderParams {
  folderId: string
  sortOrder: number
  parentId?: string | null
}
```

### `useDocuments(scope, scopeId, options?)` (`use-documents.ts`)

```typescript
export function useDocuments(
  scope: string,
  scopeId: string | null,
  options?: DocumentsQueryOptions
): UseQueryResult<DocumentListResponse, Error>

interface DocumentsQueryOptions {
  folderId?: string | null
  includeUnfiled?: boolean
}

export interface DocumentListResponse {
  items: DocumentListItem[]
  next_cursor: string | null
}
```

- Query key: `[...queryKeys.documents(scope, effectiveScopeId), folderId, includeUnfiled]`
- `select` transform: sorts items case-insensitively
- `refetchOnWindowFocus: false`
- `gcTime: 24h`

### `useDocument(id)` (`use-documents.ts`)

```typescript
export function useDocument(id: string | null): UseQueryResult<Document, Error>
```

### `useCreateDocument()` (`use-documents.ts`)

```typescript
export function useCreateDocument(): UseMutationResult<Document, Error, CreateDocumentParams>

interface CreateDocumentParams {
  title: string
  scope: string
  scope_id: string
  folder_id?: string | null
}
```

### `useRenameDocument()` (`use-documents.ts`)

```typescript
export function useRenameDocument(): UseMutationResult<Document, Error, RenameDocumentParams>

interface RenameDocumentParams {
  documentId: string
  title: string
  row_version: number
  scope: string
  scopeId: string
}
```

### `useMoveDocument()` (`use-documents.ts`)

```typescript
export function useMoveDocument(): UseMutationResult<Document, Error, MoveDocumentParams>

interface MoveDocumentParams {
  documentId: string
  folder_id: string | null
  row_version: number
  scope: string
  scopeId: string
}
```

### `useDeleteDocument()` (`use-documents.ts`)

```typescript
export function useDeleteDocument(): UseMutationResult<void, Error, {
  documentId: string;
  scope: string;
  scopeId: string
}>
```

### `useProjectsWithContent(applicationId)` (`use-documents.ts`)

```typescript
export function useProjectsWithContent(
  applicationId: string | null
): UseQueryResult<ProjectsWithContentResponse, Error>

export interface ProjectsWithContentResponse {
  project_ids: string[]
}
```

### `useApplicationsWithDocs()` (`use-documents.ts`)

```typescript
export function useApplicationsWithDocs(): UseQueryResult<ScopesSummaryResponse, Error>

export interface ScopesSummaryResponse {
  has_personal_docs: boolean
  applications: ApplicationWithDocs[]
}
```

### `useActiveLocks(scope, scopeId)` (`use-document-lock.ts`)

```typescript
export function useActiveLocks(
  scope: string,
  scopeId: string | null,
): Map<string, ActiveLockInfo>

export interface ActiveLockInfo {
  userId: string
  userName: string
}
```

- Single batch request for all locks in a scope
- Returns `Map<documentId, ActiveLockInfo>` for O(1) lookups
- `staleTime: 5 minutes`, `refetchOnMount: 'always'`, `refetchOnWindowFocus: false`
- WS subscriptions for DOCUMENT_LOCKED/UNLOCKED/FORCE_TAKEN update cache in-place

### `useDocumentLock(options)` (`use-document-lock.ts`)

```typescript
export function useDocumentLock(options: UseDocumentLockOptions): UseDocumentLockReturn

export interface UseDocumentLockOptions {
  documentId: string | null
  userId: string
  userName: string
  userRole: string | null
  lastActivityRef?: React.RefObject<number>
}

export interface UseDocumentLockReturn {
  lockHolder: LockHolder | null
  isLockedByMe: boolean
  isLockedByOther: boolean
  acquireLock: () => Promise<boolean>
  releaseLock: () => Promise<void>
  forceTakeLock: () => Promise<boolean>
  canForceTake: boolean
  isLoading: boolean
}
```

### `useEditMode(options)` (`use-edit-mode.ts`)

```typescript
export interface UseEditModeOptions {
  documentId: string | null
  userRole: string | null
}

export interface UseEditModeReturn {
  mode: 'view' | 'edit'
  saveStatus: SaveStatus
  isDirty: boolean
  isSaving: boolean
  isEntering: boolean
  isExiting: boolean
  showDiscardDialog: boolean
  showInactivityDialog: boolean
  showQuitDialog: boolean
  lockHolder: LockHolder | null
  isLockedByOther: boolean
  canForceTake: boolean
  document: Document | undefined
  isDocError: boolean
  enterEditMode: () => Promise<void>
  handleContentChange: (json: object) => void
  handleBaselineSync: (json: object) => void
  save: () => Promise<void>
  cancel: () => void
  confirmDiscard: () => void
  cancelDiscard: () => void
  inactivitySave: () => Promise<void>
  inactivityDiscard: () => void
  inactivityKeepEditing: () => void
  forceTake: () => Promise<void>
  quitSave: () => void
  quitDiscard: () => void
  quitCancel: () => void
}
```

Internally uses:
- `useDocument(documentId)` -- single source of truth for document data
- `useDocumentLock({ documentId, userId, userName, userRole, lastActivityRef })`
- `useSaveDocumentContent()` -- save mutation
- `useKnowledgeBase()` -- for `registerNavigationGuard`, `unregisterNavigationGuard`
- `registerScreenGuard` / `unregisterScreenGuard` from `@/lib/screen-navigation-guard`
- `window.electronAPI.onBeforeQuit()` -- app close guard

### `useProjects(applicationId?)` (`query-index.ts` re-exports from `use-queries.ts`)

```typescript
export function useProjects(applicationId?: string): UseQueryResult<Project[], Error>
```

Re-exported from `use-queries.ts`. Used by KnowledgeTree and ApplicationTree to get project list for project sections.

---

## 6. Component Hierarchy Summary

### Notes Page (full-page knowledge base)
```
NotesPage
  KnowledgeBaseProvider (storagePrefix='kb-')
    NotesPageContent
      SearchBar
      KnowledgeTabBar
      KnowledgeSidebar
        KnowledgeTree (applicationId=app:{id}|undefined)
          FolderTreeItem (recursive)
          FolderDocuments (per-folder lazy load)
          ProjectSection (per-project lazy load, app scope only)
          RootDropZone
          FolderContextMenu
          CreateDialog
          DeleteDialog
        TagFilterList
        CreateDialog
      EditorPanel
        DocumentActionBar
        DocumentEditor
        Discard/Inactivity/Quit Dialogs
```

### Embedded KnowledgePanel (application/project detail pages)
```
KnowledgePanel
  KnowledgeBaseProvider (storagePrefix='kb-{scope}-{scopeId}-')
    InnerPanel
      SearchBar
      [Create buttons: FilePlus, FolderPlus]
      ApplicationTree (if scope=application && showProjectFolders)
        FolderTreeItem (recursive)
        FolderDocuments (per-folder lazy load)
        ProjectSection (per-project lazy load)
        RootDropZone
        FolderContextMenu
        CreateDialog
        DeleteDialog
      OR FolderTree (if scope=project or no showProjectFolders)
        FolderTreeItem (recursive)
        FolderDocuments (per-folder lazy load)
        RootDropZone
        FolderContextMenu
        CreateDialog
        DeleteDialog
      [Resize handle]
      DocumentEditor or empty state
      Discard/Inactivity/Quit Dialogs
```

---

## 7. Key Observations for Unification

1. **KnowledgeTree already handles both personal and application scopes** -- it uses `applicationId` prop to determine whether to show project sections. It is essentially a superset of FolderTree + ApplicationTree combined.

2. **FolderTree is only used by KnowledgePanel** (line 221, when `scope !== 'application' || !showProjectFolders`). It handles personal/project scopes.

3. **ApplicationTree is only used by KnowledgePanel** (line 218, when `scope === 'application' && showProjectFolders`). It handles application scope with project sections.

4. **All three tree components read from the same context** (`useKnowledgeBase()`) and use the same hooks (`useFolderTree`, `useDocuments`, `useActiveLocks`, etc.).

5. **KnowledgeTree has the most features**: search filtering, project sections, context menu with scope awareness, DnD with scope awareness.

6. **FolderTree and ApplicationTree duplicate ~90% of KnowledgeTree's code** but with simpler scope handling.

7. **KnowledgePanel creates its own KnowledgeBaseProvider** with scoped `storagePrefix`, which isolates localStorage state from the Notes page provider.

8. **NotesPage has WS subscriptions for room management and document updates** that KnowledgePanel does not have (since it relies on app-level WS cache invalidation).

9. **The editor panel logic (EditorPanel / InnerPanel) is duplicated** between NotesPage and KnowledgePanel with nearly identical code for useEditMode, DocumentActionBar, DocumentEditor, and all three dialogs.

10. **All three trees use identical shared sub-components**: FolderTreeItem, FolderDocuments, TreeSkeleton, RootDropZone, FolderContextMenu, CreateDialog, DeleteDialog.

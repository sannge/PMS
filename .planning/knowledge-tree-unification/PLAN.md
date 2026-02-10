# Knowledge Tree Unification - Implementation Plan

## Goal

Eliminate three near-duplicate tree components (`KnowledgeTree`, `ApplicationTree`, `FolderTree`) and the duplicated editor panel, consolidating into a single `KnowledgeTree` component and a shared `EditorPanel` component.

**Files to delete by end of plan:**
- `application-tree.tsx` (~1263 lines)
- `folder-tree.tsx` (~807 lines)

**Estimated net line reduction:** ~1800 lines deleted, ~100 lines added for porting features = ~1700 net reduction.

---

## Pre-Implementation: Features to Port

These are features unique to `ApplicationTree` that must be merged into `KnowledgeTree` before `ApplicationTree` can be deleted. All line references are from the current source files.

### Feature P1: Background Refresh Indicator
- **Source:** `application-tree.tsx` line 17 (`Loader2` import), lines 364-367 (`isFoldersFetching` destructuring), lines 1154-1158 (JSX rendering)
- **What:** When `useFolderTree` is refetching in the background (not initial load), show a small `<Loader2>` spinner at the top of the tree
- **Port to KT:** Add `isFetching: isFoldersFetching` destructuring to KT's `useFolderTree` call (line 331). Add `Loader2` to icon imports (line 17). Add the spinner JSX before the `SortableContext` in the render output (after line 959).

### Feature P2: `hideIfEmpty` on ProjectSection
- **Source:** `application-tree.tsx` lines 111 (`hideIfEmpty?: boolean` prop), 134 (default `false`), 168-172 (`isEmpty` useMemo), 302 (conditional return)
- **What:** When a project section is expanded, loaded, and empty, optionally hide it entirely
- **Port to KT:** Add `hideIfEmpty?: boolean` to KT's `ProjectSectionProps` (line 101). Add the `isEmpty` useMemo and conditional `return null` to KT's `ProjectSection` component. Update the return type from `JSX.Element` to `JSX.Element | null` (line 137).

### Feature P3: `isProjectsContentLoading` in Loading Check
- **Source:** `application-tree.tsx` line 380 (`isProjectsContentLoading` destructured from `useProjectsWithContent`), line 467 (included in `isLoading` condition)
- **What:** The loading skeleton should also wait for `useProjectsWithContent` to finish in application scope
- **Port to KT:** Destructure `isLoading: isProjectsContentLoading` from `useProjectsWithContent` (line 339). Include it in `isInitialLoad` when `isApplicationScope` is true (line 409).

### Feature P4: Scoped `findDocInCache` (AT's Two-Tier Search)
- **Source:** `application-tree.tsx` lines 395-411 (scoped `findDocInCache`)
- **What:** AT searches a specific scope first, then falls back to application scope. KT does a broad unscoped search.
- **Decision: KEEP KT's approach.** KT's broad `['documents']` search is functionally correct and simpler. AT's two-tier approach was an optimization but the broad search has negligible performance impact (it iterates a few cached arrays). No porting needed.

### Feature P5: AT's More Thorough `isRootDocument`
- **Source:** `application-tree.tsx` lines 643-655 (searches all `['documents']` caches)
- **What:** AT searches all document list caches to determine if a document is at root level, while KT uses `findDocInCache` which also searches broadly.
- **Decision: KEEP KT's approach.** KT's `isRootDocument` (lines 564-568) calls `findDocInCache` which already does a broad search and checks `!doc.folder_id`. Functionally equivalent.

### Feature P6: AT's Conditional Fragment Wrappers
- **Source:** `application-tree.tsx` lines 1162-1173 (wraps folder/doc rendering in `{filteredFolders.length > 0 && <> ... </>}`)
- **Decision: NOT PORTED.** KT renders directly without conditionals. Both approaches are functionally identical -- React handles empty `.map()` arrays gracefully. KT's approach is cleaner.

---

## Types to Verify

TypeScript interfaces that will change and consumers that need updating.

### Phase 1 Changes

| Interface | File | Change | Consumers to Update |
|-----------|------|--------|-------------------|
| `KnowledgeTreeProps` | `knowledge-tree.tsx` | No change | None |
| `ProjectSectionProps` | `knowledge-tree.tsx` | Add `hideIfEmpty?: boolean` | Internal only |
| `ProjectSection` return type | `knowledge-tree.tsx` | `JSX.Element` -> `JSX.Element \| null` | Internal only |
| `ApplicationTreeProps` | **DELETED** | N/A | `knowledge-panel.tsx` |

**Consumer updates for Phase 1:**
- `knowledge-panel.tsx` lines 38, 217-218: Replace `<ApplicationTree applicationId={scopeId} />` with `<KnowledgeTree applicationId={scopeId} />`

### Phase 2 Changes

| Interface | File | Change | Consumers to Update |
|-----------|------|--------|-------------------|
| `FolderTree` component | **DELETED** | N/A | `knowledge-panel.tsx` |
| (none added) | | | |

**Consumer updates for Phase 2:**
- `knowledge-panel.tsx` lines 37, 220: Replace `<FolderTree />` with `<KnowledgeTree />`
- Then simplify the conditional: the tree selection logic `scope === 'application' && showProjectFolders ? ... : ...` becomes just `<KnowledgeTree applicationId={scope === 'application' && showProjectFolders ? scopeId : undefined} />`

### Phase 3 Changes

| Interface | File | Change | Consumers to Update |
|-----------|------|--------|-------------------|
| `EditorPanel` (new) | `editor-panel.tsx` | New shared component | `knowledge-panel.tsx`, `pages/notes/index.tsx` |
| `EditorPanelProps` | `editor-panel.tsx` | `{ keyByDocumentId?: boolean; className?: string }` | Same |

---

## Phase 1: Eliminate ApplicationTree (Merge into KnowledgeTree)

### Step 1.1: Add `Loader2` Import to KnowledgeTree

**What:** Import the `Loader2` icon needed for the background refresh indicator.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
- Line 17: Change `import { FilePlus, Folder, FileText, FolderKanban, ChevronRight } from 'lucide-react'` to include `Loader2`:
  ```ts
  import { FilePlus, Folder, FileText, FolderKanban, ChevronRight, Loader2 } from 'lucide-react'
  ```

**Order:** Independent, no dependencies.

**Verification:** TypeScript compiles without error. `Loader2` is available in scope.

**Risk:** None -- additive import only.

### Step 1.2: Add `hideIfEmpty` to KnowledgeTree's ProjectSection

**What:** Port the `hideIfEmpty` feature from AT's ProjectSection into KT's ProjectSection.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
1. Add `hideIfEmpty?: boolean` to `ProjectSectionProps` (after line 109):
   ```ts
   /** Hide this project section if it has no documents after loading */
   hideIfEmpty?: boolean
   ```

2. Add `hideIfEmpty = false` to the destructured props (line 137):
   ```ts
   function ProjectSection({
     project,
     expandedFolderIds,
     selectedDocumentId,
     renamingItemId,
     activeItem,
     dropTargetFolderId,
     contextMenuFolderId,
     hideIfEmpty = false,
     onToggleFolder,
     ...
   ```

3. Change return type to `JSX.Element | null` (line 137)

4. Add `isEmpty` useMemo after the `isLoading` calculation (after line 159):
   ```ts
   const isEmpty = useMemo(() => {
     if (!isExpanded || isLoading) return false
     return folders.length === 0 && unfiledDocs.length === 0
   }, [isExpanded, isLoading, folders.length, unfiledDocs.length])
   ```

5. Add conditional return AFTER all hooks but BEFORE the JSX return (before line 263):
   ```ts
   if (hideIfEmpty && isExpanded && isEmpty && !isLoading) {
     return null
   }
   ```

**Order:** Independent, no dependencies.

**Verification:** KnowledgeTree still renders project sections normally when `hideIfEmpty` is not passed (default `false`). Pass `hideIfEmpty={true}` to verify empty projects are hidden.

**Risk:** Low. Must place the conditional return after ALL hooks to avoid React "fewer hooks" error. The code is placed between the last `useCallback` (renderDocumentItem, ending ~line 261) and the `return` JSX (line 263).

### Step 1.3: Add Background Refresh Indicator to KnowledgeTree

**What:** Destructure `isFetching` from `useFolderTree` and render a spinner when refetching in background.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
1. Line 331: Destructure `isFetching` alongside `isLoading`:
   ```ts
   const { data: folderTree, isLoading: isFoldersLoading, isFetching: isFoldersFetching } = useFolderTree(scope, effectiveScopeId)
   ```

2. After line 959 (`<div className="py-1" role="tree">`), add the spinner:
   ```tsx
   {/* Subtle background refresh indicator */}
   {isFoldersFetching && !isFoldersLoading && (
     <div className="flex items-center justify-end px-2 pb-0.5">
       <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
     </div>
   )}
   ```

**Order:** Depends on Step 1.1 (`Loader2` import).

**Verification:** Trigger a background refetch (e.g., window focus with `refetchOnWindowFocus: true` or manual invalidation). Verify the spinner appears briefly. Verify it does NOT appear during initial load.

**Risk:** Low. The spinner only shows during `isFetching && !isLoading`, which is the correct background-refetch window.

### Step 1.4: Include `isProjectsContentLoading` in KnowledgeTree Loading Check

**What:** When in application scope, include `isProjectsContentLoading` in the initial load condition so the skeleton waits for project data.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
1. Line 339: Destructure `isLoading` from `useProjectsWithContent`:
   ```ts
   const { data: projectsWithContent, isLoading: isProjectsContentLoading } = useProjectsWithContent(isApplicationScope ? applicationId! : null)
   ```

2. Line 409: Update `isInitialLoad` to include `isProjectsContentLoading` when in application scope:
   ```ts
   const isInitialLoad = (isFoldersLoading || isUnfiledLoading || (isApplicationScope && isProjectsContentLoading)) && !hasAnyData
   ```

**Order:** Independent, no dependencies.

**Verification:** In application scope, the skeleton should remain visible until project content data loads. In personal scope, `isProjectsContentLoading` is irrelevant (`useProjectsWithContent` returns null/disabled).

**Risk:** Low. When `isApplicationScope` is false, the `&&` short-circuits, so personal scope is unaffected.

### Step 1.5: Update KnowledgePanel to Use KnowledgeTree Instead of ApplicationTree

**What:** Replace the `ApplicationTree` import and usage in `KnowledgePanel` with `KnowledgeTree`.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
1. Line 38: Remove the ApplicationTree import:
   ```ts
   // DELETE: import { ApplicationTree } from './application-tree'
   ```

2. Line 38 (replacement): Add KnowledgeTree import:
   ```ts
   import { KnowledgeTree } from './knowledge-tree'
   ```

3. Lines 217-221: Replace the tree selection:
   ```tsx
   // BEFORE:
   {scope === 'application' && showProjectFolders ? (
     <ApplicationTree applicationId={scopeId} />
   ) : (
     <FolderTree />
   )}

   // AFTER:
   {scope === 'application' && showProjectFolders ? (
     <KnowledgeTree applicationId={scopeId} />
   ) : (
     <FolderTree />
   )}
   ```

**Order:** Depends on Steps 1.1-1.4 (all features ported first).

**Verification:**
1. Open an Application detail page -> Knowledge tab. The tree should render identically to before (folders, docs, project sections).
2. Context menu operations (create, rename, delete) should work in both app-level and project scopes.
3. Drag-and-drop should work within scopes and be blocked across scopes.
4. Background refresh spinner should appear during refetches.
5. Empty state "Create your first document" button should work.

**Risk:** Medium. This is the critical swap. If any AT-specific behavior was missed in porting, it will surface here. The research documents confirm that KT already handles application scope via `applicationId` prop, so the main risk is subtle differences in cache lookup strategies (which we decided to keep KT's approach for).

### Step 1.6: Delete ApplicationTree

**What:** Delete the `application-tree.tsx` file entirely.

**File:** `electron-app/src/renderer/components/knowledge/application-tree.tsx` -- **DELETE**

**Details:**
- Delete the file.
- Verify no other imports reference it.

**Order:** Depends on Step 1.5 (all consumers updated).

**Verification:**
1. `grep -r "application-tree" electron-app/src/` returns no results (except possibly this plan file).
2. `grep -r "ApplicationTree" electron-app/src/` returns no results.
3. TypeScript compiles cleanly: `npm run typecheck`
4. Full application functions correctly in all three surfaces: Notes page (personal tab), Notes page (application tab), Application detail page Knowledge tab.

**Risk:** Low at this point -- all consumers already updated. If a stale import is found, it will be a compile error.

---

## Phase 2: Eliminate FolderTree (KnowledgeTree Handles All Scopes)

### Step 2.1: Update KnowledgePanel to Use KnowledgeTree Instead of FolderTree

**What:** Replace the remaining `FolderTree` usage in KnowledgePanel with `KnowledgeTree`.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
1. Remove the FolderTree import (line 37):
   ```ts
   // DELETE: import { FolderTree } from './folder-tree'
   ```

2. Simplify the tree selection logic. Replace the conditional (currently after Step 1.5):
   ```tsx
   // BEFORE:
   {scope === 'application' && showProjectFolders ? (
     <KnowledgeTree applicationId={scopeId} />
   ) : (
     <FolderTree />
   )}

   // AFTER:
   <KnowledgeTree
     applicationId={scope === 'application' && showProjectFolders ? scopeId : undefined}
   />
   ```

**Why this works:** When `applicationId` is `undefined`, KnowledgeTree reads `scope` and `scopeId` from the `KnowledgeBaseProvider` context. KnowledgePanel sets up the provider with `initialScope={scope}` and `initialScopeId={scopeId}`, so KT receives the correct scope (project, personal, or application without project folders).

**Order:** Depends on Phase 1 completion.

**Verification:**
1. Open a Project detail page -> Knowledge tab. The tree should show project-scoped folders and documents (no project sub-sections, since `applicationId` is `undefined`).
2. Context menu operations work.
3. Drag-and-drop works within the single scope.
4. Open Application detail page -> Knowledge tab with `showProjectFolders={true}`. Should still show project sections.
5. If there were an application detail page without `showProjectFolders`, it should show a flat application-scope tree.

**Risk:** Medium. The key behavioral difference between FolderTree and KnowledgeTree (no `applicationId`):
- FT uses `scope`/`scopeId` directly from context, while KT uses `contextScope`/`contextScopeId` (same values).
- FT has no `scope` field in `ActiveDragItem`. KT always includes `scope: parsed.prefix`. This is harmless -- the extra field is unused in single-scope mode.
- FT has a simpler 4-param `handleContextMenu`. KT has a 6-param version with default params. When called with 4 args, the defaults fill in from context. This is functionally equivalent.
- FT's `SortableContext` wraps `div[role=tree]` (line 736-751 of folder-tree.tsx). KT nests `SortableContext` inside `div[role=tree]` (lines 959-964 of knowledge-tree.tsx). **This is a DOM nesting difference but has no functional impact** -- `SortableContext` doesn't render a DOM element.

### Step 2.2: Delete FolderTree

**What:** Delete the `folder-tree.tsx` file entirely.

**File:** `electron-app/src/renderer/components/knowledge/folder-tree.tsx` -- **DELETE**

**Order:** Depends on Step 2.1 (all consumers updated).

**Verification:**
1. `grep -r "folder-tree" electron-app/src/` returns only `folder-tree-item` references (different component).
2. `grep -r "FolderTree" electron-app/src/` returns no import/usage results (only potentially the type `FolderTreeNode` which is from `use-document-folders.ts`, a different export).
3. TypeScript compiles cleanly: `npm run typecheck`
4. All three surfaces work: Notes page personal, Notes page application, Application detail Knowledge tab, Project detail Knowledge tab.

**Risk:** Low -- all consumers already updated.

### Step 2.3: Extract `useTreeDnd` Hook from KnowledgeTree

**What:** Extract DnD state and handlers into a custom hook to reduce KnowledgeTree's size.

**File (new):** `electron-app/src/renderer/hooks/use-tree-dnd.ts`
**File (modify):** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**

Extract the following from KnowledgeTree into `useTreeDnd`:

**State:**
- `activeItem` / `setActiveItem`
- `dropTargetFolderId` / `setDropTargetFolderId`

**Functions:**
- `findDocInCache`
- `getDocRowVersion`
- `getScopeFromPrefix`
- `getFolderTree`
- `isRootFolder`
- `isRootDocument`
- `moveItemToRoot`
- `handleDragStart`
- `handleDragOver`
- `handleDragEnd`

**Hook interface:**
```ts
interface UseTreeDndOptions {
  scope: string
  effectiveScopeId: string | null
  isApplicationScope: boolean
  folders: FolderTreeNode[]
  filteredFolders: FolderTreeNode[]
  filteredDocs: DocumentListItem[]
  unfiledDocs: DocumentListItem[]
  expandFolder: (folderId: string) => void
}

interface UseTreeDndReturn {
  sensors: ReturnType<typeof useSensors>
  activeItem: ActiveDragItem | null
  dropTargetFolderId: string | null
  findDocInCache: (documentId: string) => DocumentListItem | null
  getDocRowVersion: (documentId: string) => number | null
  getScopeFromPrefix: (prefix: string) => ScopeInfo
  handleDragStart: (event: DragStartEvent) => void
  handleDragOver: (event: DragOverEvent) => void
  handleDragEnd: (event: DragEndEvent) => Promise<void>
  sortableItems: string[]
  noReorderStrategy: () => null
  dndPrefix: string
  isRootFolder: (folderId: string) => boolean
  isRootDocument: (documentId: string) => boolean
}
```

**In KnowledgeTree**, replace ~150 lines of DnD logic with:
```ts
const dnd = useTreeDnd({
  scope, effectiveScopeId, isApplicationScope,
  folders, filteredFolders, filteredDocs, unfiledDocs,
  expandFolder,
})
```

Then reference `dnd.activeItem`, `dnd.handleDragStart`, etc. throughout.

**Order:** Depends on Phase 2 completion (Steps 2.1-2.2). Do this after deleting FolderTree so we only maintain one copy.

**Verification:**
1. All DnD operations still work: drag folder to folder, drag doc to folder, drag to root, cross-scope prevention.
2. Drop target highlighting works.
3. Drag overlay shows correct item name and icon.
4. TypeScript compiles cleanly.

**Risk:** Medium. Extracting hooks is refactoring -- the logic is moved, not changed. The main risk is missing a dependency or breaking a callback closure. Careful testing of all DnD scenarios is needed.

### Step 2.4: Extract `useTreeCrud` Hook from KnowledgeTree

**What:** Extract CRUD state and handlers into a custom hook.

**File (new):** `electron-app/src/renderer/hooks/use-tree-crud.ts`
**File (modify):** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**

Extract the following from KnowledgeTree:

**State:**
- `renamingItemId`, `renamingItemType`, `renamingItemScope`, `renamingItemScopeId`
- `contextMenuTarget`
- `createDialogOpen`, `createType`, `createParentId`, `createScope`, `createScopeId`
- `deleteDialogOpen`, `deleteTarget`

**Functions:**
- `handleContextMenu`
- `handleCloseContextMenu`
- `handleNewFolder`
- `handleNewDocument`
- `handleCreateSubmit`
- `handleRename`
- `handleRenameSubmit`
- `handleRenameCancel`
- `handleDelete`
- `handleDeleteConfirm`
- `handleSelectDocument`
- `handleCreateFirstDocument`

**Hook interface:**
```ts
interface UseTreeCrudOptions {
  scope: string
  effectiveScopeId: string | null
  isApplicationScope: boolean
  folders: FolderTreeNode[]
  unfiledDocs: DocumentListItem[]
  selectedDocumentId: string | null
  selectDocument: (id: string | null) => void
  expandFolder: (folderId: string) => void
  findDocInCache: (documentId: string) => DocumentListItem | null
  getDocRowVersion: (documentId: string) => number | null
}

interface UseTreeCrudReturn {
  renamingItemId: string | null
  contextMenuTarget: ContextMenuTarget | null
  contextMenuFolderId: string | null
  createDialogOpen: boolean
  createType: 'document' | 'folder'
  deleteDialogOpen: boolean
  deleteTarget: DeleteTarget | null
  handleContextMenu: (...) => void
  handleCloseContextMenu: () => void
  handleNewFolder: (parentId: string) => void
  handleNewDocument: (folderId: string) => void
  handleCreateSubmit: (name: string) => Promise<void>
  handleRename: (id: string, type: 'folder' | 'document') => void
  handleRenameSubmit: (newName: string) => Promise<void>
  handleRenameCancel: () => void
  handleDelete: (id: string, type: 'folder' | 'document') => void
  handleDeleteConfirm: () => Promise<void>
  handleSelectDocument: (documentId: string) => void
  handleCreateFirstDocument: () => void
  setCreateDialogOpen: (open: boolean) => void
  setDeleteDialogOpen: (open: boolean) => void
}
```

**In KnowledgeTree**, replace ~180 lines of CRUD logic with:
```ts
const crud = useTreeCrud({
  scope, effectiveScopeId, isApplicationScope,
  folders, unfiledDocs, selectedDocumentId,
  selectDocument, expandFolder,
  findDocInCache: dnd.findDocInCache,
  getDocRowVersion: dnd.getDocRowVersion,
})
```

**Order:** Depends on Step 2.3 (DnD hook extracted first, since CRUD uses `findDocInCache`/`getDocRowVersion` from DnD).

**Verification:**
1. Context menu appears on right-click with correct options.
2. Create dialog opens and creates folder/document in correct scope.
3. Rename inline editing works and persists.
4. Delete dialog confirms and removes items.
5. TypeScript compiles cleanly.

**Risk:** Medium. Same refactoring risk as Step 2.3. The functions depend on `findDocInCache` and `getDocRowVersion` which are now in the DnD hook -- these must be passed as dependencies.

### Step 2.5: Update dnd-utils.ts Documentation

**What:** Update the file header comment in `dnd-utils.ts` to reflect that it's now used by a single `KnowledgeTree` component.

**File:** `electron-app/src/renderer/components/knowledge/dnd-utils.ts`

**Details:**
- Line 4: Change `Used by KnowledgeTree, ApplicationTree, and FolderTree` to `Used by KnowledgeTree`.

**Order:** After Steps 2.1-2.2.

**Verification:** N/A -- documentation only.

**Risk:** None.

---

## Phase 3: Unify KnowledgePanel Editor with Notes Page EditorPanel

### Step 3.1: Extract Shared `EditorPanel` Component

**What:** Create a new `EditorPanel` component that encapsulates the entire right panel: `useEditMode`, `DocumentActionBar`, `DocumentEditor`, and all three dialogs.

**File (new):** `electron-app/src/renderer/components/knowledge/editor-panel.tsx`
**File (modify):** `electron-app/src/renderer/pages/notes/index.tsx`
**File (modify):** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**

Create `editor-panel.tsx` based on the Notes page `EditorPanel` (lines 47-194 of `pages/notes/index.tsx`), which uses the cleaner early-return pattern:

```tsx
/**
 * EditorPanel
 *
 * Shared document editor panel used by both the Notes page and KnowledgePanel.
 * Owns the useEditMode state machine, DocumentActionBar, DocumentEditor,
 * and all confirmation dialogs (discard, inactivity, quit).
 *
 * Must be rendered inside a KnowledgeBaseProvider.
 */

import { useMemo } from 'react'
import { FileText, Save, Trash2, AlertTriangle } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useEditMode } from '@/hooks/use-edit-mode'
import { DocumentEditor } from './document-editor'
import { DocumentActionBar } from './document-action-bar'
import { ensureContentHeading } from './content-utils'

export interface EditorPanelProps {
  /** Force remount of DocumentEditor on document switch (Notes page needs this) */
  keyByDocumentId?: boolean
  className?: string
}

export function EditorSkeleton(): JSX.Element {
  return (
    <div className="flex-1 p-6 space-y-4">
      <div className="h-8 w-48 rounded bg-muted animate-pulse" />
      <div className="space-y-2.5">
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '90%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '75%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '85%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '60%' }} />
      </div>
      <div className="space-y-2.5 pt-2">
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '80%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '70%' }} />
      </div>
    </div>
  )
}

export function EditorPanel({ keyByDocumentId, className }: EditorPanelProps): JSX.Element {
  const { selectedDocumentId } = useKnowledgeBase()

  const editMode = useEditMode({
    documentId: selectedDocumentId,
    userRole: null,
  })

  const currentDoc = editMode.document
  const isDocError = editMode.isDocError

  const parsedContent = useMemo(
    () => currentDoc
      ? ensureContentHeading(currentDoc.content_json, currentDoc.title)
      : undefined,
    [currentDoc?.content_json, currentDoc?.title]
  )

  // No document selected
  if (!selectedDocumentId) {
    return (
      <div className={cn("flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3", className)}>
        <FileText className="h-12 w-12 text-muted-foreground/30" />
        <p className="text-sm">Select a document to start editing</p>
      </div>
    )
  }

  // Document not found
  if (!currentDoc && isDocError) {
    return (
      <div className={cn("flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3", className)}>
        <FileText className="h-12 w-12 text-muted-foreground/30" />
        <p className="text-sm">Document not found</p>
      </div>
    )
  }

  // Loading
  if (!currentDoc) {
    return <EditorSkeleton />
  }

  return (
    <div className={cn("flex-1 flex flex-col min-w-0 min-h-0", className)}>
      <DocumentActionBar
        mode={editMode.mode}
        lockHolder={editMode.lockHolder}
        isLockedByOther={editMode.isLockedByOther}
        canForceTake={editMode.canForceTake}
        isDirty={editMode.isDirty}
        isSaving={editMode.isSaving}
        isEntering={editMode.isEntering}
        isExiting={editMode.isExiting}
        onEdit={() => void editMode.enterEditMode()}
        onSave={() => void editMode.save()}
        onCancel={editMode.cancel}
        onForceTake={() => void editMode.forceTake()}
      />

      <DocumentEditor
        key={keyByDocumentId ? selectedDocumentId : undefined}
        content={parsedContent}
        onChange={editMode.handleContentChange}
        onBaselineSync={editMode.handleBaselineSync}
        editable={editMode.mode === 'edit'}
        placeholder="Start writing..."
        className="flex-1"
        updatedAt={currentDoc.updated_at}
      />

      {/* Discard changes dialog */}
      <Dialog open={editMode.showDiscardDialog} onOpenChange={(open) => { if (!open) editMode.cancelDiscard() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Discard changes?</DialogTitle>
            <DialogDescription>
              You have unsaved changes. Are you sure you want to discard them?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={editMode.cancelDiscard}>
              Keep editing
            </Button>
            <Button variant="destructive" onClick={editMode.confirmDiscard}>
              Discard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Inactivity dialog */}
      <Dialog open={editMode.showInactivityDialog} onOpenChange={(open) => { if (!open) editMode.inactivityKeepEditing() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Are you still editing?</DialogTitle>
            <DialogDescription>
              Your changes will be auto-saved in 60 seconds.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="destructive" onClick={editMode.inactivityDiscard}>
              Discard
            </Button>
            <Button variant="outline" onClick={() => void editMode.inactivitySave()}>
              Save
            </Button>
            <Button onClick={editMode.inactivityKeepEditing}>
              Keep Editing
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Quit confirmation dialog */}
      <Dialog open={editMode.showQuitDialog} onOpenChange={(open) => { if (!open) editMode.quitCancel() }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10">
              <AlertTriangle className="h-6 w-6 text-amber-500" />
            </div>
            <DialogTitle className="text-center">Unsaved changes</DialogTitle>
            <DialogDescription className="text-center">
              You have unsaved changes in your document. What would you like to do before closing?
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 pt-2">
            <Button onClick={editMode.quitSave} className="w-full gap-2">
              <Save className="h-4 w-4" />
              Save and close
            </Button>
            <Button variant="destructive" onClick={editMode.quitDiscard} className="w-full gap-2">
              <Trash2 className="h-4 w-4" />
              Discard and close
            </Button>
            <Button variant="outline" onClick={editMode.quitCancel} className="w-full">
              Keep editing
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

Note: The component needs a `cn` import from `@/lib/utils`.

**Order:** Independent -- can be done in parallel with Phase 2.

**Verification:** File compiles. Not yet integrated.

**Risk:** Low -- new file, no consumers yet.

### Step 3.2: Update Notes Page to Use Shared EditorPanel

**What:** Replace the inline `EditorPanel` in `pages/notes/index.tsx` with the shared component.

**File:** `electron-app/src/renderer/pages/notes/index.tsx`

**Details:**
1. Remove the inline `EditorPanel` function (lines 47-194).

2. Remove the `EditorSkeleton` import from `knowledge-panel`:
   ```ts
   // DELETE: import { EditorSkeleton } from '@/components/knowledge/knowledge-panel'
   ```

3. Add the new import:
   ```ts
   import { EditorPanel } from '@/components/knowledge/editor-panel'
   ```

4. Remove these imports that are no longer needed (they were only used by the inline EditorPanel):
   - `useMemo` from react (unless used elsewhere -- check: it's NOT used in `NotesPageContent`)
   - `FileText, Save, Trash2, AlertTriangle` from lucide-react
   - `useEditMode` from `@/hooks/use-edit-mode`
   - `DocumentEditor` from knowledge components
   - `DocumentActionBar` from knowledge components
   - `ensureContentHeading` from content-utils
   - `Dialog`, `DialogContent`, etc. from `@/components/ui/dialog`
   - `Button` from `@/components/ui/button`

5. Update the JSX in `NotesPageContent` (line 290):
   ```tsx
   // BEFORE:
   <main className="flex-1 flex flex-col min-h-0">
     <EditorPanel />
   </main>

   // AFTER:
   <main className="flex-1 flex flex-col min-h-0">
     <EditorPanel keyByDocumentId />
   </main>
   ```

**Order:** Depends on Step 3.1.

**Verification:**
1. Open Notes page. Select a document. Editor renders with action bar.
2. Enter edit mode, make changes, save -- all works.
3. Switch documents -- editor fully remounts (key prop).
4. Discard dialog appears when cancelling dirty editor.
5. Inactivity dialog appears after timeout.
6. Quit dialog appears when closing app with unsaved changes.

**Risk:** Medium. The Notes page `EditorPanel` used `key={selectedDocumentId}` on `DocumentEditor`. This is now controlled by `keyByDocumentId` prop. Must verify the key behavior is preserved.

### Step 3.3: Update KnowledgePanel to Use Shared EditorPanel

**What:** Replace the inline editor/dialogs in `KnowledgePanel`'s `InnerPanel` with the shared `EditorPanel`.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
1. Remove these imports that are no longer needed:
   - `useRef, useEffect, useMemo` from react (keep `useCallback, useState`)
   - `FileText, Save, Trash2, AlertTriangle` from lucide-react (keep `FilePlus, FolderPlus`)
   - `Dialog`, `DialogContent`, etc. from `@/components/ui/dialog`
   - `Button` from `@/components/ui/button`
   - `useEditMode` from `@/hooks/use-edit-mode`
   - `DocumentEditor` from `./document-editor`
   - `DocumentActionBar` from `./document-action-bar`
   - `ensureContentHeading` from `./content-utils`

2. Remove the `EditorSkeleton` export (it moves to `editor-panel.tsx`):
   ```ts
   // DELETE: export function EditorSkeleton(): JSX.Element { ... }
   ```
   If other files import `EditorSkeleton` from `knowledge-panel`, update them to import from `editor-panel` instead.

3. Add import:
   ```ts
   import { EditorPanel } from './editor-panel'
   ```

4. In `InnerPanel`, remove:
   - `useEditMode` call (lines 102-105)
   - `currentDoc` / `isDocError` variables (lines 107-108)
   - `parsedContent` useMemo (lines 111-116)
   - The entire right panel JSX (lines 232-348) -- replace with:
     ```tsx
     <EditorPanel />
     ```
   Note: KnowledgePanel does NOT pass `keyByDocumentId` (intentional -- it relies on content prop changes, not full remount).

5. Remove `selectedDocumentId` from `useKnowledgeBase()` destructuring (line 94) since it's only needed if we use it in the JSX ternary. **Wait** -- check if `selectDocument` is still used. Yes, it's used in `handleCreateDoc` onSuccess. Keep `selectDocument`, remove `selectedDocumentId` from destructuring.

**Order:** Depends on Step 3.1.

**Verification:**
1. Open Application detail -> Knowledge tab. Select a document. Editor renders.
2. Enter edit mode, make changes, save.
3. All three dialogs work (discard, inactivity, quit).
4. Empty state shows "Select a document" message.
5. Document error state shows "Document not found".

**Risk:** Medium. The main behavioral difference: KnowledgePanel previously did NOT use `key={selectedDocumentId}` on the editor. The shared EditorPanel defaults `keyByDocumentId` to `undefined`/falsy, so `key={undefined}` is passed, which means NO key -- matching the original behavior. This is correct.

### Step 3.4: Update EditorSkeleton Imports

**What:** Find all files that import `EditorSkeleton` from `knowledge-panel.tsx` and update them to import from `editor-panel.tsx`.

**Files to check:**
- `pages/notes/index.tsx` (already updated in Step 3.2)
- Any other importers (search with grep)

**Details:**
Run: `grep -r "EditorSkeleton" electron-app/src/`

Update any remaining imports:
```ts
// BEFORE:
import { EditorSkeleton } from '@/components/knowledge/knowledge-panel'
// AFTER:
import { EditorSkeleton } from '@/components/knowledge/editor-panel'
```

**Order:** After Steps 3.2 and 3.3.

**Verification:** TypeScript compiles cleanly. No broken imports.

**Risk:** Low.

### Step 3.5: Clean Up KnowledgePanel InnerPanel

**What:** After extracting EditorPanel, simplify InnerPanel by removing the resize logic if desired, or keeping it for the tree panel width control.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
The resize logic stays -- it controls the tree panel width, not the editor. After Step 3.3, InnerPanel should be significantly smaller:
- Tree panel (left side) with search, create buttons, KnowledgeTree
- Resize handle
- `<EditorPanel />` (right side)

Remove any now-unused imports. Expected final `InnerPanel` size: ~80 lines (down from ~260).

**Order:** After Step 3.3.

**Verification:** TypeScript compiles. KnowledgePanel still renders correctly.

**Risk:** None.

---

## Verification Checklist (Post-All-Phases)

Run these after all three phases are complete:

### TypeScript
- [ ] `npm run typecheck` passes with zero errors

### Lint
- [ ] `npm run lint` passes with zero warnings

### Functional Tests (Manual)

**Notes Page - Personal Tab:**
- [ ] Tree shows personal folders and documents
- [ ] Context menu works (create, rename, delete)
- [ ] Drag-and-drop works (folder nesting, doc to folder, move to root)
- [ ] Search filtering works
- [ ] Auto-expand on search works
- [ ] Document editor opens on click
- [ ] Edit/Save/Cancel flow works
- [ ] Discard dialog works
- [ ] Empty state shows "Create your first document"

**Notes Page - Application Tab:**
- [ ] Tree shows application folders, documents, AND project sections
- [ ] Project sections expand and lazy-load
- [ ] Background refresh spinner appears during refetch
- [ ] Cross-scope drag is prevented
- [ ] All CRUD operations work in both app and project scopes

**Application Detail Page - Knowledge Tab:**
- [ ] KnowledgePanel renders with KnowledgeTree (applicationId passed)
- [ ] Project sections visible with `showProjectFolders`
- [ ] Editor panel works (view, edit, save, cancel)
- [ ] All three dialogs (discard, inactivity, quit) work

**Project Detail Page - Knowledge Tab:**
- [ ] KnowledgePanel renders with KnowledgeTree (no applicationId)
- [ ] Only project-scope folders and documents shown
- [ ] No project sections (since not in application scope)
- [ ] Editor panel works

### Deleted Files
- [ ] `application-tree.tsx` is deleted
- [ ] `folder-tree.tsx` is deleted
- [ ] No imports reference these files

### New Files
- [ ] `hooks/use-tree-dnd.ts` exists and exports `useTreeDnd`
- [ ] `hooks/use-tree-crud.ts` exists and exports `useTreeCrud`
- [ ] `components/knowledge/editor-panel.tsx` exists and exports `EditorPanel` + `EditorSkeleton`

---

## Risk Summary

| Step | Risk | Mitigation |
|------|------|-----------|
| 1.5 (Swap AT -> KT) | Medium - behavioral diff in cache lookups | KT's broad search is functionally equivalent; test all CRUD ops in app scope |
| 2.1 (Swap FT -> KT) | Medium - SortableContext nesting differs | No functional impact; `SortableContext` renders no DOM |
| 2.3-2.4 (Hook extraction) | Medium - refactoring risk | No logic changes, only code movement. Test all interactions. |
| 3.2-3.3 (EditorPanel swap) | Medium - dialog/key behavior | `keyByDocumentId` prop preserves existing per-consumer behavior |

## Estimated Scope

| Phase | Steps | Files Changed | Files Created | Files Deleted | Net Lines |
|-------|-------|---------------|---------------|---------------|-----------|
| 1 | 6 | 2 | 0 | 1 | -1200 |
| 2 | 5 | 2 | 2 | 1 | -500 (moved to hooks) |
| 3 | 5 | 2 | 1 | 0 | -130 |
| **Total** | **16** | **6** | **3** | **2** | **~-1830** |

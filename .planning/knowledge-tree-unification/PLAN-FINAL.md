# Knowledge Tree Unification - Final Implementation Plan

## Questions for User

Before implementation, these decisions should be confirmed:

1. **Hook extraction scope:** Steps 2.3-2.4 extract `useTreeDnd` and `useTreeCrud` hooks from KnowledgeTree. This is pure refactoring (not deduplication) and adds risk. Recommend deferring to a follow-up PR. If the user wants them in this PR, they are included below as optional steps.

2. **Application scope without `showProjectFolders`:** Currently no consumer uses `scope='application'` without `showProjectFolders`. The unified component will handle this (flat tree, no project sections). Confirm this is acceptable.

---

## Goal

Eliminate three near-duplicate tree components (`KnowledgeTree`, `ApplicationTree`, `FolderTree`) and the duplicated editor panel, consolidating into a single `KnowledgeTree` component and a shared `EditorPanel` component.

**Files to delete by end of plan:**
- `application-tree.tsx` (~1263 lines)
- `folder-tree.tsx` (~807 lines)

**Estimated net line reduction:** ~1800 lines deleted, ~100 lines added for porting features = ~1700 net reduction.

---

## Pre-Implementation: Features to Port

These are features unique to `ApplicationTree` (AT) that must be merged into `KnowledgeTree` (KT) before AT can be deleted. Features are also analyzed for `FolderTree` (FT) compatibility since KT will replace both.

### Feature P1: Background Refresh Indicator
- **Source:** AT lines 17, 364-367, 1154-1158
- **What:** Show a `<Loader2>` spinner when `useFolderTree` is refetching in background (not initial load)
- **Port to KT:** Add `isFetching: isFoldersFetching` to KT's `useFolderTree` call. Add `Loader2` to imports. Add spinner JSX before `SortableContext`.

### Feature P2: `hideIfEmpty` on ProjectSection
- **Source:** AT lines 111, 134, 168-172, 302
- **What:** Optionally hide empty project sections when expanded and loaded
- **Port to KT:** Add `hideIfEmpty?: boolean` to `ProjectSectionProps`, add `isEmpty` useMemo, add conditional `return null`.

### Feature P3: `isProjectsContentLoading` in Loading Check
- **Source:** AT lines 380, 467
- **What:** Skeleton should wait for `useProjectsWithContent` data in application scope
- **Port to KT:** Destructure `isLoading: isProjectsContentLoading` and include in `isInitialLoad` condition.

### Feature P4: Scoped `findDocInCache` (AT's Two-Tier Search)
- **Decision: KEEP KT's approach.** KT's broad `['documents']` search is functionally correct and simpler. AT's two-tier approach was an optimization with negligible performance impact. No porting needed.

### Feature P5: AT's More Thorough `isRootDocument`
- **Decision: KEEP KT's approach.** KT's `isRootDocument` calls `findDocInCache` which does a broad search and checks `!doc.folder_id`. Functionally equivalent.

### Feature P6: AT's Conditional Fragment Wrappers
- **Decision: NOT PORTED.** React handles empty `.map()` arrays gracefully. KT's direct rendering is cleaner.

### Feature P7: Fix DnD prefix for non-application scopes (Critical)
- **Source:** KT line 486: `const dndPrefix = isApplicationScope ? 'app' : 'personal'`
- **Bug:** When KT replaces FT in project scope (no `applicationId`), `dndPrefix` is `'personal'`. This causes `parsePrefixToScope('personal')` to return `{ scope: 'personal', scopeId: '' }`, and `getScopeFromPrefix` to return `{ scope: 'personal', scopeId: projectId }`. All DnD mutations would incorrectly use scope `'personal'` instead of `'project'`.
- **Fix:** Change `dndPrefix` to use the actual `scope` from context when not in application mode: `const dndPrefix = isApplicationScope ? 'app' : scope`. FolderTree already uses `scope` as its prefix (FT line 227), so this matches existing behavior.

---

## Types to Verify

### Phase 1 Changes

| Interface | File | Change | Consumers to Update |
|-----------|------|--------|-------------------|
| `KnowledgeTreeProps` | `knowledge-tree.tsx` | No change | None |
| `ProjectSectionProps` | `knowledge-tree.tsx` | Add `hideIfEmpty?: boolean` | Internal only |
| `ProjectSection` return type | `knowledge-tree.tsx` | `JSX.Element` -> `JSX.Element \| null` | Internal only |
| `ApplicationTreeProps` | **DELETED** | N/A | `knowledge-panel.tsx` |

**Consumer updates for Phase 1:**
- `knowledge-panel.tsx` line 38: Remove `ApplicationTree` import, add `KnowledgeTree` import
- `knowledge-panel.tsx` lines 217-221: Replace `<ApplicationTree applicationId={scopeId} />` with `<KnowledgeTree applicationId={scopeId} />`

### Phase 2 Changes

| Interface | File | Change | Consumers to Update |
|-----------|------|--------|-------------------|
| `FolderTree` component | **DELETED** | N/A | `knowledge-panel.tsx` |

**Consumer updates for Phase 2:**
- `knowledge-panel.tsx` line 37: Remove `FolderTree` import
- `knowledge-panel.tsx` lines 217-221: Simplify conditional to single `<KnowledgeTree>` with conditional `applicationId`

### Phase 3 Changes

| Interface | File | Change | Consumers to Update |
|-----------|------|--------|-------------------|
| `EditorPanel` (new) | `editor-panel.tsx` | New shared component | `knowledge-panel.tsx`, `pages/notes/index.tsx` |
| `EditorSkeleton` | Moves from `knowledge-panel.tsx` to `editor-panel.tsx` | Re-export location changes | `pages/notes/index.tsx` |

---

## Phase 1: Eliminate ApplicationTree (Merge into KnowledgeTree)

### Step 1.0: Fix DnD prefix for non-application scopes

**What:** Fix the hardcoded `'personal'` DnD prefix to use the actual scope from context. This is required before FolderTree can be replaced (Phase 2) but should be done first since it's a correctness fix.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
1. Line 486: Change the prefix computation:
   ```ts
   // BEFORE:
   const dndPrefix = isApplicationScope ? 'app' : 'personal'
   // AFTER:
   const dndPrefix = isApplicationScope ? 'app' : scope
   ```

2. Line 468: Update `sortableItems` prefix to match:
   ```ts
   // BEFORE:
   const prefix = isApplicationScope ? 'app' : 'personal'
   // AFTER (already correct -- it uses dndPrefix indirectly)
   ```
   Actually, `sortableItems` at line 468 computes its own prefix inline. Change it to use `dndPrefix`:
   ```ts
   // BEFORE:
   const prefix = isApplicationScope ? 'app' : 'personal'
   // Since dndPrefix is defined at line 486 (AFTER sortableItems at line 466),
   // we need to move dndPrefix BEFORE sortableItems, or inline the same logic.
   ```

   **Order fix:** Move the `dndPrefix` definition (line 486) to BEFORE the `sortableItems` useMemo (line 466). Then use `dndPrefix` inside `sortableItems`:
   ```ts
   const dndPrefix = isApplicationScope ? 'app' : scope

   const sortableItems = useMemo(() => {
     const items: string[] = []
     const addFolders = (nodes: FolderTreeNode[]) => {
       nodes.forEach(node => {
         items.push(`${dndPrefix}-folder-${node.id}`)
         addFolders(node.children)
       })
     }
     addFolders(filteredFolders)
     filteredDocs.forEach(doc => {
       items.push(`${dndPrefix}-doc-${doc.id}`)
     })
     return items
   }, [dndPrefix, filteredFolders, filteredDocs])
   ```

3. Also update `renderFolderNode` and `renderDocumentItem` which compute their own `prefix`:
   - Line 835 in `renderDocumentItem`: Change `const prefix = isApplicationScope ? 'app' : 'personal'` to `const prefix = dndPrefix`
   - Line 866 in `renderFolderNode`: Change `const prefix = isApplicationScope ? 'app' : 'personal'` to `const prefix = dndPrefix`
   - Update dependency arrays: replace `isApplicationScope` with `dndPrefix` where it was only used for prefix computation.

**Verification:**
1. KnowledgeTree in personal scope: `dndPrefix = 'personal'` (unchanged behavior)
2. KnowledgeTree with `applicationId`: `dndPrefix = 'app'` (unchanged behavior)
3. KnowledgeTree in project scope (future, after Phase 2): `dndPrefix = 'project'` (matches FolderTree behavior)
4. TypeScript compiles cleanly.

**Risk:** Low. The change only affects the non-application path, which currently only runs on the Notes page personal tab (where `scope = 'personal'`, so `dndPrefix` stays `'personal'` -- no behavioral change). The fix enables correct behavior for future project scope usage.

---

### Step 1.1: Add `Loader2` Import to KnowledgeTree

**What:** Import the `Loader2` icon needed for the background refresh indicator.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
- Line 17: Add `Loader2` to the lucide-react import:
  ```ts
  import { FilePlus, Folder, FileText, FolderKanban, ChevronRight, Loader2 } from 'lucide-react'
  ```

**Order:** Independent, no dependencies.

**Verification:** TypeScript compiles. `Loader2` is available in scope.

**Risk:** None -- additive import only.

---

### Step 1.2: Add `hideIfEmpty` to KnowledgeTree's ProjectSection

**What:** Port the `hideIfEmpty` feature from AT's ProjectSection into KT's ProjectSection.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
1. Add `hideIfEmpty?: boolean` to `ProjectSectionProps` (after line 109):
   ```ts
   /** Hide this project section if it has no documents after loading */
   hideIfEmpty?: boolean
   ```

2. Add `hideIfEmpty = false` to the destructured props in the function signature (line 124-137):
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
     onSelectDocument,
     onContextMenu,
     onRenameSubmit,
     onRenameCancel,
   }: ProjectSectionProps): JSX.Element | null {
   ```
   Note: Return type changes from `JSX.Element` to `JSX.Element | null`.

3. Add `isEmpty` useMemo after the `isLoading` calculation (after line 159):
   ```ts
   const isEmpty = useMemo(() => {
     if (!isExpanded || isLoading) return false
     return folders.length === 0 && unfiledDocs.length === 0
   }, [isExpanded, isLoading, folders.length, unfiledDocs.length])
   ```

4. Add conditional return AFTER all hooks but BEFORE the JSX return. Place it after `renderDocumentItem` callback (after line 261), before the `return` at line 263:
   ```ts
   // Hide section if expanded, loaded, and empty (when hideIfEmpty is true)
   // This must be AFTER all hooks to avoid React "fewer hooks" error
   if (hideIfEmpty && isExpanded && isEmpty && !isLoading) {
     return null
   }
   ```

**Order:** Independent, no dependencies.

**Verification:** KnowledgeTree still renders project sections normally when `hideIfEmpty` is not passed (default `false`). The conditional return is placed after ALL hooks.

**Risk:** Low. Must verify placement is after all hooks to avoid React rules-of-hooks violation.

---

### Step 1.3: Add Background Refresh Indicator to KnowledgeTree

**What:** Destructure `isFetching` from `useFolderTree` and render a spinner when refetching in background.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
1. Line 331: Add `isFetching` destructuring:
   ```ts
   const { data: folderTree, isLoading: isFoldersLoading, isFetching: isFoldersFetching } = useFolderTree(scope, effectiveScopeId)
   ```

2. In the render output, after `<div className="py-1" role="tree">` (line 959), add the spinner:
   ```tsx
   {/* Subtle background refresh indicator */}
   {isFoldersFetching && !isFoldersLoading && (
     <div className="flex items-center justify-end px-2 pb-0.5">
       <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
     </div>
   )}
   ```

**Order:** Depends on Step 1.1 (`Loader2` import).

**Verification:** Trigger a background refetch (e.g., manual invalidation). Verify spinner appears briefly. Verify it does NOT appear during initial load (only when `isFetching && !isLoading`).

**Risk:** Low.

---

### Step 1.4: Include `isProjectsContentLoading` in KnowledgeTree Loading Check

**What:** When in application scope, include `isProjectsContentLoading` in the initial load condition.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**
1. Line 339: Destructure `isLoading` from `useProjectsWithContent`:
   ```ts
   const { data: projectsWithContent, isLoading: isProjectsContentLoading } = useProjectsWithContent(isApplicationScope ? applicationId! : null)
   ```

2. Line 409: Update `isInitialLoad`:
   ```ts
   const isInitialLoad = (isFoldersLoading || isUnfiledLoading || (isApplicationScope && isProjectsContentLoading)) && !hasAnyData
   ```

**Order:** Independent, no dependencies.

**Verification:** In application scope, skeleton remains visible until project content data loads. In personal/project scope, `isProjectsContentLoading` is irrelevant (query is disabled when `!isApplicationScope`).

**Risk:** Low.

---

### Step 1.5: Update KnowledgePanel to Use KnowledgeTree Instead of ApplicationTree

**What:** Replace the `ApplicationTree` import and usage in `KnowledgePanel` with `KnowledgeTree`.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
1. Line 38: Remove the ApplicationTree import:
   ```ts
   // DELETE this line:
   import { ApplicationTree } from './application-tree'
   ```

2. Add KnowledgeTree import (can go where ApplicationTree was):
   ```ts
   import { KnowledgeTree } from './knowledge-tree'
   ```

3. Lines 217-221: Replace `ApplicationTree` with `KnowledgeTree` in the conditional:
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

**Order:** Depends on Steps 1.0-1.4 (all fixes and features ported first).

**Verification:**
1. Open an Application detail page -> Knowledge tab. Tree renders identically to before.
2. Context menu operations (create, rename, delete) work in both app-level and project scopes.
3. Drag-and-drop works within scopes and is blocked across scopes.
4. Background refresh spinner appears during refetches.
5. Empty state "Create your first document" button works.

**Risk:** Medium. This is the critical swap. If any AT-specific behavior was missed in porting, it will surface here.

---

### Step 1.6: Delete ApplicationTree

**What:** Delete the `application-tree.tsx` file entirely.

**File:** `electron-app/src/renderer/components/knowledge/application-tree.tsx` -- **DELETE**

**Details:**
- Delete the file.
- Run these verification searches:

**Order:** Depends on Step 1.5 (all consumers updated).

**Verification:**
1. Search for remaining imports: `grep -r "application-tree" electron-app/src/` returns no results.
2. Search for remaining references: `grep -r "ApplicationTree" electron-app/src/` returns no results.
3. TypeScript compiles: `npm run typecheck`
4. Test all three surfaces: Notes page personal tab, Notes page application tab, Application detail Knowledge tab.

**Risk:** Low -- all consumers already updated.

---

## Phase 2: Eliminate FolderTree (KnowledgeTree Handles All Scopes)

### Step 2.1: Update KnowledgePanel to Use KnowledgeTree Instead of FolderTree

**What:** Replace the remaining `FolderTree` usage in KnowledgePanel with `KnowledgeTree`.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
1. Remove the FolderTree import (line 37):
   ```ts
   // DELETE this line:
   import { FolderTree } from './folder-tree'
   ```

2. Simplify the tree selection logic. Replace the conditional:
   ```tsx
   // BEFORE (after Step 1.5):
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

**Why this works:** When `applicationId` is `undefined`, KnowledgeTree reads `scope` and `scopeId` from the `KnowledgeBaseProvider` context. KnowledgePanel sets up the provider with `initialScope={scope}` and `initialScopeId={scopeId}`, so KT receives the correct scope. The DnD prefix fix from Step 1.0 ensures `dndPrefix = scope` (e.g., `'project'`) which matches FolderTree's behavior.

**Behavioral parity analysis for FolderTree replacement:**
- **DnD prefix:** FT uses `scope` (e.g., `'project'`). KT with fix uses `scope` when `!isApplicationScope`. Match.
- **Context menu:** FT has 4-param `handleContextMenu`. KT has 6-param with defaults (falls back to context scope). When called with 4 args from `renderFolderNode`/`renderDocumentItem`, defaults fill in correctly. Match.
- **Scope tracking state:** FT has no `renamingItemScope`/`renamingItemScopeId`/`createScope`/`createScopeId`. KT has these but they default to `null`/`''` and fall back to context scope. Match.
- **`ActiveDragItem.scope`:** FT omits `scope` field. KT includes it. Extra field is harmless -- unused in single-scope mode. Match.
- **`SortableContext` nesting:** FT wraps `div[role=tree]` inside `SortableContext`. KT nests `SortableContext` inside `div[role=tree]`. `SortableContext` renders no DOM element, so functionally identical.
- **`isRootFolder`/`isRootDocument`:** FT only checks local data. KT also searches all caches. Broader search is a superset -- never produces incorrect results. Match.
- **Cache lookups:** FT searches only current scope (`queryKeys.documents(scope, scopeId)`). KT searches all scopes (`['documents']`). Broader search returns the same results for single-scope scenarios. Match.
- **`handleDeleteConfirm` dependency array:** FT is missing `scope`/`scopeId` in deps (pre-existing bug). KT correctly includes `scope`/`effectiveScopeId`. Improvement.

**Order:** Depends on Phase 1 completion (especially Step 1.0 DnD prefix fix).

**Verification:**
1. Open a Project detail page -> Knowledge tab. Tree shows project-scoped folders and documents.
2. Context menu operations work.
3. Drag-and-drop works within the single scope.
4. Open Application detail page -> Knowledge tab with `showProjectFolders={true}`. Project sections still visible.
5. All DnD operations use correct scope in mutations (verify with network inspector or console logs).

**Risk:** Medium. The DnD prefix fix is critical for correctness. Test thoroughly in project scope.

---

### Step 2.2: Delete FolderTree and Update dnd-utils.ts Comment

**What:** Delete the `folder-tree.tsx` file and update the `dnd-utils.ts` file header comment.

**Files:**
- `electron-app/src/renderer/components/knowledge/folder-tree.tsx` -- **DELETE**
- `electron-app/src/renderer/components/knowledge/dnd-utils.ts` -- **MODIFY**

**Details:**
1. Delete `folder-tree.tsx`.
2. In `dnd-utils.ts`, line 4: Change comment from `Used by KnowledgeTree, ApplicationTree, and FolderTree` to `Used by KnowledgeTree`.

**Order:** Depends on Step 2.1 (all consumers updated).

**Verification:**
1. Search: `grep -r "folder-tree" electron-app/src/` returns only `folder-tree-item` references (different component, keep it).
2. Search: `grep -r "FolderTree" electron-app/src/` returns no import/usage results. Note: `FolderTreeNode` (from `use-document-folders.ts`) is a DIFFERENT export and must NOT be removed.
3. TypeScript compiles: `npm run typecheck`
4. All four surfaces work: Notes page personal, Notes page application, Application detail Knowledge tab, Project detail Knowledge tab.

**Risk:** Low -- all consumers already updated.

---

### Step 2.3 (OPTIONAL): Extract `useTreeDnd` Hook from KnowledgeTree

**Note:** This step is recommended for a follow-up PR. Include only if user explicitly requests it.

**What:** Extract DnD state and handlers into a custom hook to reduce KnowledgeTree's size.

**File (new):** `electron-app/src/renderer/hooks/use-tree-dnd.ts`
**File (modify):** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**

Extract from KnowledgeTree:

**State:** `activeItem`, `setActiveItem`, `dropTargetFolderId`, `setDropTargetFolderId`

**Functions:** `findDocInCache`, `getDocRowVersion`, `getScopeFromPrefix`, `getFolderTree`, `isRootFolder`, `isRootDocument`, `moveItemToRoot`, `handleDragStart`, `handleDragOver`, `handleDragEnd`

**Hook interface:**
```ts
interface UseTreeDndOptions {
  scope: string
  effectiveScopeId: string | null
  isApplicationScope: boolean
  dndPrefix: string
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
  isRootFolder: (folderId: string) => boolean
  isRootDocument: (documentId: string) => boolean
}
```

**In KnowledgeTree**, replace ~150 lines of DnD logic with:
```ts
const dnd = useTreeDnd({
  scope, effectiveScopeId, isApplicationScope, dndPrefix,
  folders, filteredFolders, filteredDocs, unfiledDocs,
  expandFolder,
})
```

Then reference `dnd.activeItem`, `dnd.handleDragStart`, etc. throughout.

**Order:** After Step 2.2. Do this after deleting FolderTree so we only maintain one copy.

**Risk:** Medium. Hook extraction is refactoring -- the logic is moved, not changed. Main risk is missing a dependency or breaking a callback closure.

---

### Step 2.4 (OPTIONAL): Extract `useTreeCrud` Hook from KnowledgeTree

**Note:** This step is recommended for a follow-up PR. Include only if user explicitly requests it.

**What:** Extract CRUD state and handlers into a custom hook.

**File (new):** `electron-app/src/renderer/hooks/use-tree-crud.ts`
**File (modify):** `electron-app/src/renderer/components/knowledge/knowledge-tree.tsx`

**Details:**

Extract from KnowledgeTree:

**State:** `renamingItemId`, `renamingItemType`, `renamingItemScope`, `renamingItemScopeId`, `contextMenuTarget`, `createDialogOpen`, `createType`, `createParentId`, `createScope`, `createScopeId`, `deleteDialogOpen`, `deleteTarget`

**Functions:** `handleContextMenu`, `handleCloseContextMenu`, `handleNewFolder`, `handleNewDocument`, `handleCreateSubmit`, `handleRename`, `handleRenameSubmit`, `handleRenameCancel`, `handleDelete`, `handleDeleteConfirm`, `handleSelectDocument`, `handleCreateFirstDocument`

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
  handleContextMenu: (...args: any[]) => void
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

**Order:** Depends on Step 2.3 (DnD hook extracted first, since CRUD uses `findDocInCache`/`getDocRowVersion`).

**Risk:** Medium. Same refactoring risk as Step 2.3.

---

## Phase 3: Unify KnowledgePanel Editor with Notes Page EditorPanel

### Step 3.1: Create Shared `EditorPanel` Component

**What:** Create a new `EditorPanel` component that encapsulates the entire right panel: `useEditMode`, `DocumentActionBar`, `DocumentEditor`, and all three dialogs.

**File (new):** `electron-app/src/renderer/components/knowledge/editor-panel.tsx`

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
import { cn } from '@/lib/utils'
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

**Order:** Independent -- can be done in parallel with Phase 1 or 2.

**Verification:** File compiles. Not yet integrated.

**Risk:** Low -- new file, no consumers yet.

---

### Step 3.2: Update Notes Page to Use Shared EditorPanel

**What:** Replace the inline `EditorPanel` in `pages/notes/index.tsx` with the shared component.

**File:** `electron-app/src/renderer/pages/notes/index.tsx`

**Details:**
1. Remove the inline `EditorPanel` function (lines 47-194).

2. Remove the `EditorSkeleton` import from `knowledge-panel`:
   ```ts
   // DELETE this line:
   import { EditorSkeleton } from '@/components/knowledge/knowledge-panel'
   ```

3. Add the new import:
   ```ts
   import { EditorPanel } from '@/components/knowledge/editor-panel'
   ```

4. Remove these imports that are no longer needed (they were only used by the inline EditorPanel):
   - `useMemo` from react (line 17) -- check: `useEffect` is still used in `NotesPageContent`, so keep `useEffect`. `useMemo` is NOT used elsewhere in the file, so remove it.
   - `FileText, Save, Trash2, AlertTriangle` from lucide-react (line 19) -- entire lucide import line can be removed since no other component in this file uses these icons.
   - `useEditMode` from `@/hooks/use-edit-mode` (line 23)
   - `DocumentEditor` from knowledge components (line 30)
   - `DocumentActionBar` from knowledge components (line 31)
   - `ensureContentHeading` from content-utils (line 32)
   - `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogFooter` from `@/components/ui/dialog` (lines 33-40)
   - `Button` from `@/components/ui/button` (line 41)

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

**Key behavioral note:** The Notes page used `key={selectedDocumentId}` on the `DocumentEditor` component, which forces a full TipTap editor remount when switching documents. The shared `EditorPanel` preserves this via the `keyByDocumentId` prop, which passes `key={selectedDocumentId}` to `DocumentEditor` when truthy.

**Order:** Depends on Step 3.1.

**Verification:**
1. Open Notes page. Select a document. Editor renders with action bar.
2. Enter edit mode, make changes, save -- all works.
3. Switch documents -- editor fully remounts (key prop). Verify no stale content.
4. Discard dialog appears when cancelling dirty editor.
5. Inactivity dialog appears after timeout.
6. Quit dialog appears when closing app with unsaved changes.

**Risk:** Medium. Must verify the `key` behavior is preserved.

---

### Step 3.3: Update KnowledgePanel to Use Shared EditorPanel

**What:** Replace the inline editor/dialogs in `KnowledgePanel`'s `InnerPanel` with the shared `EditorPanel`.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
1. Remove these imports that are no longer needed:
   - `useRef, useEffect, useMemo` from react (line 15). Keep `useCallback, useState`.
     ```ts
     // BEFORE:
     import { useCallback, useRef, useEffect, useState, useMemo } from 'react'
     // AFTER:
     import { useCallback, useState } from 'react'
     ```
     Wait -- `useRef` and `useEffect` are used by the resize logic (lines 98-99, 175-180). These must be kept!
     ```ts
     // CORRECT AFTER:
     import { useCallback, useRef, useEffect, useState } from 'react'
     ```
     Only `useMemo` is removed (was used for `parsedContent`).

   - `FileText, Save, Trash2, AlertTriangle` from lucide-react (line 16). Keep `FilePlus, FolderPlus`.
     ```ts
     // BEFORE:
     import { FileText, FilePlus, FolderPlus, Save, Trash2, AlertTriangle } from 'lucide-react'
     // AFTER:
     import { FilePlus, FolderPlus } from 'lucide-react'
     ```

   - `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogFooter` from `@/components/ui/dialog` (lines 19-26) -- entire import block removed.

   - `Button` from `@/components/ui/button` (line 27) -- removed.

   - `useEditMode` from `@/hooks/use-edit-mode` (line 35) -- removed.

   - `DocumentEditor` from `./document-editor` (line 39) -- removed.

   - `DocumentActionBar` from `./document-action-bar` (line 40) -- removed.

   - `ensureContentHeading` from `./content-utils` (line 41) -- removed.

2. Remove the `EditorSkeleton` export (lines 59-75). It moves to `editor-panel.tsx`.

3. Add import for shared EditorPanel:
   ```ts
   import { EditorPanel } from './editor-panel'
   ```

4. In `InnerPanel`, remove:
   - `useEditMode` call (lines 102-105)
   - `currentDoc` / `isDocError` variables (lines 107-108)
   - `parsedContent` useMemo (lines 111-116)
   - The entire right panel JSX (lines 232-348) -- replace with:
     ```tsx
     {/* Right panel: editor */}
     <EditorPanel />
     ```

   Note: `keyByDocumentId` is NOT passed (intentional -- KnowledgePanel relies on content prop changes, not full remount, matching the original behavior where `key` was not set on `DocumentEditor`).

5. Update `useKnowledgeBase()` destructuring (line 94):
   ```ts
   // BEFORE:
   const { selectedDocumentId, selectDocument } = useKnowledgeBase()
   // AFTER:
   const { selectDocument } = useKnowledgeBase()
   ```
   `selectedDocumentId` is no longer used in InnerPanel (it was used for the editor ternary and `useEditMode`, both now in `EditorPanel`). `selectDocument` is still used in `handleCreateDoc` onSuccess callback (line 133).

**Order:** Depends on Step 3.1.

**Verification:**
1. Open Application detail -> Knowledge tab. Select a document. Editor renders.
2. Enter edit mode, make changes, save.
3. All three dialogs work (discard, inactivity, quit).
4. Empty state shows "Select a document" message.
5. Document error state shows "Document not found".
6. Verify `key` behavior: KnowledgePanel does NOT pass `keyByDocumentId`, so `key={undefined}` means no key -- editor updates via content prop changes. This matches the original behavior.

**Risk:** Medium. Must verify no regressions in editor behavior.

---

### Step 3.4: Update EditorSkeleton Import in Notes Page

**What:** This was already handled in Step 3.2 (the old import of `EditorSkeleton` from `knowledge-panel` was removed and replaced by the import of `EditorPanel` from `editor-panel`). The shared `EditorPanel` component contains its own `EditorSkeleton` internally.

However, verify no other files import `EditorSkeleton` from `knowledge-panel.tsx`:

**Verification:**
Run: `grep -r "EditorSkeleton" electron-app/src/`

Expected results:
- `editor-panel.tsx` -- exports it (new location)
- No other files should import it from `knowledge-panel`

If any other files are found, update their imports to:
```ts
import { EditorSkeleton } from '@/components/knowledge/editor-panel'
```

**Risk:** Low.

---

### Step 3.5: Clean Up KnowledgePanel InnerPanel

**What:** After extracting EditorPanel, verify InnerPanel is clean and remove any unused imports.

**File:** `electron-app/src/renderer/components/knowledge/knowledge-panel.tsx`

**Details:**
The resize logic stays -- it controls the tree panel width. After Step 3.3, InnerPanel should contain:
- Tree panel (left side): search, create buttons, KnowledgeTree in ScrollArea
- Resize handle
- `<EditorPanel />` (right side)

Run `npm run lint` to catch any unused imports or variables.

Expected final `InnerPanel` size: ~80 lines (down from ~260).

**Order:** After Step 3.3.

**Verification:** TypeScript compiles. Lint passes. KnowledgePanel still renders correctly.

**Risk:** None.

---

## Verification Checklist (Post-All-Phases)

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
- [ ] Verify DnD mutations use correct scope (network inspector)

**Project Detail Page - Knowledge Tab:**
- [ ] KnowledgePanel renders with KnowledgeTree (no applicationId)
- [ ] Only project-scope folders and documents shown
- [ ] No project sections (since not in application scope)
- [ ] Editor panel works
- [ ] DnD mutations use scope `'project'` (not `'personal'`) -- verify via network inspector
- [ ] Context menu CRUD uses correct project scope

### Deleted Files
- [ ] `application-tree.tsx` is deleted
- [ ] `folder-tree.tsx` is deleted
- [ ] No imports reference these files

### New Files
- [ ] `components/knowledge/editor-panel.tsx` exists and exports `EditorPanel` + `EditorSkeleton`

### Optional New Files (if Steps 2.3-2.4 are included)
- [ ] `hooks/use-tree-dnd.ts` exists and exports `useTreeDnd`
- [ ] `hooks/use-tree-crud.ts` exists and exports `useTreeCrud`

---

## Risk Summary

| Step | Risk | Mitigation |
|------|------|-----------|
| 1.0 (DnD prefix fix) | Low | No behavioral change for current consumers (personal tab uses `'personal'`). Enables correct project scope behavior. |
| 1.5 (Swap AT -> KT) | Medium | KT's broad cache search is functionally equivalent. Test all CRUD ops in app scope. |
| 2.1 (Swap FT -> KT) | Medium | DnD prefix fix ensures correct scope. Test project-scope CRUD and DnD. |
| 3.2-3.3 (EditorPanel swap) | Medium | `keyByDocumentId` prop preserves per-consumer behavior. |

## Rollback Strategy

Each phase is independently deployable:
- **Phase 1:** If AT replacement fails, revert Step 1.5 (restore `ApplicationTree` import/usage). Steps 1.0-1.4 are additive to KT and harmless to revert.
- **Phase 2:** If FT replacement fails, revert Step 2.1 (restore `FolderTree` import/usage).
- **Phase 3:** If EditorPanel extraction fails, revert Steps 3.2-3.3 (restore inline editors). Step 3.1 (new file) is harmless.

Recommend committing after each phase so rollback is easy.

---

## Estimated Scope

| Phase | Steps | Files Changed | Files Created | Files Deleted | Net Lines |
|-------|-------|---------------|---------------|---------------|-----------|
| 1 | 7 | 2 | 0 | 1 | -1200 |
| 2 | 2 (or 4 with optional hooks) | 2 | 0 (or 2) | 1 | -750 (or -500 with hooks) |
| 3 | 5 | 2 | 1 | 0 | -130 |
| **Total** | **14** (or **16**) | **6** | **1** (or **3**) | **2** | **~-2080** (or **~-1830**) |

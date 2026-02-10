# Research Phase 3: Layout & Structural Duplication

## Overview

This document maps the layout and structural duplication between:
- **KnowledgePanel** (`knowledge-panel.tsx`) -- embedded two-panel knowledge component for detail pages
- **Notes page** (`pages/notes/index.tsx`) -- full-screen knowledge page with KnowledgeSidebar + EditorPanel

Both surfaces share a common pattern: left panel (tree navigation) + right panel (document editor), with nearly identical editor integration, dialog rendering, and edit-mode state management.

---

## A. Left Panel Comparison

### KnowledgePanel's Left Panel (InnerPanel, lines 187-223)

| Feature | Implementation |
|---|---|
| Search | `<SearchBar />` in a `p-2 border-b` wrapper |
| Create buttons | Inline icon buttons (`FilePlus`, `FolderPlus`) -- immediate creation, no dialog |
| Tree | `<ApplicationTree>` (if scope=application + showProjectFolders) or `<FolderTree />` |
| Scroll | `<ScrollArea className="flex-1">` wrapping tree |
| Tag filter | **Not present** |
| Collapse toggle | **Not present** (always expanded) |
| Width | CSS `style={{ width: treeWidth }}`, flex-shrink-0 |
| Background | `bg-sidebar` |

### KnowledgeSidebar (knowledge-sidebar.tsx, lines 131-221)

| Feature | Implementation |
|---|---|
| Search | **Not present** (search is at page level, line 274 of notes/index.tsx) |
| Create buttons | Icon buttons (`FilePlus`, `FolderPlus`) -- opens `CreateDialog` with name input |
| Tree | `<KnowledgeTree applicationId={...}>` |
| Scroll | `<ScrollArea className="flex-1">` wrapping tree |
| Tag filter | `<TagFilterList />` in a `border-t p-2` section at bottom |
| Collapse toggle | **Present** -- `PanelLeftClose`/`PanelLeftOpen` button, shows "Notes" label when expanded |
| Width | CSS `style={{ width: sidebarWidth }}`, ref-based (persisted to localStorage) |
| Background | `bg-sidebar` |

### Resize Logic Comparison

| Aspect | KnowledgePanel | KnowledgeSidebar |
|---|---|---|
| Constants | `MIN_TREE_WIDTH=200, MAX_TREE_WIDTH=500, DEFAULT_TREE_WIDTH=280` | `MIN_WIDTH=200, MAX_WIDTH=500, DEFAULT_WIDTH=256` |
| State approach | `useState(DEFAULT_TREE_WIDTH)` + `useRef(isResizing)` | `useState(fromLocalStorage)` + `useState(isResizing)` |
| Persistence | **Not persisted** (resets on remount) | **Persisted** to `localStorage('knowledge-sidebar-width')` |
| Resize handle | Separate `<div>` between panels: `w-1 cursor-col-resize bg-border hover:bg-primary/50` | Absolutely-positioned `<div>` at right edge: `absolute top-0 right-0 w-1 h-full` with `GripVertical` icon |
| Mouse events | Adds `mousemove`/`mouseup` to `document` in mousedown handler, removes in mouseup | Uses `useEffect` driven by `isResizing` state -- adds/removes listeners reactively |
| Cursor/select | Sets `document.body.style.cursor` and `userSelect` directly | Same approach, but cleanup is in the `useEffect` return |
| Cleanup | `useEffect` cleanup to remove listeners on unmount | Effect-based cleanup is automatic |

**Key difference**: The resize patterns are functionally equivalent but use different implementation strategies (imperative ref-based vs reactive state-based). The constants are nearly identical (200/500 min/max, 256 vs 280 default).

### Create Button Behavior Comparison

| Aspect | KnowledgePanel | KnowledgeSidebar |
|---|---|---|
| UX flow | **Immediate creation** -- clicks directly call `createDocument.mutate()` with hardcoded title "Untitled" / "New Folder" | **Dialog-based** -- opens `CreateDialog` with name input field |
| Auto-select | New document is auto-selected via `onSuccess` callback | No auto-select (dialog just creates) |
| Folder context | Always creates at root (`folder_id: null`, `parent_id: null`) | Uses `selectedFolderId` from context to create inside selected folder |
| Scope resolution | Props-based (`scope` and `scopeId` from parent) | Derived from `activeTab` via `resolveScope()` helper |

---

## B. Right Panel / Editor Comparison

### KnowledgePanel's Right Panel (InnerPanel, lines 232-348)

The right panel is defined **inline within InnerPanel** as part of the same component that holds the left panel. It occupies `<div className="flex-1 flex flex-col min-w-0 min-h-0">`.

### Notes Page EditorPanel (notes/index.tsx, lines 47-193)

The right panel is a **separate inner component** `EditorPanel()` rendered inside `<main className="flex-1 flex flex-col min-h-0">`.

### Edit Mode Integration

Both use `useEditMode` identically:

```tsx
// KnowledgePanel (line 102)
const editMode = useEditMode({ documentId: selectedDocumentId, userRole: null })

// Notes page EditorPanel (line 51)
const editMode = useEditMode({ documentId: selectedDocumentId, userRole: null })
```

Both consume the same fields: `mode`, `lockHolder`, `isLockedByOther`, `canForceTake`, `isDirty`, `isSaving`, `isEntering`, `isExiting`, `document`, `isDocError`, and all action handlers.

### Dialog Rendering -- EXACT DUPLICATES

Both components render **three identical dialogs** with the same JSX structure:

1. **Discard changes dialog** (KnowledgePanel lines 264-281, EditorPanel lines 123-140)
   - Same `DialogTitle`: "Discard changes?"
   - Same buttons: "Keep editing" (outline) + "Discard" (destructive)
   - Same `onOpenChange` pattern: `if (!open) editMode.cancelDiscard()`

2. **Inactivity dialog** (KnowledgePanel lines 284-304, EditorPanel lines 143-163)
   - Same `DialogTitle`: "Are you still editing?"
   - Same buttons: "Discard" + "Save" + "Keep Editing"
   - Same `onOpenChange` pattern: `if (!open) editMode.inactivityKeepEditing()`

3. **Quit confirmation dialog** (KnowledgePanel lines 307-332, EditorPanel lines 166-191)
   - Same structure: amber warning icon, centered title/description
   - Same buttons: "Save and close" + "Discard and close" + "Keep editing"
   - Same `sm:max-w-md` class on DialogContent

These three dialogs are **character-for-character identical** between the two components. This is the single largest copy-paste duplication.

### DocumentActionBar Usage

Both pass the **exact same props** to DocumentActionBar:

```tsx
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
```

This is identical in both locations -- exact same props, same arrow-function wrappers.

### DocumentEditor Usage

| Aspect | KnowledgePanel | Notes page EditorPanel |
|---|---|---|
| `key` prop | **Not set** | `key={selectedDocumentId}` -- forces remount on doc switch |
| `content` | `parsedContent` (memoized with `ensureContentHeading`) | Same |
| `onChange` | `editMode.handleContentChange` | Same |
| `onBaselineSync` | `editMode.handleBaselineSync` | Same |
| `editable` | `editMode.mode === 'edit'` | Same |
| `placeholder` | `"Start writing..."` | Same |
| `className` | `"flex-1"` | Same |
| `updatedAt` | `currentDoc.updated_at` | Same |

**Notable difference**: The Notes page uses `key={selectedDocumentId}` to force a full editor remount when switching documents. KnowledgePanel does not -- it relies on content prop changes to update. This may cause stale TipTap state in KnowledgePanel when switching documents.

### Content Memoization

Both use the exact same `useMemo` pattern:

```tsx
const parsedContent = useMemo(
  () => currentDoc
    ? ensureContentHeading(currentDoc.content_json, currentDoc.title)
    : undefined,
  [currentDoc?.content_json, currentDoc?.title]
)
```

### Empty State / Error State

Both render the same empty and error states:

| State | KnowledgePanel | Notes page EditorPanel |
|---|---|---|
| No document selected | `FileText` icon + "Select a document to start editing" | Identical |
| Document not found | `FileText` icon + "Document not found" | Identical |
| Loading | `<EditorSkeleton />` (exported from knowledge-panel.tsx) | Same component imported from knowledge-panel.tsx |

The rendering order differs slightly:
- **KnowledgePanel**: Nested ternaries inline within the JSX (`selectedDocumentId ? currentDoc ? ... : isDocError ? ... : skeleton : empty`)
- **Notes EditorPanel**: Early returns (`if (!selectedDocumentId) return ...`, `if (!currentDoc && isDocError) return ...`, `if (!currentDoc) return skeleton`)

The early-return style in EditorPanel is cleaner and more readable.

---

## C. Top-Level Layout Comparison

### KnowledgePanel Layout

```
KnowledgeBaseProvider (storagePrefix="kb-{scope}-{scopeId}-")
  └─ InnerPanel (flex h-full overflow-hidden)
       ├─ Left panel (width: treeWidth, flex-shrink-0)
       │    ├─ SearchBar
       │    ├─ Create buttons (FilePlus, FolderPlus)
       │    └─ ScrollArea > ApplicationTree or FolderTree
       ├─ Resize handle (w-1)
       └─ Right panel (flex-1 flex flex-col)
            ├─ DocumentActionBar
            ├─ DocumentEditor
            └─ 3x Dialogs (discard, inactivity, quit)
```

- Single-level horizontal split
- Search is inside the left panel
- No tabs
- No tag filter
- Provider uses scoped `storagePrefix` to isolate localStorage

### Notes Page Layout

```
KnowledgeBaseProvider (default prefix)
  └─ NotesPageContent (flex flex-col h-full)
       ├─ SearchBar (full-width, outside sidebar)
       ├─ KnowledgeTabBar (full-width)
       └─ Main content (flex flex-1 min-h-0)
            ├─ KnowledgeSidebar (left panel)
            │    ├─ Collapse toggle
            │    ├─ Create buttons (with CreateDialog)
            │    ├─ ScrollArea > KnowledgeTree
            │    ├─ TagFilterList
            │    └─ Resize handle (absolute positioned)
            └─ main (flex-1)
                 └─ EditorPanel
                      ├─ DocumentActionBar
                      ├─ DocumentEditor (keyed)
                      └─ 3x Dialogs (discard, inactivity, quit)
```

- Two-level nesting: vertical (search + tabs + content) then horizontal (sidebar + editor)
- Search is at page level, above the tab bar
- Tab bar spans full width
- Sidebar has collapsibility, tag filter section, dialog-based creation
- Provider uses default prefix (no scoping)

### Provider Wrapping Differences

| Aspect | KnowledgePanel | Notes Page |
|---|---|---|
| Props | `initialScope={scope}`, `initialScopeId={scopeId}`, `storagePrefix={...}` | No props (uses defaults) |
| Scope management | Fixed scope from props | Dynamic -- tab changes drive scope via `deriveFromTab()` |
| Storage isolation | Scoped prefix per instance (`kb-application-{id}-`) | Shared default prefix (`kb-`) |
| Multiple instances | Can have many mounted simultaneously without conflict | Only one instance at a time |

---

## D. Features Unique to Each

### Notes Page Only

1. **WebSocket room management** (lines 207-223): Joins/leaves WS rooms based on activeTab (personal or application room)
2. **Document deletion sync** (lines 226-251): Clears selection when `DOCUMENT_DELETED` event arrives; handles `FOLDER_DELETED`
3. **Document update sync** (lines 254-269): Invalidates document query cache when `DOCUMENT_UPDATED` arrives from another user
4. **Tab bar** (`KnowledgeTabBar`): Full-width tabs for switching between personal and application scopes, with overflow dropdown
5. **Tag filtering** (`TagFilterList`): Click-to-toggle tag filter in the sidebar
6. **Sidebar collapse** (`PanelLeftClose`/`PanelLeftOpen`): Toggle sidebar visibility
7. **Dialog-based creation** (`CreateDialog`): Name input dialog for new docs/folders
8. **Folder-aware creation**: Creates docs/folders inside the currently selected folder
9. **`useApplicationsWithDocs` query**: Fetches application summary for tab bar
10. **`key={selectedDocumentId}`** on DocumentEditor: Forces full editor remount on document switch

### KnowledgePanel Only

1. **Scoped provider** with `storagePrefix`: Multiple instances can coexist without localStorage collisions
2. **`showProjectFolders` prop**: Switches between `ApplicationTree` and `FolderTree` based on scope
3. **Inline creation** (no dialog): Quick one-click creation with default names
4. **Auto-select on create**: New documents are immediately selected
5. **`EditorSkeleton` export**: Defines and exports the skeleton component (reused by Notes page)

---

## E. Unification Opportunities

### 1. Shared EditorPanel Component (HIGH IMPACT)

The entire right panel can be extracted into a shared `EditorPanel` component. The duplicated code includes:
- `useEditMode` call and all its consumers (~20 lines)
- `useMemo` for `parsedContent` (~5 lines)
- `DocumentActionBar` with identical props (~12 lines)
- `DocumentEditor` with identical props (~8 lines)
- **Three identical dialogs** (~70 lines each x 3 = ~70 lines total)
- Empty state, error state, loading skeleton (~15 lines)

**Estimated deduplication**: ~130 lines of near-identical JSX/logic.

**Proposed interface**:
```tsx
interface EditorPanelProps {
  /** Force remount on doc switch (Notes page uses this) */
  keyByDocumentId?: boolean
  className?: string
}
```

The component would:
- Get `selectedDocumentId` from `useKnowledgeBase()` context
- Own the `useEditMode` call internally
- Render DocumentActionBar + DocumentEditor + all 3 dialogs
- Handle empty/error/loading states

### 2. Shared Edit Mode Dialogs Component (MEDIUM IMPACT)

If a full EditorPanel extraction is too aggressive, at minimum the 3 dialogs can be extracted:

```tsx
interface EditModeDialogsProps {
  editMode: UseEditModeReturn
}
function EditModeDialogs({ editMode }: EditModeDialogsProps)
```

This would eliminate ~70 lines of duplicated dialog JSX.

### 3. Shared Sidebar Layout (LOW-MEDIUM IMPACT)

The left panels have more divergence (collapse toggle, tag filter, creation UX, search placement) so full unification is harder. However, the following could be shared:

- **Resize logic**: Extract a `useResizablePanel` hook with `{ width, handleMouseDown, containerRef }` return. Both panels use nearly identical logic with the same min/max constants.
- **Create button strip**: A `CreateButtonStrip` component that takes `onCreateDoc` and `onCreateFolder` callbacks. The icon buttons are identical; only the handler behavior differs.

### 4. Resize Hook (LOW IMPACT, HIGH REUSE)

```tsx
function useResizablePanel(options: {
  defaultWidth: number
  minWidth?: number  // default 200
  maxWidth?: number  // default 500
  persistKey?: string // localStorage key
}): {
  width: number
  isResizing: boolean
  handleMouseDown: (e: React.MouseEvent) => void
  containerRef: React.RefObject<HTMLDivElement>
}
```

This hook would unify the two resize implementations and eliminate ~30 lines per consumer.

### What Must Remain Separate

1. **KnowledgePanel**: Scoped provider wrapping, `showProjectFolders` tree switching, inline creation, no tabs/tags
2. **Notes page**: WebSocket room management, deletion/update sync effects, tab bar, tag filter, collapse toggle, dialog-based creation, page-level search bar placement
3. **Provider props**: KnowledgePanel needs `initialScope`/`initialScopeId`/`storagePrefix`; Notes page uses defaults

---

## F. Summary: Duplication Severity

| Duplicated Area | Lines (approx) | Severity |
|---|---|---|
| Edit mode dialogs (3x) | ~70 | **CRITICAL** -- character-for-character identical |
| DocumentActionBar props wiring | ~12 | **HIGH** -- identical props |
| DocumentEditor props wiring | ~8 | **HIGH** -- identical except `key` |
| useEditMode call + content memo | ~15 | **HIGH** -- identical |
| Empty/error/loading states | ~15 | **MEDIUM** -- same pattern, slightly different nesting |
| Resize logic | ~30 per site | **MEDIUM** -- same algorithm, different implementation style |
| Create button UI | ~10 | **LOW** -- same icons, different behavior |

**Total estimated deduplication potential**: ~160-180 lines of JSX/logic by extracting a shared EditorPanel, plus ~30 lines per site from a shared resize hook.

# Phase 6: Document Tabs & Editor UI Integration - Research

**Researched:** 2026-02-01
**Domain:** Browser-style document tabs, metadata bar, title editing, editor layout integration (React + TailwindCSS + Radix UI)
**Confidence:** HIGH

## Summary

Phase 6 integrates the editor (Phase 3), auto-save (Phase 4), lock banner (Phase 5), and sidebar (Phase 2) into a cohesive Notes screen by adding browser-style document tabs, an editable title header, a metadata bar (tags, scope, last edited by), and a bottom status bar (word count, last saved timestamp). This is a primarily frontend phase -- no new backend endpoints are required for tabs/title/status bar. However, two backend gaps exist: (1) the Document model has no `updated_by` field (needed for "last edited by" in UI-07), and (2) no frontend mutation hooks exist for tag assignment/unassignment (the backend endpoints exist).

The existing codebase provides all required infrastructure: `KnowledgeBaseContext` (at `electron-app/src/renderer/contexts/knowledge-base-context.tsx`) manages UI state including `selectedDocumentId` via useReducer, the `useDocument` hook fetches full document data, `useAutoSave` provides `isDirty()` and `saveNow()` and `saveStatus`, `useDocumentLock` provides lock state, and the Notes page at `electron-app/src/renderer/pages/notes/index.tsx` has a placeholder main content area ready to be replaced with tab bar and editor panel. The `@radix-ui/react-tabs` package is installed (v1.1.0) but should NOT be used -- see Architecture Patterns.

The key architectural decision is where to store open-tabs state: it belongs in `KnowledgeBaseContext` (extended with new actions) with localStorage persistence, NOT in a separate context or component-local state. The reason is that `activeTabId` and `selectedDocumentId` represent the same concept and must stay in sync -- they are an invariant (`activeTabId === selectedDocumentId` at all times).

**Primary recommendation:** Extend `KnowledgeBaseContext` with `openTabs: TabItem[]` and `activeTabId: string | null` state. Build a custom `DocumentTabBar` component (not Radix Tabs). Create `DocumentHeader` (editable title + metadata bar) and `DocumentStatusBar` (word count + last saved) components. Compose everything in a `DocumentPanel` that replaces the current placeholder in `NotesPage`. The existing `EditorStatusBar` inside `document-editor.tsx` must be removed to avoid duplication.

## Standard Stack

### Core (Already in Codebase -- No New Packages Required)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React Context (useReducer) | React 18.3 | Tab state in KnowledgeBaseContext | Already used for all KB UI state per STATE.md decision |
| @tanstack/react-query | ^5.90.20 | `useDocument` for fetching document data per tab | Already used for all data fetching |
| @tiptap/react | ^2.6.0 | Editor instance for active tab | Already installed, Phase 3 built the editor |
| @tiptap/extension-character-count | ^2.27.2 | Word count for status bar (via `useEditorState`) | Already installed and configured in `editor-extensions.ts` |
| lucide-react | ^0.400.0 | Icons (X, FileText, Tag, FolderKanban, Plus) | Already used throughout UI |
| tailwindcss | installed | All component styling | Already used |
| @radix-ui/react-tooltip | ^1.1.2 | Tooltips on tab items (show full title on hover) | Already installed, wrapper at `components/ui/tooltip.tsx` |
| @radix-ui/react-popover | ^1.1.1 | Tag add/remove popover in metadata bar | Already installed, wrapper at `components/ui/popover.tsx` |
| @radix-ui/react-separator | ^1.1.0 | Visual dividers in metadata bar | Already installed, wrapper at `components/ui/separator.tsx` |
| @radix-ui/react-scroll-area | ^1.1.0 | Horizontal scroll for many open tabs | Already installed, wrapper at `components/ui/scroll-area.tsx` |

### Supporting (Already in Codebase)

| Library / Module | Location | Purpose | When to Use |
|---------|---------|---------|-------------|
| `useRelativeTime` | `@/lib/time-utils.ts` | Live-updating relative timestamps | "Last edited X ago" in metadata bar, "Last saved X ago" in status bar |
| `formatRelativeTime` | `@/lib/time-utils.ts` | One-shot relative time formatting | Static timestamp display |
| `useDocument` | `@/hooks/use-documents.ts` | Fetch full document with content and tags | DocumentPanel when tab becomes active |
| `useRenameDocument` | `@/hooks/use-documents.ts` | Rename mutation with row_version | Editable title save on blur/Enter |
| `useDocumentTags` | `@/hooks/use-document-tags.ts` | Fetch available tags for scope | Tag picker popover (list available tags) |
| `useAutoSave` | `@/hooks/use-auto-save.ts` | isDirty, saveNow, saveStatus | Tab dirty indicator, status bar save state, save-on-close |
| `useSaveOnUnmount` | `@/hooks/use-auto-save.ts` | Save on component unmount | Tab switching (editor remount) |
| `useSaveOnQuit` | `@/hooks/use-auto-save.ts` | Save before Electron quit | Active document before app close |
| `useDocumentLock` | `@/hooks/use-document-lock.ts` | Lock acquisition + banner state | Lock banner in editor area |
| `SaveStatus` component | `@/components/knowledge/SaveStatus.tsx` | Live "Saving..." / "Saved Xs ago" display | Reusable in new DocumentStatusBar |
| `Skeleton` | `@/components/ui/skeleton.tsx` | Loading placeholder | While useDocument is in loading state |
| Input | `@/components/ui/input.tsx` | Inline title editing | Click-to-rename title input |
| Popover | `@/components/ui/popover.tsx` | Tag management popover | Metadata bar tag add/remove |
| Tooltip / TooltipContent | `@/components/ui/tooltip.tsx` | Tab title tooltip | Truncated tab titles |
| Separator | `@/components/ui/separator.tsx` | Vertical dividers | Between metadata bar sections |
| ScrollArea | `@/components/ui/scroll-area.tsx` | Horizontal scroll | Tab bar overflow |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom tab bar | `@radix-ui/react-tabs` (installed, v1.1.0) | Radix Tabs is a content-panel switcher (like settings tabs), NOT a browser-style tab bar. It lacks: close buttons per tab, dirty indicators, middle-click-to-close, overflow scrolling. **Custom is correct.** |
| localStorage for tab persistence | IndexedDB | Tabs are tiny (array of `{id, title}`), well under 1KB. localStorage is simpler and already used for KB state (scope, expanded folders). **Use localStorage.** |
| Separate TabContext | Extended KnowledgeBaseContext | Tab state is tightly coupled to `selectedDocumentId` -- the active tab IS the selected document. Separate context creates two sources of truth. **Extend existing context.** |
| `editor.commands.setContent()` for tab switch | `key={activeTabId}` remount | `setContent()` is unreliable for large documents, retains undo history from previous doc, causes flash-of-content. **Use key-based remount.** |

**Installation:** No new packages needed. Zero npm install operations.

## Architecture Patterns

### Recommended Project Structure (New + Modified Files)

```
electron-app/src/renderer/
├── contexts/
│   └── knowledge-base-context.tsx   # MODIFY: add openTabs, activeTabId state + 7 new actions
├── components/
│   └── knowledge/
│       ├── document-tab-bar.tsx      # NEW: browser-style tab bar container
│       ├── document-tab-item.tsx     # NEW: single tab with close button, dirty dot
│       ├── document-panel.tsx        # NEW: main content panel (header + editor + status bar)
│       ├── document-header.tsx       # NEW: editable title + metadata bar
│       ├── document-status-bar.tsx   # NEW: word count + last saved (replaces internal EditorStatusBar)
│       ├── tag-manager.tsx           # NEW: tag add/remove popover for metadata bar
│       └── document-editor.tsx       # MODIFY: remove internal EditorStatusBar, optionally expose editor ref
├── hooks/
│   └── use-document-tags.ts         # MODIFY: add useAssignDocumentTag + useUnassignDocumentTag mutations
├── pages/
│   └── notes/
│       └── index.tsx                # MODIFY: replace placeholder with DocumentTabBar + DocumentPanel
```

### Pattern 1: Tab State in KnowledgeBaseContext

**What:** Extend the existing `KnowledgeBaseContext` with open-tabs state managed via useReducer actions.
**When to use:** All tab operations (open, close, switch, mark dirty, update title).

**New state fields:**
```typescript
interface TabItem {
  id: string       // document ID (primary key for tabs)
  title: string    // cached title for display (updated on document load/rename)
  isDirty: boolean // true when document has unsaved changes
}

// Added to KnowledgeBaseUIState:
interface KnowledgeBaseUIState {
  // ... existing 8 fields ...
  openTabs: TabItem[]
  activeTabId: string | null  // which tab is currently visible
}
```

**New actions (7 total):**
```typescript
type KnowledgeBaseAction =
  // ... existing 12 action types ...
  | { type: 'OPEN_TAB'; documentId: string; title: string }
  | { type: 'CLOSE_TAB'; documentId: string }
  | { type: 'SET_ACTIVE_TAB'; documentId: string }
  | { type: 'SET_TAB_DIRTY'; documentId: string; isDirty: boolean }
  | { type: 'UPDATE_TAB_TITLE'; documentId: string; title: string }
  | { type: 'CLOSE_OTHER_TABS'; documentId: string }
  | { type: 'CLOSE_ALL_TABS' }
```

**Key reducer logic for OPEN_TAB:**
```typescript
case 'OPEN_TAB': {
  const exists = state.openTabs.find(t => t.id === action.documentId)
  if (exists) {
    // Tab already open -- just activate it
    return {
      ...state,
      activeTabId: action.documentId,
      selectedDocumentId: action.documentId,
    }
  }
  // New tab -- append and activate
  return {
    ...state,
    openTabs: [...state.openTabs, { id: action.documentId, title: action.title, isDirty: false }],
    activeTabId: action.documentId,
    selectedDocumentId: action.documentId,
  }
}
```

**Key reducer logic for CLOSE_TAB:**
```typescript
case 'CLOSE_TAB': {
  const idx = state.openTabs.findIndex(t => t.id === action.documentId)
  const newTabs = state.openTabs.filter(t => t.id !== action.documentId)
  let newActiveId = state.activeTabId

  if (state.activeTabId === action.documentId) {
    // Activate adjacent tab: prefer right neighbor, then left
    if (newTabs.length === 0) {
      newActiveId = null
    } else if (idx < newTabs.length) {
      newActiveId = newTabs[idx].id  // right neighbor moved into this index
    } else {
      newActiveId = newTabs[newTabs.length - 1].id  // was rightmost, go left
    }
  }

  return {
    ...state,
    openTabs: newTabs,
    activeTabId: newActiveId,
    selectedDocumentId: newActiveId,
  }
}
```

**Bidirectional sync with selectedDocumentId:** The existing `SELECT_DOCUMENT` reducer case (line 192 of current file) only sets `selectedDocumentId`. It must NOT be modified to also open a tab, because the reducer does not have the document title. Instead, the components that call `selectDocument()` (sidebar folder tree, search results) should call the new `openTab(documentId, title)` action instead, which both opens a tab AND sets `selectedDocumentId`.

**Persistence:** Use localStorage with keys `kb-open-tabs` and `kb-active-tab`:
- On state change, persist `openTabs` (without `isDirty` -- always resets to false on reload) and `activeTabId`
- On app startup, restore from localStorage in the useReducer initializer
- The `isDirty` flag is NOT persisted -- auto-save from Phase 4 handles unsaved content on recovery via IndexedDB drafts

**Confidence:** HIGH -- extends the existing well-tested useReducer pattern.

### Pattern 2: Document Panel with key-Based Remount

**What:** A composite component that renders the active document's header, editor, and status bar. Uses React's `key` prop to force full remount when switching tabs.
**When to use:** As the main content area to the right of the sidebar.

```typescript
function DocumentPanel() {
  const { activeTabId } = useKnowledgeBase()

  if (!activeTabId) {
    return <EmptyState />  // "Select or create a document to start editing"
  }

  // key={activeTabId} forces React to destroy + recreate the entire subtree
  // when switching tabs. This:
  // 1. Destroys the old TipTap editor (editor.destroy() on unmount)
  // 2. Creates fresh editor with new document content
  // 3. Resets auto-save timers, dirty state, undo history
  // 4. Is the recommended TipTap pattern for content switching
  return (
    <div key={activeTabId} className="flex-1 flex flex-col h-full min-w-0">
      <ActiveDocumentView documentId={activeTabId} />
    </div>
  )
}
```

**Why `key` remount (not `setContent`):** TipTap's `editor.commands.setContent()` is unreliable for large content swaps:
- Leaves undo history from previous document
- Can cause flash-of-old-content for one render frame
- Requires manual cleanup of dirty state, cursor position, and extension state
- The `key` approach is the standard pattern used in TipTap documentation and community

**Confidence:** HIGH -- standard React and TipTap best practice.

### Pattern 3: Editable Document Title (Click-to-Rename)

**What:** Title displayed as text (`h1`), becomes an input on click, saves on blur or Enter.
**When to use:** UI-06 requirement.

```typescript
function EditableTitle({ documentId, title, rowVersion }: Props) {
  const [isEditing, setIsEditing] = useState(false)
  const [value, setValue] = useState(title)
  const inputRef = useRef<HTMLInputElement>(null)

  // Determine scope from document for useRenameDocument
  // useRenameDocument requires (scope, scopeId) -- derived from document's FK fields
  const renameMutation = useRenameDocument(scope, scopeId)

  // Sync external title changes (e.g., after server refresh)
  useEffect(() => { setValue(title) }, [title])

  // Auto-focus + select all when entering edit mode
  useEffect(() => {
    if (isEditing) inputRef.current?.select()
  }, [isEditing])

  const handleSave = () => {
    setIsEditing(false)
    if (value.trim() && value !== title) {
      renameMutation.mutate(
        { documentId, title: value.trim(), row_version: rowVersion },
        {
          onSuccess: (updatedDoc) => {
            // Update tab title to match
            updateTabTitle(documentId, updatedDoc.title)
          }
        }
      )
    } else {
      setValue(title) // revert on empty or unchanged
    }
  }

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        value={value}
        onChange={e => setValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={e => {
          if (e.key === 'Enter') handleSave()
          if (e.key === 'Escape') { setValue(title); setIsEditing(false) }
        }}
        className="text-2xl font-bold bg-transparent border-b border-primary outline-none w-full px-0"
        maxLength={255}
      />
    )
  }

  return (
    <h1
      onClick={() => setIsEditing(true)}
      className="text-2xl font-bold cursor-pointer hover:text-primary/80 truncate"
      title="Click to rename"
    >
      {title}
    </h1>
  )
}
```

**Scope resolution for useRenameDocument:** The hook requires `(scope: string, scopeId: string)`. These must be derived from the Document object's FK fields:
- `document.application_id` is set -> scope='application', scopeId=application_id
- `document.project_id` is set -> scope='project', scopeId=project_id
- `document.user_id` is set -> scope='personal', scopeId=user_id

**Confidence:** HIGH -- standard inline-edit pattern, uses existing `useRenameDocument` hook.

### Pattern 4: Metadata Bar Layout

**What:** A horizontal bar below the title showing tags (with add/remove), scope badge, and "last edited by" info.
**When to use:** UI-07 requirement.

**Tag rendering must be consistent with sidebar's `tag-filter-list.tsx`:** Use the same color dot + name pattern. The default tag color is `#6b7280` (gray-500).

**Tag assignment API endpoints (backend already exists):**
- POST `/api/documents/{document_id}/tags` with body `{ tag_id: UUID }` -> 201 with `TagAssignmentResponse`
- DELETE `/api/documents/{document_id}/tags/{tag_id}` -> 204 no content

Frontend mutation hooks (`useAssignDocumentTag` and `useUnassignDocumentTag`) must be created in `use-document-tags.ts`. On success, invalidate `queryKeys.document(documentId)` to refresh the document's tags array.

**"Last edited by" data gap:** The Document model has `created_by` but NO `updated_by` field. This was not added by Phase 4 (confirmed by codebase inspection 2026-02-01). The `DocumentResponse` schema also has no `updated_by` field. For Phase 6, the metadata bar should:
- Show "Created by [name]" using `created_by` + the `creator` relationship
- OR show "Last edited [relative time]" using `updated_at` (available) without the editor's name
- Adding `updated_by` requires a backend migration and is a separate concern; it should be flagged but not blocked on

**Confidence:** MEDIUM -- tag management pattern is standard, but `updated_by` gap needs a decision.

### Pattern 5: Tab Dirty Indicator Integration with Auto-Save

**What:** The tab's dirty dot syncs with Phase 4's auto-save `isDirty()` and `saveStatus`.
**When to use:** UI-04 requirement.

```typescript
// In ActiveDocumentView (the component that wraps editor + auto-save):
function ActiveDocumentView({ documentId }: Props) {
  const { data: document } = useDocument(documentId)
  const { setTabDirty } = useKnowledgeBase()

  // Editor + auto-save
  const editor = useEditor({ ... })
  const { isDirty, saveNow, saveStatus } = useAutoSave({
    documentId,
    editor,
    rowVersion: document?.row_version ?? 1,
  })

  // Sync dirty state to tab bar on every editor update
  useEffect(() => {
    if (!editor) return
    const handler = () => { setTabDirty(documentId, isDirty()) }
    editor.on('update', handler)
    return () => { editor.off('update', handler) }
  }, [editor, documentId, isDirty, setTabDirty])

  // Clear dirty on successful save
  useEffect(() => {
    if (saveStatus.state === 'saved') {
      setTabDirty(documentId, false)
    }
  }, [saveStatus, documentId, setTabDirty])
}
```

**Tab dirty indicator visual:**
```typescript
// In document-tab-item.tsx:
{tab.isDirty && (
  <span className="h-2 w-2 rounded-full bg-amber-500 group-hover:hidden" />
)}
// Close button appears on hover, replacing dirty dot
<button
  onClick={e => { e.stopPropagation(); onClose() }}
  className={cn(
    'h-4 w-4 rounded-sm hover:bg-muted',
    tab.isDirty ? 'hidden group-hover:flex' : 'opacity-0 group-hover:opacity-100'
  )}
>
  <X className="h-3 w-3" />
</button>
```

**Confidence:** HIGH -- straightforward state sync.

### Pattern 6: Status Bar (Word Count + Last Saved)

**What:** Bottom bar showing word count (from CharacterCount) and last saved timestamp.
**When to use:** UI-09 requirement.

The existing `EditorStatusBar` inside `document-editor.tsx` (lines 24-38) shows word + character count. Phase 6's `DocumentStatusBar` supersedes it by also showing "last saved" timestamp. The internal `EditorStatusBar` must be REMOVED from `document-editor.tsx` to avoid duplication.

Two approaches for the new status bar:
1. **Compose SaveStatus component:** Reuse the existing `SaveStatus` component from `@/components/knowledge/SaveStatus.tsx` which already handles idle/saving/saved/error states with live-updating timer.
2. **Build fresh:** Use `useEditorState` for word count + `saveStatus` prop for save state.

Approach 1 is preferred because `SaveStatus` is already tested and handles edge cases (setTick re-render, error display).

```typescript
function DocumentStatusBar({ editor, saveStatus }: Props) {
  const { wordCount } = useEditorState({
    editor,
    selector: (ctx) => ({
      wordCount: ctx.editor?.storage.characterCount?.words() ?? 0,
    }),
  })

  return (
    <div className="flex items-center justify-between px-6 py-1.5 border-t border-border text-xs text-muted-foreground">
      <span>{wordCount.toLocaleString()} words</span>
      <SaveStatus status={saveStatus} />
    </div>
  )
}
```

**Confidence:** HIGH -- uses existing infrastructure.

### Pattern 7: Notes Page Layout Composition

**What:** Final layout wiring in NotesPage.
**When to use:** Plan 06-03.

```typescript
// pages/notes/index.tsx
function NotesPage({ applicationId }: NotesPageProps) {
  return (
    <KnowledgeBaseProvider initialScope={...} initialScopeId={...}>
      <div className="flex h-full">
        {/* Left: sidebar (Phase 2) */}
        <KnowledgeSidebar />

        {/* Right: tab bar + document content */}
        <div className="flex-1 flex flex-col h-full min-w-0">
          <DocumentTabBar />
          <DocumentPanel />
        </div>
      </div>
    </KnowledgeBaseProvider>
  )
}
```

**Layout constraints:**
- `min-w-0` on right panel prevents flex overflow from long document titles
- DocumentTabBar is OUTSIDE DocumentPanel so it persists across tab switches (no remount)
- DocumentPanel uses `key={activeTabId}` internally for editor remount

**Confidence:** HIGH -- standard flex layout composition.

### Anti-Patterns to Avoid

- **Using Radix Tabs for the tab bar:** Radix Tabs (installed at v1.1.0) is a content-panel switcher, not a browser-style tab bar. It does not support close buttons, dirty indicators, overflow scrolling, or middle-click-to-close. Build a custom tab bar with `<div role="tab">` elements.
- **Storing tab state in component-local state:** Component state is lost on unmount. Tabs must persist across sidebar navigation, scope changes, and app restarts. Use KnowledgeBaseContext with localStorage.
- **Using `editor.commands.setContent()` for tab switching:** Unreliable for large documents, retains undo history, causes content flash. Use `key={activeTabId}` to force remount.
- **Separate context for tab state:** Creates two sources of truth for "which document is active" (tabs vs selectedDocumentId). Extend KnowledgeBaseContext instead.
- **Fetching document data in tab bar:** Tab items display cached titles only (`TabItem.title`). Full document fetch happens in DocumentPanel when a tab activates.
- **Storing full Document object in tab state:** Only store `{ id, title, isDirty }`. Full document data lives in TanStack Query cache.
- **Not saving before tab close:** When closing a dirty tab, trigger `saveNow()` before removing. The auto-save mutation completes in background. IndexedDB draft is fallback.
- **Mounting editors for all open tabs:** Only mount ONE editor instance -- the active tab's. Use `key={activeTabId}` to destroy previous and create new. This matches VS Code behavior (undo history is per-session, not persistent).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Relative time display | Manual Date math + setInterval | `useRelativeTime` from `@/lib/time-utils.ts` | Already exists, auto-updates every 60s, handles edge cases |
| Document data fetching | Custom fetch + state | `useDocument(id)` from `@/hooks/use-documents.ts` | Already exists with caching, IndexedDB persistence, error types |
| Document rename API call | Custom fetch | `useRenameDocument(scope, scopeId)` from `@/hooks/use-documents.ts` | Already exists with cache invalidation + optimistic update |
| Word count | Manual text splitting | `CharacterCount` extension + `useEditorState` | Phase 3 installs this; reactive, handles ProseMirror node structure correctly |
| Save status display | Custom polling or timer | `SaveStatus` component from `@/components/knowledge/SaveStatus.tsx` | Phase 4 built this; handles idle/saving/saved/error with live timer |
| Save state machine | Custom state tracking | `useAutoSave` hook from `@/hooks/use-auto-save.ts` | Phase 4 built complete save lifecycle with refs, mutex, debounce |
| Save on unmount | Custom cleanup | `useSaveOnUnmount` from `@/hooks/use-auto-save.ts` | Already handles ref-based stale closure avoidance |
| Save on Electron quit | Custom IPC | `useSaveOnQuit` from `@/hooks/use-auto-save.ts` | Already handles Electron beforeQuit IPC with 3s timeout |
| Lock banner | Custom lock UI | `LockBanner` + `useDocumentLock` from Phase 5 | Already built with force-take, stop-editing, lock status |
| Tooltip on truncated text | Custom hover detection | `Tooltip`/`TooltipContent` from `@/components/ui/tooltip.tsx` | Already styled, accessible, positioned correctly |
| Tag display styling | Custom styled spans | Match existing pattern in `tag-filter-list.tsx` (color dot + name) | Consistent styling across app |

**Key insight:** Phase 6 is an integration and UI composition phase. Almost ALL data hooks, editor infrastructure, and utility components already exist from Phases 1-5. The primary new work is: (a) tab state management in context, (b) UI component building for tabs/header/metadata/status, (c) layout wiring, (d) tag assignment mutation hooks.

## Common Pitfalls

### Pitfall 1: Tab State and selectedDocumentId Out of Sync

**What goes wrong:** User clicks a document in the sidebar but tab bar shows different active tab. Or user clicks a tab but sidebar selection does not update.
**Why it happens:** Two independent state fields (`selectedDocumentId` and `activeTabId`) that conceptually represent the same thing.
**How to avoid:** Make `activeTabId === selectedDocumentId` an invariant. In the reducer: `OPEN_TAB` and `SET_ACTIVE_TAB` always update BOTH fields. Components that previously called `selectDocument()` (folder tree clicks at lines 252-258 of `folder-tree.tsx`) should instead call `openTab(doc.id, doc.title)`.
**Warning signs:** Sidebar highlights one document but editor shows another.

### Pitfall 2: Editor Content Flash on Tab Switch

**What goes wrong:** When switching tabs, the editor briefly shows the previous document's content.
**Why it happens:** If using `setContent()` instead of remounting, there is a render frame where old content is visible.
**How to avoid:** Use `key={activeTabId}` on the DocumentPanel to force full remount. Show a `Skeleton` while `useDocument` is in `isLoading` state.
**Warning signs:** Brief flash of wrong content when clicking tabs quickly.

### Pitfall 3: Memory Leak from Multiple Editor Instances

**What goes wrong:** Opening many tabs creates many TipTap editor instances consuming memory.
**Why it happens:** If architecture mounts editors for all open tabs (hidden with CSS) instead of only the active one.
**How to avoid:** Only mount ONE editor at a time -- the active tab's. `key={activeTabId}` destroys the previous editor on unmount (TipTap calls `editor.destroy()` automatically). Undo history is lost on switch -- this is acceptable (same as VS Code).
**Warning signs:** Memory usage growing linearly with number of open tabs.

### Pitfall 4: Dirty Indicator Not Clearing After Save

**What goes wrong:** Tab shows dirty dot even after auto-save completes.
**Why it happens:** `isDirty` in tab state was set on editor update but not cleared when `saveStatus` transitions to `saved`.
**How to avoid:** Watch `saveStatus.state === 'saved'` in a useEffect and dispatch `SET_TAB_DIRTY(documentId, false)`. Also clear on `useSaveOnUnmount` completion.
**Warning signs:** Permanent dirty dots on tabs even after "Saved" appears in status bar.

### Pitfall 5: Closing Dirty Tab Without Saving

**What goes wrong:** User closes a tab with unsaved changes. Changes are lost.
**Why it happens:** Tab close action removes tab without checking dirty state.
**How to avoid:** Before closing a dirty tab, call `saveNow()` from auto-save. Two approaches:
1. **Optimistic (recommended):** Call `saveNow()` and close immediately. The mutation completes in background. IndexedDB draft from Phase 4 is fallback.
2. **Confirm dialog:** Heavyweight and annoying for auto-saving editors.

Use approach 1 -- this matches Google Docs and Notion behavior. Note: `saveNow()` is a no-op if content has not changed or if already saving (mutex guard in use-auto-save.ts line 116).
**Warning signs:** Users losing work when rapidly closing tabs.

### Pitfall 6: Tab Title Stale After Rename

**What goes wrong:** User renames via editable title. Tab still shows old title.
**Why it happens:** Tab title is cached in `TabItem.title` and not updated when rename mutation succeeds.
**How to avoid:** In rename mutation's `onSuccess`, dispatch `UPDATE_TAB_TITLE` to update the tab's cached title. Also, in `ActiveDocumentView`, sync tab title from `useDocument` data when it refreshes (title may change from another user/session).
**Warning signs:** Tab shows "Untitled" while header shows renamed title.

### Pitfall 7: Sidebar Document Click Missing Title for Tab Opening

**What goes wrong:** Clicking a document in folder tree opens it in editor but no tab appears.
**Why it happens:** The current `handleSelectDocument` in `folder-tree.tsx` (line 252) calls `selectDocument(documentId)` but does NOT call `openTab(documentId, title)`. It only has `documentId`, not `title`.
**How to avoid:** The `renderDocumentItem` callback (line 323) receives the full `doc: DocumentListItem` object which has `doc.title`. Change the handler to accept both id and title:
```typescript
const handleSelectDocument = useCallback(
  (documentId: string, title: string) => {
    openTab(documentId, title)
    selectFolder(null)
  },
  [openTab, selectFolder]
)
// In renderDocumentItem:
onSelect={() => handleSelectDocument(doc.id, doc.title)}
```
Also update `handleNewDocument` (line 175) to call `openTab(data.id, data.title)` after creation.
**Warning signs:** Documents open but no tab appears. Tab bar stays empty.

### Pitfall 8: Tag Assignment Mutation Hooks Missing

**What goes wrong:** Metadata bar has tag add/remove UI but buttons do nothing.
**Why it happens:** `use-document-tags.ts` only has a read hook (`useDocumentTags`). No mutation hooks exist for assign/unassign.
**How to avoid:** Create `useAssignDocumentTag` and `useUnassignDocumentTag` in `use-document-tags.ts`. Backend endpoints exist:
- POST `/api/documents/{document_id}/tags` with `{ tag_id }` -> 201
- DELETE `/api/documents/{document_id}/tags/{tag_id}` -> 204

On success, invalidate `queryKeys.document(documentId)` to refresh the tags array in the document response.
**Warning signs:** Console errors on tag add/remove, or tags revert after assignment.

### Pitfall 9: Duplicate Status Bar

**What goes wrong:** Two status bars appear at the bottom of the editor -- one from `document-editor.tsx` and one from the new `DocumentStatusBar`.
**Why it happens:** The existing `DocumentEditor` component renders an internal `EditorStatusBar` (lines 24-38 of `document-editor.tsx`) showing word + character counts. Phase 6 adds a separate `DocumentStatusBar` in `DocumentPanel`.
**How to avoid:** Remove `EditorStatusBar` from `document-editor.tsx` when Phase 6's `DocumentStatusBar` is added. Two options:
1. Remove the internal status bar entirely (clean)
2. Add a `showStatusBar?: boolean` prop to `DocumentEditor` (flexible but more complex)

Option 1 is recommended since Phase 6 permanently supersedes the internal status bar.
**Warning signs:** Two lines of word count display at the bottom.

### Pitfall 10: Scope Resolution for useRenameDocument

**What goes wrong:** `useRenameDocument` requires `(scope, scopeId)` but the DocumentPanel only has a `documentId`.
**Why it happens:** The rename hook is scoped -- it needs to know which list to invalidate on success.
**How to avoid:** Derive scope from the document's FK fields:
```typescript
function deriveScope(doc: Document): { scope: string; scopeId: string } {
  if (doc.application_id) return { scope: 'application', scopeId: doc.application_id }
  if (doc.project_id) return { scope: 'project', scopeId: doc.project_id }
  if (doc.user_id) return { scope: 'personal', scopeId: doc.user_id }
  throw new Error('Document has no scope')
}
```
**Warning signs:** TypeScript error on hook call, or rename succeeds but list does not refresh.

## Code Examples

### KnowledgeBaseContext Extension -- New Types

```typescript
// Source: Derived from existing knowledge-base-context.tsx pattern

// New type for tab items
export interface TabItem {
  id: string       // document ID
  title: string    // display title (cached)
  isDirty: boolean // unsaved changes indicator
}

// New localStorage keys (alongside existing STORAGE_KEY_SIDEBAR, etc.)
const STORAGE_KEY_TABS = 'kb-open-tabs'
const STORAGE_KEY_ACTIVE_TAB = 'kb-active-tab'

// New persistence helpers
function loadTabs(): TabItem[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY_TABS)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed)) {
        // Restore without isDirty (always starts clean)
        return parsed.map((t: { id: string; title: string }) => ({
          id: t.id,
          title: t.title,
          isDirty: false,
        }))
      }
    }
  } catch { /* ignore */ }
  return []
}

function persistTabs(tabs: TabItem[]): void {
  try {
    // Persist id + title only (not isDirty)
    const toStore = tabs.map(t => ({ id: t.id, title: t.title }))
    localStorage.setItem(STORAGE_KEY_TABS, JSON.stringify(toStore))
  } catch { /* ignore */ }
}
```

### KnowledgeBaseContext Extension -- New Callbacks

```typescript
// Source: Matches existing useCallback pattern in knowledge-base-context.tsx

// Added to KnowledgeBaseContextValue:
openTab: (documentId: string, title: string) => void
closeTab: (documentId: string) => void
setActiveTab: (documentId: string) => void
setTabDirty: (documentId: string, isDirty: boolean) => void
updateTabTitle: (documentId: string, title: string) => void
closeOtherTabs: (documentId: string) => void
closeAllTabs: () => void

// Implementation (in provider):
const openTab = useCallback((documentId: string, title: string) => {
  dispatch({ type: 'OPEN_TAB', documentId, title })
}, [])

const closeTab = useCallback((documentId: string) => {
  dispatch({ type: 'CLOSE_TAB', documentId })
}, [])

const setActiveTab = useCallback((documentId: string) => {
  dispatch({ type: 'SET_ACTIVE_TAB', documentId })
}, [])

const setTabDirty = useCallback((documentId: string, isDirty: boolean) => {
  dispatch({ type: 'SET_TAB_DIRTY', documentId, isDirty })
}, [])

const updateTabTitle = useCallback((documentId: string, title: string) => {
  dispatch({ type: 'UPDATE_TAB_TITLE', documentId, title })
}, [])
```

### Document Tab Item Component

```typescript
// Source: Custom component following existing UI patterns

import { FileText, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { TabItem } from '@/contexts/knowledge-base-context'

interface DocumentTabItemProps {
  tab: TabItem
  isActive: boolean
  onActivate: () => void
  onClose: () => void
}

function DocumentTabItem({ tab, isActive, onActivate, onClose }: DocumentTabItemProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          role="tab"
          aria-selected={isActive}
          className={cn(
            'group flex items-center gap-2 px-3 py-2 text-sm border-r border-border cursor-pointer',
            'hover:bg-muted/50 transition-colors select-none',
            'max-w-[200px] min-w-[100px]',
            isActive
              ? 'bg-background text-foreground border-b-2 border-b-primary'
              : 'text-muted-foreground'
          )}
          onClick={onActivate}
          onMouseDown={e => {
            if (e.button === 1) { // Middle-click to close
              e.preventDefault()
              onClose()
            }
          }}
        >
          <FileText className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate flex-1">{tab.title || 'Untitled'}</span>
          <div className="shrink-0 w-4 h-4 flex items-center justify-center">
            {tab.isDirty ? (
              <span className="h-2 w-2 rounded-full bg-amber-500 group-hover:hidden" />
            ) : null}
            <button
              onClick={e => { e.stopPropagation(); onClose() }}
              className={cn(
                'h-4 w-4 rounded-sm hover:bg-muted flex items-center justify-center',
                tab.isDirty ? 'hidden group-hover:flex' : 'opacity-0 group-hover:opacity-100'
              )}
              title="Close tab"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom">{tab.title || 'Untitled'}</TooltipContent>
    </Tooltip>
  )
}
```

### Tag Assignment Mutation Hooks

```typescript
// Source: Derived from existing mutation patterns in use-documents.ts

export function useAssignDocumentTag(
  documentId: string
): UseMutationResult<TagAssignmentResponse, Error, string> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (tagId: string) => {
      const response = await window.electronAPI.post<TagAssignmentResponse>(
        `/api/documents/${documentId}/tags`,
        { tag_id: tagId },
        getAuthHeaders(token)
      )
      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data))
      }
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.document(documentId) })
    },
  })
}

export function useUnassignDocumentTag(
  documentId: string
): UseMutationResult<void, Error, string> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (tagId: string) => {
      const response = await window.electronAPI.delete<void>(
        `/api/documents/${documentId}/tags/${tagId}`,
        getAuthHeaders(token)
      )
      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.document(documentId) })
    },
  })
}
```

### Scope Helper for Document Components

```typescript
// Source: Derived from resolveScope in use-documents.ts

/**
 * Derive scope type and scope ID from a Document's FK fields.
 * Used by DocumentHeader for useRenameDocument and tag management.
 */
export function deriveDocumentScope(doc: {
  application_id: string | null
  project_id: string | null
  user_id: string | null
}): { scope: string; scopeId: string } {
  if (doc.application_id) return { scope: 'application', scopeId: doc.application_id }
  if (doc.project_id) return { scope: 'project', scopeId: doc.project_id }
  if (doc.user_id) return { scope: 'personal', scopeId: doc.user_id }
  throw new Error('Document has no scope FK set')
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single document view (placeholder) | Browser-style tabs with dirty indicators | Phase 6 | Users work with multiple docs simultaneously |
| Placeholder main area | Full editor integration (header + metadata + editor + status) | Phase 6 | Complete document editing experience |
| `selectedDocumentId` only | `openTabs[]` + `activeTabId` (synced with `selectedDocumentId`) | Phase 6 | Tab state persists across navigation + app restart |
| No inline title editing | Click-to-rename with optimistic save | Phase 6 | Faster renaming without dialog |
| Internal `EditorStatusBar` (word + chars) | External `DocumentStatusBar` (word count + save status) | Phase 6 | Unified status bar with save state |
| No tag management in editor | Inline tag add/remove popover | Phase 6 | Tags manageable without leaving editor |

**Deprecated/outdated:**
- The current Notes page placeholder (`<FileText /> Select a document...` at line 38-41 of notes/index.tsx) will be replaced entirely
- `selectedDocumentId` alone will no longer drive content area -- `activeTabId` takes over, with `selectedDocumentId` kept in sync
- `EditorStatusBar` inside `document-editor.tsx` will be removed (superseded by `DocumentStatusBar`)

## Open Questions

1. **`updated_by` field for "Last edited by" display**
   - What we know: The Document model has `created_by` but NO `updated_by`. Phase 4 did NOT add it (confirmed 2026-02-01 inspection). The `DocumentResponse` schema also lacks it.
   - What's unclear: Whether to add `updated_by` (requires Alembic migration + schema change + service change) in Phase 6 or defer it.
   - Recommendation: **For Phase 6, show "Last edited [relative time]" using `updated_at` (which exists and is updated by auto-save).** Omit the editor's name for now. Adding `updated_by` is a backend schema change that should be a separate sub-plan or deferred. The metadata bar can show: `Last edited {useRelativeTime(doc.updated_at)}` -- this satisfies the spirit of UI-07 without the name.

2. **Tab close behavior for dirty documents**
   - What we know: Phase 4 auto-saves every 10s of inactivity. IndexedDB drafts persist every 2s (Phase 4.2).
   - What's unclear: Whether to silently save or show confirmation.
   - Recommendation: **Silently call `saveNow()` and close immediately (optimistic).** The mutation completes in background. IndexedDB draft provides crash recovery. This matches Google Docs and Notion behavior. No confirmation dialog needed.

3. **Maximum number of open tabs**
   - What we know: Browser tab bars degrade around 15-20 tabs.
   - What's unclear: Whether to impose a hard limit.
   - Recommendation: **Allow unlimited tabs with horizontal scroll via `overflow-x-auto`.** Do NOT limit. Add "Close other tabs" and "Close all tabs" to right-click context menu. This matches VS Code and browser behavior.

4. **Tag picker UX in metadata bar**
   - What we know: Tags for the scope are fetched via `useDocumentTags(scope, scopeId)`. The document's assigned tags are in `document.tags`.
   - What's unclear: Whether the tag picker should allow creating new tags inline, or only assign existing ones.
   - Recommendation: **For Phase 6, only assign existing tags.** Tag CRUD (create, update, delete tags) is a management feature that can be added later. The tag picker popover shows available tags (minus already-assigned ones) with click-to-assign.

## Sources

### Primary (HIGH confidence)
- Codebase: `electron-app/src/renderer/contexts/knowledge-base-context.tsx` -- all 362 lines read, state shape, reducer, actions, localStorage patterns verified
- Codebase: `electron-app/src/renderer/pages/notes/index.tsx` -- all 48 lines read, placeholder content area at lines 38-41 confirmed
- Codebase: `electron-app/src/renderer/components/knowledge/document-editor.tsx` -- all 137 lines read, internal EditorStatusBar at lines 24-38, DocumentEditorProps verified
- Codebase: `electron-app/src/renderer/components/knowledge/editor-types.ts` -- all 46 lines read, DocumentEditorProps interface verified
- Codebase: `electron-app/src/renderer/components/knowledge/SaveStatus.tsx` -- all 75 lines read, SaveStatus component verified
- Codebase: `electron-app/src/renderer/components/knowledge/LockBanner.tsx` -- all 75 lines read, LockBanner component verified
- Codebase: `electron-app/src/renderer/hooks/use-documents.ts` -- all 391 lines read, Document type (no updated_by), useDocument, useRenameDocument verified
- Codebase: `electron-app/src/renderer/hooks/use-document-tags.ts` -- all 132 lines read, only read hook confirmed (no mutation hooks)
- Codebase: `electron-app/src/renderer/hooks/use-auto-save.ts` -- all 235 lines read, isDirty, saveNow, saveStatus, SaveStatus type, useSaveOnUnmount, useSaveOnQuit verified
- Codebase: `electron-app/src/renderer/hooks/use-document-lock.ts` -- existence verified
- Codebase: `electron-app/src/renderer/components/knowledge/folder-tree.tsx` -- all 431 lines read, handleSelectDocument at line 252 (only takes documentId), renderDocumentItem at line 323 (has full doc object)
- Codebase: `electron-app/src/renderer/components/knowledge/knowledge-sidebar.tsx` -- all 86 lines read
- Codebase: `electron-app/src/renderer/components/knowledge/tag-filter-list.tsx` -- all 112 lines read, tag display pattern verified
- Codebase: `electron-app/src/renderer/components/knowledge/editor-extensions.ts` -- all 292 lines read, CharacterCount extension confirmed
- Codebase: `electron-app/src/renderer/lib/time-utils.ts` -- all 84 lines read, useRelativeTime, formatRelativeTime, formatAbsoluteTime verified
- Codebase: `electron-app/src/renderer/lib/query-client.ts` -- queryKeys object verified (documents, document, documentFolders, documentTags, documentLock)
- Codebase: `electron-app/package.json` -- all relevant package versions verified
- Codebase: `fastapi-backend/app/models/document.py` -- all 211 lines read, NO updated_by field confirmed
- Codebase: `fastapi-backend/app/schemas/document.py` -- all 136 lines read, DocumentResponse has NO updated_by confirmed
- Codebase: `fastapi-backend/app/routers/documents.py` -- tag assignment endpoints verified (POST /{document_id}/tags, DELETE /{document_id}/tags/{tag_id})
- Codebase: `fastapi-backend/app/routers/document_tags.py` -- tag CRUD endpoints verified
- Codebase: `fastapi-backend/app/schemas/document_tag.py` -- TagAssignment and TagAssignmentResponse schemas verified
- `.planning/STATE.md` -- all decisions, blockers, and phase status verified (Phase 5 complete, Phase 6 next)

### Secondary (MEDIUM confidence)
- Tab bar UX patterns -- based on VS Code, Chrome, Notion tab behavior; no single authoritative source but well-established UI pattern
- Tag picker popover pattern -- based on GitHub labels, Linear labels; standard UI convention

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed, no new dependencies, all versions verified against package.json
- Architecture (tab state design): HIGH -- extends proven useReducer pattern with browser tab semantics, all integration points verified in codebase
- Architecture (editor remount): HIGH -- key-based remount is documented TipTap best practice
- Integration with Phases 3-5: HIGH -- all hooks and components verified to exist in codebase (useAutoSave, SaveStatus, LockBanner, CharacterCount, etc.)
- Pitfalls: HIGH -- all 10 pitfalls identified from actual codebase analysis (missing updated_by, missing tag mutations, handler signatures, duplicate status bar)
- Open questions: MEDIUM -- `updated_by` gap is confirmed but resolution approach is a product decision

**Research date:** 2026-02-01
**Valid until:** 2026-03-01 (stable domain -- React UI patterns unlikely to change)

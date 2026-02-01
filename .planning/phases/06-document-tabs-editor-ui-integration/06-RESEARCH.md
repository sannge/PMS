# Phase 6: Document Tabs & Editor UI Integration - Research

**Researched:** 2026-01-31
**Domain:** Browser-style document tabs, metadata bar, title editing, editor layout integration (React + TailwindCSS + Radix UI)
**Confidence:** HIGH

## Summary

Phase 6 integrates the editor (Phase 3), auto-save (Phase 4), and sidebar (Phase 2) into a cohesive Notes screen by adding browser-style document tabs, an editable title header, a metadata bar (tags, scope, last edited by), and a bottom status bar (word count, last saved timestamp). This is a purely frontend phase -- no new backend endpoints are required, though a missing `updated_by` field on the Document model (needed for "last edited by" in UI-07) must be tracked as a dependency on Phase 4's auto-save endpoint which adds it.

The existing codebase provides all required infrastructure: `KnowledgeBaseContext` manages UI state including `selectedDocumentId`, the `useDocument` hook fetches full document data, `@radix-ui/react-tabs` is already installed (v1.1.0) but no `tabs.tsx` shadcn/ui wrapper exists yet, and the Notes page has a placeholder main content area ready for the tab bar and editor. The key architectural decision is where to store open-tabs state: it belongs in `KnowledgeBaseContext` (extended with new actions) with localStorage persistence, NOT in a separate context or component-local state, because tab state must coordinate with `selectedDocumentId` and survive page navigations.

The tab bar is a custom component (not Radix Tabs) because browser-style tabs need features Radix Tabs does not provide: individually closeable tabs, a dirty indicator dot, middle-click-to-close, drag-to-reorder (future), and overflow scrolling. Radix Tabs is a controlled content-switching primitive, not a tab-bar widget. Building a custom tab bar with `<button>` elements and ARIA attributes is straightforward and matches how VS Code, Chrome, and Notion implement their tab UIs.

**Primary recommendation:** Extend `KnowledgeBaseContext` with `openTabs: TabItem[]` and `activeTabId: string | null` state. Build a custom `DocumentTabBar` component with close buttons and dirty indicators. Create `DocumentHeader` (editable title + metadata bar) and `DocumentStatusBar` (word count + last saved) components. Compose everything in a new `DocumentPanel` component that replaces the current placeholder in `NotesPage`.

## Standard Stack

### Core (Already in Codebase)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React Context (useReducer) | 18.3 | Tab state in KnowledgeBaseContext | Already used for all KB UI state |
| TanStack Query | ^5.90 | `useDocument` for fetching document data per tab | Already used for all data fetching |
| @tiptap/react | 2.27.2 | Editor instance for active tab | Already installed, Phase 3 builds the editor |
| @tiptap/extension-character-count | installed | Word count for status bar | Phase 3 adds this extension |
| lucide-react | ^0.400 | Icons (X for close, Circle/Dot for dirty, FileText for tab) | Already used throughout UI |
| tailwindcss | installed | All component styling | Already used |
| @radix-ui/react-tooltip | ^1.1.2 | Tooltips on tab items (show full title on hover) | Already installed |
| @radix-ui/react-popover | installed | Tag add/remove popover in metadata bar | Already installed |

### Supporting (Already in Codebase)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@/lib/time-utils.ts` | existing | `useRelativeTime` for "last saved" and "last edited by" timestamps | Status bar and metadata bar |
| `@/components/ui/input.tsx` | existing | Inline title editing input | Click-to-rename title |
| `@/components/ui/popover.tsx` | existing | Tag management popover | Metadata bar tag add/remove |
| `@/components/ui/skeleton.tsx` | existing | Loading state for document content | While useDocument is loading |
| `@/components/ui/tooltip.tsx` | existing | Tab title tooltip for truncated names | Tab bar |
| `@/components/ui/separator.tsx` | existing | Visual dividers between metadata sections | Metadata bar |
| `@/components/ui/scroll-area.tsx` | existing | Horizontal scroll for many open tabs | Tab bar overflow |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom tab bar | `@radix-ui/react-tabs` (installed, v1.1.0) | Radix Tabs is a content-panel switcher, NOT a browser-style tab bar. It lacks: close buttons per tab, dirty indicators, middle-click-to-close, overflow scrolling for many tabs. **Custom is better.** |
| localStorage for tab state | IndexedDB | Tabs are simple (array of {id, title}), < 1KB total. localStorage is simpler and already used for other KB state (scope, expanded folders). **Use localStorage.** |
| Separate TabContext | Extended KnowledgeBaseContext | Tab state is tightly coupled to selectedDocumentId (active tab IS the selected document). Separate context would require syncing two contexts. **Extend existing context.** |
| React state (no persistence) | localStorage persistence | Users expect their open tabs to survive page navigation and app restart. VS Code and Chrome both persist tabs. **Persist to localStorage.** |

**Installation:** No new packages needed.

## Architecture Patterns

### Recommended Project Structure (New Files)

```
electron-app/src/renderer/
├── contexts/
│   └── knowledge-base-context.tsx   # MODIFY: add openTabs, activeTabId state + actions
├── components/
│   └── knowledge/
│       ├── document-tab-bar.tsx      # NEW: browser-style tab bar
│       ├── document-tab-item.tsx     # NEW: single tab with close, dirty indicator
│       ├── document-panel.tsx        # NEW: main content panel (header + editor + status bar)
│       ├── document-header.tsx       # NEW: editable title + metadata bar
│       ├── document-status-bar.tsx   # NEW: word count + last saved
│       └── tag-manager.tsx           # NEW: tag add/remove popover for metadata bar
├── pages/
│   └── notes/
│       └── index.tsx                # MODIFY: replace placeholder with DocumentTabBar + DocumentPanel
```

### Pattern 1: Tab State in KnowledgeBaseContext

**What:** Extend the existing `KnowledgeBaseContext` with open-tabs state managed via useReducer actions.
**When to use:** All tab operations (open, close, switch, reorder).

**New state fields:**
```typescript
interface TabItem {
  id: string       // document ID (primary key for tabs)
  title: string    // cached title for display (updated on document load)
  isDirty: boolean // true when document has unsaved changes
}

// Added to KnowledgeBaseUIState:
interface KnowledgeBaseUIState {
  // ... existing fields ...
  openTabs: TabItem[]
  activeTabId: string | null  // which tab is currently visible
}
```

**New actions:**
```typescript
type KnowledgeBaseAction =
  // ... existing actions ...
  | { type: 'OPEN_TAB'; documentId: string; title: string }
  | { type: 'CLOSE_TAB'; documentId: string }
  | { type: 'SET_ACTIVE_TAB'; documentId: string }
  | { type: 'SET_TAB_DIRTY'; documentId: string; isDirty: boolean }
  | { type: 'UPDATE_TAB_TITLE'; documentId: string; title: string }
  | { type: 'CLOSE_OTHER_TABS'; documentId: string }
  | { type: 'CLOSE_ALL_TABS' }
```

**Key reducer logic:**
- `OPEN_TAB`: If tab already exists, just set it active. If new, append to `openTabs` and set active. Also set `selectedDocumentId` to the document ID (keeps sidebar selection in sync).
- `CLOSE_TAB`: Remove from `openTabs`. If it was the active tab, activate the next tab to the right (or left if rightmost). If no tabs remain, set `activeTabId` and `selectedDocumentId` to null.
- `SET_ACTIVE_TAB`: Update `activeTabId` and `selectedDocumentId` together (they must stay in sync).
- `SET_TAB_DIRTY`: Update the `isDirty` flag for the specified tab.

**Bidirectional sync with selectedDocumentId:** When the user clicks a document in the sidebar (`SELECT_DOCUMENT`), it should also open a tab for that document. Modify the existing `SELECT_DOCUMENT` reducer case to dispatch `OPEN_TAB` behavior (add to openTabs if not present, set as active).

**Persistence:** Persist `openTabs` and `activeTabId` to localStorage (key: `kb-open-tabs`, `kb-active-tab`). On app restart, restore tabs. The `isDirty` flag is NOT persisted (always starts false; auto-save from Phase 4 handles unsaved content).

**Confidence:** HIGH -- extends the existing well-tested useReducer pattern in KnowledgeBaseContext.

### Pattern 2: Document Panel Component Architecture

**What:** A composite component that renders the active document's header, editor, and status bar.
**When to use:** As the main content area of the Notes page.

```typescript
// document-panel.tsx
function DocumentPanel() {
  const { activeTabId, openTabs } = useKnowledgeBase()

  if (!activeTabId) {
    return <EmptyState /> // "Select a document to start editing"
  }

  // Key pattern: use `key={activeTabId}` to force full remount on tab switch.
  // This ensures the TipTap editor reinitializes with new content.
  // TipTap's `setContent()` is unreliable for large content swaps;
  // remounting is the standard approach.
  return (
    <div key={activeTabId} className="flex-1 flex flex-col h-full">
      <DocumentHeader documentId={activeTabId} />
      <div className="flex-1 overflow-auto">
        <DocumentEditor content={...} />
      </div>
      <DocumentStatusBar documentId={activeTabId} />
    </div>
  )
}
```

**Critical: `key={activeTabId}` for tab switching.** When switching tabs, the editor must remount with new content. Using `key` forces React to destroy and recreate the component tree, which:
1. Destroys the old TipTap editor instance (freeing memory)
2. Creates a fresh editor with the new document's content
3. Resets auto-save timers and dirty state
4. Is the recommended TipTap pattern for content switching

**Alternative (rejected): `editor.commands.setContent(newJson)`.** This is unreliable for large documents, can cause flash-of-old-content, and requires manual state cleanup (dirty flag, undo history, cursor position). The `key` approach is cleaner.

**Confidence:** HIGH -- `key` for remounting is standard React and TipTap best practice.

### Pattern 3: Editable Document Title

**What:** Title displayed as text, becomes an input on click, saves on blur or Enter.
**When to use:** UI-06 (click to rename).

```typescript
function EditableTitle({ documentId, title, rowVersion }: Props) {
  const [isEditing, setIsEditing] = useState(false)
  const [value, setValue] = useState(title)
  const inputRef = useRef<HTMLInputElement>(null)
  const renameMutation = useRenameDocument(scope, scopeId)

  // Sync external title changes
  useEffect(() => { setValue(title) }, [title])

  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing) inputRef.current?.select()
  }, [isEditing])

  const handleSave = () => {
    setIsEditing(false)
    if (value.trim() && value !== title) {
      renameMutation.mutate({ documentId, title: value.trim(), row_version: rowVersion })
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

**Note on `useRenameDocument` signature:** `useRenameDocument(scope: string, scopeId: string)` requires a non-null `scopeId`. The DocumentHeader must resolve the document's scope and scopeId from the Document object before calling this hook. Scope is derived from which FK is set: `project_id` -> 'project', `application_id` -> 'application', `user_id` -> 'personal'.

**Confidence:** HIGH -- standard inline-edit pattern, uses existing `useRenameDocument` hook.

### Pattern 4: Metadata Bar Layout

**What:** A horizontal bar below the title showing tags, scope badge, and "last edited by" info.
**When to use:** UI-07.

```typescript
function MetadataBar({ document }: { document: Document }) {
  return (
    <div className="flex items-center gap-3 px-6 py-2 border-b border-border text-sm text-muted-foreground">
      {/* Tags section */}
      <div className="flex items-center gap-1.5">
        <Tag className="h-3.5 w-3.5" />
        {document.tags.map(tag => (
          <span key={tag.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-muted text-xs">
            {tag.color && <span className="h-2 w-2 rounded-full" style={{ backgroundColor: tag.color }} />}
            {tag.name}
            <button onClick={() => removeTag(tag.id)} className="hover:text-destructive">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <TagAddButton onAddTag={addTag} />
      </div>

      <Separator orientation="vertical" className="h-4" />

      {/* Scope badge */}
      <span className="inline-flex items-center gap-1 text-xs">
        <FolderKanban className="h-3.5 w-3.5" />
        {scopeLabel}
      </span>

      <Separator orientation="vertical" className="h-4" />

      {/* Last edited by */}
      <span className="text-xs">
        Last edited by {lastEditorName} {relativeTime}
      </span>
    </div>
  )
}
```

**Note on "last edited by" data:** The current `Document` model has `created_by` but NO `updated_by` field. Phase 4's auto-save endpoint adds `updated_by` to the model as part of the save pipeline (see Phase 4 RESEARCH.md code example where `doc.updated_by = current_user.id`). Phase 6 depends on Phase 4, so this field will exist. However, the `DocumentResponse` schema must also include `updated_by` and ideally `updated_by_name` (or a nested user object). If Phase 4 does not add `updated_by_name`, Phase 6 should display the user ID or fetch user info separately. This is flagged as an open question.

**Confidence:** MEDIUM -- layout pattern is standard, but dependency on `updated_by` field availability needs validation.

### Pattern 5: Tab Dirty Indicator Integration with Auto-Save

**What:** The tab's dirty dot syncs with Phase 4's auto-save `isDirty()` state.
**When to use:** UI-04 (unsaved changes dot indicator).

```typescript
// In the document panel component that wraps the editor:
function ActiveDocumentView({ documentId }: Props) {
  const { setTabDirty } = useKnowledgeBase()
  const { isDirty, saveStatus } = useAutoSave(documentId, editor)

  // Sync dirty state to tab bar
  useEffect(() => {
    setTabDirty(documentId, isDirty())
  }, [documentId, isDirty, setTabDirty])

  // Also clear dirty on successful save
  useEffect(() => {
    if (saveStatus.state === 'saved') {
      setTabDirty(documentId, false)
    }
  }, [saveStatus, documentId, setTabDirty])
}
```

**The tab dirty indicator is a visual dot/circle on the tab item:**
```typescript
// In document-tab-item.tsx:
{isDirty && (
  <span className="h-2 w-2 rounded-full bg-amber-500" title="Unsaved changes" />
)}
```

**Confidence:** HIGH -- straightforward state sync between auto-save hook and tab context.

### Pattern 6: Status Bar with Word Count and Last Saved

**What:** A bottom bar showing word count (from CharacterCount extension) and last saved timestamp.
**When to use:** UI-09 and UI-14.

```typescript
function DocumentStatusBar({ editor, saveStatus }: Props) {
  // Word count from TipTap CharacterCount extension (Phase 3)
  const { wordCount } = useEditorState({
    editor,
    selector: (ctx) => ({
      wordCount: ctx.editor.storage.characterCount?.words() ?? 0,
    }),
  })

  // Last saved time
  const lastSavedText = useMemo(() => {
    if (saveStatus.state === 'saving') return 'Saving...'
    if (saveStatus.state === 'error') return 'Save failed'
    if (saveStatus.state === 'saved') return `Saved ${formatRelativeTime(saveStatus.at)}`
    return ''
  }, [saveStatus])

  return (
    <div className="flex items-center justify-between px-6 py-1.5 border-t border-border text-xs text-muted-foreground">
      <span>{wordCount.toLocaleString()} words</span>
      <span>{lastSavedText}</span>
    </div>
  )
}
```

**Note:** Phase 3 builds the word count extension (CharacterCount). Phase 4 builds the save status state machine. Phase 6 just displays both in the status bar. The status bar component receives these as props or accesses them via hooks.

**IMPORTANT: Existing EditorStatusBar duplication.** The current `document-editor.tsx` already renders an internal `EditorStatusBar` at the bottom of the editor that shows word and character counts. When Phase 6 adds a separate `DocumentStatusBar` component to the `DocumentPanel`, the editor's internal status bar MUST be removed (or the DocumentEditor refactored to accept an `showStatusBar?: boolean` prop) to avoid displaying two status bars. The Phase 6 `DocumentStatusBar` supersedes the internal one because it also shows "last saved" timestamp.

**Confidence:** HIGH -- uses existing infrastructure from Phases 3 and 4.

### Pattern 7: Notes Page Layout Composition

**What:** The final layout wiring in `NotesPage` that brings sidebar, tab bar, and document panel together.
**When to use:** Plan 06-03 (integration).

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
          {/* Top: document tab bar */}
          <DocumentTabBar />

          {/* Main: document panel (header + editor + status bar) */}
          <DocumentPanel />
        </div>
      </div>
    </KnowledgeBaseProvider>
  )
}
```

**Layout constraints:**
- `min-w-0` on the right panel prevents flex overflow when document title is very long
- The tab bar is outside DocumentPanel so it persists when switching tabs (no remount)
- DocumentPanel uses `key={activeTabId}` internally to remount editor per tab

**Confidence:** HIGH -- standard flex layout composition.

### Anti-Patterns to Avoid

- **Using Radix Tabs for the tab bar:** Radix Tabs is designed for content-panel switching (like a settings page with tabs). It does NOT support close buttons, dirty indicators, overflow scrolling, or drag-to-reorder. Build a custom tab bar.
- **Storing tab state in component-local state:** Tabs must persist across sidebar navigation, scope changes, and app restarts. Component state is lost on unmount. Use KnowledgeBaseContext with localStorage.
- **Using `editor.commands.setContent()` for tab switching:** Unreliable for large documents, leaves undo history from previous document, causes flash of content. Use `key={activeTabId}` to force remount.
- **Separate context for tab state:** Tab state (which document is active) IS the document selection state. Having two sources of truth (tabs and selectedDocumentId) causes sync bugs. Extend KnowledgeBaseContext instead.
- **Fetching document data inside the tab bar:** Tab items should only display cached titles (from the TabItem object). Full document fetch happens in DocumentPanel when a tab becomes active.
- **Storing the full Document object in tab state:** Only store `{ id, title, isDirty }` in tab state. Full document data lives in TanStack Query cache, fetched on-demand by `useDocument(activeTabId)`.
- **Not cleaning up editor on tab close:** When closing a tab, check if the document is dirty. If so, trigger a save before removing the tab. Use the same `saveNow()` function from Phase 4's `useAutoSave`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Relative time display | Manual Date math + setInterval | `useRelativeTime` from `@/lib/time-utils.ts` | Already exists, auto-updates every 60s |
| Document data fetching | Custom fetch in document panel | `useDocument(id)` from `@/hooks/use-documents.ts` | Already exists with caching, error handling, types |
| Document rename | Custom API call | `useRenameDocument(scope, scopeId)` from `@/hooks/use-documents.ts` | Already exists with cache invalidation |
| Word count | Manual text splitting | `CharacterCount` extension + `useEditorState` | Phase 3 installs this; reactive, handles ProseMirror structure |
| Save status | Custom polling | `useAutoSave` hook's `saveStatus` from Phase 4 | Phase 4 builds the complete save state machine |
| Tooltip on truncated tab titles | Custom hover state | `@radix-ui/react-tooltip` (already installed) | Accessible, positioned correctly, already styled |
| Tag display badges | Custom styled spans | Follow existing tag rendering in sidebar (`tag-filter-list.tsx`) | Consistent styling across the app |

**Key insight:** Phase 6 is an integration and UI composition phase. Almost all data hooks and editor infrastructure already exist from Phases 2-4. The primary work is UI component building and state management extension.

## Common Pitfalls

### Pitfall 1: Tab State and selectedDocumentId Out of Sync

**What goes wrong:** User clicks a document in the sidebar (sets `selectedDocumentId`) but the tab bar shows a different active tab. Or user clicks a tab but the sidebar selection doesn't update.
**Why it happens:** Two independent state fields (`selectedDocumentId` and `activeTabId`) that represent the same concept.
**How to avoid:** In the reducer, `OPEN_TAB` and `SET_ACTIVE_TAB` always set BOTH `activeTabId` and `selectedDocumentId`. The existing `SELECT_DOCUMENT` action should also trigger tab opening. These are not separate states -- `activeTabId === selectedDocumentId` is an invariant.
**Warning signs:** Sidebar highlights one document but editor shows another.

### Pitfall 2: Editor Content Flash on Tab Switch

**What goes wrong:** When switching tabs, the editor briefly shows the previous document's content before loading the new one.
**Why it happens:** If using `setContent()` instead of remounting, there's a render frame where old content is visible.
**How to avoid:** Use `key={activeTabId}` on the DocumentPanel to force full remount. The new editor instance initializes with the correct content from the start. Show a skeleton loader while `useDocument` is in `isLoading` state.
**Warning signs:** Brief flash of wrong content when clicking tabs quickly.

### Pitfall 3: Memory Leak from Multiple Editor Instances

**What goes wrong:** Opening many tabs creates many TipTap editor instances that consume memory even when not visible.
**Why it happens:** If the architecture mounts editors for all open tabs (hidden with CSS) instead of only the active tab.
**How to avoid:** Only mount ONE editor instance at a time -- the active tab's. Use `key={activeTabId}` to destroy the previous editor and create a new one. TipTap's `editor.destroy()` is called automatically on unmount. This means undo history is lost when switching tabs, which is acceptable (same as VS Code behavior).
**Warning signs:** Memory usage growing linearly with number of open tabs.

### Pitfall 4: Dirty Indicator Not Clearing After Save

**What goes wrong:** Tab shows the dirty dot even after auto-save succeeds.
**Why it happens:** The `isDirty` function compares current content against `lastSavedRef` which was set in the auto-save hook. But the tab's `isDirty` flag in context was set separately and not updated.
**How to avoid:** Use a `useEffect` that watches `saveStatus.state === 'saved'` and dispatches `SET_TAB_DIRTY(false)`. Or better: derive the dirty indicator from the auto-save hook's state rather than storing it redundantly. The tab bar can query the current active tab's dirty state from the auto-save hook.
**Warning signs:** Permanent dirty dots on tabs even after seeing "Saved".

### Pitfall 5: Closing Dirty Tab Without Saving

**What goes wrong:** User closes a tab with unsaved changes. Changes are lost.
**Why it happens:** Tab close action removes the tab without checking dirty state.
**How to avoid:** Before closing a dirty tab, trigger `saveNow()` from the auto-save hook. Two approaches:
1. **Optimistic (recommended):** Save in background, close tab immediately. The save continues even after the tab is closed because the mutation is in-flight. User doesn't wait.
2. **Confirm dialog:** Show "Unsaved changes. Save before closing?" -- but this is heavyweight and annoying for auto-saving editors.
**Warning signs:** Users losing work when rapidly closing tabs.

### Pitfall 6: Tab Title Stale After Rename

**What goes wrong:** User renames a document via the editable title. The tab still shows the old title.
**Why it happens:** Tab title is stored in context (`TabItem.title`) and not updated when the rename mutation succeeds.
**How to avoid:** In the rename mutation's `onSuccess`, dispatch `UPDATE_TAB_TITLE` to update the tab's cached title. Also, when `useDocument` returns fresh data, update the tab title if it differs.
**Warning signs:** Tab shows "Untitled" while the header shows the renamed title.

### Pitfall 7: No `updated_by` Field for "Last Edited By"

**What goes wrong:** Metadata bar needs to show who last edited the document, but the Document model has no `updated_by` field.
**Why it happens:** Phase 1 only created `created_by`. Phase 4 research mentions adding `updated_by` in the auto-save endpoint but it's not yet part of the schema.
**How to avoid:** Phase 6 depends on Phase 4. The auto-save endpoint (Phase 4, plan 04-01) should add `updated_by` to the Document model and DocumentResponse schema. If this field is not present at Phase 6 execution time, fall back to `created_by` with a "Created by" label instead of "Last edited by".
**Warning signs:** Metadata bar shows "Last edited by: Unknown" for all documents.

### Pitfall 8: Sidebar Document Click Needs Title for Tab Opening

**What goes wrong:** Clicking a document in the folder tree should open a tab, but the `handleSelectDocument` callback in `folder-tree.tsx` only has `documentId` (from `DocumentListItem`), and `openTab` needs both `documentId` and `title`.
**Why it happens:** The current `handleSelectDocument` callback passes only `documentId` via `selectDocument(documentId)`. It does not call `openTab`.
**How to avoid:** The `FolderTree` component has access to `DocumentListItem` objects which include `title`. The `renderDocumentItem` callback receives the full `doc: DocumentListItem` object. Update `handleSelectDocument` to accept both `documentId` and `title`, or change the `onSelect` callback in `renderDocumentItem` to call `openTab(doc.id, doc.title)` instead of `selectDocument(doc.id)`. The `handleNewDocument` callback (line 174) also calls `selectDocument(data.id)` after creating a new document -- this should also call `openTab(data.id, data.title)`.
**Warning signs:** Documents open in the editor but no tab appears in the tab bar.

### Pitfall 9: Tag Add/Remove Requires Backend Integration

**What goes wrong:** Metadata bar has tag add/remove UI but no mutation hooks exist for tag assignment.
**Why it happens:** Phase 1 created the tag assignment API endpoints but the frontend hooks (`use-document-tags.ts`) only have a read hook (`useDocumentTags`), not mutation hooks for assigning/unassigning tags to documents.
**How to avoid:** Phase 6 plan 06-02 must create `useAssignDocumentTag` and `useUnassignDocumentTag` mutation hooks. The backend API endpoints are: POST `/api/documents/{document_id}/tags` with body `{ tag_id: UUID }` (returns 201 with TagAssignmentResponse) and DELETE `/api/documents/{document_id}/tags/{tag_id}` (returns 204 no content).
**Warning signs:** Tag add/remove buttons do nothing or error.

## Code Examples

### KnowledgeBaseContext Extension (Tab State)

```typescript
// New types for tab management
interface TabItem {
  id: string       // document ID
  title: string    // display title
  isDirty: boolean // unsaved changes
}

// Added to KnowledgeBaseUIState:
openTabs: TabItem[]
activeTabId: string | null

// Persistence (localStorage keys):
const STORAGE_KEY_TABS = 'kb-open-tabs'
const STORAGE_KEY_ACTIVE_TAB = 'kb-active-tab'

// New reducer actions:
case 'OPEN_TAB': {
  const exists = state.openTabs.find(t => t.id === action.documentId)
  if (exists) {
    return {
      ...state,
      activeTabId: action.documentId,
      selectedDocumentId: action.documentId,
    }
  }
  return {
    ...state,
    openTabs: [...state.openTabs, { id: action.documentId, title: action.title, isDirty: false }],
    activeTabId: action.documentId,
    selectedDocumentId: action.documentId,
  }
}

case 'CLOSE_TAB': {
  const idx = state.openTabs.findIndex(t => t.id === action.documentId)
  const newTabs = state.openTabs.filter(t => t.id !== action.documentId)
  let newActiveId = state.activeTabId

  if (state.activeTabId === action.documentId) {
    // Activate adjacent tab (prefer right, then left)
    if (newTabs.length === 0) {
      newActiveId = null
    } else if (idx < newTabs.length) {
      newActiveId = newTabs[idx].id
    } else {
      newActiveId = newTabs[newTabs.length - 1].id
    }
  }

  return {
    ...state,
    openTabs: newTabs,
    activeTabId: newActiveId,
    selectedDocumentId: newActiveId,
  }
}

// IMPORTANT: Modify existing SELECT_DOCUMENT to also open a tab:
case 'SELECT_DOCUMENT': {
  if (!action.documentId) {
    return { ...state, selectedDocumentId: null }
  }
  const exists = state.openTabs.find(t => t.id === action.documentId)
  if (exists) {
    return {
      ...state,
      selectedDocumentId: action.documentId,
      activeTabId: action.documentId,
    }
  }
  // Need title -- but reducer shouldn't fetch data.
  // Solution: The component that dispatches SELECT_DOCUMENT should also dispatch OPEN_TAB with the title.
  // OR: SELECT_DOCUMENT only sets selection; a useEffect in the panel opens the tab.
  return {
    ...state,
    selectedDocumentId: action.documentId,
    activeTabId: action.documentId,
  }
}
```

### Document Tab Bar Component

```typescript
// document-tab-bar.tsx
function DocumentTabBar() {
  const { openTabs, activeTabId, setActiveTab, closeTab } = useKnowledgeBase()

  if (openTabs.length === 0) return null

  return (
    <div className="flex items-center border-b border-border bg-muted/30 overflow-x-auto">
      {openTabs.map(tab => (
        <DocumentTabItem
          key={tab.id}
          tab={tab}
          isActive={tab.id === activeTabId}
          onActivate={() => setActiveTab(tab.id)}
          onClose={() => closeTab(tab.id)}
        />
      ))}
    </div>
  )
}
```

### Document Tab Item Component

```typescript
// document-tab-item.tsx
function DocumentTabItem({ tab, isActive, onActivate, onClose }: Props) {
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
            // Middle-click to close
            if (e.button === 1) {
              e.preventDefault()
              onClose()
            }
          }}
        >
          <FileText className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate flex-1">{tab.title || 'Untitled'}</span>

          {/* Dirty indicator or close button */}
          <div className="shrink-0 w-4 h-4 flex items-center justify-center">
            {tab.isDirty ? (
              <span
                className="h-2 w-2 rounded-full bg-amber-500 group-hover:hidden"
                title="Unsaved changes"
              />
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

### Status Bar Component

```typescript
// document-status-bar.tsx
import { useEditorState } from '@tiptap/react'
import { useRelativeTime } from '@/lib/time-utils'
import type { Editor } from '@tiptap/react'

interface DocumentStatusBarProps {
  editor: Editor | null
  saveStatus: SaveStatus
  lastSavedAt?: string | null  // ISO date from document.updated_at
}

function DocumentStatusBar({ editor, saveStatus, lastSavedAt }: DocumentStatusBarProps) {
  const { wordCount } = useEditorState({
    editor,
    selector: (ctx) => ({
      wordCount: ctx.editor?.storage.characterCount?.words() ?? 0,
    }),
  })

  const savedTimeText = useRelativeTime(lastSavedAt)

  const statusText = useMemo(() => {
    switch (saveStatus.state) {
      case 'saving': return 'Saving...'
      case 'error': return 'Save failed'
      case 'saved': return `Last saved ${savedTimeText}`
      default: return lastSavedAt ? `Last saved ${savedTimeText}` : ''
    }
  }, [saveStatus, savedTimeText, lastSavedAt])

  return (
    <div className="flex items-center justify-between px-6 py-1.5 border-t border-border text-xs text-muted-foreground">
      <span>{wordCount.toLocaleString()} words</span>
      <span>{statusText}</span>
    </div>
  )
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single document view (no tabs) | Browser-style tabs with dirty indicators | Phase 6 | Users can work with multiple documents simultaneously |
| Placeholder main area | Full editor integration with header + metadata + status bar | Phase 6 | Complete document editing experience |
| selectedDocumentId only | openTabs[] + activeTabId (unified with selectedDocumentId) | Phase 6 | Tab state persists across navigation and restarts |
| No inline title editing | Click-to-rename with optimistic save | Phase 6 | Faster document renaming without dialogs |

**Deprecated/outdated:**
- The current Notes page placeholder (`<FileText /> Select a document...`) will be replaced entirely
- `selectedDocumentId` alone will no longer drive the content area -- `activeTabId` takes over, with `selectedDocumentId` kept in sync as an invariant

## Open Questions

1. **`updated_by` and `updated_by_name` in Document API response**
   - What we know: The Document model (Phase 1) has `created_by` but no `updated_by`. Phase 4 research shows the auto-save endpoint will set `updated_by = current_user.id`. The `DocumentResponse` schema currently has no `updated_by` field.
   - What's unclear: Whether Phase 4 adds `updated_by_name` to the response (a joined user display name) or just the UUID. If only UUID, Phase 6 would need a separate user lookup to display "Last edited by [Name]".
   - Recommendation: Phase 4 should add both `updated_by: UUID` and `updated_by_name: str | null` to `DocumentResponse`. If unavailable at Phase 6 execution, fall back to `created_by` with "Created by" label. Flag this as a cross-phase dependency.

2. **Tag assignment mutation hooks**
   - What we know: Phase 1 created backend endpoints for tag assignment: POST `/api/documents/{document_id}/tags` with `{ tag_id }` body (returns 201) and DELETE `/api/documents/{document_id}/tags/{tag_id}` (returns 204). The frontend `use-document-tags.ts` only has `useDocumentTags` (read hook), no mutation hooks.
   - What's unclear: Whether tag add/remove should happen inline in the metadata bar (small popover) or in a dialog.
   - Recommendation: Inline popover is the modern standard (GitHub labels, Notion tags, Linear labels). Build `useAssignDocumentTag` and `useUnassignDocumentTag` mutation hooks in Phase 6 and a compact tag picker popover.

3. **Tab close behavior for dirty documents**
   - What we know: Phase 4 auto-saves every 10 seconds of inactivity. IndexedDB drafts persist every 2 seconds.
   - What's unclear: Whether to show a confirmation dialog when closing a dirty tab, or silently trigger a save.
   - Recommendation: Silently trigger `saveNow()` and close immediately (optimistic). The auto-save mutation will complete in the background. If it fails, the IndexedDB draft from Phase 4 provides recovery. A confirmation dialog is unnecessary with auto-save. This matches Google Docs and Notion behavior.

4. **Maximum number of open tabs**
   - What we know: Browser tab bars work well up to ~15-20 tabs. Beyond that, they become unusable.
   - What's unclear: Whether to impose a limit or let tabs overflow with scrolling.
   - Recommendation: Allow unlimited tabs with horizontal scroll (using `overflow-x-auto`). Do NOT limit. Users can close tabs they don't need. This matches VS Code and browser behavior. Consider adding a "Close other tabs" context menu option.

## Sources

### Primary (HIGH confidence)
- Codebase: `electron-app/src/renderer/contexts/knowledge-base-context.tsx` -- existing useReducer pattern, state shape, localStorage persistence, all action types
- Codebase: `electron-app/src/renderer/pages/notes/index.tsx` -- current Notes page layout with placeholder content area
- Codebase: `electron-app/src/renderer/components/knowledge/knowledge-sidebar.tsx` -- sidebar component structure
- Codebase: `electron-app/src/renderer/hooks/use-documents.ts` -- `useDocument`, `useRenameDocument` hooks, `Document` type with all fields
- Codebase: `electron-app/src/renderer/hooks/use-document-tags.ts` -- `useDocumentTags` read hook (no mutation hooks)
- Codebase: `electron-app/src/renderer/components/knowledge/editor-types.ts` -- `DocumentEditorProps` interface
- Codebase: `electron-app/src/renderer/components/knowledge/editor-extensions.ts` -- CharacterCount extension included
- Codebase: `electron-app/src/renderer/lib/time-utils.ts` -- `useRelativeTime`, `formatRelativeTime`, `formatAbsoluteTime`
- Codebase: `electron-app/package.json` -- `@radix-ui/react-tabs` v1.1.0 installed (but no UI wrapper)
- Codebase: `fastapi-backend/app/models/document.py` -- Document model (no `updated_by` field)
- Codebase: `fastapi-backend/app/schemas/document.py` -- `DocumentResponse` schema (no `updated_by` field)
- `.planning/phases/02-notes-screen-shell-folder-navigation/02-RESEARCH.md` -- Phase 2 architecture patterns, KnowledgeBaseContext design
- `.planning/phases/03-rich-text-editor-core/03-RESEARCH.md` -- Editor component architecture, CharacterCount usage, useEditorState
- `.planning/phases/04-auto-save-content-pipeline/04-RESEARCH.md` -- Auto-save hook API (isDirty, saveNow, saveStatus), SaveStatus type
- `.planning/phases/05-document-locking/05-RESEARCH.md` -- Lock banner component pattern (relevant for editor area layout)

### Secondary (MEDIUM confidence)
- Tab bar UX patterns -- based on standard browser/VS Code/Notion tab behavior; no single authoritative source
- Tag picker popover pattern -- based on GitHub/Linear label pickers; standard UI pattern

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed, no new dependencies
- Architecture: HIGH -- patterns directly derived from existing KnowledgeBaseContext + component patterns in codebase
- Tab state design: HIGH -- extends proven useReducer pattern with standard browser tab semantics
- Integration with Phases 3-4: MEDIUM -- depends on interfaces not yet implemented (useAutoSave, CharacterCount, updated_by field). Documented as dependencies.
- Pitfalls: HIGH -- identified from real codebase analysis (missing updated_by, missing tag mutations, state sync requirements)

**Research date:** 2026-01-31
**Valid until:** 2026-03-01 (stable domain -- React UI patterns unlikely to change)

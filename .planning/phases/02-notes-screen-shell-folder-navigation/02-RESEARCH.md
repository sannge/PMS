# Phase 2: Notes Screen Shell & Folder Navigation - Research

**Researched:** 2026-01-31
**Domain:** React UI (folder tree, sidebar layout, context menus, scope filters), TanStack Query hooks with IndexedDB persistence, React Context for UI state
**Confidence:** HIGH

## Summary

Phase 2 builds the Notes screen shell: a sidebar with folder tree, search bar, tag list, and scope filter, plus TanStack Query hooks for documents and folders with IndexedDB caching for instant loads. This is a purely frontend phase (Phase 1 delivers all backend APIs).

The codebase has a mature TanStack Query + IndexedDB persistence infrastructure that Phase 2 plugs into. The per-query-persister already handles compression, LRU eviction, progressive hydration, and debounced writes. New query hooks for documents and folders automatically get IndexedDB persistence by using the existing `subscribeToQueryCache` subscription. The only configuration needed is adding folder/document query key prefixes to `HYDRATION_PRIORITY` in `cache-config.ts` so folder trees load during the deferred hydration phase (not on-demand).

The existing Notes page (`pages/notes/index.tsx`) will be completely rewritten. It currently depends on the old notes-context.tsx (being removed in Phase 1) and uses application-scoped notes only. The new Notes screen needs multi-scope support (All / My Notes / Application / Project), a folder tree with context menus, and a tag filter section.

**Primary recommendation:** Build three new TanStack Query hook files (`use-documents.ts`, `use-document-folders.ts`, `use-document-tags.ts`), a `KnowledgeBaseContext` for UI-only state (selected scope, expanded folders, sidebar collapsed), and a complete rewrite of the Notes page with sidebar sections. Use the existing custom context menu pattern (positioned div with backdrop) rather than installing `@radix-ui/react-context-menu`.

## Standard Stack

### Core (Already in Codebase)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @tanstack/react-query | ^5.90 | Server state for documents, folders, tags | Already used for all data domains |
| React Context (useReducer) | 18.3 | UI-only state (selected scope, expanded nodes) | Already used for auth, notification-ui |
| idb | ^8.0.1 | IndexedDB access (via existing per-query-persister) | Already powers query cache |
| @radix-ui/react-dropdown-menu | ^2.1.1 | Context menu actions | Already installed and used |
| @radix-ui/react-scroll-area | ^1.1.0 | Scrollable sidebar | Already installed and used |
| @radix-ui/react-separator | ^1.1.0 | Visual dividers | Already installed and used |
| @radix-ui/react-tooltip | ^1.1.2 | Tooltips on collapsed sidebar | Already installed and used |
| @radix-ui/react-select | ^2.1.1 | Scope dropdown selector | Already installed |
| @radix-ui/react-accordion | ^1.2.0 | Sidebar collapsible sections | Already installed |
| lucide-react | ^0.400 | Icons | Already used throughout UI |
| react-virtuoso | ^4.10.0 | Virtualized lists (for large tag/doc lists) | Already installed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tailwindcss-animate | ^1.0.7 | Entry animations (fade-in, zoom-in) | Already used for menu animations |
| lz-string | ^1.5.0 | Compression (via persister) | Automatically applied to cached queries |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom context menu (positioned div) | @radix-ui/react-context-menu | Radix context-menu is NOT installed. The existing notes-sidebar already implements a custom context menu with position tracking. **Recommendation: Continue custom pattern** -- avoids adding a dependency for a simple positioned menu. |
| Radix Select for scope filter | Custom dropdown | Radix Select already installed, provides keyboard navigation and accessibility. **Use Radix Select.** |
| React Context for expanded folders | localStorage only | Context provides reactive re-rendering when folders expand/collapse. LocalStorage is used for persistence across sessions but Context drives the live state. **Use both: Context for live state, localStorage for persistence.** |

**Installation:** No new packages needed. Everything is already installed.

## Architecture Patterns

### Recommended Frontend Structure (New Files)

```
electron-app/src/renderer/
├── hooks/
│   ├── use-documents.ts          # TanStack Query hooks for documents
│   ├── use-document-folders.ts   # TanStack Query hooks for folders + tree
│   └── use-document-tags.ts      # TanStack Query hooks for tags
├── contexts/
│   └── knowledge-base-context.tsx  # UI-only state (scope, sidebar, expanded nodes)
├── pages/
│   └── notes/
│       └── index.tsx             # REWRITE: New Notes screen shell
└── components/
    └── knowledge/
        ├── knowledge-sidebar.tsx    # Main sidebar container (search + tree + tags)
        ├── folder-tree.tsx          # Recursive folder tree with expand/collapse
        ├── folder-tree-item.tsx     # Single folder/document node
        ├── folder-context-menu.tsx  # Right-click context menu
        ├── scope-filter.tsx         # Scope selector (All / My Notes / App / Project)
        ├── tag-filter-list.tsx      # Tag list with click-to-filter
        └── search-bar.tsx           # Search input with debounce
```

### Pattern 1: KnowledgeBaseContext for UI-Only State

**What:** A React Context that holds purely client-side UI state for the Notes screen. No server data -- that's all TanStack Query.
**When to use:** For state that doesn't come from the API but needs to be shared across multiple sidebar/content components.
**State shape:**

```typescript
interface KnowledgeBaseUIState {
  // Scope selection
  scope: 'all' | 'personal' | 'application' | 'project'
  scopeId: string | null  // application_id or project_id when scope is app/project

  // Sidebar state
  isSidebarCollapsed: boolean
  expandedFolderIds: Set<string>

  // Active selection
  selectedDocumentId: string | null
  selectedFolderId: string | null

  // Search
  searchQuery: string

  // Tag filter
  activeTagIds: string[]
}
```

**Why Context and not just local state:** The scope selection affects the folder tree query, the document list query, and the tag list query. Multiple components need to read and update it. Prop drilling through 4+ levels is worse than a targeted Context.

**Persistence:** `isSidebarCollapsed` and `expandedFolderIds` persist to localStorage (existing pattern from current notes page). `scope` and `scopeId` persist to localStorage to restore last-visited scope. `searchQuery` and `activeTagIds` are ephemeral.

**Confidence:** HIGH -- follows existing auth-context and notification-ui-context patterns.

### Pattern 2: TanStack Query Hooks with Automatic IndexedDB Caching

**What:** Standard TanStack Query hooks that get IndexedDB persistence for free via the existing per-query-persister subscription.
**How it works (existing infrastructure):**

1. `subscribeToQueryCache(queryClient)` in `query-client.ts` listens to ALL query cache events
2. When any query data updates, `persistQuery()` compresses and writes to IndexedDB (debounced 1s)
3. On app startup, `initializeHydration()` loads critical queries first, then deferred queries after 2s
4. New queries are automatically persisted -- no per-hook configuration needed

**What Phase 2 needs to configure:**
- Add `'documentFolders'` to `HYDRATION_PRIORITY.deferred` (so folder tree loads during deferred hydration)
- Add `'documents'`, `'documentTags'` to `HYDRATION_PRIORITY.onDemand` (loaded when Notes screen opens)
- Add corresponding query keys to `queryKeys` in `query-client.ts`

**Critical pattern for "instant load from cache, refresh in background":**

```typescript
// Source: Existing query-client.ts pattern
export function useFolderTree(scope: string, scopeId: string | undefined) {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.documentFolders(scope, scopeId || ''),
    queryFn: async () => {
      // Fetch from server
      const response = await window.electronAPI.get(
        `/api/document-folders/tree?scope=${scope}&scope_id=${scopeId}`,
        { Authorization: `Bearer ${token}` }
      )
      if (response.status !== 200) throw new Error('Failed to fetch folder tree')
      return response.data
    },
    enabled: !!token && !!scopeId,
    staleTime: 30 * 1000,      // Fresh for 30s (no refetch if navigating back quickly)
    gcTime: 24 * 60 * 60 * 1000, // Keep in memory for 24h
    // IndexedDB persistence is automatic via subscribeToQueryCache
    // On next app open:
    // 1. Hydration loads cached data into query cache
    // 2. Component renders immediately with cached data
    // 3. TanStack Query detects stale data and refetches in background
    // 4. Component re-renders with fresh data (no loading spinner)
  })
}
```

**The "no loading spinner on repeat visits" requirement (CACHE-03) is satisfied by:**
1. Per-query-persister writes folder tree to IndexedDB on first load
2. Progressive hydration restores it on next app startup (deferred phase, 2s after critical)
3. `useQuery` finds hydrated data in cache, renders immediately
4. `staleTime` check triggers background refetch
5. Result: cached data shown instantly, fresh data replaces it silently

**Confidence:** HIGH -- this is exactly how the existing infrastructure works. Confirmed by reading per-query-persister.ts, cache-config.ts, and query-client.ts.

### Pattern 3: Custom Context Menu (Right-Click)

**What:** A positioned div that appears on right-click, using the same pattern as the existing notes-sidebar.tsx.
**Key implementation details (from existing code):**

```typescript
// Track context menu state per tree item
const [showContextMenu, setShowContextMenu] = useState(false)
const [contextMenuPosition, setContextMenuPosition] = useState({ x: 0, y: 0 })

// On right-click
const handleContextMenu = (e: React.MouseEvent) => {
  e.preventDefault()
  e.stopPropagation()
  setContextMenuPosition({ x: e.clientX, y: e.clientY })
  setShowContextMenu(true)
}

// Menu is a fixed-position div with backdrop
<div className="fixed inset-0 z-50" onClick={onClose} />
<div
  className="fixed z-50 min-w-[160px] rounded-md border border-border bg-popover p-1 shadow-md"
  style={{ top: position.y, left: position.x }}
>
  {/* Menu items */}
</div>
```

**Menu items for folder context menu:** New Folder, New Document, Rename, Move (submenu), Delete
**Menu items for document context menu:** Rename, Move (submenu), Delete

**Confidence:** HIGH -- directly observed in existing notes-sidebar.tsx.

### Pattern 4: Scope-Based Query Key Structure

**What:** Query keys that incorporate scope so different scopes have separate cache entries.
**Design:**

```typescript
// In query-client.ts queryKeys:
documentFolders: (scope: string, scopeId: string) =>
  ['documentFolders', scope, scopeId] as const,
documents: (scope: string, scopeId: string) =>
  ['documents', scope, scopeId] as const,
document: (id: string) => ['document', id] as const,
documentTags: (scope: string, scopeId: string) =>
  ['documentTags', scope, scopeId] as const,
```

This means switching from "Application A" to "Application B" creates separate cached entries. Both are persisted to IndexedDB independently. Switching back to "Application A" loads its cached tree instantly.

**Confidence:** HIGH -- follows existing queryKeys pattern.

### Pattern 5: State-Based Navigation (NOT React Router)

**What:** The app uses state-based routing. DashboardPage manages a `currentView` state that switches between pages. The Notes screen is rendered when the user clicks "Notes" in the main sidebar.
**Key constraint:** There is no URL-based routing. The Notes page receives props from DashboardPage (like `applicationId`). Navigation within the Notes screen (selecting folders, documents) is managed by the KnowledgeBaseContext and component-local state.

**How DashboardPage renders NotesPage (current pattern):**

```typescript
// In dashboard.tsx switch(currentView):
case 'notes':
  return <NotesPage applicationId={selectedApplicationId} />
```

**The new NotesPage should:**
1. Accept optional `applicationId` prop (for "open notes in this app" navigation)
2. Manage its own scope selection internally (via KnowledgeBaseContext)
3. NOT depend on DashboardPage for scope/folder/document state

**Confidence:** HIGH -- directly observed in dashboard.tsx.

### Anti-Patterns to Avoid

- **Duplicating IndexedDB persistence logic in hooks:** The per-query-persister already handles all IndexedDB reads/writes. Do NOT add `idb-keyval` calls in hook files. Just use standard `useQuery` and the persistence is automatic.
- **Creating a "knowledge base store" with CRUD methods:** The old notes-context.tsx puts fetch/create/update/delete logic inside a Context. The established pattern is TanStack Query hooks in `hooks/` files. The Context should only hold UI state.
- **Loading spinner on cached folder tree:** The success criterion explicitly says "no loading spinner on repeat visits." Use `isLoading` (true only when no data) vs `isFetching` (true during background refetch). Show skeleton only when `isLoading && !data`, never when `isFetching && data`.
- **Fetching folder tree per-folder:** Phase 1 delivers a `GET /document-folders/tree?scope=...` endpoint that returns the FULL tree in one call. Do NOT make per-folder API calls.
- **Using Zustand for any state:** Zustand is fully removed from the codebase.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IndexedDB query caching | Custom IndexedDB read/write in hooks | Existing per-query-persister | Already handles compression, LRU, debouncing, hydration |
| Progressive hydration | Custom "load from cache first" logic | Existing initializeHydration + HYDRATION_PRIORITY config | Just add key prefixes to config |
| Optimistic folder CRUD | Manual state management after API calls | TanStack Query onMutate/onSettled | Built-in rollback, automatic refetch |
| Scrollable sidebar | Custom overflow handling | `<ScrollArea>` from @radix-ui/react-scroll-area | Already installed, styled, accessible |
| Dropdown for scope filter | Custom popover | `<Select>` from @radix-ui/react-select | Already installed, provides keyboard nav |
| Tree expand/collapse animation | Custom CSS transitions | `tailwindcss-animate` classes (`animate-in`, `fade-in`) | Already used in sidebar animations |
| Debounced search input | Custom setTimeout | `useDeferredValue` or simple useEffect with cleanup | React 18 built-in, no library needed |

**Key insight:** The entire caching infrastructure is already built and battle-tested. Phase 2's job is to create the right query hooks (which automatically get cached) and the right UI components. No new caching code is needed.

## Common Pitfalls

### Pitfall 1: Showing Loading Spinner When Cached Data Exists

**What goes wrong:** Using `isLoading` from useQuery shows a spinner every time the component mounts, even when IndexedDB has cached data.
**Why it happens:** `isLoading` is `true` when `status === 'pending'` AND there's no data. But if hydration restored data from IndexedDB, `isLoading` will be `false` even on first mount.
**How to avoid:**
```typescript
const { data, isLoading, isFetching } = useFolderTree(scope, scopeId)

// Show skeleton ONLY when truly loading (no cached data at all)
if (isLoading) return <FolderTreeSkeleton />

// Show tree immediately (cached or fresh)
return (
  <div>
    <FolderTree data={data} />
    {/* Optional: subtle indicator for background refresh */}
    {isFetching && <RefreshIndicator />}
  </div>
)
```
**Warning signs:** Users see a loading spinner every time they navigate to Notes, even when they've visited before.

### Pitfall 2: Context Menu Positioned Off-Screen

**What goes wrong:** Right-clicking near the bottom or right edge of the window positions the context menu partially off-screen.
**Why it happens:** The menu is positioned at `clientX/clientY` without boundary checking.
**How to avoid:** After setting position, check if the menu would overflow the viewport and adjust:
```typescript
const adjustPosition = (x: number, y: number, menuWidth: number, menuHeight: number) => {
  const maxX = window.innerWidth - menuWidth - 8
  const maxY = window.innerHeight - menuHeight - 8
  return {
    x: Math.min(x, maxX),
    y: Math.min(y, maxY),
  }
}
```
**Warning signs:** Context menu items clipped or invisible near screen edges.

### Pitfall 3: Scope Change Without Clearing Previous Selection

**What goes wrong:** User selects a document in Application A, switches scope to Application B, and the previously selected document ID is still in state -- causing a stale reference.
**Why it happens:** KnowledgeBaseContext selectedDocumentId persists across scope changes.
**How to avoid:** In the scope change handler, clear `selectedDocumentId`, `selectedFolderId`, and `activeTagIds`. Consider a `resetSelection` action dispatched on scope change.
**Warning signs:** "Document not found" errors or stale document displayed after scope switch.

### Pitfall 4: Forgetting to Handle Scope = "all" and "personal"

**What goes wrong:** Query hooks expect a `scopeId` but "All docs" and "My Notes" scopes don't have an entity ID.
**Why it happens:** The scope filter has four modes but the API has three scope types (application, project, user).
**How to avoid:** Map UI scope to API scope:
- "All docs" -> API call without scope filter (or separate endpoint listing all accessible docs)
- "My Notes" -> `scope=user&scope_id={currentUserId}`
- "Application X" -> `scope=application&scope_id={appId}`
- "Project Y" -> `scope=project&scope_id={projectId}`
**Warning signs:** Empty results when selecting "All docs" or "My Notes".

### Pitfall 5: Expanded Folders State Lost on Tree Refresh

**What goes wrong:** When the folder tree refetches from the server (background refresh), the expanded/collapsed state of folders is lost because the tree data was replaced.
**Why it happens:** If expanded state is derived from tree data rather than independently tracked.
**How to avoid:** Keep `expandedFolderIds: Set<string>` in KnowledgeBaseContext, independent of tree data. The tree component reads the set to determine which folders are expanded. Tree data refreshes don't affect the set.
**Warning signs:** All folders collapse every 30 seconds (when staleTime triggers refetch).

### Pitfall 6: Query Key Mismatch Between Hooks and Cache Config

**What goes wrong:** Query hooks use keys like `['documentFolders', scope, scopeId]` but `HYDRATION_PRIORITY.deferred` looks for `'documentFolders'` prefix. If the key structure changes, hydration breaks silently.
**Why it happens:** The prefix matching in `getEntriesByPrefixes` checks the first element of the query key array. If hooks use a different first element (e.g., `'folders'` instead of `'documentFolders'`), deferred hydration won't find them.
**How to avoid:** Define ALL query keys in `queryKeys` object in `query-client.ts`. Use the same first-element string in `HYDRATION_PRIORITY`. Test by checking `getCacheStats()` after first load.
**Warning signs:** Folder tree shows loading spinner on app restart instead of loading from cache.

## Code Examples

### Query Keys Extension (for query-client.ts)

```typescript
// Source: Existing queryKeys pattern in query-client.ts
// Add to the queryKeys object:

// Documents
documents: (scope: string, scopeId: string) => ['documents', scope, scopeId] as const,
document: (id: string) => ['document', id] as const,

// Document Folders
documentFolders: (scope: string, scopeId: string) => ['documentFolders', scope, scopeId] as const,

// Document Tags
documentTags: (scope: string, scopeId: string) => ['documentTags', scope, scopeId] as const,

// Document Search
documentSearch: (query: string, scope: string, scopeId: string) =>
  ['documentSearch', query, scope, scopeId] as const,
```

### Cache Config Update (for cache-config.ts)

```typescript
// Source: Existing HYDRATION_PRIORITY in cache-config.ts
export const HYDRATION_PRIORITY = {
  critical: ['applications', 'projects', 'myProjects', 'myTasks'] as const,

  // ADD documentFolders here -- folder trees should hydrate early
  deferred: ['notifications', 'appMembers', 'projectMembers', 'documentFolders'] as const,

  // ADD documents, documentTags here -- loaded when Notes screen opens
  onDemand: ['tasks', 'comments', 'checklists', 'attachments', 'invitations', 'documents', 'documentTags'] as const,
} as const
```

### Folder Tree Hook (use-document-folders.ts)

```typescript
// Source: Existing use-queries.ts pattern
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

export interface DocumentFolder {
  id: string
  name: string
  parent_id: string | null
  materialized_path: string
  depth: number
  sort_order: number
  application_id: string | null
  project_id: string | null
  user_id: string | null
  created_at: string
  updated_at: string
  document_count?: number
}

export interface FolderTreeNode extends DocumentFolder {
  children: FolderTreeNode[]
}

/**
 * Build tree structure from flat folder list using materialized_path.
 * The API returns folders sorted by materialized_path ASC, sort_order ASC.
 */
function buildFolderTree(folders: DocumentFolder[]): FolderTreeNode[] {
  const map = new Map<string, FolderTreeNode>()
  const roots: FolderTreeNode[] = []

  for (const folder of folders) {
    map.set(folder.id, { ...folder, children: [] })
  }

  for (const folder of folders) {
    const node = map.get(folder.id)!
    if (folder.parent_id && map.has(folder.parent_id)) {
      map.get(folder.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}

export function useFolderTree(
  scope: string | undefined,
  scopeId: string | undefined
) {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.documentFolders(scope || '', scopeId || ''),
    queryFn: async (): Promise<FolderTreeNode[]> => {
      if (!window.electronAPI) throw new Error('Electron API not available')

      const response = await window.electronAPI.get<DocumentFolder[]>(
        `/api/document-folders/tree?scope=${scope}&scope_id=${scopeId}`,
        { Authorization: `Bearer ${token}` }
      )

      if (response.status !== 200) {
        throw new Error('Failed to fetch folder tree')
      }

      return buildFolderTree(response.data || [])
    },
    enabled: !!token && !!scope && !!scopeId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    // Cached data from IndexedDB is automatically available via hydration
  })
}
```

### KnowledgeBaseContext (UI-only state)

```typescript
// Source: Follows existing auth-context.tsx and notification-ui-context.tsx patterns
import { createContext, useContext, useReducer, useCallback, useEffect, type ReactNode } from 'react'

type ScopeType = 'all' | 'personal' | 'application' | 'project'

interface KnowledgeBaseUIState {
  scope: ScopeType
  scopeId: string | null
  isSidebarCollapsed: boolean
  expandedFolderIds: Set<string>
  selectedDocumentId: string | null
  selectedFolderId: string | null
  searchQuery: string
  activeTagIds: string[]
}

// Actions
type KBAction =
  | { type: 'SET_SCOPE'; scope: ScopeType; scopeId: string | null }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_SIDEBAR_COLLAPSED'; collapsed: boolean }
  | { type: 'TOGGLE_FOLDER'; folderId: string }
  | { type: 'SELECT_DOCUMENT'; documentId: string | null }
  | { type: 'SELECT_FOLDER'; folderId: string | null }
  | { type: 'SET_SEARCH'; query: string }
  | { type: 'TOGGLE_TAG'; tagId: string }
  | { type: 'CLEAR_TAGS' }
  | { type: 'RESET_SELECTION' }

// Reducer handles all state transitions
// SET_SCOPE also clears selection (prevents stale references)
// TOGGLE_FOLDER adds/removes from expandedFolderIds set
```

### Sidebar Layout (knowledge-sidebar.tsx structure)

```typescript
// Source: Follows existing notes-sidebar.tsx and sidebar.tsx patterns
// Layout structure:
<div className={cn(
  'flex flex-col border-r border-border bg-sidebar',
  isSidebarCollapsed ? 'w-10' : 'w-64'
)}>
  {/* 1. Search Bar (UI-01) */}
  <div className="p-2 border-b border-border">
    <SearchBar />
  </div>

  {/* 2. Scope Filter (UI-10) */}
  <div className="px-2 py-1.5 border-b border-border">
    <ScopeFilter />
  </div>

  {/* 3. Folder Tree (UI-02) - main scrollable area */}
  <ScrollArea className="flex-1">
    <FolderTree />
    {/* Unfiled section */}
    <UnfiledDocuments />
  </ScrollArea>

  {/* 4. Tag List (UI-03) - bottom section */}
  <div className="border-t border-border">
    <TagFilterList />
  </div>
</div>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Application-only notes | Multi-scope documents (personal, app, project) | Phase 1 data model | All queries need scope parameters |
| Notes Context with fetch logic | TanStack Query hooks | Phase 1 migration | Hooks in hooks/ directory, no Context for server data |
| No caching (fetch on every mount) | IndexedDB persistence via per-query-persister | Already built in codebase | Folder tree loads instantly from cache |
| Flat note list | Hierarchical folder tree | Phase 1 data model | Tree component with recursive rendering |
| notes-store.ts (Zustand shim) | Direct Context imports | Phase 1 Zustand removal | No Zustand anywhere in codebase |

**Deprecated/outdated:**
- `notes-context.tsx`: Being removed in Phase 1 (Plan 01-01). Phase 2 must NOT depend on it.
- `stores/notes-store.ts`: Being removed in Phase 1 (Plan 01-02). Phase 2 imports from `@/contexts` only.
- `pages/notes/index.tsx`: Being removed in Phase 1 (Plan 01-01). Phase 2 creates a completely new file.
- `components/notes/*`: Being removed in Phase 1 (Plan 01-01). Phase 2 creates new components in `components/knowledge/`.

## Open Questions

1. **"All docs" scope API design**
   - What we know: The scope filter includes "All docs" which spans all scopes the user has access to. Individual scope queries are `GET /document-folders/tree?scope=X&scope_id=Y`.
   - What's unclear: Phase 1 research proposed flat URLs with scope params. It's unclear if there will be a `GET /document-folders/tree` endpoint without scope params that returns all accessible folders, or if the frontend should merge trees from multiple API calls.
   - Recommendation: Phase 1 should create a `GET /api/documents?scope=all` endpoint (or similar) that returns all documents accessible to the user. For the folder tree, "All docs" can show a grouped view (sections per application/project) rather than a merged tree. If Phase 1 doesn't deliver this, Phase 2 can display scope groups and fetch trees per-scope.

2. **Tag scope behavior**
   - What we know: Tags are scoped (Phase 1 research mentions application-scoped tags). The tag filter appears in the sidebar and filters the document list.
   - What's unclear: When scope is "All docs", which tags should appear? All tags from all applications? Just the most-used tags?
   - Recommendation: Show tags for the currently selected scope. For "All docs", show a merged deduplicated tag list from all accessible scopes. For "My Notes", show personal tags.

3. **Folder tree depth and performance**
   - What we know: Phase 1 research limits folder depth to 5 levels. The tree is fetched in a single API call per scope.
   - What's unclear: For very large folder trees (100+ folders), should the initial render show only root-level folders with lazy loading of children?
   - Recommendation: Render the full tree (already fetched in one call) but default-collapse all folders. For trees with 100+ items, consider virtualizing with react-virtuoso. Phase 1's max-depth-5 constraint keeps tree sizes manageable.

## Sources

### Primary (HIGH confidence)
- `electron-app/src/renderer/lib/per-query-persister.ts` -- IndexedDB caching infrastructure, progressive hydration
- `electron-app/src/renderer/lib/query-cache-db.ts` -- IndexedDB schema, operations
- `electron-app/src/renderer/lib/cache-config.ts` -- HYDRATION_PRIORITY configuration, NON_PERSISTENT_KEYS
- `electron-app/src/renderer/lib/query-client.ts` -- queryKeys pattern, queryClient defaults, persistence initialization
- `electron-app/src/renderer/hooks/use-queries.ts` -- TanStack Query hook patterns (useQuery, useMutation, staleTime, gcTime)
- `electron-app/src/renderer/App.tsx` -- Provider nesting, persistence initialization flow
- `electron-app/src/renderer/pages/notes/index.tsx` -- Current Notes page (being rewritten)
- `electron-app/src/renderer/components/notes/notes-sidebar.tsx` -- Custom context menu pattern
- `electron-app/src/renderer/contexts/notes-context.tsx` -- Old pattern to NOT follow
- `electron-app/src/renderer/pages/dashboard.tsx` -- State-based navigation pattern
- `electron-app/package.json` -- Dependency audit (all needed packages installed)
- `.planning/phases/01-migration-and-data-foundation/01-RESEARCH.md` -- Phase 1 decisions (API URLs, data model, patterns)

### Secondary (MEDIUM confidence)
- Scope filter UI design -- reasonable extrapolation from requirements, no mockup exists
- "All docs" merged view -- recommendation based on common patterns, not specified in requirements

### Tertiary (LOW confidence)
- None -- all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed, no new packages
- Architecture: HIGH -- patterns directly observed in existing codebase
- Caching: HIGH -- existing infrastructure verified by reading all four caching files
- Pitfalls: HIGH -- identified from actual code behavior and requirement analysis
- UI structure: MEDIUM -- reasonable component decomposition but no mockup to validate against

**Research date:** 2026-01-31
**Valid until:** 2026-03-01 (stable -- patterns unlikely to change)

# Phase 10: Embedded Docs & @ Mentions - Research

**Researched:** 2026-01-31
**Domain:** Frontend component composition (embedded views) + TipTap editor extension (@ mentions)
**Confidence:** HIGH

## Summary

Phase 10 has two distinct subdomains: (1) embedding the existing knowledge base experience (folder tree + editor) into Application and Project detail pages as a new "Docs" tab, and (2) building a TipTap @ mention extension that searches Applications and Projects with a suggestion popup and inserts navigable links.

The embedded docs feature is primarily a component composition task. The existing `KnowledgeBaseProvider`, `KnowledgeSidebar`, and editor infrastructure from Phases 2-6 provide all the building blocks. The main work is creating a reusable `EmbeddedDocsTab` component that wraps these existing components with a fixed scope (application or project), then adding tab navigation to the detail pages following the existing tab pattern (Projects/Archive tabs in `ApplicationDetailPage`).

The @ mention feature uses TipTap's built-in `@tiptap/extension-mention` (already installed at ^2.6.0) with the `@tiptap/suggestion` utility (already a transitive dependency at 2.27.2). The suggestion popup needs a React component for rendering results, positioned using the suggestion utility's `clientRect` prop with manual absolute positioning (no tippy.js needed -- the project doesn't use it). Application and project data for search is already cached client-side via TanStack Query (`useApplications`, `useProjects`), so the suggestion `items` function can query the cache synchronously with optional async fallback.

**Primary recommendation:** Build a reusable `EmbeddedDocsTab` component that accepts a fixed `scope` and `scopeId`, wrapping existing `KnowledgeBaseProvider` + sidebar + editor. For mentions, configure `@tiptap/extension-mention` with a custom suggestion that filters cached TanStack Query data and renders results via `ReactRenderer` from `@tiptap/react`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @tiptap/extension-mention | ^2.6.0 | @ mention node type | Already installed; official TipTap extension for inline mentions |
| @tiptap/suggestion | 2.27.2 | Autocomplete suggestion utility | Transitive dep of mention extension; provides trigger detection, keyboard nav, positioning |
| @tiptap/react | ^2.6.0 | ReactRenderer for suggestion popup | Already installed; bridges TipTap plugins with React components |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @tanstack/react-query | existing | Cached application/project data for mention search | Items callback queries the existing cache instead of hitting API |
| @radix-ui/react-popover | existing | Potential positioning utility | Not needed -- manual absolute positioning with clientRect is simpler for suggestion popups |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Client-side mention search | Backend /api/mentions/search endpoint | Client-side is sufficient because users only have access to a bounded set of applications/projects (typically <100). Backend search adds latency without benefit. |
| Manual popup positioning | tippy.js / @floating-ui/dom | Adds a dependency for a single popup. TipTap suggestion provides `clientRect` which is enough for simple absolute positioning. |
| Single Mention extension | Two separate Mention extensions (one for apps, one for projects) | Single extension with mixed results is simpler. Two extensions would need different trigger chars (e.g., @app vs @proj) which harms UX. |

**Installation:**
```bash
# No new packages needed -- all dependencies already installed
# @tiptap/extension-mention ^2.6.0 and @tiptap/suggestion (transitive) already in package.json
```

## Architecture Patterns

### Recommended Project Structure
```
electron-app/src/renderer/
├── components/
│   ├── knowledge/
│   │   ├── embedded-docs-tab.tsx    # NEW: Reusable embedded docs container
│   │   ├── mention-list.tsx         # NEW: Suggestion popup component
│   │   ├── mention-suggestion.ts    # NEW: Suggestion config (items, render, command)
│   │   ├── editor-extensions.ts     # MODIFY: Add Mention to extension factory
│   │   ├── knowledge-sidebar.tsx    # EXISTING: Reused as-is
│   │   └── folder-tree.tsx          # EXISTING: Reused as-is
│   └── ...
├── contexts/
│   └── knowledge-base-context.tsx   # EXISTING: Reused with fixed scope
├── pages/
│   ├── applications/[id].tsx        # MODIFY: Add "Docs" tab
│   └── projects/[id].tsx            # MODIFY: Add "Docs" tab
└── hooks/
    └── use-mention-search.ts        # NEW: Hook to search cached apps/projects
```

### Pattern 1: Embedded Docs Tab Component
**What:** A self-contained component that provides the full docs experience (sidebar + editor) scoped to a specific application or project.
**When to use:** Whenever we need to embed the docs UI inside another page (Application detail, Project detail).
**Example:**
```typescript
// Source: Codebase pattern from existing KnowledgeBaseProvider usage
interface EmbeddedDocsTabProps {
  scope: 'application' | 'project'
  scopeId: string
}

export function EmbeddedDocsTab({ scope, scopeId }: EmbeddedDocsTabProps) {
  return (
    <KnowledgeBaseProvider initialScope={scope} initialScopeId={scopeId}>
      <div className="flex h-full">
        <KnowledgeSidebar />
        <main className="flex-1 flex flex-col">
          {/* Editor area -- same as NotesPage but without scope filter */}
        </main>
      </div>
    </KnowledgeBaseProvider>
  )
}
```

### Pattern 2: Tab Navigation in Detail Pages
**What:** Adding a "Docs" tab alongside existing tabs (Projects/Archive in ApplicationDetailPage, Kanban in ProjectDetailPage) using the same tab pattern already established.
**When to use:** When extending detail pages with new content sections.
**Example:**
```typescript
// Source: Existing tab pattern from ApplicationDetailPage lines 862-897
// The Application detail page already has a Projects/Archive tab toggle.
// Add "Docs" as a third tab option.
const [activeTab, setActiveTab] = useState<'projects' | 'archive' | 'docs'>('projects')

// In JSX:
<button onClick={() => setActiveTab('docs')}
  className={cn(
    'relative px-3 py-2 text-xs font-medium transition-colors',
    activeTab === 'docs' ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
  )}>
  Docs
  {activeTab === 'docs' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
</button>

// Content area:
{activeTab === 'docs' && (
  <EmbeddedDocsTab scope="application" scopeId={applicationId} />
)}
```

### Pattern 3: TipTap Mention with ReactRenderer
**What:** Configuring the Mention extension with a suggestion object that uses ReactRenderer to mount a React component as the popup.
**When to use:** For the @ mention autocomplete popup in the document editor.
**Example:**
```typescript
// Source: TipTap official docs + GitHub discussion #2274
import { ReactRenderer } from '@tiptap/react'
import Mention from '@tiptap/extension-mention'
import type { MentionOptions } from '@tiptap/extension-mention'

const suggestion: MentionOptions['suggestion'] = {
  char: '@',
  items: ({ query }) => {
    // Search cached applications and projects
    return searchEntities(query).slice(0, 8)
  },
  render: () => {
    let component: ReactRenderer<MentionListRef>

    return {
      onStart: (props) => {
        component = new ReactRenderer(MentionList, {
          props,
          editor: props.editor,
        })
        // Position popup using props.clientRect
      },
      onUpdate: (props) => {
        component.updateProps(props)
      },
      onKeyDown: ({ event }) => {
        return component.ref?.onKeyDown({ event }) ?? false
      },
      onExit: () => {
        component.destroy()
      },
    }
  },
  command: ({ editor, range, props }) => {
    editor.chain().focus()
      .insertContentAt(range, [
        { type: 'mention', attrs: { id: props.id, label: props.label } },
        { type: 'text', text: ' ' },
      ])
      .run()
  },
}
```

### Pattern 4: Mention Node Rendered as Navigable Link
**What:** Configuring `renderHTML` on the Mention extension so that mention nodes render as clickable links that navigate to the referenced entity.
**When to use:** For making @ mentions function as navigation links in the document.
**Example:**
```typescript
// Source: TipTap Mention docs - renderHTML option
Mention.configure({
  renderHTML({ node, HTMLAttributes }) {
    return [
      'a',
      mergeAttributes(HTMLAttributes, {
        class: 'mention-link text-primary font-medium cursor-pointer hover:underline',
        'data-type': node.attrs.type,     // 'application' or 'project'
        'data-id': node.attrs.id,
        href: '#',                        // Prevent default, handle via click
      }),
      `@${node.attrs.label ?? node.attrs.id}`,
    ]
  },
  // Store entity type alongside id and label
  // Need to extend mention node attrs
})
```

### Pattern 5: Click Handler for Mention Navigation
**What:** Using editor event handlers or DOM click handlers to navigate when a user clicks a mention link.
**When to use:** For implementing the "navigable link" behavior of @ mentions.
**Example:**
```typescript
// Source: Codebase pattern from state-based routing in DashboardPage
// Since the project uses state-based routing (NOT react-router),
// mention clicks must bubble up via callback props to DashboardPage.

// Option A: Props drilling from editor -> page -> dashboard
interface DocumentEditorProps {
  onMentionClick?: (type: 'application' | 'project', id: string) => void
}

// Option B: Shared context for navigation commands
// The DashboardPage already manages navigation state.
// A mention click handler would call the same navigation functions.
```

### Anti-Patterns to Avoid
- **Duplicating the knowledge base UI**: Do NOT rebuild folder tree, editor, or sidebar for embedded docs. Reuse existing components with `KnowledgeBaseProvider` scoped appropriately.
- **Hiding the scope filter in embedded mode**: The embedded docs tab should NOT show the scope filter dropdown since the scope is fixed. The `KnowledgeSidebar` component or a variant should conditionally hide it.
- **Using separate TipTap Mention extensions for apps vs projects**: Use a single Mention extension with a `type` attribute to distinguish entity types. Multiple extensions would require different trigger characters, confusing users.
- **Backend search for mentions**: The user's accessible applications/projects are already loaded via TanStack Query. Client-side filtering is instantaneous and avoids network latency in the suggestion popup.
- **Using tippy.js just for the mention popup**: Adding a positioning library for a single popup is over-engineering. Use the `clientRect` from the suggestion utility + manual absolute positioning or a portal with calculated coords.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mention trigger detection | Custom keystroke detection for @ | `@tiptap/suggestion` utility | Handles edge cases: cursor position, query extraction, decoration, re-triggering after dismiss |
| Suggestion popup keyboard nav | Custom keyDown handlers | `@tiptap/suggestion` `onKeyDown` callback | Suggestion utility manages arrow keys, enter, escape for you |
| Mention node serialization | Custom ProseMirror node | `@tiptap/extension-mention` | Handles node spec, input rules, paste rules, JSON serialization |
| Popup positioning relative to cursor | Custom getBoundingClientRect | `props.clientRect()` from suggestion utility | Suggestion utility provides exact cursor position for popup placement |
| Tab state management | Custom tab context | Local `useState` in detail pages | Tabs are page-local UI state, not shared across components |

**Key insight:** TipTap's mention + suggestion utilities handle all the hard parts (trigger detection, query extraction, keyboard navigation, node serialization). The custom work is only the React popup component and the navigation click handler.

## Common Pitfalls

### Pitfall 1: Scope Bleed in Embedded Docs
**What goes wrong:** The `KnowledgeBaseProvider` persists scope to localStorage. If the embedded docs tab uses the same provider, switching tabs on the detail page could bleed the scope into the Notes screen.
**Why it happens:** The existing provider writes scope/scopeId to localStorage on change, and the Notes page reads from localStorage on init.
**How to avoid:** The embedded docs should use a separate `KnowledgeBaseProvider` instance with `initialScope` and `initialScopeId` props but should NOT persist to the same localStorage keys. Either: (a) pass a flag to disable persistence, (b) use different storage keys prefixed with the entity ID, or (c) make the provider skip persistence when scope is fixed.
**Warning signs:** Opening the Notes screen after viewing embedded docs shows the wrong scope.

### Pitfall 2: Mention Navigation Without Router
**What goes wrong:** Clicking a mention link tries to use `window.location` or a router, but the project uses state-based routing via DashboardPage callbacks.
**Why it happens:** Mentions are rendered as `<a>` elements with href, and the natural instinct is to make them real links.
**How to avoid:** Render mentions as styled `<span>` elements (not `<a>`), and handle clicks via a callback prop that propagates up to DashboardPage's navigation state. Alternatively, use `<a href="#" onClick={...}>` with `preventDefault`.
**Warning signs:** Clicking a mention causes a page reload or navigation error instead of switching to the referenced entity's detail page.

### Pitfall 3: Stale Mention Data After Entity Rename
**What goes wrong:** An @ mention stores the entity name as `label` at insertion time. If the application/project is later renamed, the mention text becomes stale.
**Why it happens:** Mention nodes are static once inserted -- they snapshot the label at creation time.
**How to avoid:** Accept this as expected behavior for v1. Mentions display the name at insertion time. Document this limitation. A future enhancement could resolve labels from IDs at render time, but that adds complexity (async rendering, loading states for every mention).
**Warning signs:** A renamed application still shows the old name in mentions across all documents.

### Pitfall 4: ReactRenderer Cleanup in Suggestion Popup
**What goes wrong:** The suggestion popup leaks DOM elements or React roots if `onExit` is not called (e.g., editor is destroyed while popup is open).
**Why it happens:** `ReactRenderer` creates a detached DOM element and React root. If `destroy()` is never called, the element persists.
**How to avoid:** Ensure `onExit` always calls `component.destroy()`. Additionally, handle editor `destroy` event to clean up any active suggestion popup. Consider using `useEffect` cleanup in the component that mounts the editor.
**Warning signs:** Memory leaks visible in DevTools; orphaned DOM nodes after switching documents.

### Pitfall 5: Mention Extension Conflicting with Link Extension
**What goes wrong:** Both Mention and Link extensions handle inline elements with click behavior, potentially causing event handler conflicts.
**Why it happens:** The Link extension is configured with `openOnClick: false` (good), but mention click handlers could bubble unexpectedly.
**How to avoid:** Configure mention `renderHTML` to NOT use `<a>` tags if Link extension is active. Use `<span>` with `data-*` attributes and handle clicks via editor click handler or delegated event listener.
**Warning signs:** Clicking a mention opens a link editing dialog, or link clicks trigger mention navigation.

### Pitfall 6: Project Detail Page Height Management
**What goes wrong:** The embedded docs tab (with sidebar + editor) doesn't fill the available height, resulting in a squished or scrollable layout.
**Why it happens:** The Project detail page uses `flex flex-col h-full` but the Kanban board has different height requirements than a docs panel.
**How to avoid:** Ensure the `EmbeddedDocsTab` uses `h-full` and `flex-1 min-h-0` to fill the available space. Test in both pages since they have different layout structures.
**Warning signs:** The editor area is tiny or has double scroll bars.

## Code Examples

Verified patterns from the existing codebase and official sources:

### Creating an Embedded Docs Tab
```typescript
// Based on: NotesPage (pages/notes/index.tsx) and KnowledgeBaseProvider pattern
import { KnowledgeBaseProvider } from '@/contexts/knowledge-base-context'
import { KnowledgeSidebar } from '@/components/knowledge/knowledge-sidebar'

interface EmbeddedDocsTabProps {
  scope: 'application' | 'project'
  scopeId: string
}

export function EmbeddedDocsTab({ scope, scopeId }: EmbeddedDocsTabProps) {
  // Fixed scope -- no scope filter shown, no localStorage persistence
  return (
    <KnowledgeBaseProvider
      initialScope={scope}
      initialScopeId={scopeId}
      // Phase 10 may need a new prop like `fixedScope={true}`
      // to prevent scope persistence and hide scope filter
    >
      <div className="flex h-full">
        <KnowledgeSidebar />
        <main className="flex-1 flex flex-col min-h-0">
          {/* Document content area from Phase 6 integration */}
        </main>
      </div>
    </KnowledgeBaseProvider>
  )
}
```

### Mention Extension Configuration
```typescript
// Based on: TipTap Mention docs + existing editor-extensions.ts pattern
import Mention from '@tiptap/extension-mention'
import { mergeAttributes } from '@tiptap/core'
import { mentionSuggestion } from './mention-suggestion'

// Add to createDocumentExtensions() in editor-extensions.ts
Mention.configure({
  HTMLAttributes: {
    class: 'mention-link',
  },
  renderHTML({ node, HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        class: 'text-primary font-medium cursor-pointer hover:underline',
        'data-mention-type': node.attrs.type,
        'data-mention-id': node.attrs.id,
      }),
      `@${node.attrs.label ?? node.attrs.id}`,
    ]
  },
  suggestion: mentionSuggestion,
})
```

### Mention Suggestion with Client-Side Search
```typescript
// Based on: TipTap suggestion utility + existing TanStack Query hooks
import { ReactRenderer } from '@tiptap/react'
import type { MentionOptions } from '@tiptap/extension-mention'
import { MentionList, type MentionListRef } from './mention-list'
import { QueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-client'

// Access to query client for reading cached data
let queryClientRef: QueryClient | null = null

export function setMentionQueryClient(client: QueryClient) {
  queryClientRef = client
}

interface MentionItem {
  id: string
  label: string
  type: 'application' | 'project'
}

export const mentionSuggestion: MentionOptions['suggestion'] = {
  char: '@',
  allowSpaces: false,

  items: ({ query }): MentionItem[] => {
    if (!queryClientRef) return []
    const lowerQuery = query.toLowerCase()

    // Read from TanStack Query cache (synchronous)
    const apps = queryClientRef.getQueryData<Array<{ id: string; name: string }>>(
      queryKeys.applications()
    ) ?? []

    const results: MentionItem[] = []

    // Add matching applications
    for (const app of apps) {
      if (app.name.toLowerCase().includes(lowerQuery)) {
        results.push({ id: app.id, label: app.name, type: 'application' })
      }
    }

    // Add matching projects from all cached application project lists
    // Projects are cached per application: queryKeys.projects(appId)
    for (const app of apps) {
      const projects = queryClientRef.getQueryData<Array<{ id: string; name: string }>>(
        queryKeys.projects(app.id)
      ) ?? []
      for (const proj of projects) {
        if (proj.name.toLowerCase().includes(lowerQuery)) {
          results.push({ id: proj.id, label: proj.name, type: 'project' })
        }
      }
    }

    return results.slice(0, 8)
  },

  render: () => {
    let component: ReactRenderer<MentionListRef>
    let popup: HTMLDivElement | null = null

    return {
      onStart: (props) => {
        component = new ReactRenderer(MentionList, {
          props,
          editor: props.editor,
        })

        popup = document.createElement('div')
        popup.style.position = 'absolute'
        popup.style.zIndex = '9999'
        popup.appendChild(component.element)
        document.body.appendChild(popup)

        const rect = props.clientRect?.()
        if (rect && popup) {
          popup.style.left = `${rect.left}px`
          popup.style.top = `${rect.bottom + 4}px`
        }
      },

      onUpdate: (props) => {
        component.updateProps(props)

        const rect = props.clientRect?.()
        if (rect && popup) {
          popup.style.left = `${rect.left}px`
          popup.style.top = `${rect.bottom + 4}px`
        }
      },

      onKeyDown: ({ event }) => {
        return component.ref?.onKeyDown({ event }) ?? false
      },

      onExit: () => {
        component.destroy()
        if (popup) {
          popup.remove()
          popup = null
        }
      },
    }
  },
}
```

### Tab Pattern from Existing Codebase
```typescript
// Source: ApplicationDetailPage lines 862-897 (existing tab pattern)
// This is the EXISTING tab toggle pattern in the application detail page:
<div className="flex items-center gap-1 border-b border-border">
  <button
    onClick={() => setShowArchive(false)}
    className={cn(
      'relative px-3 py-2 text-xs font-medium transition-colors',
      !showArchive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
    )}
  >
    Projects
    {!showArchive && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
  </button>
  <button
    onClick={() => setShowArchive(true)}
    className={cn(
      'relative flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
      showArchive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
    )}
  >
    Archive
    {showArchive && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
  </button>
</div>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| tippy.js for TipTap suggestion popups | Manual DOM positioning or ReactRenderer | TipTap 2.x era | tippy.js is no longer required; ReactRenderer + clientRect is the recommended pattern |
| Multiple Mention extensions per entity type | Single Mention with custom attrs | Standard practice | Simpler config, single trigger character |
| `@tiptap/suggestion` as separate install | Bundled as dependency of `@tiptap/extension-mention` | TipTap 2.x | No separate install needed |

**Deprecated/outdated:**
- tippy.js integration for TipTap suggestions: Still works but adds unnecessary dependency. Manual positioning with `clientRect` is simpler and sufficient.

## Open Questions

1. **Mention click navigation propagation**
   - What we know: The project uses state-based routing via DashboardPage. Mention clicks must eventually call `setActiveItem('applications')` + `setSelectedApplicationId(id)` or similar.
   - What's unclear: The cleanest way to propagate mention click events from deep inside the editor up to DashboardPage. Options are: (a) callback prop drilling, (b) a shared navigation context, (c) custom DOM event bubbling.
   - Recommendation: Use a callback prop on the editor component (`onMentionClick`) that each parent page forwards to DashboardPage's navigation handlers. This follows the existing pattern (e.g., `onSelectProject` in ApplicationDetailPage). A navigation context could be cleaner but would be new infrastructure.

2. **Mention node custom attributes (type field)**
   - What we know: The default Mention node stores `id` and `label`. We need a `type` attribute ('application' | 'project') to distinguish entity types.
   - What's unclear: Whether extending the Mention node's attrs requires extending the extension itself or just passing extra attrs via the command.
   - Recommendation: Extend the Mention extension using `.extend()` to add a `type` attribute to the node spec. This is the documented way to add custom attrs to TipTap nodes.

3. **Embedded docs sidebar variant**
   - What we know: The existing `KnowledgeSidebar` includes a scope filter dropdown that should be hidden in embedded mode (scope is fixed).
   - What's unclear: Whether to create a separate sidebar component or add a prop to conditionally hide the scope filter.
   - Recommendation: Add an `embedded` boolean prop (or `hideScope` prop) to `KnowledgeSidebar` that conditionally hides the scope filter section. Simpler than creating a new component.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `electron-app/src/renderer/pages/applications/[id].tsx` -- Tab pattern, detail page structure
- Existing codebase: `electron-app/src/renderer/pages/projects/[id].tsx` -- Project detail page structure
- Existing codebase: `electron-app/src/renderer/contexts/knowledge-base-context.tsx` -- Provider API, scope management
- Existing codebase: `electron-app/src/renderer/components/knowledge/editor-extensions.ts` -- TipTap extension factory
- Existing codebase: `electron-app/src/renderer/components/knowledge/knowledge-sidebar.tsx` -- Sidebar composition
- Existing codebase: `electron-app/src/renderer/pages/notes/index.tsx` -- Notes page layout
- Existing codebase: `electron-app/src/renderer/hooks/use-documents.ts` -- Document query hooks
- Existing codebase: `electron-app/src/renderer/components/comments/CommentInput.tsx` -- Existing mention pattern (textarea-based)
- Existing codebase: `electron-app/package.json` -- Confirms @tiptap/extension-mention ^2.6.0 installed
- TipTap Mention docs: https://tiptap.dev/docs/editor/extensions/nodes/mention -- Extension configuration
- TipTap Suggestion docs: https://tiptap.dev/docs/editor/api/utilities/suggestion -- Suggestion utility API

### Secondary (MEDIUM confidence)
- GitHub discussion #2274: https://github.com/ueberdosis/tiptap/discussions/2274 -- TypeScript ReactRenderer pattern
- DEV Community tutorial: https://dev.to/abdelraman_ahmed_e83db59f/building-a-richtext-editor-with-tiptap-in-react-with-mentions-3l22 -- React mention implementation pattern

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed and documented
- Architecture: HIGH - Patterns derived directly from existing codebase components
- Pitfalls: HIGH - Identified from direct analysis of existing code (localStorage scope bleed, state-based routing, layout constraints)

**Research date:** 2026-01-31
**Valid until:** 2026-03-01 (stable -- all dependencies are existing, no version concerns)

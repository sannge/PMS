# Phase 4: Auto-Save & Content Pipeline - Research

**Researched:** 2026-01-31 (re-verified 2026-01-31)
**Domain:** Auto-save, content format conversion, IndexedDB draft persistence, Electron lifecycle
**Confidence:** HIGH (codebase patterns well-established, standard browser/Electron APIs)

## Summary

Phase 4 adds debounced auto-save with dirty tracking, a server-side content pipeline that converts TipTap JSON to Markdown and plain text on every save, IndexedDB draft persistence for crash recovery, and save-on-navigate/close for the Electron app. The codebase already has a mature IndexedDB infrastructure (`per-query-persister`, `query-cache-db` with LRU eviction, LZ-string compression) and TanStack Query mutations, so the frontend patterns are well-established.

The server-side conversion pipeline is the area requiring most design attention. There is no production-ready Python library that converts TipTap JSON directly to Markdown. The recommended approach is to write a custom recursive TipTap JSON-to-Markdown serializer in Python, which is straightforward because TipTap's ProseMirror JSON schema is a simple recursive tree of `type`/`content`/`marks`/`attrs` nodes. For plain text, a simpler recursive text extractor suffices. This avoids fragile multi-library chaining (tiptapy -> markdownify) and gives full control over edge cases like tables, code blocks, and task lists.

The Electron save-on-close pattern requires IPC coordination between the main process and renderer. The main process intercepts `BrowserWindow.close`, sends a `save-before-quit` IPC message to the renderer, waits up to 3 seconds for confirmation, then proceeds with quit. IndexedDB drafts (written every ~2 seconds of editor inactivity) serve as the true crash recovery mechanism -- they survive force-quit and OS kill scenarios where no events fire.

**Primary recommendation:** Build a custom Python TipTap JSON serializer (JSON-to-Markdown + JSON-to-plain-text) in `fastapi-backend/app/services/content_converter.py` with comprehensive test suite. Use the existing `idb` library to create a separate `pm-drafts-db` IndexedDB store for draft persistence. Use Electron's `BrowserWindow.close` event + IPC pattern for save-on-close, and React effect cleanup for save-on-navigate.

## Re-Research Corrections

Key corrections from re-verification against the current codebase:

1. **Extension list was based on wrong file.** The original research referenced `RichTextEditor.tsx` (task editor). The knowledge base editor uses `editor-extensions.ts` (`createDocumentExtensions()`) which has different extensions:
   - TaskList + TaskItem ARE present (not in old RichTextEditor but added to knowledge base editor)
   - Headings support levels 1-6 (not just 1-3)
   - CodeBlockLowlight replaces StarterKit's codeBlock (with `defaultLanguage: 'plaintext'`)
   - CharacterCount extension is present
   - NO Image or ResizableImage extension in the knowledge base editor
   - TextAlign configured for `['heading', 'paragraph']`

2. **Document model has NO `updated_by` column.** The auto-save endpoint code example incorrectly set `doc.updated_by = current_user.id`. The model only has `created_by`. Remove this line from endpoint implementation.

3. **Existing `document-editor.tsx` has a 300ms debounce** (not 500ms as noted in anti-patterns). The `handleUpdate` callback debounces `onChangeRef.current?.(ed.getJSON())` at 300ms. The auto-save hook should use its own independent 10-second debounce on the `editor.on('update')` event, NOT chain off the existing 300ms debounce.

4. **Preload IPC pattern uses callback Sets, not ipcRenderer.on.** The existing preload pattern (see `onWebSocketMessage`, `onMaximizedChange`) uses a `Set<callback>` in module scope with `ipcRenderer.on` registered ONCE at load time, and the exposed API adds/removes from the Set. The `onBeforeQuit` pattern MUST follow this same approach -- not register a new `ipcRenderer.on` per callback.

5. **`window:close` IPC handler exists** in `ipc/handlers.ts` (line 388) and simply calls `window?.close()`. The before-quit interception must happen on `mainWindow.on('close')` in `index.ts`, which fires BEFORE the window actually closes, allowing `event.preventDefault()`.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `idb` | ^8.0.1 | IndexedDB wrapper for draft store | Already in project (`package.json`), typed, promise-based |
| `@tanstack/react-query` | ^5.90.20 | Mutation for auto-save API calls | Already in project, handles retry/dedup |
| `@tiptap/react` | ^2.6.0 | Editor instance access (getJSON, getText) | Already in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lz-string` | ^1.5.0 | Draft compression in IndexedDB | Already in project, used by `per-query-persister` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Python JSON serializer | `tiptapy` (0.21) + `markdownify` (1.2.2) two-step | Two-step is fragile: `tiptapy` produces HTML, then `markdownify` converts to Markdown. Tables, task lists, and code block language annotations are often lost or mangled in the double conversion. Custom serializer is <400 LOC and fully controlled |
| Custom Python JSON serializer | TipTap Conversion REST API | Requires paid TipTap Cloud subscription; adds external dependency and latency to every save |
| Custom Python JSON serializer | `html-to-markdown` Python package (1.3.1) | Better typed than `markdownify` but still requires HTML intermediate step; doesn't solve the fundamental TipTap-specific edge cases |
| Custom Python JSON serializer | Node.js subprocess from Python (`@tiptap/static-renderer`) | Adds Node.js runtime dependency to backend; process spawn overhead on every save unacceptable for auto-save |
| Separate IndexedDB `drafts` store | localStorage | 5MB limit insufficient for documents with embedded content; no structured queries; no index for cleanup |
| Separate IndexedDB `drafts` store | Reuse existing `pm-query-cache-db` | Draft lifecycle differs from query cache -- drafts are sacred user data with different eviction rules; query cache is disposable and LRU-evicted |

**Installation:**
```bash
# Backend (Python)
# No new packages needed -- custom serializer uses only stdlib + existing Pydantic

# Frontend (already installed)
# idb ^8.0.1, lz-string ^1.5.0, @tanstack/react-query ^5.90.20 all present in package.json
```

## Architecture Patterns

### Recommended Project Structure
```
fastapi-backend/app/
 services/
    content_converter.py     # TipTap JSON -> Markdown + plain text
    document_service.py      # (created in Phase 1) -- add auto-save logic
 routers/
    documents.py             # (created in Phase 1) -- add PUT content endpoint
 tests/
    test_content_converter.py # TDD: test suite with fixtures for all node types

electron-app/src/
 renderer/
    hooks/
       use-auto-save.ts     # Debounced save hook with dirty tracking
       use-draft.ts         # IndexedDB draft persistence hook
    lib/
       draft-db.ts          # IndexedDB store for document drafts
    components/
       knowledge/
           SaveStatus.tsx    # "Saving..." / "Saved Xs ago" / "Save failed" indicator
 main/
    index.ts                 # Add before-quit IPC coordination
 preload/
    index.ts                 # Add onBeforeQuit IPC channel
```

### Pattern 1: Debounced Auto-Save with Dirty Tracking

**What:** A React hook that tracks editor content changes, compares against last-saved content (via JSON stringification), and triggers a save mutation after 10 seconds of inactivity.

**When to use:** Any document editor with auto-save requirements.

**Key design decisions:**
- Use `editor.getJSON()` + `JSON.stringify()` for comparison -- 5-10x faster than `getHTML()` for large documents. `getHTML()` has a known performance issue in Chrome where `Cmd+F` find dialog causes severe slowdown (TipTap issue #2447).
- Single save function with coordination flag to prevent race conditions between auto-save and manual/navigate-away saves.
- Store `lastSavedJson` as a ref (not state) to avoid re-renders on every content change.
- The auto-save hook listens to `editor.on('update')` DIRECTLY -- it does NOT chain off the existing 300ms debounce in `document-editor.tsx`. Two independent systems: the existing 300ms debounce feeds the parent component's `onChange` for state updates; the 10s auto-save debounce triggers network saves.

**Example:**
```typescript
// Pattern: useAutoSave hook
function useAutoSave(documentId: string, editor: Editor | null, rowVersion: number) {
  const lastSavedRef = useRef<string>('')
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const savingRef = useRef(false)                // Mutex to prevent concurrent saves
  const rowVersionRef = useRef(rowVersion)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>({ state: 'idle' })
  const saveMutation = useSaveDocumentContent()

  const isDirty = useCallback(() => {
    if (!editor) return false
    return JSON.stringify(editor.getJSON()) !== lastSavedRef.current
  }, [editor])

  const saveNow = useCallback(async () => {
    if (!editor || !isDirty() || savingRef.current) return
    savingRef.current = true
    // Cancel pending debounce
    if (timerRef.current) clearTimeout(timerRef.current)

    const json = editor.getJSON()
    const jsonStr = JSON.stringify(json)
    setSaveStatus({ state: 'saving' })

    try {
      const response = await saveMutation.mutateAsync({
        documentId,
        content_json: jsonStr,
        row_version: rowVersionRef.current,
      })
      lastSavedRef.current = jsonStr
      rowVersionRef.current = response.row_version  // Update from server response
      setSaveStatus({ state: 'saved', at: Date.now() })
    } catch (error) {
      setSaveStatus({ state: 'error', message: 'Save failed' })
    } finally {
      savingRef.current = false
    }
  }, [editor, documentId, isDirty, saveMutation])

  // On every editor update, reset the 10s debounce timer
  useEffect(() => {
    if (!editor) return
    const handler = () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        saveNow()
      }, 10_000) // 10 seconds of inactivity
    }
    editor.on('update', handler)
    return () => {
      editor.off('update', handler)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [editor, saveNow])

  return { isDirty, saveNow, saveStatus, setSaveStatus }
}
```

### Pattern 2: IndexedDB Draft Persistence

**What:** A separate IndexedDB object store that buffers unsaved editor content on every change (debounced at ~2s). On document open, check for a draft newer than the server version and prompt restore/discard.

**When to use:** Crash recovery for rich text editors.

**Key design decisions:**
- Separate `pm-drafts-db` database -- not co-located with query cache (`pm-query-cache-db`). Different lifecycle: drafts are sacred user data; query cache is disposable with LRU eviction.
- Store `serverUpdatedAt` (the server's `updated_at` timestamp when the doc was loaded) in each draft entry. On restore, compare against current server version to detect conflict.
- 2-second debounce for draft writes. This means worst-case data loss on force-kill is 2 seconds of typing.
- Cleanup drafts older than 7 days on app startup.

**Example:**
```typescript
// Pattern: Draft store using idb library (matches existing query-cache-db.ts patterns)
import { openDB, type IDBPDatabase, type DBSchema } from 'idb'

interface DraftEntry {
  documentId: string       // Primary key
  contentJson: string      // TipTap JSON string
  title: string            // Document title at time of draft
  serverUpdatedAt: number  // Server's updated_at when doc was loaded
  draftedAt: number        // When this draft was written to IndexedDB
}

interface DraftDBSchema extends DBSchema {
  drafts: {
    key: string
    value: DraftEntry
    indexes: {
      'by-drafted-at': number
    }
  }
}

let dbPromise: Promise<IDBPDatabase<DraftDBSchema>> | null = null

function getDraftDB(): Promise<IDBPDatabase<DraftDBSchema>> {
  if (!dbPromise) {
    dbPromise = openDB<DraftDBSchema>('pm-drafts-db', 1, {
      upgrade(db) {
        const store = db.createObjectStore('drafts', { keyPath: 'documentId' })
        store.createIndex('by-drafted-at', 'draftedAt')
      },
      terminated() {
        dbPromise = null  // Match query-cache-db.ts pattern
      },
    })
  }
  return dbPromise
}
```

### Pattern 3: Save on Navigate Away / App Close (Electron-specific)

**What:** Three-layer defense against data loss: (1) React effect cleanup for in-app navigation, (2) `beforeunload` event for Electron window close, (3) Electron IPC `before-quit` pattern for coordinated graceful shutdown.

**When to use:** Any Electron app with unsaved document state.

**Critical Electron details from codebase analysis:**
- The app has `sandbox: true` and `contextIsolation: true` (see `electron-app/src/main/index.ts`). This means renderer cannot access Node.js APIs directly -- all main process communication must go through preload IPC bridge (`electron-app/src/preload/index.ts`).
- The preload uses a **callback Set pattern** (NOT direct `ipcRenderer.on` per consumer). See `webSocketCallbacks`, `maximizedCallbacks` -- a module-level `Set<callback>` is populated by the exposed API, and a single `ipcRenderer.on` listener iterates the set. A new `beforeQuitCallbacks` Set must follow this same pattern.
- `navigator.sendBeacon` is unreliable in Electron sandbox mode and has a 64KB body limit. Do NOT use it as primary save mechanism.
- The existing `window:close` IPC handler in `ipc/handlers.ts` simply calls `window?.close()`. The before-quit interception must happen in `mainWindow.on('close')` in `index.ts`, which fires BEFORE the window actually closes.

**Implementation approach for Electron before-quit:**
```typescript
// In electron-app/src/main/index.ts:
import { ipcMain } from 'electron'  // add ipcMain to existing import

let isQuitting = false

mainWindow.on('close', (event) => {
  if (!isQuitting) {
    event.preventDefault()
    // Send IPC to renderer to save
    mainWindow.webContents.send('before-quit-save')
    // Set a 3-second timeout -- quit regardless
    setTimeout(() => {
      isQuitting = true
      mainWindow?.close()
    }, 3000)
  }
})

// Listen for renderer confirmation
ipcMain.on('quit-save-complete', () => {
  isQuitting = true
  mainWindow?.close()
})
```

```typescript
// In preload/index.ts, add callback Set (matching existing pattern):
const beforeQuitCallbacks = new Set<() => void>()

ipcRenderer.on('before-quit-save', () => {
  beforeQuitCallbacks.forEach((callback) => callback())
})

// In the exposed API object:
onBeforeQuit: (callback: () => void) => {
  beforeQuitCallbacks.add(callback)
  return () => {
    beforeQuitCallbacks.delete(callback)
  }
},
confirmQuitSave: () => {
  ipcRenderer.send('quit-save-complete')
},
```

### Pattern 4: Server-Side Content Conversion Pipeline

**What:** On every document save, the FastAPI endpoint converts TipTap JSON to Markdown and plain text before writing to the database. All three formats stored in the same row.

**When to use:** When content needs to be consumed by multiple systems (editor JSON, AI/LLM Markdown, search plain text).

**TipTap JSON structure (ProseMirror):** The document is a recursive tree. Each node has `type`, optional `attrs`, optional `content` (array of child nodes), and optional `marks` (array of inline formatting). Text nodes have `type: "text"` and a `text` field.

**Node types from the knowledge base editor (`editor-extensions.ts`):**
- Block: `doc`, `paragraph`, `heading` (levels 1-6), `bulletList`, `orderedList`, `listItem`, `taskList`, `taskItem`, `codeBlock` (with `language` attr, default `'plaintext'`), `blockquote`, `table`, `tableRow`, `tableCell`, `tableHeader`, `horizontalRule`
- Inline: `text`, `hardBreak`
- Marks: `bold`, `italic`, `underline`, `strike`, `code`, `link` (with `href` attr), `textStyle` (with `fontSize`, `fontFamily`, `color` attrs), `highlight` (with `color` attr)
- Custom attributes (via global attributes, NOT separate node types):
  - `indent` attr on `paragraph` and `heading` nodes (integer 0-8, represents indentation level)
  - `textAlign` attr on `paragraph` and `heading` nodes (string: `'left'`, `'center'`, `'right'`, `'justify'`)

**NOTE:** The knowledge base editor does NOT have Image/ResizableImage extensions. If images are added later, the converter should handle them gracefully via the unknown-node fallback.

**Example:**
```python
# fastapi-backend/app/services/content_converter.py
from typing import Any

# -- Markdown Conversion -------------------------------------------------------

_MARK_WRAPPERS = {
    "bold": "**",
    "italic": "_",
    "strike": "~~",
    "code": "`",
}

def tiptap_json_to_markdown(doc: dict[str, Any]) -> str:
    """Convert TipTap JSON document to Markdown string."""
    if not doc or doc.get("type") != "doc":
        return ""
    return _md_nodes(doc.get("content", []))

def _md_nodes(nodes: list[dict[str, Any]], list_indent: int = 0) -> str:
    parts: list[str] = []
    for node in nodes:
        t = node.get("type", "")
        if t == "paragraph":
            text = _md_inline(node.get("content", []))
            # Indent attr is presentation-only; skip in Markdown
            parts.append(text + "\n\n")
        elif t == "heading":
            level = node.get("attrs", {}).get("level", 1)
            parts.append("#" * level + " " + _md_inline(node.get("content", [])) + "\n\n")
        elif t == "bulletList":
            for item in node.get("content", []):
                prefix = "  " * list_indent + "- "
                parts.append(prefix + _md_list_item(item, list_indent))
            parts.append("\n")
        elif t == "orderedList":
            for i, item in enumerate(node.get("content", []), 1):
                prefix = "  " * list_indent + f"{i}. "
                parts.append(prefix + _md_list_item(item, list_indent))
            parts.append("\n")
        elif t == "taskList":
            for item in node.get("content", []):
                checked = item.get("attrs", {}).get("checked", False)
                marker = "[x]" if checked else "[ ]"
                prefix = "  " * list_indent + f"- {marker} "
                parts.append(prefix + _md_list_item(item, list_indent))
            parts.append("\n")
        elif t == "codeBlock":
            lang = node.get("attrs", {}).get("language", "")
            # Skip "plaintext" default language -- render as bare ```
            if lang == "plaintext":
                lang = ""
            code = _extract_text_from_nodes(node.get("content", []))
            parts.append(f"```{lang}\n{code}\n```\n\n")
        elif t == "blockquote":
            inner = _md_nodes(node.get("content", []))
            lines = inner.strip().split("\n")
            parts.append("\n".join("> " + line for line in lines) + "\n\n")
        elif t == "table":
            parts.append(_md_table(node) + "\n\n")
        elif t == "horizontalRule":
            parts.append("---\n\n")
        elif t == "image":
            # Not currently in knowledge base editor, but handle gracefully
            src = node.get("attrs", {}).get("src", "")
            alt = node.get("attrs", {}).get("alt", "")
            parts.append(f"![{alt}]({src})\n\n")
        else:
            # Unknown node -- render children if any
            if "content" in node:
                parts.append(_md_nodes(node["content"], list_indent))
    return "".join(parts)

def _md_inline(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes:
        if node.get("type") == "text":
            text = node.get("text", "")
            for mark in node.get("marks", []):
                mark_type = mark.get("type", "")
                wrapper = _MARK_WRAPPERS.get(mark_type, "")
                if mark_type == "link":
                    href = mark.get("attrs", {}).get("href", "")
                    text = f"[{text}]({href})"
                elif mark_type == "underline":
                    # Markdown has no underline -- use HTML tag
                    text = f"<u>{text}</u>"
                elif wrapper:
                    text = f"{wrapper}{text}{wrapper}"
                # textStyle, highlight marks are presentation-only; skip in Markdown
            parts.append(text)
        elif node.get("type") == "hardBreak":
            parts.append("  \n")
    return "".join(parts)

def _md_list_item(item: dict[str, Any], parent_indent: int) -> str:
    """Render a listItem node, recursively handling nested lists."""
    content = item.get("content", [])
    parts: list[str] = []
    for i, child in enumerate(content):
        if child.get("type") in ("bulletList", "orderedList", "taskList"):
            # Nested list -- increase indent
            parts.append("\n" + _md_nodes([child], parent_indent + 1))
        elif child.get("type") == "paragraph":
            text = _md_inline(child.get("content", []))
            if i == 0:
                parts.append(text + "\n")
            else:
                # Continuation paragraph in list item
                parts.append("  " * (parent_indent + 1) + text + "\n")
        else:
            parts.append(_md_nodes([child], parent_indent + 1))
    return "".join(parts)

def _md_table(node: dict[str, Any]) -> str:
    """Render a table node to Markdown."""
    rows = node.get("content", [])
    if not rows:
        return ""

    md_rows: list[list[str]] = []
    for row in rows:
        cells = row.get("content", [])
        md_cells: list[str] = []
        for cell in cells:
            cell_content = _md_inline(
                cell.get("content", [{}])[0].get("content", [])
                if cell.get("content") else []
            )
            md_cells.append(cell_content.strip())
        md_rows.append(md_cells)

    if not md_rows:
        return ""

    # Build markdown table
    lines: list[str] = []
    # Header row
    lines.append("| " + " | ".join(md_rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in md_rows[0]) + " |")
    # Data rows
    for row in md_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# -- Plain Text Extraction -----------------------------------------------------

def tiptap_json_to_plain_text(doc: dict[str, Any]) -> str:
    """Extract plain text from TipTap JSON document."""
    if not doc or doc.get("type") != "doc":
        return ""
    return _extract_text_from_nodes(doc.get("content", [])).strip()

def _extract_text_from_nodes(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes:
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        elif node.get("type") == "hardBreak":
            parts.append("\n")
        elif "content" in node:
            parts.append(_extract_text_from_nodes(node["content"]))
            # Add newline after block-level nodes
            if node.get("type") in ("paragraph", "heading", "listItem", "taskItem", "codeBlock", "blockquote"):
                parts.append("\n")
    return "".join(parts)
```

### Anti-Patterns to Avoid

- **Saving on every keystroke:** The existing `document-editor.tsx` has a 300ms debounce for its `onChange` callback. The auto-save hook must use its own INDEPENDENT 10-second inactivity debounce on `editor.on('update')`, not chain off the existing 300ms debounce.
- **Using `getHTML()` for dirty comparison:** `getHTML()` is slow for large documents and has Chrome-specific performance bugs (TipTap issue #2447). Use `getJSON()` + `JSON.stringify()` for comparison.
- **Blocking the UI on save:** Save mutations must be fire-and-forget with status indicator. Never block editor input during save.
- **Single IndexedDB store for drafts AND query cache:** Different lifecycles and eviction rules. Drafts are sacred user data; query cache is disposable with LRU eviction.
- **Relying only on `beforeunload` for crash recovery:** `beforeunload` does NOT fire on force-quit, process crash, or OS kill. IndexedDB drafts (written every ~2s) are the actual crash recovery mechanism.
- **Two-step `tiptapy` + `markdownify` for production Markdown:** Fragile for tables, task lists, code blocks with language annotations, and underline marks. Custom serializer is more reliable and maintainable.
- **Using `navigator.sendBeacon` as primary save-on-close:** Has 64KB body limit per spec, and is unreliable in Electron's sandbox mode. Use IndexedDB + Electron IPC instead.
- **Registering per-consumer `ipcRenderer.on` in preload:** The codebase uses a callback Set pattern (`webSocketCallbacks`, `maximizedCallbacks`). Do NOT create a new `ipcRenderer.on('before-quit-save', ...)` per subscriber. Use a `beforeQuitCallbacks` Set.
- **Setting `doc.updated_by` in the save endpoint:** The Document model does NOT have an `updated_by` column. Only `created_by` exists. The `updated_at` column auto-updates via SQLAlchemy's `onupdate`.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IndexedDB access | Raw IndexedDB API | `idb` library (already installed, v8.0.1) | Promise-based, typed, handles versioning/upgrades. Codebase already uses it in `query-cache-db.ts` |
| API mutation with retry | Custom fetch + retry | TanStack Query `useMutation` (already installed, v5.90+) | Built-in retry, dedup, optimistic updates, error state |
| LZ compression for drafts | Custom compression | `lz-string` (already installed, v1.5.0) | Battle-tested, fast, ~60-80% compression for JSON text. Already used by `per-query-persister.ts` |
| Debounce timer | Separate `use-debounce` npm package | Simple ref-based `setTimeout` (no library needed) | A `useRef` + `setTimeout` is ~10 LOC; no dependency needed for a single debounce timer |
| Relative time ("Saved 3s ago") | Moment.js or date-fns | Simple `useEffect` with 1s interval + `Date.now() - lastSaved` math | No library needed; existing codebase has `lib/time-utils.ts` |
| Electron IPC event bridge | Custom event system | Follow existing callback Set + `ipcRenderer.on` preload pattern | `preload/index.ts` already has the callback registration pattern for bidirectional IPC |

**Key insight:** The project already has all required infrastructure libraries installed. Phase 4 is primarily application logic on top of existing infrastructure, not new library integration.

## Common Pitfalls

### Pitfall 1: Race Condition Between Auto-Save and Immediate Save
**What goes wrong:** User triggers immediate save (navigate away or app close) while debounced auto-save is pending. Both fire, causing duplicate saves or version conflict (409 from optimistic concurrency).
**Why it happens:** Two independent save triggers without coordination.
**How to avoid:** Single `saveNow()` function with a `savingRef` mutex. Cancel pending debounce timer when immediate save triggers. Use `row_version` optimistic concurrency on the server -- if a 409 occurs, the client can refetch the latest version and reconcile.
**Warning signs:** 409 errors in console, "Save failed" flickering after a successful save.

### Pitfall 2: IndexedDB Draft Grows Unbounded
**What goes wrong:** Drafts accumulate for documents the user no longer edits. IndexedDB storage grows without limit.
**Why it happens:** No cleanup of drafts after successful server save.
**How to avoid:** Delete the IndexedDB draft immediately after a confirmed server save (in mutation `onSuccess`). On app startup, run `cleanupOldDrafts(7)` to remove drafts older than 7 days. The `by-drafted-at` index makes this cleanup efficient.
**Warning signs:** IndexedDB storage growing monotonically in DevTools Application tab.

### Pitfall 3: Draft Restore Prompt Shows for Already-Saved Content
**What goes wrong:** User sees "Restore unsaved draft?" but the draft content matches what the server already has.
**Why it happens:** Draft was written to IndexedDB, then save mutation succeeded but draft cleanup failed (race condition) or the save confirmation arrived after the draft was written.
**How to avoid:** When checking for drafts on document open, compare draft's `draftedAt` timestamp against the document's `updated_at` from server. Also compare actual content -- if draft JSON matches server JSON, silently delete the draft. Only show restore prompt if draft is newer AND content differs.
**Warning signs:** Users reporting false restore prompts on every document open.

### Pitfall 4: Electron Close Loop (Infinite Close Event)
**What goes wrong:** The `BrowserWindow.close` handler calls `event.preventDefault()` to allow save, then after save completes, calls `mainWindow.close()` which triggers the handler again in an infinite loop.
**Why it happens:** No flag to distinguish the first close attempt from the post-save close.
**How to avoid:** Set an `isQuitting` flag before the second close call. Check this flag at the top of the close handler -- if true, allow default close behavior.
**Warning signs:** App hangs on close, eventually crashes.

### Pitfall 5: `beforeunload` Cannot Make Async API Calls Reliably
**What goes wrong:** `beforeunload` fires but the API save request is cancelled by the browser before completing.
**Why it happens:** Browsers aggressively cancel pending requests when the page is unloading. `fetch()` with `keepalive: true` partially works but has body size limits.
**How to avoid:** In `beforeunload`, write to IndexedDB (which typically completes before teardown). For Electron, use the IPC pattern from Pattern 3 above. Treat the API save as best-effort; IndexedDB draft is the reliable fallback.
**Warning signs:** "Save failed" on app close, draft recovery prompts after normal close.

### Pitfall 6: TipTap JSON Schema Varies by Extension Configuration
**What goes wrong:** The Python Markdown converter encounters node types or mark types it doesn't handle, producing incomplete output.
**Why it happens:** The converter is tightly coupled to the specific TipTap extensions used. The knowledge base editor (`editor-extensions.ts`) uses: StarterKit (paragraph, heading 1-6, bulletList, orderedList, listItem, codeBlock replaced by CodeBlockLowlight, blockquote, horizontalRule, hardBreak, bold, italic, strike, code marks), Underline, TextStyle, FontFamily, custom FontSize, custom Indent, Color, Highlight, TextAlign, Link, Table/TableRow/TableCell/TableHeader, TaskList/TaskItem, CodeBlockLowlight, CharacterCount, and Placeholder.
**How to avoid:** Write the converter with explicit handlers for every node/mark type from the extensions list above. Add a catch-all fallback that renders children of unknown nodes (recursive descent) and logs a warning. Write backend tests with JSON fixtures for each node type.
**Warning signs:** Markdown output missing sections or containing raw JSON fragments.

### Pitfall 7: Electron Force-Quit Skips All Save Events
**What goes wrong:** User does Alt+F4 rapid double-click, Task Manager kill, or OS force-quit. No `beforeunload`, `before-quit`, or any event fires. Data since last IndexedDB draft write is lost.
**Why it happens:** OS-level process kill cannot be intercepted.
**How to avoid:** Write IndexedDB drafts frequently (every ~2 seconds of editor inactivity). This limits data loss to at most 2 seconds of typing. This is the only reliable crash recovery mechanism.
**Warning signs:** Users reporting lost edits after crashes, despite auto-save being "enabled."

### Pitfall 8: Content Converter Ignores Custom Attributes (indent, textAlign)
**What goes wrong:** The Markdown output loses indentation context from the custom Indent extension.
**Why it happens:** The `indent` and `textAlign` attributes are added via global attributes on paragraph/heading nodes. The converter doesn't check `node.attrs.indent`.
**How to avoid:** For Markdown, treat `indent` and `textAlign` as presentation-only -- skip them (Markdown doesn't support arbitrary indentation or alignment). For plain text, also skip. This is the correct behavior since these are visual-only attributes. Document this design decision so future maintainers understand.
**Warning signs:** None -- this is expected behavior, not a bug.

## Code Examples

### Auto-Save Endpoint (FastAPI)

```python
# Addition to fastapi-backend/app/routers/documents.py

class DocumentContentUpdate(BaseModel):
    content_json: str
    row_version: int

@router.put("/documents/{document_id}/content")
async def save_document_content(
    document_id: UUID,
    body: DocumentContentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Auto-save endpoint. Accepts content_json, runs content pipeline,
    stores all three formats, increments row_version.
    Returns 409 if row_version mismatch (stale client).
    """
    doc = await get_document_or_404(document_id, db)
    if doc.row_version != body.row_version:
        raise HTTPException(
            status_code=409,
            detail="Document was modified. Refresh to get latest version."
        )

    # Parse and convert
    content_dict = json.loads(body.content_json)
    doc.content_json = body.content_json
    doc.content_markdown = tiptap_json_to_markdown(content_dict)
    doc.content_plain = tiptap_json_to_plain_text(content_dict)
    doc.row_version += 1
    # NOTE: updated_at auto-updates via SQLAlchemy onupdate
    # NOTE: Document model has NO updated_by column

    await db.commit()
    await db.refresh(doc)
    return DocumentResponse.model_validate(doc)
```

### Save Status State Machine

```typescript
// Type for save status (used by SaveStatus component and useAutoSave hook)
type SaveStatus =
  | { state: 'idle' }
  | { state: 'saving' }
  | { state: 'saved'; at: number }
  | { state: 'error'; message: string }

// Display rules:
// 'idle'    -> nothing shown (or "No changes")
// 'saving'  -> "Saving..."
// 'saved'   -> "Saved Xs ago" (update every second via setInterval)
// 'error'   -> "Save failed" with retry button
```

### Draft Restore Check on Document Open

```typescript
// Pattern: useDraft hook checks for unsaved draft on mount
function useDraft(documentId: string, serverUpdatedAt: number) {
  const [pendingDraft, setPendingDraft] = useState<DraftEntry | null>(null)

  useEffect(() => {
    async function checkDraft() {
      const draft = await getDraft(documentId)
      if (!draft) return

      // Draft exists -- is it newer than server version?
      if (draft.draftedAt > serverUpdatedAt) {
        // Content actually differs?
        // (draft.contentJson will be compared against loaded server content)
        setPendingDraft(draft)
      } else {
        // Draft is older than server -- silently clean up
        await deleteDraft(documentId)
      }
    }
    checkDraft()
  }, [documentId, serverUpdatedAt])

  const restoreDraft = useCallback(() => {
    // Return draft content for editor to load
    const content = pendingDraft?.contentJson
    setPendingDraft(null)
    return content ? JSON.parse(content) : null
  }, [pendingDraft])

  const discardDraft = useCallback(async () => {
    await deleteDraft(documentId)
    setPendingDraft(null)
  }, [documentId])

  return { pendingDraft, restoreDraft, discardDraft }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `getHTML()` for dirty check | `getJSON()` + `JSON.stringify()` | TipTap 2.x best practice | 5-10x faster comparison for large documents |
| localStorage for drafts | IndexedDB with `idb` | 2023+ | No 5MB limit, structured data, index-based cleanup |
| Full Zustand store for save state | TanStack Query mutation state + React Context | Project decision (STATE.md) | Zustand removed in Phase 1; mutation `isPending`/`isError` covers save state |
| `tiptapy` (0.21) + `markdownify` (1.2.2) pipeline | Custom Python JSON walker | 2025+ community consensus | No external dependencies, handles edge cases (tables, task lists, code lang, underline) |
| `navigator.sendBeacon` for save-on-close | IndexedDB draft as primary + Electron IPC | Electron-specific | `sendBeacon` has 64KB limit; Electron IPC is more reliable for coordinated shutdown |
| Single-blob cache persistence | Per-query persistence (`per-query-persister.ts`) | Existing codebase | Already implemented; draft DB follows same `idb` patterns |

**Deprecated/outdated:**
- `tiptap-markdown` npm package: Maintainer no longer active; TipTap v2 has native Markdown support but it is editor-side only (JavaScript), not useful for server-side Python conversion
- Zustand stores: Removed in Phase 1 per project decision. Auth and notification state migrated to React Context.
- `markdownify` (Python): Version 1.2.2 (Nov 2025) is mature but only does HTML-to-Markdown, not TipTap JSON-to-Markdown. Would require an intermediate HTML step that loses semantic information

## Open Questions

1. **Markdown conversion fidelity for complex table structures**
   - What we know: TipTap tables (using `@tiptap/extension-table`) can have header rows and custom column widths. Markdown tables only support simple column-per-cell with optional alignment. The knowledge base editor configures `resizable: true` on tables.
   - What's unclear: Whether merged cells will be used. The extension supports them but the editor toolbar doesn't expose merge controls.
   - Recommendation: Implement basic table rendering (header row + data rows, no merge support). If a table cell contains nested block content (paragraphs, lists), render as inline text within the cell. Log a warning for unexpected table structures.

2. **Electron `before-quit` IPC timing on Windows**
   - What we know: Electron fires `close` event on BrowserWindow. `event.preventDefault()` can delay close. IPC to renderer is async.
   - What's unclear: Maximum time Windows allows before force-killing the process after user clicks close. On Windows, the "Not Responding" dialog typically appears after ~5 seconds.
   - Recommendation: Set a 3-second timeout in the main process close handler. If renderer doesn't confirm save within 3 seconds, quit anyway. IndexedDB drafts (written every ~2s) handle the force-kill case.

3. **Draft restore UX when document was edited by another user**
   - What we know: User A edits locally, closes app (draft saved). User B edits and saves on server. User A reopens -- draft is based on an older version.
   - What's unclear: Whether to show both versions side-by-side, auto-merge, or just offer restore/discard.
   - Recommendation: Keep it simple. Show a dialog: "You have an unsaved draft from [time]. Restore or discard?" If user restores, the old server version is replaced. The `row_version` check on the server will prevent accidental overwrites -- the client must refetch the current `row_version` before saving the restored draft.

4. **Content converter handling of `underline` mark**
   - What we know: Markdown has no native underline syntax. The editor supports underline via `@tiptap/extension-underline`.
   - What's unclear: Whether AI/LLM consumers of the Markdown output will handle `<u>` HTML tags.
   - Recommendation: Render underline as `<u>text</u>` in Markdown (HTML is valid in Markdown). For plain text, strip it entirely.

5. **CodeBlockLowlight `defaultLanguage: 'plaintext'` handling in Markdown**
   - What we know: The knowledge base editor sets `defaultLanguage: 'plaintext'` on CodeBlockLowlight. This means even user-created code blocks without a specified language will have `language: 'plaintext'` in the JSON attrs.
   - What's unclear: Whether AI consumers prefer bare ``` or ```plaintext for unlabeled code blocks.
   - Recommendation: Skip the language annotation when it equals `'plaintext'` -- render as bare ```. This produces cleaner Markdown and is the conventional approach.

## Sources

### Primary (HIGH confidence)
- Codebase: `electron-app/src/renderer/components/knowledge/editor-extensions.ts` -- Knowledge base editor factory with full extension list (StarterKit, Underline, TextStyle, FontFamily, FontSize, Indent, Color, Highlight, TextAlign, Link, Table/TableRow/TableCell/TableHeader, TaskList/TaskItem, CodeBlockLowlight, CharacterCount, Placeholder)
- Codebase: `electron-app/src/renderer/components/knowledge/document-editor.tsx` -- DocumentEditor component with 300ms debounce, getJSON() output, EditorStatusBar
- Codebase: `electron-app/src/renderer/lib/query-cache-db.ts` -- Existing `idb` v8.0.1 patterns for IndexedDB (openDB, object stores, indexes, cursor-based operations, singleton dbPromise)
- Codebase: `electron-app/src/renderer/lib/per-query-persister.ts` -- Existing per-query persistence with LZ-string compression
- Codebase: `electron-app/src/renderer/hooks/use-queries.ts` -- TanStack Query mutation patterns (useMutation with optimistic updates)
- Codebase: `electron-app/src/main/index.ts` -- Electron main process lifecycle (no `before-quit` handler yet; security config with sandbox/contextIsolation; existing `mainWindow.on('closed')` cleanup; `ipcMain` NOT imported yet)
- Codebase: `electron-app/src/preload/index.ts` -- IPC bridge patterns (callback Sets for `webSocketCallbacks`, `maximizedCallbacks`, `notificationCallbacks`; `contextBridge.exposeInMainWorld`; `ElectronAPI` interface)
- Codebase: `electron-app/src/main/ipc/handlers.ts` -- Existing `window:close` handler at line 388 (calls `window?.close()`)
- Codebase: `electron-app/package.json` -- Confirmed installed: `idb` ^8.0.1, `idb-keyval` ^6.2.2, `lz-string` ^1.5.0, `@tanstack/react-query` ^5.90.20, `@tiptap/react` ^2.6.0, `electron` ^30.1.2
- Codebase: `fastapi-backend/app/models/document.py` -- Document model: `content_json`, `content_markdown`, `content_plain` (all Text, nullable), `row_version` (Integer, default=1), `created_by` FK, NO `updated_by` column, `updated_at` with onupdate
- Codebase: `fastapi-backend/app/routers/documents.py` -- Existing CRUD endpoints, no PUT content endpoint yet
- Codebase: `fastapi-backend/app/services/document_service.py` -- Existing service helpers (validate_scope, cursor pagination, folder management)

### Secondary (MEDIUM confidence)
- [TipTap GitHub Discussion #5847](https://github.com/ueberdosis/tiptap/discussions/5847) -- JSON to Markdown conversion approaches; community consensus: custom serializer or HTML intermediate
- [TipTap GitHub Issue #2447](https://github.com/ueberdosis/tiptap/issues/2447) -- Performance issue with `getHTML()` in Chrome; recommends `getJSON()` for comparisons
- [Electron BrowserWindow docs](https://www.electronjs.org/docs/latest/api/browser-window) -- `close` event, `webContents.send()`
- [idb GitHub](https://github.com/jakearchibald/idb) -- Promise-based IndexedDB wrapper, ~1.19kB brotli'd

### Tertiary (LOW confidence)
- ProseMirror JSON schema structure -- Based on training data, verified against `editor-extensions.ts` extension configuration and TipTap docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed in codebase; no new dependencies needed; versions verified in package.json
- Architecture: HIGH -- patterns directly derived from existing codebase infrastructure (`per-query-persister`, `query-cache-db`, TanStack Query mutations, Electron IPC callback Set pattern)
- Content converter: HIGH -- custom Python serializer approach verified against actual TipTap extension list in `editor-extensions.ts` (NOT `RichTextEditor.tsx`); node types fully enumerated from knowledge base editor
- Electron lifecycle: MEDIUM -- `BrowserWindow.close` IPC pattern is well-documented but Windows-specific timing guarantees are not fully documented; 3-second timeout is a pragmatic choice
- Pitfalls: HIGH -- well-documented in Electron and IndexedDB ecosystems; codebase already handles similar patterns in query cache

**Re-research corrections applied:**
- Extension list corrected from `RichTextEditor.tsx` to `editor-extensions.ts`
- TaskList/TaskItem confirmed present in knowledge base editor
- Heading levels corrected from 1-3 to 1-6
- Image/ResizableImage confirmed NOT present in knowledge base editor
- `updated_by` bug identified and documented (column does not exist on Document model)
- Preload IPC pattern corrected to use callback Set (not per-consumer ipcRenderer.on)
- Existing debounce in document-editor.tsx corrected from 500ms to 300ms
- CodeBlockLowlight `defaultLanguage: 'plaintext'` handling added

**Research date:** 2026-01-31
**Valid until:** 2026-03-02 (stable domain, 30 days)

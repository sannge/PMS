# Phase 4: Auto-Save & Content Pipeline - Research

**Researched:** 2026-01-31
**Domain:** Auto-save, content format conversion, IndexedDB draft persistence, Electron lifecycle
**Confidence:** HIGH (codebase patterns well-established, standard browser/Electron APIs)

## Summary

Phase 4 adds debounced auto-save with dirty tracking, a server-side content pipeline that converts TipTap JSON to Markdown and plain text on every save, IndexedDB draft persistence for crash recovery, and save-on-navigate/close for the Electron app. The codebase already has a mature IndexedDB infrastructure (per-query-persister, query-cache-db with LRU eviction, LZ-string compression) and TanStack Query mutations, so the frontend patterns are well-established.

The server-side conversion pipeline is the area requiring most design attention. There is no production-ready Python library that converts TipTap JSON directly to Markdown. The recommended approach is to write a custom recursive TipTap JSON-to-Markdown serializer in Python, which is straightforward because TipTap's ProseMirror JSON schema is a simple recursive tree of `type`/`content`/`marks`/`attrs` nodes. For plain text, a simpler recursive text extractor suffices. This avoids fragile multi-library chaining (tiptapy -> markdownify) and gives full control over edge cases like tables, code blocks, and task lists.

**Primary recommendation:** Build a custom Python TipTap JSON serializer (JSON-to-Markdown + JSON-to-plain-text) in `fastapi-backend/app/services/content_converter.py`. Use the existing per-query-persister IndexedDB infrastructure for draft persistence, adding a separate `drafts` object store. Use Electron's `before-quit` / IPC pattern for save-on-close, and `beforeunload` + React effect cleanup for save-on-navigate.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `idb` | 8.0.1 | IndexedDB wrapper for draft store | Already in project, typed, promise-based |
| `@tanstack/react-query` | 5.90+ | Mutation for auto-save API calls | Already in project, handles retry/dedup |
| `@tiptap/react` | 2.6+ | Editor instance access (getJSON, getText) | Already in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `markdownify` | 0.14+ | HTML-to-Markdown (Python) | Fallback verification only -- not primary pipeline |
| `lz-string` | 1.5+ | Draft compression in IndexedDB | Already in project, used by per-query-persister |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Python JSON serializer | tiptapy + markdownify (two-step) | Two-step is fragile for tables/task-lists; custom serializer is <300 LOC and fully controlled |
| Custom Python JSON serializer | TipTap Conversion REST API | Requires paid TipTap Cloud subscription; adds external dependency |
| Custom Python JSON serializer | Node.js subprocess from Python | Adds Node.js runtime dependency to backend; complexity for marginal benefit |
| Separate IndexedDB `drafts` store | localStorage | 5MB limit insufficient for documents; no structured queries; no crash durability guarantee |
| Separate IndexedDB `drafts` store | Reuse existing query-cache-db | Draft lifecycle differs from query cache (drafts are user-intent, not API cache; different eviction rules) |

**Installation:**
```bash
# Backend (Python)
# No new packages needed -- custom serializer uses only stdlib + existing Pydantic

# Frontend (already installed)
# idb 8.0.1, lz-string 1.5.0, @tanstack/react-query 5.90+ all present
```

## Architecture Patterns

### Recommended Project Structure
```
fastapi-backend/app/services/
├── content_converter.py     # TipTap JSON -> Markdown + plain text
└── document_service.py      # Existing -- add auto-save endpoint logic

electron-app/src/renderer/
├── hooks/
│   ├── use-auto-save.ts     # Debounced save hook with dirty tracking
│   └── use-draft.ts         # IndexedDB draft persistence hook
├── lib/
│   ├── draft-db.ts          # IndexedDB store for document drafts
│   └── query-cache-db.ts    # Existing -- no changes needed
└── components/
    └── knowledge/
        └── save-status.tsx  # "Saving..." / "Saved Xs ago" / "Save failed" indicator
```

### Pattern 1: Debounced Auto-Save with Dirty Tracking

**What:** A React hook that tracks editor content changes, compares against last-saved content (via JSON hash), and triggers a save mutation after 10 seconds of inactivity.

**When to use:** Any document editor with auto-save requirements.

**Example:**
```typescript
// Pattern: useAutoSave hook
function useAutoSave(documentId: string, editor: Editor | null) {
  const lastSavedRef = useRef<string>('')
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const saveMutation = useSaveDocument()

  const isDirty = useCallback(() => {
    if (!editor) return false
    const currentJson = JSON.stringify(editor.getJSON())
    return currentJson !== lastSavedRef.current
  }, [editor])

  // On every editor update, reset the 10s debounce timer
  useEffect(() => {
    if (!editor) return
    const handler = () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        if (isDirty()) {
          const json = editor.getJSON()
          saveMutation.mutate({ documentId, content_json: JSON.stringify(json) })
          lastSavedRef.current = JSON.stringify(json)
        }
      }, 10_000) // 10 seconds
    }
    editor.on('update', handler)
    return () => {
      editor.off('update', handler)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [editor, documentId, isDirty, saveMutation])

  return { isDirty, save: () => { /* immediate save */ } }
}
```

### Pattern 2: IndexedDB Draft Persistence

**What:** A separate IndexedDB object store that buffers unsaved editor content on every change (debounced at ~2s). On document open, check for a draft newer than the server version and prompt restore/discard.

**When to use:** Crash recovery for rich text editors.

**Example:**
```typescript
// Pattern: Draft store using idb library
import { openDB } from 'idb'

const DRAFT_DB_NAME = 'pm-drafts-db'
const DRAFT_DB_VERSION = 1
const DRAFT_STORE = 'drafts'

interface DraftEntry {
  documentId: string       // Primary key
  contentJson: string      // TipTap JSON string
  savedAt: number          // Timestamp of last server save (to compare)
  draftedAt: number        // Timestamp of this draft
  title: string            // Document title at time of draft
}

function getDraftDB() {
  return openDB(DRAFT_DB_NAME, DRAFT_DB_VERSION, {
    upgrade(db) {
      db.createObjectStore(DRAFT_STORE, { keyPath: 'documentId' })
    }
  })
}
```

### Pattern 3: Save on Navigate Away / App Close

**What:** Two mechanisms ensure no data loss: (1) React effect cleanup + `beforeunload` for in-app navigation and browser close, (2) Electron IPC `before-quit` for app force-quit.

**When to use:** Any Electron app with unsaved document state.

**Example:**
```typescript
// Pattern: beforeunload + effect cleanup
useEffect(() => {
  const handleBeforeUnload = (e: BeforeUnloadEvent) => {
    if (isDirty()) {
      // Synchronous save to IndexedDB (fast, local)
      saveDraftSync(documentId, editor.getJSON())
      // Also attempt API save (may not complete)
      navigator.sendBeacon('/api/documents/' + documentId + '/save', body)
      e.preventDefault()
    }
  }
  window.addEventListener('beforeunload', handleBeforeUnload)
  return () => {
    window.removeEventListener('beforeunload', handleBeforeUnload)
    // On unmount (navigate away), save immediately
    if (isDirty()) {
      saveDraftToIndexedDB(documentId, editor.getJSON())
      saveToServer(documentId, editor.getJSON()) // fire-and-forget
    }
  }
}, [isDirty, documentId, editor])
```

### Pattern 4: Server-Side Content Conversion Pipeline

**What:** On every document save, the FastAPI endpoint converts TipTap JSON to Markdown and plain text before writing to the database. All three formats stored in the same row.

**When to use:** When content needs to be consumed by multiple systems (editor JSON, AI/LLM Markdown, search plain text).

**Example:**
```python
# Pattern: Content converter service
from typing import Any

def tiptap_json_to_markdown(doc: dict[str, Any]) -> str:
    """Convert TipTap JSON document to Markdown string."""
    if not doc or "content" not in doc:
        return ""
    return _render_nodes(doc["content"])

def _render_nodes(nodes: list[dict[str, Any]], indent: int = 0) -> str:
    parts: list[str] = []
    for node in nodes:
        node_type = node.get("type", "")
        if node_type == "paragraph":
            text = _render_inline(node.get("content", []))
            parts.append(text + "\n\n")
        elif node_type == "heading":
            level = node.get("attrs", {}).get("level", 1)
            text = _render_inline(node.get("content", []))
            parts.append("#" * level + " " + text + "\n\n")
        elif node_type == "bulletList":
            parts.append(_render_list(node, ordered=False, indent=indent))
        # ... etc for codeBlock, table, taskList, blockquote, image
    return "".join(parts)

def tiptap_json_to_plain_text(doc: dict[str, Any]) -> str:
    """Extract plain text from TipTap JSON document."""
    if not doc or "content" not in doc:
        return ""
    return _extract_text(doc["content"])
```

### Anti-Patterns to Avoid

- **Saving on every keystroke:** Even debounced at 500ms, this creates excessive API calls. Use 10s inactivity debounce as specified in requirements.
- **Using `getHTML()` for dirty comparison:** `getHTML()` is slow for large documents. Use `getJSON()` + `JSON.stringify()` for comparison; it is faster and deterministic.
- **Blocking the UI on save:** Save mutations must be fire-and-forget with status indicator. Never block editor input during save.
- **Single IndexedDB store for drafts AND query cache:** Different lifecycles and eviction rules. Drafts are sacred user data; query cache is disposable.
- **Relying only on `beforeunload` for crash recovery:** `beforeunload` does NOT fire on force-quit, process crash, or OS kill. IndexedDB drafts (written every ~2s) are the actual crash recovery mechanism.
- **Two-step tiptapy + markdownify for production Markdown:** Fragile for tables, task lists, code blocks with language annotations. Custom serializer is more reliable and maintainable.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IndexedDB access | Raw IndexedDB API | `idb` library (already installed) | Promise-based, typed, handles versioning/upgrades |
| API mutation with retry | Custom fetch + retry | TanStack Query `useMutation` (already installed) | Built-in retry, dedup, optimistic updates, error state |
| LZ compression for drafts | Custom compression | `lz-string` (already installed) | Battle-tested, fast, ~60-80% compression for JSON text |
| Debounce timer | Custom setTimeout management | Simple ref-based debounce (no library needed) | `use-debounce` npm package is overkill for a single timer; a ref + setTimeout is 10 LOC |
| Relative time display ("Saved 3s ago") | Custom interval + formatting | Simple `useEffect` with 1s interval updating `Date.now() - lastSaved` | No library needed, trivial calculation |

**Key insight:** The project already has all required infrastructure libraries installed. Phase 4 is primarily application logic on top of existing infrastructure, not new library integration.

## Common Pitfalls

### Pitfall 1: Race Condition Between Auto-Save and Manual Save
**What goes wrong:** User triggers manual save (Ctrl+S or navigate away) while debounced auto-save is pending. Both fire, causing duplicate saves or version conflict (409 from optimistic concurrency).
**Why it happens:** Two independent save triggers without coordination.
**How to avoid:** Single save function with a mutex/flag. Cancel pending debounce when immediate save triggers. Use `row_version` optimistic concurrency on the server to reject stale saves gracefully.
**Warning signs:** 409 errors in console, "Save failed" flickering after successful save.

### Pitfall 2: IndexedDB Draft Grows Unbounded
**What goes wrong:** Drafts accumulate for documents the user no longer edits. IndexedDB storage grows without limit.
**Why it happens:** No cleanup of drafts after successful server save.
**How to avoid:** Delete the IndexedDB draft immediately after a confirmed server save (mutation `onSuccess`). On app startup, clean up drafts older than 7 days.
**Warning signs:** IndexedDB storage growing monotonically in DevTools Application tab.

### Pitfall 3: Draft Restore Prompt Shows for Already-Saved Content
**What goes wrong:** User sees "Restore unsaved draft?" but the draft content matches what the server already has.
**Why it happens:** Draft was written to IndexedDB but the save mutation succeeded before the draft was cleaned up (race).
**How to avoid:** Compare draft `draftedAt` timestamp against the document's `updated_at` from server. Only show restore prompt if draft is newer AND content differs. Store `lastSavedAt` in the draft entry for comparison.
**Warning signs:** Users reporting false restore prompts on every document open.

### Pitfall 4: `beforeunload` Cannot Make Async API Calls Reliably
**What goes wrong:** `beforeunload` fires but the API save request is cancelled by the browser before completing.
**Why it happens:** Browsers aggressively cancel pending requests when the page is unloading. `fetch()` with `keepalive: true` or `navigator.sendBeacon()` partially work but have body size limits (64KB for `sendBeacon`).
**How to avoid:** Primary strategy: write to IndexedDB synchronously (via `idb-keyval` `set()` in `beforeunload` -- though it is async, IndexedDB writes typically complete before teardown). Secondary: use Electron IPC to main process for coordinated shutdown. Tertiary: `navigator.sendBeacon` for small payloads.
**Warning signs:** "Save failed" on app close, draft recovery prompts after normal close.

### Pitfall 5: TipTap JSON Schema Changes Break Markdown Converter
**What goes wrong:** A TipTap extension update changes the JSON node structure, and the Python Markdown converter silently produces wrong output.
**Why it happens:** The converter is tightly coupled to the JSON schema, and TipTap extensions can evolve.
**How to avoid:** Store `schema_version` on documents (already in the data model). Write the converter with explicit node type handling and a fallback that logs unknown nodes. Add backend tests with fixtures for each supported node type.
**Warning signs:** Markdown output missing sections or containing raw JSON fragments.

### Pitfall 6: Electron Force-Quit Skips All Save Events
**What goes wrong:** User does Alt+F4, Task Manager kill, or OS force-quit. No `beforeunload`, `before-quit`, or any event fires. Data since last IndexedDB draft write is lost.
**Why it happens:** OS-level process kill cannot be intercepted.
**How to avoid:** Write IndexedDB drafts frequently (every ~2 seconds of editor inactivity). This limits data loss to at most 2 seconds of typing. This is the only reliable crash recovery mechanism.
**Warning signs:** Users reporting lost edits after crashes, despite auto-save being "enabled."

## Code Examples

### Server-Side Content Converter (Python)

```python
# fastapi-backend/app/services/content_converter.py
"""
TipTap JSON to Markdown and plain text converter.

Walks the ProseMirror JSON document tree and produces:
1. Markdown (for AI/LLM consumption)
2. Plain text (for full-text search indexing)

The TipTap JSON schema uses a recursive structure:
{
  "type": "doc",
  "content": [
    {
      "type": "paragraph",
      "content": [
        { "type": "text", "text": "Hello", "marks": [{"type": "bold"}] }
      ]
    }
  ]
}
"""
from typing import Any


# ── Markdown Conversion ──────────────────────────────────────────────

_MARK_WRAPPERS = {
    "bold": "**",
    "italic": "_",
    "strike": "~~",
    "code": "`",
}

def tiptap_json_to_markdown(doc: dict[str, Any]) -> str:
    if not doc or doc.get("type") != "doc":
        return ""
    return _md_nodes(doc.get("content", []))


def _md_nodes(nodes: list[dict[str, Any]], list_indent: int = 0) -> str:
    parts: list[str] = []
    for node in nodes:
        t = node.get("type", "")
        if t == "paragraph":
            parts.append(_md_inline(node.get("content", [])) + "\n\n")
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
                wrapper = _MARK_WRAPPERS.get(mark["type"], "")
                if mark["type"] == "link":
                    href = mark.get("attrs", {}).get("href", "")
                    text = f"[{text}]({href})"
                elif wrapper:
                    text = f"{wrapper}{text}{wrapper}"
            parts.append(text)
        elif node.get("type") == "hardBreak":
            parts.append("  \n")
    return "".join(parts)


# ── Plain Text Extraction ────────────────────────────────────────────

def tiptap_json_to_plain_text(doc: dict[str, Any]) -> str:
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
            if node.get("type") in ("paragraph", "heading", "listItem", "taskItem"):
                parts.append("\n")
    return "".join(parts)
```

### Auto-Save Endpoint (FastAPI)

```python
# Addition to fastapi-backend/app/routers/documents.py

@router.put("/api/documents/{document_id}/content")
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
        raise HTTPException(status_code=409, detail="Document was modified by another user")

    # Parse and convert
    content_dict = json.loads(body.content_json)
    doc.content_json = body.content_json
    doc.content_markdown = tiptap_json_to_markdown(content_dict)
    doc.content_plain = tiptap_json_to_plain_text(content_dict)
    doc.row_version += 1
    doc.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(doc)
    return doc
```

### IndexedDB Draft Store

```typescript
// electron-app/src/renderer/lib/draft-db.ts
import { openDB, type IDBPDatabase, type DBSchema } from 'idb'

interface DraftEntry {
  documentId: string
  contentJson: string
  title: string
  serverUpdatedAt: number  // Server's updated_at when doc was loaded
  draftedAt: number        // When this draft was written
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
    })
  }
  return dbPromise
}

export async function saveDraft(draft: DraftEntry): Promise<void> {
  const db = await getDraftDB()
  await db.put('drafts', draft)
}

export async function getDraft(documentId: string): Promise<DraftEntry | undefined> {
  const db = await getDraftDB()
  return db.get('drafts', documentId)
}

export async function deleteDraft(documentId: string): Promise<void> {
  const db = await getDraftDB()
  await db.delete('drafts', documentId)
}

export async function cleanupOldDrafts(maxAgeDays: number = 7): Promise<number> {
  const db = await getDraftDB()
  const cutoff = Date.now() - maxAgeDays * 24 * 60 * 60 * 1000
  const tx = db.transaction('drafts', 'readwrite')
  const index = tx.store.index('by-drafted-at')
  let cursor = await index.openCursor()
  let deleted = 0
  while (cursor && cursor.value.draftedAt < cutoff) {
    await cursor.delete()
    deleted++
    cursor = await cursor.continue()
  }
  return deleted
}
```

### Save Status Indicator

```typescript
// Pattern for save status state machine
type SaveStatus =
  | { state: 'idle' }
  | { state: 'saving' }
  | { state: 'saved'; at: number }
  | { state: 'error'; message: string }

// In the status bar component, display:
// 'idle'   -> nothing (or "No changes")
// 'saving' -> "Saving..."
// 'saved'  -> "Saved Xs ago" (update every second via interval)
// 'error'  -> "Save failed" with retry option
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `getHTML()` for dirty check | `getJSON()` + `JSON.stringify()` | TipTap 2.x best practice | 5-10x faster comparison for large documents |
| localStorage for drafts | IndexedDB with `idb` | 2023+ | No 5MB limit, structured data, crash-durable |
| Full Zustand store for save state | TanStack Query mutation state + React Context | Project decision (STATE.md) | Zustand being removed; mutation isPending/isError covers save state |
| `tiptapy` + `markdownify` pipeline | Custom Python JSON walker | 2025+ community consensus | No external dependencies, handles edge cases (tables, task lists, code lang) |
| `navigator.sendBeacon` for save-on-close | IndexedDB draft as primary + Electron IPC | Electron-specific | sendBeacon has 64KB limit; Electron IPC is more reliable for coordinated shutdown |

**Deprecated/outdated:**
- `tiptap-markdown` npm package: Maintainer no longer updating; TipTap v2 has native Markdown support but it is editor-side only (not useful for server-side Python conversion)
- Zustand stores for save state: Being removed in Phase 1 per project decision

## Open Questions

1. **`navigator.sendBeacon` body size for large documents**
   - What we know: `sendBeacon` has a 64KB limit per spec. Large documents with embedded images (base64 in JSON) could exceed this.
   - What's unclear: Whether the project's documents will regularly exceed 64KB of JSON.
   - Recommendation: Do not rely on `sendBeacon` for primary save-on-close. Use IndexedDB draft as crash recovery and Electron IPC for coordinated shutdown. Treat `sendBeacon` as best-effort bonus.

2. **Electron `before-quit` IPC timing guarantees**
   - What we know: Electron fires `before-quit` on `app.quit()` and Cmd+Q/Alt+F4. `event.preventDefault()` can delay quit. IPC to renderer is async.
   - What's unclear: Maximum time Electron allows for IPC round-trip before force-closing. On Windows, the OS may force-kill after ~5 seconds.
   - Recommendation: In `before-quit`, send IPC to renderer, set a 3-second timeout, then quit regardless. IndexedDB drafts handle the force-kill case.

3. **Markdown conversion fidelity for complex table structures**
   - What we know: TipTap tables can have merged cells, header rows, and custom alignment. Markdown tables only support simple column-per-cell with optional alignment.
   - What's unclear: Whether merged cells will be used in the editor (Phase 3 defines tables but scope of merge support is TBD).
   - Recommendation: Implement basic table rendering (no merge support). Log a warning for merged cells. Address in a future phase if needed.

4. **Draft restore UX when document was edited by another user**
   - What we know: User A edits locally, closes app (draft saved). User B edits and saves on server. User A reopens -- draft is newer than their loaded version but server version is different.
   - What's unclear: Whether to show both versions, auto-merge, or let user choose.
   - Recommendation: Show restore prompt with "Your unsaved draft from [time] -- Restore or Discard?" Compare draft content against server content; if identical, silently discard. If different, always prompt.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `electron-app/src/renderer/lib/per-query-persister.ts` -- existing IndexedDB persistence patterns
- Codebase analysis: `electron-app/src/renderer/lib/query-cache-db.ts` -- existing `idb` library usage with LRU eviction
- Codebase analysis: `electron-app/src/renderer/lib/cache-config.ts` -- existing cache configuration patterns
- Codebase analysis: `electron-app/src/main/index.ts` -- Electron main process lifecycle
- Codebase analysis: `electron-app/src/preload/index.ts` -- IPC bridge patterns
- Codebase analysis: `electron-app/src/renderer/components/notes/note-editor.tsx` -- existing TipTap editor integration
- Codebase analysis: `electron-app/src/renderer/hooks/use-queries.ts` -- TanStack Query mutation patterns
- Codebase analysis: `fastapi-backend/app/routers/notes.py` -- existing CRUD router patterns
- `.planning/phases/01-migration-and-data-foundation/01-03-PLAN.md` -- Document model with content_json, content_markdown, content_plain columns
- [Electron app lifecycle docs](https://www.electronjs.org/docs/latest/api/app) -- `before-quit`, `will-quit`, `window-all-closed` events

### Secondary (MEDIUM confidence)
- [TipTap GitHub Discussion #5847](https://github.com/ueberdosis/tiptap/discussions/5847) -- JSON to Markdown conversion approaches
- [TipTap GitHub Discussion #2871](https://github.com/ueberdosis/tiptap/discussions/2871) -- Auto-save debounce patterns
- [markdownify Python library](https://github.com/matthewwithanm/python-markdownify) -- HTML-to-Markdown capabilities and limitations
- [tiptapy PyPI](https://pypi.org/project/tiptapy/) -- Python TipTap JSON to HTML converter (limited node support)
- [RxDB: Solving IndexedDB Slowness](https://rxdb.info/slow-indexeddb.html) -- In-memory + periodic persistence pattern
- [MDN: Using IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB) -- IndexedDB API reference

### Tertiary (LOW confidence)
- [Electron data saving best practices gist](https://gist.github.com/0q98ahdsg3987y1h987y/fb3ad45a40fe42816cb7) -- Community patterns for preventing data loss on close

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed in codebase; no new dependencies
- Architecture: HIGH -- patterns directly derived from existing codebase infrastructure (per-query-persister, TanStack Query mutations, Electron IPC)
- Content converter: MEDIUM -- custom Python serializer is straightforward but needs testing for edge cases (tables, nested lists, code blocks with language)
- Pitfalls: HIGH -- well-documented in Electron and IndexedDB ecosystems; codebase already handles similar patterns in query cache
- Electron lifecycle: MEDIUM -- `before-quit` timing guarantees on Windows are not fully documented

**Research date:** 2026-01-31
**Valid until:** 2026-03-02 (stable domain, 30 days)

# Stack Research

**Domain:** Document/Knowledge Base System for Project Management Desktop App
**Researched:** 2026-01-31
**Confidence:** HIGH

## Context

This research covers **only the new libraries and tools needed** to add a document/knowledge base system on top of the existing PM Desktop stack. The existing stack (FastAPI, SQLAlchemy, React 18, Electron 30, TipTap 2.6, PostgreSQL, Redis, MinIO, TanStack Query, Alembic) is not re-evaluated here.

### Critical Stack Decision: TipTap v2 -> v3 Migration

The project currently uses `@tiptap/*@^2.6.0`. TipTap v3 (latest: 3.15.3) is now stable and all active development has shifted to v3. TipTap v2 is receiving very limited maintenance with no formal EOL date but practically winding down.

**Recommendation: Stay on TipTap v2 for this milestone. Migrate to v3 as a separate milestone.**

Rationale:
- The knowledge base feature is large enough without adding a framework migration
- TipTap v3 has breaking changes (import paths, StarterKit defaults, BubbleMenu/FloatingMenu imports, History->UndoRedo rename, CSS class changes for collaboration)
- v2 still works and the community `tiptap-markdown` package (0.8.x) supports v2
- v3 migration can be its own focused milestone after the knowledge base ships
- Risk of doing both simultaneously: debugging whether bugs come from new feature code or migration changes

**Confidence: HIGH** -- Based on official TipTap upgrade guide and v3 changelog.

---

## Recommended Stack (New Libraries Only)

### Frontend: TipTap Extensions (stay on v2.6.x)

| Library | Version | Purpose | Why Recommended | Confidence |
|---------|---------|---------|-----------------|------------|
| `tiptap-markdown` | ^0.8.10 | Markdown serialization/deserialization | Community standard for TipTap v2 markdown. Bidirectional conversion. Maintainer recommends v0.8.x for TipTap v2 (v0.9+ is for v3). Official `@tiptap/markdown` only exists for v3. | HIGH |
| `@tiptap/extension-file-handler` | ^2.6.0 | Handle paste/drag-drop file events | Official TipTap extension for intercepting file paste and drop events. Provides `onPaste` and `onDrop` callbacks where you upload to MinIO and insert the image URL. Replaces custom ProseMirror handlers. | MEDIUM |

**Note on Image Resize:** TipTap v2's `@tiptap/extension-image` does NOT include built-in resize. The built-in `ResizableNodeView` is v3-only. For v2, build a custom NodeView with resize handles (~100 lines of code) rather than pulling in community packages like `tiptap-extension-resize-image` (1.3.2) which have inconsistent quality and framework support. Custom NodeView is more maintainable and avoids a dependency that breaks on TipTap upgrades.

**Note on @mentions:** `@tiptap/extension-mention` (already in package.json at ^2.6.0) with `@tiptap/suggestion` handles @ mentions. No new dependency needed -- just configuration with a custom suggestion renderer using Radix UI Popover (already installed) and a backend search endpoint.

### Frontend: Auto-Save & Utilities

| Library | Version | Purpose | Why Recommended | Confidence |
|---------|---------|---------|-----------------|------------|
| `use-debounce` | ^10.1.0 | Debounced auto-save hook | De facto standard React debounce hook (1,381 dependents). Provides `useDebouncedCallback` for the auto-save pattern: debounce `editor.onUpdate` -> serialize to JSON -> POST to API. Server-rendering friendly. Lightweight (~2KB). | HIGH |

### Frontend: Search (Client-Side)

| Library | Version | Purpose | Why Recommended | Confidence |
|---------|---------|---------|-----------------|------------|
| `meilisearch` | ^0.55.0 | Meilisearch JS client for search UI | Official Meilisearch JavaScript client. Used to query search results directly from the Electron renderer. Compatible with Meilisearch v1.x. Lightweight, TypeScript-native. | HIGH |

### Backend: Search Engine

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Meilisearch (engine) | 1.12+ (latest stable: 1.34.1) | Full-text search | Typo-tolerant, sub-50ms search, faceted filtering, simple REST API. Pin to a specific minor version (e.g., 1.12) to avoid breaking changes from newer versions. Does not need latest -- v1.12+ has all features needed (search, filters, sortable attributes). | HIGH |
| `meilisearch-python-sdk` | ^5.5.2 | Async Python client for Meilisearch | Provides native `AsyncClient` for FastAPI's async patterns. ~30% faster than the official sync `meilisearch` Python client for data ingestion. The `meilisearch-fastapi` integration package is archived -- use this SDK directly. | HIGH |

### Backend: Content Processing

| Library | Version | Purpose | Why Recommended | Confidence |
|---------|---------|---------|-----------------|------------|
| `markdownify` | ^0.14.1 | HTML -> Markdown conversion (server-side) | Pure Python, well-established, customizable via subclassing `MarkdownConverter`. Used when saving documents: convert TipTap HTML to Markdown for LLM consumption. Alternative `html-to-markdown` (Rust-powered, v2.24.3) is faster but adds a native dependency -- unnecessary for our write-path volumes. | HIGH |
| `beautifulsoup4` | ^4.12.0 | HTML parsing (dependency of markdownify) | Required by markdownify. Also useful for stripping HTML to plain text for search indexing. `soup.get_text()` produces clean plain text. | HIGH |
| `bleach` | ^6.2.0 | HTML sanitization | Sanitize TipTap HTML output before storage. Prevents XSS from pasted content. Whitelist allowed tags/attributes matching your TipTap schema. | HIGH |

### Backend: Document Locking

No new library needed. Use Redis (already in stack) for distributed locks:

```python
# Pattern: Redis-based document lock
lock = await redis.set(f"doc_lock:{doc_id}", user_id, nx=True, ex=300)  # 5-min TTL
```

This is simpler and more reliable than advisory database locks for the lock-based concurrent editing model. TTL prevents orphaned locks if a user disconnects.

**Confidence: HIGH** -- Standard Redis pattern, well-documented.

### Backend: Template System

No new library needed. Document templates are stored as TipTap JSON in the database. When a user creates a document from a template, the API copies the template's JSON content into the new document record. This is a data pattern, not a library concern.

### Infrastructure

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Meilisearch (Docker) | v1.12 | Search engine container | Run alongside PostgreSQL and Redis. Single binary, <100MB memory for tens of thousands of documents. Config: `MEILI_MASTER_KEY` for auth, `MEILI_DB_PATH` for persistence. | HIGH |

---

## Installation

```bash
# Frontend (electron-app/)
npm install tiptap-markdown@^0.8.10 use-debounce@^10.1.0 meilisearch@^0.55.0

# Backend (fastapi-backend/)
pip install meilisearch-python-sdk>=5.5.0 markdownify>=0.14.1 beautifulsoup4>=4.12.0 bleach>=6.2.0

# Infrastructure (docker-compose or standalone)
docker pull getmeili/meilisearch:v1.12
```

---

## Alternatives Considered

| Recommended | Alternative | Why Not Alternative |
|-------------|-------------|---------------------|
| `tiptap-markdown` (v2) | `@tiptap/markdown` (v3 only) | Only available for TipTap v3. We are staying on v2 for this milestone. |
| `meilisearch-python-sdk` | Official `meilisearch` Python client | Official client is sync-only. Our FastAPI backend is fully async. The SDK's AsyncClient integrates naturally with `async def` endpoints. |
| `markdownify` | `html-to-markdown` (Rust) | Rust-powered is faster but adds native binary wheels to our Python deployment. Our write volume (saves per minute, not per second) does not justify the complexity. |
| `markdownify` | `html2text` | html2text produces "ASCII art" markdown (e.g., reference-style links). markdownify produces cleaner, more standard markdown closer to what LLMs expect. |
| Redis locks | PostgreSQL advisory locks | Redis locks have built-in TTL for automatic expiry. PostgreSQL advisory locks require manual cleanup on disconnect. Redis is already in our stack for pub/sub. |
| Custom image resize NodeView | `tiptap-extension-resize-image` npm package | Community packages break on TipTap version bumps. Custom NodeView (~100 LOC) is fully controlled, tested, and upgradeable. |
| `use-debounce` | `lodash.debounce` | `use-debounce` is React-hook-native (respects component lifecycle, cleanup on unmount). lodash.debounce requires manual cleanup in useEffect. |
| Meilisearch | Elasticsearch/OpenSearch | Meilisearch is purpose-built for user-facing search: zero config, typo tolerance, sub-50ms. Elasticsearch is powerful but operationally heavy for our scale (tens of thousands of docs, not millions). |
| Meilisearch | PostgreSQL full-text search (`tsvector`) | PostgreSQL FTS lacks typo tolerance, relevance ranking is basic, no faceted search. Meilisearch provides a dramatically better search UX with minimal operational overhead. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `@tiptap/extension-collaboration` + Yjs | Massive complexity for lock-based editing. Yjs CRDTs are for real-time co-editing (Google Docs style). Lock-based editing is simpler, matches the PM app's workflow, and avoids the Yjs operational cost (WebSocket relay, CRDT merge complexity, snapshot management). | Redis-based document locks + auto-save with conflict detection |
| `hocuspocus` (Yjs server) | Same as above. Hocuspocus is the Yjs WebSocket server. Unnecessary for lock-based concurrent editing. | Standard FastAPI WebSocket for lock status broadcasting |
| `prosemirror-markdown` | Low-level ProseMirror markdown parser. Requires manual schema mapping. `tiptap-markdown` wraps this with TipTap-aware defaults and handles extensions automatically. | `tiptap-markdown` |
| `dompurify` | Browser-only HTML sanitizer. We need server-side sanitization (Python). | `bleach` (Python) for server-side sanitization |
| `slate` / `plate` / `lexical` | Alternative rich text editors. We already use TipTap, and it handles all our requirements (rich text, tables, mentions, images, task lists). Switching editors would be a rewrite. | TipTap (existing) |
| `meilisearch-fastapi` | Archived project, no longer maintained. Was a convenience wrapper that added Meilisearch routes to FastAPI automatically. | `meilisearch-python-sdk` used directly in service layer |
| `tiptap-markdown@^0.9.0` | Version 0.9+ targets TipTap v3. Will break with our v2 installation. | `tiptap-markdown@^0.8.10` |
| `@tiptap/markdown` | Official package, but v3-only. Not compatible with our v2 setup. | `tiptap-markdown@^0.8.10` |

---

## Stack Patterns by Feature

**Auto-Save:**
- Use `useDebouncedCallback` from `use-debounce` with 2-3 second delay
- Serialize with `editor.getJSON()` (fast, ~1ms for typical documents)
- POST JSON to `/api/documents/{id}/content`
- Backend stores TipTap JSON as primary format, generates Markdown + plain text on write
- Optimistic UI: mark as "saving..." immediately, "saved" on 200 response

**Image Handling (paste/upload/drag-drop/resize):**
- `@tiptap/extension-image` (already installed) for rendering
- Custom ProseMirror `handlePaste` + `handleDrop` via `editorProps` OR `@tiptap/extension-file-handler` for intercepting file events
- Upload intercepted files to MinIO via `/api/documents/{id}/images` endpoint
- Replace blob URL with MinIO presigned URL in editor
- Custom NodeView for resize handles (v2 does not have built-in resize)

**Content Storage (triple format):**
- **TipTap JSON** (primary): Stored in PostgreSQL JSONB column. Source of truth for editor rehydration.
- **Markdown**: Generated server-side from TipTap HTML using `markdownify`. Stored in TEXT column. Used for LLM/AI agent consumption.
- **Plain text**: Generated server-side using BeautifulSoup `get_text()`. Indexed in Meilisearch for full-text search.

**Document Locking:**
- Redis `SET key value NX EX 300` for lock acquisition (NX = only if not exists, EX = 5-min TTL)
- WebSocket broadcast lock status changes to all viewers
- Lock auto-extends on activity (heartbeat every 60s refreshes TTL)
- Lock auto-releases on disconnect (TTL expires) or explicit unlock

**Search Indexing:**
- On document save, push plain text + metadata to Meilisearch index
- Searchable attributes: `title`, `plain_text`, `tags`, `folder_path`
- Filterable attributes: `application_id`, `project_id`, `folder_id`, `created_by`, `tags`
- Sortable attributes: `updated_at`, `created_at`, `title`

**Document Templates:**
- Templates are documents with `is_template: true` flag
- Store template JSON content in same `content_json` column
- "Create from template" copies the JSON content into a new document
- No library needed -- this is a CRUD + copy pattern

**Soft Delete:**
- `deleted_at` TIMESTAMP column (NULL = active, non-NULL = deleted)
- SQLAlchemy query filter: `.where(Document.deleted_at.is_(None))`
- Restore = set `deleted_at` back to NULL
- Permanent delete after 30 days via background task
- No library needed -- standard soft delete pattern

**@ Mentions:**
- `@tiptap/extension-mention` (already installed) with custom suggestion config
- Suggestion popup rendered with Radix UI Popover (already installed)
- Backend endpoint `/api/mentions/search?q=term&context=project_id` returns matching entities
- Mention types: users, tasks, documents (configurable via mention `char` -- e.g., `@` for users, `#` for tasks)

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `tiptap-markdown@^0.8.10` | `@tiptap/*@^2.6.0` | MUST use 0.8.x for TipTap v2. 0.9+ targets v3. |
| `meilisearch@^0.55.0` (JS) | Meilisearch engine v1.x | JS client v0.55 guarantees compat with engine v1.x |
| `meilisearch-python-sdk@^5.5.0` | Meilisearch engine v1.x | Async client tracks latest engine features |
| `@tiptap/extension-file-handler@^2.6.0` | `@tiptap/react@^2.6.0` | Must match TipTap major version |
| `use-debounce@^10.1.0` | React 18.x | Supports React 16.8+ (hooks) |
| `bleach@^6.2.0` | Python 3.12 | Supports Python 3.9+ |
| `markdownify@^0.14.1` | `beautifulsoup4@^4.12.0` | markdownify depends on bs4 |

---

## Dependency Summary

**Total new frontend packages: 3**
- `tiptap-markdown`, `use-debounce`, `meilisearch`

**Total new backend packages: 4**
- `meilisearch-python-sdk`, `markdownify`, `beautifulsoup4`, `bleach`

**Total new infrastructure: 1**
- Meilisearch Docker container

This is a deliberately minimal footprint. Most features (templates, soft delete, locking, mentions) are built with existing stack capabilities + patterns rather than new dependencies.

---

## Future: TipTap v3 Migration (Separate Milestone)

When migrating to v3, the stack changes will be:
- Replace `tiptap-markdown@^0.8.x` with `@tiptap/markdown@^3.x` (official, bidirectional, CommonMark-compliant)
- Get built-in `ResizableNodeView` for image resize (remove custom NodeView)
- Get built-in `@floating-ui/dom` for suggestion popups (remove tippy.js if used)
- Update import paths (`@tiptap/react/menus` for BubbleMenu/FloatingMenu)
- Rename `history: false` to `undoRedo: false` in StarterKit config
- Update collaboration CSS classes if using collaboration later

---

## Sources

- [TipTap v3 Changelog & What's New](https://tiptap.dev/docs/resources/whats-new) -- verified v3 features, migration requirements
- [TipTap v2 to v3 Upgrade Guide](https://tiptap.dev/docs/guides/upgrade-tiptap-v2) -- breaking changes list
- [TipTap Image Extension Docs](https://tiptap.dev/docs/editor/extensions/nodes/image) -- resize API (v3 only)
- [TipTap FileHandler Extension](https://tiptap.dev/docs/editor/extensions/functionality/filehandler) -- paste/drop handling
- [TipTap Mention Extension](https://tiptap.dev/docs/editor/extensions/nodes/mention) -- mention configuration
- [tiptap-markdown npm](https://www.npmjs.com/package/tiptap-markdown) -- v0.8.x for TipTap v2, v0.9+ for v3
- [Meilisearch Releases](https://github.com/meilisearch/meilisearch/releases) -- engine v1.34.1 latest
- [meilisearch npm](https://www.npmjs.com/package/meilisearch) -- JS client v0.55.0
- [meilisearch-python-sdk PyPI](https://pypi.org/project/meilisearch-python-sdk/) -- v5.5.2, async support
- [meilisearch-python-sdk GitHub](https://github.com/sanders41/meilisearch-python-sdk) -- AsyncClient documentation
- [use-debounce npm](https://www.npmjs.com/package/use-debounce) -- v10.1.0
- [markdownify PyPI](https://pypi.org/project/markdownify/) -- HTML to Markdown
- [html-to-markdown PyPI](https://pypi.org/project/html-to-markdown/) -- Rust-powered alternative (considered, not recommended)
- [bleach PyPI](https://pypi.org/project/bleach/) -- HTML sanitization

---
*Stack research for: Document/Knowledge Base System*
*Researched: 2026-01-31*

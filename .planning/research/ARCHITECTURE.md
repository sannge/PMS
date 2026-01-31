# Architecture Research: Document/Knowledge Base System

**Domain:** Document management within an existing PM desktop application
**Researched:** 2026-01-31
**Confidence:** HIGH (based on direct codebase analysis of existing patterns)

## System Overview

```
+------------------------------------------------------------------+
|                     Electron App (Frontend)                       |
|  +------------------+  +------------------+  +-----------------+  |
|  | KnowledgeTree    |  | DocumentEditor   |  | DocumentSearch  |  |
|  | (folder/doc nav) |  | (TipTap + save)  |  | (search UI)     |  |
|  +--------+---------+  +--------+---------+  +--------+--------+  |
|           |                     |                      |          |
|  +--------+---------------------+----------------------+--------+ |
|  |               Zustand Store: useDocumentStore                | |
|  +--------+---------------------+----------------------+--------+ |
|           |                     |                      |          |
|  +--------+---------------------+----------------------+--------+ |
|  |          TanStack Query + IndexedDB Persistence              | |
|  +--------+---------------------+----------------------+--------+ |
|           |                     |                      |          |
+-----------+---------------------+----------------------+----------+
            |                     |                      |
+-----------+---------------------+----------------------+----------+
|                     FastAPI Backend                               |
|  +------------------+  +------------------+  +-----------------+  |
|  | documents router |  | folders router   |  | search router   |  |
|  +--------+---------+  +--------+---------+  +--------+--------+  |
|           |                     |                      |          |
|  +--------+---------------------+----------------------+--------+ |
|  |                    Service Layer                              | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  |  | document_service |  | lock_service     |  | search_svc  | | |
|  |  +------------------+  +------------------+  +-------------+ | |
|  +--------+---------------------+----------------------+--------+ |
|           |                     |                      |          |
|  +--------+--------+  +--------+--------+  +---------+--------+  |
|  | SQLAlchemy/MSSQL |  | Redis (locks,   |  | Meilisearch     |  |
|  | (Documents,      |  |  presence,       |  | (full-text      |  |
|  |  Folders, Tags)  |  |  pub/sub)        |  |  search index)  |  |
|  +------------------+  +-----------------+  +-----------------+  |
|                                                                   |
|  +-----------------+  +-----------------+                         |
|  | MinIO           |  | WebSocket Mgr   |                        |
|  | (images/files)  |  | (lock status,   |                        |
|  +-----------------+  |  save notifs)   |                        |
|                       +-----------------+                         |
+-------------------------------------------------------------------+
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| **KnowledgeTree** (FE) | Folder/document tree navigation, drag-drop reorder | useDocumentStore, folders API |
| **DocumentEditor** (FE) | TipTap rich-text editing, auto-save debounce, lock UI | useDocumentStore, documents API, WebSocket |
| **DocumentSearch** (FE) | Full-text search UI, result rendering | search API |
| **useDocumentStore** (FE) | Client state: open tabs, active doc, tree state, lock status | TanStack Query, WebSocket hooks |
| **documents router** (BE) | CRUD endpoints, auto-save endpoint, lock acquire/release | document_service, lock_service |
| **folders router** (BE) | Folder CRUD, tree query, reorder | document_service |
| **document_service** (BE) | Business logic: permissions, content pipeline, markdown gen | DB, MinIO, Meilisearch, Redis |
| **lock_service** (BE) | Lock acquire/release/heartbeat, expiry cleanup | Redis, WebSocket manager |
| **search_service** (BE) | Index documents, query Meilisearch | Meilisearch, DB |
| **WebSocket integration** (BE) | Broadcast lock status changes, save notifications | Existing ConnectionManager + Redis pub/sub |

## Recommended Project Structure

### Backend additions

```
fastapi-backend/app/
├── models/
│   ├── document.py           # Document model
│   ├── document_folder.py    # DocumentFolder model
│   └── document_tag.py       # DocumentTag + DocumentTagAssignment models
├── schemas/
│   ├── document.py           # Document Pydantic schemas
│   └── document_folder.py    # Folder Pydantic schemas
├── routers/
│   ├── documents.py          # Document CRUD + auto-save + lock endpoints
│   └── document_folders.py   # Folder CRUD + tree endpoints
├── services/
│   ├── document_service.py   # Document business logic + content pipeline
│   ├── document_lock_service.py  # Redis-based lock management
│   └── document_search_service.py # Meilisearch indexing + querying
└── websocket/
    └── manager.py            # Add DOCUMENT_LOCKED/UNLOCKED/SAVED message types
```

### Frontend additions

```
electron-app/src/renderer/
├── components/
│   └── knowledge/
│       ├── KnowledgeTree.tsx         # Tree sidebar component
│       ├── FolderNode.tsx            # Folder tree node
│       ├── DocumentNode.tsx          # Document tree node
│       ├── DocumentEditor.tsx        # TipTap editor with auto-save
│       ├── DocumentEditorToolbar.tsx  # Formatting toolbar
│       ├── DocumentLockBanner.tsx    # Lock status indicator
│       ├── DocumentSearch.tsx        # Search panel
│       ├── TemplateSelector.tsx      # Template picker dialog
│       └── ImageUploader.tsx         # Image upload for TipTap
├── hooks/
│   ├── use-documents.ts      # TanStack Query hooks for documents
│   ├── use-document-folders.ts # TanStack Query hooks for folders
│   ├── use-document-lock.ts  # Lock acquire/release/heartbeat hook
│   └── use-document-search.ts # Search query hook
└── stores/
    └── document-store.ts     # Zustand store for UI state (tabs, active doc)
```

### Structure Rationale

- **Separate `document_lock_service.py`:** Lock logic is Redis-heavy and distinct from CRUD business logic. Isolating it makes testing and reasoning about lock behavior simpler.
- **`knowledge/` component folder:** Groups all knowledge-base UI together, consistent with existing component organization patterns.
- **Separate hooks per concern:** Follows the existing pattern (`use-comments.ts`, `use-checklists.ts`, `use-attachments.ts`) -- one hook file per backend domain.

## Architectural Patterns

### Pattern 1: Scope Columns (Not Polymorphic FK)

**What:** Use explicit nullable scope columns (`application_id`, `project_id`, `user_id`) with a CHECK constraint ensuring exactly one is non-null, rather than a polymorphic FK pattern (`scope_type` + `scope_id`).

**When to use:** When the number of scopes is known and small (3 in this case: personal, application, project).

**Trade-offs:**
- Pro: Type-safe foreign keys with referential integrity
- Pro: Efficient indexed queries per scope (`WHERE application_id = X`)
- Pro: Consistent with existing codebase patterns (Attachment model uses direct FKs for each entity type)
- Con: Adding a 4th scope means a migration to add a column

**Example:**
```python
class Document(Base):
    __tablename__ = "Documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Scope: exactly one of these must be non-null
    application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("Projects.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="CASCADE"), nullable=True, index=True)  # personal docs

    # CHECK constraint: exactly one scope is set
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_document_single_scope"
        ),
    )
```

**Why not polymorphic FK:** The existing Attachment model already uses the direct FK pattern (separate `task_id`, `note_id`, `comment_id` columns). Following this established pattern keeps the codebase consistent. Polymorphic FKs (`scope_type` + `scope_id`) lose referential integrity and require application-level validation.

### Pattern 2: Redis-Based Document Locking

**What:** Use Redis SET with NX (set-if-not-exists) and EX (expiry) for distributed document locks. The lock holder sends periodic heartbeats to extend TTL. If a client crashes, the lock auto-expires.

**When to use:** Any time you need single-writer semantics with automatic recovery from crashes, at scale (5K concurrent users).

**Trade-offs:**
- Pro: Lock acquire is O(1) and atomic
- Pro: Automatic expiry handles crashed clients without cleanup jobs
- Pro: Uses existing Redis infrastructure (already deployed for WebSocket pub/sub)
- Pro: No DB write contention for lock operations
- Con: Redis is not strictly CP (split-brain could theoretically allow dual locks, but Redlock is overkill for document editing)

**Example:**
```python
class DocumentLockService:
    LOCK_TTL = 120  # seconds
    HEARTBEAT_INTERVAL = 30  # seconds (client sends every 30s)
    LOCK_PREFIX = "doc:lock:"

    async def acquire(self, doc_id: UUID, user_id: UUID) -> bool:
        key = f"{self.LOCK_PREFIX}{doc_id}"
        value = json.dumps({"user_id": str(user_id), "acquired_at": time.time()})
        result = await redis_service.client.set(key, value, nx=True, ex=self.LOCK_TTL)
        return result is not None

    async def heartbeat(self, doc_id: UUID, user_id: UUID) -> bool:
        key = f"{self.LOCK_PREFIX}{doc_id}"
        current = await redis_service.get_json(key)
        if current and current["user_id"] == str(user_id):
            await redis_service.client.expire(key, self.LOCK_TTL)
            return True
        return False

    async def release(self, doc_id: UUID, user_id: UUID) -> bool:
        key = f"{self.LOCK_PREFIX}{doc_id}"
        # Lua script for atomic check-and-delete
        script = "if redis.call('get', KEYS[1]) then local d = cjson.decode(redis.call('get', KEYS[1])) if d.user_id == ARGV[1] then return redis.call('del', KEYS[1]) end end return 0"
        result = await redis_service.client.eval(script, 1, key, str(user_id))
        return result == 1
```

### Pattern 3: Debounced Auto-Save with Versioned Content

**What:** Client debounces TipTap content changes (2-3 second delay), then sends the full TipTap JSON to a dedicated auto-save endpoint. Server stores content, bumps `row_version`, generates markdown asynchronously, and broadcasts save confirmation via WebSocket.

**When to use:** Any document editing scenario where you want auto-save without overwhelming the server.

**Trade-offs:**
- Pro: Simple mental model -- last write wins within a locked document
- Pro: 2-3s debounce means at most 1 save every 2-3s per document
- Pro: `row_version` enables optimistic concurrency detection if needed later
- Con: Full document sent on each save (not delta). For documents under 1MB this is fine; for huge docs, consider delta-only saves later.

**Data flow:**
```
User types in TipTap
    |
    v (onChange every keystroke)
Debounce timer (2s)
    |
    v (timer fires)
POST /api/documents/{id}/content
  body: { content_json: {...}, row_version: N }
    |
    v
Backend:
  1. Verify lock ownership
  2. Update content_json in DB
  3. Bump row_version to N+1
  4. Queue markdown generation (background task)
  5. Broadcast "document_saved" to document room via WebSocket
    |
    v
Frontend receives WS "document_saved":
  - Update row_version in local state
  - Show "saved" indicator
```

### Pattern 4: Folder Tree with Materialized Path

**What:** Each folder stores a `path` column containing its full ancestry path (e.g., `/root-id/parent-id/self-id`). Tree queries use `LIKE 'path%'` for subtree fetching. Order within a folder uses `sort_order` integer.

**When to use:** When you need efficient subtree queries and the tree is read-heavy (which knowledge base trees are).

**Trade-offs:**
- Pro: Single query fetches entire subtree: `WHERE path LIKE '/root-id/%'`
- Pro: Depth calculation is trivial: count separators in path
- Pro: Moving a subtree is one UPDATE with string replacement
- Con: Path column length limits very deep nesting (use VARCHAR(2000) -- sufficient for 30+ levels of UUID-based paths)
- Con: Moving a folder requires updating all descendant paths (but this is rare)

**Example:**
```python
class DocumentFolder(Base):
    __tablename__ = "DocumentFolders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("DocumentFolders.id", ondelete="CASCADE"), nullable=True, index=True)
    path = Column(String(2000), nullable=False, index=True)  # materialized path
    sort_order = Column(Integer, nullable=False, default=0)

    # Scope columns (same pattern as Document)
    application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("Projects.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="CASCADE"), nullable=True, index=True)
```

## Data Flow

### Auto-Save Flow (Primary Data Path)

```
[User types]
    |
    v
[TipTap onChange] --> [Debounce 2s] --> [useDocumentAutoSave hook]
    |                                         |
    v                                         v
[Local state updated]                  POST /api/documents/{id}/content
                                              |
                                              v
                                       [document_service]
                                              |
                               +--------------+--------------+
                               |              |              |
                               v              v              v
                        [Update DB]   [Queue markdown]  [Broadcast WS]
                        (content_json, (BackgroundTask)  (doc:saved)
                         row_version)       |
                                            v
                                    [Update markdown_content]
                                    [Update Meilisearch index]
```

### Lock Acquisition Flow

```
[User opens document for edit]
    |
    v
POST /api/documents/{id}/lock
    |
    v
[lock_service.acquire(doc_id, user_id)]
    |
    +-- Redis SET doc:lock:{id} NX EX 120
    |
    v (success)
[Return lock token + broadcast "document_locked" to document room]
    |
    v
[Frontend: start heartbeat interval (every 30s)]
    |
    v
PUT /api/documents/{id}/lock/heartbeat (every 30s)
    |
    v
[Redis EXPIRE doc:lock:{id} 120]
```

### Image Upload Flow

```
[User pastes/drags image into TipTap]
    |
    v
[ImageUploader component intercepts]
    |
    v
POST /api/documents/{doc_id}/images
  multipart/form-data: { file: binary }
    |
    v
[document_service]:
  1. Validate file type + size (<10MB)
  2. Generate MinIO key: documents/{doc_id}/{uuid}_{filename}
  3. Upload to MinIO pm-images bucket
  4. Create Attachment record (entity_type='document')
  5. Return { url: presigned_download_url, attachment_id: uuid }
    |
    v
[Frontend: insert TipTap image node with src=presigned_url, data-attachment-id=uuid]
```

### Search Flow

```
[User types in search box]
    |
    v
[Debounce 300ms] --> GET /api/documents/search?q={query}&scope={application_id}
    |
    v
[search_service]:
  1. Query Meilisearch with scope filter
  2. Return document IDs + highlighted snippets
    |
    v
[Frontend: render results with highlights, click navigates to document]
```

### Key Data Flows

1. **Document open:** Frontend fetches document metadata + content via TanStack Query. If editing, acquires lock. TipTap initializes with content_json.
2. **Auto-save:** Debounced content changes POST to backend. Backend writes to DB, generates markdown in background, broadcasts save event.
3. **Lock heartbeat:** Frontend sends heartbeat every 30s while editing. If tab closes without release, Redis TTL expires lock after 120s.
4. **Tree navigation:** Frontend fetches folder tree for the active scope. Lazy-loads children for collapsed folders. Drag-drop reorders folders/documents via PATCH endpoints.
5. **Search indexing:** After each document save, a background task updates the Meilisearch index with the markdown version of the content.

## Database Schema Design

### Core Tables

```
Documents
  id              UUID PK
  folder_id       UUID FK -> DocumentFolders.id (nullable, root docs have no folder)
  application_id  UUID FK -> Applications.id (nullable)
  project_id      UUID FK -> Projects.id (nullable)
  user_id         UUID FK -> Users.id (nullable, personal scope)
  title           VARCHAR(500) NOT NULL
  content_json    NVARCHAR(MAX)          -- TipTap JSON
  markdown_content NVARCHAR(MAX)         -- Generated markdown for search
  is_template     BIT DEFAULT 0          -- Templates are just docs with this flag
  template_scope  VARCHAR(20)            -- 'builtin', 'application', 'personal'
  created_by      UUID FK -> Users.id
  last_edited_by  UUID FK -> Users.id
  row_version     INT DEFAULT 1
  word_count      INT DEFAULT 0
  created_at      DATETIME2
  updated_at      DATETIME2
  archived_at     DATETIME2 (nullable)
  CHECK: exactly one of application_id, project_id, user_id is non-null (unless is_template=1 AND template_scope='builtin')

DocumentFolders
  id              UUID PK
  parent_id       UUID FK -> DocumentFolders.id (nullable, root folders)
  application_id  UUID FK -> Applications.id (nullable)
  project_id      UUID FK -> Projects.id (nullable)
  user_id         UUID FK -> Users.id (nullable)
  name            VARCHAR(255) NOT NULL
  path            VARCHAR(2000) NOT NULL  -- materialized path
  sort_order      INT DEFAULT 0
  icon            VARCHAR(50) (nullable)  -- optional custom icon
  created_by      UUID FK -> Users.id
  created_at      DATETIME2
  updated_at      DATETIME2
  CHECK: exactly one scope column is non-null

DocumentTags
  id              UUID PK
  application_id  UUID FK -> Applications.id (nullable)
  name            VARCHAR(100) NOT NULL
  color           VARCHAR(7)             -- hex color
  created_at      DATETIME2
  UNIQUE(application_id, name)

DocumentTagAssignments
  document_id     UUID FK -> Documents.id
  tag_id          UUID FK -> DocumentTags.id
  PRIMARY KEY (document_id, tag_id)
```

### Indexes

```sql
-- Scope-based lookups (most common query pattern)
CREATE INDEX IX_Documents_application_id ON Documents(application_id) WHERE application_id IS NOT NULL;
CREATE INDEX IX_Documents_project_id ON Documents(project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IX_Documents_user_id ON Documents(user_id) WHERE user_id IS NOT NULL;

-- Folder tree queries
CREATE INDEX IX_Documents_folder_id ON Documents(folder_id);
CREATE INDEX IX_DocumentFolders_path ON DocumentFolders(path);
CREATE INDEX IX_DocumentFolders_parent_scope ON DocumentFolders(parent_id, application_id, project_id, user_id);

-- Template queries
CREATE INDEX IX_Documents_templates ON Documents(is_template, template_scope) WHERE is_template = 1;

-- Search support (before Meilisearch)
CREATE INDEX IX_Documents_title ON Documents(title);
CREATE INDEX IX_Documents_updated_at ON Documents(updated_at DESC);
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-500 users | Current design. Single Redis instance, direct DB queries for search. |
| 500-5K users | Add Meilisearch for full-text search. Redis locks handle concurrency. Connection pool tuning. |
| 5K-50K users | Consider read replicas for document reads. Meilisearch sharding. Multiple Uvicorn workers (Redis pub/sub already handles cross-worker). |
| 50K+ users | Document content in object storage (MinIO) instead of DB. CDN for images. Separate document service as microservice. |

### Scaling Priorities

1. **First bottleneck: Database content storage.** Large documents (100KB+ JSON) in MSSQL will cause I/O pressure. At 5K users this is manageable with proper indexing and connection pooling (already configured: 50 pool + 100 overflow). Monitor query times on document content reads.

2. **Second bottleneck: Search indexing latency.** Background markdown generation + Meilisearch indexing could lag during heavy save periods. This is acceptable -- search results being 5-10 seconds stale is fine. But if latency exceeds 30s, add a dedicated search indexing worker.

3. **Third bottleneck: WebSocket broadcast volume.** At 5K users, document lock/unlock and save notifications are low-frequency per document. The existing Redis pub/sub pattern handles this well. The concern would be if many users are in the same application room -- but the existing `broadcast_to_room` pattern already handles this efficiently.

## Anti-Patterns

### Anti-Pattern 1: Storing Content as Markdown Only

**What people do:** Store only markdown in the DB, parse it back to TipTap on load.
**Why it is wrong:** Round-tripping through markdown loses TipTap-specific features (custom nodes, marks, attributes). Each conversion introduces subtle formatting drift.
**Do this instead:** Store the canonical TipTap JSON as `content_json`. Generate markdown separately as a derived field for search indexing. TipTap JSON is the source of truth.

### Anti-Pattern 2: Database-Based Locks with Polling

**What people do:** Add a `locked_by` column to the Documents table and poll it every few seconds.
**Why it is wrong:** At 5K users, polling creates N queries per interval. Acquiring a lock requires a DB write transaction. If the server holding the lock crashes, a background job must sweep for stale locks (adding complexity and latency).
**Do this instead:** Redis-based locks with TTL auto-expiry. Lock operations are O(1), atomic, and self-cleaning. The existing Redis infrastructure already supports this.

### Anti-Pattern 3: Loading the Entire Folder Tree in One Query

**What people do:** `SELECT * FROM DocumentFolders WHERE application_id = X` then build the tree in Python.
**Why it is wrong:** With tens of thousands of documents and folders, this transfers massive payloads and causes slow initial renders.
**Do this instead:** Lazy-load tree nodes. Fetch root-level folders first, then expand children on demand. The materialized `path` column makes subtree queries efficient: `WHERE path LIKE '/root-id/%'`. Frontend caches expanded state in IndexedDB.

### Anti-Pattern 4: Using Yjs/CRDT for Single-User Editing

**What people do:** Set up Yjs, y-websocket, and CRDT infrastructure even though the initial requirement is single-editor-at-a-time.
**Why it is wrong:** Yjs adds significant complexity: a WebSocket server per document room, binary encoding/decoding, conflict resolution logic, and operational state management. All of this is unnecessary when you have document locking ensuring a single editor.
**Do this instead:** Start with simple auto-save (debounce + POST). The document lock ensures one writer at a time. If/when true multi-user co-editing is needed, layer Yjs on top. The lock system can be repurposed as a "fallback" when Yjs cannot resolve conflicts.

## Integration Points

### Existing Services to Reuse

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **PermissionService** | Call `get_user_application_role()` / `check_can_manage_tasks()` for document access | Documents inherit scope permissions: app members can view app docs, project members can view project docs |
| **MinIOService** | Call `upload_file()` / `get_presigned_download_url()` for document images | Use bucket `pm-images`, key pattern `documents/{doc_id}/{uuid}_{filename}` |
| **RedisService** | Use `set()` with NX+EX for locks, `publish()` for lock events, `presence_*()` for editor tracking | Lock keys: `doc:lock:{doc_id}`, presence keys: `presence:document:{doc_id}` |
| **ConnectionManager** | Add new MessageTypes for document events, use existing room/broadcast infrastructure | Room pattern: `document:{doc_id}` for per-document events |
| **WebSocket handlers** | Add `handle_document_locked`, `handle_document_unlocked`, `handle_document_saved` following existing handler pattern | Follow existing `handle_note_update()` pattern exactly |
| **Auth (get_current_user)** | Standard FastAPI dependency injection, same as all other routers | No changes needed |

### New WebSocket Message Types to Add

```python
# In manager.py MessageType enum:
DOCUMENT_LOCKED = "document_locked"
DOCUMENT_UNLOCKED = "document_unlocked"
DOCUMENT_SAVED = "document_saved"
DOCUMENT_CREATED = "document_created"
DOCUMENT_UPDATED = "document_updated"
DOCUMENT_DELETED = "document_deleted"
DOCUMENT_MOVED = "document_moved"       # moved to different folder
FOLDER_CREATED = "folder_created"
FOLDER_UPDATED = "folder_updated"
FOLDER_DELETED = "folder_deleted"
```

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| DocumentEditor -> useDocumentAutoSave | Debounced callback (2s) | Hook manages timer lifecycle |
| useDocumentLock -> Backend | REST for acquire/release, REST for heartbeat (every 30s) | WebSocket for lock status broadcasts to other users |
| document_service -> search_service | Background task after save | Async -- search lag is acceptable |
| document_service -> markdown generation | Background task after save | Use `tiptap-markdown` or server-side conversion lib |
| Folder tree -> documents | `folder_id` FK | Documents belong to at most one folder; null means root-level |

### Permission Model for Documents

Documents inherit from the existing RBAC:

| Scope | Who Can View | Who Can Edit | Who Can Delete |
|-------|-------------|--------------|----------------|
| Application-scoped | All app members (owner/editor/viewer) | Owner + Editor | Owner only |
| Project-scoped | All app members who can view the project | Owner + Editor with project membership | Owner + Project Admin |
| Personal (user-scoped) | Only the owner | Only the owner | Only the owner |

This reuses the existing `PermissionService.get_user_application_role()` and `check_can_manage_tasks()` methods with minimal modification. A new `check_can_edit_document()` method wraps these with scope-awareness.

### Template Storage

Templates are regular documents with `is_template = True`:

- **Built-in templates:** `template_scope = 'builtin'`, no scope FK set. Seeded via Alembic data migration.
- **Application templates:** `template_scope = 'application'`, `application_id` set. Created by app owners/editors.
- **Personal templates:** `template_scope = 'personal'`, `user_id` set. Created by individual users.

When creating a document from a template, the backend copies `content_json` from the template document into the new document. No special template table needed.

### Content Pipeline: TipTap JSON to Markdown

**Server-side approach:** Use a lightweight Python library to convert TipTap JSON to markdown. Options:

1. **Custom converter (recommended):** Walk the TipTap JSON tree and emit markdown. TipTap JSON is a well-defined ProseMirror document structure. A 200-line recursive converter handles headings, paragraphs, bold, italic, code, lists, links, images, tables.

2. **Alternative: Call a Node.js sidecar.** Use `tiptap-utils` or `@tiptap/html` in a small Node script. Adds infrastructure complexity for minimal benefit.

**Recommendation:** Write a custom Python converter. The TipTap JSON schema is stable and well-documented. A custom converter avoids a Node.js dependency and runs in-process during the background task.

## Suggested Build Order

Based on dependency analysis, the recommended implementation order is:

### Phase 1: Data Model + Basic CRUD (no external deps)
1. Alembic migration: `Documents`, `DocumentFolders`, `DocumentTags`, `DocumentTagAssignments` tables
2. SQLAlchemy models
3. Pydantic schemas
4. Documents router: CRUD endpoints
5. Folders router: CRUD + tree endpoints
6. Register in `models/__init__.py` and `main.py`

**Rationale:** Foundation that everything else depends on. No Redis or Meilisearch needed.

### Phase 2: Frontend Tree + Editor Shell
1. `useDocumentStore` (Zustand)
2. `use-documents.ts` and `use-document-folders.ts` (TanStack Query hooks)
3. KnowledgeTree component (folder/doc navigation)
4. DocumentEditor component (TipTap rendering, read-only first)

**Rationale:** Needs Phase 1 APIs. Gets the UI navigable.

### Phase 3: Auto-Save + Content Pipeline
1. Auto-save endpoint: `POST /api/documents/{id}/content`
2. Debounced auto-save hook (`useDocumentAutoSave`)
3. TipTap JSON -> Markdown converter (Python)
4. Background task for markdown generation after save
5. Edit mode in DocumentEditor

**Rationale:** Needs Phase 2 editor. This is the core editing experience.

### Phase 4: Locking
1. `document_lock_service.py` (Redis-based)
2. Lock REST endpoints: acquire, release, heartbeat
3. `use-document-lock.ts` hook (acquire on edit, heartbeat interval, release on close)
4. WebSocket message types for lock events
5. DocumentLockBanner component
6. Lock status broadcasts via existing WebSocket infrastructure

**Rationale:** Needs Phase 3 (auto-save must work before locking). Requires Redis (already deployed).

### Phase 5: Images + Templates
1. Image upload endpoint for documents
2. TipTap image paste/drop handler
3. Template CRUD (documents with `is_template=true`)
4. TemplateSelector component
5. Built-in template seed data (Alembic data migration)

**Rationale:** Needs Phase 3 content pipeline. Image upload reuses existing MinIO service.

### Phase 6: Search
1. Meilisearch integration service
2. Index sync after document saves (background task)
3. Search REST endpoint
4. DocumentSearch component
5. DB-based fallback search (LIKE query on title + markdown_content) for environments without Meilisearch

**Rationale:** Needs Phase 3 markdown generation for indexing. Can be deferred if Meilisearch is not yet deployed.

### Phase 7: Tags + Polish
1. Tag CRUD endpoints
2. Tag assignment endpoints
3. Tag UI in editor and tree
4. Drag-drop folder/document reordering
5. Keyboard shortcuts
6. "Notes" unified screen showing all documents organized by Application -> Projects

**Rationale:** Nice-to-have features that enhance UX but are not core functionality.

## Sources

- Direct codebase analysis of `D:\FTX_CODE\pm-project\fastapi-backend\app\` (models, routers, services, websocket)
- Direct codebase analysis of `D:\FTX_CODE\pm-project\electron-app\src\renderer\` (stores, hooks, components)
- Existing patterns: Attachment model (polymorphic entity pattern), Note model (hierarchical parent-child), ConnectionManager (room-based WebSocket), RedisService (pub/sub + caching + presence), MinIOService (file storage), PermissionService (RBAC checks)
- Architecture decisions consistent with `CLAUDE.md` project specifications

---
*Architecture research for: Document/Knowledge Base System within PM Desktop*
*Researched: 2026-01-31*

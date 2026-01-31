# Phase 1: Migration & Data Foundation - Research

**Researched:** 2026-01-31
**Domain:** Backend data modeling (SQLAlchemy/Alembic), frontend state management (React Context + TanStack Query), old system removal
**Confidence:** HIGH

## Summary

This phase requires three workstreams: (1) removing the old notes system entirely, (2) completing the Zustand-to-Context migration (mostly done already), and (3) building the new document data model with scopes, folders, tags, and soft delete.

The codebase investigation reveals that Zustand has **already been fully removed** from package.json. All three stores (auth, notes, notification-ui) already have React Context implementations with re-export shims in the `stores/` directory. The remaining work is removing the shim files, the old notes Context/components/pages, and cleaning up imports.

The new document schema follows established codebase patterns: UUID primary keys via `sqlalchemy.dialects.postgresql.UUID`, `__tablename__` with PascalCase table names, `__allow_unmapped__ = True`, timestamp columns with `datetime.utcnow`. The Attachment model provides the direct FK pattern for scope (application_id, note_id, task_id). The API follows a hybrid URL pattern: nested for collections (`/api/applications/{id}/notes`), flat for individual resources (`/api/notes/{id}`).

**Primary recommendation:** Execute removal first (clean slate), then build new models and APIs bottom-up. The frontend state layer for knowledge base should use TanStack Query hooks exclusively (matching the pattern used by all other data: tasks, projects, comments, members, notifications, attachments, checklists) with a thin Context only for UI state if needed.

## Standard Stack

### Core (Already in Codebase)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.x (async) | ORM, data models | Already used for all models |
| Alembic | Latest | Database migrations | Already configured, `alembic/env.py` imports all models |
| Pydantic | v2 | Request/response schemas | Already used for all API schemas |
| FastAPI | Latest | API framework | Already the backend framework |
| @tanstack/react-query | ^5.90 | Server state management | Already used for all data hooks |
| @tanstack/query-async-storage-persister | ^5.90 | IndexedDB persistence | Already configured with per-query persistence |
| React Context (useReducer) | 18.3 | UI-only state | Already used for auth, notification-ui |

### Supporting (Already in Codebase)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| idb / idb-keyval | 8.0 / 6.2 | IndexedDB access | Already used by query-cache-db |
| lz-string | 1.5 | Compression for cached data | Already used by per-query-persister |
| lucide-react | 0.400 | Icons | Already used throughout UI |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| React Context for UI state | TanStack Query only | Context is simpler for purely client-side state like "selected folder", "sidebar collapsed". TanStack Query is for server-synchronized data. Recommendation: **TanStack Query for all server data, Context only if genuine UI-only state exists** |

**Installation:** No new packages needed. Everything is already installed.

## Architecture Patterns

### Recommended Backend Structure (New Files)

```
fastapi-backend/app/
├── models/
│   ├── document.py           # Document model (replaces Note)
│   ├── document_folder.py    # DocumentFolder model
│   ├── document_tag.py       # DocumentTag + DocumentTagAssignment models
│   └── document_snapshot.py  # DocumentSnapshot model (empty, future)
├── schemas/
│   ├── document.py           # Pydantic schemas for documents
│   ├── document_folder.py    # Pydantic schemas for folders
│   └── document_tag.py       # Pydantic schemas for tags
├── routers/
│   ├── documents.py          # Document CRUD endpoints
│   ├── document_folders.py   # Folder CRUD + tree endpoint
│   └── document_tags.py      # Tag CRUD endpoints
└── services/
    └── document_service.py   # Business logic (soft delete, trash, etc.)
```

### Recommended Frontend Structure (New Files)

```
electron-app/src/renderer/
├── hooks/
│   ├── use-documents.ts      # TanStack Query hooks for documents
│   ├── use-document-folders.ts  # TanStack Query hooks for folders
│   └── use-document-tags.ts  # TanStack Query hooks for tags
└── (no new contexts needed — TanStack Query handles server state)
```

### Pattern 1: Direct FK Scope Pattern (from Attachment model)

**What:** Use direct FK columns with a CHECK constraint to enforce exactly-one-non-null for scope assignment.
**When to use:** For entities that belong to exactly one scope (application, project, or personal).
**Example:**

```python
# Source: Codebase investigation — attachment.py pattern
class Document(Base):
    __tablename__ = "Documents"

    # Scope FKs — exactly one must be non-null (enforced by CHECK constraint)
    application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("Projects.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="CASCADE"), nullable=True, index=True)  # personal scope

    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_documents_exactly_one_scope",
        ),
    )
```

**Confidence:** HIGH — follows existing Attachment model pattern, confirmed by codebase inspection.

### Pattern 2: Materialized Path for Folder Hierarchy

**What:** Store the full ancestor path as a string column (e.g., `/root-uuid/child-uuid/grandchild-uuid/`) for efficient tree queries.
**When to use:** For hierarchical folder structures where you need subtree queries and depth limiting.
**Example:**

```python
class DocumentFolder(Base):
    __tablename__ = "DocumentFolders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("DocumentFolders.id", ondelete="CASCADE"), nullable=True)
    materialized_path = Column(String(4000), nullable=False, default="/", index=True)
    depth = Column(Integer, nullable=False, default=0)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    # Scope FKs (same pattern as Document)
    application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id"), nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("Projects.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id"), nullable=True)
```

**Path format:** `/{ancestor-uuid}/{parent-uuid}/{self-uuid}/`
- Root folder: `/{self-uuid}/`
- Child of root: `/{root-uuid}/{self-uuid}/`
- Max depth enforced server-side: `depth <= 5`

**Tree query:** `WHERE materialized_path LIKE '/{root-uuid}/%' AND scope_column = :scope_id`

**Confidence:** HIGH — standard pattern for hierarchical data in SQL, well-documented approach.

### Pattern 3: Hybrid URL Convention (from existing codebase)

**What:** Nested URLs for collection operations scoped to a parent, flat URLs for individual resource operations.
**When to use:** All API endpoints.
**Example from codebase:**

```
# Collection (nested under parent):
GET    /api/applications/{app_id}/notes        → list notes
POST   /api/applications/{app_id}/notes        → create note
GET    /api/applications/{app_id}/notes/tree   → get tree

# Individual (flat):
GET    /api/notes/{note_id}                    → get single note
PUT    /api/notes/{note_id}                    → update note
DELETE /api/notes/{note_id}                    → delete note
PUT    /api/notes/{note_id}/reorder            → reorder

# Same pattern for tasks:
GET    /api/projects/{project_id}/tasks        → list
POST   /api/projects/{project_id}/tasks        → create
GET    /api/tasks/{task_id}                    → get single
PUT    /api/tasks/{task_id}                    → update
DELETE /api/tasks/{task_id}                    → delete
```

**Recommendation for documents:**

```
# Scope-based collection endpoints:
GET    /api/documents?scope=application&scope_id={id}     → list documents in scope
POST   /api/documents                                      → create document (scope in body)
GET    /api/documents/{doc_id}                             → get single document
PUT    /api/documents/{doc_id}                             → update document
DELETE /api/documents/{doc_id}                             → soft delete (move to trash)
POST   /api/documents/{doc_id}/restore                    → restore from trash
DELETE /api/documents/{doc_id}/permanent                   → permanent delete

# Folder endpoints:
GET    /api/document-folders/tree?scope=application&scope_id={id}  → full tree
POST   /api/document-folders                               → create folder
PUT    /api/document-folders/{folder_id}                   → update folder
DELETE /api/document-folders/{folder_id}                   → delete folder

# Tag endpoints:
GET    /api/document-tags?scope=application&scope_id={id}  → list tags
POST   /api/document-tags                                  → create tag
PUT    /api/document-tags/{tag_id}                         → update tag
DELETE /api/document-tags/{tag_id}                         → delete tag
```

**Why flat with query params instead of deeply nested:** Documents span three scopes. Deeply nesting (`/api/applications/{id}/documents`, `/api/projects/{id}/documents`, `/api/users/{id}/documents`) creates three separate route sets for identical logic. A single flat endpoint with scope query params is cleaner and matches the decision to use direct FK columns.

**Confidence:** MEDIUM — reasonable extrapolation from codebase patterns, but this is a Claude recommendation, not a codebase convention for multi-scope entities.

### Pattern 4: TanStack Query Hooks (from existing codebase)

**What:** Each data domain gets its own hook file with useQuery/useMutation hooks, following the exact pattern in `use-queries.ts`.
**Key patterns observed:**
- `useAuthStore((s) => s.token)` for auth token access
- `window.electronAPI.get/post/put/delete` for API calls
- `queryKeys` centralized in `query-client.ts`
- Optimistic updates on mutations with `onMutate`/`onError`/`onSettled`
- Cursor-based pagination via `useInfiniteQuery` with `getNextPageParam`
- `staleTime` and `gcTime` configured per-query based on data volatility

**Confidence:** HIGH — directly observed in codebase.

### Pattern 5: Cursor-Based Pagination (from existing codebase)

**What:** The codebase already uses cursor-based pagination for archived tasks and projects.
**Backend response shape:**

```python
class CursorPage(BaseModel):
    items: list[T]
    next_cursor: str | None
    total: int | None = None
```

**Frontend consumption:**

```typescript
useInfiniteQuery({
    queryKey: [...baseKey, search || ''],
    queryFn: async ({ pageParam }) => {
        const params = new URLSearchParams()
        params.set('limit', '30')
        if (pageParam) params.set('cursor', pageParam)
        if (search) params.set('search', search)
        // ...fetch
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
})
```

**Confidence:** HIGH — directly observed in `use-queries.ts` (useArchivedTasks, useArchivedProjects, useMyPendingTasks, etc.).

### Anti-Patterns to Avoid

- **Using Zustand for new stores:** The codebase has migrated away from Zustand. All new server state must use TanStack Query hooks.
- **Putting API calls in Context providers:** The notes-context.tsx (to be removed) puts fetch logic inside the Context. The established pattern is TanStack Query hooks in `hooks/` files. Context should only hold UI state.
- **Offset-based pagination for document lists:** The codebase convention for paginated lists is cursor-based. Only the old notes endpoint uses skip/limit.
- **Deeply nested URL paths for multi-scope entities:** `/api/applications/{id}/projects/{id}/documents` creates unnecessarily long paths. Use flat with scope params.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IndexedDB persistence | Custom IndexedDB caching | Existing per-query-persister infrastructure | Already built, tested, handles LRU eviction, compression, migration |
| Query cache invalidation | Custom pub/sub cache sync | Existing `use-websocket-cache.ts` pattern | Already handles WebSocket-driven invalidation |
| Optimistic updates | Manual state management | TanStack Query's `onMutate`/`onError`/`onSettled` | Built-in rollback, deduplication, refetch on error |
| Auth token handling | Custom token passing | `useAuthStore((s) => s.token)` in each hook | Established pattern, auto-updates on login/logout |
| Tree building from flat list | Custom recursive algorithm | SQL materialized path + single query | More efficient than recursive CTE or app-level tree building |

**Key insight:** The existing TanStack Query infrastructure (persistence, cache invalidation, optimistic updates) is already battle-tested for this codebase. The knowledge base data layer should plug into it, not reinvent it.

## Common Pitfalls

### Pitfall 1: Forgetting to Update Relationship Back-References When Removing Note Model

**What goes wrong:** Deleting the Note model without removing `back_populates="notes"` from Application and `back_populates="created_notes"` from User causes import/relationship errors.
**Why it happens:** SQLAlchemy relationships are bidirectional. The Note model has relationships to Application, User, and Attachment.
**How to avoid:**
1. Remove `notes` relationship from `application.py` (line 92-97)
2. Remove `created_notes` relationship from `user.py` (line 102-106)
3. Remove `note` relationship from `attachment.py` (line 128-133)
4. Remove `note_id` FK column from `attachment.py` (line 96-101)
5. Remove Note from `models/__init__.py`
6. Remove Note import from `alembic/env.py`
**Warning signs:** SQLAlchemy mapper errors at startup, AttributeError on model classes.

### Pitfall 2: NotesProvider Still Wrapping App.tsx

**What goes wrong:** After removing notes-context.tsx, App.tsx still wraps everything in `<NotesProvider>` (line 334 in App.tsx), causing runtime errors.
**Why it happens:** The provider nesting in App.tsx is easy to overlook.
**How to avoid:** Remove `<NotesProvider>` from App.tsx, remove the import from `@/contexts`, update `contexts/index.ts`.
**Warning signs:** "NotesProvider is not defined" or "useNotesStore must be used within a NotesProvider" errors.

### Pitfall 3: Store Shim Files Left Behind

**What goes wrong:** The `stores/notes-store.ts`, `stores/auth-store.ts`, and `stores/notification-ui-store.ts` files are re-export shims. If stores/index.ts is updated but the individual shim files remain, they become dead code.
**Why it happens:** The migration was done incrementally — Context files created, shims left for backward compatibility.
**How to avoid:** Search for ALL imports from `@/stores/notes-store` and `@/stores/auth-store` across the codebase. Update them to import from `@/contexts` directly. Then delete the shim files.
**Warning signs:** `grep -r "stores/notes-store" src/` returns hits.

### Pitfall 4: CHECK Constraint Syntax Differs Between PostgreSQL and MSSQL

**What goes wrong:** The CLAUDE.md says "Microsoft SQL Server (via pyodbc)" but the codebase uses `sqlalchemy.dialects.postgresql.UUID` and `asyncpg`. The code appears to actually use PostgreSQL despite the CLAUDE.md mention of MSSQL.
**Why it happens:** Documentation may be aspirational or outdated.
**How to avoid:** Use PostgreSQL-compatible CHECK constraint syntax. The existing codebase uses PostgreSQL UUID type. Continue with PostgreSQL patterns.
**Warning signs:** If MSSQL is truly used, `CASE WHEN` syntax works on both. `NVARCHAR(MAX)` is MSSQL-specific; use `Text` for content columns (SQLAlchemy maps it appropriately per dialect).

### Pitfall 5: Materialized Path Updates on Folder Move

**What goes wrong:** When a folder is moved (parent_id changes), all descendant folders need their materialized_path updated.
**Why it happens:** The path contains ancestor UUIDs. Moving a folder invalidates all descendants' paths.
**How to avoid:** Implement a `_update_descendant_paths` helper that does a bulk UPDATE using `LIKE '{old_path}%'` replacement. Enforce this in the folder update endpoint. Also update depth for all descendants.
**Warning signs:** Stale paths after drag-drop folder reorganization.

### Pitfall 6: Soft Delete Queries Must Filter deleted_at by Default

**What goes wrong:** Every document query returns deleted documents unless explicitly filtered.
**Why it happens:** Soft delete adds a nullable `deleted_at` column. Without default filtering, trash items appear in normal views.
**How to avoid:** Add `.where(Document.deleted_at.is_(None))` to all non-trash queries. Consider a SQLAlchemy query helper or a `@hybrid_property` `is_deleted`. The trash endpoint uses `.where(Document.deleted_at.isnot(None))`.
**Warning signs:** Deleted documents appearing in folder views, search results.

### Pitfall 7: Tag Scope Inheritance

**What goes wrong:** A project-scoped document tries to use a tag from a different application, or personal tags leak into application scope.
**Why it happens:** Tags are scoped per-application, and projects inherit their application's tags. The tag assignment must validate scope compatibility.
**How to avoid:** When assigning a tag to a document, verify: (1) if document is application-scoped, tag must belong to that application; (2) if document is project-scoped, tag must belong to the project's parent application; (3) if document is personal, tag must belong to the user's personal namespace.
**Warning signs:** Tags from one application appearing in another.

## Code Examples

### Document Model (Recommended Schema)

```python
# Source: Codebase pattern analysis + phase context decisions
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text,
    CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database import Base

class Document(Base):
    __tablename__ = "Documents"
    __allow_unmapped__ = True

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)

    # Scope FKs (exactly one non-null)
    application_id = Column(UUID(as_uuid=True), ForeignKey("Applications.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("Projects.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="CASCADE"), nullable=True, index=True)

    # Folder (nullable = unfiled)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("DocumentFolders.id", ondelete="SET NULL"), nullable=True, index=True)

    # Content
    title = Column(String(255), nullable=False, index=True)
    content_json = Column(Text, nullable=True)      # TipTap JSON (editor)
    content_markdown = Column(Text, nullable=True)   # Markdown (AI)
    content_plain = Column(Text, nullable=True)      # Plain text (search)

    # Ordering and metadata
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(UUID(as_uuid=True), ForeignKey("Users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Concurrency and versioning
    row_version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False, default=1)

    # Soft delete
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_documents_exactly_one_scope",
        ),
        Index("ix_documents_app_folder", "application_id", "folder_id"),
        Index("ix_documents_project_folder", "project_id", "folder_id"),
    )
```

### Folder Tree Query (Recommended)

```python
# Single query to fetch full folder tree for a scope
async def get_folder_tree(db: AsyncSession, scope: str, scope_id: UUID) -> list[DocumentFolder]:
    scope_filter = getattr(DocumentFolder, f"{scope}_id") == scope_id
    result = await db.execute(
        select(DocumentFolder)
        .where(scope_filter)
        .order_by(DocumentFolder.materialized_path.asc(), DocumentFolder.sort_order.asc())
    )
    return list(result.scalars().all())
    # Client-side: reconstruct tree from flat list using materialized_path
```

### Cursor-Based Pagination Helper (Recommended)

```python
# Source: Existing pattern from tasks router, generalized
from datetime import datetime
from base64 import b64encode, b64decode
import json

def encode_cursor(created_at: datetime, id: UUID) -> str:
    """Encode pagination cursor from created_at + id."""
    payload = {"c": created_at.isoformat(), "i": str(id)}
    return b64encode(json.dumps(payload).encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode pagination cursor to created_at + id."""
    payload = json.loads(b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(payload["c"]), UUID(payload["i"])

async def list_documents_paginated(
    db: AsyncSession,
    scope: str,
    scope_id: UUID,
    cursor: str | None = None,
    limit: int = 30,
    folder_id: UUID | None = None,
) -> dict:
    scope_filter = getattr(Document, f"{scope}_id") == scope_id
    query = (
        select(Document)
        .where(scope_filter, Document.deleted_at.is_(None))
    )
    if folder_id:
        query = query.where(Document.folder_id == folder_id)
    else:
        query = query.where(Document.folder_id.is_(None))  # unfiled

    if cursor:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            (Document.created_at < cursor_created_at) |
            ((Document.created_at == cursor_created_at) & (Document.id < cursor_id))
        )

    query = query.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit + 1)
    result = await db.execute(query)
    items = list(result.scalars().all())

    has_next = len(items) > limit
    if has_next:
        items = items[:limit]

    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_next else None
    return {"items": items, "next_cursor": next_cursor}
```

### TanStack Query Hook (Recommended Pattern)

```typescript
// Source: Existing pattern from use-queries.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

export function useDocuments(scope: string, scopeId: string | undefined) {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.documents(scope, scopeId || ''),
    queryFn: async () => {
      if (!window.electronAPI) throw new Error('Electron API not available')
      const response = await window.electronAPI.get(
        `/api/documents?scope=${scope}&scope_id=${scopeId}`,
        { Authorization: `Bearer ${token}` }
      )
      if (response.status !== 200) throw new Error('Failed to fetch documents')
      return response.data
    },
    enabled: !!token && !!scopeId,
    staleTime: 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}
```

## Inventory of Files to Remove/Modify

### Files to DELETE (Old Notes System)

**Backend:**
1. `fastapi-backend/app/models/note.py` — Note SQLAlchemy model
2. `fastapi-backend/app/schemas/note.py` — Note Pydantic schemas
3. `fastapi-backend/app/routers/notes.py` — Notes CRUD API endpoints
4. `fastapi-backend/tests/test_notes.py` — Notes unit tests

**Frontend:**
5. `electron-app/src/renderer/contexts/notes-context.tsx` — Notes React Context (700+ lines)
6. `electron-app/src/renderer/__tests__/notes-context.test.tsx` — Notes context tests
7. `electron-app/src/renderer/stores/notes-store.ts` — Re-export shim
8. `electron-app/src/renderer/pages/notes/index.tsx` — Notes page (900+ lines)
9. `electron-app/src/renderer/components/notes/note-editor.tsx` — Note editor
10. `electron-app/src/renderer/components/notes/notes-sidebar.tsx` — Notes sidebar
11. `electron-app/src/renderer/components/notes/notes-tab-bar.tsx` — Notes tab bar

### Files to MODIFY

**Backend:**
12. `fastapi-backend/app/models/__init__.py` — Remove Note import/export
13. `fastapi-backend/app/models/application.py` — Remove `notes` relationship (lines 92-97)
14. `fastapi-backend/app/models/user.py` — Remove `created_notes` relationship (lines 102-106)
15. `fastapi-backend/app/models/attachment.py` — Remove `note_id` column and `note` relationship
16. `fastapi-backend/app/routers/__init__.py` — Remove notes_router import/export
17. `fastapi-backend/app/main.py` — Remove `notes_router` import and `app.include_router(notes_router)`
18. `fastapi-backend/alembic/env.py` — Remove Note import

**Frontend:**
19. `electron-app/src/renderer/App.tsx` — Remove `<NotesProvider>` wrapper and import
20. `electron-app/src/renderer/contexts/index.ts` — Remove all notes-context exports
21. `electron-app/src/renderer/stores/index.ts` — Remove all notes-context re-exports
22. `electron-app/src/renderer/pages/dashboard.tsx` — Remove NotesPage import, 'notes' case in navigation
23. `electron-app/src/renderer/components/layout/sidebar.tsx` — Remove 'notes' nav item (line 147)

### Zustand Cleanup (Store Shim Files)

24. `electron-app/src/renderer/stores/auth-store.ts` — Delete (re-export shim)
25. `electron-app/src/renderer/stores/notification-ui-store.ts` — Delete (re-export shim)
26. Update all imports from `@/stores/auth-store` to `@/contexts/auth-context`
27. Update all imports from `@/stores/notification-ui-store` to `@/contexts/notification-ui-context`
28. `electron-app/src/renderer/stores/index.ts` — Delete entirely (just re-exports contexts)

### Import Update Scope

Files importing from `@/stores/auth-store` or `@/stores/`:
- Need to be identified via grep and updated to import from `@/contexts` or `@/contexts/auth-context` directly

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Zustand stores | React Context + TanStack Query | Already migrated in this codebase | No migration needed for auth/notification-ui; notes Context gets deleted not migrated |
| Skip/limit pagination | Cursor-based pagination | Already adopted for archived tasks/projects | New document endpoints should use cursors |
| Single content column | Three-format storage (JSON + MD + plain) | New for documents | Requires three content columns |
| Hard delete | Soft delete with auto-purge | New for documents | Requires deleted_at column + trash endpoints + purge job |

**Deprecated/outdated:**
- Zustand: Package already removed from package.json. Store files are just re-export shims.
- Old notes system: Uses offset pagination, no soft delete, single content column, application-only scope.

## Discretion Recommendations

### State Management Architecture

**Recommendation: TanStack Query only for server data. No React Context for knowledge base.**

Rationale: Every other data domain in the codebase (tasks, projects, comments, members, notifications, attachments, checklists) uses TanStack Query hooks without any accompanying Context. The auth-context and notification-ui-context exist only for purely client-side UI state (auth tokens, panel open/close). The knowledge base has no equivalent client-side-only state that would justify a Context provider. Selected document, selected folder, etc. can all be component-local state or URL state.

**Confidence:** HIGH — based on direct codebase pattern analysis.

### Trash Location

**Recommendation: Global trash (per-user view of all their deleted documents across scopes).**

Rationale: A global trash is simpler to implement (single endpoint: `GET /api/documents/trash`) and avoids the question of "which scope's trash am I viewing?" Per-scope trash would require separate trash views per application, per project, and personal — adding UI complexity without clear benefit. Permission-wise, a user can only see documents they had access to, which is already enforced by the scope + ownership/membership checks.

**Confidence:** MEDIUM — reasonable default, but per-scope trash could be added later if needed.

### API URL Structure

**Recommendation: Flat URLs with scope query parameters (see Pattern 3 above).**

Rationale: Documents span three scopes. Flat URLs with `?scope=application&scope_id={id}` avoid triplicating routes. Individual document endpoints are already flat by codebase convention (`/api/documents/{id}`).

**Confidence:** MEDIUM — reasonable but deviates slightly from the existing nested-collection pattern.

### Document Content Handling

**Recommendation: Include content in single-document GET, exclude from list endpoints.**

Rationale: Document content (JSON + MD + plain) can be large (50-100KB). List endpoints should return metadata only (title, created_at, folder_id, etc.). The single-document GET (`/api/documents/{id}`) should include all three content fields. This avoids a separate content endpoint while keeping list responses lightweight.

**Confidence:** HIGH — standard pattern for document-like resources.

### Dependency Removal After Cleanup

**Recommendation: Zustand package is already removed (not in package.json). No further package removal needed.**

The old notes system doesn't introduce any unique dependencies. All TipTap packages, Radix UI components, and other libraries are used by other parts of the app. No packages should be removed.

**Confidence:** HIGH — verified by reading package.json.

## Open Questions

1. **PostgreSQL vs MSSQL ambiguity**
   - What we know: CLAUDE.md mentions "Microsoft SQL Server (via pyodbc)" but the actual codebase uses `sqlalchemy.dialects.postgresql.UUID` and `asyncpg` throughout. The database URL format in config suggests PostgreSQL.
   - What's unclear: Whether MSSQL support is a future goal or an outdated reference.
   - Recommendation: Build for PostgreSQL (matching current codebase). The CHECK constraint syntax and Text column types work on both. If MSSQL is needed later, the migration is straightforward.

2. **Attachment model note_id column migration**
   - What we know: The Attachment model has a `note_id` FK to Notes table. When Notes table is dropped, this column must be handled.
   - What's unclear: Whether to add a `document_id` FK to Attachment in this phase or defer it.
   - Recommendation: Drop `note_id` from Attachment in the migration. Add `document_id` FK in a future phase when document attachments are implemented.

## Sources

### Primary (HIGH confidence)
- Direct codebase investigation — all files listed in this document were read and analyzed
- `fastapi-backend/app/models/attachment.py` — direct FK scope pattern
- `fastapi-backend/app/models/note.py` — old notes model to remove
- `fastapi-backend/app/routers/notes.py` — old notes API to remove
- `electron-app/src/renderer/contexts/notes-context.tsx` — old notes context to remove
- `electron-app/src/renderer/hooks/use-queries.ts` — TanStack Query patterns
- `electron-app/src/renderer/lib/query-client.ts` — query client configuration
- `electron-app/src/renderer/App.tsx` — provider nesting
- `electron-app/package.json` — dependency audit (Zustand NOT present)
- `electron-app/src/renderer/stores/index.ts` — confirms all stores are re-export shims

### Secondary (MEDIUM confidence)
- Materialized path pattern — well-established SQL pattern for hierarchical data
- Cursor-based pagination — already implemented in codebase for archived entities
- Flat URL pattern recommendation — reasonable extrapolation from codebase conventions

### Tertiary (LOW confidence)
- None — all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in codebase, no new packages
- Architecture: HIGH — patterns directly observed in existing code
- Pitfalls: HIGH — identified from actual code relationships and import chains
- File inventory: HIGH — every file verified by reading

**Research date:** 2026-01-31
**Valid until:** 2026-03-01 (stable — patterns unlikely to change)

# Phase 8: Permissions - Research

**Researched:** 2026-01-31
**Domain:** Role-based access control for document/folder CRUD, FastAPI dependency-based permission enforcement, frontend permission-aware UI
**Confidence:** HIGH

## Summary

Phase 8 adds document-level permission enforcement to an existing RBAC system. The project already has a mature `PermissionService` class (`app/services/permission_service.py`) that implements the 3-tier role model (Owner/Editor/Viewer) with ProjectMember gate for task management. The document permission layer extends this pattern to the knowledge base endpoints (documents, folders, tags).

The key insight from codebase analysis: **all the permission primitives already exist**. The `PermissionService` provides `get_user_application_role()`, `is_project_member()`, and `is_application_member()` methods. The tasks router already implements the exact `verify_project_access()` + `PermissionService.check_can_manage_tasks()` pattern this phase needs to replicate for documents. The work is primarily wiring existing permission checks into the currently-unprotected document/folder/tag endpoints, adding personal-scope isolation, and building a `DocumentPermissionService` that maps document scopes to permission checks.

The current document, folder, and tag endpoints authenticate users (`get_current_user` dependency) but perform **zero authorization checks** -- any authenticated user can create, read, update, or delete any document regardless of scope. This is the gap Phase 8 closes.

**Primary recommendation:** Create a `DocumentPermissionService` class in `app/services/document_permission_service.py` that wraps the existing `PermissionService` with document-scope-aware methods (`can_read_document`, `can_edit_document`, `can_delete_document`, `can_create_in_scope`). Apply these checks as FastAPI dependency-style guards on every document, folder, and tag endpoint. On the frontend, expose a `useDocumentPermissions` hook that derives `canEdit`/`canCreate`/`canDelete` from the already-fetched `user_role` on the application response.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI `Depends()` | existing | Dependency injection for permission checks on routes | Already used for `get_current_user` on every endpoint; natural place for authorization |
| `PermissionService` | existing (app/services/permission_service.py) | Role lookups (`get_user_application_role`, `is_project_member`) | Already proven for task permissions; reuse, don't rebuild |
| SQLAlchemy async | existing | Query document scope FKs to determine which permission check to apply | Standard ORM used throughout backend |
| TanStack Query | existing | Cache user role data on frontend for permission-aware rendering | Already provides `application.user_role` in cached responses |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `HTTPException` (FastAPI) | existing | Return 403 Forbidden for permission violations | Every guarded endpoint |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-endpoint permission checks | Middleware-based RBAC | Middleware can't access route-specific parameters (document_id, scope) easily; per-endpoint is more explicit and matches existing codebase pattern |
| Service-layer permission checks | Database row-level security (PostgreSQL RLS) | RLS is powerful but requires all queries to set `current_setting` per-request, complicates testing, and is not used anywhere in this codebase. Service-layer checks match existing patterns. |
| `DocumentPermissionService` class | Standalone functions | Class pattern matches existing `PermissionService`; shares db session across multiple checks in one request |

**Installation:**
```bash
# No new packages needed -- all dependencies already installed
```

## Architecture Patterns

### Recommended Project Structure

```
fastapi-backend/app/
├── services/
│   ├── permission_service.py              # EXISTING -- Application/Project role lookups
│   └── document_permission_service.py     # NEW -- Document-scope-aware permission checks
├── routers/
│   ├── documents.py                       # MODIFY -- Add permission guards to all endpoints
│   ├── document_folders.py                # MODIFY -- Add permission guards to all endpoints
│   └── document_tags.py                   # MODIFY -- Add permission guards to all endpoints
├── schemas/
│   └── document.py                        # MODIFY -- Add can_edit field to DocumentResponse

electron-app/src/renderer/
├── hooks/
│   └── use-document-permissions.ts        # NEW -- Derives canEdit/canCreate/canDelete from user_role
├── components/knowledge/
│   ├── knowledge-sidebar.tsx              # MODIFY -- Hide create/edit controls for viewers
│   └── [editor components]               # MODIFY -- Disable editing for read-only users
```

### Pattern 1: Document Permission Service (Backend Core)

**What:** A service class that maps document scopes (personal/application/project) to the correct permission check.
**When to use:** Every document/folder/tag endpoint that needs authorization.

```python
# Source: Derived from existing PermissionService pattern (app/services/permission_service.py)
class DocumentPermissionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.permission_service = PermissionService(db)

    async def can_read_document(self, user: User, document: Document) -> bool:
        """Check if user can read a document based on its scope."""
        # Personal scope: only creator can read
        if document.user_id is not None:
            return document.user_id == user.id

        # Application scope: any app member can read
        if document.application_id is not None:
            return await self.permission_service.is_application_member(
                user.id, document.application_id
            )

        # Project scope: any app member can read (projects inherit from app)
        if document.project_id is not None:
            project = await self.permission_service.get_project_with_application(
                document.project_id
            )
            if not project:
                return False
            return await self.permission_service.is_application_member(
                user.id, project.application_id
            )

        return False

    async def can_edit_document(self, user: User, document: Document) -> bool:
        """Check if user can edit a document (owner or editor role)."""
        # Personal scope: only creator can edit
        if document.user_id is not None:
            return document.user_id == user.id

        # Application scope: owner or editor
        if document.application_id is not None:
            role = await self.permission_service.get_user_application_role(
                user.id, document.application_id
            )
            return role in ("owner", "editor")

        # Project scope: owner always, editor only if project member
        if document.project_id is not None:
            project = await self.permission_service.get_project_with_application(
                document.project_id
            )
            if not project:
                return False
            role = await self.permission_service.get_user_application_role(
                user.id, project.application_id
            )
            if role == "owner":
                return True
            if role == "editor":
                return await self.permission_service.is_project_member(
                    user.id, document.project_id
                )
            return False

        return False

    async def can_delete_document(self, user: User, document: Document) -> bool:
        """Check if user can delete a document. Same rules as edit for now."""
        # Application-scoped: only owner can delete
        if document.application_id is not None:
            role = await self.permission_service.get_user_application_role(
                user.id, document.application_id
            )
            return role == "owner"

        # For personal and project scope, same as edit
        return await self.can_edit_document(user, document)

    async def can_create_in_scope(
        self, user: User, scope: str, scope_id: UUID
    ) -> bool:
        """Check if user can create documents/folders in a scope."""
        if scope == "personal":
            return scope_id == user.id

        if scope == "application":
            role = await self.permission_service.get_user_application_role(
                user.id, scope_id
            )
            return role in ("owner", "editor")

        if scope == "project":
            project = await self.permission_service.get_project_with_application(
                scope_id
            )
            if not project:
                return False
            role = await self.permission_service.get_user_application_role(
                user.id, project.application_id
            )
            if role == "owner":
                return True
            if role == "editor":
                return await self.permission_service.is_project_member(
                    user.id, scope_id
                )
            return False

        return False

    async def get_scope_filter_for_list(
        self, user: User, scope: str, scope_id: UUID
    ) -> bool:
        """Check if user can list documents in a scope (PERM-06)."""
        if scope == "personal":
            return scope_id == user.id

        if scope == "application":
            return await self.permission_service.is_application_member(
                user.id, scope_id
            )

        if scope == "project":
            project = await self.permission_service.get_project_with_application(
                scope_id
            )
            if not project:
                return False
            return await self.permission_service.is_application_member(
                user.id, project.application_id
            )

        return False
```

### Pattern 2: Endpoint Permission Guard (Inline Check)

**What:** Each endpoint fetches the document/scope, calls the permission service, and raises 403 if denied.
**When to use:** Every mutating endpoint (create, update, delete) and read endpoints.

```python
# Source: Matches existing pattern in app/routers/tasks.py (verify_project_access)
@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    body: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Permission check
    perm_service = DocumentPermissionService(db)
    if not await perm_service.can_edit_document(current_user, document):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this document")

    # ... rest of update logic
```

### Pattern 3: List API Filtering (PERM-06)

**What:** The document list endpoint verifies the user can access the requested scope before returning results.
**When to use:** GET /documents and GET /document-folders/tree endpoints.

```python
# Source: Derived from existing scope-based list patterns
@router.get("", response_model=DocumentListResponse)
async def list_documents(
    scope: Literal["application", "project", "personal"],
    scope_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # PERM-06: Verify user can access this scope
    perm_service = DocumentPermissionService(db)
    if not await perm_service.get_scope_filter_for_list(current_user, scope, scope_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Personal scope: enforce that scope_id matches current user
    if scope == "personal" and scope_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access another user's personal documents")

    # ... rest of list query
```

### Pattern 4: Frontend Permission-Aware UI

**What:** A hook that derives document permissions from the already-cached `user_role` on the application response, avoiding extra API calls.
**When to use:** All knowledge base UI components that show create/edit/delete controls.

```typescript
// Source: Matches existing pattern in pages/applications/[id].tsx and pages/projects/[id].tsx
interface DocumentPermissions {
  canCreate: boolean
  canEdit: boolean
  canDelete: boolean
  canForceUnlock: boolean
  isReadOnly: boolean
}

function useDocumentPermissions(
  scope: 'personal' | 'application' | 'project',
  applicationUserRole: string | null,
  isPersonalOwner: boolean
): DocumentPermissions {
  if (scope === 'personal') {
    return {
      canCreate: isPersonalOwner,
      canEdit: isPersonalOwner,
      canDelete: isPersonalOwner,
      canForceUnlock: false,
      isReadOnly: !isPersonalOwner,
    }
  }

  const isOwner = applicationUserRole === 'owner'
  const isEditor = applicationUserRole === 'editor'

  return {
    canCreate: isOwner || isEditor,
    canEdit: isOwner || isEditor,
    canDelete: isOwner,
    canForceUnlock: isOwner,
    isReadOnly: !isOwner && !isEditor,
  }
}
```

### Anti-Patterns to Avoid

- **Checking permissions in the frontend only:** The frontend can hide UI controls, but the backend MUST independently enforce permissions. Never trust client-side role checks alone.
- **Fetching the full document for list permission checks:** For `GET /documents` (list), check scope access once, not per-document. The scope-based query already filters correctly.
- **Duplicating role-lookup logic:** Use the existing `PermissionService.get_user_application_role()` -- do not re-implement the Application owner check + ApplicationMember table lookup.
- **Leaking document existence in 403 responses:** Currently the codebase returns 404 for not-found and 403 for access-denied. This is fine because documents are UUID-addressed (not guessable). Maintain this pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Application role lookup | Custom query for owner/member role | `PermissionService.get_user_application_role()` | Already handles Application.owner_id + ApplicationMembers table with caching-ready pattern |
| Project-to-application resolution | Manual join query | `PermissionService.get_project_with_application()` | Already uses `selectinload(Project.application)` for efficient eager loading |
| Project membership check | EXISTS query | `PermissionService.is_project_member()` | Already uses optimized EXISTS pattern |
| Scope-to-FK mapping | Manual if/elif chains | `document_service.get_scope_filter()` and `set_scope_fks()` | Already handles all three scopes consistently |

**Key insight:** The permission infrastructure is 90% built. This phase wires it into the document endpoints, not builds it from scratch.

## Common Pitfalls

### Pitfall 1: Forgetting the Personal Scope Isolation

**What goes wrong:** Personal documents (user_id scope) leak to other users in list/search results because the list endpoint only checks scope access, not ownership.
**Why it happens:** Application and project scopes allow multiple users, but personal scope is single-user. Developers apply the same "is member" check pattern and forget personal is different.
**How to avoid:** For `scope == "personal"`, always hard-check `scope_id == current_user.id`. Never rely on a membership lookup for personal scope -- there is no "personal membership" table.
**Warning signs:** Tests where User A can see User B's personal documents; personal documents appearing in "all documents" aggregate views.

### Pitfall 2: Permission Check Duplication Between Router and Service

**What goes wrong:** Permission logic is split between the router (inline checks) and the service class, leading to inconsistency when one is updated but not the other.
**Why it happens:** Developers add a quick inline check in one endpoint and a service method in another.
**How to avoid:** ALL permission logic lives in `DocumentPermissionService`. Routers call service methods only, never perform role lookups directly. This matches how `tasks.py` uses `PermissionService.check_can_manage_tasks()` through `verify_project_access()`.
**Warning signs:** `get_user_application_role()` called directly in a document router instead of going through `DocumentPermissionService`.

### Pitfall 3: N+1 Queries in Permission Checks

**What goes wrong:** Each document in a list result triggers a separate permission check (role lookup + membership check), causing O(N) database queries for a page of documents.
**Why it happens:** Applying per-document permission checks to list endpoints instead of scope-level access checks.
**How to avoid:** For list endpoints, check scope access ONCE at the top of the handler. The scope-based WHERE clause already ensures only in-scope documents are returned. Per-document checks are only needed for single-document endpoints (GET/PUT/DELETE by ID).
**Warning signs:** Slow list API responses; database query counts scaling with page size.

### Pitfall 4: Forgetting to Guard Folder and Tag Endpoints

**What goes wrong:** Document endpoints are properly guarded, but folder create/update/delete and tag CRUD remain unprotected. A viewer can create folders or tags.
**Why it happens:** The phase name is "Permissions" but developers focus on documents and forget that folders and tags share the same scope model.
**How to avoid:** Apply the same `can_create_in_scope()` and `can_edit_in_scope()` checks to folder and tag endpoints. Document, folder, and tag endpoints all have the same scope FK pattern.
**Warning signs:** Viewers able to create folders; editors able to delete tags in applications they don't own.

### Pitfall 5: Force-Unlock Without Locking Phase

**What goes wrong:** Attempting to implement PERM-02 (force-unlock) before Phase 5 (Document Locking) is built.
**Why it happens:** PERM-02 is in this phase's requirements, but the locking system it depends on is in Phase 5.
**How to avoid:** If Phase 5 is not yet implemented when Phase 8 is built, stub the force-unlock permission check method. The method should exist in `DocumentPermissionService` (checking `role == "owner"`) but the actual force-unlock endpoint is in Phase 5. If Phase 5 IS already built, integrate the permission check into the existing lock force-take endpoint.
**Warning signs:** Building a lock system inside the permissions phase; or skipping PERM-02 entirely.

### Pitfall 6: Project-Scoped Document Editor Gate Missing

**What goes wrong:** For project-scoped documents, editors without ProjectMember status can edit documents even though they can't manage tasks in that project.
**Why it happens:** The task permission model requires ProjectMember gate for editors, but the document model might skip this check since documents feel "read/write" not "manage."
**How to avoid:** Decide explicitly whether the ProjectMember gate applies to documents. The existing `check_can_manage_tasks()` requires it for editors. The same pattern should apply to document editing in project scope for consistency. The research code examples above include this check.
**Warning signs:** An editor who can't create tasks in a project CAN edit documents in that project.

## Code Examples

### Verified: Existing Permission Check Pattern (tasks.py)

```python
# Source: app/routers/tasks.py lines 107-179
async def verify_project_access(
    project_id: UUID,
    current_user: User,
    db: AsyncSession,
    require_edit: bool = False,
) -> Project:
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.application))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user_role = await get_user_application_role(
        db, current_user.id, project.application_id, project.application
    )

    if not user_role:
        raise HTTPException(status_code=403, detail="Access denied")

    if require_edit:
        permission_service = get_permission_service(db)
        can_manage = await permission_service.check_can_manage_tasks(
            current_user, project_id, project.application_id
        )
        if not can_manage:
            if user_role == "viewer":
                raise HTTPException(status_code=403, detail="Viewers cannot manage tasks")
            elif user_role == "editor":
                raise HTTPException(
                    status_code=403,
                    detail="Editors must be project members to manage tasks"
                )

    return project
```

### Verified: Application Role in Frontend (applications/[id].tsx)

```typescript
// Source: electron-app/src/renderer/pages/applications/[id].tsx lines 439-443
const userRole = application?.user_role || 'viewer'
const isOwner = userRole === 'owner'
const isEditor = userRole === 'editor'
const canEditProjects = isOwner || isEditor
```

### Verified: Scope FK Pattern on Document Model

```python
# Source: app/models/document.py -- CHECK constraint
# Exactly one of application_id, project_id, user_id must be non-null
CheckConstraint(
    "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
    name="ck_documents_exactly_one_scope",
)
```

### Verified: Document List Scope Filter

```python
# Source: app/services/document_service.py lines 78-97
def get_scope_filter(model: Any, scope: str, scope_id: UUID) -> Any:
    if scope == "application":
        return model.application_id == scope_id
    elif scope == "project":
        return model.project_id == scope_id
    elif scope == "personal":
        return model.user_id == scope_id
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Middleware RBAC decorators | FastAPI Depends() + service classes | Standard since FastAPI 0.65+ | More explicit, testable, composable |
| Custom role enums | String-based roles ("owner"/"editor"/"viewer") | Existing codebase convention | Simpler, matches DB storage |
| Per-row permission column on documents | Scope-based permission derivation from membership | Existing architecture decision | No schema changes needed for permissions |

**Deprecated/outdated:**
- N/A -- The project's permission architecture is modern and well-structured. No deprecated patterns to replace.

## Open Questions

1. **Should editors need ProjectMember gate for project-scoped documents?**
   - What we know: Tasks require ProjectMember gate for editors (existing `check_can_manage_tasks` behavior). Documents currently have no permission checks.
   - What's unclear: Whether the same gate should apply to document editing. The phase requirements say "Editors in an application/project can create new documents and edit documents in their scope" (PERM-03) -- "in their scope" could mean with or without the ProjectMember gate.
   - Recommendation: Apply the same ProjectMember gate for consistency. If an editor can't manage tasks in a project, they shouldn't be able to manage documents either. This avoids confusing permission discrepancies.

2. **Who can delete documents: owner only, or owner + editor?**
   - What we know: PERM-01 says "Application owners can create, edit, and delete." PERM-03 says "Editors can create and edit." Delete is not mentioned for editors.
   - What's unclear: Whether editors can delete their own documents or only owners can delete.
   - Recommendation: Only application owners can delete application-scoped documents (soft delete). Editors can create and edit but not delete. For personal documents, the creator (who is the sole owner) can delete. This matches the principle of least privilege and prevents data loss.

3. **Should PERM-02 (force-unlock) be implemented now or deferred to Phase 5?**
   - What we know: Phase 5 (Document Locking) may or may not be implemented when Phase 8 is built. PERM-02 requires a locking mechanism to exist.
   - What's unclear: Build order -- will Phase 5 be complete before Phase 8?
   - Recommendation: Create the `can_force_unlock()` permission check method (checks `role == "owner"`) in Phase 8. If the locking endpoint already exists (Phase 5 complete), wire it in. If not, the method exists ready for Phase 5 to consume. This satisfies PERM-02 from the permission side regardless of lock implementation status.

4. **Should the trash endpoint (GET /documents/trash) show all trashed docs to owners?**
   - What we know: Currently trash shows only `created_by == current_user.id`. Owners should be able to manage all documents per PERM-01.
   - What's unclear: Whether owners need to see/restore other users' trashed documents.
   - Recommendation: Keep trash as personal (created_by filter). Owners can undelete via direct API if needed. The trash view is a personal convenience feature, not an admin tool.

## Sources

### Primary (HIGH confidence)
- `app/services/permission_service.py` -- Full PermissionService implementation (530 lines, 10 methods)
- `app/routers/tasks.py` -- Verified permission enforcement pattern (verify_project_access, lines 107-179)
- `app/routers/documents.py` -- Current unprotected document endpoints (494 lines, 0 permission checks)
- `app/routers/document_folders.py` -- Current unprotected folder endpoints (245 lines, 0 permission checks)
- `app/routers/document_tags.py` -- Current unprotected tag endpoints (157 lines, 0 permission checks)
- `app/models/document.py` -- Document model with scope FKs and CHECK constraint
- `app/models/document_folder.py` -- Folder model with same scope FK pattern
- `app/models/application_member.py` -- Role field: "owner", "editor", "viewer"
- `app/models/project_member.py` -- Role field: "admin", "member"
- `app/services/auth_service.py` -- `get_current_user` dependency pattern
- `app/services/document_service.py` -- Scope validation and filter helpers
- `app/websocket/room_auth.py` -- Room access pattern (application/project membership checks)
- `electron-app/src/renderer/pages/applications/[id].tsx` -- Frontend role-based UI pattern
- `electron-app/src/renderer/pages/projects/[id].tsx` -- Frontend ProjectMember gate pattern

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` -- Confirmed decisions: lock-based editing, no Zustand, materialized paths
- `.planning/ROADMAP.md` -- Phase 8 requirements and plan structure (08-01, 08-02, 08-03)
- `.planning/phases/05-document-locking/05-RESEARCH.md` -- Locking architecture for PERM-02 context

### Tertiary (LOW confidence)
- None -- all findings are from direct codebase analysis

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries already in use; no new dependencies
- Architecture: HIGH -- Pattern directly replicates existing PermissionService + tasks.py enforcement
- Pitfalls: HIGH -- Derived from actual codebase analysis of scope model and existing permission gaps

**Research date:** 2026-01-31
**Valid until:** 2026-03-01 (stable -- no external dependencies, all findings from codebase)

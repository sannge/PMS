"""Document lock API endpoints.

Provides endpoints for acquiring, releasing, heartbeating, querying, and
force-taking document locks. All endpoints require authentication.
Lock state changes are broadcast via WebSocket to document room subscribers.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.document import Document
from ..models.project import Project
from ..models.user import User
from ..schemas.document_lock import (
    ActiveLockItem,
    ActiveLocksResponse,
    DocumentLockResponse,
    LockHolder,
)
from ..services.auth_service import get_current_user
from ..services.document_lock_service import DocumentLockService, get_lock_service
from ..services.document_service import get_scope_filter
from ..services.permission_service import PermissionService
from ..websocket.handlers import handle_document_lock_change

router = APIRouter(prefix="/api/documents", tags=["document-locks"])


# ============================================================================
# Helpers
# ============================================================================


async def _resolve_lock_broadcast_ids(
    db: AsyncSession,
    application_id: UUID | None,
    project_id: UUID | None,
) -> tuple[str | None, str | None]:
    """Resolve application_id and project_id for lock event broadcast.

    For project-scoped documents (project_id set, application_id NULL),
    looks up the project's parent application_id so lock events reach
    both the project room and the application room.

    Returns:
        (app_id_str, proj_id_str) — either may be None.
    """
    app_id = str(application_id) if application_id else None
    proj_id = str(project_id) if project_id else None

    if proj_id and not app_id:
        result = await db.execute(
            select(Project.application_id).where(Project.id == project_id)
        )
        parent_app_id = result.scalar_one_or_none()
        if parent_app_id:
            app_id = str(parent_app_id)

    return app_id, proj_id


# ============================================================================
# Batch Lock Endpoints (MUST be before /{document_id} to avoid path matching)
# ============================================================================


@router.get(
    "/active-locks",
    response_model=ActiveLocksResponse,
    summary="Get active locks for a scope",
    description=(
        "Returns all currently locked documents within a scope. "
        "Typically 0-5 results. One request replaces N per-document lock queries."
    ),
    responses={
        200: {"description": "Active locks retrieved"},
        401: {"description": "Not authenticated"},
    },
)
async def get_active_locks(
    scope: Literal["application", "project", "personal"] = Query(
        ..., description="Scope type"
    ),
    scope_id: UUID = Query(..., description="Scope entity ID"),
    current_user: Annotated[User, Depends(get_current_user)] = ...,
    db: AsyncSession = Depends(get_db),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> ActiveLocksResponse:
    """Get all active document locks within a scope.

    Strategy: SCAN all doc_lock:* keys from Redis (typically 0-50 system-wide),
    then filter to documents belonging to the requested scope via a lightweight
    DB query. Returns only documents that are currently locked.
    """
    perm_service = PermissionService(db)
    if not await perm_service.check_can_view_knowledge(current_user.id, scope, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view locks in this scope",
        )

    # Step 1: Get all active locks from Redis (fast — typically 0-50 keys)
    all_locks = await lock_service.scan_all_active_locks()
    if not all_locks:
        return ActiveLocksResponse(locks=[])

    # Step 2: Filter to documents in the requested scope
    locked_doc_ids = list(all_locks.keys())
    locked_uuids = []
    for doc_id in locked_doc_ids:
        try:
            locked_uuids.append(UUID(doc_id))
        except ValueError:
            continue

    if not locked_uuids:
        return ActiveLocksResponse(locks=[])

    # Query which of the locked documents belong to this scope.
    # For application scope, include project-scoped docs (application_id is NULL
    # on the document, but the parent project belongs to this application).
    if scope == "application":
        scope_filter = or_(
            Document.application_id == scope_id,
            Document.project_id.in_(
                select(Project.id).where(Project.application_id == scope_id)
            ),
        )
    else:
        scope_filter = get_scope_filter(Document, scope, scope_id)

    result = await db.execute(
        select(Document.id)
        .where(Document.id.in_(locked_uuids))
        .where(scope_filter)
        .where(Document.deleted_at.is_(None))
    )
    scope_doc_ids = {str(row[0]) for row in result.all()}

    # Step 3: Build response with only in-scope locks
    locks = [
        ActiveLockItem(
            document_id=doc_id,
            lock_holder=LockHolder(**lock_data),
        )
        for doc_id, lock_data in all_locks.items()
        if doc_id in scope_doc_ids
    ]

    return ActiveLocksResponse(locks=locks)


# ============================================================================
# Lock Endpoints
# ============================================================================


@router.post(
    "/{document_id}/lock",
    response_model=DocumentLockResponse,
    summary="Acquire document lock",
    description="Acquire an exclusive edit lock on a document. Returns 409 if already locked.",
    responses={
        200: {"description": "Lock acquired successfully"},
        401: {"description": "Not authenticated"},
        409: {"description": "Document is already locked by another user"},
    },
)
async def acquire_lock(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Acquire an exclusive edit lock on a document."""
    # Permission check: only users with edit access can acquire locks
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id).where(Document.deleted_at.is_(None))
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this document",
        )

    result = await lock_service.acquire_lock(
        document_id=str(document_id),
        user_id=str(current_user.id),
        user_name=current_user.display_name or current_user.email,
    )

    if result is None:
        # Already locked by another user
        holder = await lock_service.get_lock_holder(str(document_id))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Document is locked",
                "lock_holder": holder,
            },
        )

    # Resolve scope IDs for WebSocket broadcast
    doc_result = await db.execute(
        select(Document.application_id, Document.project_id).where(Document.id == document_id)
    )
    doc_scope = doc_result.one_or_none()
    app_id, proj_id = await _resolve_lock_broadcast_ids(
        db,
        doc_scope.application_id if doc_scope else None,
        doc_scope.project_id if doc_scope else None,
    )

    await handle_document_lock_change(
        document_id=str(document_id),
        lock_type="locked",
        lock_holder=result,
        application_id=app_id,
        project_id=proj_id,
    )

    return DocumentLockResponse(
        locked=True,
        lock_holder=LockHolder(**result),
    )


@router.delete(
    "/{document_id}/lock",
    response_model=DocumentLockResponse,
    summary="Release document lock",
    description="Release an edit lock on a document. Only the lock owner can release.",
    responses={
        200: {"description": "Lock released successfully"},
        401: {"description": "Not authenticated"},
        409: {"description": "Lock not held by you"},
    },
)
async def release_lock(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Release an edit lock on a document."""
    released = await lock_service.release_lock(
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    if released:
        # Resolve scope IDs for WebSocket broadcast
        doc_result = await db.execute(
            select(Document.application_id, Document.project_id).where(Document.id == document_id)
        )
        doc_scope = doc_result.one_or_none()
        app_id, proj_id = await _resolve_lock_broadcast_ids(
            db,
            doc_scope.application_id if doc_scope else None,
            doc_scope.project_id if doc_scope else None,
        )

        await handle_document_lock_change(
            document_id=str(document_id),
            lock_type="unlocked",
            lock_holder=None,
            application_id=app_id,
            project_id=proj_id,
        )

        return DocumentLockResponse(locked=False, lock_holder=None)

    # Lock not held by this user (or already expired)
    holder = await lock_service.get_lock_holder(str(document_id))
    if holder is None:
        # Lock already expired/released — return success (idempotent)
        return DocumentLockResponse(locked=False, lock_holder=None)

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Lock is held by another user",
    )


@router.get(
    "/{document_id}/lock",
    response_model=DocumentLockResponse,
    summary="Get lock status",
    description="Get the current lock status and holder info for a document.",
    responses={
        200: {"description": "Lock status retrieved"},
        401: {"description": "Not authenticated"},
    },
)
async def get_lock_status(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Get the current lock status for a document."""
    # Verify document exists and user can view it before exposing lock info
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id).where(Document.deleted_at.is_(None))
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_view_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this document",
        )

    holder = await lock_service.get_lock_holder(str(document_id))

    if holder:
        return DocumentLockResponse(
            locked=True,
            lock_holder=LockHolder(**holder),
        )
    return DocumentLockResponse(locked=False, lock_holder=None)


@router.post(
    "/{document_id}/lock/heartbeat",
    summary="Extend lock TTL",
    description="Extend the lock TTL. Only the lock owner can heartbeat.",
    responses={
        200: {"description": "Lock TTL extended"},
        401: {"description": "Not authenticated"},
        409: {"description": "Lock not held by you"},
    },
)
async def lock_heartbeat(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> dict:
    """Extend the lock TTL (heartbeat)."""
    extended = await lock_service.heartbeat(
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    if not extended:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lock not held by you",
        )

    return {"extended": True}


@router.post(
    "/{document_id}/lock/force-take",
    response_model=DocumentLockResponse,
    summary="Force-take document lock",
    description="Force-take a lock from another user. Requires application owner role.",
    responses={
        200: {"description": "Lock force-taken successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden - not an application owner"},
        404: {"description": "Document not found"},
    },
)
async def force_take_lock(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Force-take a lock from another user (application owners only)."""
    # Look up the document (exclude soft-deleted documents)
    result = await db.execute(
        select(Document).where(Document.id == document_id).where(Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found",
        )

    # Personal documents (user_id set, no application or project) cannot be force-taken
    if document.user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot force-take personal documents",
        )

    # Resolve the application_id for permission check
    app_id = document.application_id
    if app_id is None and document.project_id is not None:
        # Project-scoped doc: look up parent application
        proj_result = await db.execute(
            select(Project.application_id).where(Project.id == document.project_id)
        )
        app_id = proj_result.scalar_one_or_none()

    if app_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot determine document scope for permission check",
        )

    # Check application owner role
    perm_service = PermissionService(db)
    role = await perm_service.get_user_application_role(
        current_user.id, app_id
    )

    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only application owners can force-take locks",
        )

    # Force-take the lock — capture previous holder for notification
    old_holder = await lock_service.force_take_lock(
        document_id=str(document_id),
        new_user_id=str(current_user.id),
        new_user_name=current_user.display_name or current_user.email,
    )

    new_holder = await lock_service.get_lock_holder(str(document_id))

    # Resolve scope IDs for WebSocket broadcast
    app_id, proj_id = await _resolve_lock_broadcast_ids(
        db, document.application_id, document.project_id
    )
    await handle_document_lock_change(
        document_id=str(document_id),
        lock_type="force_taken",
        lock_holder=new_holder,
        triggered_by=str(current_user.id),
        previous_holder=old_holder,
        application_id=app_id,
        project_id=proj_id,
    )

    return DocumentLockResponse(
        locked=True,
        lock_holder=LockHolder(**new_holder) if new_holder else None,
    )

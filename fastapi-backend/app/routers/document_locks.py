"""Document lock API endpoints.

Provides endpoints for acquiring, releasing, heartbeating, querying, and
force-taking document locks. All endpoints require authentication.
Lock state changes are broadcast via WebSocket to document room subscribers.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.document import Document
from ..models.user import User
from ..schemas.document_lock import DocumentLockResponse, LockHolder
from ..services.auth_service import get_current_user
from ..services.document_lock_service import DocumentLockService, get_lock_service
from ..services.permission_service import PermissionService
from ..websocket.handlers import handle_document_lock_change

router = APIRouter(prefix="/api/documents", tags=["document-locks"])


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
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Acquire an exclusive edit lock on a document."""
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

    # Broadcast lock acquired
    await handle_document_lock_change(
        document_id=str(document_id),
        lock_type="locked",
        lock_holder=result,
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
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Release an edit lock on a document."""
    released = await lock_service.release_lock(
        document_id=str(document_id),
        user_id=str(current_user.id),
    )

    if released:
        # Broadcast lock released
        await handle_document_lock_change(
            document_id=str(document_id),
            lock_type="unlocked",
            lock_holder=None,
        )

    return DocumentLockResponse(locked=False, lock_holder=None)


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
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Get the current lock status for a document."""
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
    # Look up the document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found",
        )

    # Personal documents cannot be force-taken
    if document.application_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot force-take personal documents",
        )

    # Check application owner role
    perm_service = PermissionService(db)
    role = await perm_service.get_user_application_role(
        current_user.id, document.application_id
    )

    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only application owners can force-take locks",
        )

    # Force-take the lock (old_holder returned but not needed for response)
    await lock_service.force_take_lock(
        document_id=str(document_id),
        new_user_id=str(current_user.id),
        new_user_name=current_user.display_name or current_user.email,
    )

    new_holder = await lock_service.get_lock_holder(str(document_id))

    # Broadcast force-take event
    await handle_document_lock_change(
        document_id=str(document_id),
        lock_type="force_taken",
        lock_holder=new_holder,
        triggered_by=str(current_user.id),
    )

    return DocumentLockResponse(
        locked=True,
        lock_holder=LockHolder(**new_holder) if new_holder else None,
    )

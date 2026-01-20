"""Checklists API endpoints.

Provides endpoints for managing task checklists and items.
All endpoints require authentication.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.application_member import ApplicationMember
from ..models.checklist import Checklist
from ..models.project import Project
from ..models.task import Task
from ..models.user import User
from ..schemas.checklist import (
    ChecklistCreate,
    ChecklistItemCreate,
    ChecklistItemResponse,
    ChecklistItemUpdate,
    ChecklistResponse,
    ChecklistUpdate,
    ReorderRequest,
)
from ..services.auth_service import get_current_user
from ..services.checklist_service import (
    build_checklist_item_response,
    build_checklist_response,
    create_checklist,
    create_checklist_item,
    delete_checklist,
    delete_checklist_item,
    get_checklist,
    get_checklists_for_task,
    reorder_checklist_items,
    reorder_checklists,
    toggle_checklist_item,
    update_checklist,
    update_checklist_item,
)
from ..websocket.handlers import (
    handle_checklist_created,
    handle_checklist_item_toggled,
)

router = APIRouter(tags=["Checklists"])


# ============================================================================
# Helper Functions
# ============================================================================


def verify_task_access(
    task_id: UUID,
    current_user: User,
    db: Session,
    require_edit: bool = False,
) -> Task:
    """
    Verify that the user has access to the task via application membership.

    Args:
        task_id: The UUID of the task
        current_user: The authenticated user
        db: Database session
        require_edit: If True, require owner or editor role

    Returns:
        Task: The verified task

    Raises:
        HTTPException: If task not found or user doesn't have access
    """
    task = db.query(Task).options(
        joinedload(Task.project).joinedload(Project.application)
    ).filter(
        Task.id == task_id,
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found",
        )

    application_id = task.project.application_id

    # Check if user is the owner
    if task.project.application.owner_id == current_user.id:
        return task

    # Check ApplicationMembers
    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == current_user.id,
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    if require_edit and member.role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Viewers cannot modify checklists.",
        )

    return task


# ============================================================================
# Checklist Endpoints
# ============================================================================


@router.get(
    "/api/tasks/{task_id}/checklists",
    response_model=List[ChecklistResponse],
    summary="Get checklists for a task",
    description="Get all checklists for a task with their items.",
    responses={
        200: {"description": "Checklists retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Task not found"},
    },
)
async def list_checklists(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> List[ChecklistResponse]:
    """Get all checklists for a task."""
    verify_task_access(task_id, current_user, db)

    checklists = get_checklists_for_task(db, task_id)
    return [ChecklistResponse(**build_checklist_response(c)) for c in checklists]


@router.post(
    "/api/tasks/{task_id}/checklists",
    response_model=ChecklistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a checklist",
    description="Create a new checklist for a task.",
    responses={
        201: {"description": "Checklist created successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Task not found"},
    },
)
async def create_checklist_endpoint(
    task_id: UUID,
    checklist_data: ChecklistCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ChecklistResponse:
    """Create a new checklist for a task."""
    task = verify_task_access(task_id, current_user, db, require_edit=True)

    checklist = create_checklist(db, task_id, checklist_data)

    # Reload with items
    checklist = get_checklist(db, checklist.id)
    response = build_checklist_response(checklist)

    # Broadcast WebSocket event
    await handle_checklist_created(
        task_id=task_id,
        checklist_data=response,
        user_id=current_user.id,
    )

    return ChecklistResponse(**response)


@router.put(
    "/api/checklists/{checklist_id}",
    response_model=ChecklistResponse,
    summary="Update a checklist",
    description="Update a checklist's title.",
    responses={
        200: {"description": "Checklist updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Checklist not found"},
    },
)
async def update_checklist_endpoint(
    checklist_id: UUID,
    checklist_data: ChecklistUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ChecklistResponse:
    """Update a checklist."""
    # Get checklist to find task_id
    checklist = get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    updated = update_checklist(db, checklist_id, checklist_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    # Reload with items
    updated = get_checklist(db, checklist_id)
    return ChecklistResponse(**build_checklist_response(updated))


@router.delete(
    "/api/checklists/{checklist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a checklist",
    description="Delete a checklist and all its items.",
    responses={
        204: {"description": "Checklist deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Checklist not found"},
    },
)
async def delete_checklist_endpoint(
    checklist_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """Delete a checklist."""
    # Get checklist to find task_id
    checklist = get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    deleted = delete_checklist(db, checklist_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )


@router.put(
    "/api/tasks/{task_id}/checklists/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reorder checklists",
    description="Reorder checklists for a task.",
    responses={
        204: {"description": "Checklists reordered successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Task not found"},
    },
)
async def reorder_checklists_endpoint(
    task_id: UUID,
    reorder_data: ReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """Reorder checklists for a task."""
    verify_task_access(task_id, current_user, db, require_edit=True)

    success = reorder_checklists(db, task_id, reorder_data.item_ids)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid checklist IDs provided",
        )


# ============================================================================
# Checklist Item Endpoints
# ============================================================================


@router.post(
    "/api/checklists/{checklist_id}/items",
    response_model=ChecklistItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a checklist item",
    description="Create a new item in a checklist.",
    responses={
        201: {"description": "Item created successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Checklist not found"},
    },
)
async def create_item_endpoint(
    checklist_id: UUID,
    item_data: ChecklistItemCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ChecklistItemResponse:
    """Create a new item in a checklist."""
    # Get checklist to find task_id
    checklist = get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    item = create_checklist_item(db, checklist_id, item_data)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    return ChecklistItemResponse(**build_checklist_item_response(item))


@router.put(
    "/api/checklist-items/{item_id}",
    response_model=ChecklistItemResponse,
    summary="Update a checklist item",
    description="Update a checklist item's text or status.",
    responses={
        200: {"description": "Item updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Item not found"},
    },
)
async def update_item_endpoint(
    item_id: UUID,
    item_data: ChecklistItemUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ChecklistItemResponse:
    """Update a checklist item."""
    # Get item to find checklist and task
    from ..models.checklist_item import ChecklistItem
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    checklist = get_checklist(db, item.checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    updated = update_checklist_item(db, item_id, item_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    return ChecklistItemResponse(**build_checklist_item_response(updated))


@router.post(
    "/api/checklist-items/{item_id}/toggle",
    response_model=ChecklistItemResponse,
    summary="Toggle a checklist item",
    description="Toggle a checklist item's done status.",
    responses={
        200: {"description": "Item toggled successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Item not found"},
    },
)
async def toggle_item_endpoint(
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ChecklistItemResponse:
    """Toggle a checklist item's done status."""
    # Get item to find checklist and task
    from ..models.checklist_item import ChecklistItem
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    checklist = get_checklist(db, item.checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    task = verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    result = toggle_checklist_item(db, item_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    toggled_item, checklist_id, task_id = result

    # Broadcast WebSocket event
    await handle_checklist_item_toggled(
        task_id=task_id,
        checklist_id=checklist_id,
        item_id=item_id,
        is_done=toggled_item.is_done,
        user_id=current_user.id,
        project_id=task.project_id,
    )

    return ChecklistItemResponse(**build_checklist_item_response(toggled_item))


@router.delete(
    "/api/checklist-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a checklist item",
    description="Delete a checklist item.",
    responses={
        204: {"description": "Item deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Item not found"},
    },
)
async def delete_item_endpoint(
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """Delete a checklist item."""
    # Get item to find checklist and task
    from ..models.checklist_item import ChecklistItem
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    checklist = get_checklist(db, item.checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    result = delete_checklist_item(db, item_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )


@router.put(
    "/api/checklists/{checklist_id}/items/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reorder checklist items",
    description="Reorder items within a checklist.",
    responses={
        204: {"description": "Items reordered successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Checklist not found"},
    },
)
async def reorder_items_endpoint(
    checklist_id: UUID,
    reorder_data: ReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """Reorder items within a checklist."""
    # Get checklist to find task_id
    checklist = get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    success = reorder_checklist_items(db, checklist_id, reorder_data.item_ids)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid item IDs provided",
        )

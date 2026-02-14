"""Checklists API endpoints.

Provides endpoints for managing task checklists and items.
All endpoints require authentication.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.checklist import Checklist
from ..models.project import Project
from ..models.project_member import ProjectMember
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
    handle_checklist_updated,
    handle_checklist_deleted,
    handle_checklists_reordered,
    handle_checklist_item_toggled,
    handle_checklist_item_added,
    handle_checklist_item_updated,
    handle_checklist_item_deleted,
    handle_checklist_items_reordered,
)

router = APIRouter(tags=["Checklists"])


# ============================================================================
# Helper Functions
# ============================================================================


async def verify_task_access(
    task_id: UUID,
    current_user: User,
    db: AsyncSession,
    require_edit: bool = False,
) -> Task:
    """
    Verify that the user has access to the task.

    Permission rules for VIEW (require_edit=False):
    - Application Owner: Allowed
    - Application Member (editor, viewer): Allowed
    - Project Admin/Member: Allowed

    Permission rules for EDIT (require_edit=True):
    - Application Owner: Allowed
    - Project Admin/Member: Allowed
    - Application Editor (non-project member): NOT allowed
    - Viewer: NOT allowed

    Args:
        task_id: The UUID of the task
        current_user: The authenticated user
        db: Database session
        require_edit: If True, require edit permission (owner or project member)

    Returns:
        Task: The verified task

    Raises:
        HTTPException: If task not found or user doesn't have access
    """
    from ..models.application_member import ApplicationMember

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.project).selectinload(Project.application))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found",
        )

    # Business rule: Done tasks cannot have checklists modified
    if require_edit and task.task_status and task.task_status.category == "Done":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify checklists on a completed task. Reopen the task first.",
        )

    # Check if user is the application owner - always has full access
    if task.project.application.owner_id == current_user.id:
        return task

    # Check if user is a project member (admin or member) - always has full access
    # Uses EXISTS pattern for optimal performance
    result = await db.execute(
        select(
            exists().where(
                ProjectMember.project_id == task.project_id,
                ProjectMember.user_id == current_user.id,
            )
        )
    )
    is_project_member = result.scalar() or False

    if is_project_member:
        return task

    # For edit operations, only owner and project members are allowed
    if require_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be the application owner or a project member to edit checklists.",
        )

    # For view operations, check if user is an application member (viewer/editor)
    # Uses EXISTS pattern for optimal performance
    result = await db.execute(
        select(
            exists().where(
                ApplicationMember.application_id == task.project.application_id,
                ApplicationMember.user_id == current_user.id,
            )
        )
    )
    is_application_member = result.scalar() or False

    if is_application_member:
        return task

    # User doesn't have access
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied. You must be a member of this application to view checklists.",
    )


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
    db: AsyncSession = Depends(get_db),
) -> List[ChecklistResponse]:
    """Get all checklists for a task."""
    await verify_task_access(task_id, current_user, db)

    checklists = await get_checklists_for_task(db, task_id)
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
    db: AsyncSession = Depends(get_db),
) -> ChecklistResponse:
    """Create a new checklist for a task."""
    task = await verify_task_access(task_id, current_user, db, require_edit=True)

    checklist = await create_checklist(db, task_id, checklist_data)

    # Reload with items
    checklist = await get_checklist(db, checklist.id)
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
    db: AsyncSession = Depends(get_db),
) -> ChecklistResponse:
    """Update a checklist."""
    # Get checklist to find task_id
    checklist = await get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    await verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    updated = await update_checklist(db, checklist_id, checklist_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    # Reload with items
    updated = await get_checklist(db, checklist_id)
    response = build_checklist_response(updated)

    # Broadcast WebSocket event
    await handle_checklist_updated(
        task_id=checklist.task_id,
        checklist_id=checklist_id,
        checklist_data=response,
    )

    return ChecklistResponse(**response)


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
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a checklist."""
    # Get checklist to find task_id
    checklist = await get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    task = await verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    deleted = await delete_checklist(db, checklist_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    # Broadcast WebSocket event
    await handle_checklist_deleted(
        task_id=checklist.task_id,
        checklist_id=checklist_id,
        project_id=task.project_id,
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
    db: AsyncSession = Depends(get_db),
) -> None:
    """Reorder checklists for a task."""
    await verify_task_access(task_id, current_user, db, require_edit=True)

    success = await reorder_checklists(db, task_id, reorder_data.item_ids)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid checklist IDs provided",
        )

    # Broadcast WebSocket event
    await handle_checklists_reordered(
        task_id=task_id,
        checklist_ids=reorder_data.item_ids,
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
    db: AsyncSession = Depends(get_db),
) -> ChecklistItemResponse:
    """Create a new item in a checklist."""
    # Get checklist to find task_id
    checklist = await get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    await verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    item = await create_checklist_item(db, checklist_id, item_data)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    response = build_checklist_item_response(item)

    # Broadcast WebSocket event
    await handle_checklist_item_added(
        task_id=checklist.task_id,
        checklist_id=checklist_id,
        item_data=response,
    )

    return ChecklistItemResponse(**response)


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
    db: AsyncSession = Depends(get_db),
) -> ChecklistItemResponse:
    """Update a checklist item."""
    # Get item to find checklist and task
    from ..models.checklist_item import ChecklistItem
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    checklist = await get_checklist(db, item.checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    await verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    updated = await update_checklist_item(db, item_id, item_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    response = build_checklist_item_response(updated)

    # Broadcast WebSocket event
    await handle_checklist_item_updated(
        task_id=checklist.task_id,
        item_id=item_id,
        item_data=response,
    )

    return ChecklistItemResponse(**response)


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
    db: AsyncSession = Depends(get_db),
) -> ChecklistItemResponse:
    """Toggle a checklist item's done status."""
    # Get item to find checklist and task
    from ..models.checklist_item import ChecklistItem
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    checklist = await get_checklist(db, item.checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    task = await verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    result = await toggle_checklist_item(db, item_id, user_id=current_user.id)
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
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a checklist item."""
    # Get item to find checklist and task
    from ..models.checklist_item import ChecklistItem
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    checklist = await get_checklist(db, item.checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    await verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    result = await delete_checklist_item(db, item_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    # Broadcast WebSocket event
    await handle_checklist_item_deleted(
        task_id=checklist.task_id,
        checklist_id=item.checklist_id,
        item_id=item_id,
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
    db: AsyncSession = Depends(get_db),
) -> None:
    """Reorder items within a checklist."""
    # Get checklist to find task_id
    checklist = await get_checklist(db, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist not found",
        )

    await verify_task_access(checklist.task_id, current_user, db, require_edit=True)

    success = await reorder_checklist_items(db, checklist_id, reorder_data.item_ids)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid item IDs provided",
        )

    # Broadcast WebSocket event
    await handle_checklist_items_reordered(
        task_id=checklist.task_id,
        checklist_id=checklist_id,
        item_ids=reorder_data.item_ids,
    )

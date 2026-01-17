"""Notifications CRUD API endpoints.

Provides endpoints for managing user notifications.
All endpoints require authentication.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.notification import Notification
from ..models.user import User
from ..schemas.notification import (
    EntityType,
    NotificationBulkUpdate,
    NotificationCount,
    NotificationResponse,
    NotificationType,
    NotificationUpdate,
)
from ..services.auth_service import get_current_user
from ..websocket.handlers import handle_notification_read

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


# ============================================================================
# List and Count endpoints
# ============================================================================


@router.get(
    "",
    response_model=List[NotificationResponse],
    summary="List user notifications",
    description="Get all notifications for the authenticated user.",
    responses={
        200: {"description": "List of notifications retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    unread_only: bool = Query(False, description="Return only unread notifications"),
    notification_type: Optional[NotificationType] = Query(
        None,
        alias="type",
        description="Filter by notification type",
    ),
    entity_type: Optional[EntityType] = Query(
        None,
        description="Filter by entity type",
    ),
) -> List[NotificationResponse]:
    """
    List notifications for the authenticated user.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)
    - **unread_only**: If true, return only unread notifications
    - **type**: Optional filter by notification type
    - **entity_type**: Optional filter by related entity type

    Returns notifications ordered by creation date (newest first).
    """
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
    )

    # Apply unread filter if requested
    if unread_only:
        query = query.filter(Notification.is_read == False)

    # Apply notification type filter if provided
    if notification_type:
        query = query.filter(Notification.type == notification_type.value)

    # Apply entity type filter if provided
    if entity_type:
        query = query.filter(Notification.entity_type == entity_type.value)

    # Order by newest first
    query = query.order_by(Notification.created_at.desc())

    # Apply pagination
    notifications = query.offset(skip).limit(limit).all()

    return notifications


@router.get(
    "/count",
    response_model=NotificationCount,
    summary="Get notification counts",
    description="Get total and unread notification counts for the authenticated user.",
    responses={
        200: {"description": "Notification counts retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def get_notification_count(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> NotificationCount:
    """
    Get notification counts for the authenticated user.

    Returns:
    - total: Total number of notifications
    - unread: Number of unread notifications
    """
    total = db.query(func.count(Notification.id)).filter(
        Notification.user_id == current_user.id,
    ).scalar() or 0

    unread = db.query(func.count(Notification.id)).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
    ).scalar() or 0

    return NotificationCount(total=total, unread=unread)


# ============================================================================
# Individual notification endpoints
# ============================================================================


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Get a notification by ID",
    description="Get details of a specific notification.",
    responses={
        200: {"description": "Notification retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not your notification"},
        404: {"description": "Notification not found"},
    },
)
async def get_notification(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """
    Get a specific notification by its ID.

    Only the notification's owner can access it.
    """
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
    ).first()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found",
        )

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This notification belongs to another user.",
        )

    return notification


@router.put(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Update a notification",
    description="Update a notification's read status.",
    responses={
        200: {"description": "Notification updated successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not your notification"},
        404: {"description": "Notification not found"},
    },
)
async def update_notification(
    notification_id: UUID,
    notification_data: NotificationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """
    Update a notification's read status.

    - **is_read**: New read status (true/false)

    Only the notification's owner can update it.
    Broadcasts the read status change via WebSocket to sync across devices.
    """
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
    ).first()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found",
        )

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This notification belongs to another user.",
        )

    # Update read status if provided
    if notification_data.is_read is not None:
        notification.is_read = notification_data.is_read

    db.commit()
    db.refresh(notification)

    # Broadcast read status via WebSocket if marked as read
    if notification_data.is_read:
        await handle_notification_read(current_user.id, notification_id)

    return notification


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a notification",
    description="Delete a notification.",
    responses={
        204: {"description": "Notification deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not your notification"},
        404: {"description": "Notification not found"},
    },
)
async def delete_notification(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a notification.

    Only the notification's owner can delete it.
    This action is irreversible.
    """
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
    ).first()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found",
        )

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This notification belongs to another user.",
        )

    db.delete(notification)
    db.commit()

    return None


# ============================================================================
# Bulk operations
# ============================================================================


@router.post(
    "/mark-read",
    response_model=dict,
    summary="Mark notifications as read",
    description="Mark multiple notifications as read at once.",
    responses={
        200: {"description": "Notifications marked as read"},
        401: {"description": "Not authenticated"},
    },
)
async def mark_notifications_read(
    bulk_data: NotificationBulkUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """
    Mark multiple notifications as read.

    - **notification_ids**: List of notification IDs to update
    - **is_read**: New read status (typically true)

    Only notifications belonging to the current user will be updated.
    Returns the count of successfully updated notifications.
    """
    updated_count = db.query(Notification).filter(
        Notification.id.in_(bulk_data.notification_ids),
        Notification.user_id == current_user.id,
    ).update(
        {"is_read": bulk_data.is_read},
        synchronize_session=False,
    )

    db.commit()

    # Broadcast read status for each notification via WebSocket
    if bulk_data.is_read:
        for notification_id in bulk_data.notification_ids:
            await handle_notification_read(current_user.id, notification_id)

    return {
        "message": f"Updated {updated_count} notifications",
        "updated_count": updated_count,
    }


@router.post(
    "/mark-all-read",
    response_model=dict,
    summary="Mark all notifications as read",
    description="Mark all unread notifications as read.",
    responses={
        200: {"description": "All notifications marked as read"},
        401: {"description": "Not authenticated"},
    },
)
async def mark_all_notifications_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """
    Mark all unread notifications as read.

    Updates all notifications belonging to the current user
    where is_read is false.
    """
    updated_count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
    ).update(
        {"is_read": True},
        synchronize_session=False,
    )

    db.commit()

    return {
        "message": f"Marked {updated_count} notifications as read",
        "updated_count": updated_count,
    }


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all notifications",
    description="Delete all notifications for the current user.",
    responses={
        204: {"description": "All notifications deleted"},
        401: {"description": "Not authenticated"},
    },
)
async def delete_all_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    read_only: bool = Query(False, description="Delete only read notifications"),
) -> None:
    """
    Delete notifications for the current user.

    - **read_only**: If true, only delete read notifications

    This action is irreversible.
    """
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
    )

    if read_only:
        query = query.filter(Notification.is_read == True)

    query.delete(synchronize_session=False)
    db.commit()

    return None

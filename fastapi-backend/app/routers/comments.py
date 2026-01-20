"""Comments API endpoints.

Provides endpoints for managing comments on tasks with @mentions support.
All endpoints require authentication.
"""

from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.application_member import ApplicationMember
from ..models.comment import Comment
from ..models.project import Project
from ..models.task import Task
from ..models.user import User
from ..schemas.comment import (
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    CommentUpdate,
)
from ..services.auth_service import get_current_user
from ..services.comment_service import (
    build_comment_response,
    count_comments_for_task,
    create_comment,
    delete_comment,
    get_comment,
    get_comments_for_task,
    update_comment,
)
from ..services.notification_service import create_mention_notification
from ..websocket.handlers import (
    handle_comment_added,
    handle_comment_deleted,
    handle_comment_updated,
)

router = APIRouter(tags=["Comments"])


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
    # Fetch task with project and application
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

    # Check application membership
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
            detail="Access denied. Viewers cannot comment on tasks.",
        )

    return task


# ============================================================================
# Comment Endpoints
# ============================================================================


@router.get(
    "/api/tasks/{task_id}/comments",
    response_model=CommentListResponse,
    summary="Get comments for a task",
    description="Get paginated comments for a task with cursor-based pagination.",
    responses={
        200: {"description": "Comments retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Task not found"},
    },
)
async def list_comments(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    cursor: Optional[str] = Query(
        None,
        description="Cursor for pagination (ISO datetime string)",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum number of comments to return",
    ),
) -> CommentListResponse:
    """
    Get comments for a task.

    Returns comments in newest-first order with cursor-based pagination.
    The cursor is an ISO datetime string representing the oldest comment
    from the previous page.
    """
    # Verify access
    verify_task_access(task_id, current_user, db)

    # Parse cursor
    cursor_dt = None
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor format. Expected ISO datetime string.",
            )

    # Get comments
    comments, next_cursor = get_comments_for_task(
        db=db,
        task_id=task_id,
        cursor=cursor_dt,
        limit=limit,
    )

    # Build response
    items = [build_comment_response(c) for c in comments]

    return CommentListResponse(
        items=items,
        next_cursor=next_cursor.isoformat() if next_cursor else None,
    )


@router.post(
    "/api/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a comment",
    description="Create a new comment on a task with optional @mentions.",
    responses={
        201: {"description": "Comment created successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Task not found"},
    },
)
async def create_comment_endpoint(
    task_id: UUID,
    comment_data: CommentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommentResponse:
    """
    Create a new comment on a task.

    Supports TipTap JSON format for rich text with @mentions.
    Mentioned users will receive notifications.
    """
    # Verify access (require edit permission to comment)
    task = verify_task_access(task_id, current_user, db, require_edit=True)

    # Create comment
    comment, mentioned_user_ids = create_comment(
        db=db,
        task_id=task_id,
        author_id=current_user.id,
        comment_data=comment_data,
    )

    # Reload comment with relationships
    comment = get_comment(db, comment.id)

    # Build response
    response = build_comment_response(comment)

    # Broadcast WebSocket event
    await handle_comment_added(
        task_id=task_id,
        comment_data=response,
        mentioned_user_ids=mentioned_user_ids,
    )

    # Create notifications for mentioned users
    for user_id in mentioned_user_ids:
        if user_id != current_user.id:  # Don't notify self
            await create_mention_notification(
                db=db,
                mentioned_user_id=user_id,
                mentioner_id=current_user.id,
                task_id=task_id,
                comment_id=comment.id,
            )

    return CommentResponse(**response)


@router.put(
    "/api/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Update a comment",
    description="Update an existing comment. Only the author can update.",
    responses={
        200: {"description": "Comment updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the author"},
        404: {"description": "Comment not found"},
    },
)
async def update_comment_endpoint(
    comment_id: UUID,
    comment_data: CommentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> CommentResponse:
    """
    Update an existing comment.

    Only the comment author can update their own comments.
    """
    # Update comment
    result = update_comment(
        db=db,
        comment_id=comment_id,
        author_id=current_user.id,
        comment_data=comment_data,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found or you are not the author",
        )

    comment, added_mentions, removed_mentions = result

    # Reload with relationships
    comment = get_comment(db, comment.id)

    # Build response
    response = build_comment_response(comment)

    # Broadcast WebSocket event
    await handle_comment_updated(
        task_id=comment.task_id,
        comment_id=comment_id,
        comment_data=response,
    )

    # Create notifications for newly mentioned users
    for user_id in added_mentions:
        if user_id != current_user.id:
            await create_mention_notification(
                db=db,
                mentioned_user_id=user_id,
                mentioner_id=current_user.id,
                task_id=comment.task_id,
                comment_id=comment.id,
            )

    return CommentResponse(**response)


@router.delete(
    "/api/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
    description="Soft-delete a comment. Only the author can delete.",
    responses={
        204: {"description": "Comment deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the author"},
        404: {"description": "Comment not found"},
    },
)
async def delete_comment_endpoint(
    comment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Soft-delete a comment.

    Only the comment author can delete their own comments.
    The comment content will be replaced with "[deleted]".
    """
    # Get comment first to get task_id for WebSocket
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.author_id == current_user.id,
        Comment.is_deleted == False,
    ).first()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found or you are not the author",
        )

    task_id = comment.task_id

    # Delete comment
    deleted = delete_comment(
        db=db,
        comment_id=comment_id,
        author_id=current_user.id,
        soft_delete=True,
    )

    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found or you are not the author",
        )

    # Broadcast WebSocket event
    await handle_comment_deleted(
        task_id=task_id,
        comment_id=comment_id,
    )

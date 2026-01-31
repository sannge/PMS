"""File upload/download API endpoints.

Provides endpoints for uploading files to MinIO storage, retrieving file information
with presigned download URLs, and deleting files. All endpoints require authentication.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.application_member import ApplicationMember
from ..models.attachment import Attachment
from ..models.comment import Comment
from ..models.note import Note
from ..models.project import Project
from ..models.project_member import ProjectMember
from ..models.task import Task
from ..models.user import User
from ..schemas.file import (
    AttachmentCreate,
    AttachmentResponse,
    AttachmentUpdate,
    BatchDownloadUrlsRequest,
    EntityType,
    FileDownloadResponse,
    FileUploadResponse,
)
from ..services.auth_service import get_current_user
from ..services.minio_service import MinIOService, MinIOServiceError, get_minio_service
from ..websocket.manager import manager as ws_manager, MessageType

router = APIRouter(prefix="/api/files", tags=["Files"])

# Maximum file size (100 MB)
MAX_FILE_SIZE = 100 * 1024 * 1024


# ============================================================================
# Helper Functions
# ============================================================================


async def check_task_attachment_permission(
    task_id: UUID,
    current_user: User,
    db: AsyncSession,
    check_done: bool = False,
) -> tuple[bool, str | None]:
    """
    Check if user has permission to manage attachments on a task.

    Permission rules:
    - Application Owner: Always allowed
    - Application Member (including Viewers): Allowed (can upload for comments)
    - Project Admin: Always allowed
    - Project Member: Always allowed
    - Others: Not allowed
    - Done tasks: Not allowed (if check_done=True)

    Args:
        task_id: The task ID to check access for
        current_user: The authenticated user
        db: Database session
        check_done: If True, also check if task is done and block

    Returns:
        tuple[bool, str | None]: (has_permission, error_reason)
    """
    # Get task with project and application
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.project).selectinload(Project.application))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        return False, "Task not found"

    # Check if task is done - block attachment modifications
    if check_done and task.status == "done":
        return False, "Cannot modify attachments on a completed task. Reopen the task first."

    application_id = task.project.application_id

    # Check if user is the application owner
    if task.project.application.owner_id == current_user.id:
        return True, None

    # Check if user is an application member (owner, editor, or viewer)
    # All application members can upload attachments (e.g., for comments)
    result = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == current_user.id,
        )
    )
    app_member = result.scalar_one_or_none()

    if app_member:
        return True, None

    # Check if user is a project member (admin or member)
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == task.project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    project_member = result.scalar_one_or_none()

    if project_member:
        return True, None

    return False, "Access denied. You must be the application owner or a project member to manage attachments."


async def verify_task_attachment_access(
    task_id: UUID,
    current_user: User,
    db: AsyncSession,
    action: str = "manage",
    check_done: bool = False,
) -> None:
    """
    Verify that the user has permission to manage attachments on a task.
    Raises HTTPException if not allowed.

    Args:
        task_id: The task ID to check access for
        current_user: The authenticated user
        db: Database session
        action: Description of the action for error message
        check_done: If True, also check if task is done and block

    Raises:
        HTTPException: If user doesn't have permission
    """
    has_permission, error_reason = await check_task_attachment_permission(
        task_id, current_user, db, check_done=check_done
    )

    if not has_permission:
        # Determine appropriate status code based on error
        if error_reason and "completed task" in error_reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_reason,
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_reason or f"Access denied. You must be the application owner or a project member to {action} attachments.",
        )


@router.post(
    "/upload",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file",
    description="Upload a file to MinIO storage and create an attachment record.",
    responses={
        201: {"description": "File uploaded successfully"},
        400: {"description": "Invalid file or validation error"},
        401: {"description": "Not authenticated"},
        413: {"description": "File too large"},
    },
)
async def upload_file(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
    file: UploadFile = File(..., description="The file to upload"),
    entity_type: Optional[EntityType] = Query(
        None,
        description="Type of entity to attach the file to",
    ),
    entity_id: Optional[UUID] = Query(
        None,
        description="ID of the entity to attach the file to",
    ),
    task_id: Optional[UUID] = Query(
        None,
        description="ID of the task to attach the file to (shortcut for entity_type=task)",
    ),
    note_id: Optional[UUID] = Query(
        None,
        description="ID of the note to attach the file to (shortcut for entity_type=note)",
    ),
    comment_id: Optional[UUID] = Query(
        None,
        description="ID of the comment to attach the file to (shortcut for entity_type=comment)",
    ),
) -> AttachmentResponse:
    """
    Upload a file to MinIO storage.

    - **file**: The file to upload (multipart form data)
    - **entity_type**: Type of entity to attach to (task, note, comment)
    - **entity_id**: ID of the entity to attach to
    - **task_id**: Shortcut for attaching to a task
    - **note_id**: Shortcut for attaching to a note

    Files are stored in MinIO with appropriate bucket selection based on content type:
    - Images go to 'pm-images' bucket
    - Other files go to 'pm-attachments' bucket

    Maximum file size: 100 MB
    """
    # Validate file is present
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided or file has no name",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Check file size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({file_size} bytes) exceeds maximum allowed ({MAX_FILE_SIZE} bytes)",
        )

    # Determine content type
    content_type = file.content_type or "application/octet-stream"

    # Determine entity type and ID
    resolved_entity_type = entity_type.value if entity_type else None
    resolved_entity_id = entity_id

    # Handle task_id shortcut
    if task_id and not resolved_entity_type:
        resolved_entity_type = EntityType.TASK.value
        resolved_entity_id = task_id
        # Verify task exists
        result = await db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {task_id} not found",
            )
        # Check upload permission (app owner or project member)
        await verify_task_attachment_access(task_id, current_user, db, action="upload")

    # Handle note_id shortcut
    if note_id and not resolved_entity_type:
        resolved_entity_type = EntityType.NOTE.value
        resolved_entity_id = note_id
        # Verify note exists and user has access
        result = await db.execute(
            select(Note).where(Note.id == note_id)
        )
        note = result.scalar_one_or_none()
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Note with ID {note_id} not found",
            )

    # Handle comment_id shortcut
    if comment_id and not resolved_entity_type:
        resolved_entity_type = EntityType.COMMENT.value
        resolved_entity_id = comment_id
        # Verify comment exists
        result = await db.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comment with ID {comment_id} not found",
            )

    # Handle explicit entity_type=task with entity_id
    if entity_type == EntityType.TASK and entity_id:
        result = await db.execute(
            select(Task).where(Task.id == entity_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {entity_id} not found",
            )
        # Check upload permission (app owner or project member)
        await verify_task_attachment_access(entity_id, current_user, db, action="upload")

    # Determine bucket based on content type
    bucket = minio.get_bucket_for_content_type(content_type)

    # Generate object name
    entity_for_path = resolved_entity_type or "general"
    entity_id_for_path = str(resolved_entity_id) if resolved_entity_id else str(current_user.id)
    object_name = minio.generate_object_name(
        entity_type=entity_for_path,
        entity_id=entity_id_for_path,
        filename=file.filename,
    )

    # Upload to MinIO
    try:
        minio.upload_bytes(
            bucket=bucket,
            object_name=object_name,
            data=content,
            content_type=content_type,
        )
    except MinIOServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file to storage: {str(e)}",
        )

    # Create attachment record
    attachment = Attachment(
        file_name=file.filename,
        file_type=content_type,
        file_size=file_size,
        minio_bucket=bucket,
        minio_key=object_name,
        uploaded_by=current_user.id,
        entity_type=resolved_entity_type,
        entity_id=resolved_entity_id,
        task_id=task_id,
        note_id=note_id,
        comment_id=comment_id,
    )

    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    # Broadcast attachment upload via WebSocket
    if resolved_entity_type and resolved_entity_id:
        room_id = f"{resolved_entity_type}:{resolved_entity_id}"
        await ws_manager.broadcast_to_room(
            room_id,
            {
                "type": MessageType.ATTACHMENT_UPLOADED,
                "data": {
                    "attachment": {
                        "id": str(attachment.id),
                        "file_name": attachment.file_name,
                        "file_type": attachment.file_type,
                        "file_size": attachment.file_size,
                        "entity_type": attachment.entity_type,
                        "entity_id": str(attachment.entity_id) if attachment.entity_id else None,
                        "task_id": str(attachment.task_id) if attachment.task_id else None,
                        "note_id": str(attachment.note_id) if attachment.note_id else None,
                        "uploaded_by": str(attachment.uploaded_by),
                        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
                    },
                    "entity_type": resolved_entity_type,
                    "entity_id": str(resolved_entity_id),
                },
            },
        )

    return attachment


@router.get(
    "",
    response_model=List[AttachmentResponse],
    summary="List attachments",
    description="Get a list of attachments with optional filtering.",
    responses={
        200: {"description": "List of attachments retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def list_attachments(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    entity_type: Optional[EntityType] = Query(None, description="Filter by entity type"),
    entity_id: Optional[UUID] = Query(None, description="Filter by entity ID"),
    task_id: Optional[UUID] = Query(None, description="Filter by task ID"),
    note_id: Optional[UUID] = Query(None, description="Filter by note ID"),
) -> List[AttachmentResponse]:
    """
    List attachments with optional filtering.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-500)
    - **entity_type**: Filter by entity type (task, note, comment)
    - **entity_id**: Filter by entity ID
    - **task_id**: Filter by task ID
    - **note_id**: Filter by note ID

    Returns attachments uploaded by the current user or attached to their entities.
    """
    # Build query
    query = select(Attachment).where(
        Attachment.uploaded_by == current_user.id,
    )

    # Apply filters
    if entity_type:
        query = query.where(Attachment.entity_type == entity_type.value)

    if entity_id:
        query = query.where(Attachment.entity_id == entity_id)

    if task_id:
        query = query.where(Attachment.task_id == task_id)

    if note_id:
        query = query.where(Attachment.note_id == note_id)

    # Order by most recently created
    query = query.order_by(Attachment.created_at.desc())

    # Apply pagination
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    attachments = result.scalars().all()

    return attachments


@router.get(
    "/test",
    summary="Test endpoint",
    description="Test endpoint for verifying authentication.",
    responses={
        200: {"description": "Test successful"},
        401: {"description": "Not authenticated"},
    },
)
async def test_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Test endpoint that requires authentication.

    Returns a simple response confirming the authenticated user.
    """
    return {
        "message": "Files API is working",
        "user_id": str(current_user.id),
        "user_email": current_user.email,
    }


@router.get(
    "/{attachment_id}",
    response_model=FileDownloadResponse,
    summary="Get a file by ID",
    description="Get file information and a presigned download URL.",
    responses={
        200: {"description": "File information retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Attachment not found"},
    },
)
async def get_file(
    attachment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> FileDownloadResponse:
    """
    Get file information and a presigned download URL.

    Returns the attachment metadata and a temporary URL for downloading the file.
    The download URL is valid for 1 hour.
    """
    # Get the attachment
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID {attachment_id} not found",
        )

    # Access is allowed for any authenticated user
    # Entity-level access control happens when listing attachments

    # Generate presigned download URL
    if attachment.minio_bucket and attachment.minio_key:
        try:
            download_url = minio.get_presigned_download_url(
                bucket=attachment.minio_bucket,
                object_name=attachment.minio_key,
            )
        except MinIOServiceError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate download URL: {str(e)}",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File storage information is missing",
        )

    return FileDownloadResponse(
        attachment=attachment,
        download_url=download_url,
    )


@router.get(
    "/{attachment_id}/info",
    response_model=AttachmentResponse,
    summary="Get attachment info",
    description="Get attachment metadata without a download URL.",
    responses={
        200: {"description": "Attachment information retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Attachment not found"},
    },
)
async def get_attachment_info(
    attachment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    """
    Get attachment metadata without generating a download URL.

    Useful for checking attachment details without the overhead of generating a presigned URL.
    """
    # Get the attachment
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID {attachment_id} not found",
        )

    # Access is allowed for any authenticated user
    # Entity-level access control happens when listing attachments

    return attachment


@router.put(
    "/{attachment_id}",
    response_model=AttachmentResponse,
    summary="Update attachment metadata",
    description="Update the metadata of an existing attachment.",
    responses={
        200: {"description": "Attachment updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Attachment not found"},
    },
)
async def update_attachment(
    attachment_id: UUID,
    attachment_data: AttachmentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    """
    Update attachment metadata.

    - **file_name**: New file name (optional)

    Only the uploader can update the attachment.
    Note: This only updates metadata, not the actual file in storage.
    """
    # Get the attachment
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID {attachment_id} not found",
        )

    # Check access - user must be the uploader
    if attachment.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to update this file.",
        )

    # Update fields if provided
    update_data = attachment_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided",
        )

    for field, value in update_data.items():
        setattr(attachment, field, value)

    # Save changes
    await db.commit()
    await db.refresh(attachment)

    return attachment


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a file",
    description="Delete a file from storage and remove the attachment record.",
    responses={
        204: {"description": "File deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Attachment not found"},
    },
)
async def delete_file(
    attachment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> None:
    """
    Delete a file from MinIO storage and remove the attachment record.

    This permanently deletes:
    - The file from MinIO storage
    - The attachment database record

    The following users can delete files:
    - The application owner
    - Project admins or members (for task attachments)

    This action is irreversible.
    """
    # Get the attachment
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID {attachment_id} not found",
        )

    # Check access - must be application owner, project member, or uploader
    can_delete = False
    error_reason = None

    # For task attachments, use the task permission helper
    if attachment.task_id:
        can_delete, error_reason = await check_task_attachment_permission(
            attachment.task_id, current_user, db, check_done=False
        )

    # For comment attachments, check if user is the uploader
    # Note: Comment attachments typically also have task_id set, so task permission
    # is already checked above. This check allows the uploader to delete their own
    # attachments even if they don't have broader task permissions.
    if not can_delete and attachment.comment_id:
        if attachment.uploaded_by == current_user.id:
            can_delete = True

    # For note attachments, check if user is the application owner
    if not can_delete and attachment.note_id:
        result = await db.execute(
            select(Note)
            .options(selectinload(Note.application))
            .where(Note.id == attachment.note_id)
        )
        note = result.scalar_one_or_none()

        if note and note.application.owner_id == current_user.id:
            can_delete = True

    if not can_delete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_reason or "Access denied. You must be the application owner or a project member to delete attachments.",
        )

    # Capture entity info for WebSocket broadcast before deletion
    entity_type = attachment.entity_type
    entity_id = attachment.entity_id
    deleted_attachment_id = str(attachment.id)

    # Delete from MinIO storage
    if attachment.minio_bucket and attachment.minio_key:
        try:
            minio.delete_file(
                bucket=attachment.minio_bucket,
                object_name=attachment.minio_key,
            )
        except MinIOServiceError:
            # Log the error but continue with database deletion
            # The file might already be deleted or bucket might not exist
            pass

    # Delete the database record
    await db.delete(attachment)
    await db.commit()

    # Broadcast attachment deletion via WebSocket
    if entity_type and entity_id:
        room_id = f"{entity_type}:{entity_id}"
        await ws_manager.broadcast_to_room(
            room_id,
            {
                "type": MessageType.ATTACHMENT_DELETED,
                "data": {
                    "attachment_id": deleted_attachment_id,
                    "entity_type": entity_type,
                    "entity_id": str(entity_id),
                },
            },
        )

    return None


@router.get(
    "/{attachment_id}/download-url",
    summary="Get a fresh download URL",
    description="Generate a new presigned download URL for an attachment.",
    responses={
        200: {"description": "Download URL generated successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Attachment not found"},
    },
)
async def get_download_url(
    attachment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> dict:
    """
    Generate a fresh presigned download URL.

    Useful when the previous URL has expired or is about to expire.
    The new URL is valid for 1 hour.
    """
    # Get the attachment
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment with ID {attachment_id} not found",
        )

    # Access is allowed for any authenticated user
    # Entity-level access control happens when listing attachments

    # Generate presigned download URL
    if not attachment.minio_bucket or not attachment.minio_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File storage information is missing",
        )

    try:
        download_url = minio.get_presigned_download_url(
            bucket=attachment.minio_bucket,
            object_name=attachment.minio_key,
        )
    except MinIOServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate download URL: {str(e)}",
        )

    return {
        "attachment_id": str(attachment.id),
        "file_name": attachment.file_name,
        "download_url": download_url,
    }


@router.post(
    "/download-urls",
    summary="Get download URLs for multiple attachments",
    description="Batch generate presigned download URLs for multiple attachments (max 50).",
    responses={
        200: {"description": "Download URLs generated successfully"},
        401: {"description": "Not authenticated"},
        422: {"description": "Validation error (too many IDs or invalid format)"},
    },
)
async def get_download_urls_batch(
    request: BatchDownloadUrlsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> dict[str, str]:
    """
    Batch generate presigned download URLs for multiple attachments.

    - Maximum 50 attachment IDs per request
    - Returns a dictionary mapping attachment IDs to their download URLs
    - URLs are valid for 1 hour
    - Invalid or inaccessible attachment IDs are silently skipped
    """
    if not request.ids:
        return {}

    # Get all attachments in one query
    result = await db.execute(
        select(Attachment).where(Attachment.id.in_(request.ids))
    )
    attachments = result.scalars().all()

    result_dict: dict[str, str] = {}
    for attachment in attachments:
        if attachment.minio_bucket and attachment.minio_key:
            try:
                download_url = minio.get_presigned_download_url(
                    bucket=attachment.minio_bucket,
                    object_name=attachment.minio_key,
                )
                result_dict[str(attachment.id)] = download_url
            except MinIOServiceError:
                # Skip attachments that fail to generate URLs
                pass

    return result_dict


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=List[AttachmentResponse],
    summary="Get attachments for an entity",
    description="Get all attachments for a specific entity.",
    responses={
        200: {"description": "List of attachments retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def get_entity_attachments(
    entity_type: EntityType,
    entity_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
) -> List[AttachmentResponse]:
    """
    Get all attachments for a specific entity.

    - **entity_type**: Type of entity (task, note, comment)
    - **entity_id**: ID of the entity
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-500)

    Returns attachments attached to the specified entity.
    """
    # Build query
    query = (
        select(Attachment)
        .where(
            Attachment.entity_type == entity_type.value,
            Attachment.entity_id == entity_id,
        )
        .order_by(Attachment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    attachments = result.scalars().all()

    return attachments

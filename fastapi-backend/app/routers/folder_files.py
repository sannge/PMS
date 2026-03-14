"""Folder file upload/download/management API endpoints.

Provides endpoints for uploading files into knowledge base folders,
listing, renaming, moving, replacing, and soft-deleting files. All
endpoints require authentication and use the same RBAC model as
documents (application/project/personal scope).
"""

import hashlib
import logging
import os
import re
from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete as sa_delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.config_service import get_agent_config
from ..ai.rate_limiter import AIRateLimiter, get_rate_limiter
from ..database import get_db
from ..models.document_chunk import DocumentChunk
from ..models.document_folder import DocumentFolder
from ..models.folder_file import FolderFile
from ..models.user import User
from ..schemas.folder_file import (
    FolderFileListItem,
    FolderFileListResponse,
    FolderFileReplaceResponse,
    FolderFileResponse,
    FolderFileUpdate,
)
from ..services.auth_service import get_current_user
from ..services.minio_service import MinIOService, MinIOServiceError, get_minio_service
from ..services.permission_service import PermissionService
from ..utils.timezone import utc_now
from ..websocket.manager import MessageType, manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/folder-files", tags=["FolderFiles"])

_cfg = get_agent_config()

# File extensions that support content extraction
EXTRACTABLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx",
    ".xlsx", ".xls", ".xlsm", ".xlsb",
    ".csv", ".tsv",
    ".vsdx",
}

# Blocked executable/script extensions (HIGH-1)
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".msi", ".dll", ".com", ".scr",
    ".pif", ".vbs", ".js", ".wsh", ".wsf", ".jar", ".cpl", ".inf", ".reg",
    ".rgs", ".sct", ".hta", ".php",
}

# MinIO bucket for folder files
FOLDER_FILES_BUCKET = "pm-attachments"

# Sanitize filename: keep alphanumeric, dash, underscore, dot
_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_.\-]")

# Upload rate limit: 20 uploads per minute per user (HIGH-8)
_UPLOAD_RATE_LIMIT = 20
_UPLOAD_RATE_WINDOW = 60


def _get_max_file_size() -> int:
    """Get MAX_FILE_SIZE at runtime from config (HIGH-13). Applies floor of 1024."""
    return max(1024, _cfg.get_int("file.max_upload_size", 100 * 1024 * 1024))


def _sanitize_filename(filename: str) -> str:
    """Sanitize a filename for use as a MinIO object key."""
    name = _SANITIZE_RE.sub("_", filename)
    # Collapse consecutive underscores
    name = re.sub(r"_+", "_", name)
    # Limit length
    name = name[:200] if name else "file"
    # MED-11: If name is all underscores/dots after sanitization, fall back
    if not name or all(c in "_." for c in name):
        name = "file"
    return name


def _sanitize_original_name(name: str) -> str:
    """Strip null bytes and control chars from original_name before storage (MED-12)."""
    # Remove null bytes and C0 control characters (0x00-0x1F) except tab/newline
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', name)


def _sanitize_display_name(name: str) -> str:
    """Sanitize display_name: strip whitespace, limit length, remove path separators (SA-NEW-MED-4).

    Mirrors the sanitization logic in FolderFileUpdate.sanitize_display_name
    for consistency when display_name comes via query parameter in upload.
    """
    # Remove null bytes, C0/C1 control chars (except tab/newline), DEL, angle brackets
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f<>]", "", name)
    # Remove path separators to prevent directory traversal in display names
    sanitized = sanitized.replace("/", "").replace("\\", "")
    # Strip whitespace and limit length
    sanitized = sanitized.strip()[:255]
    return sanitized if sanitized else "unnamed"


def _detect_mime_type(content: bytes, filename: str) -> str:
    """Detect MIME type from file bytes using python-magic (HIGH-2).

    Falls back to extension-based detection if python-magic is unavailable.
    """
    try:
        import magic
        detected = magic.from_buffer(content[:8192], mime=True)
        if detected:
            return detected
    except ImportError:
        # SA-NEW-MED-1: Log warning so operators know MIME validation is absent
        logger.warning(
            "python-magic is not installed; falling back to extension-based MIME detection. "
            "Install python-magic for content-based MIME validation."
        )
        pass
    except Exception:
        # magic detection failed; fall back
        pass

    # Fallback: extension-based MIME mapping
    ext = _get_extension(filename).lower()
    _ext_mime_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".tsv": "text/tab-separated-values",
        ".vsdx": "application/vnd.ms-visio.drawing",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".txt": "text/plain",
    }
    return _ext_mime_map.get(ext, "application/octet-stream")


def _get_extension(filename: str) -> str:
    """Extract lowercase file extension from filename."""
    _, ext = os.path.splitext(filename)
    return ext.lower()


# ============================================================================
# RBAC Helpers
# ============================================================================


async def _check_folder_edit_permission(
    folder: DocumentFolder,
    user_id: UUID,
    db: AsyncSession,
) -> None:
    """Verify user has edit permission on the folder's scope.

    Raises HTTPException 403 if denied.
    """
    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(folder)
    if not await perm_service.check_can_edit_knowledge(user_id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to manage files in this folder.",
        )


async def _check_folder_view_permission(
    folder: DocumentFolder,
    user_id: UUID,
    db: AsyncSession,
) -> None:
    """Verify user has view permission on the folder's scope.

    Raises HTTPException 403 if denied.
    """
    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(folder)
    if not await perm_service.check_can_view_knowledge(user_id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to view files in this folder.",
        )


async def _get_folder_or_404(folder_id: UUID, db: AsyncSession) -> DocumentFolder:
    """Fetch a DocumentFolder by ID or raise 404."""
    result = await db.execute(
        select(DocumentFolder).where(DocumentFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with ID {folder_id} not found",
        )
    return folder


async def _get_file_or_404(file_id: UUID, db: AsyncSession) -> FolderFile:
    """Fetch a FolderFile by ID (non-deleted) or raise 404."""
    result = await db.execute(
        select(FolderFile).where(
            FolderFile.id == file_id,
            FolderFile.deleted_at.is_(None),
        )
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found",
        )
    return file


async def _resolve_scope_room(file: FolderFile, db: AsyncSession) -> str | None:
    """Determine the WebSocket room for broadcasting file events."""
    if file.application_id:
        return f"application:{file.application_id}"
    elif file.project_id:
        from ..models.project import Project

        result = await db.execute(
            select(Project.application_id).where(Project.id == file.project_id)
        )
        app_id = result.scalar_one_or_none()
        return f"application:{app_id}" if app_id else None
    elif file.user_id:
        return f"user:{file.user_id}"
    return None


async def _delete_file_chunks(file_id: UUID, db: AsyncSession) -> None:
    """Delete embedding chunks for a file (MED-3: shared helper for delete/replace)."""
    try:
        async with db.begin_nested():
            await db.execute(
                sa_delete(DocumentChunk).where(DocumentChunk.file_id == file_id)
            )
    except Exception as chunk_err:
        logger.warning(
            "Failed to delete chunks for file %s (table may not exist): %s",
            file_id, chunk_err,
        )


async def _enqueue_extraction_job(file_id: UUID) -> None:
    """Enqueue an ARQ background job for file extraction and embedding."""
    from ..services.redis_service import redis_service

    defer_by = _cfg.get_int("worker.extract_defer_s", 5)  # MED-4: configurable

    if not redis_service.is_connected:
        logger.warning("Redis not connected, skipping extraction job for file %s", file_id)
        return
    try:
        await redis_service.client.enqueue_job(
            "extract_and_embed_file_job",
            str(file_id),
            _job_id=f"extract_file:{file_id}",
            _defer_by=defer_by,
        )
    except Exception as e:
        logger.warning("Failed to enqueue extraction job for file %s: %s", file_id, e)


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/upload",
    response_model=FolderFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file to a folder",
    description="Upload a file to a document folder in the knowledge base.",
    responses={
        201: {"description": "File uploaded successfully"},
        400: {"description": "Invalid file or validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        409: {"description": "Duplicate file name in folder"},
        413: {"description": "File too large"},
        429: {"description": "Upload rate limit exceeded"},
    },
)
async def upload_file(
    current_user: Annotated[User, Depends(get_current_user)],
    folder_id: UUID = Query(..., description="Target folder ID"),
    display_name: Optional[str] = Query(
        None, max_length=255, description="Display name (defaults to filename)"
    ),
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
    file: UploadFile = File(..., description="The file to upload"),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> FolderFileResponse:
    """Upload a file into a knowledge base folder.

    The file is stored in MinIO and a FolderFile record is created.
    If the file extension is extractable (PDF, DOCX, XLSX, etc.),
    a background job is enqueued for content extraction and embedding.
    """
    # HIGH-8: Rate limit check (20 uploads per minute per user)
    rl_result = await rate_limiter.check_and_increment(
        endpoint="file_upload",
        scope_id=str(current_user.id),
        limit=_UPLOAD_RATE_LIMIT,
        window_seconds=_UPLOAD_RATE_WINDOW,
    )
    if not rl_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Upload rate limit exceeded. Try again in {rl_result.reset_seconds}s.",
            headers={
                "X-RateLimit-Limit": str(rl_result.limit),
                "X-RateLimit-Remaining": str(rl_result.remaining),
                "X-RateLimit-Reset": str(int(rl_result.reset_at.timestamp())),
            },
        )

    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided or file has no name",
        )

    # HIGH-1: Block dangerous extensions
    ext = _get_extension(file.filename)
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not allowed",
        )

    # MED-9: Stream-read up to MAX_FILE_SIZE+1 to fail early
    max_size = _get_max_file_size()
    content = await file.read(max_size + 1)
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed ({max_size} bytes)",
        )

    # Get folder and check RBAC
    folder = await _get_folder_or_404(folder_id, db)
    await _check_folder_edit_permission(folder, current_user.id, db)

    # MED-12: Sanitize original_name
    original_name = _sanitize_original_name(file.filename)
    if not display_name:
        display_name = original_name

    # SA-NEW-MED-4: Sanitize display_name the same way FolderFileUpdate does
    display_name = _sanitize_display_name(display_name)

    # Check for duplicate display_name in folder (case-insensitive)
    dup_result = await db.execute(
        select(FolderFile.id).where(
            FolderFile.folder_id == folder_id,
            func.lower(FolderFile.display_name) == display_name.lower(),
            FolderFile.deleted_at.is_(None),
        )
    )
    existing_id = dup_result.scalar_one_or_none()
    if existing_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"A file named '{display_name}' already exists in this folder",
                "existing_file_id": str(existing_id),
            },
        )

    # SHA-256 hash for dedup
    sha256_hash = hashlib.sha256(content).hexdigest()

    # Generate MinIO object key
    uuid8 = str(uuid4())[:8]
    sanitized = _sanitize_filename(original_name)
    storage_key = f"folder-files/{folder_id}/{uuid8}_{sanitized}"

    # HIGH-2: Detect MIME type from file bytes, not client header
    mime_type = _detect_mime_type(content, original_name)

    # Upload to MinIO
    try:
        minio.upload_bytes(
            bucket=FOLDER_FILES_BUCKET,
            object_name=storage_key,
            data=content,
            content_type=mime_type,
        )
    except MinIOServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file to storage",
        )

    # HIGH-5: Wrap DB operations in try/except after MinIO upload;
    # on failure delete the orphaned MinIO object.
    try:
        # Determine extraction status
        extraction_status = "pending" if ext in EXTRACTABLE_EXTENSIONS else "unsupported"

        # Get max sort_order in folder
        max_sort_result = await db.execute(
            select(func.coalesce(func.max(FolderFile.sort_order), -1)).where(
                FolderFile.folder_id == folder_id,
                FolderFile.deleted_at.is_(None),
            )
        )
        max_sort = max_sort_result.scalar() or 0
        next_sort = max_sort + 1

        # Create FolderFile record
        folder_file = FolderFile(
            id=uuid4(),
            folder_id=folder_id,
            application_id=folder.application_id,
            project_id=folder.project_id,
            user_id=folder.user_id,
            original_name=original_name,
            display_name=display_name,
            mime_type=mime_type,
            file_size=file_size,
            file_extension=ext.lstrip(".") if ext else "",
            storage_bucket=FOLDER_FILES_BUCKET,
            storage_key=storage_key,
            extraction_status=extraction_status,
            sha256_hash=sha256_hash,
            sort_order=next_sort,
            created_by=current_user.id,
        )

        db.add(folder_file)
        await db.commit()
        await db.refresh(folder_file)
    except IntegrityError:
        await db.rollback()
        # Clean up orphaned MinIO object
        try:
            minio.delete_file(bucket=FOLDER_FILES_BUCKET, object_name=storage_key)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file with this name already exists in the folder",
        )
    except Exception:
        await db.rollback()
        # Clean up orphaned MinIO object
        try:
            minio.delete_file(bucket=FOLDER_FILES_BUCKET, object_name=storage_key)
        except Exception:
            pass
        raise

    # Enqueue extraction job if extractable
    if extraction_status == "pending":
        await _enqueue_extraction_job(folder_file.id)

    # WebSocket broadcast
    try:
        room_id = await _resolve_scope_room(folder_file, db)
        if room_id:
            await ws_manager.broadcast_to_room(
                room_id,
                {
                    "type": MessageType.FILE_UPLOADED,
                    "data": {
                        "file_id": str(folder_file.id),
                        "folder_id": str(folder_file.folder_id),
                        "display_name": folder_file.display_name,
                        "file_extension": folder_file.file_extension,
                        "file_size": folder_file.file_size,
                        "extraction_status": folder_file.extraction_status,
                        "uploaded_by": str(current_user.id),
                    },
                },
            )
    except Exception as ws_err:
        logger.warning("Failed to broadcast FILE_UPLOADED: %s", ws_err)

    return folder_file


@router.get(
    "",
    response_model=FolderFileListResponse,
    summary="List files in a folder",
    description="Get files in a folder sorted by sort_order, then display_name.",
    responses={
        200: {"description": "Files retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "Folder not found"},
    },
)
async def list_files(
    folder_id: UUID = Query(..., description="Folder ID to list files from"),
    limit: int = Query(100, ge=1, le=500, description="Maximum files to return"),
    cursor: Optional[UUID] = Query(None, description="Cursor for keyset pagination"),
    current_user: Annotated[User, Depends(get_current_user)] = None,  # HIGH-6: see note below
    db: AsyncSession = Depends(get_db),
) -> FolderFileListResponse:
    """List files in a folder with RBAC enforcement."""
    # HIGH-6: current_user = None default is required by FastAPI for Depends ordering
    # but get_current_user will always return a User or raise 401.
    folder = await _get_folder_or_404(folder_id, db)
    await _check_folder_view_permission(folder, current_user.id, db)

    query = (
        select(FolderFile)
        .where(
            FolderFile.folder_id == folder_id,
            FolderFile.deleted_at.is_(None),
        )
        .order_by(FolderFile.sort_order, FolderFile.display_name)
        .limit(limit)
    )

    if cursor:
        # MED-5: Cursor lookup scoped to same folder
        cursor_result = await db.execute(
            select(FolderFile.sort_order, FolderFile.display_name).where(
                FolderFile.id == cursor,
                FolderFile.folder_id == folder_id,
            )
        )
        cursor_row = cursor_result.one_or_none()
        if cursor_row:
            query = query.where(
                (FolderFile.sort_order > cursor_row[0])
                | (
                    (FolderFile.sort_order == cursor_row[0])
                    & (FolderFile.display_name > cursor_row[1])
                )
            )

    result = await db.execute(query)
    files = list(result.scalars().all())
    # CRIT-3: Return wrapped response {items: [...]}
    return FolderFileListResponse(items=files)


@router.get(
    "/{file_id}",
    response_model=FolderFileResponse,
    summary="Get file details",
    description="Get file details including a presigned download URL.",
    responses={
        200: {"description": "File details retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "File not found"},
    },
)
async def get_file(
    file_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> FolderFileResponse:
    """Get full file details with RBAC enforcement."""
    file = await _get_file_or_404(file_id, db)
    folder = await _get_folder_or_404(file.folder_id, db)
    await _check_folder_view_permission(folder, current_user.id, db)
    return file


@router.get(
    "/{file_id}/download",
    summary="Get download URL",
    description="Get a presigned download URL and filename.",
    responses={
        200: {"description": "Download URL generated"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "File not found"},
    },
)
async def get_download_url(
    file_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> dict:
    """Generate a presigned download URL for the file."""
    file = await _get_file_or_404(file_id, db)
    folder = await _get_folder_or_404(file.folder_id, db)
    await _check_folder_view_permission(folder, current_user.id, db)

    try:
        download_url = minio.get_presigned_download_url(
            bucket=file.storage_bucket,
            object_name=file.storage_key,
        )
    except MinIOServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate download URL: {str(e)}",
        )

    return {
        "file_id": str(file.id),
        "display_name": file.display_name,
        "original_name": file.original_name,
        "download_url": download_url,
    }


@router.put(
    "/{file_id}",
    response_model=FolderFileResponse,
    summary="Rename or move a file",
    description="Update file display_name, folder, or sort_order with optimistic concurrency.",
    responses={
        200: {"description": "File updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "File not found"},
        409: {"description": "Concurrency conflict or duplicate name"},
    },
)
async def update_file(
    file_id: UUID,
    body: FolderFileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> FolderFileResponse:
    """Update file metadata with optimistic concurrency control."""
    file = await _get_file_or_404(file_id, db)
    folder = await _get_folder_or_404(file.folder_id, db)
    await _check_folder_edit_permission(folder, current_user.id, db)

    # Optimistic concurrency check
    if file.row_version != body.row_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrency conflict: the file was modified by another user. Please refresh and try again.",
        )

    # If moving to another folder, check permissions on the target
    target_folder_id = body.folder_id or file.folder_id
    if body.folder_id and body.folder_id != file.folder_id:
        target_folder = await _get_folder_or_404(body.folder_id, db)
        await _check_folder_edit_permission(target_folder, current_user.id, db)
        file.folder_id = body.folder_id
        # Inherit scope from the target folder
        file.application_id = target_folder.application_id
        file.project_id = target_folder.project_id
        file.user_id = target_folder.user_id

    # Rename
    if body.display_name and body.display_name != file.display_name:
        # Check for duplicate in target folder
        dup_result = await db.execute(
            select(FolderFile.id).where(
                FolderFile.folder_id == target_folder_id,
                func.lower(FolderFile.display_name) == body.display_name.lower(),
                FolderFile.deleted_at.is_(None),
                FolderFile.id != file_id,
            )
        )
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{body.display_name}' already exists in the target folder",
            )
        file.display_name = body.display_name

    if body.sort_order is not None:
        file.sort_order = body.sort_order

    file.row_version += 1
    file.updated_at = utc_now()
    await db.commit()
    await db.refresh(file)

    # WebSocket broadcast
    try:
        room_id = await _resolve_scope_room(file, db)
        if room_id:
            await ws_manager.broadcast_to_room(
                room_id,
                {
                    "type": MessageType.FILE_UPDATED,
                    "data": {
                        "file_id": str(file.id),
                        "folder_id": str(file.folder_id),
                        "display_name": file.display_name,
                        "sort_order": file.sort_order,
                        "row_version": file.row_version,
                    },
                },
            )
    except Exception as ws_err:
        logger.warning("Failed to broadcast FILE_UPDATED: %s", ws_err)

    return file


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a file",
    description="Soft delete a file. Removes chunks and search index entry.",
    responses={
        204: {"description": "File deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "File not found"},
    },
)
async def delete_file(
    file_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete a file and clean up its chunks and search index entry."""
    file = await _get_file_or_404(file_id, db)
    folder = await _get_folder_or_404(file.folder_id, db)
    await _check_folder_edit_permission(folder, current_user.id, db)

    # Soft delete
    file.deleted_at = utc_now()
    file.updated_at = utc_now()

    # MED-3: Use shared helper for chunk deletion
    await _delete_file_chunks(file_id, db)

    await db.commit()

    # CRIT-1: Use remove_file_from_index (not remove_document_from_index)
    # Files are indexed with "file:{uuid}" prefix in Meilisearch
    try:
        from ..services.search_service import remove_file_from_index

        await remove_file_from_index(file_id)
    except Exception as ms_err:
        logger.warning("Failed to remove file %s from search index: %s", file_id, ms_err)

    # WebSocket broadcast
    try:
        room_id = await _resolve_scope_room(file, db)
        if room_id:
            await ws_manager.broadcast_to_room(
                room_id,
                {
                    "type": MessageType.FILE_DELETED,
                    "data": {
                        "file_id": str(file_id),
                        "folder_id": str(file.folder_id),
                        "deleted_by": str(current_user.id),
                    },
                },
            )
    except Exception as ws_err:
        logger.warning("Failed to broadcast FILE_DELETED: %s", ws_err)

    return None


@router.post(
    "/{file_id}/replace",
    response_model=FolderFileReplaceResponse,
    summary="Replace file content",
    description="Upload a new version of the file, reset extraction/embedding, re-enqueue job.",
    responses={
        200: {"description": "File replaced successfully"},
        400: {"description": "Invalid file"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "File not found"},
        413: {"description": "File too large"},
    },
)
async def replace_file(
    file_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
    file: UploadFile = File(..., description="The replacement file"),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> FolderFileReplaceResponse:
    """Replace a file's content. Resets extraction/embedding status and re-enqueues extraction."""
    # SA-NEW-MED-2: Rate limit check (same as upload: 20 per minute per user)
    rl_result = await rate_limiter.check_and_increment(
        endpoint="file_upload",
        scope_id=str(current_user.id),
        limit=_UPLOAD_RATE_LIMIT,
        window_seconds=_UPLOAD_RATE_WINDOW,
    )
    if not rl_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Upload rate limit exceeded. Try again in {rl_result.reset_seconds}s.",
            headers={
                "X-RateLimit-Limit": str(rl_result.limit),
                "X-RateLimit-Remaining": str(rl_result.remaining),
                "X-RateLimit-Reset": str(int(rl_result.reset_at.timestamp())),
            },
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided or file has no name",
        )

    # HIGH-1: Block dangerous extensions
    ext = _get_extension(file.filename)
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not allowed",
        )

    # MED-9: Stream-read up to MAX_FILE_SIZE+1
    max_size = _get_max_file_size()
    content = await file.read(max_size + 1)
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed ({max_size} bytes)",
        )

    folder_file = await _get_file_or_404(file_id, db)
    folder = await _get_folder_or_404(folder_file.folder_id, db)
    await _check_folder_edit_permission(folder, current_user.id, db)

    # HIGH-4: Save old storage key for post-commit deletion
    old_storage_bucket = folder_file.storage_bucket
    old_storage_key = folder_file.storage_key

    # Upload new file first
    uuid8 = str(uuid4())[:8]
    sanitized = _sanitize_filename(file.filename)
    new_storage_key = f"folder-files/{folder_file.folder_id}/{uuid8}_{sanitized}"

    # HIGH-2: Detect MIME type from file bytes
    mime_type = _detect_mime_type(content, file.filename)

    try:
        minio.upload_bytes(
            bucket=FOLDER_FILES_BUCKET,
            object_name=new_storage_key,
            data=content,
            content_type=mime_type,
        )
    except MinIOServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload replacement file",
        )

    # Update FolderFile record
    folder_file.original_name = _sanitize_original_name(file.filename)
    folder_file.mime_type = mime_type
    folder_file.file_size = file_size
    folder_file.file_extension = ext.lstrip(".") if ext else ""
    folder_file.storage_key = new_storage_key
    folder_file.sha256_hash = hashlib.sha256(content).hexdigest()
    folder_file.extraction_status = "pending" if ext in EXTRACTABLE_EXTENSIONS else "unsupported"
    folder_file.extraction_error = None
    folder_file.content_plain = None
    folder_file.extracted_metadata = {}
    folder_file.embedding_status = "none"
    folder_file.embedding_updated_at = None
    folder_file.row_version += 1
    folder_file.updated_at = utc_now()

    # MED-3: Use shared helper for chunk deletion
    await _delete_file_chunks(file_id, db)

    try:
        await db.commit()
        await db.refresh(folder_file)
    except Exception:
        await db.rollback()
        # HIGH-5: Clean up orphaned new MinIO object on commit failure
        try:
            minio.delete_file(bucket=FOLDER_FILES_BUCKET, object_name=new_storage_key)
        except Exception:
            pass
        raise

    # HIGH-4: Delete old MinIO object AFTER successful commit
    try:
        minio.delete_file(
            bucket=old_storage_bucket,
            object_name=old_storage_key,
        )
    except MinIOServiceError:
        pass  # Old file may already be gone

    # Re-enqueue extraction job
    if folder_file.extraction_status == "pending":
        await _enqueue_extraction_job(folder_file.id)

    return FolderFileReplaceResponse(
        id=folder_file.id,
        display_name=folder_file.display_name,
        extraction_status=folder_file.extraction_status,
        message="File replaced successfully",
    )

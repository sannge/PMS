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
import time
from typing import Annotated, Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete as sa_delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai.config_service import get_agent_config
from ..ai.rate_limiter import AIRateLimiter, get_rate_limiter
from ..database import get_db
from ..models.attachment import Attachment
from ..models.document_chunk import DocumentChunk
from ..models.document_folder import DocumentFolder
from ..models.folder_file import FolderFile
from ..models.user import User
from ..schemas.folder_file import (
    FolderFileDownloadUrlResponse,
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

# F-128: Removed module-level _cfg; get_agent_config() called at runtime inside helpers

# File extensions that support content extraction
EXTRACTABLE_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".xlsb",
    ".csv",
    ".tsv",
    ".vsdx",
}

# Blocked executable/script extensions (HIGH-1)
BLOCKED_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".ps1",
    ".msi",
    ".dll",
    ".com",
    ".scr",
    ".pif",
    ".vbs",
    ".js",
    ".wsh",
    ".wsf",
    ".jar",
    ".cpl",
    ".inf",
    ".reg",
    ".rgs",
    ".sct",
    ".hta",
    ".php",
}


# MinIO bucket for folder files — read from config at runtime
def _folder_files_bucket() -> str:
    from ..config import settings

    return settings.minio_attachments_bucket


# Sanitize filename: keep alphanumeric, dash, underscore, dot
_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_.\-]")


def _get_upload_rate_limit() -> int:
    """Get upload rate limit at runtime from config."""
    return get_agent_config().get_int("file.upload_rate_limit", 20)


def _get_upload_rate_window() -> int:
    """Get upload rate window at runtime from config."""
    return get_agent_config().get_int("file.upload_rate_window", 60)


def _get_max_file_size() -> int:
    """Get MAX_FILE_SIZE at runtime from config (HIGH-13). Applies floor of 1024."""
    cfg = get_agent_config()
    return max(1024, cfg.get_int("file.max_upload_size", 100 * 1024 * 1024))


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
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", name)


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


_EXT_MIME_MAP: dict[str, str] = {
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


def _detect_mime_type(content: bytes, filename: str) -> str:
    """Detect MIME type from file bytes using python-magic (HIGH-2).

    For known Office formats (.docx, .xlsx, .pptx, etc.), extension-based
    detection takes priority because these are ZIP archives internally and
    python-magic incorrectly reports them as application/zip.

    Falls back to extension-based detection if python-magic is unavailable.
    """
    # Check extension first for formats where magic detection is unreliable
    ext = _get_extension(filename).lower()
    ext_mime = _EXT_MIME_MAP.get(ext)
    if ext_mime:
        # Secondary content-type check: if python-magic is available, verify
        # the content family matches the extension. Don't reject outright
        # (to avoid false positives from magic) but log a warning.
        try:
            import magic as _magic

            detected = _magic.from_buffer(content[:8192], mime=True)
            if detected:
                ext_family = ext_mime.split("/")[0]
                detected_family = detected.split("/")[0]
                # ZIP-based formats (docx, xlsx, pptx, vsdx) will be
                # detected as application/zip by magic, which is expected.
                if detected_family != ext_family and detected not in (
                    "application/zip",
                    "application/x-zip-compressed",
                    "application/octet-stream",
                ):
                    logger.warning(
                        "MIME mismatch for '%s': extension says %s but content detected as %s",
                        filename,
                        ext_mime,
                        detected,
                    )
        except ImportError:
            pass
        except Exception as magic_err:
            logger.debug("Secondary MIME check failed for '%s': %s", filename, magic_err)
        return ext_mime

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
    except Exception as e:
        # magic detection failed; fall back
        logger.debug("MIME detection failed: %s", e)

    return "application/octet-stream"


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


async def _check_file_view_permission(
    file: FolderFile,
    user_id: UUID,
    db: AsyncSession,
) -> None:
    """Verify user has view permission on a file.

    Uses denormalized scope FKs on the file directly (authoritative),
    avoiding a redundant folder query.
    """
    perm_service = PermissionService(db)
    scope_type, scope_id = _resolve_file_scope(file)
    if not await perm_service.check_can_view_knowledge(user_id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to view this file.",
        )


async def _check_file_edit_permission(
    file: FolderFile,
    user_id: UUID,
    db: AsyncSession,
) -> None:
    """Verify user has edit permission on a file.

    Uses denormalized scope FKs on the file directly (authoritative),
    avoiding a redundant folder query.
    """
    perm_service = PermissionService(db)
    scope_type, scope_id = _resolve_file_scope(file)
    if not await perm_service.check_can_edit_knowledge(user_id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to manage this file.",
        )


def _resolve_file_scope(file: FolderFile) -> tuple[str, UUID]:
    """Resolve scope type and ID from a file's scope fields."""
    if file.application_id:
        return "application", file.application_id
    elif file.project_id:
        return "project", file.project_id
    elif file.user_id:
        return "personal", file.user_id
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="File has no scope assignment",
    )


async def _get_folder_or_404(folder_id: UUID, db: AsyncSession) -> DocumentFolder:
    """Fetch a DocumentFolder by ID or raise 404."""
    result = await db.execute(select(DocumentFolder).where(DocumentFolder.id == folder_id))
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

        result = await db.execute(select(Project.application_id).where(Project.id == file.project_id))
        app_id = result.scalar_one_or_none()
        return f"application:{app_id}" if app_id else None
    elif file.user_id:
        return f"user:{file.user_id}"
    return None


async def _delete_file_chunks(file_id: UUID, db: AsyncSession) -> None:
    """Delete all DocumentChunk rows for a given file. Errors propagate to caller."""
    await db.execute(sa_delete(DocumentChunk).where(DocumentChunk.file_id == file_id))


async def _enqueue_extraction_job(file_id: UUID) -> None:
    """Enqueue an ARQ background job for file extraction and embedding."""
    cfg = get_agent_config()
    defer_by = cfg.get_int("worker.extract_defer_s", 5)  # MED-4: configurable

    try:
        from ..services.arq_helper import get_arq_redis

        arq_redis = await get_arq_redis()
        await arq_redis.enqueue_job(
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
    folder_id: Optional[UUID] = Query(None, description="Target folder ID (null for unfiled)"),
    scope: Optional[Literal["application", "project", "personal"]] = Query(
        None, description="Scope type: application, project, personal"
    ),
    scope_id: Optional[UUID] = Query(None, description="Scope entity ID"),
    display_name: Optional[str] = Query(None, max_length=255, description="Display name (defaults to filename)"),
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
    file: UploadFile = File(..., description="The file to upload"),
    rate_limiter: AIRateLimiter = Depends(get_rate_limiter),
) -> FolderFileResponse:
    """Upload a file into a knowledge base folder or at scope root (unfiled).

    The file is stored in MinIO and a FolderFile record is created.
    If the file extension is extractable (PDF, DOCX, XLSX, etc.),
    a background job is enqueued for content extraction and embedding.
    """
    # HIGH-8: Rate limit check (20 uploads per minute per user)
    rl_result = await rate_limiter.check_and_increment(
        endpoint="file_upload",
        scope_id=str(current_user.id),
        limit=_get_upload_rate_limit(),
        window_seconds=_get_upload_rate_window(),
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

    # F-104: Block dangerous extensions — check ALL dot-separated parts
    # Sanitize null bytes and URL-decode before extension check
    import urllib.parse

    clean_filename = urllib.parse.unquote(file.filename or "").replace("\x00", "")
    if not clean_filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is empty or contains only invalid characters.",
        )
    ext = _get_extension(clean_filename)
    for part in clean_filename.split(".")[1:]:
        if f".{part.lower()}" in BLOCKED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension '.{part.lower()}' is not allowed",
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

    # Resolve scope: from folder if provided, else from explicit scope params
    file_application_id = None
    file_project_id = None
    file_user_id = None

    if folder_id:
        folder = await _get_folder_or_404(folder_id, db)
        await _check_folder_edit_permission(folder, current_user.id, db)
        file_application_id = folder.application_id
        file_project_id = folder.project_id
        file_user_id = folder.user_id
    elif scope and scope_id:
        # F-114: For personal scope, enforce scope_id == current_user.id
        if scope == "personal" and scope_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Cannot upload to another user's personal scope.",
            )
        # F-101: RBAC check for unfiled uploads (mirrors folder_id branch)
        perm_service = PermissionService(db)
        if not await perm_service.check_can_edit_knowledge(current_user.id, scope, scope_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not have permission to upload files in this scope.",
            )
        if scope == "application":
            file_application_id = scope_id
        elif scope == "project":
            file_project_id = scope_id
        elif scope == "personal":
            file_user_id = scope_id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scope must be 'application', 'project', or 'personal'",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either folder_id or scope+scope_id is required",
        )

    # MED-12: Sanitize original_name
    original_name = _sanitize_original_name(file.filename)
    if not display_name:
        display_name = original_name

    # SA-NEW-MED-4: Sanitize display_name the same way FolderFileUpdate does
    display_name = _sanitize_display_name(display_name)

    # Check for duplicate display_name in same folder/root (case-insensitive)
    dup_where = [
        func.lower(FolderFile.display_name) == display_name.lower(),
        FolderFile.deleted_at.is_(None),
    ]
    if folder_id:
        dup_where.append(FolderFile.folder_id == folder_id)
    else:
        dup_where.append(FolderFile.folder_id.is_(None))
        if file_application_id:
            dup_where.append(FolderFile.application_id == file_application_id)
        elif file_project_id:
            dup_where.append(FolderFile.project_id == file_project_id)
        elif file_user_id:
            dup_where.append(FolderFile.user_id == file_user_id)

    dup_result = await db.execute(select(FolderFile.id).where(*dup_where))
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
    scope_prefix = str(folder_id) if folder_id else f"unfiled/{scope_id}"
    storage_key = f"folder-files/{scope_prefix}/{uuid8}_{sanitized}"

    # HIGH-2: Detect MIME type from file bytes, not client header
    mime_type = _detect_mime_type(content, original_name)

    # Upload to MinIO
    try:
        await minio.upload_bytes(
            bucket=_folder_files_bucket(),
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

        # Get max sort_order in folder/scope
        sort_where = [FolderFile.deleted_at.is_(None)]
        if folder_id:
            sort_where.append(FolderFile.folder_id == folder_id)
        else:
            sort_where.append(FolderFile.folder_id.is_(None))
            if file_application_id:
                sort_where.append(FolderFile.application_id == file_application_id)
            elif file_project_id:
                sort_where.append(FolderFile.project_id == file_project_id)
            elif file_user_id:
                sort_where.append(FolderFile.user_id == file_user_id)
        # NOTE: sort_order ties from concurrent uploads are non-critical
        # (files still appear, just with potentially duplicate sort_order).
        # A with_for_update() would serialize uploads unnecessarily.
        max_sort_result = await db.execute(select(func.coalesce(func.max(FolderFile.sort_order), 0)).where(*sort_where))
        max_sort = max_sort_result.scalar()
        next_sort = max_sort + 1

        # Create FolderFile record
        folder_file = FolderFile(
            id=uuid4(),
            folder_id=folder_id,
            application_id=file_application_id,
            project_id=file_project_id,
            user_id=file_user_id,
            original_name=original_name,
            display_name=display_name,
            mime_type=mime_type,
            file_size=file_size,
            file_extension=ext.lstrip(".") if ext else "",
            storage_bucket=_folder_files_bucket(),
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
            await minio.delete_file(bucket=_folder_files_bucket(), object_name=storage_key)
        except Exception as minio_err:
            logger.error(
                "ORPHAN: Failed to delete MinIO object %s after error for upload: %s",
                storage_key,
                minio_err,
            )
        # Re-query to find the conflicting file so frontend can offer "Replace"
        conflict_result = await db.execute(select(FolderFile.id).where(*dup_where))
        existing_id = conflict_result.scalar_one_or_none()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"File '{display_name}' already exists",
                "existing_file_id": str(existing_id) if existing_id else None,
            },
        )
    except Exception:
        await db.rollback()
        # Clean up orphaned MinIO object
        try:
            await minio.delete_file(bucket=_folder_files_bucket(), object_name=storage_key)
        except Exception as minio_err:
            logger.error(
                "ORPHAN: Failed to delete MinIO object %s after error for upload: %s",
                storage_key,
                minio_err,
            )
        raise

    # Extraction + embedding runs via scheduled batch job or manual trigger,
    # not auto-enqueued on upload.

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
                        "folder_id": str(folder_file.folder_id) if folder_file.folder_id else None,
                        "display_name": folder_file.display_name,
                        "file_extension": folder_file.file_extension,
                        "file_size": folder_file.file_size,
                        "extraction_status": folder_file.extraction_status,
                        "uploaded_by": str(current_user.id),
                        "actor_id": str(current_user.id),
                        "scope": "application"
                        if folder_file.application_id
                        else "project"
                        if folder_file.project_id
                        else "personal",
                        "scope_id": str(folder_file.application_id or folder_file.project_id or folder_file.user_id),
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
    folder_id: Optional[UUID] = Query(None, description="Folder ID to list files from"),
    scope: Optional[Literal["application", "project", "personal"]] = Query(
        None, description="Scope type for unfiled listing"
    ),
    scope_id: Optional[UUID] = Query(None, description="Scope entity ID for unfiled listing"),
    limit: int = Query(100, ge=1, le=500, description="Maximum files to return"),
    cursor: Optional[UUID] = Query(None, description="Cursor for keyset pagination"),
    current_user: Annotated[User, Depends(get_current_user)] = None,  # HIGH-6: see note below
    db: AsyncSession = Depends(get_db),
) -> FolderFileListResponse:
    """List files in a folder or unfiled at scope root with RBAC enforcement."""
    # HIGH-6: current_user = None default is required by FastAPI for Depends ordering
    # but get_current_user will always return a User or raise 401.

    # F-303: Validate scope parameter
    VALID_SCOPES = {"application", "project", "personal"}
    if scope and scope not in VALID_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scope: {scope}. Must be one of: {', '.join(sorted(VALID_SCOPES))}",
        )

    where_clauses = [FolderFile.deleted_at.is_(None)]

    if folder_id:
        folder = await _get_folder_or_404(folder_id, db)
        await _check_folder_view_permission(folder, current_user.id, db)
        where_clauses.append(FolderFile.folder_id == folder_id)
    elif scope and scope_id:
        # F-102: RBAC check for unfiled scope listing
        perm_service = PermissionService(db)
        if not await perm_service.check_can_view_knowledge(current_user.id, scope, scope_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not have permission to view files in this scope.",
            )
        where_clauses.append(FolderFile.folder_id.is_(None))
        if scope == "application":
            where_clauses.append(FolderFile.application_id == scope_id)
        elif scope == "project":
            where_clauses.append(FolderFile.project_id == scope_id)
        elif scope == "personal":
            where_clauses.append(FolderFile.user_id == scope_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either folder_id or scope+scope_id is required",
        )

    query = (
        select(FolderFile)
        .where(*where_clauses)
        .order_by(FolderFile.sort_order, func.lower(FolderFile.display_name))
        .limit(limit)
    )

    if cursor:
        # F-108: Cursor lookup scoped to same folder or unfiled scope
        cursor_where = [FolderFile.id == cursor, FolderFile.deleted_at.is_(None)]
        if folder_id:
            cursor_where.append(FolderFile.folder_id == folder_id)
        else:
            cursor_where.append(FolderFile.folder_id.is_(None))
            if scope == "application":
                cursor_where.append(FolderFile.application_id == scope_id)
            elif scope == "project":
                cursor_where.append(FolderFile.project_id == scope_id)
            elif scope == "personal":
                cursor_where.append(FolderFile.user_id == scope_id)
        cursor_result = await db.execute(
            select(FolderFile.sort_order, func.lower(FolderFile.display_name)).where(
                *cursor_where,
            )
        )
        cursor_row = cursor_result.one_or_none()
        if cursor_row:
            query = query.where(
                (FolderFile.sort_order > cursor_row[0])
                | ((FolderFile.sort_order == cursor_row[0]) & (func.lower(FolderFile.display_name) > cursor_row[1]))
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
    await _check_file_view_permission(file, current_user.id, db)
    return file


@router.get(
    "/{file_id}/download",
    response_model=FolderFileDownloadUrlResponse,
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
) -> FolderFileDownloadUrlResponse:
    """Generate a presigned download URL for the file."""
    file = await _get_file_or_404(file_id, db)
    await _check_file_view_permission(file, current_user.id, db)

    try:
        download_url = await minio.get_presigned_download_url(
            bucket=file.storage_bucket,
            object_name=file.storage_key,
        )
    except MinIOServiceError as e:
        # F-130: Log full error, return generic message to client
        logger.error("Failed to generate download URL for file %s: %s", file_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL",
        )

    return FolderFileDownloadUrlResponse(
        file_id=str(file.id),
        display_name=file.display_name,
        original_name=file.original_name,
        download_url=download_url,
    )


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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> FolderFileResponse:
    """Update file metadata with optimistic concurrency control."""
    file = await _get_file_or_404(file_id, db)
    await _check_file_edit_permission(file, current_user.id, db)

    # CRIT-2: Capture original folder_id before mutation for WS source_folder_id
    original_folder_id = file.folder_id
    # Capture original scope FKs to detect cross-scope moves
    original_scope = (file.application_id, file.project_id, file.user_id)

    # Build update values dict for atomic UPDATE ... WHERE row_version
    update_values: dict = {
        "row_version": body.row_version + 1,
        "updated_at": utc_now(),
    }

    # Determine target folder: distinguish "not provided" from "explicitly null"
    if "folder_id" in body.model_fields_set:
        # Explicitly set — None means "move to unfiled"
        target_folder_id = body.folder_id
        if body.folder_id is None and file.folder_id is not None:
            # Moving from a folder to unfiled — clear folder_id, keep current scope
            update_values["folder_id"] = None
        elif body.folder_id is not None and body.folder_id != file.folder_id:
            # Moving to a different folder — check permissions on the target
            target_folder = await _get_folder_or_404(body.folder_id, db)
            await _check_folder_edit_permission(target_folder, current_user.id, db)
            update_values["folder_id"] = body.folder_id
            # Inherit scope from the target folder
            update_values["application_id"] = target_folder.application_id
            update_values["project_id"] = target_folder.project_id
            update_values["user_id"] = target_folder.user_id
    else:
        # Not provided — keep current folder
        target_folder_id = file.folder_id

    # Rename
    if body.display_name and body.display_name != file.display_name:
        # Check for duplicate in target folder (F-201: scope filter for unfiled)
        if target_folder_id is None:
            dup_where = [
                FolderFile.folder_id.is_(None),
                func.lower(FolderFile.display_name) == body.display_name.lower(),
                FolderFile.deleted_at.is_(None),
                FolderFile.id != file_id,
            ]
            if file.application_id:
                dup_where.append(FolderFile.application_id == file.application_id)
            elif file.project_id:
                dup_where.append(FolderFile.project_id == file.project_id)
            elif file.user_id:
                dup_where.append(FolderFile.user_id == file.user_id)
        else:
            dup_where = [
                FolderFile.folder_id == target_folder_id,
                func.lower(FolderFile.display_name) == body.display_name.lower(),
                FolderFile.deleted_at.is_(None),
                FolderFile.id != file_id,
            ]
        dup_result = await db.execute(select(FolderFile.id).where(*dup_where))
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A file named '{body.display_name}' already exists in the target folder",
            )
        update_values["display_name"] = body.display_name

    if body.sort_order is not None:
        update_values["sort_order"] = body.sort_order

    # F-105: Atomic UPDATE ... WHERE row_version = expected (prevents TOCTOU)
    # F-215: Wrap in IntegrityError handler for concurrent rename race condition
    try:
        result = await db.execute(
            update(FolderFile)
            .where(FolderFile.id == file_id, FolderFile.row_version == body.row_version)
            .values(**update_values)
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Concurrency conflict: the file was modified by another user. Please refresh and try again.",
            )

        # CRIT-2: If scope changed, update DocumentChunk scope FKs to prevent
        # incorrect search results and RBAC leakage.
        new_scope = (
            update_values.get("application_id", original_scope[0]),
            update_values.get("project_id", original_scope[1]),
            update_values.get("user_id", original_scope[2]),
        )
        if new_scope != original_scope:
            await db.execute(
                update(DocumentChunk)
                .where(DocumentChunk.file_id == file_id)
                .values(
                    application_id=new_scope[0],
                    project_id=new_scope[1],
                    user_id=new_scope[2],
                )
            )

        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A file with this name already exists in the target location.",
        )

    # Re-fetch the updated file
    db.expire(file)
    file = await _get_file_or_404(file_id, db)

    # Re-index in Meilisearch (background, non-blocking) to sync display_name and scope FKs
    try:
        from ..services.search_service import build_search_file_data, index_file_from_data
        from ..models.project import Project

        _proj_app_id: UUID | None = None
        if file.project_id:
            _proj = await db.get(Project, file.project_id)
            if _proj:
                _proj_app_id = _proj.application_id
        _search_data = build_search_file_data(file, _proj_app_id)
        background_tasks.add_task(index_file_from_data, _search_data)
    except Exception as _ms_err:
        logger.warning("Failed to prepare file %s re-index: %s", file_id, _ms_err)

    # WebSocket broadcast
    # CRIT-2: Include source_folder_id so clients can invalidate the old folder's cache on move
    source_folder_str = str(original_folder_id) if original_folder_id else None
    try:
        room_id = await _resolve_scope_room(file, db)
        if room_id:
            await ws_manager.broadcast_to_room(
                room_id,
                {
                    "type": MessageType.FILE_UPDATED,
                    "data": {
                        "file_id": str(file.id),
                        "folder_id": str(file.folder_id) if file.folder_id else None,
                        "source_folder_id": source_folder_str,
                        "display_name": file.display_name,
                        "sort_order": file.sort_order,
                        "row_version": file.row_version,
                        "actor_id": str(current_user.id),
                        "scope": "application" if file.application_id else "project" if file.project_id else "personal",
                        "scope_id": str(file.application_id or file.project_id or file.user_id),
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
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete a file and clean up its chunks and search index entry."""
    file = await _get_file_or_404(file_id, db)
    await _check_file_edit_permission(file, current_user.id, db)

    # Capture storage info before mutation for background cleanup
    storage_bucket = file.storage_bucket
    storage_key = file.storage_key
    thumbnail_key = file.thumbnail_key

    # FIX-14/25: Single transaction — soft-delete, chunk deletion, and image attachment cleanup
    _now = utc_now()
    file.deleted_at = _now
    file.updated_at = _now
    await db.execute(sa_delete(DocumentChunk).where(DocumentChunk.file_id == file_id))
    # Delete image Attachments and collect MinIO refs for background cleanup
    # (query + delete in same transaction to avoid TOCTOU race)
    att_result = await db.execute(
        sa_delete(Attachment)
        .where(
            Attachment.entity_type == "file",
            Attachment.entity_id == file_id,
        )
        .returning(Attachment.minio_bucket, Attachment.minio_key)
    )
    image_minio_refs = [(row[0], row[1]) for row in att_result.all() if row[0] and row[1]]
    await db.commit()

    # FIX-13: Move MinIO cleanup to background task to avoid blocking async event loop
    async def _cleanup_minio() -> None:
        try:
            minio = get_minio_service()
            await minio.delete_file(bucket=storage_bucket, object_name=storage_key)
            if thumbnail_key:
                await minio.delete_file(bucket=storage_bucket, object_name=thumbnail_key)
            # Clean up vision-processed image objects
            for img_bucket, img_key in image_minio_refs:
                try:
                    await minio.delete_file(bucket=img_bucket, object_name=img_key)
                except Exception:
                    logger.warning("Failed to delete image %s/%s for file %s", img_bucket, img_key, file_id)
        except Exception as minio_err:
            logger.warning("Failed to delete MinIO objects for file %s: %s", file_id, minio_err)

    background_tasks.add_task(_cleanup_minio)

    # Soft-delete from search index (non-blocking, consistency checker is backstop)
    try:
        from ..services.search_service import get_meili_index, _meili_circuit_is_open

        if not _meili_circuit_is_open():
            _index = get_meili_index()
            await _index.update_documents(
                [
                    {
                        "id": f"file_{file_id}",
                        "deleted_at": int(time.time()),
                    }
                ]
            )
    except Exception as ms_err:
        logger.warning("Failed to soft-delete file %s from search index: %s", file_id, ms_err)

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
                        "folder_id": str(file.folder_id) if file.folder_id else None,
                        "deleted_by": str(current_user.id),
                        "actor_id": str(current_user.id),
                        "scope": "application" if file.application_id else "project" if file.project_id else "personal",
                        "scope_id": str(file.application_id or file.project_id or file.user_id),
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
    background_tasks: BackgroundTasks,
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
        limit=_get_upload_rate_limit(),
        window_seconds=_get_upload_rate_window(),
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

    # F-104: Block dangerous extensions — check ALL dot-separated parts
    # Sanitize null bytes and URL-decode before extension check
    import urllib.parse

    clean_filename = urllib.parse.unquote(file.filename or "").replace("\x00", "")
    if not clean_filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is empty or contains only invalid characters.",
        )
    ext = _get_extension(clean_filename)
    for part in clean_filename.split(".")[1:]:
        if f".{part.lower()}" in BLOCKED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension '.{part.lower()}' is not allowed",
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
    await _check_file_edit_permission(folder_file, current_user.id, db)

    # HIGH-4: Save old storage info for post-commit background cleanup
    old_storage_bucket = folder_file.storage_bucket
    old_storage_key = folder_file.storage_key
    old_thumbnail_key = folder_file.thumbnail_key

    # F-107: Use scope_prefix logic matching upload_file (unfiled/{scope_id} when no folder)
    uuid8 = str(uuid4())[:8]
    sanitized = _sanitize_filename(file.filename)
    if folder_file.folder_id:
        scope_prefix = str(folder_file.folder_id)
    else:
        _, file_scope_id = _resolve_file_scope(folder_file)
        scope_prefix = f"unfiled/{file_scope_id}"
    new_storage_key = f"folder-files/{scope_prefix}/{uuid8}_{sanitized}"

    # HIGH-2: Detect MIME type from file bytes
    mime_type = _detect_mime_type(content, file.filename)

    try:
        await minio.upload_bytes(
            bucket=_folder_files_bucket(),
            object_name=new_storage_key,
            data=content,
            content_type=mime_type,
        )
    except MinIOServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload replacement file",
        )

    # F3: Atomic UPDATE...WHERE row_version guard — prevents concurrent replace orphaning MinIO objects
    result = await db.execute(
        update(FolderFile)
        .where(FolderFile.id == file_id, FolderFile.row_version == folder_file.row_version)
        .values(
            original_name=_sanitize_original_name(file.filename),
            mime_type=mime_type,
            file_size=file_size,
            file_extension=ext.lstrip(".") if ext else "",
            storage_key=new_storage_key,
            sha256_hash=hashlib.sha256(content).hexdigest(),
            extraction_status="pending"
            if ext.lower().lstrip(".") in {e.lstrip(".") for e in EXTRACTABLE_EXTENSIONS}
            else "unsupported",
            extraction_error=None,
            content_plain=None,
            extracted_metadata={},
            embedding_status="none",
            embedding_updated_at=None,
            thumbnail_key=None,
            row_version=folder_file.row_version + 1,
            updated_at=utc_now(),
        )
    )
    if result.rowcount != 1:
        # Concurrent replace won the race — clean up our orphaned upload
        try:
            await minio.delete_file(bucket=_folder_files_bucket(), object_name=new_storage_key)
        except Exception:
            logger.error("ORPHAN: concurrent replace cleanup failed for %s", new_storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File was modified concurrently. Please refresh and try again.",
        )

    # MED-3: Use shared helper for chunk deletion
    await _delete_file_chunks(file_id, db)

    # Clean up old image Attachments from previous vision processing
    old_att_result = await db.execute(
        sa_delete(Attachment)
        .where(
            Attachment.entity_type == "file",
            Attachment.entity_id == file_id,
        )
        .returning(Attachment.minio_bucket, Attachment.minio_key)
    )
    old_image_refs = [(row[0], row[1]) for row in old_att_result.all() if row[0] and row[1]]

    try:
        await db.commit()
        await db.refresh(folder_file)
    except Exception:
        await db.rollback()
        db.expire(folder_file)  # F8: discard in-memory mutations
        # HIGH-5: Clean up orphaned new MinIO object on commit failure
        try:
            await minio.delete_file(
                bucket=_folder_files_bucket(),
                object_name=new_storage_key,
            )
        except Exception as minio_err:
            logger.error(
                "ORPHAN: Failed to delete MinIO object %s after rollback for file %s: %s",
                new_storage_key,
                file_id,
                minio_err,
            )
        raise

    # HIGH-4: Delete old MinIO objects in background task (matches delete_file pattern)
    async def _cleanup_old_minio() -> None:
        try:
            if old_storage_key:
                await minio.delete_file(bucket=old_storage_bucket, object_name=old_storage_key)
            if old_thumbnail_key:
                await minio.delete_file(bucket=old_storage_bucket, object_name=old_thumbnail_key)
            # Clean up old vision-processed image objects
            for img_bucket, img_key in old_image_refs:
                try:
                    await minio.delete_file(bucket=img_bucket, object_name=img_key)
                except Exception:
                    logger.warning("Failed to delete old image %s/%s", img_bucket, img_key)
        except Exception as e:
            logger.warning("Failed to clean up old MinIO objects: %s", e)

    background_tasks.add_task(_cleanup_old_minio)

    # Extraction + embedding runs via scheduled batch job or manual trigger.

    # CRIT-1: Broadcast FILE_UPDATED so collaborators see the replacement
    try:
        room_id = await _resolve_scope_room(folder_file, db)
        if room_id:
            await ws_manager.broadcast_to_room(
                room_id,
                {
                    "type": MessageType.FILE_UPDATED,
                    "data": {
                        "file_id": str(folder_file.id),
                        "folder_id": str(folder_file.folder_id) if folder_file.folder_id else None,
                        "display_name": folder_file.display_name,
                        "sort_order": folder_file.sort_order,
                        "row_version": folder_file.row_version,
                        "actor_id": str(current_user.id),
                        "scope": "application"
                        if folder_file.application_id
                        else "project"
                        if folder_file.project_id
                        else "personal",
                        "scope_id": str(folder_file.application_id or folder_file.project_id or folder_file.user_id),
                    },
                },
            )
    except Exception as ws_err:
        logger.warning("Failed to broadcast FILE_UPDATED on replace: %s", ws_err)

    return FolderFileReplaceResponse(
        id=folder_file.id,
        display_name=folder_file.display_name,
        extraction_status=folder_file.extraction_status,
        message="File replaced successfully",
    )


# ============================================================================
# Embedding sync endpoint
# ============================================================================


@router.post(
    "/{file_id}/sync-embeddings",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue embedding sync for a file",
    description="Re-extract (if needed) and re-embed a file's content.",
    responses={
        202: {"description": "Sync job queued"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied"},
        404: {"description": "File not found"},
        503: {"description": "Background worker unavailable"},
    },
)
async def sync_embeddings(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Queue an extraction + embedding sync job for a single file.

    Requires Editor or Owner permission on the file's folder scope
    (or direct scope for unfiled files).
    Returns 202 Accepted with the file ID.
    """
    file = await _get_file_or_404(file_id, db)
    await _check_file_edit_permission(file, current_user.id, db)

    # HIGH-22: Atomic status transition to prevent concurrent sync races
    sync_update_values: dict = {"embedding_status": "syncing", "updated_at": utc_now()}
    if file.extraction_status != "completed":
        sync_update_values["extraction_status"] = "pending"

    sync_result = await db.execute(
        update(FolderFile)
        .where(
            FolderFile.id == file_id,
            FolderFile.embedding_status.notin_(["syncing"]),
        )
        .values(**sync_update_values)
        .returning(FolderFile.id)
    )
    if not sync_result.scalar_one_or_none():
        # Already syncing — still accept to be idempotent
        pass
    await db.flush()

    try:
        from ..services.arq_helper import get_arq_redis

        arq_redis = await get_arq_redis()

        # F-124: Use Redis pipeline for atomic delete+enqueue
        job_key = f"extract_file:{file_id}"
        pipe = arq_redis.pipeline()
        pipe.delete(f"arq:job:{job_key}", f"arq:result:{job_key}")
        await pipe.execute()
        await arq_redis.enqueue_job(
            "extract_and_embed_file_job",
            str(file_id),
            _job_id=job_key,
        )
        await db.commit()
    except RuntimeError:
        # FIX-10: Use atomic UPDATE to avoid operating on stale ORM object
        await db.execute(
            update(FolderFile).where(FolderFile.id == file.id).values(embedding_status="stale", updated_at=utc_now())
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background worker not available",
        )
    except Exception:
        # FIX-10: Use atomic UPDATE to avoid operating on stale ORM object
        await db.execute(
            update(FolderFile).where(FolderFile.id == file.id).values(embedding_status="stale", updated_at=utc_now())
        )
        await db.commit()
        logger.exception("Failed to enqueue extract_and_embed_file_job for file %s", file_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue embedding sync job",
        )

    return {"status": "queued", "file_id": str(file.id)}

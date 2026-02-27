"""AI document import API endpoints.

Provides endpoints for uploading PDF/DOCX/PPTX files and importing them
into the knowledge base via the Docling conversion pipeline. Imports are
processed asynchronously by the ARQ background worker.

All endpoints require authentication.
"""

import logging
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.import_job import ImportJob
from ..models.user import User
from ..schemas.import_job import ImportJobListResponse, ImportJobResponse
from ..ai.rate_limiter import check_import_rate_limit
from ..services.auth_service import get_current_user
from ..services.permission_service import PermissionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai/import", tags=["ai-import"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx"}

ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}

VALID_SCOPES = {"application", "project", "personal"}

# Magic bytes for file type detection
FILE_MAGIC = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "docx_or_pptx",  # ZIP archive (DOCX/PPTX are ZIP)
}


# ---------------------------------------------------------------------------
# POST /api/ai/import/  --  Upload and import a document
# ---------------------------------------------------------------------------


@router.post("/", status_code=202, response_model=dict)
async def upload_and_import(
    file: UploadFile = File(...),
    scope: str = Form(...),
    scope_id: UUID = Form(...),
    folder_id: Optional[UUID] = Form(None),
    title: Optional[str] = Form(None, max_length=255),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(check_import_rate_limit),
) -> dict:
    """Upload a file and start an asynchronous import job.

    Accepts PDF, DOCX, and PPTX files up to 50 MB. The file is validated,
    saved to a temp location, and an ARQ background job is enqueued to
    convert the document contents into the knowledge base.

    Returns 202 Accepted with job metadata so the client can poll for status.
    """
    # --- Validate scope value ---
    if scope not in VALID_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid scope '{scope}'. Must be one of: {', '.join(sorted(VALID_SCOPES))}",
        )

    # --- For personal scope, enforce scope_id == current_user.id ---
    if scope == "personal" and scope_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Personal scope_id must match your user ID",
        )

    # --- Validate file extension ---
    file_name = file.filename or "unknown"
    # Sanitize filename: strip control characters and limit length
    file_name = "".join(c for c in file_name if unicodedata.category(c)[0] != 'C')[:500]
    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # --- Validate MIME type ---
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type '{content_type}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES.keys()))}",
        )

    # --- Validate file size (read into memory to check) ---
    contents = await file.read()
    file_size = len(contents)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({file_size} bytes). Maximum allowed: {MAX_FILE_SIZE} bytes (50 MB)",
        )

    # --- Verify file magic bytes ---
    detected = None
    for magic, ftype in FILE_MAGIC.items():
        if contents.startswith(magic):
            detected = ftype
            break

    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match expected format",
        )

    file_type = ALLOWED_MIME_TYPES[content_type]

    # For DOCX/PPTX, both start with PK (ZIP), so check the extension matches
    if detected == "docx_or_pptx" and file_type not in ("docx", "pptx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match declared file type",
        )
    if detected == "pdf" and file_type != "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match declared file type",
        )

    # --- RBAC: check write access to target scope ---
    perm_service = PermissionService(db)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have write access to the target scope",
        )

    # --- Validate folder_id belongs to target scope ---
    if folder_id:
        from ..models.document_folder import DocumentFolder
        folder_result = await db.execute(
            select(DocumentFolder).where(
                DocumentFolder.id == folder_id,
                # Match scope
                DocumentFolder.application_id == (scope_id if scope == "application" else None),
                DocumentFolder.project_id == (scope_id if scope == "project" else None),
                DocumentFolder.user_id == (scope_id if scope == "personal" else None),
            )
        )
        if not folder_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder not found in target scope",
            )

    # --- Save uploaded file to temp location ---
    try:
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{file_type}",
            prefix="import_",
        )
        tmp.write(contents)
        tmp.close()
        temp_file_path = tmp.name
        os.chmod(temp_file_path, 0o600)
    except OSError as e:
        logger.error("Failed to save uploaded file to temp: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file",
        )

    # --- Derive title from filename if not provided ---
    job_title = title if title else Path(file_name).stem

    # --- Create ImportJob record and enqueue ---
    # Wrap in try/except to ensure temp file cleanup on failure
    try:
        job = ImportJob(
            user_id=current_user.id,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            title=job_title,
            status="pending",
            progress_pct=0,
            scope=scope,
            scope_id=scope_id,
            folder_id=folder_id,
            temp_file_path=temp_file_path,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        job_id = str(job.id)

        await db.commit()
    except Exception as e:
        # Clean up temp file if job creation fails
        try:
            os.unlink(temp_file_path)
        except OSError:
            pass
        logger.error("Failed to create import job: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create import job",
        )

    # --- Enqueue ARQ background job ---
    try:
        from arq.connections import create_pool

        from ..worker import parse_redis_url
        from ..config import settings

        redis = await create_pool(parse_redis_url(settings.redis_url))
        await redis.enqueue_job("process_document_import", job_id, _job_id=f"import:{job_id}")
        await redis.aclose()
    except Exception as e:
        # Clean up temp file if enqueue fails
        try:
            os.unlink(temp_file_path)
        except OSError:
            pass
        logger.error("Failed to enqueue import job %s: %s", job_id, e)
        # Update job status to failed since we can't process it
        job.status = "failed"
        job.error_message = "Failed to enqueue background job"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background worker not available",
        )

    logger.info(
        "Import job %s created for file '%s' (%s, %d bytes) by user %s",
        job_id, file_name, file_type, file_size, current_user.id,
    )

    return {
        "job_id": job_id,
        "status": "pending",
        "file_name": file_name,
    }


# ---------------------------------------------------------------------------
# GET /api/ai/import/jobs  --  List user's import jobs
# NOTE: This route MUST be defined before /{job_id} to avoid FastAPI
#       matching the literal "jobs" as a UUID path parameter.
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=ImportJobListResponse)
async def list_jobs(
    status_filter: Optional[Literal["pending", "processing", "completed", "failed"]] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportJobListResponse:
    """List the current user's import jobs with optional status filtering.

    Returns a paginated list ordered by most recent first.

    Query params:
        status: Optional filter by job status (pending, processing, completed, failed)
        limit: Max items per page (default 20, max 100)
        offset: Number of items to skip (default 0)
    """
    # Build base query scoped to current user
    base_filter = [ImportJob.user_id == current_user.id]
    if status_filter is not None:
        base_filter.append(ImportJob.status == status_filter)

    # Count total matching jobs
    count_query = select(func.count(ImportJob.id)).where(*base_filter)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch paginated results
    items_query = (
        select(ImportJob)
        .where(*base_filter)
        .order_by(ImportJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items_result = await db.execute(items_query)
    jobs = items_result.scalars().all()

    return ImportJobListResponse(
        items=[ImportJobResponse.model_validate(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/ai/import/{job_id}  --  Job status
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportJobResponse:
    """Get the status of an import job.

    Only the job owner can view their job. Returns 404 for non-owners
    (to avoid leaking information about other users' jobs) and for
    non-existent job IDs.
    """
    result = await db.execute(
        select(ImportJob).where(
            ImportJob.id == job_id,
            ImportJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found",
        )

    return ImportJobResponse.model_validate(job)

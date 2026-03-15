"""
ARQ Worker Configuration

Background job processing with Redis-backed task queue.
Handles scheduled jobs that were previously run via asyncio loops.

Run with:
    arq app.worker.WorkerSettings
"""

import asyncio
import logging
import os
from datetime import timedelta
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import async_session_maker
from .utils.timezone import utc_now
from .models.project import Project
from .models.task import Task
from .models.task_status import StatusName, TaskStatus
from .services.redis_service import redis_service
from .services.search_service import check_search_index_consistency
from .services.status_derivation_service import recalculate_aggregation_from_tasks
from .models.document import Document
from .models.folder_file import FolderFile

logger = logging.getLogger(__name__)

# Parse Redis URL into components for ARQ
# Format: redis://host:port/db or redis://:password@host:port/db
def parse_redis_url(url: str) -> RedisSettings:
    """Parse Redis URL into ARQ RedisSettings."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(parsed.path.lstrip("/") or 0),
    )


# =============================================================================
# Archive Jobs
# =============================================================================

from .ai.config_service import get_agent_config


async def run_archive_jobs(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Archive stale tasks and projects.

    Archives:
    - Tasks in Done status for 7+ days
    - Projects where all tasks are archived

    Returns:
        dict with counts of archived items
    """
    logger.info("Running scheduled archive jobs...")

    tasks_archived = 0
    projects_archived = 0

    try:
        async with async_session_maker() as db:
            tasks_archived = await archive_stale_done_tasks(db)
            projects_archived = await archive_eligible_projects(db)
            await db.commit()

            logger.info(
                f"Archive jobs complete: {tasks_archived} tasks, {projects_archived} projects archived"
            )
    except Exception as e:
        logger.error(f"Error running archive jobs: {e}", exc_info=True)

    return {
        "tasks_archived": tasks_archived,
        "projects_archived": projects_archived,
        "run_at": utc_now().isoformat(),
    }


async def archive_stale_done_tasks(db: AsyncSession) -> int:
    """Archive all tasks that have been in Done status for 7+ days."""
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession
    from .models.project_task_status_agg import ProjectTaskStatusAgg

    now = utc_now()
    archive_after_days = get_agent_config().get_int("worker.archive_after_days", 7)
    cutoff_date = now - timedelta(days=archive_after_days)

    # Find all "Done" status IDs
    done_status_result = await db.execute(
        select(TaskStatus.id).where(TaskStatus.name == StatusName.DONE)
    )
    done_status_ids = [row[0] for row in done_status_result.all()]

    if not done_status_ids:
        return 0

    # L5: Use SQL GROUP BY to get affected project IDs and counts without
    # loading all task rows into memory.
    from sqlalchemy import func as sa_func

    affected_result = await db.execute(
        select(Task.project_id, sa_func.count(Task.id))
        .where(
            Task.task_status_id.in_(done_status_ids),
            Task.archived_at.is_(None),
            Task.completed_at.isnot(None),
            Task.completed_at <= cutoff_date,
        )
        .group_by(Task.project_id)
    )
    affected_rows = affected_result.all()

    if not affected_rows:
        logger.debug("No tasks eligible for archiving")
        return 0

    total_count = sum(row[1] for row in affected_rows)
    affected_project_ids = {row[0] for row in affected_rows}

    logger.info("Archiving %d tasks across %d projects", total_count, len(affected_project_ids))

    # Archive the tasks (bulk UPDATE, no need to load all IDs)
    await db.execute(
        update(Task)
        .where(
            Task.task_status_id.in_(done_status_ids),
            Task.archived_at.is_(None),
            Task.completed_at.isnot(None),
            Task.completed_at <= cutoff_date,
        )
        .values(archived_at=now)
    )

    # Update aggregations for affected projects
    for project_id in affected_project_ids:
        await _recalculate_project_aggregation(db, project_id)

    return total_count


async def archive_eligible_projects(db: AsyncSession) -> int:
    """Archive projects where all tasks are archived."""
    from sqlalchemy import select, update

    now = utc_now()

    # Subquery: projects with at least one task
    has_tasks = (
        select(Task.project_id)
        .where(Task.project_id == Project.id)
        .correlate(Project)
        .exists()
    )

    # Subquery: projects with at least one non-archived task
    has_active_tasks = (
        select(Task.project_id)
        .where(
            Task.project_id == Project.id,
            Task.archived_at.is_(None),
        )
        .correlate(Project)
        .exists()
    )

    # Find projects to archive
    query = (
        select(Project.id, Project.key, Project.name)
        .where(
            Project.archived_at.is_(None),
            has_tasks,
            ~has_active_tasks,
        )
    )

    result = await db.execute(query)
    projects_to_archive = result.all()

    if not projects_to_archive:
        logger.debug("No projects eligible for archiving")
        return 0

    project_ids_to_archive = [row[0] for row in projects_to_archive]

    # Log each project being archived
    for project_id, project_key, project_name in projects_to_archive:
        logger.info(f"  Archiving project: {project_key} - {project_name}")

    # Archive the projects
    await db.execute(
        update(Project)
        .where(Project.id.in_(project_ids_to_archive))
        .values(archived_at=now, updated_at=now)
    )

    return len(project_ids_to_archive)


async def _recalculate_project_aggregation(db: AsyncSession, project_id: Any) -> None:
    """Recalculate project aggregation after archiving tasks.

    Uses a single SQL GROUP BY query instead of loading all tasks in memory.
    """
    from sqlalchemy import func, select
    from .models.project_task_status_agg import ProjectTaskStatusAgg
    from .services.status_derivation_service import (
        STATUS_TO_COUNTER_FIELD,
        derive_project_status_from_model,
    )

    result = await db.execute(
        select(ProjectTaskStatusAgg).where(ProjectTaskStatusAgg.project_id == project_id)
    )
    agg = result.scalar_one_or_none()

    if agg is None:
        agg = ProjectTaskStatusAgg(
            project_id=project_id,
            total_tasks=0,
            todo_tasks=0,
            active_tasks=0,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=0,
        )
        db.add(agg)
        await db.flush()

    # Count non-archived tasks grouped by status name in a single SQL query
    counts_result = await db.execute(
        select(TaskStatus.name, func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id == project_id,
            Task.archived_at.is_(None),
        )
        .group_by(TaskStatus.name)
    )
    status_counts: dict[str, int] = dict(counts_result.all())

    # Reset all counters and rebuild from SQL result
    agg.total_tasks = 0
    agg.todo_tasks = 0
    agg.active_tasks = 0
    agg.review_tasks = 0
    agg.issue_tasks = 0
    agg.done_tasks = 0

    for status_name, count in status_counts.items():
        counter_field = STATUS_TO_COUNTER_FIELD.get(status_name, "todo_tasks")
        setattr(agg, counter_field, count)
        agg.total_tasks += count

    agg.updated_at = utc_now()

    # Derive the new project status
    derived_status_name = derive_project_status_from_model(agg)

    # Update project's derived status
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if project:
        # Look up the TaskStatus ID for the derived status name
        result = await db.execute(
            select(TaskStatus.id).where(
                TaskStatus.project_id == project_id,
                TaskStatus.name == derived_status_name,
            )
        )
        status_id = result.scalar_one_or_none()
        if status_id:
            project.derived_status_id = status_id


# =============================================================================
# Presence Cleanup Jobs
# =============================================================================

PRESENCE_TTL = 45  # seconds
PRESENCE_PREFIX = "presence:"
USER_DATA_PREFIX = "presence_data:"


async def cleanup_stale_presence(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Remove presence entries older than PRESENCE_TTL.

    Returns:
        dict with count of removed entries
    """
    import time

    cutoff = time.time() - PRESENCE_TTL
    total_removed = 0

    if not redis_service.is_connected:
        logger.debug("Redis not connected, skipping presence cleanup")
        return {"removed": 0}

    try:
        keys = await redis_service.scan_keys(f"{PRESENCE_PREFIX}*")
        if keys:
            # L2: Process in batches to avoid sending thousands of commands
            # in a single pipeline.
            _SCAN_BATCH_LIMIT = 200
            room_ids = []
            for batch_start in range(0, len(keys), _SCAN_BATCH_LIMIT):
                batch_keys = keys[batch_start:batch_start + _SCAN_BATCH_LIMIT]
                pipe = redis_service.client.pipeline(transaction=False)
                batch_room_ids = []
                for key in batch_keys:
                    room_id = key.replace(PRESENCE_PREFIX, "")
                    batch_room_ids.append(room_id)
                    pipe.zremrangebyscore(
                        f"{PRESENCE_PREFIX}{room_id}",
                        min="-inf",
                        max=cutoff,
                    )
                results = await pipe.execute()
                for room_id, removed in zip(batch_room_ids, results):
                    if removed > 0:
                        logger.debug(f"Cleaned {removed} stale entries from room {room_id}")
                        total_removed += removed
                room_ids.extend(batch_room_ids)
    except Exception as e:
        logger.error(f"Redis presence cleanup error: {e}")

    return {"removed": total_removed}


# =============================================================================
# Embedding Jobs
# =============================================================================


async def _broadcast_embedding_status(
    doc_scope: dict[str, Any] | None,
    document_id: str,
    embedding_status: str,
    chunk_count: int = 0,
) -> None:
    """Broadcast embedding status change to the frontend via WS."""
    if doc_scope is None:
        return
    try:
        ws_payload = {
            "type": "embedding_updated",
            "data": {
                "document_id": document_id,
                "chunk_count": chunk_count,
                "embedding_status": embedding_status,
                "timestamp": utc_now().isoformat(),
            },
        }
        if doc_scope["application_id"]:
            room_id = f"application:{doc_scope['application_id']}"
        elif doc_scope["project_id"]:
            # Use pre-resolved application_id if available to avoid extra DB session
            app_id = doc_scope.get("_application_id")
            if app_id:
                room_id = f"application:{app_id}"
            else:
                from .models.project import Project
                async with async_session_maker() as ws_db:
                    proj = await ws_db.get(Project, doc_scope["project_id"])
                room_id = f"application:{proj.application_id}" if proj and proj.application_id else None
        elif doc_scope["user_id"]:
            room_id = f"user:{doc_scope['user_id']}"
        else:
            room_id = None
        if room_id:
            await redis_service.publish("ws:broadcast", {"room_id": room_id, "message": ws_payload})
    except Exception as ws_err:
        logger.warning(
            "Failed to broadcast embedding_status=%s for document %s: %s",
            embedding_status, document_id, ws_err,
        )


async def embed_document_job(ctx: dict[str, Any], document_id: str) -> dict[str, Any]:
    """
    Background job to embed a single document.

    ARQ deduplication (_job_id) ensures only one pending embed job exists
    per document. The job reads current content from DB at execution time,
    so it always embeds the latest version regardless of when it was enqueued.

    Args:
        ctx: ARQ context dict.
        document_id: UUID string of the document to embed.

    Returns:
        dict with chunk_count and token_count on success, or error info.
    """
    import json
    from uuid import UUID as _UUID

    from sqlalchemy import select

    _cfg = get_agent_config()
    EMBED_TIMEOUT_S = _cfg.get_int("worker.embed_timeout_s", 30)
    MAX_EMBED_RETRIES = _cfg.get_int("worker.max_embed_retries", 3)
    EMBED_RETRY_KEY = f"embed_retry:{document_id}"

    doc_uuid = _UUID(document_id)
    doc_scope: dict[str, Any] | None = None

    # Retry guard: check and increment retry counter in Redis
    try:
        retry_count = 0
        if redis_service.is_connected:
            raw = await redis_service.get(EMBED_RETRY_KEY)
            retry_count = int(raw) if raw else 0
            if retry_count >= MAX_EMBED_RETRIES:
                logger.error(
                    "embed_document_job: max retries (%d) reached for %s, setting failed",
                    MAX_EMBED_RETRIES, document_id,
                )
                async with async_session_maker() as err_db:
                    from sqlalchemy import select as sa_select, update as sa_update
                    # Fetch scope before update for WS broadcast
                    doc_row = (await err_db.execute(
                        sa_select(Document.application_id, Document.project_id, Document.user_id)
                        .where(Document.id == doc_uuid)
                    )).one_or_none()
                    await err_db.execute(
                        sa_update(Document)
                        .where(Document.id == doc_uuid)
                        .values(embedding_status="failed", updated_at=utc_now())
                    )
                    await err_db.commit()
                    if doc_row:
                        scope = {"application_id": doc_row[0], "project_id": doc_row[1], "user_id": doc_row[2]}
                        await _broadcast_embedding_status(scope, document_id, "failed")
                return {"status": "error", "error": "max_retries_exceeded"}
            await redis_service.set(EMBED_RETRY_KEY, str(retry_count + 1), ttl=3600)
    except Exception as retry_err:
        logger.warning("embed_document_job: retry counter check failed: %s", retry_err)

    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Document).where(
                    Document.id == doc_uuid,
                    Document.deleted_at.is_(None),
                )
            )
            doc = result.scalar_one_or_none()

            if doc is None:
                logger.warning("embed_document_job: document %s not found or deleted", document_id)
                return {"status": "skipped", "reason": "not_found"}

            # Save scope info for failure-path WS broadcast (doc may not be available in except)
            doc_scope = {
                "application_id": doc.application_id,
                "project_id": doc.project_id,
                "user_id": doc.user_id,
            }

            # FIX-6: Pre-resolve project's application_id to avoid second DB session in broadcast
            if doc.project_id and not doc.application_id:
                from .models.project import Project
                proj_row = await db.get(Project, doc.project_id)
                if proj_row and proj_row.application_id:
                    doc_scope["_application_id"] = proj_row.application_id

            if not doc.content_json:
                # Reset syncing status for empty documents
                doc.embedding_status = "none"
                await db.commit()
                logger.info("embed_document_job: document %s has no content, reset to none", document_id)
                await _broadcast_embedding_status(doc_scope, document_id, "none")
                return {"status": "skipped", "reason": "no_content"}

            # Transition to "syncing" BEFORE embedding so the WHERE guard
            # in _update_embedding_timestamp can succeed
            doc.embedding_status = "syncing"
            await db.flush()

            content = json.loads(doc.content_json)

            # Detect canvas format for proper chunking strategy
            doc_type = "canvas" if isinstance(content, dict) and content.get("format") == "canvas" else "document"

            # Guard against malformed content_json (e.g., empty array from buggy migration)
            if not isinstance(content, dict):
                doc.embedding_status = "failed"
                await db.commit()
                logger.warning("embed_document_job: document %s has non-dict content_json (type=%s), marked failed", document_id, type(content).__name__)
                await _broadcast_embedding_status(doc_scope, document_id, "failed")
                return {"status": "error", "error": "invalid_content_format"}

            scope_ids = {
                "application_id": doc.application_id,
                "project_id": doc.project_id,
                "user_id": doc.user_id,
            }

            from .ai.chunking_service import SemanticChunker
            from .ai.embedding_normalizer import EmbeddingNormalizer
            from .ai.embedding_service import EmbeddingService
            from .ai.provider_registry import ProviderRegistry

            registry = ProviderRegistry()
            chunker = SemanticChunker()
            normalizer = EmbeddingNormalizer()

            service = EmbeddingService(
                provider_registry=registry,
                chunker=chunker,
                normalizer=normalizer,
                db=db,
            )

            embed_result = await asyncio.wait_for(
                service.embed_document(
                    document_id=doc_uuid,
                    content_json=content,
                    title=doc.title,
                    scope_ids=scope_ids,
                    document_type=doc_type,
                ),
                timeout=EMBED_TIMEOUT_S,
            )

            # Process images through vision LLM and store as supplementary chunks
            image_count = 0
            try:
                from .ai.image_understanding_service import ImageUnderstandingService
                from .services.minio_service import minio_service

                image_svc = ImageUnderstandingService(
                    provider_registry=registry,
                    embedding_service=service,
                    minio_service=minio_service,
                    db=db,
                )
                image_descriptions = await image_svc.process_document_images(
                    document_id=doc_uuid,
                    content_json=content,
                )
                image_count = len(image_descriptions)
            except Exception as img_err:
                logger.warning(
                    "embed_document_job: image processing failed for %s (non-fatal): %s",
                    document_id, img_err,
                )

            await db.commit()

            total_chunks = embed_result.chunk_count + image_count
            logger.info(
                "embed_document_job: document %s embedded — %d text chunks, %d image chunks, %d tokens, %dms",
                document_id, embed_result.chunk_count, image_count, embed_result.token_count, embed_result.duration_ms,
            )

            await _broadcast_embedding_status(doc_scope, document_id, "synced", total_chunks)

            # Clear retry counter on success
            try:
                if redis_service.is_connected:
                    await redis_service.delete(EMBED_RETRY_KEY)
            except Exception:
                pass

            return {
                "status": "success",
                "chunk_count": total_chunks,
                "text_chunks": embed_result.chunk_count,
                "image_chunks": image_count,
                "token_count": embed_result.token_count,
                "duration_ms": embed_result.duration_ms,
            }

    except Exception as e:
        logger.error("embed_document_job failed for document %s: %s", document_id, e, exc_info=True)
        # Use "failed" when retries exhausted, "stale" for retryable failures
        # retry_count was already incremented before the main try block
        retries_exhausted = (retry_count + 1) >= MAX_EMBED_RETRIES
        new_status = "failed" if retries_exhausted else "stale"
        try:
            async with async_session_maker() as err_db:
                from sqlalchemy import update as sa_update
                # FIX-5: Atomic UPDATE...WHERE guards against TOCTOU race
                err_result = await err_db.execute(
                    sa_update(Document)
                    .where(Document.id == doc_uuid, Document.embedding_status == "syncing")
                    .values(embedding_status=new_status, updated_at=utc_now())
                )
                await err_db.commit()
                if err_result.rowcount == 0:
                    logger.warning(
                        "Document %s embedding_status already changed, skipping error broadcast",
                        document_id,
                    )
                    return {"status": "error", "error": type(e).__name__}
        except Exception as reset_err:
            logger.warning("Failed to reset embedding_status for %s: %s", document_id, reset_err)
        await _broadcast_embedding_status(doc_scope, document_id, new_status)
        # Return type name only (not str(e)) to avoid leaking sensitive context
        return {"status": "error", "error": type(e).__name__}


# =============================================================================
# File Extraction & Embedding Job
# =============================================================================


async def extract_and_embed_file_job(ctx: dict[str, Any], file_id: str) -> dict[str, Any]:
    """Background job to extract content from a FolderFile and embed it.

    Pipeline:
    1. Retry guard (Redis key extract_retry:{file_id})
    2. Load FolderFile (skip if deleted/completed/unsupported)
    3. Set processing status
    4. Download from MinIO to temp file
    5. Extract content (with timeout)
    6. Index in Meilisearch
    7. Embed content (if extraction succeeded)
    8. Commit + WebSocket broadcast
    9. Error handling: set failed status, broadcast failure

    Args:
        ctx: ARQ context dict.
        file_id: UUID string of the FolderFile.

    Returns:
        dict with extraction/embedding results.
    """
    import json
    import tempfile
    from uuid import UUID as _UUID
    from pathlib import Path

    from sqlalchemy import select, update as sa_update

    _cfg = get_agent_config()
    EXTRACT_TIMEOUT_S = _cfg.get_int("worker.extract_timeout_s", 120)
    MAX_EXTRACT_RETRIES = _cfg.get_int("worker.max_extract_retries", 3)
    RETRY_KEY = f"extract_retry:{file_id}"

    file_uuid = _UUID(file_id)
    file_scope: dict[str, Any] | None = None

    # Retry guard
    try:
        retry_count = 0
        if redis_service.is_connected:
            raw = await redis_service.get(RETRY_KEY)
            retry_count = int(raw) if raw else 0
            if retry_count >= MAX_EXTRACT_RETRIES:
                logger.error(
                    "extract_and_embed_file_job: max retries (%d) reached for %s",
                    MAX_EXTRACT_RETRIES, file_id,
                )
                async with async_session_maker() as err_db:
                    await err_db.execute(
                        sa_update(FolderFile)
                        .where(FolderFile.id == file_uuid)
                        .values(
                            extraction_status="failed",
                            extraction_error="Max retries exceeded",
                            updated_at=utc_now(),
                        )
                    )
                    await err_db.commit()
                return {"status": "error", "error": "max_retries_exceeded"}
            await redis_service.set(RETRY_KEY, str(retry_count + 1), ttl=3600)
    except Exception as retry_err:
        logger.warning("extract_and_embed_file_job: retry check failed: %s", retry_err)

    import shutil

    # HIGH-10: Max content_plain size (2MB), configurable at runtime (QE-NEW-1)
    # FIX-7: Reuse _cfg from top of function instead of opening a second config handle
    MAX_CONTENT_PLAIN = max(1024, _cfg.get_int("worker.max_content_plain", 2_000_000))
    # HIGH-7: Use configurable embed timeout
    EMBED_TIMEOUT_S = _cfg.get_int("worker.embed_timeout_s", 30)

    try:
        # HIGH-11 / MED-8: First session — load file and set "processing" status,
        # then close so we don't hold a DB connection during CPU-bound extraction.
        file_display_name: str = ""
        file_mime_type: str = ""
        file_extension: str = ""
        file_storage_bucket: str = ""
        file_storage_key: str = ""
        file_file_size: int = 0
        file_folder_id = None
        file_created_by = None
        file_updated_at_ts: int = 0

        async with async_session_maker() as db:
            # HIGH-12: Atomic status transition — only grab the job if status
            # is pending or failed (prevents double-processing)
            atomic_result = await db.execute(
                sa_update(FolderFile)
                .where(
                    FolderFile.id == file_uuid,
                    FolderFile.deleted_at.is_(None),
                    FolderFile.extraction_status.in_(["pending", "failed"]),
                )
                .values(extraction_status="processing", updated_at=utc_now())
                .returning(FolderFile.id)
            )
            if not atomic_result.scalar_one_or_none():
                # Either not found, deleted, or already being processed
                check_result = await db.execute(
                    select(FolderFile.extraction_status).where(FolderFile.id == file_uuid)
                )
                current_status = check_result.scalar_one_or_none()
                if current_status is None:
                    logger.warning("extract_and_embed_file_job: file %s not found or deleted", file_id)
                    return {"status": "skipped", "reason": "not_found"}
                logger.info("extract_and_embed_file_job: file %s is %s, skipping", file_id, current_status)
                return {"status": "skipped", "reason": current_status}

            await db.commit()

            # Re-fetch to cache fields needed after session close
            result = await db.execute(
                select(FolderFile).where(FolderFile.id == file_uuid)
            )
            ff = result.scalar_one()

            # Save scope for WS broadcast
            file_scope = {
                "application_id": ff.application_id,
                "project_id": ff.project_id,
                "user_id": ff.user_id,
            }

            # FIX-6: Pre-resolve project's application_id to avoid second DB session in broadcast
            project_application_id = None
            if ff.project_id and not ff.application_id:
                from .models.project import Project
                proj_row = await db.get(Project, ff.project_id)
                if proj_row and proj_row.application_id:
                    file_scope["_application_id"] = proj_row.application_id
                    project_application_id = proj_row.application_id

            # Cache fields needed after session close
            file_display_name = ff.display_name
            file_mime_type = ff.mime_type
            file_extension = ff.file_extension
            file_storage_bucket = ff.storage_bucket
            file_storage_key = ff.storage_key
            file_file_size = ff.file_size
            file_folder_id = ff.folder_id
            file_created_by = ff.created_by
            file_updated_at_ts = int(ff.updated_at.timestamp())
        # Session closed here — no DB held during extraction

        # HIGH-3: Wrap entire temp dir usage in try/finally for guaranteed cleanup
        tmp_dir = tempfile.mkdtemp(prefix="pm_extract_")
        try:
            # Download from MinIO to temp file
            from .services.minio_service import minio_service

            ext = f".{file_extension}" if file_extension else ""
            tmp_path = Path(tmp_dir) / f"file{ext}"

            # QE-NEW-2: Stream download to temp file instead of buffering in memory
            # FIX-3: Wrap synchronous MinIO call in asyncio.to_thread to avoid blocking event loop
            try:
                await asyncio.to_thread(
                    minio_service.download_to_file,
                    bucket=file_storage_bucket,
                    object_name=file_storage_key,
                    file_path=str(tmp_path),
                )
            except Exception as dl_err:
                raise RuntimeError(f"MinIO download failed: {dl_err}")

            # Extract content
            from .ai.file_extraction_service import FileExtractionService

            extraction_svc = FileExtractionService()
            extraction_result = await asyncio.wait_for(
                extraction_svc.extract(
                    file_path=tmp_path,
                    extension=ext,
                    file_size=file_file_size,
                ),
                timeout=EXTRACT_TIMEOUT_S,
            )
        finally:
            # HIGH-3: Guaranteed temp dir cleanup
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # CRIT-4: Map extraction errors to safe categories
        if not extraction_result.success:
            error_category = _categorize_extraction_error(extraction_result.error)
            async with async_session_maker() as db2:
                # FIX-3: Atomic UPDATE...WHERE prevents TOCTOU race with reaper
                err_result = await db2.execute(
                    sa_update(FolderFile)
                    .where(
                        FolderFile.id == file_uuid,
                        FolderFile.extraction_status == "processing",
                    )
                    .values(
                        extraction_status="failed",
                        extraction_error=error_category,
                        embedding_status="failed",
                        updated_at=utc_now(),
                    )
                )
                await db2.commit()
            # FIX-6: Skip broadcast if reaper already reset the status
            if err_result.rowcount == 0:
                logger.warning("File %s status already changed by reaper, skipping error broadcast", file_id)
            else:
                await _broadcast_file_event(
                    file_scope, file_id, "file_extraction_failed",
                    {"error": error_category, "folder_id": str(file_folder_id) if file_folder_id else None},
                )
            return {"status": "error", "error": error_category}

        # HIGH-11: Re-open session for final updates
        async with async_session_maker() as db3:
            result3 = await db3.execute(
                select(FolderFile).where(
                    FolderFile.id == file_uuid,
                    FolderFile.deleted_at.is_(None),
                )
            )
            ff3 = result3.scalar_one_or_none()
            if ff3 is None:
                logger.warning(
                    "extract_and_embed_file_job: file %s was deleted during processing, skipping",
                    file_id,
                )
                return {"status": "skipped", "reason": "deleted_during_extraction"}

            # HIGH-10: Truncate content_plain to cap
            content_plain = extraction_result.markdown or ""
            if len(content_plain) > MAX_CONTENT_PLAIN:
                content_plain = content_plain[:MAX_CONTENT_PLAIN]

            ff3.content_plain = content_plain
            ff3.extracted_metadata = extraction_result.metadata or {}
            ff3.extraction_status = "completed"
            ff3.extraction_error = None

            # MED-14: Index in Meilisearch using index_file_from_data consistently
            try:
                from .services.search_service import build_search_file_data, index_file_from_data

                search_data = build_search_file_data(ff3, project_application_id=project_application_id)
                await index_file_from_data(search_data)
            except Exception as ms_err:
                logger.warning(
                    "extract_and_embed_file_job: Meilisearch indexing failed for %s: %s",
                    file_id, ms_err,
                )

            # Embed content
            embed_chunk_count = 0
            embed_token_count = 0
            embed_duration_ms = 0
            if content_plain.strip():
                try:
                    ff3.embedding_status = "syncing"
                    await db3.flush()

                    from .ai.chunking_service import SemanticChunker
                    from .ai.embedding_normalizer import EmbeddingNormalizer
                    from .ai.embedding_service import EmbeddingService
                    from .ai.provider_registry import ProviderRegistry

                    registry = ProviderRegistry()
                    chunker = SemanticChunker()
                    normalizer = EmbeddingNormalizer()

                    embed_svc = EmbeddingService(
                        provider_registry=registry,
                        chunker=chunker,
                        normalizer=normalizer,
                        db=db3,
                    )

                    embed_result = await asyncio.wait_for(
                        embed_svc.embed_file(
                            file_id=file_uuid,
                            markdown=content_plain,
                            title=file_display_name,
                            scope_ids={
                                "application_id": ff3.application_id,
                                "project_id": ff3.project_id,
                                "user_id": ff3.user_id,
                            },
                        ),
                        timeout=EMBED_TIMEOUT_S,
                    )
                    embed_chunk_count = embed_result.chunk_count
                    embed_token_count = embed_result.token_count
                    embed_duration_ms = embed_result.duration_ms
                    ff3.embedding_status = "synced"
                    ff3.embedding_updated_at = utc_now()
                except Exception as embed_err:
                    logger.warning(
                        "extract_and_embed_file_job: embedding failed for %s (non-fatal): %s",
                        file_id, embed_err,
                    )
                    ff3.embedding_status = "failed"

            await db3.commit()

            logger.info(
                "extract_and_embed_file_job: file %s processed — extraction=%s, "
                "%d chunks, %d tokens, %dms",
                file_id, ff3.extraction_status,
                embed_chunk_count, embed_token_count, embed_duration_ms,
            )

            # CRIT-2: Include folder_id in broadcast payload
            await _broadcast_file_event(
                file_scope, file_id, "file_extraction_completed",
                {
                    "folder_id": str(file_folder_id) if file_folder_id else None,
                    "extraction_status": "completed",
                    "embedding_status": ff3.embedding_status,
                    "chunk_count": embed_chunk_count,
                },
            )

            # Broadcast embedding status so the frontend updates the file's
            # embedding badge without a full refetch (mirrors embed_document_job).
            await _broadcast_embedding_status(
                file_scope, file_id, ff3.embedding_status or "none", embed_chunk_count,
            )

            # Clear retry counter on success
            try:
                if redis_service.is_connected:
                    await redis_service.delete(RETRY_KEY)
            except Exception:
                pass

            return {
                "status": "success",
                "extraction_status": "completed",
                "chunk_count": embed_chunk_count,
                "token_count": embed_token_count,
                "duration_ms": embed_duration_ms,
            }

    except Exception as e:
        logger.error("extract_and_embed_file_job failed for file %s: %s", file_id, e, exc_info=True)
        # CRIT-4: Store safe error category, not raw exception text
        error_category = _categorize_extraction_error(str(e))
        try:
            async with async_session_maker() as err_db:
                # FIX-3: Atomic UPDATE...WHERE prevents TOCTOU race with reaper.
                # Only transition from "processing" to "failed" — if the reaper
                # already reset to "pending", skip the error update.
                err_result = await err_db.execute(
                    sa_update(FolderFile)
                    .where(
                        FolderFile.id == file_uuid,
                        FolderFile.extraction_status == "processing",
                    )
                    .values(
                        extraction_status="failed",
                        extraction_error=error_category,
                        embedding_status="failed",
                        updated_at=utc_now(),
                    )
                )
                await err_db.commit()
                # FIX-6: Skip broadcast if reaper already reset the status
                if err_result.rowcount == 0:
                    logger.warning(
                        "File %s status already changed by reaper, skipping error broadcast",
                        file_id,
                    )
                else:
                    if file_scope is not None:
                        await _broadcast_file_event(
                            file_scope, file_id, "file_extraction_failed",
                            {"error": error_category, "folder_id": str(file_folder_id) if file_folder_id else None},
                        )
        except Exception as reset_err:
            logger.warning("Failed to set extraction_status for %s: %s", file_id, reset_err)

        return {"status": "error", "error": type(e).__name__}


def _categorize_extraction_error(error_text: str | None) -> str:
    """Map raw exception text to a safe user-facing error category (CRIT-4).

    Full exception text is only logged server-side. The returned category
    is stored in extraction_error and returned to all users.
    """
    if not error_text:
        return "extraction_failed"

    lower = error_text.lower()

    if "password" in lower or "encrypted" in lower:
        return "password_protected"
    if "corrupt file" in lower or "corrupted" in lower or "bad zip" in lower or "badzipfile" in lower:
        return "corrupt_file"
    if "invalid file" in lower or "invalid format" in lower:
        return "corrupt_file"
    if "timeout" in lower:
        return "extraction_timeout"

    return "extraction_failed"


async def _broadcast_file_event(
    scope: dict[str, Any] | None,
    file_id: str,
    event_type: str,
    extra_data: dict[str, Any] | None = None,
) -> None:
    """Broadcast a file extraction event via WebSocket (through Redis pub/sub).

    CRIT-2: extra_data should include folder_id for frontend cache invalidation.
    """
    if scope is None:
        return

    try:
        # Derive scope and scope_id from the scope dict for targeted cache invalidation
        if scope.get("application_id"):
            derived_scope = "application"
            derived_scope_id = str(scope["application_id"])
        elif scope.get("project_id"):
            derived_scope = "project"
            derived_scope_id = str(scope["project_id"])
        elif scope.get("user_id"):
            derived_scope = "personal"
            derived_scope_id = str(scope["user_id"])
        else:
            derived_scope = None
            derived_scope_id = None

        ws_payload: dict[str, Any] = {
            "type": event_type,
            "data": {
                "file_id": file_id,
                "timestamp": utc_now().isoformat(),
                "scope": derived_scope,
                "scope_id": derived_scope_id,
                **(extra_data or {}),
            },
        }

        room_id: str | None = None
        if scope.get("application_id"):
            room_id = f"application:{scope['application_id']}"
        elif scope.get("project_id"):
            # Use pre-resolved application_id if available to avoid extra DB session
            app_id = scope.get("_application_id")
            if app_id:
                room_id = f"application:{app_id}"
            else:
                from .models.project import Project
                async with async_session_maker() as _db:
                    proj = await _db.get(Project, scope["project_id"])
                    if proj and proj.application_id:
                        room_id = f"application:{proj.application_id}"
        elif scope.get("user_id"):
            room_id = f"user:{scope['user_id']}"

        if room_id:
            await redis_service.publish(
                "ws:broadcast",
                {"room_id": room_id, "message": ws_payload},
            )
    except Exception as ws_err:
        logger.warning("Failed to broadcast %s for file %s: %s", event_type, file_id, ws_err)


# =============================================================================
# Nightly Batch Embedding Job (Phase 9.6)
# =============================================================================

async def batch_embed_stale_documents(ctx: dict[str, Any]) -> dict[str, Any]:
    """Nightly cron job: embed all documents with stale or missing embeddings.

    Queries documents where ``embedding_status`` is ``'stale'`` or ``'none'``
    and ``content_json IS NOT NULL``, then enqueues embed jobs
    in batches with spacing to avoid overwhelming the embedding API.

    Returns:
        dict with count of documents queued.
    """
    from sqlalchemy import select

    _cfg = get_agent_config()
    NIGHTLY_EMBED_BATCH_SIZE = _cfg.get_int("worker.nightly_embed_batch_size", 10)
    NIGHTLY_EMBED_BATCH_DELAY_S = _cfg.get_int("worker.nightly_embed_batch_delay_s", 5)
    MAX_NIGHTLY_EMBED = _cfg.get_int("worker.max_nightly_embed", 500)

    queued = 0
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Document.id).where(
                    Document.deleted_at.is_(None),
                    Document.content_json.isnot(None),
                    Document.embedding_status.in_(["stale", "none"]),
                ).limit(MAX_NIGHTLY_EMBED)
            )
            stale_ids = [row[0] for row in result.all()]

            if not stale_ids:
                logger.info("batch_embed_stale_documents: no stale documents found")
                return {"status": "success", "queued": 0}

            logger.info(
                "batch_embed_stale_documents: found %d stale documents",
                len(stale_ids),
            )

            # M5: Removed bulk pre-update to 'syncing'. Each embed_document_job
            # transitions its own document to 'syncing' atomically, preventing
            # 24h limbo on crash.

            from .services.arq_helper import get_arq_redis

            arq_redis = await get_arq_redis()

            for i in range(0, len(stale_ids), NIGHTLY_EMBED_BATCH_SIZE):
                batch = stale_ids[i : i + NIGHTLY_EMBED_BATCH_SIZE]
                for doc_id in batch:
                    try:
                        await arq_redis.enqueue_job(
                            "embed_document_job",
                            str(doc_id),
                            _job_id=f"embed:{doc_id}",
                        )
                        queued += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to enqueue embed for doc %s: %s", doc_id, e
                        )

                # Pause between batches to avoid overwhelming the API
                if i + NIGHTLY_EMBED_BATCH_SIZE < len(stale_ids):
                    await asyncio.sleep(NIGHTLY_EMBED_BATCH_DELAY_S)

    except Exception as e:
        logger.error("batch_embed_stale_documents failed: %s", e, exc_info=True)
        return {"status": "error", "error": type(e).__name__, "queued": queued}

    logger.info("batch_embed_stale_documents: queued %d documents", queued)
    return {"status": "success", "queued": queued}


# =============================================================================
# Document Import Jobs
# =============================================================================

MAX_IMPORT_RETRIES = 5
IMPORT_CONCURRENCY_KEY = "import:concurrency:count"
IMPORT_CONCURRENCY_TTL = 3600  # 1hr safety TTL

# Lua script for atomic INCR + EXPIRE (prevents TTL leak on crash between calls)
_INCR_WITH_TTL_LUA = """
local v = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[1])
return v
"""


async def _update_import_progress(session: AsyncSession, job_id, pct: int) -> None:
    """Update import job progress percentage in a separate connection.

    Uses an independent session so progress updates are immediately visible
    to polling clients, without interfering with the main pipeline transaction.
    """
    from sqlalchemy import update as sa_update

    from .models.import_job import ImportJob

    async with async_session_maker() as progress_db:
        await progress_db.execute(
            sa_update(ImportJob).where(ImportJob.id == job_id).values(progress_pct=pct)
        )
        await progress_db.commit()


def _parse_inline_marks(text: str) -> list[dict]:
    """Parse inline markdown formatting into TipTap text nodes with marks.

    Handles:
    - ``[text](url)`` links
    - ``**bold**`` text
    - ``*italic*`` text
    - ````code```` spans
    - Plain text (everything else)

    Args:
        text: Raw inline markdown string.

    Returns:
        List of TipTap text nodes with appropriate marks applied.
    """
    import re

    nodes: list[dict] = []
    pattern = re.compile(
        r'\[([^\]]+)\]\(([^)]+)\)'  # [text](url)
        r'|\*\*(.+?)\*\*'           # **bold**
        r'|\*(.+?)\*'               # *italic*
        r'|`(.+?)`'                 # `code`
        r'|([^*`\[]+)'              # plain text
    )
    for match in pattern.finditer(text):
        if match.group(1):  # link
            href = match.group(2)
            # Only allow safe URL protocols
            if href.lower().startswith(('http://', 'https://', 'mailto:')):
                nodes.append({
                    "type": "text",
                    "marks": [{"type": "link", "attrs": {"href": href}}],
                    "text": match.group(1),
                })
            else:
                # Unsafe protocol - render as plain text
                nodes.append({"type": "text", "text": match.group(1)})
        elif match.group(3):  # bold
            nodes.append({
                "type": "text",
                "marks": [{"type": "bold"}],
                "text": match.group(3),
            })
        elif match.group(4):  # italic
            nodes.append({
                "type": "text",
                "marks": [{"type": "italic"}],
                "text": match.group(4),
            })
        elif match.group(5):  # code
            nodes.append({
                "type": "text",
                "marks": [{"type": "code"}],
                "text": match.group(5),
            })
        elif match.group(6):  # plain
            nodes.append({"type": "text", "text": match.group(6)})
    return nodes or [{"type": "text", "text": text}]


def _parse_table_block(lines: list[str], start: int) -> tuple[dict | None, int]:
    """Parse a Markdown pipe table starting at *start* into a TipTap table node.

    Returns ``(table_node, next_line_index)`` on success or
    ``(None, start)`` if the lines do not form a valid table.

    A valid table requires at least a header row and a separator row
    (``| --- | --- |``).

    Args:
        lines: Full list of document lines.
        start: Index of the first line that might be a header row.

    Returns:
        Tuple of (TipTap table dict or None, next line index to process).
    """
    import re

    if start >= len(lines):
        return None, start

    header_line = lines[start].strip()
    if not header_line.startswith("|"):
        return None, start

    # Must have a separator row immediately after the header
    if start + 1 >= len(lines):
        return None, start
    sep_line = lines[start + 1].strip()
    if not re.match(r"^\|[\s\-:|]+\|$", sep_line):
        return None, start

    def parse_row(line: str) -> list[str]:
        cells = line.strip().strip("|").split("|")
        return [c.strip() for c in cells]

    header_cells = parse_row(header_line)

    rows: list[dict] = []
    # Header row as tableHeader cells
    header_row = {
        "type": "tableRow",
        "content": [
            {
                "type": "tableHeader",
                "content": [{"type": "paragraph", "content": _parse_inline_marks(cell)}],
            }
            for cell in header_cells
        ],
    }
    rows.append(header_row)

    i = start + 2  # skip header + separator
    while i < len(lines):
        row_line = lines[i].strip()
        if not row_line.startswith("|"):
            break
        cells = parse_row(row_line)
        rows.append({
            "type": "tableRow",
            "content": [
                {
                    "type": "tableCell",
                    "content": [{"type": "paragraph", "content": _parse_inline_marks(cell)}],
                }
                for cell in cells
            ],
        })
        i += 1

    return {"type": "table", "content": rows}, i


def markdown_to_tiptap_json(markdown: str) -> dict:
    """Convert markdown text to a TipTap JSON document structure.

    Handles:
    - Paragraphs (with inline **bold**, *italic*, ``code``, [links](url))
    - Headings (``#`` through ``######``)
    - Bullet lists (``-`` or ``*``)
    - Ordered lists (``1.`` ``2.`` etc.)
    - Code blocks (fenced with ``````)
    - Blockquotes (``>``)
    - Horizontal rules (``---``, ``***``, ``___``)
    - Pipe tables (``| col | col |``)

    Args:
        markdown: Raw markdown string.

    Returns:
        TipTap-compatible JSON dict with ``"type": "doc"`` at the root.
    """
    import re

    lines = markdown.split("\n")
    content: list[dict] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # --- Code block (fenced) ---
        if line.strip().startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code_text = "\n".join(code_lines)
            content.append({
                "type": "codeBlock",
                "content": [{"type": "text", "text": code_text}] if code_text else [],
            })
            continue

        # --- Horizontal rule ---
        if re.match(r"^\s*([-*_])\s*\1\s*\1[\s\-*_]*$", line):
            content.append({"type": "horizontalRule"})
            i += 1
            continue

        # --- Heading ---
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            content.append({
                "type": "heading",
                "attrs": {"level": level},
                "content": _parse_inline_marks(text),
            })
            i += 1
            continue

        # --- Blockquote ---
        if line.strip().startswith(">"):
            bq_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                bq_lines.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            bq_text = "\n".join(bq_lines).strip()
            # Parse inner content as paragraphs
            inner_paras = [p.strip() for p in bq_text.split("\n") if p.strip()]
            bq_content: list[dict] = []
            for para in inner_paras:
                bq_content.append({
                    "type": "paragraph",
                    "content": _parse_inline_marks(para),
                })
            if not bq_content:
                bq_content = [{"type": "paragraph", "content": []}]
            content.append({"type": "blockquote", "content": bq_content})
            continue

        # --- Pipe table ---
        if line.strip().startswith("|"):
            table_node, next_i = _parse_table_block(lines, i)
            if table_node is not None:
                content.append(table_node)
                i = next_i
                continue

        # --- Bullet list ---
        bullet_match = re.match(r"^[\s]*[-*]\s+(.+)$", line)
        if bullet_match:
            items: list[dict] = []
            while i < len(lines):
                bm = re.match(r"^[\s]*[-*]\s+(.+)$", lines[i])
                if not bm:
                    break
                items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": _parse_inline_marks(bm.group(1).strip()),
                    }],
                })
                i += 1
            content.append({"type": "bulletList", "content": items})
            continue

        # --- Ordered list ---
        ordered_match = re.match(r"^[\s]*\d+[.)]\s+(.+)$", line)
        if ordered_match:
            items = []
            while i < len(lines):
                om = re.match(r"^[\s]*\d+[.)]\s+(.+)$", lines[i])
                if not om:
                    break
                items.append({
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": _parse_inline_marks(om.group(1).strip()),
                    }],
                })
                i += 1
            content.append({"type": "orderedList", "content": items})
            continue

        # --- Empty line: skip ---
        if not line.strip():
            i += 1
            continue

        # --- Paragraph (default) ---
        content.append({
            "type": "paragraph",
            "content": _parse_inline_marks(line.strip()),
        })
        i += 1

    # Ensure at least one empty paragraph for TipTap compatibility
    if not content:
        content.append({"type": "paragraph", "content": [{"type": "text", "text": ""}]})

    return {"type": "doc", "content": content}


async def process_document_import(ctx: dict[str, Any], job_id: str, _retry_count: int = 0) -> dict[str, Any]:
    """Background job to process a document import.

    Pipeline:
        1. Load ImportJob from DB, set status='processing', progress=10%
        2. Read file from temp_file_path
        3. Convert via DoclingService.process_file() -> progress=40%
        4. Create Document (convert markdown to TipTap JSON) -> progress=50%
        5. Upload extracted images to MinIO -> progress=60%
        6. Process images through vision LLM -> progress=80%
        7. Trigger embed_document_job -> progress=90%
        8. Finalize: status='completed', document_id, progress=100%

    Error handling: Any failure sets status='failed', error_message, and
    cleans up the temp file.

    WebSocket: Broadcasts IMPORT_COMPLETED or IMPORT_FAILED to the user's
    channel so the frontend can react in real time.

    Args:
        ctx: ARQ context dict.
        job_id: UUID string of the ImportJob to process.

    Returns:
        dict with status and metadata on success, or error info.
    """
    import json
    import os
    from uuid import UUID as _UUID

    from sqlalchemy import select

    from .models.import_job import ImportJob
    from .models.document import Document
    from .services.document_service import set_scope_fks

    MAX_CONCURRENT_IMPORTS = get_agent_config().get_int("worker.max_concurrent_imports", 5)

    job_uuid = _UUID(job_id)
    temp_path: str | None = None

    try:
        async with async_session_maker() as db:
            # ----------------------------------------------------------------
            # 1. Load job and mark as processing (10%)
            # ----------------------------------------------------------------
            result = await db.execute(
                select(ImportJob).where(ImportJob.id == job_uuid)
            )
            job = result.scalar_one_or_none()
            if job is None:
                logger.warning("process_document_import: job %s not found", job_id)
                return {"status": "skipped", "reason": "not_found"}

            if job.status in ("completed", "failed"):
                logger.info("process_document_import: job %s already %s, skipping", job_id, job.status)
                return {"status": "skipped", "reason": job.status}

            temp_path = job.temp_file_path

            # ----------------------------------------------------------------
            # 1b. Global concurrency check (Redis-based)
            # ----------------------------------------------------------------
            _concurrency_acquired = False
            try:
                if redis_service.is_connected:
                    current_count = await redis_service.client.eval(
                        _INCR_WITH_TTL_LUA, 1, IMPORT_CONCURRENCY_KEY, IMPORT_CONCURRENCY_TTL
                    )

                    if current_count > MAX_CONCURRENT_IMPORTS:
                        # Over limit — decrement and re-enqueue with delay
                        await redis_service.client.decr(IMPORT_CONCURRENCY_KEY)

                        if _retry_count >= MAX_IMPORT_RETRIES:
                            logger.warning(
                                "Import job %s exceeded max retries (%d) due to concurrency limits",
                                job_id,
                                MAX_IMPORT_RETRIES,
                            )
                            # Mark job as failed
                            job.status = "failed"
                            job.error_message = (
                                "Import deferred too many times due to high server load. "
                                "Please try again later."
                            )
                            job.completed_at = utc_now()
                            await db.commit()
                            return {"status": "failed", "reason": "max_retries_exceeded"}

                        logger.info(
                            "Import concurrency: %d/%d active — re-enqueuing job %s with 15s delay (retry %d/%d)",
                            current_count - 1,
                            MAX_CONCURRENT_IMPORTS,
                            job_id,
                            _retry_count + 1,
                            MAX_IMPORT_RETRIES,
                        )
                        # M4: Reuse shared ARQ pool instead of creating a fresh one
                        from .services.arq_helper import get_arq_redis
                        _arq_pool = await get_arq_redis()
                        # M6: Exponential backoff with jitter to prevent thundering herd
                        import random as _rnd
                        _retry_delay = 15 * (2 ** _retry_count) + _rnd.uniform(0, 5)
                        await _arq_pool.enqueue_job(
                            "process_document_import",
                            job_id,
                            _retry_count + 1,
                            _job_id=f"import:{job_id}:retry:{_retry_count + 1}",
                            _defer_by=timedelta(seconds=_retry_delay),
                        )
                        return {"status": "deferred", "reason": "concurrency_limit"}
                    _concurrency_acquired = True
                    logger.info(
                        "Import concurrency: %d/%d active",
                        current_count,
                        MAX_CONCURRENT_IMPORTS,
                    )
            except Exception as redis_err:
                # Fail-open: if Redis is down, allow the import
                logger.warning(
                    "Redis concurrency check failed (fail-open): %s", redis_err
                )

            job.status = "processing"
            job.progress_pct = 10
            await db.commit()

            # ----------------------------------------------------------------
            # 2. Read the uploaded file
            # ----------------------------------------------------------------
            if not temp_path or not os.path.exists(temp_path):
                raise FileNotFoundError(
                    f"Temp file not found: {temp_path}"
                )

            # ----------------------------------------------------------------
            # 2b. Set restrictive permissions on temp file
            # ----------------------------------------------------------------
            os.chmod(temp_path, 0o600)

            # ----------------------------------------------------------------
            # 3. Convert document via Docling (40%)
            # ----------------------------------------------------------------
            from .ai.docling_service import DoclingService

            docling = DoclingService()

            conversion_result = await docling.process_file(
                temp_path, job.file_type
            )
            markdown_content = conversion_result.markdown
            extracted_images = conversion_result.images

            await _update_import_progress(db, job_uuid, 40)

            # ----------------------------------------------------------------
            # 4. Create Document with TipTap JSON content (50%)
            # ----------------------------------------------------------------
            tiptap_json = markdown_to_tiptap_json(markdown_content)

            # Title priority: user-provided title > document metadata title > filename stem
            user_title = getattr(job, "title", None)
            metadata_title = conversion_result.metadata.get("title_from_doc")
            base_name = os.path.splitext(job.file_name)[0]
            doc_title = (user_title or metadata_title or base_name)[:255]

            import re as _re

            # Strip markdown formatting for plain text version
            plain_text = _re.sub(r'[#*`\[\]()>|_~-]', '', markdown_content)
            plain_text = _re.sub(r'\n{3,}', '\n\n', plain_text).strip()

            doc = Document(
                title=doc_title,
                content_json=json.dumps(tiptap_json),
                content_markdown=markdown_content,
                content_plain=plain_text,
                created_by=job.user_id,
                folder_id=job.folder_id,
            )
            set_scope_fks(doc, job.scope, job.scope_id)
            db.add(doc)
            await db.flush()
            await db.refresh(doc)

            await _update_import_progress(db, job_uuid, 50)

            # ----------------------------------------------------------------
            # 5–6. Upload images and process through vision LLM (60→80%)
            # ----------------------------------------------------------------
            if extracted_images:
                try:
                    from .ai.image_understanding_service import (
                        ExtractedImage as IUSExtractedImage,
                        ImageUnderstandingService,
                    )
                    from .ai.provider_registry import ProviderRegistry
                    from .ai.embedding_service import EmbeddingService
                    from .ai.embedding_normalizer import EmbeddingNormalizer
                    from .ai.chunking_service import SemanticChunker
                    from .services.minio_service import minio_service

                    registry = ProviderRegistry()
                    normalizer = EmbeddingNormalizer()
                    chunker = SemanticChunker()
                    embedding_svc = EmbeddingService(
                        provider_registry=registry,
                        chunker=chunker,
                        normalizer=normalizer,
                        db=db,
                    )
                    image_svc = ImageUnderstandingService(
                        provider_registry=registry,
                        embedding_service=embedding_svc,
                        minio_service=minio_service,
                        db=db,
                    )

                    # Convert Docling ExtractedImage to ImageUnderstandingService ExtractedImage
                    ius_images: list[IUSExtractedImage] = []
                    for img in extracted_images:
                        fmt = img.image_format  # "png" or "jpg"
                        content_type = f"image/{'jpeg' if fmt == 'jpg' else fmt}"
                        filename = f"page{img.page_number or 0}_pos{img.position}.{fmt}"
                        ius_images.append(IUSExtractedImage(
                            data=img.image_bytes,
                            content_type=content_type,
                            filename=filename,
                            caption=img.caption or "",
                            page_number=img.page_number or 0,
                        ))

                    await _update_import_progress(db, job_uuid, 60)

                    scope_ids = {
                        "application_id": doc.application_id,
                        "project_id": doc.project_id,
                        "user_id": doc.user_id or job.user_id,
                    }

                    # Parse slide titles from markdown for image heading context
                    slide_titles = _parse_slide_titles(markdown_content)

                    await image_svc.process_imported_images(
                        images=ius_images,
                        document_id=doc.id,
                        scope_ids=scope_ids,
                        slide_titles=slide_titles if slide_titles else None,
                    )
                except Exception as img_err:
                    logger.warning(
                        "Image processing failed for job %s (non-fatal): %s",
                        job_id, img_err,
                    )
            else:
                await _update_import_progress(db, job_uuid, 60)

            await _update_import_progress(db, job_uuid, 80)

            # ----------------------------------------------------------------
            # 7. Trigger embed_document_job (90%)
            # ----------------------------------------------------------------
            try:
                from arq.connections import create_pool

                redis_pool = await create_pool(parse_redis_url(settings.redis_url))
                await redis_pool.enqueue_job(
                    "embed_document_job",
                    str(doc.id),
                    _job_id=f"embed:{doc.id}",
                    _defer_by=timedelta(seconds=120),
                )
                await redis_pool.aclose()
            except Exception as embed_err:
                logger.warning(
                    "Failed to enqueue embedding for doc %s (non-fatal): %s",
                    doc.id, embed_err,
                )

            await _update_import_progress(db, job_uuid, 90)

            # ----------------------------------------------------------------
            # 8. Finalize: status=completed, link document (100%)
            # ----------------------------------------------------------------
            job.status = "completed"
            job.progress_pct = 100
            job.document_id = doc.id
            job.completed_at = utc_now()
            job.temp_file_path = None
            await db.commit()

            # Broadcast IMPORT_COMPLETED via WebSocket
            try:
                await redis_service.publish(
                    f"user:{job.user_id}",
                    {
                        "type": "import_completed",
                        "data": {
                            "job_id": str(job.id),
                            "document_id": str(doc.id),
                            "title": doc.title,
                            "scope": job.scope,
                            "timestamp": utc_now().isoformat(),
                        },
                    },
                )
            except Exception as ws_err:
                logger.warning(
                    "Failed to broadcast IMPORT_COMPLETED for job %s: %s",
                    job_id, ws_err,
                )

            # Clean up temp file
            _cleanup_temp_file(temp_path)

            # Telemetry: log successful import
            try:
                from .ai.telemetry import AITelemetry

                _import_elapsed = int(
                    (job.completed_at - job.created_at).total_seconds() * 1000
                ) if job.completed_at and job.created_at else 0
                AITelemetry.log_import(
                    user_id=job.user_id,
                    file_type=job.file_type,
                    file_size=job.file_size or 0,
                    duration_ms=_import_elapsed,
                    success=True,
                )
            except Exception:
                pass  # Non-critical

            logger.info(
                "process_document_import: job %s completed — document %s created",
                job_id, doc.id,
            )

            # Decrement concurrency counter on success
            if _concurrency_acquired:
                try:
                    val = await redis_service.client.decr(IMPORT_CONCURRENCY_KEY)
                    if val < 0:
                        await redis_service.client.set(IMPORT_CONCURRENCY_KEY, 0)
                except Exception:
                    pass

            return {
                "status": "completed",
                "document_id": str(doc.id),
                "title": doc.title,
            }

    except Exception as e:
        # Map exception types to safe user-facing messages
        safe_messages = {
            "FileNotFoundError": "The uploaded file could not be found for processing.",
            "ImportError": "The document could not be converted. It may be corrupted or password-protected.",
            "TimeoutError": "The import took too long and was cancelled.",
        }
        error_type = type(e).__name__
        safe_msg = safe_messages.get(error_type, "An unexpected error occurred during import.")
        logger.error("process_document_import failed for job %s: %s", job_id, str(e), exc_info=True)

        # Mark job as failed
        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(ImportJob).where(ImportJob.id == job_uuid)
                )
                job = result.scalar_one_or_none()
                if job:
                    job.status = "failed"
                    job.error_message = safe_msg
                    job.completed_at = utc_now()
                    await db.commit()

                    # Broadcast IMPORT_FAILED
                    try:
                        await redis_service.publish(
                            f"user:{job.user_id}",
                            {
                                "type": "import_failed",
                                "data": {
                                    "job_id": str(job.id),
                                    "error_message": safe_msg,
                                    "file_name": job.file_name,
                                    "timestamp": utc_now().isoformat(),
                                },
                            },
                        )
                    except Exception:
                        pass
        except Exception as db_err:
            logger.error(
                "Failed to update job %s status to failed: %s",
                job_id, db_err,
            )

        # Telemetry: log failed import
        try:
            from .ai.telemetry import AITelemetry

            AITelemetry.log_import(
                user_id=str(job_uuid),
                file_type="unknown",
                file_size=0,
                duration_ms=0,
                success=False,
                error=error_type,
            )
        except Exception:
            pass  # Non-critical

        # Decrement concurrency counter on failure
        try:
            if redis_service.is_connected:
                val = await redis_service.client.decr(IMPORT_CONCURRENCY_KEY)
                if val < 0:
                    await redis_service.client.set(IMPORT_CONCURRENCY_KEY, 0)
        except Exception:
            pass

        # Clean up temp file on failure
        if temp_path:
            _cleanup_temp_file(temp_path)

        return {"status": "error", "error": type(e).__name__}


def _parse_slide_titles(markdown: str) -> dict[int, str]:
    """Parse ``## Slide N: Title`` headings from Docling-produced markdown.

    Returns a mapping of page_number -> slide_title for use as image heading
    context (Task 9.14).
    """
    import re

    titles: dict[int, str] = {}
    for m in re.finditer(r'^#{1,3}\s+(Slide\s+\d+.*)', markdown, re.MULTILINE):
        full = m.group(1).strip()
        # Extract page number and optional title after colon
        num_match = re.match(r'Slide\s+(\d+)(?::\s*(.*))?', full)
        if num_match:
            page = int(num_match.group(1))
            title = (num_match.group(2) or "").strip() or full
            titles[page] = title
    return titles


def _cleanup_temp_file(path: str | None) -> None:
    """Safely remove a temporary file if it exists."""
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


# =============================================================================
# Checkpoint Cleanup Job (DB-001)
# =============================================================================


async def cleanup_checkpoints(ctx: dict[str, Any]) -> None:
    """Delete checkpoint data for threads not seen in 48 hours.

    The LangGraph checkpoint tables (checkpoints, checkpoint_blobs,
    checkpoint_writes) have no ``created_at`` column.  Instead we identify
    stale threads by finding those whose most recent ``checkpoint_id``
    (a ULID-style string that sorts chronologically) is older than the
    cutoff.  Because checkpoint_id encodes a timestamp we approximate the
    age by comparing against a synthetic cutoff ID.

    As a simpler, safer approach we delete threads that have not been
    touched by the application's ``ai_chat`` router in the last 48 h.
    The chat router stores ``chat:thread:<thread_id>`` keys in Redis
    with a TTL.  Any thread_id *not* present in Redis is considered
    expired and eligible for cleanup.

    If Redis is unavailable we fall back to a conservative strategy:
    delete checkpoint data for threads older than 48 hours using the
    ``metadata`` JSONB column (which contains a ``created_at`` field
    written by LangGraph when ``config["metadata"]`` is set).

    Runs daily at 03:00 via ARQ cron.
    """
    logger.info("Starting checkpoint cleanup job")
    try:
        from urllib.parse import quote_plus

        import asyncpg

        pg_uri = (
            f"postgresql://{settings.db_user}:{quote_plus(settings.db_password)}"
            f"@{settings.db_server}:{settings.db_port}/{settings.db_name}"
        )
        conn = await asyncpg.connect(pg_uri)
        try:
            # Safety check: verify tables exist before attempting cleanup
            table_check = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'checkpoints')"
            )
            if not table_check:
                logger.info("Checkpoint cleanup skipped: checkpoints table does not exist")
                return

            # Identify stale thread_ids via the metadata JSONB column.
            # LangGraph stores a 'ts' key when config['metadata'] is set.
            # Threads without 'ts' metadata are treated as older than 49h
            # so they get cleaned up conservatively.  Each DELETE targets
            # threads whose *newest* checkpoint has ts < 48h ago.

            # QE-R2-002: Wrap all three DELETEs in a transaction for atomicity
            async with conn.transaction():
                deleted_writes = await conn.execute("""
                    DELETE FROM checkpoint_writes
                    WHERE thread_id IN (
                        SELECT c.thread_id
                        FROM checkpoints c
                        WHERE NOT EXISTS (
                            SELECT 1 FROM checkpoints c2
                            WHERE c2.thread_id = c.thread_id
                            AND c2.checkpoint_id > c.checkpoint_id
                        )
                        GROUP BY c.thread_id
                        HAVING MAX(
                            CASE
                                WHEN c.metadata->>'ts' IS NOT NULL
                                THEN to_timestamp((c.metadata->>'ts')::double precision)
                                ELSE NOW() - INTERVAL '49 hours'
                            END
                        ) < NOW() - INTERVAL '48 hours'
                    )
                """)

                deleted_blobs = await conn.execute("""
                    DELETE FROM checkpoint_blobs
                    WHERE thread_id IN (
                        SELECT c.thread_id
                        FROM checkpoints c
                        WHERE NOT EXISTS (
                            SELECT 1 FROM checkpoints c2
                            WHERE c2.thread_id = c.thread_id
                            AND c2.checkpoint_id > c.checkpoint_id
                        )
                        GROUP BY c.thread_id
                        HAVING MAX(
                            CASE
                                WHEN c.metadata->>'ts' IS NOT NULL
                                THEN to_timestamp((c.metadata->>'ts')::double precision)
                                ELSE NOW() - INTERVAL '49 hours'
                            END
                        ) < NOW() - INTERVAL '48 hours'
                    )
                """)

                deleted_cps = await conn.execute("""
                    DELETE FROM checkpoints
                    WHERE thread_id IN (
                        SELECT c.thread_id
                        FROM checkpoints c
                        GROUP BY c.thread_id
                        HAVING MAX(
                            CASE
                                WHEN c.metadata->>'ts' IS NOT NULL
                                THEN to_timestamp((c.metadata->>'ts')::double precision)
                                ELSE NOW() - INTERVAL '49 hours'
                            END
                        ) < NOW() - INTERVAL '48 hours'
                    )
                """)

            logger.info(
                "Checkpoint cleanup complete: writes=%s, blobs=%s, checkpoints=%s",
                deleted_writes,
                deleted_blobs,
                deleted_cps,
            )
        finally:
            await conn.close()
    except Exception:
        logger.warning("Checkpoint cleanup failed", exc_info=True)


# =============================================================================
# Startup/Shutdown Hooks
# =============================================================================

async def startup(ctx: dict[str, Any]) -> None:
    """Initialize resources when worker starts."""
    logger.info("ARQ worker starting up...")

    # Connect to Redis (for presence cleanup jobs and consistency checker)
    try:
        await redis_service.connect()
        logger.info("Redis connected for ARQ worker")
    except Exception as e:
        logger.warning(f"Redis connection failed in ARQ worker: {e}")

    # Initialize Meilisearch (for search index consistency checker)
    try:
        from .services.search_service import init_meilisearch
        await init_meilisearch()
        logger.info("Meilisearch initialized for ARQ worker")
    except Exception as e:
        logger.warning(f"Meilisearch init failed in ARQ worker: {e}")

    # Crash recovery: reset stuck 'syncing' documents back to 'stale'
    try:
        from sqlalchemy import update as sa_update
        async with async_session_maker() as db:
            result = await db.execute(
                sa_update(Document)
                .where(Document.embedding_status == "syncing")
                .values(embedding_status="stale", updated_at=utc_now())
            )
            if result.rowcount > 0:
                logger.info("Crash recovery: reset %d stuck syncing documents to stale", result.rowcount)
            await db.commit()
    except Exception as e:
        logger.warning("Crash recovery (documents) failed: %s", e)

    # Crash recovery: reset stuck 'syncing' folder files back to 'stale'
    try:
        from sqlalchemy import update as sa_update
        async with async_session_maker() as db:
            result = await db.execute(
                sa_update(FolderFile)
                .where(FolderFile.embedding_status == "syncing")
                .values(embedding_status="stale", updated_at=utc_now())
            )
            if result.rowcount > 0:
                logger.info("Crash recovery: reset %d stuck syncing files to stale", result.rowcount)
            await db.commit()
    except Exception as e:
        logger.warning("Crash recovery (files) failed: %s", e)


async def shutdown(ctx: dict[str, Any]) -> None:
    """Cleanup resources when worker stops."""
    logger.info("ARQ worker shutting down...")

    await redis_service.disconnect()
    logger.info("Redis disconnected")


# =============================================================================
# Schedule Parsing
# =============================================================================

def parse_schedule_set(value: str) -> set[int]:
    """
    Parse a comma-separated string of integers into a set.

    Examples:
        "0,12" -> {0, 12}
        "0,15,30,45" -> {0, 15, 30, 45}
    """
    return {int(x.strip()) for x in value.split(",") if x.strip()}


def get_archive_hours() -> set[int] | None:
    """Get archive job hours from settings. Returns None if using minutes instead."""
    if settings.arq_archive_hours.strip():
        return parse_schedule_set(settings.arq_archive_hours)
    return None


def get_archive_minutes() -> set[int] | None:
    """Get archive job minutes from settings. Returns None if using hours instead."""
    if settings.arq_archive_minutes.strip():
        return parse_schedule_set(settings.arq_archive_minutes)
    return None


def get_presence_cleanup_seconds() -> set[int]:
    """Get presence cleanup seconds from settings."""
    return parse_schedule_set(settings.arq_presence_cleanup_seconds)


async def generate_session_title(ctx: dict[str, Any], session_id: str, first_message: str) -> dict[str, Any]:
    """Generate a concise LLM-powered title for a chat session."""
    from sqlalchemy import select

    from .ai.provider_registry import ProviderRegistry
    from .models.chat_session import ChatSession

    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return {"status": "skipped", "reason": "session deleted"}

        registry = ProviderRegistry()
        await registry.load_from_db(db)
        llm = registry.get_chat_model()
        if not llm:
            return {"status": "skipped", "reason": "no chat model configured"}

        from langchain_core.messages import HumanMessage, SystemMessage

        response = await llm.ainvoke([
            SystemMessage(
                content="Generate a concise 3-6 word title for this conversation. Reply with only the title, no quotes."
            ),
            HumanMessage(content=first_message[:500]),
        ])
        new_title = str(response.content).strip()[:200]
        if new_title:
            session.title = new_title
            await db.commit()
        return {"status": "success", "title": new_title}


async def cleanup_stale_processing_files(ctx: dict[str, Any]) -> dict[str, Any]:
    """Reset files stuck in 'processing' for >10 minutes.

    Standalone cron job to prevent livelock from per-job reapers resetting
    other workers' active jobs. Runs every 5 minutes.
    """
    from sqlalchemy import update as sa_update

    try:
        async with async_session_maker() as reaper_db:
            _cfg = get_agent_config()
            stale_minutes = _cfg.get_int("worker.stale_processing_cutoff_minutes", 10)
            stale_cutoff = utc_now() - timedelta(minutes=stale_minutes)
            # F15: Use RETURNING clause to get reset IDs atomically (no post-commit SELECT)
            stale_result = await reaper_db.execute(
                sa_update(FolderFile)
                .where(
                    FolderFile.extraction_status == "processing",
                    FolderFile.updated_at < stale_cutoff,
                    FolderFile.deleted_at.is_(None),
                )
                .values(extraction_status="pending", updated_at=utc_now())
                .returning(FolderFile.id)
            )
            reset_ids = [row[0] for row in stale_result.all()]
            await reaper_db.commit()

            if reset_ids:
                logger.warning(
                    "cleanup_stale_processing_files: Reset %d stale 'processing' files back to 'pending'",
                    len(reset_ids),
                )
                try:
                    from .services.arq_helper import get_arq_redis

                    arq_redis = await get_arq_redis()
                    for fid in reset_ids:
                        await arq_redis.enqueue_job(
                            "extract_and_embed_file_job",
                            str(fid),
                            _job_id=f"extract_file:{fid}",
                        )
                except Exception as enq_err:
                    logger.warning("Failed to re-enqueue reset files: %s", enq_err)

            return {"status": "success", "reset_count": len(reset_ids)}
    except Exception as reaper_err:
        logger.error("cleanup_stale_processing_files failed: %s", reaper_err, exc_info=True)
        return {"status": "error", "error": str(type(reaper_err).__name__)}


def build_archive_cron():
    """Build archive cron job based on config (hours or minutes)."""
    hours = get_archive_hours()
    minutes = get_archive_minutes()

    if minutes:
        # Run at specific minutes (for testing, e.g., every 2 mins)
        return cron(run_archive_jobs, minute=minutes, second=0)
    elif hours:
        # Run at specific hours (production default)
        return cron(run_archive_jobs, hour=hours, minute=0, second=0)
    else:
        # Fallback: run at midnight
        return cron(run_archive_jobs, hour={0}, minute=0, second=0)


# =============================================================================
# Worker Settings
# =============================================================================

class WorkerSettings:
    """ARQ worker configuration."""

    # Redis connection
    redis_settings = parse_redis_url(settings.redis_url)

    # Job functions that can be called via arq.enqueue_job()
    functions = [
        run_archive_jobs,
        cleanup_stale_presence,
        check_search_index_consistency,
        embed_document_job,
        extract_and_embed_file_job,
        batch_embed_stale_documents,
        process_document_import,
        cleanup_checkpoints,
        generate_session_title,
        cleanup_stale_processing_files,
    ]

    # Scheduled cron jobs (configured via .env)
    # ARQ_ARCHIVE_HOURS: comma-separated hours (default "0,12" = midnight and noon)
    # ARQ_ARCHIVE_MINUTES: comma-separated minutes (used if ARQ_ARCHIVE_HOURS is empty)
    # ARQ_PRESENCE_CLEANUP_SECONDS: comma-separated seconds (default "0,30" = every 30s)
    cron_jobs = [
        build_archive_cron(),
        cron(cleanup_stale_presence, second=get_presence_cleanup_seconds()),
        # Search index consistency checker: every 5 minutes (at minute 0,5,10,...,55)
        cron(check_search_index_consistency, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, second=0),
        # Nightly batch embed stale documents: 2:00 AM daily
        cron(batch_embed_stale_documents, hour={2}, minute=0, second=0),
        # Daily checkpoint cleanup: 3:00 AM (DB-001 — prevent unbounded table growth)
        cron(cleanup_checkpoints, hour={3}, minute=0, run_at_startup=False),
        # Stale processing file reaper: every 5 minutes (replaces per-job reaper)
        cron(cleanup_stale_processing_files, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, second=30),
    ]

    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Worker behavior
    max_jobs = 10  # Max concurrent jobs
    job_timeout = 300  # 5 minutes max per job
    keep_result = 3600  # Keep results for 1 hour

    # Health check
    health_check_interval = 30

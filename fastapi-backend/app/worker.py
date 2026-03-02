"""
ARQ Worker Configuration

Background job processing with Redis-backed task queue.
Handles scheduled jobs that were previously run via asyncio loops.

Run with:
    arq app.worker.WorkerSettings
"""

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

ARCHIVE_AFTER_DAYS = 7


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


async def archive_stale_done_tasks(db) -> int:
    """Archive all tasks that have been in Done status for 7+ days."""
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession
    from .models.project_task_status_agg import ProjectTaskStatusAgg

    now = utc_now()
    cutoff_date = now - timedelta(days=ARCHIVE_AFTER_DAYS)

    # Find all "Done" status IDs
    done_status_result = await db.execute(
        select(TaskStatus.id).where(TaskStatus.name == StatusName.DONE)
    )
    done_status_ids = [row[0] for row in done_status_result.all()]

    if not done_status_ids:
        return 0

    # Find tasks to archive
    tasks_to_archive_query = (
        select(Task.id, Task.task_key, Task.project_id, Task.completed_at)
        .where(
            Task.task_status_id.in_(done_status_ids),
            Task.archived_at.is_(None),
            Task.completed_at.isnot(None),
            Task.completed_at <= cutoff_date,
        )
    )

    result = await db.execute(tasks_to_archive_query)
    tasks_to_archive = result.all()

    if not tasks_to_archive:
        logger.debug("No tasks eligible for archiving")
        return 0

    task_ids = [row[0] for row in tasks_to_archive]
    affected_project_ids = set(row[2] for row in tasks_to_archive)

    # Log each task being archived
    for task_id, task_key, project_id, completed_at in tasks_to_archive:
        days_since_done = (now - completed_at).days if completed_at else 0
        logger.info(f"  Archiving task: {task_key} (done {days_since_done} days ago)")

    # Archive the tasks
    await db.execute(
        update(Task)
        .where(Task.id.in_(task_ids))
        .values(archived_at=now)
    )

    # Update aggregations for affected projects
    for project_id in affected_project_ids:
        await _recalculate_project_aggregation(db, project_id)

    return len(task_ids)


async def archive_eligible_projects(db) -> int:
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


async def _recalculate_project_aggregation(db, project_id) -> None:
    """Recalculate project aggregation after archiving tasks."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from .models.project_task_status_agg import ProjectTaskStatusAgg

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

    # Get non-archived tasks
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.task_status))
        .where(
            Task.project_id == project_id,
            Task.archived_at.is_(None),
        )
    )
    tasks = result.scalars().all()

    # Recalculate aggregation and get derived status name
    derived_status_name = recalculate_aggregation_from_tasks(agg, tasks)

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
            # Batch all zremrangebyscore calls in a single pipeline
            pipe = redis_service.client.pipeline(transaction=False)
            room_ids = []
            for key in keys:
                room_id = key.replace(PRESENCE_PREFIX, "")
                room_ids.append(room_id)
                pipe.zremrangebyscore(
                    f"{PRESENCE_PREFIX}{room_id}",
                    min="-inf",
                    max=cutoff,
                )
            results = await pipe.execute()
            for room_id, removed in zip(room_ids, results):
                if removed > 0:
                    logger.debug(f"Cleaned {removed} stale entries from room {room_id}")
                    total_removed += removed
    except Exception as e:
        logger.error(f"Redis presence cleanup error: {e}")

    return {"removed": total_removed}


# =============================================================================
# Embedding Jobs
# =============================================================================


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

    doc_uuid = _UUID(document_id)

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

            if not doc.content_json:
                logger.debug("embed_document_job: document %s has no content", document_id)
                return {"status": "skipped", "reason": "no_content"}

            content = json.loads(doc.content_json)
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

            embed_result = await service.embed_document(
                document_id=doc_uuid,
                content_json=content,
                title=doc.title,
                scope_ids=scope_ids,
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

            # Broadcast EMBEDDING_UPDATED to the scope room the user is in
            # (worker runs in separate process, so publish to ws:broadcast directly)
            try:
                ws_payload = {
                    "type": "embedding_updated",
                    "data": {
                        "document_id": document_id,
                        "chunk_count": total_chunks,
                        "timestamp": utc_now().isoformat(),
                    },
                }
                # Determine the scope room — user is in application or user room
                if doc.application_id:
                    room_id = f"application:{doc.application_id}"
                elif doc.project_id:
                    # Project-scoped docs: resolve parent application
                    from .models.project import Project
                    proj = await db.get(Project, doc.project_id)
                    room_id = f"application:{proj.application_id}" if proj and proj.application_id else None
                elif doc.user_id:
                    room_id = f"user:{doc.user_id}"
                else:
                    room_id = None

                if room_id:
                    await redis_service.publish(
                        "ws:broadcast",
                        {"room_id": room_id, "message": ws_payload},
                    )
            except Exception as ws_err:
                logger.warning(
                    "Failed to broadcast EMBEDDING_UPDATED for document %s: %s",
                    document_id, ws_err,
                )

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
        # Return type name only (not str(e)) to avoid leaking sensitive context
        return {"status": "error", "error": type(e).__name__}


# =============================================================================
# Nightly Batch Embedding Job (Phase 9.6)
# =============================================================================

NIGHTLY_EMBED_BATCH_SIZE = 10
NIGHTLY_EMBED_BATCH_DELAY_S = 5
MAX_NIGHTLY_EMBED = 500


async def batch_embed_stale_documents(ctx: dict[str, Any]) -> dict[str, Any]:
    """Nightly cron job: embed all documents with stale or missing embeddings.

    Queries documents where ``embedding_updated_at IS NULL`` or
    ``embedding_updated_at < updated_at``, then enqueues embed jobs
    in batches with spacing to avoid overwhelming the embedding API.

    Returns:
        dict with count of documents queued.
    """
    import asyncio

    from sqlalchemy import select, or_

    queued = 0
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Document.id).where(
                    Document.deleted_at.is_(None),
                    or_(
                        Document.embedding_updated_at.is_(None),
                        Document.embedding_updated_at < Document.updated_at,
                    ),
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

MAX_CONCURRENT_IMPORTS = 5
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
                        from arq.connections import create_pool
                        redis_pool = await create_pool(parse_redis_url(settings.redis_url))
                        await redis_pool.enqueue_job(
                            "process_document_import",
                            job_id,
                            _retry_count + 1,
                            _job_id=f"import:{job_id}:retry:{_retry_count + 1}",
                            _defer_by=timedelta(seconds=15),
                        )
                        await redis_pool.aclose()
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
        batch_embed_stale_documents,
        process_document_import,
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

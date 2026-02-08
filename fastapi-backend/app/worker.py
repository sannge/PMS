"""
ARQ Worker Configuration

Background job processing with Redis-backed task queue.
Handles scheduled jobs that were previously run via asyncio loops.

Run with:
    arq app.worker.WorkerSettings
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from .config import settings
from .database import async_session_maker
from .models.project import Project
from .models.task import Task
from .models.task_status import StatusName, TaskStatus
from .services.redis_service import redis_service
from .services.status_derivation_service import recalculate_aggregation_from_tasks

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
        "run_at": datetime.utcnow().isoformat(),
    }


async def archive_stale_done_tasks(db) -> int:
    """Archive all tasks that have been in Done status for 7+ days."""
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession
    from .models.project_task_status_agg import ProjectTaskStatusAgg

    now = datetime.utcnow()
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

    now = datetime.utcnow()

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
# Startup/Shutdown Hooks
# =============================================================================

async def startup(ctx: dict[str, Any]) -> None:
    """Initialize resources when worker starts."""
    logger.info("ARQ worker starting up...")

    # Connect to Redis (for presence cleanup jobs)
    try:
        await redis_service.connect()
        logger.info("Redis connected for ARQ worker")
    except Exception as e:
        logger.warning(f"Redis connection failed in ARQ worker: {e}")


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
    ]

    # Scheduled cron jobs (configured via .env)
    # ARQ_ARCHIVE_HOURS: comma-separated hours (default "0,12" = midnight and noon)
    # ARQ_ARCHIVE_MINUTES: comma-separated minutes (used if ARQ_ARCHIVE_HOURS is empty)
    # ARQ_PRESENCE_CLEANUP_SECONDS: comma-separated seconds (default "0,30" = every 30s)
    cron_jobs = [
        build_archive_cron(),
        cron(cleanup_stale_presence, second=get_presence_cleanup_seconds()),
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

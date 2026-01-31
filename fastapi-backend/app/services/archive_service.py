"""
Background Archive Service

Simple asyncio-based service that runs archive jobs twice daily.
Archives:
- Tasks in Done status for 7+ days
- Projects where all tasks are archived

Uses the same pattern as presence.py - a simple asyncio loop.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import async_session_maker
from ..models.project import Project
from ..models.project_task_status_agg import ProjectTaskStatusAgg
from ..models.task import Task
from ..models.task_status import StatusName, TaskStatus
from ..services.status_derivation_service import recalculate_aggregation_from_tasks

logger = logging.getLogger(__name__)

# Days after which a Done task is archived
ARCHIVE_AFTER_DAYS = 7

# Run archive jobs every 12 hours (twice daily)
# In test mode (ARCHIVE_TEST_MODE=true in .env): run every 2 minutes for easier testing
ARCHIVE_INTERVAL_SECONDS = 2 * 60 if settings.archive_test_mode else 12 * 60 * 60  # 120s or 43200s


class ArchiveService:
    """
    Simple asyncio-based archive service.

    Runs a background loop that archives stale tasks and projects
    every 12 hours (twice daily).
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the background archive loop."""
        self._running = True
        self._task = asyncio.create_task(self._archive_loop())
        interval_desc = "2 minutes (TEST MODE)" if settings.archive_test_mode else "12 hours"
        logger.info(f"Archive service started (runs every {interval_desc})")

    async def stop(self) -> None:
        """Stop the archive service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Archive service stopped")

    @property
    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running

    async def _archive_loop(self) -> None:
        """Background loop that runs archive jobs every 12 hours."""
        # Run immediately on startup, then every 12 hours
        while self._running:
            try:
                await self._run_archive_jobs()
            except Exception as e:
                logger.error(f"Archive job error: {e}", exc_info=True)

            # Sleep for 12 hours
            try:
                await asyncio.sleep(ARCHIVE_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def _run_archive_jobs(self) -> None:
        """Run both archive jobs."""
        logger.info("Running scheduled archive jobs...")

        try:
            async with async_session_maker() as db:
                # Archive stale done tasks
                tasks_archived = await archive_stale_done_tasks_all_projects(db)

                # Archive projects with all tasks archived
                projects_archived = await archive_eligible_projects_all_applications(db)

                await db.commit()

                logger.info(
                    f"Archive jobs complete: {tasks_archived} tasks, {projects_archived} projects archived"
                )
        except Exception as e:
            logger.error(f"Error running archive jobs: {e}", exc_info=True)

    async def run_now(self) -> dict:
        """
        Manually trigger archive jobs immediately.

        Returns:
            dict: Summary of archived counts
        """
        logger.info("Manually triggering archive jobs...")

        tasks_archived = 0
        projects_archived = 0

        try:
            async with async_session_maker() as db:
                tasks_archived = await archive_stale_done_tasks_all_projects(db)
                projects_archived = await archive_eligible_projects_all_applications(db)
                await db.commit()
        except Exception as e:
            logger.error(f"Error in manual archive run: {e}", exc_info=True)

        return {
            "tasks_archived": tasks_archived,
            "projects_archived": projects_archived,
            "run_at": datetime.utcnow().isoformat(),
        }


# ============================================================================
# Archive Functions
# ============================================================================


async def archive_stale_done_tasks_all_projects(db: AsyncSession) -> int:
    """
    Archive all tasks that have been in Done status for 7+ days.

    Args:
        db: Database session

    Returns:
        int: Number of tasks archived
    """
    now = datetime.utcnow()
    cutoff_date = now - timedelta(days=ARCHIVE_AFTER_DAYS)

    # Find all "Done" status IDs
    done_status_result = await db.execute(
        select(TaskStatus.id).where(TaskStatus.name == StatusName.DONE)
    )
    done_status_ids = [row[0] for row in done_status_result.all()]

    if not done_status_ids:
        return 0

    # Find tasks to archive (include task_key for logging)
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


async def archive_eligible_projects_all_applications(db: AsyncSession) -> int:
    """
    Archive projects where all tasks are archived.

    Args:
        db: Database session

    Returns:
        int: Number of projects archived
    """
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

    # Find projects to archive (include name and key for logging)
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


async def _recalculate_project_aggregation(db: AsyncSession, project_id: UUID) -> None:
    """Recalculate project aggregation after archiving tasks."""
    from sqlalchemy.orm import selectinload

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


# Global instance
archive_service = ArchiveService()

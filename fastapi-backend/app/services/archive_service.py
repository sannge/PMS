"""
Archive Service

Provides manual archive trigger for admin endpoint.
Scheduled archiving is handled by ARQ worker (see app/worker.py).

Archives:
- Tasks in Done status for 7+ days
- Projects where all tasks are archived
"""

import logging
from datetime import datetime

from ..database import async_session_maker

logger = logging.getLogger(__name__)


class ArchiveService:
    """
    Archive service for manual triggers.

    Scheduled archiving is handled by ARQ worker cron jobs.
    This class provides a manual trigger for the admin endpoint.
    """

    async def run_now(self) -> dict:
        """
        Manually trigger archive jobs immediately.

        Returns:
            dict: Summary of archived counts
        """
        # Import here to avoid circular imports
        from ..worker import archive_stale_done_tasks, archive_eligible_projects

        logger.info("Manually triggering archive jobs...")

        tasks_archived = 0
        projects_archived = 0

        try:
            async with async_session_maker() as db:
                tasks_archived = await archive_stale_done_tasks(db)
                projects_archived = await archive_eligible_projects(db)
                await db.commit()
        except Exception as e:
            logger.error(f"Error in manual archive run: {e}", exc_info=True)

        return {
            "tasks_archived": tasks_archived,
            "projects_archived": projects_archived,
            "run_at": datetime.utcnow().isoformat(),
        }


# Global instance
archive_service = ArchiveService()

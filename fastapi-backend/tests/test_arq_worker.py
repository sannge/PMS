"""Tests for ARQ worker jobs."""

import time
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Application, Project, Task, User
from app.models.task_status import TaskStatus, StatusName, STATUS_CATEGORY_MAP
from app.services.redis_service import redis_service
from app.worker import (
    archive_stale_done_tasks,
    archive_eligible_projects,
    cleanup_stale_presence,
    run_archive_jobs,
    ARCHIVE_AFTER_DAYS,
    PRESENCE_PREFIX,
)


# =============================================================================
# Fixtures
# =============================================================================


def get_test_password_hash(password: str) -> str:
    """Generate a password hash for testing."""
    import bcrypt
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


@pytest_asyncio.fixture
async def arq_test_user(db_session: AsyncSession) -> User:
    """Create a test user for ARQ tests."""
    user = User(
        id=uuid4(),
        email=f"arq_test_{uuid4().hex[:8]}@example.com",
        password_hash=get_test_password_hash("TestPassword123!"),
        display_name="ARQ Test User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def arq_test_application(db_session: AsyncSession, arq_test_user: User) -> Application:
    """Create a test application for ARQ tests."""
    application = Application(
        id=uuid4(),
        name=f"ARQ Test Application {uuid4().hex[:8]}",
        description="A test application for ARQ tests",
        owner_id=arq_test_user.id,
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest_asyncio.fixture
async def arq_test_project(db_session: AsyncSession, arq_test_application: Application) -> Project:
    """Create a test project with statuses for ARQ tests."""
    from datetime import date
    project = Project(
        id=uuid4(),
        application_id=arq_test_application.id,
        name=f"ARQ Test Project {uuid4().hex[:8]}",
        key=f"ARQ{uuid4().hex[:4].upper()}",
        description="A test project for ARQ tests",
        project_type="kanban",
        due_date=date.today(),
    )
    db_session.add(project)
    await db_session.flush()

    # Create default statuses
    statuses = TaskStatus.create_default_statuses(project.id)
    for status in statuses:
        db_session.add(status)

    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def done_status(db_session: AsyncSession, arq_test_project: Project) -> TaskStatus:
    """Get the Done status for the test project."""
    result = await db_session.execute(
        select(TaskStatus).where(
            TaskStatus.project_id == arq_test_project.id,
            TaskStatus.name == StatusName.DONE.value,
        )
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def todo_status(db_session: AsyncSession, arq_test_project: Project) -> TaskStatus:
    """Get the Todo status for the test project."""
    result = await db_session.execute(
        select(TaskStatus).where(
            TaskStatus.project_id == arq_test_project.id,
            TaskStatus.name == StatusName.TODO.value,
        )
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def archivable_task(
    db_session: AsyncSession,
    arq_test_project: Project,
    arq_test_user: User,
    done_status: TaskStatus,
) -> Task:
    """Create a task eligible for archiving (done 8+ days ago)."""
    task = Task(
        id=uuid4(),
        project_id=arq_test_project.id,
        task_key=f"ARQ-{uuid4().hex[:4].upper()}",
        title="Archivable Task",
        description="This task should be archived",
        task_type="story",
        task_status_id=done_status.id,
        priority="medium",
        reporter_id=arq_test_user.id,
        completed_at=datetime.utcnow() - timedelta(days=ARCHIVE_AFTER_DAYS + 1),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest_asyncio.fixture
async def recent_done_task(
    db_session: AsyncSession,
    arq_test_project: Project,
    arq_test_user: User,
    done_status: TaskStatus,
) -> Task:
    """Create a task done recently (should NOT be archived)."""
    task = Task(
        id=uuid4(),
        project_id=arq_test_project.id,
        task_key=f"ARQ-{uuid4().hex[:4].upper()}",
        title="Recent Done Task",
        description="This task was done recently",
        task_type="story",
        task_status_id=done_status.id,
        priority="medium",
        reporter_id=arq_test_user.id,
        completed_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest_asyncio.fixture
async def active_task(
    db_session: AsyncSession,
    arq_test_project: Project,
    arq_test_user: User,
    todo_status: TaskStatus,
) -> Task:
    """Create an active (non-done) task."""
    task = Task(
        id=uuid4(),
        project_id=arq_test_project.id,
        task_key=f"ARQ-{uuid4().hex[:4].upper()}",
        title="Active Task",
        description="This task is still in progress",
        task_type="story",
        task_status_id=todo_status.id,
        priority="medium",
        reporter_id=arq_test_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest_asyncio.fixture
async def redis_connected():
    """Ensure Redis is connected for presence tests."""
    # Always reconnect to avoid stale connection issues
    if redis_service.is_connected:
        await redis_service.disconnect()
    await redis_service.connect()
    yield redis_service
    await redis_service.disconnect()


# =============================================================================
# Archive Task Tests
# =============================================================================


class TestArchiveStaledoneTasks:
    """Tests for archive_stale_done_tasks function."""

    @pytest.mark.asyncio
    async def test_archives_old_done_task(
        self, db_session: AsyncSession, archivable_task: Task
    ):
        """Task done 8+ days ago should be archived."""
        # Verify task is not archived initially
        assert archivable_task.archived_at is None

        # Run archive
        count = await archive_stale_done_tasks(db_session)
        await db_session.commit()

        # Verify task was archived
        assert count >= 1
        await db_session.refresh(archivable_task)
        assert archivable_task.archived_at is not None

    @pytest.mark.asyncio
    async def test_does_not_archive_recent_done_task(
        self, db_session: AsyncSession, recent_done_task: Task
    ):
        """Task done less than 7 days ago should NOT be archived."""
        task_id = recent_done_task.id

        # Run archive
        await archive_stale_done_tasks(db_session)
        await db_session.commit()

        # Verify task was NOT archived
        await db_session.refresh(recent_done_task)
        assert recent_done_task.archived_at is None

    @pytest.mark.asyncio
    async def test_does_not_archive_active_task(
        self, db_session: AsyncSession, active_task: Task
    ):
        """Active (non-done) task should NOT be archived."""
        # Run archive
        await archive_stale_done_tasks(db_session)
        await db_session.commit()

        # Verify task was NOT archived
        await db_session.refresh(active_task)
        assert active_task.archived_at is None

    @pytest.mark.asyncio
    async def test_archive_is_idempotent(
        self, db_session: AsyncSession, archivable_task: Task
    ):
        """Running archive twice should not cause errors."""
        # First run
        count1 = await archive_stale_done_tasks(db_session)
        await db_session.commit()
        assert count1 >= 1

        # Second run - should find nothing to archive
        count2 = await archive_stale_done_tasks(db_session)
        await db_session.commit()

        # Already archived tasks should not be re-archived
        # (count2 should not include the already archived task)
        await db_session.refresh(archivable_task)
        assert archivable_task.archived_at is not None


class TestArchiveEligibleProjects:
    """Tests for archive_eligible_projects function."""

    @pytest.mark.asyncio
    async def test_archives_project_with_all_tasks_archived(
        self,
        db_session: AsyncSession,
        arq_test_project: Project,
        archivable_task: Task,
    ):
        """Project with all tasks archived should be archived."""
        # First archive the task
        await archive_stale_done_tasks(db_session)
        await db_session.commit()

        # Verify task is archived
        await db_session.refresh(archivable_task)
        assert archivable_task.archived_at is not None

        # Now archive eligible projects
        count = await archive_eligible_projects(db_session)
        await db_session.commit()

        # Verify project was archived
        assert count >= 1
        await db_session.refresh(arq_test_project)
        assert arq_test_project.archived_at is not None

    @pytest.mark.asyncio
    async def test_does_not_archive_project_with_active_tasks(
        self,
        db_session: AsyncSession,
        arq_test_project: Project,
        active_task: Task,
    ):
        """Project with active tasks should NOT be archived."""
        # Run archive
        count = await archive_eligible_projects(db_session)
        await db_session.commit()

        # Verify project was NOT archived
        await db_session.refresh(arq_test_project)
        assert arq_test_project.archived_at is None


class TestRunArchiveJobs:
    """Tests for the combined run_archive_jobs function."""

    @pytest.mark.asyncio
    async def test_run_archive_jobs_returns_counts(
        self, db_session: AsyncSession, archivable_task: Task
    ):
        """run_archive_jobs should return counts of archived items."""
        # Use empty context dict like ARQ does
        ctx = {}

        result = await run_archive_jobs(ctx)

        assert "tasks_archived" in result
        assert "projects_archived" in result
        assert "run_at" in result
        assert result["tasks_archived"] >= 1


# =============================================================================
# Presence Cleanup Tests
# =============================================================================


class TestCleanupStalePresence:
    """Tests for cleanup_stale_presence function."""

    @pytest.mark.asyncio
    async def test_removes_stale_presence_entries(self, redis_connected):
        """Stale presence entries should be removed."""
        room_id = f"test_room_{uuid4().hex[:8]}"
        user_id = f"test_user_{uuid4().hex[:8]}"

        # Add a stale presence entry (old timestamp)
        stale_timestamp = time.time() - 60  # 60 seconds ago (TTL is 45s)
        await redis_service.client.zadd(
            f"{PRESENCE_PREFIX}{room_id}",
            {user_id: stale_timestamp}
        )

        # Verify entry exists
        score = await redis_service.client.zscore(
            f"{PRESENCE_PREFIX}{room_id}", user_id
        )
        assert score is not None

        # Run cleanup
        ctx = {}
        result = await cleanup_stale_presence(ctx)

        # Verify entry was removed
        score = await redis_service.client.zscore(
            f"{PRESENCE_PREFIX}{room_id}", user_id
        )
        assert score is None
        assert result["removed"] >= 1

        # Cleanup
        await redis_service.client.delete(f"{PRESENCE_PREFIX}{room_id}")

    @pytest.mark.asyncio
    async def test_keeps_fresh_presence_entries(self, redis_connected):
        """Fresh presence entries should NOT be removed."""
        room_id = f"test_room_{uuid4().hex[:8]}"
        user_id = f"test_user_{uuid4().hex[:8]}"

        # Add a fresh presence entry (current timestamp)
        fresh_timestamp = time.time()
        await redis_service.client.zadd(
            f"{PRESENCE_PREFIX}{room_id}",
            {user_id: fresh_timestamp}
        )

        # Run cleanup
        ctx = {}
        await cleanup_stale_presence(ctx)

        # Verify entry still exists
        score = await redis_service.client.zscore(
            f"{PRESENCE_PREFIX}{room_id}", user_id
        )
        assert score is not None

        # Cleanup
        await redis_service.client.delete(f"{PRESENCE_PREFIX}{room_id}")

    @pytest.mark.asyncio
    async def test_cleanup_handles_empty_redis(self, redis_connected):
        """Cleanup should handle case with no presence entries."""
        ctx = {}
        result = await cleanup_stale_presence(ctx)

        # Should not raise, should return a result
        assert "removed" in result


# =============================================================================
# Worker Settings Tests
# =============================================================================


class TestWorkerSettings:
    """Tests for ARQ WorkerSettings configuration."""

    def test_redis_settings_parsed_from_url(self):
        """Redis settings should be parsed from settings.redis_url."""
        from app.worker import parse_redis_url, WorkerSettings

        redis_settings = parse_redis_url(settings.redis_url)

        assert redis_settings.host is not None
        assert redis_settings.port is not None

    def test_cron_jobs_configured(self):
        """Cron jobs should be configured."""
        from app.worker import WorkerSettings

        assert len(WorkerSettings.cron_jobs) == 2

    def test_functions_registered(self):
        """Job functions should be registered."""
        from app.worker import WorkerSettings

        assert len(WorkerSettings.functions) == 2
        function_names = [f.__name__ for f in WorkerSettings.functions]
        assert "run_archive_jobs" in function_names
        assert "cleanup_stale_presence" in function_names

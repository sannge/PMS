"""Shared pytest fixtures for backend tests with async PostgreSQL.

Uses session-scoped table creation (DDL runs once) with function-scoped
savepoint rollback for fast, isolated tests.
"""

import asyncio
import os
import sys
from datetime import date, timedelta
from typing import AsyncGenerator

from app.utils.timezone import utc_now
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Add app to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now import app modules
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Application, Notification, Project, Task, User
from app.models.task_status import TaskStatus, StatusName, STATUS_CATEGORY_MAP
from app.services.auth_service import create_access_token
from app.services.user_cache_service import clear_all_caches


def get_test_password_hash(password: str) -> str:
    """
    Generate a password hash for testing.

    Uses bcrypt directly to avoid passlib version detection issues.
    """
    import bcrypt
    # Use bcrypt directly - encode password to bytes
    password_bytes = password.encode('utf-8')
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


# Use test database (pmsdb_test) - NEVER use main database for tests!
TEST_DATABASE_URL = settings.test_database_url

# ---------------------------------------------------------------------------
# Session-scoped engine: tables created ONCE, dropped ONCE
# ---------------------------------------------------------------------------

# SQL to drop stale composite types left behind by CREATE TABLE.
# Without this, a crashed previous session can leave orphan types
# that cause UniqueViolationError on the next CREATE TABLE.
# IMPORTANT: Exclude types that are table row types (typrelid != 0)
# because those are managed by PostgreSQL and CASCADE would drop the table.
_DROP_COMPOSITE_TYPES_SQL = """DO $$ DECLARE r RECORD;
BEGIN
    FOR r IN (SELECT typname FROM pg_type
              WHERE typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
              AND typtype = 'c'
              AND typrelid = 0
              AND typname NOT LIKE 'pg_%'
              AND typname NOT IN ('vector'))
    LOOP
        EXECUTE 'DROP TYPE IF EXISTS "' || r.typname || '" CASCADE';
    END LOOP;
END $$;"""

_DROP_STATEMENTS = [
    # Drop scoped views first (created by migration, reference tables below)
    'DROP VIEW IF EXISTS v_checklist_items CASCADE',
    'DROP VIEW IF EXISTS v_checklists CASCADE',
    'DROP VIEW IF EXISTS v_attachments CASCADE',
    'DROP VIEW IF EXISTS v_users CASCADE',
    'DROP VIEW IF EXISTS v_project_assignments CASCADE',
    'DROP VIEW IF EXISTS v_project_members CASCADE',
    'DROP VIEW IF EXISTS v_application_members CASCADE',
    'DROP VIEW IF EXISTS v_comments CASCADE',
    'DROP VIEW IF EXISTS v_document_folders CASCADE',
    'DROP VIEW IF EXISTS v_documents CASCADE',
    'DROP VIEW IF EXISTS v_task_statuses CASCADE',
    'DROP VIEW IF EXISTS v_tasks CASCADE',
    'DROP VIEW IF EXISTS v_projects CASCADE',
    'DROP VIEW IF EXISTS v_applications CASCADE',
    # Drop tables in FK-safe order
    'DROP TABLE IF EXISTS "AgentConfigurations" CASCADE',
    'DROP TABLE IF EXISTS ai_system_prompts CASCADE',
    'DROP TABLE IF EXISTS "ChatMessages" CASCADE',
    'DROP TABLE IF EXISTS "ChatSessions" CASCADE',
    'DROP TABLE IF EXISTS "ImportJobs" CASCADE',
    'DROP TABLE IF EXISTS "DocumentChunks" CASCADE',
    'DROP TABLE IF EXISTS "FolderFiles" CASCADE',
    'DROP TABLE IF EXISTS "DocumentSnapshots" CASCADE',
    'DROP TABLE IF EXISTS "DocumentTagAssignments" CASCADE',
    'DROP TABLE IF EXISTS "DocumentTags" CASCADE',
    'DROP TABLE IF EXISTS "Documents" CASCADE',
    'DROP TABLE IF EXISTS "DocumentFolders" CASCADE',
    'DROP TABLE IF EXISTS "AiModels" CASCADE',
    'DROP TABLE IF EXISTS "AiProviders" CASCADE',
    'DROP TABLE IF EXISTS "Mentions" CASCADE',
    'DROP TABLE IF EXISTS "ChecklistItems" CASCADE',
    'DROP TABLE IF EXISTS "Attachments" CASCADE',
    'DROP TABLE IF EXISTS "ApplicationMembers" CASCADE',
    'DROP TABLE IF EXISTS "Comments" CASCADE',
    'DROP TABLE IF EXISTS "Checklists" CASCADE',
    'DROP TABLE IF EXISTS "Notes" CASCADE',
    'DROP TABLE IF EXISTS "Invitations" CASCADE',
    'DROP TABLE IF EXISTS "Tasks" CASCADE',
    'DROP TABLE IF EXISTS "ProjectTaskStatusAgg" CASCADE',
    'DROP TABLE IF EXISTS "ProjectMembers" CASCADE',
    'DROP TABLE IF EXISTS "ProjectAssignments" CASCADE',
    'DROP TABLE IF EXISTS "TaskStatuses" CASCADE',
    'DROP TABLE IF EXISTS "Projects" CASCADE',
    'DROP TABLE IF EXISTS "Notifications" CASCADE',
    'DROP TABLE IF EXISTS "Applications" CASCADE',
    'DROP TABLE IF EXISTS "Users" CASCADE',
]

# Track pgvector availability at module level (set during engine setup)
_pgvector_installed = False


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine():
    """Create async test engine — tables created once for the whole session.

    Architecture:
    - DDL operations (DROP/CREATE) use a disposable NullPool engine that is
      disposed immediately after schema setup.  This avoids poisoning the
      test engine's pool with long-lived DDL connections.
    - Test execution uses a POOLED engine (pool_size=5) with
      pool_reset_on_return="rollback".  Pooled connections prevent Windows
      TCP port exhaustion: NullPool creates a fresh TCP socket per test
      (~1000+ sockets in TIME_WAIT), which exhausts the ephemeral port
      range on Windows after ~576 tests.  A pool reuses a small number
      of connections, avoiding the problem entirely.
    """
    # --- Phase 1: DDL setup with a small pooled engine ---
    # Use pool_size=1 instead of NullPool to avoid Windows TCP churn
    # (NullPool creates a fresh TCP socket per begin() block which can
    # cause ConnectionDoesNotExistError when connections drop mid-DDL).
    _ddl_engine = create_async_engine(
        TEST_DATABASE_URL, pool_size=1, max_overflow=0,
    )

    # Terminate stale connections to avoid deadlocks during DROP TABLE
    async with _ddl_engine.begin() as conn:
        await conn.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid != pg_backend_pid()"
        ))

    # Drop all tables and stale composite types (clean slate)
    async with _ddl_engine.begin() as conn:
        for stmt in _DROP_STATEMENTS:
            await conn.execute(text(stmt))
        await conn.execute(text(_DROP_COMPOSITE_TYPES_SQL))

    # Ensure required PostgreSQL extensions exist.
    # Extensions must be in their own transactions because CREATE EXTENSION
    # failures (InsufficientPrivilegeError) abort the current transaction.
    global _pgvector_installed
    _pgvector_available = False

    async with _ddl_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        )
        if result.scalar() is not None:
            try:
                await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
                _pgvector_available = True
                _pgvector_installed = True
            except Exception:
                pass  # Insufficient privileges (test user is not superuser)

    async with _ddl_engine.begin() as conn:
        try:
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm'))
        except Exception:
            pass  # Already installed or insufficient privileges

    # Safety net: drop any stale composite types that survived table drops
    # (handles partially-failed previous sessions)
    async with _ddl_engine.begin() as conn:
        await conn.execute(text(_DROP_COMPOSITE_TYPES_SQL))

    # Create all tables once
    async with _ddl_engine.begin() as conn:
        if _pgvector_available:
            await conn.run_sync(Base.metadata.create_all)
        else:
            # Create all tables except DocumentChunks (which requires vector type)
            from app.models.document_chunk import DocumentChunk
            tables_to_create = [
                t for t in Base.metadata.sorted_tables
                if t.name != DocumentChunk.__tablename__
            ]
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, tables=tables_to_create
                )
            )

    # Dispose DDL engine — its connections are no longer needed
    await _ddl_engine.dispose()

    # --- Phase 2: Create pooled engine for test execution ---
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
    )

    yield _engine

    # --- Teardown: drop all tables + composite types, dispose engine ---
    async with _engine.begin() as conn:
        for stmt in _DROP_STATEMENTS:
            await conn.execute(text(stmt))
        await conn.execute(text(_DROP_COMPOSITE_TYPES_SQL))

    await _engine.dispose()


# ---------------------------------------------------------------------------
# Function-scoped: each test runs inside a transaction that gets rolled back
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db_connection(engine) -> AsyncGenerator[AsyncConnection, None]:
    """Open a connection and begin a transaction that will be rolled back."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield conn
        await trans.rollback()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    """Create a session bound to the test transaction.

    Uses begin_nested() (savepoints) so that session.commit() inside tests
    doesn't actually commit to the DB — the outer transaction rollback in
    db_connection undoes everything.
    """
    async_session = async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session() as session:
        # Start a savepoint; commits inside the test become savepoint releases
        await session.begin_nested()

        # After each commit (savepoint release), start a new savepoint
        # so subsequent operations in the same test still work
        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(session_sync, transaction):
            if transaction.nested and not transaction._parent.nested:
                session_sync.begin_nested()

        yield session


@pytest.fixture(autouse=True)
def _clear_user_caches():
    """Clear in-memory user/role caches before each test to prevent cross-test interference."""
    clear_all_caches()
    yield
    clear_all_caches()


@pytest.fixture(autouse=True)
def _clear_rate_limit_counters():
    """Clear in-memory rate limit counters between tests.

    When Redis is unavailable (the norm in tests), the rate limiter falls back
    to in-memory counters keyed by IP. Without clearing, limits accumulate
    across tests sharing the same test client IP.
    """
    from app.ai.rate_limiter import _inmemory_counters
    _inmemory_counters.clear()
    yield
    _inmemory_counters.clear()


@pytest.fixture(autouse=True)
def _mock_smtp():
    """Prevent real SMTP connections during tests.

    The production .env has SMTP_ENABLED=true, so without this mock every
    call to create_user() / resend_verification / forgot-password would
    attempt a real SMTP connection (60 s timeout x 3 retries), blocking
    the event loop and cascading into hundreds of asyncpg errors.
    """
    with patch(
        "app.services.email_service.aiosmtplib.send",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_token_blacklist():
    """Prevent token blacklist checks from failing when Redis is unavailable.

    Tests run without Redis. With redis_required=True in .env the
    fail-closed blacklist check would reject every JWT token. This mock
    makes is_token_blacklisted always return False (not blacklisted) so
    that auth works normally in tests.
    """
    with patch(
        "app.services.auth_service.is_token_blacklisted",
        new_callable=AsyncMock,
        return_value=False,
    ):
        yield


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with database dependency override."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user (email verified)."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        password_hash=get_test_password_hash("TestPassword123!"),
        display_name="Test User",
        email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession) -> User:
    """Create a second test user (email verified)."""
    user = User(
        id=uuid4(),
        email="test2@example.com",
        password_hash=get_test_password_hash("TestPassword456!"),
        display_name="Test User 2",
        email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User) -> str:
    """Create an authentication token for the test user."""
    return create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email}
    )


@pytest.fixture
def auth_token_2(test_user_2: User) -> str:
    """Create an authentication token for the second test user."""
    return create_access_token(
        data={"sub": str(test_user_2.id), "email": test_user_2.email}
    )


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Create authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def auth_headers_2(auth_token_2: str) -> dict:
    """Create authorization headers for second user."""
    return {"Authorization": f"Bearer {auth_token_2}"}


@pytest_asyncio.fixture
async def test_application(db_session: AsyncSession, test_user: User) -> Application:
    """Create a test application."""
    application = Application(
        id=uuid4(),
        name="Test Application",
        description="A test application",
        owner_id=test_user.id,
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)
    return application


@pytest_asyncio.fixture
async def test_project(db_session: AsyncSession, test_application: Application) -> Project:
    """Create a test project with default statuses."""
    project = Project(
        id=uuid4(),
        application_id=test_application.id,
        name="Test Project",
        key="TEST",
        description="A test project",
        project_type="kanban",
        due_date=date.today() + timedelta(days=30),
    )
    db_session.add(project)
    await db_session.flush()

    # Create default statuses for the project
    statuses = TaskStatus.create_default_statuses(project.id)
    for status in statuses:
        db_session.add(status)

    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def test_task_status_todo(db_session: AsyncSession, test_project: Project) -> TaskStatus:
    """Get the Todo status for the test project."""
    from sqlalchemy import select
    result = await db_session.execute(
        select(TaskStatus).where(
            TaskStatus.project_id == test_project.id,
            TaskStatus.name == StatusName.TODO.value,
        )
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def test_task(db_session: AsyncSession, test_project: Project, test_user: User, test_task_status_todo: TaskStatus) -> Task:
    """Create a test task."""
    task = Task(
        id=uuid4(),
        project_id=test_project.id,
        task_key="TEST-1",
        title="Test Task",
        description="A test task description",
        task_type="story",
        task_status_id=test_task_status_todo.id,
        priority="medium",
        reporter_id=test_user.id,
    )
    db_session.add(task)
    # Bump counter to stay in sync with the manually-created task key
    test_project.next_task_number = 2
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest_asyncio.fixture
async def test_notification(db_session: AsyncSession, test_user: User) -> Notification:
    """Create a test notification."""
    notification = Notification(
        id=uuid4(),
        user_id=test_user.id,
        type="task_assigned",
        title="Task Assigned",
        message="You have been assigned a task",
        is_read=False,
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.fixture
def requires_pgvector():
    """Skip test if pgvector extension is not installed on the test database."""
    if not _pgvector_installed:
        pytest.skip("pgvector extension not installed on test database")


@pytest.fixture
def mock_minio_service():
    """Create a mock MinIO service."""
    with patch("app.services.minio_service.MinIOService") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        # Configure mock methods
        mock_instance.ensure_buckets_exist.return_value = None
        mock_instance.upload_file.return_value = "test/path/file.txt"
        mock_instance.upload_bytes.return_value = "test/path/file.txt"
        mock_instance.download_file.return_value = b"test content"
        mock_instance.delete_file.return_value = True
        mock_instance.file_exists.return_value = True
        mock_instance.get_presigned_download_url.return_value = "http://example.com/download"
        mock_instance.get_presigned_upload_url.return_value = "http://example.com/upload"
        mock_instance.get_file_info.return_value = {
            "size": 1024,
            "content_type": "text/plain",
            "last_modified": utc_now(),
            "etag": "abc123",
        }
        mock_instance.generate_object_name.return_value = "task/uuid/12345678_file.txt"
        mock_instance.get_bucket_for_content_type.return_value = "pm-attachments"
        mock_instance.list_objects.return_value = []
        mock_instance.copy_object.return_value = "dest/path/file.txt"

        yield mock_instance

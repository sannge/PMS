"""Shared pytest fixtures for backend tests with async PostgreSQL."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add app to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now import app modules
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Application, Note, Notification, Project, Task, User
from app.services.auth_service import create_access_token


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


# Use PostgreSQL test database
TEST_DATABASE_URL = settings.test_database_url


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create async test engine with PostgreSQL."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    # Drop all tables first (clean slate)
    async with engine.begin() as conn:
        # Use raw SQL for tables with circular FK dependencies
        await conn.execute(text("DROP TABLE IF EXISTS \"Mentions\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ChecklistItems\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Attachments\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ApplicationMembers\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Comments\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Checklists\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Notes\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Invitations\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Tasks\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ProjectTaskStatusAgg\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ProjectMembers\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ProjectAssignments\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"TaskStatuses\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Projects\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Notifications\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Applications\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Users\" CASCADE"))

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables at end
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS \"Mentions\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ChecklistItems\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Attachments\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ApplicationMembers\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Comments\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Checklists\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Notes\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Invitations\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Tasks\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ProjectTaskStatusAgg\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ProjectMembers\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"ProjectAssignments\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"TaskStatuses\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Projects\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Notifications\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Applications\" CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS \"Users\" CASCADE"))

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async test database session."""
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


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
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        password_hash=get_test_password_hash("TestPassword123!"),
        display_name="Test User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession) -> User:
    """Create a second test user."""
    user = User(
        id=uuid4(),
        email="test2@example.com",
        password_hash=get_test_password_hash("TestPassword456!"),
        display_name="Test User 2",
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
    """Create a test project."""
    project = Project(
        id=uuid4(),
        application_id=test_application.id,
        name="Test Project",
        key="TEST",
        description="A test project",
        project_type="kanban",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def test_task(db_session: AsyncSession, test_project: Project, test_user: User) -> Task:
    """Create a test task."""
    task = Task(
        id=uuid4(),
        project_id=test_project.id,
        task_key="TEST-1",
        title="Test Task",
        description="A test task description",
        task_type="story",
        status="todo",
        priority="medium",
        reporter_id=test_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest_asyncio.fixture
async def test_note(db_session: AsyncSession, test_application: Application, test_user: User) -> Note:
    """Create a test note."""
    note = Note(
        id=uuid4(),
        application_id=test_application.id,
        title="Test Note",
        content="<p>Test note content</p>",
        tab_order=0,
        created_by=test_user.id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


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
            "last_modified": datetime.utcnow(),
            "etag": "abc123",
        }
        mock_instance.generate_object_name.return_value = "task/uuid/12345678_file.txt"
        mock_instance.get_bucket_for_content_type.return_value = "pm-attachments"
        mock_instance.list_objects.return_value = []
        mock_instance.copy_object.return_value = "dest/path/file.txt"

        yield mock_instance

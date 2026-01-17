"""Shared pytest fixtures for backend tests."""

import os
import sys
from datetime import datetime, timedelta
from typing import Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, String
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Add app to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch UNIQUEIDENTIFIER for SQLite BEFORE importing models
from sqlalchemy.dialects import sqlite
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER

# Add SQLite type compiler method to handle UNIQUEIDENTIFIER
def visit_UNIQUEIDENTIFIER(self, type_, **kw):
    """Compile UNIQUEIDENTIFIER as VARCHAR(36) for SQLite."""
    return "VARCHAR(36)"

# Apply the patch to SQLite type compiler
sqlite.base.SQLiteTypeCompiler.visit_UNIQUEIDENTIFIER = visit_UNIQUEIDENTIFIER

# Now import app modules after patching
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


# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    """Create a test database engine with SQLite."""
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key support for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Clean up
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        password_hash=get_test_password_hash("TestPassword123!"),
        display_name="Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_2(db_session: Session) -> User:
    """Create a second test user."""
    user = User(
        id=uuid4(),
        email="test2@example.com",
        password_hash=get_test_password_hash("TestPassword456!"),
        display_name="Test User 2",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
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


@pytest.fixture
def test_application(db_session: Session, test_user: User) -> Application:
    """Create a test application."""
    application = Application(
        id=uuid4(),
        name="Test Application",
        description="A test application",
        owner_id=test_user.id,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


@pytest.fixture
def test_project(db_session: Session, test_application: Application) -> Project:
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
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def test_task(db_session: Session, test_project: Project, test_user: User) -> Task:
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
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def test_note(db_session: Session, test_application: Application, test_user: User) -> Note:
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
    db_session.commit()
    db_session.refresh(note)
    return note


@pytest.fixture
def test_notification(db_session: Session, test_user: User) -> Notification:
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
    db_session.commit()
    db_session.refresh(notification)
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

"""Unit tests for Files API endpoints.

Tests cover:
- File upload
- File listing with filters
- Get file info
- Get download URL
- Delete file
- Entity attachments
"""

import io
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attachment, Task, User
from app.services.minio_service import get_minio_service


@pytest.mark.asyncio
class TestListFiles:
    """Tests for GET /api/files endpoint."""

    async def test_list_files_empty(self, client: AsyncClient, auth_headers: dict):
        """Test listing files when none exist."""
        response = await client.get("/api/files", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_files_with_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
    ):
        """Test listing files with existing data."""
        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="task/uuid/test.txt",
            uploaded_by=test_user.id,
            entity_type="task",
            entity_id=test_task.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        response = await client.get("/api/files", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["file_name"] == "test.txt"

    async def test_list_files_pagination(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test file listing pagination."""
        for i in range(5):
            attachment = Attachment(
                id=uuid4(),
                file_name=f"file{i}.txt",
                file_type="text/plain",
                file_size=1024,
                minio_bucket="pm-attachments",
                minio_key=f"general/uuid/file{i}.txt",
                uploaded_by=test_user.id,
            )
            db_session.add(attachment)
        await db_session.commit()

        response = await client.get(
            "/api/files", headers=auth_headers, params={"limit": 2}
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    async def test_list_files_filter_by_entity(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
    ):
        """Test filtering files by entity type."""
        # Create attachments for different entities
        task_attachment = Attachment(
            id=uuid4(),
            file_name="task_file.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="task/uuid/task_file.txt",
            uploaded_by=test_user.id,
            entity_type="task",
            entity_id=test_task.id,
        )
        general_attachment = Attachment(
            id=uuid4(),
            file_name="general_file.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/general_file.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(task_attachment)
        db_session.add(general_attachment)
        await db_session.commit()

        response = await client.get(
            "/api/files",
            headers=auth_headers,
            params={"entity_type": "task"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["file_name"] == "task_file.txt"


@pytest.mark.asyncio
class TestGetFileInfo:
    """Tests for GET /api/files/{id}/info endpoint."""

    async def test_get_file_info_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting file metadata only."""
        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        response = await client.get(
            f"/api/files/{attachment.id}/info", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "test.txt"
        assert data["file_size"] == 1024

    async def test_get_file_info_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting info of non-existent file."""
        fake_id = uuid4()
        response = await client.get(f"/api/files/{fake_id}/info", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_file_info_wrong_user(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting another user's file info."""
        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        response = await client.get(
            f"/api/files/{attachment.id}/info", headers=auth_headers_2
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestDeleteFile:
    """Tests for DELETE /api/files/{id} endpoint."""

    async def test_delete_file_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting a file."""
        from app.main import app as fastapi_app

        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()
        attachment_id = attachment.id

        # Mock the MinIO service for this test
        mock_minio = MagicMock()
        mock_minio.delete_file.return_value = True

        def override_minio():
            return mock_minio

        fastapi_app.dependency_overrides[get_minio_service] = override_minio

        try:
            response = await client.delete(
                f"/api/files/{attachment_id}", headers=auth_headers
            )
            assert response.status_code == 204

            # Verify deleted from database
            result = await db_session.execute(
                select(Attachment).filter(Attachment.id == attachment_id)
            )
            deleted = result.scalar_one_or_none()
            assert deleted is None
        finally:
            fastapi_app.dependency_overrides.pop(get_minio_service, None)

    async def test_delete_file_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test deleting non-existent file."""
        fake_id = uuid4()
        response = await client.delete(f"/api/files/{fake_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_delete_file_wrong_user(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting another user's file."""
        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        response = await client.delete(
            f"/api/files/{attachment.id}", headers=auth_headers_2
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestEntityAttachments:
    """Tests for GET /api/files/entity/{type}/{id} endpoint."""

    async def test_get_entity_attachments_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_task: Task,
    ):
        """Test getting attachments for an entity."""
        # Create attachments for the task
        for i in range(3):
            attachment = Attachment(
                id=uuid4(),
                file_name=f"file{i}.txt",
                file_type="text/plain",
                file_size=1024,
                minio_bucket="pm-attachments",
                minio_key=f"task/uuid/file{i}.txt",
                uploaded_by=test_user.id,
                entity_type="task",
                entity_id=test_task.id,
            )
            db_session.add(attachment)
        await db_session.commit()

        response = await client.get(
            f"/api/files/entity/task/{test_task.id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    async def test_get_entity_attachments_empty(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_task: Task,
    ):
        """Test getting attachments for entity with none."""
        response = await client.get(
            f"/api/files/entity/task/{test_task.id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
class TestAuthTest:
    """Tests for GET /api/files/test endpoint."""

    async def test_auth_test_authenticated(
        self, client: AsyncClient, auth_headers: dict, test_user: User
    ):
        """Test auth test endpoint with valid token."""
        response = await client.get("/api/files/test", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Files API is working"
        assert data["user_id"] == str(test_user.id)
        assert data["user_email"] == test_user.email

    async def test_auth_test_unauthenticated(self, client: AsyncClient):
        """Test auth test endpoint without token."""
        response = await client.get("/api/files/test")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestGetFile:
    """Tests for GET /api/files/{id} endpoint."""

    async def test_get_file_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting file by ID with download URL."""
        from app.main import app as fastapi_app

        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        # Mock the MinIO service
        mock_minio = MagicMock()
        mock_minio.get_presigned_download_url.return_value = "http://example.com/download"

        def override_minio():
            return mock_minio

        fastapi_app.dependency_overrides[get_minio_service] = override_minio

        try:
            response = await client.get(
                f"/api/files/{attachment.id}", headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            # Response is FileDownloadResponse with nested attachment
            assert data["attachment"]["file_name"] == "test.txt"
            assert data["download_url"] == "http://example.com/download"
        finally:
            fastapi_app.dependency_overrides.pop(get_minio_service, None)

    async def test_get_file_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting non-existent file."""
        fake_id = uuid4()
        response = await client.get(f"/api/files/{fake_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_file_wrong_user(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting another user's file."""
        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        response = await client.get(
            f"/api/files/{attachment.id}", headers=auth_headers_2
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestGetDownloadUrl:
    """Tests for GET /api/files/{id}/download-url endpoint."""

    async def test_get_download_url_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting a fresh download URL."""
        from app.main import app as fastapi_app

        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        # Mock the MinIO service
        mock_minio = MagicMock()
        mock_minio.get_presigned_download_url.return_value = "http://example.com/fresh-url"

        def override_minio():
            return mock_minio

        fastapi_app.dependency_overrides[get_minio_service] = override_minio

        try:
            response = await client.get(
                f"/api/files/{attachment.id}/download-url", headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["download_url"] == "http://example.com/fresh-url"
        finally:
            fastapi_app.dependency_overrides.pop(get_minio_service, None)

    async def test_get_download_url_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting download URL for non-existent file."""
        fake_id = uuid4()
        response = await client.get(f"/api/files/{fake_id}/download-url", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_download_url_wrong_user(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting download URL for another user's file."""
        attachment = Attachment(
            id=uuid4(),
            file_name="test.txt",
            file_type="text/plain",
            file_size=1024,
            minio_bucket="pm-attachments",
            minio_key="general/uuid/test.txt",
            uploaded_by=test_user.id,
        )
        db_session.add(attachment)
        await db_session.commit()

        response = await client.get(
            f"/api/files/{attachment.id}/download-url", headers=auth_headers_2
        )
        assert response.status_code == 403

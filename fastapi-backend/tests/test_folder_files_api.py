"""Tests for folder file upload/management API endpoints (Phase 2)."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.document_folder import DocumentFolder
from app.models.folder_file import FolderFile
from app.models.user import User
from app.services.auth_service import create_access_token
from app.utils.timezone import utc_now


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def app_folder(
    db_session: AsyncSession, test_user: User, test_application: Application
) -> DocumentFolder:
    """Create a test folder scoped to the test application."""
    folder = DocumentFolder(
        id=uuid4(),
        name="Test Folder",
        application_id=test_application.id,
        created_by=test_user.id,
        materialized_path=f"/{uuid4()}/",
        depth=0,
        sort_order=0,
    )
    db_session.add(folder)
    await db_session.commit()
    await db_session.refresh(folder)
    return folder


@pytest_asyncio.fixture
async def personal_folder(
    db_session: AsyncSession, test_user: User
) -> DocumentFolder:
    """Create a personal-scope folder for test_user."""
    folder = DocumentFolder(
        id=uuid4(),
        name="Personal Folder",
        user_id=test_user.id,
        created_by=test_user.id,
        materialized_path=f"/{uuid4()}/",
        depth=0,
        sort_order=0,
    )
    db_session.add(folder)
    await db_session.commit()
    await db_session.refresh(folder)
    return folder


@pytest_asyncio.fixture
async def test_folder_file(
    db_session: AsyncSession,
    test_user: User,
    test_application: Application,
    app_folder: DocumentFolder,
) -> FolderFile:
    """Create a test FolderFile record."""
    ff = FolderFile(
        id=uuid4(),
        folder_id=app_folder.id,
        application_id=test_application.id,
        original_name="test.pdf",
        display_name="test.pdf",
        mime_type="application/pdf",
        file_size=1024,
        file_extension="pdf",
        storage_bucket="pm-attachments",
        storage_key=f"folder-files/{app_folder.id}/12345678_test.pdf",
        extraction_status="pending",
        sha256_hash="abc123",
        sort_order=0,
        created_by=test_user.id,
    )
    db_session.add(ff)
    await db_session.commit()
    await db_session.refresh(ff)
    return ff


def _mock_rate_limiter():
    """Create a mock rate limiter that always allows requests."""
    mock_rl = MagicMock()
    mock_result = MagicMock()
    mock_result.allowed = True
    mock_result.remaining = 19
    mock_result.reset_seconds = 60
    mock_result.limit = 20
    mock_result.reset_at = MagicMock(timestamp=MagicMock(return_value=9999999999))
    mock_rl.check_and_increment = AsyncMock(return_value=mock_result)
    return mock_rl


# ============================================================================
# Upload Tests
# ============================================================================


class TestUploadFile:
    """Tests for POST /api/folder-files/upload."""

    @pytest.mark.asyncio
    async def test_upload_file_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """Uploading a PDF creates a FolderFile and returns 201."""
        with (
            patch(
                "app.routers.folder_files.get_minio_service",
                return_value=MagicMock(
                    upload_bytes=MagicMock(),
                    delete_file=MagicMock(),
                    get_bucket_for_content_type=MagicMock(return_value="pm-attachments"),
                ),
            ),
            patch(
                "app.services.minio_service.get_minio_service",
                return_value=MagicMock(upload_bytes=MagicMock()),
            ),
            patch("app.routers.folder_files._enqueue_extraction_job", new_callable=AsyncMock),
            patch("app.routers.folder_files.ws_manager", MagicMock(broadcast_to_room=AsyncMock())),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}",
                files={"file": ("report.pdf", b"fake pdf content", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["display_name"] == "report.pdf"
        assert data["file_extension"] == "pdf"
        assert data["extraction_status"] == "pending"
        assert data["folder_id"] == str(app_folder.id)

    @pytest.mark.asyncio
    async def test_upload_file_custom_display_name(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """Custom display_name is used instead of original filename."""
        with (
            patch(
                "app.routers.folder_files.get_minio_service",
                return_value=MagicMock(upload_bytes=MagicMock(), delete_file=MagicMock()),
            ),
            patch(
                "app.services.minio_service.get_minio_service",
                return_value=MagicMock(upload_bytes=MagicMock()),
            ),
            patch("app.routers.folder_files._enqueue_extraction_job", new_callable=AsyncMock),
            patch("app.routers.folder_files.ws_manager", MagicMock(broadcast_to_room=AsyncMock())),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}&display_name=My Report",
                files={"file": ("report.pdf", b"fake pdf content", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert response.json()["display_name"] == "My Report"

    @pytest.mark.asyncio
    async def test_upload_file_unsupported_extension(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """Non-extractable files get extraction_status='unsupported'."""
        with (
            patch(
                "app.routers.folder_files.get_minio_service",
                return_value=MagicMock(upload_bytes=MagicMock(), delete_file=MagicMock()),
            ),
            patch(
                "app.services.minio_service.get_minio_service",
                return_value=MagicMock(upload_bytes=MagicMock()),
            ),
            patch("app.routers.folder_files.ws_manager", MagicMock(broadcast_to_room=AsyncMock())),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}",
                files={"file": ("photo.jpg", b"fake image", "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert response.json()["extraction_status"] == "unsupported"

    @pytest.mark.asyncio
    async def test_upload_file_empty_file(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """Empty files are rejected with 400."""
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}",
                files={"file": ("empty.pdf", b"", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_file_duplicate_name_409(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
        test_folder_file: FolderFile,
    ):
        """Duplicate display_name in same folder returns 409."""
        with (
            patch(
                "app.routers.folder_files.get_minio_service",
                return_value=MagicMock(upload_bytes=MagicMock()),
            ),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}",
                files={"file": ("test.pdf", b"another pdf", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_upload_file_nonexistent_folder_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Upload to non-existent folder returns 404."""
        fake_folder_id = uuid4()
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={fake_folder_id}",
                files={"file": ("test.pdf", b"pdf content", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_file_rbac_denied(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        app_folder: DocumentFolder,
    ):
        """Non-member gets 403 when uploading to app-scoped folder."""
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}",
                files={"file": ("test.pdf", b"pdf content", "application/pdf")},
                headers=auth_headers_2,
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_upload_file_exceeding_max_size_413(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """File exceeding MAX_FILE_SIZE returns 413."""
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
            patch("app.routers.folder_files._get_max_file_size", return_value=100),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}",
                files={"file": ("big.pdf", b"x" * 200, "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_upload_blocked_extension_400(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """Blocked extensions (.exe, .bat, etc.) return 400."""
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/upload?folder_id={app_folder.id}",
                files={"file": ("malware.exe", b"bad content", "application/octet-stream")},
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_rate_limit_429(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """TE-GAP-3: Upload returns 429 when rate limit is exceeded."""
        from app.main import app as _app
        from app.ai.rate_limiter import get_rate_limiter as _get_rate_limiter

        mock_rl = MagicMock()
        mock_result = MagicMock()
        mock_result.allowed = False
        mock_result.remaining = 0
        mock_result.reset_seconds = 45
        mock_result.limit = 20
        mock_result.reset_at = MagicMock(timestamp=MagicMock(return_value=9999999999))
        mock_rl.check_and_increment = AsyncMock(return_value=mock_result)

        _app.dependency_overrides[_get_rate_limiter] = lambda: mock_rl
        try:
            with patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()):
                response = await client.post(
                    f"/api/folder-files/upload?folder_id={app_folder.id}",
                    files={"file": ("test.pdf", b"pdf content", "application/pdf")},
                    headers=auth_headers,
                )
        finally:
            _app.dependency_overrides.pop(_get_rate_limiter, None)

        assert response.status_code == 429
        assert "rate limit exceeded" in response.json()["detail"].lower()
        assert response.headers.get("X-RateLimit-Limit") == "20"
        assert response.headers.get("X-RateLimit-Remaining") == "0"


# ============================================================================
# List Tests
# ============================================================================


class TestListFiles:
    """Tests for GET /api/folder-files."""

    @pytest.mark.asyncio
    async def test_list_files_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
        test_folder_file: FolderFile,
    ):
        """List returns files in the folder wrapped in {items: [...]}."""
        response = await client.get(
            f"/api/folder-files?folder_id={app_folder.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # CRIT-3: Response is {items: [...]}
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["display_name"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_list_files_empty_folder(
        self,
        client: AsyncClient,
        auth_headers: dict,
        app_folder: DocumentFolder,
    ):
        """Empty folder returns {items: []}."""
        response = await client.get(
            f"/api/folder-files?folder_id={app_folder.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data == {"items": []}

    @pytest.mark.asyncio
    async def test_list_files_rbac_denied(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        app_folder: DocumentFolder,
    ):
        """Non-member gets 403 when listing files in app-scoped folder."""
        response = await client.get(
            f"/api/folder-files?folder_id={app_folder.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403


# ============================================================================
# Get File Details Tests
# ============================================================================


class TestGetFile:
    """Tests for GET /api/folder-files/{file_id}."""

    @pytest.mark.asyncio
    async def test_get_file_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
    ):
        """Get returns full file details."""
        response = await client.get(
            f"/api/folder-files/{test_folder_file.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_folder_file.id)
        assert data["display_name"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_get_file_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Non-existent file returns 404."""
        response = await client.get(
            f"/api/folder-files/{uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_file_rbac_denied(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_folder_file: FolderFile,
    ):
        """Non-member gets 403 when getting file details."""
        response = await client.get(
            f"/api/folder-files/{test_folder_file.id}",
            headers=auth_headers_2,
        )
        assert response.status_code == 403


# ============================================================================
# Download URL Tests
# ============================================================================


class TestDownloadURL:
    """Tests for GET /api/folder-files/{file_id}/download."""

    @pytest.mark.asyncio
    async def test_download_url_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
    ):
        """Download returns presigned URL."""
        from app.main import app as _app
        from app.services.minio_service import get_minio_service as _get_minio_service

        mock_minio = MagicMock()
        mock_minio.get_presigned_download_url.return_value = "https://minio.local/file.pdf"

        _app.dependency_overrides[_get_minio_service] = lambda: mock_minio
        try:
            response = await client.get(
                f"/api/folder-files/{test_folder_file.id}/download",
                headers=auth_headers,
            )
        finally:
            _app.dependency_overrides.pop(_get_minio_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["download_url"] == "https://minio.local/file.pdf"
        assert data["display_name"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_download_url_rbac_denied(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_folder_file: FolderFile,
    ):
        """Non-member gets 403 when getting download URL."""
        response = await client.get(
            f"/api/folder-files/{test_folder_file.id}/download",
            headers=auth_headers_2,
        )
        assert response.status_code == 403


# ============================================================================
# Update (Rename/Move) Tests
# ============================================================================


class TestUpdateFile:
    """Tests for PUT /api/folder-files/{file_id}."""

    @pytest.mark.asyncio
    async def test_rename_file_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
    ):
        """Rename with correct row_version succeeds."""
        initial_version = test_folder_file.row_version
        response = await client.put(
            f"/api/folder-files/{test_folder_file.id}",
            json={
                "display_name": "renamed.pdf",
                "row_version": initial_version,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "renamed.pdf"
        assert data["row_version"] == initial_version + 1

    @pytest.mark.asyncio
    async def test_update_file_concurrency_conflict(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
    ):
        """Wrong row_version returns 409."""
        response = await client.put(
            f"/api/folder-files/{test_folder_file.id}",
            json={
                "display_name": "renamed.pdf",
                "row_version": 999,
            },
            headers=auth_headers,
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_update_file_rbac_denied(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_folder_file: FolderFile,
    ):
        """Non-member gets 403 when updating a file."""
        response = await client.put(
            f"/api/folder-files/{test_folder_file.id}",
            json={
                "display_name": "renamed.pdf",
                "row_version": test_folder_file.row_version,
            },
            headers=auth_headers_2,
        )
        assert response.status_code == 403


# ============================================================================
# Delete Tests
# ============================================================================


class TestDeleteFile:
    """Tests for DELETE /api/folder-files/{file_id}."""

    @pytest.mark.asyncio
    async def test_delete_file_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
        db_session: AsyncSession,
    ):
        """Soft delete returns 204 and sets deleted_at."""
        with (
            patch("app.routers.folder_files.ws_manager", MagicMock(broadcast_to_room=AsyncMock())),
            patch(
                "app.services.search_service.remove_file_from_index",
                new_callable=AsyncMock,
            ) as mock_remove,
        ):
            response = await client.delete(
                f"/api/folder-files/{test_folder_file.id}",
                headers=auth_headers,
            )

        assert response.status_code == 204

        # Verify deleted_at is set
        result = await db_session.execute(
            select(FolderFile).where(FolderFile.id == test_folder_file.id)
        )
        deleted_file = result.scalar_one_or_none()
        assert deleted_file is not None
        assert deleted_file.deleted_at is not None

        # Verify correct search function was called (CRIT-1)
        mock_remove.assert_called_once_with(test_folder_file.id)

    @pytest.mark.asyncio
    async def test_delete_file_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Deleting non-existent file returns 404."""
        response = await client.delete(
            f"/api/folder-files/{uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_file_rbac_denied(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_folder_file: FolderFile,
    ):
        """Non-member gets 403 when deleting a file."""
        response = await client.delete(
            f"/api/folder-files/{test_folder_file.id}",
            headers=auth_headers_2,
        )
        assert response.status_code == 403


# ============================================================================
# Replace Tests
# ============================================================================


class TestReplaceFile:
    """Tests for POST /api/folder-files/{file_id}/replace."""

    @pytest.mark.asyncio
    async def test_replace_file_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
    ):
        """Replacing file content resets extraction and re-enqueues."""
        mock_minio = MagicMock()
        mock_minio.delete_file.return_value = None
        mock_minio.upload_bytes.return_value = None

        with (
            patch("app.routers.folder_files.get_minio_service", return_value=mock_minio),
            patch("app.services.minio_service.get_minio_service", return_value=mock_minio),
            patch("app.routers.folder_files._enqueue_extraction_job", new_callable=AsyncMock),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/{test_folder_file.id}/replace",
                files={"file": ("new_report.xlsx", b"new content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["extraction_status"] == "pending"
        assert data["message"] == "File replaced successfully"

    @pytest.mark.asyncio
    async def test_replace_file_empty(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
    ):
        """Replacing with empty file returns 400."""
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/{test_folder_file.id}/replace",
                files={"file": ("empty.pdf", b"", "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_replace_file_blocked_extension(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_folder_file: FolderFile,
    ):
        """Replacing with blocked extension returns 400."""
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/{test_folder_file.id}/replace",
                files={"file": ("virus.exe", b"bad content", "application/octet-stream")},
                headers=auth_headers,
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_replace_file_rbac_denied(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_folder_file: FolderFile,
    ):
        """TE-GAP-4: Non-member (viewer) gets 403 when replacing a file."""
        with (
            patch("app.routers.folder_files.get_minio_service", return_value=MagicMock()),
            patch("app.routers.folder_files.get_rate_limiter", return_value=_mock_rate_limiter()),
        ):
            response = await client.post(
                f"/api/folder-files/{test_folder_file.id}/replace",
                files={"file": ("new.pdf", b"new content", "application/pdf")},
                headers=auth_headers_2,
            )

        assert response.status_code == 403


# ============================================================================
# WebSocket Message Type Tests
# ============================================================================


class TestMessageTypes:
    """Verify that file-related WebSocket message types are registered."""

    def test_file_message_types_exist(self):
        from app.websocket.manager import MessageType

        assert hasattr(MessageType, "FILE_UPLOADED")
        assert hasattr(MessageType, "FILE_UPDATED")
        assert hasattr(MessageType, "FILE_DELETED")
        assert hasattr(MessageType, "FILE_EXTRACTION_COMPLETED")
        assert hasattr(MessageType, "FILE_EXTRACTION_FAILED")

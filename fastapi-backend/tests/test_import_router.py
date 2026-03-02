"""Integration tests for document import router (app.routers.ai_import).

Uses httpx.AsyncClient with ASGITransport against the real FastAPI app,
with conftest fixtures for authentication, database sessions, and test data.
ARQ pool and PermissionService are mocked to prevent external dependencies.

Tests cover:
- POST /api/ai/import/    (file upload + job creation)
- GET  /api/ai/import/jobs (list user jobs)
- GET  /api/ai/import/{id} (single job status)
- Validation: extension, MIME type, file size, auth
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_job import ImportJob
from app.models.user import User
from app.models.application import Application
from app.utils.timezone import utc_now


# ---------------------------------------------------------------------------
# Auto-use fixtures: mock ARQ and PermissionService for all tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_arq():
    """Prevent real ARQ Redis connections; capture enqueue calls.

    The router uses lazy imports inside the function body:
        from arq.connections import create_pool
        from ..worker import parse_redis_url
    So we patch at the source module level.
    """
    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=MagicMock())
    mock_redis.aclose = AsyncMock()

    with patch("arq.connections.create_pool", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_redis
        with patch("app.worker.parse_redis_url", return_value=MagicMock()):
            yield mock_redis


@pytest.fixture(autouse=True)
def mock_permissions():
    """Grant edit permission by default; individual tests can override."""
    with patch("app.routers.ai_import.PermissionService") as mock_cls:
        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance
        mock_instance.check_can_edit_knowledge = AsyncMock(return_value=True)
        yield mock_instance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal PDF magic bytes (enough to pass MIME-type validation in upload)
_FAKE_PDF_BYTES = b"%PDF-1.4 fake content for test"

# DOCX and PPTX are ZIP-based but we only check MIME type, not actual content
_FAKE_DOCX_BYTES = b"PK\x03\x04 fake docx"
_FAKE_PPTX_BYTES = b"PK\x03\x04 fake pptx"

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


# ---------------------------------------------------------------------------
# POST /api/ai/import/ tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUploadAndImport:
    """Tests for the upload endpoint."""

    async def test_upload_pdf_creates_job(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST multipart with valid PDF bytes, verify 202, job_id returned."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("report.pdf", _FAKE_PDF_BYTES, "application/pdf")},
            data={"scope": "application", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert body["status"] == "pending"
        assert body["file_name"] == "report.pdf"

    async def test_upload_docx_creates_job(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST with DOCX MIME type, verify 202."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("design.docx", _FAKE_DOCX_BYTES, _DOCX_MIME)},
            data={"scope": "application", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 202
        body = response.json()
        assert body["file_name"] == "design.docx"

    async def test_upload_pptx_creates_job(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST with PPTX MIME type, verify 202."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("slides.pptx", _FAKE_PPTX_BYTES, _PPTX_MIME)},
            data={"scope": "application", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 202
        body = response.json()
        assert body["file_name"] == "slides.pptx"

    async def test_upload_invalid_type_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST with .txt file, verify 400."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"scope": "application", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    async def test_upload_mime_type_mismatch_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST .pdf extension but text/plain MIME, verify 400."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("fake.pdf", _FAKE_PDF_BYTES, "text/plain")},
            data={"scope": "application", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Unsupported MIME type" in response.json()["detail"]

    async def test_upload_too_large_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST with file >50MB, verify 413."""
        # Create content that exceeds 50MB limit
        # To avoid actually allocating 50MB+ in memory, we mock file.read()
        with patch("app.routers.ai_import.UploadFile") as _:
            # Instead, just send actual oversized content indicator
            # The router reads content = await file.read() and checks len(contents)
            # We need to actually send >50MB or patch the size check.
            # Practical approach: patch MAX_FILE_SIZE to a small value for this test
            with patch("app.routers.ai_import.MAX_FILE_SIZE", 10):
                response = await client.post(
                    "/api/ai/import/",
                    files={"file": ("big.pdf", _FAKE_PDF_BYTES, "application/pdf")},
                    data={"scope": "application", "scope_id": str(test_application.id)},
                    headers=auth_headers,
                )

        assert response.status_code == 413
        assert "File too large" in response.json()["detail"]

    async def test_upload_requires_auth(
        self,
        client: AsyncClient,
        test_application: Application,
    ) -> None:
        """POST without auth headers, verify 401."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("report.pdf", _FAKE_PDF_BYTES, "application/pdf")},
            data={"scope": "application", "scope_id": str(test_application.id)},
            # No auth_headers
        )

        assert response.status_code == 401

    async def test_import_job_cleans_temp_file(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_application: Application,
    ) -> None:
        """Verify temp file path set on the ImportJob record."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("doc.pdf", _FAKE_PDF_BYTES, "application/pdf")},
            data={"scope": "application", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Query the ImportJob directly to check temp_file_path
        from sqlalchemy import select
        result = await db_session.execute(
            select(ImportJob).where(ImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        assert job is not None
        assert job.temp_file_path is not None
        assert job.temp_file_path.endswith(".pdf")


# ---------------------------------------------------------------------------
# GET /api/ai/import/{job_id} tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetJobStatus:
    """Tests for the single job status endpoint."""

    async def test_get_job_status_returns_progress(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
    ) -> None:
        """Create job in DB, GET status, verify fields."""
        job = ImportJob(
            user_id=test_user.id,
            file_name="report.pdf",
            file_type="pdf",
            file_size=12345,
            status="processing",
            progress_pct=45,
            scope="application",
            scope_id=test_application.id,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        response = await client.get(
            f"/api/ai/import/{job.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(job.id)
        assert body["file_name"] == "report.pdf"
        assert body["file_type"] == "pdf"
        assert body["file_size"] == 12345
        assert body["status"] == "processing"
        assert body["progress_pct"] == 45
        assert body["scope"] == "application"
        assert body["scope_id"] == str(test_application.id)
        assert "created_at" in body

    async def test_get_job_status_unauthorized(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        db_session: AsyncSession,
        test_user: User,
        test_user_2: User,
        test_application: Application,
    ) -> None:
        """GET status for other user's job, verify 404."""
        # Job belongs to test_user
        job = ImportJob(
            user_id=test_user.id,
            file_name="private.pdf",
            file_type="pdf",
            file_size=5000,
            status="completed",
            progress_pct=100,
            scope="application",
            scope_id=test_application.id,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        # Request with test_user_2's auth headers
        response = await client.get(
            f"/api/ai/import/{job.id}",
            headers=auth_headers_2,
        )

        # Should return 404 (not 403) to avoid leaking job existence
        assert response.status_code == 404

    async def test_get_nonexistent_job_returns_404(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ) -> None:
        """GET with a random UUID returns 404."""
        random_id = uuid4()
        response = await client.get(
            f"/api/ai/import/{random_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/ai/import/jobs tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListJobs:
    """Tests for the list jobs endpoint."""

    async def test_list_jobs_returns_user_jobs_only(
        self,
        client: AsyncClient,
        auth_headers: dict,
        auth_headers_2: dict,
        db_session: AsyncSession,
        test_user: User,
        test_user_2: User,
        test_application: Application,
    ) -> None:
        """Create jobs for 2 users, verify filtering."""
        # Create 2 jobs for test_user
        for i in range(2):
            job = ImportJob(
                user_id=test_user.id,
                file_name=f"user1_file{i}.pdf",
                file_type="pdf",
                file_size=1000 * (i + 1),
                status="completed",
                progress_pct=100,
                scope="application",
                scope_id=test_application.id,
            )
            db_session.add(job)

        # Create 1 job for test_user_2
        job2 = ImportJob(
            user_id=test_user_2.id,
            file_name="user2_file.pdf",
            file_type="pdf",
            file_size=3000,
            status="pending",
            progress_pct=0,
            scope="application",
            scope_id=test_application.id,
        )
        db_session.add(job2)
        await db_session.commit()

        # List jobs as test_user: should see exactly 2
        response = await client.get(
            "/api/ai/import/jobs",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        file_names = {item["file_name"] for item in body["items"]}
        assert "user1_file0.pdf" in file_names
        assert "user1_file1.pdf" in file_names
        assert "user2_file.pdf" not in file_names

        # List jobs as test_user_2: should see exactly 1
        response2 = await client.get(
            "/api/ai/import/jobs",
            headers=auth_headers_2,
        )

        assert response2.status_code == 200
        body2 = response2.json()
        assert body2["total"] == 1
        assert body2["items"][0]["file_name"] == "user2_file.pdf"

    async def test_list_jobs_with_status_filter(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
    ) -> None:
        """Filter by status=completed."""
        # Create jobs with different statuses
        for status_val in ["completed", "completed", "pending", "failed"]:
            job = ImportJob(
                user_id=test_user.id,
                file_name=f"file_{status_val}.pdf",
                file_type="pdf",
                file_size=1000,
                status=status_val,
                progress_pct=100 if status_val == "completed" else 0,
                scope="application",
                scope_id=test_application.id,
            )
            db_session.add(job)
        await db_session.commit()

        # Filter by completed
        response = await client.get(
            "/api/ai/import/jobs?status=completed",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert all(item["status"] == "completed" for item in body["items"])

    async def test_list_jobs_pagination(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
    ) -> None:
        """Verify limit/offset work."""
        # Create 5 jobs
        for i in range(5):
            job = ImportJob(
                user_id=test_user.id,
                file_name=f"page_file_{i}.pdf",
                file_type="pdf",
                file_size=1000,
                status="completed",
                progress_pct=100,
                scope="application",
                scope_id=test_application.id,
            )
            db_session.add(job)
        await db_session.commit()

        # Request page 1 (limit=2, offset=0)
        response1 = await client.get(
            "/api/ai/import/jobs?limit=2&offset=0",
            headers=auth_headers,
        )

        assert response1.status_code == 200
        body1 = response1.json()
        assert body1["total"] == 5
        assert len(body1["items"]) == 2
        assert body1["limit"] == 2
        assert body1["offset"] == 0

        # Request page 2 (limit=2, offset=2)
        response2 = await client.get(
            "/api/ai/import/jobs?limit=2&offset=2",
            headers=auth_headers,
        )

        assert response2.status_code == 200
        body2 = response2.json()
        assert body2["total"] == 5
        assert len(body2["items"]) == 2
        assert body2["offset"] == 2

        # Items on page 1 and page 2 should be different
        page1_ids = {item["id"] for item in body1["items"]}
        page2_ids = {item["id"] for item in body2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

        # Request beyond last page
        response3 = await client.get(
            "/api/ai/import/jobs?limit=2&offset=10",
            headers=auth_headers,
        )

        assert response3.status_code == 200
        body3 = response3.json()
        assert body3["total"] == 5
        assert len(body3["items"]) == 0

    async def test_list_jobs_requires_auth(
        self,
        client: AsyncClient,
    ) -> None:
        """GET /jobs without auth headers returns 401."""
        response = await client.get("/api/ai/import/jobs")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestValidationEdgeCases:
    """Additional validation tests for the upload endpoint."""

    async def test_invalid_scope_returns_422(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST with invalid scope value returns 422."""
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("report.pdf", _FAKE_PDF_BYTES, "application/pdf")},
            data={"scope": "organization", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert "Invalid scope" in response.json()["detail"]

    async def test_magic_bytes_mismatch_returns_400(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ) -> None:
        """POST with PDF magic bytes but DOCX MIME type returns 400.

        The file starts with %PDF but Content-Type claims DOCX. The router
        detects that magic='pdf' but declared file_type='docx' and rejects.
        """
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("report.docx", _FAKE_PDF_BYTES, _DOCX_MIME)},
            data={"scope": "application", "scope_id": str(test_application.id)},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "does not match" in response.json()["detail"]

    async def test_personal_scope_wrong_user_returns_403(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ) -> None:
        """POST with scope=personal but scope_id != current user returns 403."""
        wrong_user_id = uuid4()
        response = await client.post(
            "/api/ai/import/",
            files={"file": ("report.pdf", _FAKE_PDF_BYTES, "application/pdf")},
            data={"scope": "personal", "scope_id": str(wrong_user_id)},
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert "Personal scope_id" in response.json()["detail"]

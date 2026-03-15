"""Tests for file extraction and embedding worker job (Phase 5).

TEST FIXES applied:
- Shared mock_folder_file fixture (avoids repeating MagicMock setup)
- Extraction timeout test (asyncio.TimeoutError path)
- Soft-deleted file skip test (deleted_at filter in query)
- document_id=None assertion in embed test (embed_file scope_ids)
- Exact count assertions instead of weak >= 1
- Updated to work with 3-session split architecture (HIGH-11)
- QE-NEW-2: Updated mocks for streaming download_to_file (writes to disk)
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

from app.ai.file_extraction_service import ExtractionResult


# ============================================================================
# Shared Fixtures
# ============================================================================


def _make_mock_folder_file(**overrides):
    """Create a mock FolderFile with sensible defaults.

    Shared across tests to avoid repeating the full mock setup.
    """
    ff = MagicMock()
    ff.id = overrides.get("id", uuid4())
    ff.extraction_status = overrides.get("extraction_status", "pending")
    ff.embedding_status = overrides.get("embedding_status", "none")
    ff.file_extension = overrides.get("file_extension", "pdf")
    ff.storage_bucket = overrides.get("storage_bucket", "pm-attachments")
    ff.storage_key = overrides.get("storage_key", "folder-files/test.pdf")
    ff.file_size = overrides.get("file_size", 1024)
    ff.display_name = overrides.get("display_name", "test.pdf")
    ff.mime_type = overrides.get("mime_type", "application/pdf")
    ff.application_id = overrides.get("application_id", uuid4())
    ff.project_id = overrides.get("project_id", None)
    ff.user_id = overrides.get("user_id", None)
    ff.folder_id = overrides.get("folder_id", uuid4())
    ff.created_by = overrides.get("created_by", uuid4())
    ff.updated_at = MagicMock(timestamp=MagicMock(return_value=1000000))
    ff.deleted_at = overrides.get("deleted_at", None)
    ff.content_plain = overrides.get("content_plain", None)
    ff.extracted_metadata = overrides.get("extracted_metadata", None)
    ff.extraction_error = overrides.get("extraction_error", None)
    return ff


def _make_session_cm(db_mock):
    """Wrap an AsyncMock DB into an async context manager."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db_mock)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_db_returning(ff_or_none):
    """Create a mock DB session that returns ff_or_none from scalar_one_or_none."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = ff_or_none
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_mock_minio(content: bytes = b"fake pdf bytes"):
    """Create a mock MinIO service that streams content to file (QE-NEW-2).

    download_to_file writes content to the file_path argument.
    """
    mock = MagicMock()

    def _write_to_file(bucket, object_name, file_path):
        Path(file_path).write_bytes(content)

    mock.download_to_file.side_effect = _write_to_file
    return mock


# ============================================================================
# extract_and_embed_file_job Tests
# ============================================================================


class TestExtractAndEmbedFileJob:
    """Tests for the extract_and_embed_file_job worker function."""

    @pytest.mark.asyncio
    async def test_skip_not_found(self):
        """Missing file (or soft-deleted) returns skipped/not_found."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        db = _make_db_returning(None)
        cm = _make_session_cm(db)

        with (
            patch("app.worker.async_session_maker", return_value=cm),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "skipped"
        assert result["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_skip_soft_deleted(self):
        """File with deleted_at set is filtered out by WHERE clause, returning not_found."""
        from app.worker import extract_and_embed_file_job

        # The query has `FolderFile.deleted_at.is_(None)` so a soft-deleted file
        # returns None from scalar_one_or_none.
        file_id = str(uuid4())
        db = _make_db_returning(None)  # deleted_at filter causes None
        cm = _make_session_cm(db)

        with (
            patch("app.worker.async_session_maker", return_value=cm),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "skipped"
        assert result["reason"] == "not_found"

    @pytest.mark.asyncio
    async def test_skip_completed(self):
        """File with extraction_status=completed is skipped."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file(extraction_status="completed")
        db = _make_db_returning(ff)
        cm = _make_session_cm(db)

        with (
            patch("app.worker.async_session_maker", return_value=cm),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "skipped"
        assert result["reason"] == "completed"

    @pytest.mark.asyncio
    async def test_skip_unsupported(self):
        """File with extraction_status=unsupported is skipped."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file(extraction_status="unsupported")
        db = _make_db_returning(ff)
        cm = _make_session_cm(db)

        with (
            patch("app.worker.async_session_maker", return_value=cm),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "skipped"
        assert result["reason"] == "unsupported"

    @pytest.mark.asyncio
    async def test_skip_processing(self):
        """File with extraction_status=processing is skipped (MED-7)."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file(extraction_status="processing")
        db = _make_db_returning(ff)
        cm = _make_session_cm(db)

        with (
            patch("app.worker.async_session_maker", return_value=cm),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "skipped"
        assert result["reason"] == "processing"

    @pytest.mark.asyncio
    async def test_extraction_failure_sets_failed(self):
        """Failed extraction sets extraction_status=failed with safe error category."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file()

        # Session 1: load + set processing
        db1 = _make_db_returning(ff)
        cm1 = _make_session_cm(db1)

        # Session 2: write failure
        ff2 = _make_mock_folder_file(id=ff.id)
        db2 = _make_db_returning(ff2)
        cm2 = _make_session_cm(db2)

        call_count = 0
        def session_factory():
            nonlocal call_count
            call_count += 1
            return cm1 if call_count == 1 else cm2

        mock_minio = _make_mock_minio()

        extraction_result = ExtractionResult(
            markdown="",
            success=False,
            error="Failed to parse PDF",
        )

        with (
            patch("app.worker.async_session_maker", side_effect=session_factory),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
            patch("app.services.minio_service.minio_service", mock_minio),
            patch(
                "app.ai.file_extraction_service.FileExtractionService.extract",
                new_callable=AsyncMock,
                return_value=extraction_result,
            ),
            patch("app.worker._broadcast_file_event", new_callable=AsyncMock),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "error"
        # CRIT-4: returns safe error category, not raw text
        assert result["error"] == "extraction_failed"
        assert ff2.extraction_status == "failed"
        assert ff2.extraction_error == "extraction_failed"

    @pytest.mark.asyncio
    async def test_extraction_timeout_sets_failed(self):
        """Extraction timeout returns timeout error category."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file()

        # Session 1: load + set processing
        db1 = _make_db_returning(ff)
        cm1 = _make_session_cm(db1)

        # Session 2: write failure (from outer except block)
        db2 = AsyncMock()
        db2.execute = AsyncMock()
        db2.commit = AsyncMock()
        cm2 = _make_session_cm(db2)

        call_count = 0
        def session_factory():
            nonlocal call_count
            call_count += 1
            return cm1 if call_count == 1 else cm2

        mock_minio = _make_mock_minio()

        with (
            patch("app.worker.async_session_maker", side_effect=session_factory),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
            patch("app.services.minio_service.minio_service", mock_minio),
            patch(
                "app.ai.file_extraction_service.FileExtractionService.extract",
                new_callable=AsyncMock,
                side_effect=asyncio.TimeoutError("Extraction timed out"),
            ),
            patch("app.worker._broadcast_file_event", new_callable=AsyncMock) as mock_broadcast,
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "error"
        # TimeoutError.__name__ is returned by the outer except block
        assert result["error"] == "TimeoutError"
        # Broadcast should be called with file_extraction_failed
        mock_broadcast.assert_called_once()
        broadcast_args = mock_broadcast.call_args
        assert broadcast_args[0][2] == "file_extraction_failed"

    @pytest.mark.asyncio
    async def test_successful_extraction_and_embedding(self):
        """Successful extraction + embedding returns success with exact counts."""
        from app.worker import extract_and_embed_file_job
        from app.ai.embedding_service import EmbedResult

        file_id = str(uuid4())
        ff = _make_mock_folder_file(file_extension="csv", display_name="data.csv",
                                     mime_type="text/csv",
                                     storage_key="folder-files/data.csv",
                                     file_size=256)

        # Session 1: load + set processing
        db1 = _make_db_returning(ff)
        cm1 = _make_session_cm(db1)

        # Session 2 (success path): re-load for final updates
        ff3 = _make_mock_folder_file(id=ff.id, file_extension="csv",
                                      display_name="data.csv", mime_type="text/csv")
        db3 = _make_db_returning(ff3)
        cm3 = _make_session_cm(db3)

        call_count = 0
        def session_factory():
            nonlocal call_count
            call_count += 1
            return cm1 if call_count == 1 else cm3

        mock_minio = _make_mock_minio(b"Name,Age\nAlice,30\n")

        extraction_result = ExtractionResult(
            markdown="| Name | Age |\n| --- | --- |\n| Alice | 30 |",
            success=True,
            metadata={"total_rows": 1},
        )

        embed_result = EmbedResult(chunk_count=2, token_count=50, duration_ms=100)

        with (
            patch("app.worker.async_session_maker", side_effect=session_factory),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
            patch("app.services.minio_service.minio_service", mock_minio),
            patch(
                "app.ai.file_extraction_service.FileExtractionService.extract",
                new_callable=AsyncMock,
                return_value=extraction_result,
            ),
            patch(
                "app.services.search_service.build_search_file_data",
                return_value={"id": "file_" + str(ff.id)},
            ),
            patch(
                "app.services.search_service.index_file_from_data",
                new_callable=AsyncMock,
            ),
            patch(
                "app.ai.embedding_service.EmbeddingService.embed_file",
                new_callable=AsyncMock,
                return_value=embed_result,
            ) as mock_embed,
            patch("app.worker._broadcast_file_event", new_callable=AsyncMock),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "success"
        assert result["extraction_status"] == "completed"
        # Exact count assertions (not weak >= 1)
        assert result["chunk_count"] == 2
        assert result["token_count"] == 50
        assert result["duration_ms"] == 100

        # Verify embed_file was called with the file_uuid parsed from file_id string
        mock_embed.assert_called_once()
        embed_kwargs = mock_embed.call_args
        from uuid import UUID as _UUID
        assert embed_kwargs[1]["file_id"] == _UUID(file_id)

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Exceeding max retries sets extraction_status=failed."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis.get = AsyncMock(return_value="3")  # At max
        mock_redis.set = AsyncMock()

        mock_err_db = AsyncMock()
        mock_err_db.execute = AsyncMock()
        mock_err_db.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_err_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.worker.async_session_maker", return_value=mock_cm),
            patch("app.worker.redis_service", mock_redis),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "error"
        assert result["error"] == "max_retries_exceeded"

    @pytest.mark.asyncio
    async def test_minio_download_failure(self):
        """MinIO download failure returns error with safe category."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file()

        # Session 1: load + set processing
        db1 = _make_db_returning(ff)
        cm1 = _make_session_cm(db1)

        # Session 2: error-path session
        mock_err_db = AsyncMock()
        mock_err_db.execute = AsyncMock()
        mock_err_db.commit = AsyncMock()
        cm2 = _make_session_cm(mock_err_db)

        call_count = 0
        def session_factory():
            nonlocal call_count
            call_count += 1
            return cm1 if call_count == 1 else cm2

        mock_minio = MagicMock()
        mock_minio.download_to_file.side_effect = Exception("Connection refused")

        with (
            patch("app.worker.async_session_maker", side_effect=session_factory),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
            patch("app.services.minio_service.minio_service", mock_minio),
            patch("app.worker._broadcast_file_event", new_callable=AsyncMock),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "error"
        assert result["error"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_extraction_success_embedding_failure_non_fatal(self):
        """Embedding failure is non-fatal; extraction result still committed."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file()

        # Session 1: load + set processing
        db1 = _make_db_returning(ff)
        cm1 = _make_session_cm(db1)

        # Session 2 (success path): re-load for final updates
        ff3 = _make_mock_folder_file(id=ff.id)
        db3 = _make_db_returning(ff3)
        cm3 = _make_session_cm(db3)

        call_count = 0
        def session_factory():
            nonlocal call_count
            call_count += 1
            return cm1 if call_count == 1 else cm3

        mock_minio = _make_mock_minio(b"fake pdf")

        extraction_result = ExtractionResult(
            markdown="# Document Title\n\nSome content here.",
            success=True,
        )

        with (
            patch("app.worker.async_session_maker", side_effect=session_factory),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
            patch("app.services.minio_service.minio_service", mock_minio),
            patch(
                "app.ai.file_extraction_service.FileExtractionService.extract",
                new_callable=AsyncMock,
                return_value=extraction_result,
            ),
            patch(
                "app.services.search_service.build_search_file_data",
                return_value={"id": "file_" + str(ff.id)},
            ),
            patch(
                "app.services.search_service.index_file_from_data",
                new_callable=AsyncMock,
            ),
            patch(
                "app.ai.embedding_service.EmbeddingService.embed_file",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Provider unavailable"),
            ),
            patch("app.worker._broadcast_file_event", new_callable=AsyncMock),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        # Extraction succeeded despite embedding failure
        assert result["status"] == "success"
        assert result["extraction_status"] == "completed"
        assert ff3.extraction_status == "completed"
        assert ff3.embedding_status == "failed"

    @pytest.mark.asyncio
    async def test_content_plain_truncated_at_2mb(self):
        """Content exceeding MAX_CONTENT_PLAIN (2MB) is truncated (HIGH-10)."""
        from app.worker import extract_and_embed_file_job

        file_id = str(uuid4())
        ff = _make_mock_folder_file()

        db1 = _make_db_returning(ff)
        cm1 = _make_session_cm(db1)

        ff3 = _make_mock_folder_file(id=ff.id)
        db3 = _make_db_returning(ff3)
        cm3 = _make_session_cm(db3)

        call_count = 0
        def session_factory():
            nonlocal call_count
            call_count += 1
            return cm1 if call_count == 1 else cm3

        mock_minio = _make_mock_minio(b"fake pdf")

        # 3MB of content should be truncated to 2MB
        large_content = "x" * 3_000_000
        extraction_result = ExtractionResult(
            markdown=large_content,
            success=True,
        )

        with (
            patch("app.worker.async_session_maker", side_effect=session_factory),
            patch("app.worker.redis_service", MagicMock(is_connected=False)),
            patch("app.services.minio_service.minio_service", mock_minio),
            patch(
                "app.ai.file_extraction_service.FileExtractionService.extract",
                new_callable=AsyncMock,
                return_value=extraction_result,
            ),
            patch(
                "app.services.search_service.build_search_file_data",
                return_value={"id": "file_" + str(ff.id)},
            ),
            patch(
                "app.services.search_service.index_file_from_data",
                new_callable=AsyncMock,
            ),
            patch(
                "app.ai.embedding_service.EmbeddingService.embed_file",
                new_callable=AsyncMock,
                side_effect=RuntimeError("skip embed"),
            ),
            patch("app.worker._broadcast_file_event", new_callable=AsyncMock),
        ):
            result = await extract_and_embed_file_job({}, file_id)

        assert result["status"] == "success"
        # Verify content was truncated
        assert len(ff3.content_plain) == 2_000_000


# ============================================================================
# _broadcast_file_event Tests
# ============================================================================


class TestBroadcastFileEvent:
    """Tests for _broadcast_file_event helper."""

    @pytest.mark.asyncio
    async def test_broadcast_app_scope(self):
        """Application-scoped file broadcasts to application room."""
        from app.worker import _broadcast_file_event

        app_id = uuid4()
        scope = {"application_id": app_id, "project_id": None, "user_id": None}

        with patch("app.worker.redis_service") as mock_redis:
            mock_redis.publish = AsyncMock()
            await _broadcast_file_event(scope, str(uuid4()), "file_extraction_completed", {})

            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert call_args[0][0] == "ws:broadcast"
            payload = call_args[0][1]
            assert payload["room_id"] == f"application:{app_id}"

    @pytest.mark.asyncio
    async def test_broadcast_user_scope(self):
        """User-scoped file broadcasts to user room."""
        from app.worker import _broadcast_file_event

        user_id = uuid4()
        scope = {"application_id": None, "project_id": None, "user_id": user_id}

        with patch("app.worker.redis_service") as mock_redis:
            mock_redis.publish = AsyncMock()
            await _broadcast_file_event(scope, str(uuid4()), "file_extraction_completed", {})

            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            payload = call_args[0][1]
            assert payload["room_id"] == f"user:{user_id}"

    @pytest.mark.asyncio
    async def test_broadcast_none_scope(self):
        """None scope is a no-op."""
        from app.worker import _broadcast_file_event

        with patch("app.worker.redis_service") as mock_redis:
            mock_redis.publish = AsyncMock()
            await _broadcast_file_event(None, str(uuid4()), "file_extraction_completed", {})

            mock_redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_includes_folder_id(self):
        """CRIT-2: Broadcast payload includes folder_id."""
        from app.worker import _broadcast_file_event

        app_id = uuid4()
        folder_id = uuid4()
        scope = {"application_id": app_id, "project_id": None, "user_id": None}

        with patch("app.worker.redis_service") as mock_redis:
            mock_redis.publish = AsyncMock()
            await _broadcast_file_event(
                scope, str(uuid4()), "file_extraction_completed",
                {"folder_id": str(folder_id)},
            )

            mock_redis.publish.assert_called_once()
            payload = mock_redis.publish.call_args[0][1]
            assert payload["message"]["data"]["folder_id"] == str(folder_id)


# ============================================================================
# _categorize_extraction_error Tests
# ============================================================================


class TestCategorizeExtractionError:
    """Tests for _categorize_extraction_error helper (CRIT-4)."""

    def test_none_returns_extraction_failed(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error(None) == "extraction_failed"

    def test_empty_string_returns_extraction_failed(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error("") == "extraction_failed"

    def test_password_detected(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error("File is password protected") == "password_protected"

    def test_encrypted_detected(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error("Encrypted file format") == "password_protected"

    def test_corrupt_detected(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error("File is corrupt") == "corrupt_file"

    def test_badzipfile_detected(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error("BadZipFile: not a zip file") == "corrupt_file"

    def test_timeout_detected(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error("Extraction timeout after 120s") == "extraction_timeout"

    def test_unknown_error_returns_extraction_failed(self):
        from app.worker import _categorize_extraction_error
        assert _categorize_extraction_error("Some random error") == "extraction_failed"


# ============================================================================
# Worker Registration Tests
# ============================================================================


class TestWorkerRegistration:
    """Tests that extract_and_embed_file_job is registered in WorkerSettings."""

    def test_job_registered(self):
        """extract_and_embed_file_job should be in WorkerSettings.functions."""
        from app.worker import WorkerSettings

        function_names = [f.__name__ for f in WorkerSettings.functions]
        assert "extract_and_embed_file_job" in function_names

"""Tests for process_document_import background worker function.

Covers the full import pipeline from job lookup through Docling conversion,
Document creation, image processing, embedding enqueue, WebSocket broadcast,
and temp file cleanup. All external dependencies are mocked: database session,
DoclingService, ImageUnderstandingService, arq, Redis pub/sub.

Mocks the Docling/docling_core modules at import time (same pattern as
test_docling_service.py) so imports resolve without the real library.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch
from uuid import UUID, uuid4

import pytest

# ---------------------------------------------------------------------------
# Mock Docling modules BEFORE importing worker (which lazy-imports
# DoclingService). Same pattern as test_docling_service.py.
# ---------------------------------------------------------------------------

_mock_InputFormat = MagicMock()
_mock_InputFormat.PDF = "pdf"
_mock_InputFormat.DOCX = "docx"
_mock_InputFormat.PPTX = "pptx"

_mock_ConversionStatus = MagicMock()
_mock_ConversionStatus.SUCCESS = "SUCCESS"

_mock_PictureItem = type("PictureItem", (), {})

_mock_base_models = MagicMock()
_mock_base_models.ConversionStatus = _mock_ConversionStatus
_mock_base_models.InputFormat = _mock_InputFormat

_mock_pipeline_options = MagicMock()
_mock_document_converter_mod = MagicMock()
_mock_docling_core_types = MagicMock()
_mock_docling_core_types.PictureItem = _mock_PictureItem

sys.modules.setdefault("docling", MagicMock())
sys.modules.setdefault("docling.datamodel", MagicMock())
sys.modules.setdefault("docling.datamodel.base_models", _mock_base_models)
sys.modules.setdefault("docling.datamodel.pipeline_options", _mock_pipeline_options)
sys.modules.setdefault("docling.document_converter", _mock_document_converter_mod)
sys.modules.setdefault("docling_core", MagicMock())
sys.modules.setdefault("docling_core.types", MagicMock())
sys.modules.setdefault("docling_core.types.doc", _mock_docling_core_types)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = uuid4()
_JOB_ID = uuid4()
_DOC_ID = uuid4()
_APP_ID = uuid4()
_FOLDER_ID = uuid4()


def _make_import_job(
    *,
    job_id: UUID = _JOB_ID,
    user_id: UUID = _USER_ID,
    file_name: str = "report.pdf",
    file_type: str = "pdf",
    file_size: int = 12345,
    title: str | None = None,
    status: str = "pending",
    progress_pct: int = 0,
    scope: str = "application",
    scope_id: UUID = _APP_ID,
    folder_id: UUID | None = _FOLDER_ID,
    temp_file_path: str | None = "/tmp/import_abc123.pdf",
    document_id: UUID | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> MagicMock:
    """Build a mock ImportJob object with the given attributes."""
    job = MagicMock()
    job.id = job_id
    job.user_id = user_id
    job.file_name = file_name
    job.file_type = file_type
    job.file_size = file_size
    job.title = title
    job.status = status
    job.progress_pct = progress_pct
    job.scope = scope
    job.scope_id = scope_id
    job.folder_id = folder_id
    job.temp_file_path = temp_file_path
    job.document_id = document_id
    job.error_message = error_message
    job.completed_at = completed_at
    return job


def _make_process_result(
    markdown: str = "# Title\n\nHello world",
    images: list | None = None,
    metadata: dict | None = None,
    warnings: list | None = None,
) -> MagicMock:
    """Build a mock DoclingService.process_file() return value (ProcessResult)."""
    result = MagicMock()
    result.markdown = markdown
    result.images = images or []
    result.metadata = metadata or {"title_from_doc": None, "page_count": 1, "word_count": 5}
    result.warnings = warnings or []
    return result


def _make_extracted_image(
    image_bytes: bytes = b"\x89PNG_FAKE",
    image_format: str = "png",
    page_number: int = 1,
    position: int = 0,
    caption: str | None = "Figure 1",
) -> MagicMock:
    """Build a mock ExtractedImage for the process result."""
    img = MagicMock()
    img.image_bytes = image_bytes
    img.image_format = image_format
    img.page_number = page_number
    img.position = position
    img.caption = caption
    return img


# ---------------------------------------------------------------------------
# Session factory mock builder
# ---------------------------------------------------------------------------


def _build_session_and_factory(job: MagicMock | None) -> tuple[MagicMock, MagicMock]:
    """Return (mock_session, mock_session_maker) that yields the session.

    The session.execute().scalar_one_or_none() will return *job*.
    After db.flush() + db.refresh(), doc.id is set.
    """
    mock_session = AsyncMock()

    # select(ImportJob) → scalar_one_or_none → job
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()

    # db.refresh(doc) should set doc.id
    async def _fake_refresh(obj: Any) -> None:
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = _DOC_ID

    mock_session.refresh = AsyncMock(side_effect=_fake_refresh)
    mock_session.add = MagicMock()

    # Make session work as async context manager
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)
    return mock_session, mock_factory


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProcessDocumentImport:
    """Tests for app.worker.process_document_import."""

    # -----------------------------------------------------------------------
    # 1. Happy path: full pipeline success
    # -----------------------------------------------------------------------

    async def test_happy_path_full_pipeline(self) -> None:
        """Job loaded, Docling converts, Document created, images processed,
        embedding enqueued, job marked completed with document_id."""
        job = _make_import_job(title=None)
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(
            markdown="# Converted\n\nBody text.",
            metadata={"title_from_doc": None, "page_count": 2, "word_count": 10},
        )

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks") as mock_set_scope,
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "completed"
        assert result["document_id"] == str(_DOC_ID)
        assert result["title"] == "report"  # filename stem, since no user or metadata title

        # Job status was set to processing, then completed
        assert job.status == "completed"
        assert job.progress_pct == 100
        assert job.document_id == _DOC_ID
        assert job.completed_at is not None

        # Document was added to session
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called()

        # set_scope_fks called with correct params
        mock_set_scope.assert_called_once()

        # Embedding enqueued
        mock_redis_pool.enqueue_job.assert_called_once()
        enqueue_call = mock_redis_pool.enqueue_job.call_args
        assert enqueue_call[0][0] == "embed_document_job"

        # WebSocket IMPORT_COMPLETED broadcast
        mock_redis_service.publish.assert_called_once()
        publish_call = mock_redis_service.publish.call_args
        assert publish_call[0][0] == f"user:{_USER_ID}"
        assert publish_call[0][1]["type"] == "import_completed"
        assert publish_call[0][1]["data"]["job_id"] == str(_JOB_ID)
        assert publish_call[0][1]["data"]["document_id"] == str(_DOC_ID)

        # Temp file cleanup
        mock_cleanup.assert_called_once_with("/tmp/import_abc123.pdf")

    # -----------------------------------------------------------------------
    # 2. Job not found
    # -----------------------------------------------------------------------

    async def test_job_not_found_returns_skipped(self) -> None:
        """job_id doesn't exist -> returns {"status": "skipped", "reason": "not_found"}."""
        mock_session, mock_factory = _build_session_and_factory(None)

        with (
            patch("app.worker.async_session_maker", mock_factory),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(uuid4()))

        assert result["status"] == "skipped"
        assert result["reason"] == "not_found"

    # -----------------------------------------------------------------------
    # 3. Temp file missing
    # -----------------------------------------------------------------------

    async def test_temp_file_missing_marks_failed(self) -> None:
        """temp_file_path doesn't exist -> job marked 'failed' with error."""
        job = _make_import_job(temp_file_path="/tmp/gone.pdf")

        # We need TWO session calls: first for the main try block, second for
        # the error handler. Both need to return a session that returns the job.
        mock_session_1, _ = _build_session_and_factory(job)
        mock_session_2, _ = _build_session_and_factory(job)

        call_count = [0]
        sessions = [mock_session_1, mock_session_2]

        def factory_side_effect():
            idx = min(call_count[0], len(sessions) - 1)
            call_count[0] += 1
            return sessions[idx]

        mock_factory = MagicMock(side_effect=factory_side_effect)

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=False),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", mock_redis_service),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "error"
        assert "FileNotFoundError" in result["error"]

        # Job should be marked failed in the error handler (fresh query in except block)
        # The error handler uses safe_messages mapping for user-facing text
        assert job.status == "failed"
        assert job.error_message is not None
        assert "could not be found" in job.error_message.lower()

        # IMPORT_FAILED broadcast
        mock_redis_service.publish.assert_called()
        last_publish = mock_redis_service.publish.call_args
        assert last_publish[0][1]["type"] == "import_failed"

        # Temp file cleanup attempted (even on failure path)
        mock_cleanup.assert_called_once_with("/tmp/gone.pdf")

    # -----------------------------------------------------------------------
    # 4. Temp file path is None
    # -----------------------------------------------------------------------

    async def test_temp_file_path_none_marks_failed(self) -> None:
        """temp_file_path is None -> FileNotFoundError, job marked 'failed'."""
        job = _make_import_job(temp_file_path=None)

        mock_session_1, _ = _build_session_and_factory(job)
        mock_session_2, _ = _build_session_and_factory(job)

        call_count = [0]
        sessions = [mock_session_1, mock_session_2]

        def factory_side_effect():
            idx = min(call_count[0], len(sessions) - 1)
            call_count[0] += 1
            return sessions[idx]

        mock_factory = MagicMock(side_effect=factory_side_effect)

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", mock_redis_service),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "error"
        assert job.status == "failed"

        # Cleanup should NOT be called with None (guarded by `if temp_path:`)
        mock_cleanup.assert_not_called()

    # -----------------------------------------------------------------------
    # 5. Docling conversion failure
    # -----------------------------------------------------------------------

    async def test_docling_failure_marks_job_failed(self) -> None:
        """DoclingService.process_file raises ImportError -> job marked 'failed'."""
        job = _make_import_job()

        mock_session_1, _ = _build_session_and_factory(job)
        mock_session_2, _ = _build_session_and_factory(job)

        call_count = [0]
        sessions = [mock_session_1, mock_session_2]

        def factory_side_effect():
            idx = min(call_count[0], len(sessions) - 1)
            call_count[0] += 1
            return sessions[idx]

        mock_factory = MagicMock(side_effect=factory_side_effect)

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(side_effect=ImportError("Password-protected PDF not supported"))

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "error"
        assert result["error"] == "ImportError"

        assert job.status == "failed"
        # Worker uses safe_messages mapping: ImportError -> user-friendly message
        assert job.error_message is not None
        assert "could not be converted" in job.error_message.lower()

        # IMPORT_FAILED broadcast
        mock_redis_service.publish.assert_called()
        last_publish = mock_redis_service.publish.call_args
        assert last_publish[0][1]["type"] == "import_failed"

        mock_cleanup.assert_called_once_with("/tmp/import_abc123.pdf")

    # -----------------------------------------------------------------------
    # 6. Image processing fails (non-fatal)
    # -----------------------------------------------------------------------

    async def test_image_processing_failure_is_nonfatal(self) -> None:
        """ImageUnderstandingService raises -> job still completes, images skipped."""
        img = _make_extracted_image()
        job = _make_import_job()
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(
            markdown="# Doc\n\nWith image.",
            images=[img],
        )

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        # ImageUnderstandingService will raise inside the try/except
        mock_image_svc = MagicMock()
        mock_image_svc.process_imported_images = AsyncMock(side_effect=RuntimeError("Vision LLM unavailable"))

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
            patch("app.ai.image_understanding_service.ImageUnderstandingService", return_value=mock_image_svc),
            patch("app.ai.provider_registry.ProviderRegistry", return_value=MagicMock()),
            patch("app.ai.embedding_normalizer.EmbeddingNormalizer", return_value=MagicMock()),
            patch("app.ai.chunking_service.SemanticChunker", return_value=MagicMock()),
            patch("app.ai.embedding_service.EmbeddingService", return_value=MagicMock()),
            patch("app.services.minio_service.minio_service", MagicMock()),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        # Job still completed despite image failure
        assert result["status"] == "completed"
        assert result["document_id"] == str(_DOC_ID)
        assert job.status == "completed"
        assert job.progress_pct == 100

        # IMPORT_COMPLETED (not IMPORT_FAILED)
        mock_redis_service.publish.assert_called_once()
        assert mock_redis_service.publish.call_args[0][1]["type"] == "import_completed"

        mock_cleanup.assert_called_once()

    # -----------------------------------------------------------------------
    # 7. Embed enqueue fails (non-fatal)
    # -----------------------------------------------------------------------

    async def test_embed_enqueue_failure_is_nonfatal(self) -> None:
        """arq create_pool raises -> job still completes."""
        job = _make_import_job()
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(markdown="# Doc\n\nBody.")

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, side_effect=ConnectionError("Redis down")),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        # Job completed despite embed failure
        assert result["status"] == "completed"
        assert job.status == "completed"
        assert job.progress_pct == 100

        mock_cleanup.assert_called_once()

    # -----------------------------------------------------------------------
    # 8. Title priority: user title > metadata title > filename stem
    # -----------------------------------------------------------------------

    async def test_title_priority_user_title_wins(self) -> None:
        """When user provides a title, it takes priority over metadata and filename."""
        job = _make_import_job(title="My Custom Title", file_name="boring_name.pdf")
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(
            metadata={"title_from_doc": "Metadata Title", "page_count": 1, "word_count": 5},
        )

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "completed"
        assert result["title"] == "My Custom Title"

    async def test_title_priority_metadata_over_filename(self) -> None:
        """When no user title, metadata title takes priority over filename stem."""
        job = _make_import_job(title=None, file_name="boring_name.pdf")
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(
            metadata={"title_from_doc": "Document Metadata Title", "page_count": 1, "word_count": 5},
        )

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "completed"
        assert result["title"] == "Document Metadata Title"

    async def test_title_priority_filename_stem_fallback(self) -> None:
        """When no user title and no metadata title, filename stem is used."""
        job = _make_import_job(title=None, file_name="quarterly_report_2026.pdf")
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(
            metadata={"title_from_doc": None, "page_count": 1, "word_count": 5},
        )

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "completed"
        assert result["title"] == "quarterly_report_2026"

    # -----------------------------------------------------------------------
    # 9. WebSocket broadcast on success
    # -----------------------------------------------------------------------

    async def test_websocket_broadcast_on_success(self) -> None:
        """IMPORT_COMPLETED published to redis on success with correct channel and data."""
        job = _make_import_job()
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result()

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            await process_document_import({}, str(_JOB_ID))

        mock_redis_service.publish.assert_called_once()
        channel, payload = mock_redis_service.publish.call_args[0]
        assert channel == f"user:{_USER_ID}"
        assert payload["type"] == "import_completed"
        assert "document_id" in payload["data"]
        assert "title" in payload["data"]
        assert payload["data"]["job_id"] == str(_JOB_ID)

    # -----------------------------------------------------------------------
    # 10. WebSocket broadcast on failure
    # -----------------------------------------------------------------------

    async def test_websocket_broadcast_on_failure(self) -> None:
        """IMPORT_FAILED published to redis when pipeline fails."""
        job = _make_import_job()

        mock_session_1, _ = _build_session_and_factory(job)
        mock_session_2, _ = _build_session_and_factory(job)

        call_count = [0]
        sessions = [mock_session_1, mock_session_2]

        def factory_side_effect():
            idx = min(call_count[0], len(sessions) - 1)
            call_count[0] += 1
            return sessions[idx]

        mock_factory = MagicMock(side_effect=factory_side_effect)

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(side_effect=RuntimeError("Conversion crashed"))

        mock_redis_service = AsyncMock()
        mock_redis_service.publish = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", mock_redis_service),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "error"

        # IMPORT_FAILED was broadcast
        mock_redis_service.publish.assert_called()
        last_publish = mock_redis_service.publish.call_args
        channel, payload = last_publish[0]
        assert channel == f"user:{_USER_ID}"
        assert payload["type"] == "import_failed"
        assert "error_message" in payload["data"]
        assert payload["data"]["job_id"] == str(_JOB_ID)

    # -----------------------------------------------------------------------
    # 11. Temp file cleanup on success
    # -----------------------------------------------------------------------

    async def test_temp_file_cleanup_on_success(self) -> None:
        """_cleanup_temp_file called with the correct path after successful pipeline."""
        job = _make_import_job(temp_file_path="/tmp/success_cleanup.pdf")
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result()

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", AsyncMock()),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            await process_document_import({}, str(_JOB_ID))

        mock_cleanup.assert_called_once_with("/tmp/success_cleanup.pdf")

    # -----------------------------------------------------------------------
    # 12. Temp file cleanup on failure
    # -----------------------------------------------------------------------

    async def test_temp_file_cleanup_on_failure(self) -> None:
        """_cleanup_temp_file called in error path with temp_path."""
        job = _make_import_job(temp_file_path="/tmp/failure_cleanup.pdf")

        mock_session_1, _ = _build_session_and_factory(job)
        mock_session_2, _ = _build_session_and_factory(job)

        call_count = [0]
        sessions = [mock_session_1, mock_session_2]

        def factory_side_effect():
            idx = min(call_count[0], len(sessions) - 1)
            call_count[0] += 1
            return sessions[idx]

        mock_factory = MagicMock(side_effect=factory_side_effect)

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(side_effect=RuntimeError("Kaboom"))

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file") as mock_cleanup,
            patch("app.worker.redis_service", AsyncMock()),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
        ):
            from app.worker import process_document_import

            await process_document_import({}, str(_JOB_ID))

        mock_cleanup.assert_called_once_with("/tmp/failure_cleanup.pdf")

    # -----------------------------------------------------------------------
    # 13. No images: image processing block skipped
    # -----------------------------------------------------------------------

    async def test_no_images_skips_image_processing(self) -> None:
        """When no images extracted, ImageUnderstandingService is never imported."""
        job = _make_import_job()
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(
            markdown="# No Images\n\nJust text.",
            images=[],  # No images
        )

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", AsyncMock()),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "completed"

    # -----------------------------------------------------------------------
    # 14. Already completed/failed job is skipped
    # -----------------------------------------------------------------------

    async def test_already_completed_job_is_skipped(self) -> None:
        """Job with status 'completed' returns skipped with reason."""
        job = _make_import_job(status="completed")
        mock_session, mock_factory = _build_session_and_factory(job)

        with (
            patch("app.worker.async_session_maker", mock_factory),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "skipped"
        assert result["reason"] == "completed"

    async def test_already_failed_job_is_skipped(self) -> None:
        """Job with status 'failed' returns skipped with reason."""
        job = _make_import_job(status="failed")
        mock_session, mock_factory = _build_session_and_factory(job)

        with (
            patch("app.worker.async_session_maker", mock_factory),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "skipped"
        assert result["reason"] == "failed"

    # -----------------------------------------------------------------------
    # 15. Error message uses safe user-facing messages
    # -----------------------------------------------------------------------

    async def test_error_message_uses_safe_user_facing_text(self) -> None:
        """Error messages stored on job use safe_messages mapping, not raw exception text."""
        job = _make_import_job()

        mock_session_1, _ = _build_session_and_factory(job)
        mock_session_2, _ = _build_session_and_factory(job)

        call_count = [0]
        sessions = [mock_session_1, mock_session_2]

        def factory_side_effect():
            idx = min(call_count[0], len(sessions) - 1)
            call_count[0] += 1
            return sessions[idx]

        mock_factory = MagicMock(side_effect=factory_side_effect)

        # Use a generic RuntimeError (not in safe_messages mapping)
        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(side_effect=RuntimeError("Internal details should not leak"))

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", AsyncMock()),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
        ):
            from app.worker import process_document_import

            await process_document_import({}, str(_JOB_ID))

        assert job.error_message is not None
        # Should be the generic safe message, NOT the raw exception text
        assert "unexpected error" in job.error_message.lower()
        assert "Internal details" not in job.error_message

    # -----------------------------------------------------------------------
    # 15. Document content_json is valid TipTap JSON
    # -----------------------------------------------------------------------

    async def test_document_content_json_is_valid_tiptap(self) -> None:
        """The created Document has valid TipTap JSON structure."""
        job = _make_import_job()
        mock_session, mock_factory = _build_session_and_factory(job)

        process_result = _make_process_result(
            markdown="# Heading\n\nParagraph text.\n\n- Bullet one\n- Bullet two",
        )

        mock_docling_instance = AsyncMock()
        mock_docling_instance.process_file = AsyncMock(return_value=process_result)

        mock_redis_pool = AsyncMock()
        mock_redis_pool.enqueue_job = AsyncMock()
        mock_redis_pool.aclose = AsyncMock()

        added_docs: list = []
        original_add = mock_session.add

        def capture_add(obj: Any) -> None:
            added_docs.append(obj)

        mock_session.add = MagicMock(side_effect=capture_add)

        with (
            patch("app.worker.async_session_maker", mock_factory),
            patch("app.worker.os.path.exists", return_value=True),
            patch("app.worker.os.chmod"),
            patch("app.worker._cleanup_temp_file"),
            patch("app.worker.redis_service", AsyncMock()),
            patch("app.ai.docling_service.DoclingService", return_value=mock_docling_instance),
            patch("arq.connections.create_pool", new_callable=AsyncMock, return_value=mock_redis_pool),
            patch("app.worker.parse_redis_url", return_value=MagicMock()),
            patch("app.services.document_service.set_scope_fks"),
        ):
            from app.worker import process_document_import

            result = await process_document_import({}, str(_JOB_ID))

        assert result["status"] == "completed"
        assert len(added_docs) == 1

        doc = added_docs[0]
        content = json.loads(doc.content_json)
        assert content["type"] == "doc"
        assert isinstance(content["content"], list)
        assert len(content["content"]) > 0

        # Should have heading + paragraph + bulletList
        types = [node["type"] for node in content["content"]]
        assert "heading" in types
        assert "paragraph" in types
        assert "bulletList" in types


# ---------------------------------------------------------------------------
# Tests for _cleanup_temp_file helper
# ---------------------------------------------------------------------------


class TestCleanupTempFile:
    """Tests for the _cleanup_temp_file helper."""

    def test_removes_existing_file(self) -> None:
        """Removes file if it exists."""
        with patch("app.worker.os.remove") as mock_remove:
            from app.worker import _cleanup_temp_file

            _cleanup_temp_file("/tmp/some_file.pdf")
            mock_remove.assert_called_once_with("/tmp/some_file.pdf")

    def test_no_error_on_missing_file(self) -> None:
        """Silently ignores OSError when file doesn't exist."""
        with patch("app.worker.os.remove", side_effect=OSError("No such file")):
            from app.worker import _cleanup_temp_file

            # Should not raise
            _cleanup_temp_file("/tmp/nonexistent.pdf")

    def test_none_path_is_noop(self) -> None:
        """None path does nothing."""
        with patch("app.worker.os.remove") as mock_remove:
            from app.worker import _cleanup_temp_file

            _cleanup_temp_file(None)
            mock_remove.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for markdown_to_tiptap_json helper
# ---------------------------------------------------------------------------


class TestMarkdownToTiptapJson:
    """Tests for the markdown_to_tiptap_json conversion used in the pipeline."""

    def test_empty_markdown_returns_empty_doc(self) -> None:
        """Empty string produces a doc with a single empty paragraph."""
        from app.worker import markdown_to_tiptap_json

        result = markdown_to_tiptap_json("")
        assert result["type"] == "doc"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "paragraph"

    def test_heading_and_paragraph(self) -> None:
        """Heading + paragraph produce correct TipTap nodes."""
        from app.worker import markdown_to_tiptap_json

        result = markdown_to_tiptap_json("# Title\n\nSome text.")
        types = [n["type"] for n in result["content"]]
        assert "heading" in types
        assert "paragraph" in types

    def test_code_block(self) -> None:
        """Fenced code block produces codeBlock node."""
        from app.worker import markdown_to_tiptap_json

        md = "```\nprint('hello')\n```"
        result = markdown_to_tiptap_json(md)
        types = [n["type"] for n in result["content"]]
        assert "codeBlock" in types

    def test_horizontal_rule(self) -> None:
        """--- produces horizontalRule node."""
        from app.worker import markdown_to_tiptap_json

        result = markdown_to_tiptap_json("---")
        types = [n["type"] for n in result["content"]]
        assert "horizontalRule" in types

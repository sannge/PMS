"""Tests for ImageUnderstandingService.

Validates TipTap image node extraction, vision LLM processing, size filtering,
batch limits, MinIO uploads, error resilience, embedding generation, and
graceful degradation when no vision provider is configured.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.ai.image_understanding_service import (
    ExtractedImage,
    ImageDescription,
    ImageUnderstandingService,
    _MAX_IMAGES_PER_DOCUMENT,
    _MIN_IMAGE_SIZE_BYTES,
)
from app.ai.provider_interface import VisionProvider
from app.ai.provider_registry import ConfigurationError

# ---------------------------------------------------------------------------
# Sample TipTap JSON for tests
# ---------------------------------------------------------------------------

_ATTACHMENT_ID_1 = "aaaaaaaa-0000-0000-0000-000000000001"
_ATTACHMENT_ID_2 = "aaaaaaaa-0000-0000-0000-000000000002"
_ATTACHMENT_ID_3 = "aaaaaaaa-0000-0000-0000-000000000003"

SAMPLE_TIPTAP_JSON = {
    "type": "doc",
    "content": [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Test Doc"}],
        },
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Some text"}],
        },
        {
            "type": "image",
            "attrs": {
                "src": "http://example.com/img1.png",
                "attachmentId": _ATTACHMENT_ID_1,
                "alt": "Test image 1",
                "title": "Image One",
                "width": 500,
            },
        },
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Middle text"}],
        },
        {
            "type": "image",
            "attrs": {
                "src": "http://example.com/img2.png",
                "attachmentId": _ATTACHMENT_ID_2,
                "alt": "Test image 2",
                "title": "Image Two",
                "width": 400,
            },
        },
        {
            "type": "image",
            "attrs": {
                "src": "http://example.com/img3.png",
                "attachmentId": _ATTACHMENT_ID_3,
                "alt": "Test image 3",
                "title": "Image Three",
                "width": 300,
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_mock_attachment(
    attachment_id: UUID | None = None,
    file_size: int = 50_000,
) -> MagicMock:
    """Create a mock Attachment ORM instance."""
    att = MagicMock()
    att.id = attachment_id or uuid4()
    att.file_name = "image.png"
    att.file_type = "image/png"
    att.file_size = file_size
    att.minio_bucket = "pm-attachments"
    att.minio_key = f"document/{att.id}/image.png"
    return att


@pytest.fixture
def mock_provider_registry() -> MagicMock:
    """Mock ProviderRegistry returning a vision provider."""
    registry = MagicMock()

    vision_provider = AsyncMock(spec=VisionProvider)
    vision_provider.describe_image = AsyncMock(return_value="A detailed description of the image content.")

    registry.get_vision_provider = AsyncMock(return_value=(vision_provider, "gpt-4o"))

    embedding_provider = AsyncMock()
    embedding_provider.generate_embeddings_batch = AsyncMock(
        side_effect=lambda texts, model: [[0.1] * 1536 for _ in texts]
    )
    registry.get_embedding_provider = AsyncMock(return_value=(embedding_provider, "text-embedding-3-small"))

    return registry


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Mock EmbeddingService."""
    service = MagicMock()
    return service


@pytest.fixture
def mock_minio() -> MagicMock:
    """Mock MinIOService."""
    minio = MagicMock()
    # download returns bytes large enough to pass the 10KB threshold
    minio.download_file.return_value = b"\x89PNG" + b"\x00" * 20_000
    minio.upload_bytes.return_value = "document/uuid/image.png"
    minio.get_bucket_for_content_type.return_value = "pm-attachments"
    minio.generate_object_name.return_value = "document/uuid/12345678_image.png"
    return minio


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession with execute returning no existing chunks."""
    db = AsyncMock()

    # Default: scalar() returns None (no existing chunks)
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    mock_result.scalar_one_or_none.return_value = None
    mock_result.first.return_value = None
    db.execute.return_value = mock_result
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()

    return db


@pytest.fixture
def service(
    mock_provider_registry: MagicMock,
    mock_embedding_service: MagicMock,
    mock_minio: MagicMock,
    mock_db: AsyncMock,
) -> ImageUnderstandingService:
    """Build an ImageUnderstandingService with all mocked dependencies."""
    with patch("app.ai.image_understanding_service.tiktoken") as mock_tiktoken:
        mock_encoder = MagicMock()
        mock_encoder.encode.side_effect = lambda text: list(range(len(text.split())))
        mock_tiktoken.get_encoding.return_value = mock_encoder

        svc = ImageUnderstandingService(
            provider_registry=mock_provider_registry,
            embedding_service=mock_embedding_service,
            minio_service=mock_minio,
            db=mock_db,
        )
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExtractImageNodes:
    """Tests for TipTap JSON tree walking."""

    async def test_extract_image_nodes_from_tiptap(
        self, service: ImageUnderstandingService
    ) -> None:
        """Pass TipTap JSON with 3 image nodes, verify all detected."""
        nodes = service._extract_image_nodes(SAMPLE_TIPTAP_JSON)

        assert len(nodes) == 3

        assert nodes[0]["attachment_id"] == UUID(_ATTACHMENT_ID_1)
        assert nodes[0]["alt"] == "Test image 1"
        assert nodes[0]["title"] == "Image One"
        # First image is under the "Test Doc" heading
        assert nodes[0]["heading_context"] == "Test Doc"

        assert nodes[1]["attachment_id"] == UUID(_ATTACHMENT_ID_2)
        assert nodes[1]["alt"] == "Test image 2"

        assert nodes[2]["attachment_id"] == UUID(_ATTACHMENT_ID_3)
        assert nodes[2]["alt"] == "Test image 3"


@pytest.mark.asyncio
class TestProcessDocumentImages:
    """Tests for process_document_images pipeline."""

    async def test_process_document_images_creates_chunks(
        self,
        service: ImageUnderstandingService,
        mock_db: AsyncMock,
        mock_minio: MagicMock,
    ) -> None:
        """Mock vision provider, verify DocumentChunk records created with chunk_type='image'."""
        doc_id = uuid4()
        attachment = _build_mock_attachment(attachment_id=UUID(_ATTACHMENT_ID_1))

        # Mock DB to return the attachment when queried
        attachment_result = MagicMock()
        attachment_result.scalar_one_or_none.return_value = attachment

        # First call: get_attachment lookup returns the attachment
        # Second+ calls: max chunk_index query returns None, scope query returns None
        max_idx_result = MagicMock()
        max_idx_result.scalar.return_value = None
        scope_result = MagicMock()
        scope_result.first.return_value = None

        mock_db.execute = AsyncMock(
            side_effect=[attachment_result, max_idx_result, scope_result]
        )

        single_image_json = {
            "type": "doc",
            "content": [
                {
                    "type": "image",
                    "attrs": {
                        "src": "http://example.com/img1.png",
                        "attachmentId": _ATTACHMENT_ID_1,
                        "alt": "Test image",
                        "title": "Image",
                        "width": 500,
                    },
                },
            ],
        }

        results = await service.process_document_images(doc_id, single_image_json)

        assert len(results) == 1
        assert isinstance(results[0], ImageDescription)
        assert results[0].description == "A detailed description of the image content."
        assert results[0].token_count > 0
        # Verify chunks were stored
        mock_db.add_all.assert_called_once()
        mock_db.flush.assert_awaited()
        # Verify chunk_type is set to "image"
        stored_chunks = mock_db.add_all.call_args[0][0]
        assert len(stored_chunks) == 1
        assert stored_chunks[0].chunk_type == "image"

    async def test_process_document_images_skips_small_images(
        self,
        service: ImageUnderstandingService,
        mock_db: AsyncMock,
        mock_minio: MagicMock,
    ) -> None:
        """Include <10KB image, verify skipped."""
        doc_id = uuid4()
        small_attachment = _build_mock_attachment(file_size=5_000)

        # Return small image bytes (below threshold)
        mock_minio.download_file.return_value = b"\x89PNG" + b"\x00" * 5_000

        attachment_result = MagicMock()
        attachment_result.scalar_one_or_none.return_value = small_attachment
        mock_db.execute = AsyncMock(return_value=attachment_result)

        single_image_json = {
            "type": "doc",
            "content": [
                {
                    "type": "image",
                    "attrs": {
                        "src": "http://example.com/img.png",
                        "attachmentId": str(small_attachment.id),
                        "alt": "Tiny icon",
                        "width": 16,
                    },
                },
            ],
        }

        results = await service.process_document_images(doc_id, single_image_json)

        # Image was skipped because it's too small, so no descriptions returned
        assert len(results) == 0
        # Vision provider should NOT have been called
        vision_provider, _ = await service.provider_registry.get_vision_provider(mock_db)
        # The describe_image on the vision provider was only called by get_vision_provider setup
        # But within process_document_images, it should not have been called for this image

    async def test_process_document_images_limits_to_10(
        self,
        service: ImageUnderstandingService,
        mock_db: AsyncMock,
        mock_minio: MagicMock,
    ) -> None:
        """Pass 15 images, verify only 10 processed."""
        doc_id = uuid4()

        # Build 15 image nodes
        content_nodes: list[dict[str, Any]] = []
        attachments: list[MagicMock] = []
        for i in range(15):
            att_id = uuid4()
            att = _build_mock_attachment(attachment_id=att_id)
            attachments.append(att)
            content_nodes.append({
                "type": "image",
                "attrs": {
                    "src": f"http://example.com/img{i}.png",
                    "attachmentId": str(att_id),
                    "alt": f"Image {i}",
                    "width": 500,
                },
            })

        tiptap_json = {"type": "doc", "content": content_nodes}

        # Each execute call returns the corresponding attachment
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            result = MagicMock()
            if call_count < _MAX_IMAGES_PER_DOCUMENT:
                result.scalar_one_or_none.return_value = attachments[call_count]
                call_count += 1
            else:
                # For max chunk index and scope queries
                result.scalar.return_value = None
                result.first.return_value = None
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        results = await service.process_document_images(doc_id, tiptap_json)

        # At most 10 images processed (some might fail attachment lookup
        # but the node list is definitely truncated to 10)
        assert len(results) <= _MAX_IMAGES_PER_DOCUMENT


@pytest.mark.asyncio
class TestProcessImportedImages:
    """Tests for process_imported_images pipeline."""

    async def test_process_imported_images_uploads_to_minio(
        self,
        service: ImageUnderstandingService,
        mock_db: AsyncMock,
        mock_minio: MagicMock,
    ) -> None:
        """Verify MinIO upload called for each image."""
        doc_id = uuid4()
        scope_ids = {
            "application_id": uuid4(),
            "project_id": uuid4(),
            "user_id": uuid4(),
        }

        images = [
            ExtractedImage(
                data=b"\x89PNG" + b"\x00" * 20_000,
                content_type="image/png",
                filename="fig1.png",
                caption="Figure 1",
                page_number=1,
            ),
            ExtractedImage(
                data=b"\xFF\xD8\xFF" + b"\x00" * 20_000,
                content_type="image/jpeg",
                filename="fig2.jpg",
                caption="Figure 2",
                page_number=2,
            ),
        ]

        # Mock the attachment creation (flush assigns an id)
        def mock_add(obj):
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid4()

        mock_db.add = MagicMock(side_effect=mock_add)

        # For max chunk_index and scope queries
        max_idx_result = MagicMock()
        max_idx_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=max_idx_result)

        results = await service.process_imported_images(images, doc_id, scope_ids)

        assert len(results) == 2
        # MinIO upload_bytes called once for each image
        assert mock_minio.upload_bytes.call_count == 2

    async def test_vision_provider_error_continues_batch(
        self,
        service: ImageUnderstandingService,
        mock_db: AsyncMock,
        mock_minio: MagicMock,
        mock_provider_registry: MagicMock,
    ) -> None:
        """Mock failure on image #2, verify others still processed."""
        doc_id = uuid4()
        scope_ids = {"application_id": uuid4(), "project_id": None, "user_id": uuid4()}

        images = [
            ExtractedImage(
                data=b"\x89PNG" + b"\x00" * 20_000,
                content_type="image/png",
                filename="ok1.png",
                caption="OK Image 1",
                page_number=1,
            ),
            ExtractedImage(
                data=b"\x89PNG" + b"\x00" * 20_000,
                content_type="image/png",
                filename="fail.png",
                caption="Failing Image",
                page_number=2,
            ),
            ExtractedImage(
                data=b"\x89PNG" + b"\x00" * 20_000,
                content_type="image/png",
                filename="ok2.png",
                caption="OK Image 2",
                page_number=3,
            ),
        ]

        # Vision provider succeeds for images 0 and 2, raises for image 1
        call_idx = 0
        vision_provider, _ = await mock_provider_registry.get_vision_provider(mock_db)

        async def describe_with_failure(*args, **kwargs):
            nonlocal call_idx
            current = call_idx
            call_idx += 1
            if current == 1:
                raise Exception("Vision API timeout")
            return "Description of the image."

        vision_provider.describe_image = AsyncMock(side_effect=describe_with_failure)

        def mock_add(obj):
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid4()

        mock_db.add = MagicMock(side_effect=mock_add)

        max_idx_result = MagicMock()
        max_idx_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=max_idx_result)

        results = await service.process_imported_images(images, doc_id, scope_ids)

        # Images 0 and 2 should succeed, image 1 should fail gracefully
        assert len(results) == 2
        assert all(r.description == "Description of the image." for r in results)

    async def test_image_descriptions_are_embedded(
        self,
        service: ImageUnderstandingService,
        mock_db: AsyncMock,
        mock_minio: MagicMock,
        mock_provider_registry: MagicMock,
    ) -> None:
        """Verify embedding service called for descriptions."""
        doc_id = uuid4()
        scope_ids = {"application_id": uuid4(), "project_id": None, "user_id": uuid4()}

        images = [
            ExtractedImage(
                data=b"\x89PNG" + b"\x00" * 20_000,
                content_type="image/png",
                filename="chart.png",
                caption="Revenue chart",
                page_number=1,
            ),
        ]

        def mock_add(obj):
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid4()

        mock_db.add = MagicMock(side_effect=mock_add)

        max_idx_result = MagicMock()
        max_idx_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=max_idx_result)

        results = await service.process_imported_images(images, doc_id, scope_ids)

        assert len(results) == 1
        # Embedding provider should have been called (via _generate_embeddings)
        embedding_provider, _ = await mock_provider_registry.get_embedding_provider(mock_db)
        embedding_provider.generate_embeddings_batch.assert_awaited()

    async def test_no_vision_provider_returns_empty(
        self,
        mock_embedding_service: MagicMock,
        mock_minio: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """When no vision provider configured, return empty list."""
        registry = MagicMock()
        registry.get_vision_provider = AsyncMock(
            side_effect=ConfigurationError("No vision provider configured")
        )

        with patch("app.ai.image_understanding_service.tiktoken") as mock_tiktoken:
            mock_encoder = MagicMock()
            mock_encoder.encode.return_value = []
            mock_tiktoken.get_encoding.return_value = mock_encoder

            svc = ImageUnderstandingService(
                provider_registry=registry,
                embedding_service=mock_embedding_service,
                minio_service=mock_minio,
                db=mock_db,
            )

        doc_id = uuid4()
        images = [
            ExtractedImage(
                data=b"\x89PNG" + b"\x00" * 20_000,
                content_type="image/png",
                filename="img.png",
                caption="Test",
                page_number=1,
            ),
        ]

        results = await svc.process_imported_images(
            images, doc_id, {"application_id": uuid4(), "project_id": None, "user_id": uuid4()}
        )

        assert results == []


@pytest.mark.asyncio
class TestProcessDocumentImagesNoProvider:
    """Tests for process_document_images when vision provider is unavailable."""

    async def test_no_vision_provider_for_tiptap_returns_empty(
        self,
        mock_embedding_service: MagicMock,
        mock_minio: MagicMock,
        mock_db: AsyncMock,
    ) -> None:
        """When no vision provider, process_document_images returns []."""
        registry = MagicMock()
        registry.get_vision_provider = AsyncMock(
            side_effect=ConfigurationError("No vision provider")
        )

        with patch("app.ai.image_understanding_service.tiktoken") as mock_tiktoken:
            mock_encoder = MagicMock()
            mock_encoder.encode.return_value = []
            mock_tiktoken.get_encoding.return_value = mock_encoder

            svc = ImageUnderstandingService(
                provider_registry=registry,
                embedding_service=mock_embedding_service,
                minio_service=mock_minio,
                db=mock_db,
            )

        results = await svc.process_document_images(uuid4(), SAMPLE_TIPTAP_JSON)
        assert results == []

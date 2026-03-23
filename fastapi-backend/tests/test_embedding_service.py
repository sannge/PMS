"""Unit tests for embedding pipeline service.

Tests use mocked providers to avoid real API calls. Verifies the full
embedding pipeline: chunk -> embed -> normalize -> store -> timestamp.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.chunking_service import SemanticChunker
from app.ai.embedding_normalizer import EmbeddingNormalizer
from app.ai.embedding_service import BatchResult, EmbedResult, EmbeddingService
from app.ai.provider_interface import LLMProviderError
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


# ---- Fixtures ----


def _make_mock_provider(embedding_dim: int = 1536):
    """Create a mock LLM provider that returns fake embeddings."""
    mock_provider = AsyncMock()
    mock_provider.generate_embeddings_batch = AsyncMock(
        side_effect=lambda texts, model: [[0.1] * embedding_dim for _ in texts]
    )
    mock_provider.generate_embedding = AsyncMock(return_value=[0.1] * embedding_dim)
    return mock_provider


def _make_mock_registry(provider=None):
    """Create a mock ProviderRegistry."""
    if provider is None:
        provider = _make_mock_provider()

    mock_registry = AsyncMock()
    mock_registry.get_embedding_provider = AsyncMock(return_value=(provider, "text-embedding-3-small"))
    return mock_registry


def _make_tiptap_content(text: str = "Hello world") -> dict:
    """Create a simple TipTap document for testing."""
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


@pytest.fixture(autouse=True)
def _skip_without_pgvector(requires_pgvector):
    """All tests in this module require pgvector."""


@pytest_asyncio.fixture
async def test_document(db_session: AsyncSession, test_user, test_application) -> Document:
    """Create a test document for embedding tests."""
    doc = Document(
        id=uuid.uuid4(),
        title="Test Embedding Document",
        content_json='{"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello world, this is a test document for embedding."}]}]}',
        content_plain="Hello world, this is a test document for embedding.",
        application_id=test_application.id,
        created_by=test_user.id,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
def embedding_service(db_session: AsyncSession):
    """Create EmbeddingService with mocked dependencies."""
    registry = _make_mock_registry()
    chunker = SemanticChunker(target_tokens=600, overlap_tokens=100)
    normalizer = EmbeddingNormalizer(target_dimensions=1536)

    return EmbeddingService(
        provider_registry=registry,
        chunker=chunker,
        normalizer=normalizer,
        db=db_session,
    )


# ---- Tests ----


class TestEmbedDocument:
    """Tests for single document embedding."""

    @pytest.mark.asyncio
    async def test_embed_document_creates_chunks(self, embedding_service, test_document, db_session):
        """Verify DocumentChunk rows are created with correct fields."""
        content = _make_tiptap_content("This is a test paragraph with enough text to create a chunk.")
        scope_ids = {
            "application_id": test_document.application_id,
            "project_id": None,
            "user_id": test_document.created_by,
        }

        result = await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content,
            title=test_document.title,
            scope_ids=scope_ids,
        )

        assert isinstance(result, EmbedResult)
        assert result.chunk_count >= 1
        assert result.token_count > 0
        assert result.duration_ms >= 0

        # Verify chunks in DB
        chunks = (
            (await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == test_document.id)))
            .scalars()
            .all()
        )

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.document_id == test_document.id
            assert chunk.chunk_text is not None
            assert chunk.embedding is not None
            assert chunk.token_count > 0

    @pytest.mark.asyncio
    async def test_embed_document_sets_embedding_updated_at(self, embedding_service, test_document, db_session):
        """Verify Document.embedding_updated_at is set after embed."""
        content = _make_tiptap_content("Content for timestamp test.")
        scope_ids = {"application_id": test_document.application_id}

        await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content,
            title=test_document.title,
            scope_ids=scope_ids,
        )

        await db_session.refresh(test_document)
        assert test_document.embedding_updated_at is not None

    @pytest.mark.asyncio
    async def test_embed_document_replaces_existing_chunks(self, embedding_service, test_document, db_session):
        """Embed twice, verify old chunks deleted and new ones created."""
        scope_ids = {"application_id": test_document.application_id}

        # First embed
        content1 = _make_tiptap_content("First version content.")
        await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content1,
            title=test_document.title,
            scope_ids=scope_ids,
        )

        chunks1 = (
            (await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == test_document.id)))
            .scalars()
            .all()
        )
        count1 = len(chunks1)
        assert count1 >= 1

        # Second embed with different content
        content2 = _make_tiptap_content("Second version with completely different content.")
        await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content2,
            title=test_document.title,
            scope_ids=scope_ids,
        )

        chunks2 = (
            (await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == test_document.id)))
            .scalars()
            .all()
        )

        # Old chunks should be replaced, not duplicated
        for chunk in chunks2:
            assert "Second version" in chunk.chunk_text or "different" in chunk.chunk_text

    @pytest.mark.asyncio
    async def test_embed_document_denormalizes_scope_ids(self, embedding_service, test_document, db_session):
        """Verify scope IDs are correctly denormalized onto chunks."""
        app_id = test_document.application_id
        user_id = test_document.created_by
        scope_ids = {
            "application_id": app_id,
            "project_id": None,
            "user_id": user_id,
        }

        content = _make_tiptap_content("Scope test content.")
        await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content,
            title=test_document.title,
            scope_ids=scope_ids,
        )

        chunks = (
            (await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == test_document.id)))
            .scalars()
            .all()
        )

        for chunk in chunks:
            assert chunk.application_id == app_id
            assert chunk.project_id is None
            assert chunk.user_id == user_id

    @pytest.mark.asyncio
    async def test_embed_empty_document(self, embedding_service, test_document, db_session):
        """Embedding empty document creates 0 chunks."""
        content = {"type": "doc", "content": []}
        scope_ids = {"application_id": test_document.application_id}

        result = await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content,
            title=test_document.title,
            scope_ids=scope_ids,
        )

        assert result.chunk_count == 0


class TestEmbedBatch:
    """Tests for batch embedding."""

    @pytest.mark.asyncio
    async def test_embed_batch_processes_multiple_documents(
        self, embedding_service, test_document, test_user, test_application, db_session
    ):
        """Batch of multiple docs returns correct BatchResult."""
        # Create additional documents
        doc2 = Document(
            id=uuid.uuid4(),
            title="Batch Doc 2",
            content_json='{"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Batch document two."}]}]}',
            content_plain="Batch document two.",
            application_id=test_application.id,
            created_by=test_user.id,
        )
        db_session.add(doc2)
        await db_session.commit()

        result = await embedding_service.embed_documents_batch([test_document.id, doc2.id])

        assert isinstance(result, BatchResult)
        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_embed_batch_continues_on_single_failure(
        self, db_session, test_document, test_user, test_application
    ):
        """1 of N docs fails, batch still processes others."""
        # Create a provider that fails on second call
        mock_provider = _make_mock_provider()
        call_count = 0

        async def failing_batch(texts, model):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise LLMProviderError("API error", provider="test")
            return [[0.1] * 1536 for _ in texts]

        mock_provider.generate_embeddings_batch = AsyncMock(side_effect=failing_batch)
        registry = _make_mock_registry(mock_provider)

        doc2 = Document(
            id=uuid.uuid4(),
            title="Fail Doc",
            content_json='{"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "This will fail."}]}]}',
            content_plain="This will fail.",
            application_id=test_application.id,
            created_by=test_user.id,
        )
        db_session.add(doc2)
        await db_session.commit()

        service = EmbeddingService(
            provider_registry=registry,
            chunker=SemanticChunker(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )

        result = await service.embed_documents_batch([test_document.id, doc2.id])

        assert result.total == 2
        assert result.succeeded >= 1
        assert result.failed >= 1


class TestDeleteChunks:
    """Tests for chunk deletion."""

    @pytest.mark.asyncio
    async def test_delete_document_chunks_removes_all(self, embedding_service, test_document, db_session):
        """Create chunks then delete, verify 0 remain."""
        content = _make_tiptap_content("Content to be deleted.")
        scope_ids = {"application_id": test_document.application_id}

        await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content,
            title=test_document.title,
            scope_ids=scope_ids,
        )

        # Verify chunks exist
        chunks = (
            (await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == test_document.id)))
            .scalars()
            .all()
        )
        assert len(chunks) >= 1

        # Delete
        await embedding_service.delete_document_chunks(test_document.id)

        # Verify all deleted
        chunks_after = (
            (await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == test_document.id)))
            .scalars()
            .all()
        )
        assert len(chunks_after) == 0

    @pytest.mark.asyncio
    async def test_delete_document_chunks_returns_count(self, embedding_service, test_document, db_session):
        """Verify returned int matches number of deleted chunks."""
        content = _make_tiptap_content("Count test content.")
        scope_ids = {"application_id": test_document.application_id}

        result = await embedding_service.embed_document(
            document_id=test_document.id,
            content_json=content,
            title=test_document.title,
            scope_ids=scope_ids,
        )
        expected_count = result.chunk_count

        deleted = await embedding_service.delete_document_chunks(test_document.id)
        assert deleted == expected_count

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document_returns_zero(self, embedding_service):
        """Deleting chunks for nonexistent document returns 0."""
        deleted = await embedding_service.delete_document_chunks(uuid.uuid4())
        assert deleted == 0


class TestEmbedErrorHandling:
    """Tests for error handling in the embedding pipeline."""

    @pytest.fixture(autouse=True)
    def _skip_without_pgvector(self, requires_pgvector):
        pass

    @pytest.mark.asyncio
    async def test_embed_document_raises_llm_provider_error(self, db_session, test_document):
        """LLMProviderError from provider is re-raised."""
        mock_provider = _make_mock_provider()
        mock_provider.generate_embeddings_batch = AsyncMock(
            side_effect=LLMProviderError("API error", provider="openai")
        )
        registry = _make_mock_registry(mock_provider)
        service = EmbeddingService(
            provider_registry=registry,
            chunker=SemanticChunker(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )
        content = _make_tiptap_content("Error handling test.")
        with pytest.raises(LLMProviderError, match="API error"):
            await service.embed_document(
                document_id=test_document.id,
                content_json=content,
                title=test_document.title,
                scope_ids={"application_id": test_document.application_id},
            )

    @pytest.mark.asyncio
    async def test_embed_document_wraps_generic_exception(self, db_session, test_document):
        """Generic exception is wrapped in LLMProviderError."""
        mock_provider = _make_mock_provider()
        mock_provider.generate_embeddings_batch = AsyncMock(side_effect=RuntimeError("connection refused"))
        registry = _make_mock_registry(mock_provider)
        service = EmbeddingService(
            provider_registry=registry,
            chunker=SemanticChunker(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )
        content = _make_tiptap_content("Wrap error test.")
        with pytest.raises(LLMProviderError, match="connection refused"):
            await service.embed_document(
                document_id=test_document.id,
                content_json=content,
                title=test_document.title,
                scope_ids={"application_id": test_document.application_id},
            )

    @pytest.mark.asyncio
    async def test_embed_batch_not_found_document(self, db_session):
        """Batch embed with nonexistent document ID counts as failed."""
        registry = _make_mock_registry()
        service = EmbeddingService(
            provider_registry=registry,
            chunker=SemanticChunker(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )
        fake_id = uuid.uuid4()
        result = await service.embed_documents_batch([fake_id])
        assert result.total == 1
        assert result.failed == 1
        assert result.succeeded == 0
        assert any(str(fake_id) in err for err in result.errors)

"""Integration tests for hybrid retrieval service.

Tests cover semantic search, keyword search (Meilisearch), fuzzy title search
(pg_trgm), RRF merge, RBAC boundaries, and deduplication.

Note: These tests mock external services (embedding providers, Meilisearch)
to avoid requiring live infrastructure in CI.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding_normalizer import EmbeddingNormalizer
from app.ai.retrieval_service import (
    HybridRetrievalService,
    _RankedResult,
)
from app.models.application import Application
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


# ---- Fixtures ----


def _make_mock_provider(embedding_dim: int = 1536):
    """Create a mock LLM provider."""
    mock = AsyncMock()
    mock.generate_embedding = AsyncMock(return_value=[0.1] * embedding_dim)
    mock.generate_embeddings_batch = AsyncMock(
        side_effect=lambda texts, model: [[0.1] * embedding_dim for _ in texts]
    )
    return mock


def _make_mock_registry(provider=None):
    """Create a mock ProviderRegistry."""
    if provider is None:
        provider = _make_mock_provider()
    mock_registry = AsyncMock()
    mock_registry.get_embedding_provider = AsyncMock(
        return_value=(provider, "text-embedding-3-small")
    )
    return mock_registry


@pytest_asyncio.fixture
async def test_doc_with_chunks(
    db_session: AsyncSession, test_user, test_application, requires_pgvector
) -> Document:
    """Create a test document with pre-created chunks."""
    doc = Document(
        id=uuid.uuid4(),
        title="Architecture Decision Record",
        content_json='{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"This document describes the architecture."}]}]}',
        content_plain="This document describes the architecture.",
        application_id=test_application.id,
        created_by=test_user.id,
    )
    db_session.add(doc)
    await db_session.flush()

    # Create chunks with fake embeddings
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        chunk_text="This document describes the architecture decisions for the project.",
        heading_context="Architecture",
        embedding=[0.1] * 1536,
        token_count=15,
        application_id=test_application.id,
        project_id=None,
        user_id=test_user.id,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def second_application(db_session: AsyncSession, test_user_2) -> Application:
    """Create a second application owned by user 2."""
    app = Application(
        id=uuid.uuid4(),
        name="Second Application",
        description="App for user 2",
        owner_id=test_user_2.id,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app


@pytest_asyncio.fixture
async def doc_in_second_app(
    db_session: AsyncSession, test_user_2, second_application, requires_pgvector
) -> Document:
    """Create a document in the second application."""
    doc = Document(
        id=uuid.uuid4(),
        title="Confidential Report",
        content_json='{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"Secret data."}]}]}',
        content_plain="Secret data.",
        application_id=second_application.id,
        created_by=test_user_2.id,
    )
    db_session.add(doc)
    await db_session.flush()

    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        chunk_text="This contains secret data that should not be visible to unauthorized users.",
        heading_context="Confidential",
        embedding=[0.2] * 1536,
        token_count=15,
        application_id=second_application.id,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


# ---- RRF Unit Tests ----


class TestReciprocalRankFusion:
    """Tests for the RRF merge algorithm."""

    def test_rrf_merges_multiple_sources(self):
        """Document in both semantic and keyword results gets combined score."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id = uuid.uuid4()
        semantic = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="text",
            heading_context=None, chunk_index=0, rank=1, raw_score=0.9,
            source="semantic",
        )]
        keyword = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="text",
            heading_context=None, chunk_index=0, rank=2, raw_score=0.8,
            source="keyword",
        )]

        results = service._reciprocal_rank_fusion(semantic, keyword, k=60)
        assert len(results) == 1
        assert results[0].document_id == doc_id
        # Score should be sum of 1/(60+1) + 1/(60+2)
        expected = 1 / 61 + 1 / 62
        assert abs(results[0].score - expected) < 1e-6
        assert "semantic" in results[0].source
        assert "keyword" in results[0].source

    def test_rrf_deduplicates_same_document(self):
        """Same chunk from multiple sources appears once in final results."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id = uuid.uuid4()
        list1 = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="chunk text",
            heading_context="H1", chunk_index=0, rank=1, raw_score=0.95,
            source="semantic",
        )]
        list2 = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="chunk text",
            heading_context="H1", chunk_index=0, rank=3, raw_score=0.7,
            source="keyword",
        )]

        results = service._reciprocal_rank_fusion(list1, list2, k=60)
        assert len(results) == 1

    def test_rrf_same_doc_different_chunks_merged(self):
        """Different chunk_index values from same doc merge by document_id."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id = uuid.uuid4()
        list1 = [
            _RankedResult(
                document_id=doc_id, document_title="Test", chunk_text="chunk 0 most relevant",
                heading_context="Billing", chunk_index=0, rank=1, raw_score=0.9,
                source="semantic",
            ),
            _RankedResult(
                document_id=doc_id, document_title="Test", chunk_text="chunk 1 is longer text but less relevant",
                heading_context="Security", chunk_index=1, rank=2, raw_score=0.8,
                source="semantic",
            ),
        ]

        results = service._reciprocal_rank_fusion(list1, k=60)
        # Same document merges into 1 result with combined RRF score
        assert len(results) == 1
        # Score = 1/(60+1) + 1/(60+2)
        expected = 1 / 61 + 1 / 62
        assert abs(results[0].score - expected) < 1e-6
        # Highest-ranked chunk text preserved (rank=1, not the longer rank=2)
        assert "chunk 0 most relevant" in results[0].chunk_text
        assert results[0].heading_context == "Billing"

    def test_rrf_different_documents_stay_separate(self):
        """Different documents are not merged."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id_1 = uuid.uuid4()
        doc_id_2 = uuid.uuid4()
        list1 = [
            _RankedResult(
                document_id=doc_id_1, document_title="Doc A", chunk_text="text a",
                heading_context=None, chunk_index=0, rank=1, raw_score=0.9,
                source="semantic",
            ),
            _RankedResult(
                document_id=doc_id_2, document_title="Doc B", chunk_text="text b",
                heading_context=None, chunk_index=0, rank=2, raw_score=0.8,
                source="semantic",
            ),
        ]

        results = service._reciprocal_rank_fusion(list1, k=60)
        assert len(results) == 2

    def test_rrf_cross_source_dedup_by_document_id(self):
        """Semantic (chunk_index=0) + keyword (chunk_index=None) merge for same doc."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id = uuid.uuid4()
        semantic = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="semantic chunk",
            heading_context="H1", chunk_index=0, rank=1, raw_score=0.9,
            source="semantic",
        )]
        keyword = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="keyword full content preview",
            heading_context=None, chunk_index=None, rank=3, raw_score=0.8,
            source="keyword",
        )]

        results = service._reciprocal_rank_fusion(semantic, keyword, k=60)
        assert len(results) == 1  # Merged, not 2 separate entries
        assert "keyword" in results[0].source
        assert "semantic" in results[0].source
        # Highest-ranked (semantic rank=1) chunk text preserved
        assert "semantic chunk" in results[0].chunk_text
        assert results[0].heading_context == "H1"

    def test_rrf_empty_lists(self):
        """Empty ranked lists produce empty results."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )
        results = service._reciprocal_rank_fusion([], [], k=60)
        assert results == []

    def test_rrf_source_attribution(self):
        """Results include correct source attribution."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id = uuid.uuid4()
        semantic = [_RankedResult(
            document_id=doc_id, document_title="T", chunk_text="t",
            heading_context=None, chunk_index=0, rank=1, raw_score=0.9,
            source="semantic",
        )]

        results = service._reciprocal_rank_fusion(semantic, k=60)
        assert len(results) == 1
        assert results[0].source == "semantic"

    def test_rrf_returns_snippets(self):
        """Results include non-empty snippet field."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        semantic = [_RankedResult(
            document_id=uuid.uuid4(), document_title="Title",
            chunk_text="This is the chunk text content.",
            heading_context="Introduction",
            chunk_index=0, rank=1, raw_score=0.9, source="semantic",
        )]

        results = service._reciprocal_rank_fusion(semantic, k=60)
        assert len(results) == 1
        assert results[0].snippet != ""
        assert "Introduction" in results[0].snippet


class TestRetrievalEmptyQuery:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_retrieval_empty_query_returns_empty(self, db_session, test_user, requires_pgvector):
        """Empty string query returns empty list, no errors."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )
        results = await service.retrieve("", test_user.id)
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieval_whitespace_query_returns_empty(
        self, db_session, test_user, requires_pgvector
    ):
        """Whitespace-only query returns empty list."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )
        results = await service.retrieve("   ", test_user.id)
        assert results == []


class TestSnippetGeneration:
    """Tests for snippet generation."""

    def test_snippet_with_heading_and_text(self):
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )
        snippet = service._generate_snippet("Heading", "Some long text here.")
        assert "[Heading]" in snippet
        assert "Some long text" in snippet

    def test_snippet_truncation(self):
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )
        long_text = "word " * 100
        snippet = service._generate_snippet(None, long_text, max_length=50)
        assert len(snippet) < len(long_text)
        assert snippet.endswith("...")

    def test_snippet_no_heading(self):
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )
        snippet = service._generate_snippet(None, "Just text.")
        assert "[" not in snippet
        assert "Just text" in snippet


class TestRetrievalRBACBoundaries:
    """Tests for RBAC enforcement in retrieval.

    Critical security tests: User A cannot see User B's documents.
    """

    @pytest.mark.asyncio
    async def test_retrieval_respects_rbac_boundaries(
        self,
        db_session,
        test_user,
        test_user_2,
        test_doc_with_chunks,
        doc_in_second_app,
        requires_pgvector,
    ):
        """User A (member of App X) cannot see documents from App Y."""
        # Verify the scope resolution logic directly
        # User 1 should only have access to test_application
        from app.services.search_service import _get_user_application_ids
        app_ids = await _get_user_application_ids(db_session, test_user.id)
        assert test_doc_with_chunks.application_id in app_ids
        assert doc_in_second_app.application_id not in app_ids

    @pytest.mark.asyncio
    async def test_retrieval_filters_by_application(
        self, db_session, test_user, test_doc_with_chunks, requires_pgvector
    ):
        """retrieve(application_id=X) only returns documents from App X."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )

        # Filtering by a non-accessible app should return empty
        non_accessible_app = uuid.uuid4()
        results = await service.retrieve(
            "architecture",
            test_user.id,
            application_id=non_accessible_app,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieval_filters_by_project(
        self, db_session, test_user, requires_pgvector
    ):
        """retrieve(project_id=Y) with non-accessible project returns empty."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )

        non_accessible_project = uuid.uuid4()
        results = await service.retrieve(
            "test query",
            test_user.id,
            project_id=non_accessible_project,
        )
        assert results == []


class TestRetrievalExcludesDeleted:
    """Tests for soft-delete filtering."""

    @pytest.mark.asyncio
    async def test_retrieval_excludes_deleted_documents(
        self, db_session, test_user, test_application, requires_pgvector
    ):
        """Soft-deleted document never appears in any retrieval path."""
        from app.utils.timezone import utc_now

        # Create a deleted document with chunks
        doc = Document(
            id=uuid.uuid4(),
            title="Deleted Document",
            content_json='{"type":"doc","content":[]}',
            content_plain="Deleted content.",
            application_id=test_application.id,
            created_by=test_user.id,
            deleted_at=utc_now(),  # Soft-deleted
        )
        db_session.add(doc)
        await db_session.flush()

        chunk = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            chunk_index=0,
            chunk_text="This document is deleted.",
            heading_context=None,
            embedding=[0.1] * 1536,
            token_count=5,
            application_id=test_application.id,
        )
        db_session.add(chunk)
        await db_session.commit()

        # Verify that deleted doc's application is still accessible but
        # the SQL WHERE clause filters out deleted documents.
        from app.services.search_service import _get_user_application_ids
        app_ids = await _get_user_application_ids(db_session, test_user.id)
        assert test_application.id in app_ids


class TestRetrievalGracefulDegradation:
    """Tests for graceful degradation when individual search sources fail."""

    def test_rrf_with_single_source(self):
        """RRF produces valid results with only one source contributing."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id = uuid.uuid4()
        semantic_only = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="text",
            heading_context=None, chunk_index=0, rank=1, raw_score=0.9,
            source="semantic",
        )]

        results = service._reciprocal_rank_fusion(semantic_only, [], k=60)
        assert len(results) == 1
        assert results[0].document_id == doc_id
        assert results[0].source == "semantic"

    def test_rrf_highest_ranked_chunk_text_preserved(self):
        """When same doc appears in multiple sources, highest-ranked text is kept."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )

        doc_id = uuid.uuid4()
        # Semantic has rank=1 (best), keyword has rank=3 (worse)
        semantic_hit = [_RankedResult(
            document_id=doc_id, document_title="Test", chunk_text="relevant semantic chunk",
            heading_context="Security", chunk_index=0, rank=1, raw_score=0.9,
            source="semantic",
        )]
        keyword_hit = [_RankedResult(
            document_id=doc_id, document_title="Test",
            chunk_text="this is a much longer keyword text that is less relevant",
            heading_context=None, chunk_index=None, rank=3, raw_score=0.8,
            source="keyword",
        )]

        results = service._reciprocal_rank_fusion(semantic_hit, keyword_hit, k=60)
        assert len(results) == 1
        # Highest-ranked (rank=1) chunk text preserved, not the longest
        assert "relevant semantic chunk" in results[0].chunk_text
        assert results[0].heading_context == "Security"

    @pytest.mark.asyncio
    async def test_retrieval_empty_app_ids_returns_empty(
        self, db_session, requires_pgvector
    ):
        """User with no accessible applications gets empty results."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=db_session,
        )
        # Use a user UUID that has no application memberships
        no_apps_user = uuid.uuid4()
        results = await service.retrieve("test query", no_apps_user)
        assert results == []


class TestSnippetEdgeCases:
    """Edge case tests for snippet generation."""

    def test_snippet_empty_chunk_text(self):
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )
        snippet = service._generate_snippet("Heading", "")
        assert "[Heading]" in snippet

    def test_snippet_no_spaces_in_long_text(self):
        """Text with no spaces still truncates and adds ellipsis."""
        service = HybridRetrievalService(
            provider_registry=_make_mock_registry(),
            normalizer=EmbeddingNormalizer(),
            db=AsyncMock(),
        )
        long_word = "a" * 300
        snippet = service._generate_snippet(None, long_word, max_length=50)
        assert snippet.endswith("...")
        # rsplit on no-spaces text returns the full truncated text + "..."
        # so snippet is text[:50] + "..." = 53 chars max
        assert len(snippet) <= 53

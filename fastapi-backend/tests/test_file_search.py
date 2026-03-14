"""Tests for file search integration (Phase 6).

Tests cover:
- Meilisearch index settings for file fields
- build_search_file_data()
- index_file_from_data()
- remove_file_from_index()
- _expand_hits() file detection
- HybridRetrievalService file-aware retrieval
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.search_service import (
    MEILISEARCH_INDEX_SETTINGS,
    _expand_hits,
    build_search_file_data,
)


# ============================================================================
# Index Settings Tests
# ============================================================================


class TestIndexSettings:
    """Verify Meilisearch index settings include file-related fields."""

    def test_file_name_in_searchable(self):
        """file_name should be in searchableAttributes."""
        assert "file_name" in MEILISEARCH_INDEX_SETTINGS["searchableAttributes"]

    def test_content_type_in_filterable(self):
        """content_type should be filterable."""
        assert "content_type" in MEILISEARCH_INDEX_SETTINGS["filterableAttributes"]

    def test_mime_type_in_filterable(self):
        """mime_type should be filterable."""
        assert "mime_type" in MEILISEARCH_INDEX_SETTINGS["filterableAttributes"]

    def test_content_type_in_displayed(self):
        """content_type should be in displayedAttributes."""
        assert "content_type" in MEILISEARCH_INDEX_SETTINGS["displayedAttributes"]

    def test_mime_type_in_displayed(self):
        """mime_type should be in displayedAttributes."""
        assert "mime_type" in MEILISEARCH_INDEX_SETTINGS["displayedAttributes"]

    def test_file_name_in_displayed(self):
        """file_name should be in displayedAttributes."""
        assert "file_name" in MEILISEARCH_INDEX_SETTINGS["displayedAttributes"]


# ============================================================================
# build_search_file_data Tests
# ============================================================================


class TestBuildSearchFileData:
    """Tests for build_search_file_data."""

    def test_basic_file_data(self):
        """Builds correct search doc for a FolderFile."""
        ff = MagicMock()
        ff.id = uuid4()
        ff.display_name = "report.pdf"
        ff.content_plain = "This is report content."
        ff.mime_type = "application/pdf"
        ff.application_id = uuid4()
        ff.project_id = None
        ff.user_id = None
        ff.folder_id = uuid4()
        ff.created_by = uuid4()
        ff.updated_at = MagicMock(timestamp=MagicMock(return_value=1700000000))

        data = build_search_file_data(ff)

        assert data["id"] == f"file:{ff.id}"
        assert data["title"] == "report.pdf"
        assert data["file_name"] == "report.pdf"
        assert data["content_type"] == "file"
        assert data["mime_type"] == "application/pdf"
        assert data["content_plain"] == "This is report content."
        assert data["application_id"] == str(ff.application_id)
        assert data["folder_id"] == str(ff.folder_id)
        assert data["deleted_at"] is None

    def test_project_scoped_file(self):
        """Project-scoped file resolves application_id from project."""
        ff = MagicMock()
        ff.id = uuid4()
        ff.display_name = "spec.docx"
        ff.content_plain = "Specification"
        ff.mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ff.application_id = None
        ff.project_id = uuid4()
        ff.user_id = None
        ff.folder_id = None
        ff.created_by = uuid4()
        ff.updated_at = MagicMock(timestamp=MagicMock(return_value=1700000000))

        project_app_id = uuid4()
        data = build_search_file_data(ff, project_application_id=project_app_id)

        assert data["application_id"] == str(project_app_id)
        assert data["project_id"] == str(ff.project_id)

    def test_personal_file(self):
        """Personal-scoped file has user_id but no app/project."""
        ff = MagicMock()
        ff.id = uuid4()
        ff.display_name = "notes.csv"
        ff.content_plain = "Personal notes"
        ff.mime_type = "text/csv"
        ff.application_id = None
        ff.project_id = None
        ff.user_id = uuid4()
        ff.folder_id = uuid4()
        ff.created_by = ff.user_id
        ff.updated_at = MagicMock(timestamp=MagicMock(return_value=1700000000))

        data = build_search_file_data(ff)

        assert data["application_id"] is None
        assert data["project_id"] is None
        assert data["user_id"] == str(ff.user_id)

    def test_content_truncated(self):
        """Content longer than MAX_CONTENT_LENGTH is truncated."""
        ff = MagicMock()
        ff.id = uuid4()
        ff.display_name = "big.txt"
        ff.content_plain = "x" * 500_000
        ff.mime_type = "text/plain"
        ff.application_id = uuid4()
        ff.project_id = None
        ff.user_id = None
        ff.folder_id = None
        ff.created_by = uuid4()
        ff.updated_at = MagicMock(timestamp=MagicMock(return_value=1700000000))

        data = build_search_file_data(ff)

        # Should be truncated to MAX_CONTENT_LENGTH (300_000)
        assert len(data["content_plain"]) <= 300_000


# ============================================================================
# index_file_from_data Tests
# ============================================================================


class TestIndexFileFromData:
    """Tests for index_file_from_data."""

    @pytest.mark.asyncio
    async def test_delegates_to_index_document_from_data(self):
        """index_file_from_data calls index_document_from_data."""
        from app.services.search_service import index_file_from_data

        data = {"id": f"file:{uuid4()}", "title": "test.pdf"}

        with patch(
            "app.services.search_service.index_document_from_data",
            new_callable=AsyncMock,
        ) as mock_index:
            await index_file_from_data(data)
            mock_index.assert_called_once_with(data)


# ============================================================================
# remove_file_from_index Tests
# ============================================================================


class TestRemoveFileFromIndex:
    """Tests for remove_file_from_index."""

    @pytest.mark.asyncio
    async def test_uses_file_prefix(self):
        """remove_file_from_index uses file: prefix for deletion."""
        from app.services.search_service import remove_file_from_index

        file_id = uuid4()

        mock_index = MagicMock()
        mock_task = MagicMock()
        mock_task.task_uid = 123
        mock_index.delete_document = AsyncMock(return_value=mock_task)

        mock_client = MagicMock()
        mock_client.wait_for_task = AsyncMock()

        with (
            patch("app.services.search_service.get_meili_index", return_value=mock_index),
            patch("app.services.search_service.get_meili_client", return_value=mock_client),
        ):
            await remove_file_from_index(file_id)

        mock_index.delete_document.assert_called_once_with(f"file:{file_id}")

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        """Exception during removal is caught and logged."""
        from app.services.search_service import remove_file_from_index

        with patch(
            "app.services.search_service.get_meili_index",
            side_effect=RuntimeError("not initialized"),
        ):
            # Should not raise
            await remove_file_from_index(uuid4())


# ============================================================================
# _expand_hits File Detection Tests
# ============================================================================


class TestExpandHitsFileDetection:
    """Tests for _expand_hits file entry handling."""

    def test_file_prefix_detected(self):
        """Hits with file: prefix get content_type and file_name."""
        hits = [
            {
                "id": f"file:{uuid4()}",
                "title": "report.xlsx",
                "file_name": "report.xlsx",
                "content_plain": "Revenue data",
                "_matchesPosition": {},
                "_formatted": {"title": "report.xlsx"},
            }
        ]

        expanded = _expand_hits(hits)
        assert len(expanded) == 1
        assert expanded[0]["content_type"] == "file"
        assert expanded[0]["file_name"] == "report.xlsx"

    def test_document_hit_no_content_type(self):
        """Regular document hits do not get content_type=file."""
        doc_id = str(uuid4())
        hits = [
            {
                "id": doc_id,
                "title": "Meeting Notes",
                "content_plain": "We discussed...",
                "_matchesPosition": {},
                "_formatted": {"title": "Meeting Notes"},
            }
        ]

        expanded = _expand_hits(hits)
        assert len(expanded) == 1
        assert expanded[0].get("content_type") != "file"

    def test_file_with_content_matches(self):
        """File hit with content matches generates per-occurrence entries."""
        hits = [
            {
                "id": f"file:{uuid4()}",
                "title": "data.csv",
                "file_name": "data.csv",
                "content_plain": "Alice is 30 years old. Bob is 25 years old.",
                "_matchesPosition": {
                    "content_plain": [
                        {"start": 0, "length": 5},  # "Alice"
                        {"start": 23, "length": 3},  # "Bob"
                    ],
                },
                "_formatted": {"title": "data.csv"},
            }
        ]

        expanded = _expand_hits(hits)
        assert len(expanded) == 2
        for entry in expanded:
            assert entry["content_type"] == "file"
            assert entry["file_name"] == "data.csv"
            assert "snippet" in entry

    def test_file_name_falls_back_to_title(self):
        """When file_name is missing, file_name falls back to title."""
        hits = [
            {
                "id": f"file:{uuid4()}",
                "title": "fallback-title.pdf",
                "content_plain": "",
                "_matchesPosition": {},
                "_formatted": {"title": "fallback-title.pdf"},
            }
        ]

        expanded = _expand_hits(hits)
        assert expanded[0]["file_name"] == "fallback-title.pdf"


# ============================================================================
# RetrievalResult Dataclass Tests
# ============================================================================


class TestRetrievalResultFileFields:
    """Tests for file-related fields on RetrievalResult."""

    def test_default_source_type(self):
        """Default source_type is 'document'."""
        from app.ai.retrieval_service import RetrievalResult

        r = RetrievalResult(
            document_id=uuid4(),
            document_title="Test",
            chunk_text="text",
            heading_context=None,
            score=0.5,
            source="semantic",
            application_id=None,
            project_id=None,
            snippet="text",
        )
        assert r.source_type == "document"
        assert r.file_id is None

    def test_file_source_type(self):
        """File results have source_type='file' and file_id set."""
        from app.ai.retrieval_service import RetrievalResult

        file_id = uuid4()
        r = RetrievalResult(
            document_id=file_id,
            document_title="data.xlsx",
            chunk_text="spreadsheet data",
            heading_context="Sheet1",
            score=0.8,
            source="semantic",
            application_id=uuid4(),
            project_id=None,
            snippet="[Sheet1] spreadsheet data",
            source_type="file",
            file_id=file_id,
        )
        assert r.source_type == "file"
        assert r.file_id == file_id


# ============================================================================
# RRF Dedup Tests
# ============================================================================


class TestRRFFileDedup:
    """Tests for RRF dedup handling file vs document results."""

    def test_same_id_different_source_type_not_merged(self):
        """Document and file with same UUID are kept separate in RRF."""
        from app.ai.retrieval_service import HybridRetrievalService, _RankedResult

        svc = HybridRetrievalService(
            provider_registry=MagicMock(),
            normalizer=MagicMock(),
            db=MagicMock(),
        )

        shared_id = uuid4()

        doc_results = [
            _RankedResult(
                document_id=shared_id,
                document_title="Doc Title",
                chunk_text="doc chunk",
                heading_context=None,
                chunk_index=0,
                rank=1,
                raw_score=0.9,
                source="semantic",
                source_type="document",
                file_id=None,
            ),
        ]

        file_results = [
            _RankedResult(
                document_id=shared_id,
                document_title="File Title",
                chunk_text="file chunk",
                heading_context=None,
                chunk_index=0,
                rank=1,
                raw_score=0.8,
                source="keyword",
                source_type="file",
                file_id=shared_id,
            ),
        ]

        merged = svc._reciprocal_rank_fusion(doc_results, file_results, k=60)

        # Should produce 2 separate results (not merged)
        assert len(merged) == 2

        source_types = {r.source_type for r in merged}
        assert "document" in source_types
        assert "file" in source_types

    def test_same_file_from_two_sources_merged(self):
        """Same file appearing in semantic + keyword is merged."""
        from app.ai.retrieval_service import HybridRetrievalService, _RankedResult

        svc = HybridRetrievalService(
            provider_registry=MagicMock(),
            normalizer=MagicMock(),
            db=MagicMock(),
        )

        file_id = uuid4()

        semantic_results = [
            _RankedResult(
                document_id=file_id,
                document_title="data.xlsx",
                chunk_text="semantic chunk",
                heading_context="Sheet1",
                chunk_index=0,
                rank=1,
                raw_score=0.9,
                source="semantic",
                source_type="file",
                file_id=file_id,
            ),
        ]

        keyword_results = [
            _RankedResult(
                document_id=file_id,
                document_title="data.xlsx",
                chunk_text="keyword hit",
                heading_context=None,
                chunk_index=None,
                rank=2,
                raw_score=0.5,
                source="keyword",
                source_type="file",
                file_id=file_id,
            ),
        ]

        merged = svc._reciprocal_rank_fusion(semantic_results, keyword_results, k=60)

        # Same file from two sources should be merged into 1
        assert len(merged) == 1
        assert merged[0].source_type == "file"
        assert merged[0].file_id == file_id
        # Source should combine both
        assert "semantic" in merged[0].source
        assert "keyword" in merged[0].source
        # RRF score should be sum of both sources
        expected_score = 1.0 / (60 + 1) + 1.0 / (60 + 2)
        assert abs(merged[0].score - expected_score) < 0.0001


# ============================================================================
# Keyword Search file: prefix Tests
# ============================================================================


class TestKeywordSearchFilePrefix:
    """Tests for _keyword_search handling file: prefixed IDs."""

    @pytest.mark.asyncio
    async def test_file_prefix_parsed(self):
        """Meilisearch hits with file: prefix are parsed correctly."""
        from app.ai.retrieval_service import HybridRetrievalService

        file_id = uuid4()

        mock_index = MagicMock()
        mock_results = MagicMock()
        mock_results.hits = [
            {
                "id": f"file:{file_id}",
                "title": "report.xlsx",
                "content_plain": "Revenue data",
                "application_id": str(uuid4()),
                "project_id": None,
            },
        ]
        mock_index.search = AsyncMock(return_value=mock_results)

        svc = HybridRetrievalService(
            provider_registry=MagicMock(),
            normalizer=MagicMock(),
            db=MagicMock(),
        )

        scope_ids = {
            "app_ids": [uuid4()],
            "project_ids": [],
            "user_id": uuid4(),
        }

        with patch(
            "app.ai.retrieval_service.get_meili_index",
            return_value=mock_index,
        ):
            results = await svc._keyword_search("revenue", scope_ids)

        assert len(results) == 1
        assert results[0].source_type == "file"
        assert results[0].file_id == file_id
        assert results[0].document_id == file_id

    @pytest.mark.asyncio
    async def test_regular_doc_not_file(self):
        """Regular document IDs (no prefix) remain source_type=document."""
        from app.ai.retrieval_service import HybridRetrievalService

        doc_id = uuid4()

        mock_index = MagicMock()
        mock_results = MagicMock()
        mock_results.hits = [
            {
                "id": str(doc_id),
                "title": "Meeting Notes",
                "content_plain": "Discussed project plans",
                "application_id": str(uuid4()),
                "project_id": None,
            },
        ]
        mock_index.search = AsyncMock(return_value=mock_results)

        svc = HybridRetrievalService(
            provider_registry=MagicMock(),
            normalizer=MagicMock(),
            db=MagicMock(),
        )

        scope_ids = {
            "app_ids": [uuid4()],
            "project_ids": [],
            "user_id": uuid4(),
        }

        with patch(
            "app.ai.retrieval_service.get_meili_index",
            return_value=mock_index,
        ):
            results = await svc._keyword_search("meeting", scope_ids)

        assert len(results) == 1
        assert results[0].source_type == "document"
        assert results[0].file_id is None

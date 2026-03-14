"""Tests for Markdown chunking extension and file embedding (Phase 4)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.ai.chunking_service import ChunkResult, SemanticChunker


# ============================================================================
# chunk_markdown Tests
# ============================================================================


class TestChunkMarkdown:
    """Tests for SemanticChunker.chunk_markdown."""

    def setup_method(self):
        self.chunker = SemanticChunker(target_tokens=600, overlap_tokens=100)

    def test_empty_markdown(self):
        """Empty input returns empty list."""
        assert self.chunker.chunk_markdown("", "Title") == []
        assert self.chunker.chunk_markdown("   ", "Title") == []

    def test_simple_text(self):
        """Simple text becomes a single chunk."""
        text = "This is a simple paragraph of text."
        chunks = self.chunker.chunk_markdown(text, "Test File")
        assert len(chunks) >= 1
        assert chunks[0].chunk_index == 0
        assert "simple paragraph" in chunks[0].text

    def test_heading_boundaries(self):
        """Chunks split at heading boundaries."""
        md = (
            "# Introduction\n\n"
            "Some intro text here.\n\n"
            "# Methods\n\n"
            "Some methods text here with more content to make it substantial. " * 20 + "\n\n"
            "# Results\n\n"
            "Some results text here with even more content. " * 20 + "\n"
        )
        chunks = self.chunker.chunk_markdown(md, "Research Paper")
        assert len(chunks) >= 2
        # Check that heading contexts are set
        headings = {c.heading_context for c in chunks if c.heading_context}
        assert len(headings) >= 2

    def test_pipe_table_detection(self):
        """Pipe tables are detected and chunked separately."""
        md = (
            "# Data\n\n"
            "| Name | Age | City |\n"
            "| --- | --- | --- |\n"
            "| Alice | 30 | NYC |\n"
            "| Bob | 25 | LA |\n"
            "\n"
            "Some text after the table.\n"
        )
        chunks = self.chunker.chunk_markdown(md, "Test")
        # Table should be in its own chunk (or merged with heading)
        all_text = " ".join(c.text for c in chunks)
        assert "Alice" in all_text
        assert "Bob" in all_text

    def test_large_table_split(self):
        """Tables with many rows should be split."""
        # Create a table with 200 rows
        header = "| Col1 | Col2 | Col3 |\n"
        rows = "".join(f"| val{i}_1 | val{i}_2 | val{i}_3 |\n" for i in range(200))
        md = f"# Big Table\n\n{header}{rows}"

        chunks = self.chunker.chunk_markdown(md, "Big Data", rows_per_chunk=50)
        # With 200 rows and 50 per chunk, should get multiple chunks
        assert len(chunks) >= 2

    def test_sequential_chunk_indices(self):
        """All chunks have sequential chunk_index values."""
        md = "# Section 1\n\nText 1\n\n# Section 2\n\nText 2\n"
        chunks = self.chunker.chunk_markdown(md, "Test")
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_mixed_content(self):
        """Mix of headings, text, and tables."""
        md = (
            "# Overview\n\n"
            "This document provides an overview.\n\n"
            "| Metric | Value |\n"
            "| --- | --- |\n"
            "| Revenue | $1M |\n"
            "| Costs | $500K |\n"
            "\n"
            "## Details\n\n"
            "More detailed analysis follows.\n"
        )
        chunks = self.chunker.chunk_markdown(md, "Report")
        assert len(chunks) >= 1
        all_text = " ".join(c.text for c in chunks)
        assert "Revenue" in all_text
        assert "detailed analysis" in all_text

    def test_heading_context_propagation(self):
        """Heading context propagates to subsequent text."""
        md = (
            "# Chapter 1\n\n"
            "Paragraph under chapter 1.\n\n"
            "More text under chapter 1.\n"
        )
        chunks = self.chunker.chunk_markdown(md, "Book")
        for chunk in chunks:
            # All chunks should have a heading context
            assert chunk.heading_context is not None

    def test_no_pipe_in_regular_text(self):
        """Regular text with pipe character is not treated as a table."""
        md = "This is text with a | pipe character.\n"
        chunks = self.chunker.chunk_markdown(md, "Test")
        assert len(chunks) >= 1


# ============================================================================
# EmbeddingService.embed_file Tests
# ============================================================================


class TestEmbedFile:
    """Tests for EmbeddingService.embed_file."""

    @pytest.mark.asyncio
    async def test_embed_file_empty_markdown(self):
        """Empty markdown produces zero chunks."""
        from app.ai.embedding_service import EmbeddingService

        mock_registry = MagicMock()
        mock_chunker = MagicMock()
        mock_chunker.chunk_markdown.return_value = []
        mock_normalizer = MagicMock()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(rowcount=0))

        svc = EmbeddingService(
            provider_registry=mock_registry,
            chunker=mock_chunker,
            normalizer=mock_normalizer,
            db=mock_db,
        )

        result = await svc.embed_file(
            file_id=uuid4(),
            markdown="",
            title="empty.csv",
            scope_ids={"application_id": uuid4()},
        )

        assert result.chunk_count == 0
        assert result.token_count == 0

    @pytest.mark.asyncio
    async def test_embed_file_with_content(self):
        """File with content produces chunks with source_type=file."""
        from app.ai.embedding_service import EmbeddingService

        file_id = uuid4()
        mock_registry = MagicMock()

        # Mock provider
        mock_provider = AsyncMock()
        mock_provider.generate_embeddings_batch = AsyncMock(
            return_value=[[0.1] * 1536, [0.2] * 1536]
        )
        mock_registry.get_embedding_provider = AsyncMock(
            return_value=(mock_provider, "text-embedding-3-small")
        )

        mock_chunker = MagicMock()
        mock_chunker.chunk_markdown.return_value = [
            ChunkResult(text="Chunk 1", heading_context="Sheet1", token_count=10, chunk_index=0),
            ChunkResult(text="Chunk 2", heading_context="Sheet1", token_count=15, chunk_index=1),
        ]

        mock_normalizer = MagicMock()
        mock_normalizer.normalize.side_effect = lambda x: x

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        mock_db.add_all = MagicMock()
        mock_db.flush = AsyncMock()

        svc = EmbeddingService(
            provider_registry=mock_registry,
            chunker=mock_chunker,
            normalizer=mock_normalizer,
            db=mock_db,
        )

        result = await svc.embed_file(
            file_id=file_id,
            markdown="Some table data",
            title="data.xlsx",
            scope_ids={"application_id": uuid4(), "project_id": None, "user_id": None},
        )

        assert result.chunk_count == 2
        assert result.token_count == 25

        # Verify chunks were added with file_id
        mock_db.add_all.assert_called_once()
        chunks = mock_db.add_all.call_args[0][0]
        assert len(chunks) == 2
        assert chunks[0].file_id == file_id
        assert chunks[0].source_type == "file"

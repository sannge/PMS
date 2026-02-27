"""Embedding pipeline service for document vector search.

Orchestrates the full document embedding pipeline: chunk -> embed -> store
in DocumentChunks. Handles single document embedding, batch processing, and
cleanup on document deletion.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import Document
from ..models.document_chunk import DocumentChunk
from ..utils.timezone import utc_now
from .chunking_service import SemanticChunker
from .embedding_normalizer import EmbeddingNormalizer
from .provider_interface import LLMProviderError
from .provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass
class EmbedResult:
    """Result of embedding a single document."""

    chunk_count: int
    token_count: int
    duration_ms: int


@dataclass
class BatchResult:
    """Result of batch embedding multiple documents."""

    total: int
    succeeded: int
    failed: int
    errors: list[str] = field(default_factory=list)


class EmbeddingService:
    """Orchestrates the full document embedding pipeline.

    Pipeline: chunk content -> generate embeddings -> normalize -> store in DB.

    Args:
        provider_registry: Registry for resolving embedding providers.
        chunker: Semantic chunking service instance.
        normalizer: Embedding vector normalizer.
        db: Async database session.
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        chunker: SemanticChunker,
        normalizer: EmbeddingNormalizer,
        db: AsyncSession,
    ) -> None:
        self.provider_registry = provider_registry
        self.chunker = chunker
        self.normalizer = normalizer
        self.db = db

    async def embed_document(
        self,
        document_id: UUID,
        content_json: dict,
        title: str,
        scope_ids: dict,
        document_type: str = "document",
    ) -> EmbedResult:
        """Full pipeline for one document.

        1. Chunk content using SemanticChunker
        2. Generate embeddings via provider (batch if possible)
        3. Normalize embeddings to target dimensions
        4. Delete existing chunks for this document (re-embed)
        5. Insert new DocumentChunk rows
        6. Update Document.embedding_updated_at
        7. Return EmbedResult

        Args:
            document_id: UUID of the document to embed.
            content_json: Parsed JSON content (TipTap or Canvas format).
            title: Document title for heading context.
            scope_ids: Dict with application_id, project_id, user_id for denormalization.
            document_type: "document" for TipTap, "canvas" for spatial canvas.

        Returns:
            EmbedResult with chunk_count, token_count, duration_ms.

        Raises:
            LLMProviderError: If embedding generation fails.
        """
        start_time = time.monotonic()

        # Step 1: Chunk content
        chunks = self.chunker.chunk_document(content_json, title, document_type)
        if not chunks:
            # Empty document - clean up any existing chunks
            await self.delete_document_chunks(document_id)
            await self._update_embedding_timestamp(document_id)
            elapsed = int((time.monotonic() - start_time) * 1000)
            return EmbedResult(chunk_count=0, token_count=0, duration_ms=elapsed)

        # Step 2: Generate embeddings via provider
        provider, model_id = await self.provider_registry.get_embedding_provider(self.db)
        texts = [chunk.text for chunk in chunks]

        try:
            raw_embeddings = await provider.generate_embeddings_batch(texts, model_id)
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(
                f"Embedding generation failed for document {document_id}: {e}",
                provider="unknown",
                original=e,
            )

        # Step 3: Normalize embeddings
        normalized_embeddings = [
            self.normalizer.normalize(emb) for emb in raw_embeddings
        ]

        # Step 4: Delete existing chunks (replace on re-embed)
        await self.delete_document_chunks(document_id)

        # Step 5: Insert new DocumentChunk rows
        total_tokens = 0
        new_chunks: list[DocumentChunk] = []
        for i, (chunk, embedding) in enumerate(zip(chunks, normalized_embeddings)):
            total_tokens += chunk.token_count
            db_chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.text,
                heading_context=chunk.heading_context,
                embedding=embedding,
                token_count=chunk.token_count,
                application_id=scope_ids.get("application_id"),
                project_id=scope_ids.get("project_id"),
                user_id=scope_ids.get("user_id"),
            )
            new_chunks.append(db_chunk)

        self.db.add_all(new_chunks)
        await self.db.flush()

        # Step 6: Update Document.embedding_updated_at
        await self._update_embedding_timestamp(document_id)

        elapsed = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "Embedded document %s: %d chunks, %d tokens, %dms",
            document_id, len(chunks), total_tokens, elapsed,
        )

        # Telemetry: log embedding operation
        try:
            from .telemetry import AITelemetry

            provider_name = getattr(provider, "provider_name", "unknown")
            await AITelemetry.log_embedding_batch(
                document_count=1,
                chunk_count=len(chunks),
                total_tokens=total_tokens,
                provider=provider_name,
                model=model_id or "unknown",
                duration_ms=elapsed,
                success=True,
            )
        except Exception:
            pass  # Non-critical — don't fail embedding on telemetry error

        return EmbedResult(
            chunk_count=len(chunks),
            token_count=total_tokens,
            duration_ms=elapsed,
        )

    async def embed_documents_batch(
        self,
        document_ids: list[UUID],
    ) -> BatchResult:
        """Batch processing for reindexing.

        Each document is processed within a savepoint so that a failure
        in document N only rolls back that document's changes, leaving
        previously successful documents intact.

        Args:
            document_ids: List of document UUIDs to embed.

        Returns:
            BatchResult with total, succeeded, failed, errors.
        """
        total = len(document_ids)
        succeeded = 0
        failed = 0
        errors: list[str] = []

        for doc_id in document_ids:
            try:
                async with self.db.begin_nested():
                    result = await self.db.execute(
                        select(Document).where(
                            Document.id == doc_id,
                            Document.deleted_at.is_(None),
                        )
                    )
                    doc = result.scalar_one_or_none()

                    if doc is None:
                        logger.warning("Batch embed: document %s not found or deleted, skipping", doc_id)
                        failed += 1
                        errors.append(f"Document {doc_id} not found or deleted")
                        continue

                    if not doc.content_json:
                        logger.debug("Batch embed: document %s has no content, skipping", doc_id)
                        succeeded += 1
                        continue

                    content = json.loads(doc.content_json)

                    scope_ids = {
                        "application_id": doc.application_id,
                        "project_id": doc.project_id,
                        "user_id": doc.user_id,
                    }

                    # TODO: Pass document_type when Canvas support is added
                    await self.embed_document(
                        document_id=doc_id,
                        content_json=content,
                        title=doc.title,
                        scope_ids=scope_ids,
                    )
                    succeeded += 1

            except Exception as e:
                failed += 1
                error_msg = f"Document {doc_id}: {type(e).__name__}"
                errors.append(error_msg)
                logger.error("Batch embed failed for document %s: %s", doc_id, e)

        logger.info(
            "Batch embed complete: total=%d, succeeded=%d, failed=%d",
            total, succeeded, failed,
        )

        return BatchResult(
            total=total,
            succeeded=succeeded,
            failed=failed,
            errors=errors,
        )

    async def delete_document_chunks(self, document_id: UUID) -> int:
        """Remove all chunks for a document.

        Called when document is deleted or before re-embedding.

        Args:
            document_id: UUID of the document.

        Returns:
            Count of deleted chunks.
        """
        result = await self.db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        )
        count = result.rowcount
        if count > 0:
            logger.debug("Deleted %d chunks for document %s", count, document_id)
        return count

    async def _update_embedding_timestamp(self, document_id: UUID) -> None:
        """Set Document.embedding_updated_at to current UTC time."""
        await self.db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(embedding_updated_at=utc_now())
        )

"""DocumentChunk SQLAlchemy model for vector embeddings.

Stores chunked content with pgvector embeddings for semantic search.
Each chunk belongs to exactly one source: either a Document or a FolderFile,
enforced by a CHECK constraint. Chunks are replaced entirely when the source
is re-embedded. Includes denormalized scope fields (application_id,
project_id, user_id) for fast RBAC-filtered similarity search.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils.timezone import utc_now


class DocumentChunk(Base):
    """
    DocumentChunk model for vector embeddings.

    Each chunk represents a segment of content from either a Document or
    a FolderFile, with its pgvector embedding for semantic similarity
    search. Exactly one of document_id or file_id must be set (enforced
    by CHECK constraint). Scope fields are denormalized from the parent
    source to enable fast RBAC-filtered vector queries without joins.

    Attributes:
        id: Unique identifier (UUID)
        document_id: FK to Documents (CASCADE delete, nullable for file chunks)
        file_id: FK to FolderFiles (CASCADE delete, nullable for document chunks)
        source_type: Source discriminator — "document" or "file"
        chunk_index: Position of this chunk within the source
        chunk_text: Plain text content of this chunk
        chunk_type: Type of chunk content — "text" (default) or "image"
        heading_context: Nearest heading for context (nullable)
        embedding: pgvector embedding (1536 dimensions for text-embedding-3-small)
        token_count: Number of tokens in this chunk
        application_id: Denormalized scope FK for RBAC filtering (nullable)
        project_id: Denormalized scope FK for RBAC filtering (nullable)
        user_id: Denormalized scope FK for RBAC filtering (nullable)
        created_at: Timestamp when chunk was created
        updated_at: Timestamp when chunk was last updated
    """

    __tablename__ = "DocumentChunks"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Parent document (nullable for file-sourced chunks)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Documents.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Parent file (nullable for document-sourced chunks)
    file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("FolderFiles.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Source discriminator: "document" or "file"
    source_type = Column(
        String(10),
        nullable=False,
        default="document",
    )

    # Chunk position within source
    chunk_index = Column(
        Integer,
        nullable=False,
    )

    # Chunk content
    chunk_text = Column(
        Text,
        nullable=False,
    )

    # Chunk type: "text" (default) or "image" (vision-described)
    chunk_type = Column(
        String(20),
        nullable=False,
        default="text",
    )

    # Nearest heading for context
    heading_context = Column(
        String(500),
        nullable=True,
    )

    # pgvector embedding (1536 dimensions for text-embedding-3-small)
    embedding = Column(
        Vector(1536),
        nullable=True,
    )

    # Token count for this chunk
    token_count = Column(
        Integer,
        nullable=False,
    )

    # Denormalized scope fields for RBAC-filtered similarity search
    application_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    project_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    user_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "(document_id IS NOT NULL AND file_id IS NULL)"
            " OR (document_id IS NULL AND file_id IS NOT NULL)",
            name="ck_chunks_exactly_one_source",
        ),
        Index("idx_document_chunks_doc_idx", "document_id", "chunk_index", unique=True),
        Index(
            "idx_document_chunks_file_idx",
            "file_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("file_id IS NOT NULL"),
        ),
    )

    # Relationships
    document = relationship(
        "Document",
        back_populates="chunks",
    )

    file = relationship(
        "FolderFile",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        """String representation of DocumentChunk."""
        source = f"document_id={self.document_id}" if self.document_id else f"file_id={self.file_id}"
        return f"<DocumentChunk(id={self.id}, {source}, chunk_index={self.chunk_index})>"

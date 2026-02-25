"""Add DocumentChunks table and embedding columns to Documents.

Creates the DocumentChunks table for storing chunked document text with
pgvector embeddings for semantic search. Also adds embedding_updated_at
and graph_ingested_at tracking columns to Documents, plus a trigram GIN
index on Documents.title for fuzzy text search.

Revision ID: 20260225_doc_chunks
Revises: 20260225_pgvector_ext
Create Date: 2026-02-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260225_doc_chunks"
down_revision: Union[str, None] = "20260225_pgvector_ext"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create DocumentChunks table and add embedding columns to Documents."""
    # ========================================================================
    # 1. Create DocumentChunks table
    # ========================================================================
    op.create_table(
        'DocumentChunks',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('heading_context', sa.String(length=500), nullable=True),
        # embedding column added via raw SQL (pgvector type not in SA core)
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.UUID(), nullable=True),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['Documents.id'], ondelete='CASCADE'),
    )

    # Add the embedding column using pgvector type (not available in SA core)
    op.execute(
        'ALTER TABLE "DocumentChunks" ADD COLUMN embedding vector(1536)'
    )

    # ========================================================================
    # 2. Create indexes on DocumentChunks
    # ========================================================================

    # HNSW index for approximate nearest neighbor cosine similarity search
    op.execute(
        'CREATE INDEX idx_document_chunks_embedding '
        'ON "DocumentChunks" USING hnsw (embedding vector_cosine_ops) '
        'WITH (m = 16, ef_construction = 200)'
    )

    # Unique composite index: one chunk per index position per document
    op.execute(
        'CREATE UNIQUE INDEX idx_document_chunks_doc_idx '
        'ON "DocumentChunks" (document_id, chunk_index)'
    )

    # Denormalized scope indexes for filtered vector search
    op.create_index('idx_document_chunks_app', 'DocumentChunks', ['application_id'])
    op.create_index('idx_document_chunks_project', 'DocumentChunks', ['project_id'])
    op.create_index('idx_document_chunks_user', 'DocumentChunks', ['user_id'])

    # ========================================================================
    # 3. Add embedding tracking columns to Documents
    # ========================================================================
    op.add_column(
        'Documents',
        sa.Column('embedding_updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'Documents',
        sa.Column('graph_ingested_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Trigram GIN index for fuzzy title search
    op.execute(
        'CREATE INDEX idx_documents_title_trgm '
        'ON "Documents" USING GIN (title gin_trgm_ops)'
    )


def downgrade() -> None:
    """Drop DocumentChunks table and remove embedding columns from Documents."""
    # ========================================================================
    # 1. Drop trigram index and columns from Documents
    # ========================================================================
    op.execute('DROP INDEX IF EXISTS idx_documents_title_trgm')
    op.drop_column('Documents', 'graph_ingested_at')
    op.drop_column('Documents', 'embedding_updated_at')

    # ========================================================================
    # 2. Drop indexes on DocumentChunks
    # ========================================================================
    op.drop_index('idx_document_chunks_user', table_name='DocumentChunks')
    op.drop_index('idx_document_chunks_project', table_name='DocumentChunks')
    op.drop_index('idx_document_chunks_app', table_name='DocumentChunks')
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_doc_idx')
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_embedding')

    # ========================================================================
    # 3. Drop DocumentChunks table
    # ========================================================================
    op.drop_table('DocumentChunks')

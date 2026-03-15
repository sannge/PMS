"""Add 'failed' to documents.embedding_status check constraint.

Documents can now have embedding_status='failed' when the embedding
worker encounters an error, matching the folder_files behavior.

Revision ID: 20260314_doc_embed_failed
Revises: 20260313_nullable_folder
Create Date: 2026-03-14
"""
from alembic import op

revision = "20260314_doc_embed_failed"
down_revision = "20260313_nullable_folder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "Documents" DROP CONSTRAINT IF EXISTS ck_documents_embedding_status')
    op.execute(
        'ALTER TABLE "Documents" ADD CONSTRAINT ck_documents_embedding_status '
        "CHECK (embedding_status IN ('none', 'stale', 'syncing', 'synced', 'failed'))"
    )


def downgrade() -> None:
    op.execute(
        'UPDATE "Documents" SET embedding_status = \'stale\' '
        "WHERE embedding_status = 'failed'"
    )
    op.execute('ALTER TABLE "Documents" DROP CONSTRAINT IF EXISTS ck_documents_embedding_status')
    op.execute(
        'ALTER TABLE "Documents" ADD CONSTRAINT ck_documents_embedding_status '
        "CHECK (embedding_status IN ('none', 'stale', 'syncing', 'synced'))"
    )

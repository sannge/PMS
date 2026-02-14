"""Drop Notes table, create Documents/DocumentFolders/DocumentSnapshots tables

Atomically migrates from the old Notes system to the new knowledge base
document model. Drops the Notes table and note_id FK from Attachments,
then creates DocumentFolders, Documents, and DocumentSnapshots tables
with scope CHECK constraints, materialized path, and composite indexes.

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-01-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop Notes table and create new document tables."""
    # ========================================================================
    # 1. Drop note_id FK and column from Attachments
    # ========================================================================
    op.drop_index('ix_Attachments_note_id', table_name='Attachments')
    op.drop_constraint('Attachments_note_id_fkey', 'Attachments', type_='foreignkey')
    op.drop_column('Attachments', 'note_id')

    # ========================================================================
    # 2. Drop Notes table
    # ========================================================================
    op.drop_index(op.f('ix_Notes_title'), table_name='Notes')
    op.drop_index(op.f('ix_Notes_parent_id'), table_name='Notes')
    op.drop_index(op.f('ix_Notes_created_by'), table_name='Notes')
    op.drop_index(op.f('ix_Notes_application_id'), table_name='Notes')
    op.drop_table('Notes')

    # ========================================================================
    # 3. Create DocumentFolders table
    # ========================================================================
    op.create_table(
        'DocumentFolders',
        sa.Column('id', sa.UUID(), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('materialized_path', sa.String(length=4000), nullable=False, server_default='/'),
        sa.Column('depth', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('application_id', sa.UUID(), nullable=True),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['parent_id'], ['DocumentFolders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['application_id'], ['Applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['Projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['Users.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name='ck_document_folders_exactly_one_scope',
        ),
    )
    op.create_index(op.f('ix_DocumentFolders_parent_id'), 'DocumentFolders', ['parent_id'])
    op.create_index(op.f('ix_DocumentFolders_materialized_path'), 'DocumentFolders', ['materialized_path'])
    op.create_index(op.f('ix_DocumentFolders_application_id'), 'DocumentFolders', ['application_id'])
    op.create_index(op.f('ix_DocumentFolders_project_id'), 'DocumentFolders', ['project_id'])
    op.create_index(op.f('ix_DocumentFolders_user_id'), 'DocumentFolders', ['user_id'])
    op.create_index(op.f('ix_DocumentFolders_created_by'), 'DocumentFolders', ['created_by'])

    # ========================================================================
    # 4. Create Documents table
    # ========================================================================
    op.create_table(
        'Documents',
        sa.Column('id', sa.UUID(), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('application_id', sa.UUID(), nullable=True),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('folder_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content_json', sa.Text(), nullable=True),
        sa.Column('content_markdown', sa.Text(), nullable=True),
        sa.Column('content_plain', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['Applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['Projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['DocumentFolders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['Users.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN project_id IS NOT NULL THEN 1 ELSE 0 END"
            " + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name='ck_documents_exactly_one_scope',
        ),
    )
    op.create_index(op.f('ix_Documents_application_id'), 'Documents', ['application_id'])
    op.create_index(op.f('ix_Documents_project_id'), 'Documents', ['project_id'])
    op.create_index(op.f('ix_Documents_user_id'), 'Documents', ['user_id'])
    op.create_index(op.f('ix_Documents_folder_id'), 'Documents', ['folder_id'])
    op.create_index(op.f('ix_Documents_title'), 'Documents', ['title'])
    op.create_index(op.f('ix_Documents_created_by'), 'Documents', ['created_by'])
    op.create_index(op.f('ix_Documents_deleted_at'), 'Documents', ['deleted_at'])
    op.create_index('ix_documents_app_folder', 'Documents', ['application_id', 'folder_id'])
    op.create_index('ix_documents_project_folder', 'Documents', ['project_id', 'folder_id'])

    # ========================================================================
    # 5. Create DocumentSnapshots table
    # ========================================================================
    op.create_table(
        'DocumentSnapshots',
        sa.Column('id', sa.UUID(), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('content_json', sa.Text(), nullable=True),
        sa.Column('snapshot_type', sa.String(length=50), nullable=False, server_default='auto'),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['Documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['Users.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_DocumentSnapshots_document_id'), 'DocumentSnapshots', ['document_id'])


def downgrade() -> None:
    """Drop new document tables and recreate Notes table."""
    # ========================================================================
    # 1. Drop DocumentSnapshots
    # ========================================================================
    op.drop_index(op.f('ix_DocumentSnapshots_document_id'), table_name='DocumentSnapshots')
    op.drop_table('DocumentSnapshots')

    # ========================================================================
    # 2. Drop Documents
    # ========================================================================
    op.drop_index('ix_documents_project_folder', table_name='Documents')
    op.drop_index('ix_documents_app_folder', table_name='Documents')
    op.drop_index(op.f('ix_Documents_deleted_at'), table_name='Documents')
    op.drop_index(op.f('ix_Documents_created_by'), table_name='Documents')
    op.drop_index(op.f('ix_Documents_title'), table_name='Documents')
    op.drop_index(op.f('ix_Documents_folder_id'), table_name='Documents')
    op.drop_index(op.f('ix_Documents_user_id'), table_name='Documents')
    op.drop_index(op.f('ix_Documents_project_id'), table_name='Documents')
    op.drop_index(op.f('ix_Documents_application_id'), table_name='Documents')
    op.drop_table('Documents')

    # ========================================================================
    # 3. Drop DocumentFolders
    # ========================================================================
    op.drop_index(op.f('ix_DocumentFolders_created_by'), table_name='DocumentFolders')
    op.drop_index(op.f('ix_DocumentFolders_user_id'), table_name='DocumentFolders')
    op.drop_index(op.f('ix_DocumentFolders_project_id'), table_name='DocumentFolders')
    op.drop_index(op.f('ix_DocumentFolders_application_id'), table_name='DocumentFolders')
    op.drop_index(op.f('ix_DocumentFolders_materialized_path'), table_name='DocumentFolders')
    op.drop_index(op.f('ix_DocumentFolders_parent_id'), table_name='DocumentFolders')
    op.drop_table('DocumentFolders')

    # ========================================================================
    # 4. Recreate Notes table (stub for rollback)
    # ========================================================================
    op.create_table(
        'Notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('application_id', sa.UUID(), nullable=False),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('tab_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['Applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['Users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_id'], ['Notes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_Notes_application_id'), 'Notes', ['application_id'])
    op.create_index(op.f('ix_Notes_created_by'), 'Notes', ['created_by'])
    op.create_index(op.f('ix_Notes_parent_id'), 'Notes', ['parent_id'])
    op.create_index(op.f('ix_Notes_title'), 'Notes', ['title'])

    # ========================================================================
    # 5. Recreate note_id column on Attachments
    # ========================================================================
    op.add_column('Attachments', sa.Column('note_id', sa.UUID(), nullable=True))
    op.create_foreign_key('Attachments_note_id_fkey', 'Attachments', 'Notes', ['note_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_Attachments_note_id', 'Attachments', ['note_id'])

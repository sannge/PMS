"""add document tags

Revision ID: e3440224ad17
Revises: e5f6g7h8i9j0
Create Date: 2026-01-31 18:34:12.787429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3440224ad17'
down_revision: Union[str, None] = 'e5f6g7h8i9j0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create DocumentTags and DocumentTagAssignments tables."""
    op.create_table('DocumentTags',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('application_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('(CASE WHEN application_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) = 1', name='ck_document_tags_exactly_one_scope'),
    sa.ForeignKeyConstraint(['application_id'], ['Applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_DocumentTags_application_id'), 'DocumentTags', ['application_id'], unique=False)
    op.create_index(op.f('ix_DocumentTags_user_id'), 'DocumentTags', ['user_id'], unique=False)
    op.create_index('uq_document_tags_app_name', 'DocumentTags', ['application_id', 'name'], unique=True, postgresql_where='application_id IS NOT NULL')
    op.create_index('uq_document_tags_user_name', 'DocumentTags', ['user_id', 'name'], unique=True, postgresql_where='user_id IS NOT NULL')

    op.create_table('DocumentTagAssignments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('tag_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['Documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['DocumentTags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'tag_id', name='uq_document_tag_assignments_doc_tag')
    )
    op.create_index(op.f('ix_DocumentTagAssignments_document_id'), 'DocumentTagAssignments', ['document_id'], unique=False)
    op.create_index(op.f('ix_DocumentTagAssignments_tag_id'), 'DocumentTagAssignments', ['tag_id'], unique=False)


def downgrade() -> None:
    """Drop DocumentTagAssignments and DocumentTags tables."""
    op.drop_index(op.f('ix_DocumentTagAssignments_tag_id'), table_name='DocumentTagAssignments')
    op.drop_index(op.f('ix_DocumentTagAssignments_document_id'), table_name='DocumentTagAssignments')
    op.drop_table('DocumentTagAssignments')
    op.drop_index('uq_document_tags_user_name', table_name='DocumentTags', postgresql_where='user_id IS NOT NULL')
    op.drop_index('uq_document_tags_app_name', table_name='DocumentTags', postgresql_where='application_id IS NOT NULL')
    op.drop_index(op.f('ix_DocumentTags_user_id'), table_name='DocumentTags')
    op.drop_index(op.f('ix_DocumentTags_application_id'), table_name='DocumentTags')
    op.drop_table('DocumentTags')

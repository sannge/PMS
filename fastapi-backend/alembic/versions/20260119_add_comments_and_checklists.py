"""add_comments_and_checklists

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-01-19 10:00:00.000000

This migration adds comments and checklists tables:
1. Creates Comments table for task discussions
2. Creates Mentions table for @mentions in comments
3. Creates Checklists table for task checklists
4. Creates ChecklistItems table for checklist items
5. Adds checklist_total and checklist_done columns to Tasks

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ==========================================================================
    # 1. Create Comments table
    # ==========================================================================
    op.create_table('Comments',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('task_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('author_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('body_json', sa.Text(), nullable=True),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('is_deleted', mssql.BIT(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['Tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['Users.id'], ondelete='NO ACTION'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_Comments_task_id'), 'Comments', ['task_id'], unique=False)
    op.create_index(op.f('ix_Comments_author_id'), 'Comments', ['author_id'], unique=False)
    # Covering index for common query pattern: Get comments for a task (newest first)
    op.create_index(
        'IX_Comments_TaskId_CreatedAt',
        'Comments',
        ['task_id', sa.text('created_at DESC')],
    )

    # ==========================================================================
    # 2. Create Mentions table
    # ==========================================================================
    op.create_table('Mentions',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('comment_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('user_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['Comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('comment_id', 'user_id', name='UX_Mentions_Comment_User')
    )
    op.create_index(op.f('ix_Mentions_comment_id'), 'Mentions', ['comment_id'], unique=False)
    op.create_index(op.f('ix_Mentions_user_id'), 'Mentions', ['user_id'], unique=False)
    # Index for notification queries: Get all mentions for a user (newest first)
    op.create_index(
        'IX_Mentions_UserId_CreatedAt',
        'Mentions',
        ['user_id', sa.text('created_at DESC')],
    )

    # ==========================================================================
    # 3. Create Checklists table
    # ==========================================================================
    op.create_table('Checklists',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('task_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('rank', sa.String(length=50), nullable=False),
        sa.Column('total_items', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_items', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['Tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_Checklists_task_id'), 'Checklists', ['task_id'], unique=False)
    # Index for ordered checklist retrieval
    op.create_index(
        'IX_Checklists_TaskId_Rank',
        'Checklists',
        ['task_id', 'rank'],
    )

    # ==========================================================================
    # 4. Create ChecklistItems table
    # ==========================================================================
    op.create_table('ChecklistItems',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('checklist_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_done', mssql.BIT(), nullable=False, server_default='0'),
        sa.Column('completed_by', mssql.UNIQUEIDENTIFIER(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('rank', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['checklist_id'], ['Checklists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['completed_by'], ['Users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ChecklistItems_checklist_id'), 'ChecklistItems', ['checklist_id'], unique=False)
    # Index for ordered item retrieval
    op.create_index(
        'IX_ChecklistItems_ChecklistId_Rank',
        'ChecklistItems',
        ['checklist_id', 'rank'],
    )

    # ==========================================================================
    # 5. Add checklist count columns to Tasks table
    # ==========================================================================
    op.add_column('Tasks', sa.Column('checklist_total', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('Tasks', sa.Column('checklist_done', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade database schema."""
    # ==========================================================================
    # 1. Remove checklist count columns from Tasks table
    # ==========================================================================
    op.drop_column('Tasks', 'checklist_done')
    op.drop_column('Tasks', 'checklist_total')

    # ==========================================================================
    # 2. Drop ChecklistItems table
    # ==========================================================================
    op.drop_index('IX_ChecklistItems_ChecklistId_Rank', table_name='ChecklistItems')
    op.drop_index(op.f('ix_ChecklistItems_checklist_id'), table_name='ChecklistItems')
    op.drop_table('ChecklistItems')

    # ==========================================================================
    # 3. Drop Checklists table
    # ==========================================================================
    op.drop_index('IX_Checklists_TaskId_Rank', table_name='Checklists')
    op.drop_index(op.f('ix_Checklists_task_id'), table_name='Checklists')
    op.drop_table('Checklists')

    # ==========================================================================
    # 4. Drop Mentions table
    # ==========================================================================
    op.drop_index('IX_Mentions_UserId_CreatedAt', table_name='Mentions')
    op.drop_index(op.f('ix_Mentions_user_id'), table_name='Mentions')
    op.drop_index(op.f('ix_Mentions_comment_id'), table_name='Mentions')
    op.drop_table('Mentions')

    # ==========================================================================
    # 5. Drop Comments table
    # ==========================================================================
    op.drop_index('IX_Comments_TaskId_CreatedAt', table_name='Comments')
    op.drop_index(op.f('ix_Comments_author_id'), table_name='Comments')
    op.drop_index(op.f('ix_Comments_task_id'), table_name='Comments')
    op.drop_table('Comments')

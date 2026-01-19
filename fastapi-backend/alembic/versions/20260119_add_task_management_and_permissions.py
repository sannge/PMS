"""add_task_management_and_permissions

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-01-19 00:00:00.000000

This migration adds the task management and permissions system:
1. Creates TaskStatuses table for unified 5-status system
2. Creates ProjectMembers table for project team gate
3. Creates ProjectTaskStatusAgg table for status derivation counters
4. Extends Tasks table with task_status_id, task_rank, row_version
5. Extends Projects table with status derivation and override fields
6. Migrates 'blocked' status to 'issue' in existing tasks

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ==========================================================================
    # 1. Create TaskStatuses table
    # ==========================================================================
    op.create_table('TaskStatuses',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('project_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['Projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_TaskStatuses_project_id'), 'TaskStatuses', ['project_id'], unique=False)
    op.create_index(op.f('ix_TaskStatuses_name'), 'TaskStatuses', ['name'], unique=False)
    op.create_index(op.f('ix_TaskStatuses_category'), 'TaskStatuses', ['category'], unique=False)

    # ==========================================================================
    # 2. Create ProjectMembers table
    # Note: SQL Server doesn't allow multiple CASCADE paths to same table
    # So user_id uses CASCADE but added_by_user_id uses SET NULL
    # ==========================================================================
    op.create_table('ProjectMembers',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('project_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('user_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('added_by_user_id', mssql.UNIQUEIDENTIFIER(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['Projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['added_by_user_id'], ['Users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'user_id', name='UQ_ProjectMembers_Project_User')
    )
    op.create_index(op.f('ix_ProjectMembers_project_id'), 'ProjectMembers', ['project_id'], unique=False)
    op.create_index(op.f('ix_ProjectMembers_user_id'), 'ProjectMembers', ['user_id'], unique=False)
    op.create_index(op.f('ix_ProjectMembers_added_by_user_id'), 'ProjectMembers', ['added_by_user_id'], unique=False)
    op.create_index(op.f('ix_ProjectMembers_created_at'), 'ProjectMembers', ['created_at'], unique=False)

    # ==========================================================================
    # 3. Create ProjectTaskStatusAgg table
    # ==========================================================================
    op.create_table('ProjectTaskStatusAgg',
        sa.Column('project_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('total_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('todo_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('review_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('issue_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('done_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['Projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('project_id')
    )

    # ==========================================================================
    # 4. Add new columns to Tasks table
    # ==========================================================================
    # Add task_status_id column with foreign key
    op.add_column('Tasks', sa.Column('task_status_id', mssql.UNIQUEIDENTIFIER(), nullable=True))
    op.create_index(op.f('ix_Tasks_task_status_id'), 'Tasks', ['task_status_id'], unique=False)
    op.create_foreign_key(
        'fk_Tasks_task_status_id_TaskStatuses',
        'Tasks', 'TaskStatuses',
        ['task_status_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add task_rank column for lexorank ordering
    op.add_column('Tasks', sa.Column('task_rank', sa.String(length=50), nullable=True))

    # Add row_version column for optimistic concurrency
    op.add_column('Tasks', sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'))

    # ==========================================================================
    # 5. Add new columns to Projects table
    # Note: SQL Server doesn't allow multiple CASCADE paths to same table
    # All user FKs use SET NULL, all TaskStatus FKs use SET NULL
    # ==========================================================================
    # Add project_owner_user_id column
    op.add_column('Projects', sa.Column('project_owner_user_id', mssql.UNIQUEIDENTIFIER(), nullable=True))
    op.create_index(op.f('ix_Projects_project_owner_user_id'), 'Projects', ['project_owner_user_id'], unique=False)
    op.create_foreign_key(
        'fk_Projects_project_owner_user_id_Users',
        'Projects', 'Users',
        ['project_owner_user_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add derived_status_id column
    op.add_column('Projects', sa.Column('derived_status_id', mssql.UNIQUEIDENTIFIER(), nullable=True))
    op.create_index(op.f('ix_Projects_derived_status_id'), 'Projects', ['derived_status_id'], unique=False)
    op.create_foreign_key(
        'fk_Projects_derived_status_id_TaskStatuses',
        'Projects', 'TaskStatuses',
        ['derived_status_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add override_status_id column
    op.add_column('Projects', sa.Column('override_status_id', mssql.UNIQUEIDENTIFIER(), nullable=True))
    op.create_index(op.f('ix_Projects_override_status_id'), 'Projects', ['override_status_id'], unique=False)
    op.create_foreign_key(
        'fk_Projects_override_status_id_TaskStatuses',
        'Projects', 'TaskStatuses',
        ['override_status_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add override_reason column
    op.add_column('Projects', sa.Column('override_reason', sa.String(length=500), nullable=True))

    # Add override_by_user_id column
    op.add_column('Projects', sa.Column('override_by_user_id', mssql.UNIQUEIDENTIFIER(), nullable=True))
    op.create_index(op.f('ix_Projects_override_by_user_id'), 'Projects', ['override_by_user_id'], unique=False)
    op.create_foreign_key(
        'fk_Projects_override_by_user_id_Users',
        'Projects', 'Users',
        ['override_by_user_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add override_expires_at column
    op.add_column('Projects', sa.Column('override_expires_at', sa.DateTime(), nullable=True))

    # Add row_version column for optimistic concurrency
    op.add_column('Projects', sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'))

    # ==========================================================================
    # 6. Data migration: Rename 'blocked' status to 'issue' in existing tasks
    # ==========================================================================
    op.execute("UPDATE Tasks SET status = 'issue' WHERE status = 'blocked'")


def downgrade() -> None:
    """Downgrade database schema."""
    # ==========================================================================
    # 1. Revert data migration: Rename 'issue' status back to 'blocked'
    # ==========================================================================
    op.execute("UPDATE Tasks SET status = 'blocked' WHERE status = 'issue'")

    # ==========================================================================
    # 2. Remove columns from Projects table
    # ==========================================================================
    op.drop_column('Projects', 'row_version')
    op.drop_column('Projects', 'override_expires_at')
    op.drop_constraint('fk_Projects_override_by_user_id_Users', 'Projects', type_='foreignkey')
    op.drop_index(op.f('ix_Projects_override_by_user_id'), table_name='Projects')
    op.drop_column('Projects', 'override_by_user_id')
    op.drop_column('Projects', 'override_reason')
    op.drop_constraint('fk_Projects_override_status_id_TaskStatuses', 'Projects', type_='foreignkey')
    op.drop_index(op.f('ix_Projects_override_status_id'), table_name='Projects')
    op.drop_column('Projects', 'override_status_id')
    op.drop_constraint('fk_Projects_derived_status_id_TaskStatuses', 'Projects', type_='foreignkey')
    op.drop_index(op.f('ix_Projects_derived_status_id'), table_name='Projects')
    op.drop_column('Projects', 'derived_status_id')
    op.drop_constraint('fk_Projects_project_owner_user_id_Users', 'Projects', type_='foreignkey')
    op.drop_index(op.f('ix_Projects_project_owner_user_id'), table_name='Projects')
    op.drop_column('Projects', 'project_owner_user_id')

    # ==========================================================================
    # 3. Remove columns from Tasks table
    # ==========================================================================
    op.drop_column('Tasks', 'row_version')
    op.drop_column('Tasks', 'task_rank')
    op.drop_constraint('fk_Tasks_task_status_id_TaskStatuses', 'Tasks', type_='foreignkey')
    op.drop_index(op.f('ix_Tasks_task_status_id'), table_name='Tasks')
    op.drop_column('Tasks', 'task_status_id')

    # ==========================================================================
    # 4. Drop ProjectTaskStatusAgg table
    # ==========================================================================
    op.drop_table('ProjectTaskStatusAgg')

    # ==========================================================================
    # 5. Drop ProjectMembers table
    # ==========================================================================
    op.drop_index(op.f('ix_ProjectMembers_created_at'), table_name='ProjectMembers')
    op.drop_index(op.f('ix_ProjectMembers_added_by_user_id'), table_name='ProjectMembers')
    op.drop_index(op.f('ix_ProjectMembers_user_id'), table_name='ProjectMembers')
    op.drop_index(op.f('ix_ProjectMembers_project_id'), table_name='ProjectMembers')
    op.drop_table('ProjectMembers')

    # ==========================================================================
    # 6. Drop TaskStatuses table
    # ==========================================================================
    op.drop_index(op.f('ix_TaskStatuses_category'), table_name='TaskStatuses')
    op.drop_index(op.f('ix_TaskStatuses_name'), table_name='TaskStatuses')
    op.drop_index(op.f('ix_TaskStatuses_project_id'), table_name='TaskStatuses')
    op.drop_table('TaskStatuses')

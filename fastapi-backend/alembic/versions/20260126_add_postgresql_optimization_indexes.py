"""add_postgresql_optimization_indexes

Revision ID: f8a9c3d5e712
Revises: 26b648a3dc17
Create Date: 2026-01-26 14:30:00.000000

PostgreSQL-specific performance optimizations:
- Composite indexes for common query patterns
- BRIN indexes for time-series data (10-100x smaller than B-tree)
- Partial indexes for filtered queries (smaller and faster)
- Covering indexes to avoid table lookups

These indexes target 5,000+ concurrent users.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'f8a9c3d5e712'
down_revision: Union[str, None] = '8f3a2b1c4d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add PostgreSQL optimization indexes."""
    # ========================================================================
    # PHASE 1: Composite Indexes for Common Query Patterns
    # ========================================================================

    # Tasks - Most queried table
    # Used by: Kanban board (project_id + status), task filtering
    op.create_index(
        'ix_Tasks_project_status',
        'Tasks',
        ['project_id', 'status'],
        postgresql_using='btree'
    )

    # Used by: Task ordering within project/status columns
    op.create_index(
        'ix_Tasks_project_rank',
        'Tasks',
        ['project_id', 'task_rank'],
        postgresql_using='btree'
    )

    # Used by: "My tasks" queries filtering by assignee and status
    op.create_index(
        'ix_Tasks_assignee_status',
        'Tasks',
        ['assignee_id', 'status'],
        postgresql_using='btree'
    )

    # Used by: Task status ID lookups (new unified status system)
    op.create_index(
        'ix_Tasks_project_status_id',
        'Tasks',
        ['project_id', 'task_status_id'],
        postgresql_using='btree'
    )

    # Comments - Frequently filtered by task with time ordering
    op.create_index(
        'ix_Comments_task_created',
        'Comments',
        ['task_id', 'created_at'],
        postgresql_using='btree'
    )

    # Notifications - User + read status is common filter pattern
    op.create_index(
        'ix_Notifications_user_read_created',
        'Notifications',
        ['user_id', 'is_read', 'created_at'],
        postgresql_using='btree'
    )

    # Checklists - Task lookup with rank ordering
    op.create_index(
        'ix_Checklists_task_rank',
        'Checklists',
        ['task_id', 'rank'],
        postgresql_using='btree'
    )

    # ChecklistItems - Checklist lookup with rank ordering
    op.create_index(
        'ix_ChecklistItems_checklist_rank',
        'ChecklistItems',
        ['checklist_id', 'rank'],
        postgresql_using='btree'
    )

    # ApplicationMembers - Application + role for permission checks
    op.create_index(
        'ix_ApplicationMembers_app_role',
        'ApplicationMembers',
        ['application_id', 'role'],
        postgresql_using='btree'
    )

    # ApplicationMembers - User + application for membership lookups
    op.create_index(
        'ix_ApplicationMembers_user_app',
        'ApplicationMembers',
        ['user_id', 'application_id'],
        postgresql_using='btree'
    )

    # ProjectMembers - User + project for permission checks
    op.create_index(
        'ix_ProjectMembers_user_project',
        'ProjectMembers',
        ['user_id', 'project_id'],
        postgresql_using='btree'
    )

    # ========================================================================
    # PHASE 2: BRIN Indexes for Time-Series Data
    # BRIN is 10-100x smaller than B-tree for naturally time-ordered data
    # ========================================================================

    # Notifications - Naturally ordered by created_at (append-only)
    op.create_index(
        'ix_Notifications_created_brin',
        'Notifications',
        ['created_at'],
        postgresql_using='brin',
        postgresql_with={'pages_per_range': '32'}
    )

    # Comments - Time-ordered (newer comments appended)
    op.create_index(
        'ix_Comments_created_brin',
        'Comments',
        ['created_at'],
        postgresql_using='brin',
        postgresql_with={'pages_per_range': '32'}
    )

    # Attachments - Time-ordered uploads
    op.create_index(
        'ix_Attachments_created_brin',
        'Attachments',
        ['created_at'],
        postgresql_using='brin',
        postgresql_with={'pages_per_range': '32'}
    )

    # ========================================================================
    # PHASE 3: Partial Indexes for Filtered Queries
    # Only index rows matching condition - smaller and faster
    # ========================================================================

    # Unread notifications - Most queries filter is_read=false
    op.create_index(
        'ix_Notifications_unread',
        'Notifications',
        ['user_id', 'created_at'],
        postgresql_where=text('is_read = false')
    )

    # Active tasks - Tasks with a status (exclude NULL task_status_id)
    op.create_index(
        'ix_Tasks_active_by_project',
        'Tasks',
        ['project_id', 'task_rank'],
        postgresql_where=text('task_status_id IS NOT NULL')
    )

    # Pending invitations - Only index unresponded invitations
    op.create_index(
        'ix_Invitations_pending',
        'Invitations',
        ['invitee_id', 'created_at'],
        postgresql_where=text("status = 'pending'")
    )

    # Incomplete checklist items - For progress tracking
    op.create_index(
        'ix_ChecklistItems_incomplete',
        'ChecklistItems',
        ['checklist_id', 'rank'],
        postgresql_where=text('is_done = false')
    )

    # Non-deleted comments - Most queries exclude deleted
    op.create_index(
        'ix_Comments_active',
        'Comments',
        ['task_id', 'created_at'],
        postgresql_where=text('is_deleted = false')
    )

    # ========================================================================
    # PHASE 4: Covering Indexes (INCLUDE clause)
    # Include extra columns to avoid table lookups entirely
    # ========================================================================

    # Task list query optimization
    # SELECT id, title, task_rank, assignee_id FROM Tasks WHERE project_id = ? AND status = ?
    op.create_index(
        'ix_Tasks_project_status_covering',
        'Tasks',
        ['project_id', 'status'],
        postgresql_include=['title', 'task_rank', 'assignee_id', 'priority', 'task_key']
    )

    # Notification list query optimization
    # SELECT id, title, type, created_at FROM Notifications WHERE user_id = ? AND is_read = false
    op.create_index(
        'ix_Notifications_user_unread_covering',
        'Notifications',
        ['user_id'],
        postgresql_include=['title', 'type', 'created_at', 'is_read'],
        postgresql_where=text('is_read = false')
    )


def downgrade() -> None:
    """Remove PostgreSQL optimization indexes."""
    # Phase 4: Covering indexes
    op.drop_index('ix_Notifications_user_unread_covering', table_name='Notifications')
    op.drop_index('ix_Tasks_project_status_covering', table_name='Tasks')

    # Phase 3: Partial indexes
    op.drop_index('ix_Comments_active', table_name='Comments')
    op.drop_index('ix_ChecklistItems_incomplete', table_name='ChecklistItems')
    op.drop_index('ix_Invitations_pending', table_name='Invitations')
    op.drop_index('ix_Tasks_active_by_project', table_name='Tasks')
    op.drop_index('ix_Notifications_unread', table_name='Notifications')

    # Phase 2: BRIN indexes
    op.drop_index('ix_Attachments_created_brin', table_name='Attachments')
    op.drop_index('ix_Comments_created_brin', table_name='Comments')
    op.drop_index('ix_Notifications_created_brin', table_name='Notifications')

    # Phase 1: Composite indexes
    op.drop_index('ix_ProjectMembers_user_project', table_name='ProjectMembers')
    op.drop_index('ix_ApplicationMembers_user_app', table_name='ApplicationMembers')
    op.drop_index('ix_ApplicationMembers_app_role', table_name='ApplicationMembers')
    op.drop_index('ix_ChecklistItems_checklist_rank', table_name='ChecklistItems')
    op.drop_index('ix_Checklists_task_rank', table_name='Checklists')
    op.drop_index('ix_Notifications_user_read_created', table_name='Notifications')
    op.drop_index('ix_Comments_task_created', table_name='Comments')
    op.drop_index('ix_Tasks_project_status_id', table_name='Tasks')
    op.drop_index('ix_Tasks_assignee_status', table_name='Tasks')
    op.drop_index('ix_Tasks_project_rank', table_name='Tasks')
    op.drop_index('ix_Tasks_project_status', table_name='Tasks')

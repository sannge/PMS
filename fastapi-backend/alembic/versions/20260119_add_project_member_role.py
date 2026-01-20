"""add_project_member_role

Revision ID: d9f1e2a3b4c5
Revises: 20260119_add_comments_and_checklists
Create Date: 2026-01-19 14:00:00.000000

This migration adds role and updated_at columns to ProjectMembers table:
1. Adds role column (VARCHAR 20, NOT NULL, DEFAULT 'member')
2. Adds updated_at column (DATETIME, DEFAULT GETDATE())
3. Creates composite index on (project_id, role) for admin lookups
4. Updates existing project creators to role='admin'

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = 'd9f1e2a3b4c5'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # ==========================================================================
    # 1. Add role column with default 'member'
    # ==========================================================================
    op.add_column(
        'ProjectMembers',
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member')
    )

    # ==========================================================================
    # 2. Add updated_at column
    # ==========================================================================
    op.add_column(
        'ProjectMembers',
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('GETDATE()'))
    )

    # ==========================================================================
    # 3. Create composite index on (project_id, role) for fast admin lookups
    # ==========================================================================
    op.create_index(
        'ix_ProjectMembers_project_role',
        'ProjectMembers',
        ['project_id', 'role'],
        unique=False
    )

    # ==========================================================================
    # 4. Update existing project creators to role='admin'
    # This finds all ProjectMember records where the user_id matches
    # the created_by (creator) of the project and sets their role to admin
    # ==========================================================================
    op.execute("""
        UPDATE pm
        SET pm.role = 'admin'
        FROM ProjectMembers pm
        INNER JOIN Projects p ON pm.project_id = p.id
        WHERE pm.user_id = p.created_by
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    # ==========================================================================
    # 1. Drop composite index
    # ==========================================================================
    op.drop_index('ix_ProjectMembers_project_role', table_name='ProjectMembers')

    # ==========================================================================
    # 2. Drop updated_at column
    # ==========================================================================
    op.drop_column('ProjectMembers', 'updated_at')

    # ==========================================================================
    # 3. Drop role column
    # ==========================================================================
    op.drop_column('ProjectMembers', 'role')

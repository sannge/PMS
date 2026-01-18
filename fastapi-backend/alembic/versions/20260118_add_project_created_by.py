"""Add created_by column to Projects table.

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-18 16:00:00.000000

This migration adds a created_by column to track who created each project.
This is needed for the permission system where editors can only delete
projects they created.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add created_by column to Projects table."""
    # Add created_by column (nullable since existing projects won't have a creator)
    op.add_column(
        'Projects',
        sa.Column(
            'created_by',
            mssql.UNIQUEIDENTIFIER(),
            nullable=True,
        )
    )

    # Create foreign key constraint
    op.create_foreign_key(
        'fk_projects_created_by_users',
        'Projects',
        'Users',
        ['created_by'],
        ['id'],
        ondelete='SET NULL'
    )

    # Create index for the new column
    op.create_index(
        'ix_Projects_created_by',
        'Projects',
        ['created_by'],
        unique=False
    )


def downgrade() -> None:
    """Remove created_by column from Projects table."""
    op.drop_index('ix_Projects_created_by', table_name='Projects')
    op.drop_constraint('fk_projects_created_by_users', 'Projects', type_='foreignkey')
    op.drop_column('Projects', 'created_by')

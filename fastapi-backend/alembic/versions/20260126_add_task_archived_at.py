"""Add archived_at column to Tasks table

Revision ID: a1b2c3d4e5f6
Revises: 9g4b3c2d5e6f
Create Date: 2026-01-26 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9g4b3c2d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add archived_at column to track when tasks are archived."""
    op.add_column(
        'Tasks',
        sa.Column('archived_at', sa.DateTime(), nullable=True)
    )
    op.create_index(
        'ix_Tasks_archived_at',
        'Tasks',
        ['archived_at']
    )


def downgrade() -> None:
    """Remove archived_at column."""
    op.drop_index('ix_Tasks_archived_at', table_name='Tasks')
    op.drop_column('Tasks', 'archived_at')

"""Add archived_at column to Projects table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add archived_at column to track when projects are archived."""
    op.add_column(
        'Projects',
        sa.Column('archived_at', sa.DateTime(), nullable=True)
    )
    op.create_index(
        'ix_Projects_archived_at',
        'Projects',
        ['archived_at']
    )


def downgrade() -> None:
    """Remove archived_at column."""
    op.drop_index('ix_Projects_archived_at', table_name='Projects')
    op.drop_column('Projects', 'archived_at')

"""Drop priority column from Projects table

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-01-28 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop priority column and its index from Projects table."""
    op.drop_index('ix_Projects_priority', table_name='Projects')
    op.drop_column('Projects', 'priority')


def downgrade() -> None:
    """Re-add priority column with default value."""
    op.add_column(
        'Projects',
        sa.Column('priority', sa.String(50), nullable=False, server_default='medium')
    )
    op.create_index('ix_Projects_priority', 'Projects', ['priority'])

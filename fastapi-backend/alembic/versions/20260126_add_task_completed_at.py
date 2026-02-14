"""Add completed_at column to Tasks table

Revision ID: 9g4b3c2d5e6f
Revises: 8f3a2b1c4d5e
Create Date: 2026-01-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9g4b3c2d5e6f'
down_revision: Union[str, None] = 'f8a9c3d5e712'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add completed_at column to track when tasks are completed."""
    op.add_column(
        'Tasks',
        sa.Column('completed_at', sa.DateTime(), nullable=True)
    )

    # Set completed_at for existing done tasks to their updated_at timestamp
    op.execute("""
        UPDATE "Tasks"
        SET completed_at = updated_at
        WHERE status = 'done'
    """)


def downgrade() -> None:
    """Remove completed_at column."""
    op.drop_column('Tasks', 'completed_at')

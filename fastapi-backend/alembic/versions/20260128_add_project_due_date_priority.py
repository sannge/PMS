"""Add due_date and priority columns to Projects table

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-28 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add due_date and priority columns with backfill for existing projects."""
    # Step 1: Add due_date as nullable first (for backfill)
    op.add_column(
        'Projects',
        sa.Column('due_date', sa.Date(), nullable=True)
    )

    # Step 2: Add priority as NOT NULL with default
    op.add_column(
        'Projects',
        sa.Column('priority', sa.String(50), nullable=False, server_default='medium')
    )

    # Step 3: Backfill due_date for existing projects (created_at + 30 days)
    op.execute("""
        UPDATE "Projects"
        SET due_date = (created_at::date + interval '30 days')::date
        WHERE due_date IS NULL
    """)

    # Step 4: Alter due_date to NOT NULL after backfill
    op.alter_column(
        'Projects',
        'due_date',
        nullable=False,
    )

    # Step 5: Create indexes for sorting and filtering
    op.create_index('ix_Projects_due_date', 'Projects', ['due_date'])
    op.create_index('ix_Projects_priority', 'Projects', ['priority'])


def downgrade() -> None:
    """Remove due_date and priority columns."""
    op.drop_index('ix_Projects_priority', table_name='Projects')
    op.drop_index('ix_Projects_due_date', table_name='Projects')
    op.drop_column('Projects', 'priority')
    op.drop_column('Projects', 'due_date')

"""Add next_task_number to Projects for atomic task key generation

Revision ID: 8f3a2b1c4d5e
Revises: 26b648a3dc17
Create Date: 2026-01-26 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3a2b1c4d5e'
down_revision: Union[str, None] = '26b648a3dc17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add next_task_number column and initialize from existing task counts."""
    # Add the column with a default of 1
    op.add_column(
        'Projects',
        sa.Column('next_task_number', sa.Integer(), nullable=False, server_default='1')
    )

    # Initialize next_task_number based on existing task counts
    # This ensures existing projects get the correct next number
    op.execute("""
        UPDATE "Projects" p
        SET next_task_number = COALESCE(
            (SELECT COUNT(*) + 1 FROM "Tasks" t WHERE t.project_id = p.id),
            1
        )
    """)

    # Remove the server default after initialization
    op.alter_column('Projects', 'next_task_number', server_default=None)


def downgrade() -> None:
    """Remove next_task_number column."""
    op.drop_column('Projects', 'next_task_number')

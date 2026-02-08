"""drop legacy status column from Tasks

Revision ID: a9b8c7d6e5f4
Revises: f1a2b3c4d5e6
Create Date: 2026-02-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the legacy status column and its index from the Tasks table."""
    # Drop the index on the status column
    op.drop_index("ix_Tasks_status", table_name="Tasks")

    # Drop the legacy status column
    op.drop_column("Tasks", "status")


def downgrade() -> None:
    """Re-add the legacy status column (populated as 'todo' default)."""
    op.add_column(
        "Tasks",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="todo",
        ),
    )
    op.create_index("ix_Tasks_status", "Tasks", ["status"])

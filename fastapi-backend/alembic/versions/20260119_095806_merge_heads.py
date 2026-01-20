"""merge_heads

Revision ID: e49b5e6849c1
Revises: b2c3d4e5f6g7, c7d8e9f0a1b2
Create Date: 2026-01-19 09:58:06.450815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e49b5e6849c1'
down_revision: Union[str, None] = ('b2c3d4e5f6g7', 'c7d8e9f0a1b2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass

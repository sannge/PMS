"""merge_multiple_heads

Revision ID: 915638a6468d
Revises: e49b5e6849c1, d9f1e2a3b4c5
Create Date: 2026-01-19 21:16:23.728961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '915638a6468d'
down_revision: Union[str, None] = ('e49b5e6849c1', 'd9f1e2a3b4c5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass

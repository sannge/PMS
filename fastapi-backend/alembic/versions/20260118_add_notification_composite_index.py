"""Add composite index for notification queries

Revision ID: 8f3a2b1c4d5e
Revises: aa2fc27435bc
Create Date: 2026-01-18 10:00:00.000000

This migration adds a composite index on the Notifications table
to optimize the common query pattern: fetching unread notifications
for a user, ordered by creation date.

Query pattern optimized:
    SELECT * FROM Notifications
    WHERE user_id = ? AND is_read = ?
    ORDER BY created_at DESC
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8f3a2b1c4d5e'
down_revision: Union[str, None] = 'b8c9d2e3f4a5'  # After invitation tables migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite index for optimal notification queries."""
    # Create composite index for the common query pattern:
    # WHERE user_id = X AND is_read = Y ORDER BY created_at DESC
    op.create_index(
        'ix_notifications_user_read_created',
        'Notifications',
        ['user_id', 'is_read', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    """Remove the composite index."""
    op.drop_index('ix_notifications_user_read_created', table_name='Notifications')

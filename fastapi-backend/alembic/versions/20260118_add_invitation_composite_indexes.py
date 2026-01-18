"""Add composite indexes for invitation queries

Revision ID: 9a4b3c2d1e0f
Revises: 8f3a2b1c4d5e
Create Date: 2026-01-18 12:00:00.000000

This migration adds composite indexes on the Invitations table
to optimize common query patterns.

Query patterns optimized:
    1. Listing pending invitations by invitee (most common):
       WHERE invitee_id = ? AND status = ? ORDER BY created_at DESC

    2. Listing sent invitations by inviter:
       WHERE inviter_id = ? AND status = ? ORDER BY created_at DESC

    3. Duplicate invitation check on create:
       WHERE application_id = ? AND invitee_id = ? AND status = ?
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9a4b3c2d1e0f'
down_revision: Union[str, None] = '8f3a2b1c4d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite indexes for optimal invitation queries."""
    # Index for listing pending invitations by invitee (most common query)
    op.create_index(
        'ix_invitations_invitee_status_created',
        'Invitations',
        ['invitee_id', 'status', 'created_at'],
        unique=False,
    )

    # Index for listing sent invitations by inviter
    op.create_index(
        'ix_invitations_inviter_status_created',
        'Invitations',
        ['inviter_id', 'status', 'created_at'],
        unique=False,
    )

    # Index for duplicate invitation check on create
    op.create_index(
        'ix_invitations_app_invitee_status',
        'Invitations',
        ['application_id', 'invitee_id', 'status'],
        unique=False,
    )


def downgrade() -> None:
    """Remove the composite indexes."""
    op.drop_index('ix_invitations_app_invitee_status', table_name='Invitations')
    op.drop_index('ix_invitations_inviter_status_created', table_name='Invitations')
    op.drop_index('ix_invitations_invitee_status_created', table_name='Invitations')

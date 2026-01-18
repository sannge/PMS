"""Remove overly restrictive unique constraint on invitations

Revision ID: a1b2c3d4e5f6
Revises: 9a4b3c2d1e0f
Create Date: 2026-01-18 14:00:00.000000

The unique constraint on (application_id, invitee_id) prevents re-inviting
a user after they reject or cancel an invitation. The application code
already checks for pending invitations, so this constraint is not needed.

This migration removes the constraint to allow:
- Re-inviting a user after they rejected a previous invitation
- Re-inviting a user after the inviter cancelled a previous invitation
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9a4b3c2d1e0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the unique constraint on (application_id, invitee_id)."""
    op.drop_constraint('uq_invitations_app_invitee', 'Invitations', type_='unique')


def downgrade() -> None:
    """Re-add the unique constraint."""
    op.create_unique_constraint(
        'uq_invitations_app_invitee',
        'Invitations',
        ['application_id', 'invitee_id']
    )

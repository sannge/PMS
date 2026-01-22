"""add_comment_id_to_attachments

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-01-21 10:00:00.000000

This migration adds comment_id column to the Attachments table to support
file attachments on comments.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, None] = '915638a6468d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add comment_id column to Attachments table
    op.add_column(
        'Attachments',
        sa.Column('comment_id', mssql.UNIQUEIDENTIFIER(), nullable=True)
    )

    # Create foreign key constraint
    op.create_foreign_key(
        'FK_Attachments_Comments',
        'Attachments',
        'Comments',
        ['comment_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Create index for faster lookups
    op.create_index(
        'IX_Attachments_comment_id',
        'Attachments',
        ['comment_id'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop index
    op.drop_index('IX_Attachments_comment_id', table_name='Attachments')

    # Drop foreign key constraint
    op.drop_constraint('FK_Attachments_Comments', 'Attachments', type_='foreignkey')

    # Drop column
    op.drop_column('Attachments', 'comment_id')

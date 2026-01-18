"""add_invitation_and_member_tables

Revision ID: b8c9d2e3f4a5
Revises: aa2fc27435bc
Create Date: 2026-01-17 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = 'b8c9d2e3f4a5'
down_revision: Union[str, None] = 'aa2fc27435bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Create Invitations table
    # Note: SQL Server doesn't allow multiple CASCADE paths to same table
    # So inviter_id and invitee_id use NO ACTION instead of CASCADE
    op.create_table('Invitations',
    sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('application_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('inviter_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('invitee_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('responded_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['application_id'], ['Applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['inviter_id'], ['Users.id'], ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['invitee_id'], ['Users.id'], ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id', 'invitee_id', name='uq_invitations_app_invitee')
    )
    op.create_index(op.f('ix_Invitations_application_id'), 'Invitations', ['application_id'], unique=False)
    op.create_index(op.f('ix_Invitations_inviter_id'), 'Invitations', ['inviter_id'], unique=False)
    op.create_index(op.f('ix_Invitations_invitee_id'), 'Invitations', ['invitee_id'], unique=False)
    op.create_index(op.f('ix_Invitations_role'), 'Invitations', ['role'], unique=False)
    op.create_index(op.f('ix_Invitations_status'), 'Invitations', ['status'], unique=False)
    op.create_index(op.f('ix_Invitations_created_at'), 'Invitations', ['created_at'], unique=False)

    # Create ApplicationMembers table
    # Note: SQL Server doesn't allow multiple CASCADE paths
    op.create_table('ApplicationMembers',
    sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('application_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('user_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('invitation_id', mssql.UNIQUEIDENTIFIER(), nullable=True),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('is_manager', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['Applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['invitation_id'], ['Invitations.id'], ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id', 'user_id', name='uq_application_members_app_user')
    )
    op.create_index(op.f('ix_ApplicationMembers_application_id'), 'ApplicationMembers', ['application_id'], unique=False)
    op.create_index(op.f('ix_ApplicationMembers_user_id'), 'ApplicationMembers', ['user_id'], unique=False)
    op.create_index(op.f('ix_ApplicationMembers_invitation_id'), 'ApplicationMembers', ['invitation_id'], unique=False)
    op.create_index(op.f('ix_ApplicationMembers_role'), 'ApplicationMembers', ['role'], unique=False)
    op.create_index(op.f('ix_ApplicationMembers_created_at'), 'ApplicationMembers', ['created_at'], unique=False)

    # Create ProjectAssignments table
    # Note: SQL Server doesn't allow multiple CASCADE paths to same table
    op.create_table('ProjectAssignments',
    sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('project_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('user_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('assigned_by', mssql.UNIQUEIDENTIFIER(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['Projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['assigned_by'], ['Users.id'], ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'user_id', name='uq_project_assignments_project_user')
    )
    op.create_index(op.f('ix_ProjectAssignments_project_id'), 'ProjectAssignments', ['project_id'], unique=False)
    op.create_index(op.f('ix_ProjectAssignments_user_id'), 'ProjectAssignments', ['user_id'], unique=False)
    op.create_index(op.f('ix_ProjectAssignments_assigned_by'), 'ProjectAssignments', ['assigned_by'], unique=False)
    op.create_index(op.f('ix_ProjectAssignments_created_at'), 'ProjectAssignments', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop ProjectAssignments table
    op.drop_index(op.f('ix_ProjectAssignments_created_at'), table_name='ProjectAssignments')
    op.drop_index(op.f('ix_ProjectAssignments_assigned_by'), table_name='ProjectAssignments')
    op.drop_index(op.f('ix_ProjectAssignments_user_id'), table_name='ProjectAssignments')
    op.drop_index(op.f('ix_ProjectAssignments_project_id'), table_name='ProjectAssignments')
    op.drop_table('ProjectAssignments')

    # Drop ApplicationMembers table
    op.drop_index(op.f('ix_ApplicationMembers_created_at'), table_name='ApplicationMembers')
    op.drop_index(op.f('ix_ApplicationMembers_role'), table_name='ApplicationMembers')
    op.drop_index(op.f('ix_ApplicationMembers_invitation_id'), table_name='ApplicationMembers')
    op.drop_index(op.f('ix_ApplicationMembers_user_id'), table_name='ApplicationMembers')
    op.drop_index(op.f('ix_ApplicationMembers_application_id'), table_name='ApplicationMembers')
    op.drop_table('ApplicationMembers')

    # Drop Invitations table
    op.drop_index(op.f('ix_Invitations_created_at'), table_name='Invitations')
    op.drop_index(op.f('ix_Invitations_status'), table_name='Invitations')
    op.drop_index(op.f('ix_Invitations_role'), table_name='Invitations')
    op.drop_index(op.f('ix_Invitations_invitee_id'), table_name='Invitations')
    op.drop_index(op.f('ix_Invitations_inviter_id'), table_name='Invitations')
    op.drop_index(op.f('ix_Invitations_application_id'), table_name='Invitations')
    op.drop_table('Invitations')

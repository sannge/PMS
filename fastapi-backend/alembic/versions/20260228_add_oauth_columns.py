"""Add OAuth columns to AiProviders table.

Extends AiProviders to support OAuth-based provider authentication in
addition to the existing API key flow. Adds auth_method discriminator
column, OAuth token storage columns, and a CHECK constraint limiting
auth_method to known values.

Revision ID: 20260228_oauth_columns
Revises: 20260228_ai_system_prompt
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260228_oauth_columns"
down_revision = "20260228_ai_system_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add OAuth columns, CHECK constraint, and index to AiProviders."""
    # auth_method discriminator: 'api_key' (default) or 'oauth'
    op.add_column(
        "AiProviders",
        sa.Column(
            "auth_method",
            sa.String(20),
            nullable=False,
            server_default="api_key",
        ),
    )

    # OAuth token storage columns
    op.add_column(
        "AiProviders",
        sa.Column("oauth_access_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "AiProviders",
        sa.Column("oauth_refresh_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "AiProviders",
        sa.Column(
            "oauth_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "AiProviders",
        sa.Column("oauth_scope", sa.String(500), nullable=True),
    )
    op.add_column(
        "AiProviders",
        sa.Column("oauth_provider_user_id", sa.String(255), nullable=True),
    )

    # CHECK constraint on auth_method
    op.create_check_constraint(
        "ck_ai_providers_auth_method",
        "AiProviders",
        "auth_method IN ('api_key', 'oauth')",
    )

    # Index on auth_method for filtering by auth type
    op.create_index(
        op.f("ix_AiProviders_auth_method"),
        "AiProviders",
        ["auth_method"],
    )


def downgrade() -> None:
    """Remove OAuth columns, index, and constraint from AiProviders."""
    op.drop_index(op.f("ix_AiProviders_auth_method"), table_name="AiProviders")
    op.drop_constraint("ck_ai_providers_auth_method", "AiProviders", type_="check")
    op.drop_column("AiProviders", "oauth_provider_user_id")
    op.drop_column("AiProviders", "oauth_scope")
    op.drop_column("AiProviders", "oauth_token_expires_at")
    op.drop_column("AiProviders", "oauth_refresh_token")
    op.drop_column("AiProviders", "oauth_access_token")
    op.drop_column("AiProviders", "auth_method")

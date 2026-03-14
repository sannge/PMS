"""Add session_token to auth_method check constraint.

Extends the auth_method CHECK constraint on AiProviders to allow
'session_token' alongside 'api_key' and 'oauth'. This supports
subscription-based authentication where users paste a session token
obtained from their CLI (e.g. claude setup-token).

Revision ID: 20260309_session_token
Revises: 20260307_add_agent_config
Create Date: 2026-03-09
"""

from alembic import op


# revision identifiers
revision = "20260309_session_token"
down_revision = "20260307_add_agent_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace auth_method CHECK to include 'session_token'."""
    op.drop_constraint("ck_ai_providers_auth_method", "AiProviders", type_="check")
    op.create_check_constraint(
        "ck_ai_providers_auth_method",
        "AiProviders",
        "auth_method IN ('api_key', 'oauth', 'session_token')",
    )


def downgrade() -> None:
    """Revert auth_method CHECK to original values.

    WARNING: This downgrade will fail if any rows with
    auth_method='session_token' still exist in the AiProviders table.
    Delete or migrate those rows before running this downgrade.
    """
    op.drop_constraint("ck_ai_providers_auth_method", "AiProviders", type_="check")
    op.create_check_constraint(
        "ck_ai_providers_auth_method",
        "AiProviders",
        "auth_method IN ('api_key', 'oauth')",
    )

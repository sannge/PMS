"""Add provider_type column to AiModels table.

Adds provider_type directly to AiModels so the frontend can filter model
dropdowns by provider without needing to join through the AiProviders table.
Uses a CHECK constraint to restrict values to 'openai', 'anthropic', 'ollama'.

Revision ID: 20260227_model_provider_type
Revises: 20260227_is_developer
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260227_model_provider_type"
down_revision = "20260227_is_developer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add provider_type column with a temporary default for existing rows
    op.add_column(
        "AiModels",
        sa.Column(
            "provider_type",
            sa.String(50),
            nullable=True,
        ),
    )

    # Backfill existing rows from the parent AiProviders table
    op.execute(
        """
        UPDATE "AiModels" m
        SET provider_type = p.provider_type
        FROM "AiProviders" p
        WHERE m.provider_id = p.id
        """
    )

    # Default any remaining NULLs (orphans) to 'openai'
    op.execute(
        """
        UPDATE "AiModels"
        SET provider_type = 'openai'
        WHERE provider_type IS NULL
        """
    )

    # Make column NOT NULL
    op.alter_column(
        "AiModels",
        "provider_type",
        nullable=False,
    )

    # Add CHECK constraint
    op.create_check_constraint(
        "ck_ai_models_provider_type",
        "AiModels",
        "provider_type IN ('openai', 'anthropic', 'ollama')",
    )

    # Add index for filtering
    op.create_index(
        "ix_AiModels_provider_type",
        "AiModels",
        ["provider_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_AiModels_provider_type", table_name="AiModels")
    op.drop_constraint("ck_ai_models_provider_type", "AiModels", type_="check")
    op.drop_column("AiModels", "provider_type")

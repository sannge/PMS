"""Add AiProviders and AiModels tables for AI configuration.

Creates the foundational AI configuration tables:
- AiProviders: stores provider connections (OpenAI, Anthropic, Ollama)
  with encrypted API keys and global/user scoping
- AiModels: stores available models per provider with capability tags

Includes partial unique indexes for PostgreSQL NULL-aware uniqueness
on provider_type scoping.

Revision ID: 20260224_ai_config
Revises: a1b2c3d4e5f6
Create Date: 2026-02-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260224_ai_config"
down_revision: Union[str, None] = "20260224_timestamptz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create AiProviders and AiModels tables."""
    # ========================================================================
    # 1. Create AiProviders table
    # ========================================================================
    op.create_table(
        "AiProviders",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="global"),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "provider_type IN ('openai', 'anthropic', 'ollama')",
            name="ck_ai_providers_provider_type",
        ),
        sa.CheckConstraint(
            "scope IN ('global', 'user')",
            name="ck_ai_providers_scope",
        ),
    )
    op.create_index(op.f("ix_AiProviders_provider_type"), "AiProviders", ["provider_type"])
    op.create_index(op.f("ix_AiProviders_user_id"), "AiProviders", ["user_id"])
    op.create_index(op.f("ix_AiProviders_is_enabled"), "AiProviders", ["is_enabled"])

    # Partial unique index for global providers (user_id IS NULL):
    # Only one provider per type at global scope
    op.execute(
        "CREATE UNIQUE INDEX uq_ai_providers_global_type ON \"AiProviders\" (provider_type) WHERE scope = 'global'"
    )

    # Partial unique index for user-scoped providers:
    # Only one provider per type per user
    op.execute(
        "CREATE UNIQUE INDEX uq_ai_providers_user_type ON \"AiProviders\" (provider_type, user_id) WHERE scope = 'user'"
    )

    # ========================================================================
    # 2. Create AiModels table
    # ========================================================================
    op.create_table(
        "AiModels",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("capability", sa.String(length=50), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["provider_id"], ["AiProviders.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "capability IN ('chat', 'embedding', 'vision')",
            name="ck_ai_models_capability",
        ),
        sa.UniqueConstraint("provider_id", "model_id", "capability", name="uq_ai_models_provider_model_capability"),
    )
    op.create_index(op.f("ix_AiModels_provider_id"), "AiModels", ["provider_id"])
    op.create_index(op.f("ix_AiModels_model_id"), "AiModels", ["model_id"])
    op.create_index(op.f("ix_AiModels_capability"), "AiModels", ["capability"])
    op.create_index(op.f("ix_AiModels_is_default"), "AiModels", ["is_default"])
    op.create_index(op.f("ix_AiModels_is_enabled"), "AiModels", ["is_enabled"])


def downgrade() -> None:
    """Drop AiModels then AiProviders (FK dependency order)."""
    # ========================================================================
    # 1. Drop AiModels
    # ========================================================================
    op.drop_index(op.f("ix_AiModels_is_enabled"), table_name="AiModels")
    op.drop_index(op.f("ix_AiModels_is_default"), table_name="AiModels")
    op.drop_index(op.f("ix_AiModels_capability"), table_name="AiModels")
    op.drop_index(op.f("ix_AiModels_model_id"), table_name="AiModels")
    op.drop_index(op.f("ix_AiModels_provider_id"), table_name="AiModels")
    op.drop_table("AiModels")

    # ========================================================================
    # 2. Drop AiProviders
    # ========================================================================
    op.execute("DROP INDEX IF EXISTS uq_ai_providers_user_type")
    op.execute("DROP INDEX IF EXISTS uq_ai_providers_global_type")
    op.drop_index(op.f("ix_AiProviders_is_enabled"), table_name="AiProviders")
    op.drop_index(op.f("ix_AiProviders_user_id"), table_name="AiProviders")
    op.drop_index(op.f("ix_AiProviders_provider_type"), table_name="AiProviders")
    op.drop_table("AiProviders")

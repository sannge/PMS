"""Add ai_system_prompts table for global AI system prompt configuration.

Creates a single-row table that stores the system prompt used by the AI
agent across all conversations. Designed for admin override of default
agent behavior.

Revision ID: 20260228_ai_system_prompt
Revises: 20260228_perf_indexes
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260228_ai_system_prompt"
down_revision = "20260228_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ai_system_prompts table."""
    op.create_table(
        'ai_system_prompts',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Drop ai_system_prompts table."""
    op.drop_table('ai_system_prompts')

"""Fix agent config seed drift: clarify rounds min_value and synthesize rounds row.

Updates agent.max_clarify_rounds min_value from '1' to '0' so clarification
can be disabled, and inserts the missing agent.max_synthesize_rounds row.

Revision ID: 20260310_fix_seed_drift
Revises: 20260310_pipeline_config
Create Date: 2026-03-10
"""
from alembic import op

revision = "20260310_fix_seed_drift"
down_revision = "20260310_pipeline_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix min_value for max_clarify_rounds to allow 0 (disabled)
    op.execute("""
        UPDATE "AgentConfigurations"
        SET min_value = '0'
        WHERE key = 'agent.max_clarify_rounds'
    """)

    # Add missing max_synthesize_rounds row
    op.execute("""
        INSERT INTO "AgentConfigurations"
            (key, value, value_type, category, description, min_value, max_value)
        VALUES
            ('agent.max_synthesize_rounds', '2', 'int', 'agent',
             'Maximum re-routing through synthesize node before forcing respond (0 = disabled, synthesis still runs once)',
             '0', '10')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE "AgentConfigurations"
        SET min_value = '1'
        WHERE key = 'agent.max_clarify_rounds'
    """)

    op.execute("""
        DELETE FROM "AgentConfigurations"
        WHERE key = 'agent.max_synthesize_rounds'
    """)

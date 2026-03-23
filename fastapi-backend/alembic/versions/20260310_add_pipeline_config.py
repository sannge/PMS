"""Add cognitive pipeline configuration seeds.

Seeds AgentConfigurations with entries for the 7-node cognitive
pipeline: explore iteration limits, confidence thresholds for
fast-path and clarification routing, and LLM parameters for
classification and synthesis nodes.

Revision ID: 20260310_pipeline_config
Revises: 20260309_session_token
Create Date: 2026-03-10
"""

from alembic import op

revision = "20260310_pipeline_config"
down_revision = "20260309_session_token"
branch_labels = None
depends_on = None

# Keys inserted by this migration (used by both upgrade and downgrade).
_KEYS = [
    "agent.max_explore_iterations",
    "agent.max_explore_llm_calls",
    "agent.confidence_fast_path",
    "agent.confidence_clarify",
    "agent.classification_temperature",
    "agent.classification_max_tokens",
    "agent.synthesis_max_tokens",
    "agent.classification_recent_messages",
]


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO "AgentConfigurations"
            (key, value, value_type, category, description, min_value, max_value)
        VALUES
            ('agent.max_explore_iterations', '10', 'int', 'agent',
             'Max ReAct iterations within explore phase', '1', '50'),
            ('agent.max_explore_llm_calls', '15', 'int', 'agent',
             'Max LLM calls within explore phase', '1', '50'),
            ('agent.confidence_fast_path', '0.7', 'float', 'agent',
             'Min confidence for fast-path (greeting/follow_up)', '0.0', '1.0'),
            ('agent.confidence_clarify', '0.5', 'float', 'agent',
             'Below this confidence, trigger clarification', '0.0', '1.0'),
            ('agent.classification_temperature', '0.1', 'float', 'agent',
             'Temperature for understand node classification LLM call', '0.0', '2.0'),
            ('agent.classification_max_tokens', '512', 'int', 'agent',
             'Max tokens for classification response', '64', '4096'),
            ('agent.synthesis_max_tokens', '2048', 'int', 'agent',
             'Max tokens for synthesis response', '256', '16000'),
            ('agent.classification_recent_messages', '6', 'int', 'agent',
             'Number of recent messages to use for classification', '2', '20')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    # Build a comma-separated list of quoted keys for the IN clause.
    keys_csv = ", ".join(f"'{k}'" for k in _KEYS)
    op.execute(f'DELETE FROM "AgentConfigurations" WHERE key IN ({keys_csv})')

"""Seed AiProviders and AiModels with all 32 known models.

Creates three global providers (OpenAI, Anthropic, Ollama) without API keys
and inserts all known models categorized by capability (chat, embedding, vision).
Frontend dropdowns read from these rows, filtered by provider_type + capability.

Revision ID: 20260227_seed_models
Revises: 20260227_model_provider_type
Create Date: 2026-02-27
"""

from alembic import op

# revision identifiers
revision = "20260227_seed_models"
down_revision = "20260227_model_provider_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =====================================================================
    # 1. Create three global providers (no API keys — configured by admin)
    # =====================================================================
    op.execute(
        """
        INSERT INTO "AiProviders" (id, name, display_name, provider_type, is_enabled, scope)
        VALUES
            ('a0000000-0000-0000-0000-000000000001'::uuid, 'openai', 'OpenAI', 'openai', true, 'global'),
            ('a0000000-0000-0000-0000-000000000002'::uuid, 'anthropic', 'Anthropic', 'anthropic', true, 'global'),
            ('a0000000-0000-0000-0000-000000000003'::uuid, 'ollama', 'Ollama', 'ollama', true, 'global')
        ON CONFLICT DO NOTHING
        """
    )

    # =====================================================================
    # 2. Insert all known models (32 total)
    # =====================================================================

    # -- OpenAI chat models (7) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5.2',      'GPT-5.2',       'chat', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5.1',      'GPT-5.1',       'chat', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5',        'GPT-5',         'chat', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5-mini',   'GPT-5 Mini',    'chat', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5-nano',   'GPT-5 Nano',    'chat', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-4.1',      'GPT-4.1',       'chat', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-4.1-mini', 'GPT-4.1 Mini',  'chat', 'openai', false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )

    # -- Anthropic chat models (5) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-opus-4-6',   'Claude Opus 4.6',   'chat', 'anthropic', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-sonnet-4-6', 'Claude Sonnet 4.6', 'chat', 'anthropic', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-opus-4-5',   'Claude Opus 4.5',   'chat', 'anthropic', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-sonnet-4-5', 'Claude Sonnet 4.5', 'chat', 'anthropic', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-haiku-4-5',  'Claude Haiku 4.5',  'chat', 'anthropic', false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )

    # -- Ollama chat models (4) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'llama3.1', 'Llama 3.1', 'chat', 'ollama', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'llama3.2', 'Llama 3.2', 'chat', 'ollama', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'mistral',  'Mistral',   'chat', 'ollama', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'qwen3',    'Qwen 3',    'chat', 'ollama', false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )

    # -- OpenAI embedding models (2) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, embedding_dimensions, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'text-embedding-3-small', 'Embedding 3 Small', 'embedding', 'openai', 1536, false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'text-embedding-3-large', 'Embedding 3 Large', 'embedding', 'openai', 3072, false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )

    # -- Ollama embedding models (4) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, embedding_dimensions, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'nomic-embed-text',       'Nomic Embed Text',  'embedding', 'ollama', 768,  false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'mxbai-embed-large',      'MxBai Embed Large', 'embedding', 'ollama', 1024, false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'all-minilm',             'All-MiniLM',        'embedding', 'ollama', 384,  false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'snowflake-arctic-embed', 'Snowflake Arctic',  'embedding', 'ollama', 1024, false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )

    # -- OpenAI vision models (4) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5.2', 'GPT-5.2 Vision', 'vision', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5.1', 'GPT-5.1 Vision', 'vision', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-5',   'GPT-5 Vision',   'vision', 'openai', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001'::uuid, 'gpt-4.1', 'GPT-4.1 Vision', 'vision', 'openai', false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )

    # -- Anthropic vision models (3) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-opus-4-6',   'Claude Opus 4.6 Vision',   'vision', 'anthropic', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-sonnet-4-6', 'Claude Sonnet 4.6 Vision', 'vision', 'anthropic', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000002'::uuid, 'claude-sonnet-4-5', 'Claude Sonnet 4.5 Vision', 'vision', 'anthropic', false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )

    # -- Ollama vision models (3) --
    op.execute(
        """
        INSERT INTO "AiModels" (id, provider_id, model_id, display_name, capability, provider_type, is_default, is_enabled)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'llava',        'LLaVA 1.6',      'vision', 'ollama', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'llava-llama3', 'LLaVA-Llama3',   'vision', 'ollama', false, true),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000003'::uuid, 'qwen2.5-vl',   'Qwen 2.5 VL',    'vision', 'ollama', false, true)
        ON CONFLICT ON CONSTRAINT uq_ai_models_provider_model_capability DO NOTHING
        """
    )


def downgrade() -> None:
    # Delete seeded models (by known provider IDs)
    op.execute(
        """
        DELETE FROM "AiModels"
        WHERE provider_id IN (
            'a0000000-0000-0000-0000-000000000001'::uuid,
            'a0000000-0000-0000-0000-000000000002'::uuid,
            'a0000000-0000-0000-0000-000000000003'::uuid
        )
        """
    )

    # Delete seeded providers
    op.execute(
        """
        DELETE FROM "AiProviders"
        WHERE id IN (
            'a0000000-0000-0000-0000-000000000001'::uuid,
            'a0000000-0000-0000-0000-000000000002'::uuid,
            'a0000000-0000-0000-0000-000000000003'::uuid
        )
        """
    )

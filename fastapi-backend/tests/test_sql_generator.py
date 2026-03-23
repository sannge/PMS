"""Unit tests for AI SQL generator (app.ai.sql_generator).

All LLM calls are mocked — no real provider API requests are made.
"""

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider_interface import LLMProviderError
from app.ai.provider_registry import ProviderRegistry
from app.ai.sql_generator import (
    MAX_RETRIES,
    GeneratedQuery,
    _build_system_prompt,
    _parse_llm_json,
    generate_query,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(
    sql: str = "SELECT count(*) AS task_count FROM v_tasks LIMIT 1",
    explanation: str = "Count all tasks.",
    tables_used: list[str] | None = None,
) -> str:
    """Build a JSON string mimicking LLM output."""
    return json.dumps(
        {
            "sql": sql,
            "explanation": explanation,
            "tables_used": tables_used or ["v_tasks"],
        }
    )


def _mock_provider_and_registry(
    response: str | list[str],
) -> tuple[AsyncMock, AsyncMock]:
    """Create mock provider + registry that returns the given response(s).

    If *response* is a list, successive calls to ``chat_completion``
    return the next item via ``side_effect``.
    """
    mock_provider = AsyncMock()
    if isinstance(response, list):
        mock_provider.chat_completion = AsyncMock(side_effect=response)
    else:
        mock_provider.chat_completion = AsyncMock(return_value=response)

    mock_registry = AsyncMock(spec=ProviderRegistry)
    mock_registry.get_chat_provider = AsyncMock(
        return_value=(mock_provider, "gpt-4o"),
    )
    return mock_provider, mock_registry


# ---------------------------------------------------------------------------
# _parse_llm_json
# ---------------------------------------------------------------------------


class TestParseLlmJson:
    def test_plain_json(self):
        raw = '{"sql": "SELECT 1", "explanation": "one", "tables_used": ["v_tasks"]}'
        result = _parse_llm_json(raw)
        assert result["sql"] == "SELECT 1"
        assert result["tables_used"] == ["v_tasks"]

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"sql": "SELECT 1", "explanation": "one", "tables_used": ["v_tasks"]}\n```'
        result = _parse_llm_json(raw)
        assert result["sql"] == "SELECT 1"

    def test_json_with_plain_fences(self):
        raw = '```\n{"sql": "SELECT 1", "explanation": "one", "tables_used": ["v_tasks"]}\n```'
        result = _parse_llm_json(raw)
        assert result["sql"] == "SELECT 1"

    def test_trailing_comma_in_object(self):
        raw = '{"sql": "SELECT 1", "explanation": "one", "tables_used": ["v_tasks"],}'
        result = _parse_llm_json(raw)
        assert result["sql"] == "SELECT 1"

    def test_trailing_comma_in_array(self):
        raw = '{"sql": "SELECT 1", "explanation": "one", "tables_used": ["v_tasks",]}'
        result = _parse_llm_json(raw)
        assert result["tables_used"] == ["v_tasks"]

    def test_extra_whitespace(self):
        raw = '  \n  {"sql": "SELECT 1", "explanation": "one", "tables_used": []}  \n  '
        result = _parse_llm_json(raw)
        assert result["sql"] == "SELECT 1"

    def test_json_embedded_in_text(self):
        raw = 'Here is the query:\n{"sql": "SELECT 1", "explanation": "one", "tables_used": []}\nDone.'
        result = _parse_llm_json(raw)
        assert result["sql"] == "SELECT 1"

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Failed to parse LLM JSON"):
            _parse_llm_json("this is not json at all")


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    @patch("app.ai.sql_generator.get_schema_prompt")
    def test_includes_schema_context(self, mock_get_schema):
        mock_get_schema.return_value = "## FAKE SCHEMA"
        prompt = _build_system_prompt()

        assert "## FAKE SCHEMA" in prompt
        mock_get_schema.assert_called_once()

    @patch("app.ai.sql_generator.get_schema_prompt")
    def test_includes_rules(self, mock_get_schema):
        mock_get_schema.return_value = ""
        prompt = _build_system_prompt()

        assert "SELECT" in prompt
        assert "LIMIT" in prompt
        assert "v_*" in prompt or "v_tasks" in prompt

    @patch("app.ai.sql_generator.get_schema_prompt")
    def test_includes_examples(self, mock_get_schema):
        mock_get_schema.return_value = ""
        prompt = _build_system_prompt()

        assert "How many tasks are there?" in prompt
        assert "Show all high priority tasks" in prompt


# ---------------------------------------------------------------------------
# generate_query — happy path
# ---------------------------------------------------------------------------


class TestGenerateQueryHappyPath:
    async def test_simple_question_generates_valid_sql(self):
        """Mock LLM returns valid JSON — should succeed on first attempt."""
        response = _make_llm_response()
        mock_provider, mock_registry = _mock_provider_and_registry(response)
        mock_db = AsyncMock(spec=AsyncSession)

        result = await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
        )

        assert isinstance(result, GeneratedQuery)
        assert "v_tasks" in result.sql.lower()
        assert result.explanation == "Count all tasks."
        assert "v_tasks" in result.tables_used
        assert result.generation_attempts == 1

        mock_registry.get_chat_provider.assert_awaited_once_with(mock_db)
        mock_provider.chat_completion.assert_awaited_once()

    async def test_question_with_application_filter(self):
        """Application ID context is appended to user message."""
        response = _make_llm_response(
            sql="SELECT count(*) AS task_count FROM v_tasks WHERE application_id = 'abc' LIMIT 1",
        )
        mock_provider, mock_registry = _mock_provider_and_registry(response)
        mock_db = AsyncMock(spec=AsyncSession)
        app_id = uuid4()

        await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
            application_id=app_id,
        )

        # Verify the user message sent to LLM includes application_id context
        call_kwargs = mock_provider.chat_completion.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][0]
        # Find the user message
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert str(app_id) in user_msg["content"]
        assert "application_id" in user_msg["content"]

    async def test_question_with_project_filter(self):
        """Project ID context is appended to user message."""
        response = _make_llm_response()
        mock_provider, mock_registry = _mock_provider_and_registry(response)
        mock_db = AsyncMock(spec=AsyncSession)
        proj_id = uuid4()

        await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
            project_id=proj_id,
        )

        call_kwargs = mock_provider.chat_completion.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][0]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert str(proj_id) in user_msg["content"]
        assert "project_id" in user_msg["content"]

    async def test_generation_attempts_and_duration_populated(self):
        """Result metadata fields are set."""
        response = _make_llm_response()
        _, mock_registry = _mock_provider_and_registry(response)
        mock_db = AsyncMock(spec=AsyncSession)

        result = await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
        )

        assert result.generation_attempts >= 1
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# generate_query — retry scenarios
# ---------------------------------------------------------------------------


class TestGenerateQueryRetries:
    async def test_retry_on_validation_failure(self):
        """First LLM response references a base table (fails validation),
        second response is valid — should succeed on attempt 2."""
        bad_response = _make_llm_response(
            sql="SELECT count(*) FROM tasks LIMIT 1",  # base table, not v_tasks
            tables_used=["tasks"],
        )
        good_response = _make_llm_response(
            sql="SELECT count(*) AS task_count FROM v_tasks LIMIT 1",
            tables_used=["v_tasks"],
        )
        mock_provider, mock_registry = _mock_provider_and_registry(
            [bad_response, good_response],
        )
        mock_db = AsyncMock(spec=AsyncSession)

        result = await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
        )

        assert result.generation_attempts == 2
        assert "v_tasks" in result.sql.lower()
        assert mock_provider.chat_completion.await_count == 2

    async def test_retry_on_empty_sql(self):
        """LLM returns empty SQL first, valid SQL second."""
        empty_response = _make_llm_response(sql="")
        good_response = _make_llm_response()
        _, mock_registry = _mock_provider_and_registry(
            [empty_response, good_response],
        )
        mock_db = AsyncMock(spec=AsyncSession)

        result = await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
        )

        assert result.generation_attempts == 2

    async def test_max_retries_exhausted_raises_value_error(self):
        """All attempts fail — raises ValueError after MAX_RETRIES + 1 attempts."""
        bad_response = _make_llm_response(
            sql="SELECT count(*) FROM tasks LIMIT 1",  # always fails validation
            tables_used=["tasks"],
        )
        # Need MAX_RETRIES + 1 responses (1 initial + MAX_RETRIES retries)
        responses = [bad_response] * (MAX_RETRIES + 1)
        mock_provider, mock_registry = _mock_provider_and_registry(responses)
        mock_db = AsyncMock(spec=AsyncSession)

        with pytest.raises(ValueError, match="SQL generation failed after"):
            await generate_query(
                question="How many tasks?",
                db=mock_db,
                provider_registry=mock_registry,
            )

        assert mock_provider.chat_completion.await_count == MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# generate_query — error handling
# ---------------------------------------------------------------------------


class TestGenerateQueryErrors:
    async def test_llm_provider_error_reraised(self):
        """LLMProviderError from provider is not retried — re-raised directly."""
        mock_provider = AsyncMock()
        mock_provider.chat_completion = AsyncMock(
            side_effect=LLMProviderError("API key invalid", provider="openai"),
        )
        mock_registry = AsyncMock(spec=ProviderRegistry)
        mock_registry.get_chat_provider = AsyncMock(
            return_value=(mock_provider, "gpt-4o"),
        )
        mock_db = AsyncMock(spec=AsyncSession)

        with pytest.raises(LLMProviderError, match="API key invalid"):
            await generate_query(
                question="How many tasks?",
                db=mock_db,
                provider_registry=mock_registry,
            )

        # Should NOT retry — only 1 call
        assert mock_provider.chat_completion.await_count == 1

    async def test_system_prompt_includes_schema(self):
        """Verify the system message sent to LLM contains schema info."""
        response = _make_llm_response()
        mock_provider, mock_registry = _mock_provider_and_registry(response)
        mock_db = AsyncMock(spec=AsyncSession)

        await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
        )

        call_kwargs = mock_provider.chat_completion.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][0]
        system_msg = [m for m in messages if m["role"] == "system"][0]
        assert "Database Schema" in system_msg["content"]
        assert "v_tasks" in system_msg["content"]

    async def test_llm_called_with_correct_params(self):
        """Provider chat_completion receives temperature=0.1 and max_tokens=1024."""
        response = _make_llm_response()
        mock_provider, mock_registry = _mock_provider_and_registry(response)
        mock_db = AsyncMock(spec=AsyncSession)

        await generate_query(
            question="How many tasks?",
            db=mock_db,
            provider_registry=mock_registry,
        )

        mock_provider.chat_completion.assert_awaited_once()
        call_kwargs = mock_provider.chat_completion.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.1 or call_kwargs[1].get("temperature") == 0.1
        assert call_kwargs.kwargs.get("max_tokens") == 1024 or call_kwargs[1].get("max_tokens") == 1024
        assert call_kwargs.kwargs.get("model") == "gpt-4o" or call_kwargs[1].get("model") == "gpt-4o"

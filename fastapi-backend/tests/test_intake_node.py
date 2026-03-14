"""Unit tests for the intake node (app.ai.agent.nodes.intake).

Tests cover:
- Counter initialization (all start at 0)
- DB system prompt load (happy path, DB exception fallback, empty prompt)
- chat_model_cache already populated -> skips DB call
- _get_langchain_chat_model raises -> propagates up
- bound_model_cache populated after model is cached
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.ai.agent.nodes.intake import intake_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    """Build a minimal AgentState dict with defaults."""
    state = {
        "messages": [],
        "user_id": str(uuid4()),
        "accessible_app_ids": [],
        "accessible_project_ids": [],
        "total_tool_calls": 0,
        "total_llm_calls": 0,
        "iteration_count": 0,
    }
    state.update(overrides)
    return state


class _FakeAsyncCM:
    """Fake async context manager wrapping a mock session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _make_mock_db(prompt_text=None, prompt_raises=False):
    """Build a mock async session factory that returns a fake system prompt.

    The factory is a regular callable (not coroutine) that returns an
    async context manager, matching ``async with factory() as db``.
    """
    mock_session = AsyncMock()
    mock_prompt_row = MagicMock()
    mock_prompt_row.prompt = prompt_text

    if prompt_raises:
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))
    else:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = (
            mock_prompt_row if prompt_text is not None else None
        )
        mock_session.execute = AsyncMock(return_value=mock_result)

    def factory():
        return _FakeAsyncCM(mock_session)

    return factory


# ---------------------------------------------------------------------------
# Tests: Counter initialisation
# ---------------------------------------------------------------------------

class TestCounterInit:

    async def test_counters_reset_to_zero_each_turn(self):
        """intake_node resets counters to 0 for each new user message turn."""
        chat_model_cache = [MagicMock()]  # already populated
        system_prompt_cache = ["test prompt"]
        bound_model_cache = [MagicMock()]

        # Simulate state from a previous turn with accumulated counters
        state = _make_state(total_tool_calls=50, total_llm_calls=25, iteration_count=20)
        result = await intake_node(
            state,
            tools=[],
            provider_registry=MagicMock(),
            db_session_factory=MagicMock(),
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        # Counters must reset to 0 — they are per-turn, not per-thread
        assert result["total_tool_calls"] == 0
        assert result["total_llm_calls"] == 0
        assert result["iteration_count"] == 0

    async def test_default_counters_are_zero(self):
        """When state has no counters, they default to 0."""
        chat_model_cache = [MagicMock()]
        system_prompt_cache = ["test"]
        bound_model_cache = [MagicMock()]

        state = {"messages": [], "user_id": str(uuid4())}
        result = await intake_node(
            state,
            tools=[],
            provider_registry=MagicMock(),
            db_session_factory=MagicMock(),
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        assert result["total_tool_calls"] == 0
        assert result["total_llm_calls"] == 0
        assert result["iteration_count"] == 0

    async def test_no_stale_pipeline_fields_in_result(self):
        """intake_node result should NOT contain pipeline fields it doesn't manage.

        Pipeline fields like classification, research, fast_path are set by
        the understand node, not intake. Intake only resets counters.
        """
        chat_model_cache = [MagicMock()]
        system_prompt_cache = ["test"]
        bound_model_cache = [MagicMock()]

        state = _make_state()
        result = await intake_node(
            state,
            tools=[],
            provider_registry=MagicMock(),
            db_session_factory=MagicMock(),
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        # Intake does NOT set pipeline fields -- those are set by understand node
        assert "classification" not in result
        # DA3-MED-001: Intake now resets research to {} to clear stale accumulator
        assert result["research"] == {}
        assert "fast_path" not in result
        assert "current_phase" not in result
        # B1/B3: Intake DOES reset loop guard counters
        assert result["clarify_count"] == 0
        assert result["synthesize_count"] == 0
        # Old fields that never existed
        assert "respond_recovery_count" not in result
        assert "clarify_questions" not in result
        assert "clarify_answers" not in result
        assert "clarify_options" not in result


# ---------------------------------------------------------------------------
# Tests: System prompt loading
# ---------------------------------------------------------------------------

class TestSystemPromptLoad:

    @patch("app.ai.config_service.get_agent_config")
    @patch("app.ai.agent.graph._get_langchain_chat_model")
    async def test_loads_custom_prompt_from_db(self, mock_get_model, mock_cfg):
        """When DB has a custom prompt, it's stored in system_prompt_cache."""
        # Isolate from config cache pollution by other tests
        mock_cfg_instance = MagicMock()
        mock_cfg_instance.get_str = MagicMock(side_effect=lambda k, d: d)
        mock_cfg.return_value = mock_cfg_instance

        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=MagicMock())
        mock_get_model.return_value = mock_model

        chat_model_cache: list = []
        system_prompt_cache: list = []
        bound_model_cache: list = []

        factory = _make_mock_db(prompt_text="Custom system prompt")

        await intake_node(
            _make_state(),
            tools=[MagicMock()],
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        # CRIT-1: custom prompt is appended after the base SYSTEM_PROMPT, never replaces it
        assert len(system_prompt_cache) == 1
        assert "Custom system prompt" in system_prompt_cache[0]
        assert system_prompt_cache[0].startswith("You are Blair")

    @patch("app.ai.config_service.get_agent_config")
    @patch("app.ai.agent.graph._get_langchain_chat_model")
    async def test_falls_back_to_default_when_no_db_prompt(self, mock_get_model, mock_cfg):
        """When DB returns None, fall back to base prompt (built from config)."""
        mock_cfg_instance = MagicMock()
        mock_cfg_instance.get_str = MagicMock(side_effect=lambda k, d: d)
        mock_cfg.return_value = mock_cfg_instance

        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=MagicMock())
        mock_get_model.return_value = mock_model

        chat_model_cache: list = []
        system_prompt_cache: list = []
        bound_model_cache: list = []

        factory = _make_mock_db(prompt_text=None)

        await intake_node(
            _make_state(),
            tools=[MagicMock()],
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        assert len(system_prompt_cache) == 1
        assert system_prompt_cache[0].startswith("You are Blair")

    @patch("app.ai.config_service.get_agent_config")
    @patch("app.ai.agent.graph._get_langchain_chat_model")
    async def test_falls_back_to_default_on_db_exception(self, mock_get_model, mock_cfg):
        """When DB query raises, fall back to base prompt (built from config)."""
        mock_cfg_instance = MagicMock()
        mock_cfg_instance.get_str = MagicMock(side_effect=lambda k, d: d)
        mock_cfg.return_value = mock_cfg_instance

        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=MagicMock())
        mock_get_model.return_value = mock_model

        chat_model_cache: list = []
        system_prompt_cache: list = []
        bound_model_cache: list = []

        factory = _make_mock_db(prompt_raises=True)

        await intake_node(
            _make_state(),
            tools=[MagicMock()],
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        assert len(system_prompt_cache) == 1
        assert system_prompt_cache[0].startswith("You are Blair")


# ---------------------------------------------------------------------------
# Tests: Model caching
# ---------------------------------------------------------------------------

class TestModelCaching:

    async def test_skips_db_when_cache_populated(self):
        """When chat_model_cache already has a model, skip DB call."""
        existing_model = MagicMock()
        chat_model_cache = [existing_model]
        system_prompt_cache = ["cached prompt"]
        bound_model_cache = [MagicMock()]

        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock()

        await intake_node(
            _make_state(),
            tools=[],
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        # The factory should NOT have been called (cache hit)
        factory.assert_not_called()
        assert chat_model_cache == [existing_model]

    @patch("app.ai.agent.graph._get_langchain_chat_model")
    async def test_populates_chat_model_cache(self, mock_get_model):
        """First call populates chat_model_cache."""
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=MagicMock())
        mock_get_model.return_value = mock_model

        chat_model_cache: list = []
        system_prompt_cache: list = []
        bound_model_cache: list = []

        factory = _make_mock_db(prompt_text=None)

        await intake_node(
            _make_state(),
            tools=[MagicMock()],
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        assert len(chat_model_cache) == 1
        assert chat_model_cache[0] is mock_model

    @patch("app.ai.agent.graph._get_langchain_chat_model")
    async def test_populates_bound_model_cache_with_tools(self, mock_get_model):
        """bound_model_cache is populated with model.bind_tools(tools)."""
        mock_bound = MagicMock()
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_bound)
        mock_get_model.return_value = mock_model

        tools = [MagicMock(), MagicMock()]
        chat_model_cache: list = []
        system_prompt_cache: list = []
        bound_model_cache: list = []

        factory = _make_mock_db(prompt_text=None)

        await intake_node(
            _make_state(),
            tools=tools,
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        mock_model.bind_tools.assert_called_once_with(tools)
        assert len(bound_model_cache) == 1
        assert bound_model_cache[0] is mock_bound

    @patch("app.ai.agent.graph._get_langchain_chat_model")
    async def test_empty_tools_skips_bind(self, mock_get_model):
        """When tools list is empty, bound_model_cache stays empty."""
        mock_model = MagicMock()
        mock_get_model.return_value = mock_model

        chat_model_cache: list = []
        system_prompt_cache: list = []
        bound_model_cache: list = []

        factory = _make_mock_db(prompt_text=None)

        await intake_node(
            _make_state(),
            tools=[],
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )

        mock_model.bind_tools.assert_not_called()
        assert len(bound_model_cache) == 0

    @patch("app.ai.agent.graph._get_langchain_chat_model")
    async def test_model_raises_leaves_caches_empty(self, mock_get_model):
        """If _get_langchain_chat_model raises, caches stay empty (graceful degradation)."""
        mock_get_model.side_effect = ValueError("No provider configured")

        chat_model_cache: list = []
        system_prompt_cache: list = []
        bound_model_cache: list = []

        factory = _make_mock_db(prompt_text=None)

        # intake_node catches the error and leaves caches empty;
        # downstream nodes detect empty caches and return error messages.
        result = await intake_node(
            _make_state(),
            tools=[MagicMock()],
            provider_registry=MagicMock(),
            db_session_factory=factory,
            chat_model_cache=chat_model_cache,
            system_prompt_cache=system_prompt_cache,
            bound_model_cache=bound_model_cache,
        )
        # Result still has counter fields
        assert result["total_tool_calls"] == 0
        assert result["total_llm_calls"] == 0
        assert result["iteration_count"] == 0
        assert len(chat_model_cache) == 0
        assert len(bound_model_cache) == 0

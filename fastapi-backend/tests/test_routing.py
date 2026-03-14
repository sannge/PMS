"""Unit tests for routing functions (app.ai.agent.routing).

Tests cover:
- route_after_understand: fast path, clarify, explore branches
- route_after_explore: tool_calls, synthesize, respond, safety limits
- route_after_respond: misclassification recovery, normal end
- route_after_synthesize: user correction, normal respond
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai.agent.constants import (
    get_max_clarify_rounds,
    get_max_iterations,
    get_max_llm_calls,
    get_max_synthesize_rounds,
    get_max_tool_calls,
)
from app.ai.agent.routing import (
    route_after_explore,
    route_after_respond,
    route_after_synthesize,
    route_after_understand,
)


# ---------------------------------------------------------------------------
# Tests: route_after_understand
# ---------------------------------------------------------------------------


class TestRouteAfterUnderstand:

    def test_greeting_high_confidence_fast_paths(self):
        state = {
            "messages": [],
            "classification": {"intent": "greeting", "confidence": 0.9},
        }
        assert route_after_understand(state) == "respond"

    def test_follow_up_high_confidence_fast_paths(self):
        state = {
            "messages": [],
            "classification": {"intent": "follow_up", "confidence": 0.8},
        }
        assert route_after_understand(state) == "respond"

    def test_greeting_low_confidence_explores(self):
        """Greeting with confidence between clarify and fast_path thresholds goes to explore."""
        state = {
            "messages": [],
            "classification": {"intent": "greeting", "confidence": 0.6},
        }
        assert route_after_understand(state) == "explore"

    def test_info_query_high_confidence_explores(self):
        """info_query never fast-paths, even with high confidence."""
        state = {
            "messages": [],
            "classification": {"intent": "info_query", "confidence": 0.95},
        }
        assert route_after_understand(state) == "explore"

    def test_needs_clarification_intent_routes_clarify(self):
        state = {
            "messages": [],
            "classification": {"intent": "needs_clarification", "confidence": 0.8},
        }
        assert route_after_understand(state) == "clarify"

    def test_low_confidence_routes_clarify(self):
        state = {
            "messages": [],
            "classification": {"intent": "info_query", "confidence": 0.3},
        }
        assert route_after_understand(state) == "clarify"

    def test_boundary_confidence_exact_fast_path(self):
        """Exactly at CONFIDENCE_FAST_PATH (0.7) with greeting fast-paths."""
        state = {
            "messages": [],
            "classification": {"intent": "greeting", "confidence": 0.7},
        }
        assert route_after_understand(state) == "respond"

    def test_boundary_confidence_just_below_fast_path(self):
        """Just below CONFIDENCE_FAST_PATH with greeting does NOT fast-path."""
        state = {
            "messages": [],
            "classification": {"intent": "greeting", "confidence": 0.69},
        }
        assert route_after_understand(state) == "explore"

    def test_boundary_confidence_exact_clarify(self):
        """Exactly at CONFIDENCE_CLARIFY (0.5) does NOT trigger clarify."""
        state = {
            "messages": [],
            "classification": {"intent": "info_query", "confidence": 0.5},
        }
        assert route_after_understand(state) == "explore"

    def test_boundary_confidence_just_below_clarify(self):
        """Just below CONFIDENCE_CLARIFY triggers clarify."""
        state = {
            "messages": [],
            "classification": {"intent": "info_query", "confidence": 0.49},
        }
        assert route_after_understand(state) == "clarify"

    def test_missing_classification_defaults_to_explore(self):
        """Missing classification defaults to confidence=0.7, intent=info_query."""
        state = {"messages": []}
        assert route_after_understand(state) == "explore"

    def test_action_request_explores(self):
        state = {
            "messages": [],
            "classification": {"intent": "action_request", "confidence": 0.8},
        }
        assert route_after_understand(state) == "explore"

    def test_multi_step_explores(self):
        state = {
            "messages": [],
            "classification": {"intent": "multi_step", "confidence": 0.75},
        }
        assert route_after_understand(state) == "explore"

    def test_clarify_limit_forces_explore(self):
        """B1: When clarify_count >= MAX_CLARIFY_ROUNDS, force explore."""
        state = {
            "messages": [],
            "classification": {"intent": "needs_clarification", "confidence": 0.3},
            "clarify_count": get_max_clarify_rounds(),
        }
        assert route_after_understand(state) == "explore"

    def test_clarify_count_under_limit_still_clarifies(self):
        """Clarify_count < MAX_CLARIFY_ROUNDS still routes to clarify."""
        state = {
            "messages": [],
            "classification": {"intent": "needs_clarification", "confidence": 0.3},
            "clarify_count": 1,
        }
        assert route_after_understand(state) == "clarify"


# ---------------------------------------------------------------------------
# Tests: route_after_explore
# ---------------------------------------------------------------------------


class TestRouteAfterExplore:

    def test_tool_calls_routes_to_explore_tools(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        state = {
            "messages": [ai_msg],
            "total_llm_calls": 1,
            "total_tool_calls": 0,
            "iteration_count": 1,
        }
        assert route_after_explore(state) == "explore_tools"

    def test_text_only_simple_routes_to_respond(self):
        state = {
            "messages": [AIMessage(content="Here are results.")],
            "classification": {"complexity": "simple"},
        }
        assert route_after_explore(state) == "respond"

    def test_text_only_complex_routes_to_synthesize(self):
        state = {
            "messages": [AIMessage(content="Data gathered.")],
            "classification": {"complexity": "complex"},
        }
        assert route_after_explore(state) == "synthesize"

    def test_text_only_multi_step_routes_to_synthesize(self):
        state = {
            "messages": [AIMessage(content="Data gathered.")],
            "classification": {"intent": "multi_step", "complexity": "moderate"},
        }
        assert route_after_explore(state) == "synthesize"

    def test_empty_messages_routes_to_respond(self):
        state = {"messages": []}
        assert route_after_explore(state) == "respond"

    def test_tool_calls_at_llm_limit_routes_to_respond(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}],
        )
        state = {
            "messages": [ai_msg],
            "total_llm_calls": get_max_llm_calls(),
            "total_tool_calls": 0,
            "iteration_count": 0,
        }
        assert route_after_explore(state) == "respond"

    def test_tool_calls_at_tool_limit_routes_to_respond(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}],
        )
        state = {
            "messages": [ai_msg],
            "total_llm_calls": 0,
            "total_tool_calls": get_max_tool_calls(),
            "iteration_count": 0,
        }
        assert route_after_explore(state) == "respond"

    def test_tool_calls_at_iteration_limit_routes_to_respond(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}],
        )
        state = {
            "messages": [ai_msg],
            "total_llm_calls": 0,
            "total_tool_calls": 0,
            "iteration_count": get_max_iterations(),
        }
        assert route_after_explore(state) == "respond"

    def test_tool_calls_under_all_limits(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}],
        )
        state = {
            "messages": [ai_msg],
            "total_llm_calls": get_max_llm_calls() - 1,
            "total_tool_calls": get_max_tool_calls() - 1,
            "iteration_count": get_max_iterations() - 1,
        }
        assert route_after_explore(state) == "explore_tools"

    def test_human_message_last_routes_to_respond(self):
        """If somehow a HumanMessage is last, route to respond (no tool_calls)."""
        state = {
            "messages": [HumanMessage(content="hello")],
            "classification": {"complexity": "simple"},
        }
        assert route_after_explore(state) == "respond"

    def test_missing_classification_defaults_simple(self):
        """Missing classification defaults complexity to simple -> respond."""
        state = {"messages": [AIMessage(content="done")]}
        assert route_after_explore(state) == "respond"


# ---------------------------------------------------------------------------
# Tests: route_after_respond
# ---------------------------------------------------------------------------


class TestRouteAfterRespond:

    def test_text_only_routes_to_end(self):
        state = {"messages": [AIMessage(content="Hello!")]}
        assert route_after_respond(state) == "end"

    def test_tool_calls_reroute_to_explore_tools(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {}, "id": "tc1"}],
        )
        state = {"messages": [ai_msg]}
        assert route_after_respond(state) == "explore_tools"

    def test_empty_messages_routes_to_end(self):
        state = {"messages": []}
        assert route_after_respond(state) == "end"

    def test_human_message_routes_to_end(self):
        state = {"messages": [HumanMessage(content="hi")]}
        assert route_after_respond(state) == "end"


# ---------------------------------------------------------------------------
# Tests: route_after_synthesize
# ---------------------------------------------------------------------------


class TestRouteAfterSynthesize:

    def test_ai_message_routes_to_respond(self):
        state = {"messages": [AIMessage(content="Synthesized results.")], "current_phase": "synthesize"}
        assert route_after_synthesize(state) == "respond"

    def test_human_message_routes_to_understand(self):
        """User correction after synthesis routes back to understand."""
        state = {
            "messages": [HumanMessage(content="No, I meant something else")],
            "current_phase": "synthesize",
        }
        assert route_after_synthesize(state) == "understand"

    def test_empty_messages_routes_to_respond(self):
        state = {"messages": []}
        assert route_after_synthesize(state) == "respond"

    def test_synthesize_count_limit_forces_respond(self):
        """B3: When synthesize_count >= MAX_SYNTHESIZE_ROUNDS, force respond."""
        state = {
            "messages": [HumanMessage(content="correction")],
            "current_phase": "synthesize",
            "synthesize_count": get_max_synthesize_rounds(),
        }
        assert route_after_synthesize(state) == "respond"

    def test_human_message_without_synthesize_phase_routes_respond(self):
        """S7: HumanMessage only re-routes when current_phase is 'synthesize'."""
        state = {
            "messages": [HumanMessage(content="No, I meant something else")],
            "current_phase": "explore",  # Not synthesize
        }
        assert route_after_synthesize(state) == "respond"


# ---------------------------------------------------------------------------
# Tests: safety getter hard floors (DA2-F4, DA2-F5)
# ---------------------------------------------------------------------------


class TestSafetyGetterHardFloors:
    """Safety limits have a hard floor of 1 (max(1,...)) to prevent
    complete disabling. Behavioral controls allow 0."""

    def test_get_max_tool_calls_floor_at_one(self):
        """get_max_tool_calls returns 1 when config is 0."""
        from unittest.mock import patch, MagicMock

        mock_cfg = MagicMock()
        mock_cfg.get_int = MagicMock(return_value=0)
        with patch("app.ai.agent.constants._config_svc.get_agent_config", return_value=mock_cfg):
            assert get_max_tool_calls() == 1

    def test_get_max_iterations_floor_at_one(self):
        """get_max_iterations returns 1 when config is 0."""
        from unittest.mock import patch, MagicMock

        mock_cfg = MagicMock()
        mock_cfg.get_int = MagicMock(return_value=0)
        with patch("app.ai.agent.constants._config_svc.get_agent_config", return_value=mock_cfg):
            assert get_max_iterations() == 1

    def test_get_max_llm_calls_floor_at_one(self):
        """get_max_llm_calls returns 1 when config is 0."""
        from unittest.mock import patch, MagicMock

        mock_cfg = MagicMock()
        mock_cfg.get_int = MagicMock(return_value=0)
        with patch("app.ai.agent.constants._config_svc.get_agent_config", return_value=mock_cfg):
            assert get_max_llm_calls() == 1

    def test_get_summary_timeout_floor_at_one(self):
        """get_summary_timeout returns 1 when config is 0."""
        from unittest.mock import patch, MagicMock

        from app.ai.agent.constants import get_summary_timeout

        mock_cfg = MagicMock()
        mock_cfg.get_int = MagicMock(return_value=0)
        with patch("app.ai.agent.constants._config_svc.get_agent_config", return_value=mock_cfg):
            assert get_summary_timeout() == 1


# ---------------------------------------------------------------------------
# Tests: behavioral getter allows zero (DA2-F4, DA2-F5)
# ---------------------------------------------------------------------------


class TestBehavioralGetterAllowsZero:
    """Behavioral controls (clarify rounds, synthesize rounds) can be set to
    0 to disable the loop entirely."""

    def test_get_max_clarify_rounds_allows_zero(self):
        """get_max_clarify_rounds returns 0 when config is 0 (disabled)."""
        from unittest.mock import patch, MagicMock

        mock_cfg = MagicMock()
        mock_cfg.get_int = MagicMock(return_value=0)
        with patch("app.ai.agent.constants._config_svc.get_agent_config", return_value=mock_cfg):
            assert get_max_clarify_rounds() == 0

    def test_get_max_synthesize_rounds_allows_zero(self):
        """get_max_synthesize_rounds returns 0 when config is 0 (disabled)."""
        from unittest.mock import patch, MagicMock

        mock_cfg = MagicMock()
        mock_cfg.get_int = MagicMock(return_value=0)
        with patch("app.ai.agent.constants._config_svc.get_agent_config", return_value=mock_cfg):
            assert get_max_synthesize_rounds() == 0


# ---------------------------------------------------------------------------
# Tests: getter default values
# ---------------------------------------------------------------------------


class TestGetterDefaults:
    """Verify default values for getters when no config override is present."""

    def test_get_summary_timeout_default(self):
        """get_summary_timeout defaults to 30."""
        from app.ai.agent.constants import get_summary_timeout

        assert get_summary_timeout() == 30

    def test_get_max_synthesize_rounds_default(self):
        """get_max_synthesize_rounds defaults to 2."""
        assert get_max_synthesize_rounds() == 2

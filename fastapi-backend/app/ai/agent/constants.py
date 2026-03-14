"""Shared constants for the Blair AI agent pipeline.

Single source of truth for safety limits and LLM configuration used across
graph.py and nodes. Values are read from AgentConfigService at call time
via getter functions so that admin config changes take effect without
worker restarts.

Always use getter functions directly (e.g. ``get_max_tool_calls()``) to
read live config values.

WARNING: ``from .constants import MAX_TOOL_CALLS`` freezes the value at
import time. Always call getter functions directly: ``get_max_tool_calls()``.
The ``__getattr__`` backward-compat layer only works for attribute access
on the module object (e.g. ``constants.MAX_TOOL_CALLS``), NOT for
``from ... import`` bindings which capture once and never re-evaluate.
"""

import app.ai.config_service as _config_svc


# ---------------------------------------------------------------------------
# Getter functions -- read from AgentConfigService at call time
# ---------------------------------------------------------------------------

def get_max_iterations() -> int:
    """Agent per-request maximum iterations."""
    return max(1, _config_svc.get_agent_config().get_int("agent.max_iterations", 25))


def get_max_tool_calls() -> int:
    """Agent per-request maximum tool calls."""
    return max(1, _config_svc.get_agent_config().get_int("agent.max_tool_calls", 50))


def get_max_llm_calls() -> int:
    """Agent per-request maximum LLM calls."""
    return max(1, _config_svc.get_agent_config().get_int("agent.max_llm_calls", 25))


def get_max_clarify_rounds() -> int:
    """Maximum clarification rounds per turn."""
    return max(0, _config_svc.get_agent_config().get_int("agent.max_clarify_rounds", 3))


def get_agent_temperature() -> float:
    """LLM temperature for agent calls."""
    return _config_svc.get_agent_config().get_float("agent.temperature", 0.1)


def get_agent_max_tokens() -> int:
    """LLM max tokens for agent calls."""
    return _config_svc.get_agent_config().get_int("agent.max_tokens", 4096)


def get_agent_request_timeout() -> int:
    """LLM request timeout in seconds."""
    return _config_svc.get_agent_config().get_int("agent.request_timeout", 30)


def get_context_window() -> int:
    """Context window size in tokens."""
    return _config_svc.get_agent_config().get_int("agent.context_window", 128000)


def get_context_summarize_threshold() -> float:
    """Fraction of context window that triggers auto-summarization."""
    return _config_svc.get_agent_config().get_float("agent.context_summarize_threshold", 0.90)


def get_recent_window() -> int:
    """Number of recent messages to keep during summarization."""
    return _config_svc.get_agent_config().get_int("agent.recent_window", 12)


def get_summary_max_tokens() -> int:
    """Maximum tokens for summarization output."""
    return _config_svc.get_agent_config().get_int("agent.summary_max_tokens", 1000)


def get_max_explore_iterations() -> int:
    """Maximum explore loop iterations."""
    return _config_svc.get_agent_config().get_int("agent.max_explore_iterations", 10)


def get_max_explore_llm_calls() -> int:
    """Maximum LLM calls during explore phase."""
    return _config_svc.get_agent_config().get_int("agent.max_explore_llm_calls", 15)


def get_confidence_fast_path() -> float:
    """Confidence threshold for fast-path routing."""
    return _config_svc.get_agent_config().get_float("agent.confidence_fast_path", 0.7)


def get_confidence_clarify() -> float:
    """Confidence threshold below which clarification is requested."""
    return _config_svc.get_agent_config().get_float("agent.confidence_clarify", 0.5)


def get_selection_threshold() -> int:
    """Number of search results that triggers selection UI."""
    return _config_svc.get_agent_config().get_int("agent.selection_threshold", 5)


def get_selection_max_items() -> int:
    """Maximum items shown in selection UI."""
    return _config_svc.get_agent_config().get_int("agent.selection_max_items", 20)


def get_summary_timeout() -> int:
    """Timeout in seconds for context summarization LLM calls."""
    return max(1, _config_svc.get_agent_config().get_int("agent.summary_timeout", 30))


def get_max_synthesize_rounds() -> int:
    """Maximum synthesize re-routing rounds before forcing respond."""
    return max(0, _config_svc.get_agent_config().get_int("agent.max_synthesize_rounds", 2))


# ---------------------------------------------------------------------------
# Backward-compatible module-level attributes via __getattr__
#
# WARNING: ``from .constants import MAX_TOOL_CALLS`` captures the value
# once at import time and does NOT re-evaluate on subsequent reads.
# Only ``constants.MAX_TOOL_CALLS`` (attribute access on the module object)
# goes through __getattr__ on each access. Prefer getter functions.
# ---------------------------------------------------------------------------

_ATTR_TO_GETTER = {
    "MAX_ITERATIONS": get_max_iterations,
    "MAX_TOOL_CALLS": get_max_tool_calls,
    "MAX_LLM_CALLS": get_max_llm_calls,
    "MAX_CLARIFY_ROUNDS": get_max_clarify_rounds,
    "AGENT_TEMPERATURE": get_agent_temperature,
    "AGENT_MAX_TOKENS": get_agent_max_tokens,
    "AGENT_REQUEST_TIMEOUT": get_agent_request_timeout,
    "CONTEXT_WINDOW": get_context_window,
    "CONTEXT_SUMMARIZE_THRESHOLD": get_context_summarize_threshold,
    "RECENT_WINDOW": get_recent_window,
    "SUMMARY_MAX_TOKENS": get_summary_max_tokens,
    "SUMMARY_TIMEOUT": get_summary_timeout,
    "MAX_EXPLORE_ITERATIONS": get_max_explore_iterations,
    "MAX_EXPLORE_LLM_CALLS": get_max_explore_llm_calls,
    "MAX_SYNTHESIZE_ROUNDS": get_max_synthesize_rounds,
    "CONFIDENCE_FAST_PATH": get_confidence_fast_path,
    "CONFIDENCE_CLARIFY": get_confidence_clarify,
    "SELECTION_THRESHOLD": get_selection_threshold,
    "SELECTION_MAX_ITEMS": get_selection_max_items,
}


def __getattr__(name: str):  # noqa: ANN001
    getter = _ATTR_TO_GETTER.get(name)
    if getter is not None:
        return getter()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

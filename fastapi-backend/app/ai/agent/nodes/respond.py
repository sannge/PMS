"""Respond node -- delivers the final response to the user.

Handles three cases:
1. Fast path (greeting/follow_up): 1 LLM call with tools bound
2. Post-explore: 0 LLM calls (response already in messages)
3. Post-synthesize: 0 LLM calls (response already in messages)

Includes misclassification recovery: if fast-path LLM unexpectedly
returns tool_calls, re-routes to explore_tools via routing.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from ..state import AgentState

logger = logging.getLogger(__name__)


async def respond_node(
    state: AgentState,
    *,
    bound_model_cache: list[Any],
    chat_model_cache: list[Any],
    system_prompt_cache: list[str],
) -> dict:
    """Deliver the final response.

    For fast-path requests (greetings, follow-ups with high confidence),
    makes 1 LLM call with tools bound. For post-explore/post-synthesize
    flows, the response is already in the message history.

    Args:
        state: Current pipeline state.
        bound_model_cache: Mutable list containing the tool-bound model.
        chat_model_cache: Mutable list containing the raw model.
        system_prompt_cache: Mutable list containing the system prompt.

    Returns:
        State update with current_phase set to "respond". May include
        an LLM response for fast-path requests.
    """
    # Deferred import to avoid circular dependency: graph.py -> nodes -> graph.py
    from ..graph import _sanitize_orphaned_tool_calls, _strip_completed_tool_messages

    fast_path = state.get("fast_path", False)
    total_llm_calls = state.get("total_llm_calls", 0)

    if not fast_path:
        # Post-explore or post-synthesize: response already in messages
        return {"current_phase": "respond"}

    # Fast path: 1 LLM call for greetings/follow-ups
    if not bound_model_cache:
        if not chat_model_cache:
            return {
                "messages": [AIMessage(content="Internal error: AI model not initialized.")],
                "current_phase": "respond",
            }
        model = chat_model_cache[0]
    else:
        model = bound_model_cache[0]

    system_prompt = system_prompt_cache[0] if system_prompt_cache else ""

    all_messages = list(state.get("messages", []))
    all_messages = _strip_completed_tool_messages(all_messages)
    all_messages = _sanitize_orphaned_tool_calls(all_messages)

    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)] + all_messages

    try:
        response = await model.ainvoke(messages)
    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning("respond_node LLM call failed: %s", exc)
        response = AIMessage(content="I encountered an error. Please try again.")

    # B5: If fast-path LLM returned tool_calls, clear fast_path to prevent
    # the next respond call from attempting fast-path again (misclassification).
    if isinstance(response, AIMessage) and getattr(response, "tool_calls", None):
        return {
            "messages": [response],
            "current_phase": "respond",
            "total_llm_calls": total_llm_calls + 1,
            "fast_path": False,
        }

    return {
        "messages": [response],
        "current_phase": "respond",
        "total_llm_calls": total_llm_calls + 1,
    }

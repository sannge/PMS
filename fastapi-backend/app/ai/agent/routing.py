"""Routing functions for the Blair cognitive pipeline.

Three conditional edge functions that control flow between nodes:
- route_after_understand: understand -> respond | clarify | explore
- route_after_explore: explore -> explore_tools | synthesize | respond
- route_after_respond: respond -> explore_tools | end
- route_after_synthesize: synthesize -> understand | respond
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage

from .constants import (
    get_confidence_clarify,
    get_confidence_fast_path,
    get_max_clarify_rounds,
    get_max_iterations,
    get_max_llm_calls,
    get_max_synthesize_rounds,
    get_max_tool_calls,
)
from .state import AgentState

logger = logging.getLogger(__name__)


def route_after_understand(state: AgentState) -> str:
    """Route after the understand node classifies the request.

    Returns:
        "respond" for fast-path greetings/follow-ups,
        "clarify" for low-confidence or needs_clarification,
        "explore" for everything else.
    """
    classification = state.get("classification", {})
    confidence = classification.get("confidence", 0.7)
    intent = classification.get("intent", "info_query")

    # B1: Enforce clarify round limit — prevent infinite clarify loop
    clarify_count = state.get("clarify_count", 0)

    # H5: High confidence greeting only -> fast path.
    # Follow-up questions may need document exploration, so they go through explore.
    if confidence >= get_confidence_fast_path() and intent == "greeting":
        logger.info(
            "route_after_understand: fast path (intent=%s, confidence=%.2f)",
            intent, confidence,
        )
        return "respond"

    # Low confidence or needs_clarification -> clarify (unless limit reached)
    if confidence < get_confidence_clarify() or intent == "needs_clarification":
        if clarify_count >= get_max_clarify_rounds():
            logger.info(
                "route_after_understand: clarify limit reached (%d/%d), forcing explore",
                clarify_count, get_max_clarify_rounds(),
            )
            return "explore"
        logger.info(
            "route_after_understand: clarify (intent=%s, confidence=%.2f)",
            intent, confidence,
        )
        return "clarify"

    # Everything else -> explore
    logger.info(
        "route_after_understand: explore (intent=%s, confidence=%.2f)",
        intent, confidence,
    )
    return "explore"


def route_after_explore(state: AgentState) -> str:
    """Route after the explore node finishes an LLM call.

    If the LLM produced tool_calls, loop back to explore_tools.
    If no tool_calls, check if synthesis is needed for complex queries.
    Otherwise, route to respond.

    Returns:
        "explore_tools" to execute pending tool calls,
        "synthesize" for complex/multi_step queries,
        "respond" otherwise.
    """
    messages = state.get("messages", [])
    if not messages:
        return "respond"

    last = messages[-1]

    # If last message has tool_calls, loop back to explore_tools
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        # Check safety limits
        if state.get("total_llm_calls", 0) >= get_max_llm_calls():
            logger.info("route_after_explore: LLM limit reached, going to respond")
            return "respond"
        if state.get("total_tool_calls", 0) >= get_max_tool_calls():
            logger.info("route_after_explore: tool limit reached, going to respond")
            return "respond"
        if state.get("iteration_count", 0) >= get_max_iterations():
            logger.info("route_after_explore: iteration limit reached, going to respond")
            return "respond"
        # L1: TODO — Wire explore-specific iteration limit once a dedicated
        # explore_iteration_count field is added to AgentState.  Currently
        # only total_llm_calls/total_tool_calls/iteration_count are tracked
        # globally, so the explore-specific limits (max_explore_iterations=10,
        # max_explore_llm_calls=15) cannot be enforced without a new counter.
        return "explore_tools"

    # No tool calls -- check if synthesis needed
    classification = state.get("classification", {})
    complexity = classification.get("complexity", "simple")
    intent = classification.get("intent", "info_query")

    if complexity == "complex" or intent == "multi_step":
        logger.info("route_after_explore: routing to synthesize (complexity=%s)", complexity)
        return "synthesize"

    return "respond"


def route_after_respond(state: AgentState) -> str:
    """Misclassification recovery after the respond node.

    If the fast-path LLM unexpectedly returned tool_calls,
    re-route to explore_tools to execute them.

    Returns:
        "explore_tools" for misclassified fast-path with tool calls,
        "end" otherwise.
    """
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        logger.info("route_after_respond: misclassification recovery, re-routing to explore_tools")
        return "explore_tools"

    return "end"


def route_after_synthesize(state: AgentState) -> str:
    """Route after synthesis completes.

    If the user provided a correction (HumanMessage from interrupt resume)
    and the current phase is synthesize, route back to understand for
    re-classification. Otherwise, deliver the synthesized response.

    Returns:
        "understand" if user correction detected (within synthesize limit),
        "respond" otherwise.
    """
    # B3: Cap synthesize re-routing to prevent infinite synthesize->understand loop
    max_rounds = get_max_synthesize_rounds()
    if state.get("synthesize_count", 0) >= max_rounds:
        logger.info(
            "route_after_synthesize: synthesize limit reached (%d/%d), forcing respond",
            state.get("synthesize_count", 0), max_rounds,
        )
        return "respond"

    messages = state.get("messages", [])
    if not messages:
        return "respond"

    last = messages[-1]
    # S7: Only re-route if the last message is a HumanMessage AND the current
    # phase is synthesize (indicating an interrupt-resume correction).
    if isinstance(last, HumanMessage) and state.get("current_phase") == "synthesize":
        logger.info("route_after_synthesize: user correction detected, re-classifying")
        return "understand"

    return "respond"

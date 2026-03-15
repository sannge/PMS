"""Explore node -- ReAct loop with tool calling.

This is the main reasoning node that calls the LLM with all tools bound.
It replaces the old ``_agent_node`` from the 3-node graph, enhanced with
classification context from the understand phase.

The explore <-> explore_tools loop continues until the LLM produces a
text-only response (no tool_calls) or safety limits are reached.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from ..constants import (
    get_confidence_clarify,
    get_max_clarify_rounds,
    get_max_iterations,
    get_max_llm_calls,
    get_max_tool_calls,
)
from ..source_references import drain_accumulated_sources
from ..prompts import EXPLORE_SUFFIX_TEMPLATE
from ..state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auto-clarify helpers (moved from graph.py)
# ---------------------------------------------------------------------------

# Maximum number of bullet-list options to extract for clarification UI.
_MAX_CLARIFICATION_OPTIONS = 5

_INPUT_REQUEST_PHRASES = (
    "let me know",
    "please specify",
    "please provide",
    "please choose",
    "would you like",
    "do you want",
    "do you prefer",
    "here are some things i can help",
    "here are some options",
)


def _text_requests_user_input(text: str) -> bool:
    """Detect if an LLM text response is asking the user for input.

    Checks the tail of the response (last 5 non-empty lines) for question
    marks and common request-for-input phrases. Returns True if the LLM
    appears to be asking instead of using request_clarification.
    """
    if not text or len(text.strip()) < 10:
        return False
    lines = [line for line in text.strip().split("\n") if line.strip()]
    tail_lines = lines[-5:]
    # Only count ? if the line looks like natural language, not code
    for line in tail_lines:
        stripped = line.strip()
        if any(c in stripped for c in ("()", "{}", "[]", "==", "=>", "::", "//")):
            continue
        if stripped.endswith("?"):
            return True
    tail = "\n".join(tail_lines).lower()
    return any(p in tail for p in _INPUT_REQUEST_PHRASES)


def _extract_clarification(text: str) -> tuple[str, list[str]]:
    """Extract question text and any bullet-list options from LLM text."""
    options: list[str] = []
    other: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        m = re.match(r"^[-*\u2022]\s+(.+)$", stripped) or re.match(
            r"^\d+[.)]\s+(.+)$", stripped
        )
        if m:
            opt = m.group(1).strip()
            # Skip very short (<4 chars) or very long (120+ chars) option text
            if 3 < len(opt) < 120:
                options.append(opt)
        else:
            other.append(line)
    question = "\n".join(other).strip() or text.strip()
    return question, options[:_MAX_CLARIFICATION_OPTIONS] if options else []


# ---------------------------------------------------------------------------
# Explore suffix builder
# ---------------------------------------------------------------------------

def _build_explore_suffix(state: AgentState) -> str:
    """Build an explore-phase suffix from the classification context."""
    classification = state.get("classification")
    if classification is None:
        return ""

    intent = classification.get("intent", "unknown")
    complexity = classification.get("complexity", "unknown")
    data_sources = ", ".join(classification.get("data_sources", [])) or "none specified"
    entities = classification.get("entities", [])
    # S5: Sanitize entity values to prevent injection via classification output
    entities_str = ", ".join(
        '{safe_type}: {safe_val}'.format(
            safe_type=str(e.get("type", "?"))[:20].replace("\n", " ").replace("\r", " "),
            safe_val=str(e.get("value", "?"))[:50].replace("\n", " ").replace("\r", " "),
        )
        for e in entities
        if isinstance(e, dict)
    ) or "none identified"

    suffix = EXPLORE_SUFFIX_TEMPLATE.format(
        intent=intent,
        complexity=complexity,
        data_sources=data_sources,
        entities=entities_str,
    )

    # DA-R3: When clarify_count exhausted and confidence is still low,
    # add an uncertainty note so the LLM knows to hedge its response.
    # DA3-HIGH-002: Require clarify_count > 0 to avoid firing when
    # MAX_CLARIFY_ROUNDS=0 (operator disabled clarification entirely).
    clarify_count = state.get("clarify_count", 0)
    confidence = classification.get("confidence", 1.0)
    if clarify_count > 0 and clarify_count >= get_max_clarify_rounds() and confidence < get_confidence_clarify():
        suffix += (
            "\n**Note**: The user's request is still ambiguous after "
            f"{clarify_count} clarification attempts. Do your best to answer "
            "based on available context, but clearly state any assumptions "
            "you're making. If multiple interpretations exist, briefly present "
            "the most likely one and mention alternatives."
        )

    return suffix


# ---------------------------------------------------------------------------
# Explore node
# ---------------------------------------------------------------------------

async def explore_node(
    state: AgentState,
    *,
    bound_model_cache: list[Any],
    chat_model_cache: list[Any],
    system_prompt_cache: list[str],
) -> dict:
    """Single LLM call with all tools bound -- the core of the ReAct loop.

    Enhanced with classification context from the understand phase.
    Uses two-stage context management (strip completed, auto-summarize).

    Args:
        state: Current pipeline state.
        bound_model_cache: Mutable list containing the tool-bound model.
        chat_model_cache: Mutable list containing the raw model (for summarization).
        system_prompt_cache: Mutable list containing the system prompt.

    Returns:
        State update with LLM response and incremented counters.
    """
    # Deferred import to avoid circular dependency
    from ..graph import (
        _maybe_summarize,
        _sanitize_orphaned_tool_calls,
        _strip_completed_tool_messages,
    )

    total_llm_calls = state.get("total_llm_calls", 0)
    iteration_count = state.get("iteration_count", 0)

    # Safety limits
    if total_llm_calls >= get_max_llm_calls() or iteration_count >= get_max_iterations():
        return {
            "messages": [AIMessage(content=(
                "I've reached my processing limit for this request. "
                "Here's what I found so far based on the data I gathered above."
            ))],
            "current_phase": "explore",
        }

    if not bound_model_cache:
        return {
            "messages": [AIMessage(content="Internal error: AI model not initialized.")],
            "current_phase": "explore",
        }

    system_prompt = system_prompt_cache[0] if system_prompt_cache else ""
    # S1: Only append classification context on the first iteration to avoid
    # redundant tokens on subsequent explore cycles.
    full_system_prompt = system_prompt
    if state.get("iteration_count", 0) == 0:
        explore_suffix = _build_explore_suffix(state)
        if explore_suffix:
            full_system_prompt += explore_suffix

    model = bound_model_cache[0]

    # --- Two-stage context management ---
    all_messages = list(state.get("messages", []))

    # Stage A: Strip completed tool messages
    all_messages = _strip_completed_tool_messages(all_messages)

    # Stage B: Auto-summarize if approaching context window threshold
    summary_model = chat_model_cache[0] if chat_model_cache else model
    context_summary: str | None = None
    try:
        all_messages, context_summary = await _maybe_summarize(all_messages, summary_model, state)
    except Exception:
        logger.warning("Context summarization failed, proceeding without it", exc_info=True)

    # Sanitize: remove orphaned tool_calls (must run AFTER stripping)
    all_messages = _sanitize_orphaned_tool_calls(all_messages)

    messages: list[BaseMessage] = [SystemMessage(content=full_system_prompt)] + all_messages

    try:
        response = await model.ainvoke(messages)
    except Exception as exc:
        logger.warning("explore_node LLM call failed: %s", exc, exc_info=True)
        response = AIMessage(content="I encountered an error. Please try again.")

    # Auto-clarify: convert text questions to request_clarification tool calls
    already_attempted = state.get("auto_clarify_attempted", False)
    if (
        isinstance(response, AIMessage)
        and response.content
        and not getattr(response, "tool_calls", None)
        and not already_attempted
        and _text_requests_user_input(str(response.content))
    ):
        question, options = _extract_clarification(str(response.content))
        args: dict[str, Any] = {"question": question}
        if options:
            args["options"] = options
        response = AIMessage(
            content="",
            tool_calls=[{
                "name": "request_clarification",
                "args": args,
                "id": f"auto_clarify_{uuid4().hex[:8]}",
            }],
        )
        logger.info("Auto-converted text question to request_clarification tool call")
        result: dict[str, Any] = {
            "messages": [response],
            "total_llm_calls": total_llm_calls + 1,
            "iteration_count": iteration_count + 1,
            "auto_clarify_attempted": True,
            "current_phase": "explore",
        }
        if context_summary:
            result["context_summary"] = context_summary
        return result

    result = {
        "messages": [response],
        "total_llm_calls": total_llm_calls + 1,
        "iteration_count": iteration_count + 1,
        "current_phase": "explore",
    }
    if context_summary:
        result["context_summary"] = context_summary
    return result


# ---------------------------------------------------------------------------
# Execute tools (explore_tools node)
# ---------------------------------------------------------------------------

async def execute_tools(
    state: AgentState,
    *,
    tool_node: ToolNode,
) -> dict:
    """Execute tool calls from the LLM response. Handle HITL for writes.

    Args:
        state: Current pipeline state.
        tool_node: LangGraph ToolNode with all tools registered.

    Returns:
        State update with tool results and incremented tool counter.
    """
    messages = state.get("messages", [])
    last = messages[-1] if messages else None

    if not (isinstance(last, AIMessage) and getattr(last, "tool_calls", None)):
        return {}

    new_calls = len(last.tool_calls)
    current_total = state.get("total_tool_calls", 0)
    max_tool_calls = get_max_tool_calls()

    if current_total + new_calls > max_tool_calls:
        # DA-R4-004: Return ToolMessages (not AIMessage) to satisfy provider
        # message protocol -- tool_calls must be followed by ToolMessages.
        limit_msg = (
            "Tool call limit reached. Skipped to avoid exceeding "
            "the maximum number of operations."
        )
        tool_results = [
            ToolMessage(
                content=limit_msg,
                tool_call_id=tc["id"],
                name=tc.get("name", "unknown"),
            )
            for tc in last.tool_calls
        ]
        return {
            "messages": tool_results,
            "total_tool_calls": max_tool_calls,
        }

    # NOTE: Write tools and request_clarification handle their own interrupt()
    # calls internally. We must NOT catch GraphBubbleUp/GraphInterrupt here
    # as those must propagate to LangGraph for proper HITL pausing.
    try:
        result = await tool_node.ainvoke(state)
    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning("Tool execution failed: %s", exc)
        # DA-R4-004: Return ToolMessages to satisfy provider protocol.
        error_results = [
            ToolMessage(
                content="Tool encountered an issue. Let me try a different approach.",
                tool_call_id=tc["id"],
                name=tc.get("name", "unknown"),
            )
            for tc in last.tool_calls
        ]
        return {
            "messages": error_results,
            "total_tool_calls": current_total + new_calls,
        }

    # S4: Collect tool results into the research field for downstream synthesis.
    result_messages = result.get("messages", [])
    # H3: Raise per-entry cap from 500 to 3000 chars so search results
    # survive into synthesis.  Window is capped at 8 entries (see below).
    _TOOL_RESULT_CHARS = 3000
    tool_results = []
    for msg in result_messages:
        if isinstance(msg, ToolMessage):
            tool_results.append({
                "tool": getattr(msg, "name", "unknown"),
                "result": str(msg.content)[:_TOOL_RESULT_CHARS],
            })

    return_dict: dict[str, Any] = {
        "messages": result_messages,
        "total_tool_calls": current_total + new_calls,
    }

    existing = state.get("research", {})
    if not isinstance(existing, dict):
        existing = {}

    # Merge tool results when present
    if tool_results:
        existing_results = existing.get("tool_results") or []
        # DA3-CRIT-001: Cap accumulator at write time to prevent unbounded
        # growth in checkpoint storage. max_tool_calls is the natural upper
        # bound since each tool call produces at most one result entry.
        combined = (existing_results + tool_results)[-max_tool_calls:]
        return_dict.setdefault("research", {})["tool_results"] = combined

    # Always merge source references independently from tool_results.
    # A tool may push sources into the ContextVar without producing a
    # ToolMessage (e.g. side-effect-only tools). Writing sources only
    # when tool_results is non-empty would silently lose those references.
    accumulated_sources = drain_accumulated_sources()
    if accumulated_sources:
        existing_sources = existing.get("sources") or []
        combined_sources = (existing_sources + accumulated_sources)[-max_tool_calls:]
        return_dict.setdefault("research", {})["sources"] = combined_sources

    return return_dict

"""Synthesize node -- organizes research findings for complex queries.

Only reached when classification.complexity is "complex" or intent is
"multi_step". Makes 1 LLM call to organize accumulated research into
a structured response.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..prompts import SYNTHESIS_PROMPT
from ..state import AgentState

logger = logging.getLogger(__name__)


async def synthesize_node(
    state: AgentState,
    *,
    chat_model_cache: list[Any],
) -> dict:
    """Synthesize accumulated research into a structured response.

    Uses the raw (unbound) chat model with the SYNTHESIS_PROMPT to
    organize tool results into a clear, structured answer.

    Args:
        state: Current pipeline state.
        chat_model_cache: Mutable list containing the raw LangChain chat model.

    Returns:
        State update with synthesized response and incremented LLM counter.
    """
    total_llm_calls = state.get("total_llm_calls", 0)

    synthesize_count = state.get("synthesize_count", 0)

    if not chat_model_cache:
        logger.error("synthesize_node: no chat model available")
        return {
            "current_phase": "synthesize",
            "total_llm_calls": total_llm_calls,
            # Don't increment synthesize_count -- no actual synthesis attempted.
        }

    model = chat_model_cache[0]

    # DA-R3: Prefer the research.tool_results accumulator populated by
    # execute_tools (S4) over scanning all messages. Falls back to message
    # scan when the accumulator is empty (e.g., simple flows).
    research = state.get("research", {})
    # DA3-HIGH-001: Use `or []` to handle research={"tool_results": None}
    tool_results_acc = (research.get("tool_results") or []) if isinstance(research, dict) else []

    if tool_results_acc:
        # Accumulator entries are pre-truncated to 500 chars each (in execute_tools),
        # so [-15:] ≈ 7,500 chars max — well within context window budget.
        research_context = [
            f"Tool result ({r.get('tool', 'unknown')}): {r.get('result', '')}"
            for r in tool_results_acc[-15:]
        ]
    else:
        # Fallback: scan messages for tool and AI content.
        # Entries are truncated to 2,000 chars each, so [-10:] ≈ 20,000 chars max.
        all_messages = state.get("messages", [])
        research_context = []
        for msg in all_messages:
            if isinstance(msg, ToolMessage) and msg.content:
                tool_name = getattr(msg, "name", "tool")
                research_context.append(f"Tool result ({tool_name}): {str(msg.content)[:2000]}")
            elif isinstance(msg, AIMessage) and msg.content:
                research_context.append(str(msg.content)[:2000])
        research_context = research_context[-10:]

    research_text = "\n---\n".join(research_context) if research_context else "No research data available."

    synthesis_messages = [
        SystemMessage(content=SYNTHESIS_PROMPT),
        HumanMessage(content=f"Research findings to synthesize:\n\n{research_text}"),
    ]

    try:
        response = await model.ainvoke(synthesis_messages)
    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning("synthesize_node LLM call failed: %s", exc)
        # DA-R3: Don't increment synthesize_count on error -- the synthesis
        # didn't produce useful output. The routing logic only re-routes to
        # "understand" on HumanMessage, so failed synthesis routes to "respond"
        # safely without needing the counter as a loop guard.
        return {
            "current_phase": "synthesize",
            "total_llm_calls": total_llm_calls + 1,
        }

    return {
        "messages": [response] if response.content else [],
        "current_phase": "synthesize",
        "total_llm_calls": total_llm_calls + 1,
        # B3: Track synthesize rounds to prevent infinite synthesize->understand loop.
        # Only increment on successful synthesis (DA-R3).
        "synthesize_count": synthesize_count + 1,
    }

"""Understand node -- classifies user intent with 1 LLM call.

Uses a focused classification prompt on the last few messages to produce
a structured RequestClassification.  Sets fast_path for high-confidence
greetings/follow-ups.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..constants import get_confidence_fast_path
from ..prompts import CLASSIFICATION_PROMPT
from ..state import AgentState, RequestClassification

logger = logging.getLogger(__name__)

# Number of recent messages to include for classification context
_CLASSIFY_CONTEXT_WINDOW = 6

# Default classification when JSON parsing fails
_FALLBACK_CLASSIFICATION: RequestClassification = {
    "intent": "info_query",
    "confidence": 0.7,
    "data_sources": [],
    "entities": [],
    "clarification_questions": [],
    "complexity": "moderate",
    "reasoning": "Fallback classification due to parse failure",
}


def _parse_classification(raw_text: str) -> RequestClassification:
    """Parse LLM JSON response into a RequestClassification.

    Handles common issues like markdown code fences around JSON.
    Falls back to defaults on parse failure.
    """
    text = raw_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (possibly ```json)
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[: -3]
    text = text.strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("understand_node: failed to parse classification JSON, using fallback")
        return dict(_FALLBACK_CLASSIFICATION)  # type: ignore[return-value]

    # Validate and coerce fields
    valid_intents = {
        "info_query", "action_request", "needs_clarification",
        "multi_step", "greeting", "follow_up",
    }
    valid_complexities = {"simple", "moderate", "complex"}

    intent = data.get("intent", "info_query")
    if intent not in valid_intents:
        intent = "info_query"

    confidence = data.get("confidence", 0.7)
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.7

    complexity = data.get("complexity", "moderate")
    if complexity not in valid_complexities:
        complexity = "moderate"

    return {
        "intent": intent,
        "confidence": confidence,
        "data_sources": data.get("data_sources", []) if isinstance(data.get("data_sources"), list) else [],
        "entities": data.get("entities", []) if isinstance(data.get("entities"), list) else [],
        "clarification_questions": (
            data.get("clarification_questions", [])
            if isinstance(data.get("clarification_questions"), list)
            else []
        ),
        "complexity": complexity,
        "reasoning": str(data.get("reasoning", "")),
    }


async def understand_node(
    state: AgentState,
    *,
    chat_model_cache: list[Any],
    system_prompt_cache: list[str],
) -> dict:
    """Classify the user's request with 1 LLM call.

    Uses the raw (unbound) chat model for efficiency -- no tool definitions
    are sent, keeping the classification prompt small and fast.

    Args:
        state: Current pipeline state.
        chat_model_cache: Mutable list containing the raw LangChain chat model.
        system_prompt_cache: Mutable list containing the system prompt (unused
            here but kept for consistent node signatures).

    Returns:
        State update dict with classification, current_phase, and fast_path.
    """
    total_llm_calls = state.get("total_llm_calls", 0)

    if not chat_model_cache:
        logger.error("understand_node: no chat model available")
        return {
            "current_phase": "understand",
            "classification": dict(_FALLBACK_CLASSIFICATION),
            "fast_path": False,
            "total_llm_calls": total_llm_calls,
        }

    model = chat_model_cache[0]

    # Build classification messages -- only last N messages for efficiency
    all_messages = state.get("messages", [])
    recent = all_messages[-_CLASSIFY_CONTEXT_WINDOW:] if len(all_messages) > _CLASSIFY_CONTEXT_WINDOW else all_messages

    # Build a compact text representation for classification
    context_lines = []
    for msg in recent:
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            # B2: Sanitize user content to prevent prompt injection
            safe_content = content[:500].replace("```", "` ` `")
            context_lines.append(f"[USER CONTENT]: {safe_content}")
        elif hasattr(msg, "content") and msg.content:
            content = str(msg.content)[:500]
            context_lines.append(f"Assistant: {content}")

    context_text = "\n".join(context_lines) if context_lines else "No context available."

    classify_messages = [
        SystemMessage(content=CLASSIFICATION_PROMPT),
        HumanMessage(content=f"Conversation context:\n{context_text}"),
    ]

    try:
        response = await model.ainvoke(classify_messages)
        raw_text = str(response.content) if response.content else ""
        classification = _parse_classification(raw_text)
    except Exception as exc:
        from langgraph.errors import GraphBubbleUp

        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning("understand_node: classification LLM call failed: %s", exc)
        classification = dict(_FALLBACK_CLASSIFICATION)  # type: ignore[assignment]

    # Determine fast path
    fast_path = (
        classification.get("confidence", 0.0) >= get_confidence_fast_path()
        and classification.get("intent") in ("greeting", "follow_up")
    )

    return {
        "current_phase": "understand",
        "classification": classification,
        "fast_path": fast_path,
        "total_llm_calls": total_llm_calls + 1,
    }

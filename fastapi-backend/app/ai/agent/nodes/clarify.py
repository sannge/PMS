"""Clarify node -- batches clarification questions via interrupt().

Triggered when the understand node produces low confidence or
``needs_clarification`` intent.  Uses LangGraph's ``interrupt()``
to pause the graph and present questions to the user.

After the user responds via ``/api/ai/chat/resume``, their answers
are injected as a HumanMessage and the graph routes back to
understand for re-classification.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from ..state import AgentState

logger = logging.getLogger(__name__)


def _build_clarification_payload(state: AgentState) -> dict[str, Any]:
    """Build the interrupt payload from classification questions.

    Returns a dict suitable for the frontend clarification UI.
    """
    classification = state.get("classification", {})
    questions = classification.get("clarification_questions", [])
    reasoning = classification.get("reasoning", "")

    # Build structured question list
    question_list: list[dict[str, Any]] = []
    for q in questions:
        if isinstance(q, str) and q.strip():
            question_list.append({"text": q.strip()})
        elif isinstance(q, dict):
            question_list.append(q)

    # Fallback if no questions were generated
    if not question_list:
        question_list.append({"text": "Could you provide more details about what you're looking for?"})

    return {
        "type": "clarification",
        "questions": question_list,
        "context": reasoning or "I need some clarification to help you better.",
    }


async def clarify_node(state: AgentState) -> dict:
    """Pause the graph with clarification questions.

    Uses ``interrupt()`` to present batched questions to the user.
    When the user resumes, their answers become a HumanMessage
    that flows back to the understand node for re-classification.

    Args:
        state: Current pipeline state.

    Returns:
        State update dict with current_phase and the user's response
        as a HumanMessage (after resume).
    """
    payload = _build_clarification_payload(state)

    logger.info(
        "clarify_node: interrupting with %d question(s)",
        len(payload.get("questions", [])),
    )

    # interrupt() raises GraphInterrupt -- the graph pauses here.
    # When resumed, interrupt() returns the user's response value.
    user_response = interrupt(payload)

    # After resume: inject user's answer as a HumanMessage so the
    # understand node can re-classify with the new context.
    answer_text = str(user_response) if user_response else ""
    logger.info("clarify_node: resumed with user response (length=%d)", len(answer_text))

    return {
        "current_phase": "clarify",
        "messages": [HumanMessage(content=answer_text)] if answer_text else [],
        # B1: Track clarify rounds to prevent infinite clarify loop.
        "clarify_count": state.get("clarify_count", 0) + 1,
    }

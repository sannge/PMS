"""Unit tests for the clarify node (app.ai.agent.nodes.clarify).

Tests cover:
- Interrupt payload construction with questions
- Fallback when no questions are provided
- Question batching
- Payload format for frontend
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langgraph.errors import GraphInterrupt

from app.ai.agent.nodes.clarify import _build_clarification_payload, clarify_node


# ---------------------------------------------------------------------------
# Tests: _build_clarification_payload
# ---------------------------------------------------------------------------


class TestBuildClarificationPayload:
    def test_builds_payload_from_classification_questions(self):
        state = {
            "messages": [],
            "classification": {
                "intent": "needs_clarification",
                "confidence": 0.3,
                "clarification_questions": [
                    "Which project do you mean?",
                    "What time range?",
                ],
                "reasoning": "Multiple projects found",
            },
        }

        payload = _build_clarification_payload(state)

        assert payload["type"] == "clarification"
        assert len(payload["questions"]) == 2
        assert payload["questions"][0]["text"] == "Which project do you mean?"
        assert payload["questions"][1]["text"] == "What time range?"
        assert payload["context"] == "Multiple projects found"

    def test_empty_questions_adds_fallback(self):
        state = {
            "messages": [],
            "classification": {
                "intent": "needs_clarification",
                "confidence": 0.3,
                "clarification_questions": [],
                "reasoning": "",
            },
        }

        payload = _build_clarification_payload(state)

        assert len(payload["questions"]) == 1
        assert "more details" in payload["questions"][0]["text"].lower()

    def test_no_classification_uses_defaults(self):
        state = {"messages": []}

        payload = _build_clarification_payload(state)

        assert payload["type"] == "clarification"
        assert len(payload["questions"]) == 1

    def test_blank_questions_filtered(self):
        state = {
            "messages": [],
            "classification": {
                "clarification_questions": ["Valid question?", "", "  ", "Another question?"],
                "reasoning": "test",
            },
        }

        payload = _build_clarification_payload(state)

        # Only non-blank questions included (+ fallback if all blank, but here 2 are valid)
        assert len(payload["questions"]) == 2
        assert payload["questions"][0]["text"] == "Valid question?"
        assert payload["questions"][1]["text"] == "Another question?"

    def test_dict_questions_passed_through(self):
        state = {
            "messages": [],
            "classification": {
                "clarification_questions": [
                    {"text": "Which project?", "options": ["Alpha", "Beta"]},
                ],
                "reasoning": "test",
            },
        }

        payload = _build_clarification_payload(state)

        assert len(payload["questions"]) == 1
        assert payload["questions"][0]["text"] == "Which project?"
        assert payload["questions"][0]["options"] == ["Alpha", "Beta"]


# ---------------------------------------------------------------------------
# Tests: clarify_node (interrupt behavior)
# ---------------------------------------------------------------------------


class TestClarifyNode:
    async def test_clarify_node_calls_interrupt(self):
        """clarify_node should call interrupt() which raises in LangGraph runtime.

        Outside the LangGraph runtime, interrupt() raises RuntimeError
        because there is no runnable context. In production, LangGraph
        catches this as GraphInterrupt.
        """
        state = {
            "messages": [],
            "classification": {
                "intent": "needs_clarification",
                "confidence": 0.3,
                "clarification_questions": ["Which project?"],
                "reasoning": "Ambiguous",
            },
        }

        # Outside LangGraph runtime, interrupt() raises RuntimeError
        # (no runnable context). In production this becomes GraphInterrupt.
        with pytest.raises((GraphInterrupt, RuntimeError)):
            await clarify_node(state)

    async def test_clarify_node_resumes_with_user_answer(self):
        """When interrupt() returns (after resume), the answer becomes a HumanMessage."""
        state = {
            "messages": [],
            "classification": {
                "clarification_questions": ["Which project?"],
                "reasoning": "test",
            },
        }

        # Mock interrupt to return the user's answer directly
        with patch("app.ai.agent.nodes.clarify.interrupt", return_value="Alpha"):
            result = await clarify_node(state)

        assert result["current_phase"] == "clarify"
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "Alpha"
        # B1: clarify_count incremented
        assert result["clarify_count"] == 1

    async def test_clarify_count_increments_from_existing(self):
        """B1: clarify_count increments from existing state value."""
        state = {
            "messages": [],
            "classification": {
                "clarification_questions": ["Which project?"],
                "reasoning": "test",
            },
            "clarify_count": 2,
        }

        with patch("app.ai.agent.nodes.clarify.interrupt", return_value="Beta"):
            result = await clarify_node(state)

        assert result["clarify_count"] == 3

    async def test_clarify_node_empty_response(self):
        """When user provides empty response, no message is added."""
        state = {
            "messages": [],
            "classification": {
                "clarification_questions": ["Which project?"],
                "reasoning": "test",
            },
        }

        with patch("app.ai.agent.nodes.clarify.interrupt", return_value=""):
            result = await clarify_node(state)

        assert result["current_phase"] == "clarify"
        assert result["messages"] == []

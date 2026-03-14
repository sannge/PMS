"""Agent state definitions for the Blair AI cognitive pipeline.

Defines the typed state that flows through the 7-node agent graph:
    START -> intake -> understand -> [clarify ->] explore <-> explore_tools -> [synthesize ->] respond -> END
"""

from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


class RequestClassification(TypedDict, total=False):
    """Structured classification of a user request, produced by the understand node."""

    intent: Literal[
        "info_query",
        "action_request",
        "needs_clarification",
        "multi_step",
        "greeting",
        "follow_up",
    ]
    confidence: float  # 0.0-1.0
    data_sources: list[str]  # ["projects", "tasks", "knowledge", "members", "applications"]
    entities: list[dict[str, str]]  # [{"type": "project", "value": "Alpha"}]
    clarification_questions: list[str]
    complexity: Literal["simple", "moderate", "complex"]
    reasoning: str


class ResearchFindings(TypedDict, total=False):
    """Accumulated research from the explore phase."""

    tool_results: list[dict[str, str]]  # [{"tool": "get_project_details", "result": "..."}]
    sources: list[dict]


class AgentState(TypedDict):
    """State for the Blair cognitive pipeline.

    Fields:
    - **conversation**: messages (with LangGraph's add_messages reducer)
    - **identity**: user_id, accessible_app_ids, accessible_project_ids
    - **safety**: total_tool_calls, total_llm_calls, iteration_count
    - **pipeline**: current_phase, classification, research, fast_path
    """

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]

    # Identity / RBAC
    user_id: str
    accessible_app_ids: list[str]
    accessible_project_ids: list[str]

    # Safety counters
    total_tool_calls: int
    total_llm_calls: int
    iteration_count: int

    # Auto-clarify guard — prevents the heuristic from firing more than once per turn
    # CR2-M1: NotRequired — initial state dicts omit this; intake_node resets it per turn.
    auto_clarify_attempted: NotRequired[bool]

    # Context summarization — populated when messages are auto-summarized
    context_summary: NotRequired[str | None]

    # Pipeline phase tracking
    current_phase: NotRequired[str]
    classification: NotRequired[RequestClassification]
    research: NotRequired[ResearchFindings]
    fast_path: NotRequired[bool]

    # Loop guards — prevent infinite clarify/synthesize loops (B1, B3)
    clarify_count: NotRequired[int]
    synthesize_count: NotRequired[int]


def extract_last_user_message(state: AgentState) -> str:
    """Extract the most recent user message content from conversation history."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""

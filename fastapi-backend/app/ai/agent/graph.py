"""Blair AI agent graph — ReAct loop with human-in-the-loop support."""

from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10  # Prevent infinite ReAct loops
MAX_TOOL_CALLS = 50  # Hard limit on total tool calls across all iterations

# LLM configuration constants — shared across all provider constructors.
AGENT_TEMPERATURE = 0.1
AGENT_MAX_TOKENS = 4096
AGENT_REQUEST_TIMEOUT = 30  # seconds

# Module-level checkpointer — set via ``set_checkpointer`` at startup.
_checkpointer: Any | None = None


def get_checkpointer() -> Any | None:
    """Return the global checkpointer (or None if not configured)."""
    return _checkpointer


def set_checkpointer(cp: Any) -> None:
    """Register the global checkpointer for time-travel support."""
    global _checkpointer
    _checkpointer = cp


class AgentState(TypedDict):
    """State that flows through the agent graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    accessible_app_ids: list[str]
    accessible_project_ids: list[str]


SYSTEM_PROMPT = (
    "You are Blair, the PM Desktop AI assistant. You help users with their "
    "projects, tasks, and knowledge base.\n\n"
    "Be concise and professional. Give direct answers. No filler, no preamble, "
    "no unnecessary pleasantries. Use bullet points and tables over prose. "
    "Only elaborate when the user asks.\n\n"
    "You have access to the user's applications, projects, tasks, and knowledge "
    "base documents (including regular documents and canvas documents). You can "
    "create tasks, update statuses, and create documents — always confirm before "
    "taking action.\n\n"
    "Tool usage:\n"
    "- List your applications → get_applications tool\n"
    "- Browse documents/folders → browse_knowledge tool\n"
    "- Content search (document search, knowledge lookup) → query_knowledge tool\n"
    "- Structural questions (projects, tasks, members, statuses) → sql_query tool\n"
    "- Specific project overview → get_projects, get_project_status, get_tasks tools\n"
    "- Detailed task info → get_task_detail tool\n"
    "- Late work → get_overdue_tasks tool\n"
    "- Team composition → get_team_members tool\n"
    "- Image analysis → understand_image tool\n"
    "- Application/project parameters accept UUIDs or names (partial match)\n"
    "- User identity (who am I, my email, my account) → sql_query tool "
    "(query v_users with current_setting('app.current_user_id')::uuid)\n"
    "- Write operations → always confirm before executing\n"
    "- Include source references when citing content (document title + section)\n"
    "- If you don't find relevant information, say so — don't guess\n\n"
    "Important:\n"
    "- You have full conversation history. You can reference earlier messages.\n"
    "- The scoped views (v_applications, v_projects, v_tasks, etc.) already "
    "filter to data the current user can access. You do NOT need "
    "current_setting() to query them — just SELECT from the view directly.\n"
    "- Only use current_setting('app.current_user_id')::uuid when you need "
    "to match a specific column like assignee_id, reporter_id, or user id "
    "against the current user.\n"
    "- NEVER use current_setting() with any parameter other than "
    "'app.current_user_id'. Parameters like 'app.current_application_id' or "
    "'app.current_project_id' do NOT exist.\n\n"
    "Knowledge search behavior:\n"
    "- When query_knowledge returns results, present the top 10 most relevant as a numbered list. "
    "Each entry: number, title, section heading (if any), and a one-sentence summary of relevance.\n"
    "- Wait for the user to pick one or more items by number before showing full content.\n"
    "- When the user picks an item, show the full chunk text from results you already have. "
    "Do NOT re-search.\n\n"
    "Clarification:\n"
    "- If the request is ambiguous, ask for clarification before proceeding. "
    "Use request_clarification to present options when helpful.\n"
    "- Ask one thing at a time. Get the answer, then ask the next if needed.\n"
    "- Don't over-ask — if you have enough context, just answer."
)


async def _get_langchain_chat_model(
    provider_registry: Any,
    db: Any,
    user_id: UUID | None = None,
) -> Any:
    """Build a LangChain ChatModel from our ProviderRegistry config.

    Resolves the active provider configuration from the database and
    constructs the appropriate LangChain chat model adapter. This bridges
    our custom ProviderRegistry (which stores encrypted API keys and
    provider configs) with LangChain's ChatModel interface that LangGraph
    ToolNode expects.

    Args:
        provider_registry: ProviderRegistry instance.
        db: Active async database session.
        user_id: Optional user ID for user-specific provider override.

    Returns:
        A LangChain ChatModel (ChatOpenAI or ChatAnthropic) configured
        with the resolved provider's credentials and settings.

    Raises:
        ValueError: If the provider type is not supported.
    """
    provider_orm, model_orm = await provider_registry._resolve_provider(
        db, "chat", user_id
    )
    api_key = provider_registry._decrypt_key(provider_orm)

    if provider_orm.provider_type == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_orm.model_id,
            api_key=api_key,
            base_url=provider_orm.base_url,
            temperature=AGENT_TEMPERATURE,
            max_tokens=AGENT_MAX_TOKENS,
            request_timeout=AGENT_REQUEST_TIMEOUT,
        )
    elif provider_orm.provider_type == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_orm.model_id,
            api_key=api_key,
            temperature=AGENT_TEMPERATURE,
            max_tokens=AGENT_MAX_TOKENS,
            timeout=float(AGENT_REQUEST_TIMEOUT),
        )
    elif provider_orm.provider_type == "ollama":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_orm.model_id,
            api_key=api_key or "ollama",
            base_url=provider_orm.base_url or "http://localhost:11434/v1",
            temperature=AGENT_TEMPERATURE,
            max_tokens=AGENT_MAX_TOKENS,
            request_timeout=AGENT_REQUEST_TIMEOUT,
        )
    else:
        raise ValueError(
            f"Unsupported provider type for LangChain adapter: "
            f"{provider_orm.provider_type}"
        )


def _count_tool_iterations(messages: list[BaseMessage]) -> int:
    """Count the number of tool call round-trips in the message history.

    Each AIMessage with tool_calls followed by tool responses constitutes
    one iteration. This prevents runaway ReAct loops.

    Args:
        messages: Current conversation messages.

    Returns:
        Number of tool call iterations completed so far.
    """
    count = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            count += 1
    return count


def _count_total_tool_calls(messages: list[BaseMessage]) -> int:
    """Count total individual tool calls across all messages.

    Unlike ``_count_tool_iterations`` which counts AIMessages, this counts
    the actual number of tool invocations. An AIMessage that batches 20
    tool_calls counts as 20 here, not 1.

    Args:
        messages: Current conversation messages.

    Returns:
        Total number of tool calls issued so far.
    """
    count = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            count += len(msg.tool_calls)
    return count


def build_agent_graph(
    tools: list,
    checkpointer: Any | None = None,
    provider_registry: Any | None = None,
    db_session_factory: Any | None = None,
) -> Any:
    """Build Blair's ReAct agent graph with human-in-the-loop support.

    Creates a compiled LangGraph StateGraph implementing the ReAct pattern:
    agent calls LLM -> LLM optionally returns tool_calls -> ToolNode
    executes tools -> results fed back to agent -> repeat until done.

    The graph uses an interrupt-before pattern on the tools node so that
    write operations can be confirmed by the user before execution
    (human-in-the-loop via CopilotKit).

    Args:
        tools: List of LangChain tool objects to bind to the agent.
        checkpointer: Optional LangGraph checkpointer for interrupt/resume.
            Required for human-in-the-loop (persists state across interrupts).
        provider_registry: ProviderRegistry instance for LLM calls.
            Used to resolve which provider (OpenAI/Anthropic/Ollama) and
            model to use, then construct the appropriate LangChain ChatModel.
        db_session_factory: Async session factory (async_sessionmaker) for
            DB access within the agent node. Each invocation opens a fresh
            session to resolve provider config.

    Returns:
        Compiled StateGraph ready for invocation via ``graph.ainvoke(state)``
        or ``graph.astream(state)``.
    """

    tool_node = ToolNode(tools)

    # Cache the resolved chat model and custom system prompt across ReAct
    # iterations within one graph invocation.
    _cached_chat_model: list[Any] = []  # mutable container for nonlocal
    _cached_system_prompt: list[str] = []  # mutable container for nonlocal

    async def agent_node(state: AgentState) -> dict[str, list[BaseMessage]]:
        """Invoke the LLM with the current messages and bound tools.

        Opens a fresh DB session to resolve the active provider config
        on the first call, then caches the model for subsequent ReAct
        iterations. Binds the available tools and invokes with the full
        conversation history (system prompt + user/assistant/tool messages).

        Args:
            state: Current agent state with messages and RBAC context.

        Returns:
            Dict with ``messages`` key containing the LLM's AIMessage
            response (which may include tool_calls for the ReAct loop).
        """
        # Check tool call limit to prevent cost explosion
        total_calls = _count_total_tool_calls(state["messages"])
        if total_calls >= MAX_TOOL_CALLS:
            logger.warning(
                "Agent hit max tool calls (%d/%d) for user %s, forcing stop",
                total_calls,
                MAX_TOOL_CALLS,
                state.get("user_id", "unknown"),
            )
            from ..telemetry import AITelemetry

            AITelemetry.log_tool_call(
                tool_name="__limit_reached__",
                user_id=state.get("user_id", ""),
                duration_ms=0,
                success=False,
                error=f"tool_call_limit_reached: {total_calls}",
            )
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I've reached the maximum number of operations for "
                            "this request. Here's what I found so far based on "
                            "the information gathered. Please try a more specific "
                            "question if you need additional details."
                        )
                    )
                ]
            }

        # Secondary safety: iteration count
        iteration_count = _count_tool_iterations(state["messages"])
        if iteration_count >= MAX_ITERATIONS:
            logger.warning(
                "Agent hit max iterations (%d) for user %s, forcing stop",
                MAX_ITERATIONS,
                state.get("user_id", "unknown"),
            )
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I've reached the maximum number of operations for "
                            "this request. Here's what I found so far based on "
                            "the information gathered. Please try a more specific "
                            "question if you need additional details."
                        )
                    )
                ]
            }

        # Resolve chat model and custom system prompt once per graph invocation
        if not _cached_chat_model:
            async with db_session_factory() as db:
                user_id_val = state.get("user_id")
                user_uuid = UUID(user_id_val) if user_id_val else None

                chat_model = await _get_langchain_chat_model(
                    provider_registry, db, user_uuid
                )

                # Query custom system prompt (fallback to hardcoded SYSTEM_PROMPT)
                try:
                    from sqlalchemy import select as sa_select
                    from ...models.ai_system_prompt import AiSystemPrompt

                    prompt_result = await db.execute(
                        sa_select(AiSystemPrompt).limit(1)
                    )
                    prompt_row = prompt_result.scalar_one_or_none()
                    if prompt_row and prompt_row.prompt:
                        _cached_system_prompt.append(prompt_row.prompt)
                    else:
                        _cached_system_prompt.append(SYSTEM_PROMPT)
                except Exception:
                    _cached_system_prompt.append(SYSTEM_PROMPT)

            _cached_chat_model.append(chat_model)

        # Bind tools to the chat model so it can generate tool_calls
        model_with_tools = _cached_chat_model[0].bind_tools(tools)

        # Build full message list: system prompt + conversation history
        effective_prompt = _cached_system_prompt[0] if _cached_system_prompt else SYSTEM_PROMPT
        messages = [SystemMessage(content=effective_prompt)] + list(
            state["messages"]
        )

        # Invoke the model
        response = await model_with_tools.ainvoke(messages)

        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        """Determine whether the agent should continue the ReAct loop.

        Checks the last message in the conversation. If it's an AIMessage
        with tool_calls, the loop continues to the tools node. Otherwise,
        the agent has produced a final response and the graph ends.

        Also enforces the MAX_ITERATIONS safety limit to prevent infinite
        loops in case of misbehaving tool call patterns.

        Args:
            state: Current agent state.

        Returns:
            ``"continue"`` to route to the tools node, or ``"end"`` to
            terminate the graph.
        """
        messages = state["messages"]
        if not messages:
            return "end"

        last_message = messages[-1]

        # Only continue if the last message is an AI message with tool calls
        if not isinstance(last_message, AIMessage):
            return "end"

        if not getattr(last_message, "tool_calls", None):
            return "end"

        # Safety: check total tool call count (primary limit)
        total_calls = _count_total_tool_calls(messages)
        if total_calls >= MAX_TOOL_CALLS:
            logger.warning(
                "should_continue: tool call limit reached (%d/%d), ending",
                total_calls,
                MAX_TOOL_CALLS,
            )
            return "end"

        # Secondary safety: iteration count
        iteration_count = _count_tool_iterations(messages)
        if iteration_count >= MAX_ITERATIONS:
            logger.warning(
                "should_continue: iteration limit reached (%d), ending",
                iteration_count,
            )
            return "end"

        return "continue"

    # Build the state graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    # Set entry point
    graph.set_entry_point("agent")

    # Add conditional edges from agent
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END,
        },
    )

    # Tools always route back to agent for the next ReAct iteration
    graph.add_edge("tools", "agent")

    # Compile with optional checkpointer for interrupt/resume support
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info(
        "Agent graph compiled with %d tools, checkpointer=%s",
        len(tools),
        type(checkpointer).__name__ if checkpointer else "None",
    )

    return compiled

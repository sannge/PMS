"""AI chat API endpoints (Phase 4 LangGraph agent).

Provides streaming and non-streaming chat with Blair, the PM Desktop
AI copilot.  Also exposes time-travel endpoints (checkpoint history
and replay), a HITL resume endpoint, and an optional CopilotKit AG-UI
runtime.

All endpoints require JWT authentication.
"""

from __future__ import annotations

import base64
import json
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session_maker, get_db
from ..models.user import User
from ..schemas.ai_chat import (
    ChatImageAttachment,
    ChatRequest,
    ChatResponse,
    CheckpointSummary,
    ReplayRequest,
    ResumeRequest,
)
from ..ai.rate_limiter import check_chat_rate_limit
from ..ai.telemetry import AITelemetry, TelemetryTimer
from ..services.auth_service import get_current_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_IMAGES = 5
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB decoded
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# ---------------------------------------------------------------------------
# Thread ownership tracking (H4 — prevent IDOR)
# ---------------------------------------------------------------------------
# Maps thread_id -> user_id string.  Set when a thread is created in
# chat / chat_stream, checked in history / replay / resume endpoints.
# Sufficient for single-process deployments; a proper DB-backed table
# should replace this in production multi-worker setups.


class _BoundedThreadOwners(OrderedDict):
    """Thread ownership store with max-size eviction (FIFO).

    Single-process only. For multi-worker deployments, replace with
    Redis-backed storage (key: f"thread_owner:{thread_id}", TTL: 86400).
    """

    MAX_SIZE = 100_000

    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key, value)
        if len(self) > self.MAX_SIZE:
            self.popitem(last=False)  # evict oldest


_thread_owners: _BoundedThreadOwners = _BoundedThreadOwners()


def _register_thread(thread_id: str, user_id: str) -> None:
    """Record the owner of a thread."""
    _thread_owners[thread_id] = user_id


def _validate_thread_owner(thread_id: str, user_id: str) -> None:
    """Raise 403 if *thread_id* does not belong to *user_id*.

    Threads that have no recorded owner (e.g. created before this check
    was added) are allowed through to avoid breaking existing sessions.
    """
    owner = _thread_owners.get(thread_id)
    if owner is not None and owner != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Thread does not belong to the current user",
        )

# ---------------------------------------------------------------------------
# Database session factory for agent tools
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_tool_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an independent database session for agent tool execution.

    Agent tools run inside the LangGraph tool node which is separate from the
    request's ``Depends(get_db)`` session.  Using the factory ensures each
    tool call gets its own session lifecycle (auto-commit / rollback).
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_images(images: list[ChatImageAttachment]) -> None:
    """Validate image attachments before passing to the agent.

    Raises:
        HTTPException: If any constraint is violated.
    """
    if len(images) > MAX_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Too many images (max {MAX_IMAGES})",
        )
    for img in images:
        if img.media_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported image type: {img.media_type}",
            )
        try:
            decoded = base64.b64decode(img.data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid base64 image data",
            )
        if len(decoded) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Image too large (max 10 MB)",
            )


# ---------------------------------------------------------------------------
# Message conversion helpers
# ---------------------------------------------------------------------------


def _history_to_langchain_messages(
    history: list[Any],
) -> list[Any]:
    """Convert conversation_history entries to LangChain message objects.

    Each entry is a ``ChatHistoryEntry`` with ``role`` ("user" | "assistant")
    and ``content`` (str) attributes.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    messages: list[Any] = []
    for entry in history:
        role = entry.role if hasattr(entry, "role") else entry.get("role", "user")
        content = entry.content if hasattr(entry, "content") else entry.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _build_human_message(
    text: str,
    images: list[ChatImageAttachment],
) -> Any:
    """Build a LangChain ``HumanMessage``, optionally multimodal.

    When images are present the message uses the OpenAI-style content
    block format which the provider adapters translate to
    provider-specific payloads.
    """
    from langchain_core.messages import HumanMessage

    if not images:
        return HumanMessage(content=text)

    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for img in images:
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img.media_type};base64,{img.data}"
                },
            }
        )
    return HumanMessage(content=content_blocks)


def _extract_tool_calls(messages: list[Any]) -> list[dict]:
    """Walk messages and collect tool-call metadata for the response."""
    tool_calls: list[dict] = []
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    {
                        "tool": tc.get("name", "unknown"),
                        "args": tc.get("args", {}),
                    }
                )
    return tool_calls


def _extract_sources(messages: list[Any]) -> list[dict]:
    """Extract structured source references from tool messages.

    Source references are attached as ``metadata["sources"]`` on tool
    result messages by the ``query_knowledge`` and similar tools.
    """
    sources: list[dict] = []
    for msg in messages:
        if hasattr(msg, "additional_kwargs"):
            msg_sources = msg.additional_kwargs.get("sources")
            if msg_sources and isinstance(msg_sources, list):
                sources.extend(msg_sources)
    return sources


# ---------------------------------------------------------------------------
# Agent setup and response helpers (Fix 5 & Fix 6)
# ---------------------------------------------------------------------------


async def _setup_agent_context(
    current_user: User,
    db: AsyncSession,
) -> tuple[Any, dict[str, Any]]:
    """Build RBAC context, set tool context, and compile agent graph.

    Returns (graph, context).
    Caller must call clear_tool_context() in a finally block.
    """
    from ..ai.agent.graph import build_agent_graph, get_checkpointer
    from ..ai.agent.rbac_context import AgentRBACContext
    from ..ai.agent.tools_read import create_read_tools, set_tool_context
    from ..ai.agent.tools_write import WRITE_TOOLS
    from ..ai.provider_registry import ProviderRegistry

    context = await AgentRBACContext.build_agent_context(str(current_user.id), db)
    registry = ProviderRegistry()
    set_tool_context(
        user_id=str(current_user.id),
        accessible_app_ids=context["accessible_app_ids"],
        accessible_project_ids=context["accessible_project_ids"],
        db_session_factory=get_tool_db,
        provider_registry=registry,
    )
    read_tools = create_read_tools(db_session_factory=get_tool_db, provider_registry=registry)
    all_tools = read_tools + WRITE_TOOLS
    graph = build_agent_graph(
        tools=all_tools,
        checkpointer=get_checkpointer(),
        provider_registry=registry,
        db_session_factory=get_tool_db,
    )
    return graph, context


def _build_chat_response(
    result_messages: list,
    thread_id: str,
    interrupted: bool = False,
    interrupt_payload: dict | None = None,
) -> ChatResponse:
    """Extract response text, tool calls, and sources from agent result messages."""
    if not result_messages:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent returned no messages.",
        )

    last_msg = result_messages[-1]
    response_text = ""
    if hasattr(last_msg, "content"):
        content = last_msg.content
        if isinstance(content, str):
            response_text = content
        elif isinstance(content, list):
            response_text = " ".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )

    return ChatResponse(
        response=response_text,
        tool_calls=_extract_tool_calls(result_messages),
        thread_id=thread_id,
        sources=_extract_sources(result_messages),
        interrupted=interrupted,
        interrupt_payload=interrupt_payload,
    )


# ---------------------------------------------------------------------------
# Streaming helper (H5 + H6: AG-UI events and error sanitisation)
# ---------------------------------------------------------------------------


async def _stream_agent(
    graph: Any,
    state: dict,
    config: dict,
    thread_id: str = "",
) -> AsyncGenerator[dict, None]:
    """Async generator that streams LangGraph agent events as SSE payloads.

    Each yielded dict has ``event`` (SSE event name) and ``data`` (JSON
    string) matching the AG-UI event vocabulary.

    Emitted events:
        run_started, text_delta, tool_call_start, tool_call_end,
        interrupt, run_finished, end, error.

    Args:
        graph: Compiled LangGraph agent graph.
        state: Initial agent state dict.
        config: LangGraph config dict (must include ``configurable.thread_id``).
        thread_id: Thread ID to include in ``run_started`` event.
    """
    import time as _time

    yield {"event": "run_started", "data": json.dumps({"thread_id": thread_id})}

    interrupted = False
    # Track tool call start times for telemetry
    _tool_starts: dict[str, float] = {}  # run_id -> start_time
    _user_id_for_telemetry = state.get("user_id", "")

    try:
        async for event in graph.astream_events(state, config=config, version="v2"):
            event_kind: str = event["event"]

            if event_kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk is not None and hasattr(chunk, "content") and chunk.content:
                    yield {
                        "event": "text_delta",
                        "data": json.dumps({"content": chunk.content}),
                    }

            elif event_kind == "on_tool_start":
                run_id = event.get("run_id", "")
                _tool_starts[run_id] = _time.monotonic()
                yield {
                    "event": "tool_call_start",
                    "data": json.dumps({"tool": event.get("name", "unknown")}),
                }

            elif event_kind == "on_tool_end":
                output = event.get("data", {}).get("output", "")
                tool_name = event.get("name", "unknown")
                run_id = event.get("run_id", "")
                # Calculate tool duration
                start_ts = _tool_starts.pop(run_id, None)
                tool_duration = int((_time.monotonic() - start_ts) * 1000) if start_ts else 0
                # Telemetry: log individual tool call
                try:
                    await AITelemetry.log_tool_call(
                        tool_name=tool_name,
                        user_id=_user_id_for_telemetry,
                        duration_ms=tool_duration,
                        success=True,
                    )
                except Exception:
                    pass  # Non-critical
                # Extract structured sources from tool result metadata
                sources: list[dict] = []
                raw_output = event.get("data", {}).get("output")
                if hasattr(raw_output, "additional_kwargs"):
                    msg_sources = raw_output.additional_kwargs.get("sources")
                    if msg_sources and isinstance(msg_sources, list):
                        sources = msg_sources
                yield {
                    "event": "tool_call_end",
                    "data": json.dumps(
                        {
                            "tool": tool_name,
                            "result": str(output),
                            **({"sources": sources} if sources else {}),
                        }
                    ),
                }

    except Exception as e:
        logger.exception("Stream error: %s", e)
        yield {"event": "error", "data": json.dumps({"message": "Agent encountered an error."})}

    # Check for interrupt state after stream completes
    try:
        graph_state = await graph.aget_state(config)
        if graph_state and getattr(graph_state, "next", None):
            interrupted = True
            # Extract the interrupt payload from pending tasks
            interrupt_payload: dict[str, Any] = {"thread_id": thread_id}
            tasks = getattr(graph_state, "tasks", None)
            if tasks:
                for t in tasks:
                    interrupts = getattr(t, "interrupts", None)
                    if interrupts:
                        for intr in interrupts:
                            value = getattr(intr, "value", None)
                            if isinstance(value, dict):
                                interrupt_payload.update(value)
                                break
                        if len(interrupt_payload) > 1:
                            break
            yield {
                "event": "interrupt",
                "data": json.dumps(interrupt_payload),
            }
    except Exception:
        logger.debug("Could not check interrupt state after stream", exc_info=True)

    yield {"event": "run_finished", "data": json.dumps({"interrupted": interrupted})}
    yield {"event": "end", "data": "{}"}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/ai",
    tags=["ai-chat"],
)

# ---------------------------------------------------------------------------
# POST /api/ai/chat  --  Non-streaming chat
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(check_chat_rate_limit),
) -> ChatResponse:
    """Non-streaming chat endpoint.

    Builds the RBAC context, configures the agent tools, runs the
    LangGraph agent to completion, and returns the final response.
    """
    from ..ai.agent.tools_read import clear_tool_context

    # 1. Validate images
    _validate_images(request.images)

    # 2. Setup agent context (RBAC, tools, graph)
    graph, context = await _setup_agent_context(current_user, db)

    try:
        # 3. Build messages
        messages = _history_to_langchain_messages(request.conversation_history)
        human_msg = _build_human_message(request.message, request.images)
        messages.append(human_msg)

        # 4. Build initial state and config
        thread_id = request.thread_id or str(uuid4())
        if request.thread_id:
            _validate_thread_owner(thread_id, str(current_user.id))
        _register_thread(thread_id, str(current_user.id))
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

        state: dict[str, Any] = {
            "messages": messages,
            "user_id": str(current_user.id),
            "accessible_app_ids": context["accessible_app_ids"],
            "accessible_project_ids": context["accessible_project_ids"],
        }

        # 5. Run graph to completion
        timer = TelemetryTimer().start()
        try:
            result = await graph.ainvoke(state, config=config)
        except Exception:
            logger.exception("Agent graph execution failed for user %s", current_user.id)
            await AITelemetry.log_chat_request(
                user_id=current_user.id,
                provider="unknown",
                model="unknown",
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                duration_ms=timer.elapsed_ms,
                success=False,
                error="Agent execution failed",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Agent execution failed. Please try again.",
            )
    finally:
        clear_tool_context()

    # 6. Extract response
    result_messages = result.get("messages", [])

    # Extract token usage from result messages for telemetry
    _input_tokens = 0
    _output_tokens = 0
    _provider_name = "unknown"
    _model_name = "unknown"
    for msg in result_messages:
        usage = getattr(msg, "usage_metadata", None)
        if usage and isinstance(usage, dict):
            _input_tokens += usage.get("input_tokens", 0)
            _output_tokens += usage.get("output_tokens", 0)
        resp_meta = getattr(msg, "response_metadata", None)
        if resp_meta and isinstance(resp_meta, dict):
            if resp_meta.get("model_name"):
                _model_name = resp_meta["model_name"]

    await AITelemetry.log_chat_request(
        user_id=current_user.id,
        provider=_provider_name,
        model=_model_name,
        input_tokens=_input_tokens,
        output_tokens=_output_tokens,
        tool_calls=len(_extract_tool_calls(result_messages)),
        duration_ms=timer.elapsed_ms,
        success=True,
    )

    # Check for interrupt state (HITL)
    interrupted = False
    interrupt_payload: dict | None = None
    try:
        graph_state = await graph.aget_state(config)
        if graph_state and getattr(graph_state, "next", None):
            interrupted = True
            tasks = getattr(graph_state, "tasks", None)
            if tasks:
                interrupt_payload = {"pending_tasks": [str(t) for t in tasks]}
    except Exception:
        pass  # Non-critical — don't fail the response

    return _build_chat_response(
        result_messages,
        thread_id,
        interrupted=interrupted,
        interrupt_payload=interrupt_payload,
    )


# ---------------------------------------------------------------------------
# POST /api/ai/chat/stream  --  SSE streaming chat
# ---------------------------------------------------------------------------


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(check_chat_rate_limit),
) -> Any:
    """SSE streaming chat endpoint.

    Returns an ``EventSourceResponse`` that streams AG-UI compatible
    events (text_delta, tool_call_start, tool_call_end, run_started,
    run_finished, end) as the agent executes.
    """
    from sse_starlette.sse import EventSourceResponse

    from ..ai.agent.tools_read import clear_tool_context

    # 1. Validate images
    _validate_images(request.images)

    # 2. Setup agent context (RBAC, tools, graph)
    graph, context = await _setup_agent_context(current_user, db)

    # C3: wrap message/state building in try/finally so context is cleared on setup failure
    try:
        # 3. Build messages
        messages = _history_to_langchain_messages(request.conversation_history)
        human_msg = _build_human_message(request.message, request.images)
        messages.append(human_msg)

        # 4. Build initial state and config
        thread_id = request.thread_id or str(uuid4())
        if request.thread_id:
            _validate_thread_owner(thread_id, str(current_user.id))
        _register_thread(thread_id, str(current_user.id))
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

        state: dict[str, Any] = {
            "messages": messages,
            "user_id": str(current_user.id),
            "accessible_app_ids": context["accessible_app_ids"],
            "accessible_project_ids": context["accessible_project_ids"],
        }
    except Exception:
        clear_tool_context()
        raise

    # 5. Return SSE stream (cleanup in generator)
    async def _guarded_stream() -> AsyncGenerator[dict, None]:
        try:
            async for event in _stream_agent(graph, state, config, thread_id=thread_id):
                yield event
        finally:
            clear_tool_context()

    return EventSourceResponse(
        _guarded_stream(),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# POST /api/ai/chat/resume  --  HITL resume (H2)
# ---------------------------------------------------------------------------


@router.post("/chat/resume", response_model=ChatResponse)
async def resume_chat(
    request: ResumeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Resume a conversation after a human-in-the-loop interrupt.

    When a write tool calls ``interrupt()``, the agent pauses and the
    frontend receives an interrupt event.  This endpoint accepts the
    user's approval/rejection and resumes the agent from the
    interrupted checkpoint.

    Args:
        request: Contains thread_id and user response payload.
        current_user: Authenticated user (JWT).
        db: Database session.

    Returns:
        ChatResponse with the agent's post-resume reply.
    """
    from ..ai.agent.graph import get_checkpointer
    from ..ai.agent.tools_read import clear_tool_context

    # Validate thread ownership
    _validate_thread_owner(request.thread_id, str(current_user.id))

    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Checkpointer not configured — HITL resume unavailable",
        )

    # Setup agent context (RBAC, tools, graph)
    graph, _context = await _setup_agent_context(current_user, db)

    try:
        config: dict[str, Any] = {
            "configurable": {"thread_id": request.thread_id}
        }

        try:
            result = await graph.ainvoke(
                Command(resume=request.response), config=config
            )
        except Exception:
            logger.exception(
                "Agent resume failed for user %s, thread %s",
                current_user.id,
                request.thread_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Agent resume failed. Please try again.",
            )
    finally:
        clear_tool_context()

    # Extract response
    result_messages = result.get("messages", [])
    return _build_chat_response(result_messages, request.thread_id)


# ---------------------------------------------------------------------------
# GET /api/ai/chat/history/{thread_id}  --  Checkpoint timeline
# ---------------------------------------------------------------------------


@router.get("/chat/history/{thread_id}")
async def get_conversation_history(
    thread_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, list[CheckpointSummary]]:
    """List user-visible checkpoints for a conversation thread.

    Returns only checkpoints produced by the ``agent`` node (i.e.
    after LLM responses), not internal tool execution checkpoints.
    This powers the time-travel / rewind UI.
    """
    from ..ai.agent.graph import get_checkpointer  # noqa: F811

    # H4: validate thread ownership
    _validate_thread_owner(thread_id, str(current_user.id))

    checkpointer = get_checkpointer()
    if checkpointer is None:
        return {"checkpoints": []}

    checkpoints: list[CheckpointSummary] = []
    config = {"configurable": {"thread_id": thread_id}}

    async for cp_tuple in checkpointer.alist(config):
        cp = cp_tuple.checkpoint
        metadata = cp_tuple.metadata or {}
        node = metadata.get("source", "unknown")
        channel_values = cp.get("channel_values", {})
        message_count = len(channel_values.get("messages", []))

        checkpoints.append(
            CheckpointSummary(
                checkpoint_id=cp["id"],
                thread_id=thread_id,
                timestamp=cp.get("ts", ""),
                node=node,
                message_count=message_count,
            )
        )

    # Filter to user-visible turns
    visible = [
        cp
        for cp in checkpoints
        if cp.node == "agent" and cp.message_count > 0
    ]
    return {"checkpoints": visible}


# ---------------------------------------------------------------------------
# POST /api/ai/chat/replay  --  Replay from checkpoint
# ---------------------------------------------------------------------------


@router.post("/chat/replay")
async def replay_conversation(
    request: ReplayRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Replay a conversation from a previous checkpoint.

    If ``message`` is provided the conversation branches from the
    checkpoint with the new user message (creating a new thread).
    If omitted, the endpoint returns the agent state at the checkpoint
    (for preview).

    Returns an ``EventSourceResponse`` that streams the replayed
    execution.
    """
    from langchain_core.messages import HumanMessage
    from sse_starlette.sse import EventSourceResponse

    from ..ai.agent.graph import get_checkpointer
    from ..ai.agent.tools_read import clear_tool_context

    # H4: validate thread ownership
    _validate_thread_owner(request.thread_id, str(current_user.id))

    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Checkpointer not configured — time-travel unavailable",
        )

    # Setup agent context (RBAC, tools, graph)
    graph, context = await _setup_agent_context(current_user, db)

    if request.message:
        # H8: branch — create a new thread_id for the replayed conversation
        # NOTE: Do NOT wrap the streaming return in try/finally — the
        # generator's own finally handles cleanup. Matching chat_stream pattern.
        try:
            branch_thread_id = str(uuid4())
            _register_thread(branch_thread_id, str(current_user.id))
            branch_config: dict[str, Any] = {
                "configurable": {
                    "thread_id": branch_thread_id,
                    "checkpoint_id": request.checkpoint_id,
                }
            }

            input_state: dict[str, Any] = {
                "messages": [HumanMessage(content=request.message)],
                "user_id": str(current_user.id),
                "accessible_app_ids": context["accessible_app_ids"],
                "accessible_project_ids": context["accessible_project_ids"],
            }
        except Exception:
            clear_tool_context()
            raise

        async def _guarded_replay() -> AsyncGenerator[dict, None]:
            try:
                async for event in _stream_agent(
                    graph, input_state, branch_config,
                    thread_id=branch_thread_id,
                ):
                    yield event
            finally:
                clear_tool_context()

        return EventSourceResponse(
            _guarded_replay(),
            media_type="text/event-stream",
        )
    else:
        # Preview: return the state at the checkpoint
        config: dict[str, Any] = {
            "configurable": {
                "thread_id": request.thread_id,
                "checkpoint_id": request.checkpoint_id,
            }
        }
        try:
            state = await graph.aget_state(config)
            if state is None or not state.values:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Checkpoint not found",
                )
            msgs = state.values.get("messages", [])
            return {
                "thread_id": request.thread_id,
                "checkpoint_id": request.checkpoint_id,
                "message_count": len(msgs),
                "messages": [
                    {
                        "role": (
                            "assistant" if hasattr(m, "type") and m.type == "ai" else "user"
                        ),
                        "content": m.content if hasattr(m, "content") else str(m),
                    }
                    for m in msgs
                ],
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("Replay preview failed")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Checkpoint not found or invalid",
            )
        finally:
            clear_tool_context()

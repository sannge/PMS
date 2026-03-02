"""AI chat API endpoints (Phase 4 LangGraph agent).

Provides streaming and non-streaming chat with Blair, the PM Desktop
AI copilot.  Also exposes time-travel endpoints (checkpoint history
and replay), a HITL resume endpoint, and an optional CopilotKit AG-UI
runtime.

All endpoints require JWT authentication.
"""

from __future__ import annotations

import asyncio
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

from ..database import async_session_maker
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

# Streaming safety limits
STREAM_OVERALL_TIMEOUT_S = 120  # Max total stream duration
STREAM_IDLE_TIMEOUT_S = 30  # Max gap between chunks
MAX_CHUNKS_PER_RESPONSE = 2000  # ~32KB at avg 16 bytes/chunk

# ---------------------------------------------------------------------------
# Thread ownership tracking (H4 — prevent IDOR)
# ---------------------------------------------------------------------------
# Redis-backed storage: key "thread_owner:{thread_id}" -> user_id string.
# Falls back to in-memory OrderedDict when Redis is unavailable.
# NOTE: In-memory fallback is per-process. Multi-worker deployments MUST have
# Redis available for thread ownership to work across workers. When Redis is
# down, cross-worker requests to foreign threads are allowed through (fail-open)
# to avoid breaking existing sessions.

_THREAD_OWNER_TTL = 86400  # 24 hours

# In-memory fallback (used only when Redis is down)
_thread_owners_fallback: OrderedDict[str, str] = OrderedDict()
_FALLBACK_MAX_SIZE = 100_000


async def _register_thread(thread_id: str, user_id: str) -> None:
    """Record the owner of a thread in Redis (with in-memory fallback)."""
    from ..services.redis_service import redis_service

    try:
        if redis_service.is_connected:
            await redis_service.set(
                f"thread_owner:{thread_id}", user_id, ttl=_THREAD_OWNER_TTL
            )
            return
    except Exception:
        pass  # Fall through to in-memory

    _thread_owners_fallback[thread_id] = user_id
    if len(_thread_owners_fallback) > _FALLBACK_MAX_SIZE:
        _thread_owners_fallback.popitem(last=False)


async def _validate_thread_owner(thread_id: str, user_id: str) -> None:
    """Raise 403 if *thread_id* does not belong to *user_id*.

    Threads that have no recorded owner (e.g. created before this check
    was added, or Redis was unavailable) are allowed through to avoid
    breaking existing sessions.
    """
    from ..services.redis_service import redis_service

    owner: str | None = None
    try:
        if redis_service.is_connected:
            owner = await redis_service.get(f"thread_owner:{thread_id}")
    except Exception:
        pass  # Fall through to in-memory

    if owner is None:
        owner = _thread_owners_fallback.get(thread_id)

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

    Agent tools run inside the LangGraph tool node which is separate from
    the request lifecycle.  Using the factory ensures each tool call gets
    its own session lifecycle (auto-commit / rollback).
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
) -> tuple[Any, dict[str, Any]]:
    """Build RBAC context, set tool context, and compile agent graph.

    Opens a short-lived DB session for the RBAC query only, then releases
    the connection back to the pool before returning.  This prevents
    holding a connection idle for the entire agent execution (~120 s).

    Returns (graph, context).
    Caller must call clear_tool_context() in a finally block.
    """
    from ..ai.agent.graph import build_agent_graph, get_checkpointer
    from ..ai.agent.rbac_context import AgentRBACContext
    from ..ai.agent.tools_read import create_read_tools, set_tool_context
    from ..ai.agent.tools_write import WRITE_TOOLS
    from ..ai.provider_registry import ProviderRegistry

    async with async_session_maker() as db:
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

    from app.ai.agent.source_references import reset_source_accumulator, get_accumulated_sources

    yield {"event": "run_started", "data": json.dumps({"thread_id": thread_id})}

    interrupted = False
    # Initialize per-request source accumulator (ContextVar).
    # Tool functions push sources here; we read them after the run completes.
    reset_source_accumulator()
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
                    "data": json.dumps({
                        "id": run_id,
                        "name": event.get("name", "unknown"),
                    }),
                }

            elif event_kind == "on_tool_end":
                raw_output = event.get("data", {}).get("output")
                # Extract text content — ToolMessage has .content, otherwise str()
                if hasattr(raw_output, "content"):
                    output_text = str(raw_output.content)
                elif isinstance(raw_output, str):
                    output_text = raw_output
                else:
                    output_text = str(raw_output) if raw_output else ""
                tool_name = event.get("name", "unknown")
                run_id = event.get("run_id", "")
                is_error = output_text.lower().startswith("error") or "failed" in output_text.lower()
                # Calculate tool duration
                start_ts = _tool_starts.pop(run_id, None)
                tool_duration = int((_time.monotonic() - start_ts) * 1000) if start_ts else 0
                # Telemetry: log individual tool call
                try:
                    AITelemetry.log_tool_call(
                        tool_name=tool_name,
                        user_id=_user_id_for_telemetry,
                        duration_ms=tool_duration,
                        success=not is_error,
                    )
                except Exception:
                    pass  # Non-critical
                yield {
                    "event": "tool_call_end",
                    "data": json.dumps(
                        {
                            "id": run_id,
                            "name": tool_name,
                            "summary": output_text[:200] if output_text else "",
                            "details": output_text if output_text else "",
                            **({"error": output_text} if is_error else {}),
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

    # Extract checkpoint_id for rewind/time-travel feature
    checkpoint_id: str | None = None
    try:
        if graph_state:
            config_val = getattr(graph_state, "config", {})
            configurable = config_val.get("configurable", {}) if isinstance(config_val, dict) else {}
            checkpoint_id = configurable.get("checkpoint_id")
    except Exception:
        pass

    yield {
        "event": "run_finished",
        "data": json.dumps({
            "interrupted": interrupted,
            "sources": get_accumulated_sources(),
            **({"checkpoint_id": checkpoint_id} if checkpoint_id else {}),
        }),
    }
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
    graph, context = await _setup_agent_context(current_user)

    try:
        # 3. Build messages
        messages = _history_to_langchain_messages(request.conversation_history)
        human_msg = _build_human_message(request.message, request.images)
        messages.append(human_msg)

        # 4. Build initial state and config
        thread_id = request.thread_id or str(uuid4())
        if request.thread_id:
            await _validate_thread_owner(thread_id, str(current_user.id))
        await _register_thread(thread_id, str(current_user.id))
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

        state: dict[str, Any] = {
            "messages": messages,
            "user_id": str(current_user.id),
            "accessible_app_ids": context["accessible_app_ids"],
            "accessible_project_ids": context["accessible_project_ids"],
        }

        # 5. Run graph to completion (with timeout)
        timer = TelemetryTimer().start()
        try:
            async with asyncio.timeout(STREAM_OVERALL_TIMEOUT_S):
                result = await graph.ainvoke(state, config=config)
        except TimeoutError:
            logger.warning(
                "Agent graph timed out (%ds) for user %s",
                STREAM_OVERALL_TIMEOUT_S,
                current_user.id,
            )
            AITelemetry.log_chat_request(
                user_id=current_user.id,
                provider="unknown",
                model="unknown",
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                duration_ms=timer.elapsed_ms,
                success=False,
                error="Agent execution timed out",
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Agent response timed out. Please try again.",
            )
        except Exception:
            logger.exception("Agent graph execution failed for user %s", current_user.id)
            AITelemetry.log_chat_request(
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

    AITelemetry.log_chat_request(
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
    graph, context = await _setup_agent_context(current_user)

    # C3: wrap message/state building in try/finally so context is cleared on setup failure
    try:
        # 3. Build messages
        messages = _history_to_langchain_messages(request.conversation_history)
        human_msg = _build_human_message(request.message, request.images)
        messages.append(human_msg)

        # 4. Build initial state and config
        thread_id = request.thread_id or str(uuid4())
        if request.thread_id:
            await _validate_thread_owner(thread_id, str(current_user.id))
        await _register_thread(thread_id, str(current_user.id))
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

    # 5. Return SSE stream (cleanup in generator) with timeout + chunk limit
    async def _guarded_stream() -> AsyncGenerator[dict, None]:
        chunk_count = 0
        aiter_stream = _stream_agent(graph, state, config, thread_id=thread_id).__aiter__()

        try:
            async with asyncio.timeout(STREAM_OVERALL_TIMEOUT_S):
                while True:
                    try:
                        event = await asyncio.wait_for(
                            anext(aiter_stream),
                            timeout=STREAM_IDLE_TIMEOUT_S,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Stream idle timeout (%ds) for user %s, thread %s",
                            STREAM_IDLE_TIMEOUT_S,
                            current_user.id,
                            thread_id,
                        )
                        yield {
                            "event": "error",
                            "data": json.dumps(
                                {"message": "Stream timeout — response took too long"}
                            ),
                        }
                        return

                    # Chunk limit check
                    chunk_count += 1
                    if chunk_count > MAX_CHUNKS_PER_RESPONSE:
                        logger.warning(
                            "Stream chunk limit (%d) exceeded for user %s, thread %s",
                            MAX_CHUNKS_PER_RESPONSE,
                            current_user.id,
                            thread_id,
                        )
                        yield {
                            "event": "error",
                            "data": json.dumps(
                                {"message": "Response exceeded maximum size"}
                            ),
                        }
                        return

                    yield event
        except TimeoutError:
            logger.warning(
                "Stream overall timeout (%ds) for user %s, thread %s",
                STREAM_OVERALL_TIMEOUT_S,
                current_user.id,
                thread_id,
            )
            yield {
                "event": "error",
                "data": json.dumps(
                    {"message": "Stream timeout — response took too long"}
                ),
            }
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
    _rate_limit: None = Depends(check_chat_rate_limit),
) -> Any:
    """Resume a conversation after a human-in-the-loop interrupt.

    When a write tool calls ``interrupt()``, the agent pauses and the
    frontend receives an interrupt event.  This endpoint accepts the
    user's approval/rejection and resumes the agent from the
    interrupted checkpoint.

    Args:
        request: Contains thread_id and user response payload.
        current_user: Authenticated user (JWT).

    Returns:
        ChatResponse with the agent's post-resume reply.
    """
    from ..ai.agent.graph import get_checkpointer
    from ..ai.agent.tools_read import clear_tool_context

    # Validate thread ownership
    await _validate_thread_owner(request.thread_id, str(current_user.id))

    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Checkpointer not configured — HITL resume unavailable",
        )

    # Setup agent context (RBAC, tools, graph)
    graph, _context = await _setup_agent_context(current_user)

    try:
        timer = TelemetryTimer().start()
        config: dict[str, Any] = {
            "configurable": {"thread_id": request.thread_id}
        }

        try:
            async with asyncio.timeout(STREAM_OVERALL_TIMEOUT_S):
                result = await graph.ainvoke(
                    Command(resume=request.response), config=config
                )
        except TimeoutError:
            logger.warning(
                "Agent resume timed out (%ds) for user %s, thread %s",
                STREAM_OVERALL_TIMEOUT_S,
                current_user.id,
                request.thread_id,
            )
            AITelemetry.log_chat_request(
                user_id=current_user.id,
                provider="unknown",
                model="unknown",
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                duration_ms=timer.elapsed_ms,
                success=False,
                error="Agent resume timed out",
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Agent response timed out. Please try again.",
            )
        except Exception:
            logger.exception(
                "Agent resume failed for user %s, thread %s",
                current_user.id,
                request.thread_id,
            )
            AITelemetry.log_chat_request(
                user_id=current_user.id,
                provider="unknown",
                model="unknown",
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                duration_ms=timer.elapsed_ms,
                success=False,
                error="Agent resume failed",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Agent resume failed. Please try again.",
            )
    finally:
        clear_tool_context()

    # Extract response and log success telemetry
    result_messages = result.get("messages", [])

    _input_tokens = 0
    _output_tokens = 0
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

    AITelemetry.log_chat_request(
        user_id=current_user.id,
        provider="unknown",
        model=_model_name,
        input_tokens=_input_tokens,
        output_tokens=_output_tokens,
        tool_calls=len(_extract_tool_calls(result_messages)),
        duration_ms=timer.elapsed_ms,
        success=True,
    )

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
    from ..ai.agent.graph import get_checkpointer

    # H4: validate thread ownership
    await _validate_thread_owner(thread_id, str(current_user.id))

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
    _rate_limit: None = Depends(check_chat_rate_limit),
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
    await _validate_thread_owner(request.thread_id, str(current_user.id))

    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Checkpointer not configured — time-travel unavailable",
        )

    # Setup agent context (RBAC, tools, graph)
    graph, context = await _setup_agent_context(current_user)

    if request.message:
        # H8: branch — create a new thread_id for the replayed conversation
        # NOTE: Do NOT wrap the streaming return in try/finally — the
        # generator's own finally handles cleanup. Matching chat_stream pattern.
        try:
            branch_thread_id = str(uuid4())
            await _register_thread(branch_thread_id, str(current_user.id))
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
            chunk_count = 0
            aiter_stream = _stream_agent(
                graph, input_state, branch_config,
                thread_id=branch_thread_id,
            ).__aiter__()

            try:
                async with asyncio.timeout(STREAM_OVERALL_TIMEOUT_S):
                    while True:
                        try:
                            event = await asyncio.wait_for(
                                anext(aiter_stream),
                                timeout=STREAM_IDLE_TIMEOUT_S,
                            )
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            logger.warning(
                                "Replay idle timeout (%ds) for user %s, thread %s",
                                STREAM_IDLE_TIMEOUT_S,
                                current_user.id,
                                branch_thread_id,
                            )
                            yield {
                                "event": "error",
                                "data": json.dumps(
                                    {"message": "Stream timeout — response took too long"}
                                ),
                            }
                            return

                        chunk_count += 1
                        if chunk_count > MAX_CHUNKS_PER_RESPONSE:
                            logger.warning(
                                "Replay chunk limit (%d) for user %s, thread %s",
                                MAX_CHUNKS_PER_RESPONSE,
                                current_user.id,
                                branch_thread_id,
                            )
                            yield {
                                "event": "error",
                                "data": json.dumps(
                                    {"message": "Response exceeded maximum size"}
                                ),
                            }
                            return

                        yield event
            except TimeoutError:
                logger.warning(
                    "Replay overall timeout (%ds) for user %s, thread %s",
                    STREAM_OVERALL_TIMEOUT_S,
                    current_user.id,
                    branch_thread_id,
                )
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"message": "Stream timeout — response took too long"}
                    ),
                }
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

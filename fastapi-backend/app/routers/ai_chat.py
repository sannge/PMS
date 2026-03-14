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
import time as _time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session_maker
from ..models.user import User
from ..schemas.ai_chat import (
    ChatHistoryEntry,
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

from ..ai.config_service import get_agent_config

_cfg = get_agent_config()

# NOTE: These values are read once at import time and do NOT change at runtime.
# Changing these config keys requires a process/worker restart to take effect.
MAX_IMAGES = _cfg.get_int("file.max_chat_images", 5)
MAX_IMAGE_SIZE = _cfg.get_int("file.max_image_size", 10 * 1024 * 1024)  # 10 MB decoded
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# NOTE: These values are read once at import time and do NOT change at runtime.
# Changing these config keys requires a process/worker restart to take effect.
STREAM_OVERALL_TIMEOUT_S = _cfg.get_int("stream.overall_timeout_s", 300)
STREAM_IDLE_TIMEOUT_S = _cfg.get_int("stream.idle_timeout_s", 60)
MAX_CHUNKS_PER_RESPONSE = _cfg.get_int("stream.max_chunks", 2000)

# S6: Allowlisted keys for interrupt payloads (prevent arbitrary data injection)
_SAFE_INTERRUPT_KEYS = {
    "type", "questions", "context", "action", "tool_name", "args",
    "summary", "details", "question", "options", "prompt", "items",
}

# NOTE: This value is read once at import time and does NOT change at runtime.
# Changing this config key requires a process/worker restart to take effect.
# asyncio.Semaphore cannot be resized after creation.
_MAX_CONCURRENT_AGENTS = _cfg.get_int("agent.max_concurrent_agents", 50)
_agent_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_AGENTS)

# Module-level cancel tracking
_MAX_CANCEL_EVENTS = 1000  # Safety cap — should never hit this in practice

_active_stream_cancels: OrderedDict[str, asyncio.Event] = OrderedDict()


def _register_cancel_event(thread_id: str) -> asyncio.Event:
    """Register a cancel event for a stream, with FIFO eviction if at capacity."""
    if len(_active_stream_cancels) >= _MAX_CANCEL_EVENTS:
        # Evict oldest entry
        oldest = next(iter(_active_stream_cancels))
        _active_stream_cancels.pop(oldest, None)
        logger.warning("Cancel event dict at capacity, evicted oldest: %s", oldest)
    event = asyncio.Event()
    _active_stream_cancels[thread_id] = event
    return event

# ---------------------------------------------------------------------------
# Thread ownership tracking (H4 — prevent IDOR)
# ---------------------------------------------------------------------------
# Redis-backed storage: key "thread_owner:{thread_id}" -> user_id string.
# Falls back to in-memory OrderedDict when Redis is unavailable.
# NOTE: In-memory fallback is per-process. Multi-worker deployments MUST have
# Redis available for thread ownership to work across workers. When Redis is
# down, cross-worker requests to foreign threads are allowed through (fail-open)
# to avoid breaking existing sessions.

# NOTE: This value is read once at import time and does NOT change at runtime.
_THREAD_OWNER_TTL = _cfg.get_int("stream.thread_owner_ttl", 86400)  # 24 hours

# In-memory fallback (used only when Redis is down)
_thread_owners_fallback: OrderedDict[str, str] = OrderedDict()
_FALLBACK_MAX_SIZE = 10_000


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

    # TE-R4-011: Evict BEFORE adding (consistent with _register_cancel_event)
    if len(_thread_owners_fallback) >= _FALLBACK_MAX_SIZE:
        _thread_owners_fallback.popitem(last=False)
    _thread_owners_fallback[thread_id] = user_id


async def _validate_thread_owner(
    thread_id: str,
    user_id: str,
    *,
    require_existing: bool = False,
    strict: bool = False,
) -> None:
    """Raise 403 if *thread_id* does not belong to *user_id*.

    Fail-closed: when Redis is unavailable AND the thread is not in the
    in-memory fallback, return 503 instead of allowing access to prevent
    IDOR when Redis is down.

    Args:
        thread_id: The thread to check.
        user_id: The expected owner.
        require_existing: If True and the thread is not found (owner is None)
            even though Redis is available, raise 404. Use this for resume/replay
            endpoints where the thread must already exist.
        strict: If True, return 503 immediately when Redis is unavailable
            instead of consulting the in-memory fallback.  Use for sensitive
            endpoints (resume, replay, history) to prevent IDOR after FIFO
            eviction of the fallback dict.
    """
    from ..services.redis_service import redis_service

    owner: str | None = None
    redis_available = False
    try:
        if redis_service.is_connected:
            redis_available = True
            owner = await redis_service.get(f"thread_owner:{thread_id}")
    except Exception:
        redis_available = False

    # CRIT-4: For strict endpoints, refuse immediately when Redis is down
    if strict and not redis_available:
        logger.warning(
            "Thread ownership check (strict) refused: Redis unavailable "
            "for thread %s",
            thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Thread ownership verification temporarily unavailable",
        )

    if owner is None and not strict:
        owner = _thread_owners_fallback.get(thread_id)

    if owner is None and not redis_available:
        # Fail-closed: Redis down + not in local fallback = refuse
        logger.warning(
            "Thread ownership check fail-closed: Redis unavailable, "
            "thread %s not in local fallback",
            thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Thread ownership verification temporarily unavailable",
        )

    # SA-001: For resume/replay, thread must exist
    if owner is None and redis_available and require_existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found or expired",
        )

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
        except asyncio.CancelledError:
            await session.rollback()
            raise
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
    for i, img in enumerate(images):
        if img.media_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported image type: {img.media_type}",
            )
        # SA-006: Check base64 string length before decoding to avoid
        # allocating memory for oversized payloads.
        max_b64_len = (MAX_IMAGE_SIZE * 4) // 3 + 4  # +4 for padding
        if len(img.data) > max_b64_len:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image {i + 1} exceeds maximum size of {MAX_IMAGE_SIZE // (1024 * 1024)}MB",
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
    history: list[ChatHistoryEntry],
) -> list[Any]:
    """Convert conversation_history entries to LangChain message objects.

    Each entry is a ``ChatHistoryEntry`` with ``role`` ("user" | "assistant")
    and ``content`` (str) attributes.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    messages: list[Any] = []
    for entry in history:
        if entry.role == "assistant":
            messages.append(AIMessage(content=entry.content))
        else:
            messages.append(HumanMessage(content=entry.content))
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
    *,
    warm_model: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Build RBAC context, set tool context, and compile agent graph.

    Opens a short-lived DB session for the RBAC query only, then releases
    the connection back to the pool before returning.  This prevents
    holding a connection idle for the entire agent execution (~120 s).

    Args:
        current_user: Authenticated user.
        warm_model: If True, resolve the LLM model upfront and inject it
            into the graph caches.  Required for interrupt/resume flows
            where intake_node won't re-run.

    Returns (graph, context).
    Caller must call clear_tool_context() in a finally block.
    """
    from ..ai.agent.graph import build_agent_graph, get_checkpointer
    from ..ai.agent.rbac_context import AgentRBACContext
    from ..ai.agent.tools import ALL_READ_TOOLS, ALL_WRITE_TOOLS, set_tool_context
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

    # Pre-warm model for resume flows (intake won't re-run after interrupt)
    pre_warmed_model = None
    pre_warmed_prompt = None
    if warm_model:
        from ..ai.agent.graph import _get_langchain_chat_model
        from ..ai.agent.prompts import SYSTEM_PROMPT, load_system_prompt
        try:
            async with async_session_maker() as db:
                pre_warmed_model = await _get_langchain_chat_model(
                    registry, db, current_user.id,
                )
                # Load system prompt via unified loader (config + legacy fallback)
                try:
                    pre_warmed_prompt = await load_system_prompt(db)
                except Exception:
                    pre_warmed_prompt = SYSTEM_PROMPT
        except Exception as exc:
            logger.warning("Failed to pre-warm model for resume: %s", exc)

    all_tools = ALL_READ_TOOLS + ALL_WRITE_TOOLS
    graph = build_agent_graph(
        tools=all_tools,
        checkpointer=get_checkpointer(),
        provider_registry=registry,
        db_session_factory=get_tool_db,
        pre_warmed_model=pre_warmed_model,
        pre_warmed_system_prompt=pre_warmed_prompt,
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

# Nodes whose LLM token streams are forwarded as text_delta events.
# S2: Include synthesize so its LLM tokens stream to the user
_STREAMABLE_NODES = {"explore", "respond", "synthesize"}

# Pipeline nodes that emit thinking_step events.
_THINKING_NODES = {
    "intake", "understand", "clarify", "explore",
    "explore_tools", "synthesize", "respond",
}

_NODE_LABELS_START: dict[str, str] = {
    "intake": "Reading your message...",
    "understand": "Understanding your request...",
    "clarify": "Need some clarification...",
    "explore": "Researching...",
    "explore_tools": "Using tools...",
    "synthesize": "Analyzing results...",
    "respond": "Preparing response...",
}


def _extract_node_details(node_name: str, event: dict) -> str | None:
    """Extract details from a node's on_chain_end output."""
    try:
        output = event.get("data", {}).get("output")
        if not isinstance(output, dict):
            return None
        if node_name in ("explore", "respond"):
            messages = output.get("messages")
            if isinstance(messages, list) and messages:
                last = messages[-1]
                if hasattr(last, "tool_calls") and last.tool_calls:
                    tools = [tc.get("name", "?") for tc in last.tool_calls]
                    return f"**Calling:** {', '.join(tools)}"
            return None
        if node_name == "explore_tools":
            messages = output.get("messages")
            if isinstance(messages, list):
                return f"**Executed** {len(messages)} tool(s)"
            return None
    except Exception:
        return None
    return None


async def _stream_agent(
    graph: Any,
    state: dict | Command,
    config: dict,
    thread_id: str = "",
    shared_state: dict[str, Any] | None = None,
    session_id: str = "",
    context_limit: int = 128_000,
    user_id: str = "",
) -> AsyncGenerator[dict, None]:
    """Async generator that streams LangGraph agent events as SSE payloads.

    Each yielded dict has ``event`` (SSE event name) and ``data`` (JSON
    string) matching the AG-UI event vocabulary.

    Emitted events:
        run_started, thinking_step, text_delta, tool_call_start,
        tool_call_end, interrupt, run_finished, end, error.

    Args:
        graph: Compiled LangGraph agent graph.
        state: Initial agent state dict, or ``Command(resume=...)`` for HITL resume.
        config: LangGraph config dict (must include ``configurable.thread_id``).
        thread_id: Thread ID to include in ``run_started`` event.
    """
    from ..ai.agent.source_references import reset_source_accumulator, get_accumulated_sources

    yield {"event": "run_started", "data": json.dumps({"thread_id": thread_id, "session_id": session_id})}

    interrupted = False
    # Initialize per-request source accumulator (ContextVar).
    # Tool functions push sources here; we read them after the run completes.
    reset_source_accumulator()
    # Track tool call start times for telemetry
    _tool_starts: dict[str, float] = {}  # run_id -> start_time
    _user_id_for_telemetry = user_id or (state.get("user_id", "") if isinstance(state, dict) else "")
    # Track active graph node — fallback when on_chat_model_stream metadata
    # is missing langgraph_node (happens with bind_tools + ainvoke in some
    # LangGraph versions).
    _active_node: str = ""
    _any_text_emitted = False

    try:
        async for event in graph.astream_events(state, config=config, version="v2"):
            event_kind: str = event["event"]

            if event_kind == "on_chain_start":
                node_name = event.get("name", "")
                if node_name in _THINKING_NODES:
                    _active_node = node_name
                label = _NODE_LABELS_START.get(node_name)
                if node_name in _THINKING_NODES and label:
                    yield {
                        "event": "thinking_step",
                        "data": json.dumps({
                            "type": "node",
                            "node": node_name,
                            "label": label,
                            "status": "active",
                        }),
                    }
                    # S3: Emit phase_changed event for frontend phase tracking
                    yield {
                        "event": "phase_changed",
                        "data": json.dumps({
                            "phase": node_name,
                            "label": label,
                        }),
                    }

            elif event_kind == "on_chain_end":
                node_name = event.get("name", "")
                if node_name in _THINKING_NODES:
                    payload: dict[str, Any] = {
                        "type": "node",
                        "node": node_name,
                        "label": _NODE_LABELS_START.get(node_name, node_name),
                        "status": "complete",
                    }
                    # Extract markdown details for all thinking nodes
                    details = _extract_node_details(node_name, event)
                    if details:
                        payload["details"] = details
                    yield {
                        "event": "thinking_step",
                        "data": json.dumps(payload),
                    }

            elif event_kind == "on_chat_model_stream":
                node = event.get("metadata", {}).get("langgraph_node", "") or _active_node
                if node not in _STREAMABLE_NODES:
                    continue
                chunk = event["data"].get("chunk")
                if chunk is not None and hasattr(chunk, "content") and chunk.content:
                    _any_text_emitted = True
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
                is_error = output_text.startswith("Error:") or output_text.startswith("Tool error:")
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
                            "details": output_text[:2000] if output_text else "",
                            **({"error": output_text[:500]} if is_error else {}),
                        }
                    ),
                }

    except Exception as e:
        # MED-24: Let LangGraph interrupts propagate — they are control flow, not errors
        if isinstance(e, GraphBubbleUp):
            raise
        logger.exception("Stream error: %s", e)
        yield {"event": "error", "data": json.dumps({"message": "Agent encountered an error."})}
    finally:
        # R3 QE-R3-008: Clear orphaned tool start timestamps
        _tool_starts.clear()

    # CR-R4-003: Fetch graph state once and reuse for both text fallback and interrupt check
    # HIGH-17: Reuse externally-fetched state if available (avoids double aget_state)
    graph_state = shared_state.get("graph_state") if shared_state else None
    if graph_state is None:
        try:
            graph_state = await graph.aget_state(config)
            if shared_state is not None:
                shared_state["graph_state"] = graph_state
        except Exception:
            logger.warning("Could not fetch graph state after stream", exc_info=True)

    # Bug 6 fix: If no text was streamed (pre-constructed AIMessage), emit content
    if not _any_text_emitted and graph_state:
        try:
            from langchain_core.messages import AIMessage as _AIMessage
            _fb_msgs = graph_state.values.get("messages", [])
            for _fb_msg in reversed(_fb_msgs):
                if isinstance(_fb_msg, _AIMessage) and _fb_msg.content and not getattr(_fb_msg, "tool_calls", None):
                    yield {"event": "text_delta", "data": json.dumps({"content": _fb_msg.content})}
                    break
        except Exception:
            pass

    # Check for interrupt state after stream completes
    try:
        if graph_state and getattr(graph_state, "next", None):
            interrupted = True
            # Complete the active node's thinking_step so its spinner stops.
            # When a node calls interrupt(), on_chain_end never fires.
            if _active_node in _THINKING_NODES:
                yield {
                    "event": "thinking_step",
                    "data": json.dumps({
                        "type": "node",
                        "node": _active_node,
                        "label": _NODE_LABELS_START.get(_active_node, _active_node),
                        "status": "complete",
                    }),
                }
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
                                # S6: Allowlist interrupt payload keys
                                for k, v in value.items():
                                    if k in _SAFE_INTERRUPT_KEYS:
                                        interrupt_payload[k] = v
                                break
                        if len(interrupt_payload) > 1:
                            break
            yield {
                "event": "interrupt",
                "data": json.dumps(interrupt_payload),
            }
    except Exception:
        logger.warning("Could not check interrupt state after stream", exc_info=True)

    # Extract checkpoint_id for rewind/time-travel feature
    checkpoint_id: str | None = None
    try:
        if graph_state:
            config_val = getattr(graph_state, "config", {})
            configurable = config_val.get("configurable", {}) if isinstance(config_val, dict) else {}
            checkpoint_id = configurable.get("checkpoint_id")
    except Exception:
        pass

    # Emit token usage from the LAST AIMessage (current turn, not cumulative)
    _input_tokens = 0
    _output_tokens = 0
    if graph_state:
        from langchain_core.messages import AIMessage as _AIMsg
        for msg in reversed(graph_state.values.get("messages", [])):
            if isinstance(msg, _AIMsg):
                usage = getattr(msg, "usage_metadata", None)
                if usage and isinstance(usage, dict):
                    _input_tokens = usage.get("input_tokens", 0)
                    _output_tokens = usage.get("output_tokens", 0)
                break

    # Persist token counts to session DB row
    if session_id and (_input_tokens or _output_tokens):
        try:
            from sqlalchemy import update as sa_update
            from ..models.chat_session import ChatSession as _CS
            async with async_session_maker() as _db:
                await _db.execute(
                    sa_update(_CS).where(_CS.id == session_id).values(
                        total_input_tokens=_CS.total_input_tokens + _input_tokens,
                        total_output_tokens=_CS.total_output_tokens + _output_tokens,
                    )
                )
                await _db.commit()
        except Exception:
            logger.debug("Failed to persist token usage to session", exc_info=True)

    yield {
        "event": "token_usage",
        "data": json.dumps({
            "input_tokens": _input_tokens,
            "output_tokens": _output_tokens,
            "total_tokens": _input_tokens + _output_tokens,
            "context_limit": context_limit,
        }),
    }

    # Emit context_summary if the agent auto-summarized old messages
    _context_summary_text: str | None = None
    if graph_state:
        _context_summary_text = graph_state.values.get("context_summary")
    if _context_summary_text:
        # Determine up_to_sequence from the most recent message count
        _summary_seq = len(graph_state.values.get("messages", [])) if graph_state else 0
        yield {
            "event": "context_summary",
            "data": json.dumps({
                "summary": _context_summary_text,
                "up_to_sequence": _summary_seq,
            }),
        }
        # Persist summary to ChatSession (only if session exists)
        if session_id:
            try:
                from sqlalchemy import update as _sa_update
                from ..models.chat_session import ChatSession as _CSSum
                async with async_session_maker() as _sum_db:
                    await _sum_db.execute(
                        _sa_update(_CSSum).where(_CSSum.id == session_id).values(
                            context_summary=_context_summary_text,
                            summary_up_to_msg_seq=_summary_seq,
                        )
                    )
                    await _sum_db.commit()
            except Exception:
                logger.debug("Failed to persist context summary to session", exc_info=True)

    yield {
        "event": "run_finished",
        "data": json.dumps({
            "interrupted": interrupted,
            "sources": get_accumulated_sources(),
            "session_id": session_id,
            **({"checkpoint_id": checkpoint_id} if checkpoint_id else {}),
        }),
    }
    yield {"event": "end", "data": "{}"}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
# CR2-001/CR2-002: Shared guarded SSE stream helper
# ---------------------------------------------------------------------------


async def _guarded_sse_stream(
    graph: Any,
    state: Any,
    config: dict[str, Any],
    thread_id: str,
    *,
    user_id: str,
    check_interrupt: bool = False,
    cleanup: Any = None,
    logger_ctx: logging.LoggerAdapter | None = None,
    cancel_event: asyncio.Event | None = None,
    session_id: str = "",
    context_limit: int = 128_000,
) -> AsyncGenerator[dict, None]:
    """Unified guarded SSE stream with timeout, chunk limit, and cleanup.

    Eliminates code duplication across chat_stream, resume_chat_stream,
    and replay_conversation endpoints.

    Args:
        graph: Compiled LangGraph agent graph.
        state: Agent state dict or ``Command(resume=...)``.
        config: LangGraph config dict.
        thread_id: Thread ID for logging.
        user_id: User ID for logging.
        check_interrupt: If True, check for graph interrupt on idle timeout
            (used by chat_stream where clarify/HITL pauses may trigger idle).
        cleanup: Optional async callable to invoke in finally block.
        logger_ctx: Optional LoggerAdapter for correlated logging.
        cancel_event: Optional asyncio.Event that, when set, cancels the stream.
    """
    log = logger_ctx or logger
    chunk_count = 0
    emitted_interrupt = False
    emitted_run_finished = False
    # HIGH-17: Shared mutable container so idle-timeout state fetch is reused by _stream_agent
    shared_state: dict[str, Any] = {}
    aiter_stream = _stream_agent(
        graph, state, config, thread_id=thread_id, shared_state=shared_state,
        session_id=session_id, context_limit=context_limit, user_id=user_id,
    ).__aiter__()

    try:
        async with asyncio.timeout(STREAM_OVERALL_TIMEOUT_S):
            while True:
                if cancel_event and cancel_event.is_set():
                    yield {"event": "error", "data": json.dumps({"message": "Cancelled by user"})}
                    yield {"event": "end", "data": "{}"}
                    return

                try:
                    event = await asyncio.wait_for(
                        anext(aiter_stream),
                        timeout=STREAM_IDLE_TIMEOUT_S,
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    if check_interrupt:
                        # Before declaring timeout, check if graph was
                        # interrupted (clarify/HITL). astream_events may
                        # hang after interrupt() in some LangGraph versions.
                        try:
                            gs = await graph.aget_state(config)
                            # HIGH-17: Store in shared container so _stream_agent skips re-fetch
                            shared_state["graph_state"] = gs
                            if gs and getattr(gs, "next", None):
                                log.info(
                                    "Idle timeout fired but graph is interrupted — "
                                    "emitting interrupt event for thread %s",
                                    thread_id,
                                )
                                try:
                                    while True:
                                        remaining = await asyncio.wait_for(
                                            anext(aiter_stream), timeout=5,
                                        )
                                        if remaining.get("event") == "interrupt":
                                            emitted_interrupt = True
                                        elif remaining.get("event") == "run_finished":
                                            emitted_run_finished = True
                                        yield remaining
                                except (StopAsyncIteration, asyncio.TimeoutError):
                                    pass
                                # DA-R2-013: Ensure frontend receives
                                # interrupt + run_finished even if drain
                                # didn't capture them
                                if not emitted_interrupt:
                                    interrupt_payload = {"thread_id": thread_id}
                                    tasks = getattr(gs, "tasks", None)
                                    if tasks:
                                        for t in tasks:
                                            interrupts = getattr(t, "interrupts", None)
                                            if interrupts:
                                                for intr in interrupts:
                                                    value = getattr(intr, "value", None)
                                                    if isinstance(value, dict):
                                                        # S6: Allowlist interrupt payload keys
                                                        for k, v in value.items():
                                                            if k in _SAFE_INTERRUPT_KEYS:
                                                                interrupt_payload[k] = v
                                                        break
                                                if len(interrupt_payload) > 1:
                                                    break
                                    yield {
                                        "event": "interrupt",
                                        "data": json.dumps(interrupt_payload),
                                    }
                                if not emitted_run_finished:
                                    yield {
                                        "event": "run_finished",
                                        "data": json.dumps({"sources": [], "session_id": session_id}),
                                    }
                                yield {"event": "end", "data": "{}"}
                                return
                        except Exception:
                            pass  # Fall through to normal timeout handling

                    log.warning(
                        "Stream idle timeout (%ds) for user %s, thread %s",
                        STREAM_IDLE_TIMEOUT_S,
                        user_id,
                        thread_id,
                    )
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"message": "Stream timeout — response took too long"}
                        ),
                    }
                    yield {"event": "end", "data": "{}"}
                    return

                # Chunk limit check
                chunk_count += 1
                if chunk_count > MAX_CHUNKS_PER_RESPONSE:
                    log.warning(
                        "Stream chunk limit (%d) exceeded for user %s, thread %s",
                        MAX_CHUNKS_PER_RESPONSE,
                        user_id,
                        thread_id,
                    )
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"message": "Response exceeded maximum size"}
                        ),
                    }
                    yield {"event": "end", "data": "{}"}
                    return

                # Track emitted events for DA-R2-013 completeness
                evt_name = event.get("event")
                if evt_name == "interrupt":
                    emitted_interrupt = True
                elif evt_name == "run_finished":
                    emitted_run_finished = True
                yield event
    except TimeoutError:
        log.warning(
            "Stream overall timeout (%ds) for user %s, thread %s",
            STREAM_OVERALL_TIMEOUT_S,
            user_id,
            thread_id,
        )
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": "Stream timeout — response took too long"}
            ),
        }
        yield {"event": "end", "data": "{}"}
    finally:
        # Ensure async generator is closed to release resources
        try:
            await aiter_stream.aclose()
        except Exception:
            pass
        if cleanup:
            await cleanup() if asyncio.iscoroutinefunction(cleanup) else cleanup()


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
    from ..ai.agent.tools import clear_tool_context

    # 1. Validate images
    _validate_images(request.images)

    # DA-003: Acquire agent concurrency semaphore
    try:
        async with asyncio.timeout(1):
            await _agent_semaphore.acquire()
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is at capacity. Please try again shortly.",
        )

    try:
        # 2. Setup agent context (RBAC, tools, graph)
        graph, context = await _setup_agent_context(current_user)

        try:
            # 3. Build messages
            # HIGH-6: Only trust user messages from client-supplied history
            if request.conversation_history:
                request.conversation_history = [
                    entry for entry in request.conversation_history
                    if entry.role == "user"
                ]
            messages = _history_to_langchain_messages(request.conversation_history)
            human_msg = _build_human_message(request.message, request.images)
            messages.append(human_msg)

            # 4. Build initial state and config
            thread_id = request.thread_id or str(uuid4())
            if request.thread_id:
                await _validate_thread_owner(thread_id, str(current_user.id))
            await _register_thread(thread_id, str(current_user.id))

            # QE-006: Correlated logging context
            extra = {"thread_id": thread_id, "user_id": str(current_user.id)}
            logger_ctx = logging.LoggerAdapter(logger, extra)
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
        except HTTPException:
            raise
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
                # CR-R4-005: Infer provider from response_metadata signatures
                if _provider_name == "unknown":
                    if "system_fingerprint" in resp_meta:
                        _provider_name = "openai"
                    elif resp_meta.get("type") == "message":
                        _provider_name = "anthropic"

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
    finally:
        _agent_semaphore.release()


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

    from ..ai.agent.tools import clear_tool_context

    # 1. Validate images
    _validate_images(request.images)

    # DA-001: Acquire semaphore eagerly to reject 503 fast, but track
    # that we acquired it so cleanup can release it reliably even if
    # the generator is never iterated.
    try:
        async with asyncio.timeout(1):
            await _agent_semaphore.acquire()
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is at capacity. Please try again shortly.",
        )

    # 2. Setup agent context (RBAC, tools, graph)
    try:
        graph, context = await _setup_agent_context(current_user)
    except Exception:
        _agent_semaphore.release()
        clear_tool_context()
        raise

    # C3: wrap message/state building in try/finally so context is cleared on setup failure
    try:
        # 3. Build messages
        # HIGH-6: Only trust user messages from client-supplied history
        if request.conversation_history:
            request.conversation_history = [
                entry for entry in request.conversation_history
                if entry.role == "user"
            ]
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
        _agent_semaphore.release()
        clear_tool_context()
        raise

    # QE-006: Create correlated logger for this endpoint
    extra = {"thread_id": thread_id, "user_id": str(current_user.id)}
    logger_ctx = logging.LoggerAdapter(logger, extra)

    # 5. Create cancel event for this stream (SA-R2-002: bounded dict)
    # Registered inside the cleanup-covered scope so _cleanup() always pops it
    cancel_event = _register_cancel_event(thread_id)

    # 5b. Session handling — auto-create if not provided
    session_id = ""
    _context_limit = 128_000
    try:
        from sqlalchemy import func, select, update
        from ..models.chat_session import ChatSession
        from ..models.ai_model import AiModel

        async with async_session_maker() as db:
            # Look up model context limit
            model_result = await db.execute(
                select(AiModel.max_tokens).where(
                    AiModel.is_default.is_(True),
                    AiModel.capability == "chat",
                )
            )
            model_max = model_result.scalar_one_or_none()
            if model_max and model_max > 0:
                _context_limit = model_max

            if request.session_id:
                # Verify ownership
                sess_result = await db.execute(
                    select(ChatSession).where(ChatSession.id == request.session_id)
                )
                sess = sess_result.scalar_one_or_none()
                if sess is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Chat session not found.",
                    )
                if sess.user_id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied to this chat session.",
                    )
                session_id = str(sess.id)
                if not sess.thread_id:
                    sess.thread_id = thread_id
                    await db.commit()
            else:
                # Auto-create session (enforce 100-session cap)
                from ..utils.timezone import utc_now

                count_q = select(func.count()).select_from(ChatSession).where(
                    ChatSession.user_id == current_user.id,
                    ChatSession.is_archived.is_(False),
                )
                active_count = (await db.execute(count_q)).scalar() or 0
                if active_count >= 100:
                    oldest_q = (
                        select(ChatSession.id)
                        .where(
                            ChatSession.user_id == current_user.id,
                            ChatSession.is_archived.is_(False),
                        )
                        .order_by(ChatSession.updated_at.asc())
                        .limit(active_count - 99)
                    )
                    oldest_ids = [row[0] for row in (await db.execute(oldest_q)).all()]
                    if oldest_ids:
                        await db.execute(
                            update(ChatSession)
                            .where(ChatSession.id.in_(oldest_ids))
                            .values(is_archived=True)
                        )

                now = utc_now()
                new_sess = ChatSession(
                    user_id=current_user.id,
                    thread_id=thread_id,
                    application_id=None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(new_sess)
                await db.flush()
                await db.refresh(new_sess)
                session_id = str(new_sess.id)
                await db.commit()
    except Exception:
        logger.debug("Session handling failed, continuing without session", exc_info=True)

    # 6. Return SSE stream using shared helper (CR2-001)
    # DA-018: Exception-safe cleanup — each step is isolated so a failure
    # in one does not prevent the others from executing.
    # Cleanup is handled by the generator's finally block (via _guarded_sse_stream).
    # Do NOT call _cleanup() in a route-level finally — EventSourceResponse
    # iterates the generator in a later task, so a route-level finally would
    # clear the ContextVar before the generator starts.
    _cleaned_up = False

    def _cleanup():
        nonlocal _cleaned_up
        if _cleaned_up:
            return
        _cleaned_up = True
        try:
            clear_tool_context()
        except Exception:
            pass
        try:
            _agent_semaphore.release()
        except Exception:
            pass
        _active_stream_cancels.pop(thread_id, None)

    async def _background_cleanup():
        """Safety net: release resources if the generator was never iterated."""
        _cleanup()

    return EventSourceResponse(
        _guarded_sse_stream(
            graph, state, config, thread_id,
            user_id=str(current_user.id),
            check_interrupt=True,
            cleanup=_cleanup,
            logger_ctx=logger_ctx,
            cancel_event=cancel_event,
            session_id=session_id,
            context_limit=_context_limit,
        ),
        media_type="text/event-stream",
        background=_background_cleanup,
    )


# ---------------------------------------------------------------------------
# POST /api/ai/chat/cancel  --  Cancel active stream
# ---------------------------------------------------------------------------


@router.post("/chat/cancel/{thread_id}")
async def cancel_chat(
    thread_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Cancel an active streaming chat."""
    await _validate_thread_owner(thread_id, str(current_user.id))
    cancel_event = _active_stream_cancels.get(thread_id)
    if cancel_event:
        cancel_event.set()
        return {"status": "cancelled"}
    return {"status": "not_found"}


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
    from ..ai.agent.tools import clear_tool_context

    # Validate thread ownership (SA-001: require_existing for resume, CRIT-4: strict)
    await _validate_thread_owner(
        request.thread_id, str(current_user.id), require_existing=True, strict=True,
    )

    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Checkpointer not configured — HITL resume unavailable",
        )

    # DA-003: Acquire agent concurrency semaphore
    try:
        async with asyncio.timeout(1):
            await _agent_semaphore.acquire()
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is at capacity. Please try again shortly.",
        )

    # QE-006: Correlated logging context
    extra = {"thread_id": request.thread_id, "user_id": str(current_user.id)}
    logger_ctx = logging.LoggerAdapter(logger, extra)

    try:
        # Setup agent context (RBAC, tools, graph) — warm_model=True because
        # intake_node won't re-run on resume, so nodes need a pre-warmed model.
        graph, _context = await _setup_agent_context(current_user, warm_model=True)

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
                logger_ctx.warning(
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
            except HTTPException:
                raise
            except Exception:
                logger_ctx.exception(
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
                if _provider_name == "unknown":
                    if "system_fingerprint" in resp_meta:
                        _provider_name = "openai"
                    elif resp_meta.get("type") == "message":
                        _provider_name = "anthropic"

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

        return _build_chat_response(result_messages, request.thread_id)
    finally:
        _agent_semaphore.release()


# ---------------------------------------------------------------------------
# POST /api/ai/chat/resume/stream  --  SSE streaming HITL resume
# ---------------------------------------------------------------------------


@router.post("/chat/resume/stream")
async def resume_chat_stream(
    request: ResumeRequest,
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(check_chat_rate_limit),
) -> Any:
    """SSE streaming resume after a human-in-the-loop interrupt.

    Same semantics as ``POST /chat/resume`` but returns an SSE stream
    with the same event vocabulary as ``POST /chat/stream``.
    """
    from sse_starlette.sse import EventSourceResponse

    from ..ai.agent.graph import get_checkpointer
    from ..ai.agent.tools import clear_tool_context

    # Validate thread ownership (SA-001: require_existing for resume, CRIT-4: strict)
    await _validate_thread_owner(
        request.thread_id, str(current_user.id), require_existing=True, strict=True,
    )

    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Checkpointer not configured — HITL resume unavailable",
        )

    # DA-003: Acquire agent concurrency semaphore
    try:
        async with asyncio.timeout(1):
            await _agent_semaphore.acquire()
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is at capacity. Please try again shortly.",
        )

    # Setup agent context (RBAC, tools, graph) — warm_model=True because
    # intake_node won't re-run on resume, so nodes need a pre-warmed model.
    try:
        graph, _context = await _setup_agent_context(current_user, warm_model=True)
    except Exception:
        _agent_semaphore.release()
        clear_tool_context()
        raise

    config: dict[str, Any] = {
        "configurable": {"thread_id": request.thread_id}
    }
    resume_cmd = Command(resume=request.response)

    # CR-004: Create cancel event for this stream (SA-R2-002: bounded dict)
    cancel_event = _register_cancel_event(request.thread_id)

    # QE-006: Correlated logger
    extra = {"thread_id": request.thread_id, "user_id": str(current_user.id)}
    logger_ctx = logging.LoggerAdapter(logger, extra)

    # R3: Resolve session_id from thread so token usage is persisted for resumed turns
    resume_session_id = ""
    resume_context_limit = 128_000
    try:
        async with async_session_maker() as db:
            from ..models.chat_session import ChatSession
            sess_result = await db.execute(
                select(ChatSession.id).where(
                    ChatSession.thread_id == request.thread_id,
                    ChatSession.user_id == current_user.id,
                ).limit(1)
            )
            sess_row = sess_result.scalar_one_or_none()
            if sess_row:
                resume_session_id = str(sess_row)
    except Exception:
        logger.debug("resume_chat_stream: session lookup failed, continuing without session_id")

    # CR2-002: Use shared guarded stream helper
    # CR2-C1: Idempotent cleanup with flag — safety net if generator never iterated.
    _cleaned_up = False

    def _cleanup():
        nonlocal _cleaned_up
        if _cleaned_up:
            return
        _cleaned_up = True
        try:
            clear_tool_context()
        except Exception:
            pass
        try:
            _agent_semaphore.release()
        except Exception:
            pass
        _active_stream_cancels.pop(request.thread_id, None)

    async def _background_cleanup():
        _cleanup()

    return EventSourceResponse(
        _guarded_sse_stream(
            graph, resume_cmd, config, request.thread_id,
            user_id=str(current_user.id),
            check_interrupt=True,  # DA-R4-005: detect chained interrupts during resume
            cleanup=_cleanup,
            logger_ctx=logger_ctx,
            cancel_event=cancel_event,
            session_id=resume_session_id,
            context_limit=resume_context_limit,
        ),
        media_type="text/event-stream",
        background=_background_cleanup,
    )


# ---------------------------------------------------------------------------
# GET /api/ai/chat/history/{thread_id}  --  Checkpoint timeline
# ---------------------------------------------------------------------------


@router.get("/chat/history/{thread_id}")
async def get_conversation_history(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(check_chat_rate_limit),
    limit: int = Query(default=50, le=200),
) -> dict[str, list[CheckpointSummary]]:
    """List user-visible checkpoints for a conversation thread.

    Returns checkpoints produced by the ReAct loop nodes (agent, tools),
    filtering out internal intake checkpoints. This powers the time-travel
    / rewind UI.
    """
    from ..ai.agent.graph import get_checkpointer

    # H4: validate thread ownership (CRIT-4: strict)
    await _validate_thread_owner(thread_id, str(current_user.id), strict=True)

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

    # Filter to user-visible turns (ReAct loop node names)
    _VISIBLE_NODES = {"agent", "tools"}
    visible = [
        cp
        for cp in checkpoints
        if cp.node in _VISIBLE_NODES and cp.message_count > 0
    ]
    return {"checkpoints": visible[:limit]}


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
    from ..ai.agent.tools import clear_tool_context

    # H4: validate thread ownership (SA-001: require_existing for replay, CRIT-4: strict)
    await _validate_thread_owner(
        request.thread_id, str(current_user.id), require_existing=True, strict=True,
    )

    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Checkpointer not configured — time-travel unavailable",
        )

    # Setup agent context (RBAC, tools, graph)
    try:
        graph, context = await _setup_agent_context(current_user)
    except Exception:
        clear_tool_context()
        raise

    if request.message:
        # DA-003: Acquire agent concurrency semaphore (only for branching/streaming)
        try:
            async with asyncio.timeout(1):
                await _agent_semaphore.acquire()
        except asyncio.TimeoutError:
            clear_tool_context()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is at capacity. Please try again shortly.",
            )

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
            _agent_semaphore.release()
            clear_tool_context()
            raise

        # QE-006: Correlated logger
        extra = {"thread_id": branch_thread_id, "user_id": str(current_user.id)}
        logger_ctx = logging.LoggerAdapter(logger, extra)

        # CR-R2-004: Create cancel event for replay stream (SA-R2-002: bounded dict)
        cancel_event = _register_cancel_event(branch_thread_id)

        # CR2-002: Use shared guarded stream helper
        # CR2-C1: Idempotent cleanup with flag — safety net if generator never iterated.
        _cleaned_up = False

        def _cleanup():
            nonlocal _cleaned_up
            if _cleaned_up:
                return
            _cleaned_up = True
            try:
                clear_tool_context()
            except Exception:
                pass
            try:
                _agent_semaphore.release()
            except Exception:
                pass
            _active_stream_cancels.pop(branch_thread_id, None)

        async def _background_cleanup():
            _cleanup()

        return EventSourceResponse(
            _guarded_sse_stream(
                graph, input_state, branch_config, branch_thread_id,
                user_id=str(current_user.id),
                check_interrupt=False,
                cleanup=_cleanup,
                logger_ctx=logger_ctx,
                cancel_event=cancel_event,
            ),
            media_type="text/event-stream",
            background=_background_cleanup,
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

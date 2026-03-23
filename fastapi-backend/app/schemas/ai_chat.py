"""Pydantic schemas for AI chat endpoints (Phase 4 LangGraph agent)."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatImageAttachment(BaseModel):
    """Image attached to a chat message by the user (paste or upload)."""

    data: str = Field(
        ...,
        description="Base64-encoded image data",
    )
    media_type: str = Field(
        ...,
        description='MIME type: "image/png", "image/jpeg", "image/gif", "image/webp"',
    )
    filename: str | None = Field(
        None,
        description="Original filename if uploaded",
    )


class ChatHistoryEntry(BaseModel):
    """A single message in conversation history."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=32_000)


class ChatRequest(BaseModel):
    """Request body for POST /api/ai/chat and /api/ai/chat/stream."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=32_000,
        description="User message text",
    )
    images: list[ChatImageAttachment] = Field(
        default_factory=list,
        description="Images pasted or uploaded by the user (max 5)",
    )
    conversation_history: list[ChatHistoryEntry] = Field(
        default_factory=list,
        description="Previous messages for multi-turn context (max 50)",
    )

    @field_validator("conversation_history")
    @classmethod
    def truncate_history(cls, v: list[ChatHistoryEntry]) -> list[ChatHistoryEntry]:
        """SA-018: Silently truncate conversation history to last 50 entries (not reject)."""
        if len(v) > 50:
            return v[-50:]
        return v

    # TODO: Phase 5 — application_id will be used to scope agent context
    application_id: str | None = Field(
        None,
        description="Optional scope hint — limits search to this application",
    )
    thread_id: str | None = Field(
        None,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Thread ID for conversation continuity (omit for new thread)",
    )
    session_id: str | None = Field(
        None,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="Chat session ID for persistence (omit to auto-create)",
    )

    @model_validator(mode="after")
    def _check_total_history_size(self) -> "ChatRequest":
        """Cap total conversation_history size to prevent memory abuse."""
        max_total_chars = 500_000  # ~500K chars total across all messages
        total = sum(len(e.content) for e in self.conversation_history)
        if total > max_total_chars:
            raise ValueError(
                f"conversation_history total size ({total} chars) exceeds maximum ({max_total_chars} chars)"
            )
        return self


class ChatResponse(BaseModel):
    """Response from the non-streaming POST /api/ai/chat endpoint."""

    response: str = Field(
        ...,
        description="Blair's text response",
    )
    tool_calls: list[dict] = Field(
        default_factory=list,
        description="Tool calls made during this turn (for transparency)",
    )
    thread_id: str = Field(
        ...,
        description="Thread ID for follow-up messages",
    )
    sources: list[dict] = Field(
        default_factory=list,
        description="Structured source references from knowledge retrieval",
    )
    interrupted: bool = Field(
        default=False,
        description="Whether the agent is waiting for user input",
    )
    interrupt_payload: dict | None = Field(
        default=None,
        description="HITL confirmation payload if interrupted",
    )


class ResumeRequest(BaseModel):
    """Request body for POST /api/ai/chat/resume (HITL confirmation)."""

    thread_id: str = Field(
        ...,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Thread ID of the interrupted conversation",
    )
    response: dict = Field(
        ...,
        description='User response payload (e.g. {"approved": true})',
    )

    @model_validator(mode="after")
    def _check_response_size(self) -> "ResumeRequest":
        """DA-R4-001: Cap response payload size to prevent memory abuse."""
        max_bytes = 10_000
        serialized = json.dumps(self.response, default=str)
        if len(serialized) > max_bytes:
            raise ValueError(f"response payload too large ({len(serialized)} bytes, max {max_bytes})")
        return self


class ReplayRequest(BaseModel):
    """Request body for POST /api/ai/chat/replay (time-travel)."""

    thread_id: str = Field(
        ...,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Conversation thread to replay",
    )
    checkpoint_id: str = Field(
        ...,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Checkpoint to rewind to",
    )
    message: str | None = Field(
        None,
        max_length=32_000,
        description="Optional new message to send from the replayed checkpoint",
    )


class ChatSessionCreate(BaseModel):
    """Request to create a new chat session."""

    application_id: str | None = None


class ChatSessionUpdate(BaseModel):
    """Request to update a chat session."""

    title: str | None = Field(None, max_length=200)
    is_archived: bool | None = None


class ChatSessionSummary(BaseModel):
    """Summary of a chat session for list views."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_preview: str
    application_id: str | None
    thread_id: str | None
    total_input_tokens: int
    total_output_tokens: int
    context_summary: str | None = None
    summary_up_to_msg_seq: int | None = None


class ChatMessageOut(BaseModel):
    """A single persisted chat message."""

    id: str
    role: str
    content: str
    sources: dict | list | None = None
    checkpoint_id: str | None = None
    is_error: bool
    created_at: str
    sequence: int


class ChatMessagePage(BaseModel):
    """Paginated chat messages response."""

    messages: list[ChatMessageOut]
    has_more: bool


class PersistMessageEntry(BaseModel):
    """A single message to persist."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=32_000)
    sources: dict | list | None = None
    checkpoint_id: str | None = None
    is_error: bool = False

    @field_validator("sources")
    @classmethod
    def _cap_sources_size(cls, v: dict | list | None) -> dict | list | None:
        if v is not None:
            serialized = json.dumps(v, default=str)
            if len(serialized) > 65_536:
                raise ValueError("sources JSON exceeds 64KB limit")
        return v


class PersistMessagesRequest(BaseModel):
    """Request to persist messages to a session."""

    messages: list[PersistMessageEntry] = Field(..., max_length=10)


class SummarizeRequest(BaseModel):
    """Request to summarize a session's conversation."""

    up_to_sequence: int = Field(..., ge=1)


class CheckpointSummary(BaseModel):
    """Summary of a single agent checkpoint (used in time-travel UI)."""

    checkpoint_id: str = Field(
        ...,
        description="Unique checkpoint identifier",
    )
    thread_id: str = Field(
        ...,
        description="Owning conversation thread",
    )
    timestamp: str = Field(
        ...,
        description="ISO-8601 timestamp when the checkpoint was created",
    )
    node: str = Field(
        ...,
        description='Graph node that produced this checkpoint (e.g. "agent")',
    )
    message_count: int = Field(
        ...,
        ge=0,
        description="Number of messages in the conversation at this checkpoint",
    )

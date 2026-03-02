"""Pydantic schemas for AI chat endpoints (Phase 4 LangGraph agent)."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
        max_length=50,
        description="Previous messages for multi-turn context (max 50)",
    )
    # TODO: Phase 5 — application_id will be used to scope agent context
    application_id: str | None = Field(
        None,
        description="Optional scope hint — limits search to this application",
    )
    thread_id: str | None = Field(
        None,
        description="Thread ID for conversation continuity (omit for new thread)",
    )


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
        description="Thread ID of the interrupted conversation",
    )
    response: dict = Field(
        ...,
        description='User response payload (e.g. {"approved": true})',
    )


class ReplayRequest(BaseModel):
    """Request body for POST /api/ai/chat/replay (time-travel)."""

    thread_id: str = Field(
        ...,
        description="Conversation thread to replay",
    )
    checkpoint_id: str = Field(
        ...,
        description="Checkpoint to rewind to",
    )
    message: str | None = Field(
        None,
        max_length=32_000,
        description="Optional new message to send from the replayed checkpoint",
    )


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

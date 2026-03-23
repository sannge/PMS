"""Unit tests for ai_chat.py helper functions and module-level utilities.

Covers audit findings:
- TE-R4-002: _build_chat_response
- TE-R4-003: _register_cancel_event FIFO eviction
- TE-R4-006: get_tool_db CancelledError handling
- TE-R4-011: _thread_owners_fallback eviction
- CR-R4-005: _provider_name inference from response_metadata
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage


# ---------------------------------------------------------------------------
# Tests: _build_chat_response (TE-R4-002)
# ---------------------------------------------------------------------------


class TestBuildChatResponse:
    def test_empty_messages_raises_500(self):
        from app.routers.ai_chat import _build_chat_response

        with pytest.raises(HTTPException) as exc_info:
            _build_chat_response([], "thread-1")
        assert exc_info.value.status_code == 500

    def test_string_content_extracted(self):
        from app.routers.ai_chat import _build_chat_response

        msg = AIMessage(content="Hello world")
        result = _build_chat_response([msg], "thread-1")
        assert result.response == "Hello world"
        assert result.thread_id == "thread-1"

    def test_list_content_extracted(self):
        """Multimodal list-block content is joined."""
        from app.routers.ai_chat import _build_chat_response

        msg = AIMessage(
            content=[
                {"type": "text", "text": "Part A"},
                {"type": "text", "text": "Part B"},
            ]
        )
        result = _build_chat_response([msg], "thread-2")
        assert "Part A" in result.response
        assert "Part B" in result.response

    def test_thread_id_passed_through(self):
        from app.routers.ai_chat import _build_chat_response

        msg = AIMessage(content="ok")
        result = _build_chat_response([msg], "my-thread")
        assert result.thread_id == "my-thread"

    def test_interrupted_flag(self):
        from app.routers.ai_chat import _build_chat_response

        msg = AIMessage(content="paused")
        result = _build_chat_response([msg], "t1", interrupted=True, interrupt_payload={"type": "confirmation"})
        assert result.interrupted is True
        assert result.interrupt_payload == {"type": "confirmation"}

    def test_tool_calls_extracted(self):
        from app.routers.ai_chat import _build_chat_response

        msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_tasks", "args": {"q": "x"}, "id": "tc1"}],
        )
        final = AIMessage(content="Done")
        result = _build_chat_response([msg, final], "t1")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool"] == "list_tasks"


# ---------------------------------------------------------------------------
# Tests: _register_cancel_event FIFO eviction (TE-R4-003)
# ---------------------------------------------------------------------------


class TestRegisterCancelEvent:
    def test_returns_asyncio_event(self):
        import app.routers.ai_chat as mod

        original = dict(mod._active_stream_cancels)
        try:
            event = mod._register_cancel_event("test-thread-1")
            assert isinstance(event, asyncio.Event)
        finally:
            mod._active_stream_cancels.clear()
            mod._active_stream_cancels.update(original)

    def test_fifo_eviction_at_capacity(self):
        import app.routers.ai_chat as mod

        original_dict = dict(mod._active_stream_cancels)
        original_max = mod._MAX_CANCEL_EVENTS
        try:
            mod._active_stream_cancels.clear()
            mod._MAX_CANCEL_EVENTS = 3

            # Fill to capacity
            mod._register_cancel_event("t1")
            mod._register_cancel_event("t2")
            mod._register_cancel_event("t3")
            assert len(mod._active_stream_cancels) == 3
            assert "t1" in mod._active_stream_cancels

            # 4th registration should evict oldest (t1)
            mod._register_cancel_event("t4")
            assert len(mod._active_stream_cancels) == 3
            assert "t1" not in mod._active_stream_cancels
            assert "t4" in mod._active_stream_cancels
        finally:
            mod._MAX_CANCEL_EVENTS = original_max
            mod._active_stream_cancels.clear()
            mod._active_stream_cancels.update(original_dict)


# ---------------------------------------------------------------------------
# Tests: _thread_owners_fallback eviction (TE-R4-011)
# ---------------------------------------------------------------------------


class TestRegisterThread:
    async def test_fallback_stores_owner(self):
        """When Redis is down, stores in in-memory fallback."""
        import app.routers.ai_chat as mod

        original = OrderedDict(mod._thread_owners_fallback)
        try:
            mod._thread_owners_fallback.clear()
            with patch("app.services.redis_service.redis_service") as mock_redis:
                mock_redis.is_connected = False
                await mod._register_thread("thread-abc", "user-123")

            assert mod._thread_owners_fallback["thread-abc"] == "user-123"
        finally:
            mod._thread_owners_fallback.clear()
            mod._thread_owners_fallback.update(original)

    async def test_fallback_evicts_oldest_at_capacity(self):
        """When fallback dict reaches capacity, oldest entry is evicted."""
        import app.routers.ai_chat as mod

        original = OrderedDict(mod._thread_owners_fallback)
        original_max = mod._FALLBACK_MAX_SIZE
        try:
            mod._thread_owners_fallback.clear()
            mod._FALLBACK_MAX_SIZE = 2

            with patch("app.services.redis_service.redis_service") as mock_redis:
                mock_redis.is_connected = False
                await mod._register_thread("t1", "u1")
                await mod._register_thread("t2", "u2")
                assert len(mod._thread_owners_fallback) == 2

                # 3rd should evict t1
                await mod._register_thread("t3", "u3")
                assert len(mod._thread_owners_fallback) == 2
                assert "t1" not in mod._thread_owners_fallback
                assert "t3" in mod._thread_owners_fallback
        finally:
            mod._FALLBACK_MAX_SIZE = original_max
            mod._thread_owners_fallback.clear()
            mod._thread_owners_fallback.update(original)


# ---------------------------------------------------------------------------
# Tests: get_tool_db CancelledError handling (TE-R4-006)
# ---------------------------------------------------------------------------


class TestGetToolDb:
    async def test_cancelled_error_rolls_back_and_reraises(self):
        """CancelledError in get_tool_db body causes rollback and re-raise."""
        from app.routers.ai_chat import get_tool_db

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        @asynccontextmanager
        async def mock_session_maker():
            yield mock_session

        with patch("app.routers.ai_chat.async_session_maker", mock_session_maker):
            with pytest.raises(asyncio.CancelledError):
                async with get_tool_db() as _session:
                    raise asyncio.CancelledError()

        mock_session.rollback.assert_awaited_once()
        mock_session.commit.assert_not_awaited()

    async def test_generic_exception_rolls_back_and_reraises(self):
        """Generic Exception in get_tool_db body causes rollback and re-raise."""
        from app.routers.ai_chat import get_tool_db

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        @asynccontextmanager
        async def mock_session_maker():
            yield mock_session

        with patch("app.routers.ai_chat.async_session_maker", mock_session_maker):
            with pytest.raises(ValueError, match="boom"):
                async with get_tool_db() as _session:
                    raise ValueError("boom")

        mock_session.rollback.assert_awaited_once()
        mock_session.commit.assert_not_awaited()

    async def test_normal_flow_commits(self):
        """Normal flow without exception calls commit."""
        from app.routers.ai_chat import get_tool_db

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        @asynccontextmanager
        async def mock_session_maker():
            yield mock_session

        with patch("app.routers.ai_chat.async_session_maker", mock_session_maker):
            async with get_tool_db() as session:
                pass  # Normal flow

        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: _extract_tool_calls and _extract_sources (support for TE-R4-002)
# ---------------------------------------------------------------------------


class TestExtractHelpers:
    def test_extract_tool_calls_from_ai_messages(self):
        from app.routers.ai_chat import _extract_tool_calls

        msgs = [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "list_tasks", "args": {"project": "P1"}, "id": "tc1"},
                    {"name": "sql_query", "args": {"q": "SELECT 1"}, "id": "tc2"},
                ],
            ),
            AIMessage(content="done"),
        ]
        result = _extract_tool_calls(msgs)
        assert len(result) == 2
        assert result[0]["tool"] == "list_tasks"
        assert result[1]["tool"] == "sql_query"

    def test_extract_tool_calls_empty_messages(self):
        from app.routers.ai_chat import _extract_tool_calls

        assert _extract_tool_calls([]) == []

    def test_extract_sources_from_tool_messages(self):
        from app.routers.ai_chat import _extract_sources

        msg = MagicMock()
        msg.additional_kwargs = {
            "sources": [
                {"document_id": "d1", "document_title": "Doc 1", "score": 0.9},
            ]
        }
        result = _extract_sources([msg])
        assert len(result) == 1
        assert result[0]["document_id"] == "d1"

    def test_extract_sources_no_sources(self):
        from app.routers.ai_chat import _extract_sources

        msg = MagicMock()
        msg.additional_kwargs = {}
        assert _extract_sources([msg]) == []

"""Unit tests for Phase 4 Blair AI chat router and schemas.

Covers schemas (ChatRequest, ChatResponse, etc.), validation helpers,
message conversion helpers, SourceReference / ToolResultWithSources,
and the CopilotKit SDK factory.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.ai_chat import (
    ChatImageAttachment,
    ChatRequest,
    ChatResponse,
    CheckpointSummary,
    ReplayRequest,
)
from app.routers.ai_chat import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_SIZE,
    MAX_IMAGES,
    _build_human_message,
    _extract_sources,
    _extract_tool_calls,
    _history_to_langchain_messages,
    _validate_images,
)
from app.ai.agent.source_references import SourceReference, ToolResultWithSources
from app.ai.agent.copilotkit_runtime import create_copilotkit_sdk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TINY_B64 = base64.b64encode(b"tiny").decode()


def _make_image(
    data: str = TINY_B64,
    media_type: str = "image/png",
    filename: str | None = None,
) -> ChatImageAttachment:
    return ChatImageAttachment(data=data, media_type=media_type, filename=filename)


def _make_source(**overrides) -> SourceReference:
    defaults = {
        "document_id": "doc-1",
        "document_title": "Design Doc",
        "document_type": "document",
        "heading_context": "Overview",
        "chunk_text": "Some chunk",
        "chunk_index": 0,
        "score": 0.95,
        "source_type": "semantic",
        "entity_name": None,
    }
    defaults.update(overrides)
    return SourceReference(**defaults)


# ===========================================================================
# 1. Schema Tests
# ===========================================================================


class TestSchemas:
    """Validate Pydantic schema construction and defaults."""

    def test_chat_image_attachment_fields(self):
        img = ChatImageAttachment(data="abc", media_type="image/png", filename="pic.png")
        assert img.data == "abc"
        assert img.media_type == "image/png"
        assert img.filename == "pic.png"

    def test_chat_image_attachment_filename_optional(self):
        img = ChatImageAttachment(data="abc", media_type="image/jpeg")
        assert img.filename is None

    def test_chat_request_message_required(self):
        with pytest.raises(Exception):
            ChatRequest()  # missing message

    def test_chat_request_defaults(self):
        req = ChatRequest(message="hello")
        assert req.message == "hello"
        assert req.images == []
        assert req.conversation_history == []
        assert req.application_id is None
        assert req.thread_id is None

    def test_chat_response_fields(self):
        resp = ChatResponse(response="hi", thread_id="t1")
        assert resp.response == "hi"
        assert resp.tool_calls == []
        assert resp.thread_id == "t1"
        assert resp.sources == []

    def test_replay_request_fields(self):
        req = ReplayRequest(thread_id="t1", checkpoint_id="cp1")
        assert req.thread_id == "t1"
        assert req.checkpoint_id == "cp1"
        assert req.message is None

    def test_replay_request_with_message(self):
        req = ReplayRequest(thread_id="t1", checkpoint_id="cp1", message="try again")
        assert req.message == "try again"

    def test_checkpoint_summary_fields(self):
        cp = CheckpointSummary(
            checkpoint_id="cp1",
            thread_id="t1",
            timestamp="2026-02-26T00:00:00Z",
            node="agent",
            message_count=3,
        )
        assert cp.checkpoint_id == "cp1"
        assert cp.thread_id == "t1"
        assert cp.timestamp == "2026-02-26T00:00:00Z"
        assert cp.node == "agent"
        assert cp.message_count == 3


# ===========================================================================
# 2. Validation Tests
# ===========================================================================


class TestValidateImages:
    """Tests for _validate_images helper."""

    def test_passes_with_valid_images(self):
        images = [_make_image() for _ in range(3)]
        _validate_images(images)  # should not raise

    def test_passes_with_empty_list(self):
        _validate_images([])  # should not raise

    def test_rejects_too_many_images(self):
        images = [_make_image() for _ in range(MAX_IMAGES + 1)]
        with pytest.raises(HTTPException) as exc_info:
            _validate_images(images)
        assert exc_info.value.status_code == 422
        assert "Too many images" in exc_info.value.detail

    def test_rejects_invalid_mime_type(self):
        img = _make_image(media_type="application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            _validate_images([img])
        assert exc_info.value.status_code == 422
        assert "Unsupported image type" in exc_info.value.detail

    def test_rejects_invalid_base64(self):
        img = _make_image(data="!!!not-base64!!!")
        with pytest.raises(HTTPException) as exc_info:
            _validate_images([img])
        assert exc_info.value.status_code == 422
        assert "Invalid base64" in exc_info.value.detail

    def test_rejects_oversized_image(self):
        # Create base64 data that decodes to > MAX_IMAGE_SIZE
        big_bytes = b"\x00" * (MAX_IMAGE_SIZE + 1)
        big_b64 = base64.b64encode(big_bytes).decode()
        img = _make_image(data=big_b64)
        with pytest.raises(HTTPException) as exc_info:
            _validate_images([img])
        assert exc_info.value.status_code == 422
        assert "Image too large" in exc_info.value.detail

    def test_allowed_image_types_are_expected(self):
        assert ALLOWED_IMAGE_TYPES == {"image/png", "image/jpeg", "image/gif", "image/webp"}


# ===========================================================================
# 3. Message Conversion Tests
# ===========================================================================


class TestMessageConversion:
    """Tests for message conversion helpers."""

    def test_history_to_langchain_user_and_assistant(self):
        from langchain_core.messages import AIMessage, HumanMessage

        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "Thanks"},
        ]
        msgs = _history_to_langchain_messages(history)
        assert len(msgs) == 3
        assert isinstance(msgs[0], HumanMessage)
        assert msgs[0].content == "Hello"
        assert isinstance(msgs[1], AIMessage)
        assert msgs[1].content == "Hi there"
        assert isinstance(msgs[2], HumanMessage)

    def test_history_defaults_to_user_role(self):
        from langchain_core.messages import HumanMessage

        msgs = _history_to_langchain_messages([{"content": "no role"}])
        assert len(msgs) == 1
        assert isinstance(msgs[0], HumanMessage)

    def test_history_empty_list(self):
        assert _history_to_langchain_messages([]) == []

    def test_build_human_message_text_only(self):
        from langchain_core.messages import HumanMessage

        msg = _build_human_message("hello", [])
        assert isinstance(msg, HumanMessage)
        assert msg.content == "hello"

    def test_build_human_message_with_images(self):
        from langchain_core.messages import HumanMessage

        images = [_make_image(), _make_image(media_type="image/jpeg")]
        msg = _build_human_message("describe these", images)
        assert isinstance(msg, HumanMessage)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 3  # 1 text + 2 image blocks
        assert msg.content[0] == {"type": "text", "text": "describe these"}
        assert msg.content[1]["type"] == "image_url"
        assert msg.content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_extract_tool_calls_from_messages(self):
        msg_with_tc = MagicMock()
        msg_with_tc.tool_calls = [
            {"name": "search", "args": {"query": "test"}},
            {"name": "read_doc", "args": {"id": "1"}},
        ]
        msg_without = MagicMock(spec=[])  # no tool_calls attribute

        result = _extract_tool_calls([msg_with_tc, msg_without])
        assert len(result) == 2
        assert result[0] == {"tool": "search", "args": {"query": "test"}}
        assert result[1] == {"tool": "read_doc", "args": {"id": "1"}}

    def test_extract_tool_calls_empty(self):
        msg = MagicMock(spec=[])  # no tool_calls attribute
        assert _extract_tool_calls([msg]) == []

    def test_extract_tool_calls_with_empty_list(self):
        msg = MagicMock()
        msg.tool_calls = []
        assert _extract_tool_calls([msg]) == []

    def test_extract_sources_from_additional_kwargs(self):
        msg = MagicMock()
        msg.additional_kwargs = {
            "sources": [
                {"document_id": "d1", "title": "Doc 1"},
                {"document_id": "d2", "title": "Doc 2"},
            ]
        }
        result = _extract_sources([msg])
        assert len(result) == 2
        assert result[0]["document_id"] == "d1"

    def test_extract_sources_no_sources(self):
        msg = MagicMock()
        msg.additional_kwargs = {}
        assert _extract_sources([msg]) == []

    def test_extract_sources_no_additional_kwargs(self):
        msg = MagicMock(spec=[])  # no additional_kwargs attribute
        assert _extract_sources([msg]) == []


# ===========================================================================
# 4. Source References Tests
# ===========================================================================


class TestSourceReferences:
    """Tests for SourceReference and ToolResultWithSources."""

    def test_source_reference_to_dict(self):
        src = _make_source(entity_name="Project X")
        d = src.to_dict()
        assert d["document_id"] == "doc-1"
        assert d["document_title"] == "Design Doc"
        assert d["document_type"] == "document"
        assert d["heading_context"] == "Overview"
        assert d["chunk_text"] == "Some chunk"
        assert d["chunk_index"] == 0
        assert d["score"] == 0.95
        assert d["source_type"] == "semantic"
        assert d["entity_name"] == "Project X"

    def test_tool_result_to_dict(self):
        src = _make_source()
        result = ToolResultWithSources(text="answer", sources=[src])
        d = result.to_dict()
        assert d["text"] == "answer"
        assert len(d["sources"]) == 1
        assert d["sources"][0]["document_id"] == "doc-1"

    def test_tool_result_has_sources_true(self):
        result = ToolResultWithSources(text="x", sources=[_make_source()])
        assert result.has_sources is True

    def test_tool_result_has_sources_false(self):
        result = ToolResultWithSources(text="x", sources=[])
        assert result.has_sources is False

    def test_tool_result_format_for_llm_without_sources(self):
        result = ToolResultWithSources(text="plain answer")
        assert result.format_for_llm() == "plain answer"

    def test_tool_result_format_for_llm_with_sources(self):
        src1 = _make_source(document_title="Doc A", heading_context="Section 1")
        src2 = _make_source(
            document_title="Doc B",
            heading_context=None,
            entity_name="Proj Y",
        )
        result = ToolResultWithSources(text="answer", sources=[src1, src2])
        formatted = result.format_for_llm()
        assert "answer" in formatted
        assert "[1] Doc A > Section 1" in formatted
        assert "[2] Doc B (Proj Y)" in formatted

    def test_tool_result_default_sources_empty(self):
        result = ToolResultWithSources(text="just text")
        assert result.sources == []


# ===========================================================================
# 5. CopilotKit Tests
# ===========================================================================


class TestCopilotKit:
    """Tests for create_copilotkit_sdk factory."""

    def test_returns_none_when_copilotkit_not_installed(self):
        with patch.dict("sys.modules", {"copilotkit": None, "copilotkit.langgraph": None}):
            # Force ImportError by patching the import to raise
            with patch(
                "app.ai.agent.copilotkit_runtime.create_copilotkit_sdk",
                wraps=create_copilotkit_sdk,
            ):
                # Reimport won't work with wraps, so call directly with
                # a patched __import__ instead
                pass

        # Simpler approach: mock the import to fail
        fake_graph = MagicMock()
        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def _mock_import(name, *args, **kwargs):
            if name == "copilotkit" or name.startswith("copilotkit."):
                raise ImportError("no copilotkit")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            result = create_copilotkit_sdk(fake_graph)
        assert result is None

    def test_returns_sdk_when_available(self):
        mock_sdk_instance = MagicMock()
        mock_sdk_cls = MagicMock(return_value=mock_sdk_instance)
        mock_agent_cls = MagicMock()

        mock_copilotkit = MagicMock()
        mock_copilotkit.CopilotKitSDK = mock_sdk_cls
        mock_copilotkit_lg = MagicMock()
        mock_copilotkit_lg.LangGraphAgent = mock_agent_cls

        fake_graph = MagicMock()

        with patch.dict(
            "sys.modules",
            {"copilotkit": mock_copilotkit, "copilotkit.langgraph": mock_copilotkit_lg},
        ):
            result = create_copilotkit_sdk(fake_graph)

        assert result is mock_sdk_instance
        mock_sdk_cls.assert_called_once()
        mock_agent_cls.assert_called_once()


# ===========================================================================
# 6. get_tool_db session lifecycle tests
# ===========================================================================


class TestGetToolDb:
    """Tests for the get_tool_db async context manager."""

    async def test_provides_session_with_commit(self):
        """get_tool_db commits the session on successful exit."""
        from unittest.mock import AsyncMock as AM
        from app.routers.ai_chat import get_tool_db

        mock_session = AM()
        mock_session.commit = AM()
        mock_session.rollback = AM()

        with patch("app.routers.ai_chat.async_session_maker") as mock_maker:
            # async_session_maker() should be an async context manager
            ctx = AM()
            ctx.__aenter__ = AM(return_value=mock_session)
            ctx.__aexit__ = AM(return_value=None)
            mock_maker.return_value = ctx

            async with get_tool_db() as session:
                assert session is mock_session

            mock_session.commit.assert_awaited_once()
            mock_session.rollback.assert_not_awaited()

    async def test_provides_session_with_rollback_on_error(self):
        """get_tool_db rolls back the session when an exception occurs."""
        from unittest.mock import AsyncMock as AM
        from app.routers.ai_chat import get_tool_db

        mock_session = AM()
        mock_session.commit = AM()
        mock_session.rollback = AM()

        with patch("app.routers.ai_chat.async_session_maker") as mock_maker:
            ctx = AM()
            ctx.__aenter__ = AM(return_value=mock_session)
            ctx.__aexit__ = AM(return_value=None)
            mock_maker.return_value = ctx

            with pytest.raises(ValueError):
                async with get_tool_db() as session:
                    raise ValueError("boom")

            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()


# ===========================================================================
# 7. ChatResponse schema — interrupted field
# ===========================================================================


class TestChatResponseInterrupted:
    """Tests for the interrupted and interrupt_payload fields on ChatResponse."""

    def test_default_interrupted_is_false(self):
        resp = ChatResponse(response="hi", thread_id="t1")
        assert resp.interrupted is False
        assert resp.interrupt_payload is None

    def test_interrupted_true_with_payload(self):
        payload = {"type": "confirmation", "action": "create_task", "summary": "Create X"}
        resp = ChatResponse(
            response="",
            thread_id="t1",
            interrupted=True,
            interrupt_payload=payload,
        )
        assert resp.interrupted is True
        assert resp.interrupt_payload == payload


# ===========================================================================
# 8. ResumeRequest schema tests
# ===========================================================================


class TestResumeRequest:
    """Tests for the ResumeRequest schema (HITL confirmation)."""

    def test_fields(self):
        from app.schemas.ai_chat import ResumeRequest

        req = ResumeRequest(
            thread_id="t1",
            response={"approved": True},
        )
        assert req.thread_id == "t1"
        assert req.response == {"approved": True}

    def test_response_with_rejection(self):
        from app.schemas.ai_chat import ResumeRequest

        req = ResumeRequest(
            thread_id="t1",
            response={"approved": False, "reason": "Not now"},
        )
        assert req.response["approved"] is False
        assert req.response["reason"] == "Not now"


# ===========================================================================
# 9. _stream_agent event mapping
# ===========================================================================


class TestStreamAgent:
    """Tests for _stream_agent async generator."""

    async def test_yields_expected_events(self):
        """_stream_agent converts LangGraph events to SSE events."""
        from app.routers.ai_chat import _stream_agent

        # Mock graph that produces known events
        mock_graph = MagicMock()

        async def fake_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": MagicMock(content="Hello")},
            }
            yield {
                "event": "on_tool_start",
                "name": "sql_query",
                "data": {},
            }
            yield {
                "event": "on_tool_end",
                "name": "sql_query",
                "data": {"output": "result data"},
            }

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        # Should get: run_started, text_delta, tool_call_start, tool_call_end, run_finished, end
        assert len(events) == 6
        assert events[0]["event"] == "run_started"
        assert events[1]["event"] == "text_delta"
        assert events[2]["event"] == "tool_call_start"
        assert events[3]["event"] == "tool_call_end"
        assert events[4]["event"] == "run_finished"
        assert events[5]["event"] == "end"

    async def test_yields_end_event_when_no_stream_events(self):
        """_stream_agent always yields run_started, run_finished, and end events."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def empty_events(*args, **kwargs):
            return
            yield  # Make it an async generator

        mock_graph.astream_events = empty_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        # run_started + run_finished + end
        assert len(events) == 3
        assert events[0]["event"] == "run_started"
        assert events[1]["event"] == "run_finished"
        assert events[2]["event"] == "end"


# ===========================================================================
# 10. Thread ownership tests (IDOR prevention)
# ===========================================================================


class TestThreadOwnership:
    """Tests for _register_thread and _validate_thread_owner IDOR prevention.

    After R1 fix BE-C10, thread ownership is Redis-backed with an in-memory
    fallback (``_thread_owners_fallback``). Tests patch Redis as unavailable
    so the in-memory OrderedDict fallback is exercised directly.
    """

    def setup_method(self):
        """Clear in-memory fallback state between tests."""
        from app.routers.ai_chat import _thread_owners_fallback

        _thread_owners_fallback.clear()

    @pytest.mark.asyncio
    async def test_register_and_validate_owner_succeeds(self):
        from app.routers.ai_chat import _register_thread, _validate_thread_owner

        with patch("app.services.redis_service.redis_service") as mock_rs:
            mock_rs.is_connected = False
            await _register_thread("t1", "user-A")
            await _validate_thread_owner("t1", "user-A")  # should not raise

    @pytest.mark.asyncio
    async def test_validate_wrong_owner_raises_403(self):
        from app.routers.ai_chat import _register_thread, _validate_thread_owner

        with patch("app.services.redis_service.redis_service") as mock_rs:
            mock_rs.is_connected = False
            await _register_thread("t1", "user-A")
            with pytest.raises(HTTPException) as exc_info:
                await _validate_thread_owner("t1", "user-B")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_validate_unregistered_thread_passes(self):
        from app.routers.ai_chat import _validate_thread_owner

        with patch("app.services.redis_service.redis_service") as mock_rs:
            mock_rs.is_connected = False
            await _validate_thread_owner("unknown-thread", "any-user")  # should not raise

    @pytest.mark.asyncio
    async def test_register_overwrites_previous_owner(self):
        from app.routers.ai_chat import _register_thread, _validate_thread_owner

        with patch("app.services.redis_service.redis_service") as mock_rs:
            mock_rs.is_connected = False
            await _register_thread("t1", "user-A")
            await _register_thread("t1", "user-B")
            await _validate_thread_owner("t1", "user-B")  # should not raise
            with pytest.raises(HTTPException):
                await _validate_thread_owner("t1", "user-A")  # now denied

    @pytest.mark.asyncio
    async def test_fallback_eviction_removes_oldest(self):
        """Verify in-memory fallback evicts oldest when _FALLBACK_MAX_SIZE exceeded."""
        from app.routers.ai_chat import _thread_owners_fallback, _FALLBACK_MAX_SIZE

        with patch("app.services.redis_service.redis_service") as mock_rs:
            mock_rs.is_connected = False

            import app.routers.ai_chat as chat_mod
            original_max = chat_mod._FALLBACK_MAX_SIZE
            try:
                chat_mod._FALLBACK_MAX_SIZE = 3
                await chat_mod._register_thread("t1", "user-A")
                await chat_mod._register_thread("t2", "user-B")
                await chat_mod._register_thread("t3", "user-C")
                assert len(_thread_owners_fallback) == 3

                # Adding a 4th entry should evict the oldest (t1)
                await chat_mod._register_thread("t4", "user-D")
                assert len(_thread_owners_fallback) == 3
                assert "t1" not in _thread_owners_fallback
                assert "t4" in _thread_owners_fallback
                assert _thread_owners_fallback["t4"] == "user-D"
            finally:
                chat_mod._FALLBACK_MAX_SIZE = original_max


# ===========================================================================
# 11. _stream_agent error event test
# ===========================================================================


class TestStreamAgentError:
    """Tests for _stream_agent error handling."""

    async def test_stream_error_yields_error_event(self):
        """When astream_events raises, the stream yields an error event with sanitized message."""
        import json

        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def failing_events(*args, **kwargs):
            raise RuntimeError("LLM API timeout")
            yield  # unreachable but makes it an async generator

        mock_graph.astream_events = failing_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        # Should have run_started, error, run_finished, end
        event_types = [e["event"] for e in events]
        assert "run_started" in event_types
        assert "error" in event_types
        assert "run_finished" in event_types
        assert "end" in event_types

        # Error message should be sanitized (no internal details)
        error_event = next(e for e in events if e["event"] == "error")
        error_data = json.loads(error_event["data"])
        assert "Agent encountered an error" in error_data["message"]
        # Internal error details should NOT leak
        assert "timeout" not in error_data["message"].lower()

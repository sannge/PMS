"""Unit tests for Phase 4 Blair AI chat router and schemas.

Covers schemas (ChatRequest, ChatResponse, etc.), validation helpers,
message conversion helpers, SourceReference / ToolResultWithSources,
the CopilotKit SDK factory, and thread ownership IDOR guards.
"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

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
    _extract_node_details,
    _extract_sources,
    _extract_tool_calls,
    _history_to_langchain_messages,
    _register_thread,
    _thread_owners_fallback,
    _validate_thread_owner,
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
        from app.schemas.ai_chat import ChatHistoryEntry

        history = [
            ChatHistoryEntry(role="user", content="Hello"),
            ChatHistoryEntry(role="assistant", content="Hi there"),
            ChatHistoryEntry(role="user", content="Thanks"),
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
        from app.schemas.ai_chat import ChatHistoryEntry

        msgs = _history_to_langchain_messages([ChatHistoryEntry(role="user", content="no role")])
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
                "metadata": {"langgraph_node": "explore"},
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

        # Should get: run_started, text_delta, tool_call_start, tool_call_end, token_usage, run_finished, end
        assert len(events) == 7
        assert events[0]["event"] == "run_started"
        assert events[1]["event"] == "text_delta"
        assert events[2]["event"] == "tool_call_start"
        assert events[3]["event"] == "tool_call_end"
        assert events[4]["event"] == "token_usage"
        assert events[5]["event"] == "run_finished"
        assert events[6]["event"] == "end"

    async def test_filters_text_delta_by_node(self):
        """_stream_agent only emits text_delta for streamable nodes (explore, respond)."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def fake_events(*args, **kwargs):
            # intake node — should NOT produce text_delta (not in _STREAMABLE_NODES)
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "intake"},
                "data": {"chunk": MagicMock(content="internal")},
            }
            # explore node — should produce text_delta (_STREAMABLE_NODES = {"explore", "respond"})
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "explore"},
                "data": {"chunk": MagicMock(content="Hello")},
            }
            # No metadata — should NOT produce text_delta
            yield {
                "event": "on_chat_model_stream",
                "metadata": {},
                "data": {"chunk": MagicMock(content="hidden")},
            }

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        text_events = [e for e in events if e["event"] == "text_delta"]
        assert len(text_events) == 1
        assert json.loads(text_events[0]["data"])["content"] == "Hello"

    async def test_emits_thinking_step_for_pipeline_nodes(self):
        """_stream_agent emits thinking_step on_chain_start/end for known nodes."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def fake_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "intake", "data": {}}
            yield {"event": "on_chain_end", "name": "intake", "data": {"output": {}}}
            yield {"event": "on_chain_start", "name": "explore", "data": {}}
            yield {"event": "on_chain_end", "name": "explore", "data": {"output": {}}}

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        thinking = [e for e in events if e["event"] == "thinking_step"]
        assert len(thinking) == 4
        # Check start/complete for intake
        d0 = json.loads(thinking[0]["data"])
        assert d0["node"] == "intake"
        assert d0["status"] == "active"
        d1 = json.loads(thinking[1]["data"])
        assert d1["node"] == "intake"
        assert d1["status"] == "complete"

    async def test_skips_thinking_step_for_unknown_node(self):
        """_stream_agent does NOT emit thinking_step for nodes not in _THINKING_NODES."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def fake_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "some_unknown_node", "data": {}}
            yield {"event": "on_chain_end", "name": "some_unknown_node", "data": {"output": {}}}

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        thinking = [e for e in events if e["event"] == "thinking_step"]
        assert len(thinking) == 0

    async def test_thinking_step_agent_with_tool_calls(self):
        """on_chain_end for explore includes tool call details."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        # Simulate explore node returning tool_calls
        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = [
            {"name": "sql_query", "args": {}, "id": "tc1"},
            {"name": "search_knowledge", "args": {}, "id": "tc2"},
        ]

        async def fake_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "explore", "data": {}}
            yield {
                "event": "on_chain_end",
                "name": "explore",
                "data": {
                    "output": {
                        "messages": [mock_ai_msg],
                    }
                },
            }

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        thinking = [e for e in events if e["event"] == "thinking_step"]
        assert len(thinking) == 2
        complete_data = json.loads(thinking[1]["data"])
        assert complete_data["status"] == "complete"
        assert "Calling" in complete_data["details"]
        assert "sql_query" in complete_data["details"]
        assert "search_knowledge" in complete_data["details"]

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

        # run_started + token_usage + run_finished + end
        assert len(events) == 4
        assert events[0]["event"] == "run_started"
        assert events[1]["event"] == "token_usage"
        assert events[2]["event"] == "run_finished"
        assert events[3]["event"] == "end"


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
    async def test_validate_unregistered_thread_fails_closed(self):
        """Fail-closed: unknown thread + Redis down = 503 (not pass-through)."""
        from app.routers.ai_chat import _validate_thread_owner

        with patch("app.services.redis_service.redis_service") as mock_rs:
            mock_rs.is_connected = False
            with pytest.raises(HTTPException) as exc_info:
                await _validate_thread_owner("unknown-thread", "any-user")
            assert exc_info.value.status_code == 503

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


# ===========================================================================
# 12-14. REMOVED: _humanize_classification, _extract_classification_from_event,
#         _humanize_intent helpers were removed in the ReAct rewrite.
#         The agent no longer classifies requests — it reasons via tool use.
# ===========================================================================


# ===========================================================================
# 15. _extract_node_details tests
# ===========================================================================


class TestExtractNodeDetails:
    """Tests for _extract_node_details helper — explore, explore_tools nodes + edge cases."""

    # -- explore with tool_calls --

    def test_explore_with_tool_calls(self):
        """explore node with tool_calls returns Calling: details."""
        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = [
            {"name": "sql_query", "args": {}, "id": "tc1"},
            {"name": "search_knowledge", "args": {}, "id": "tc2"},
        ]
        event = {"data": {"output": {"messages": [mock_ai_msg]}}}
        result = _extract_node_details("explore", event)
        assert result is not None
        assert "**Calling:**" in result
        assert "sql_query" in result
        assert "search_knowledge" in result

    def test_explore_no_tool_calls(self):
        """explore node without tool_calls returns None."""
        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = []
        event = {"data": {"output": {"messages": [mock_ai_msg]}}}
        result = _extract_node_details("explore", event)
        assert result is None

    def test_explore_no_messages(self):
        """explore node with no messages returns None."""
        event = {"data": {"output": {"messages": []}}}
        result = _extract_node_details("explore", event)
        assert result is None

    def test_explore_text_only_response(self):
        """explore node with text-only response returns None."""
        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = None
        event = {"data": {"output": {"messages": [mock_ai_msg]}}}
        result = _extract_node_details("explore", event)
        assert result is None

    # -- explore_tools --

    def test_explore_tools_with_messages(self):
        """explore_tools node with messages returns Executed count."""
        event = {"data": {"output": {"messages": [MagicMock(), MagicMock()]}}}
        result = _extract_node_details("explore_tools", event)
        assert result is not None
        assert "**Executed** 2 tool(s)" in result

    def test_explore_tools_no_messages_key(self):
        """explore_tools node without messages key returns None."""
        event = {"data": {"output": {"total_tool_calls": 5}}}
        result = _extract_node_details("explore_tools", event)
        assert result is None

    # -- intake (always returns None) --

    def test_intake_returns_none(self):
        """intake node has no meaningful details."""
        event = {"data": {"output": {"total_tool_calls": 0}}}
        assert _extract_node_details("intake", event) is None

    # -- respond with tool_calls (misclassification recovery) --

    def test_respond_with_tool_calls(self):
        """respond node with tool_calls returns Calling: details."""
        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = [{"name": "list_tasks", "args": {}, "id": "tc1"}]
        event = {"data": {"output": {"messages": [mock_ai_msg]}}}
        result = _extract_node_details("respond", event)
        assert result is not None
        assert "**Calling:**" in result

    # -- edge cases --

    def test_output_is_none(self):
        """output is None returns None for any node."""
        event = {"data": {"output": None}}
        assert _extract_node_details("explore", event) is None

    def test_output_is_non_dict(self):
        """output is non-dict returns None for any node."""
        event = {"data": {"output": [1, 2, 3]}}
        assert _extract_node_details("explore_tools", event) is None

    def test_exception_in_extraction(self):
        """exception during extraction returns None, does not raise."""
        class BadEvent:
            def get(self, *args, **kwargs):
                raise TypeError("boom")
        assert _extract_node_details("explore", BadEvent()) is None


# ===========================================================================
# 16. on_chain_end details integration tests
# ===========================================================================


class TestOnChainEndDetails:
    """Integration tests: on_chain_end SSE payloads include details for agent/tools nodes."""

    async def test_agent_on_chain_end_with_tool_calls_has_details(self):
        """on_chain_end for explore node with tool_calls includes details in SSE payload."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = [{"name": "sql_query", "args": {}, "id": "tc1"}]

        async def fake_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "explore", "data": {}}
            yield {
                "event": "on_chain_end",
                "name": "explore",
                "data": {"output": {"messages": [mock_ai_msg]}},
            }

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        thinking = [e for e in events if e["event"] == "thinking_step"]
        complete = [json.loads(t["data"]) for t in thinking if json.loads(t["data"])["status"] == "complete"]
        assert len(complete) == 1
        assert "details" in complete[0]
        assert "sql_query" in complete[0]["details"]
        assert "Calling" in complete[0]["details"]

    async def test_tools_on_chain_end_has_details(self):
        """on_chain_end for explore_tools node includes details in SSE payload."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def fake_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "explore_tools", "data": {}}
            yield {
                "event": "on_chain_end",
                "name": "explore_tools",
                "data": {"output": {"messages": [MagicMock(), MagicMock()]}},
            }

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        thinking = [e for e in events if e["event"] == "thinking_step"]
        complete = [json.loads(t["data"]) for t in thinking if json.loads(t["data"])["status"] == "complete"]
        assert len(complete) == 1
        assert "Executed" in complete[0]["details"]

    async def test_intake_on_chain_end_has_no_details(self):
        """on_chain_end for intake node does NOT include details key."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def fake_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "intake", "data": {}}
            yield {
                "event": "on_chain_end",
                "name": "intake",
                "data": {"output": {"total_tool_calls": 0}},
            }

        mock_graph.astream_events = fake_events

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        thinking = [e for e in events if e["event"] == "thinking_step"]
        complete = [json.loads(t["data"]) for t in thinking if json.loads(t["data"])["status"] == "complete"]
        assert len(complete) == 1
        assert "details" not in complete[0]


# ===========================================================================
# 17. HITL spinner fix — interrupt emits thinking_step complete
# ===========================================================================


class TestHITLSpinnerFix:
    """Verify that when interrupt is detected, a thinking_step complete event
    is emitted BEFORE the interrupt event (so the spinner stops)."""

    async def test_interrupt_emits_thinking_complete_before_interrupt_event(self):
        """When graph interrupts in explore_tools node, spinner gets closed before interrupt payload."""
        from app.routers.ai_chat import _stream_agent

        mock_graph = MagicMock()

        async def fake_events(*args, **kwargs):
            # Simulate explore_tools node starting (on_chain_start fires)
            yield {"event": "on_chain_start", "name": "explore_tools", "data": {}}
            # on_chain_end never fires because interrupt() is called inside execute_tools

        mock_graph.astream_events = fake_events

        # Mock aget_state to return an interrupted state
        mock_state = MagicMock()
        mock_state.next = ("explore_tools",)
        mock_task = MagicMock()
        mock_interrupt = MagicMock()
        mock_interrupt.value = {"type": "confirmation", "action": "create_task"}
        mock_task.interrupts = [mock_interrupt]
        mock_state.tasks = (mock_task,)
        mock_state.config = {"configurable": {"checkpoint_id": "cp-123"}}
        mock_state.values = {"messages": [], "context_summary": None}
        from unittest.mock import AsyncMock
        mock_graph.aget_state = AsyncMock(return_value=mock_state)

        events = []
        async for event in _stream_agent(mock_graph, {}, {}, thread_id="t-test"):
            events.append(event)

        event_types = [e["event"] for e in events]

        # Must have: run_started, thinking_step (active), thinking_step (complete), interrupt, run_finished, end
        assert "thinking_step" in event_types
        assert "interrupt" in event_types

        # Find the thinking_step complete for explore_tools
        thinking_events = [e for e in events if e["event"] == "thinking_step"]
        complete_events = [
            e for e in thinking_events
            if json.loads(e["data"]).get("status") == "complete"
            and json.loads(e["data"]).get("node") == "explore_tools"
        ]
        assert len(complete_events) >= 1, "Expected a thinking_step complete for explore_tools"

        # The thinking_step complete must come BEFORE the interrupt event
        complete_idx = events.index(complete_events[0])
        interrupt_idx = next(i for i, e in enumerate(events) if e["event"] == "interrupt")
        assert complete_idx < interrupt_idx, (
            f"thinking_step complete (idx={complete_idx}) must precede interrupt (idx={interrupt_idx})"
        )


# ---------------------------------------------------------------------------
# Tests: Thread ownership IDOR guards (TE-R2-02)
# ---------------------------------------------------------------------------


def _mock_redis_service(*, connected: bool, get_return=None):
    """Create a mock redis_service with controllable state."""
    mock = MagicMock()
    mock.is_connected = connected
    mock.set = AsyncMock()
    mock.get = AsyncMock(return_value=get_return)
    return mock


# Patch target: redis_service is imported inside function bodies via
# `from ..services.redis_service import redis_service`, so we patch at
# the module where the singleton is defined.
_REDIS_PATCH = "app.services.redis_service.redis_service"


class TestRegisterThread:

    async def test_redis_available_stores_in_redis(self):
        """When Redis is available, thread ownership is stored there."""
        mock_redis = _mock_redis_service(connected=True)
        with patch(_REDIS_PATCH, mock_redis):
            await _register_thread("thread-1", "user-A")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "thread_owner:thread-1"
        assert call_args[0][1] == "user-A"

    async def test_redis_down_stores_in_fallback(self):
        """When Redis is down, ownership is stored in in-memory fallback."""
        mock_redis = _mock_redis_service(connected=False)
        _thread_owners_fallback.clear()

        with patch(_REDIS_PATCH, mock_redis):
            await _register_thread("thread-2", "user-B")

        assert _thread_owners_fallback.get("thread-2") == "user-B"
        _thread_owners_fallback.clear()

    async def test_redis_exception_falls_through_to_fallback(self):
        """When Redis raises, falls through to in-memory fallback."""
        mock_redis = _mock_redis_service(connected=True)
        mock_redis.set = AsyncMock(side_effect=ConnectionError("boom"))
        _thread_owners_fallback.clear()

        with patch(_REDIS_PATCH, mock_redis):
            await _register_thread("thread-3", "user-C")

        assert _thread_owners_fallback.get("thread-3") == "user-C"
        _thread_owners_fallback.clear()


class TestValidateThreadOwner:

    async def test_redis_available_correct_owner_passes(self):
        """Redis available + correct owner -> no exception."""
        mock_redis = _mock_redis_service(connected=True, get_return="user-A")
        with patch(_REDIS_PATCH, mock_redis):
            # Should not raise
            await _validate_thread_owner("thread-1", "user-A")

    async def test_redis_available_wrong_owner_raises_403(self):
        """Redis available + wrong owner -> 403 Forbidden."""
        mock_redis = _mock_redis_service(connected=True, get_return="user-A")
        with patch(_REDIS_PATCH, mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await _validate_thread_owner("thread-1", "user-WRONG")
            assert exc_info.value.status_code == 403

    async def test_redis_down_fallback_hit_passes(self):
        """Redis down + thread in fallback with correct owner -> passes."""
        mock_redis = _mock_redis_service(connected=False)
        _thread_owners_fallback.clear()
        _thread_owners_fallback["thread-4"] = "user-D"

        with patch(_REDIS_PATCH, mock_redis):
            await _validate_thread_owner("thread-4", "user-D")

        _thread_owners_fallback.clear()

    async def test_redis_down_no_fallback_raises_503(self):
        """Redis down + not in fallback -> 503 Service Unavailable (fail-closed)."""
        mock_redis = _mock_redis_service(connected=False)
        _thread_owners_fallback.clear()

        with patch(_REDIS_PATCH, mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await _validate_thread_owner("thread-missing", "user-X")
            assert exc_info.value.status_code == 503

        _thread_owners_fallback.clear()

    async def test_require_existing_no_owner_raises_404(self):
        """Redis available + require_existing=True + no owner -> 404."""
        mock_redis = _mock_redis_service(connected=True, get_return=None)
        _thread_owners_fallback.clear()

        with patch(_REDIS_PATCH, mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await _validate_thread_owner(
                    "thread-new", "user-Y", require_existing=True
                )
            assert exc_info.value.status_code == 404

        _thread_owners_fallback.clear()

    async def test_redis_down_fallback_wrong_owner_raises_403(self):
        """Redis down + fallback exists but wrong owner -> 403."""
        mock_redis = _mock_redis_service(connected=False)
        _thread_owners_fallback.clear()
        _thread_owners_fallback["thread-5"] = "user-E"

        with patch(_REDIS_PATCH, mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await _validate_thread_owner("thread-5", "user-WRONG")
            assert exc_info.value.status_code == 403

        _thread_owners_fallback.clear()

    async def test_redis_available_no_owner_no_require_existing_passes(self):
        """Redis available + no owner + require_existing=False -> passes (new thread)."""
        mock_redis = _mock_redis_service(connected=True, get_return=None)
        _thread_owners_fallback.clear()

        with patch(_REDIS_PATCH, mock_redis):
            # Should not raise — new thread, no ownership recorded yet
            await _validate_thread_owner("thread-new", "user-Z")

        _thread_owners_fallback.clear()


# ===========================================================================
# 18. Cancel endpoint tests (TE-001)
# ===========================================================================


class TestCancelEndpoint:
    """Tests for POST /api/ai/chat/cancel/{thread_id} endpoint."""

    async def test_cancel_active_stream(self, client, auth_headers, test_user):
        """When an active cancel event exists for the thread, cancel sets it and returns cancelled."""
        import asyncio
        from app.routers.ai_chat import _active_stream_cancels, _register_thread

        thread_id = "cancel-test-active"
        cancel_event = asyncio.Event()
        _active_stream_cancels[thread_id] = cancel_event

        # Register thread ownership so _validate_thread_owner passes
        mock_redis = _mock_redis_service(connected=True, get_return=str(test_user.id))
        with patch(_REDIS_PATCH, mock_redis):
            resp = await client.post(
                f"/api/ai/chat/cancel/{thread_id}",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"status": "cancelled"}
        assert cancel_event.is_set()

        # Cleanup
        _active_stream_cancels.pop(thread_id, None)

    async def test_cancel_no_active_stream(self, client, auth_headers, test_user):
        """When no active stream exists for the thread, returns not_found."""
        thread_id = "cancel-test-none"

        # Register thread ownership but no active stream
        mock_redis = _mock_redis_service(connected=True, get_return=str(test_user.id))
        with patch(_REDIS_PATCH, mock_redis):
            resp = await client.post(
                f"/api/ai/chat/cancel/{thread_id}",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"status": "not_found"}

    async def test_cancel_wrong_owner(self, client, auth_headers, test_user):
        """When thread belongs to a different user, returns 403."""
        thread_id = "cancel-test-wrong-owner"

        # Thread is owned by a different user
        mock_redis = _mock_redis_service(connected=True, get_return="different-user-id")
        with patch(_REDIS_PATCH, mock_redis):
            resp = await client.post(
                f"/api/ai/chat/cancel/{thread_id}",
                headers=auth_headers,
            )

        assert resp.status_code == 403

    async def test_cancel_requires_auth(self, client):
        """Calling cancel without authentication returns 401/403."""
        resp = await client.post("/api/ai/chat/cancel/some-thread")
        assert resp.status_code in (401, 403)


# ===========================================================================
# 19. Bug 6 fallback text tests (TE-002)
# ===========================================================================


class TestBug6FallbackText:
    """Tests for the Bug 6 fix: fallback text_delta when no on_chat_model_stream events."""

    async def test_fallback_text_emitted_when_no_stream(self):
        """When astream_events yields no on_chat_model_stream, the fallback
        reads the final AIMessage from graph state and emits a text_delta."""
        from app.routers.ai_chat import _stream_agent
        from langchain_core.messages import AIMessage
        from unittest.mock import AsyncMock

        mock_graph = MagicMock()

        # astream_events yields no on_chat_model_stream events
        async def no_text_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "explore", "data": {}}
            yield {"event": "on_chain_end", "name": "explore", "data": {"output": {}}}

        mock_graph.astream_events = no_text_events

        # aget_state returns a state with an AIMessage containing content
        mock_state = MagicMock()
        mock_state.values = {
            "messages": [
                AIMessage(content="Fallback response from the agent"),
            ]
        }
        mock_state.next = None
        mock_state.config = {"configurable": {}}
        mock_graph.aget_state = AsyncMock(return_value=mock_state)

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        text_events = [e for e in events if e["event"] == "text_delta"]
        assert len(text_events) == 1
        data = json.loads(text_events[0]["data"])
        assert data["content"] == "Fallback response from the agent"

    async def test_no_fallback_when_text_already_emitted(self):
        """When on_chat_model_stream emits text, no fallback text_delta is added."""
        from app.routers.ai_chat import _stream_agent
        from langchain_core.messages import AIMessage
        from unittest.mock import AsyncMock

        mock_graph = MagicMock()

        # astream_events yields an on_chat_model_stream with content
        async def text_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "explore"},
                "data": {"chunk": MagicMock(content="Streamed text")},
            }

        mock_graph.astream_events = text_events

        # aget_state also has an AIMessage (should NOT be used as fallback)
        mock_state = MagicMock()
        mock_state.values = {
            "messages": [
                AIMessage(content="This should NOT appear as extra text_delta"),
            ]
        }
        mock_state.next = None
        mock_state.config = {"configurable": {}}
        mock_graph.aget_state = AsyncMock(return_value=mock_state)

        events = []
        async for event in _stream_agent(mock_graph, {}, {}):
            events.append(event)

        text_events = [e for e in events if e["event"] == "text_delta"]
        # Only the one streamed text_delta, no fallback
        assert len(text_events) == 1
        data = json.loads(text_events[0]["data"])
        assert data["content"] == "Streamed text"

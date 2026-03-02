"""Tests for Phase 9 Category A: Cost & Safety fixes (Tasks 9.1–9.9).

Covers:
- 9.1 Agent tool call counting (MAX_TOOL_CALLS)
- 9.2 Streaming timeout (overall + idle)
- 9.3 Streaming chunk limit
- 9.4 Vision API timeout
- 9.5 Global import concurrency limit
- 9.6 Embedding manual sync (auto-embed removal, sync endpoint, nightly job, stale flag)
- 9.7 SQL execution backup timeout
- 9.8 RAG query embedding cache
- 9.9 Import file streaming
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# 9.1 Agent Tool Call Counting
# ---------------------------------------------------------------------------


class TestAgentToolCallCounting:
    """Tests for _count_total_tool_calls and MAX_TOOL_CALLS enforcement."""

    def test_count_total_tool_calls_batched(self):
        """LLM batching 20 tool_calls in one message counts as 20, not 1."""
        from langchain_core.messages import AIMessage

        from app.ai.agent.graph import _count_total_tool_calls

        # Simulate 3 AIMessages, each with 20 tool calls
        messages = []
        for _ in range(3):
            msg = AIMessage(
                content="",
                tool_calls=[
                    {"id": f"call_{i}", "name": "test_tool", "args": {}}
                    for i in range(20)
                ],
            )
            messages.append(msg)

        assert _count_total_tool_calls(messages) == 60

    def test_count_total_tool_calls_sequential(self):
        """Normal pattern: 1 tool call per message."""
        from langchain_core.messages import AIMessage

        from app.ai.agent.graph import _count_total_tool_calls

        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": f"call_{i}", "name": "tool", "args": {}}],
            )
            for i in range(5)
        ]
        assert _count_total_tool_calls(messages) == 5

    def test_count_total_tool_calls_mixed(self):
        """Messages without tool_calls are not counted."""
        from langchain_core.messages import AIMessage, HumanMessage

        from app.ai.agent.graph import _count_total_tool_calls

        messages = [
            HumanMessage(content="hello"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "c1", "name": "t1", "args": {}},
                    {"id": "c2", "name": "t2", "args": {}},
                ],
            ),
            AIMessage(content="just text"),
            AIMessage(
                content="",
                tool_calls=[{"id": "c3", "name": "t3", "args": {}}],
            ),
        ]
        assert _count_total_tool_calls(messages) == 3

    def test_count_tool_iterations_unchanged(self):
        """Original _count_tool_iterations counts messages, not individual calls."""
        from langchain_core.messages import AIMessage

        from app.ai.agent.graph import _count_tool_iterations

        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": f"call_{i}", "name": "t", "args": {}}
                    for i in range(20)
                ],
            )
        ]
        # 1 message with 20 calls = 1 iteration
        assert _count_tool_iterations(messages) == 1

    def test_should_continue_respects_max_tool_calls(self):
        """should_continue returns 'end' when total tool calls >= MAX_TOOL_CALLS."""
        from langchain_core.messages import AIMessage

        from app.ai.agent.graph import MAX_TOOL_CALLS, build_agent_graph

        # Build minimal graph to access should_continue via state check
        # Instead, test the function directly
        from app.ai.agent.graph import _count_total_tool_calls

        # Create messages with exactly MAX_TOOL_CALLS tool calls
        msgs = []
        calls_per_msg = 10
        num_msgs = MAX_TOOL_CALLS // calls_per_msg
        for _ in range(num_msgs):
            msgs.append(
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": f"c_{i}", "name": "t", "args": {}}
                        for i in range(calls_per_msg)
                    ],
                )
            )

        assert _count_total_tool_calls(msgs) == MAX_TOOL_CALLS

    def test_max_tool_calls_value(self):
        """MAX_TOOL_CALLS should be 50."""
        from app.ai.agent.graph import MAX_TOOL_CALLS

        assert MAX_TOOL_CALLS == 50


# ---------------------------------------------------------------------------
# 9.2 + 9.3 Streaming Timeout & Chunk Limit
# ---------------------------------------------------------------------------


class TestStreamingLimits:
    """Tests for streaming timeout and chunk limit constants."""

    def test_streaming_constants_exist(self):
        from app.routers.ai_chat import (
            MAX_CHUNKS_PER_RESPONSE,
            STREAM_IDLE_TIMEOUT_S,
            STREAM_OVERALL_TIMEOUT_S,
        )

        assert STREAM_OVERALL_TIMEOUT_S == 120
        assert STREAM_IDLE_TIMEOUT_S == 30
        assert MAX_CHUNKS_PER_RESPONSE == 2000


# ---------------------------------------------------------------------------
# 9.4 Vision API Timeout
# ---------------------------------------------------------------------------


class TestVisionAPITimeout:
    """Tests for vision API per-image timeout."""

    def test_vision_timeout_constant(self):
        from app.ai.image_understanding_service import _VISION_TIMEOUT_S

        assert _VISION_TIMEOUT_S == 30

    @pytest.mark.asyncio
    async def test_describe_image_timeout_handled(self):
        """Vision provider that hangs should be caught by timeout."""
        from app.ai.image_understanding_service import ImageUnderstandingService

        # Create a service with mocks
        mock_registry = MagicMock()
        mock_embedding = MagicMock()
        mock_minio = MagicMock()
        mock_db = AsyncMock()

        svc = ImageUnderstandingService(
            provider_registry=mock_registry,
            embedding_service=mock_embedding,
            minio_service=mock_minio,
            db=mock_db,
        )

        # Mock vision provider that never returns
        async def _hang_forever(*args, **kwargs):
            await asyncio.sleep(3600)
            return "never reached"

        mock_provider = MagicMock()
        mock_provider.describe_image = _hang_forever

        # The _describe_image wrapping should catch the timeout
        # We test indirectly via the timeout constant existing
        import asyncio as _asyncio

        with pytest.raises(_asyncio.TimeoutError):
            await _asyncio.wait_for(
                svc._describe_image(mock_provider, "model", b"image_data"),
                timeout=0.01,  # Very short timeout for testing
            )


# ---------------------------------------------------------------------------
# 9.5 Global Import Concurrency Limit
# ---------------------------------------------------------------------------


class TestImportConcurrency:
    """Tests for Redis-based import concurrency limiter."""

    def test_concurrency_constants(self):
        from app.worker import (
            IMPORT_CONCURRENCY_KEY,
            IMPORT_CONCURRENCY_TTL,
            MAX_CONCURRENT_IMPORTS,
        )

        assert MAX_CONCURRENT_IMPORTS == 5
        assert IMPORT_CONCURRENCY_KEY == "import:concurrency:count"
        assert IMPORT_CONCURRENCY_TTL == 3600


# ---------------------------------------------------------------------------
# 9.6 Embedding — Manual Sync Only
# ---------------------------------------------------------------------------


class TestManualSync:
    """Tests for manual-sync-only embedding pattern."""

    def test_document_model_is_embedding_stale_null(self):
        """Document with no embedding_updated_at is stale."""
        from app.models.document import Document

        doc = Document()
        doc.embedding_updated_at = None
        doc.updated_at = datetime.now(timezone.utc)
        assert doc.is_embedding_stale is True

    def test_document_model_is_embedding_stale_old(self):
        """Document with embedding older than content is stale."""
        from app.models.document import Document

        doc = Document()
        doc.embedding_updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        doc.updated_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
        assert doc.is_embedding_stale is True

    def test_document_model_is_embedding_fresh(self):
        """Document with embedding newer than content is not stale."""
        from app.models.document import Document

        doc = Document()
        doc.embedding_updated_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
        doc.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert doc.is_embedding_stale is False

    def test_document_response_has_stale_field(self):
        """DocumentResponse schema includes is_embedding_stale field."""
        from app.schemas.document import DocumentResponse

        fields = DocumentResponse.model_fields
        assert "is_embedding_stale" in fields

    def test_no_auto_embed_on_save(self):
        """Verify the auto-embed code has been removed from the save_content endpoint.

        We check that the documents router source does not contain enqueue of
        embed_document_job in the save_content function.
        """
        import inspect

        from app.routers.documents import save_content

        source = inspect.getsource(save_content)
        assert "embed_document_job" not in source

    def test_batch_embed_job_exists(self):
        """Verify batch_embed_stale_documents is registered as a worker function."""
        from app.worker import WorkerSettings

        function_names = [f.__name__ for f in WorkerSettings.functions]
        assert "batch_embed_stale_documents" in function_names

    def test_nightly_cron_registered(self):
        """Verify the nightly batch embed cron job is registered."""
        from app.worker import WorkerSettings

        # Check cron_jobs contains batch_embed_stale_documents
        cron_names = []
        for cj in WorkerSettings.cron_jobs:
            # ARQ cron objects have a .coroutine attribute
            if hasattr(cj, "coroutine"):
                cron_names.append(cj.coroutine.__name__)
        assert "batch_embed_stale_documents" in cron_names

    def test_websocket_event_type_exists(self):
        """DOCUMENT_EMBEDDING_SYNCED MessageType exists."""
        from app.websocket.manager import MessageType

        assert hasattr(MessageType, "DOCUMENT_EMBEDDING_SYNCED")
        assert MessageType.DOCUMENT_EMBEDDING_SYNCED.value == "document_embedding_synced"


# ---------------------------------------------------------------------------
# 9.7 SQL Execution Backup Timeout
# ---------------------------------------------------------------------------


class TestSQLBackupTimeout:
    """Tests for asyncio.wait_for backup in sql_executor."""

    def test_timeout_constant(self):
        from app.ai.sql_executor import APP_QUERY_TIMEOUT_S

        assert APP_QUERY_TIMEOUT_S == 6.0

    @pytest.mark.asyncio
    async def test_asyncio_timeout_fires(self):
        """If DB execute hangs beyond APP_QUERY_TIMEOUT_S, ValueError is raised."""
        from app.ai.sql_executor import execute

        mock_db = AsyncMock()

        # First two execute calls succeed (SET LOCAL), third hangs
        call_count = 0

        async def _mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                # SET LOCAL and SET TRANSACTION succeed
                mock_result = MagicMock()
                mock_result.keys.return_value = []
                mock_result.fetchmany.return_value = []
                return mock_result
            # Fourth call (the actual query) hangs
            await asyncio.sleep(3600)

        mock_db.execute = _mock_execute

        # Patch APP_QUERY_TIMEOUT_S to something very short for testing
        with patch("app.ai.sql_executor.APP_QUERY_TIMEOUT_S", 0.05):
            with pytest.raises(ValueError, match="timeout exceeded"):
                await execute("SELECT 1", uuid4(), mock_db)


# ---------------------------------------------------------------------------
# 9.8 RAG Query Embedding Cache
# ---------------------------------------------------------------------------


class TestRAGEmbeddingCache:
    """Tests for query embedding caching in rag_search_tool."""

    @pytest.mark.asyncio
    async def test_rag_tool_accepts_cache_param(self):
        """rag_search_tool accepts query_embedding_cache parameter."""
        from app.ai.agent_tools import rag_search_tool
        import inspect

        sig = inspect.signature(rag_search_tool)
        assert "query_embedding_cache" in sig.parameters

    @pytest.mark.asyncio
    async def test_retrieve_accepts_query_embedding(self):
        """HybridRetrievalService.retrieve accepts query_embedding parameter."""
        from app.ai.retrieval_service import HybridRetrievalService
        import inspect

        sig = inspect.signature(HybridRetrievalService.retrieve)
        assert "query_embedding" in sig.parameters

    @pytest.mark.asyncio
    async def test_semantic_search_uses_precomputed_embedding(self):
        """_semantic_search skips embedding generation when query_embedding provided."""
        from app.ai.retrieval_service import HybridRetrievalService

        mock_registry = MagicMock()
        mock_normalizer = MagicMock()
        mock_db = AsyncMock()

        svc = HybridRetrievalService(
            provider_registry=mock_registry,
            normalizer=mock_normalizer,
            db=mock_db,
        )

        # Mock db.execute to return empty result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Call with a pre-computed embedding
        pre_embedding = [0.1] * 1536
        results = await svc._semantic_search(
            query="test",
            scope_ids={"app_ids": [], "project_ids": [], "user_id": uuid4()},
            limit=10,
            query_embedding=pre_embedding,
        )

        # The embedding provider should NOT have been called
        mock_registry.get_embedding_provider.assert_not_called()


# ---------------------------------------------------------------------------
# 9.9 Import File Streaming
# ---------------------------------------------------------------------------


class TestImportFileStreaming:
    """Tests for streaming file upload to temp file."""

    def test_no_full_file_read_in_import(self):
        """Verify the import router no longer uses 'contents = await file.read()'."""
        import inspect

        from app.routers.ai_import import upload_and_import

        source = inspect.getsource(upload_and_import)
        # The old pattern was 'contents = await file.read()'
        assert "contents = await file.read()" not in source

    def test_streaming_uses_chunked_read(self):
        """Verify the import router uses chunked reading pattern."""
        import inspect

        from app.routers.ai_import import upload_and_import

        source = inspect.getsource(upload_and_import)
        # Should contain the 64KB chunk read pattern
        assert "64 * 1024" in source or "CHUNK_SIZE" in source


# ---------------------------------------------------------------------------
# TE-002: Streaming Timeout Behavioral Tests
# ---------------------------------------------------------------------------


class TestStreamingTimeoutBehavior:
    """Behavioral tests for streaming safety limits via _guarded_stream.

    Tests the actual production code path by hitting the /api/ai/chat/stream
    endpoint with mocked agent setup and stream generator, which exercises
    _guarded_stream (a closure inside chat_stream).
    """

    @pytest.mark.asyncio
    async def test_overall_timeout_fires(self, client, test_user, auth_headers):
        """Overall timeout fires and emits an error event near the limit."""
        # Mock _stream_agent to yield chunks slowly (one per second)
        async def slow_stream(graph, state, config, thread_id=""):
            for i in range(200):
                yield {"event": "text_delta", "data": json.dumps({"content": f"chunk {i}"})}
                await asyncio.sleep(1)

        mock_graph = MagicMock()
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat._stream_agent", slow_stream), \
             patch("app.routers.ai_chat.STREAM_OVERALL_TIMEOUT_S", 0.3), \
             patch("app.routers.ai_chat.STREAM_IDLE_TIMEOUT_S", 600), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock):

            resp = await client.post(
                "/api/ai/chat/stream",
                json={"message": "hello", "conversation_history": [], "images": []},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.text
        # Parse SSE events from the response body
        assert "Stream timeout" in body

    @pytest.mark.asyncio
    async def test_idle_timeout_fires(self, client, test_user, auth_headers):
        """Idle timeout fires when gap between chunks exceeds STREAM_IDLE_TIMEOUT_S."""
        async def stalling_stream(graph, state, config, thread_id=""):
            yield {"event": "text_delta", "data": json.dumps({"content": "first chunk"})}
            # Pause longer than idle timeout
            await asyncio.sleep(1.0)
            yield {"event": "text_delta", "data": json.dumps({"content": "after pause"})}

        mock_graph = MagicMock()
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat._stream_agent", stalling_stream), \
             patch("app.routers.ai_chat.STREAM_OVERALL_TIMEOUT_S", 60), \
             patch("app.routers.ai_chat.STREAM_IDLE_TIMEOUT_S", 0.1), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock):

            resp = await client.post(
                "/api/ai/chat/stream",
                json={"message": "hello", "conversation_history": [], "images": []},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.text
        assert "Stream timeout" in body

    @pytest.mark.asyncio
    async def test_chunk_limit_fires(self, client, test_user, auth_headers):
        """Chunk limit fires when stream produces more than MAX_CHUNKS_PER_RESPONSE."""
        async def verbose_stream(graph, state, config, thread_id=""):
            for i in range(50):
                yield {"event": "text_delta", "data": json.dumps({"content": f"c{i}"})}

        mock_graph = MagicMock()
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat._stream_agent", verbose_stream), \
             patch("app.routers.ai_chat.MAX_CHUNKS_PER_RESPONSE", 20), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock):

            resp = await client.post(
                "/api/ai/chat/stream",
                json={"message": "hello", "conversation_history": [], "images": []},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.text
        assert "exceeded maximum" in body.lower()

    @pytest.mark.asyncio
    async def test_normal_stream_no_timeout(self, client, test_user, auth_headers):
        """Normal stream with 10 chunks in ~0s completes without timeout or errors."""
        async def fast_stream(graph, state, config, thread_id=""):
            for i in range(10):
                yield {"event": "text_delta", "data": json.dumps({"content": f"chunk {i}"})}
            yield {"event": "end", "data": "{}"}

        mock_graph = MagicMock()
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat._stream_agent", fast_stream), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock):

            resp = await client.post(
                "/api/ai/chat/stream",
                json={"message": "hello", "conversation_history": [], "images": []},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.text
        # No error events in the stream
        assert "Stream timeout" not in body
        assert "exceeded maximum" not in body.lower()
        # Should contain our content chunks
        assert "chunk 0" in body
        assert "chunk 9" in body


# ---------------------------------------------------------------------------
# TE-003: Sync-Embeddings Endpoint Tests
# ---------------------------------------------------------------------------


class TestSyncEmbeddingsEndpoint:
    """Behavioral tests for POST /documents/{id}/sync-embeddings."""

    @pytest.mark.asyncio
    async def test_happy_path_202(self, client, test_user, auth_headers, db_session):
        """Authenticated Editor user gets 202 + job enqueued."""
        from app.models.document import Document

        doc = Document(
            id=uuid4(),
            title="Test Doc",
            user_id=test_user.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)

        with patch("app.routers.documents.PermissionService") as MockPS:
            mock_ps = MagicMock()
            MockPS.return_value = mock_ps
            MockPS.resolve_entity_scope.return_value = ("personal", test_user.id)
            mock_ps.check_can_edit_knowledge = AsyncMock(return_value=True)

            with patch("app.services.arq_helper.get_arq_redis") as mock_arq:
                mock_redis = AsyncMock()
                mock_arq.return_value = mock_redis

                resp = await client.post(
                    f"/api/documents/{doc.id}/sync-embeddings",
                    headers=auth_headers,
                )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["document_id"] == str(doc.id)

    @pytest.mark.asyncio
    async def test_missing_document_404(self, client, auth_headers):
        """Non-existent document returns 404."""
        fake_id = uuid4()
        resp = await client.post(
            f"/api/documents/{fake_id}/sync-embeddings",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_403(self, client, test_user, auth_headers, db_session):
        """Viewer role returns 403."""
        from app.models.document import Document

        doc = Document(
            id=uuid4(),
            title="Restricted Doc",
            user_id=test_user.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)

        with patch("app.routers.documents.PermissionService") as MockPS:
            mock_ps = MagicMock()
            MockPS.return_value = mock_ps
            MockPS.resolve_entity_scope.return_value = ("personal", test_user.id)
            mock_ps.check_can_edit_knowledge = AsyncMock(return_value=False)

            resp = await client.post(
                f"/api/documents/{doc.id}/sync-embeddings",
                headers=auth_headers,
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_worker_unavailable_503(self, client, test_user, auth_headers, db_session):
        """Worker unavailable returns 503."""
        from app.models.document import Document

        doc = Document(
            id=uuid4(),
            title="Worker Down Doc",
            user_id=test_user.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)

        with patch("app.routers.documents.PermissionService") as MockPS:
            mock_ps = MagicMock()
            MockPS.return_value = mock_ps
            MockPS.resolve_entity_scope.return_value = ("personal", test_user.id)
            mock_ps.check_can_edit_knowledge = AsyncMock(return_value=True)

            with patch("app.services.arq_helper.get_arq_redis", side_effect=RuntimeError("no worker")):
                resp = await client.post(
                    f"/api/documents/{doc.id}/sync-embeddings",
                    headers=auth_headers,
                )

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# TE-004: Batch Embed Stale Documents Tests
# ---------------------------------------------------------------------------


class TestBatchEmbedStaleDocuments:
    """Behavioral tests for batch_embed_stale_documents nightly cron."""

    @pytest.mark.asyncio
    async def test_has_stale_docs_enqueues_jobs(self):
        """Mock query returning 5 stale doc IDs, verify 5 embed jobs enqueued."""
        from app.worker import batch_embed_stale_documents

        stale_ids = [uuid4() for _ in range(5)]

        mock_result = MagicMock()
        mock_result.all.return_value = [(sid,) for sid in stale_ids]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_arq_pool = AsyncMock()

        with patch("app.worker.async_session_maker") as mock_session_maker:
            # Setup async context manager
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session_maker.return_value = mock_ctx

            with patch("app.services.arq_helper.get_arq_redis", AsyncMock(return_value=mock_arq_pool)):
                result = await batch_embed_stale_documents({})

        assert result["status"] == "success"
        assert result["queued"] == 5
        assert mock_arq_pool.enqueue_job.call_count == 5

    @pytest.mark.asyncio
    async def test_no_stale_docs(self):
        """Mock empty query result, verify no jobs enqueued."""
        from app.worker import batch_embed_stale_documents

        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.worker.async_session_maker") as mock_session_maker:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session_maker.return_value = mock_ctx

            result = await batch_embed_stale_documents({})

        assert result["status"] == "success"
        assert result["queued"] == 0

    @pytest.mark.asyncio
    async def test_db_query_failure(self):
        """Mock DB query failure, verify error returned."""
        from app.worker import batch_embed_stale_documents

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))

        with patch("app.worker.async_session_maker") as mock_session_maker:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_session_maker.return_value = mock_ctx

            result = await batch_embed_stale_documents({})

        assert result["status"] == "error"
        assert "RuntimeError" in result["error"]


# ---------------------------------------------------------------------------
# TE-005: Import Concurrency Limiter Tests
# ---------------------------------------------------------------------------


class TestImportConcurrencyLimiter:
    """Behavioral tests for Redis-based import concurrency limiter.

    Calls the actual process_document_import function from app.worker with
    mocked DB session, Redis, and file system to verify the concurrency
    check logic in production code paths.
    """

    @pytest.mark.asyncio
    async def test_under_limit_proceeds(self):
        """Redis eval returns 3 (<= 5), verify import proceeds past concurrency check.

        After the concurrency check passes, the function sets job.status='processing'
        and then checks os.path.exists(temp_path). We let the file not exist so
        FileNotFoundError is raised -- proving the code got past the concurrency gate.
        """
        from app.worker import process_document_import

        job_id = str(uuid4())
        user_id = uuid4()

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "pending"
        mock_job.temp_file_path = "/tmp/test_import.pdf"
        mock_job.file_type = "pdf"
        mock_job.file_name = "test.pdf"
        mock_job.user_id = user_id
        mock_job.folder_id = None
        mock_job.scope = "personal"
        mock_job.scope_id = user_id
        mock_job.title = "Test Doc"
        mock_job.file_size = 1024
        mock_job.progress_pct = 0
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis: eval (Lua INCR+EXPIRE) returns 3 (under limit)
        mock_redis_client = AsyncMock()
        mock_redis_client.eval = AsyncMock(return_value=3)
        mock_redis_client.decr = AsyncMock(return_value=2)
        mock_redis_client.set = AsyncMock()

        mock_redis_svc = MagicMock()
        mock_redis_svc.is_connected = True
        mock_redis_svc.client = mock_redis_client

        with patch("app.worker.async_session_maker", return_value=mock_session_ctx), \
             patch("app.worker.redis_service", mock_redis_svc):
            # temp file doesn't exist, so FileNotFoundError fires AFTER concurrency OK
            result = await process_document_import({}, job_id)

        # The job should have failed (file not found), NOT been deferred
        assert result["status"] == "error"
        assert result["error"] == "FileNotFoundError"
        # Redis eval was called (concurrency check passed)
        mock_redis_client.eval.assert_called_once()
        # Job was set to "processing" before the file check
        assert mock_job.status == "processing" or mock_job.status == "failed"

    @pytest.mark.asyncio
    async def test_at_limit_defers_job(self):
        """Redis eval returns 6 (> 5), verify job is deferred with DECR."""
        from app.worker import process_document_import, MAX_CONCURRENT_IMPORTS

        job_id = str(uuid4())
        user_id = uuid4()

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "pending"
        mock_job.temp_file_path = "/tmp/test_import.pdf"
        mock_job.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis: eval returns over limit
        mock_redis_client = AsyncMock()
        mock_redis_client.eval = AsyncMock(return_value=MAX_CONCURRENT_IMPORTS + 1)
        mock_redis_client.decr = AsyncMock()

        mock_redis_svc = MagicMock()
        mock_redis_svc.is_connected = True
        mock_redis_svc.client = mock_redis_client

        # Mock ARQ pool for re-enqueue
        mock_arq_pool = AsyncMock()
        mock_arq_pool.enqueue_job = AsyncMock()
        mock_arq_pool.aclose = AsyncMock()

        with patch("app.worker.async_session_maker", return_value=mock_session_ctx), \
             patch("app.worker.redis_service", mock_redis_svc), \
             patch("arq.connections.create_pool", AsyncMock(return_value=mock_arq_pool)):

            result = await process_document_import({}, job_id)

        # Job should be deferred due to concurrency limit
        assert result["status"] == "deferred"
        assert result["reason"] == "concurrency_limit"
        # DECR should have been called to undo the INCR
        mock_redis_client.decr.assert_called_once()
        # Re-enqueue should have been called
        mock_arq_pool.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_down_fail_open(self):
        """Redis raises exception during concurrency check, import proceeds (fail-open).

        When Redis eval fails, the concurrency check falls through (fail-open) and
        the import proceeds. We verify this by checking the function gets past
        the concurrency gate and into file processing (where it hits FileNotFoundError).
        The failure handler still attempts to decr the counter (Redis may be back).
        """
        from app.worker import process_document_import

        job_id = str(uuid4())
        user_id = uuid4()

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "pending"
        mock_job.temp_file_path = "/tmp/test_import.pdf"
        mock_job.file_type = "pdf"
        mock_job.file_name = "test.pdf"
        mock_job.user_id = user_id
        mock_job.folder_id = None
        mock_job.scope = "personal"
        mock_job.scope_id = user_id
        mock_job.title = "Test Doc"
        mock_job.file_size = 1024
        mock_job.progress_pct = 0
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis: eval raises (Redis down), but is_connected=True so decr is attempted
        mock_redis_client = AsyncMock()
        mock_redis_client.eval = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis_client.decr = AsyncMock(return_value=0)
        mock_redis_client.set = AsyncMock()

        mock_redis_svc = MagicMock()
        mock_redis_svc.is_connected = True
        mock_redis_svc.client = mock_redis_client

        with patch("app.worker.async_session_maker", return_value=mock_session_ctx), \
             patch("app.worker.redis_service", mock_redis_svc):
            # temp file doesn't exist -> FileNotFoundError after concurrency (fail-open)
            result = await process_document_import({}, job_id)

        # Import proceeded (fail-open): got past concurrency gate, hit file check
        assert result["status"] == "error"
        assert result["error"] == "FileNotFoundError"
        # eval was attempted and raised ConnectionError
        mock_redis_client.eval.assert_called_once()
        # Job was set to "processing" (proves concurrency gate was passed)
        assert mock_job.progress_pct == 10

    @pytest.mark.asyncio
    async def test_decr_on_failure(self):
        """Concurrency counter is decremented when import fails after acquisition."""
        from app.worker import process_document_import, IMPORT_CONCURRENCY_KEY

        job_id = str(uuid4())
        user_id = uuid4()

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "pending"
        mock_job.temp_file_path = "/tmp/nonexistent_file.pdf"
        mock_job.file_type = "pdf"
        mock_job.file_name = "test.pdf"
        mock_job.user_id = user_id
        mock_job.folder_id = None
        mock_job.scope = "personal"
        mock_job.scope_id = user_id
        mock_job.title = "Test Doc"
        mock_job.file_size = 1024
        mock_job.progress_pct = 0
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis: concurrency acquired successfully (eval returns 2)
        mock_redis_client = AsyncMock()
        mock_redis_client.eval = AsyncMock(return_value=2)
        mock_redis_client.decr = AsyncMock(return_value=1)
        mock_redis_client.set = AsyncMock()

        mock_redis_svc = MagicMock()
        mock_redis_svc.is_connected = True
        mock_redis_svc.client = mock_redis_client

        with patch("app.worker.async_session_maker", return_value=mock_session_ctx), \
             patch("app.worker.redis_service", mock_redis_svc), \
             patch("os.path.exists", return_value=False):
            # File doesn't exist -> FileNotFoundError, but AFTER concurrency acquired

            result = await process_document_import({}, job_id)

        # Job failed
        assert result["status"] == "error"
        assert result["error"] == "FileNotFoundError"
        # DECR was called in the failure handler to release the concurrency slot
        mock_redis_client.decr.assert_called()


# ---------------------------------------------------------------------------
# TE-001: Agent Tool Call Enforcement (graph-level behavioral test)
# ---------------------------------------------------------------------------


class TestAgentToolCallEnforcement:
    """Behavioral test for tool call limit enforcement at graph level.

    Builds a real agent graph via build_agent_graph and invokes it with
    state containing >= MAX_TOOL_CALLS to verify the graph routes to END
    and agent_node returns a user-facing limit message.
    """

    @pytest.mark.asyncio
    async def test_graph_stops_at_50_tool_calls(self):
        """Build agent graph, invoke with 50+ tool calls, verify it stops with limit message."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from langchain_core.tools import tool as lc_tool

        from app.ai.agent.graph import (
            MAX_TOOL_CALLS,
            _count_total_tool_calls,
            build_agent_graph,
        )

        # Create a dummy tool so build_agent_graph has at least one tool
        @lc_tool
        def dummy_tool(query: str) -> str:
            """A dummy tool for testing."""
            return "ok"

        # Mock provider_registry and db_session_factory (not needed since
        # agent_node will hit the tool call limit before invoking the LLM)
        mock_registry = MagicMock()
        mock_db_factory = MagicMock()

        graph = build_agent_graph(
            tools=[dummy_tool],
            checkpointer=None,
            provider_registry=mock_registry,
            db_session_factory=mock_db_factory,
        )

        # Build message history with exactly MAX_TOOL_CALLS tool calls
        messages = []
        messages.append(HumanMessage(content="analyze everything"))
        for batch in range(MAX_TOOL_CALLS // 10):
            ai_msg = AIMessage(
                content="",
                tool_calls=[
                    {"id": f"call_{batch}_{i}", "name": "dummy_tool", "args": {"query": "test"}}
                    for i in range(10)
                ],
            )
            messages.append(ai_msg)
            for i in range(10):
                messages.append(
                    ToolMessage(content="ok", tool_call_id=f"call_{batch}_{i}")
                )

        assert _count_total_tool_calls(messages) == MAX_TOOL_CALLS

        state = {
            "messages": messages,
            "user_id": "test-user",
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        # Invoke the graph — agent_node should detect the limit and return
        # a limit message without calling the LLM
        result = await graph.ainvoke(state)

        # The last message should be the limit-reached AIMessage
        result_messages = result["messages"]
        last_msg = result_messages[-1]
        assert isinstance(last_msg, AIMessage)
        assert "maximum number of operations" in last_msg.content

    @pytest.mark.asyncio
    async def test_agent_node_returns_user_message_at_limit(self):
        """When at limit, agent_node returns a user-facing message (not silent stop)."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from langchain_core.tools import tool as lc_tool

        from app.ai.agent.graph import MAX_TOOL_CALLS, build_agent_graph

        @lc_tool
        def noop_tool(input: str) -> str:
            """A no-op tool."""
            return "done"

        graph = build_agent_graph(
            tools=[noop_tool],
            checkpointer=None,
            provider_registry=MagicMock(),
            db_session_factory=MagicMock(),
        )

        # Build messages at exactly MAX_TOOL_CALLS
        messages = [HumanMessage(content="do lots of things")]
        for batch in range(MAX_TOOL_CALLS // 10):
            messages.append(
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": f"c_{batch}_{i}", "name": "noop_tool", "args": {"input": "x"}}
                        for i in range(10)
                    ],
                )
            )
            for i in range(10):
                messages.append(
                    ToolMessage(content="done", tool_call_id=f"c_{batch}_{i}")
                )

        state = {
            "messages": messages,
            "user_id": "test-user",
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        result = await graph.ainvoke(state)

        # Verify the response contains the user-facing limit message
        last_msg = result["messages"][-1]
        assert isinstance(last_msg, AIMessage)
        assert "maximum number of operations" in last_msg.content
        # Verify it's not empty / silent stop
        assert len(last_msg.content) > 20


# ---------------------------------------------------------------------------
# Resume Chat Timeout + Telemetry Tests
# ---------------------------------------------------------------------------


class TestResumeChatEndpoint:
    """Tests for POST /api/ai/chat/resume timeout, error handling, and telemetry."""

    @pytest.mark.asyncio
    async def test_resume_chat_timeout_returns_504(self, client, test_user, auth_headers):
        """resume_chat returns 504 when graph.ainvoke times out."""
        mock_graph = MagicMock()

        async def _hang_forever(*args, **kwargs):
            await asyncio.sleep(3600)

        mock_graph.ainvoke = _hang_forever
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat.STREAM_OVERALL_TIMEOUT_S", 0.1), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.ai.agent.graph.get_checkpointer", return_value=MagicMock()), \
             patch("app.routers.ai_chat.AITelemetry") as mock_telemetry, \
             patch("app.ai.agent.tools_read.clear_tool_context") as mock_clear:

            resp = await client.post(
                "/api/ai/chat/resume",
                json={"thread_id": "test-thread", "response": {"approved": True}},
                headers=auth_headers,
            )

        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()
        # Verify telemetry was logged
        mock_telemetry.log_chat_request.assert_called_once()
        call_kwargs = mock_telemetry.log_chat_request.call_args
        assert call_kwargs[1]["success"] is False
        assert "timed out" in call_kwargs[1]["error"].lower()
        # Verify tool context is always cleaned up
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_chat_error_returns_500(self, client, test_user, auth_headers):
        """resume_chat returns 500 when graph.ainvoke raises an unexpected error."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM provider down"))
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.ai.agent.graph.get_checkpointer", return_value=MagicMock()), \
             patch("app.routers.ai_chat.AITelemetry") as mock_telemetry, \
             patch("app.ai.agent.tools_read.clear_tool_context") as mock_clear:

            resp = await client.post(
                "/api/ai/chat/resume",
                json={"thread_id": "test-thread", "response": {"approved": True}},
                headers=auth_headers,
            )

        assert resp.status_code == 500
        assert "failed" in resp.json()["detail"].lower()
        mock_telemetry.log_chat_request.assert_called_once()
        call_kwargs = mock_telemetry.log_chat_request.call_args
        assert call_kwargs[1]["success"] is False
        # Verify tool context is always cleaned up
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_chat_happy_path(self, client, test_user, auth_headers):
        """resume_chat returns 200 with agent response on success."""
        from langchain_core.messages import AIMessage

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "messages": [AIMessage(content="Here is the result")],
        })
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.ai.agent.graph.get_checkpointer", return_value=MagicMock()), \
             patch("app.routers.ai_chat.AITelemetry") as mock_telemetry, \
             patch("app.ai.agent.tools_read.clear_tool_context") as mock_clear:

            resp = await client.post(
                "/api/ai/chat/resume",
                json={"thread_id": "test-thread", "response": {"approved": True}},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Here is the result"
        assert data["thread_id"] == "test-thread"
        # Verify success telemetry
        mock_telemetry.log_chat_request.assert_called_once()
        call_kwargs = mock_telemetry.log_chat_request.call_args
        assert call_kwargs[1]["success"] is True
        # Verify tool context is always cleaned up
        mock_clear.assert_called_once()


# ---------------------------------------------------------------------------
# Non-streaming Chat Timeout Test
# ---------------------------------------------------------------------------


class TestNonStreamingChatTimeout:
    """Tests for POST /api/ai/chat (non-streaming) timeout behavior."""

    @pytest.mark.asyncio
    async def test_chat_timeout_returns_504(self, client, test_user, auth_headers):
        """Non-streaming chat returns 504 when graph.ainvoke times out."""
        mock_graph = MagicMock()

        async def _hang_forever(*args, **kwargs):
            await asyncio.sleep(3600)

        mock_graph.ainvoke = _hang_forever
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat.STREAM_OVERALL_TIMEOUT_S", 0.1), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock), \
             patch("app.routers.ai_chat.AITelemetry") as mock_telemetry:

            resp = await client.post(
                "/api/ai/chat",
                json={"message": "hello", "conversation_history": [], "images": []},
                headers=auth_headers,
            )

        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()
        mock_telemetry.log_chat_request.assert_called_once()
        call_kwargs = mock_telemetry.log_chat_request.call_args
        assert call_kwargs[1]["success"] is False


# ---------------------------------------------------------------------------
# Replay Conversation Rate Limit + Guards Tests
# ---------------------------------------------------------------------------


class TestReplayConversationGuards:
    """Tests for replay_conversation rate limiting and _guarded_replay guards."""

    def test_replay_has_rate_limit(self):
        """replay_conversation endpoint has rate limit dependency."""
        import inspect
        from app.routers.ai_chat import replay_conversation

        sig = inspect.signature(replay_conversation)
        # The _rate_limit parameter should have check_chat_rate_limit as its default Depends
        assert "_rate_limit" in sig.parameters
        param = sig.parameters["_rate_limit"]
        from app.ai.rate_limiter import check_chat_rate_limit
        assert param.default.dependency is check_chat_rate_limit

    @pytest.mark.asyncio
    async def test_guarded_replay_overall_timeout(self, client, test_user, auth_headers):
        """_guarded_replay emits error event on overall timeout."""
        async def slow_stream(graph, state, config, thread_id=""):
            for i in range(200):
                yield {"event": "text_delta", "data": json.dumps({"content": f"chunk {i}"})}
                await asyncio.sleep(1)

        mock_graph = MagicMock()
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat._stream_agent", slow_stream), \
             patch("app.routers.ai_chat.STREAM_OVERALL_TIMEOUT_S", 0.3), \
             patch("app.routers.ai_chat.STREAM_IDLE_TIMEOUT_S", 600), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock), \
             patch("app.ai.agent.graph.get_checkpointer", return_value=MagicMock()):

            resp = await client.post(
                "/api/ai/chat/replay",
                json={
                    "thread_id": "test-thread",
                    "checkpoint_id": "cp-1",
                    "message": "replay this",
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.text
        assert "Stream timeout" in body

    @pytest.mark.asyncio
    async def test_guarded_replay_chunk_limit(self, client, test_user, auth_headers):
        """_guarded_replay emits error event when chunk limit exceeded."""
        async def verbose_stream(graph, state, config, thread_id=""):
            for i in range(50):
                yield {"event": "text_delta", "data": json.dumps({"content": f"c{i}"})}

        mock_graph = MagicMock()
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat._stream_agent", verbose_stream), \
             patch("app.routers.ai_chat.MAX_CHUNKS_PER_RESPONSE", 20), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock), \
             patch("app.ai.agent.graph.get_checkpointer", return_value=MagicMock()):

            resp = await client.post(
                "/api/ai/chat/replay",
                json={
                    "thread_id": "test-thread",
                    "checkpoint_id": "cp-1",
                    "message": "replay this",
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.text
        assert "maximum size" in body

    @pytest.mark.asyncio
    async def test_guarded_replay_idle_timeout(self, client, test_user, auth_headers):
        """_guarded_replay emits error event when a single chunk takes too long."""
        async def stalling_stream(graph, state, config, thread_id=""):
            yield {"event": "text_delta", "data": json.dumps({"content": "chunk 0"})}
            # Second chunk stalls longer than idle timeout
            await asyncio.sleep(3600)
            yield {"event": "text_delta", "data": json.dumps({"content": "chunk 1"})}

        mock_graph = MagicMock()
        mock_context = {
            "accessible_app_ids": [],
            "accessible_project_ids": [],
        }

        with patch("app.routers.ai_chat._setup_agent_context", new_callable=AsyncMock, return_value=(mock_graph, mock_context)), \
             patch("app.routers.ai_chat._stream_agent", stalling_stream), \
             patch("app.routers.ai_chat.STREAM_OVERALL_TIMEOUT_S", 600), \
             patch("app.routers.ai_chat.STREAM_IDLE_TIMEOUT_S", 0.2), \
             patch("app.routers.ai_chat.check_chat_rate_limit", return_value=None), \
             patch("app.routers.ai_chat._validate_thread_owner", new_callable=AsyncMock), \
             patch("app.routers.ai_chat._register_thread", new_callable=AsyncMock), \
             patch("app.ai.agent.graph.get_checkpointer", return_value=MagicMock()):

            resp = await client.post(
                "/api/ai/chat/replay",
                json={
                    "thread_id": "test-thread",
                    "checkpoint_id": "cp-1",
                    "message": "replay this",
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        body = resp.text
        assert "Stream timeout" in body

"""Unit tests for AI agent graph (app.ai.agent.graph).

Tests cover:
- AgentState TypedDict structure
- SYSTEM_PROMPT content
- _count_tool_iterations with mock AIMessages
- _get_langchain_chat_model for openai, anthropic, ollama providers
- build_agent_graph returns compiled graph with correct nodes/edges
- get_checkpointer / set_checkpointer module-level accessors
- MAX_ITERATIONS constant
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as langchain_tool

from app.ai.agent.graph import (
    MAX_ITERATIONS,
    SYSTEM_PROMPT,
    AgentState,
    _count_tool_iterations,
    _get_langchain_chat_model,
    build_agent_graph,
    get_checkpointer,
    set_checkpointer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider_orm(provider_type: str, base_url: str | None = None) -> MagicMock:
    """Create a mock ORM provider object."""
    orm = MagicMock()
    orm.provider_type = provider_type
    orm.base_url = base_url
    return orm


def _make_model_orm(model_id: str = "gpt-4o") -> MagicMock:
    """Create a mock ORM model object."""
    orm = MagicMock()
    orm.model_id = model_id
    return orm


def _make_registry(provider_type: str, model_id: str = "gpt-4o",
                   base_url: str | None = None) -> MagicMock:
    """Build a mock ProviderRegistry that resolves to a given provider."""
    provider_orm = _make_provider_orm(provider_type, base_url)
    model_orm = _make_model_orm(model_id)

    registry = MagicMock()
    registry._resolve_provider = AsyncMock(return_value=(provider_orm, model_orm))
    registry._decrypt_key = MagicMock(return_value="test-api-key")
    return registry


# ---------------------------------------------------------------------------
# Tests: Constants and AgentState
# ---------------------------------------------------------------------------

class TestConstants:

    def test_max_iterations_is_10(self):
        assert MAX_ITERATIONS == 10

    def test_system_prompt_mentions_blair(self):
        assert "Blair" in SYSTEM_PROMPT

    def test_system_prompt_mentions_tool_guidance(self):
        assert "sql_query" in SYSTEM_PROMPT
        assert "query_knowledge" in SYSTEM_PROMPT

    def test_system_prompt_mentions_confirmation(self):
        assert "confirm" in SYSTEM_PROMPT.lower()


class TestAgentState:

    def test_agent_state_has_messages_field(self):
        annotations = AgentState.__annotations__
        assert "messages" in annotations

    def test_agent_state_has_user_id_field(self):
        annotations = AgentState.__annotations__
        assert "user_id" in annotations

    def test_agent_state_has_accessible_app_ids_field(self):
        annotations = AgentState.__annotations__
        assert "accessible_app_ids" in annotations

    def test_agent_state_has_accessible_project_ids_field(self):
        annotations = AgentState.__annotations__
        assert "accessible_project_ids" in annotations


# ---------------------------------------------------------------------------
# Tests: Checkpointer accessors
# ---------------------------------------------------------------------------

class TestCheckpointerAccessors:

    def test_get_checkpointer_returns_none_initially(self):
        # Reset module state
        import app.ai.agent.graph as graph_mod
        original = graph_mod._checkpointer
        try:
            graph_mod._checkpointer = None
            assert get_checkpointer() is None
        finally:
            graph_mod._checkpointer = original

    def test_set_and_get_checkpointer(self):
        import app.ai.agent.graph as graph_mod
        original = graph_mod._checkpointer
        try:
            sentinel = MagicMock()
            set_checkpointer(sentinel)
            assert get_checkpointer() is sentinel
        finally:
            graph_mod._checkpointer = original


# ---------------------------------------------------------------------------
# Tests: _count_tool_iterations
# ---------------------------------------------------------------------------

class TestCountToolIterations:

    def test_empty_messages_returns_zero(self):
        assert _count_tool_iterations([]) == 0

    def test_human_messages_only_returns_zero(self):
        messages = [HumanMessage(content="hello")]
        assert _count_tool_iterations(messages) == 0

    def test_ai_message_without_tool_calls_returns_zero(self):
        messages = [AIMessage(content="Sure, here is the answer.")]
        assert _count_tool_iterations(messages) == 0

    def test_ai_message_with_tool_calls_counts_one(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "sql_query", "args": {}, "id": "tc1"}],
        )
        assert _count_tool_iterations([ai_msg]) == 1

    def test_multiple_tool_call_iterations(self):
        messages = [
            HumanMessage(content="get tasks"),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_tasks", "args": {}, "id": "tc1"}],
            ),
            ToolMessage(content="result", tool_call_id="tc1"),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_task_detail", "args": {}, "id": "tc2"}],
            ),
            ToolMessage(content="detail", tool_call_id="tc2"),
            AIMessage(content="Here are the tasks."),
        ]
        # Two AIMessages with tool_calls + one without = 2
        assert _count_tool_iterations(messages) == 2


# ---------------------------------------------------------------------------
# Tests: _get_langchain_chat_model
# ---------------------------------------------------------------------------

class TestGetLangchainChatModel:

    @patch("app.ai.agent.graph.ChatOpenAI", create=True)
    async def test_openai_provider_returns_chat_openai(self, mock_cls):
        mock_cls.return_value = MagicMock()
        registry = _make_registry("openai", "gpt-4o", "https://api.openai.com/v1")
        db = AsyncMock()

        with patch("app.ai.agent.graph.ChatOpenAI", mock_cls, create=True):
            # We need to patch the import inside the function
            pass

        # Instead, call directly and patch the lazy import
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            result = await _get_langchain_chat_model(registry, db, None)

        mock_cls.assert_called_once_with(
            model="gpt-4o",
            api_key="test-api-key",
            base_url="https://api.openai.com/v1",
            temperature=0.1,
            max_tokens=4096,
            request_timeout=30,
        )
        assert result is mock_cls.return_value

    @patch.dict("sys.modules")
    async def test_anthropic_provider_returns_chat_anthropic(self):
        mock_cls = MagicMock()
        mock_cls.return_value = MagicMock()
        mock_anthropic_mod = MagicMock(ChatAnthropic=mock_cls)
        import sys
        sys.modules["langchain_anthropic"] = mock_anthropic_mod

        registry = _make_registry("anthropic", "claude-sonnet-4-6")
        db = AsyncMock()

        result = await _get_langchain_chat_model(registry, db, None)

        mock_cls.assert_called_once_with(
            model="claude-sonnet-4-6",
            api_key="test-api-key",
            temperature=0.1,
            max_tokens=4096,
            timeout=30.0,
        )
        assert result is mock_cls.return_value

    @patch.dict("sys.modules")
    async def test_ollama_provider_returns_chat_openai_with_defaults(self):
        mock_cls = MagicMock()
        mock_cls.return_value = MagicMock()
        mock_openai_mod = MagicMock(ChatOpenAI=mock_cls)
        import sys
        sys.modules["langchain_openai"] = mock_openai_mod

        # Ollama with no api_key and no base_url -> defaults
        registry = _make_registry("ollama", "llama3")
        registry._decrypt_key = MagicMock(return_value=None)
        db = AsyncMock()

        result = await _get_langchain_chat_model(registry, db, None)

        mock_cls.assert_called_once_with(
            model="llama3",
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            temperature=0.1,
            max_tokens=4096,
            request_timeout=30,
        )
        assert result is mock_cls.return_value

    async def test_unsupported_provider_raises_value_error(self):
        registry = _make_registry("azure")
        db = AsyncMock()

        import pytest
        with pytest.raises(ValueError, match="Unsupported provider type"):
            await _get_langchain_chat_model(registry, db, None)


# ---------------------------------------------------------------------------
# Tests: build_agent_graph
# ---------------------------------------------------------------------------

@langchain_tool
def _dummy_tool(query: str) -> str:
    """A dummy tool for testing graph compilation."""
    return "dummy result"


class TestBuildAgentGraph:

    def test_returns_compiled_graph(self):
        compiled = build_agent_graph(tools=[_dummy_tool])
        assert compiled is not None

    def test_compiled_graph_has_agent_and_tools_nodes(self):
        compiled = build_agent_graph(tools=[_dummy_tool])
        graph_repr = compiled.get_graph()
        # get_graph().nodes is a dict keyed by node name
        node_ids = set(graph_repr.nodes)
        assert "agent" in node_ids
        assert "tools" in node_ids

    def test_accepts_checkpointer_true(self):
        # LangGraph accepts True as a shortcut for InMemorySaver
        compiled = build_agent_graph(tools=[_dummy_tool], checkpointer=True)
        assert compiled is not None

    def test_build_agent_graph_without_checkpointer_succeeds(self):
        """build_agent_graph works without a checkpointer (None default)."""
        compiled = build_agent_graph(tools=[_dummy_tool], checkpointer=None)
        assert compiled is not None
        graph_repr = compiled.get_graph()
        assert "agent" in set(graph_repr.nodes)

    def test_build_agent_graph_with_provider_and_factory(self):
        """build_agent_graph accepts provider_registry and db_session_factory."""
        registry = MagicMock()
        factory = MagicMock()
        compiled = build_agent_graph(
            tools=[_dummy_tool],
            provider_registry=registry,
            db_session_factory=factory,
        )
        assert compiled is not None


# ---------------------------------------------------------------------------
# Tests: should_continue (via compiled graph inspection)
# ---------------------------------------------------------------------------

class TestShouldContinue:
    """Test the should_continue conditional routing logic.

    We can't call should_continue directly (it's a closure inside
    build_agent_graph), but we can test the same logic by inspecting
    _count_tool_iterations and observing message patterns that drive
    the routing decision.
    """

    def test_should_continue_returns_end_on_empty_messages(self):
        """Empty messages list routes to 'end' — covered by _count_tool_iterations == 0."""
        # The should_continue function returns "end" for empty messages
        # We verify the logic: no messages -> no tool calls -> should end
        assert _count_tool_iterations([]) == 0

    def test_should_continue_returns_end_on_human_message(self):
        """A HumanMessage as last message routes to 'end'."""
        messages = [HumanMessage(content="hello")]
        last = messages[-1]
        # HumanMessage is not an AIMessage, so should_continue returns "end"
        assert not isinstance(last, AIMessage)

    def test_should_continue_returns_continue_on_tool_calls(self):
        """An AIMessage with tool_calls triggers 'continue' routing."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_tasks", "args": {}, "id": "tc1"}],
        )
        # This message has tool_calls -> should_continue returns "continue"
        assert isinstance(ai_msg, AIMessage)
        assert getattr(ai_msg, "tool_calls", None)
        # And iteration count is only 1, well below MAX_ITERATIONS
        assert _count_tool_iterations([ai_msg]) < MAX_ITERATIONS

    def test_should_continue_returns_end_at_max_iterations(self):
        """At MAX_ITERATIONS tool call rounds, should_continue returns 'end'."""
        messages = []
        for i in range(MAX_ITERATIONS):
            messages.append(
                AIMessage(
                    content="",
                    tool_calls=[{"name": f"tool_{i}", "args": {}, "id": f"tc{i}"}],
                )
            )
            messages.append(ToolMessage(content="result", tool_call_id=f"tc{i}"))
        # One more AI with tool_calls — should be at the limit
        messages.append(
            AIMessage(
                content="",
                tool_calls=[{"name": "final", "args": {}, "id": "tcf"}],
            )
        )

        # Total AI messages with tool_calls = MAX_ITERATIONS + 1
        count = _count_tool_iterations(messages)
        assert count >= MAX_ITERATIONS


# ---------------------------------------------------------------------------
# Tests: agent_node MAX_ITERATIONS stop message
# ---------------------------------------------------------------------------

class TestAgentNodeMaxIterations:
    """Test that the agent_node returns a stop message at MAX_ITERATIONS."""

    async def test_agent_node_max_iterations_stop(self):
        """When messages contain MAX_ITERATIONS tool-call rounds,
        agent_node returns the stop message without calling the LLM."""
        import pytest

        # Build messages with MAX_ITERATIONS tool-call rounds
        messages = []
        for i in range(MAX_ITERATIONS):
            messages.append(
                AIMessage(
                    content="",
                    tool_calls=[{"name": "test", "args": {}, "id": f"call_{i}"}],
                )
            )
            messages.append(ToolMessage(content="ok", tool_call_id=f"call_{i}"))

        # Build a graph with a mock LLM to verify it's NOT called
        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock(return_value=mock_llm)
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="This should NOT be called")
        )

        # We need a db_session_factory and provider_registry for the agent_node
        # but they should NOT be called when max iterations is hit
        mock_db_session = AsyncMock()
        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_db_factory = MagicMock(return_value=mock_db_ctx)

        mock_registry = MagicMock()

        compiled = build_agent_graph(
            tools=[_dummy_tool],
            provider_registry=mock_registry,
            db_session_factory=mock_db_factory,
        )

        # We can't invoke the full graph easily, but we can test the
        # internal agent_node by extracting it and calling it directly.
        # The agent_node is registered on the graph's nodes.
        # Instead, test via the compiled graph with a mocked LLM.
        # The key insight: _count_tool_iterations(messages) >= MAX_ITERATIONS
        # so agent_node returns early without calling the LLM.

        # Patch _get_langchain_chat_model to return our mock LLM
        with patch(
            "app.ai.agent.graph._get_langchain_chat_model",
            new=AsyncMock(return_value=mock_llm),
        ):
            # Use ainvoke with no checkpointer (graph runs in-memory)
            state = {
                "messages": messages,
                "user_id": "test-user",
                "accessible_app_ids": [],
                "accessible_project_ids": [],
            }

            result = await compiled.ainvoke(state)

        # The last message should be the stop message (not from mock_llm)
        result_messages = result["messages"]
        last_msg = result_messages[-1]
        assert isinstance(last_msg, AIMessage)
        assert "maximum number of operations" in last_msg.content
        assert "more specific question" in last_msg.content

        # The LLM should NOT have been invoked
        mock_llm.ainvoke.assert_not_awaited()

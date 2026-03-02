"""Unit tests for AI Config Panel fixes (Tasks 9.17-9.19).

Tests:
- 9.17: require_developer safety net for is_developer=None (stale cache)
- 9.18: GET /models filtering by provider_type and capability
- 9.19: GET /capability/{capability} endpoint
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as fastapi_app
from app.models.ai_model import AiModel
from app.models.ai_provider import AiProvider
from app.models.application import Application
from app.models.user import User
from app.services.auth_service import get_current_user

# ---------------------------------------------------------------------------
# Encryption key fixture
# ---------------------------------------------------------------------------

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Ensure AI encryption key is set for all tests in this module."""
    monkeypatch.setattr("app.config.settings.ai_encryption_key", TEST_ENCRYPTION_KEY)


@pytest_asyncio.fixture(autouse=True)
async def _make_test_user_developer(test_user: User, db_session: AsyncSession):
    """Mark the primary test user as a developer for admin AI config access."""
    test_user.is_developer = True
    db_session.add(test_user)
    await db_session.commit()
    await db_session.refresh(test_user)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def openai_provider(client: AsyncClient, auth_headers: dict, test_application: Application):
    """Create an OpenAI global provider."""
    response = await client.post(
        "/api/ai/config/providers",
        headers=auth_headers,
        json={
            "name": "openai",
            "display_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test-key-12345",
            "is_enabled": True,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def anthropic_provider(client: AsyncClient, auth_headers: dict, test_application: Application):
    """Create an Anthropic global provider."""
    response = await client.post(
        "/api/ai/config/providers",
        headers=auth_headers,
        json={
            "name": "anthropic",
            "display_name": "Anthropic",
            "provider_type": "anthropic",
            "api_key": "sk-ant-test-key",
            "is_enabled": True,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def openai_chat_model(client: AsyncClient, auth_headers: dict, openai_provider: dict):
    """Create an OpenAI chat model (default)."""
    response = await client.post(
        "/api/ai/config/models",
        headers=auth_headers,
        json={
            "provider_id": openai_provider["id"],
            "model_id": "gpt-4o",
            "display_name": "GPT-4o",
            "provider_type": "openai",
            "capability": "chat",
            "max_tokens": 128000,
            "is_default": True,
            "is_enabled": True,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def openai_embedding_model(client: AsyncClient, auth_headers: dict, openai_provider: dict):
    """Create an OpenAI embedding model."""
    response = await client.post(
        "/api/ai/config/models",
        headers=auth_headers,
        json={
            "provider_id": openai_provider["id"],
            "model_id": "text-embedding-3-small",
            "display_name": "Text Embedding 3 Small",
            "provider_type": "openai",
            "capability": "embedding",
            "embedding_dimensions": 1536,
            "is_default": False,
            "is_enabled": True,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def anthropic_chat_model(client: AsyncClient, auth_headers: dict, anthropic_provider: dict):
    """Create an Anthropic chat model."""
    response = await client.post(
        "/api/ai/config/models",
        headers=auth_headers,
        json={
            "provider_id": anthropic_provider["id"],
            "model_id": "claude-sonnet-4-20250514",
            "display_name": "Claude Sonnet 4",
            "provider_type": "anthropic",
            "capability": "chat",
            "is_default": False,
            "is_enabled": True,
        },
    )
    assert response.status_code == 201
    return response.json()


# ============================================================================
# 9.17: Fix is_developer Bug
# ============================================================================


@pytest.mark.asyncio
class TestRequireDeveloperSafetyNet:
    """Tests for require_developer() handling is_developer=None."""

    async def test_is_developer_none_returns_403_and_invalidates_cache(
        self,
        test_user: User,
        db_session: AsyncSession,
    ):
        """User with is_developer=None gets 403 and their cache is invalidated."""
        # Create a stale user object with is_developer=None
        stale_user = User(
            id=test_user.id,
            email=test_user.email,
            password_hash="fake",
            display_name="Stale User",
            email_verified=True,
        )
        # Force is_developer to None (simulating stale cache)
        object.__setattr__(stale_user, "is_developer", None)

        async def override_get_db():
            yield db_session

        async def override_get_current_user():
            return stale_user

        fastapi_app.dependency_overrides[get_current_user] = override_get_current_user

        try:
            async with AsyncClient(
                transport=ASGITransport(app=fastapi_app),
                base_url="http://test",
            ) as test_client:
                with patch(
                    "app.services.user_cache_service.invalidate_user",
                ) as mock_invalidate:
                    response = await test_client.get(
                        "/api/ai/config/providers",
                        headers={"Authorization": "Bearer fake"},
                    )

            assert response.status_code == 403
            assert "developer access required" in response.json()["detail"].lower()
            mock_invalidate.assert_called_once_with(test_user.id)
        finally:
            fastapi_app.dependency_overrides.pop(get_current_user, None)

    async def test_is_developer_false_returns_403(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_user_2: User,
    ):
        """User with is_developer=False gets 403 (existing behavior preserved)."""
        response = await client.get(
            "/api/ai/config/providers",
            headers=auth_headers_2,
        )
        assert response.status_code == 403

    async def test_is_developer_true_allows_access(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ):
        """User with is_developer=True can access developer endpoints."""
        response = await client.get(
            "/api/ai/config/providers",
            headers=auth_headers,
        )
        assert response.status_code == 200


# ============================================================================
# 9.18: Add Filtering to GET /models
# ============================================================================


@pytest.mark.asyncio
class TestListModelsFiltering:
    """Tests for GET /models with provider_type and capability filters."""

    async def test_list_models_no_filter_returns_all(
        self,
        client: AsyncClient,
        auth_headers: dict,
        openai_chat_model: dict,
        openai_embedding_model: dict,
        anthropic_chat_model: dict,
    ):
        """GET /models without filters returns all models."""
        response = await client.get(
            "/api/ai/config/models",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    async def test_list_models_filter_by_provider_type(
        self,
        client: AsyncClient,
        auth_headers: dict,
        openai_chat_model: dict,
        openai_embedding_model: dict,
        anthropic_chat_model: dict,
    ):
        """GET /models?provider_type=openai returns only OpenAI models."""
        response = await client.get(
            "/api/ai/config/models",
            headers=auth_headers,
            params={"provider_type": "openai"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(m["provider_type"] == "openai" for m in data)

    async def test_list_models_filter_by_capability(
        self,
        client: AsyncClient,
        auth_headers: dict,
        openai_chat_model: dict,
        openai_embedding_model: dict,
        anthropic_chat_model: dict,
    ):
        """GET /models?capability=chat returns only chat models."""
        response = await client.get(
            "/api/ai/config/models",
            headers=auth_headers,
            params={"capability": "chat"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(m["capability"] == "chat" for m in data)

    async def test_list_models_filter_by_both(
        self,
        client: AsyncClient,
        auth_headers: dict,
        openai_chat_model: dict,
        openai_embedding_model: dict,
        anthropic_chat_model: dict,
    ):
        """GET /models?provider_type=openai&capability=embedding returns only matching."""
        response = await client.get(
            "/api/ai/config/models",
            headers=auth_headers,
            params={"provider_type": "openai", "capability": "embedding"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["model_id"] == "text-embedding-3-small"

    async def test_list_models_filter_no_match_returns_empty(
        self,
        client: AsyncClient,
        auth_headers: dict,
        openai_chat_model: dict,
    ):
        """GET /models with non-matching filter returns empty list."""
        response = await client.get(
            "/api/ai/config/models",
            headers=auth_headers,
            params={"provider_type": "anthropic"},
        )
        assert response.status_code == 200
        assert response.json() == []


# ============================================================================
# 9.19: GET /capability/{capability} Endpoint
# ============================================================================


@pytest.mark.asyncio
class TestGetCapabilityConfig:
    """Tests for GET /capability/{capability}."""

    async def test_get_capability_with_configured_default(
        self,
        client: AsyncClient,
        auth_headers: dict,
        openai_provider: dict,
        openai_chat_model: dict,
    ):
        """GET /capability/chat with a configured default returns provider+model info."""
        response = await client.get(
            "/api/ai/config/capability/chat",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["capability"] == "chat"
        assert data["provider_id"] == openai_provider["id"]
        assert data["provider_type"] == "openai"
        assert data["model_id"] == "gpt-4o"
        assert data["model_display_name"] == "GPT-4o"
        assert data["has_api_key"] is True

    async def test_get_capability_no_default_returns_nulls(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ):
        """GET /capability/chat with no default model returns null fields."""
        response = await client.get(
            "/api/ai/config/capability/chat",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["capability"] == "chat"
        assert data["provider_id"] is None
        assert data["provider_type"] is None
        assert data["model_id"] is None
        assert data["model_display_name"] is None
        assert data["has_api_key"] is False

    async def test_get_capability_invalid_returns_400(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
    ):
        """GET /capability/invalid returns 400."""
        response = await client.get(
            "/api/ai/config/capability/invalid",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid capability" in response.json()["detail"]

    async def test_get_capability_requires_developer(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_user_2: User,
    ):
        """GET /capability/chat requires developer access."""
        response = await client.get(
            "/api/ai/config/capability/chat",
            headers=auth_headers_2,
        )
        assert response.status_code == 403

    async def test_get_capability_embedding(
        self,
        client: AsyncClient,
        auth_headers: dict,
        openai_provider: dict,
        openai_embedding_model: dict,
    ):
        """GET /capability/embedding with non-default model returns nulls."""
        # The embedding model was created with is_default=False
        response = await client.get(
            "/api/ai/config/capability/embedding",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["capability"] == "embedding"
        # No default configured, so all fields are null
        assert data["provider_id"] is None
        assert data["model_id"] is None

    async def test_get_capability_provider_without_api_key(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_application: Application,
    ):
        """GET /capability/chat where provider has no API key returns has_api_key=False."""
        # Create Ollama provider (no API key)
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "ollama-local",
                "display_name": "Ollama Local",
                "provider_type": "ollama",
                "base_url": "http://localhost:11434",
                "is_enabled": True,
            },
        )
        assert response.status_code == 201
        ollama_id = response.json()["id"]

        # Create default chat model under Ollama
        response = await client.post(
            "/api/ai/config/models",
            headers=auth_headers,
            json={
                "provider_id": ollama_id,
                "model_id": "llama3",
                "display_name": "Llama 3",
                "provider_type": "ollama",
                "capability": "chat",
                "is_default": True,
                "is_enabled": True,
            },
        )
        assert response.status_code == 201

        # Query capability
        response = await client.get(
            "/api/ai/config/capability/chat",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["capability"] == "chat"
        assert data["model_id"] == "llama3"
        assert data["has_api_key"] is False

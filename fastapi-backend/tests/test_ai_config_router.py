"""Integration tests for AI configuration router endpoints.

Tests admin provider/model CRUD, user override endpoints, encryption,
auth guards, and isolation between users and scopes.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_model import AiModel
from app.models.ai_provider import AiProvider
from app.models.application import Application
from app.models.user import User

# ---------------------------------------------------------------------------
# Encryption key fixture
# ---------------------------------------------------------------------------

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Ensure AI encryption key is set for all tests in this module."""
    monkeypatch.setattr("app.config.settings.ai_encryption_key", TEST_ENCRYPTION_KEY)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_provider(client: AsyncClient, auth_headers: dict, test_application: Application):
    """Create a test OpenAI global provider."""
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
async def test_model(client: AsyncClient, auth_headers: dict, test_provider: dict):
    """Create a test AI model under the test provider."""
    response = await client.post(
        "/api/ai/config/models",
        headers=auth_headers,
        json={
            "provider_id": test_provider["id"],
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
async def user_override(client: AsyncClient, auth_headers: dict, test_application: Application):
    """Create a user-scoped provider override."""
    response = await client.post(
        "/api/ai/config/me/providers",
        headers=auth_headers,
        json={
            "provider_type": "openai",
            "api_key": "sk-user-personal-key",
        },
    )
    assert response.status_code == 201
    return response.json()


# ============================================================================
# Admin: Provider CRUD
# ============================================================================


@pytest.mark.asyncio
class TestListProviders:
    """Tests for GET /api/ai/config/providers."""

    async def test_list_providers_empty(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Listing providers when none exist returns empty list."""
        response = await client.get("/api/ai/config/providers", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_providers_returns_data(
        self, client: AsyncClient, auth_headers: dict, test_provider: dict
    ):
        """Listing providers returns previously created providers."""
        response = await client.get("/api/ai/config/providers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "openai"
        assert data[0]["provider_type"] == "openai"
        assert data[0]["scope"] == "global"


@pytest.mark.asyncio
class TestCreateProvider:
    """Tests for POST /api/ai/config/providers."""

    async def test_create_provider_openai(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Creating an OpenAI provider succeeds with 201."""
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "openai-prod",
                "display_name": "OpenAI Production",
                "provider_type": "openai",
                "api_key": "sk-prod-key-abc",
                "is_enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "openai-prod"
        assert data["provider_type"] == "openai"
        assert data["is_enabled"] is True
        assert data["scope"] == "global"
        assert data["has_api_key"] is True
        # API key itself must not be exposed
        assert "api_key" not in data
        assert "api_key_encrypted" not in data

    async def test_create_provider_ollama_no_key(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Ollama provider can be created without an API key."""
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
        data = response.json()
        assert data["provider_type"] == "ollama"
        assert data["has_api_key"] is False
        assert data["base_url"] == "http://localhost:11434"

    async def test_create_provider_validates_type(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Invalid provider_type is rejected with 422."""
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "bad",
                "display_name": "Bad Provider",
                "provider_type": "azure",
                "is_enabled": True,
            },
        )
        assert response.status_code == 422

    async def test_create_ollama_provider_rejects_public_url(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Ollama provider with a public URL is rejected (SSRF prevention)."""
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "ollama-bad",
                "display_name": "Ollama Public",
                "provider_type": "ollama",
                "base_url": "http://169.254.169.254",
                "is_enabled": True,
            },
        )
        assert response.status_code == 422
        assert "localhost or a private network" in response.json()["detail"]

    async def test_create_ollama_provider_allows_localhost(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Ollama provider with localhost URL is accepted."""
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "ollama-ok",
                "display_name": "Ollama Local",
                "provider_type": "ollama",
                "base_url": "http://localhost:11434",
                "is_enabled": True,
            },
        )
        assert response.status_code == 201

    async def test_create_ollama_provider_allows_private_network(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Ollama provider with private network IP (10.x, 192.168.x) is accepted."""
        for url in [
            "http://10.0.0.5:11434",
            "http://192.168.1.100:11434",
            "http://172.16.0.10:11434",
        ]:
            response = await client.post(
                "/api/ai/config/providers",
                headers=auth_headers,
                json={
                    "name": f"ollama-private-{url.split('//')[1].split(':')[0].replace('.', '-')}",
                    "display_name": "Ollama Private",
                    "provider_type": "ollama",
                    "base_url": url,
                    "is_enabled": True,
                },
            )
            assert response.status_code == 201, f"Expected 201 for {url}, got {response.status_code}"

    async def test_create_ollama_provider_rejects_metadata_ip(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Ollama provider with cloud metadata endpoint IP is rejected."""
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "ollama-metadata",
                "display_name": "Ollama Metadata",
                "provider_type": "ollama",
                "base_url": "http://169.254.169.254/latest/meta-data",
                "is_enabled": True,
            },
        )
        assert response.status_code == 422

    async def test_create_ollama_provider_rejects_external_dns(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Ollama provider with external DNS hostname is rejected."""
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "ollama-external",
                "display_name": "Ollama External",
                "provider_type": "ollama",
                "base_url": "http://evil.example.com:11434",
                "is_enabled": True,
            },
        )
        assert response.status_code == 422

    async def test_create_provider_encrypts_key(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        db_session: AsyncSession,
    ):
        """The stored api_key_encrypted is a valid Fernet ciphertext."""
        raw_key = "sk-plaintext-secret-key"
        response = await client.post(
            "/api/ai/config/providers",
            headers=auth_headers,
            json={
                "name": "enc-test",
                "display_name": "Encryption Test",
                "provider_type": "openai",
                "api_key": raw_key,
                "is_enabled": True,
            },
        )
        assert response.status_code == 201
        provider_id = response.json()["id"]

        # Query the DB directly to verify encryption
        result = await db_session.execute(
            select(AiProvider).where(AiProvider.id == provider_id)
        )
        provider = result.scalar_one()
        assert provider.api_key_encrypted is not None
        assert provider.api_key_encrypted != raw_key

        # Decrypt and verify it matches the original
        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())
        decrypted = fernet.decrypt(provider.api_key_encrypted.encode()).decode()
        assert decrypted == raw_key


@pytest.mark.asyncio
class TestGetProvider:
    """Tests for provider response security."""

    async def test_get_provider_does_not_expose_key(
        self, client: AsyncClient, auth_headers: dict, test_provider: dict
    ):
        """Provider responses never contain the actual or encrypted API key."""
        response = await client.get("/api/ai/config/providers", headers=auth_headers)
        assert response.status_code == 200
        provider = response.json()[0]
        assert "api_key" not in provider
        assert "api_key_encrypted" not in provider
        assert provider["has_api_key"] is True


@pytest.mark.asyncio
class TestUpdateProvider:
    """Tests for PUT /api/ai/config/providers/{provider_id}."""

    async def test_update_provider_preserves_key_if_not_sent(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_provider: dict,
        db_session: AsyncSession,
    ):
        """Omitting api_key in update keeps existing encrypted key."""
        provider_id = test_provider["id"]

        # Get original encrypted key
        result = await db_session.execute(
            select(AiProvider).where(AiProvider.id == provider_id)
        )
        original_encrypted = result.scalar_one().api_key_encrypted

        # Update only display_name (no api_key in body)
        response = await client.put(
            f"/api/ai/config/providers/{provider_id}",
            headers=auth_headers,
            json={"display_name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Updated Name"

        # Re-query to confirm encrypted key is preserved
        result = await db_session.execute(
            select(AiProvider).where(AiProvider.id == provider_id)
        )
        assert result.scalar_one().api_key_encrypted == original_encrypted

    async def test_update_provider_re_encrypts_new_key(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_provider: dict,
        db_session: AsyncSession,
    ):
        """Sending a new api_key re-encrypts it in the database."""
        provider_id = test_provider["id"]
        new_key = "sk-brand-new-key"

        response = await client.put(
            f"/api/ai/config/providers/{provider_id}",
            headers=auth_headers,
            json={"api_key": new_key},
        )
        assert response.status_code == 200

        # Verify new encrypted value decrypts to the new key
        result = await db_session.execute(
            select(AiProvider).where(AiProvider.id == provider_id)
        )
        provider = result.scalar_one()
        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())
        decrypted = fernet.decrypt(provider.api_key_encrypted.encode()).decode()
        assert decrypted == new_key


@pytest.mark.asyncio
class TestDeleteProvider:
    """Tests for DELETE /api/ai/config/providers/{provider_id}."""

    async def test_delete_provider_cascades_models(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_provider: dict,
        test_model: dict,
        db_session: AsyncSession,
    ):
        """Deleting a provider cascades to delete its models."""
        provider_id = test_provider["id"]
        model_id = test_model["id"]

        response = await client.delete(
            f"/api/ai/config/providers/{provider_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify provider is gone
        result = await db_session.execute(
            select(AiProvider).where(AiProvider.id == provider_id)
        )
        assert result.scalar_one_or_none() is None

        # Verify model is also gone (CASCADE)
        result = await db_session.execute(
            select(AiModel).where(AiModel.id == model_id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
class TestTestProvider:
    """Tests for POST /api/ai/config/providers/{provider_id}/test."""

    async def test_test_provider_connectivity_success(
        self, client: AsyncClient, auth_headers: dict, test_provider: dict
    ):
        """Successful connectivity test returns success=True."""
        provider_id = test_provider["id"]

        with patch(
            "app.routers.ai_config._test_openai",
            new_callable=AsyncMock,
            return_value={"success": True, "message": "OpenAI API connection successful"},
        ):
            response = await client.post(
                f"/api/ai/config/providers/{provider_id}/test",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_test_provider_connectivity_failure(
        self, client: AsyncClient, auth_headers: dict, test_provider: dict
    ):
        """Failed connectivity test returns success=False with error."""
        provider_id = test_provider["id"]

        with patch(
            "app.routers.ai_config._test_openai",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            response = await client.post(
                f"/api/ai/config/providers/{provider_id}/test",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Connection refused" in data["error"]


# ============================================================================
# Admin: Model CRUD
# ============================================================================


@pytest.mark.asyncio
class TestCreateModel:
    """Tests for model CRUD endpoints."""

    async def test_create_model(
        self, client: AsyncClient, auth_headers: dict, test_provider: dict
    ):
        """Creating a model under an existing provider succeeds."""
        response = await client.post(
            "/api/ai/config/models",
            headers=auth_headers,
            json={
                "provider_id": test_provider["id"],
                "model_id": "gpt-4o-mini",
                "display_name": "GPT-4o Mini",
                "provider_type": "openai",
                "capability": "chat",
                "max_tokens": 16384,
                "is_default": False,
                "is_enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["model_id"] == "gpt-4o-mini"
        assert data["capability"] == "chat"
        assert data["provider_id"] == test_provider["id"]

    async def test_create_model_unique_constraint(
        self, client: AsyncClient, auth_headers: dict, test_provider: dict
    ):
        """Duplicate (provider_id, model_id, capability) is rejected."""
        model_payload = {
            "provider_id": test_provider["id"],
            "model_id": "gpt-4o",
            "display_name": "GPT-4o",
            "provider_type": "openai",
            "capability": "chat",
            "is_default": True,
            "is_enabled": True,
        }
        # First creation should succeed
        resp1 = await client.post(
            "/api/ai/config/models",
            headers=auth_headers,
            json=model_payload,
        )
        assert resp1.status_code == 201

        # Duplicate should fail (DB unique constraint)
        resp2 = await client.post(
            "/api/ai/config/models",
            headers=auth_headers,
            json=model_payload,
        )
        assert resp2.status_code in (409, 500)

    async def test_update_model(
        self, client: AsyncClient, auth_headers: dict, test_model: dict
    ):
        """Updating model fields succeeds."""
        model_id = test_model["id"]
        response = await client.put(
            f"/api/ai/config/models/{model_id}",
            headers=auth_headers,
            json={"display_name": "GPT-4o Updated", "max_tokens": 256000},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "GPT-4o Updated"
        assert data["max_tokens"] == 256000

    async def test_delete_model(
        self, client: AsyncClient, auth_headers: dict, test_model: dict
    ):
        """Deleting a model returns 204 and removes it."""
        model_id = test_model["id"]
        response = await client.delete(
            f"/api/ai/config/models/{model_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify it's gone via list
        response = await client.get("/api/ai/config/models", headers=auth_headers)
        assert response.status_code == 200
        model_ids = [m["id"] for m in response.json()]
        assert model_id not in model_ids


# ============================================================================
# Admin: Config Summary
# ============================================================================


@pytest.mark.asyncio
class TestConfigSummary:
    """Tests for GET /api/ai/config/summary."""

    async def test_config_summary(
        self, client: AsyncClient, auth_headers: dict, test_provider: dict, test_model: dict
    ):
        """Summary includes providers and resolves default models."""
        response = await client.get("/api/ai/config/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["providers"]) >= 1
        # test_model is marked as default chat
        assert data["default_chat_model"] is not None
        assert data["default_chat_model"]["model_id"] == "gpt-4o"


# ============================================================================
# Admin: Auth guard
# ============================================================================


@pytest.mark.asyncio
class TestAdminAuth:
    """Tests for admin-only access (require_ai_admin dependency)."""

    async def test_non_owner_gets_403(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_user_2: User,
    ):
        """A user who owns no application gets 403 on admin endpoints."""
        response = await client.get("/api/ai/config/providers", headers=auth_headers_2)
        assert response.status_code == 403
        assert "application ownership" in response.json()["detail"].lower()

    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        """Requests without auth token get 401."""
        response = await client.get("/api/ai/config/providers")
        assert response.status_code == 401


# ============================================================================
# User Override Endpoints (/me)
# ============================================================================


@pytest.mark.asyncio
class TestUserCreateOverride:
    """Tests for POST /api/ai/config/me/providers."""

    async def test_user_create_override_openai(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Any authenticated user can create a personal provider override."""
        response = await client.post(
            "/api/ai/config/me/providers",
            headers=auth_headers,
            json={
                "provider_type": "openai",
                "api_key": "sk-my-personal-key",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "user"
        assert data["provider_type"] == "openai"
        assert data["has_api_key"] is True
        assert "api_key" not in data
        assert "api_key_encrypted" not in data

    async def test_user_create_override_encrypts_key(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        db_session: AsyncSession,
    ):
        """User override API key is encrypted in database."""
        raw_key = "sk-user-secret-key-999"
        response = await client.post(
            "/api/ai/config/me/providers",
            headers=auth_headers,
            json={
                "provider_type": "anthropic",
                "api_key": raw_key,
            },
        )
        assert response.status_code == 201
        provider_id = response.json()["id"]

        result = await db_session.execute(
            select(AiProvider).where(AiProvider.id == provider_id)
        )
        provider = result.scalar_one()
        assert provider.api_key_encrypted is not None
        assert provider.api_key_encrypted != raw_key

        fernet = Fernet(TEST_ENCRYPTION_KEY.encode())
        decrypted = fernet.decrypt(provider.api_key_encrypted.encode()).decode()
        assert decrypted == raw_key

    async def test_user_create_override_duplicate_409(
        self, client: AsyncClient, auth_headers: dict, user_override: dict
    ):
        """Creating a duplicate override for the same provider_type returns 409."""
        response = await client.post(
            "/api/ai/config/me/providers",
            headers=auth_headers,
            json={
                "provider_type": "openai",
                "api_key": "sk-another-key",
            },
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
class TestUserListOverrides:
    """Tests for GET /api/ai/config/me/providers."""

    async def test_user_list_own_overrides(
        self, client: AsyncClient, auth_headers: dict, user_override: dict
    ):
        """User sees only their own overrides."""
        response = await client.get("/api/ai/config/me/providers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["provider_type"] == "openai"
        assert data[0]["scope"] == "user"

    async def test_user_cannot_see_other_users_overrides(
        self,
        client: AsyncClient,
        auth_headers: dict,
        auth_headers_2: dict,
        test_user_2: User,
        user_override: dict,
    ):
        """User 2 cannot see user 1's overrides."""
        response = await client.get("/api/ai/config/me/providers", headers=auth_headers_2)
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
class TestUserUpdateOverride:
    """Tests for PUT /api/ai/config/me/providers/{provider_type}."""

    async def test_user_update_override_model_preference(
        self, client: AsyncClient, auth_headers: dict, user_override: dict
    ):
        """Updating a user override replaces the API key."""
        response = await client.put(
            "/api/ai/config/me/providers/openai",
            headers=auth_headers,
            json={
                "provider_type": "openai",
                "api_key": "sk-updated-personal-key",
            },
        )
        assert response.status_code == 200
        assert response.json()["has_api_key"] is True

    async def test_user_update_nonexistent_override_404(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Updating an override that doesn't exist returns 404."""
        response = await client.put(
            "/api/ai/config/me/providers/anthropic",
            headers=auth_headers,
            json={
                "provider_type": "anthropic",
                "api_key": "sk-some-key",
            },
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestUserDeleteOverride:
    """Tests for DELETE /api/ai/config/me/providers/{provider_type}."""

    async def test_user_delete_override_reverts_to_global(
        self, client: AsyncClient, auth_headers: dict, user_override: dict
    ):
        """Deleting a user override returns 204 and removes it."""
        response = await client.delete(
            "/api/ai/config/me/providers/openai",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Confirm the override is gone
        response = await client.get("/api/ai/config/me/providers", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_user_delete_nonexistent_override_404(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Deleting an override that doesn't exist returns 404."""
        response = await client.delete(
            "/api/ai/config/me/providers/anthropic",
            headers=auth_headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestUserTestOverride:
    """Tests for POST /api/ai/config/me/providers/{provider_type}/test."""

    async def test_user_test_own_key_connectivity(
        self, client: AsyncClient, auth_headers: dict, user_override: dict
    ):
        """User can test connectivity for their own override."""
        with patch(
            "app.routers.ai_config._test_openai",
            new_callable=AsyncMock,
            return_value={"success": True, "message": "OpenAI API connection successful"},
        ):
            response = await client.post(
                "/api/ai/config/me/providers/openai/test",
                headers=auth_headers,
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_user_test_nonexistent_override_404(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Testing an override that doesn't exist returns 404."""
        response = await client.post(
            "/api/ai/config/me/providers/anthropic/test",
            headers=auth_headers,
        )
        assert response.status_code == 404


# ============================================================================
# User Summary
# ============================================================================


@pytest.mark.asyncio
class TestUserSummary:
    """Tests for GET /api/ai/config/me/summary."""

    async def test_user_summary_with_override(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_provider: dict,
        test_model: dict,
        user_override: dict,
    ):
        """User summary includes their override in place of global for same type."""
        response = await client.get("/api/ai/config/me/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should have providers (user override replaces global for openai)
        openai_providers = [
            p for p in data["providers"] if p["provider_type"] == "openai"
        ]
        # Exactly one openai provider - the user override
        assert len(openai_providers) == 1
        assert openai_providers[0]["scope"] == "user"

    async def test_user_summary_without_override_shows_global(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_provider: dict,
        test_model: dict,
    ):
        """Without override, user summary shows global providers."""
        response = await client.get("/api/ai/config/me/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        openai_providers = [
            p for p in data["providers"] if p["provider_type"] == "openai"
        ]
        assert len(openai_providers) == 1
        assert openai_providers[0]["scope"] == "global"
        # Default chat model from global config
        assert data["default_chat_model"] is not None
        assert data["default_chat_model"]["model_id"] == "gpt-4o"


# ============================================================================
# User Isolation
# ============================================================================


@pytest.mark.asyncio
class TestUserIsolation:
    """Tests for multi-user isolation of overrides vs global config."""

    async def test_user_override_does_not_affect_global(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_provider: dict,
        user_override: dict,
    ):
        """Creating a user override does not modify the global provider."""
        response = await client.get("/api/ai/config/providers", headers=auth_headers)
        assert response.status_code == 200
        global_providers = response.json()
        # The global provider is still there, unchanged
        assert len(global_providers) == 1
        assert global_providers[0]["scope"] == "global"
        assert global_providers[0]["id"] == test_provider["id"]

    async def test_any_authenticated_user_can_set_override(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_user_2: User,
    ):
        """Even a non-admin user can create personal overrides via /me."""
        response = await client.post(
            "/api/ai/config/me/providers",
            headers=auth_headers_2,
            json={
                "provider_type": "anthropic",
                "api_key": "sk-user2-anthropic-key",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "user"
        assert data["provider_type"] == "anthropic"

        # User 2 can list their own overrides
        response = await client.get(
            "/api/ai/config/me/providers",
            headers=auth_headers_2,
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

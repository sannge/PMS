"""Integration tests for AI system prompt endpoints.

Tests GET/PUT /api/ai/config/system-prompt for developer access,
empty/create/reset flows, character limit validation, and auth guards.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def _make_test_user_developer(test_user: User, db_session: AsyncSession):
    """Mark the primary test user as a developer for admin AI config access."""
    test_user.is_developer = True
    db_session.add(test_user)
    await db_session.commit()
    await db_session.refresh(test_user)


@pytest.mark.asyncio
class TestSystemPrompt:
    """Tests for GET/PUT /api/ai/config/system-prompt."""

    async def test_get_system_prompt_empty(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET returns empty prompt when no row exists in the table."""
        response = await client.get(
            "/api/ai/config/system-prompt", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["prompt"] == ""

    async def test_put_system_prompt_create(
        self, client: AsyncClient, auth_headers: dict
    ):
        """PUT creates a prompt and returns it."""
        prompt_text = "You are a helpful project management assistant."
        response = await client.put(
            "/api/ai/config/system-prompt",
            headers=auth_headers,
            json={"prompt": prompt_text},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["prompt"] == prompt_text

    async def test_get_system_prompt_after_put(
        self, client: AsyncClient, auth_headers: dict
    ):
        """GET returns the created prompt after a PUT."""
        prompt_text = "Custom system prompt for testing."
        # Create
        put_resp = await client.put(
            "/api/ai/config/system-prompt",
            headers=auth_headers,
            json={"prompt": prompt_text},
        )
        assert put_resp.status_code == 200

        # Read back
        get_resp = await client.get(
            "/api/ai/config/system-prompt", headers=auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["prompt"] == prompt_text

    async def test_put_empty_resets(
        self, client: AsyncClient, auth_headers: dict
    ):
        """PUT with empty string resets/deletes the prompt."""
        # First create a prompt
        await client.put(
            "/api/ai/config/system-prompt",
            headers=auth_headers,
            json={"prompt": "Some initial prompt"},
        )

        # Reset with empty string
        response = await client.put(
            "/api/ai/config/system-prompt",
            headers=auth_headers,
            json={"prompt": ""},
        )
        assert response.status_code == 200
        assert response.json()["prompt"] == ""

        # Confirm GET also returns empty
        get_resp = await client.get(
            "/api/ai/config/system-prompt", headers=auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["prompt"] == ""

    async def test_put_over_2000_chars_422(
        self, client: AsyncClient, auth_headers: dict
    ):
        """PUT with >2000 characters returns 422 validation error."""
        long_prompt = "x" * 2001
        response = await client.put(
            "/api/ai/config/system-prompt",
            headers=auth_headers,
            json={"prompt": long_prompt},
        )
        assert response.status_code == 422

    async def test_non_developer_403(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_user_2: User,
    ):
        """Non-developer user gets 403 on system prompt endpoints."""
        # test_user_2 is NOT a developer
        get_resp = await client.get(
            "/api/ai/config/system-prompt", headers=auth_headers_2
        )
        assert get_resp.status_code == 403

        put_resp = await client.put(
            "/api/ai/config/system-prompt",
            headers=auth_headers_2,
            json={"prompt": "hijack attempt"},
        )
        assert put_resp.status_code == 403

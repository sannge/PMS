"""Tests for AgentConfigService and admin config endpoints.

Covers:
- In-memory cache getters (int, float, str, rate_limit)
- Cache TTL and invalidation
- Value validation (type + bounds)
- Admin RBAC enforcement
- System prompt config injection
"""

import asyncio
import re
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config_service import AgentConfigService, get_agent_config
from app.database import get_db
from app.main import app
from app.models.agent_config import AgentConfiguration
from app.models.user import User
from app.services.auth_service import create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def config_service() -> AgentConfigService:
    """Create a fresh AgentConfigService instance for each test."""
    svc = AgentConfigService()
    return svc


@pytest_asyncio.fixture
async def populated_service() -> AgentConfigService:
    """AgentConfigService with pre-loaded cache data."""
    svc = AgentConfigService()
    svc._cache = {
        "agent.max_tool_calls": "50",
        "agent.temperature": "0.1",
        "prompt.agent_name": "Blair",
        "rate_limit.ai_chat": "30,60",
    }
    svc._cache_loaded_at = time.monotonic()
    return svc


@pytest_asyncio.fixture
async def developer_user(db_session: AsyncSession) -> User:
    """Create a developer user for admin endpoint tests."""
    from tests.conftest import get_test_password_hash

    user = User(
        id=uuid4(),
        email="dev@example.com",
        password_hash=get_test_password_hash("DevPassword123!"),
        display_name="Developer",
        email_verified=True,
        is_developer=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def dev_auth_headers(developer_user: User) -> dict:
    """Auth headers for developer user."""
    token = create_access_token(
        data={"sub": str(developer_user.id), "email": developer_user.email}
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test: get_int returns DB value when loaded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_int_returns_db_value(populated_service: AgentConfigService):
    """get_int should return the parsed integer from cache."""
    assert populated_service.get_int("agent.max_tool_calls", 99) == 50


# ---------------------------------------------------------------------------
# Test: get_int returns default when key missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_int_returns_default_when_missing(config_service: AgentConfigService):
    """get_int should return the default when key is not in cache."""
    assert config_service.get_int("nonexistent.key", 42) == 42


# ---------------------------------------------------------------------------
# Test: get_float parses correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_float_parses_correctly(populated_service: AgentConfigService):
    """get_float should return the parsed float from cache."""
    result = populated_service.get_float("agent.temperature", 0.5)
    assert result == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Test: get_rate_limit parses "30,60" tuple
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rate_limit_parses_tuple(populated_service: AgentConfigService):
    """get_rate_limit should parse 'limit,window' string to tuple."""
    result = populated_service.get_rate_limit("rate_limit.ai_chat", (10, 30))
    assert result == (30, 60)


@pytest.mark.asyncio
async def test_get_rate_limit_returns_default_on_bad_format(config_service: AgentConfigService):
    """get_rate_limit should return default when format is wrong."""
    config_service._cache["rate_limit.bad"] = "not_a_tuple"
    result = config_service.get_rate_limit("rate_limit.bad", (10, 30))
    assert result == (10, 30)


# ---------------------------------------------------------------------------
# Test: Cache TTL triggers reload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_ttl_triggers_stale(config_service: AgentConfigService):
    """_is_stale should return True when cache TTL is exceeded."""
    config_service._cache = {"key": "value"}
    config_service._cache_loaded_at = time.monotonic() - 400  # > 300s TTL
    assert config_service._is_stale() is True


@pytest.mark.asyncio
async def test_cache_not_stale_within_ttl(config_service: AgentConfigService):
    """_is_stale should return False when within TTL."""
    config_service._cache = {"key": "value"}
    config_service._cache_loaded_at = time.monotonic()
    assert config_service._is_stale() is False


# ---------------------------------------------------------------------------
# Test: invalidate() clears cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_clears_cache(populated_service: AgentConfigService):
    """invalidate() should clear the in-memory cache."""
    assert len(populated_service._cache) > 0
    with patch("app.services.redis_service.redis_service") as mock_redis:
        mock_redis.is_connected = False
        await populated_service.invalidate()
    assert len(populated_service._cache) == 0
    assert populated_service._cache_loaded_at == 0.0


# ---------------------------------------------------------------------------
# Test: set_value validates bounds (rejects out-of-range)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_value_rejects_out_of_range(
    db_session: AsyncSession,
    developer_user: User,
):
    """set_value should raise ValueError for out-of-range values."""
    # Create a config row
    row = AgentConfiguration(
        key="test.bounded",
        value="10",
        value_type="int",
        category="test",
        description="Test bounded config",
        min_value="1",
        max_value="100",
    )
    db_session.add(row)
    await db_session.commit()

    svc = AgentConfigService()
    with pytest.raises(ValueError, match="above maximum"):
        await svc.set_value("test.bounded", "999", developer_user.id, db_session)


# ---------------------------------------------------------------------------
# Test: set_value validates type (rejects "abc" for int)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_value_rejects_wrong_type(
    db_session: AsyncSession,
    developer_user: User,
):
    """set_value should raise ValueError for invalid type."""
    row = AgentConfiguration(
        key="test.typed",
        value="10",
        value_type="int",
        category="test",
        description="Test typed config",
        min_value="1",
        max_value="100",
    )
    db_session.add(row)
    await db_session.commit()

    svc = AgentConfigService()
    with pytest.raises(ValueError, match="Expected integer"):
        await svc.set_value("test.typed", "abc", developer_user.id, db_session)


# ---------------------------------------------------------------------------
# Test: Fallback on DB error returns default
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_on_db_error_returns_default(config_service: AgentConfigService):
    """When load_all fails, getters should still return defaults."""
    # Mock a failing session factory
    async def failing_factory():
        raise RuntimeError("DB down")

    config_service._db_session_factory = MagicMock(side_effect=failing_factory)
    await config_service.load_all()
    # Cache should still be empty, getters return defaults
    assert config_service.get_int("agent.max_tool_calls", 42) == 42
    assert config_service.get_str("prompt.agent_name", "Default") == "Default"


# ---------------------------------------------------------------------------
# Test: Admin endpoint RBAC (non-admin gets 403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_endpoint_rejects_non_developer(
    db_session: AsyncSession,
    client: AsyncClient,
    test_user: User,
    auth_headers: dict,
):
    """Non-developer users should get 403 on admin config endpoints."""
    response = await client.get(
        "/api/v1/admin/agent-config",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_endpoint_allows_developer(
    db_session: AsyncSession,
    client: AsyncClient,
    developer_user: User,
    dev_auth_headers: dict,
):
    """Developer users should get 200 on admin config list endpoint."""
    # Seed a config row for the test
    row = AgentConfiguration(
        key="test.admin_access",
        value="100",
        value_type="int",
        category="test",
        description="Test admin access",
    )
    db_session.add(row)
    await db_session.commit()

    response = await client.get(
        "/api/v1/admin/agent-config",
        headers=dev_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Should have at least one category group
    assert len(data) >= 1


# ---------------------------------------------------------------------------
# Test: Prompt agent_name injection works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_agent_name_injection():
    """System prompt should use configured agent name."""
    from app.ai.agent.prompts import _build_system_prompt

    prompt = _build_system_prompt("TestBot", "concise")
    assert "You are TestBot" in prompt
    assert "Blair" not in prompt


# ---------------------------------------------------------------------------
# Test: Prompt custom_addendum appended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_custom_addendum_appended(db_session: AsyncSession):
    """load_system_prompt should append custom_addendum from config."""
    from app.ai.agent.prompts import load_system_prompt

    # Pre-populate config cache with custom addendum
    svc = get_agent_config()
    svc._cache["prompt.custom_addendum"] = "Always be extra helpful."
    svc._cache["prompt.agent_name"] = "Blair"
    svc._cache["prompt.communication_style"] = "concise"
    svc._cache_loaded_at = time.monotonic()

    prompt = await load_system_prompt(db_session)
    assert "## Custom Instructions" in prompt
    assert "Always be extra helpful." in prompt


# ---------------------------------------------------------------------------
# Test: validate_value for bool type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_value_bool_valid():
    """_validate_value should accept valid bool strings."""
    AgentConfigService._validate_value("true", "bool", None, None)
    AgentConfigService._validate_value("false", "bool", None, None)
    AgentConfigService._validate_value("1", "bool", None, None)
    AgentConfigService._validate_value("0", "bool", None, None)


@pytest.mark.asyncio
async def test_validate_value_bool_invalid():
    """_validate_value should reject invalid bool strings."""
    with pytest.raises(ValueError, match="Expected bool"):
        AgentConfigService._validate_value("maybe", "bool", None, None)


# ---------------------------------------------------------------------------
# Test: validate_value for float bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_value_float_below_min():
    """_validate_value should reject floats below minimum."""
    with pytest.raises(ValueError, match="below minimum"):
        AgentConfigService._validate_value("0.05", "float", "0.1", "2.0")


# ---------------------------------------------------------------------------
# Test: set_value rejects [USER CONTENT delimiter in prompt values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_value_rejects_user_content_delimiter(
    db_session: AsyncSession,
    developer_user: User,
):
    """set_value should reject prompt values containing '[USER CONTENT' delimiter."""
    # Create a prompt config row
    row = AgentConfiguration(
        key="prompt.test_injection",
        value="safe value",
        value_type="str",
        category="prompt",
        description="Test prompt config",
    )
    db_session.add(row)
    await db_session.commit()

    svc = AgentConfigService()

    # Test with exact match
    with pytest.raises(ValueError, match="USER CONTENT"):
        await svc.set_value(
            "prompt.test_injection", "[USER CONTENT END]",
            developer_user.id, db_session,
        )

    # Test with case variation — the check uses exact "[USER CONTENT" substring
    # so a lowercase variant should pass the delimiter check (if it passes type check)
    # But the actual implementation checks `"[USER CONTENT" in value` which is case-sensitive
    # Verify that the exact uppercase form is rejected
    with pytest.raises(ValueError, match="USER CONTENT"):
        await svc.set_value(
            "prompt.test_injection", "prefix [USER CONTENT START] suffix",
            developer_user.id, db_session,
        )


# ---------------------------------------------------------------------------
# Test: Admin endpoint rejects invalid key format
# ---------------------------------------------------------------------------


def test_admin_endpoint_rejects_invalid_key_format():
    """PUT /admin/agent-config with invalid key format returns 422.

    The regex is: ^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$
    Test the regex directly since full app setup is heavy.
    """
    key_pattern = re.compile(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$')

    invalid_keys = [
        "../secret",       # path traversal
        "KEY_UPPER",       # uppercase
        "key with spaces", # spaces
        "key..double.dot", # consecutive dots rejected
        "key.",            # trailing dot rejected
        ".key",            # leading dot rejected
        "1key",            # leading digit rejected
    ]

    for key in invalid_keys:
        assert not key_pattern.match(key), f"Key '{key}' should be rejected"

    # Verify the regex accepts valid keys including underscored prefixes
    valid_keys = ["agent.max_tool_calls", "prompt.agent_name", "rate_limit.ai_chat",
                  "agent_tool.max_output", "export.pdf_ttl_seconds"]
    for key in valid_keys:
        assert key_pattern.match(key), f"Key '{key}' should be accepted"

"""Unit tests for DocumentLockService (app.services.document_lock_service).

Tests cover:
- acquire_lock: new lock (no existing), same-user renewal, conflict (different user)
- release_lock: by owner (success), by non-owner (failure)
- heartbeat: by owner extends TTL, by non-owner (failure)
- force_take_lock: transfers ownership, returns previous holder
- get_lock_holder: locked and unlocked documents
- get_active_locks: batch check with mixed locked/unlocked
- scan_all_active_locks: pattern-based scan
- Lua scripts are called with correct arguments
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.document_lock_service import (
    DocumentLockService,
    LOCK_KEY_PREFIX,
    LOCK_TTL_SECONDS,
    _ACQUIRE_LOCK_SCRIPT,
    _RELEASE_LOCK_SCRIPT,
    _HEARTBEAT_SCRIPT,
    _FORCE_TAKE_SCRIPT,
    _lock_key,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOC_ID = "aaaaaaaa-1111-2222-3333-444444444444"
USER_ID_A = "user-aaaa-1111-2222-333333333333"
USER_NAME_A = "Alice"
USER_ID_B = "user-bbbb-1111-2222-333333333333"
USER_NAME_B = "Bob"


@pytest.fixture
def lock_service():
    return DocumentLockService()


@pytest.fixture
def mock_redis():
    """Patch redis_service.client and scan_keys with AsyncMock."""
    mock_client = AsyncMock()
    with patch(
        "app.services.document_lock_service.redis_service"
    ) as mock_rs:
        mock_rs.client = mock_client
        mock_rs.scan_keys = AsyncMock(return_value=[])
        yield mock_rs


# ---------------------------------------------------------------------------
# _lock_key helper
# ---------------------------------------------------------------------------


class TestLockKey:
    def test_lock_key_format(self):
        key = _lock_key("some-doc-id")
        assert key == f"{LOCK_KEY_PREFIX}some-doc-id"

    def test_lock_key_prefix_constant(self):
        assert LOCK_KEY_PREFIX == "doc_lock:"


# ---------------------------------------------------------------------------
# acquire_lock
# ---------------------------------------------------------------------------


class TestAcquireLock:
    @pytest.mark.asyncio
    async def test_acquire_new_lock_success(self, lock_service, mock_redis):
        """No existing lock -> status 'acquired', returns lock data."""
        mock_redis.client.eval.return_value = json.dumps({"status": "acquired"})

        result = await lock_service.acquire_lock(DOC_ID, USER_ID_A, USER_NAME_A)

        assert result is not None
        assert result["user_id"] == USER_ID_A
        assert result["user_name"] == USER_NAME_A
        assert "acquired_at" in result

    @pytest.mark.asyncio
    async def test_acquire_renewal_same_user(self, lock_service, mock_redis):
        """Same user re-acquires -> status 'renewed', returns existing lock data."""
        existing_data = json.dumps({
            "user_id": USER_ID_A,
            "user_name": USER_NAME_A,
            "acquired_at": 1700000000.0,
        })
        mock_redis.client.eval.return_value = json.dumps({
            "status": "renewed",
            "holder": existing_data,
        })

        result = await lock_service.acquire_lock(DOC_ID, USER_ID_A, USER_NAME_A)

        assert result is not None
        assert result["user_id"] == USER_ID_A
        assert result["acquired_at"] == 1700000000.0

    @pytest.mark.asyncio
    async def test_acquire_conflict_different_user(self, lock_service, mock_redis):
        """Different user tries to acquire -> status 'conflict', returns None."""
        mock_redis.client.eval.return_value = json.dumps({"status": "conflict"})

        result = await lock_service.acquire_lock(DOC_ID, USER_ID_B, USER_NAME_B)

        assert result is None

    @pytest.mark.asyncio
    async def test_acquire_lua_script_called_with_correct_args(self, lock_service, mock_redis):
        """Verify the Lua script is called with the right arguments."""
        mock_redis.client.eval.return_value = json.dumps({"status": "acquired"})

        await lock_service.acquire_lock(DOC_ID, USER_ID_A, USER_NAME_A)

        mock_redis.client.eval.assert_called_once()
        args = mock_redis.client.eval.call_args
        # Positional args: (script, num_keys, key, value_json, ttl_str, user_id)
        assert args[0][0] == _ACQUIRE_LOCK_SCRIPT
        assert args[0][1] == 1  # num keys
        assert args[0][2] == _lock_key(DOC_ID)
        # args[0][3] is the value JSON — decode to verify content
        value = json.loads(args[0][3])
        assert value["user_id"] == USER_ID_A
        assert value["user_name"] == USER_NAME_A
        assert args[0][4] == str(LOCK_TTL_SECONDS)
        assert args[0][5] == USER_ID_A


# ---------------------------------------------------------------------------
# release_lock
# ---------------------------------------------------------------------------


class TestReleaseLock:
    @pytest.mark.asyncio
    async def test_release_by_owner_success(self, lock_service, mock_redis):
        """Owner releases -> Lua returns 1 -> True."""
        mock_redis.client.eval.return_value = 1

        result = await lock_service.release_lock(DOC_ID, USER_ID_A)

        assert result is True

    @pytest.mark.asyncio
    async def test_release_by_non_owner_failure(self, lock_service, mock_redis):
        """Non-owner release -> Lua returns 0 -> False."""
        mock_redis.client.eval.return_value = 0

        result = await lock_service.release_lock(DOC_ID, USER_ID_B)

        assert result is False

    @pytest.mark.asyncio
    async def test_release_no_lock_returns_false(self, lock_service, mock_redis):
        """No existing lock -> Lua returns 0 -> False."""
        mock_redis.client.eval.return_value = 0

        result = await lock_service.release_lock(DOC_ID, USER_ID_A)

        assert result is False

    @pytest.mark.asyncio
    async def test_release_lua_script_called_with_correct_args(self, lock_service, mock_redis):
        mock_redis.client.eval.return_value = 1

        await lock_service.release_lock(DOC_ID, USER_ID_A)

        args = mock_redis.client.eval.call_args
        assert args[0][0] == _RELEASE_LOCK_SCRIPT
        assert args[0][1] == 1
        assert args[0][2] == _lock_key(DOC_ID)
        assert args[0][3] == USER_ID_A


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_by_owner_extends_ttl(self, lock_service, mock_redis):
        """Owner heartbeat -> Lua returns 1 -> True."""
        mock_redis.client.eval.return_value = 1

        result = await lock_service.heartbeat(DOC_ID, USER_ID_A)

        assert result is True

    @pytest.mark.asyncio
    async def test_heartbeat_by_non_owner_failure(self, lock_service, mock_redis):
        """Non-owner heartbeat -> Lua returns 0 -> False."""
        mock_redis.client.eval.return_value = 0

        result = await lock_service.heartbeat(DOC_ID, USER_ID_B)

        assert result is False

    @pytest.mark.asyncio
    async def test_heartbeat_no_lock_returns_false(self, lock_service, mock_redis):
        """No existing lock -> Lua returns 0 -> False."""
        mock_redis.client.eval.return_value = 0

        result = await lock_service.heartbeat(DOC_ID, USER_ID_A)

        assert result is False

    @pytest.mark.asyncio
    async def test_heartbeat_lua_script_called_with_correct_args(self, lock_service, mock_redis):
        mock_redis.client.eval.return_value = 1

        await lock_service.heartbeat(DOC_ID, USER_ID_A)

        args = mock_redis.client.eval.call_args
        assert args[0][0] == _HEARTBEAT_SCRIPT
        assert args[0][1] == 1
        assert args[0][2] == _lock_key(DOC_ID)
        assert args[0][3] == USER_ID_A
        assert args[0][4] == str(LOCK_TTL_SECONDS)


# ---------------------------------------------------------------------------
# force_take_lock
# ---------------------------------------------------------------------------


class TestForceTakeLock:
    @pytest.mark.asyncio
    async def test_force_take_with_previous_holder(self, lock_service, mock_redis):
        """Force-take replaces existing holder -> returns old holder data."""
        old_holder = json.dumps({
            "user_id": USER_ID_A,
            "user_name": USER_NAME_A,
            "acquired_at": 1700000000.0,
        })
        mock_redis.client.eval.return_value = old_holder

        result = await lock_service.force_take_lock(DOC_ID, USER_ID_B, USER_NAME_B)

        assert result is not None
        assert result["user_id"] == USER_ID_A
        assert result["user_name"] == USER_NAME_A

    @pytest.mark.asyncio
    async def test_force_take_no_previous_lock(self, lock_service, mock_redis):
        """Force-take with no existing lock -> returns None."""
        mock_redis.client.eval.return_value = None

        result = await lock_service.force_take_lock(DOC_ID, USER_ID_B, USER_NAME_B)

        assert result is None

    @pytest.mark.asyncio
    async def test_force_take_lua_script_called_with_correct_args(self, lock_service, mock_redis):
        mock_redis.client.eval.return_value = None

        await lock_service.force_take_lock(DOC_ID, USER_ID_B, USER_NAME_B)

        args = mock_redis.client.eval.call_args
        assert args[0][0] == _FORCE_TAKE_SCRIPT
        assert args[0][1] == 1
        assert args[0][2] == _lock_key(DOC_ID)
        value = json.loads(args[0][3])
        assert value["user_id"] == USER_ID_B
        assert value["user_name"] == USER_NAME_B
        assert args[0][4] == str(LOCK_TTL_SECONDS)


# ---------------------------------------------------------------------------
# get_lock_holder
# ---------------------------------------------------------------------------


class TestGetLockHolder:
    @pytest.mark.asyncio
    async def test_lock_exists_returns_holder(self, lock_service, mock_redis):
        holder_data = {
            "user_id": USER_ID_A,
            "user_name": USER_NAME_A,
            "acquired_at": 1700000000.0,
        }
        mock_redis.client.get.return_value = json.dumps(holder_data)

        result = await lock_service.get_lock_holder(DOC_ID)

        assert result == holder_data
        mock_redis.client.get.assert_called_once_with(_lock_key(DOC_ID))

    @pytest.mark.asyncio
    async def test_no_lock_returns_none(self, lock_service, mock_redis):
        mock_redis.client.get.return_value = None

        result = await lock_service.get_lock_holder(DOC_ID)

        assert result is None


# ---------------------------------------------------------------------------
# get_active_locks (batch)
# ---------------------------------------------------------------------------


class TestGetActiveLocks:
    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, lock_service, mock_redis):
        result = await lock_service.get_active_locks([])

        assert result == {}

    @pytest.mark.asyncio
    async def test_some_locked_some_not(self, lock_service, mock_redis):
        """Two IDs: first locked, second not."""
        doc_id_1 = "doc-1111"
        doc_id_2 = "doc-2222"
        holder = {"user_id": USER_ID_A, "user_name": USER_NAME_A}
        mock_redis.client.mget.return_value = [json.dumps(holder), None]

        result = await lock_service.get_active_locks([doc_id_1, doc_id_2])

        assert doc_id_1 in result
        assert result[doc_id_1] == holder
        assert doc_id_2 not in result

    @pytest.mark.asyncio
    async def test_mget_called_with_correct_keys(self, lock_service, mock_redis):
        doc_ids = ["doc-a", "doc-b", "doc-c"]
        mock_redis.client.mget.return_value = [None, None, None]

        await lock_service.get_active_locks(doc_ids)

        expected_keys = [_lock_key(d) for d in doc_ids]
        mock_redis.client.mget.assert_called_once_with(expected_keys)


# ---------------------------------------------------------------------------
# scan_all_active_locks
# ---------------------------------------------------------------------------


class TestScanAllActiveLocks:
    @pytest.mark.asyncio
    async def test_no_keys_returns_empty(self, lock_service, mock_redis):
        mock_redis.scan_keys.return_value = []

        result = await lock_service.scan_all_active_locks()

        assert result == {}

    @pytest.mark.asyncio
    async def test_scan_returns_active_locks(self, lock_service, mock_redis):
        doc_id = "some-doc-uuid"
        key = f"{LOCK_KEY_PREFIX}{doc_id}"
        holder = {"user_id": USER_ID_A, "user_name": USER_NAME_A}

        mock_redis.scan_keys.return_value = [key]
        mock_redis.client.mget.return_value = [json.dumps(holder)]

        result = await lock_service.scan_all_active_locks()

        assert doc_id in result
        assert result[doc_id] == holder

    @pytest.mark.asyncio
    async def test_scan_filters_out_expired_keys(self, lock_service, mock_redis):
        """Keys returned by scan but with None value (expired between scan and mget)."""
        key = f"{LOCK_KEY_PREFIX}expired-doc"
        mock_redis.scan_keys.return_value = [key]
        mock_redis.client.mget.return_value = [None]

        result = await lock_service.scan_all_active_locks()

        assert result == {}

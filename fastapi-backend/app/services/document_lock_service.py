"""Document lock service using Redis for atomic lock operations.

Provides distributed document locking with:
- Atomic acquire/release using Redis SET NX and Lua scripts
- Heartbeat-based TTL extension for lock keepalive
- Force-take for application owners to reclaim locks
- Lock holder info retrieval

Designed for 5000+ concurrent users across multiple Uvicorn workers.
All ownership-checked operations use Lua scripts for atomicity.
"""

import json
import logging
import time
from typing import Optional

from .redis_service import redis_service

logger = logging.getLogger(__name__)

# Lock configuration
LOCK_KEY_PREFIX = "doc_lock:"
LOCK_TTL_SECONDS = 300  # 5 minutes


def _lock_key(document_id: str) -> str:
    """Build Redis key for a document lock."""
    return f"{LOCK_KEY_PREFIX}{document_id}"


# Lua script: Acquire lock with same-user re-acquisition support
# KEYS[1] = lock key, ARGV[1] = new value JSON, ARGV[2] = ttl, ARGV[3] = user_id
# Returns JSON: {status: "acquired"} | {status: "renewed", holder: <data>} | {status: "conflict"}
_ACQUIRE_LOCK_SCRIPT = """
local data = redis.call('GET', KEYS[1])
if data == false then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
    return cjson.encode({status = "acquired"})
end
local holder = cjson.decode(data)
if holder.user_id == ARGV[3] then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
    return cjson.encode({status = "renewed", holder = data})
end
return cjson.encode({status = "conflict"})
"""

# Lua script: Release lock only if caller owns it
# KEYS[1] = lock key, ARGV[1] = user_id
# Returns 1 if released, 0 if not owner or not found
_RELEASE_LOCK_SCRIPT = """
local data = redis.call('GET', KEYS[1])
if data == false then
    return 0
end
local holder = cjson.decode(data)
if holder.user_id == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""

# Lua script: Heartbeat - extend TTL only if caller owns it
# KEYS[1] = lock key, ARGV[1] = user_id, ARGV[2] = ttl seconds
# Returns 1 if extended, 0 if not owner or not found
_HEARTBEAT_SCRIPT = """
local data = redis.call('GET', KEYS[1])
if data == false then
    return 0
end
local holder = cjson.decode(data)
if holder.user_id == ARGV[1] then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
    return 1
end
return 0
"""

# Lua script: Force-take lock regardless of current owner
# KEYS[1] = lock key, ARGV[1] = new value JSON, ARGV[2] = ttl seconds
# Returns old holder JSON string or nil if no previous lock
_FORCE_TAKE_SCRIPT = """
local old_data = redis.call('GET', KEYS[1])
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
if old_data == false then
    return nil
end
return old_data
"""


class DocumentLockService:
    """
    Service for managing document locks via Redis.

    All ownership-checked operations (release, heartbeat, force-take) use
    Lua scripts to ensure atomicity. Redis is configured with
    decode_responses=True, so all returns are strings (not bytes).
    """

    async def acquire_lock(
        self,
        document_id: str,
        user_id: str,
        user_name: str,
    ) -> Optional[dict]:
        """
        Acquire a lock on a document atomically.

        Uses a Lua script for atomic acquisition with same-user re-acquisition:
        - If no lock exists → SET with TTL → return new lock data
        - If locked by same user → EXPIRE (extend TTL) → return existing lock data
        - If locked by different user → return None (caller should 409)

        Args:
            document_id: The document's UUID string
            user_id: The requesting user's UUID string
            user_name: The requesting user's display name

        Returns:
            Lock holder dict on success, None if already locked by another user.
        """
        key = _lock_key(document_id)
        lock_data = {
            "user_id": user_id,
            "user_name": user_name,
            "acquired_at": time.time(),
        }
        value = json.dumps(lock_data)

        result_str = await redis_service.client.eval(
            _ACQUIRE_LOCK_SCRIPT, 1, key, value, str(LOCK_TTL_SECONDS), user_id
        )

        result = json.loads(result_str)

        if result["status"] == "acquired":
            logger.info(
                f"Lock acquired: document={document_id}, user={user_id}"
            )
            return lock_data

        if result["status"] == "renewed":
            logger.info(
                f"Lock renewed (same user): document={document_id}, user={user_id}"
            )
            # Return the existing lock data from Redis
            return json.loads(result["holder"])

        logger.debug(
            f"Lock acquisition failed (already locked): document={document_id}, user={user_id}"
        )
        return None

    async def release_lock(
        self,
        document_id: str,
        user_id: str,
    ) -> bool:
        """
        Release a lock only if the caller owns it (atomic via Lua script).

        Args:
            document_id: The document's UUID string
            user_id: The requesting user's UUID string

        Returns:
            True if lock was released, False if not owner or no lock exists.
        """
        key = _lock_key(document_id)
        result = await redis_service.client.eval(
            _RELEASE_LOCK_SCRIPT, 1, key, user_id
        )

        released = result == 1
        if released:
            logger.info(
                f"Lock released: document={document_id}, user={user_id}"
            )
        else:
            logger.debug(
                f"Lock release failed (not owner or not found): "
                f"document={document_id}, user={user_id}"
            )
        return released

    async def heartbeat(
        self,
        document_id: str,
        user_id: str,
    ) -> bool:
        """
        Extend lock TTL only if the caller owns it (atomic via Lua script).

        Args:
            document_id: The document's UUID string
            user_id: The requesting user's UUID string

        Returns:
            True if TTL was extended, False if not owner or no lock exists.
        """
        key = _lock_key(document_id)
        result = await redis_service.client.eval(
            _HEARTBEAT_SCRIPT, 1, key, user_id, str(LOCK_TTL_SECONDS)
        )

        extended = result == 1
        if extended:
            logger.debug(
                f"Lock heartbeat: document={document_id}, user={user_id}"
            )
        else:
            logger.debug(
                f"Lock heartbeat failed (not owner or not found): "
                f"document={document_id}, user={user_id}"
            )
        return extended

    async def force_take_lock(
        self,
        document_id: str,
        new_user_id: str,
        new_user_name: str,
    ) -> Optional[dict]:
        """
        Force-take a lock regardless of current owner (atomic via Lua script).

        Used by application owners to reclaim locks from unresponsive users.

        Args:
            document_id: The document's UUID string
            new_user_id: The new lock holder's UUID string
            new_user_name: The new lock holder's display name

        Returns:
            Previous lock holder dict if there was one, None if no previous lock.
        """
        key = _lock_key(document_id)
        new_lock_data = {
            "user_id": new_user_id,
            "user_name": new_user_name,
            "acquired_at": time.time(),
        }
        new_value = json.dumps(new_lock_data)

        old_holder_str = await redis_service.client.eval(
            _FORCE_TAKE_SCRIPT, 1, key, new_value, str(LOCK_TTL_SECONDS)
        )

        logger.info(
            f"Lock force-taken: document={document_id}, new_user={new_user_id}, "
            f"had_previous={'yes' if old_holder_str else 'no'}"
        )

        if old_holder_str:
            return json.loads(old_holder_str)
        return None

    async def get_lock_holder(
        self,
        document_id: str,
    ) -> Optional[dict]:
        """
        Get the current lock holder for a document.

        Args:
            document_id: The document's UUID string

        Returns:
            Lock holder dict if locked, None if no lock exists.
        """
        key = _lock_key(document_id)
        value = await redis_service.client.get(key)

        if value:
            return json.loads(value)
        return None


def get_lock_service() -> DocumentLockService:
    """
    Factory function for FastAPI Depends().

    Returns:
        DocumentLockService instance.
    """
    return DocumentLockService()

"""
Redis Integration Test Script

Tests all Redis functionality:
1. Connection
2. Caching (set/get/delete/TTL)
3. Pub/Sub messaging
4. Presence (sorted sets)
5. Rate limiting
6. WebSocket manager integration

Run with: python -m scripts.test_redis_integration
"""

import asyncio
import sys
import time
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, ".")

from app.services.redis_service import RedisService, redis_service
from app.config import settings


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(title: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_test(name: str, passed: bool, details: str = "") -> None:
    status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
    print(f"  [{status}] {name}")
    if details:
        print(f"         {Colors.YELLOW}{details}{Colors.RESET}")


def print_section(name: str) -> None:
    print(f"\n{Colors.BOLD}>> {name}{Colors.RESET}")


async def test_connection(redis: RedisService) -> bool:
    """Test Redis connection."""
    print_section("Connection Test")

    try:
        await redis.connect()
        print_test("Connect to Redis", True, f"URL: {settings.redis_url[:30]}...")

        # Test ping
        pong = await redis.client.ping()
        print_test("Ping/Pong", pong == True)

        # Test health check
        health = await redis.health_check()
        print_test("Health check", health["status"] == "healthy",
                   f"Memory: {health.get('used_memory_human', 'N/A')}")

        return True
    except Exception as e:
        print_test("Connect to Redis", False, str(e))
        return False


async def test_caching(redis: RedisService) -> bool:
    """Test caching operations."""
    print_section("Caching Tests")

    all_passed = True
    test_key = f"test:cache:{uuid4()}"

    try:
        # Test string set/get
        await redis.set(test_key, "hello")
        value = await redis.get(test_key)
        passed = value == "hello"
        print_test("Set/Get string", passed, f"Got: {value}")
        all_passed &= passed

        # Test JSON set/get
        json_key = f"test:json:{uuid4()}"
        test_data = {"name": "Test User", "count": 42, "active": True}
        await redis.set(json_key, test_data)
        retrieved = await redis.get_json(json_key)
        passed = retrieved == test_data
        print_test("Set/Get JSON", passed, f"Got: {retrieved}")
        all_passed &= passed

        # Test TTL
        ttl_key = f"test:ttl:{uuid4()}"
        await redis.set(ttl_key, "expires", ttl=2)
        value1 = await redis.get(ttl_key)
        passed1 = value1 == "expires"
        print_test("Set with TTL", passed1)
        all_passed &= passed1

        # Wait for expiration
        await asyncio.sleep(2.5)
        value2 = await redis.get(ttl_key)
        passed2 = value2 is None
        print_test("TTL expiration", passed2, f"Value after TTL: {value2}")
        all_passed &= passed2

        # Test delete
        await redis.delete(test_key)
        value3 = await redis.get(test_key)
        passed = value3 is None
        print_test("Delete key", passed)
        all_passed &= passed

        # Test delete pattern
        pattern_prefix = f"test:pattern:{uuid4()}"
        for i in range(3):
            await redis.set(f"{pattern_prefix}:{i}", f"value{i}")
        deleted = await redis.delete_pattern(f"{pattern_prefix}:*")
        passed = deleted == 3
        print_test("Delete pattern", passed, f"Deleted {deleted} keys")
        all_passed &= passed

        # Test exists
        exists_key = f"test:exists:{uuid4()}"
        await redis.set(exists_key, "here")
        exists = await redis.exists(exists_key)
        print_test("Key exists", exists)
        all_passed &= exists

        not_exists = await redis.exists(f"test:nonexistent:{uuid4()}")
        print_test("Key not exists", not not_exists)
        all_passed &= not not_exists

        # Cleanup
        await redis.delete(json_key)
        await redis.delete(exists_key)

        return all_passed
    except Exception as e:
        print_test("Caching operations", False, str(e))
        return False


async def test_pubsub(redis: RedisService) -> bool:
    """Test pub/sub messaging."""
    print_section("Pub/Sub Tests")

    all_passed = True
    received_messages = []
    channel = f"test:pubsub:{uuid4()}"

    async def message_handler(data: dict) -> None:
        received_messages.append(data)

    try:
        # Subscribe
        await redis.subscribe(channel, message_handler)
        print_test("Subscribe to channel", True, f"Channel: {channel[:30]}...")

        # Start listener
        await redis.start_listening()
        print_test("Start pub/sub listener", True)

        # Give listener time to start
        await asyncio.sleep(0.5)

        # Publish messages
        test_messages = [
            {"type": "test", "id": 1, "content": "Hello"},
            {"type": "test", "id": 2, "content": "World"},
        ]

        for msg in test_messages:
            subscribers = await redis.publish(channel, msg)
            print_test(f"Publish message {msg['id']}", subscribers >= 1,
                       f"Subscribers: {subscribers}")
            all_passed &= subscribers >= 1

        # Wait for messages to be received
        await asyncio.sleep(1.5)

        # Verify received
        passed = len(received_messages) == len(test_messages)
        print_test("Receive messages", passed,
                   f"Received: {len(received_messages)}/{len(test_messages)}")
        all_passed &= passed

        # Verify content
        if received_messages:
            content_match = received_messages[0].get("content") == "Hello"
            print_test("Message content integrity", content_match)
            all_passed &= content_match

        # Unsubscribe
        await redis.unsubscribe(channel)
        print_test("Unsubscribe", True)

        return all_passed
    except Exception as e:
        print_test("Pub/Sub operations", False, str(e))
        return False


async def test_presence(redis: RedisService) -> bool:
    """Test presence operations using sorted sets."""
    print_section("Presence Tests (Sorted Sets)")

    all_passed = True
    room_id = f"test:room:{uuid4()}"
    user1 = str(uuid4())
    user2 = str(uuid4())
    user3 = str(uuid4())

    try:
        now = time.time()

        # Set presence for multiple users
        await redis.presence_set(room_id, user1, now)
        await redis.presence_set(room_id, user2, now - 10)
        await redis.presence_set(room_id, user3, now - 100)  # Old presence
        print_test("Set user presence", True, "Added 3 users to room")

        # Get all users
        users = await redis.presence_get_room(room_id, since=0)
        passed = len(users) == 3
        print_test("Get all room users", passed, f"Users in room: {len(users)}")
        all_passed &= passed

        # Get recent users only (last 50 seconds)
        recent = await redis.presence_get_room(room_id, since=now - 50)
        passed = len(recent) == 2  # user1 and user2
        print_test("Get recent users (TTL filter)", passed,
                   f"Recent users: {len(recent)}")
        all_passed &= passed

        # Get score (timestamp)
        score = await redis.presence_get_score(room_id, user1)
        passed = score is not None and abs(score - now) < 1
        print_test("Get user timestamp", passed, f"Score: {score}")
        all_passed &= passed

        # Remove user
        await redis.presence_remove(room_id, user2)
        users_after = await redis.presence_get_room(room_id, since=0)
        passed = len(users_after) == 2
        print_test("Remove user presence", passed, f"Users after remove: {len(users_after)}")
        all_passed &= passed

        # Cleanup old entries
        removed = await redis.presence_cleanup(room_id, now - 50)
        passed = removed == 1  # user3 was old
        print_test("Cleanup stale presence", passed, f"Removed {removed} stale entries")
        all_passed &= passed

        # Final count
        final_users = await redis.presence_get_room(room_id, since=0)
        passed = len(final_users) == 1 and user1 in final_users
        print_test("Final room state", passed, f"Remaining: {final_users}")
        all_passed &= passed

        # Cleanup
        await redis.client.delete(f"presence:{room_id}")

        return all_passed
    except Exception as e:
        print_test("Presence operations", False, str(e))
        return False


async def test_rate_limiting(redis: RedisService) -> bool:
    """Test rate limiting."""
    print_section("Rate Limiting Tests")

    all_passed = True
    key = f"test:ratelimit:{uuid4()}"

    try:
        # Test under limit
        for i in range(5):
            allowed, count = await redis.rate_limit_check(key, limit=10, window=60)
            if i == 0:
                print_test("First request allowed", allowed, f"Count: {count}")
                all_passed &= allowed

        # Should still be under limit
        allowed, count = await redis.rate_limit_check(key, limit=10, window=60)
        passed = allowed and count == 6
        print_test("Under limit (6/10)", passed, f"Count: {count}")
        all_passed &= passed

        # Push to limit
        for i in range(4):
            await redis.rate_limit_check(key, limit=10, window=60)

        # Now at limit
        allowed, count = await redis.rate_limit_check(key, limit=10, window=60)
        passed = not allowed and count == 11
        print_test("Over limit (11/10)", passed, f"Allowed: {allowed}, Count: {count}")
        all_passed &= passed

        # Test window expiration
        short_key = f"test:ratelimit:short:{uuid4()}"
        await redis.rate_limit_check(short_key, limit=1, window=2)
        allowed1, _ = await redis.rate_limit_check(short_key, limit=1, window=2)
        print_test("Blocked at limit", not allowed1)
        all_passed &= not allowed1

        await asyncio.sleep(2.5)
        allowed2, count2 = await redis.rate_limit_check(short_key, limit=1, window=2)
        passed = allowed2 and count2 == 1
        print_test("Allowed after window reset", passed, f"Count reset to: {count2}")
        all_passed &= passed

        # Cleanup
        await redis.delete(key)
        await redis.delete(short_key)

        return all_passed
    except Exception as e:
        print_test("Rate limiting operations", False, str(e))
        return False


async def test_websocket_manager_integration() -> bool:
    """Test WebSocket manager Redis integration."""
    print_section("WebSocket Manager Integration")

    all_passed = True

    try:
        from app.websocket.manager import manager, ConnectionManager
        from app.services.redis_service import redis_service

        # Initialize Redis on the global manager
        await manager.initialize_redis()
        print_test("Initialize manager with Redis", manager._redis_initialized)
        all_passed &= manager._redis_initialized

        # Test that channels are subscribed on the global redis_service
        broadcast_subscribed = ConnectionManager._BROADCAST_CHANNEL in redis_service._handlers
        user_subscribed = ConnectionManager._USER_CHANNEL in redis_service._handlers

        print_test("Broadcast channel subscribed", broadcast_subscribed,
                   f"Channel: {ConnectionManager._BROADCAST_CHANNEL}")
        print_test("User channel subscribed", user_subscribed,
                   f"Channel: {ConnectionManager._USER_CHANNEL}")

        all_passed &= broadcast_subscribed and user_subscribed

        return all_passed
    except Exception as e:
        print_test("WebSocket manager integration", False, str(e))
        return False


async def test_presence_manager_integration() -> bool:
    """Test Presence manager Redis integration."""
    print_section("Presence Manager Integration")

    all_passed = True

    try:
        from app.websocket.presence import presence_manager
        from app.services.redis_service import redis_service

        room_id = f"test:pm:room:{uuid4()}"
        user_id = str(uuid4())

        # Test heartbeat
        await presence_manager.heartbeat(room_id, user_id, "Test User", avatar_url=None, idle=False)
        print_test("Heartbeat (set presence)", True)

        # Test get presence
        presence = await presence_manager.get_presence(room_id)
        passed = len(presence) == 1 and presence[0]["id"] == user_id
        print_test("Get presence", passed, f"Found: {presence}")
        all_passed &= passed

        # Test is_present
        is_present = await presence_manager.is_present(room_id, user_id)
        print_test("Is present check", is_present)
        all_passed &= is_present

        # Test leave
        await presence_manager.leave(room_id, user_id)
        presence_after = await presence_manager.get_presence(room_id)
        passed = len(presence_after) == 0
        print_test("Leave room", passed)
        all_passed &= passed

        # Test stats
        stats = await presence_manager.get_stats()
        passed = stats.get("backend") == "redis"
        print_test("Stats (Redis backend)", passed, f"Backend: {stats.get('backend')}")
        all_passed &= passed

        # Cleanup
        await redis_service.client.delete(f"presence:{room_id}")
        await redis_service.client.delete(f"presence_data:{room_id}")

        return all_passed
    except Exception as e:
        print_test("Presence manager integration", False, str(e))
        return False


async def main():
    """Run all Redis integration tests."""
    print_header("Redis Integration Test Suite")
    print(f"Redis URL: {settings.redis_url[:40]}...")
    print(f"Redis Required: {settings.redis_required}")

    # Use the global redis_service singleton
    from app.services.redis_service import redis_service

    results = {}

    # Test connection first
    if not await test_connection(redis_service):
        print(f"\n{Colors.RED}{Colors.BOLD}Connection failed - cannot continue tests{Colors.RESET}")
        return 1

    results["Connection"] = True

    # Start listening for pub/sub (needed for manager/presence tests)
    await redis_service.start_listening()

    # Run all tests
    results["Caching"] = await test_caching(redis_service)
    results["Pub/Sub"] = await test_pubsub(redis_service)
    results["Presence"] = await test_presence(redis_service)
    results["Rate Limiting"] = await test_rate_limiting(redis_service)
    results["WebSocket Manager"] = await test_websocket_manager_integration()
    results["Presence Manager"] = await test_presence_manager_integration()

    # Disconnect
    await redis_service.disconnect()

    # Summary
    print_header("Test Summary")

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for name, result in results.items():
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {name}: [{status}]")

    print(f"\n{Colors.BOLD}Total: {passed}/{total} test groups passed{Colors.RESET}")

    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}All tests passed! Redis integration is working correctly.{Colors.RESET}\n")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}Some tests failed. Please check the output above.{Colors.RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

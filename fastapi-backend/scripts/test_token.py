"""Quick test: verify an Anthropic token works.

Usage:
    python scripts/test_token.py <YOUR_TOKEN>
"""

import asyncio
import sys

from anthropic import AsyncAnthropic


async def test(token: str) -> None:
    # Test 1: auth_token (Bearer header — for OAuth tokens)
    print("\n--- Test 1: auth_token (Bearer) ---")
    try:
        client = AsyncAnthropic(auth_token=token)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        print(f"SUCCESS: {resp.content}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

    # Test 2: api_key (X-Api-Key header — for API keys)
    print("\n--- Test 2: api_key (X-Api-Key) ---")
    try:
        client = AsyncAnthropic(api_key=token)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        print(f"SUCCESS: {resp.content}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_token.py <YOUR_TOKEN>")
        sys.exit(1)
    asyncio.run(test(sys.argv[1].strip()))

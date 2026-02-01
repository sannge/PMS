# Phase 5: Document Locking - Research

**Researched:** 2026-01-31
**Domain:** Redis distributed locking, WebSocket real-time lock broadcasting, frontend lock UI
**Confidence:** HIGH

## Summary

Document locking for this project is a well-understood pattern: Redis `SET NX EX` for atomic lock acquisition with TTL-based auto-expiry, a heartbeat loop to keep locks alive during active editing, WebSocket broadcasts for real-time lock status propagation, and frontend UI to show lock state and provide manual release/override controls.

This is simpler than most distributed locking scenarios because: (1) we have a single Redis instance (not multi-master Redlock), (2) the lock holder is always a human editor with seconds-scale response times, not a sub-millisecond process, and (3) the project already has a mature Redis service, WebSocket infrastructure, and presence system that the lock service can follow as patterns.

**Primary recommendation:** Build a custom `DocumentLockService` class in `app/services/document_lock_service.py` using raw `redis.asyncio` `SET NX EX` calls (not a third-party lock library). This keeps full control over the lock key structure, heartbeat renewal, force-take logic, and save-before-release semantics that are specific to this feature. The existing `RedisService` singleton provides the connection; the lock service adds document-specific logic on top.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `redis.asyncio` (redis-py) | 5.x+ (already installed) | `SET NX EX`, `GET`, `DEL`, `PEXPIRE` for lock operations | Already in use via `RedisService`; native async; no new dependency |
| FastAPI WebSocket + `ConnectionManager` | existing | Broadcast lock status changes to document viewers | Established pattern in codebase for real-time events |
| React `useEffect` + `setInterval` | built-in | Client-side heartbeat loop | No library needed for a simple periodic timer |
| TanStack Query | existing | Lock status polling/caching on frontend | Already used for all data fetching; `useQuery` for lock status |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Lua scripting (Redis `EVAL`) | Redis 7+ | Atomic conditional release and force-take | Required for safe release (compare-and-delete) and atomic force-take (save signal + overwrite) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `SET NX EX` | `redis.asyncio.lock.Lock` | Built-in Lock class abstracts away key details; but we need custom key naming (`doc_lock:{doc_id}`), custom heartbeat interval (10s vs default), and force-take logic that the built-in class doesn't support. Raw is better here. |
| Raw `SET NX EX` | `python-redis-lock` or `aioredlock` | Third-party libraries add Redlock (multi-master) or BLPOP-based waiting. Overkill for single-instance document locking. Adds dependency for no benefit. |
| Redis lock | Database row lock (SELECT FOR UPDATE) | Database locks don't TTL-expire on client crash. Redis TTL is the key safety mechanism for LOCK-05. |

**Installation:**
```bash
# No new packages needed -- all dependencies already installed
```

## Architecture Patterns

### Recommended Project Structure

```
fastapi-backend/app/
├── services/
│   ├── redis_service.py          # Existing -- provides Redis client
│   └── document_lock_service.py  # NEW -- lock acquire/release/heartbeat/force-take
├── routers/
│   └── document_locks.py         # NEW -- REST endpoints for lock operations
├── schemas/
│   └── document_lock.py          # NEW -- Pydantic request/response models
└── websocket/
    ├── manager.py                # Existing -- add DOCUMENT_LOCKED/UNLOCKED message types
    └── handlers.py               # Existing -- add lock broadcast handler

electron-app/src/renderer/
├── hooks/
│   └── use-document-lock.ts      # NEW -- lock state, heartbeat, acquire/release
├── components/
│   └── editor/
│       └── LockBanner.tsx        # NEW -- "Being edited by [name]" banner + controls
```

### Pattern 1: Redis Lock Key Structure

**What:** Use a consistent key naming convention for document locks in Redis.
**When to use:** All lock operations.
**Key format:** `doc_lock:{document_id}`
**Value format:** JSON string `{"user_id": "uuid", "user_name": "Display Name", "acquired_at": 1706700000.0}`

```python
# Key structure
LOCK_KEY_PREFIX = "doc_lock:"
LOCK_TTL_SECONDS = 45  # Server-side TTL (30s inactivity + 15s buffer for heartbeat jitter)
HEARTBEAT_INTERVAL = 10  # Client sends heartbeat every 10 seconds

def _lock_key(document_id: str) -> str:
    return f"{LOCK_KEY_PREFIX}{document_id}"
```

**Why 45s TTL:** The requirement says auto-release after 30s of inactivity. The client heartbeat runs every 10s. If the client stops heartbeating (crash/disconnect), the TTL expires 45s after the last heartbeat. With heartbeats every 10s, the worst-case staleness is 45s (last heartbeat at T, TTL expires at T+45). This is close to 30s inactivity with margin for network jitter. The auto-release timer on the *client side* handles the "30s of inactivity" UX (LOCK-03), while the server TTL handles crash recovery (LOCK-05).

### Pattern 2: Atomic Lock Acquisition with SET NX EX

**What:** Acquire a lock atomically -- only succeeds if no lock exists.
**When to use:** When user clicks "Edit" or opens a document for editing.

```python
async def acquire_lock(
    self,
    document_id: str,
    user_id: str,
    user_name: str,
) -> dict | None:
    """
    Attempt to acquire the document lock.

    Returns lock info dict on success, None if already locked by another user.
    """
    key = self._lock_key(document_id)
    lock_value = json.dumps({
        "user_id": user_id,
        "user_name": user_name,
        "acquired_at": time.time(),
    })

    # SET NX EX: atomic acquire with TTL
    acquired = await self._redis.client.set(
        key, lock_value, nx=True, ex=LOCK_TTL_SECONDS
    )

    if acquired:
        return json.loads(lock_value)

    # Lock already held -- return current holder info
    return None
```

### Pattern 3: Safe Release with Lua Script

**What:** Release the lock only if the caller is the current holder.
**When to use:** Manual "stop editing" (LOCK-04) and auto-release after inactivity (LOCK-03).

```python
# Lua script: atomic compare-and-delete
RELEASE_SCRIPT = """
local current = redis.call("GET", KEYS[1])
if current == false then
    return 0
end
local data = cjson.decode(current)
if data.user_id == ARGV[1] then
    redis.call("DEL", KEYS[1])
    return 1
else
    return 0
end
"""

async def release_lock(self, document_id: str, user_id: str) -> bool:
    key = self._lock_key(document_id)
    result = await self._redis.client.eval(
        RELEASE_SCRIPT, 1, key, user_id
    )
    return result == 1
```

### Pattern 4: Heartbeat Renewal

**What:** Extend the lock TTL while the client is actively editing.
**When to use:** Client sends heartbeat every 10 seconds while editor is open and user is active.

```python
# Lua script: extend TTL only if caller owns the lock
HEARTBEAT_SCRIPT = """
local current = redis.call("GET", KEYS[1])
if current == false then
    return 0
end
local data = cjson.decode(current)
if data.user_id == ARGV[1] then
    redis.call("EXPIRE", KEYS[1], ARGV[2])
    return 1
else
    return 0
end
"""

async def heartbeat(self, document_id: str, user_id: str) -> bool:
    key = self._lock_key(document_id)
    result = await self._redis.client.eval(
        HEARTBEAT_SCRIPT, 1, key, user_id, str(LOCK_TTL_SECONDS)
    )
    return result == 1
```

### Pattern 5: Force-Take (Owner Override)

**What:** Application owner forcefully takes the lock from current holder.
**When to use:** LOCK-06 -- owners can override locks (previous editor's work saved first).

```python
# Lua script: overwrite lock regardless of current holder, return old holder info
FORCE_TAKE_SCRIPT = """
local current = redis.call("GET", KEYS[1])
local old_holder = nil
if current ~= false then
    old_holder = current
end
redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[2])
return old_holder
"""

async def force_take_lock(
    self,
    document_id: str,
    new_user_id: str,
    new_user_name: str,
) -> dict | None:
    """Force-take the lock. Returns the previous holder info (or None if unlocked)."""
    key = self._lock_key(document_id)
    new_value = json.dumps({
        "user_id": new_user_id,
        "user_name": new_user_name,
        "acquired_at": time.time(),
    })

    old_holder_json = await self._redis.client.eval(
        FORCE_TAKE_SCRIPT, 1, key, new_value, str(LOCK_TTL_SECONDS)
    )

    if old_holder_json:
        return json.loads(old_holder_json)
    return None
```

### Pattern 6: WebSocket Lock Status Broadcast

**What:** Broadcast lock acquire/release events to all users viewing the document.
**When to use:** Every lock state change.

```python
# Add to MessageType enum in manager.py:
DOCUMENT_LOCKED = "document_locked"
DOCUMENT_UNLOCKED = "document_unlocked"
DOCUMENT_LOCK_EXPIRED = "document_lock_expired"

# Broadcast pattern (follows existing handle_note_update pattern):
async def broadcast_lock_change(
    document_id: str,
    lock_type: str,  # "locked" | "unlocked" | "expired" | "force_taken"
    lock_holder: dict | None,
    triggered_by: str | None = None,
):
    room_id = f"note:{document_id}"  # Reuse existing note room
    message = {
        "type": f"document_{lock_type}",
        "data": {
            "document_id": document_id,
            "lock_holder": lock_holder,
            "triggered_by": triggered_by,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }
    await manager.broadcast_to_room(room_id, message)
```

### Pattern 7: Frontend Lock Hook

**What:** React hook encapsulating lock state, heartbeat, and acquire/release API calls.
**When to use:** In the document editor component.

```typescript
// use-document-lock.ts
interface UseDocumentLockReturn {
  lockHolder: LockHolder | null      // Current lock holder info
  isLockedByMe: boolean              // Am I the lock holder?
  isLockedByOther: boolean           // Is someone else holding the lock?
  acquireLock: () => Promise<boolean> // Try to acquire lock
  releaseLock: () => Promise<void>    // Release lock (manual stop editing)
  forceTakeLock: () => Promise<boolean> // Owner override
  canForceTake: boolean              // Does current user have owner permissions?
}

function useDocumentLock(documentId: string): UseDocumentLockReturn {
  // 1. useQuery to poll/cache lock status (GET /api/documents/{id}/lock)
  // 2. useMutation for acquire/release/force-take
  // 3. useEffect with setInterval for heartbeat (POST /api/documents/{id}/lock/heartbeat)
  // 4. Listen to WebSocket for real-time lock/unlock events
  // 5. useEffect cleanup: release lock on unmount (+ beforeunload handler)
}
```

### Pattern 8: Client-Side Inactivity Timer (LOCK-03)

**What:** Auto-release lock after 30 seconds of no user activity in the editor.
**When to use:** While user holds the lock.

```typescript
// Inside useDocumentLock or a separate useInactivityTimer hook:
// - Track last activity timestamp (keypress, mouse move in editor)
// - setInterval checks every 5s: if (now - lastActivity > 30000) { save(); releaseLock(); }
// - Reset timer on any editor activity
// - This is CLIENT-SIDE only -- server TTL (LOCK-05) is the crash safety net
```

### Anti-Patterns to Avoid

- **Polling for lock status instead of WebSocket:** Wastes bandwidth and adds latency. Use WebSocket broadcast for instant lock change notifications, with a single REST GET for initial page load.
- **Using `DEL` without ownership check:** Another user could steal your lock between GET and DEL. Always use the Lua compare-and-delete script.
- **TTL too short (< heartbeat interval):** If TTL < heartbeat interval, the lock expires between heartbeats. TTL must be > 2x heartbeat interval.
- **No save before release:** LOCK-03 and LOCK-06 both require saving the document before releasing the lock. The release flow must be: save content -> release lock -> broadcast unlock.
- **Blocking lock acquisition:** Users should never wait/retry for a lock. If it's locked, show "Being edited by [name]" immediately. No spin-lock.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic lock acquire | Custom check-then-set with race conditions | `SET key value NX EX ttl` (single Redis command) | Race conditions between GET and SET; the NX flag makes it atomic |
| Safe lock release | `GET` then `DEL` in two commands | Lua script with `EVAL` | Another process could acquire between GET and DEL |
| Lock TTL extension | Python timer + `EXPIRE` | Lua script comparing owner before `EXPIRE` | Another user could have taken the lock between check and extend |
| Cross-worker lock broadcasts | Custom pub/sub implementation | Existing `ConnectionManager.broadcast_to_room()` with Redis pub/sub | Already built, tested, and handles cross-worker delivery |
| Frontend heartbeat timing | Custom setTimeout chain | `setInterval` with cleanup | Simple, built-in, and sufficient for 10s intervals |

**Key insight:** Every lock operation that involves "check state then modify state" must be atomic. Redis Lua scripts provide this atomicity. Never split these into separate Redis commands.

## Common Pitfalls

### Pitfall 1: Lock Expires During Save

**What goes wrong:** User's inactivity timer fires, triggering save + release. But the save takes >15 seconds (large document, slow network). Meanwhile, the Redis TTL expires and another user acquires the lock. Now two users think they own the document.
**Why it happens:** The save operation is async and can take variable time.
**How to avoid:** On the server side, the save endpoint should check lock ownership before writing. If the lock expired during save, the save should still succeed (it's the user's work), but the lock is not re-acquired. The response tells the client the lock was lost.
**Warning signs:** Save latency exceeding 10 seconds in production monitoring.

### Pitfall 2: Stale Lock Banner After Redis TTL Expiry

**What goes wrong:** User A holds the lock. User A's client crashes. Redis TTL expires the lock after 45s. But User B's UI still shows "Being edited by User A" because no WebSocket event was sent for TTL expiry.
**Why it happens:** Redis TTL expiry is passive -- there's no built-in notification when a key expires.
**How to avoid:** Two complementary strategies:
1. Frontend `useQuery` polls lock status every 15-30 seconds as a fallback (stale-while-revalidate pattern).
2. Optionally, use Redis keyspace notifications (`notify-keyspace-events Ex`) to detect key expiry and broadcast an unlock event. However, this adds Redis configuration complexity.
The simpler approach (#1) is sufficient: the banner updates within 30 seconds of TTL expiry via polling.
**Warning signs:** Users reporting "stuck" lock banners that don't clear.

### Pitfall 3: Double-Release on Unmount

**What goes wrong:** React component unmounts, triggering both `useEffect` cleanup and `beforeunload` handler. Both call `releaseLock()`, but the second call fails because the lock was already released, potentially causing an error.
**Why it happens:** Multiple cleanup paths fire for the same event.
**How to avoid:** Use a ref (`lockReleasedRef`) to track whether release has already been called. Skip if already released. The Lua release script is also idempotent (returns 0 if lock doesn't exist), so server-side double-release is safe.
**Warning signs:** Console errors on page navigation away from editor.

### Pitfall 4: Heartbeat Stops But Tab Stays Open

**What goes wrong:** User switches to another browser tab. `setInterval` slows down (browser throttles background tabs). Heartbeat stops arriving at the expected 10s interval. Lock TTL expires even though the user intends to come back.
**Why it happens:** Browsers throttle timers in background tabs to save CPU/battery.
**How to avoid:**
1. Use `document.visibilitychange` event to detect tab becoming hidden/visible.
2. When tab becomes visible again, immediately send a heartbeat and re-check lock status.
3. The 45s TTL (vs 10s heartbeat) provides significant buffer -- browser throttling typically delays timers to 1s minimum, not 45s.
4. Electron desktop app may not throttle as aggressively as web browsers.
**Warning signs:** Lock unexpectedly lost when switching between documents in tabs.

### Pitfall 5: Force-Take Without Saving Previous Editor's Work

**What goes wrong:** Owner force-takes the lock. Previous editor's unsaved changes are lost.
**Why it happens:** Force-take only overwrites the Redis lock key; it doesn't trigger a save on the previous editor's client.
**How to avoid:** The force-take flow must:
1. Send a WebSocket event to the previous editor: `document_force_save_requested`
2. Previous editor's client receives this, triggers an immediate save
3. After a brief delay (2-3 seconds) or after receiving save confirmation, the force-take completes
4. If the previous editor's client is unreachable (crashed), the force-take proceeds anyway after the timeout
**Warning signs:** Users reporting lost work after owner override.

## Code Examples

### REST API Endpoints (FastAPI Router)

```python
# Source: follows existing router patterns in app/routers/

router = APIRouter(prefix="/api/documents", tags=["document-locks"])

@router.post("/{document_id}/lock")
async def acquire_lock(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Acquire edit lock on a document."""
    result = await lock_service.acquire_lock(
        str(document_id), str(current_user.id), current_user.display_name
    )
    if result is None:
        # Lock held by someone else
        holder = await lock_service.get_lock_holder(str(document_id))
        raise HTTPException(
            status_code=409,
            detail={"message": "Document is locked", "lock_holder": holder}
        )
    # Broadcast lock acquired
    await broadcast_lock_change(str(document_id), "locked", result)
    return DocumentLockResponse(locked=True, lock_holder=result)

@router.delete("/{document_id}/lock")
async def release_lock(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Release edit lock on a document."""
    released = await lock_service.release_lock(str(document_id), str(current_user.id))
    if released:
        await broadcast_lock_change(str(document_id), "unlocked", None)
    return DocumentLockResponse(locked=False, lock_holder=None)

@router.post("/{document_id}/lock/heartbeat")
async def lock_heartbeat(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> dict:
    """Extend lock TTL (client heartbeat)."""
    extended = await lock_service.heartbeat(str(document_id), str(current_user.id))
    if not extended:
        raise HTTPException(status_code=409, detail="Lock not held by you")
    return {"extended": True}

@router.get("/{document_id}/lock")
async def get_lock_status(
    document_id: UUID,
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Get current lock status for a document."""
    holder = await lock_service.get_lock_holder(str(document_id))
    return DocumentLockResponse(locked=holder is not None, lock_holder=holder)

@router.post("/{document_id}/lock/force-take")
async def force_take_lock(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
) -> DocumentLockResponse:
    """Force-take lock (application owner only). Saves previous editor's work first."""
    # Permission check: must be application owner
    # ... (check current_user is owner of document's application)

    old_holder = await lock_service.force_take_lock(
        str(document_id), str(current_user.id), current_user.display_name
    )

    # If someone was holding the lock, broadcast force-take event
    if old_holder:
        await broadcast_lock_change(
            str(document_id), "force_taken",
            {"user_id": str(current_user.id), "user_name": current_user.display_name},
            triggered_by=str(current_user.id),
        )

    return DocumentLockResponse(
        locked=True,
        lock_holder={
            "user_id": str(current_user.id),
            "user_name": current_user.display_name,
        }
    )
```

### Pydantic Schemas

```python
from pydantic import BaseModel
from typing import Optional

class LockHolder(BaseModel):
    user_id: str
    user_name: str
    acquired_at: Optional[float] = None

class DocumentLockResponse(BaseModel):
    locked: bool
    lock_holder: Optional[LockHolder] = None
```

### Frontend Lock Banner Component

```tsx
// LockBanner.tsx -- follows existing Radix UI + Tailwind patterns
function LockBanner({ lockHolder, canForceTake, onForceTake, onStopEditing, isLockedByMe }) {
  if (!lockHolder) return null

  if (isLockedByMe) {
    return (
      <div className="flex items-center justify-between px-4 py-2 bg-primary/10 border-b">
        <span className="text-sm">You are editing this document</span>
        <button onClick={onStopEditing} className="text-sm text-primary hover:underline">
          Stop editing
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-amber-500/10 border-b">
      <span className="text-sm text-amber-700">
        Being edited by {lockHolder.user_name}
      </span>
      {canForceTake && (
        <button onClick={onForceTake} className="text-sm text-amber-700 hover:underline">
          Take over editing
        </button>
      )}
    </div>
  )
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SETNX + separate EXPIRE | `SET key value NX EX ttl` (single atomic command) | Redis 2.6.12 (2013) | Eliminates race between set and expire |
| DEL for release | Lua script compare-and-delete | Redis 2.6+ (scripting) | Prevents releasing another user's lock |
| Redlock for all distributed locks | Single-instance for non-critical apps | Ongoing debate (Kleppmann vs antirez) | Single-instance is fine for document locking where the worst case is brief dual-editing, not data corruption |

**Deprecated/outdated:**
- `SETNX` command alone: Superseded by `SET ... NX EX` which combines set-if-not-exists and TTL atomically
- Redlock for document locking: Overkill; single-instance Redis is sufficient when the cost of a brief lock overlap is low (user sees stale banner for a few seconds)

## Open Questions

1. **Redis keyspace notifications for TTL expiry**
   - What we know: Redis can notify on key expiry via `notify-keyspace-events Ex`. This would allow the server to broadcast an "unlock" event when a lock TTL expires (crashed client scenario).
   - What's unclear: Whether the existing Redis deployment has keyspace notifications enabled, and whether the added complexity is worth it vs. simple frontend polling.
   - Recommendation: Start without keyspace notifications. Use frontend polling (every 15-30s) as the fallback for stale lock detection. Add keyspace notifications only if users report "stuck" lock banners as a real problem.

2. **Save-before-force-take timing**
   - What we know: LOCK-06 requires saving the previous editor's work before force-take. This needs a WebSocket event to the old editor's client to trigger a save.
   - What's unclear: How long to wait for the save to complete before proceeding with the force-take. What if the old client is unreachable?
   - Recommendation: Send a `force_save_requested` WebSocket event. Wait up to 3 seconds for a save confirmation. If no confirmation, proceed with force-take anyway (the document's last saved state is preserved; only unsaved delta is lost). The force-take UI should show a brief "Saving previous editor's work..." state.

3. **Document room naming for lock broadcasts**
   - What we know: The existing codebase uses `note:{note_id}` for note rooms in `handlers.py`. Phase 1 replaces notes with documents.
   - What's unclear: Whether the document model from Phase 1 will use the same room naming convention (likely `document:{document_id}` instead of `note:{note_id}`).
   - Recommendation: Use `document:{document_id}` as the room ID for lock broadcasts. This will be established in earlier phases. The lock service should accept the room ID as a parameter, not hard-code it.

## Sources

### Primary (HIGH confidence)
- [Redis SET command documentation](https://redis.io/docs/latest/commands/set/) - `NX` and `EX` flags for atomic lock acquisition
- [Redis Distributed Locks official pattern](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/) - Lua release script, TTL recommendations, safety guarantees
- Existing codebase: `app/services/redis_service.py` - Redis connection, pub/sub, caching patterns
- Existing codebase: `app/websocket/manager.py` - Room-based broadcast, `MessageType` enum
- Existing codebase: `app/websocket/presence.py` - Heartbeat pattern, TTL-based cleanup (direct analog for lock heartbeat)
- Existing codebase: `electron-app/src/renderer/hooks/use-presence.ts` - Frontend heartbeat hook pattern

### Secondary (MEDIUM confidence)
- [redis-py Lock API](https://redis.readthedocs.io/en/stable/lock.html) - Built-in async Lock class API (decided against using it, but verified its existence and limitations)
- [redis.asyncio examples](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html) - Async Redis usage patterns

### Tertiary (LOW confidence)
- [Twelve Redis Locking Patterns (Medium)](https://medium.com/@navidbarsalari/the-twelve-redis-locking-patterns-every-distributed-systems-engineer-should-know-06f16dfe7375) - Heartbeat/lease pattern descriptions (verified concepts against official Redis docs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using only existing dependencies (`redis.asyncio`, FastAPI, existing WebSocket infrastructure). No new libraries.
- Architecture: HIGH - Follows established patterns already in the codebase (presence manager, WebSocket handlers, room-based broadcasts). Redis `SET NX EX` is the official recommended lock pattern.
- Pitfalls: HIGH - Well-documented failure modes in Redis distributed locking literature. Mapped each pitfall to specific requirements (LOCK-03, LOCK-05, LOCK-06).

**Research date:** 2026-01-31
**Valid until:** 2026-03-31 (stable domain; Redis locking patterns haven't changed in years)

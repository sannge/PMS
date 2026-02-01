# Phase 5: Document Locking - Research

**Researched:** 2026-01-31 (forced re-research)
**Domain:** Redis distributed locking, WebSocket real-time lock broadcasting, frontend lock UI
**Confidence:** HIGH

## Summary

Document locking for this project is a well-understood pattern: Redis `SET NX EX` for atomic lock acquisition with TTL-based auto-expiry, a heartbeat loop to keep locks alive during active editing, WebSocket broadcasts for real-time lock status propagation, and frontend UI to show lock state and provide manual release/override controls.

This is simpler than most distributed locking scenarios because: (1) we have a single Redis instance (not multi-master Redlock), (2) the lock holder is always a human editor with seconds-scale response times, and (3) the project already has a mature Redis service, WebSocket infrastructure, and presence system that the lock service follows as patterns.

The codebase has been thoroughly explored. Key findings that differ from or improve upon the previous research:

- **Redis is configured with `decode_responses=True`** (line 52, `redis_service.py`). This means Lua script return values come back as Python strings, not bytes. All Lua scripts must account for this.
- **The `RedisService` exposes `.client` property** returning the raw `redis.asyncio.Redis` instance. The lock service should use `redis_service.client` for direct Redis operations (SET, EVAL), not the high-level methods.
- **WebSocket broadcasts go through Redis pub/sub** via `manager.broadcast_to_room()` which publishes to channel `ws:broadcast`. This is cross-worker safe. Lock broadcasts must use this pattern, not raw sends.
- **The frontend uses `window.electronAPI.get/post/put/delete`** for HTTP calls, not `fetch()` directly. The lock hook must use these Electron IPC bridge methods.
- **Auth pattern**: `get_current_user` dependency returns a `User` model with `.id` (UUID) and `.display_name`. This is the standard auth dependency for all routers.
- **Permission service**: `PermissionService.get_user_application_role()` returns `"owner"`, `"editor"`, `"viewer"`, or `None`. Force-take must check for `"owner"` role, which requires loading the document's application_id from the database.
- **Room naming convention**: Existing rooms use `{entity}:{uuid}` format (e.g., `project:{uuid}`, `task:{uuid}`). The document room should be `document:{document_id}`.
- **Room auth**: `room_auth.py` checks `check_room_access()` for rooms joined via WebSocket. A `document` room type must be added.
- **Roadmap confirms 2 plans** (not 3 as the phase description suggested): 05-01 (backend) and 05-02 (frontend).

**Primary recommendation:** Build a `DocumentLockService` class in `app/services/document_lock_service.py` using raw `redis.asyncio` `SET NX EX` calls via `redis_service.client`. Use Lua scripts for safe release, heartbeat, and force-take. Follow the existing `PresenceManager` pattern for the service structure and the existing handler patterns for WebSocket broadcasts.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `redis.asyncio` (redis-py) | 5.x+ (already installed) | `SET NX EX`, `GET`, `DEL`, `EVAL` for lock operations | Already in use via `RedisService`; native async; no new dependency |
| FastAPI WebSocket + `ConnectionManager` | existing | Broadcast lock status changes to document viewers | Established pattern in codebase (`manager.broadcast_to_room`) |
| React `useEffect` + `setInterval` | built-in | Client-side heartbeat loop and inactivity timer | No library needed; matches `use-presence.ts` pattern exactly |
| TanStack Query `useQuery` + `useMutation` | existing | Lock status fetching and mutation on frontend | Already used for all data fetching in `use-queries.ts` |
| `window.electronAPI` | existing Electron IPC bridge | HTTP calls from renderer to backend | All existing hooks use this pattern (not raw `fetch`) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Lua scripting (Redis `EVAL`) | Redis 7+ | Atomic conditional release, heartbeat extension, and force-take | Required for all multi-step Redis operations that check ownership before modifying |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `SET NX EX` | `redis.asyncio.lock.Lock` | Built-in Lock class abstracts key details; but we need custom key naming (`doc_lock:{doc_id}`), custom heartbeat interval (10s), and force-take logic that built-in class doesn't support. Raw is better. |
| Raw `SET NX EX` | `python-redis-lock` or `aioredlock` | Third-party libraries add Redlock (multi-master) or BLPOP-based waiting. Overkill for single-instance. Adds dependency for no benefit. |
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
│   ├── redis_service.py              # Existing -- provides Redis client via .client property
│   └── document_lock_service.py      # NEW -- lock acquire/release/heartbeat/force-take
├── routers/
│   └── document_locks.py             # NEW -- REST endpoints for lock operations
├── schemas/
│   ├── __init__.py                   # Existing -- add new schema imports
│   └── document_lock.py              # NEW -- Pydantic request/response models
├── websocket/
│   ├── manager.py                    # MODIFY -- add DOCUMENT_LOCKED/UNLOCKED message types
│   ├── handlers.py                   # MODIFY -- add lock broadcast handlers
│   └── room_auth.py                  # MODIFY -- add "document" room type support
└── main.py                           # MODIFY -- register document_locks router

electron-app/src/renderer/
├── hooks/
│   ├── use-document-lock.ts          # NEW -- lock state, heartbeat, acquire/release
│   └── index.ts                      # MODIFY -- export new hook
├── components/
│   └── editor/
│       └── LockBanner.tsx            # NEW -- "Being edited by [name]" banner + controls
└── lib/
    └── websocket.ts                  # MODIFY -- add document lock MessageType entries
```

### Pattern 1: Redis Lock Key Structure

**What:** Consistent key naming convention for document locks in Redis.
**When to use:** All lock operations.
**Key format:** `doc_lock:{document_id}`
**Value format:** JSON string `{"user_id": "uuid", "user_name": "Display Name", "acquired_at": 1706700000.0}`

```python
# Key structure
LOCK_KEY_PREFIX = "doc_lock:"
LOCK_TTL_SECONDS = 45  # Server-side TTL (see timing rationale below)
HEARTBEAT_INTERVAL_SECONDS = 10  # Client sends heartbeat every 10 seconds

def _lock_key(document_id: str) -> str:
    return f"{LOCK_KEY_PREFIX}{document_id}"
```

**Timing rationale:**
- Client heartbeat: every 10 seconds (LOCK-07)
- Server TTL: 45 seconds (allows 3 missed heartbeats + 15s jitter buffer)
- Client inactivity timer: 30 seconds (LOCK-03) -- client-side only, triggers save + release
- If client crashes, worst case: lock held for 45s after last heartbeat (LOCK-05)

### Pattern 2: Atomic Lock Acquisition with SET NX EX

**What:** Acquire a lock atomically -- only succeeds if no lock exists.
**When to use:** When user clicks "Edit" or opens a document for editing.

```python
import json
import time
from ..services.redis_service import redis_service

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
    # Note: redis_service is configured with decode_responses=True
    acquired = await redis_service.client.set(
        key, lock_value, nx=True, ex=LOCK_TTL_SECONDS
    )

    if acquired:
        return json.loads(lock_value)
    return None
```

**CRITICAL: `decode_responses=True` impact.** The Redis client in this project is initialized with `decode_responses=True` (line 52 of `redis_service.py`). This means:
- `GET` returns `str | None` (not `bytes | None`)
- Lua script `EVAL` return values are decoded as strings
- `SET ... NX` returns `True | None` (not `b"OK" | None`)
- All code must handle string returns, not bytes

### Pattern 3: Safe Release with Lua Script

**What:** Release the lock only if the caller is the current holder.
**When to use:** Manual "stop editing" (LOCK-04) and auto-release after inactivity (LOCK-03).

```python
# Lua script: atomic compare-and-delete
# With decode_responses=True, ARGV[1] arrives as a string
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
    result = await redis_service.client.eval(
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
    redis.call("EXPIRE", KEYS[1], tonumber(ARGV[2]))
    return 1
else
    return 0
end
"""

async def heartbeat(self, document_id: str, user_id: str) -> bool:
    key = self._lock_key(document_id)
    result = await redis_service.client.eval(
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
redis.call("SET", KEYS[1], ARGV[1], "EX", tonumber(ARGV[2]))
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

    old_holder_json = await redis_service.client.eval(
        FORCE_TAKE_SCRIPT, 1, key, new_value, str(LOCK_TTL_SECONDS)
    )

    if old_holder_json:
        return json.loads(old_holder_json)
    return None
```

### Pattern 6: WebSocket Lock Status Broadcast

**What:** Broadcast lock acquire/release events to all users viewing the document.
**When to use:** Every lock state change.

**Backend -- Add to MessageType enum in manager.py:**
```python
# Add to MessageType(str, Enum):
DOCUMENT_LOCKED = "document_locked"
DOCUMENT_UNLOCKED = "document_unlocked"
DOCUMENT_FORCE_TAKEN = "document_force_taken"
```

**Backend -- Add handler function in handlers.py (follows existing pattern):**
```python
# Source: follows handle_task_update pattern in handlers.py

def get_document_room(document_id: UUID | str) -> str:
    """Get the room ID for a document."""
    return f"document:{document_id}"

async def handle_document_lock_change(
    document_id: UUID | str,
    lock_type: str,  # "locked" | "unlocked" | "force_taken"
    lock_holder: dict | None,
    triggered_by: str | None = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    mgr = connection_manager or manager
    room_id = get_document_room(document_id)

    message_type_map = {
        "locked": MessageType.DOCUMENT_LOCKED,
        "unlocked": MessageType.DOCUMENT_UNLOCKED,
        "force_taken": MessageType.DOCUMENT_FORCE_TAKEN,
    }

    message = {
        "type": message_type_map[lock_type].value,
        "data": {
            "document_id": str(document_id),
            "lock_holder": lock_holder,
            "triggered_by": triggered_by,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }

    recipients = await mgr.broadcast_to_room(room_id, message)
    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=message_type_map[lock_type].value,
        success=True,
    )
```

**Frontend -- Add to MessageType enum in lib/websocket.ts:**
```typescript
// Add to MessageType enum:
DOCUMENT_LOCKED = 'document_locked',
DOCUMENT_UNLOCKED = 'document_unlocked',
DOCUMENT_FORCE_TAKEN = 'document_force_taken',
```

### Pattern 7: Room Auth for Document Rooms

**What:** Add document room access checks to `room_auth.py`.
**When to use:** When users join `document:{uuid}` rooms via WebSocket.

```python
# Add to _check_room_access_async in room_auth.py:
elif room_type == "document":
    return await _check_document_access(db, user_id, resource_id)

# New function (requires Document model from Phase 1):
async def _check_document_access(db: AsyncSession, user_id: UUID, document_id: UUID) -> bool:
    """Check if user has access to the document via its scope's application membership."""
    from ..models.document import Document  # Phase 1 model
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        return False
    # Documents are scoped to applications -- check application membership
    return await _check_application_access(db, user_id, document.application_id)
```

### Pattern 8: Frontend Lock Hook

**What:** React hook encapsulating lock state, heartbeat, and acquire/release API calls.
**When to use:** In the document editor component.

```typescript
// use-document-lock.ts
// Source: follows use-presence.ts heartbeat pattern + use-queries.ts fetch pattern

interface LockHolder {
  user_id: string
  user_name: string
  acquired_at: number | null
}

interface UseDocumentLockReturn {
  lockHolder: LockHolder | null      // Current lock holder info
  isLockedByMe: boolean              // Am I the lock holder?
  isLockedByOther: boolean           // Is someone else holding the lock?
  acquireLock: () => Promise<boolean> // Try to acquire lock
  releaseLock: () => Promise<void>   // Release lock (manual stop editing)
  forceTakeLock: () => Promise<boolean> // Owner override
  canForceTake: boolean              // Does current user have owner permissions?
  isLoading: boolean                 // Is lock status loading?
}

function useDocumentLock(documentId: string, userRole: string | null): UseDocumentLockReturn {
  // Implementation pattern:
  // 1. useQuery for initial lock status (GET /api/documents/{id}/lock)
  //    - refetchInterval: 30000 (30s fallback poll for stale lock detection)
  // 2. useMutation for acquire/release/force-take
  // 3. useEffect with setInterval for heartbeat (POST /api/documents/{id}/lock/heartbeat)
  //    - 10s interval, only when isLockedByMe
  // 4. Subscribe to WebSocket events (document_locked/unlocked/force_taken)
  //    - Update queryClient cache on WebSocket events (instant update)
  // 5. Inactivity timer: track last editor activity, auto-release after 30s
  //    - Track: keydown, mousemove in editor area (not global window)
  //    - On timeout: call save first, then release
  // 6. Cleanup: release lock on unmount + beforeunload handler
  //    - Use lockReleasedRef to prevent double-release
  // 7. canForceTake = userRole === 'owner'
  // 8. All HTTP calls via window.electronAPI.post/delete/get
}
```

### Pattern 9: Client-Side Inactivity Timer (LOCK-03)

**What:** Auto-release lock after 30 seconds of no user activity in the editor.
**When to use:** While user holds the lock.

```typescript
// Inside useDocumentLock:
// - Track last activity timestamp (keypress, mouse move in EDITOR AREA only)
// - setInterval checks every 5s: if (now - lastActivity > 30000) { save(); releaseLock(); }
// - Reset timer on any editor activity
// - IMPORTANT: This is CLIENT-SIDE only -- server TTL (LOCK-05) is the crash safety net
//
// Implementation note: use useRef for lastActivity to avoid re-renders.
// The check interval (5s) means worst-case release happens at 35s of inactivity.
// This is acceptable -- the 30s requirement is approximate.
```

### Pattern 10: Force-Take Flow (LOCK-06)

**What:** The sequence of events when an application owner force-takes a lock.
**When to use:** Owner clicks "Take over editing" on a locked document.

```
1. Owner clicks "Take over editing" button
2. Frontend calls POST /api/documents/{id}/lock/force-take
3. Backend:
   a. Verify current_user has "owner" role in document's application
   b. Call lock_service.force_take_lock() -- returns previous holder info
   c. If previous holder exists:
      - Broadcast DOCUMENT_FORCE_TAKEN to document room
        (includes previous_holder_id so their client can react)
   d. Return new lock info to owner
4. Previous holder's client receives DOCUMENT_FORCE_TAKEN via WebSocket:
   a. Trigger immediate auto-save of current editor content
   b. Set editor to read-only mode
   c. Show banner: "Editing taken over by [owner_name]"
5. Owner's client receives lock confirmation:
   a. Set editor to edit mode
   b. Start heartbeat timer
   c. Show banner: "You are editing this document"
```

**IMPORTANT:** The previous holder's save happens AFTER the force-take, not before. This is because:
- We cannot wait for the previous holder's client to respond (it might be crashed)
- The previous holder's client saves their current state to the server when it receives the event
- If the previous holder's client is unreachable, the last server-saved state is preserved
- Only the delta between last save and force-take moment is potentially lost

### Anti-Patterns to Avoid

- **Polling for lock status instead of WebSocket:** Wastes bandwidth and adds latency. Use WebSocket broadcast for instant lock change notifications, with `useQuery` at 30s refetch as fallback for stale lock detection (crash recovery scenario).
- **Using `DEL` without ownership check:** Another user could steal your lock between GET and DEL. Always use the Lua compare-and-delete script.
- **TTL too short (< heartbeat interval):** If TTL < heartbeat interval, the lock expires between heartbeats. TTL must be > 2x heartbeat interval (45s vs 10s).
- **No save before release:** LOCK-03 and LOCK-06 both require saving the document before releasing the lock. Release flow: save content -> release lock -> broadcast unlock.
- **Blocking lock acquisition:** Users should never wait/retry for a lock. If it's locked, show "Being edited by [name]" immediately. No spin-lock.
- **Using `redis_service.set()` for lock acquisition:** The `RedisService.set()` method (line 207-227) uses `setex` which does NOT support the `NX` flag. Must use `redis_service.client.set(key, value, nx=True, ex=ttl)` directly.
- **Forgetting `tonumber()` in Lua EXPIRE calls:** ARGV values arrive as strings in Lua. Must call `tonumber(ARGV[2])` before passing to `EXPIRE`.
- **Using `useAuthStore` in the lock hook:** Per STATE.md, Zustand stores are being removed. The hook should receive user info as props or use the React Context replacement that Phase 1 introduces.
- **Global activity tracking for inactivity timer:** Only track activity within the editor element, not the entire window. Otherwise, clicking sidebar items resets the timer even though the user isn't editing.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic lock acquire | Custom check-then-set with race conditions | `SET key value NX EX ttl` (single Redis command) | Race conditions between GET and SET; the NX flag makes it atomic |
| Safe lock release | `GET` then `DEL` in two commands | Lua script with `EVAL` | Another process could acquire between GET and DEL |
| Lock TTL extension | Python timer + `EXPIRE` | Lua script comparing owner before `EXPIRE` | Another user could have taken the lock between check and extend |
| Cross-worker lock broadcasts | Custom pub/sub implementation | `manager.broadcast_to_room()` (existing) | Already built, tested, handles cross-worker delivery via Redis pub/sub |
| Frontend heartbeat timing | Custom setTimeout chain | `setInterval` with cleanup in `useEffect` return | Matches `use-presence.ts` pattern; simple and sufficient for 10s intervals |
| HTTP calls from renderer | Raw `fetch()` | `window.electronAPI.get/post/delete()` | All existing hooks use this Electron IPC bridge pattern |
| Lock status caching | Custom React state | TanStack Query `useQuery` with 30s `refetchInterval` | Built-in stale-while-revalidate, dedup, and cache invalidation via WebSocket |

**Key insight:** Every lock operation that involves "check state then modify state" must be atomic. Redis Lua scripts provide this atomicity. Never split these into separate Redis commands.

## Common Pitfalls

### Pitfall 1: Lock Expires During Save

**What goes wrong:** User's inactivity timer fires, triggering save + release. But the save takes >15 seconds (large document, slow network). Meanwhile, the Redis TTL expires and another user acquires the lock. Now two users think they own the document.
**Why it happens:** The save operation is async and can take variable time.
**How to avoid:** The save endpoint should be independent of lock ownership. If the lock expired during save, the save still succeeds (it's the user's work). The release will fail silently (Lua script returns 0 because lock is gone or owned by someone else). The client's heartbeat will have already stopped, so it won't interfere.
**Warning signs:** Save latency exceeding 10 seconds in production monitoring.

### Pitfall 2: Stale Lock Banner After Redis TTL Expiry

**What goes wrong:** User A holds the lock. User A's client crashes. Redis TTL expires the lock after 45s. But User B's UI still shows "Being edited by User A" because no WebSocket event was sent for TTL expiry.
**Why it happens:** Redis TTL expiry is passive -- there's no built-in notification when a key expires.
**How to avoid:** Frontend `useQuery` refetches lock status every 30 seconds. After the TTL expires, the next poll returns `locked: false`, clearing the banner. Maximum staleness: 30 seconds after TTL expiry (75 seconds total after last heartbeat).
**Why NOT use Redis keyspace notifications:** They require `notify-keyspace-events Ex` server configuration, add subscriber management complexity, and are unreliable under heavy load. The 30s poll is simple, sufficient, and matches the existing stale-while-revalidate pattern used throughout the app.
**Warning signs:** Users reporting "stuck" lock banners that don't clear.

### Pitfall 3: Double-Release on Unmount

**What goes wrong:** React component unmounts, triggering both `useEffect` cleanup and `beforeunload` handler. Both call `releaseLock()`, but the second call fails silently.
**Why it happens:** Multiple cleanup paths fire for the same event.
**How to avoid:** Use a `lockReleasedRef` (useRef<boolean>) to track whether release has already been called. Check before releasing. The server-side Lua release script is also idempotent (returns 0 if lock doesn't exist or caller doesn't own it).
**Warning signs:** Console errors on page navigation away from editor.

### Pitfall 4: Heartbeat Stops But Tab Stays Open

**What goes wrong:** User switches to another browser tab. `setInterval` slows down (browser throttles background tabs). Heartbeat stops arriving at the expected 10s interval. Lock TTL expires.
**Why it happens:** Browsers throttle timers in background tabs to save CPU/battery.
**How to avoid:**
1. **Electron context:** This is a desktop app, not a web browser. Electron's renderer process is less aggressive about throttling. However, the `visibilitychange` event should still be handled.
2. Use `document.visibilitychange` event to detect tab becoming hidden/visible.
3. When tab becomes visible again, immediately send a heartbeat and re-check lock status via `queryClient.invalidateQueries()`.
4. The 45s TTL provides significant buffer -- even aggressive throttling (1s minimum timer) won't cause 45s of missed heartbeats.
**Warning signs:** Lock unexpectedly lost when switching between app sections.

### Pitfall 5: Force-Take Without Saving Previous Editor's Work

**What goes wrong:** Owner force-takes the lock. Previous editor's unsaved changes are lost.
**Why it happens:** Force-take overwrites the Redis lock key without triggering a save on the previous editor's client.
**How to avoid:** The force-take broadcasts a `DOCUMENT_FORCE_TAKEN` WebSocket event. The previous editor's client receives this and triggers an immediate save before switching to read-only mode. If the previous editor's client is crashed/unreachable, the last server-saved state is preserved -- only unsaved delta since last auto-save is lost (at most 10 seconds of typing, since Phase 4's auto-save runs on a 10s debounce).
**Warning signs:** Users reporting lost work after owner override.

### Pitfall 6: Zustand Store Dependency

**What goes wrong:** The lock hook imports from `@/stores/auth-store` (Zustand) which is being removed in Phase 1.
**Why it happens:** The existing `use-presence.ts` currently uses `useAuthStore`. By Phase 5, this will have been migrated to React Context.
**How to avoid:** The lock hook should accept `userId`, `userName`, and `userRole` as parameters (or use the React Context provider that Phase 1 introduces). Do NOT import from `@/stores/auth-store`. Check what Phase 1 actually delivers before implementing.
**Warning signs:** Import errors at build time.

### Pitfall 7: Lock Service Depends on Document Model Not Yet Created

**What goes wrong:** The lock service needs to look up the document's `application_id` for permission checks, but the Document model doesn't exist yet.
**Why it happens:** The Document model is created in Phase 1 (plan 01-03). Phase 5 depends on Phase 4 which depends on Phase 3 which depends on Phase 2 which depends on Phase 1.
**How to avoid:** By Phase 5, the Document model will exist. The force-take endpoint needs to query the Document table to find `application_id`, then use `PermissionService.get_user_application_role()` to verify the user is an owner. The lock service itself does NOT need the Document model -- it only uses Redis. Only the router needs the DB query for permission checks.
**Warning signs:** Import errors if Document model doesn't exist.

## Code Examples

### REST API Endpoints (FastAPI Router)

```python
# Source: follows existing router patterns (comments.py, checklists.py)

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..schemas.document_lock import DocumentLockResponse, LockHolder
from ..services.auth_service import get_current_user
from ..services.document_lock_service import DocumentLockService, get_lock_service
from ..services.permission_service import PermissionService
from ..websocket.handlers import handle_document_lock_change

router = APIRouter(prefix="/api/documents", tags=["document-locks"])

@router.post("/{document_id}/lock", response_model=DocumentLockResponse)
async def acquire_lock(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
):
    """Acquire edit lock on a document."""
    result = await lock_service.acquire_lock(
        str(document_id), str(current_user.id), current_user.display_name or "Unknown"
    )
    if result is None:
        holder = await lock_service.get_lock_holder(str(document_id))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Document is locked", "lock_holder": holder}
        )
    await handle_document_lock_change(str(document_id), "locked", result)
    return DocumentLockResponse(locked=True, lock_holder=LockHolder(**result))

@router.delete("/{document_id}/lock", response_model=DocumentLockResponse)
async def release_lock(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
):
    """Release edit lock on a document."""
    released = await lock_service.release_lock(str(document_id), str(current_user.id))
    if released:
        await handle_document_lock_change(str(document_id), "unlocked", None)
    return DocumentLockResponse(locked=False, lock_holder=None)

@router.post("/{document_id}/lock/heartbeat")
async def lock_heartbeat(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
):
    """Extend lock TTL (client heartbeat)."""
    extended = await lock_service.heartbeat(str(document_id), str(current_user.id))
    if not extended:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lock not held by you")
    return {"extended": True}

@router.get("/{document_id}/lock", response_model=DocumentLockResponse)
async def get_lock_status(
    document_id: UUID,
    lock_service: DocumentLockService = Depends(get_lock_service),
):
    """Get current lock status for a document."""
    holder = await lock_service.get_lock_holder(str(document_id))
    if holder:
        return DocumentLockResponse(locked=True, lock_holder=LockHolder(**holder))
    return DocumentLockResponse(locked=False, lock_holder=None)

@router.post("/{document_id}/lock/force-take", response_model=DocumentLockResponse)
async def force_take_lock(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    lock_service: DocumentLockService = Depends(get_lock_service),
    db: AsyncSession = Depends(get_db),
):
    """Force-take lock (application owner only)."""
    # Permission check: must be application owner
    # Need to look up document's application_id
    from ..models.document import Document  # Phase 1 model
    from sqlalchemy import select

    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    perm_service = PermissionService(db)
    role = await perm_service.get_user_application_role(
        current_user.id, document.application_id
    )
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only application owners can force-take locks")

    old_holder = await lock_service.force_take_lock(
        str(document_id), str(current_user.id), current_user.display_name or "Unknown"
    )

    new_holder = {
        "user_id": str(current_user.id),
        "user_name": current_user.display_name or "Unknown",
    }

    if old_holder:
        await handle_document_lock_change(
            str(document_id), "force_taken", new_holder,
            triggered_by=str(current_user.id),
        )

    return DocumentLockResponse(locked=True, lock_holder=LockHolder(**new_holder))
```

### Pydantic Schemas

```python
# Source: follows existing schema patterns (comment.py)
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class LockHolder(BaseModel):
    """Lock holder information."""
    model_config = ConfigDict(from_attributes=True)

    user_id: str = Field(..., description="UUID of the lock holder")
    user_name: str = Field(..., description="Display name of the lock holder")
    acquired_at: Optional[float] = Field(None, description="Unix timestamp when lock was acquired")

class DocumentLockResponse(BaseModel):
    """Response for lock status queries and mutations."""
    locked: bool = Field(..., description="Whether the document is currently locked")
    lock_holder: Optional[LockHolder] = Field(None, description="Lock holder info if locked")
```

### Frontend Lock Banner Component

```tsx
// LockBanner.tsx -- follows existing Radix UI + Tailwind patterns
import { LockHolder } from '../hooks/use-document-lock'

interface LockBannerProps {
  lockHolder: LockHolder | null
  canForceTake: boolean
  onForceTake: () => void
  onStopEditing: () => void
  isLockedByMe: boolean
}

function LockBanner({ lockHolder, canForceTake, onForceTake, onStopEditing, isLockedByMe }: LockBannerProps) {
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
| Redlock for all distributed locks | Single-instance for non-critical apps | Ongoing debate | Single-instance is fine for document locking where worst case is brief dual-editing |
| Zustand for state management | React Context + TanStack Query | Phase 1 decision | Lock hook should NOT use Zustand stores |

**Deprecated/outdated:**
- `SETNX` command alone: Superseded by `SET ... NX EX` which combines set-if-not-exists and TTL atomically
- Redlock for document locking: Overkill; single-instance Redis is sufficient when the cost of a brief lock overlap is low
- `useAuthStore` (Zustand): Being removed in Phase 1. Use React Context equivalent.

## Open Questions

1. **Document model field names for application_id**
   - What we know: Phase 1 (plan 01-03) creates the Document model. It will have an `application_id` field for scope-based access control.
   - What's unclear: The exact field name and whether personal documents have a null `application_id` or a special scope field.
   - Recommendation: The lock service doesn't need this -- only the force-take endpoint does. Defer this detail to implementation time when Phase 1 is complete.

2. **Auth context after Zustand removal**
   - What we know: Phase 1 removes `auth-store` (Zustand) and replaces with React Context.
   - What's unclear: The exact API of the React Context provider (hook name, return shape).
   - Recommendation: The lock hook should accept `userId`, `userName`, `userRole` as parameters. The consuming component provides these from whatever auth mechanism Phase 1 delivers. This decouples the lock hook from the auth implementation.

3. **Editor read-only toggle mechanism**
   - What we know: TipTap editors support `editable` prop for toggling read-only mode.
   - What's unclear: Whether Phase 3's editor exposes this as a prop or requires imperative `editor.setEditable(false)`.
   - Recommendation: The lock hook should return `isEditable: boolean` (true when locked by me or unlocked, false when locked by other). The editor component reads this to set TipTap's editable state.

4. **Save callback for inactivity release and force-take**
   - What we know: LOCK-03 requires saving before release. Phase 4 implements auto-save.
   - What's unclear: How the lock hook triggers a save. It needs a reference to Phase 4's save function.
   - Recommendation: The lock hook should accept an `onBeforeRelease: () => Promise<void>` callback. The consuming component passes the auto-save's `saveNow()` function. This keeps the lock hook decoupled from the save implementation.

## Sources

### Primary (HIGH confidence)
- [Redis SET command documentation](https://redis.io/docs/latest/commands/set/) - `NX` and `EX` flags for atomic lock acquisition
- [Redis EVAL command documentation](https://redis.io/docs/latest/commands/eval/) - Lua scripting for atomic multi-step operations
- Codebase: `fastapi-backend/app/services/redis_service.py` - Redis connection (`decode_responses=True`), pub/sub, caching patterns
- Codebase: `fastapi-backend/app/websocket/manager.py` - Room-based broadcast, `MessageType` enum, `broadcast_to_room`
- Codebase: `fastapi-backend/app/websocket/handlers.py` - Handler function pattern (`handle_task_update`, `BroadcastResult`, `get_project_room`)
- Codebase: `fastapi-backend/app/websocket/presence.py` - Heartbeat pattern, TTL constants, cleanup loop
- Codebase: `fastapi-backend/app/websocket/room_auth.py` - Room access checking pattern, cache, room type routing
- Codebase: `fastapi-backend/app/services/permission_service.py` - `get_user_application_role()`, role values ("owner"/"editor"/"viewer")
- Codebase: `fastapi-backend/app/services/auth_service.py` - `get_current_user` dependency
- Codebase: `fastapi-backend/app/routers/comments.py` - Router pattern, auth dependencies, service injection
- Codebase: `fastapi-backend/app/schemas/comment.py` - Pydantic schema pattern with `ConfigDict`, `Field`
- Codebase: `electron-app/src/renderer/hooks/use-presence.ts` - Frontend heartbeat hook pattern, activity tracking, refs
- Codebase: `electron-app/src/renderer/hooks/use-websocket.ts` - WebSocket hook API, subscribe/send pattern
- Codebase: `electron-app/src/renderer/hooks/use-queries.ts` - `window.electronAPI` fetch pattern, `getAuthHeaders`, TanStack Query hooks
- Codebase: `electron-app/src/renderer/lib/websocket.ts` - `MessageType` enum, `WebSocketClient` class
- Codebase: `electron-app/src/renderer/hooks/use-websocket-cache.ts` - WebSocket-to-cache-invalidation pattern
- Codebase: `.planning/ROADMAP.md` - Phase 5 scope, 2 plans, dependencies
- Codebase: `.planning/STATE.md` - Zustand removal decision, IndexedDB caching decision

### Secondary (MEDIUM confidence)
- [redis-py Lock API](https://redis.readthedocs.io/en/stable/lock.html) - Built-in async Lock class (decided against, but verified limitations)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using only existing dependencies (`redis.asyncio`, FastAPI, existing WebSocket infrastructure). No new libraries. Verified all patterns against actual codebase.
- Architecture: HIGH - Follows established patterns already in the codebase (presence manager, WebSocket handlers, room-based broadcasts, Electron IPC). Redis `SET NX EX` is the official recommended lock pattern. All code examples verified against actual codebase patterns.
- Pitfalls: HIGH - Well-documented failure modes mapped to codebase specifics (`decode_responses=True`, Zustand removal, Electron IPC). New pitfalls added based on codebase exploration (Pitfall 6, 7).

**Research date:** 2026-01-31
**Valid until:** 2026-03-31 (stable domain; Redis locking patterns haven't changed in years)

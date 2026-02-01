# Phase 5 Plan 1: Backend Document Locking Summary

**One-liner:** Redis-backed document lock service with Lua scripts, 5 REST endpoints, WebSocket broadcast, and document room auth

## What Was Built

### DocumentLockService (Redis + Lua Scripts)
- `acquire_lock`: Uses `SET NX` with TTL for atomic lock acquisition
- `release_lock`: Lua script verifies ownership via `cjson.decode` before `DEL`
- `heartbeat`: Lua script verifies ownership before `EXPIRE` extension
- `force_take_lock`: Lua script saves old holder, overwrites with new lock
- `get_lock_holder`: Simple `GET` + JSON parse
- 45-second TTL with heartbeat-based extension

### Pydantic Schemas
- `LockHolder`: user_id, user_name, acquired_at
- `DocumentLockResponse`: locked flag + optional LockHolder

### REST Endpoints (5 routes)
- `POST /api/documents/{id}/lock` - Acquire (200 success, 409 if locked)
- `DELETE /api/documents/{id}/lock` - Release (owner-only)
- `GET /api/documents/{id}/lock` - Get status with holder info
- `POST /api/documents/{id}/lock/heartbeat` - Extend TTL (owner-only)
- `POST /api/documents/{id}/lock/force-take` - Owner-only force reclaim (403 for non-owners, personal docs blocked)

### WebSocket Integration
- Three new MessageType enum values: DOCUMENT_LOCKED, DOCUMENT_UNLOCKED, DOCUMENT_FORCE_TAKEN
- `handle_document_lock_change` broadcasts to document room
- `get_document_room` helper returns `document:{uuid}` format

### Room Auth
- `_check_document_access` with scope-aware logic:
  - Personal docs: owner-only access
  - Application docs: checks application membership
  - Project docs: checks project access transitively

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 48af1ed | DocumentLockService + Pydantic schemas |
| 2 | 96edc19 | REST endpoints, WebSocket types, room auth, wiring |

## Files Created
- `fastapi-backend/app/services/document_lock_service.py`
- `fastapi-backend/app/schemas/document_lock.py`
- `fastapi-backend/app/routers/document_locks.py`

## Files Modified
- `fastapi-backend/app/schemas/__init__.py` (added lock schema exports)
- `fastapi-backend/app/routers/__init__.py` (added lock router export)
- `fastapi-backend/app/websocket/manager.py` (3 new MessageType values)
- `fastapi-backend/app/websocket/handlers.py` (document lock handler + room helper)
- `fastapi-backend/app/websocket/room_auth.py` (document room type support)
- `fastapi-backend/app/main.py` (router registration)

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Lua scripts for ownership checks | Atomic GET-check-modify prevents race conditions between workers |
| 45s TTL with heartbeat | Matches frontend heartbeat interval with margin for network latency |
| Personal docs block force-take | Personal docs have no application context for owner role check |
| No prefix on document_locks_router in main.py | Router already has `/api/documents` prefix internally |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed unused variable warning**
- **Found during:** Task 2 ruff check
- **Issue:** `old_holder` assigned but not used in force-take endpoint
- **Fix:** Removed variable assignment, called `force_take_lock()` without capturing return
- **Files modified:** `fastapi-backend/app/routers/document_locks.py`

## Verification Results

- All imports resolve correctly via `app.main`
- 5 lock routes registered in FastAPI app
- 3 document message types in MessageType enum
- room_auth.py compiles with document access check
- ruff clean on new files (no new warnings introduced)

## Duration

~4 minutes

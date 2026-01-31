# Codebase Concerns

**Analysis Date:** 2026-01-31

## Tech Debt

**WebSocket Broadcast Error Handling:**
- Issue: `asyncio.gather(*tasks, return_exceptions=True)` in `broadcast_to_target_users` function silently swallows exceptions from failed sends without logging
- Files: `fastapi-backend/app/websocket/handlers.py:58`
- Impact: Failed message deliveries go undetected, some users may miss real-time updates without knowing broadcast failed
- Fix approach: Extract and log exceptions from gather results before summing

**Bare Exception Catches in Database Layer:**
- Issue: Generic `except Exception` blocks without specific exception types in critical paths
- Files: `fastapi-backend/app/database.py:56`, `fastapi-backend/scripts/insert_archived_projects.py:298`
- Impact: Connection failures, permission errors, and constraint violations masked as generic errors; difficult debugging
- Fix approach: Catch specific SQLAlchemy exceptions (IntegrityError, OperationalError, etc.) for proper error classification

**UUID Type Coercion in WebSocket Handlers:**
- Issue: Multiple try/except blocks attempting UUID conversion with bare (ValueError, TypeError) catches scattered throughout handlers
- Files: `fastapi-backend/app/websocket/handlers.py:864-878, 934-941, 1000-1005, 1064-1080, 1135-1142, 1198-1205`
- Impact: Invalid UUIDs logged only as warnings; bad data silently ignored; no validation before sending to users
- Fix approach: Centralize UUID validation helper with strict validation and error details

**Event Handler Authorization Gaps:**
- Issue: `route_incoming_message` allows authorization bypass for non-join_room messages; only JOIN_ROOM messages are checked against `room_authorizer`
- Files: `fastapi-backend/app/websocket/handlers.py:628-671`
- Impact: Users could send application-specific messages to rooms they're not authorized for if handler doesn't double-check permissions
- Fix approach: Enforce room authorization check at handler level before processing all message types

## Known Bugs

**AsyncIO Gather Return Exceptions Not Inspected:**
- Symptoms: Broadcast operations report success count even when underlying send operations fail
- Files: `fastapi-backend/app/websocket/handlers.py:52-60`
- Trigger: Any failed WebSocket send during parallel broadcast (network error, user disconnected, etc.)
- Workaround: Monitor server logs for partial delivery; implement client-side resync on reconnect

**Type Coercion Failures in UUID Fields:**
- Symptoms: Member data with string UUIDs passed directly to UUID constructor without validation
- Files: `fastapi-backend/app/websocket/handlers.py:862-878, 1064-1080`
- Trigger: Malformed UUID strings in payload data (e.g., from frontend typo or corrupt cache)
- Workaround: Frontend must validate UUIDs before sending; backend logs but continues

**Missing Type Safety in Frontend Event Handlers:**
- Symptoms: Type `any` used in 19+ locations across frontend TypeScript code
- Files: `electron-app/src/renderer/components/editor/RichTextEditor.tsx:2`, `electron-app/src/renderer/components/tasks/task-detail.tsx:1`, and 5 other files
- Trigger: Complex nested data structures from WebSocket messages
- Workaround: Rely on runtime validation; prone to silent failures if API response format changes

## Security Considerations

**WebSocket Message Injection Risk:**
- Risk: `route_incoming_message` calls `await mgr.handle_message(connection, data)` then processes `data` again without sanitization
- Files: `fastapi-backend/app/websocket/handlers.py:628-717`
- Current mitigation: Connection manager validates message type enum; room_authorizer checks JOIN_ROOM
- Recommendations:
  - Validate all message structure/schema before processing application-specific handlers
  - Rate-limit message types per user/room to prevent DoS via broadcast spam
  - Add signed message verification for critical operations (task_moved, role changes)

**Database Pool Exhaustion Under Load:**
- Risk: Pool size 50 + 100 overflow may be insufficient for 5000 concurrent users with long-running queries
- Files: `fastapi-backend/app/database.py:16-24`
- Current mitigation: Connection pool warmup at startup, pool_pre_ping=True, timeout=15
- Recommendations:
  - Monitor actual connection usage under load testing
  - Consider query timeout on expensive operations (like `applications.py:618` that loads all tasks)
  - Add circuit breaker pattern for database health degradation

**Unvalidated File Upload Size:**
- Risk: MAX_FILE_SIZE = 100MB enforced in code but not at FastAPI middleware level
- Files: `fastapi-backend/app/routers/files.py:41`
- Current mitigation: Application member check before upload
- Recommendations:
  - Add FastAPI max_body_size middleware
  - Validate Content-Length header before accepting upload
  - Implement per-user/project upload quota

**Redis Connection Secrets in Debug:**
- Risk: Connection errors in redis_service may log full connection URL with credentials
- Files: `fastapi-backend/app/services/redis_service.py:76-80`
- Current mitigation: Service logs "Redis connected" without details
- Recommendations:
  - Mask credentials in error messages
  - Log redis_url with redacted password (e.g., redis://user:***@host:port)

## Performance Bottlenecks

**N+1 Queries in Application List Endpoints:**
- Problem: Loading all applications then fetching counts/statuses in separate queries per app
- Files: `fastapi-backend/app/routers/applications.py:159-223` (member apps load, counts fetched separately at lines 207, 222)
- Cause: Using `.all()` to materialize list, then iterating to fetch additional data
- Improvement path:
  - Use SQLAlchemy selectinload/joinedload to fetch counts in single query
  - Implement batch query helpers that fetch data for multiple applications at once
  - Consider view/materialized table for aggregated counts if queries slow

**Full Task Scan for Archived Projects:**
- Problem: `applications.py:597-618` loads all project_ids then queries ALL tasks across all projects to find first N
- Files: `fastapi-backend/app/routers/applications.py:597-618`
- Cause: Cursor-based pagination on created_at timestamp across multiple projects with no project filter until after fetch
- Improvement path:
  - Use compound cursor (project_id, created_at) to anchor pagination more precisely
  - Add project_id to initial query to reduce result set before cursor filtering
  - Benchmark against limit 1000 with filter vs current approach

**Broadcast Parallelism Overhead:**
- Problem: Each broadcast spawns new asyncio tasks for all target users; 5000 users = 5000 tasks potentially
- Files: `fastapi-backend/app/websocket/handlers.py:52-60`, `broadcast_to_target_users` function
- Cause: No batching or windowing of broadcast sends
- Improvement path:
  - Batch direct sends to users in groups of 100
  - Use asyncio.Semaphore to limit concurrent sends (e.g., max 500 parallel)
  - Profile memory impact under 5000 user load

**Redis Keys Pattern Scan with KEYS Command:**
- Problem: `redis_service.py:250` uses KEYS command which blocks Redis server during scan
- Files: `fastapi-backend/app/services/redis_service.py:237-253`
- Cause: No pagination on pattern matching
- Improvement path:
  - Use SCAN cursor instead of KEYS for non-blocking iteration
  - Add warning when used (currently used for cache invalidation on role changes)
  - Consider pre-computing invalidation targets instead of pattern scan

## Fragile Areas

**Concurrent Checklist Item Reordering:**
- Files: `fastapi-backend/app/routers/checklists.py`, `fastapi-backend/app/websocket/handlers.py:1731-1775`
- Why fragile: No optimistic locking on item order; two simultaneous reorder requests can race and apply out-of-order updates
- Safe modification: Add version field to checklist_item, increment on each modification, validate version matches before save
- Test coverage: No concurrent update tests in `fastapi-backend/tests/test_checklists.py`

**WebSocket Connection State Machine:**
- Files: `fastapi-backend/app/websocket/manager.py`, `electron-app/src/renderer/lib/websocket.ts`
- Why fragile: Multiple async operations can trigger state transitions simultaneously; reconnect race conditions possible
- Safe modification: Use async locks to serialize state transitions; validate state before each operation (e.g., "DISCONNECTED can only transition to CONNECTING")
- Test coverage: Basic connection tests exist but no chaos engineering tests for dropped packets

**Task Status Derivation Complexity:**
- Files: `fastapi-backend/app/services/status_derivation_service.py` (200+ lines of status logic)
- Why fragile: Derivation priority order (Done → Issue → In Progress → Todo) spread across multiple functions; inconsistent between single-task and bulk operations
- Safe modification: Consolidate all derivation logic into single canonical function; add extensive unit test matrix
- Test coverage: `fastapi-backend/tests/test_status_derivation.py` has 806 lines but needs explicit regression tests for each priority order edge case

**Database Migration Sequencing:**
- Files: `fastapi-backend/alembic/versions/` (8 migrations as of Jan 31)
- Why fragile: No rollback validation; alembic rev down requires manual testing
- Safe modification: Test each migration backward (rev down) during CI; add idempotent down migrations
- Test coverage: Migrations tested only forward on PostgreSQL

## Missing Critical Features

**Search Resilience:**
- Problem: No documented fallback if Meilisearch is down; full-text search endpoint likely returns 5xx error
- Blocks: Real-time search in knowledge base; users cannot browse documents if search fails
- Implementation: Add cache layer; return recent documents if search fails; implement retry with exponential backoff

**Document Conflict Resolution for Concurrent Edits:**
- Problem: Yjs/CRDT integration for notes exists but no automatic conflict resolution strategy documented
- Blocks: Multiple users editing same document simultaneously may see inconsistent state
- Implementation: Document merge strategy; add tests for concurrent Yjs updates; consider server-side convergence guarantee

**WebSocket Reconnection with State Recovery:**
- Problem: No mechanism to restore room subscriptions after reconnect
- Blocks: Users see blank screens after network hiccup; require manual page refresh
- Implementation: Send list of previously subscribed rooms on CONNECTED message; client resubscribes

## Test Coverage Gaps

**WebSocket Broadcast Failure Scenarios:**
- What's not tested: Partial failures in broadcast_to_target_users (e.g., 3 of 5 sends fail)
- Files: `fastapi-backend/app/websocket/handlers.py`, test file `fastapi-backend/tests/test_websocket.py`
- Risk: Silent failures go undetected in production; return_exceptions=True hides problems
- Priority: HIGH - Affects real-time user experience

**Concurrent Mutation on Same Resource:**
- What's not tested: Two simultaneous PATCH requests to same task (status change race)
- Files: `fastapi-backend/app/routers/tasks.py` (no concurrent mutation tests)
- Risk: Last-write-wins may violate business logic (e.g., task assigned then reassigned simultaneously)
- Priority: HIGH - Can corrupt task state

**Redis Connection Failover:**
- What's not tested: Redis goes down mid-broadcast; reconnection handling
- Files: `fastapi-backend/app/services/redis_service.py` (no failover tests)
- Risk: WebSocket pub/sub fails silently; multi-worker deployments split-brain
- Priority: MEDIUM - Production deployments require failover testing

**Frontend Memory Leaks in Long Sessions:**
- What's not tested: Memory usage over 8+ hour session with 100+ rooms subscribed
- Files: `electron-app/src/renderer/hooks/use-websocket.ts`, component cleanup
- Risk: Browser memory grows unbounded; causes performance degradation after extended use
- Priority: MEDIUM - Affects daily active users with long sessions

**File Upload Virus/Malware Scanning:**
- What's not tested: No antivirus/malware scanning of uploaded files
- Files: `fastapi-backend/app/routers/files.py` (FILE_UPLOAD endpoint)
- Risk: Malicious files stored in MinIO; distributed to other users
- Priority: CRITICAL for production deployments

---

*Concerns audit: 2026-01-31*

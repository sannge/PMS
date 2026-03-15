"""FastAPI application entry point."""

import asyncio
import json
import logging
import traceback
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from .config import settings

# Configure logging to show errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# STARTUP BANNER - Confirms which backend is running
# ============================================================================
logger.info("PM API starting up - WebSocket logging ENABLED")

from .database import warmup_connection_pool
from .routers import admin_config_router, ai_chat_router, ai_config_router, ai_import_router, ai_oauth_router, ai_query_router, application_members_router, applications_router, auth_router, chat_sessions_router, checklists_router, comments_router, dashboard_router, document_folders_router, document_locks_router, document_search_router, document_tags_router, documents_router, files_router, folder_files_router, invitations_router, notifications_router, project_assignments_router, project_members_router, projects_router, tasks_router, users_router
from .websocket import manager, route_incoming_message, check_room_access
from .models.user import User
from .services.auth_service import decode_access_token, get_current_user, is_token_blacklisted, validate_ws_connection_token
from .dependencies.redis_gate import require_redis
from .services.redis_service import redis_service
from .services.archive_service import archive_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""
    # Startup
    logger.info("Warming up database connection pool...")
    await warmup_connection_pool()
    logger.info("Database connection pool ready")

    logger.info("Connecting to Redis...")
    try:
        await redis_service.connect()
        logger.info("Redis connected")

        logger.info("Initializing WebSocket manager with Redis...")
        await manager.initialize_redis()
        logger.info("WebSocket manager Redis initialized")

        logger.info("Starting Redis pub/sub listener...")
        await redis_service.start_listening()
        logger.info("Redis pub/sub listener started")

        # Start background health monitor with state-change callback
        async def _on_redis_state_change(connected: bool) -> None:
            """Handle Redis connected ↔ disconnected transitions."""
            if connected:
                logger.info("Redis recovered — re-initializing pub/sub and WebSocket relay")
                try:
                    await redis_service.start_listening()
                    await manager.initialize_redis()
                except Exception as exc:
                    logger.error("Failed to re-initialize after Redis recovery: %s", exc)
            else:
                logger.warning("Redis health monitor detected outage — gate is active")

            # Broadcast status change to all local WebSocket connections
            from .websocket.manager import MessageType
            try:
                await manager.broadcast_to_all({
                    "type": MessageType.REDIS_STATUS_CHANGED,
                    "data": {"connected": connected},
                })
            except Exception as exc:
                logger.error("Failed to broadcast Redis status change: %s", exc)

        await redis_service.start_health_monitor(
            interval=5, on_state_change=_on_redis_state_change
        )
        logger.info("Redis health monitor started")
    except Exception as e:
        if settings.redis_required:
            logger.error(f"Redis connection failed and REDIS_REQUIRED=true: {e}")
            raise RuntimeError(
                f"Redis is required for multi-worker deployment but connection failed: {e}"
            )
        logger.warning(f"Redis connection failed, running in single-worker mode: {e}")

    # Note: Background jobs (archive, presence cleanup) are handled by ARQ worker
    # Run separately with: arq app.worker.WorkerSettings

    # Initialize LangGraph checkpointer (required for interrupt/resume in clarify node)
    # Uses Postgres for production (survives restarts, works with multiple workers)
    # Falls back to in-memory MemorySaver if Postgres checkpointer fails
    #
    # Connection budget per worker:
    # - SQLAlchemy pool: pool_size(50) + max_overflow(100) = 150 max
    # - Checkpointer pool: 10 connections (psycopg_pool)
    # - Total per worker: 160
    # - With 4 workers: 640 total (ensure Postgres max_connections >= 700)
    from .ai.agent.graph import set_checkpointer
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
        from psycopg.rows import dict_row
        from urllib.parse import quote_plus
        pg_uri = (
            f"postgresql://{settings.db_user}:{quote_plus(settings.db_password)}"
            f"@{settings.db_server}:{settings.db_port}/{settings.db_name}"
        )
        # Use a bounded connection pool instead of the default single
        # connection to limit Postgres connection consumption (DB-002).
        # F16: Raised from 5 to 10 to avoid bottleneck with _MAX_CONCURRENT_AGENTS=50.
        _checkpointer_pool = AsyncConnectionPool(
            pg_uri,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        )
        await _checkpointer_pool.open()
        pg_checkpointer = AsyncPostgresSaver(conn=_checkpointer_pool)
        await pg_checkpointer.setup()
        set_checkpointer(pg_checkpointer)
        app.state._checkpointer_pool = _checkpointer_pool  # prevent GC, clean up on shutdown
        logger.info("LangGraph checkpointer initialized (AsyncPostgresSaver → Postgres, pool_size=10)")
    except Exception as e:
        if getattr(settings, 'redis_required', False):
            logger.critical(
                "Postgres checkpointer failed and redis_required=True "
                "(multi-worker mode). Cannot use MemorySaver fallback: %s", e,
            )
            raise RuntimeError(
                f"Checkpointer initialization failed in multi-worker mode: {e}"
            ) from e
        logger.warning(f"Postgres checkpointer failed, falling back to MemorySaver: {e}")
        from langgraph.checkpoint.memory import MemorySaver
        set_checkpointer(MemorySaver())
        logger.info("LangGraph checkpointer initialized (MemorySaver — in-memory fallback, single-worker only)")

    # Initialize Meilisearch (non-critical -- app starts even if Meilisearch is down)
    try:
        from .services.search_service import init_meilisearch
        await init_meilisearch()
        logger.info("Meilisearch initialized")
    except Exception as e:
        logger.warning(f"Meilisearch initialization failed (search degraded): {e}")

    # Initialize AgentConfigService (load all config from DB into memory cache)
    try:
        from .ai.config_service import get_agent_config
        from .database import async_session_maker as _asm
        _agent_cfg = get_agent_config()
        _agent_cfg.set_db_session_factory(_asm)
        await _agent_cfg.load_all()
        logger.info("AgentConfigService initialized")

        # Reload rate limits now that config is available from DB
        from .ai.rate_limiter import reload_rate_limits
        reload_rate_limits()
        logger.info("Rate limits reloaded from config")

        # Start Redis invalidation listener as background task
        from .utils.tasks import fire_and_forget
        fire_and_forget(_agent_cfg.subscribe_invalidation(), name="agent-cfg-subscription")
    except Exception as e:
        logger.warning(f"AgentConfigService initialization failed: {e}")

    yield

    # Shutdown
    # Drain any in-flight background tasks before tearing down connections
    from .utils.tasks import drain_background_tasks
    await drain_background_tasks(timeout=5.0)

    # Close Postgres checkpointer connection pool (DB-002: bounded psycopg_pool)
    checkpointer_pool = getattr(app.state, "_checkpointer_pool", None)
    if checkpointer_pool:
        try:
            await checkpointer_pool.close()
            logger.info("Postgres checkpointer connection pool closed")
        except Exception:
            pass

    logger.info("Stopping Redis health monitor...")
    await redis_service.stop_health_monitor()

    logger.info("Disconnecting from Redis...")
    await redis_service.disconnect()
    logger.info("Redis disconnected")


# Create FastAPI application
_is_dev = settings.environment == "development"
app = FastAPI(
    title="PM API",
    description="Project Management API with Jira-like features and knowledge base",
    version="1.0.0",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
    lifespan=lifespan,
)

# CORS Middleware - required for Electron app requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_origin_regex=r"^http://localhost:(5173|5174|8001|3000)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Cache-Control", "X-Requested-With"],
    expose_headers=["Content-Type", "Cache-Control", "X-Accel-Buffering"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    # Swagger/ReDoc UI needs permissive CSP to load scripts/styles
    path = request.url.path
    if _is_dev and path in ("/docs", "/redoc", "/openapi.json"):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    else:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Database pool exhaustion handler - return 503 so clients can retry
@app.exception_handler(SQLAlchemyTimeoutError)
async def db_pool_exhausted_handler(request: Request, exc: SQLAlchemyTimeoutError):
    """Handle database connection pool exhaustion with 503 Service Unavailable."""
    logger.warning(
        f"Database pool exhausted on {request.method} {request.url}: {exc}"
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Service temporarily unavailable. Please retry.",
            "retry_after": 5,
        },
        headers={"Retry-After": "5"},
    )


# Global exception handler to log errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log all unhandled exceptions with full traceback."""
    logger.error(f"Unhandled exception on {request.method} {request.url}:")
    logger.error(f"Exception type: {type(exc).__name__}")
    logger.error(f"Exception message: {str(exc)}")
    logger.error(f"Traceback:\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Include API routers
app.include_router(auth_router)
app.include_router(applications_router)
app.include_router(application_members_router)
app.include_router(projects_router)
app.include_router(project_assignments_router)
app.include_router(project_members_router)
app.include_router(tasks_router)

app.include_router(files_router)
app.include_router(notifications_router)
app.include_router(invitations_router)
app.include_router(users_router)
app.include_router(dashboard_router)
app.include_router(comments_router)
app.include_router(checklists_router)
app.include_router(
    document_locks_router,
    tags=["document-locks"],
    dependencies=[Depends(require_redis)],
)
app.include_router(document_search_router, tags=["document-search"])
app.include_router(documents_router, prefix="/api", tags=["documents"])
app.include_router(document_tags_router, prefix="/api", tags=["document-tags"])
app.include_router(document_folders_router, prefix="/api", tags=["document-folders"])
app.include_router(admin_config_router)
app.include_router(ai_config_router)
app.include_router(ai_oauth_router)
app.include_router(ai_query_router)
app.include_router(ai_chat_router)
app.include_router(ai_import_router)
app.include_router(chat_sessions_router)
app.include_router(folder_files_router)

# TODO: Mount CopilotKit AG-UI endpoint at startup when the agent graph is
# built.  Requires a compiled graph instance which depends on provider config
# from the DB (resolved per-request currently).  Once a shared graph instance
# is available at startup, use:
#   from .ai.agent.copilotkit_runtime import create_copilotkit_sdk
#   sdk = create_copilotkit_sdk(graph)
#   if sdk:
#       app.mount("/api/copilotkit", sdk)


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "healthy",
        "service": "PM API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check(request: Request):
    """Health check endpoint for monitoring.

    Returns minimal status for unauthenticated requests.
    Returns detailed info (DB, Redis, AI health) only for authenticated users.
    """
    # Check for valid JWT to decide detail level
    auth_header = request.headers.get("authorization", "")
    authenticated = False
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:]
        token_data = decode_access_token(raw_token)
        if token_data and token_data.user_id:
            if not (token_data.jti and await is_token_blacklisted(token_data.jti)):
                authenticated = True

    if not authenticated:
        return {"status": "healthy"}

    redis_health = await redis_service.health_check()

    # Lightweight DB health check
    db_health = "unavailable"
    try:
        from .database import async_session_maker
        async with async_session_maker() as db:
            await asyncio.wait_for(
                db.execute(text("SELECT 1")), timeout=2.0
            )
            db_health = "healthy"
    except Exception:
        db_health = "unavailable"

    # AI health sub-checks (each independently timed out)
    ai_health = await _build_ai_health()

    # QE-R2-001: Include AI agent semaphore utilization
    from .routers.ai_chat import get_agent_semaphore_usage
    ai_agent_slots = get_agent_semaphore_usage()

    return {
        "status": "healthy",
        "database": db_health,
        "redis": redis_health,
        "websocket": {
            "connections": manager.total_connections,
            "rooms": manager.total_rooms,
        },
        "scheduler": {
            "type": "arq",
            "note": "Run ARQ worker separately: arq app.worker.WorkerSettings",
        },
        "ai": ai_health,
        "ai_agent_slots": ai_agent_slots,
    }


# Cache for AI provider connectivity checks (avoid real API calls on every /health)
_ai_health_cache: dict[str, tuple[dict, float]] = {}
_AI_HEALTH_CACHE_TTL = 300  # 5 minutes for successful checks
_AI_HEALTH_FAILURE_CACHE_TTL = 30  # 30 seconds for failed checks


async def _build_ai_health() -> dict:
    """Build AI health section with per-check timeouts.

    Each sub-check is wrapped in asyncio.wait_for with a 2s timeout.
    On timeout or error, that sub-section returns a degraded/unavailable
    status instead of failing the entire health endpoint.

    Embedding and chat provider connectivity checks are cached for 5 minutes
    to avoid making real API calls on every health check.
    """
    import time as _time
    from .database import async_session_maker

    AI_CHECK_TIMEOUT = 2.0

    async def check_sql_access() -> dict:
        """Count available scoped views and report last AI query timestamp."""
        from .ai.schema_context import VALID_VIEW_NAMES
        return {
            "scoped_views_count": len(VALID_VIEW_NAMES),
            "last_query_at": None,  # TODO: track via telemetry once available
        }

    async def check_embedding_provider() -> dict:
        """Resolve default embedding provider and test connectivity.

        Cached for _AI_HEALTH_CACHE_TTL seconds to avoid real API calls
        on every health check (saves API credits and reduces latency).
        """
        now = _time.time()
        cached = _ai_health_cache.get("embedding")
        if cached and cached[1] > now:
            return cached[0]

        from .ai.provider_registry import ProviderRegistry, ConfigurationError
        try:
            async with async_session_maker() as db:
                registry = ProviderRegistry()
                provider, model_id = await registry.get_embedding_provider(db)
                await provider.generate_embedding("test", model_id)
                result = {
                    "name": getattr(provider, '__class__', type(provider)).__name__.lower().replace("provider", ""),
                    "model": model_id,
                    "connected": True,
                }
                _ai_health_cache["embedding"] = (result, now + _AI_HEALTH_CACHE_TTL)
                return result
        except ConfigurationError:
            fail = {"name": None, "model": None, "connected": False}
            _ai_health_cache["embedding"] = (fail, now + _AI_HEALTH_FAILURE_CACHE_TTL)
            return fail
        except Exception:
            fail = {"name": None, "model": None, "connected": False}
            _ai_health_cache["embedding"] = (fail, now + _AI_HEALTH_FAILURE_CACHE_TTL)
            return fail

    async def check_chat_provider() -> dict:
        """Resolve default chat provider and test connectivity.

        Cached for _AI_HEALTH_CACHE_TTL seconds to avoid real API calls
        on every health check.
        """
        now = _time.time()
        cached = _ai_health_cache.get("chat")
        if cached and cached[1] > now:
            return cached[0]

        from .ai.provider_registry import ProviderRegistry, ConfigurationError
        try:
            async with async_session_maker() as db:
                registry = ProviderRegistry()
                adapter, model_id = await registry.get_chat_provider(db)
                await adapter.chat_completion(
                    messages=[{"role": "user", "content": "hi"}],
                    model=model_id,
                    max_tokens=1,
                )
                result = {
                    "name": type(adapter).__name__.lower().replace("provider", ""),
                    "model": model_id,
                    "connected": True,
                }
                _ai_health_cache["chat"] = (result, now + _AI_HEALTH_CACHE_TTL)
                return result
        except ConfigurationError:
            fail = {"name": None, "model": None, "connected": False}
            _ai_health_cache["chat"] = (fail, now + _AI_HEALTH_FAILURE_CACHE_TTL)
            return fail
        except Exception:
            fail = {"name": None, "model": None, "connected": False}
            _ai_health_cache["chat"] = (fail, now + _AI_HEALTH_FAILURE_CACHE_TTL)
            return fail

    async def check_document_chunks_count() -> int:
        """Count total DocumentChunk rows."""
        from sqlalchemy import func, select
        from .models.document_chunk import DocumentChunk
        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(func.count()).select_from(DocumentChunk)
                )
                return result.scalar_one()
        except Exception:
            return 0

    async def check_pending_embedding_jobs() -> int:
        """Query ARQ queue depth from Redis for embedding jobs."""
        try:
            if not redis_service.is_connected:
                return 0
            # ARQ stores pending jobs in a sorted set keyed "arq:queue"
            count = await redis_service.client.zcard("arq:queue")
            return count or 0
        except Exception:
            return 0

    # Run all checks with individual timeouts
    async def _safe_check(coro, default):
        try:
            return await asyncio.wait_for(coro(), timeout=AI_CHECK_TIMEOUT)
        except asyncio.TimeoutError:
            return default
        except Exception:
            return default

    sql_access, embedding, chat, chunks, pending = await asyncio.gather(
        _safe_check(check_sql_access, {"scoped_views_count": 0, "last_query_at": None}),
        _safe_check(check_embedding_provider, {"name": None, "model": None, "connected": False}),
        _safe_check(check_chat_provider, {"name": None, "model": None, "connected": False}),
        _safe_check(check_document_chunks_count, 0),
        _safe_check(check_pending_embedding_jobs, 0),
    )

    return {
        "sql_access": sql_access,
        "embedding_provider": embedding,
        "chat_provider": chat,
        "document_chunks_count": chunks,
        "pending_embedding_jobs": pending,
    }


@app.post("/api/admin/run-archive-jobs")
async def run_archive_jobs_manually(
    current_user: User = Depends(get_current_user),  # noqa: ARG001 — auth required
):
    """
    Manually trigger archive jobs (admin/developer endpoint).

    Archives:
    - Tasks in Done status for 7+ days
    - Projects where all tasks are archived

    Returns the count of archived items.
    """
    from .routers.ai_config import require_developer
    await require_developer(current_user)

    result = await archive_service.run_now()
    return result


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    """
    WebSocket endpoint for real-time collaboration.

    Args:
        websocket: The WebSocket connection
        token: Opaque connection token for authentication (query parameter)

    Authentication uses opaque connection tokens obtained via POST /auth/ws-token.
    JWT tokens are NOT accepted directly to avoid exposing them in URLs/logs.

    Usage:
        ws://localhost:8000/ws?token=<opaque_connection_token>
    """
    # Validate token — only accept opaque connection tokens
    if not token:
        logger.debug("WebSocket connection attempt without token")
        await websocket.close(code=4001, reason="Authentication required")
        return

    user_id: UUID | None = None

    try:
        ws_user_id = await validate_ws_connection_token(token)
        if ws_user_id:
            user_id = UUID(ws_user_id)
        else:
            logger.debug("WebSocket connection with invalid token")
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception as e:
        logger.warning(f"WebSocket token validation error: {e}")
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Accept connection and register
    connection = await manager.connect(websocket, user_id)
    if connection is None:
        logger.warning(f"WebSocket connection rejected (limit) for user: {user_id}")
        return  # Connection rejected (DDoS protection)

    logger.info(f"WebSocket connection established for user: {user_id}")

    # Connection configuration (read from AgentConfigService with hardcoded fallbacks)
    from .ai.config_service import get_agent_config as _get_ws_cfg
    _ws_cfg = _get_ws_cfg()
    RECEIVE_TIMEOUT = _ws_cfg.get_int("websocket.receive_timeout", 45)
    SERVER_PING_INTERVAL = _ws_cfg.get_int("websocket.ping_interval", 30)
    RATE_LIMIT_MESSAGES = _ws_cfg.get_int("websocket.rate_limit_messages", 100)
    RATE_LIMIT_WINDOW = _ws_cfg.get_int("websocket.rate_limit_window", 10)

    # Rate limiting state
    message_timestamps: list[float] = []

    # Token validity tracking
    token_valid = True

    async def server_ping_task():
        """Background task to send periodic pings."""
        nonlocal token_valid
        try:
            while True:
                await asyncio.sleep(SERVER_PING_INTERVAL)
                try:
                    # Send ping
                    await websocket.send_json({"type": "ping", "data": {}})
                except Exception:
                    break  # Connection is dead, exit task
        except asyncio.CancelledError:
            pass

    # Start server-initiated ping task
    ping_task = asyncio.create_task(server_ping_task())

    try:
        while token_valid:
            # Receive with timeout to detect stale connections
            try:
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=RECEIVE_TIMEOUT
                )
            except asyncio.TimeoutError:
                # No message received within timeout - send ping to verify
                try:
                    await websocket.send_json({"type": "ping", "data": {}})
                    raw_message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=10
                    )
                except (asyncio.TimeoutError, Exception):
                    logger.info(f"Connection timeout for user: {user_id}")
                    break

            # Rate limiting check
            current_time = asyncio.get_event_loop().time()
            # Remove timestamps outside the window
            message_timestamps[:] = [t for t in message_timestamps if current_time - t < RATE_LIMIT_WINDOW]

            if len(message_timestamps) >= RATE_LIMIT_MESSAGES:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                await websocket.send_json({
                    "type": "error",
                    "data": {"error": "RATE_LIMIT", "message": "Too many messages, slow down"},
                })
                continue

            message_timestamps.append(current_time)

            # Validate message size
            if len(raw_message) > settings.ws_max_message_size:
                logger.warning(
                    f"Message too large from user {user_id}: "
                    f"{len(raw_message)} bytes (max: {settings.ws_max_message_size})"
                )
                await websocket.send_json({
                    "type": "error",
                    "data": {
                        "error": "MESSAGE_TOO_LARGE",
                        "message": f"Message exceeds maximum size of {settings.ws_max_message_size} bytes",
                    },
                })
                continue

            # Parse JSON
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from user {user_id}")
                await websocket.send_json({
                    "type": "error",
                    "data": {"error": "INVALID_JSON", "message": "Invalid JSON format"},
                })
                continue

            await route_incoming_message(connection, data, room_authorizer=check_room_access)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnect for user: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket exception for user {user_id}: {e}")
    finally:
        # Cancel ping task and cleanup
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
        await manager.disconnect(websocket)

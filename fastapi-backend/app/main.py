"""FastAPI application entry point."""

import asyncio
import json
import logging
import traceback
from uuid import UUID

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from .config import settings

# Configure logging to show errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# STARTUP BANNER - Confirms which backend is running
# ============================================================================
print("\n" + "=" * 60, flush=True)
print("  PM API - WORKTREE 019-knowledge-base", flush=True)
print("  WebSocket logging ENABLED", flush=True)
print("=" * 60 + "\n", flush=True)
from contextlib import asynccontextmanager

from .database import warmup_connection_pool
from .routers import application_members_router, applications_router, auth_router, checklists_router, comments_router, files_router, invitations_router, notifications_router, project_assignments_router, project_members_router, projects_router, tasks_router, users_router
from .websocket import manager, route_incoming_message, check_room_access
from .websocket.presence import presence_manager
from .services.auth_service import decode_access_token
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
    except Exception as e:
        if settings.redis_required:
            logger.error(f"Redis connection failed and REDIS_REQUIRED=true: {e}")
            raise RuntimeError(
                f"Redis is required for multi-worker deployment but connection failed: {e}"
            )
        logger.warning(f"Redis connection failed, running in single-worker mode: {e}")

    logger.info("Starting presence manager...")
    await presence_manager.start()
    logger.info("Presence manager started")

    logger.info("Starting archive service...")
    await archive_service.start()
    logger.info("Archive service started (runs every 12 hours)")

    yield

    # Shutdown
    logger.info("Stopping archive service...")
    await archive_service.stop()
    logger.info("Archive service stopped")

    logger.info("Stopping presence manager...")
    await presence_manager.stop()
    logger.info("Presence manager stopped")

    logger.info("Disconnecting from Redis...")
    await redis_service.disconnect()
    logger.info("Redis disconnected")


# Create FastAPI application
app = FastAPI(
    title="PM API",
    description="Project Management API with Jira-like features and knowledge base",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware - required for Electron app requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(comments_router)
app.include_router(checklists_router)


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "healthy",
        "service": "PM API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    redis_health = await redis_service.health_check()
    return {
        "status": "healthy",
        "database": "pending",  # Will be updated when database is configured
        "minio": "pending",  # Will be updated when MinIO is configured
        "redis": redis_health,
        "websocket": {
            "connections": manager.total_connections,
            "rooms": manager.total_rooms,
        },
        "scheduler": {
            "running": archive_service.is_running,
        },
    }


@app.post("/api/admin/run-archive-jobs")
async def run_archive_jobs_manually():
    """
    Manually trigger archive jobs (admin endpoint).

    Archives:
    - Tasks in Done status for 7+ days
    - Projects where all tasks are archived

    Returns the count of archived items.
    """
    result = await archive_service.run_now()
    return result


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    """
    WebSocket endpoint for real-time collaboration.

    Args:
        websocket: The WebSocket connection
        token: JWT token for authentication (query parameter)

    Authentication is done via query parameter since WebSocket
    doesn't support custom headers in the initial handshake
    from browser clients.

    Usage:
        ws://localhost:8000/ws?token=<jwt_token>
    """
    # Validate token
    if not token:
        logger.debug("WebSocket connection attempt without token")
        await websocket.close(code=4001, reason="Authentication required")
        return

    try:
        token_data = decode_access_token(token)
        if token_data is None or token_data.user_id is None:
            logger.debug("WebSocket connection with invalid token")
            await websocket.close(code=4001, reason="Invalid token")
            return
        user_id = UUID(token_data.user_id)
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

    # Connection configuration
    RECEIVE_TIMEOUT = 45  # 45s timeout for receiving messages
    SERVER_PING_INTERVAL = 30  # Send server ping every 30s
    TOKEN_REVALIDATION_INTERVAL = 1800  # Re-validate token every 30 minutes
    RATE_LIMIT_MESSAGES = 100  # Max messages per window
    RATE_LIMIT_WINDOW = 10  # Window in seconds (100 msg/10s = 10 msg/sec avg)

    # Rate limiting state
    message_timestamps: list[float] = []

    # Token validity tracking
    token_valid = True
    last_token_check = asyncio.get_event_loop().time()

    async def server_ping_task():
        """Background task to send periodic pings and validate token."""
        nonlocal token_valid, last_token_check
        try:
            while True:
                await asyncio.sleep(SERVER_PING_INTERVAL)
                try:
                    # Send ping
                    await websocket.send_json({"type": "ping", "data": {}})

                    # Check if token needs re-validation
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_token_check > TOKEN_REVALIDATION_INTERVAL:
                        # Re-validate token
                        token_data = decode_access_token(token)
                        if token_data is None or token_data.user_id is None:
                            logger.warning(f"Token expired for user {user_id}, closing connection")
                            token_valid = False
                            await websocket.send_json({
                                "type": "error",
                                "data": {"error": "TOKEN_EXPIRED", "message": "Session expired, please re-authenticate"},
                            })
                            await websocket.close(code=4001, reason="Token expired")
                            break
                        last_token_check = current_time

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

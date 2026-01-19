"""FastAPI application entry point."""

import json
import logging
from uuid import UUID

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

logger = logging.getLogger(__name__)
from .routers import application_members_router, applications_router, auth_router, files_router, invitations_router, notes_router, notifications_router, project_assignments_router, project_members_router, projects_router, tasks_router, users_router
from .websocket import manager, route_incoming_message, check_room_access
from .services.auth_service import decode_access_token

# Create FastAPI application
app = FastAPI(
    title="PM API",
    description="Project Management API with Jira-like features and OneNote-style notes",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware - required for Electron app requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_router)
app.include_router(applications_router)
app.include_router(application_members_router)
app.include_router(projects_router)
app.include_router(project_assignments_router)
app.include_router(project_members_router)
app.include_router(tasks_router)
app.include_router(notes_router)
app.include_router(files_router)
app.include_router(notifications_router)
app.include_router(invitations_router)
app.include_router(users_router)


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
    return {
        "status": "healthy",
        "database": "pending",  # Will be updated when database is configured
        "minio": "pending",  # Will be updated when MinIO is configured
        "websocket": {
            "connections": manager.total_connections,
            "rooms": manager.total_rooms,
        },
    }


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
        await websocket.close(code=4001, reason="Authentication required")
        return

    try:
        token_data = decode_access_token(token)
        if token_data is None or token_data.user_id is None:
            await websocket.close(code=4001, reason="Invalid token")
            return
        # Convert user_id to UUID for consistent type handling
        user_id = UUID(token_data.user_id)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Accept connection and register
    connection = await manager.connect(websocket, user_id)
    if connection is None:
        return  # Connection rejected (DDoS protection)

    try:
        while True:
            # Receive raw text first to check size (DoS protection)
            raw_message = await websocket.receive_text()

            # Validate message size before parsing
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

            # Parse JSON after size validation
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
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)

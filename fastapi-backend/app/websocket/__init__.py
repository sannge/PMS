"""WebSocket module for real-time collaboration."""

from .manager import (
    ConnectionManager,
    MessageType,
    WebSocketConnection,
    manager,
)
from .handlers import (
    BroadcastResult,
    UpdateAction,
    get_application_room,
    get_note_room,
    get_project_room,
    get_task_room,
    handle_application_update,
    handle_note_update,
    handle_notification,
    handle_notification_read,
    handle_project_update,
    handle_task_update,
    handle_user_presence,
    route_incoming_message,
)

__all__ = [
    # Manager
    "ConnectionManager",
    "MessageType",
    "WebSocketConnection",
    "manager",
    # Handlers
    "BroadcastResult",
    "UpdateAction",
    "get_application_room",
    "get_note_room",
    "get_project_room",
    "get_task_room",
    "handle_application_update",
    "handle_note_update",
    "handle_notification",
    "handle_notification_read",
    "handle_project_update",
    "handle_task_update",
    "handle_user_presence",
    "route_incoming_message",
]

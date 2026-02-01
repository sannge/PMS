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
    get_project_room,
    get_task_room,
    handle_application_update,
    handle_comment_added,
    handle_comment_deleted,
    handle_comment_updated,
    handle_checklist_created,
    handle_checklist_deleted,
    handle_checklist_item_toggled,
    handle_checklist_updated,
    handle_notification,
    handle_notification_read,
    handle_presence_update,
    handle_project_update,
    handle_task_moved,
    handle_task_update,
    handle_task_viewers,
    handle_typing_indicator,
    handle_user_presence,
    route_incoming_message,
)
from .presence import (
    PresenceManager,
    UserPresence,
    presence_manager,
    PRESENCE_TTL,
    HEARTBEAT_INTERVAL,
)
from .room_auth import check_room_access

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
    "get_project_room",
    "get_task_room",
    "handle_application_update",
    "handle_comment_added",
    "handle_comment_deleted",
    "handle_comment_updated",
    "handle_checklist_created",
    "handle_checklist_deleted",
    "handle_checklist_item_toggled",
    "handle_checklist_updated",
    "handle_notification",
    "handle_notification_read",
    "handle_presence_update",
    "handle_project_update",
    "handle_task_moved",
    "handle_task_update",
    "handle_task_viewers",
    "handle_typing_indicator",
    "handle_user_presence",
    "route_incoming_message",
    # Presence
    "PresenceManager",
    "UserPresence",
    "presence_manager",
    "PRESENCE_TTL",
    "HEARTBEAT_INTERVAL",
    # Room authorization
    "check_room_access",
]

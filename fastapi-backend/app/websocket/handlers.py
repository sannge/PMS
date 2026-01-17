"""WebSocket event handlers for different event types."""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from .manager import ConnectionManager, MessageType, WebSocketConnection, manager

logger = logging.getLogger(__name__)


class UpdateAction(str, Enum):
    """Action type for entity updates."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATUS_CHANGED = "status_changed"
    CONTENT_CHANGED = "content_changed"


@dataclass
class BroadcastResult:
    """Result of a broadcast operation."""

    room_id: str
    recipients: int
    message_type: str
    success: bool


def get_project_room(project_id: UUID | str) -> str:
    """
    Get the room ID for a project.

    Args:
        project_id: The project's UUID

    Returns:
        str: Room ID in format 'project:{uuid}'
    """
    return f"project:{project_id}"


def get_application_room(application_id: UUID | str) -> str:
    """
    Get the room ID for an application.

    Args:
        application_id: The application's UUID

    Returns:
        str: Room ID in format 'application:{uuid}'
    """
    return f"application:{application_id}"


def get_task_room(task_id: UUID | str) -> str:
    """
    Get the room ID for a task (for detailed viewing/editing).

    Args:
        task_id: The task's UUID

    Returns:
        str: Room ID in format 'task:{uuid}'
    """
    return f"task:{task_id}"


def get_note_room(note_id: UUID | str) -> str:
    """
    Get the room ID for a note (for collaborative editing).

    Args:
        note_id: The note's UUID

    Returns:
        str: Room ID in format 'note:{uuid}'
    """
    return f"note:{note_id}"


async def handle_task_update(
    project_id: UUID | str,
    task_id: UUID | str,
    action: UpdateAction,
    task_data: dict[str, Any],
    user_id: Optional[UUID | str] = None,
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle task update events and broadcast to project room.

    Args:
        project_id: The project's UUID
        task_id: The task's UUID
        action: The type of update (created, updated, deleted)
        task_data: The task data to broadcast
        user_id: The user who made the change
        old_status: Previous status (for status_changed events)
        new_status: New status (for status_changed events)
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_project_room(project_id)

    # Determine message type
    message_type_map = {
        UpdateAction.CREATED: MessageType.TASK_CREATED,
        UpdateAction.UPDATED: MessageType.TASK_UPDATED,
        UpdateAction.DELETED: MessageType.TASK_DELETED,
        UpdateAction.STATUS_CHANGED: MessageType.TASK_STATUS_CHANGED,
    }
    message_type = message_type_map.get(action, MessageType.TASK_UPDATED)

    # Build the message payload
    payload: dict[str, Any] = {
        "task_id": str(task_id),
        "project_id": str(project_id),
        "action": action.value,
        "task": task_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if user_id:
        payload["changed_by"] = str(user_id)

    if action == UpdateAction.STATUS_CHANGED and old_status and new_status:
        payload["old_status"] = old_status
        payload["new_status"] = new_status

    message = {
        "type": message_type.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # Also broadcast to task-specific room for detailed view subscribers
    task_room_id = get_task_room(task_id)
    await mgr.broadcast_to_room(task_room_id, message)

    logger.info(
        f"Task {action.value}: task_id={task_id}, "
        f"project_room={room_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=message_type.value,
        success=True,
    )


async def handle_note_update(
    application_id: UUID | str,
    note_id: UUID | str,
    action: UpdateAction,
    note_data: dict[str, Any],
    user_id: Optional[UUID | str] = None,
    content_delta: Optional[dict[str, Any]] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle note update events and broadcast to application room.

    Args:
        application_id: The application's UUID
        note_id: The note's UUID
        action: The type of update (created, updated, deleted, content_changed)
        note_data: The note data to broadcast
        user_id: The user who made the change
        content_delta: Optional delta changes for collaborative editing
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_application_room(application_id)

    # Determine message type
    message_type_map = {
        UpdateAction.CREATED: MessageType.NOTE_CREATED,
        UpdateAction.UPDATED: MessageType.NOTE_UPDATED,
        UpdateAction.DELETED: MessageType.NOTE_DELETED,
        UpdateAction.CONTENT_CHANGED: MessageType.NOTE_CONTENT_CHANGED,
    }
    message_type = message_type_map.get(action, MessageType.NOTE_UPDATED)

    # Build the message payload
    payload: dict[str, Any] = {
        "note_id": str(note_id),
        "application_id": str(application_id),
        "action": action.value,
        "note": note_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if user_id:
        payload["changed_by"] = str(user_id)

    if action == UpdateAction.CONTENT_CHANGED and content_delta:
        payload["content_delta"] = content_delta

    message = {
        "type": message_type.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # Also broadcast to note-specific room for collaborative editors
    note_room_id = get_note_room(note_id)
    await mgr.broadcast_to_room(note_room_id, message)

    logger.info(
        f"Note {action.value}: note_id={note_id}, "
        f"application_room={room_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=message_type.value,
        success=True,
    )


async def handle_project_update(
    application_id: UUID | str,
    project_id: UUID | str,
    action: UpdateAction,
    project_data: dict[str, Any],
    user_id: Optional[UUID | str] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle project update events and broadcast to application room.

    Args:
        application_id: The application's UUID
        project_id: The project's UUID
        action: The type of update (created, updated, deleted)
        project_data: The project data to broadcast
        user_id: The user who made the change
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_application_room(application_id)

    # Determine message type
    message_type_map = {
        UpdateAction.CREATED: MessageType.PROJECT_CREATED,
        UpdateAction.UPDATED: MessageType.PROJECT_UPDATED,
        UpdateAction.DELETED: MessageType.PROJECT_DELETED,
    }
    message_type = message_type_map.get(action, MessageType.PROJECT_UPDATED)

    # Build the message payload
    payload: dict[str, Any] = {
        "project_id": str(project_id),
        "application_id": str(application_id),
        "action": action.value,
        "project": project_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if user_id:
        payload["changed_by"] = str(user_id)

    message = {
        "type": message_type.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # Also broadcast to the project room for users viewing the project
    project_room_id = get_project_room(project_id)
    await mgr.broadcast_to_room(project_room_id, message)

    logger.info(
        f"Project {action.value}: project_id={project_id}, "
        f"application_room={room_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=message_type.value,
        success=True,
    )


async def handle_application_update(
    application_id: UUID | str,
    action: UpdateAction,
    application_data: dict[str, Any],
    user_id: Optional[UUID | str] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle application update events and broadcast to application room.

    Args:
        application_id: The application's UUID
        action: The type of update (created, updated, deleted)
        application_data: The application data to broadcast
        user_id: The user who made the change
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_application_room(application_id)

    # Determine message type
    message_type_map = {
        UpdateAction.CREATED: MessageType.APPLICATION_CREATED,
        UpdateAction.UPDATED: MessageType.APPLICATION_UPDATED,
        UpdateAction.DELETED: MessageType.APPLICATION_DELETED,
    }
    message_type = message_type_map.get(action, MessageType.APPLICATION_UPDATED)

    # Build the message payload
    payload: dict[str, Any] = {
        "application_id": str(application_id),
        "action": action.value,
        "application": application_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if user_id:
        payload["changed_by"] = str(user_id)

    message = {
        "type": message_type.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # For application deleted, we also need to broadcast to all users
    # since the application list might need updating
    if action == UpdateAction.DELETED:
        await mgr.broadcast_to_all(message)

    logger.info(
        f"Application {action.value}: application_id={application_id}, "
        f"recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=message_type.value,
        success=True,
    )


async def handle_user_presence(
    room_id: str,
    user_id: UUID | str,
    action: str,
    metadata: Optional[dict[str, Any]] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle user presence events (join, leave, typing, viewing).

    Args:
        room_id: The room where the presence event occurred
        user_id: The user ID
        action: The action type (joined, left, typing, viewing)
        metadata: Optional metadata (e.g., entity being viewed)
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager

    payload: dict[str, Any] = {
        "room_id": room_id,
        "user_id": str(user_id),
        "action": action,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if metadata:
        payload.update(metadata)

    message = {
        "type": MessageType.USER_PRESENCE.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    logger.debug(
        f"User presence: user_id={user_id}, room={room_id}, "
        f"action={action}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.USER_PRESENCE.value,
        success=True,
    )


async def handle_notification(
    user_id: UUID,
    notification_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> int:
    """
    Send a notification to a specific user across all their connections.

    Args:
        user_id: The user to notify
        notification_data: The notification payload
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        int: Number of connections that received the notification
    """
    mgr = connection_manager or manager

    message = {
        "type": MessageType.NOTIFICATION.value,
        "data": {
            **notification_data,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }

    recipients = await mgr.broadcast_to_user(user_id, message)

    logger.info(
        f"Notification sent: user_id={user_id}, "
        f"type={notification_data.get('notification_type')}, "
        f"recipients={recipients}"
    )

    return recipients


async def handle_notification_read(
    user_id: UUID,
    notification_id: UUID | str,
    connection_manager: Optional[ConnectionManager] = None,
) -> int:
    """
    Broadcast notification read status to all user's connections.

    Args:
        user_id: The user who read the notification
        notification_id: The notification that was read
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        int: Number of connections that received the update
    """
    mgr = connection_manager or manager

    message = {
        "type": MessageType.NOTIFICATION_READ.value,
        "data": {
            "notification_id": str(notification_id),
            "user_id": str(user_id),
            "timestamp": datetime.utcnow().isoformat(),
        },
    }

    recipients = await mgr.broadcast_to_user(user_id, message)

    logger.debug(
        f"Notification read: user_id={user_id}, "
        f"notification_id={notification_id}, recipients={recipients}"
    )

    return recipients


async def route_incoming_message(
    connection: WebSocketConnection,
    data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> None:
    """
    Route incoming WebSocket messages to appropriate handlers.

    This extends the base manager's handle_message with additional
    application-specific message handling.

    Args:
        connection: The connection that sent the message
        data: The message data
        connection_manager: Optional custom manager (defaults to global)
    """
    mgr = connection_manager or manager
    message_type = data.get("type")

    # First, let the manager handle core message types
    await mgr.handle_message(connection, data)

    # Handle additional application-specific messages
    if message_type == "task_update_request":
        # Client requesting to broadcast a task update
        project_id = data.get("data", {}).get("project_id")
        task_id = data.get("data", {}).get("task_id")
        task_data = data.get("data", {}).get("task")
        action_str = data.get("data", {}).get("action", "updated")

        if project_id and task_id and task_data:
            try:
                action = UpdateAction(action_str)
                await handle_task_update(
                    project_id=project_id,
                    task_id=task_id,
                    action=action,
                    task_data=task_data,
                    user_id=connection.user_id,
                    connection_manager=mgr,
                )
            except ValueError:
                logger.warning(f"Invalid action: {action_str}")

    elif message_type == "note_update_request":
        # Client requesting to broadcast a note update
        application_id = data.get("data", {}).get("application_id")
        note_id = data.get("data", {}).get("note_id")
        note_data = data.get("data", {}).get("note")
        action_str = data.get("data", {}).get("action", "updated")
        content_delta = data.get("data", {}).get("content_delta")

        if application_id and note_id and note_data:
            try:
                action = UpdateAction(action_str)
                await handle_note_update(
                    application_id=application_id,
                    note_id=note_id,
                    action=action,
                    note_data=note_data,
                    user_id=connection.user_id,
                    content_delta=content_delta,
                    connection_manager=mgr,
                )
            except ValueError:
                logger.warning(f"Invalid action: {action_str}")


# Export all handlers and utilities
__all__ = [
    "UpdateAction",
    "BroadcastResult",
    "get_project_room",
    "get_application_room",
    "get_task_room",
    "get_note_room",
    "handle_task_update",
    "handle_note_update",
    "handle_project_update",
    "handle_application_update",
    "handle_user_presence",
    "handle_notification",
    "handle_notification_read",
    "route_incoming_message",
]

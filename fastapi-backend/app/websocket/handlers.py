"""WebSocket event handlers for different event types."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from .manager import ConnectionManager, MessageType, WebSocketConnection, manager

logger = logging.getLogger(__name__)


async def broadcast_to_target_users(
    mgr: ConnectionManager,
    room_id: str,
    message: dict[str, Any],
    target_user_ids: list[UUID],
) -> int:
    """
    Broadcast efficiently: room + specific users not in room.

    Strategy for 5000+ concurrent users:
    1. Broadcast to room (covers users actively viewing the page)
    2. Send direct notifications only to specific target users NOT in room
    3. All operations run in parallel

    This is O(1) for room broadcast + O(k) parallel for k target users,
    where k is typically 1-2 (the affected user + action performer).

    Args:
        mgr: The connection manager
        room_id: The room to broadcast to
        message: The message to send
        target_user_ids: Specific users who MUST receive this (e.g., affected user)

    Returns:
        int: Total number of successful sends
    """
    # Get users currently in the room (O(1) set lookup prep)
    users_in_room = set(mgr.get_room_users(room_id))

    # Find target users NOT already in room
    users_needing_direct = [
        uid for uid in target_user_ids
        if uid not in users_in_room
    ]

    # Run room broadcast and direct sends in parallel
    tasks = [mgr.broadcast_to_room(room_id, message)]
    tasks.extend(
        mgr.broadcast_to_user(uid, message)
        for uid in users_needing_direct
    )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    return sum(r for r in results if isinstance(r, int))


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


async def handle_project_status_changed(
    application_id: UUID | str,
    project_id: UUID | str,
    project_data: dict[str, Any],
    old_status: str,
    new_status: str,
    user_id: Optional[UUID | str] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle project status change events and broadcast to application and project rooms.

    This is a specialized handler for project status transitions that includes
    both old and new status information for UI state management.

    Args:
        application_id: The application's UUID
        project_id: The project's UUID
        project_data: The project data to broadcast
        old_status: The previous project status
        new_status: The new project status
        user_id: The user who made the change
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_application_room(application_id)

    # Build the message payload with status change details
    payload: dict[str, Any] = {
        "project_id": str(project_id),
        "application_id": str(application_id),
        "action": UpdateAction.STATUS_CHANGED.value,
        "project": project_data,
        "old_status": old_status,
        "new_status": new_status,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if user_id:
        payload["changed_by"] = str(user_id)

    message = {
        "type": MessageType.PROJECT_STATUS_CHANGED.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # Also broadcast to the project room for users viewing the project
    project_room_id = get_project_room(project_id)
    await mgr.broadcast_to_room(project_room_id, message)

    logger.info(
        f"Project status changed: project_id={project_id}, "
        f"{old_status} -> {new_status}, "
        f"application_room={room_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.PROJECT_STATUS_CHANGED.value,
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

    # Note: We intentionally do NOT broadcast_to_all for deleted applications
    # as that would leak application information to unauthorized users.
    # Users viewing the application get notified via room broadcast.
    # Users with the application in their list will discover the deletion
    # when they next fetch/interact with it (lazy invalidation).

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
    room_authorizer: Optional[Any] = None,
) -> None:
    """
    Route incoming WebSocket messages to appropriate handlers.

    This extends the base manager's handle_message with additional
    application-specific message handling.

    Args:
        connection: The connection that sent the message
        data: The message data
        connection_manager: Optional custom manager (defaults to global)
        room_authorizer: Optional callable(user_id, room_id) -> bool for room access check
    """
    mgr = connection_manager or manager
    message_type = data.get("type")

    logger.debug(f"Routing message: user={connection.user_id}, type={message_type}")

    # Intercept JOIN_ROOM to enforce authorization
    if message_type == MessageType.JOIN_ROOM.value or message_type == "join_room":
        room_id = data.get("data", {}).get("room_id")
        if room_id and room_authorizer:
            is_authorized = await room_authorizer(connection.user_id, room_id)
            if not is_authorized:
                logger.warning(f"Room access denied: user={connection.user_id}, room={room_id}")
                await mgr.send_personal(
                    connection,
                    {
                        "type": MessageType.ERROR.value,
                        "data": {
                            "error": "UNAUTHORIZED",
                            "message": f"Access denied to room: {room_id}",
                        },
                    },
                )
                return  # Don't process this message further

    # Let the manager handle core message types
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


async def handle_invitation_notification(
    user_id: UUID,
    invitation_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> int:
    """
    Send an invitation notification to a specific user.

    This is called when a user receives a new invitation to join an application.

    Args:
        user_id: The user to notify (the invitee)
        invitation_data: The invitation payload containing:
            - invitation_id: UUID of the invitation
            - application_id: UUID of the application
            - application_name: Name of the application
            - inviter_id: UUID of the user who sent the invitation
            - inviter_name: Name of the inviter
            - role: The offered role (owner, editor, viewer)
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        int: Number of connections that received the notification
    """
    mgr = connection_manager or manager

    message = {
        "type": MessageType.INVITATION_RECEIVED.value,
        "data": {
            **invitation_data,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }

    recipients = await mgr.broadcast_to_user(user_id, message)

    logger.info(
        f"Invitation notification sent: user_id={user_id}, "
        f"invitation_id={invitation_data.get('invitation_id')}, "
        f"recipients={recipients}"
    )

    return recipients


async def handle_invitation_response(
    inviter_id: UUID,
    application_id: UUID | str,
    response_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> int:
    """
    Notify the inviter when an invitation is accepted or rejected.

    This is called when an invitee responds to an invitation.

    Args:
        inviter_id: The user to notify (the original inviter)
        application_id: The application's UUID
        response_data: The response payload containing:
            - invitation_id: UUID of the invitation
            - invitee_id: UUID of the user who responded
            - invitee_name: Name of the responder
            - status: The response (accepted, rejected)
            - role: The role that was offered
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        int: Number of connections that received the notification
    """
    mgr = connection_manager or manager

    message = {
        "type": MessageType.INVITATION_RESPONSE.value,
        "data": {
            "application_id": str(application_id),
            **response_data,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }

    # Notify the inviter
    recipients = await mgr.broadcast_to_user(inviter_id, message)

    # Also broadcast to the application room for other members
    room_id = get_application_room(application_id)
    await mgr.broadcast_to_room(room_id, message)

    logger.info(
        f"Invitation response sent: inviter_id={inviter_id}, "
        f"status={response_data.get('status')}, "
        f"recipients={recipients}"
    )

    return recipients


async def handle_member_added(
    application_id: UUID | str,
    member_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast when a new member is added to an application.

    Optimized for 5000+ concurrent users:
    - Room broadcast: O(1) for users viewing the application
    - Direct notification: Only to new member + inviter (2 users max)
    - No DB query for all members needed
    - All sends run in parallel

    Args:
        application_id: The application's UUID
        member_data: The member payload containing:
            - user_id: UUID of the new member
            - user_name: Name of the new member
            - user_email: Email of the new member
            - role: The member's role
            - is_manager: Whether the member has manager privileges
            - added_by: UUID of who added the member
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_application_room(application_id)

    payload: dict[str, Any] = {
        "message_id": str(uuid4()),
        "application_id": str(application_id),
        **member_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    message = {
        "type": MessageType.MEMBER_ADDED.value,
        "data": payload,
    }

    # Only notify: new member + person who added them
    # Other members will see update when they view the page (room broadcast covers that)
    target_users: list[UUID] = []

    new_user_id = member_data.get("user_id")
    if new_user_id:
        try:
            target_users.append(
                UUID(new_user_id) if isinstance(new_user_id, str) else new_user_id
            )
        except (ValueError, TypeError):
            pass

    added_by = member_data.get("added_by")
    if added_by:
        try:
            added_by_uuid = UUID(added_by) if isinstance(added_by, str) else added_by
            if added_by_uuid not in target_users:
                target_users.append(added_by_uuid)
        except (ValueError, TypeError):
            pass

    recipients = await broadcast_to_target_users(mgr, room_id, message, target_users)

    logger.debug(
        f"member_added: app={application_id}, user={new_user_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.MEMBER_ADDED.value,
        success=True,
    )


async def handle_member_removed(
    application_id: UUID | str,
    removed_user_id: UUID,
    member_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast when a member is removed from an application.

    Optimized for scale:
    - Room broadcast covers members viewing the page
    - Direct notification only to removed user + remover

    Args:
        application_id: The application's UUID
        removed_user_id: The UUID of the removed user
        member_data: The removal payload
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_application_room(application_id)

    payload: dict[str, Any] = {
        "message_id": str(uuid4()),
        "application_id": str(application_id),
        **member_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    message = {
        "type": MessageType.MEMBER_REMOVED.value,
        "data": payload,
    }

    # Target: removed user + person who removed them
    target_users: list[UUID] = [removed_user_id]

    removed_by = member_data.get("removed_by")
    if removed_by:
        try:
            removed_by_uuid = UUID(removed_by) if isinstance(removed_by, str) else removed_by
            if removed_by_uuid != removed_user_id:
                target_users.append(removed_by_uuid)
        except (ValueError, TypeError):
            pass

    recipients = await broadcast_to_target_users(mgr, room_id, message, target_users)

    logger.debug(
        f"member_removed: app={application_id}, user={removed_user_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.MEMBER_REMOVED.value,
        success=True,
    )


async def handle_role_updated(
    application_id: UUID | str,
    user_id: UUID,
    role_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast when a member's role is updated.

    Optimized for scale:
    - Room broadcast covers members viewing the page
    - Direct notification only to affected user + updater

    Args:
        application_id: The application's UUID
        user_id: The UUID of the user whose role changed
        role_data: The role update payload
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_application_room(application_id)

    payload: dict[str, Any] = {
        "message_id": str(uuid4()),
        "application_id": str(application_id),
        **role_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    message = {
        "type": MessageType.ROLE_UPDATED.value,
        "data": payload,
    }

    # Target: affected user + person who updated
    target_users: list[UUID] = [user_id]

    updated_by = role_data.get("updated_by")
    if updated_by:
        try:
            updated_by_uuid = UUID(updated_by) if isinstance(updated_by, str) else updated_by
            if updated_by_uuid != user_id:
                target_users.append(updated_by_uuid)
        except (ValueError, TypeError):
            pass

    recipients = await broadcast_to_target_users(mgr, room_id, message, target_users)

    logger.debug(
        f"role_updated: app={application_id}, user={user_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.ROLE_UPDATED.value,
        success=True,
    )


# =============================================================================
# Project Member Event Handlers
# =============================================================================


async def handle_project_member_added(
    project_id: UUID | str,
    member_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast when a member is added to a project.

    Args:
        project_id: The project's UUID
        member_data: The member payload containing:
            - user_id: UUID of the new member
            - user_name: Name of the new member
            - role: The member's project role (admin/member)
            - added_by: UUID of who added the member
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_project_room(project_id)

    payload: dict[str, Any] = {
        "message_id": str(uuid4()),
        "project_id": str(project_id),
        **member_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    message = {
        "type": MessageType.PROJECT_MEMBER_ADDED.value,
        "data": payload,
    }

    # Target: new member + person who added them
    target_users: list[UUID] = []

    new_user_id = member_data.get("user_id")
    if new_user_id:
        try:
            target_users.append(
                UUID(new_user_id) if isinstance(new_user_id, str) else new_user_id
            )
        except (ValueError, TypeError):
            pass

    added_by = member_data.get("added_by")
    if added_by:
        try:
            added_by_uuid = UUID(added_by) if isinstance(added_by, str) else added_by
            if added_by_uuid not in target_users:
                target_users.append(added_by_uuid)
        except (ValueError, TypeError):
            pass

    recipients = await broadcast_to_target_users(mgr, room_id, message, target_users)

    logger.debug(
        f"project_member_added: project={project_id}, user={new_user_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.PROJECT_MEMBER_ADDED.value,
        success=True,
    )


async def handle_project_member_removed(
    project_id: UUID | str,
    removed_user_id: UUID,
    member_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast when a member is removed from a project.

    Args:
        project_id: The project's UUID
        removed_user_id: The UUID of the removed user
        member_data: The removal payload containing:
            - removed_by: UUID of who removed the member
            - tasks_unassigned: Number of tasks that were unassigned
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_project_room(project_id)

    payload: dict[str, Any] = {
        "message_id": str(uuid4()),
        "project_id": str(project_id),
        "user_id": str(removed_user_id),
        **member_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    message = {
        "type": MessageType.PROJECT_MEMBER_REMOVED.value,
        "data": payload,
    }

    # Target: removed user + person who removed them
    target_users: list[UUID] = [removed_user_id]

    removed_by = member_data.get("removed_by")
    if removed_by:
        try:
            removed_by_uuid = UUID(removed_by) if isinstance(removed_by, str) else removed_by
            if removed_by_uuid != removed_user_id:
                target_users.append(removed_by_uuid)
        except (ValueError, TypeError):
            pass

    recipients = await broadcast_to_target_users(mgr, room_id, message, target_users)

    logger.debug(
        f"project_member_removed: project={project_id}, user={removed_user_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.PROJECT_MEMBER_REMOVED.value,
        success=True,
    )


async def handle_project_member_role_changed(
    project_id: UUID | str,
    user_id: UUID,
    role_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast when a project member's role is changed.

    Args:
        project_id: The project's UUID
        user_id: The UUID of the user whose role changed
        role_data: The role update payload containing:
            - old_role: Previous role (admin/member)
            - new_role: New role (admin/member)
            - changed_by: UUID of who changed the role
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_project_room(project_id)

    payload: dict[str, Any] = {
        "message_id": str(uuid4()),
        "project_id": str(project_id),
        "user_id": str(user_id),
        **role_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    message = {
        "type": MessageType.PROJECT_ROLE_CHANGED.value,
        "data": payload,
    }

    # Target: affected user + person who changed the role
    target_users: list[UUID] = [user_id]

    changed_by = role_data.get("changed_by")
    if changed_by:
        try:
            changed_by_uuid = UUID(changed_by) if isinstance(changed_by, str) else changed_by
            if changed_by_uuid != user_id:
                target_users.append(changed_by_uuid)
        except (ValueError, TypeError):
            pass

    recipients = await broadcast_to_target_users(mgr, room_id, message, target_users)

    logger.debug(
        f"project_member_role_changed: project={project_id}, user={user_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.PROJECT_ROLE_CHANGED.value,
        success=True,
    )


# =============================================================================
# Comment Event Handlers
# =============================================================================


async def handle_comment_added(
    task_id: UUID | str,
    comment_data: dict[str, Any],
    mentioned_user_ids: list[UUID] | None = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle comment_added event and broadcast to task room.

    Args:
        task_id: The task's UUID
        comment_data: The comment payload
        mentioned_user_ids: List of mentioned users to notify directly
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload: dict[str, Any] = {
        "t": "ca",  # Minified type for efficiency
        "d": {
            "id": str(comment_data.get("id", "")),
            "tid": str(task_id),
            "a": str(comment_data.get("author_id", "")),
            "an": comment_data.get("author_name", ""),
            "b": (comment_data.get("body_text", "") or "")[:100],  # Preview
            "m": [str(uid) for uid in (mentioned_user_ids or [])],
            "ts": int(datetime.utcnow().timestamp()),
        },
    }

    message = {
        "type": MessageType.COMMENT_ADDED.value,
        "data": payload,
    }

    # Broadcast to task room + notify mentioned users directly
    target_users = mentioned_user_ids or []
    recipients = await broadcast_to_target_users(mgr, room_id, message, target_users)

    logger.info(
        f"Comment added: task_id={task_id}, comment_id={comment_data.get('id')}, "
        f"mentions={len(target_users)}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.COMMENT_ADDED.value,
        success=True,
    )


async def handle_comment_updated(
    task_id: UUID | str,
    comment_id: UUID | str,
    comment_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle comment_updated event and broadcast to task room.

    Args:
        task_id: The task's UUID
        comment_id: The comment's UUID
        comment_data: The updated comment payload
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "cu",
        "d": {
            "id": str(comment_id),
            "b": (comment_data.get("body_text", "") or "")[:100],
            "ts": int(datetime.utcnow().timestamp()),
        },
    }

    message = {
        "type": MessageType.COMMENT_UPDATED.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    logger.debug(f"Comment updated: task_id={task_id}, comment_id={comment_id}")

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.COMMENT_UPDATED.value,
        success=True,
    )


async def handle_comment_deleted(
    task_id: UUID | str,
    comment_id: UUID | str,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle comment_deleted event and broadcast to task room.

    Args:
        task_id: The task's UUID
        comment_id: The comment's UUID
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "cd",
        "d": {
            "id": str(comment_id),
            "ts": int(datetime.utcnow().timestamp()),
        },
    }

    message = {
        "type": MessageType.COMMENT_DELETED.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    logger.debug(f"Comment deleted: task_id={task_id}, comment_id={comment_id}")

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.COMMENT_DELETED.value,
        success=True,
    )


# =============================================================================
# Checklist Event Handlers
# =============================================================================


async def handle_checklist_created(
    task_id: UUID | str,
    checklist_data: dict[str, Any],
    user_id: UUID | str,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle checklist_created event and broadcast to task room.

    Args:
        task_id: The task's UUID
        checklist_data: The checklist payload
        user_id: The user who created the checklist
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "clc",
        "d": {
            "id": str(checklist_data.get("id", "")),
            "tid": str(task_id),
            "title": checklist_data.get("title", ""),
            "by": str(user_id),
            "ts": int(datetime.utcnow().timestamp()),
        },
    }

    message = {
        "type": MessageType.CHECKLIST_CREATED.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # Also broadcast to project room for task card updates
    project_id = checklist_data.get("project_id")
    if project_id:
        project_room = get_project_room(project_id)
        await mgr.broadcast_to_room(project_room, message)

    logger.debug(f"Checklist created: task_id={task_id}, checklist_id={checklist_data.get('id')}")

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.CHECKLIST_CREATED.value,
        success=True,
    )


async def handle_checklist_updated(
    task_id: UUID | str,
    checklist_id: UUID | str,
    checklist_data: dict[str, Any],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle checklist_updated event and broadcast to task room.

    Args:
        task_id: The task's UUID
        checklist_id: The checklist's UUID
        checklist_data: The updated checklist payload
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "clu",
        "d": {
            "id": str(checklist_id),
            "title": checklist_data.get("title", ""),
            "ts": int(datetime.utcnow().timestamp()),
        },
    }

    message = {
        "type": MessageType.CHECKLIST_UPDATED.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    logger.debug(f"Checklist updated: task_id={task_id}, checklist_id={checklist_id}")

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.CHECKLIST_UPDATED.value,
        success=True,
    )


async def handle_checklist_deleted(
    task_id: UUID | str,
    checklist_id: UUID | str,
    project_id: UUID | str | None = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle checklist_deleted event and broadcast to task and project rooms.

    Args:
        task_id: The task's UUID
        checklist_id: The checklist's UUID
        project_id: Optional project ID for task card update
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "cld",
        "d": {
            "id": str(checklist_id),
            "ts": int(datetime.utcnow().timestamp()),
        },
    }

    message = {
        "type": MessageType.CHECKLIST_DELETED.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # Also broadcast to project room for task card updates
    if project_id:
        project_room = get_project_room(project_id)
        await mgr.broadcast_to_room(project_room, message)

    logger.debug(f"Checklist deleted: task_id={task_id}, checklist_id={checklist_id}")

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.CHECKLIST_DELETED.value,
        success=True,
    )


async def handle_checklist_item_toggled(
    task_id: UUID | str,
    checklist_id: UUID | str,
    item_id: UUID | str,
    is_done: bool,
    user_id: UUID | str,
    project_id: UUID | str | None = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle checklist_item_toggled event and broadcast to task and project rooms.

    Args:
        task_id: The task's UUID
        checklist_id: The checklist's UUID
        item_id: The item's UUID
        is_done: New completion status
        user_id: The user who toggled the item
        project_id: Optional project ID for task card update
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "cit",
        "d": {
            "id": str(item_id),
            "clid": str(checklist_id),
            "done": is_done,
            "by": str(user_id),
            "ts": int(datetime.utcnow().timestamp()),
        },
    }

    message = {
        "type": MessageType.CHECKLIST_ITEM_TOGGLED.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    # Also broadcast to project room for task card progress updates
    if project_id:
        project_room = get_project_room(project_id)
        await mgr.broadcast_to_room(project_room, message)

    logger.debug(
        f"Checklist item toggled: task_id={task_id}, item_id={item_id}, done={is_done}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.CHECKLIST_ITEM_TOGGLED.value,
        success=True,
    )


# =============================================================================
# Presence Event Handlers (Ephemeral)
# =============================================================================


async def handle_presence_update(
    room_id: str,
    users: list[dict[str, Any]],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast presence update with list of users in room.

    Args:
        room_id: The room (project or task)
        users: List of user presence info (id, name, avatar, idle)
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager

    payload = {
        "t": "pr",
        "d": {
            "users": users,
        },
    }

    message = {
        "type": MessageType.PRESENCE_UPDATE.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.PRESENCE_UPDATE.value,
        success=True,
    )


async def handle_typing_indicator(
    task_id: UUID | str,
    user_id: UUID | str,
    user_name: str,
    ttl_ms: int = 3000,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast typing indicator for comment composition.

    Args:
        task_id: The task's UUID
        user_id: The typing user's UUID
        user_name: The typing user's name
        ttl_ms: Time-to-live in milliseconds (default 3000)
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "ty",
        "d": {
            "uid": str(user_id),
            "un": user_name,
            "ttl": ttl_ms,
        },
    }

    message = {
        "type": MessageType.USER_TYPING.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.USER_TYPING.value,
        success=True,
    )


async def handle_task_viewers(
    task_id: UUID | str,
    viewer_ids: list[UUID],
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Broadcast list of users currently viewing a task.

    Args:
        task_id: The task's UUID
        viewer_ids: List of user IDs viewing the task
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_task_room(task_id)

    payload = {
        "t": "tv",
        "d": {
            "tid": str(task_id),
            "users": [str(uid) for uid in viewer_ids],
        },
    }

    message = {
        "type": MessageType.TASK_VIEWERS.value,
        "data": payload,
    }

    recipients = await mgr.broadcast_to_room(room_id, message)

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.TASK_VIEWERS.value,
        success=True,
    )


async def handle_task_moved(
    project_id: UUID | str,
    task_id: UUID | str,
    old_status_id: UUID | str,
    new_status_id: UUID | str,
    new_rank: str,
    user_id: UUID | str,
    task_data: Optional[dict] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> BroadcastResult:
    """
    Handle task_moved event for Kanban drag-and-drop.

    Args:
        project_id: The project's UUID
        task_id: The task's UUID
        old_status_id: Previous status ID
        new_status_id: New status ID
        new_rank: New Lexorank position
        user_id: User who moved the task
        task_data: Optional serialized task data to include
        connection_manager: Optional custom manager (defaults to global)

    Returns:
        BroadcastResult: Result of the broadcast operation
    """
    mgr = connection_manager or manager
    room_id = get_project_room(project_id)

    # Use expanded field names to match frontend expectations
    payload = {
        "task_id": str(task_id),
        "project_id": str(project_id),
        "old_status_id": str(old_status_id),
        "new_status_id": str(new_status_id),
        "old_rank": None,
        "new_rank": new_rank,
        "task": task_data or {},
        "timestamp": datetime.utcnow().isoformat(),
        "changed_by": str(user_id),
    }

    message = {
        "type": MessageType.TASK_MOVED.value,
        "data": payload,
    }

    # Log room membership before broadcast
    room_connections = mgr._rooms.get(room_id, set())
    room_user_ids = [str(conn.user_id) for conn in room_connections]
    logger.info(
        f"Broadcasting TASK_MOVED: task_id={task_id}, room_id={room_id}, "
        f"old_status={old_status_id} -> new_status={new_status_id}, "
        f"room_members={room_user_ids}, triggered_by={user_id}"
    )

    recipients = await mgr.broadcast_to_room(room_id, message)

    logger.info(
        f"Task moved broadcast complete: task_id={task_id}, "
        f"project_room={room_id}, recipients={recipients}"
    )

    return BroadcastResult(
        room_id=room_id,
        recipients=recipients,
        message_type=MessageType.TASK_MOVED.value,
        success=True,
    )


# Export all handlers and utilities
__all__ = [
    "UpdateAction",
    "BroadcastResult",
    "get_project_room",
    "get_application_room",
    "get_task_room",
    "get_note_room",
    "handle_task_update",
    "handle_task_moved",
    "handle_note_update",
    "handle_project_update",
    "handle_project_status_changed",
    "handle_application_update",
    "handle_user_presence",
    "handle_notification",
    "handle_notification_read",
    "handle_invitation_notification",
    "handle_invitation_response",
    "handle_member_added",
    "handle_member_removed",
    "handle_role_updated",
    "route_incoming_message",
    # Project member handlers
    "handle_project_member_added",
    "handle_project_member_removed",
    "handle_project_member_role_changed",
    # Comment handlers
    "handle_comment_added",
    "handle_comment_updated",
    "handle_comment_deleted",
    # Checklist handlers
    "handle_checklist_created",
    "handle_checklist_updated",
    "handle_checklist_deleted",
    "handle_checklist_item_toggled",
    # Presence handlers
    "handle_presence_update",
    "handle_typing_indicator",
    "handle_task_viewers",
]

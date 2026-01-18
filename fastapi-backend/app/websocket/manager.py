"""WebSocket connection manager with room-based support."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """WebSocket message types."""

    # Connection events
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"

    # Room events
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    ROOM_JOINED = "room_joined"
    ROOM_LEFT = "room_left"

    # Entity update events
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_STATUS_CHANGED = "task_status_changed"

    NOTE_CREATED = "note_created"
    NOTE_UPDATED = "note_updated"
    NOTE_DELETED = "note_deleted"
    NOTE_CONTENT_CHANGED = "note_content_changed"

    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_DELETED = "project_deleted"

    APPLICATION_CREATED = "application_created"
    APPLICATION_UPDATED = "application_updated"
    APPLICATION_DELETED = "application_deleted"

    # Collaboration events
    USER_PRESENCE = "user_presence"
    USER_TYPING = "user_typing"
    USER_VIEWING = "user_viewing"

    # Notification events
    NOTIFICATION = "notification"
    NOTIFICATION_READ = "notification_read"

    # Invitation/member events
    INVITATION_RECEIVED = "invitation_received"
    INVITATION_RESPONSE = "invitation_response"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    ROLE_UPDATED = "role_updated"

    # Ping/pong for keepalive
    PING = "ping"
    PONG = "pong"


@dataclass
class WebSocketConnection:
    """Represents a WebSocket connection with user context."""

    websocket: WebSocket
    user_id: UUID
    connected_at: datetime = field(default_factory=datetime.utcnow)
    rooms: set[str] = field(default_factory=set)

    def __hash__(self) -> int:
        """Hash by websocket id for set operations."""
        return id(self.websocket)

    def __eq__(self, other: object) -> bool:
        """Equality check by websocket id."""
        if not isinstance(other, WebSocketConnection):
            return False
        return id(self.websocket) == id(other.websocket)


class ConnectionManager:
    """
    WebSocket connection manager with room-based support.

    Features:
    - Room-based connection grouping for targeted broadcasts
    - User tracking per room
    - Graceful disconnect handling
    - Message type validation
    - Keepalive ping/pong support
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        # Map of room_id -> set of connections
        self._rooms: dict[str, set[WebSocketConnection]] = {}
        # Map of websocket -> connection object
        self._connections: dict[WebSocket, WebSocketConnection] = {}
        # Map of user_id -> set of connections (for user-targeted messages)
        self._user_connections: dict[UUID, set[WebSocketConnection]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    @property
    def total_connections(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)

    @property
    def total_rooms(self) -> int:
        """Get total number of active rooms."""
        return len(self._rooms)

    def get_room_count(self, room_id: str) -> int:
        """Get number of connections in a room."""
        return len(self._rooms.get(room_id, set()))

    def get_user_connections_count(self, user_id: UUID) -> int:
        """Get number of connections for a user."""
        return len(self._user_connections.get(user_id, set()))

    async def connect(
        self,
        websocket: WebSocket,
        user_id: UUID,
        initial_rooms: Optional[list[str]] = None,
    ) -> WebSocketConnection:
        """
        Accept a WebSocket connection and register it.

        Args:
            websocket: The WebSocket instance
            user_id: The authenticated user's ID
            initial_rooms: Optional list of rooms to join immediately

        Returns:
            WebSocketConnection: The connection wrapper object
        """
        await websocket.accept()

        connection = WebSocketConnection(
            websocket=websocket,
            user_id=user_id,
        )

        async with self._lock:
            self._connections[websocket] = connection

            # Track by user
            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()
            self._user_connections[user_id].add(connection)

        # Join initial rooms if specified
        if initial_rooms:
            for room_id in initial_rooms:
                await self.join_room(connection, room_id)

        logger.info(
            f"WebSocket connected: user={user_id}, "
            f"total_connections={self.total_connections}"
        )

        # Send connection confirmation
        await self.send_personal(
            connection,
            {
                "type": MessageType.CONNECTED,
                "data": {
                    "user_id": str(user_id),
                    "connected_at": connection.connected_at.isoformat(),
                    "rooms": list(connection.rooms),
                },
            },
        )

        return connection

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Disconnect a WebSocket and clean up all associated resources.

        Args:
            websocket: The WebSocket instance to disconnect
        """
        async with self._lock:
            connection = self._connections.pop(websocket, None)

            if connection is None:
                return

            # Remove from user tracking
            if connection.user_id in self._user_connections:
                self._user_connections[connection.user_id].discard(connection)
                if not self._user_connections[connection.user_id]:
                    del self._user_connections[connection.user_id]

            # Remove from all rooms
            for room_id in list(connection.rooms):
                if room_id in self._rooms:
                    self._rooms[room_id].discard(connection)
                    if not self._rooms[room_id]:
                        del self._rooms[room_id]

        logger.info(
            f"WebSocket disconnected: user={connection.user_id}, "
            f"total_connections={self.total_connections}"
        )

    async def join_room(
        self,
        connection: WebSocketConnection,
        room_id: str,
        notify_others: bool = True,
    ) -> None:
        """
        Add a connection to a room.

        Args:
            connection: The connection to add
            room_id: The room identifier
            notify_others: Whether to notify other room members
        """
        async with self._lock:
            if room_id not in self._rooms:
                self._rooms[room_id] = set()
            self._rooms[room_id].add(connection)
            connection.rooms.add(room_id)

        logger.debug(
            f"User {connection.user_id} joined room {room_id} "
            f"(room_size={self.get_room_count(room_id)})"
        )

        # Confirm to the joining user
        await self.send_personal(
            connection,
            {
                "type": MessageType.ROOM_JOINED,
                "data": {
                    "room_id": room_id,
                    "user_count": self.get_room_count(room_id),
                },
            },
        )

        # Notify other room members
        if notify_others:
            await self.broadcast_to_room(
                room_id,
                {
                    "type": MessageType.USER_PRESENCE,
                    "data": {
                        "room_id": room_id,
                        "user_id": str(connection.user_id),
                        "action": "joined",
                        "user_count": self.get_room_count(room_id),
                    },
                },
                exclude=connection,
            )

    async def leave_room(
        self,
        connection: WebSocketConnection,
        room_id: str,
        notify_others: bool = True,
    ) -> None:
        """
        Remove a connection from a room.

        Args:
            connection: The connection to remove
            room_id: The room identifier
            notify_others: Whether to notify other room members
        """
        async with self._lock:
            if room_id in self._rooms:
                self._rooms[room_id].discard(connection)
                if not self._rooms[room_id]:
                    del self._rooms[room_id]
            connection.rooms.discard(room_id)

        logger.debug(
            f"User {connection.user_id} left room {room_id} "
            f"(room_size={self.get_room_count(room_id)})"
        )

        # Confirm to the leaving user
        await self.send_personal(
            connection,
            {
                "type": MessageType.ROOM_LEFT,
                "data": {"room_id": room_id},
            },
        )

        # Notify other room members
        if notify_others:
            await self.broadcast_to_room(
                room_id,
                {
                    "type": MessageType.USER_PRESENCE,
                    "data": {
                        "room_id": room_id,
                        "user_id": str(connection.user_id),
                        "action": "left",
                        "user_count": self.get_room_count(room_id),
                    },
                },
            )

    async def send_personal(
        self,
        connection: WebSocketConnection,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a message to a specific connection.

        Args:
            connection: The target connection
            message: The message to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            await connection.websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(
                f"Failed to send message to user {connection.user_id}: {e}"
            )
            return False

    async def broadcast_to_room(
        self,
        room_id: str,
        message: dict[str, Any],
        exclude: Optional[WebSocketConnection] = None,
    ) -> int:
        """
        Broadcast a message to all connections in a room.

        Args:
            room_id: The room to broadcast to
            message: The message to send
            exclude: Optional connection to exclude from broadcast

        Returns:
            int: Number of successful sends
        """
        connections = self._rooms.get(room_id, set()).copy()

        if exclude:
            connections.discard(exclude)

        if not connections:
            return 0

        # Send to all connections concurrently
        tasks = [
            self.send_personal(conn, message)
            for conn in connections
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        logger.debug(
            f"Broadcast to room {room_id}: "
            f"{success_count}/{len(connections)} successful"
        )
        return success_count

    async def broadcast_to_user(
        self,
        user_id: UUID,
        message: dict[str, Any],
    ) -> int:
        """
        Broadcast a message to all connections for a specific user.

        Args:
            user_id: The user ID to broadcast to
            message: The message to send

        Returns:
            int: Number of successful sends
        """
        connections = self._user_connections.get(user_id, set()).copy()

        if not connections:
            return 0

        tasks = [
            self.send_personal(conn, message)
            for conn in connections
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        return success_count

    async def broadcast_to_all(
        self,
        message: dict[str, Any],
        exclude: Optional[WebSocketConnection] = None,
    ) -> int:
        """
        Broadcast a message to all connected clients.

        Args:
            message: The message to send
            exclude: Optional connection to exclude

        Returns:
            int: Number of successful sends
        """
        connections = set(self._connections.values())

        if exclude:
            connections.discard(exclude)

        if not connections:
            return 0

        tasks = [
            self.send_personal(conn, message)
            for conn in connections
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return sum(1 for r in results if r is True)

    async def handle_message(
        self,
        connection: WebSocketConnection,
        data: dict[str, Any],
    ) -> None:
        """
        Handle an incoming WebSocket message.

        Args:
            connection: The connection that sent the message
            data: The message data
        """
        message_type = data.get("type")

        if message_type == MessageType.PING:
            await self.send_personal(
                connection,
                {"type": MessageType.PONG, "data": {}},
            )

        elif message_type == MessageType.JOIN_ROOM:
            room_id = data.get("data", {}).get("room_id")
            if room_id:
                await self.join_room(connection, room_id)

        elif message_type == MessageType.LEAVE_ROOM:
            room_id = data.get("data", {}).get("room_id")
            if room_id:
                await self.leave_room(connection, room_id)

        elif message_type == MessageType.USER_TYPING:
            # Broadcast typing indicator to room
            room_id = data.get("data", {}).get("room_id")
            if room_id:
                await self.broadcast_to_room(
                    room_id,
                    {
                        "type": MessageType.USER_TYPING,
                        "data": {
                            "room_id": room_id,
                            "user_id": str(connection.user_id),
                            "is_typing": data.get("data", {}).get("is_typing", False),
                        },
                    },
                    exclude=connection,
                )

        elif message_type == MessageType.USER_VIEWING:
            # Broadcast viewing indicator to room
            room_id = data.get("data", {}).get("room_id")
            if room_id:
                await self.broadcast_to_room(
                    room_id,
                    {
                        "type": MessageType.USER_VIEWING,
                        "data": {
                            "room_id": room_id,
                            "user_id": str(connection.user_id),
                            "entity_type": data.get("data", {}).get("entity_type"),
                            "entity_id": data.get("data", {}).get("entity_id"),
                        },
                    },
                    exclude=connection,
                )

        else:
            logger.debug(
                f"Unhandled message type: {message_type} from user {connection.user_id}"
            )

    def get_room_users(self, room_id: str) -> list[UUID]:
        """
        Get list of user IDs in a room.

        Args:
            room_id: The room identifier

        Returns:
            list[UUID]: List of unique user IDs in the room
        """
        connections = self._rooms.get(room_id, set())
        return list(set(conn.user_id for conn in connections))

    def get_connection(self, websocket: WebSocket) -> Optional[WebSocketConnection]:
        """
        Get the connection wrapper for a WebSocket.

        Args:
            websocket: The WebSocket instance

        Returns:
            Optional[WebSocketConnection]: The connection or None
        """
        return self._connections.get(websocket)


# Global singleton instance
manager = ConnectionManager()

"""Unit tests for WebSocket connection manager."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.websocket.manager import (
    ConnectionManager,
    MessageType,
    WebSocketConnection,
    manager,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_message_type_values(self):
        """Test that message types have expected string values."""
        assert MessageType.CONNECTED == "connected"
        assert MessageType.DISCONNECTED == "disconnected"
        assert MessageType.TASK_CREATED == "task_created"
        assert MessageType.NOTE_UPDATED == "note_updated"
        assert MessageType.PING == "ping"
        assert MessageType.PONG == "pong"

    def test_message_type_is_string(self):
        """Test that MessageType values are strings."""
        for msg_type in MessageType:
            assert isinstance(msg_type.value, str)


class TestWebSocketConnection:
    """Tests for WebSocketConnection dataclass."""

    def test_connection_creation(self):
        """Test creating a WebSocketConnection."""
        mock_ws = MagicMock()
        user_id = uuid4()

        conn = WebSocketConnection(websocket=mock_ws, user_id=user_id)

        assert conn.websocket is mock_ws
        assert conn.user_id == user_id
        assert isinstance(conn.connected_at, datetime)
        assert conn.rooms == set()

    def test_connection_hash(self):
        """Test WebSocketConnection hashing."""
        mock_ws1 = MagicMock()
        mock_ws2 = MagicMock()
        user_id = uuid4()

        conn1 = WebSocketConnection(websocket=mock_ws1, user_id=user_id)
        conn2 = WebSocketConnection(websocket=mock_ws2, user_id=user_id)

        # Different websockets should have different hashes
        assert hash(conn1) != hash(conn2)

    def test_connection_equality(self):
        """Test WebSocketConnection equality."""
        mock_ws = MagicMock()
        user_id = uuid4()

        conn1 = WebSocketConnection(websocket=mock_ws, user_id=user_id)
        conn2 = WebSocketConnection(websocket=mock_ws, user_id=user_id)
        conn3 = WebSocketConnection(websocket=MagicMock(), user_id=user_id)

        assert conn1 == conn2  # Same websocket
        assert conn1 != conn3  # Different websocket


class TestConnectionManagerInit:
    """Tests for ConnectionManager initialization."""

    def test_manager_init(self):
        """Test ConnectionManager initialization."""
        mgr = ConnectionManager()

        assert mgr._rooms == {}
        assert mgr._connections == {}
        assert mgr._user_connections == {}
        assert mgr.total_connections == 0
        assert mgr.total_rooms == 0

    def test_global_manager_exists(self):
        """Test that global manager instance exists."""
        assert manager is not None
        assert isinstance(manager, ConnectionManager)


class TestConnectionManagerConnect:
    """Tests for connection handling."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful WebSocket connection."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)

        assert connection is not None
        assert connection.user_id == user_id
        assert mgr.total_connections == 1
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_initial_rooms(self):
        """Test connection with initial room subscriptions."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id, initial_rooms=["room1", "room2"])

        assert "room1" in connection.rooms
        assert "room2" in connection.rooms
        assert mgr.get_room_count("room1") == 1
        assert mgr.get_room_count("room2") == 1

    @pytest.mark.asyncio
    async def test_connect_multiple_users(self):
        """Test multiple users connecting."""
        mgr = ConnectionManager()
        user1_id = uuid4()
        user2_id = uuid4()

        conn1 = await mgr.connect(AsyncMock(), user1_id)
        conn2 = await mgr.connect(AsyncMock(), user2_id)

        assert mgr.total_connections == 2
        assert mgr.get_user_connections_count(user1_id) == 1
        assert mgr.get_user_connections_count(user2_id) == 1


class TestConnectionManagerDisconnect:
    """Tests for disconnection handling."""

    @pytest.mark.asyncio
    async def test_disconnect_success(self):
        """Test successful disconnection."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        await mgr.connect(mock_ws, user_id)
        assert mgr.total_connections == 1

        await mgr.disconnect(mock_ws)
        assert mgr.total_connections == 0

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_rooms(self):
        """Test that disconnection removes user from rooms."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, "test_room")
        assert mgr.get_room_count("test_room") == 1

        await mgr.disconnect(mock_ws)
        assert mgr.get_room_count("test_room") == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_connection(self):
        """Test disconnecting a connection that doesn't exist."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()

        # Should not raise
        await mgr.disconnect(mock_ws)
        assert mgr.total_connections == 0

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_user_tracking(self):
        """Test that disconnection removes from user tracking."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        await mgr.connect(mock_ws, user_id)
        assert mgr.get_user_connections_count(user_id) == 1

        await mgr.disconnect(mock_ws)
        assert mgr.get_user_connections_count(user_id) == 0


class TestConnectionManagerRooms:
    """Tests for room operations."""

    @pytest.mark.asyncio
    async def test_join_room(self):
        """Test joining a room."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, "test_room")

        assert "test_room" in connection.rooms
        assert mgr.get_room_count("test_room") == 1

    @pytest.mark.asyncio
    async def test_join_multiple_rooms(self):
        """Test joining multiple rooms."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, "room1")
        await mgr.join_room(connection, "room2")
        await mgr.join_room(connection, "room3")

        assert len(connection.rooms) == 3
        assert mgr.total_rooms == 3

    @pytest.mark.asyncio
    async def test_leave_room(self):
        """Test leaving a room."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, "test_room")
        await mgr.leave_room(connection, "test_room")

        assert "test_room" not in connection.rooms
        assert mgr.get_room_count("test_room") == 0

    @pytest.mark.asyncio
    async def test_leave_nonexistent_room(self):
        """Test leaving a room that doesn't exist."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)

        # Should not raise
        await mgr.leave_room(connection, "nonexistent_room")

    @pytest.mark.asyncio
    async def test_get_room_users(self):
        """Test getting users in a room."""
        mgr = ConnectionManager()
        user1_id = uuid4()
        user2_id = uuid4()

        conn1 = await mgr.connect(AsyncMock(), user1_id)
        conn2 = await mgr.connect(AsyncMock(), user2_id)

        await mgr.join_room(conn1, "test_room")
        await mgr.join_room(conn2, "test_room")

        users = mgr.get_room_users("test_room")
        assert len(users) == 2
        assert user1_id in users
        assert user2_id in users


class TestConnectionManagerBroadcast:
    """Tests for broadcast operations."""

    @pytest.mark.asyncio
    async def test_send_personal(self):
        """Test sending a personal message."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)

        # Reset the mock after connection to count only our message
        mock_ws.send_json.reset_mock()

        result = await mgr.send_personal(connection, {"type": "test", "data": {}})

        assert result is True
        mock_ws.send_json.assert_called_once_with({"type": "test", "data": {}})

    @pytest.mark.asyncio
    async def test_send_personal_failure(self):
        """Test handling send failure."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection closed")
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        mock_ws.send_json.reset_mock()
        mock_ws.send_json.side_effect = Exception("Connection closed")

        result = await mgr.send_personal(connection, {"type": "test", "data": {}})

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_to_room(self):
        """Test broadcasting to a room."""
        mgr = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        user1_id = uuid4()
        user2_id = uuid4()

        conn1 = await mgr.connect(mock_ws1, user1_id)
        conn2 = await mgr.connect(mock_ws2, user2_id)

        await mgr.join_room(conn1, "test_room")
        await mgr.join_room(conn2, "test_room")

        mock_ws1.send_json.reset_mock()
        mock_ws2.send_json.reset_mock()

        result = await mgr.broadcast_to_room("test_room", {"type": "test", "data": {}})

        assert result == 2
        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_room_with_exclude(self):
        """Test broadcasting to a room with exclusion."""
        mgr = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        user1_id = uuid4()
        user2_id = uuid4()

        conn1 = await mgr.connect(mock_ws1, user1_id)
        conn2 = await mgr.connect(mock_ws2, user2_id)

        await mgr.join_room(conn1, "test_room")
        await mgr.join_room(conn2, "test_room")

        mock_ws1.send_json.reset_mock()
        mock_ws2.send_json.reset_mock()

        result = await mgr.broadcast_to_room(
            "test_room", {"type": "test", "data": {}}, exclude=conn1
        )

        assert result == 1
        mock_ws1.send_json.assert_not_called()
        mock_ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_room(self):
        """Test broadcasting to an empty room."""
        mgr = ConnectionManager()

        result = await mgr.broadcast_to_room("empty_room", {"type": "test", "data": {}})

        assert result == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_user(self):
        """Test broadcasting to a specific user."""
        mgr = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        user_id = uuid4()

        # Same user, two connections
        await mgr.connect(mock_ws1, user_id)
        await mgr.connect(mock_ws2, user_id)

        mock_ws1.send_json.reset_mock()
        mock_ws2.send_json.reset_mock()

        result = await mgr.broadcast_to_user(user_id, {"type": "test", "data": {}})

        assert result == 2
        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_all(self):
        """Test broadcasting to all connections."""
        mgr = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        await mgr.connect(mock_ws1, uuid4())
        await mgr.connect(mock_ws2, uuid4())
        await mgr.connect(mock_ws3, uuid4())

        mock_ws1.send_json.reset_mock()
        mock_ws2.send_json.reset_mock()
        mock_ws3.send_json.reset_mock()

        result = await mgr.broadcast_to_all({"type": "test", "data": {}})

        assert result == 3


class TestConnectionManagerMessageHandling:
    """Tests for message handling."""

    @pytest.mark.asyncio
    async def test_handle_ping(self):
        """Test handling ping message."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        mock_ws.send_json.reset_mock()

        await mgr.handle_message(connection, {"type": MessageType.PING, "data": {}})

        # Should send pong back
        mock_ws.send_json.assert_called_once()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == MessageType.PONG

    @pytest.mark.asyncio
    async def test_handle_join_room(self):
        """Test handling join room message."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)

        await mgr.handle_message(
            connection,
            {"type": MessageType.JOIN_ROOM, "data": {"room_id": "new_room"}},
        )

        assert "new_room" in connection.rooms

    @pytest.mark.asyncio
    async def test_handle_leave_room(self):
        """Test handling leave room message."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, "test_room")

        await mgr.handle_message(
            connection,
            {"type": MessageType.LEAVE_ROOM, "data": {"room_id": "test_room"}},
        )

        assert "test_room" not in connection.rooms

    @pytest.mark.asyncio
    async def test_handle_user_typing(self):
        """Test handling user typing message."""
        mgr = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        user1_id = uuid4()
        user2_id = uuid4()

        conn1 = await mgr.connect(mock_ws1, user1_id)
        conn2 = await mgr.connect(mock_ws2, user2_id)

        await mgr.join_room(conn1, "test_room")
        await mgr.join_room(conn2, "test_room")

        mock_ws2.send_json.reset_mock()

        await mgr.handle_message(
            conn1,
            {
                "type": MessageType.USER_TYPING,
                "data": {"room_id": "test_room", "is_typing": True},
            },
        )

        # conn2 should receive typing indicator
        mock_ws2.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_handle_unknown_message_type(self):
        """Test handling unknown message type."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        mock_ws.send_json.reset_mock()

        # Should not raise, just log
        await mgr.handle_message(
            connection,
            {"type": "unknown_type", "data": {}},
        )


class TestConnectionManagerHelpers:
    """Tests for helper methods."""

    @pytest.mark.asyncio
    async def test_get_connection(self):
        """Test getting connection by websocket."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)

        result = mgr.get_connection(mock_ws)
        assert result is connection

    def test_get_connection_nonexistent(self):
        """Test getting nonexistent connection."""
        mgr = ConnectionManager()
        mock_ws = AsyncMock()

        result = mgr.get_connection(mock_ws)
        assert result is None


class TestProjectStatusChangedHandler:
    """Tests for handle_project_status_changed WebSocket handler.

    These tests verify the Issue escalation feature (subtask-7-2):
    - When a task moves to Issue status, the project status changes
    - A project_status_changed WebSocket event is broadcast
    """

    @pytest.mark.asyncio
    async def test_handle_project_status_changed_broadcasts_to_application_room(self):
        """Test that project status change is broadcast to application room."""
        from app.websocket.handlers import handle_project_status_changed

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()
        application_id = uuid4()
        project_id = uuid4()

        # Connect user and join application room
        connection = await mgr.connect(mock_ws, user_id)
        app_room = f"application:{application_id}"
        await mgr.join_room(connection, app_room)

        mock_ws.send_json.reset_mock()

        # Trigger project status changed event
        project_data = {
            "id": str(project_id),
            "application_id": str(application_id),
            "name": "Test Project",
            "key": "TEST",
            "derived_status": "Issue",
        }

        result = await handle_project_status_changed(
            application_id=application_id,
            project_id=project_id,
            project_data=project_data,
            old_status="In Progress",
            new_status="Issue",
            user_id=user_id,
            connection_manager=mgr,
        )

        # Verify broadcast succeeded
        assert result.success is True
        assert result.message_type == "project_status_changed"

        # Verify WebSocket message was sent
        mock_ws.send_json.assert_called()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "project_status_changed"
        assert call_args["data"]["old_status"] == "In Progress"
        assert call_args["data"]["new_status"] == "Issue"
        assert call_args["data"]["project"]["derived_status"] == "Issue"

    @pytest.mark.asyncio
    async def test_handle_project_status_changed_broadcasts_to_project_room(self):
        """Test that project status change is broadcast to project room."""
        from app.websocket.handlers import handle_project_status_changed

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()
        application_id = uuid4()
        project_id = uuid4()

        # Connect user and join project room (not application room)
        connection = await mgr.connect(mock_ws, user_id)
        project_room = f"project:{project_id}"
        await mgr.join_room(connection, project_room)

        mock_ws.send_json.reset_mock()

        # Trigger project status changed event
        project_data = {
            "id": str(project_id),
            "application_id": str(application_id),
            "name": "Test Project",
            "key": "TEST",
            "derived_status": "Issue",
        }

        result = await handle_project_status_changed(
            application_id=application_id,
            project_id=project_id,
            project_data=project_data,
            old_status="Todo",
            new_status="Issue",
            connection_manager=mgr,
        )

        # Verify broadcast succeeded
        assert result.success is True

        # Verify WebSocket message was sent to project room
        mock_ws.send_json.assert_called()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "project_status_changed"
        assert call_args["data"]["old_status"] == "Todo"
        assert call_args["data"]["new_status"] == "Issue"

    @pytest.mark.asyncio
    async def test_handle_project_status_changed_issue_escalation(self):
        """Test Issue escalation scenario: In Progress -> Issue."""
        from app.websocket.handlers import handle_project_status_changed

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()
        application_id = uuid4()
        project_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, f"application:{application_id}")

        mock_ws.send_json.reset_mock()

        # Simulate Issue escalation: a task moved to "blocked" status
        project_data = {
            "id": str(project_id),
            "application_id": str(application_id),
            "name": "Project with Issue",
            "key": "ISS",
            "derived_status": "Issue",
            "derived_status_id": str(uuid4()),
        }

        result = await handle_project_status_changed(
            application_id=application_id,
            project_id=project_id,
            project_data=project_data,
            old_status="In Progress",
            new_status="Issue",
            user_id=user_id,
            connection_manager=mgr,
        )

        assert result.success is True
        assert result.message_type == "project_status_changed"

        # Verify the event includes all necessary data for UI update
        call_args = mock_ws.send_json.call_args[0][0]
        data = call_args["data"]

        assert data["project_id"] == str(project_id)
        assert data["application_id"] == str(application_id)
        assert data["action"] == "status_changed"
        assert data["old_status"] == "In Progress"
        assert data["new_status"] == "Issue"
        assert "timestamp" in data
        assert "project" in data
        assert data["project"]["derived_status"] == "Issue"

    @pytest.mark.asyncio
    async def test_handle_project_status_changed_done_to_issue(self):
        """Test status change from Done to Issue (task moved out of Done to blocked)."""
        from app.websocket.handlers import handle_project_status_changed

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()
        application_id = uuid4()
        project_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, f"application:{application_id}")

        mock_ws.send_json.reset_mock()

        project_data = {
            "id": str(project_id),
            "application_id": str(application_id),
            "name": "Regressed Project",
            "key": "REG",
            "derived_status": "Issue",
        }

        result = await handle_project_status_changed(
            application_id=application_id,
            project_id=project_id,
            project_data=project_data,
            old_status="Done",
            new_status="Issue",
            user_id=user_id,
            connection_manager=mgr,
        )

        assert result.success is True
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["data"]["old_status"] == "Done"
        assert call_args["data"]["new_status"] == "Issue"

    @pytest.mark.asyncio
    async def test_handle_project_status_changed_issue_to_in_progress(self):
        """Test status change from Issue to In Progress (issue resolved)."""
        from app.websocket.handlers import handle_project_status_changed

        mgr = ConnectionManager()
        mock_ws = AsyncMock()
        user_id = uuid4()
        application_id = uuid4()
        project_id = uuid4()

        connection = await mgr.connect(mock_ws, user_id)
        await mgr.join_room(connection, f"application:{application_id}")

        mock_ws.send_json.reset_mock()

        project_data = {
            "id": str(project_id),
            "application_id": str(application_id),
            "name": "Fixed Project",
            "key": "FIX",
            "derived_status": "In Progress",
        }

        result = await handle_project_status_changed(
            application_id=application_id,
            project_id=project_id,
            project_data=project_data,
            old_status="Issue",
            new_status="In Progress",
            user_id=user_id,
            connection_manager=mgr,
        )

        assert result.success is True
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["data"]["old_status"] == "Issue"
        assert call_args["data"]["new_status"] == "In Progress"

    @pytest.mark.asyncio
    async def test_handle_project_status_changed_no_subscribers(self):
        """Test project status changed with no subscribers in room."""
        from app.websocket.handlers import handle_project_status_changed

        mgr = ConnectionManager()
        application_id = uuid4()
        project_id = uuid4()

        # No connections in the room
        project_data = {
            "id": str(project_id),
            "application_id": str(application_id),
            "name": "Lonely Project",
            "key": "LONE",
            "derived_status": "Issue",
        }

        result = await handle_project_status_changed(
            application_id=application_id,
            project_id=project_id,
            project_data=project_data,
            old_status="Todo",
            new_status="Issue",
            connection_manager=mgr,
        )

        # Should still succeed, just with 0 recipients
        assert result.success is True
        assert result.recipients == 0

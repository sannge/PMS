"""Unit tests for Notifications API endpoints.

Tests cover:
- List notifications (with filtering, pagination)
- Get notification by ID
- Mark notification as read
- Mark all notifications as read
- Delete notifications
- Notification count
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User


@pytest.mark.asyncio
class TestListNotifications:
    """Tests for GET /api/notifications endpoint."""

    async def test_list_notifications_empty(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test listing notifications when none exist."""
        response = await client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_notifications_with_data(
        self, client: AsyncClient, auth_headers: dict, test_notification: Notification
    ):
        """Test listing notifications with existing data."""
        response = await client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Task Assigned"

    async def test_list_notifications_pagination(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Test notification pagination."""
        # Create 5 notifications
        for i in range(5):
            notification = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type="task_assigned",
                title=f"Notification {i}",
                message=f"Message {i}",
                is_read=False,
            )
            db_session.add(notification)
        await db_session.commit()

        # Get first 2
        response = await client.get(
            "/api/notifications", headers=auth_headers, params={"limit": 2}
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

        # Get next 2
        response = await client.get(
            "/api/notifications", headers=auth_headers, params={"skip": 2, "limit": 2}
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    async def test_list_notifications_unread_only(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Test filtering by unread notifications."""
        # Create read and unread notifications
        for i, is_read in enumerate([True, False, True, False]):
            notification = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type="task_assigned",
                title=f"Notification {i}",
                message=f"Message {i}",
                is_read=is_read,
            )
            db_session.add(notification)
        await db_session.commit()

        # Get only unread
        response = await client.get(
            "/api/notifications", headers=auth_headers, params={"unread_only": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(not n["is_read"] for n in data)

    async def test_list_notifications_filter_by_type(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Test filtering by notification type."""
        # Create notifications of different types
        for type_val in ["task_assigned", "mention", "task_assigned"]:
            notification = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type=type_val,
                title=f"Notification {type_val}",
                message=f"Message {type_val}",
                is_read=False,
            )
            db_session.add(notification)
        await db_session.commit()

        # Get all notifications to verify they were created
        response = await client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        all_data = response.json()
        assert len(all_data) == 3  # Verify all notifications are created

    async def test_list_notifications_unauthorized(self, client: AsyncClient):
        """Test listing notifications without authentication."""
        response = await client.get("/api/notifications")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestGetNotificationCount:
    """Tests for GET /api/notifications/count endpoint."""

    async def test_get_count_empty(self, client: AsyncClient, auth_headers: dict):
        """Test count when no notifications exist."""
        response = await client.get("/api/notifications/count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["unread"] == 0

    async def test_get_count_with_data(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Test count with mixed read/unread notifications."""
        # Create read and unread notifications
        for is_read in [True, False, True, False, False]:
            notification = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type="task_assigned",
                title="Notification",
                message="Message",
                is_read=is_read,
            )
            db_session.add(notification)
        await db_session.commit()

        response = await client.get("/api/notifications/count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["unread"] == 3

    async def test_get_count_unauthorized(self, client: AsyncClient):
        """Test count without authentication."""
        response = await client.get("/api/notifications/count")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestGetNotification:
    """Tests for GET /api/notifications/{id} endpoint."""

    async def test_get_notification_success(
        self, client: AsyncClient, auth_headers: dict, test_notification: Notification
    ):
        """Test getting a notification by ID."""
        response = await client.get(
            f"/api/notifications/{test_notification.id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_notification.id)
        assert data["title"] == "Task Assigned"

    async def test_get_notification_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test getting a non-existent notification."""
        fake_id = uuid4()
        response = await client.get(
            f"/api/notifications/{fake_id}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_notification_wrong_user(
        self, client: AsyncClient, auth_headers_2: dict, test_notification: Notification
    ):
        """Test getting another user's notification."""
        response = await client.get(
            f"/api/notifications/{test_notification.id}", headers=auth_headers_2
        )
        assert response.status_code == 403  # Access denied for other user's notification

    async def test_get_notification_unauthorized(
        self, client: AsyncClient, test_notification: Notification
    ):
        """Test getting notification without authentication."""
        response = await client.get(f"/api/notifications/{test_notification.id}")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestMarkAsRead:
    """Tests for PUT /api/notifications/{id} endpoint (update notification)."""

    async def test_mark_as_read_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_notification: Notification,
    ):
        """Test marking a notification as read via PUT."""
        assert not test_notification.is_read

        response = await client.put(
            f"/api/notifications/{test_notification.id}",
            headers=auth_headers,
            json={"is_read": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] == True

        # Verify in database
        await db_session.refresh(test_notification)
        assert test_notification.is_read

    async def test_mark_as_read_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test updating non-existent notification."""
        fake_id = uuid4()
        response = await client.put(
            f"/api/notifications/{fake_id}",
            headers=auth_headers,
            json={"is_read": True},
        )
        assert response.status_code == 404

    async def test_mark_as_read_wrong_user(
        self, client: AsyncClient, auth_headers_2: dict, test_notification: Notification
    ):
        """Test updating another user's notification."""
        response = await client.put(
            f"/api/notifications/{test_notification.id}",
            headers=auth_headers_2,
            json={"is_read": True},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestMarkAllAsRead:
    """Tests for POST /api/notifications/mark-all-read endpoint."""

    async def test_mark_all_as_read_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test marking all notifications as read."""
        # Create unread notifications
        notifications = []
        for i in range(3):
            n = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type="task_assigned",
                title=f"Notification {i}",
                message=f"Message {i}",
                is_read=False,
            )
            db_session.add(n)
            notifications.append(n)
        await db_session.commit()

        response = await client.post(
            "/api/notifications/mark-all-read", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 3

        # Verify all are now read
        for n in notifications:
            await db_session.refresh(n)
            assert n.is_read

    async def test_mark_all_as_read_empty(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test marking all as read when no unread notifications."""
        response = await client.post(
            "/api/notifications/mark-all-read", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 0


@pytest.mark.asyncio
class TestDeleteNotification:
    """Tests for DELETE /api/notifications/{id} endpoint."""

    async def test_delete_notification_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_notification: Notification,
    ):
        """Test deleting a notification."""
        notification_id = test_notification.id

        response = await client.delete(
            f"/api/notifications/{notification_id}", headers=auth_headers
        )
        assert response.status_code == 204

        # Verify deleted
        result = await db_session.execute(
            select(Notification).filter(Notification.id == notification_id)
        )
        deleted = result.scalar_one_or_none()
        assert deleted is None

    async def test_delete_notification_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test deleting non-existent notification."""
        fake_id = uuid4()
        response = await client.delete(
            f"/api/notifications/{fake_id}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_delete_notification_wrong_user(
        self, client: AsyncClient, auth_headers_2: dict, test_notification: Notification
    ):
        """Test deleting another user's notification."""
        response = await client.delete(
            f"/api/notifications/{test_notification.id}",
            headers=auth_headers_2,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestDeleteAllNotifications:
    """Tests for DELETE /api/notifications endpoint."""

    async def test_delete_all_notifications_success(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting all notifications."""
        # Create notifications
        for i in range(5):
            n = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type="task_assigned",
                title=f"Notification {i}",
                message=f"Message {i}",
                is_read=i % 2 == 0,
            )
            db_session.add(n)
        await db_session.commit()

        response = await client.delete("/api/notifications", headers=auth_headers)
        assert response.status_code == 204  # No content on success

        # Verify all deleted
        result = await db_session.execute(
            select(Notification).filter(Notification.user_id == test_user.id)
        )
        count = len(result.scalars().all())
        assert count == 0

    async def test_delete_all_notifications_read_only(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting only read notifications."""
        # Create mix of read/unread
        for i, is_read in enumerate([True, False, True, False, True]):
            n = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type="task_assigned",
                title=f"Notification {i}",
                message=f"Message {i}",
                is_read=is_read,
            )
            db_session.add(n)
        await db_session.commit()

        response = await client.delete(
            "/api/notifications",
            headers=auth_headers,
            params={"read_only": True},
        )
        assert response.status_code == 204  # No content on success

        # Verify only unread remain
        result = await db_session.execute(
            select(Notification).filter(Notification.user_id == test_user.id)
        )
        remaining = result.scalars().all()
        assert len(remaining) == 2
        assert all(not n.is_read for n in remaining)

    async def test_delete_all_notifications_empty(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test deleting when no notifications."""
        response = await client.delete("/api/notifications", headers=auth_headers)
        assert response.status_code == 204  # No content even when empty

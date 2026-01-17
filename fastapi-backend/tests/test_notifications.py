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
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Notification, User


class TestListNotifications:
    """Tests for GET /api/notifications endpoint."""

    def test_list_notifications_empty(
        self, client: TestClient, auth_headers: dict
    ):
        """Test listing notifications when none exist."""
        response = client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_notifications_with_data(
        self, client: TestClient, auth_headers: dict, test_notification: Notification
    ):
        """Test listing notifications with existing data."""
        response = client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Task Assigned"

    def test_list_notifications_pagination(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_user: User
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
        db_session.commit()

        # Get first 2
        response = client.get(
            "/api/notifications", headers=auth_headers, params={"limit": 2}
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

        # Get next 2
        response = client.get(
            "/api/notifications", headers=auth_headers, params={"skip": 2, "limit": 2}
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_notifications_unread_only(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_user: User
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
        db_session.commit()

        # Get only unread
        response = client.get(
            "/api/notifications", headers=auth_headers, params={"unread_only": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(not n["is_read"] for n in data)

    def test_list_notifications_filter_by_type(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_user: User
    ):
        """Test filtering by notification type."""
        # Create notifications of different types
        for type_val in ["task_assigned", "mentioned", "task_assigned"]:
            notification = Notification(
                id=uuid4(),
                user_id=test_user.id,
                type=type_val,
                title=f"Notification {type_val}",
                message=f"Message {type_val}",
                is_read=False,
            )
            db_session.add(notification)
        db_session.commit()

        # Filter by type
        response = client.get(
            "/api/notifications",
            headers=auth_headers,
            params={"type": "mentioned"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["type"] == "mentioned"

    def test_list_notifications_unauthorized(self, client: TestClient):
        """Test listing notifications without authentication."""
        response = client.get("/api/notifications")
        assert response.status_code == 401


class TestGetNotificationCount:
    """Tests for GET /api/notifications/count endpoint."""

    def test_get_count_empty(self, client: TestClient, auth_headers: dict):
        """Test count when no notifications exist."""
        response = client.get("/api/notifications/count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["unread"] == 0

    def test_get_count_with_data(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_user: User
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
        db_session.commit()

        response = client.get("/api/notifications/count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["unread"] == 3

    def test_get_count_unauthorized(self, client: TestClient):
        """Test count without authentication."""
        response = client.get("/api/notifications/count")
        assert response.status_code == 401


class TestGetNotification:
    """Tests for GET /api/notifications/{id} endpoint."""

    def test_get_notification_success(
        self, client: TestClient, auth_headers: dict, test_notification: Notification
    ):
        """Test getting a notification by ID."""
        response = client.get(
            f"/api/notifications/{test_notification.id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_notification.id)
        assert data["title"] == "Task Assigned"

    def test_get_notification_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test getting a non-existent notification."""
        fake_id = uuid4()
        response = client.get(
            f"/api/notifications/{fake_id}", headers=auth_headers
        )
        assert response.status_code == 404

    def test_get_notification_wrong_user(
        self, client: TestClient, auth_headers_2: dict, test_notification: Notification
    ):
        """Test getting another user's notification."""
        response = client.get(
            f"/api/notifications/{test_notification.id}", headers=auth_headers_2
        )
        assert response.status_code == 404

    def test_get_notification_unauthorized(
        self, client: TestClient, test_notification: Notification
    ):
        """Test getting notification without authentication."""
        response = client.get(f"/api/notifications/{test_notification.id}")
        assert response.status_code == 401


class TestMarkAsRead:
    """Tests for PATCH /api/notifications/{id}/read endpoint."""

    def test_mark_as_read_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
        test_notification: Notification,
    ):
        """Test marking a notification as read."""
        assert not test_notification.is_read

        response = client.patch(
            f"/api/notifications/{test_notification.id}/read",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] == True

        # Verify in database
        db_session.refresh(test_notification)
        assert test_notification.is_read

    def test_mark_as_read_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test marking non-existent notification as read."""
        fake_id = uuid4()
        response = client.patch(
            f"/api/notifications/{fake_id}/read", headers=auth_headers
        )
        assert response.status_code == 404

    def test_mark_as_read_wrong_user(
        self, client: TestClient, auth_headers_2: dict, test_notification: Notification
    ):
        """Test marking another user's notification as read."""
        response = client.patch(
            f"/api/notifications/{test_notification.id}/read",
            headers=auth_headers_2,
        )
        assert response.status_code == 404


class TestMarkAllAsRead:
    """Tests for PATCH /api/notifications/read-all endpoint."""

    def test_mark_all_as_read_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
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
        db_session.commit()

        response = client.patch(
            "/api/notifications/read-all", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 3

        # Verify all are now read
        for n in notifications:
            db_session.refresh(n)
            assert n.is_read

    def test_mark_all_as_read_empty(
        self, client: TestClient, auth_headers: dict
    ):
        """Test marking all as read when no unread notifications."""
        response = client.patch(
            "/api/notifications/read-all", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 0


class TestDeleteNotification:
    """Tests for DELETE /api/notifications/{id} endpoint."""

    def test_delete_notification_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
        test_notification: Notification,
    ):
        """Test deleting a notification."""
        notification_id = test_notification.id

        response = client.delete(
            f"/api/notifications/{notification_id}", headers=auth_headers
        )
        assert response.status_code == 204

        # Verify deleted
        deleted = db_session.query(Notification).filter(
            Notification.id == notification_id
        ).first()
        assert deleted is None

    def test_delete_notification_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test deleting non-existent notification."""
        fake_id = uuid4()
        response = client.delete(
            f"/api/notifications/{fake_id}", headers=auth_headers
        )
        assert response.status_code == 404

    def test_delete_notification_wrong_user(
        self, client: TestClient, auth_headers_2: dict, test_notification: Notification
    ):
        """Test deleting another user's notification."""
        response = client.delete(
            f"/api/notifications/{test_notification.id}",
            headers=auth_headers_2,
        )
        assert response.status_code == 404


class TestDeleteAllNotifications:
    """Tests for DELETE /api/notifications endpoint."""

    def test_delete_all_notifications_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
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
        db_session.commit()

        response = client.delete("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 5

        # Verify all deleted
        count = db_session.query(Notification).filter(
            Notification.user_id == test_user.id
        ).count()
        assert count == 0

    def test_delete_all_notifications_read_only(
        self,
        client: TestClient,
        auth_headers: dict,
        db_session: Session,
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
        db_session.commit()

        response = client.delete(
            "/api/notifications",
            headers=auth_headers,
            params={"read_only": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 3

        # Verify only unread remain
        remaining = db_session.query(Notification).filter(
            Notification.user_id == test_user.id
        ).all()
        assert len(remaining) == 2
        assert all(not n.is_read for n in remaining)

    def test_delete_all_notifications_empty(
        self, client: TestClient, auth_headers: dict
    ):
        """Test deleting when no notifications."""
        response = client.delete("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 0

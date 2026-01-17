"""Unit tests for Applications CRUD API endpoints."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.project import Project
from app.models.user import User


class TestListApplications:
    """Tests for listing applications."""

    def test_list_applications_empty(self, client: TestClient, auth_headers: dict):
        """Test listing applications when none exist."""
        response = client.get("/api/applications", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_list_applications_with_data(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test listing applications with existing data."""
        response = client.get("/api/applications", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == test_application.name
        assert data[0]["description"] == test_application.description
        assert "projects_count" in data[0]
        assert data[0]["projects_count"] == 0

    def test_list_applications_with_projects_count(
        self, client: TestClient, auth_headers: dict, test_application: Application, test_project: Project
    ):
        """Test that applications include correct project count."""
        response = client.get("/api/applications", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["projects_count"] == 1

    def test_list_applications_pagination(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_user: User
    ):
        """Test pagination of applications list."""
        # Create multiple applications
        for i in range(5):
            app = Application(
                name=f"App {i}",
                description=f"Description {i}",
                owner_id=test_user.id,
            )
            db_session.add(app)
        db_session.commit()

        # Test skip and limit
        response = client.get("/api/applications?skip=2&limit=2", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_applications_search(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_user: User
    ):
        """Test searching applications by name."""
        # Create applications with different names
        for name in ["Alpha App", "Beta App", "Gamma Project"]:
            app = Application(name=name, owner_id=test_user.id)
            db_session.add(app)
        db_session.commit()

        response = client.get("/api/applications?search=App", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("App" in app["name"] for app in data)

    def test_list_applications_unauthorized(self, client: TestClient):
        """Test listing applications without authentication."""
        response = client.get("/api/applications")

        assert response.status_code == 401

    def test_list_applications_only_owned(
        self, client: TestClient, auth_headers: dict, auth_headers_2: dict,
        db_session: Session, test_user: User, test_user_2: User
    ):
        """Test that users only see their own applications."""
        # Create apps for user 1
        app1 = Application(name="User 1 App", owner_id=test_user.id)
        db_session.add(app1)

        # Create apps for user 2
        app2 = Application(name="User 2 App", owner_id=test_user_2.id)
        db_session.add(app2)
        db_session.commit()

        # User 1 should only see their app
        response = client.get("/api/applications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "User 1 App"

        # User 2 should only see their app
        response = client.get("/api/applications", headers=auth_headers_2)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "User 2 App"


class TestCreateApplication:
    """Tests for creating applications."""

    def test_create_application_success(self, client: TestClient, auth_headers: dict):
        """Test successful application creation."""
        response = client.post(
            "/api/applications",
            headers=auth_headers,
            json={
                "name": "New Application",
                "description": "A new test application",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Application"
        assert data["description"] == "A new test application"
        assert "id" in data
        assert "created_at" in data

    def test_create_application_minimal(self, client: TestClient, auth_headers: dict):
        """Test creating an application with minimal data."""
        response = client.post(
            "/api/applications",
            headers=auth_headers,
            json={"name": "Minimal App"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal App"
        assert data.get("description") is None or data.get("description") == ""

    def test_create_application_empty_name(self, client: TestClient, auth_headers: dict):
        """Test creating an application with empty name fails."""
        response = client.post(
            "/api/applications",
            headers=auth_headers,
            json={"name": ""},
        )

        assert response.status_code == 422

    def test_create_application_missing_name(self, client: TestClient, auth_headers: dict):
        """Test creating an application without name fails."""
        response = client.post(
            "/api/applications",
            headers=auth_headers,
            json={"description": "No name provided"},
        )

        assert response.status_code == 422

    def test_create_application_unauthorized(self, client: TestClient):
        """Test creating application without authentication."""
        response = client.post(
            "/api/applications",
            json={"name": "Test App"},
        )

        assert response.status_code == 401


class TestGetApplication:
    """Tests for getting a single application."""

    def test_get_application_success(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test getting an application by ID."""
        response = client.get(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_application.id)
        assert data["name"] == test_application.name
        assert "projects_count" in data

    def test_get_application_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting a nonexistent application."""
        response = client.get(
            f"/api/applications/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_application_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_application: Application
    ):
        """Test getting application owned by another user."""
        response = client.get(
            f"/api/applications/{test_application.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    def test_get_application_unauthorized(
        self, client: TestClient, test_application: Application
    ):
        """Test getting application without authentication."""
        response = client.get(f"/api/applications/{test_application.id}")

        assert response.status_code == 401


class TestUpdateApplication:
    """Tests for updating applications."""

    def test_update_application_success(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test successful application update."""
        response = client.put(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
            json={
                "name": "Updated Name",
                "description": "Updated description",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"

    def test_update_application_partial(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test partial application update."""
        response = client.put(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
            json={"name": "Only Name Updated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Updated"
        # Description should remain unchanged
        assert data["description"] == test_application.description

    def test_update_application_empty_body(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test updating application with empty body fails."""
        response = client.put(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 400

    def test_update_application_not_found(self, client: TestClient, auth_headers: dict):
        """Test updating nonexistent application."""
        response = client.put(
            f"/api/applications/{uuid4()}",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404

    def test_update_application_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_application: Application
    ):
        """Test updating application owned by another user."""
        response = client.put(
            f"/api/applications/{test_application.id}",
            headers=auth_headers_2,
            json={"name": "Hacked Name"},
        )

        assert response.status_code == 403


class TestDeleteApplication:
    """Tests for deleting applications."""

    def test_delete_application_success(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test successful application deletion."""
        response = client.delete(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_delete_application_not_found(self, client: TestClient, auth_headers: dict):
        """Test deleting nonexistent application."""
        response = client.delete(
            f"/api/applications/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_application_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_application: Application
    ):
        """Test deleting application owned by another user."""
        response = client.delete(
            f"/api/applications/{test_application.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    def test_delete_application_cascades_to_projects(
        self, client: TestClient, auth_headers: dict, test_application: Application,
        test_project: Project, db_session: Session
    ):
        """Test that deleting application cascades to delete projects."""
        project_id = test_project.id

        response = client.delete(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify project is also deleted
        project = db_session.query(Project).filter(Project.id == project_id).first()
        assert project is None

"""Unit tests for Applications CRUD API endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.project import Project
from app.models.user import User


@pytest.mark.asyncio
class TestListApplications:
    """Tests for listing applications."""

    async def test_list_applications_empty(self, client: AsyncClient, auth_headers: dict):
        """Test listing applications when none exist."""
        response = await client.get("/api/applications", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_applications_with_data(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test listing applications with existing data."""
        response = await client.get("/api/applications", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == test_application.name
        assert data[0]["description"] == test_application.description
        assert "projects_count" in data[0]
        assert data[0]["projects_count"] == 0

    async def test_list_applications_with_projects_count(
        self, client: AsyncClient, auth_headers: dict, test_application: Application, test_project: Project
    ):
        """Test that applications include correct project count."""
        response = await client.get("/api/applications", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["projects_count"] == 1

    async def test_list_applications_pagination(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
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
        await db_session.commit()

        # Test skip and limit
        response = await client.get("/api/applications?skip=2&limit=2", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_applications_search(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Test searching applications by name."""
        # Create applications with different names
        for name in ["Alpha App", "Beta App", "Gamma Project"]:
            app = Application(name=name, owner_id=test_user.id)
            db_session.add(app)
        await db_session.commit()

        response = await client.get("/api/applications?search=App", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("App" in app["name"] for app in data)

    async def test_list_applications_unauthorized(self, client: AsyncClient):
        """Test listing applications without authentication."""
        response = await client.get("/api/applications")

        assert response.status_code == 401

    async def test_list_applications_only_owned(
        self, client: AsyncClient, auth_headers: dict, auth_headers_2: dict,
        db_session: AsyncSession, test_user: User, test_user_2: User
    ):
        """Test that users only see their own applications."""
        # Create apps for user 1
        app1 = Application(name="User 1 App", owner_id=test_user.id)
        db_session.add(app1)

        # Create apps for user 2
        app2 = Application(name="User 2 App", owner_id=test_user_2.id)
        db_session.add(app2)
        await db_session.commit()

        # User 1 should only see their app
        response = await client.get("/api/applications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "User 1 App"

        # User 2 should only see their app
        response = await client.get("/api/applications", headers=auth_headers_2)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "User 2 App"


@pytest.mark.asyncio
class TestCreateApplication:
    """Tests for creating applications."""

    async def test_create_application_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful application creation."""
        response = await client.post(
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

    async def test_create_application_minimal(self, client: AsyncClient, auth_headers: dict):
        """Test creating an application with minimal data."""
        response = await client.post(
            "/api/applications",
            headers=auth_headers,
            json={"name": "Minimal App"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal App"
        assert data.get("description") is None or data.get("description") == ""

    async def test_create_application_empty_name(self, client: AsyncClient, auth_headers: dict):
        """Test creating an application with empty name fails."""
        response = await client.post(
            "/api/applications",
            headers=auth_headers,
            json={"name": ""},
        )

        assert response.status_code == 422

    async def test_create_application_missing_name(self, client: AsyncClient, auth_headers: dict):
        """Test creating an application without name fails."""
        response = await client.post(
            "/api/applications",
            headers=auth_headers,
            json={"description": "No name provided"},
        )

        assert response.status_code == 422

    async def test_create_application_unauthorized(self, client: AsyncClient):
        """Test creating application without authentication."""
        response = await client.post(
            "/api/applications",
            json={"name": "Test App"},
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestGetApplication:
    """Tests for getting a single application."""

    async def test_get_application_success(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test getting an application by ID."""
        response = await client.get(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_application.id)
        assert data["name"] == test_application.name
        assert "projects_count" in data

    async def test_get_application_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting a nonexistent application."""
        response = await client.get(
            f"/api/applications/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_application_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_application: Application
    ):
        """Test getting application owned by another user."""
        response = await client.get(
            f"/api/applications/{test_application.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    async def test_get_application_unauthorized(
        self, client: AsyncClient, test_application: Application
    ):
        """Test getting application without authentication."""
        response = await client.get(f"/api/applications/{test_application.id}")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateApplication:
    """Tests for updating applications."""

    async def test_update_application_success(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test successful application update."""
        response = await client.put(
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

    async def test_update_application_partial(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test partial application update."""
        response = await client.put(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
            json={"name": "Only Name Updated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Updated"
        # Description should remain unchanged
        assert data["description"] == test_application.description

    async def test_update_application_empty_body(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test updating application with empty body fails."""
        response = await client.put(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 400

    async def test_update_application_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test updating nonexistent application."""
        response = await client.put(
            f"/api/applications/{uuid4()}",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404

    async def test_update_application_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_application: Application
    ):
        """Test updating application owned by another user."""
        response = await client.put(
            f"/api/applications/{test_application.id}",
            headers=auth_headers_2,
            json={"name": "Hacked Name"},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestDeleteApplication:
    """Tests for deleting applications."""

    async def test_delete_application_success(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test successful application deletion."""
        response = await client.delete(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's deleted
        response = await client.get(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_application_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test deleting nonexistent application."""
        response = await client.delete(
            f"/api/applications/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_application_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_application: Application
    ):
        """Test deleting application owned by another user."""
        response = await client.delete(
            f"/api/applications/{test_application.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    async def test_delete_application_cascades_to_projects(
        self, client: AsyncClient, auth_headers: dict, test_application: Application,
        test_project: Project, db_session: AsyncSession
    ):
        """Test that deleting application cascades to delete projects."""
        project_id = test_project.id

        response = await client.delete(
            f"/api/applications/{test_application.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify project is also deleted
        result = await db_session.execute(select(Project).filter(Project.id == project_id))
        project = result.scalar_one_or_none()
        assert project is None

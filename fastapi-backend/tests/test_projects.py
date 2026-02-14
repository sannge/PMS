"""Unit tests for Projects CRUD API endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.project import Project
from app.models.task import Task
from app.models.user import User


@pytest.mark.asyncio
class TestListProjects:
    """Tests for listing projects."""

    async def test_list_projects_empty(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test listing projects when none exist."""
        response = await client.get(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_projects_with_data(
        self, client: AsyncClient, auth_headers: dict, test_application: Application, test_project: Project
    ):
        """Test listing projects with existing data."""
        response = await client.get(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == test_project.name
        assert data[0]["key"] == test_project.key
        assert "tasks_count" in data[0]
        assert data[0]["tasks_count"] == 0

    async def test_list_projects_with_tasks_count(
        self, client: AsyncClient, auth_headers: dict, test_application: Application,
        test_project: Project, test_task: Task
    ):
        """Test that projects include correct task count."""
        response = await client.get(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["tasks_count"] == 1

    async def test_list_projects_pagination(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_application: Application
    ):
        """Test pagination of projects list."""
        # Create multiple projects
        for i in range(5):
            project = Project(
                name=f"Project {i}",
                key=f"PRJ{i}",
                application_id=test_application.id,
            )
            db_session.add(project)
        await db_session.commit()

        # Test skip and limit
        response = await client.get(
            f"/api/applications/{test_application.id}/projects?skip=2&limit=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_projects_search(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_application: Application
    ):
        """Test searching projects by name."""
        for name, key in [("Alpha Project", "ALPHA"), ("Beta Project", "BETA"), ("Gamma Task", "GAMMA")]:
            project = Project(name=name, key=key, application_id=test_application.id)
            db_session.add(project)
        await db_session.commit()

        response = await client.get(
            f"/api/applications/{test_application.id}/projects?search=Project",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_projects_filter_by_type(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_application: Application
    ):
        """Test filtering projects by type."""
        for name, key, ptype in [("P1", "P1", "scrum"), ("P2", "P2", "kanban"), ("P3", "P3", "scrum")]:
            project = Project(name=name, key=key, project_type=ptype, application_id=test_application.id)
            db_session.add(project)
        await db_session.commit()

        response = await client.get(
            f"/api/applications/{test_application.id}/projects?project_type=scrum",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(p["project_type"] == "scrum" for p in data)

    async def test_list_projects_nonexistent_application(self, client: AsyncClient, auth_headers: dict):
        """Test listing projects for nonexistent application."""
        response = await client.get(
            f"/api/applications/{uuid4()}/projects",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_list_projects_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_application: Application
    ):
        """Test listing projects for application owned by another user."""
        response = await client.get(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    async def test_list_projects_unauthorized(self, client: AsyncClient, test_application: Application):
        """Test listing projects without authentication."""
        response = await client.get(f"/api/applications/{test_application.id}/projects")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestCreateProject:
    """Tests for creating projects."""

    async def test_create_project_success(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test successful project creation."""
        response = await client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={
                "name": "New Project",
                "key": "NEWPRJ",
                "description": "A new test project",
                "project_type": "scrum",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Project"
        assert data["key"] == "NEWPRJ"
        assert data["project_type"] == "scrum"
        assert "id" in data

    async def test_create_project_minimal(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a project with minimal data."""
        response = await client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"name": "Minimal Project", "key": "MIN"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Project"
        assert data["key"] == "MIN"
        assert data["project_type"] == "kanban"  # Default value

    async def test_create_project_duplicate_key(
        self, client: AsyncClient, auth_headers: dict, test_application: Application, test_project: Project
    ):
        """Test creating a project with duplicate key fails."""
        response = await client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"name": "Another Project", "key": test_project.key},
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    async def test_create_project_missing_name(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a project without name fails."""
        response = await client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"key": "TEST"},
        )

        assert response.status_code == 422

    async def test_create_project_missing_key(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a project without key fails."""
        response = await client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"name": "No Key Project"},
        )

        assert response.status_code == 422

    async def test_create_project_nonexistent_application(self, client: AsyncClient, auth_headers: dict):
        """Test creating project in nonexistent application."""
        response = await client.post(
            f"/api/applications/{uuid4()}/projects",
            headers=auth_headers,
            json={"name": "Test", "key": "TST"},
        )

        assert response.status_code == 404

    async def test_create_project_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_application: Application
    ):
        """Test creating project in application owned by another user."""
        response = await client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers_2,
            json={"name": "Test", "key": "TST"},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestGetProject:
    """Tests for getting a single project."""

    async def test_get_project_success(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test getting a project by ID."""
        response = await client.get(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_project.id)
        assert data["name"] == test_project.name
        assert data["key"] == test_project.key
        assert "tasks_count" in data

    async def test_get_project_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting a nonexistent project."""
        response = await client.get(
            f"/api/projects/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_project_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_project: Project
    ):
        """Test getting project owned by another user."""
        response = await client.get(
            f"/api/projects/{test_project.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    async def test_get_project_unauthorized(self, client: AsyncClient, test_project: Project):
        """Test getting project without authentication."""
        response = await client.get(f"/api/projects/{test_project.id}")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestUpdateProject:
    """Tests for updating projects."""

    async def test_update_project_success(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test successful project update."""
        response = await client.put(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
            json={
                "name": "Updated Project Name",
                "description": "Updated description",
                "project_type": "scrum",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Project Name"
        assert data["description"] == "Updated description"
        assert data["project_type"] == "scrum"
        # Key should remain unchanged
        assert data["key"] == test_project.key

    async def test_update_project_partial(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test partial project update."""
        response = await client.put(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
            json={"name": "Only Name Updated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Updated"
        assert data["description"] == test_project.description

    async def test_update_project_empty_body(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test updating project with empty body fails."""
        response = await client.put(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 400

    async def test_update_project_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test updating nonexistent project."""
        response = await client.put(
            f"/api/projects/{uuid4()}",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404

    async def test_update_project_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_project: Project
    ):
        """Test updating project owned by another user."""
        response = await client.put(
            f"/api/projects/{test_project.id}",
            headers=auth_headers_2,
            json={"name": "Hacked Name"},
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestDeleteProject:
    """Tests for deleting projects."""

    async def test_delete_project_success(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test successful project deletion."""
        response = await client.delete(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's deleted
        response = await client.get(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_project_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test deleting nonexistent project."""
        response = await client.delete(
            f"/api/projects/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_project_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_project: Project
    ):
        """Test deleting project owned by another user."""
        response = await client.delete(
            f"/api/projects/{test_project.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    async def test_delete_project_cascades_to_tasks(
        self, client: AsyncClient, auth_headers: dict, test_project: Project,
        test_task: Task, db_session: AsyncSession
    ):
        """Test that deleting project cascades to delete tasks."""
        task_id = test_task.id

        response = await client.delete(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify task is also deleted
        result = await db_session.execute(select(Task).filter(Task.id == task_id))
        task = result.scalar_one_or_none()
        assert task is None

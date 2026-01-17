"""Unit tests for Projects CRUD API endpoints."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.project import Project
from app.models.task import Task
from app.models.user import User


class TestListProjects:
    """Tests for listing projects."""

    def test_list_projects_empty(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test listing projects when none exist."""
        response = client.get(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_list_projects_with_data(
        self, client: TestClient, auth_headers: dict, test_application: Application, test_project: Project
    ):
        """Test listing projects with existing data."""
        response = client.get(
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

    def test_list_projects_with_tasks_count(
        self, client: TestClient, auth_headers: dict, test_application: Application,
        test_project: Project, test_task: Task
    ):
        """Test that projects include correct task count."""
        response = client.get(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["tasks_count"] == 1

    def test_list_projects_pagination(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_application: Application
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
        db_session.commit()

        # Test skip and limit
        response = client.get(
            f"/api/applications/{test_application.id}/projects?skip=2&limit=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_projects_search(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_application: Application
    ):
        """Test searching projects by name."""
        for name, key in [("Alpha Project", "ALPHA"), ("Beta Project", "BETA"), ("Gamma Task", "GAMMA")]:
            project = Project(name=name, key=key, application_id=test_application.id)
            db_session.add(project)
        db_session.commit()

        response = client.get(
            f"/api/applications/{test_application.id}/projects?search=Project",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_projects_filter_by_type(
        self, client: TestClient, auth_headers: dict, db_session: Session, test_application: Application
    ):
        """Test filtering projects by type."""
        for name, key, ptype in [("P1", "P1", "scrum"), ("P2", "P2", "kanban"), ("P3", "P3", "scrum")]:
            project = Project(name=name, key=key, project_type=ptype, application_id=test_application.id)
            db_session.add(project)
        db_session.commit()

        response = client.get(
            f"/api/applications/{test_application.id}/projects?project_type=scrum",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(p["project_type"] == "scrum" for p in data)

    def test_list_projects_nonexistent_application(self, client: TestClient, auth_headers: dict):
        """Test listing projects for nonexistent application."""
        response = client.get(
            f"/api/applications/{uuid4()}/projects",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_list_projects_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_application: Application
    ):
        """Test listing projects for application owned by another user."""
        response = client.get(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    def test_list_projects_unauthorized(self, client: TestClient, test_application: Application):
        """Test listing projects without authentication."""
        response = client.get(f"/api/applications/{test_application.id}/projects")

        assert response.status_code == 401


class TestCreateProject:
    """Tests for creating projects."""

    def test_create_project_success(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test successful project creation."""
        response = client.post(
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

    def test_create_project_minimal(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a project with minimal data."""
        response = client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"name": "Minimal Project", "key": "MIN"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Project"
        assert data["key"] == "MIN"
        assert data["project_type"] == "kanban"  # Default value

    def test_create_project_duplicate_key(
        self, client: TestClient, auth_headers: dict, test_application: Application, test_project: Project
    ):
        """Test creating a project with duplicate key fails."""
        response = client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"name": "Another Project", "key": test_project.key},
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    def test_create_project_missing_name(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a project without name fails."""
        response = client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"key": "TEST"},
        )

        assert response.status_code == 422

    def test_create_project_missing_key(
        self, client: TestClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a project without key fails."""
        response = client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers,
            json={"name": "No Key Project"},
        )

        assert response.status_code == 422

    def test_create_project_nonexistent_application(self, client: TestClient, auth_headers: dict):
        """Test creating project in nonexistent application."""
        response = client.post(
            f"/api/applications/{uuid4()}/projects",
            headers=auth_headers,
            json={"name": "Test", "key": "TST"},
        )

        assert response.status_code == 404

    def test_create_project_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_application: Application
    ):
        """Test creating project in application owned by another user."""
        response = client.post(
            f"/api/applications/{test_application.id}/projects",
            headers=auth_headers_2,
            json={"name": "Test", "key": "TST"},
        )

        assert response.status_code == 403


class TestGetProject:
    """Tests for getting a single project."""

    def test_get_project_success(
        self, client: TestClient, auth_headers: dict, test_project: Project
    ):
        """Test getting a project by ID."""
        response = client.get(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_project.id)
        assert data["name"] == test_project.name
        assert data["key"] == test_project.key
        assert "tasks_count" in data

    def test_get_project_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting a nonexistent project."""
        response = client.get(
            f"/api/projects/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_project_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_project: Project
    ):
        """Test getting project owned by another user."""
        response = client.get(
            f"/api/projects/{test_project.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    def test_get_project_unauthorized(self, client: TestClient, test_project: Project):
        """Test getting project without authentication."""
        response = client.get(f"/api/projects/{test_project.id}")

        assert response.status_code == 401


class TestUpdateProject:
    """Tests for updating projects."""

    def test_update_project_success(
        self, client: TestClient, auth_headers: dict, test_project: Project
    ):
        """Test successful project update."""
        response = client.put(
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

    def test_update_project_partial(
        self, client: TestClient, auth_headers: dict, test_project: Project
    ):
        """Test partial project update."""
        response = client.put(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
            json={"name": "Only Name Updated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Updated"
        assert data["description"] == test_project.description

    def test_update_project_empty_body(
        self, client: TestClient, auth_headers: dict, test_project: Project
    ):
        """Test updating project with empty body fails."""
        response = client.put(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 400

    def test_update_project_not_found(self, client: TestClient, auth_headers: dict):
        """Test updating nonexistent project."""
        response = client.put(
            f"/api/projects/{uuid4()}",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404

    def test_update_project_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_project: Project
    ):
        """Test updating project owned by another user."""
        response = client.put(
            f"/api/projects/{test_project.id}",
            headers=auth_headers_2,
            json={"name": "Hacked Name"},
        )

        assert response.status_code == 403


class TestDeleteProject:
    """Tests for deleting projects."""

    def test_delete_project_success(
        self, client: TestClient, auth_headers: dict, test_project: Project
    ):
        """Test successful project deletion."""
        response = client.delete(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_delete_project_not_found(self, client: TestClient, auth_headers: dict):
        """Test deleting nonexistent project."""
        response = client.delete(
            f"/api/projects/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_project_wrong_owner(
        self, client: TestClient, auth_headers_2: dict, test_project: Project
    ):
        """Test deleting project owned by another user."""
        response = client.delete(
            f"/api/projects/{test_project.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    def test_delete_project_cascades_to_tasks(
        self, client: TestClient, auth_headers: dict, test_project: Project,
        test_task: Task, db_session: Session
    ):
        """Test that deleting project cascades to delete tasks."""
        task_id = test_task.id

        response = client.delete(
            f"/api/projects/{test_project.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify task is also deleted
        task = db_session.query(Task).filter(Task.id == task_id).first()
        assert task is None

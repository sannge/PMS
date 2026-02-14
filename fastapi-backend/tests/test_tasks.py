"""Unit tests for Tasks CRUD API endpoints."""

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
class TestListTasks:
    """Tests for listing tasks."""

    async def test_list_tasks_empty(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test listing tasks when none exist."""
        response = await client.get(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_tasks_with_data(
        self, client: AsyncClient, auth_headers: dict, test_project: Project, test_task: Task
    ):
        """Test listing tasks with existing data."""
        response = await client.get(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == test_task.title
        assert data[0]["task_key"] == test_task.task_key
        assert "subtasks_count" in data[0]

    async def test_list_tasks_pagination(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_project: Project, test_user: User
    ):
        """Test pagination of tasks list."""
        # Create multiple tasks
        for i in range(5):
            task = Task(
                title=f"Task {i}",
                task_key=f"TEST-{i+10}",
                project_id=test_project.id,
                reporter_id=test_user.id,
            )
            db_session.add(task)
        await db_session.commit()

        # Test skip and limit
        response = await client.get(
            f"/api/projects/{test_project.id}/tasks?skip=2&limit=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_tasks_search(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_project: Project, test_user: User
    ):
        """Test searching tasks by title."""
        for title, key in [("Login Feature", "T1"), ("Logout Feature", "T2"), ("Profile Page", "T3")]:
            task = Task(title=title, task_key=key, project_id=test_project.id, reporter_id=test_user.id)
            db_session.add(task)
        await db_session.commit()

        response = await client.get(
            f"/api/projects/{test_project.id}/tasks?search=Feature",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_tasks_filter_by_status(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_project: Project, test_user: User
    ):
        """Test filtering tasks by status."""
        for title, key, status in [("T1", "K1", "todo"), ("T2", "K2", "in_progress"), ("T3", "K3", "todo")]:
            task = Task(title=title, task_key=key, status=status, project_id=test_project.id, reporter_id=test_user.id)
            db_session.add(task)
        await db_session.commit()

        response = await client.get(
            f"/api/projects/{test_project.id}/tasks?status=todo",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(t["status"] == "todo" for t in data)

    async def test_list_tasks_filter_by_priority(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_project: Project, test_user: User
    ):
        """Test filtering tasks by priority."""
        for title, key, priority in [("T1", "K1", "high"), ("T2", "K2", "low"), ("T3", "K3", "high")]:
            task = Task(title=title, task_key=key, priority=priority, project_id=test_project.id, reporter_id=test_user.id)
            db_session.add(task)
        await db_session.commit()

        response = await client.get(
            f"/api/projects/{test_project.id}/tasks?priority=high",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(t["priority"] == "high" for t in data)

    async def test_list_tasks_filter_by_type(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_project: Project, test_user: User
    ):
        """Test filtering tasks by type."""
        for title, key, task_type in [("T1", "K1", "bug"), ("T2", "K2", "story"), ("T3", "K3", "bug")]:
            task = Task(title=title, task_key=key, task_type=task_type, project_id=test_project.id, reporter_id=test_user.id)
            db_session.add(task)
        await db_session.commit()

        response = await client.get(
            f"/api/projects/{test_project.id}/tasks?task_type=bug",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(t["task_type"] == "bug" for t in data)

    async def test_list_tasks_nonexistent_project(self, client: AsyncClient, auth_headers: dict):
        """Test listing tasks for nonexistent project."""
        response = await client.get(
            f"/api/projects/{uuid4()}/tasks",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_list_tasks_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_project: Project
    ):
        """Test listing tasks for project owned by another user."""
        response = await client.get(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers_2,
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestCreateTask:
    """Tests for creating tasks."""

    async def test_create_task_success(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test successful task creation."""
        response = await client.post(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
            json={
                "project_id": str(test_project.id),
                "title": "New Task",
                "description": "A new test task",
                "task_type": "story",
                "status": "todo",
                "priority": "high",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Task"
        assert data["task_type"] == "story"
        assert data["status"] == "todo"
        assert data["priority"] == "high"
        assert "task_key" in data
        assert data["task_key"].startswith(test_project.key + "-")

    async def test_create_task_minimal(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test creating a task with minimal data."""
        response = await client.post(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
            json={
                "project_id": str(test_project.id),
                "title": "Minimal Task",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Task"
        assert data["status"] == "todo"  # Default
        assert data["priority"] == "medium"  # Default

    async def test_create_task_with_story_points(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test creating a task with story points."""
        response = await client.post(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
            json={
                "project_id": str(test_project.id),
                "title": "Task with Points",
                "story_points": 5,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["story_points"] == 5

    async def test_create_task_missing_title(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test creating a task without title fails."""
        response = await client.post(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
            json={"project_id": str(test_project.id)},
        )

        assert response.status_code == 422

    async def test_create_task_project_id_mismatch(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Test creating a task with mismatched project ID fails."""
        response = await client.post(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
            json={
                "project_id": str(uuid4()),  # Different ID
                "title": "Task",
            },
        )

        assert response.status_code == 400

    async def test_create_task_nonexistent_project(self, client: AsyncClient, auth_headers: dict):
        """Test creating task in nonexistent project."""
        project_id = uuid4()
        response = await client.post(
            f"/api/projects/{project_id}/tasks",
            headers=auth_headers,
            json={
                "project_id": str(project_id),
                "title": "Task",
            },
        )

        assert response.status_code == 404

    async def test_create_task_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_project: Project
    ):
        """Test creating task in project owned by another user."""
        response = await client.post(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers_2,
            json={
                "project_id": str(test_project.id),
                "title": "Task",
            },
        )

        assert response.status_code == 403

    async def test_create_task_generates_sequential_key(
        self, client: AsyncClient, auth_headers: dict, test_project: Project, test_task: Task
    ):
        """Test that task keys are generated sequentially."""
        response = await client.post(
            f"/api/projects/{test_project.id}/tasks",
            headers=auth_headers,
            json={
                "project_id": str(test_project.id),
                "title": "Second Task",
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Should be TEST-2 since TEST-1 already exists
        assert data["task_key"] == f"{test_project.key}-2"


@pytest.mark.asyncio
class TestGetTask:
    """Tests for getting a single task."""

    async def test_get_task_success(
        self, client: AsyncClient, auth_headers: dict, test_task: Task
    ):
        """Test getting a task by ID."""
        response = await client.get(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_task.id)
        assert data["title"] == test_task.title
        assert data["task_key"] == test_task.task_key
        assert "subtasks_count" in data

    async def test_get_task_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting a nonexistent task."""
        response = await client.get(
            f"/api/tasks/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_task_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_task: Task
    ):
        """Test getting task owned by another user."""
        response = await client.get(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestUpdateTask:
    """Tests for updating tasks."""

    async def test_update_task_success(
        self, client: AsyncClient, auth_headers: dict, test_task: Task
    ):
        """Test successful task update."""
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
            json={
                "title": "Updated Task Title",
                "description": "Updated description",
                "status": "in_progress",
                "priority": "high",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Task Title"
        assert data["status"] == "in_progress"
        assert data["priority"] == "high"

    async def test_update_task_partial(
        self, client: AsyncClient, auth_headers: dict, test_task: Task
    ):
        """Test partial task update."""
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
            json={"status": "done"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        assert data["title"] == test_task.title  # Unchanged

    async def test_update_task_status_transition(
        self, client: AsyncClient, auth_headers: dict, test_task: Task
    ):
        """Test task status transitions."""
        # Move to in_progress
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
            json={"status": "in_progress"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

        # Move to in_review
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
            json={"status": "in_review"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_review"

        # Move to done
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
            json={"status": "done"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "done"

    async def test_update_task_empty_body(
        self, client: AsyncClient, auth_headers: dict, test_task: Task
    ):
        """Test updating task with empty body fails."""
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 400

    async def test_update_task_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test updating nonexistent task."""
        response = await client.put(
            f"/api/tasks/{uuid4()}",
            headers=auth_headers,
            json={"title": "Updated"},
        )

        assert response.status_code == 404

    async def test_update_task_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_task: Task
    ):
        """Test updating task owned by another user."""
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers_2,
            json={"title": "Hacked"},
        )

        assert response.status_code == 403

    async def test_update_task_self_parent_fails(
        self, client: AsyncClient, auth_headers: dict, test_task: Task
    ):
        """Test setting task as its own parent fails."""
        response = await client.put(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
            json={"parent_id": str(test_task.id)},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
class TestDeleteTask:
    """Tests for deleting tasks."""

    async def test_delete_task_success(
        self, client: AsyncClient, auth_headers: dict, test_task: Task
    ):
        """Test successful task deletion."""
        response = await client.delete(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's deleted
        response = await client.get(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_task_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test deleting nonexistent task."""
        response = await client.delete(
            f"/api/tasks/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_task_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_task: Task
    ):
        """Test deleting task owned by another user."""
        response = await client.delete(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    async def test_delete_task_with_subtasks(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_project: Project, test_task: Task, test_user: User
    ):
        """Test deleting task with subtasks cascades deletion."""
        # Create a subtask
        subtask = Task(
            title="Subtask",
            task_key="TEST-SUB",
            project_id=test_project.id,
            parent_id=test_task.id,
            reporter_id=test_user.id,
        )
        db_session.add(subtask)
        await db_session.commit()
        subtask_id = subtask.id

        # Delete parent task
        response = await client.delete(
            f"/api/tasks/{test_task.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify subtask is also deleted
        result = await db_session.execute(select(Task).filter(Task.id == subtask_id))
        subtask = result.scalar_one_or_none()
        assert subtask is None

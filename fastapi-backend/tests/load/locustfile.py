"""
Load Testing for PM Desktop Backend API

Comprehensive load test suite targeting 5,000 concurrent users.
Tests all major API endpoints with realistic usage patterns.

Run with:
    locust -f locustfile.py --host=http://localhost:8001

For headless mode:
    locust -f locustfile.py --host=http://localhost:8001 -u 5000 -r 100 --headless -t 10m
"""

import random
import string
from typing import Optional

from locust import HttpUser, between, task


def random_string(length: int = 8) -> str:
    """Generate a random string for unique test data."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def random_project_key(length: int = 4) -> str:
    """Generate a random project key (uppercase letters only)."""
    return ''.join(random.choices(string.ascii_uppercase, k=length))


class PMUser(HttpUser):
    """
    Simulates a PM Desktop user with realistic behavior patterns.

    Each user:
    1. Registers a new account (or uses existing)
    2. Logs in to get auth token
    3. Performs various operations (browse, create, update)
    """

    wait_time = between(0.5, 2)

    def on_start(self):
        """Initialize user instance and login."""
        # Instance-level state (not shared between users)
        self.token: Optional[str] = None
        self.application_ids: list[str] = []
        self.project_ids: list[str] = []
        self.task_ids: list[str] = []
        self.comment_ids: list[str] = []
        self.checklist_ids: list[str] = []
        self.note_ids: list[str] = []

        self._login()
        self._create_test_data()

    def _login(self):
        """Register and login to get auth token."""
        email = f"loadtest_{random_string(12)}@test.com"
        password = "LoadTest123"  # Simple password without special chars

        # Register new user
        with self.client.post(
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": f"Load Test User {random_string(4)}",
            },
            catch_response=True,
            name="/auth/register",
        ) as resp:
            if resp.status_code == 201:
                resp.success()
            elif resp.status_code == 400:
                # Already exists, ok
                resp.success()
            else:
                resp.failure(f"Registration failed: {resp.status_code}")
                return

        # Login
        with self.client.post(
            "/auth/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            catch_response=True,
            name="/auth/login",
        ) as resp:
            if resp.status_code == 200:
                self.token = resp.json().get("access_token")
                resp.success()
            else:
                resp.failure(f"Login failed: {resp.status_code}")

    def _headers(self) -> dict:
        """Get request headers with auth token."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def _create_test_data(self):
        """Create initial test data for the user."""
        if not self.token:
            return

        # Create an application
        with self.client.post(
            "/api/applications",
            json={
                "name": f"Load Test App {random_string(6)}",
                "description": "Created by load test",
            },
            headers=self._headers(),
            catch_response=True,
            name="/api/applications [POST]",
        ) as resp:
            if resp.status_code == 201:
                app = resp.json()
                self.application_ids.append(app["id"])
                resp.success()

                # Create a project in the application
                with self.client.post(
                    f"/api/applications/{app['id']}/projects",
                    json={
                        "name": f"Load Test Project {random_string(6)}",
                        "key": random_project_key(4),
                        "description": "Created by load test",
                    },
                    headers=self._headers(),
                    catch_response=True,
                    name="/api/applications/{id}/projects [POST]",
                ) as proj_resp:
                    if proj_resp.status_code == 201:
                        proj = proj_resp.json()
                        self.project_ids.append(proj["id"])
                        proj_resp.success()

                        # Create a task
                        with self.client.post(
                            f"/api/projects/{proj['id']}/tasks",
                            json={
                                "title": f"Load Test Task {random_string(6)}",
                                "description": "Created by load test",
                                "status": "todo",
                            },
                            headers=self._headers(),
                            catch_response=True,
                            name="/api/projects/{id}/tasks [POST]",
                        ) as task_resp:
                            if task_resp.status_code == 201:
                                t = task_resp.json()
                                self.task_ids.append(t["id"])
                                task_resp.success()
                            else:
                                task_resp.success()  # Ignore task creation failure
                    else:
                        proj_resp.success()  # Ignore project creation failure
            else:
                resp.success()  # Ignore app creation failure

    # ========== Application Tasks (Weight: 10) ==========

    @task(10)
    def list_applications(self):
        """List all applications - most common operation."""
        if not self.token:
            return
        self.client.get(
            "/api/applications",
            headers=self._headers(),
            name="/api/applications [GET]",
        )

    @task(3)
    def get_application_detail(self):
        """Get application details."""
        if not self.token or not self.application_ids:
            return
        app_id = random.choice(self.application_ids)
        self.client.get(
            f"/api/applications/{app_id}",
            headers=self._headers(),
            name="/api/applications/{id} [GET]",
        )

    @task(1)
    def create_application(self):
        """Create a new application."""
        if not self.token:
            return
        with self.client.post(
            "/api/applications",
            json={
                "name": f"Load Test App {random_string(6)}",
                "description": "Created by load test",
            },
            headers=self._headers(),
            catch_response=True,
            name="/api/applications [POST]",
        ) as resp:
            if resp.status_code == 201:
                app = resp.json()
                self.application_ids.append(app["id"])
                resp.success()
            else:
                resp.failure(f"Create app failed: {resp.status_code}")

    # ========== Project Tasks (Weight: 15) ==========

    @task(8)
    def list_projects(self):
        """List projects in an application."""
        if not self.token or not self.application_ids:
            return
        app_id = random.choice(self.application_ids)
        with self.client.get(
            f"/api/applications/{app_id}/projects",
            headers=self._headers(),
            catch_response=True,
            name="/api/applications/{id}/projects [GET]",
        ) as resp:
            if resp.status_code == 200:
                projects = resp.json()
                for p in projects:
                    if p["id"] not in self.project_ids:
                        self.project_ids.append(p["id"])
                resp.success()
            else:
                resp.failure(f"List projects failed: {resp.status_code}")

    @task(4)
    def get_project_detail(self):
        """Get project details."""
        if not self.token or not self.project_ids:
            return
        proj_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/projects/{proj_id}",
            headers=self._headers(),
            name="/api/projects/{id} [GET]",
        )

    @task(2)
    def create_project(self):
        """Create a new project."""
        if not self.token or not self.application_ids:
            return
        app_id = random.choice(self.application_ids)
        with self.client.post(
            f"/api/applications/{app_id}/projects",
            json={
                "name": f"Load Test Project {random_string(6)}",
                "description": "Created by load test",
            },
            headers=self._headers(),
            catch_response=True,
            name="/api/applications/{id}/projects [POST]",
        ) as resp:
            if resp.status_code == 201:
                proj = resp.json()
                self.project_ids.append(proj["id"])
                resp.success()
            else:
                resp.failure(f"Create project failed: {resp.status_code}")

    # ========== Task Management (Weight: 25) ==========

    @task(15)
    def list_tasks(self):
        """List tasks in a project - most frequent operation."""
        if not self.token or not self.project_ids:
            return
        proj_id = random.choice(self.project_ids)
        with self.client.get(
            f"/api/projects/{proj_id}/tasks",
            headers=self._headers(),
            catch_response=True,
            name="/api/projects/{id}/tasks [GET]",
        ) as resp:
            if resp.status_code == 200:
                tasks = resp.json()
                for t in tasks:
                    if t["id"] not in self.task_ids:
                        self.task_ids.append(t["id"])
                resp.success()
            else:
                resp.failure(f"List tasks failed: {resp.status_code}")

    @task(5)
    def get_task_detail(self):
        """Get task details."""
        if not self.token or not self.task_ids:
            return
        task_id = random.choice(self.task_ids)
        self.client.get(
            f"/api/tasks/{task_id}",
            headers=self._headers(),
            name="/api/tasks/{id} [GET]",
        )

    @task(3)
    def create_task(self):
        """Create a new task."""
        if not self.token or not self.project_ids:
            return
        proj_id = random.choice(self.project_ids)
        with self.client.post(
            f"/api/projects/{proj_id}/tasks",
            json={
                "title": f"Load Test Task {random_string(6)}",
                "description": "Created by load test",
                "status": random.choice(["todo", "in_progress", "review", "done"]),
                "priority": random.choice(["low", "medium", "high", "urgent"]),
            },
            headers=self._headers(),
            catch_response=True,
            name="/api/projects/{id}/tasks [POST]",
        ) as resp:
            if resp.status_code == 201:
                task = resp.json()
                self.task_ids.append(task["id"])
                resp.success()
            else:
                resp.failure(f"Create task failed: {resp.status_code}")

    @task(2)
    def update_task(self):
        """Update a task - simulates status change or edit."""
        if not self.token or not self.task_ids:
            return
        task_id = random.choice(self.task_ids)
        self.client.put(
            f"/api/tasks/{task_id}",
            json={
                "title": f"Updated Task {random_string(6)}",
                "status": random.choice(["todo", "in_progress", "review", "done"]),
            },
            headers=self._headers(),
            name="/api/tasks/{id} [PUT]",
        )

    # ========== Comments (Weight: 8) ==========

    @task(5)
    def list_comments(self):
        """List comments on a task."""
        if not self.token or not self.task_ids:
            return
        task_id = random.choice(self.task_ids)
        with self.client.get(
            f"/api/tasks/{task_id}/comments",
            headers=self._headers(),
            catch_response=True,
            name="/api/tasks/{id}/comments [GET]",
        ) as resp:
            if resp.status_code == 200:
                comments = resp.json()
                self.comment_ids = [c["id"] for c in comments]
                resp.success()
            else:
                resp.failure(f"List comments failed: {resp.status_code}")

    @task(2)
    def create_comment(self):
        """Create a comment on a task."""
        if not self.token or not self.task_ids:
            return
        task_id = random.choice(self.task_ids)
        with self.client.post(
            f"/api/tasks/{task_id}/comments",
            json={"content": f"Load test comment {random_string(20)}"},
            headers=self._headers(),
            catch_response=True,
            name="/api/tasks/{id}/comments [POST]",
        ) as resp:
            if resp.status_code == 201:
                comment = resp.json()
                self.comment_ids.append(comment["id"])
                resp.success()
            else:
                resp.failure(f"Create comment failed: {resp.status_code}")

    # ========== Checklists (Weight: 5) ==========

    @task(3)
    def list_checklists(self):
        """List checklists on a task."""
        if not self.token or not self.task_ids:
            return
        task_id = random.choice(self.task_ids)
        with self.client.get(
            f"/api/tasks/{task_id}/checklists",
            headers=self._headers(),
            catch_response=True,
            name="/api/tasks/{id}/checklists [GET]",
        ) as resp:
            if resp.status_code == 200:
                checklists = resp.json()
                for cl in checklists:
                    if cl["id"] not in self.checklist_ids:
                        self.checklist_ids.append(cl["id"])
                resp.success()
            else:
                resp.failure(f"List checklists failed: {resp.status_code}")

    @task(2)
    def create_checklist(self):
        """Create a checklist on a task."""
        if not self.token or not self.task_ids:
            return
        task_id = random.choice(self.task_ids)
        with self.client.post(
            f"/api/tasks/{task_id}/checklists",
            json={"title": f"Load Test Checklist {random_string(6)}"},
            headers=self._headers(),
            catch_response=True,
            name="/api/tasks/{id}/checklists [POST]",
        ) as resp:
            if resp.status_code == 201:
                checklist = resp.json()
                self.checklist_ids.append(checklist["id"])
                resp.success()
            else:
                resp.failure(f"Create checklist failed: {resp.status_code}")

    # ========== Notifications (Weight: 5) ==========

    @task(3)
    def list_notifications(self):
        """List notifications."""
        if not self.token:
            return
        self.client.get(
            "/api/notifications",
            headers=self._headers(),
            name="/api/notifications [GET]",
        )

    @task(2)
    def get_notification_count(self):
        """Get notification count."""
        if not self.token:
            return
        self.client.get(
            "/api/notifications/count",
            headers=self._headers(),
            name="/api/notifications/count [GET]",
        )

    # ========== Notes (Weight: 5) ==========

    @task(3)
    def list_notes(self):
        """List notes in an application."""
        if not self.token or not self.application_ids:
            return
        app_id = random.choice(self.application_ids)
        with self.client.get(
            f"/api/applications/{app_id}/notes",
            headers=self._headers(),
            catch_response=True,
            name="/api/applications/{id}/notes [GET]",
        ) as resp:
            if resp.status_code == 200:
                notes = resp.json()
                self.note_ids = [n["id"] for n in notes]
                resp.success()
            else:
                resp.failure(f"List notes failed: {resp.status_code}")

    @task(2)
    def create_note(self):
        """Create a note."""
        if not self.token or not self.application_ids:
            return
        app_id = random.choice(self.application_ids)
        with self.client.post(
            f"/api/applications/{app_id}/notes",
            json={
                "title": f"Load Test Note {random_string(6)}",
                "content": f"Content created by load test {random_string(50)}",
                "application_id": app_id,
            },
            headers=self._headers(),
            catch_response=True,
            name="/api/applications/{id}/notes [POST]",
        ) as resp:
            if resp.status_code == 201:
                note = resp.json()
                self.note_ids.append(note["id"])
                resp.success()
            else:
                resp.failure(f"Create note failed: {resp.status_code}")

    # ========== User Profile (Weight: 2) ==========

    @task(2)
    def get_current_user(self):
        """Get current user profile."""
        if not self.token:
            return
        self.client.get(
            "/auth/me",
            headers=self._headers(),
            name="/auth/me [GET]",
        )

    @task(1)
    def search_users(self):
        """Search for users."""
        if not self.token:
            return
        self.client.get(
            f"/api/users/search?email={random_string(3)}",
            headers=self._headers(),
            name="/api/users/search [GET]",
        )

    # ========== Members (Weight: 3) ==========

    @task(2)
    def list_app_members(self):
        """List application members."""
        if not self.token or not self.application_ids:
            return
        app_id = random.choice(self.application_ids)
        self.client.get(
            f"/api/applications/{app_id}/members",
            headers=self._headers(),
            name="/api/applications/{id}/members [GET]",
        )

    @task(1)
    def list_project_members(self):
        """List project members."""
        if not self.token or not self.project_ids:
            return
        proj_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/projects/{proj_id}/members",
            headers=self._headers(),
            name="/api/projects/{id}/members [GET]",
        )

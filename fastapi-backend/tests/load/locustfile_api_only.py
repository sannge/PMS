"""API-only load test file - skips authentication operations.

This test uses pre-authenticated tokens to test CRUD operations
without the bcrypt bottleneck of registration/login.

Run with:
    locust -f locustfile_api_only.py --host=http://localhost:8005 -u 100 -r 10 --headless -t 2m
"""

import random
import string
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner

# Pre-created test data (created manually before test)
TEST_USER_EMAIL = "loadtest4@test.com"
TEST_USER_PASSWORD = "LoadTest123"
TEST_APP_ID = "f0851605-562c-4f4a-a11b-01923eb10ce1"
TEST_PROJECT_ID = "ae2f73a4-f75c-44fe-8078-0acb69cdeac3"
TEST_TASK_ID = "2b53b1b5-60dd-44bf-9919-23711e882993"


class APIOnlyUser(HttpUser):
    """User that tests API operations using a pre-authenticated token."""

    wait_time = between(0.5, 2)  # Faster wait time for API testing

    def on_start(self):
        """Login once to get a token for all requests."""
        response = self.client.post(
            "/auth/login",
            data={
                "username": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            # Store test data
            self.app_id = TEST_APP_ID
            self.project_id = TEST_PROJECT_ID
            self.task_id = TEST_TASK_ID
            self.created_task_ids = []
            self.created_comment_ids = []
        else:
            self.token = None
            self.headers = {}

    # ============ Application Operations (10%) ============

    @task(3)
    def list_applications(self):
        """List all applications."""
        if not self.token:
            return
        self.client.get("/api/applications", headers=self.headers)

    @task(1)
    def get_application(self):
        """Get application details."""
        if not self.token or not self.app_id:
            return
        self.client.get(f"/api/applications/{self.app_id}", headers=self.headers)

    # ============ Project Operations (15%) ============

    @task(4)
    def list_projects(self):
        """List projects in an application."""
        if not self.token or not self.app_id:
            return
        self.client.get(
            f"/api/applications/{self.app_id}/projects",
            headers=self.headers,
        )

    @task(2)
    def get_project(self):
        """Get project details."""
        if not self.token or not self.project_id:
            return
        self.client.get(f"/api/projects/{self.project_id}", headers=self.headers)

    # ============ Task Operations (50%) - Highest traffic ============

    @task(15)
    def list_tasks(self):
        """List all tasks in a project - most common operation."""
        if not self.token or not self.project_id:
            return
        self.client.get(
            f"/api/projects/{self.project_id}/tasks",
            headers=self.headers,
        )

    @task(5)
    def get_task(self):
        """Get task details."""
        if not self.token or not self.task_id:
            return
        self.client.get(f"/api/tasks/{self.task_id}", headers=self.headers)

    @task(3)
    def create_task(self):
        """Create a new task."""
        if not self.token or not self.project_id:
            return
        random_suffix = ''.join(random.choices(string.ascii_lowercase, k=8))
        response = self.client.post(
            f"/api/projects/{self.project_id}/tasks",
            json={
                "title": f"Load Test Task {random_suffix}",
                "description": "Task created during load testing",
                "project_id": self.project_id,
                "task_type": "story",
                "priority": "medium",
            },
            headers=self.headers,
        )
        if response.status_code == 201:
            data = response.json()
            task_id = data.get("id")
            if task_id:
                self.created_task_ids.append(task_id)
                # Keep only last 10 tasks per user to avoid memory growth
                if len(self.created_task_ids) > 10:
                    self.created_task_ids.pop(0)

    @task(2)
    def update_task(self):
        """Update an existing task."""
        if not self.token:
            return
        # Use either pre-existing task or a created one
        task_ids = [self.task_id] + self.created_task_ids
        task_id = random.choice(task_ids) if task_ids else None
        if not task_id:
            return
        self.client.patch(
            f"/api/tasks/{task_id}",
            json={
                "title": f"Updated Task {random.randint(1, 1000)}",
            },
            headers=self.headers,
        )

    # ============ Comment Operations (15%) ============

    @task(4)
    def list_comments(self):
        """List comments on a task."""
        if not self.token or not self.task_id:
            return
        self.client.get(f"/api/tasks/{self.task_id}/comments", headers=self.headers)

    @task(2)
    def create_comment(self):
        """Create a comment on a task."""
        if not self.token:
            return
        # Use either pre-existing task or a created one
        task_ids = [self.task_id] + self.created_task_ids
        task_id = random.choice(task_ids) if task_ids else None
        if not task_id:
            return
        random_suffix = ''.join(random.choices(string.ascii_lowercase, k=8))
        response = self.client.post(
            f"/api/tasks/{task_id}/comments",
            json={
                "body_text": f"Load test comment {random_suffix}",
            },
            headers=self.headers,
        )
        if response.status_code == 201:
            data = response.json()
            comment_id = data.get("id")
            if comment_id:
                self.created_comment_ids.append(comment_id)
                if len(self.created_comment_ids) > 5:
                    self.created_comment_ids.pop(0)

    # ============ Member Operations (5%) ============

    @task(1)
    def list_app_members(self):
        """List application members."""
        if not self.token or not self.app_id:
            return
        self.client.get(
            f"/api/applications/{self.app_id}/members",
            headers=self.headers,
        )

    @task(1)
    def list_project_members(self):
        """List project members."""
        if not self.token or not self.project_id:
            return
        self.client.get(
            f"/api/projects/{self.project_id}/members",
            headers=self.headers,
        )

    # ============ Checklist Operations (5%) ============

    @task(2)
    def list_checklists(self):
        """List checklists for a task."""
        if not self.token or not self.task_id:
            return
        self.client.get(f"/api/tasks/{self.task_id}/checklists", headers=self.headers)


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Print test configuration on startup."""
    if not isinstance(environment.runner, (MasterRunner, WorkerRunner)):
        print("\n" + "=" * 60)
        print("  API-Only Load Test (No Auth Operations)")
        print("  Using pre-authenticated user")
        print("=" * 60 + "\n")

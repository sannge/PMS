"""Load test with shared token - TRUE API-only testing.

This test gets a token ONCE before spawning users, then shares it
across all virtual users. This completely eliminates the bcrypt bottleneck.

Run with:
    locust -f locustfile_shared_token.py --host=http://localhost:8005 -u 100 -r 20 --headless -t 2m
"""

import random
import string
import requests
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner

# Pre-created test data
TEST_USER_EMAIL = "loadtest4@test.com"
TEST_USER_PASSWORD = "LoadTest123"
TEST_APP_ID = "f0851605-562c-4f4a-a11b-01923eb10ce1"
TEST_PROJECT_ID = "ae2f73a4-f75c-44fe-8078-0acb69cdeac3"
TEST_TASK_ID = "2b53b1b5-60dd-44bf-9919-23711e882993"

# Shared token (set once on test start)
SHARED_TOKEN = None
SHARED_HEADERS = None


@events.init.add_listener
def on_locust_init_get_token(environment, **kwargs):
    """Get a single auth token BEFORE ramping up users."""
    global SHARED_TOKEN, SHARED_HEADERS

    print("\n[SETUP] Getting shared auth token (synchronous, before user spawn)...")
    host = environment.host or "http://localhost:8005"

    # Multiple retries for robustness
    for attempt in range(3):
        try:
            response = requests.post(
                f"{host}/auth/login",
                data={
                    "username": TEST_USER_EMAIL,
                    "password": TEST_USER_PASSWORD,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                SHARED_TOKEN = data.get("access_token")
                SHARED_HEADERS = {"Authorization": f"Bearer {SHARED_TOKEN}"}
                print(f"[SETUP] Token obtained successfully!")
                return
            else:
                print(f"[SETUP] Attempt {attempt + 1}: Failed with status {response.status_code}")
        except Exception as e:
            print(f"[SETUP] Attempt {attempt + 1}: Error - {e}")

    print("[SETUP] Failed to get token after 3 attempts!")
    SHARED_TOKEN = None
    SHARED_HEADERS = {}


class SharedTokenUser(HttpUser):
    """User that shares a single auth token with all other users."""

    wait_time = between(0.1, 0.5)  # Fast - we're just testing API capacity

    def on_start(self):
        """Use the shared token - no login needed."""
        self.headers = SHARED_HEADERS
        self.app_id = TEST_APP_ID
        self.project_id = TEST_PROJECT_ID
        self.task_id = TEST_TASK_ID
        self.created_task_ids = []
        self.created_comment_ids = []

    # ============ Application Operations (10%) ============

    @task(3)
    def list_applications(self):
        """List all applications."""
        if not SHARED_TOKEN:
            return
        self.client.get("/api/applications", headers=self.headers)

    @task(1)
    def get_application(self):
        """Get application details."""
        if not SHARED_TOKEN:
            return
        self.client.get(f"/api/applications/{self.app_id}", headers=self.headers)

    # ============ Project Operations (15%) ============

    @task(4)
    def list_projects(self):
        """List projects in an application."""
        if not SHARED_TOKEN:
            return
        self.client.get(
            f"/api/applications/{self.app_id}/projects",
            headers=self.headers,
        )

    @task(2)
    def get_project(self):
        """Get project details."""
        if not SHARED_TOKEN:
            return
        self.client.get(f"/api/projects/{self.project_id}", headers=self.headers)

    # ============ Task Operations (50%) - Highest traffic ============

    @task(15)
    def list_tasks(self):
        """List all tasks in a project - most common operation."""
        if not SHARED_TOKEN:
            return
        self.client.get(
            f"/api/projects/{self.project_id}/tasks",
            headers=self.headers,
        )

    @task(5)
    def get_task(self):
        """Get task details."""
        if not SHARED_TOKEN:
            return
        self.client.get(f"/api/tasks/{self.task_id}", headers=self.headers)

    @task(3)
    def create_task(self):
        """Create a new task."""
        if not SHARED_TOKEN:
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
                if len(self.created_task_ids) > 10:
                    self.created_task_ids.pop(0)

    @task(2)
    def update_task(self):
        """Update an existing task using PUT."""
        if not SHARED_TOKEN:
            return
        task_ids = [self.task_id] + self.created_task_ids
        task_id = random.choice(task_ids) if task_ids else None
        if not task_id:
            return
        # Use PUT instead of PATCH
        self.client.put(
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
        if not SHARED_TOKEN:
            return
        self.client.get(f"/api/tasks/{self.task_id}/comments", headers=self.headers)

    @task(2)
    def create_comment(self):
        """Create a comment on a task."""
        if not SHARED_TOKEN:
            return
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
        if not SHARED_TOKEN:
            return
        self.client.get(
            f"/api/applications/{self.app_id}/members",
            headers=self.headers,
        )

    @task(1)
    def list_project_members(self):
        """List project members."""
        if not SHARED_TOKEN:
            return
        self.client.get(
            f"/api/projects/{self.project_id}/members",
            headers=self.headers,
        )

    # ============ Checklist Operations (5%) ============

    @task(2)
    def list_checklists(self):
        """List checklists for a task."""
        if not SHARED_TOKEN:
            return
        self.client.get(f"/api/tasks/{self.task_id}/checklists", headers=self.headers)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Print test configuration on startup."""
    print("\n" + "=" * 60)
    print("  SHARED TOKEN Load Test")
    print("  Zero auth overhead - pure API testing")
    print(f"  Token acquired: {SHARED_TOKEN is not None}")
    print("=" * 60 + "\n")

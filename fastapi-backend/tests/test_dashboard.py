"""Unit tests for Dashboard API endpoint."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.application_member import ApplicationMember
from app.models.project import Project
from app.models.project_task_status_agg import ProjectTaskStatusAgg
from app.models.task import Task
from app.models.task_status import TaskStatus, StatusName, STATUS_CATEGORY_MAP
from app.models.user import User
from app.utils.timezone import central_today


DASHBOARD_URL = "/api/me/dashboard"


@pytest.mark.asyncio
class TestDashboardEmpty:
    """Tests for dashboard with no data."""

    async def test_dashboard_empty_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A user with no apps should get all zeros and empty arrays."""
        from tests.conftest import get_test_password_hash
        from app.services.auth_service import create_access_token

        # Create a brand new user with no apps
        user = User(
            id=uuid4(),
            email="empty_dashboard@example.com",
            password_hash=get_test_password_hash("EmptyPass123!"),
            display_name="Empty User",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get(DASHBOARD_URL, headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert data["applications_count"] == 0
        assert data["projects_count"] == 0
        assert data["active_tasks_count"] == 0
        assert data["completed_this_week"] == 0
        assert data["overdue_tasks_count"] == 0
        assert data["task_status_breakdown"]["todo"] == 0
        assert data["task_status_breakdown"]["in_progress"] == 0
        assert data["task_status_breakdown"]["in_review"] == 0
        assert data["task_status_breakdown"]["issue"] == 0
        assert data["task_status_breakdown"]["done"] == 0
        assert data["project_health"] == []
        assert data["overdue_tasks"] == []
        assert data["upcoming_tasks"] == []
        assert data["recently_completed"] == []

        # Completion trend should always have 14 entries
        assert len(data["completion_trend"]) == 14
        for point in data["completion_trend"]:
            assert point["count"] == 0


@pytest.mark.asyncio
class TestDashboardWithData:
    """Tests for dashboard with existing fixture data."""

    async def test_dashboard_with_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task: Task,
        test_task_status_todo: TaskStatus,
    ):
        """Verify all response fields with 1 app, 1 project, 1 task in Todo."""
        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Stat cards
        assert data["applications_count"] == 1
        assert data["projects_count"] == 1
        # Task is in Todo category, not Active, so active_tasks_count should be 0
        assert data["active_tasks_count"] == 0
        assert data["completed_this_week"] == 0
        assert data["overdue_tasks_count"] == 0

        # Trends (no completed or active tasks => None)
        assert data["active_tasks_trend"] is None
        assert data["completed_trend"] is None

        # Charts
        assert data["task_status_breakdown"]["todo"] == 0  # Breakdown from agg table, not populated
        assert data["task_status_breakdown"]["in_progress"] == 0
        assert data["task_status_breakdown"]["in_review"] == 0
        assert data["task_status_breakdown"]["issue"] == 0
        assert data["task_status_breakdown"]["done"] == 0

        # Project health should contain the test project
        assert len(data["project_health"]) == 1
        health = data["project_health"][0]
        assert health["name"] == test_project.name
        assert health["key"] == test_project.key
        assert health["total_tasks"] == 0
        assert health["completion_pct"] == 0

        # Completion trend should always have 14 entries
        assert len(data["completion_trend"]) == 14

        # Actionable lists
        assert data["overdue_tasks"] == []
        assert data["upcoming_tasks"] == []
        assert data["recently_completed"] == []

        # Timestamp
        assert "generated_at" in data


@pytest.mark.asyncio
class TestDashboardUnauthenticated:
    """Test that unauthenticated requests are rejected."""

    async def test_dashboard_unauthenticated(self, client: AsyncClient):
        """Call without auth headers should return 401."""
        response = await client.get(DASHBOARD_URL)
        assert response.status_code == 401


@pytest.mark.asyncio
class TestDashboardOverdueTasks:
    """Tests for overdue task detection."""

    async def test_dashboard_overdue_tasks(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """A task with past due_date should appear in overdue_tasks."""
        yesterday = central_today() - timedelta(days=1)
        overdue_task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-OVD",
            title="Overdue Task",
            task_type="story",
            task_status_id=test_task_status_todo.id,
            priority="high",
            due_date=yesterday,
        )
        db_session.add(overdue_task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["overdue_tasks_count"] == 1

        overdue_keys = [t["task_key"] for t in data["overdue_tasks"]]
        assert "TEST-OVD" in overdue_keys

        # Verify the item has expected fields
        overdue_item = next(t for t in data["overdue_tasks"] if t["task_key"] == "TEST-OVD")
        assert overdue_item["title"] == "Overdue Task"
        assert overdue_item["priority"] == "high"
        assert overdue_item["project_name"] == test_project.name
        assert overdue_item["project_key"] == test_project.key


@pytest.mark.asyncio
class TestDashboardCompletedThisWeek:
    """Tests for completed this week count."""

    async def test_dashboard_completed_this_week(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """A task with completed_at = now and Done status should count."""
        # Get the Done status for the test project
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        completed_task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-DONE",
            title="Completed Task",
            task_type="story",
            task_status_id=done_status.id,
            priority="medium",
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(completed_task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["completed_this_week"] == 1


@pytest.mark.asyncio
class TestDashboardCompletionTrend:
    """Tests for completion trend data."""

    async def test_dashboard_completion_trend_14_entries(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
    ):
        """Completion trend should always have exactly 14 entries."""
        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        trend = data["completion_trend"]
        assert len(trend) == 14

        # Verify entries are ordered by date ascending
        dates = [point["date"] for point in trend]
        assert dates == sorted(dates)

        # Verify each entry has date and count
        for point in trend:
            assert "date" in point
            assert "count" in point
            assert isinstance(point["count"], int)
            assert point["count"] == 0

    async def test_dashboard_completion_trend_with_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """Completion trend should reflect tasks completed within 14 days."""
        # Get the Done status for the test project
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        # Create a task completed today
        completed_task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-CT1",
            title="Completed Today",
            task_type="story",
            task_status_id=done_status.id,
            priority="medium",
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(completed_task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        trend = data["completion_trend"]
        # The last entry (today) should have count >= 1
        today_str = central_today().isoformat()
        today_entry = next(
            (p for p in trend if p["date"] == today_str), None
        )
        assert today_entry is not None
        assert today_entry["count"] == 1


@pytest.mark.asyncio
class TestDashboardCrossUserIsolation:
    """Tests for cross-user data isolation."""

    async def test_dashboard_cross_user_isolation(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_application: Application,
        test_project: Project,
        test_task: Task,
    ):
        """User 2 should not see User 1's application/project/task data."""
        response = await client.get(DASHBOARD_URL, headers=auth_headers_2)
        assert response.status_code == 200
        data = response.json()
        assert data["applications_count"] == 0
        assert data["projects_count"] == 0
        assert data["active_tasks_count"] == 0


@pytest.mark.asyncio
class TestDashboardArchivedExclusion:
    """Tests that archived items are excluded."""

    async def test_dashboard_archived_task_excluded(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """Archived tasks should not appear in any counts."""
        yesterday = central_today() - timedelta(days=1)
        archived_task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-ARCH",
            title="Archived Overdue Task",
            task_type="story",
            task_status_id=test_task_status_todo.id,
            priority="high",
            due_date=yesterday,
            archived_at=datetime.now(timezone.utc),
        )
        db_session.add(archived_task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # The archived overdue task should NOT count
        assert data["overdue_tasks_count"] == 0
        overdue_keys = [t["task_key"] for t in data["overdue_tasks"]]
        assert "TEST-ARCH" not in overdue_keys

    async def test_dashboard_archived_project_excluded(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """Archived projects should not be counted in projects_count."""
        archived_project = Project(
            id=uuid4(),
            application_id=test_application.id,
            name="Archived Project",
            key="ARCHP",
            description="An archived project",
            project_type="kanban",
            archived_at=datetime.now(timezone.utc),
            due_date=date.today() + timedelta(days=30),
        )
        db_session.add(archived_project)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # test_project is non-archived so should count; archived project should not
        assert data["projects_count"] == 1
        # The archived project should definitely not be in project_health
        for health in data["project_health"]:
            assert health["key"] != "ARCHP"


@pytest.mark.asyncio
class TestDashboardMemberAccess:
    """Tests for application member access."""

    async def test_dashboard_member_accessed_application(
        self,
        client: AsyncClient,
        auth_headers_2: dict,
        test_application: Application,
        test_project: Project,
        test_user_2: User,
        db_session: AsyncSession,
    ):
        """A user who is an ApplicationMember (not owner) can see that app's data."""
        # Add test_user_2 as a member of test_application
        membership = ApplicationMember(
            id=uuid4(),
            application_id=test_application.id,
            user_id=test_user_2.id,
            role="editor",
        )
        db_session.add(membership)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers_2)
        assert response.status_code == 200

        data = response.json()
        assert data["applications_count"] == 1
        assert data["projects_count"] == 1


@pytest.mark.asyncio
class TestDashboardTrends:
    """Tests for trend calculation branches."""

    async def test_trend_both_zero_returns_none(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
    ):
        """When both current and prior periods have zero, trend should be None."""
        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # No tasks at all => both trends should be None
        assert data["active_tasks_trend"] is None
        assert data["completed_trend"] is None

    async def test_trend_prior_zero_returns_100(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """When prior period is zero but current has data, value should be 100."""
        # Get Done status
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        # Create a task completed recently (within 30 days)
        task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-TR1",
            title="Recent Completed Task",
            task_type="story",
            task_status_id=done_status.id,
            priority="medium",
            completed_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Prior period has 0 completed, current has 1 => value=100, is_positive=True
        assert data["completed_trend"] is not None
        assert data["completed_trend"]["value"] == 100
        assert data["completed_trend"]["is_positive"] is True

    async def test_trend_normal_delta(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """When both periods have data, trend should reflect the delta."""
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        now = datetime.now(timezone.utc)

        # Create tasks completed in prior period (35 and 45 days ago)
        for i, days_ago in enumerate([35, 45]):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"TEST-PRIOR{i}",
                title=f"Prior Completed {i}",
                task_type="story",
                task_status_id=done_status.id,
                priority="medium",
                completed_at=now - timedelta(days=days_ago),
            )
            db_session.add(task)

        # Create tasks completed in current period (5 and 10 days ago)
        for i, days_ago in enumerate([5, 10]):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"TEST-CURR{i}",
                title=f"Current Completed {i}",
                task_type="story",
                task_status_id=done_status.id,
                priority="medium",
                completed_at=now - timedelta(days=days_ago),
            )
            db_session.add(task)

        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Both periods have 2 tasks => diff=0, trend returns None (no change)
        assert data["completed_trend"] is None


@pytest.mark.asyncio
class TestDashboardRecentlyCompletedFilter:
    """Tests for recently_completed Done category filter."""

    async def test_recently_completed_excludes_non_done(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """A task with completed_at set but NOT in Done status should NOT appear in recently_completed."""
        # Create a task with completed_at but still in Todo status
        task_not_done = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-NOTDONE",
            title="Not Actually Done",
            task_type="story",
            task_status_id=test_task_status_todo.id,  # Todo, not Done
            priority="medium",
            completed_at=datetime.now(timezone.utc),  # Has completed_at
        )
        db_session.add(task_not_done)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        recently_keys = [t["task_key"] for t in data["recently_completed"]]
        assert "TEST-NOTDONE" not in recently_keys


@pytest.mark.asyncio
class TestDashboardUpcomingTasksBoundary:
    """Tests for upcoming tasks date boundary handling."""

    async def test_upcoming_tasks_boundary(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """Test tasks at due_date boundaries (today, today+14, today+15)."""
        today = central_today()

        # Task due today - should appear
        task_today = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-TODAY",
            title="Due Today",
            task_type="story",
            task_status_id=test_task_status_todo.id,
            priority="medium",
            due_date=today,
        )
        # Task due in 14 days - should appear (boundary inclusive)
        task_14 = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-14D",
            title="Due in 14 days",
            task_type="story",
            task_status_id=test_task_status_todo.id,
            priority="medium",
            due_date=today + timedelta(days=14),
        )
        # Task due in 15 days - should NOT appear
        task_15 = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-15D",
            title="Due in 15 days",
            task_type="story",
            task_status_id=test_task_status_todo.id,
            priority="medium",
            due_date=today + timedelta(days=15),
        )
        db_session.add_all([task_today, task_14, task_15])
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        upcoming_keys = [t["task_key"] for t in data["upcoming_tasks"]]
        assert "TEST-TODAY" in upcoming_keys
        assert "TEST-14D" in upcoming_keys
        assert "TEST-15D" not in upcoming_keys


@pytest.mark.asyncio
class TestDashboardOverdueTasksLimit:
    """Tests for overdue tasks list cap."""

    async def test_overdue_tasks_capped_at_5(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """Create 6 overdue tasks, verify list is capped at 5."""
        yesterday = central_today() - timedelta(days=1)
        for i in range(6):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"TEST-OVD{i}",
                title=f"Overdue Task {i}",
                task_type="story",
                task_status_id=test_task_status_todo.id,
                priority="high",
                due_date=yesterday - timedelta(days=i),
            )
            db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["overdue_tasks"]) == 5
        # But the count should reflect all 6
        assert data["overdue_tasks_count"] == 6


@pytest.mark.asyncio
class TestDashboardMultiAppAggregation:
    """Tests for multi-application aggregation."""

    async def test_multi_app_aggregation(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Create 2 apps with 2 projects each, verify counts sum correctly."""
        apps = []
        projects = []
        for app_i in range(2):
            app = Application(
                id=uuid4(),
                name=f"Multi App {app_i}",
                description=f"Multi app {app_i}",
                owner_id=test_user.id,
            )
            db_session.add(app)
            await db_session.flush()
            apps.append(app)

            for proj_i in range(2):
                proj = Project(
                    id=uuid4(),
                    application_id=app.id,
                    name=f"Multi Project {app_i}-{proj_i}",
                    key=f"MP{app_i}{proj_i}",
                    description=f"Multi project {app_i}-{proj_i}",
                    project_type="kanban",
                    due_date=date.today() + timedelta(days=30),
                )
                db_session.add(proj)
                await db_session.flush()
                projects.append(proj)

                # Create default statuses
                statuses = TaskStatus.create_default_statuses(proj.id)
                for status in statuses:
                    db_session.add(status)

        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["applications_count"] == 2
        assert data["projects_count"] == 4


@pytest.mark.asyncio
class TestDashboardActiveTasksAssigneeFilter:
    """Tests that active_tasks_count only counts tasks assigned to the current user."""

    async def test_active_tasks_counts_only_assigned_to_user(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """A task in Active category assigned to user should count; unassigned should not."""
        # Get the In Progress status (Active category) for the test project
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.IN_PROGRESS.value,
            )
        )
        in_progress_status = result.scalar_one()

        # Create a task assigned to test_user
        assigned_task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-ASSIGNED",
            title="Assigned Active Task",
            task_type="story",
            task_status_id=in_progress_status.id,
            priority="medium",
            assignee_id=test_user.id,
        )
        db_session.add(assigned_task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["active_tasks_count"] == 1

        # Now create a task with NO assignee (should not be counted)
        unassigned_task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-UNASSIGNED",
            title="Unassigned Active Task",
            task_type="story",
            task_status_id=in_progress_status.id,
            priority="medium",
            assignee_id=None,
        )
        db_session.add(unassigned_task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Still 1 — the unassigned task should NOT be counted
        assert data["active_tasks_count"] == 1


@pytest.mark.asyncio
class TestDashboardStatusAggBreakdown:
    """Tests for task_status_breakdown from ProjectTaskStatusAgg."""

    async def test_status_breakdown_with_agg_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """ProjectTaskStatusAgg row with non-zero values should reflect in breakdown."""
        agg = ProjectTaskStatusAgg(
            project_id=test_project.id,
            total_tasks=20,
            todo_tasks=5,
            active_tasks=4,
            review_tasks=3,
            issue_tasks=2,
            done_tasks=6,
        )
        db_session.add(agg)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        breakdown = data["task_status_breakdown"]
        assert breakdown["todo"] == 5
        assert breakdown["in_progress"] == 4
        assert breakdown["in_review"] == 3
        assert breakdown["issue"] == 2
        assert breakdown["done"] == 6


@pytest.mark.asyncio
class TestDashboardProjectHealthLimit:
    """Tests for project_health limit of 10."""

    async def test_project_health_capped_at_10(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Create 12 projects across apps, verify project_health is capped at 10."""
        app = Application(
            id=uuid4(),
            name="Health Limit App",
            description="App for health limit test",
            owner_id=test_user.id,
        )
        db_session.add(app)
        await db_session.flush()

        for i in range(12):
            proj = Project(
                id=uuid4(),
                application_id=app.id,
                name=f"Health Project {i}",
                key=f"HP{i:02d}",
                description=f"Health project {i}",
                project_type="kanban",
                due_date=date.today() + timedelta(days=30),
            )
            db_session.add(proj)
            await db_session.flush()
            statuses = TaskStatus.create_default_statuses(proj.id)
            for status in statuses:
                db_session.add(status)

        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["project_health"]) == 10


@pytest.mark.asyncio
class TestDashboardUpcomingTasksLimit:
    """Tests for upcoming_tasks limit of 10."""

    async def test_upcoming_tasks_capped_at_10(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """Create 12 tasks with due_date in next 14 days, verify limit of 10."""
        today = central_today()
        for i in range(12):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"TEST-UP{i:02d}",
                title=f"Upcoming Task {i}",
                task_type="story",
                task_status_id=test_task_status_todo.id,
                priority="medium",
                due_date=today + timedelta(days=i + 1),
            )
            db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["upcoming_tasks"]) == 10


@pytest.mark.asyncio
class TestDashboardRecentlyCompletedLimit:
    """Tests for recently_completed limit of 5."""

    async def test_recently_completed_capped_at_5(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """Create 7 Done tasks completed in last 7 days, verify limit of 5."""
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        now = datetime.now(timezone.utc)
        for i in range(7):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"TEST-RC{i}",
                title=f"Recently Completed {i}",
                task_type="story",
                task_status_id=done_status.id,
                priority="medium",
                completed_at=now - timedelta(hours=i + 1),
            )
            db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["recently_completed"]) == 5


@pytest.mark.asyncio
class TestDashboardCompletedThisWeekMonday:
    """Tests for completed_this_week Monday boundary."""

    async def test_completed_this_week_monday_boundary(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """Task completed last Sunday should not count; task completed this Monday should count."""
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        today = central_today()
        # Monday of current week
        monday = today - timedelta(days=today.weekday())
        # Last Sunday = Monday - 1 day
        last_sunday = monday - timedelta(days=1)

        # Task completed last Sunday (should NOT count)
        task_sunday = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-SUN",
            title="Completed Sunday",
            task_type="story",
            task_status_id=done_status.id,
            priority="medium",
            completed_at=datetime.combine(last_sunday, datetime.min.time()),
        )
        # Task completed this Monday (should count)
        task_monday = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-MON",
            title="Completed Monday",
            task_type="story",
            task_status_id=done_status.id,
            priority="medium",
            completed_at=datetime.combine(monday, datetime.min.time()),
        )
        db_session.add_all([task_sunday, task_monday])
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Only the Monday task should count
        assert data["completed_this_week"] == 1


@pytest.mark.asyncio
class TestDashboardOverdueExcludesDone:
    """Tests that overdue excludes Done tasks."""

    async def test_overdue_excludes_done_tasks(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """A task with due_date yesterday but status=Done should not be overdue."""
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        yesterday = central_today() - timedelta(days=1)
        task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-DONE-OVD",
            title="Done but past due",
            task_type="story",
            task_status_id=done_status.id,
            priority="medium",
            due_date=yesterday,
        )
        db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["overdue_tasks_count"] == 0


@pytest.mark.asyncio
class TestDashboardNullDueDateNotOverdue:
    """Tests that NULL due_date is not counted as overdue."""

    async def test_null_due_date_not_overdue(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """A task with due_date=None and active status should not be overdue."""
        task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-NODUE",
            title="No Due Date",
            task_type="story",
            task_status_id=test_task_status_todo.id,
            priority="medium",
            due_date=None,
        )
        db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["overdue_tasks_count"] == 0


@pytest.mark.asyncio
class TestDashboardActiveTrendWithData:
    """Tests for active_tasks_trend with data (inverted polarity)."""

    async def test_active_tasks_trend_inverted_polarity(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Create active tasks in current period only; trend should be is_positive=False."""
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.IN_PROGRESS.value,
            )
        )
        in_progress_status = result.scalar_one()

        now = datetime.now(timezone.utc)
        # Create active tasks created recently (within 30 days) — current period
        for i in range(3):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"TEST-ACT{i}",
                title=f"Active Task {i}",
                task_type="story",
                task_status_id=in_progress_status.id,
                priority="medium",
                created_at=now - timedelta(days=i + 1),
            )
            db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Current active > 0, prior active = 0 => value=100, is_positive=False
        assert data["active_tasks_trend"] is not None
        assert data["active_tasks_trend"]["value"] == 100
        assert data["active_tasks_trend"]["is_positive"] is False


@pytest.mark.asyncio
class TestDashboardCompletedTrendNegative:
    """Tests for completed_trend with negative delta."""

    async def test_completed_trend_negative_delta(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """More tasks in prior 30d than current 30d should show is_positive=False."""
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status = result.scalar_one()

        now = datetime.now(timezone.utc)

        # 3 tasks in prior period (35, 40, 50 days ago)
        for i, days_ago in enumerate([35, 40, 50]):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"TEST-PNEG{i}",
                title=f"Prior Negative {i}",
                task_type="story",
                task_status_id=done_status.id,
                priority="medium",
                completed_at=now - timedelta(days=days_ago),
            )
            db_session.add(task)

        # 1 task in current period (5 days ago)
        task_current = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="TEST-CNEG0",
            title="Current Negative 0",
            task_type="story",
            task_status_id=done_status.id,
            priority="medium",
            completed_at=now - timedelta(days=5),
        )
        db_session.add(task_current)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # current=1, prior=3, diff=-2, pct=66 (abs(2*100)//3), is_positive=False
        assert data["completed_trend"] is not None
        assert data["completed_trend"]["value"] == 66
        assert data["completed_trend"]["is_positive"] is False


@pytest.mark.asyncio
class TestDashboardProjectHealthFields:
    """Tests for project_health field completeness."""

    async def test_project_health_field_completeness(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """ProjectTaskStatusAgg with total=10, done=3 should show completion_pct=30 and all fields."""
        agg = ProjectTaskStatusAgg(
            project_id=test_project.id,
            total_tasks=10,
            todo_tasks=2,
            active_tasks=3,
            review_tasks=1,
            issue_tasks=1,
            done_tasks=3,
        )
        db_session.add(agg)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["project_health"]) >= 1

        health = next(
            h for h in data["project_health"] if h["key"] == test_project.key
        )
        assert health["completion_pct"] == 30
        assert health["total_tasks"] == 10
        assert health["done_tasks"] == 3
        assert health["issue_tasks"] == 1
        assert health["review_tasks"] == 1
        assert health["active_tasks"] == 3
        assert health["id"] == str(test_project.id)
        assert health["name"] == test_project.name
        assert health["key"] == test_project.key
        assert health["application_id"] == str(test_application.id)
        assert health["application_name"] == test_application.name
        assert "derived_status" in health


@pytest.mark.asyncio
class TestDashboardOverdueSortOrder:
    """Tests for overdue tasks sort order."""

    async def test_overdue_tasks_sorted_ascending(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_task_status_todo: TaskStatus,
        db_session: AsyncSession,
    ):
        """Overdue tasks should be returned in ascending due_date order (most overdue first)."""
        today = central_today()
        # Create 3 overdue tasks with different due dates
        dates_and_keys = [
            (today - timedelta(days=3), "TEST-OVD-3"),
            (today - timedelta(days=1), "TEST-OVD-1"),
            (today - timedelta(days=5), "TEST-OVD-5"),
        ]
        for due, key in dates_and_keys:
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=key,
                title=f"Overdue {key}",
                task_type="story",
                task_status_id=test_task_status_todo.id,
                priority="medium",
                due_date=due,
            )
            db_session.add(task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        overdue_dates = [t["due_date"] for t in data["overdue_tasks"]]
        assert overdue_dates == sorted(overdue_dates)


@pytest.mark.asyncio
class TestDashboardCacheControlHeader:
    """Tests for Cache-Control header."""

    async def test_cache_control_header(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
    ):
        """Response should include Cache-Control: no-store, no-cache header."""
        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, no-cache"


@pytest.mark.asyncio
class TestDashboardAllProjectsArchived:
    """Tests for dashboard when all projects are archived."""

    async def test_apps_with_only_archived_projects(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        db_session: AsyncSession,
    ):
        """User has apps but all projects are archived."""
        # Create a project and archive it
        project = Project(
            id=uuid4(),
            application_id=test_application.id,
            name="Archived",
            key="ARC",
            description="Archived project",
            project_type="kanban",
            due_date=date.today() + timedelta(days=30),
            archived_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["applications_count"] == 1
        assert data["projects_count"] == 0
        assert data["active_tasks_count"] == 0


@pytest.mark.asyncio
class TestDashboardActiveTrendNormalDelta:
    """Tests for active_tasks_trend with tasks in both periods."""

    async def test_active_trend_normal_delta(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_application: Application,
        test_project: Project,
        test_user: User,
        db_session: AsyncSession,
    ):
        """Active trend with tasks in both periods."""
        # Get an active status (multiple may exist: In Progress, In Review)
        result = await db_session.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == test_project.id,
                TaskStatus.category == "Active",
            )
        )
        active_status = result.scalars().first()

        now = datetime.now(timezone.utc)
        # 2 tasks created in current period (last 30 days), assigned to user
        for i in range(2):
            task = Task(
                id=uuid4(),
                project_id=test_project.id,
                task_key=f"CUR-{i}",
                title=f"Current {i}",
                task_type="story",
                task_status_id=active_status.id,
                priority="medium",
                assignee_id=test_user.id,
                created_at=now - timedelta(days=10),
            )
            db_session.add(task)

        # 1 task created in prior period (30-60 days ago), still active, assigned to user
        prior_task = Task(
            id=uuid4(),
            project_id=test_project.id,
            task_key="PRI-0",
            title="Prior Active",
            task_type="story",
            task_status_id=active_status.id,
            priority="medium",
            assignee_id=test_user.id,
            created_at=now - timedelta(days=45),
        )
        db_session.add(prior_task)
        await db_session.commit()

        response = await client.get(DASHBOARD_URL, headers=auth_headers)
        data = response.json()
        trend = data["active_tasks_trend"]
        assert trend is not None
        # current=3 (all assigned active), prior=1 (created 30-60d ago still active)
        # diff = 3-1 = 2, pct = 200//1 = 200, is_positive = diff < 0 = False (more active = bad)
        assert trend["value"] == 200
        assert trend["is_positive"] is False

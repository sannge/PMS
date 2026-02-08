"""
Create fake projects and tasks ready to be archived for testing.

Usage:
    cd fastapi-backend
    python scripts/create_archivable_data.py

This creates:
- 1 Application: "Archive Test App"
- 2 Projects with tasks ready for archiving
- Tasks in Done status completed 8+ days ago
"""

import asyncio
import sys
from datetime import datetime, timedelta
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, ".")

from sqlalchemy import select
from app.database import async_session_maker
from app.models import Application, Project, Task, User
from app.models.task_status import TaskStatus, StatusName


async def create_archivable_data():
    """Create test data for archive testing."""

    async with async_session_maker() as db:
        # Find or create a test user
        result = await db.execute(
            select(User).where(User.email == "archive-test@example.com")
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                id=uuid4(),
                email="archive-test@example.com",
                password_hash="not-a-real-hash",
                display_name="Archive Test User",
            )
            db.add(user)
            await db.flush()
            print(f"[OK] Created user: {user.email}")
        else:
            print(f"-> Using existing user: {user.email}")

        # Create test application
        app_name = f"Archive Test App {datetime.now().strftime('%H%M%S')}"
        application = Application(
            id=uuid4(),
            name=app_name,
            description="Test application for archive testing",
            owner_id=user.id,
        )
        db.add(application)
        await db.flush()
        print(f"[OK] Created application: {app_name}")

        # Create Project 1: All tasks done and old (should be archived after tasks are archived)
        project1_key = f"ARC{uuid4().hex[:4].upper()}"
        project1 = Project(
            id=uuid4(),
            application_id=application.id,
            name="Project Ready to Archive",
            key=project1_key,
            description="All tasks are done for 8+ days - project should be archived",
            project_type="kanban",
            due_date=datetime.now().date(),
        )
        db.add(project1)
        await db.flush()

        # Create statuses for project 1
        statuses1 = TaskStatus.create_default_statuses(project1.id)
        for status in statuses1:
            db.add(status)
        await db.flush()

        # Get Done status for project 1
        result = await db.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == project1.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status1 = result.scalar_one()

        print(f"[OK] Created project: {project1_key} - {project1.name}")

        # Create 3 archivable tasks for project 1 (done 8-15 days ago)
        for i in range(3):
            days_ago = 8 + i * 3  # 8, 11, 14 days ago
            task = Task(
                id=uuid4(),
                project_id=project1.id,
                task_key=f"{project1_key}-{i+1}",
                title=f"Old Done Task {i+1} (done {days_ago} days ago)",
                description=f"This task was completed {days_ago} days ago and should be archived",
                task_type="story",
                task_status_id=done_status1.id,
                priority="medium",
                reporter_id=user.id,
                completed_at=datetime.utcnow() - timedelta(days=days_ago),
            )
            db.add(task)
            print(f"  [OK] Created task: {task.task_key} (done {days_ago} days ago)")

        # Create Project 2: Mixed tasks (some archivable, some not)
        project2_key = f"MIX{uuid4().hex[:4].upper()}"
        project2 = Project(
            id=uuid4(),
            application_id=application.id,
            name="Project With Mixed Tasks",
            key=project2_key,
            description="Some tasks archivable, some active - project should NOT be archived",
            project_type="kanban",
            due_date=datetime.now().date(),
        )
        db.add(project2)
        await db.flush()

        # Create statuses for project 2
        statuses2 = TaskStatus.create_default_statuses(project2.id)
        for status in statuses2:
            db.add(status)
        await db.flush()

        # Get statuses for project 2
        result = await db.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == project2.id,
                TaskStatus.name == StatusName.DONE.value,
            )
        )
        done_status2 = result.scalar_one()

        result = await db.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == project2.id,
                TaskStatus.name == StatusName.TODO.value,
            )
        )
        todo_status2 = result.scalar_one()

        result = await db.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == project2.id,
                TaskStatus.name == StatusName.IN_PROGRESS.value,
            )
        )
        in_progress_status2 = result.scalar_one()

        print(f"[OK] Created project: {project2_key} - {project2.name}")

        # Create archivable task (done 10 days ago)
        task_old = Task(
            id=uuid4(),
            project_id=project2.id,
            task_key=f"{project2_key}-1",
            title="Old Done Task (done 10 days ago)",
            description="This task should be archived",
            task_type="story",
            task_status_id=done_status2.id,
            priority="medium",
            reporter_id=user.id,
            completed_at=datetime.utcnow() - timedelta(days=10),
        )
        db.add(task_old)
        print(f"  [OK] Created task: {task_old.task_key} (done 10 days ago - ARCHIVABLE)")

        # Create recent done task (done 2 days ago - should NOT be archived)
        task_recent = Task(
            id=uuid4(),
            project_id=project2.id,
            task_key=f"{project2_key}-2",
            title="Recent Done Task (done 2 days ago)",
            description="This task should NOT be archived yet",
            task_type="story",
            task_status_id=done_status2.id,
            priority="medium",
            reporter_id=user.id,
            completed_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add(task_recent)
        print(f"  [OK] Created task: {task_recent.task_key} (done 2 days ago - NOT archivable)")

        # Create active task (in progress)
        task_active = Task(
            id=uuid4(),
            project_id=project2.id,
            task_key=f"{project2_key}-3",
            title="Active Task (in progress)",
            description="This task is still being worked on",
            task_type="story",
            task_status_id=in_progress_status2.id,
            priority="high",
            reporter_id=user.id,
        )
        db.add(task_active)
        print(f"  [OK] Created task: {task_active.task_key} (in progress - NOT archivable)")

        # Create todo task
        task_todo = Task(
            id=uuid4(),
            project_id=project2.id,
            task_key=f"{project2_key}-4",
            title="Todo Task (not started)",
            description="This task hasn't been started",
            task_type="story",
            task_status_id=todo_status2.id,
            priority="low",
            reporter_id=user.id,
        )
        db.add(task_todo)
        print(f"  [OK] Created task: {task_todo.task_key} (todo - NOT archivable)")

        await db.commit()

        print("\n" + "=" * 60)
        print("TEST DATA CREATED SUCCESSFULLY")
        print("=" * 60)
        print(f"""
Summary:
  Application: {app_name}

  Project 1: {project1_key} - "Project Ready to Archive"
    - 3 tasks done 8+ days ago (ALL should be archived)
    - After archiving tasks, project should also be archived

  Project 2: {project2_key} - "Project With Mixed Tasks"
    - 1 task done 10 days ago (should be archived)
    - 1 task done 2 days ago (should NOT be archived)
    - 1 task in progress (should NOT be archived)
    - 1 task todo (should NOT be archived)
    - Project should NOT be archived (has active tasks)

To test archiving:
  1. Run: python -c "
import asyncio
from arq.connections import create_pool
from app.worker import parse_redis_url
from app.config import settings

async def main():
    pool = await create_pool(parse_redis_url(settings.redis_url))
    job = await pool.enqueue_job('run_archive_jobs')
    print(f'Job ID: {{job.job_id}}')
    result = await job.result(timeout=60)
    print(f'Result: {{result}}')
    await pool.close()

asyncio.run(main())
"

  2. Or use the API endpoint:
     curl -X POST http://localhost:8001/api/admin/run-archive-jobs

Expected result:
  - 4 tasks archived (3 from project 1, 1 from project 2)
  - 1 project archived (project 1)
""")


if __name__ == "__main__":
    asyncio.run(create_archivable_data())

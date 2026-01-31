"""
Script to insert 80 archived projects for testing.

Each project will have:
- At least 1 task in Done status
- Tasks completed and archived more than 7 days ago
- Project members from the specified users

Run from fastapi-backend directory:
    python scripts/insert_archived_projects.py
"""

import asyncio
import uuid
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Database connection - same as insert_archived_tasks.py
DB_URL = "postgresql+asyncpg://pmsdbuser:never%21again@10.18.137.202:5432/pmsdb"

# Configuration
USER_EMAILS = [
    "samngestep@gmail.com",
    "samngestep2@gmail.com",
    "bellaeaint@gmail.com",
]
APPLICATION_NAME = "WMS3"
NUM_PROJECTS = 80
DAYS_AGO = 10  # Tasks completed this many days ago

# Task title templates
TASK_TITLES = [
    "Implement inventory sync module",
    "Fix barcode scanner integration",
    "Update warehouse layout algorithm",
    "Optimize picking route calculation",
    "Add batch processing for shipments",
    "Create stock level alerts",
    "Implement cycle counting feature",
    "Fix receiving dock assignment",
    "Update packing slip template",
    "Add support for multiple warehouses",
    "Implement wave planning",
    "Fix order allocation logic",
    "Create inventory adjustment workflow",
    "Add putaway strategy configuration",
    "Implement zone-based picking",
    "Fix carrier integration timeout",
    "Update shipping label format",
    "Add inventory forecasting",
    "Implement return processing",
    "Fix stock transfer validation",
]

# Project name templates
PROJECT_NAMES = [
    "Inventory Management System",
    "Order Processing Module",
    "Warehouse Automation",
    "Shipping Integration",
    "Stock Control System",
    "Picking Optimization",
    "Receiving Module",
    "Packing Station",
    "Returns Processing",
    "Analytics Dashboard",
    "Mobile Scanner App",
    "Label Printing System",
    "Zone Management",
    "Batch Processing",
    "Carrier Integration",
    "Report Generator",
    "Audit Trail System",
    "Notification Service",
    "API Gateway",
    "Data Sync Engine",
]


async def main():
    """Main function to insert archived projects."""
    print(f"Creating {NUM_PROJECTS} archived projects in '{APPLICATION_NAME}'...")

    # Create engine
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            from sqlalchemy import text

            # Get users - use ANY with array for asyncpg compatibility
            result = await db.execute(
                text("""SELECT id, email FROM "Users" WHERE email = ANY(:emails)"""),
                {"emails": USER_EMAILS}
            )
            users_data = result.fetchall()

            if len(users_data) != len(USER_EMAILS):
                found_emails = [u[1] for u in users_data]
                missing = [e for e in USER_EMAILS if e not in found_emails]
                raise ValueError(f"Missing users: {missing}")

            users = [{"id": row[0], "email": row[1]} for row in users_data]
            print(f"Found {len(users)} users: {[u['email'] for u in users]}")

            # Get application
            result = await db.execute(
                __import__("sqlalchemy", fromlist=["text"]).text(
                    f"""SELECT id, name FROM "Applications" WHERE name = :name"""
                ),
                {"name": APPLICATION_NAME}
            )
            app_row = result.fetchone()

            if not app_row:
                raise ValueError(f"Application '{APPLICATION_NAME}' not found")

            app_id = app_row[0]
            print(f"Found application: {app_row[1]} (ID: {app_id})")

            # Calculate timestamps
            now = datetime.utcnow()
            completed_at = now - timedelta(days=DAYS_AGO)
            archived_at = now - timedelta(days=DAYS_AGO - 1)
            created_at = completed_at - timedelta(days=30)

            print(f"Tasks will be completed at: {completed_at}")
            print(f"Tasks will be archived at: {archived_at}")

            # Create projects using raw SQL for better control
            for i in range(NUM_PROJECTS):
                # Rotate through users for ownership
                owner = users[i % len(users)]
                project_id = uuid.uuid4()
                project_key = f"AP{i + 1:03d}"
                project_name_base = PROJECT_NAMES[i % len(PROJECT_NAMES)]
                project_name = f"{project_name_base} - Archive Test {i + 1:03d}"

                # Insert project
                await db.execute(text("""
                    INSERT INTO "Projects" (
                        id, application_id, name, key, description, project_type,
                        created_by, project_owner_user_id, next_task_number,
                        row_version, created_at, updated_at, archived_at
                    ) VALUES (
                        :id, :app_id, :name, :key, :desc, :type,
                        :created_by, :owner_id, :next_task,
                        1, :created_at, :updated_at, NULL
                    )
                """), {
                    "id": project_id,
                    "app_id": app_id,
                    "name": project_name,
                    "key": project_key,
                    "desc": f"Archived test project #{i + 1}",
                    "type": "kanban",
                    "created_by": owner["id"],
                    "owner_id": owner["id"],
                    "next_task": 1,
                    "created_at": created_at,
                    "updated_at": archived_at,
                })

                # Create TaskStatuses
                status_data = [
                    ("Todo", "Todo", 0),
                    ("In Progress", "Active", 1),
                    ("In Review", "Active", 2),
                    ("Issue", "Issue", 3),
                    ("Done", "Done", 4),
                ]
                done_status_id = None

                for status_name, category, rank in status_data:
                    status_id = uuid.uuid4()
                    if status_name == "Done":
                        done_status_id = status_id

                    await db.execute(text("""
                        INSERT INTO "TaskStatuses" (id, project_id, name, category, rank, created_at)
                        VALUES (:id, :project_id, :name, :category, :rank, :created_at)
                    """), {
                        "id": status_id,
                        "project_id": project_id,
                        "name": status_name,
                        "category": category,
                        "rank": rank,
                        "created_at": created_at,
                    })

                # Update project's derived_status_id to Done
                await db.execute(text("""
                    UPDATE "Projects" SET derived_status_id = :status_id WHERE id = :project_id
                """), {
                    "status_id": done_status_id,
                    "project_id": project_id,
                })

                # Create tasks (1-3 per project, all archived)
                num_tasks = (i % 3) + 1
                for task_idx in range(num_tasks):
                    assignee = users[(i + task_idx) % len(users)]
                    reporter = users[(i + task_idx + 1) % len(users)]
                    task_id = uuid.uuid4()
                    task_key = f"{project_key}-{task_idx + 1}"
                    task_title = TASK_TITLES[(i + task_idx) % len(TASK_TITLES)]

                    await db.execute(text("""
                        INSERT INTO "Tasks" (
                            id, project_id, task_status_id, task_key, title, description,
                            task_type, status, priority, assignee_id, reporter_id,
                            story_points, row_version, checklist_total, checklist_done,
                            created_at, updated_at, completed_at, archived_at
                        ) VALUES (
                            :id, :project_id, :status_id, :key, :title, :desc,
                            :type, :status, :priority, :assignee, :reporter,
                            :points, 1, 0, 0,
                            :created_at, :updated_at, :completed_at, :archived_at
                        )
                    """), {
                        "id": task_id,
                        "project_id": project_id,
                        "status_id": done_status_id,
                        "key": task_key,
                        "title": task_title,
                        "desc": f"Completed task for archive testing",
                        "type": "story",
                        "status": "done",
                        "priority": "medium",
                        "assignee": assignee["id"],
                        "reporter": reporter["id"],
                        "points": (task_idx + 1) * 2,
                        "created_at": created_at + timedelta(days=task_idx),
                        "updated_at": completed_at,
                        "completed_at": completed_at,
                        "archived_at": archived_at,
                    })

                # Update project's next_task_number
                await db.execute(text("""
                    UPDATE "Projects" SET next_task_number = :num WHERE id = :project_id
                """), {
                    "num": num_tasks + 1,
                    "project_id": project_id,
                })

                # Create ProjectTaskStatusAgg (all zeros since tasks are archived)
                await db.execute(text("""
                    INSERT INTO "ProjectTaskStatusAgg" (
                        project_id, total_tasks, todo_tasks, active_tasks,
                        review_tasks, issue_tasks, done_tasks, updated_at
                    ) VALUES (
                        :project_id, 0, 0, 0, 0, 0, 0, :updated_at
                    )
                """), {
                    "project_id": project_id,
                    "updated_at": archived_at,
                })

                # Create ProjectMember records
                for idx, user in enumerate(users):
                    role = "admin" if user["id"] == owner["id"] else "member"
                    member_id = uuid.uuid4()

                    await db.execute(text("""
                        INSERT INTO "ProjectMembers" (
                            id, project_id, user_id, role, added_by_user_id, created_at, updated_at
                        ) VALUES (
                            :id, :project_id, :user_id, :role, :added_by, :created_at, :updated_at
                        )
                    """), {
                        "id": member_id,
                        "project_id": project_id,
                        "user_id": user["id"],
                        "role": role,
                        "added_by": owner["id"],
                        "created_at": created_at,
                        "updated_at": created_at,
                    })

                if (i + 1) % 10 == 0:
                    print(f"Created {i + 1}/{NUM_PROJECTS} projects...")

            # Commit all changes
            await db.commit()
            print(f"\nSuccessfully created {NUM_PROJECTS} projects!")
            print(f"Project keys: AP001 to AP{NUM_PROJECTS:03d}")

        except Exception as e:
            await db.rollback()
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(main())

"""
Script to insert 60 archived tasks for testing.
These tasks will have completed_at dates older than 7 days.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
import random
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Database connection
DB_URL = "postgresql+asyncpg://pmsdbuser:never!again@10.18.137.202:5432/pmsdb"

# Task data templates
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
    "Create custom report builder",
    "Add mobile scanner support",
    "Implement FIFO/LIFO selection",
    "Fix lot tracking issues",
    "Update inventory valuation",
    "Add serial number tracking",
    "Implement quality inspection",
    "Fix cross-docking workflow",
    "Create vendor management portal",
    "Add EDI integration",
    "Implement demand planning",
    "Fix replenishment triggers",
    "Update bin location system",
    "Add weight/dimension capture",
    "Implement kitting operations",
    "Fix inventory reconciliation",
    "Create performance dashboard",
    "Add labor management tracking",
    "Implement slotting optimization",
    "Fix pallet build logic",
    "Update shipping manifests",
    "Add customs documentation",
    "Implement hazmat handling",
    "Fix temperature monitoring",
    "Create equipment maintenance logs",
    "Add dock scheduling",
    "Implement yard management",
    "Fix trailer tracking",
    "Update inventory aging report",
    "Add ABC classification",
    "Implement safety stock calc",
    "Fix reorder point alerts",
    "Create supplier scorecard",
    "Add purchase order automation",
    "Implement goods receipt posting",
    "Fix invoice matching",
    "Update cost allocation",
    "Add freight rate management",
    "Implement container tracking",
    "Fix ASN processing",
]

TASK_TYPES = ["task", "story", "bug"]
PRIORITIES = ["lowest", "low", "medium", "high", "highest"]


async def main():
    # Create async engine
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Find application "WMS3"
        result = await session.execute(
            text("SELECT id FROM \"Applications\" WHERE name = 'WMS3' LIMIT 1")
        )
        app_row = result.fetchone()
        if not app_row:
            print("Application 'WMS3' not found!")
            return
        app_id = app_row[0]
        print(f"Found application WMS3: {app_id}")

        # Find project "project1" in WMS3
        result = await session.execute(
            text("""
                SELECT id, key, next_task_number
                FROM "Projects"
                WHERE application_id = :app_id AND name = 'project1'
                LIMIT 1
            """),
            {"app_id": app_id}
        )
        proj_row = result.fetchone()
        if not proj_row:
            print("Project 'project1' not found in WMS3!")
            return
        project_id = proj_row[0]
        task_key_prefix = proj_row[1]
        current_sequence = proj_row[2] or 1
        print(f"Found project1: {project_id}, prefix: {task_key_prefix}, next_task_number: {current_sequence}")

        # Find a user to use as reporter (get first user)
        result = await session.execute(
            text("SELECT id FROM \"Users\" LIMIT 1")
        )
        user_row = result.fetchone()
        if not user_row:
            print("No users found!")
            return
        reporter_id = user_row[0]
        print(f"Using reporter: {reporter_id}")

        # Get the 'Done' task status for this project
        result = await session.execute(
            text("""
                SELECT id FROM "TaskStatuses"
                WHERE project_id = :project_id AND name = 'Done'
                LIMIT 1
            """),
            {"project_id": project_id}
        )
        status_row = result.fetchone()
        done_status_id = status_row[0] if status_row else None
        print(f"Done status ID: {done_status_id}")

        # Generate 60 tasks
        now = datetime.utcnow()
        tasks_to_insert = []

        for i in range(60):
            task_id = uuid.uuid4()
            task_number = current_sequence + i
            task_key = f"{task_key_prefix}-{task_number}"

            # Completed 8-30 days ago (all over 7 days)
            days_ago = random.randint(8, 30)
            completed_at = now - timedelta(days=days_ago)
            created_at = completed_at - timedelta(days=random.randint(1, 14))

            task = {
                "id": task_id,
                "project_id": project_id,
                "task_key": task_key,
                "title": TASK_TITLES[i % len(TASK_TITLES)],
                "description": f"<p>This is an archived task for testing. Task #{i+1}</p>",
                "task_type": random.choice(TASK_TYPES),
                "status": "done",
                "task_status_id": done_status_id,
                "priority": random.choice(PRIORITIES),
                "reporter_id": reporter_id,
                "story_points": random.choice([1, 2, 3, 5, 8, 13, None]),
                "row_version": 1,
                "checklist_total": 0,
                "checklist_done": 0,
                "created_at": created_at,
                "updated_at": completed_at,
                "completed_at": completed_at,
                "archived_at": None,  # Will be auto-archived on fetch
            }
            tasks_to_insert.append(task)

        # Insert tasks in batches
        print(f"Inserting {len(tasks_to_insert)} tasks...")

        for task in tasks_to_insert:
            await session.execute(
                text("""
                    INSERT INTO "Tasks" (
                        id, project_id, task_key, title, description, task_type,
                        status, task_status_id, priority, reporter_id, story_points,
                        row_version, checklist_total, checklist_done,
                        created_at, updated_at, completed_at, archived_at
                    ) VALUES (
                        :id, :project_id, :task_key, :title, :description, :task_type,
                        :status, :task_status_id, :priority, :reporter_id, :story_points,
                        :row_version, :checklist_total, :checklist_done,
                        :created_at, :updated_at, :completed_at, :archived_at
                    )
                """),
                task
            )

        # Update project next_task_number
        new_sequence = current_sequence + 60
        await session.execute(
            text("""
                UPDATE "Projects"
                SET next_task_number = :seq
                WHERE id = :project_id
            """),
            {"seq": new_sequence, "project_id": project_id}
        )

        await session.commit()
        print(f"Successfully inserted 60 archived tasks!")
        print(f"Task keys: {task_key_prefix}-{current_sequence} to {task_key_prefix}-{new_sequence - 1}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

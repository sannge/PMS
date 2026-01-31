"""
Test script to verify auto-archive logic works correctly.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://pmsdbuser:password@localhost:5432/pmsdb")

async def test():
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Get WMS3 application ID
        result = await db.execute(
            text('SELECT id FROM "Applications" WHERE name = :name'),
            {"name": "WMS3"}
        )
        app_row = result.fetchone()
        if not app_row:
            print("WMS3 application not found")
            return

        app_id = app_row[0]
        print(f"Application ID: {app_id}")

        # Check AP projects status
        result = await db.execute(text('''
            SELECT
                p.key,
                p.archived_at,
                (SELECT COUNT(*) FROM "Tasks" t WHERE t.project_id = p.id) as total_tasks,
                (SELECT COUNT(*) FROM "Tasks" t WHERE t.project_id = p.id AND t.archived_at IS NULL) as active_tasks
            FROM "Projects" p
            WHERE p.key LIKE 'AP%' AND p.application_id = :app_id
            ORDER BY p.key
            LIMIT 5
        '''), {"app_id": app_id})
        rows = result.fetchall()

        print("\nSample AP projects BEFORE auto-archive:")
        print("Key | Project Archived | Total Tasks | Active Tasks")
        print("-" * 60)
        for row in rows:
            print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]}")

        # Count eligible projects (has tasks, all archived, project not archived)
        result = await db.execute(text('''
            SELECT COUNT(*)
            FROM "Projects" p
            WHERE p.application_id = :app_id
              AND p.archived_at IS NULL
              AND EXISTS (SELECT 1 FROM "Tasks" t WHERE t.project_id = p.id)
              AND NOT EXISTS (SELECT 1 FROM "Tasks" t WHERE t.project_id = p.id AND t.archived_at IS NULL)
        '''), {"app_id": app_id})
        eligible_count = result.scalar()
        print(f"\nProjects eligible for auto-archive: {eligible_count}")

        if eligible_count > 0:
            # Run auto-archive manually
            print("\nRunning auto-archive...")
            from datetime import datetime
            now = datetime.utcnow()

            result = await db.execute(text('''
                UPDATE "Projects" p
                SET archived_at = :now
                WHERE p.application_id = :app_id
                  AND p.archived_at IS NULL
                  AND EXISTS (SELECT 1 FROM "Tasks" t WHERE t.project_id = p.id)
                  AND NOT EXISTS (SELECT 1 FROM "Tasks" t WHERE t.project_id = p.id AND t.archived_at IS NULL)
            '''), {"app_id": app_id, "now": now})

            await db.commit()
            print(f"Archived {result.rowcount} projects")

            # Verify
            result = await db.execute(text('''
                SELECT p.key, p.archived_at
                FROM "Projects" p
                WHERE p.key LIKE 'AP%' AND p.application_id = :app_id
                ORDER BY p.key
                LIMIT 5
            '''), {"app_id": app_id})
            rows = result.fetchall()

            print("\nSample AP projects AFTER auto-archive:")
            print("Key | Project Archived")
            print("-" * 40)
            for row in rows:
                print(f"{row[0]} | {row[1]}")

asyncio.run(test())

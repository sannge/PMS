"""Reset test database - drop all tables and composite types."""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

# Drop views first
DROP_VIEWS = [
    "DROP VIEW IF EXISTS v_checklist_items CASCADE",
    "DROP VIEW IF EXISTS v_checklists CASCADE",
    "DROP VIEW IF EXISTS v_attachments CASCADE",
    "DROP VIEW IF EXISTS v_users CASCADE",
    "DROP VIEW IF EXISTS v_project_assignments CASCADE",
    "DROP VIEW IF EXISTS v_project_members CASCADE",
    "DROP VIEW IF EXISTS v_application_members CASCADE",
    "DROP VIEW IF EXISTS v_comments CASCADE",
    "DROP VIEW IF EXISTS v_document_folders CASCADE",
    "DROP VIEW IF EXISTS v_documents CASCADE",
    "DROP VIEW IF EXISTS v_task_statuses CASCADE",
    "DROP VIEW IF EXISTS v_tasks CASCADE",
    "DROP VIEW IF EXISTS v_projects CASCADE",
    "DROP VIEW IF EXISTS v_applications CASCADE",
]

DROP_STMTS = [
    "DROP TABLE IF EXISTS ai_system_prompts CASCADE",
    'DROP TABLE IF EXISTS "ImportJobs" CASCADE',
    'DROP TABLE IF EXISTS "DocumentChunks" CASCADE',
    'DROP TABLE IF EXISTS "DocumentSnapshots" CASCADE',
    'DROP TABLE IF EXISTS "DocumentTagAssignments" CASCADE',
    'DROP TABLE IF EXISTS "DocumentTags" CASCADE',
    'DROP TABLE IF EXISTS "Documents" CASCADE',
    'DROP TABLE IF EXISTS "DocumentFolders" CASCADE',
    'DROP TABLE IF EXISTS "AiModels" CASCADE',
    'DROP TABLE IF EXISTS "AiProviders" CASCADE',
    'DROP TABLE IF EXISTS "Mentions" CASCADE',
    'DROP TABLE IF EXISTS "ChecklistItems" CASCADE',
    'DROP TABLE IF EXISTS "Attachments" CASCADE',
    'DROP TABLE IF EXISTS "ApplicationMembers" CASCADE',
    'DROP TABLE IF EXISTS "Comments" CASCADE',
    'DROP TABLE IF EXISTS "Checklists" CASCADE',
    'DROP TABLE IF EXISTS "Notes" CASCADE',
    'DROP TABLE IF EXISTS "Invitations" CASCADE',
    'DROP TABLE IF EXISTS "Tasks" CASCADE',
    'DROP TABLE IF EXISTS "ProjectTaskStatusAgg" CASCADE',
    'DROP TABLE IF EXISTS "ProjectMembers" CASCADE',
    'DROP TABLE IF EXISTS "ProjectAssignments" CASCADE',
    'DROP TABLE IF EXISTS "TaskStatuses" CASCADE',
    'DROP TABLE IF EXISTS "Projects" CASCADE',
    'DROP TABLE IF EXISTS "Notifications" CASCADE',
    'DROP TABLE IF EXISTS "Applications" CASCADE',
    'DROP TABLE IF EXISTS "Users" CASCADE',
]

DROP_TYPES_SQL = """DO $$ DECLARE r RECORD;
BEGIN
    FOR r IN (SELECT typname FROM pg_type
              WHERE typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
              AND typtype = 'c'
              AND typname NOT LIKE 'pg_%'
              AND typname NOT IN ('vector'))
    LOOP
        EXECUTE 'DROP TYPE IF EXISTS "' || r.typname || '" CASCADE';
    END LOOP;
END $$;"""


async def reset():
    engine = create_async_engine(settings.test_database_url, pool_size=1, max_overflow=0)
    # Drop views
    async with engine.begin() as conn:
        for stmt in DROP_VIEWS:
            await conn.execute(text(stmt))
    # Drop tables
    async with engine.begin() as conn:
        for stmt in DROP_STMTS:
            await conn.execute(text(stmt))
    # Drop composite types (separate transaction)
    async with engine.begin() as conn:
        await conn.execute(text(DROP_TYPES_SQL))
    # Verify no "Users" type remains
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT typname FROM pg_type WHERE typname = 'Users' AND typtype = 'c'"))
        rows = result.fetchall()
        if rows:
            print(f"WARNING: Users composite type still exists! Dropping explicitly...")
            await conn.execute(text('DROP TYPE IF EXISTS "Users" CASCADE'))
        else:
            print("No stale composite types found")
    await engine.dispose()
    print("Test database reset complete")


asyncio.run(reset())

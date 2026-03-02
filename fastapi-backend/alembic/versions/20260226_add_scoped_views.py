"""Add 14 scoped PostgreSQL views for AI agent SQL access.

Creates RBAC-enforced views that filter data based on the current user's
application membership. Each view uses current_setting('app.current_user_id')
to scope rows to applications the user owns or is a member of.

Views created:
  v_applications, v_projects, v_tasks, v_task_statuses, v_documents,
  v_document_folders, v_comments, v_application_members, v_project_members,
  v_project_assignments, v_users, v_attachments, v_checklists,
  v_checklist_items

Revision ID: 20260226_scoped_views
Revises: 20260225_doc_chunks
Create Date: 2026-02-26
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260226_scoped_views"
down_revision: Union[str, None] = "20260226_drop_kg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Reusable CTE fragment: applications accessible to the current user
# (owner OR member). Used by most views to enforce RBAC.
# ---------------------------------------------------------------------------
_ACCESSIBLE_APPS = """
    SELECT a.id FROM "Applications" a
    WHERE a.owner_id = current_setting('app.current_user_id')::uuid
    UNION
    SELECT am.application_id FROM "ApplicationMembers" am
    WHERE am.user_id = current_setting('app.current_user_id')::uuid
"""


def upgrade() -> None:
    """Create 14 scoped views for AI agent SQL access."""

    # 1. v_applications - apps where user is owner OR member
    op.execute(f"""
        CREATE OR REPLACE VIEW v_applications AS
        SELECT a.*
        FROM "Applications" a
        WHERE a.id IN ({_ACCESSIBLE_APPS});
    """)

    # 2. v_projects - projects in accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_projects AS
        SELECT p.*
        FROM "Projects" p
        WHERE p.application_id IN ({_ACCESSIBLE_APPS});
    """)

    # 3. v_tasks - tasks in accessible apps, not archived
    op.execute(f"""
        CREATE OR REPLACE VIEW v_tasks AS
        SELECT t.*
        FROM "Tasks" t
        JOIN "Projects" p ON p.id = t.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS})
          AND t.archived_at IS NULL;
    """)

    # 4. v_task_statuses - statuses in accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_task_statuses AS
        SELECT ts.*
        FROM "TaskStatuses" ts
        JOIN "Projects" p ON p.id = ts.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS});
    """)

    # 5. v_documents - 3-scope: app docs, project docs, personal docs
    #    Filters deleted_at IS NULL for all scopes
    op.execute(f"""
        CREATE OR REPLACE VIEW v_documents AS
        SELECT d.*
        FROM "Documents" d
        WHERE d.deleted_at IS NULL
          AND (
            (d.application_id IS NOT NULL
             AND d.project_id IS NULL
             AND d.user_id IS NULL
             AND d.application_id IN ({_ACCESSIBLE_APPS}))
            OR
            (d.project_id IS NOT NULL
             AND d.user_id IS NULL
             AND d.project_id IN (
                 SELECT p.id FROM "Projects" p
                 WHERE p.application_id IN ({_ACCESSIBLE_APPS})
             ))
            OR
            (d.user_id IS NOT NULL
             AND d.application_id IS NULL
             AND d.project_id IS NULL
             AND d.user_id = current_setting('app.current_user_id')::uuid)
          );
    """)

    # 6. v_document_folders - same 3-scope pattern as documents
    op.execute(f"""
        CREATE OR REPLACE VIEW v_document_folders AS
        SELECT df.*
        FROM "DocumentFolders" df
        WHERE
            (df.application_id IS NOT NULL
             AND df.application_id IN ({_ACCESSIBLE_APPS}))
            OR
            (df.project_id IS NOT NULL
             AND df.project_id IN (
                 SELECT p.id FROM "Projects" p
                 WHERE p.application_id IN ({_ACCESSIBLE_APPS})
             ))
            OR
            (df.user_id IS NOT NULL
             AND df.application_id IS NULL
             AND df.project_id IS NULL
             AND df.user_id = current_setting('app.current_user_id')::uuid);
    """)

    # 7. v_comments - comments on tasks in accessible apps, not deleted
    op.execute(f"""
        CREATE OR REPLACE VIEW v_comments AS
        SELECT c.*
        FROM "Comments" c
        JOIN "Tasks" t ON t.id = c.task_id
        JOIN "Projects" p ON p.id = t.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS})
          AND c.is_deleted = false;
    """)

    # 8. v_application_members - members of accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_application_members AS
        SELECT am.*
        FROM "ApplicationMembers" am
        WHERE am.application_id IN ({_ACCESSIBLE_APPS});
    """)

    # 9. v_project_members - members of projects in accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_project_members AS
        SELECT pm.*
        FROM "ProjectMembers" pm
        JOIN "Projects" p ON p.id = pm.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS});
    """)

    # 10. v_project_assignments - assignments in projects in accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_project_assignments AS
        SELECT pa.*
        FROM "ProjectAssignments" pa
        JOIN "Projects" p ON p.id = pa.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS});
    """)

    # 11. v_users - all users visible, but EXCLUDE password_hash
    op.execute("""
        CREATE OR REPLACE VIEW v_users AS
        SELECT u.id,
               u.email,
               u.display_name,
               u.avatar_url,
               u.created_at,
               u.updated_at
        FROM "Users" u;
    """)

    # 12. v_attachments - attachments on tasks in accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_attachments AS
        SELECT att.*
        FROM "Attachments" att
        JOIN "Tasks" t ON t.id = att.task_id
        JOIN "Projects" p ON p.id = t.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS});
    """)

    # 13. v_checklists - checklists on tasks in accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_checklists AS
        SELECT cl.*
        FROM "Checklists" cl
        JOIN "Tasks" t ON t.id = cl.task_id
        JOIN "Projects" p ON p.id = t.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS});
    """)

    # 14. v_checklist_items - items in checklists on tasks in accessible apps
    op.execute(f"""
        CREATE OR REPLACE VIEW v_checklist_items AS
        SELECT ci.*
        FROM "ChecklistItems" ci
        JOIN "Checklists" cl ON cl.id = ci.checklist_id
        JOIN "Tasks" t ON t.id = cl.task_id
        JOIN "Projects" p ON p.id = t.project_id
        WHERE p.application_id IN ({_ACCESSIBLE_APPS});
    """)


def downgrade() -> None:
    """Drop all 14 scoped views in reverse dependency order."""
    op.execute("DROP VIEW IF EXISTS v_checklist_items;")
    op.execute("DROP VIEW IF EXISTS v_checklists;")
    op.execute("DROP VIEW IF EXISTS v_attachments;")
    op.execute("DROP VIEW IF EXISTS v_users;")
    op.execute("DROP VIEW IF EXISTS v_project_assignments;")
    op.execute("DROP VIEW IF EXISTS v_project_members;")
    op.execute("DROP VIEW IF EXISTS v_application_members;")
    op.execute("DROP VIEW IF EXISTS v_comments;")
    op.execute("DROP VIEW IF EXISTS v_document_folders;")
    op.execute("DROP VIEW IF EXISTS v_documents;")
    op.execute("DROP VIEW IF EXISTS v_task_statuses;")
    op.execute("DROP VIEW IF EXISTS v_tasks;")
    op.execute("DROP VIEW IF EXISTS v_projects;")
    op.execute("DROP VIEW IF EXISTS v_applications;")

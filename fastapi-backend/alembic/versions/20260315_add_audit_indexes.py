"""Add indexes for QE audit findings (H7, M5, M14, M15, L7).

Addresses database audit findings:

- QE-H7: Partial composite index on Tasks(project_id, task_status_id)
  WHERE archived_at IS NULL for the most frequent query pattern.

- QE-M5: Functional indexes on lower(name) for DocumentFolders and
  lower(title) for Documents to support case-insensitive uniqueness checks
  in document_service.py.

- QE-M14: Composite indexes on Notifications(user_id, created_at DESC)
  for paginated notification listing, plus a partial index for unread-only.

- QE-M15: text_pattern_ops index on DocumentFolders.materialized_path for
  LIKE prefix queries used in subtree operations.

- QE-L7: Unique partial indexes enforcing name uniqueness at the DB level
  for DocumentFolders (scoped by parent + application/project/user) and
  Documents (scoped by folder + application/project/user).

Revision ID: 20260315_audit_indexes
Revises: 20260314_proj_name_trgm
Create Date: 2026-03-15
"""

from alembic import op
from sqlalchemy import text

revision = "20260315_audit_indexes"
down_revision = "20260314_proj_name_trgm"
branch_labels = None
depends_on = None

# Sentinel UUID for COALESCE on nullable columns in unique indexes.
# Maps NULL parent_id / folder_id to a fixed value so NULLs are
# properly de-duplicated (NULLs are never equal in a unique index).
_SENTINEL = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # Each CREATE INDEX CONCURRENTLY must run outside a transaction.
    # psycopg2 auto-begins a new transaction after every COMMIT, so we
    # must issue COMMIT before *every* CONCURRENTLY statement.
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # QE-H7: Partial composite index for active tasks by project.
    # Covers: WHERE project_id = ? AND archived_at IS NULL
    #         AND task_status_id = ?
    # ------------------------------------------------------------------
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tasks_project_active "
        'ON "Tasks" (project_id, task_status_id) '
        "WHERE archived_at IS NULL"
    )

    # ------------------------------------------------------------------
    # QE-M5: Functional indexes for case-insensitive name lookups.
    # Supports: WHERE lower(name) = ? and WHERE lower(title) = ?
    # ------------------------------------------------------------------
    conn.execute(text("COMMIT"))
    op.execute(
        'CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_document_folders_name_lower ON "DocumentFolders" (lower(name))'
    )

    conn.execute(text("COMMIT"))
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_documents_title_lower ON "Documents" (lower(title))')

    # ------------------------------------------------------------------
    # QE-M14: Composite indexes for notification pagination.
    # Covers: WHERE user_id = ? ORDER BY created_at DESC OFFSET/LIMIT
    # Plus partial for: WHERE user_id = ? AND is_read = false
    # ------------------------------------------------------------------
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notifications_user_created "
        'ON "Notifications" (user_id, created_at DESC)'
    )

    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_notifications_user_unread "
        'ON "Notifications" (user_id, created_at DESC) '
        "WHERE is_read = false"
    )

    # ------------------------------------------------------------------
    # QE-M15: text_pattern_ops index for materialized_path LIKE prefix.
    # Supports: WHERE materialized_path LIKE '{path}%'
    # ------------------------------------------------------------------
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_document_folders_path_pattern "
        'ON "DocumentFolders" (materialized_path text_pattern_ops)'
    )

    # ------------------------------------------------------------------
    # QE-L7: Unique partial indexes for name uniqueness enforcement.
    #
    # Three scopes exist: application, project, personal (user).
    # Each scope gets its own partial unique index with a WHERE clause
    # that isolates it from the other scopes.
    #
    # Folders: unique lower(name) within same parent and scope.
    # COALESCE maps NULL parent_id to a sentinel UUID so that
    # root-level folders are properly de-duplicated.
    # ------------------------------------------------------------------

    # Folders scoped to application (application_id set, no project/user)
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_document_folders_unique_name "
        'ON "DocumentFolders" '
        f"(application_id, COALESCE(parent_id, '{_SENTINEL}'), lower(name)) "
        "WHERE project_id IS NULL AND user_id IS NULL"
    )

    # Folders scoped to project (project_id set)
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_document_folders_unique_name_project "
        'ON "DocumentFolders" '
        f"(project_id, COALESCE(parent_id, '{_SENTINEL}'), lower(name)) "
        "WHERE project_id IS NOT NULL"
    )

    # Folders scoped to personal/user (user_id set)
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_document_folders_unique_name_user "
        'ON "DocumentFolders" '
        f"(user_id, COALESCE(parent_id, '{_SENTINEL}'), lower(name)) "
        "WHERE user_id IS NOT NULL"
    )

    # Documents scoped to application (application_id set, no project/user)
    # Unique lower(title) within same folder + scope.
    # COALESCE maps NULL folder_id (unfiled) to a sentinel UUID.
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_documents_unique_title "
        'ON "Documents" '
        f"(application_id, COALESCE(folder_id, '{_SENTINEL}'), lower(title)) "
        "WHERE project_id IS NULL AND user_id IS NULL AND deleted_at IS NULL"
    )

    # Documents scoped to project (project_id set)
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_documents_unique_title_project "
        'ON "Documents" '
        f"(project_id, COALESCE(folder_id, '{_SENTINEL}'), lower(title)) "
        "WHERE project_id IS NOT NULL AND deleted_at IS NULL"
    )

    # Documents scoped to personal/user (user_id set)
    conn.execute(text("COMMIT"))
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_documents_unique_title_user "
        'ON "Documents" '
        f"(user_id, COALESCE(folder_id, '{_SENTINEL}'), lower(title)) "
        "WHERE user_id IS NOT NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    # QE-L7: Drop unique name indexes (all three scopes)
    op.execute("DROP INDEX IF EXISTS ix_documents_unique_title_user")
    op.execute("DROP INDEX IF EXISTS ix_documents_unique_title_project")
    op.execute("DROP INDEX IF EXISTS ix_documents_unique_title")
    op.execute("DROP INDEX IF EXISTS ix_document_folders_unique_name_user")
    op.execute("DROP INDEX IF EXISTS ix_document_folders_unique_name_project")
    op.execute("DROP INDEX IF EXISTS ix_document_folders_unique_name")

    # QE-M15: Drop path pattern index
    op.execute("DROP INDEX IF EXISTS ix_document_folders_path_pattern")

    # QE-M14: Drop notification indexes
    op.execute("DROP INDEX IF EXISTS ix_notifications_user_unread")
    op.execute("DROP INDEX IF EXISTS ix_notifications_user_created")

    # QE-M5: Drop functional indexes
    op.execute("DROP INDEX IF EXISTS ix_documents_title_lower")
    op.execute("DROP INDEX IF EXISTS ix_document_folders_name_lower")

    # QE-H7: Drop active tasks index
    op.execute("DROP INDEX IF EXISTS ix_tasks_project_active")

"""Add performance indexes and ImportJobs.folder_id FK.

Addresses R1 database audit findings:

- DB-C1: Composite index on ApplicationMembers(user_id, application_id) to make
  the _ACCESSIBLE_APPS subquery in all 14 scoped views an index-only scan.

- DB-C2: Foreign key on ImportJobs.folder_id -> DocumentFolders.id to enforce
  referential integrity (previously a bare UUID column with no FK constraint).

- DB-P7: Note about HNSW index CONCURRENTLY for future reference.

- DB-P8: Composite index on ImportJobs(user_id, status, created_at DESC) for
  the paginated job listing endpoint (GET /api/ai/import/jobs).

Revision ID: 20260228_perf_indexes
Revises: 20260227_seed_models
Create Date: 2026-02-28
"""

from alembic import op

# revision identifiers
revision = "20260228_perf_indexes"
down_revision = "20260227_seed_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DB-C1: Composite index for scoped view RBAC subquery optimization.
    # Every scoped view (v_tasks, v_projects, etc.) runs:
    #   SELECT a.id FROM "Applications" a WHERE a.owner_id = ...
    #   UNION
    #   SELECT am.application_id FROM "ApplicationMembers" am WHERE am.user_id = ...
    # This composite index makes the second half an index-only scan.
    op.create_index(
        "idx_application_members_user_app",
        "ApplicationMembers",
        ["user_id", "application_id"],
    )

    # DB-C2: Add FK constraint on ImportJobs.folder_id -> DocumentFolders.id.
    # The column already exists (created in 20260226_add_import_jobs) but without
    # a FK constraint. This ensures referential integrity.
    op.create_foreign_key(
        "fk_import_jobs_folder_id",
        "ImportJobs",
        "DocumentFolders",
        ["folder_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # DB-P8: Composite index for paginated job listing (list_jobs endpoint).
    # Covers: WHERE user_id = ? AND status = ? ORDER BY created_at DESC
    # Using raw SQL because Alembic's create_index doesn't support DESC columns.
    op.execute(
        'CREATE INDEX idx_import_jobs_user_status_created '
        'ON "ImportJobs" (user_id, status, created_at DESC)'
    )

    # DB-P7: Note for future reference -- if the HNSW index on DocumentChunks
    # needs to be recreated on a production database with existing data, use:
    #   CREATE INDEX CONCURRENTLY idx_document_chunks_embedding_hnsw
    #   ON "DocumentChunks" USING hnsw (embedding vector_cosine_ops)
    #   WITH (m = 16, ef_construction = 64);
    # CONCURRENTLY avoids holding an exclusive lock on the table during build.
    # Alembic does not natively support CONCURRENTLY, so use op.execute() with
    # autocommit mode when needed.


def downgrade() -> None:
    op.drop_index("idx_import_jobs_user_status_created", table_name="ImportJobs")
    op.drop_constraint("fk_import_jobs_folder_id", "ImportJobs", type_="foreignkey")
    op.drop_index("idx_application_members_user_app", table_name="ApplicationMembers")

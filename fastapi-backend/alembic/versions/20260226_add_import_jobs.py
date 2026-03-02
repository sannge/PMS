"""Add import jobs table.

Stores document import job metadata for tracking PDF/DOCX/PPTX imports
via the Docling pipeline. Each job tracks upload, conversion progress,
and links to the resulting Document on completion.

Revision ID: 20260226_add_import_jobs
Revises: 20260226_email_verify
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260226_add_import_jobs"
down_revision = "20260226_email_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ImportJobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("Users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "progress_pct",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("Documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column(
            "scope_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("temp_file_path", sa.String(1000), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        # CHECK constraints
        sa.CheckConstraint(
            "file_type IN ('pdf', 'docx', 'pptx')",
            name="ck_import_jobs_file_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_import_jobs_status",
        ),
        sa.CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100",
            name="ck_import_jobs_progress_pct",
        ),
        sa.CheckConstraint(
            "scope IN ('application', 'project', 'personal')",
            name="ck_import_jobs_scope",
        ),
    )

    op.create_index("idx_import_jobs_user", "ImportJobs", ["user_id"])
    op.create_index("idx_import_jobs_status", "ImportJobs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_import_jobs_status", table_name="ImportJobs")
    op.drop_index("idx_import_jobs_user", table_name="ImportJobs")
    op.drop_table("ImportJobs")

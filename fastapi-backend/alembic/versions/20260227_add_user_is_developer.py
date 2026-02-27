"""Add is_developer column to Users table.

Adds a boolean flag for developer access to AI configuration admin endpoints.
Defaults to false for all existing and new users. Set manually via database
for trusted developers — no UI for managing this column.

Revision ID: 20260227_is_developer
Revises: 20260226_add_import_jobs
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260227_is_developer"
down_revision = "20260226_add_import_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "Users",
        sa.Column(
            "is_developer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("Users", "is_developer")

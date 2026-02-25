"""Convert all datetime columns to timestamp with time zone.

All existing data is UTC. This migration makes that explicit by converting
columns from 'timestamp without time zone' to 'timestamp with time zone',
telling PostgreSQL the existing values are UTC.

Revision ID: a1b2c3d4e5f6
Revises: 20260223_dashboard_indexes
Create Date: 2026-02-24
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "20260223_dashboard_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All tables and their datetime columns, grouped for clarity.
_TABLES_COLUMNS: list[tuple[str, list[str]]] = [
    ("Users", ["created_at", "updated_at"]),
    ("Applications", ["created_at", "updated_at"]),
    ("Projects", ["override_expires_at", "created_at", "updated_at", "archived_at"]),
    ("TaskStatuses", ["created_at"]),
    ("Notifications", ["created_at"]),
    ("ProjectAssignments", ["created_at"]),
    ("ProjectMembers", ["created_at", "updated_at"]),
    ("ProjectTaskStatusAgg", ["updated_at"]),
    ("Tasks", ["created_at", "updated_at", "completed_at", "archived_at"]),
    ("Comments", ["created_at", "updated_at"]),
    ("Invitations", ["created_at", "responded_at"]),
    ("ApplicationMembers", ["created_at", "updated_at"]),
    ("Attachments", ["created_at"]),
    ("ChecklistItems", ["completed_at", "created_at", "updated_at"]),
    ("Checklists", ["created_at"]),
    ("Mentions", ["created_at"]),
    ("Documents", ["created_at", "updated_at", "deleted_at"]),
    ("DocumentFolders", ["created_at", "updated_at"]),
    ("DocumentSnapshots", ["created_at"]),
    ("DocumentTags", ["created_at"]),
    ("DocumentTagAssignments", ["created_at"]),
]


def upgrade() -> None:
    """Convert all TIMESTAMP WITHOUT TIME ZONE columns to TIMESTAMP WITH TIME ZONE.

    Uses AT TIME ZONE 'UTC' to tell PostgreSQL the existing naive values are UTC.
    """
    for table, columns in _TABLES_COLUMNS:
        for col in columns:
            op.execute(
                f'ALTER TABLE "{table}" '
                f"ALTER COLUMN {col} "
                f"TYPE TIMESTAMP WITH TIME ZONE "
                f"USING {col} AT TIME ZONE 'UTC'"
            )


def downgrade() -> None:
    """Convert all TIMESTAMP WITH TIME ZONE columns back to TIMESTAMP WITHOUT TIME ZONE."""
    for table, columns in _TABLES_COLUMNS:
        for col in columns:
            op.execute(
                f'ALTER TABLE "{table}" '
                f"ALTER COLUMN {col} "
                f"TYPE TIMESTAMP WITHOUT TIME ZONE"
            )

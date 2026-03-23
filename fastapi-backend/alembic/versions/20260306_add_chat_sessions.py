"""Add ChatSessions and ChatMessages tables.

Revision ID: 20260306_add_chat_sessions
Revises: 20260302_add_embedding_status
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260306_add_chat_sessions"
down_revision = "20260302_add_embedding_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ChatSessions",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.String(256), nullable=True),
        sa.Column("title", sa.String(200), nullable=False, server_default="New Chat"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("application_id", UUID(as_uuid=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_preview", sa.String(150), server_default=""),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("summary_up_to_msg_seq", sa.Integer(), nullable=True),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["Applications.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_chatsessions_user_updated",
        "ChatSessions",
        ["user_id", sa.text("updated_at DESC")],
        postgresql_where=sa.text("NOT is_archived"),
    )

    op.create_table(
        "ChatMessages",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("sources", JSONB(), nullable=True),
        sa.Column("checkpoint_id", sa.String(256), nullable=True),
        sa.Column("is_error", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["ChatSessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_chatmessages_role"),
    )
    op.create_index(
        "ix_chatmessages_session_seq",
        "ChatMessages",
        ["session_id", sa.text("sequence DESC")],
    )
    op.create_unique_constraint(
        "uq_chatmessages_session_seq",
        "ChatMessages",
        ["session_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_chatmessages_session_seq", "ChatMessages", type_="unique")
    op.drop_index("ix_chatmessages_session_seq", table_name="ChatMessages")
    op.drop_table("ChatMessages")
    op.drop_index("ix_chatsessions_user_updated", table_name="ChatSessions")
    op.drop_table("ChatSessions")

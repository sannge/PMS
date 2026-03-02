"""Add email verification and password reset columns to Users table.

Adds 7 columns:
  - email_verified (Boolean, default false, existing rows set to true)
  - verification_code (String(64), nullable) - SHA-256 hashed 6-digit code
  - verification_code_expires_at (DateTime(tz), nullable)
  - verification_attempts (Integer, default 0) - brute-force tracking
  - password_reset_code (String(64), nullable) - SHA-256 hashed 6-digit code
  - password_reset_code_expires_at (DateTime(tz), nullable)
  - reset_attempts (Integer, default 0) - brute-force tracking

Revision ID: 20260226_email_verify
Revises: 20260226_scoped_views
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260226_email_verify"
down_revision = "20260226_scoped_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add email_verified with server_default=true so existing users are verified
    op.add_column(
        "Users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "Users",
        sa.Column("verification_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "Users",
        sa.Column(
            "verification_code_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "Users",
        sa.Column(
            "verification_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "Users",
        sa.Column("password_reset_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "Users",
        sa.Column(
            "password_reset_code_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "Users",
        sa.Column(
            "reset_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Change server_default to false for new users going forward
    op.alter_column(
        "Users",
        "email_verified",
        server_default=sa.text("false"),
    )


def downgrade() -> None:
    op.drop_column("Users", "reset_attempts")
    op.drop_column("Users", "password_reset_code_expires_at")
    op.drop_column("Users", "password_reset_code")
    op.drop_column("Users", "verification_attempts")
    op.drop_column("Users", "verification_code_expires_at")
    op.drop_column("Users", "verification_code")
    op.drop_column("Users", "email_verified")

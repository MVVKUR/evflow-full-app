"""track password change time for session invalidation

Revision ID: 0008_user_password_changed_at
Revises: 0007_password_reset_tokens
Create Date: 2026-07-16
"""
from alembic import op

revision = "0008_user_password_changed_at"
down_revision = "0007_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at;")

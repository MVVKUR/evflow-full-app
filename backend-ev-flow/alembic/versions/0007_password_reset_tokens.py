"""password reset tokens

Revision ID: 0007_password_reset_tokens
Revises: 0006_user_scoped_wallet
Create Date: 2026-07-16
"""
from alembic import op

revision = "0007_password_reset_tokens"
down_revision = "0006_user_scoped_wallet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id          uuid PRIMARY KEY,
            user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  text NOT NULL UNIQUE,
            expires_at  timestamptz NOT NULL,
            used_at     timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS password_reset_user_created_ix "
               "ON password_reset_tokens (user_id, created_at DESC);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS password_reset_user_created_ix;")
    op.execute("DROP TABLE IF EXISTS password_reset_tokens;")

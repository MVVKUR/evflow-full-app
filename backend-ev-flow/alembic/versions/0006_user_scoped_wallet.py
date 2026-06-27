"""user scoped wallet and charging sessions

Revision ID: 0006_user_scoped_wallet
Revises: 0005_charging_sessions
Create Date: 2026-06-27
"""
from alembic import op

revision = "0006_user_scoped_wallet"
down_revision = "0005_charging_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;")
    op.execute("ALTER TABLE wallet ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE CASCADE;")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS wallet_user_id_uidx ON wallet (user_id) WHERE user_id IS NOT NULL;")
    op.execute("ALTER TABLE topups ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS topups_user_created_ix ON topups (user_id, created_at DESC);")
    op.execute("ALTER TABLE charging_sessions ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS charging_sessions_user_created_ix ON charging_sessions (user_id, created_at DESC);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS charging_sessions_user_created_ix;")
    op.execute("ALTER TABLE charging_sessions DROP COLUMN IF EXISTS user_id;")
    op.execute("DROP INDEX IF EXISTS topups_user_created_ix;")
    op.execute("ALTER TABLE topups DROP COLUMN IF EXISTS user_id;")
    op.execute("DROP INDEX IF EXISTS wallet_user_id_uidx;")
    op.execute("ALTER TABLE wallet DROP COLUMN IF EXISTS user_id;")

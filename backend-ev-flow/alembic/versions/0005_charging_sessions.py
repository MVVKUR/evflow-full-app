"""charging sessions

Revision ID: 0005_charging_sessions
Revises: 0004_users
Create Date: 2026-06-13
"""
from alembic import op

revision = "0005_charging_sessions"
down_revision = "0004_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE charging_sessions (
            id              uuid PRIMARY KEY,
            station_id      text NOT NULL,
            station_name    text,
            connector_type  text,
            power_kw        double precision,
            energy_kwh      double precision NOT NULL CHECK (energy_kwh > 0),
            base_rate_idr   integer NOT NULL,
            admin_fee_idr   integer NOT NULL,
            deposit_idr     bigint NOT NULL CHECK (deposit_idr >= 0),
            delivered_kwh   double precision,
            actual_cost_idr bigint,
            refund_idr      bigint,
            status          text NOT NULL DEFAULT 'active',  -- active | completed
            created_at      timestamptz NOT NULL DEFAULT now(),
            completed_at    timestamptz
        );
    """)
    op.execute("CREATE INDEX charging_sessions_created_ix ON charging_sessions (created_at DESC);")

    # DEMO ONLY: give the single shared wallet a starting balance so the charging
    # flow can be exercised end-to-end without first running a real Xendit top-up.
    # Only seeds when the wallet is still empty; remove for a real deployment.
    op.execute("UPDATE wallet SET balance_idr = 250000 WHERE id = 1 AND balance_idr = 0;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS charging_sessions;")

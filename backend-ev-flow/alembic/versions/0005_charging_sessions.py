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


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS charging_sessions;")

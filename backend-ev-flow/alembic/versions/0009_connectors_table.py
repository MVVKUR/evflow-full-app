"""connectors table promoted from stations.connectors JSONB + availability

Revision ID: 0009_connectors_table
Revises: 0008_user_password_changed_at
Create Date: 2026-07-24
"""
from alembic import op

revision = "0009_connectors_table"
down_revision = "0008_user_password_changed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE connectors (
            id            uuid PRIMARY KEY,
            station_id    text NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
            type          text NOT NULL,
            power_kw      double precision,
            speed_tier    text,
            type_inferred boolean NOT NULL DEFAULT false,
            status        text NOT NULL DEFAULT 'available'
                          CHECK (status IN ('available','in_use','out_of_service')),
            updated_at    timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX connectors_station_ix ON connectors (station_id);")
    op.execute("CREATE INDEX connectors_station_status_ix ON connectors (station_id, status);")
    # Backfill: one row per PHYSICAL connector, exploding the JSONB 'count'
    # (gen_random_uuid() is core in PostgreSQL 13+).
    op.execute("""
        INSERT INTO connectors (id, station_id, type, power_kw, speed_tier, type_inferred)
        SELECT gen_random_uuid(), s.id, c->>'type', (c->>'power_kw')::double precision,
               c->>'speed_tier', COALESCE((c->>'type_inferred')::boolean, false)
        FROM stations s,
             LATERAL jsonb_array_elements(s.connectors) AS c,
             LATERAL generate_series(1, GREATEST(COALESCE((c->>'count')::int, 1), 1)) AS n
        WHERE jsonb_typeof(s.connectors) = 'array';
    """)
    op.execute("""
        ALTER TABLE charging_sessions
        ADD COLUMN connector_id uuid REFERENCES connectors(id) ON DELETE SET NULL;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE charging_sessions DROP COLUMN IF EXISTS connector_id;")
    op.execute("DROP TABLE IF EXISTS connectors;")

"""Load + dedupe stations into Postgres. Run once after `alembic upgrade head`:

    python -m scripts.seed_db

Reads data/raw/*.json (host-mounted), normalizes, infers connectors, clusters
within 75 m, then truncates and inserts the unique stations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text          # noqa: E402

from api import dedup, security, sources  # noqa: E402
from api.db import engine            # noqa: E402

_INSERT = text("""
    INSERT INTO stations
      (id, geom, name, address, province, city, operator, power_kw, speed_tier,
       connector_types, connector_inferred, connectors, sources, status, date_verified)
    VALUES
      (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, :address, :province,
       :city, :operator, :power_kw, :speed_tier, :connector_types, :connector_inferred,
       CAST(:connectors AS jsonb), :sources, :status, :date_verified)
""")


def build_stations() -> list[dict]:
    return dedup.cluster_stations(sources.normalized_rows())


# Mirrors the 0009 migration backfill: one connectors row per PHYSICAL connector,
# exploding each JSONB entry's 'count'. Keeping the two queries identical means a
# freshly seeded DB and a migrated DB end up with the same connector inventory.
_EXPLODE_CONNECTORS = text("""
    INSERT INTO connectors (id, station_id, type, power_kw, speed_tier, type_inferred)
    SELECT gen_random_uuid(), s.id, c->>'type', (c->>'power_kw')::double precision,
           c->>'speed_tier', COALESCE((c->>'type_inferred')::boolean, false)
    FROM stations s,
         LATERAL jsonb_array_elements(s.connectors) AS c,
         LATERAL generate_series(1, GREATEST(COALESCE((c->>'count')::int, 1), 1)) AS n
    WHERE jsonb_typeof(s.connectors) = 'array'
""")


def seed_demo_users(conn) -> None:
    pw_hash = security.hash_password("evflow-demo-2026")
    conn.execute(text("""
        INSERT INTO users (id, username, password_hash, full_name, account_type, profile_completed)
        VALUES
            ('a0000000-0000-0000-0000-000000000001'::uuid, 'demo.driver', :ph, 'Demo User', 'ev_user', true),
            ('a0000000-0000-0000-0000-000000000002'::uuid, 'fleet.operator', :ph, 'Fleet Operator', 'business_planner', true)
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            full_name = EXCLUDED.full_name,
            account_type = EXCLUDED.account_type,
            profile_completed = EXCLUDED.profile_completed;
    """), {"ph": pw_hash})

    conn.execute(text("""
        INSERT INTO wallet (id, user_id, balance_idr)
        SELECT (SELECT COALESCE(MAX(id), 0) FROM wallet) + row_number() over (), u.id, 500000
        FROM users u
        WHERE u.username IN ('demo.driver', 'fleet.operator')
          AND NOT EXISTS (SELECT 1 FROM wallet w WHERE w.user_id = u.id);
    """))
    conn.execute(text("""
        UPDATE wallet SET balance_idr = GREATEST(balance_idr, 500000), updated_at = now()
        WHERE user_id IN (SELECT id FROM users WHERE username IN ('demo.driver', 'fleet.operator'));
    """))


def main() -> None:
    stations = build_stations()
    with engine.begin() as conn:
        # DELETE, not TRUNCATE: connectors FK-references stations, so TRUNCATE
        # would need CASCADE-to-table semantics. DELETE fires the row-level FK
        # actions instead — connectors rows cascade away and any
        # charging_sessions.connector_id pointing at them is SET NULL, so past
        # sessions survive a re-seed.
        conn.execute(text("DELETE FROM stations;"))
        for s in stations:
            conn.execute(_INSERT, {
                "id": s["id"], "lat": s["latitude"], "lon": s["longitude"],
                "name": s.get("name"), "address": s.get("address"),
                "province": s.get("province"), "city": s.get("city"),
                "operator": s.get("operator"), "power_kw": s.get("power_kw"),
                "speed_tier": s.get("speed_tier"),
                "connector_types": list(s.get("connector_types") or []),
                "connector_inferred": bool(s.get("connector_inferred", True)),
                "connectors": json.dumps(s.get("connectors") or []),
                "sources": list(s.get("sources") or []),
                "status": s.get("status"), "date_verified": s.get("date_verified"),
            })
        n_connectors = conn.execute(_EXPLODE_CONNECTORS).rowcount
        seed_demo_users(conn)
    print(f"seeded {len(stations)} stations, {n_connectors} connectors, and 2 demo users")


if __name__ == "__main__":
    main()

"""Load + dedupe stations into Postgres. Run once after `alembic upgrade head`:

    python -m scripts.seed_db

Reads data/raw/*.json (host-mounted), normalizes, infers connectors, clusters
within 75 m, then deletes and re-inserts the unique stations.

Demo accounts are opt-in and driven entirely by the environment — see the
"demo accounts" block below and .env.example. With no demo env vars set, this
script only touches stations/connectors: it never creates a login and never
creates wallet balance. That matters because DEPLOY.md runs it in production.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
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


# --- demo accounts -----------------------------------------------------------
#
# Everything below is OPT-IN. This script is run against production (see
# DEPLOY.md), so it must never invent a password and must never mint spendable
# money on a re-seed.
#
#   DEMO_USER_PASSWORD    plaintext password for the demo accounts. UNSET =>
#                         demo users are not seeded at all (no default).
#   SEED_DEMO_WALLET      "1"/"true"/"yes"/"on" => also seed a demo wallet
#                         balance. Default OFF.
#   DEMO_WALLET_BALANCE_IDR  amount to grant once, in IDR (default 500000).
#
DEMO_PASSWORD_ENV = "DEMO_USER_PASSWORD"
SEED_WALLET_ENV = "SEED_DEMO_WALLET"
DEMO_WALLET_BALANCE_ENV = "DEMO_WALLET_BALANCE_IDR"
DEFAULT_DEMO_WALLET_BALANCE_IDR = 500_000

DEMO_USERS = (
    ("a0000000-0000-0000-0000-000000000001", "demo.driver", "Demo User", "ev_user"),
    ("a0000000-0000-0000-0000-000000000002", "fleet.operator", "Fleet Operator", "business_planner"),
)

# Stable per-user external_id, so re-running the seed collides with the row that
# already exists instead of creating a second grant.
_TOPUP_EXTERNAL_ID = "seed-demo-grant-{username}"
_TOPUP_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")

_TRUE = {"1", "true", "yes", "on"}


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in _TRUE


def _demo_wallet_amount() -> int:
    raw = os.getenv(DEMO_WALLET_BALANCE_ENV, "").strip()
    if not raw:
        return DEFAULT_DEMO_WALLET_BALANCE_IDR
    try:
        amount = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{DEMO_WALLET_BALANCE_ENV} must be an integer number of IDR") from exc
    if amount <= 0:
        raise SystemExit(f"{DEMO_WALLET_BALANCE_ENV} must be > 0 (topups.amount_idr has a CHECK > 0)")
    return amount


# Insert the demo users. password_hash is set ONLY on first creation: a re-seed
# must not silently reset the password of an account somebody is already using.
_UPSERT_DEMO_USER = text("""
    INSERT INTO users (id, username, password_hash, full_name, account_type, profile_completed)
    VALUES (CAST(:id AS uuid), :username, :ph, :full_name, :account_type, true)
    ON CONFLICT (username) DO UPDATE SET
        full_name = EXCLUDED.full_name,
        account_type = EXCLUDED.account_type,
        profile_completed = EXCLUDED.profile_completed
""")

# A zero-balance wallet row is not money, so it is always safe to create.
_ENSURE_WALLET_ROW = text("""
    INSERT INTO wallet (id, user_id, balance_idr)
    SELECT (SELECT COALESCE(MAX(id), 0) + 1 FROM wallet), u.id, 0
    FROM users u
    WHERE u.username = :username
      AND NOT EXISTS (SELECT 1 FROM wallet w WHERE w.user_id = u.id)
""")

# Money is only ever created together with its ledger row. The topups insert is
# the idempotency guard: external_id is UNIQUE, so the second run inserts
# nothing, returns no rows, and the wallet UPDATE therefore credits nothing.
_GRANT_DEMO_BALANCE = text("""
    WITH granted AS (
        INSERT INTO topups (id, user_id, external_id, xendit_invoice_id, amount_idr,
                            status, invoice_url, paid_at)
        SELECT CAST(:topup_id AS uuid), u.id, :external_id, NULL, :amount, 'paid', NULL, now()
        FROM users u
        WHERE u.username = :username
        ON CONFLICT (external_id) DO NOTHING
        RETURNING user_id, amount_idr
    )
    UPDATE wallet w
       SET balance_idr = w.balance_idr + g.amount_idr, updated_at = now()
      FROM granted g
     WHERE w.user_id = g.user_id
    RETURNING w.balance_idr
""")


def seed_demo_users(conn) -> str:
    """Seed the demo accounts. Returns a human-readable summary of what happened."""
    password = os.getenv(DEMO_PASSWORD_ENV, "")
    if not password.strip():
        return (f"skipped demo users: {DEMO_PASSWORD_ENV} is not set "
                f"(set it to seed demo.driver / fleet.operator)")

    # Same 72-BYTE bcrypt limit the HTTP boundary enforces. Reported as a skip
    # with a readable reason rather than a bcrypt traceback mid-seed.
    length_problem = security.password_length_problem(password)
    if length_problem:
        return f"skipped demo users: {DEMO_PASSWORD_ENV} is unusable -- {length_problem}"

    pw_hash = security.hash_password(password)
    for user_id, username, full_name, account_type in DEMO_USERS:
        conn.execute(_UPSERT_DEMO_USER, {
            "id": user_id, "username": username, "ph": pw_hash,
            "full_name": full_name, "account_type": account_type,
        })
        conn.execute(_ENSURE_WALLET_ROW, {"username": username})

    if not _flag_enabled(SEED_WALLET_ENV):
        return (f"{len(DEMO_USERS)} demo users (no wallet balance: "
                f"{SEED_WALLET_ENV} is off)")

    amount = _demo_wallet_amount()
    granted = 0
    for _user_id, username, _full_name, _account_type in DEMO_USERS:
        external_id = _TOPUP_EXTERNAL_ID.format(username=username)
        topup_id = str(uuid.uuid5(_TOPUP_NAMESPACE, external_id))
        rows = conn.execute(_GRANT_DEMO_BALANCE, {
            "topup_id": topup_id, "external_id": external_id,
            "amount": amount, "username": username,
        }).fetchall()
        granted += len(rows)
    return (f"{len(DEMO_USERS)} demo users, {granted} wallet grant(s) of "
            f"{amount} IDR (each with a matching topups row)")


def main() -> None:
    stations = build_stations()
    # `api.sources` now reads `raw_station_records`, not data/raw/*.json. With
    # nothing staged it returns no rows, and the DELETE below would then replace
    # every station in the database with nothing -- a silent wipe caused by
    # skipping one deploy step. Refuse instead, and name the step.
    if not stations:
        raise SystemExit(
            "no stations built: raw_station_records is empty (or holds nothing "
            "usable). Run `python -m scripts.ingest_raw` before seeding; the "
            "deploy order is migrate -> ingest -> seed."
        )
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
        demo_summary = seed_demo_users(conn)
    print(f"seeded {len(stations)} stations, {n_connectors} connectors; {demo_summary}")


if __name__ == "__main__":
    main()

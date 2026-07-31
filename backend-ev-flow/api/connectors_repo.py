"""Connector inventory + availability (promoted from stations.connectors JSONB).

Read helpers open their own connection. occupy()/release() take an ALREADY-OPEN
connection `c` because they run inside charging_repo's money transaction; they
must never open or commit transactions themselves.

This module must NOT import charging_repo (charging_repo imports us).
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text

from .db import engine

ALLOWED_STATUSES = ("available", "in_use", "out_of_service")

_COLS = "id, station_id, type, power_kw, speed_tier, type_inferred, status, updated_at"


def _row(r) -> Optional[dict]:
    if r is None:
        return None
    d = dict(r)
    d["id"] = str(d["id"])
    return d


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def list_by_station(station_id: str) -> list[dict]:
    """All connector rows for one station, ordered by type then id."""
    with engine.connect() as c:
        rows = c.execute(
            text(f"SELECT {_COLS} FROM connectors WHERE station_id = :sid ORDER BY type, id"),
            {"sid": station_id}).mappings().all()
    return [_row(r) for r in rows]


def availability(station_id: str) -> dict:
    """Status counts for one station: total / available / in_use / out_of_service."""
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT status, count(*) FROM connectors WHERE station_id = :sid GROUP BY status"),
            {"sid": station_id}).all()
    counts = {status: int(n) for status, n in rows}
    return {
        "station_id": station_id,
        "total": sum(counts.values()),
        "available": counts.get("available", 0),
        "in_use": counts.get("in_use", 0),
        "out_of_service": counts.get("out_of_service", 0),
    }


def set_status(connector_id: str, status: str) -> Optional[dict]:
    """Set a connector's status. Raises ValueError on a bad status; None if unknown id."""
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"status must be one of {', '.join(ALLOWED_STATUSES)}; got '{status}'")
    if not _is_uuid(connector_id):  # avoid a DB cast error -> treat as not found
        return None
    with engine.begin() as c:
        row = c.execute(text(f"""
            UPDATE connectors SET status = :st, updated_at = now()
            WHERE id = :id
            RETURNING {_COLS}
        """), {"id": connector_id, "st": status}).mappings().first()
    return _row(row)


def occupy(c, station_id: str, connector_type: Optional[str] = None) -> Optional[str]:
    """Atomically claim ONE available connector at the station; return its id.

    Runs inside the caller's open transaction `c`. Prefers a connector matching
    connector_type when given but falls back to any available one. SKIP LOCKED
    keeps concurrent session starts from blocking or double-claiming.
    Returns None when nothing is available (or the station has no rows).
    """
    if connector_type:
        order, params = "ORDER BY (type = :ctype) DESC, id", {"sid": station_id, "ctype": connector_type}
    else:
        order, params = "ORDER BY id", {"sid": station_id}
    row = c.execute(text(f"""
        UPDATE connectors SET status = 'in_use', updated_at = now()
        WHERE id = (
            SELECT id FROM connectors
            WHERE station_id = :sid AND status = 'available'
            {order}
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id
    """), params).first()
    return str(row[0]) if row else None


def release(c, connector_id: str) -> None:
    """Mark a connector available again, inside the caller's open transaction `c`.

    The status='in_use' guard makes it a no-op if an operator already flipped it
    to out_of_service (or it was released some other way).
    """
    c.execute(text("""
        UPDATE connectors SET status = 'available', updated_at = now()
        WHERE id = :cid AND status = 'in_use'
    """), {"cid": connector_id})


# <Aidil> 2026-07-29
_COUNT_KEYS = ("available", "total", "in_use", "out_of_service")

# One row per (type, speed_tier, power_kw) group of interchangeable connectors.
# power_kw is SELECTed, not just grouped by: without it two groups differing only
# in power come back as indistinguishable duplicates the client cannot label.
#
# The active session is reached through a LATERAL aggregate instead of a plain
# LEFT JOIN because a join multiplies the connector row once per matching session,
# which inflates the status counts whenever a connector carries more than one
# 'active' session row. The subquery always yields exactly one row per connector.
_REALTIME_STATUS_SQL = text("""
    SELECT c.type,
           c.speed_tier,
           c.power_kw,
           count(*)                                            AS total,
           count(*) FILTER (WHERE c.status = 'available')       AS available,
           count(*) FILTER (WHERE c.status = 'in_use')          AS in_use,
           count(*) FILTER (WHERE c.status = 'out_of_service')  AS out_of_service,
           CASE
               WHEN count(*) FILTER (WHERE c.status = 'available') > 0 THEN 0
               -- No session on record (or one with no usable power) means the wait is
               -- UNKNOWN, which is not the same answer as "no wait". It has to stay NULL
               -- all the way to the client. GREATEST() cannot carry it: it ignores NULL
               -- arguments, so GREATEST(0, NULL) is 0 -- hence the explicit branch.
               WHEN min(s.frees_up_at) IS NULL THEN NULL
               -- Clamp an overdue session to 0 rather than reporting a negative wait.
               ELSE round(GREATEST(
                        EXTRACT(EPOCH FROM (min(s.frees_up_at) - now())) / 60.0, 0)::numeric, 2)
           END                                                 AS waiting_time
    FROM connectors c
    LEFT JOIN LATERAL (
        SELECT min(cs.created_at + make_interval(
                   secs => (cs.energy_kwh / NULLIF(cs.power_kw, 0)) * 3600.0)) AS frees_up_at
        FROM charging_sessions cs
        WHERE cs.connector_id = c.id AND cs.status = 'active'
    ) s ON true
    WHERE c.station_id = :sid
    GROUP BY c.type, c.speed_tier, c.power_kw
    ORDER BY c.type, c.speed_tier, c.power_kw
""")


def _status_group(r) -> dict:
    """One (type, speed_tier, power_kw) group of connectors, shaped for the API."""
    wait = r["waiting_time"]
    power_kw = r["power_kw"]
    return {
        "type": r["type"],
        "speed_tier": r["speed_tier"],
        "power_kw": None if power_kw is None else float(power_kw),
        # Real ints, not str(): the client compares and sums these, and "17" > "9"
        # is false in JavaScript while "17" + 1 is "171".
        "available": int(r["available"]),
        "total": int(r["total"]),
        "in_use": int(r["in_use"]),
        "out_of_service": int(r["out_of_service"]),
        "waiting_time": None if wait is None else float(wait),
    }


def get_station_realtime_status(station_id: str) -> dict:
    """Live per-status counts for a station, plus the same breakdown per connector group.

    waiting_time (both levels) is three-state: 0 = a plug is free right now,
    a positive number = minutes until the soonest active session finishes,
    None = unknown, no estimate can be computed.
    """
    with engine.connect() as c:
        rows = c.execute(_REALTIME_STATUS_SQL, {"sid": station_id}).mappings().all()

    if not rows:  # station has no connectors on record: nothing free, nothing to estimate from
        return {
            "station_id": station_id,
            "station_status": 0,
            "available": 0,
            "total": 0,
            "in_use": 0,
            "out_of_service": 0,
            "waiting_time": None,
            "connectors": [],
        }

    connectors = [_status_group(r) for r in rows]
    totals = {k: sum(g[k] for g in connectors) for k in _COUNT_KEYS}
    known_waits = [g["waiting_time"] for g in connectors if g["waiting_time"] is not None]
    if totals["available"] > 0:
        waiting_time = 0.0
    else:
        # min() over an empty sequence raises, and every group being unknown is the
        # normal state of a full station nobody has an active session at.
        waiting_time = min(known_waits) if known_waits else None

    return {
        "station_id": station_id,
        "station_status": 1 if totals["available"] > 0 else 0,
        "available": totals["available"],
        "total": totals["total"],
        "in_use": totals["in_use"],
        "out_of_service": totals["out_of_service"],
        "waiting_time": waiting_time,
        "connectors": connectors,
    }
# </Aidil> 2026-07-29

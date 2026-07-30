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
def get_station_realtime_status(station_id: str) -> dict:
    """Retrieve full status summary for a station including connector status."""
    connectors_sql = """
        SELECT 
            c.type,
            c.speed_tier,
            COUNT(CASE WHEN c.status = 'available' THEN 1 END) AS available,
            COUNT(c.id) AS total,
            CASE 
                -- If all connectors in this group are in use, calculate remaining waiting time in minutes
                WHEN COUNT(CASE WHEN c.status = 'available' THEN 1 END) = 0 THEN
                    ROUND(
                        GREATEST(
                            0,
                            EXTRACT(
                                EPOCH FROM (
                                    MIN(
                                        cs.created_at + (((cs.energy_kwh / NULLIF(cs.power_kw, 0)) * 60.0) || ' minutes')::INTERVAL
                                    ) - NOW()
                                )
                            ) / 60.0
                        )::NUMERIC,
                        2
                    )
                ELSE 0.00 -- Available connectors have 0 waiting time
            END AS waiting_time
        FROM connectors c
        LEFT JOIN charging_sessions cs 
            ON c.id = cs.connector_id 
        AND cs.status = 'active'
        WHERE c.station_id = :sid
        GROUP BY 
            c.station_id,
            c.type,
            c.speed_tier,
            c.power_kw
        ORDER BY c.type, c.speed_tier;
    """
    
    with engine.connect() as c:
        connector_rows = c.execute(text(connectors_sql), {"sid": station_id}).mappings().all()
        
    if not connector_rows:
        return {
            "station_id": station_id,
            "station_status": 0,
            "available": "0",
            "total": "0",
            "waiting_time": 0.0,
            "connectors": []
        }
        
    connectors = []
    total_available = 0
    total_total = 0
    waiting_times = []
    
    for r in connector_rows:
        available_val = int(r["available"])
        total_val = int(r["total"])
        total_available += available_val
        total_total += total_val
        
        # Format waiting_time as string for connectors (e.g. "0" if zero, otherwise decimal string)
        wt = r["waiting_time"]
        if wt is None or float(wt) == 0:
            wt_str = "0"
        else:
            wt_float = float(wt)
            wt_str = str(int(wt_float)) if wt_float.is_integer() else str(wt)
        
        waiting_times.append(float(wt) if wt is not None else 0.0)
        
        connectors.append({
            "type": r["type"],
            "speed_tier": r["speed_tier"],
            "available": str(available_val),
            "total": str(total_val),
            "waiting_time": wt_str
        })
        
    summary = {
        "station_id": station_id,
        "station_status": 1 if total_available > 0 else 0,
        "available": str(total_available),
        "total": str(total_total),
        "waiting_time": 0.0 if total_available > 0 else min(waiting_times),
        "connectors": connectors
    }
    return summary
# </Aidil> 2026-07-29

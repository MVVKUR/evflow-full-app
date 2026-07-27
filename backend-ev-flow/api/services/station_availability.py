"""Live connector availability for a batch of stations (AC 2.2.9).

The `connectors` table -- not `stations.status` or `stations.connector_types` --
is the source of truth for whether a driver can actually plug in right now.

Read-only. Deliberately separate from `api.connectors_repo` so nothing here can
be confused with (or accidentally modify) the money-path occupy/release
functions that run inside charging_repo's transaction.

ONE set-based query covers every candidate station; there is no per-station
round trip.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, NamedTuple, Optional

from sqlalchemy import text

from api.db import engine

_AVAILABILITY_SQL = text("""
    SELECT station_id,
           type,
           count(*)                                           AS total,
           count(*) FILTER (WHERE status = 'available')        AS available,
           count(*) FILTER (WHERE status = 'in_use')           AS in_use,
           count(*) FILTER (WHERE status = 'out_of_service')   AS out_of_service,
           max(power_kw) FILTER (WHERE status = 'available')   AS best_available_power_kw
    FROM connectors
    WHERE station_id = ANY(:ids)
    GROUP BY station_id, type
""")


class StationConnectorAvailability(NamedTuple):
    """Live connector counts for one station, sliced by connector type."""

    station_id: str
    total: int
    available: int
    in_use: int
    out_of_service: int
    available_by_type: Dict[str, int]
    total_by_type: Dict[str, int]
    best_available_power_kw: Optional[float]
    # Best AVAILABLE power per connector type; empty when nothing is free.
    power_by_type: Dict[str, Optional[float]] = {}

    @property
    def available_types(self) -> List[str]:
        return [t for t, n in self.available_by_type.items() if n > 0]

    def available_count_for(self, types: Iterable[str]) -> int:
        wanted = set(types)
        return sum(n for t, n in self.available_by_type.items() if t in wanted and n > 0)

    def best_power_for(self, types: Iterable[str]) -> Optional[float]:
        """Best available power among the requested types (falls back to overall)."""
        wanted = set(types)
        powers = [
            p for t, p in (self.power_by_type or {}).items()
            if t in wanted and p is not None
        ]
        if powers:
            return max(powers)
        return self.best_available_power_kw


def _empty(station_id: str) -> StationConnectorAvailability:
    return StationConnectorAvailability(
        station_id=station_id,
        total=0,
        available=0,
        in_use=0,
        out_of_service=0,
        available_by_type={},
        total_by_type={},
        best_available_power_kw=None,
        power_by_type={},
    )


def fetch_availability(station_ids: Iterable[str]) -> Dict[str, StationConnectorAvailability]:
    """Live availability for every given station id, in ONE query.

    Stations with no connector rows are simply absent from the result: callers
    must treat "absent" as "no free connector", never as "unknown, allow it".
    Returns ``{}`` when the database is unreachable, which the ranker also
    treats as "cannot prove a free connector".
    """
    ids = [str(s) for s in station_ids if s]
    if not ids:
        return {}

    try:
        with engine.connect() as c:
            rows = c.execute(_AVAILABILITY_SQL, {"ids": ids}).mappings().all()
    except Exception:
        return {}

    acc: Dict[str, dict] = {}
    for r in rows:
        sid = str(r["station_id"])
        bucket = acc.setdefault(sid, {
            "total": 0, "available": 0, "in_use": 0, "out_of_service": 0,
            "available_by_type": {}, "total_by_type": {}, "power_by_type": {},
            "best": None,
        })
        ctype = r["type"] or "unknown"
        total = int(r["total"] or 0)
        available = int(r["available"] or 0)
        power = r["best_available_power_kw"]
        power = float(power) if power is not None else None

        bucket["total"] += total
        bucket["available"] += available
        bucket["in_use"] += int(r["in_use"] or 0)
        bucket["out_of_service"] += int(r["out_of_service"] or 0)
        bucket["total_by_type"][ctype] = bucket["total_by_type"].get(ctype, 0) + total
        bucket["available_by_type"][ctype] = bucket["available_by_type"].get(ctype, 0) + available
        if available > 0:
            prev = bucket["power_by_type"].get(ctype)
            if power is not None and (prev is None or power > prev):
                bucket["power_by_type"][ctype] = power
            elif ctype not in bucket["power_by_type"]:
                bucket["power_by_type"][ctype] = power
            if power is not None and (bucket["best"] is None or power > bucket["best"]):
                bucket["best"] = power

    out: Dict[str, StationConnectorAvailability] = {}
    for sid, b in acc.items():
        out[sid] = StationConnectorAvailability(
            station_id=sid,
            total=b["total"],
            available=b["available"],
            in_use=b["in_use"],
            out_of_service=b["out_of_service"],
            available_by_type=b["available_by_type"],
            total_by_type=b["total_by_type"],
            best_available_power_kw=b["best"],
            power_by_type=b["power_by_type"],
        )
    return out


def availability_or_empty(
    availability: Dict[str, StationConnectorAvailability], station_id: str
) -> StationConnectorAvailability:
    return availability.get(str(station_id)) or _empty(str(station_id))

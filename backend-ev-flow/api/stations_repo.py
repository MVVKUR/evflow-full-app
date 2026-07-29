"""All station SQL lives here, isolated from the endpoints. Functions return
plain dicts/tuples that map onto the Pydantic models in api/models.py.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from .db import engine

# geom decomposed back to lat/lon; arrays come back as Python lists.
_COLS = """
    id, name, ST_Y(geom) AS latitude, ST_X(geom) AS longitude, address, province,
    city, operator, power_kw, speed_tier, connector_types, connector_inferred,
    connectors, sources, status, date_verified
"""


def _filter_clauses(filters: dict) -> tuple[list[str], dict]:
    """Build SQL WHERE clauses + params from a filters dict (shared by list + nearby)."""
    clauses, params = [], {}
    if filters.get("source"):
        clauses.append(":source = ANY(sources)"); params["source"] = filters["source"]
    connector_types = list(filters.get("connector_type") or [])
    speed_tiers = list(filters.get("speed_tier") or [])
    if connector_types or speed_tiers:
        connector_checks = []
        if connector_types:
            connector_checks.append("connector->>'type' = ANY(:cts)")
            params["cts"] = connector_types
        if speed_tiers:
            connector_checks.append("connector->>'speed_tier' = ANY(:tiers)")
            params["tiers"] = speed_tiers
        clauses.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements(connectors) AS connector WHERE "
            + " AND ".join(connector_checks)
            + ")"
        )
    if filters.get("province"):
        clauses.append("lower(province) = lower(:prov)"); params["prov"] = filters["province"]
    if filters.get("city"):
        clauses.append("city ILIKE :city"); params["city"] = f"%{filters['city']}%"
    if filters.get("q"):
        clauses.append("name ILIKE :q"); params["q"] = f"%{filters['q']}%"
    if filters.get("min_power") is not None:
        clauses.append("power_kw >= :minp"); params["minp"] = filters["min_power"]
    if filters.get("max_power") is not None:
        clauses.append("power_kw <= :maxp"); params["maxp"] = filters["max_power"]
    if filters.get("bbox"):
        mnlon, mnlat, mxlon, mxlat = filters["bbox"]
        clauses.append("geom && ST_MakeEnvelope(:mnlon,:mnlat,:mxlon,:mxlat,4326)")
        params.update(mnlon=mnlon, mnlat=mnlat, mxlon=mxlon, mxlat=mxlat)
    return clauses, params


def _where(filters: dict) -> tuple[str, dict]:
    clauses, params = _filter_clauses(filters)
    sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def list_stations(filters: dict, limit: int, offset: int) -> tuple[int, list[dict]]:
    where, params = _where(filters)
    with engine.connect() as c:
        total = c.execute(text(f"SELECT count(*) FROM stations{where}"), params).scalar_one()
        rows = c.execute(
            text(f"SELECT {_COLS} FROM stations{where} ORDER BY id LIMIT :lim OFFSET :off"),
            {**params, "lim": limit, "off": offset},
        ).mappings().all()
    return total, [dict(r) for r in rows]


def get_station(station_id: str) -> Optional[dict]:
    with engine.connect() as c:
        row = c.execute(text(f"SELECT {_COLS} FROM stations WHERE id = :id"),
                        {"id": station_id}).mappings().first()
    return dict(row) if row else None


def nearby(lat: float, lon: float, radius_km: float, limit: int,
           filters: Optional[dict] = None) -> list[dict]:
    clauses, params = _filter_clauses(filters or {})
    extra = (" AND " + " AND ".join(clauses)) if clauses else ""
    params.update(lat=lat, lon=lon, r=radius_km * 1000.0, lim=limit)
    sql = f"""
        SELECT {_COLS},
               ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography)/1000.0 AS distance_km
        FROM stations
        WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :r){extra}
        ORDER BY distance_km ASC
        LIMIT :lim
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def along_corridor(
    origin: tuple[float, float],       # (lat, lon)
    destination: tuple[float, float],  # (lat, lon)
    corridor_km: float,
    limit: int,
    buckets: int = 20,
    filters: Optional[dict] = None,
) -> list[dict]:
    """Stations within ``corridor_km`` of the origin->destination line.

    Ordered by PROXIMITY TO THE ROUTE, never by id: `ORDER BY id LIMIT n` returns
    a lexicographic slice of the table, which silently hid the whole
    `pln_spklu-*` network (ids sort after `open_charge_map-*`) from route
    planning.

    The result is also spread ALONG the corridor: stations are bucketed by their
    position on the line and emitted round-robin (closest-to-the-line first in
    every bucket), so a `limit` smaller than the corridor population still
    covers the far end of the trip instead of returning only the dense cluster
    around the origin.
    """
    clauses, params = _filter_clauses(filters or {})
    extra = (" AND " + " AND ".join(clauses)) if clauses else ""
    params.update(
        olat=origin[0], olon=origin[1], dlat=destination[0], dlon=destination[1],
        r=float(corridor_km) * 1000.0, lim=limit, buckets=max(1, int(buckets)),
    )
    sql = f"""
        WITH corridor AS (
            SELECT ST_SetSRID(
                       ST_MakeLine(ST_MakePoint(:olon, :olat), ST_MakePoint(:dlon, :dlat)),
                       4326) AS line
        ),
        candidates AS (
            SELECT {_COLS},
                   ST_Distance(geom::geography, corridor.line::geography) / 1000.0
                       AS corridor_distance_km,
                   ST_LineLocatePoint(corridor.line, geom) AS along_fraction
            FROM stations, corridor
            WHERE ST_DWithin(geom::geography, corridor.line::geography, :r){extra}
        ),
        ranked AS (
            SELECT *,
                   width_bucket(along_fraction, 0.0, 1.0, :buckets) AS corridor_bucket,
                   row_number() OVER (
                       PARTITION BY width_bucket(along_fraction, 0.0, 1.0, :buckets)
                       ORDER BY corridor_distance_km ASC, id ASC
                   ) AS bucket_rank
            FROM candidates
        )
        SELECT * FROM ranked
        ORDER BY bucket_rank ASC, corridor_distance_km ASC, id ASC
        LIMIT :lim
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def count() -> int:
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM stations")).scalar_one()


def source_counts() -> list[tuple[str, int]]:
    sql = "SELECT unnest(sources) AS s, count(*) FROM stations GROUP BY s ORDER BY count(*) DESC"
    with engine.connect() as c:
        return [(r[0], r[1]) for r in c.execute(text(sql)).all()]


def connector_counts() -> list[tuple[str, int]]:
    sql = ("SELECT unnest(connector_types) AS t, count(*) FROM stations "
           "GROUP BY t ORDER BY count(*) DESC")
    with engine.connect() as c:
        return [(r[0], r[1]) for r in c.execute(text(sql)).all()]


def speed_tier_counts() -> dict[str, int]:
    sql = "SELECT speed_tier, count(*) FROM stations WHERE speed_tier IS NOT NULL GROUP BY speed_tier"
    with engine.connect() as c:
        return {r[0]: r[1] for r in c.execute(text(sql)).all()}


def provinces() -> list[tuple[str, int]]:
    sql = ("SELECT province, count(*) FROM stations WHERE province IS NOT NULL "
           "GROUP BY province ORDER BY count(*) DESC")
    with engine.connect() as c:
        return [(r[0], r[1]) for r in c.execute(text(sql)).all()]


def cities(province: Optional[str]) -> list[tuple[str, int]]:
    where = "WHERE city IS NOT NULL"
    params = {}
    if province:
        where += " AND lower(province) = lower(:prov)"; params["prov"] = province
    sql = f"SELECT city, count(*) FROM stations {where} GROUP BY city ORDER BY count(*) DESC"
    with engine.connect() as c:
        return [(r[0], r[1]) for r in c.execute(text(sql), params).all()]


def stats() -> dict:
    with engine.connect() as c:
        total = c.execute(text("SELECT count(*) FROM stations")).scalar_one()
        p = c.execute(text(
            "SELECT count(power_kw), min(power_kw), max(power_kw), round(avg(power_kw)::numeric,2) "
            "FROM stations")).one()
    return {"total": total, "with_power_kw": p[0],
            "power_kw_min": float(p[1]) if p[1] is not None else None,
            "power_kw_max": float(p[2]) if p[2] is not None else None,
            "power_kw_mean": float(p[3]) if p[3] is not None else None}


def routing_coords(source: Optional[str] = None) -> list[dict]:
    """id + lat/lon for every station, for the routing nearest-station scan."""
    where = " WHERE :source = ANY(sources)" if source else ""
    params = {"source": source} if source else {}
    sql = f"SELECT id, ST_Y(geom) AS latitude, ST_X(geom) AS longitude FROM stations{where}"
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


# <Aidil> 2026-07-29
def get_hourly_occupancy(station_id: str) -> dict:
    """Retrieve hourly occupancy data for a station structured by day and hour."""
    sql = """
        SELECT 
            station_id,
            day_of_week,
            CASE day_of_week
                WHEN 1 THEN 'Monday'
                WHEN 2 THEN 'Tuesday'
                WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday'
                WHEN 5 THEN 'Friday'
                WHEN 6 THEN 'Saturday'
                WHEN 7 THEN 'Sunday'
            END AS day_name,
            hour_of_day,
            avg_occupancy
        FROM station_hourly_occupancy
        WHERE station_id = :sid
        ORDER BY 
            day_of_week ASC, 
            hour_of_day ASC;
    """
    with engine.connect() as c:
        rows = c.execute(text(sql), {"sid": station_id}).mappings().all()

    # Structure the flat rows into days -> hours
    days_map = {}
    for r in rows:
        dow = int(r["day_of_week"])
        if dow not in days_map:
            days_map[dow] = {
                "day_of_week": dow,
                "day_name": r["day_name"],
                "hours": []
            }
        days_map[dow]["hours"].append({
            "hour_of_day": int(r["hour_of_day"]),
            "avg_occupancy": float(r["avg_occupancy"]) if r["avg_occupancy"] is not None else 0.0
        })
        
    return {
        "station_id": station_id,
        "days": list(days_map.values())
    }
# </Aidil> 2026-07-29

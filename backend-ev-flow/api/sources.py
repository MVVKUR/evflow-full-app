"""Source loaders + normalization for PLN / OCM / OSM into one row schema.

Reads the STAGING TABLE, never a file. `python -m scripts.ingest_raw` is the one
place a dataset file is opened; it copies each snapshot verbatim into
`raw_station_records` (source, ordinal, source_id, payload jsonb) and this module
reads it back ordered by `ordinal`, which is the record's index in the original
file. Every normalisation rule below -- the chargerbox expansion, the (0,0)
filter, the OSM name fallback, the `or 1` connector counts -- is unchanged, and
`ordinal` guarantees the loaders see the records in the same order they saw them
on disk, so the seeded output is identical: 2931 stations, 6733 connectors.
"""
from __future__ import annotations

import math

from . import connectors

PLN_SOURCE = "pln_spklu"
OCM_SOURCE = "open_charge_map"
OSM_SOURCE = "osm"

COLUMNS = [
    "id", "name", "source", "latitude", "longitude", "address", "province",
    "city", "operator", "power_kw", "charge_type", "connectors", "status",
    "date_verified",
]


_STAGED = (
    "SELECT payload FROM raw_station_records "
    "WHERE source = :source ORDER BY ordinal"
)


def _staged(source: str) -> list[dict]:
    """Every staged record for one feed, in the order it had in the file.

    An empty list means the snapshot has not been ingested. That is the same
    answer the file loaders gave for a missing file, so `normalized_rows` keeps
    behaving the way it always did; `scripts/seed_db.py` is where the "you
    forgot to run the ingest" guard lives, because that is the step that would
    otherwise wipe the stations table and replace it with nothing.
    """
    from sqlalchemy import text

    from .db import engine

    with engine.connect() as conn:
        rows = conn.execute(text(_STAGED), {"source": source}).scalars().all()
    return [r for r in rows if isinstance(r, dict)]


def _raw_pln() -> list[dict]:
    return _staged(PLN_SOURCE)


def _raw_ocm() -> list[dict]:
    return _staged(OCM_SOURCE)


def _raw_osm() -> list[dict]:
    """OSM *elements*, already unwrapped from the Overpass envelope at ingest."""
    return _staged(OSM_SOURCE)


def _num(v) -> float:
    try:
        return float(str(v).split()[0])
    except (TypeError, ValueError, IndexError):
        return math.nan


def _box_count(v) -> int:
    """Connector count for one chargerbox, from PLN's `jumlah_konektor`.

    The field arrives as a string ("1", "2", ...) and is "0" for 13 boxes in the
    production dump. A chargerbox that exists physically cannot have zero plugs,
    so 0 / missing / unparseable all mean "unknown" and fall back to 1 -- the
    same `or 1` rule `_load_ocm` applies to a null `Quantity` and the
    station-level path applies to a missing `total_konektor`. Dropping the box
    instead would also throw away its power and its connector type.
    """
    n = _num(v)
    if math.isnan(n):
        return 1
    return int(n) if n >= 1 else 1


def _pln_connections(r: dict) -> list[dict] | None:
    """One connection entry per chargerbox, shaped like `_load_ocm`'s.

    PLN's station-level `total_konektor` is 0 for every record in the feed; the
    real inventory lives in `chargerboxes`, where each box carries its own
    `watt`, `type_charge` and `jumlah_konektor`. Boxes at different power levels
    therefore become different connector entries instead of collapsing into one.

    Returns None when the array is absent or unusable, which leaves the station
    on the legacy station-level path in `normalized_rows` (one connection from
    `watt` + `total_konektor`) so those records behave exactly as before.
    """
    boxes = r.get("chargerboxes")
    if not isinstance(boxes, list) or not boxes:
        return None
    station_power = _clean_power(_num(r.get("watt")))
    station_type = r.get("type_charge")
    out = []
    for b in boxes:
        if not isinstance(b, dict):
            continue
        # A box with no readable `watt` falls back to the station's own power
        # (what this station reported before this change) rather than losing its
        # power entirely, which would also cost it its inferred connector type.
        power = _clean_power(_num(b.get("watt")))
        out.append({
            "power_kw": station_power if power is None else power,
            "count": _box_count(b.get("jumlah_konektor")),
            "charge_type": b.get("type_charge") or station_type,
        })
    return out or None


def _load_pln() -> list[dict]:
    out = []
    for r in _raw_pln():
        try:
            lat, lon = float(r.get("latitude")), float(r.get("longitude"))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)) or (lat == 0 and lon == 0):
            continue
        out.append({
            "id": f"pln_spklu-{r.get('id')}",
            "name": r.get("nama_lokasi"),
            "source": "pln_spklu",
            "latitude": lat, "longitude": lon,
            "address": r.get("alamat"),
            "province": (r.get("provinsi") or "").strip() or None,
            "city": r.get("kabupaten_kota"),
            "operator": "PLN",
            "power_kw": _num(r.get("watt")),
            "charge_type": r.get("type_charge"),
            "_connections": _pln_connections(r),
            "connectors": r.get("total_konektor") or None,
            "status": "operational" if r.get("status") == 1 else (str(r.get("status")) if r.get("status") is not None else None),
            "date_verified": None,
        })
    return out


def _load_ocm() -> list[dict]:
    out = []
    # `i` is the record's position in the snapshot and is the id of last resort
    # for a record with no `ID`. The staging read is ordered by `ordinal`, which
    # IS that position, so this enumerate reproduces the file-based ids exactly.
    for i, p in enumerate(_raw_ocm()):
        ai = p.get("AddressInfo") or {}
        lat, lon = ai.get("Latitude"), ai.get("Longitude")
        if lat is None or lon is None:
            continue
        conns = p.get("Connections") or []
        power = [c.get("PowerKW") for c in conns if c.get("PowerKW")]
        stat = (p.get("StatusType") or {}).get("IsOperational")
        out.append({
            "id": f"open_charge_map-{p.get('ID', i)}",
            "name": ai.get("Title"),
            "source": "open_charge_map",
            "latitude": float(lat), "longitude": float(lon),
            "address": ai.get("AddressLine1"),
            "province": ai.get("StateOrProvince"),
            "city": ai.get("Town"),
            "operator": (p.get("OperatorInfo") or {}).get("Title"),
            "power_kw": max(power) if power else math.nan,
            "_connections": [{"power_kw": c.get("PowerKW"), "count": c.get("Quantity") or 1}
                             for c in conns],
            "charge_type": None,
            "connectors": p.get("NumberOfPoints") or None,
            "status": None if stat is None else ("operational" if stat else "non-operational"),
            "date_verified": p.get("DateLastVerified"),
        })
    return out


def _load_osm() -> list[dict]:
    out = []
    for el in _raw_osm():
        tags = el.get("tags", {}) or {}
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        # Fall back through the other identity tags OSM uses for charging
        # stations (many SPKLU nodes carry only `brand`/`ref`, not `name`).
        name = (tags.get("name") or tags.get("name:en") or tags.get("brand")
                or tags.get("operator") or tags.get("network") or tags.get("ref"))
        operator = tags.get("operator") or tags.get("brand") or tags.get("network")
        out.append({
            "id": f"osm-{el['type']}-{el['id']}",
            "name": name,
            "source": "osm",
            "latitude": float(lat), "longitude": float(lon),
            "address": tags.get("addr:full") or tags.get("addr:street"),
            "province": None,
            "city": tags.get("addr:city"),
            "operator": operator,
            "power_kw": _num(tags.get("charging_station:output") or tags.get("socket:type2_combo:output")),
            "charge_type": None,
            "connectors": int(_num(tags.get("capacity"))) if not math.isnan(_num(tags.get("capacity"))) else None,
            "status": tags.get("access"),
            "date_verified": None,
        })
    return out


def _clean_power(p):
    if p is None:
        return None
    if isinstance(p, float) and math.isnan(p):
        return None
    return float(p)


def _build_connectors(conns_in: list[dict], charge_type) -> list[dict]:
    """`connectors.build_connectors`, honouring a per-connection `charge_type`.

    `build_connectors` takes ONE station-level charge_type -- that is the agreed
    inference model and is deliberately left alone -- but a PLN site can hold a
    `medium` AC box next to an `ultrafast` DC one. Each connection is therefore
    built on its own (falling back to the station's charge_type when the entry
    has none, which is every OCM/OSM entry) and the results are merged on
    (type, power_kw) with counts summed: the same key, the same sum rule and the
    same first-seen ordering `build_connectors` uses internally, so a list whose
    entries all share one charge_type comes out byte-identical to before.

    Merged entries keep the first contributor's speed_tier. That only differs
    from the later one when power_kw is unknown AND the two charge_types map to
    different tiers, in which case the first box listed at the site wins.
    """
    agg: dict = {}
    order: list = []
    for c in conns_in:
        for built in connectors.build_connectors([c], c.get("charge_type") or charge_type):
            key = (built["type"], built["power_kw"])
            if key in agg:
                agg[key]["count"] += built["count"]
            else:
                agg[key] = built
                order.append(key)
    return [agg[k] for k in order]


def normalized_rows() -> list[dict]:
    """All source rows, normalized, each with a `connectors` list + derived fields."""
    rows = _load_pln() + _load_ocm() + _load_osm()
    out = []
    for r in rows:
        if r.get("latitude") is None or r.get("longitude") is None:
            continue
        conns_in = r.get("_connections")
        if conns_in is None:  # OSM, PLN without chargerboxes (and tests): station power + count
            conns_in = [{"power_kw": _clean_power(r.get("power_kw")), "count": r.get("connectors") or 1}]
        r["connectors"] = _build_connectors(conns_in, r.get("charge_type"))
        derived = connectors.derive_station_fields(r["connectors"])
        r["connector_types"] = derived["connector_types"]
        r["speed_tier"] = derived["speed_tier"]
        r["power_kw"] = derived["power_kw"]
        r["connector_inferred"] = derived["connector_inferred"]
        out.append(r)
    return out

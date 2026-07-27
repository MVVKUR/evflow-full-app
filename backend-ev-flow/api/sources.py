"""Source loaders + normalization for PLN / OCM / OSM into one row schema."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from . import connectors

# dataset/data/raw  (this file lives in dataset/api/)
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(os.getenv("RAW_DIR", ROOT / "data" / "raw"))

PLN_PATH = RAW_DIR / "_petaspklu_all.json"
OCM_PATH = RAW_DIR / "ocm_jakarta.json"
OSM_PATH = RAW_DIR / "osm_charging_jakarta.json"

COLUMNS = [
    "id", "name", "source", "latitude", "longitude", "address", "province",
    "city", "operator", "power_kw", "charge_type", "connectors", "status",
    "date_verified",
]


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
    if not PLN_PATH.exists():
        return []
    raw = json.loads(PLN_PATH.read_text(encoding="utf-8"))
    out = []
    for r in raw:
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
    if not OCM_PATH.exists():
        return []
    raw = json.loads(OCM_PATH.read_text(encoding="utf-8"))
    out = []
    for i, p in enumerate(raw):
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
    if not OSM_PATH.exists():
        return []
    payload = json.loads(OSM_PATH.read_text(encoding="utf-8"))
    out = []
    for el in payload.get("elements", []):
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

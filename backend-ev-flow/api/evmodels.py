"""EV model catalogue (Kaggle Indonesia-EV-2026 enriched with 2025 specs).

Database-backed repository reading from PostgreSQL `ev_models` table with
a JSON file and zip fallback for offline test runs and local development.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "processed" / "ev_models_enriched.json"
CSV_PATH = Path(os.getenv("EV_DATASET_CSV", ROOT / "data" / "raw" / "indonesia_ev_specs_pricing_2026.csv"))
ZIP_PATH = ROOT / "ev_dataset.zip"
ZIP_MEMBER = "indonesia_ev_specs_pricing_2026.csv"

RANGE_SAFETY_FACTOR = float(os.getenv("ROUTING_RANGE_SAFETY_FACTOR", 0.85))

_MODELS_CACHE: Optional[List[Dict[str, Any]]] = None


def _slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _numbers(s) -> list:
    if not s:
        return []
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(s))]


def _min_num(s) -> Optional[float]:
    nums = _numbers(s)
    return min(nums) if nums else None


# Catalogue columns declared numeric(8,2)/numeric come back from psycopg as
# Decimal. Mixing Decimal with float (min(), '/') raises TypeError deep inside
# the energy math and surfaces as an HTTP 500, so every numeric is coerced to
# float at the repository boundary and no Decimal ever escapes this module.
_NUMERIC_FIELDS = (
    "battery_kwh", "battery_kwh_min", "battery_kwh_max",
    "range_km", "range_km_min", "range_km_max",
    "efficiency_wh_per_km", "max_dc_charge_kw", "fast_charging_power_kw_dc",
    "charging_time_minutes", "match_confidence", "power_hp", "seats", "top_speed_kmh",
)


def _to_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_numerics(model: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with every known numeric field as a plain float (or None)."""
    out = dict(model)
    for field in _NUMERIC_FIELDS:
        if field in out:
            out[field] = _to_float(out[field])
    # `max_dc_charge_kw` was never populated by the importer; the DC power that
    # IS populated lives in `fast_charging_power_kw_dc`. Migration 0013
    # backfills the column, and this keeps older/partial databases working too.
    if not out.get("max_dc_charge_kw"):
        fallback = out.get("fast_charging_power_kw_dc")
        if fallback:
            out["max_dc_charge_kw"] = fallback
    return out


def _load_from_db() -> List[Dict[str, Any]]:
    try:
        from sqlalchemy import text
        from api.db import engine

        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, name, make, model, brand, battery_kwh, range_km, efficiency_wh_per_km,
                       efficiency_source,
                       COALESCE(max_dc_charge_kw::double precision, fast_charging_power_kw_dc)
                           AS max_dc_charge_kw,
                       fast_charging_power_kw_dc,
                       fast_charge_port, price_range, charging_time_minutes, source_url
                FROM ev_models
                ORDER BY name ASC;
            """)).mappings().all()
            if rows:
                return [coerce_numerics(dict(r)) for r in rows]
    except Exception:
        pass
    return []


def _load_from_json() -> List[Dict[str, Any]]:
    if JSON_PATH.exists():
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _read_raw_rows() -> list:
    if CSV_PATH.exists():
        with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    if ZIP_PATH.exists():
        with zipfile.ZipFile(ZIP_PATH) as z:
            member = ZIP_MEMBER if ZIP_MEMBER in z.namelist() else next(
                (n for n in z.namelist() if n.endswith(".csv")), None)
            if member is None:
                return []
            with z.open(member) as fh:
                return list(csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")))
    return []


def _parse_fallback(row: dict) -> Optional[dict]:
    name = (row.get("name") or row.get("Vehicle Name") or "").strip()
    if not name:
        return None
    parts = name.split()
    brand = (row.get("brand") or row.get("make") or parts[0]).strip()
    make = brand
    model = (row.get("model") or (" ".join(parts[1:]) if len(parts) > 1 else name)).strip()

    bat_kwh = _min_num(row.get("battery_kwh") or row.get("Battery Capacity"))
    range_km = _min_num(row.get("range_km") or row.get("Range (Jarak Tempuh)"))

    eff = _min_num(row.get("efficiency_wh_per_km"))
    eff_src = "dataset"
    if eff is None and bat_kwh and range_km and range_km > 0:
        eff = round((bat_kwh * 1000.0) / range_km, 2)
        eff_src = "derived_local_specs"

    return {
        "id": row.get("id") or _slug(name),
        "brand": brand,
        "name": name,
        "make": make,
        "model": model,
        "battery_kwh": bat_kwh,
        "range_km": range_km,
        "efficiency_wh_per_km": eff,
        "efficiency_source": eff_src,
        "max_dc_charge_kw": _min_num(row.get("fast_charging_power_kw_dc")),
        "fast_charge_port": (row.get("fast_charge_port") or "").strip() or None,
        "price_range": (row.get("price_range") or row.get("Vehicle Price Range") or "").strip() or None,
        "charging_time_minutes": _min_num(row.get("charging_time_minutes") or row.get("charging_time") or row.get("Charging time")),
        "source_url": (row.get("source_url") or row.get("Source URL") or "").strip() or None,
    }


def load() -> List[Dict[str, Any]]:
    """Return EV model catalogue, trying DB first, then JSON, then raw fallback."""
    global _MODELS_CACHE
    if _MODELS_CACHE is not None:
        return _MODELS_CACHE

    db_models = _load_from_db()
    if db_models:
        _MODELS_CACHE = db_models
        return _MODELS_CACHE

    json_models = _load_from_json()
    if json_models:
        _MODELS_CACHE = [coerce_numerics(m) for m in json_models]
        return _MODELS_CACHE

    seen: dict = {}
    for row in _read_raw_rows():
        m = _parse_fallback(row)
        if m and m["id"] not in seen:
            seen[m["id"]] = coerce_numerics(m)
    _MODELS_CACHE = list(seen.values())
    return _MODELS_CACHE


def reload() -> List[Dict[str, Any]]:
    """Force cache clear and reload."""
    global _MODELS_CACHE
    _MODELS_CACHE = None
    return load()


def get(model_id: str) -> Optional[Dict[str, Any]]:
    return next((m for m in load() if m["id"] == model_id), None)


def search(q: Optional[str], limit: int, offset: int):
    models = load()
    if q:
        ql = q.casefold()
        models = [m for m in models if ql in m["name"].casefold()]
    return len(models), models[offset: offset + limit]


def remaining_range_km(range_km: Optional[float], soc_percent: float,
                       safety_factor: float = RANGE_SAFETY_FACTOR) -> Optional[float]:
    if range_km is None:
        return None
    return round(range_km * (soc_percent / 100.0) * safety_factor, 2)

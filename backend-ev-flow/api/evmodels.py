"""EV model catalogue. DATABASE ONLY.

The catalogue is the `ev_models` table, populated by
`python -m scripts.ingest_raw` from the union of the two EV datasets (535
models: 60 Indonesian, 478 global, 3 shared ids merged). There is no JSON, CSV
or zip fallback any more, on purpose.

WHY IT RAISES INSTEAD OF RETURNING AN EMPTY CATALOGUE
-----------------------------------------------------
The removed fallbacks did not fail -- they answered. A database outage or a
forgotten ingest used to be served as a slightly older, slightly different
catalogue from a file nobody was watching, and the only symptom was that a
driver's saved vehicle quietly stopped existing. Returning `[]` here would be
the same defect wearing different clothes: `GET /api/v1/ev-models` would answer
`200 {"total": 0}` ("we sell no cars") and `POST /api/v1/route-plans` would
answer `404 Unknown EV model` ("your car is not real"), both of which are
plausible, actionable-looking, and wrong.

`CatalogueUnavailable` is therefore raised, and `api/main.py` maps it to
**503 Service Unavailable** with the remedy in the message. 503 is the truth: a
dependency is down, the request was not refused on its merits, and a client is
free to retry. An operator reading the log sees "run scripts/ingest_raw", not a
404 that looks like a user error.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RANGE_SAFETY_FACTOR = float(os.getenv("ROUTING_RANGE_SAFETY_FACTOR", 0.85))

_MODELS_CACHE: Optional[List[Dict[str, Any]]] = None


class CatalogueUnavailable(RuntimeError):
    """The `ev_models` catalogue could not be served: DB down, or never ingested."""


# The client is told WHAT is wrong and WHAT to do; it is not told WHERE the
# database lives. `str(exc)` on a psycopg/SQLAlchemy failure carries the DSN --
# host, port, user, sometimes the database name -- and `api/main.py` puts this
# message straight into the 503 body, which is reachable without a token. The
# driver's own text is logged instead, where an operator can read it and an
# attacker cannot. See `_load_from_db`.
_UNREACHABLE = ("EV model catalogue unavailable: the database is not reachable. "
                "The catalogue is served from the ev_models table only; retry, "
                "and if it persists check the API's database connection.")
_EMPTY = ("EV model catalogue is empty: the ev_models table has no rows. "
          "Run `python -m alembic upgrade head` then `python -m scripts.ingest_raw`.")


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


_SELECT = """
    SELECT id, name, make, model, brand, battery_kwh, range_km, efficiency_wh_per_km,
           efficiency_source,
           COALESCE(max_dc_charge_kw::double precision, fast_charging_power_kw_dc)
               AS max_dc_charge_kw,
           fast_charging_power_kw_dc,
           fast_charge_port, price_range, charging_time_minutes, source_url
    FROM ev_models
    ORDER BY name ASC;
"""


def _load_from_db() -> List[Dict[str, Any]]:
    """Every model in the table. Raises `CatalogueUnavailable` if the DB is down.

    An empty table is NOT an error here -- it is `load()` that decides an empty
    catalogue cannot be served -- so the two failures stay distinguishable.
    """
    from sqlalchemy import text

    from api.db import engine

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(_SELECT)).mappings().all()
    except CatalogueUnavailable:
        raise
    except Exception as exc:  # driver / network / missing table
        # Full detail server-side, generic detail on the wire. The original
        # exception stays chained (`from exc`) so a traceback still has it.
        logger.error("ev_models query failed, serving 503: %s: %s",
                     type(exc).__name__, exc, exc_info=True)
        raise CatalogueUnavailable(_UNREACHABLE) from exc
    return [coerce_numerics(dict(r)) for r in rows]


def load() -> List[Dict[str, Any]]:
    """The EV model catalogue, from the database. Never from a file."""
    global _MODELS_CACHE
    if _MODELS_CACHE is not None:
        return _MODELS_CACHE

    models = _load_from_db()
    if not models:
        raise CatalogueUnavailable(_EMPTY)
    _MODELS_CACHE = models
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

"""Build the `ev_models` UNION from the two EV datasets.

Pure functions: no database, no file system. `scripts/ingest_raw.py` reads the
CSVs and hands the rows here; the tests call these directly.

THE GAP THIS CLOSES
-------------------
`ev_models` used to hold only the 60 Indonesian models. The 478 rows of
`electric_vehicles_spec_2025.csv` were read as an enrichment *lookup* and thrown
away, which is why the team's ER diagram lists spec columns (torque, segment,
dimensions...) that did not exist in any table. Both datasets are now stored.

  478 global rows  +  60 local rows  -  3 shared ids  =  535 models

IDS
---
`slug()` is the existing `_slug` with one addition: a literal '+' becomes the
word "plus" before slugification. Without it the five "+" trims in the global
feed (Mercedes-Benz EQA 250 vs EQA 250+, Smart #1 Pro vs #1 Pro+, ...) collapse
onto their non-plus sibling and five genuinely different cars -- different
battery, different range, different efficiency -- silently become one. No name in
the local feed contains '+', so local ids are byte-identical to the ones already
in production ('byd-m6', 'byd-seal', 'wuling-air-ev').

THE ENRICHMENT IS NOT THE UNION'S TO INVENT
-------------------------------------------
The union changes WHICH rows exist. It must not change what a local model's
spec fields SAY. Those fields -- efficiency, DC power, charge port, top speed,
body type, drivetrain -- and the brand casing come from
`scripts/wrangle_ev_dataset.py`, which is the code path that produced
`data/processed/indonesia_ev_cleaned.csv`, which migration 0010 loads into the
live `ev_models` table. `local_record` therefore calls
`wrangle_ev_dataset.enrichment_for` rather than deriving anything of its own.

Getting this wrong is not cosmetic. `api/services/connector_compat.py` reads
`fast_charge_port` to decide which plugs a car can use, so a NULL port demotes
every Indonesian model to AC Type 2 and a BYD M6 driver is never offered a CCS2
station; and a NULL `max_dc_charge_kw` makes the energy estimator fall back to a
hardcoded 50 kW, which is 2.5x optimistic for a 20 kW Wuling Air EV.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.import_ev_models import (_parse_charging_time_minutes,
                                      _parse_range_bounds, _slug)
from scripts.wrangle_ev_dataset import (_extract_brand, _extract_model,
                                        enrichment_for)

LOCAL_DATASET = "indonesia_ev_specs_pricing_2026.csv"
GLOBAL_DATASET = "electric_vehicles_spec_2025.csv"

#: Efficiency that the global feed MEASURED, as opposed to one derived from
#: battery / range. Stored in `ev_models.efficiency_source`.
EFFICIENCY_MEASURED = GLOBAL_DATASET
EFFICIENCY_DERIVED = "derived_local_specs"

#: An efficiency that came from the local enrichment gets NO `efficiency_source`,
#: because production records none: migration 0010 never wrote the column, so all
#: 60 local models serve NULL there and `api/main.py` renders that as "dataset".
#: Writing a source string here would change what every route plan reports for
#: every Indonesian model, which is exactly the kind of drift this union is not
#: allowed to introduce. The provenance is still recorded -- in `match_method`.
EFFICIENCY_ENRICHED_SOURCE = None

#: `match_method` values for a local model, by where its enrichment came from.
MATCH_LOCAL_ONLY = "canonical_local_only"
MATCH_LOCAL_GLOBAL_SPEC = "local_enriched_global_spec"
MATCH_LOCAL_CURATED = "local_enriched_curated"

#: Every column the ingest writes, in one place so the INSERT, the merge and the
#: tests cannot drift apart.
COLUMNS: Tuple[str, ...] = (
    "id", "name", "make", "model", "brand",
    "battery_kwh", "battery_kwh_min", "battery_kwh_max",
    "range_km", "range_km_min", "range_km_max",
    "efficiency_wh_per_km", "efficiency_source",
    "max_dc_charge_kw", "fast_charging_power_kw_dc", "fast_charge_port",
    "price_range", "charging_time_minutes", "power_hp", "seats",
    "top_speed_kmh", "car_body_type", "drivetrain", "source_url",
    "torque_nm", "acceleration_0_100_s", "battery_type", "number_of_cells",
    "towing_capacity_kg", "cargo_volume_l", "segment",
    "length_mm", "width_mm", "height_mm",
    "source_datasets", "source_payload", "match_method", "match_confidence",
)


def slug(name: str) -> str:
    """`_slug`, but '+' survives as the word "plus" instead of vanishing."""
    return _slug(str(name).replace("+", " plus "))


def _strict_num(value: Any) -> Optional[float]:
    """Number only when the WHOLE field is one.

    Deliberately not a "leading number" parser. `cargo_volume_l` holds
    "10 Banana Boxes" in three rows of the global feed; reading that as 10 litres
    would publish a wrong number that looks exactly like a right one, so it
    becomes NULL and the verbatim string stays in `source_payload`.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _strict_int(value: Any) -> Optional[int]:
    n = _strict_num(value)
    return None if n is None else int(n)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# --- the Indonesian (local) dataset -----------------------------------------

def _planner_dc_kw(fast_charging_power_kw_dc: Optional[float]) -> Optional[float]:
    """`max_dc_charge_kw` as migration 0013 fills it: the DC power, rounded to 2dp.

    Two columns hold the same quantity -- `fast_charging_power_kw_dc` is what the
    feeds carry, `max_dc_charge_kw` (numeric(8,2)) is what the route planner
    reads -- and 0013 backfills the second from the first `WHERE ... > 0`.
    Reproducing that here keeps a freshly-ingested database identical to a
    migrated one instead of relying on a backfill that only runs once.
    """
    if not fast_charging_power_kw_dc or fast_charging_power_kw_dc <= 0:
        return None
    return round(float(fast_charging_power_kw_dc), 2)


def local_record(row: Dict[str, str],
                 global_rows: Sequence[Dict[str, str]] = ()) -> Optional[Dict[str, Any]]:
    """One row of indonesia_ev_specs_pricing_2026.csv as an ev_models record.

    Parsing is the importer's, unchanged: a "51 - 64 kWh" range keeps its
    conservative lower bound as the headline figure and both bounds alongside,
    and "8.5 Jam" becomes 510 minutes.

    Brand, model and the six enrichment fields are `wrangle_ev_dataset`'s,
    unchanged, because they are what production already publishes -- see the
    module docstring. `global_rows` is the 2025 spec feed the enrichment matches
    against; passing none is legal and simply leaves the hand-curated table as
    the only source, which is what the pure unit tests exercise.

    Efficiency falls back to `battery * 1000 / range` ONLY when the enrichment
    has nothing to say. That fallback is flagged in `efficiency_source` so the
    merge below can let a measured global figure beat it; an enriched value is
    never overridden, because production's value is the contract.
    """
    name = _text(row.get("Vehicle Name"))
    if not name:
        return None

    model_id = slug(name)
    brand = _extract_brand(name)
    model = _extract_model(name, brand)

    bat, bat_min, bat_max = _parse_range_bounds(row.get("Battery Capacity"))
    rng, rng_min, rng_max = _parse_range_bounds(row.get("Range (Jarak Tempuh)"))

    enrichment = enrichment_for(model_id, brand, model, name, list(global_rows))
    spec = enrichment.fields

    efficiency = spec["efficiency_wh_per_km"]
    efficiency_source = EFFICIENCY_ENRICHED_SOURCE
    if efficiency is None and bat is not None and rng:
        efficiency = round((bat * 1000.0) / rng, 2)
        efficiency_source = EFFICIENCY_DERIVED

    if enrichment.matched_global_row is not None:
        match_method, match_confidence = MATCH_LOCAL_GLOBAL_SPEC, 0.85
    elif enrichment.curated:
        match_method, match_confidence = MATCH_LOCAL_CURATED, 1.0
    else:
        match_method, match_confidence = MATCH_LOCAL_ONLY, 1.0

    return {
        "id": model_id,
        "name": name,
        "make": brand,
        "model": model,
        "brand": brand,
        "battery_kwh": bat, "battery_kwh_min": bat_min, "battery_kwh_max": bat_max,
        "range_km": rng, "range_km_min": rng_min, "range_km_max": rng_max,
        "efficiency_wh_per_km": efficiency,
        "efficiency_source": efficiency_source,
        "max_dc_charge_kw": _planner_dc_kw(spec["fast_charging_power_kw_dc"]),
        "fast_charging_power_kw_dc": spec["fast_charging_power_kw_dc"],
        "fast_charge_port": spec["fast_charge_port"],
        "price_range": _text(row.get("Vehicle Price Range")),
        "charging_time_minutes": _parse_charging_time_minutes(row.get("Charging time")),
        "power_hp": _text(row.get("Power/Horsepower")),
        "seats": _strict_int((_text(row.get("Seating Capacity")) or "").split(" ")[0]),
        "top_speed_kmh": spec["top_speed_kmh"],
        "car_body_type": spec["car_body_type"],
        "drivetrain": spec["drivetrain"],
        "source_url": _text(row.get("Source URL")),
        "torque_nm": None, "acceleration_0_100_s": None, "battery_type": None,
        "number_of_cells": None, "towing_capacity_kg": None, "cargo_volume_l": None,
        "segment": None, "length_mm": None, "width_mm": None, "height_mm": None,
        "source_datasets": [LOCAL_DATASET],
        "source_payload": {LOCAL_DATASET: dict(row)},
        "match_method": match_method,
        "match_confidence": match_confidence,
    }


# --- the global (2025 spec) dataset ------------------------------------------

def global_record(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """One row of electric_vehicles_spec_2025.csv as an ev_models record."""
    brand = _text(row.get("brand"))
    model = _text(row.get("model"))
    if not brand and not model:
        return None
    name = " ".join(p for p in (brand, model) if p)

    battery = _strict_num(row.get("battery_capacity_kWh"))
    range_km = _strict_num(row.get("range_km"))
    dc_kw = _strict_num(row.get("fast_charging_power_kw_dc"))

    return {
        "id": slug(name),
        "name": name,
        "make": brand,
        "model": model,
        "brand": brand,
        "battery_kwh": battery, "battery_kwh_min": battery, "battery_kwh_max": battery,
        "range_km": range_km, "range_km_min": range_km, "range_km_max": range_km,
        "efficiency_wh_per_km": _strict_num(row.get("efficiency_wh_per_km")),
        "efficiency_source": (EFFICIENCY_MEASURED
                              if _strict_num(row.get("efficiency_wh_per_km")) is not None
                              else None),
        "max_dc_charge_kw": dc_kw,
        "fast_charging_power_kw_dc": dc_kw,
        "fast_charge_port": _text(row.get("fast_charge_port")),
        "price_range": None,
        "charging_time_minutes": None,
        "power_hp": None,
        "seats": _strict_int(row.get("seats")),
        "top_speed_kmh": _strict_num(row.get("top_speed_kmh")),
        "car_body_type": _text(row.get("car_body_type")),
        "drivetrain": _text(row.get("drivetrain")),
        "source_url": _text(row.get("source_url")),
        "torque_nm": _strict_num(row.get("torque_nm")),
        "acceleration_0_100_s": _strict_num(row.get("acceleration_0_100_s")),
        "battery_type": _text(row.get("battery_type")),
        "number_of_cells": _strict_int(row.get("number_of_cells")),
        "towing_capacity_kg": _strict_int(row.get("towing_capacity_kg")),
        "cargo_volume_l": _strict_int(row.get("cargo_volume_l")),
        "segment": _text(row.get("segment")),
        "length_mm": _strict_int(row.get("length_mm")),
        "width_mm": _strict_int(row.get("width_mm")),
        "height_mm": _strict_int(row.get("height_mm")),
        "source_datasets": [GLOBAL_DATASET],
        "source_payload": {GLOBAL_DATASET: dict(row)},
        "match_method": "global_spec_only",
        "match_confidence": 1.0,
    }


# --- the union ---------------------------------------------------------------

def merge(local: Dict[str, Any], world: Dict[str, Any]) -> Dict[str, Any]:
    """Merge the two records that share an id. Neither one overwrites the other.

    Rules, and why:

    * Start from the global record, then let every NON-NULL local value win.
      The local feed describes the trim actually sold in Indonesia -- its price,
      its charging time, its marketing name -- and its battery/range bounds come
      from that market's published figures. Anything the local feed does not
      carry (torque, dimensions, segment, DC port...) is simply kept.
    * The MEASURED efficiency beats a DERIVED one. The derived value is
      `battery * 1000 / range`, an arithmetic consequence of two other columns;
      the global value was measured. `efficiency_source` records which one won,
      so no caller has to guess.
    * It does NOT beat an ENRICHED one. When the local record's efficiency came
      from `wrangle_ev_dataset` it is, by definition, the number production
      already publishes for that model, and the ids that collide are local
      models ('citroen-e-c3', 'porsche-taycan', 'rolls-royce-spectre' today).
      Letting the global feed win there would restate those cars' range and
      charging estimates as a side effect of adding 478 unrelated rows. The
      union is allowed to add rows, not to rewrite the ones already served.
    * `source_datasets` lists both files and `source_payload` keeps both raw rows
      keyed by file name, so every field is traceable to the dataset it came
      from even where the two disagree.
    """
    merged = dict(world)
    for key, value in local.items():
        if value is not None:
            merged[key] = value

    local_efficiency_is_replaceable = (
        local.get("efficiency_wh_per_km") is None
        or local.get("efficiency_source") == EFFICIENCY_DERIVED)
    if world.get("efficiency_wh_per_km") is not None and local_efficiency_is_replaceable:
        merged["efficiency_wh_per_km"] = world["efficiency_wh_per_km"]
        merged["efficiency_source"] = EFFICIENCY_MEASURED
    else:
        merged["efficiency_source"] = local.get("efficiency_source")

    merged["source_datasets"] = [LOCAL_DATASET, GLOBAL_DATASET]
    merged["source_payload"] = {**world["source_payload"], **local["source_payload"]}
    merged["match_method"] = "union_merge_local_and_global"
    merged["match_confidence"] = 1.0
    return merged


def build_union(local_rows: Iterable[Dict[str, str]],
                global_rows: Iterable[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Both datasets as one de-duplicated catalogue, plus a summary.

    Within a single dataset the first row for an id wins; across datasets the
    two are merged. Order is deterministic: local models first (they are what
    this deployment sells), then the global-only ones.
    """
    # Materialised once: the local enrichment matches every model against the
    # whole global feed, so a one-shot iterator would be exhausted after the
    # first row and 59 of the 60 local models would lose their spec fields.
    global_rows = list(global_rows)

    locals_by_id: Dict[str, Dict[str, Any]] = {}
    local_dupes = 0
    for row in local_rows:
        record = local_record(row, global_rows)
        if record is None:
            continue
        if record["id"] in locals_by_id:
            local_dupes += 1
            continue
        locals_by_id[record["id"]] = record

    globals_by_id: Dict[str, Dict[str, Any]] = {}
    global_dupes = 0
    for row in global_rows:
        record = global_record(row)
        if record is None:
            continue
        if record["id"] in globals_by_id:
            global_dupes += 1
            continue
        globals_by_id[record["id"]] = record

    collisions = sorted(set(locals_by_id) & set(globals_by_id))
    out: List[Dict[str, Any]] = []
    for model_id, record in locals_by_id.items():
        world = globals_by_id.get(model_id)
        out.append(merge(record, world) if world else record)
    for model_id, record in globals_by_id.items():
        if model_id not in locals_by_id:
            out.append(record)

    measured = sum(1 for r in out if r["efficiency_source"] == EFFICIENCY_MEASURED)
    # An enriched local efficiency carries no source (see EFFICIENCY_ENRICHED_SOURCE),
    # so it is counted by what it is rather than by what it is not.
    enriched = sum(1 for r in out
                   if r["efficiency_wh_per_km"] is not None
                   and r["efficiency_source"] is None)
    stats = {
        "local_rows": len(locals_by_id),
        "global_rows": len(globals_by_id),
        "local_duplicate_ids_dropped": local_dupes,
        "global_duplicate_ids_dropped": global_dupes,
        "collisions_merged": len(collisions),
        "collision_ids": collisions,
        "union_total": len(out),
        "measured_efficiency": measured,
        "enriched_efficiency": enriched,
        "derived_efficiency": sum(1 for r in out
                                  if r["efficiency_source"] == EFFICIENCY_DERIVED),
    }
    return out, stats

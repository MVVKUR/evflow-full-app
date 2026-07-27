"""Idempotent EV model importer script for EV-FLOW (Epic 2.0).

SUPERSEDED BY `python -m scripts.ingest_raw`, which is now the only step that
reads a dataset file. This script ENRICHES the 60 Indonesian models with a
lookup into the global dataset and discards the other 478; `ingest_raw` stores
both as a 535-model union. `data/processed/ev_models_enriched.json`, which this
script writes, is no longer read by anything -- `api/evmodels.py` is
database-only. Kept because its parsing helpers (`_parse_range_bounds`,
`_parse_charging_time_minutes`, `_slug`) are what `scripts/ev_union.py` reuses,
so the local dataset is still parsed by exactly the code that produced the rows
now in production.

Imports and enriches EV specifications from:
1. indonesia_ev_specs_pricing_2026.csv (canonical local dataset)
2. electric_vehicles_spec_2025.csv (global specification dataset for enrichment)

Saves to PostgreSQL database `ev_models` table if DB connection is configured,
and/or writes to `data/processed/ev_models_enriched.json` for lightweight file fallback.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = ROOT / "ev_dataset.zip"
OUTPUT_JSON_PATH = ROOT / "data" / "processed" / "ev_models_enriched.json"


def _slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def _parse_numbers(val: Any) -> List[float]:
    if val is None:
        return []
    s = str(val).strip()
    if not s:
        return []
    # Replace decimal commas with dots
    cleaned = re.sub(r"(\d+),(\d+)", r"\1.\2", s)
    matches = re.findall(r"\d+(?:\.\d+)?", cleaned)
    nums = []
    for m in matches:
        try:
            nums.append(float(m))
        except ValueError:
            pass
    return nums


def _parse_range_bounds(val: Any) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    nums = _parse_numbers(val)
    if not nums:
        return None, None, None
    val_min = min(nums)
    val_max = max(nums)
    # Default is conservative min
    return val_min, val_min, val_max


def _parse_charging_time_minutes(val: Any) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s or s == "nan":
        return None
    is_hours = "jam" in s or "hour" in s or "hr" in s
    nums = _parse_numbers(val)
    if not nums:
        return None
    val_num = sum(nums) / len(nums) if len(nums) <= 2 else nums[0]
    return round(val_num * 60.0, 1) if is_hours else round(nums[0], 1)


def _normalize_token(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\b(ev|electric|vehicle|car|long|range|standard|plus|pro|max)\b", "", t)
    return re.sub(r"[^a-z0-9]", "", t)


def read_zip_csvs() -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    rows_2026: List[Dict[str, str]] = []
    rows_2025: List[Dict[str, str]] = []

    if ZIP_PATH.exists():
        with zipfile.ZipFile(ZIP_PATH) as z:
            if "indonesia_ev_specs_pricing_2026.csv" in z.namelist():
                with z.open("indonesia_ev_specs_pricing_2026.csv") as f:
                    rows_2026 = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))

            if "electric_vehicles_spec_2025.csv" in z.namelist():
                with z.open("electric_vehicles_spec_2025.csv") as f:
                    rows_2025 = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))

    return rows_2026, rows_2025


def build_enriched_models(rows_2026: List[Dict[str, str]], rows_2025: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    # Index 2025 rows by normalized make+model tokens for matching
    spec_2025_index: Dict[str, List[Dict[str, str]]] = {}
    for r in rows_2025:
        brand = (r.get("brand") or "").strip()
        model = (r.get("model") or "").strip()
        key = _normalize_token(f"{brand} {model}")
        if key:
            spec_2025_index.setdefault(key, []).append(r)

    enriched: List[Dict[str, Any]] = []
    stats = {
        "total_local_2026": len(rows_2026),
        "exact_matched": 0,
        "fuzzy_matched": 0,
        "derived_local_specs": 0,
        "unmatched_no_efficiency": 0,
        "ambiguous_matches": 0,
    }

    seen_ids = set()

    for r2026 in rows_2026:
        name = (r2026.get("Vehicle Name") or "").strip()
        if not name:
            continue

        parts = name.split()
        brand = parts[0]
        make = brand
        model = " ".join(parts[1:]) if len(parts) > 1 else name

        model_id = _slug(name)
        if model_id in seen_ids:
            idx = 2
            while f"{model_id}-{idx}" in seen_ids:
                idx += 1
            model_id = f"{model_id}-{idx}"
        seen_ids.add(model_id)

        bat_val, bat_min, bat_max = _parse_range_bounds(r2026.get("Battery Capacity"))
        rng_val, rng_min, rng_max = _parse_range_bounds(r2026.get("Range (Jarak Tempuh)"))

        # Matching against 2025 global dataset
        token_key = _normalize_token(name)
        candidates = spec_2025_index.get(token_key, [])

        match_method = "canonical_local_only"
        match_confidence = 1.0 if not candidates else 0.9
        matched_2025: Optional[Dict[str, str]] = None

        if len(candidates) == 1:
            matched_2025 = candidates[0]
            match_method = "exact_make_model_match"
            match_confidence = 1.00
            stats["exact_matched"] += 1
        elif len(candidates) > 1:
            matched_2025 = candidates[0]
            match_method = "ambiguous_match_best_pick"
            match_confidence = 0.75
            stats["ambiguous_matches"] += 1
        else:
            # Try fuzzy token containment match
            fuzzy_found = []
            for k2025, r2025_list in spec_2025_index.items():
                if _normalize_token(make) in k2025 and _normalize_token(model) in k2025:
                    fuzzy_found.extend(r2025_list)

            if len(fuzzy_found) >= 1:
                matched_2025 = fuzzy_found[0]
                match_method = "normalized_fuzzy_match"
                match_confidence = 0.85
                stats["fuzzy_matched"] += 1

        # Extract efficiency and specs
        efficiency_wh_per_km: Optional[float] = None
        efficiency_source: str = "dataset"
        max_dc_charge_kw: Optional[float] = None
        fast_charge_port: Optional[str] = None

        if matched_2025:
            eff_nums = _parse_numbers(matched_2025.get("efficiency_wh_per_km"))
            if eff_nums:
                efficiency_wh_per_km = eff_nums[0]
                efficiency_source = "2025_spec_dataset"

            dc_nums = _parse_numbers(matched_2025.get("fast_charging_power_kw_dc"))
            if dc_nums:
                max_dc_charge_kw = dc_nums[0]

            fast_charge_port = (matched_2025.get("fast_charge_port") or "").strip() or None

        # Derive efficiency if missing from 2025 match
        if efficiency_wh_per_km is None and bat_val is not None and rng_val is not None and rng_val > 0:
            efficiency_wh_per_km = round((bat_val * 1000.0) / rng_val, 2)
            efficiency_source = "derived_local_specs"
            stats["derived_local_specs"] += 1
        elif efficiency_wh_per_km is None:
            stats["unmatched_no_efficiency"] += 1

        source_datasets = ["indonesia_ev_specs_pricing_2026.csv"]
        if matched_2025:
            source_datasets.append("electric_vehicles_spec_2025.csv")

        record = {
            "id": model_id,
            "name": name,
            "make": make,
            "model": model,
            "brand": brand,
            "battery_kwh": bat_val,
            "battery_kwh_min": bat_min,
            "battery_kwh_max": bat_max,
            "range_km": rng_val,
            "range_km_min": rng_min,
            "range_km_max": rng_max,
            "efficiency_wh_per_km": efficiency_wh_per_km,
            "efficiency_source": efficiency_source,
            "max_dc_charge_kw": max_dc_charge_kw,
            "fast_charge_port": fast_charge_port,
            "price_range": (r2026.get("Vehicle Price Range") or "").strip() or None,
            "charging_time_minutes": _parse_charging_time_minutes(r2026.get("Charging time") or r2026.get("Charging Time (0-80% / 10-80%)")),
            "source_url": (r2026.get("Source URL") or "").strip() or None,
            "source_datasets": source_datasets,
            "source_payload": {
                "raw_2026": r2026,
                "raw_2025": matched_2025
            },
            "match_method": match_method,
            "match_confidence": match_confidence,
        }
        enriched.append(record)

    return enriched, stats


def save_to_json(enriched_models: List[Dict[str, Any]]) -> None:
    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(enriched_models, f, indent=2)
    print(f"[Importer] Saved {len(enriched_models)} records to {OUTPUT_JSON_PATH}")


def save_to_db(enriched_models: List[Dict[str, Any]]) -> int:
    try:
        from sqlalchemy import create_engine, text
        database_url = os.getenv("DATABASE_URL", "postgresql+psycopg://evflow:evflow_pass@localhost:5432/evflow")
        engine = create_engine(database_url)

        upsert_stmt = text("""
            INSERT INTO ev_models (
                id, name, make, model, brand, battery_kwh, battery_kwh_min, battery_kwh_max,
                range_km, range_km_min, range_km_max, efficiency_wh_per_km, efficiency_source,
                max_dc_charge_kw, fast_charge_port, price_range, charging_time_minutes, source_url,
                source_datasets, source_payload, match_method, match_confidence, updated_at
            ) VALUES (
                :id, :name, :make, :model, :brand, :battery_kwh, :battery_kwh_min, :battery_kwh_max,
                :range_km, :range_km_min, :range_km_max, :efficiency_wh_per_km, :efficiency_source,
                :max_dc_charge_kw, :fast_charge_port, :price_range, :charging_time_minutes, :source_url,
                :source_datasets, :source_payload, :match_method, :match_confidence, NOW()
            ) ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                make = EXCLUDED.make,
                model = EXCLUDED.model,
                brand = EXCLUDED.brand,
                battery_kwh = EXCLUDED.battery_kwh,
                battery_kwh_min = EXCLUDED.battery_kwh_min,
                battery_kwh_max = EXCLUDED.battery_kwh_max,
                range_km = EXCLUDED.range_km,
                range_km_min = EXCLUDED.range_km_min,
                range_km_max = EXCLUDED.range_km_max,
                efficiency_wh_per_km = EXCLUDED.efficiency_wh_per_km,
                efficiency_source = EXCLUDED.efficiency_source,
                max_dc_charge_kw = EXCLUDED.max_dc_charge_kw,
                fast_charge_port = EXCLUDED.fast_charge_port,
                price_range = EXCLUDED.price_range,
                charging_time_minutes = EXCLUDED.charging_time_minutes,
                source_url = EXCLUDED.source_url,
                source_datasets = EXCLUDED.source_datasets,
                source_payload = EXCLUDED.source_payload,
                match_method = EXCLUDED.match_method,
                match_confidence = EXCLUDED.match_confidence,
                updated_at = NOW();
        """)

        count = 0
        with engine.begin() as conn:
            for m in enriched_models:
                payload_json = json.dumps(m["source_payload"])
                conn.execute(upsert_stmt, {
                    "id": m["id"],
                    "name": m["name"],
                    "make": m["make"],
                    "model": m["model"],
                    "brand": m["brand"],
                    "battery_kwh": m["battery_kwh"],
                    "battery_kwh_min": m["battery_kwh_min"],
                    "battery_kwh_max": m["battery_kwh_max"],
                    "range_km": m["range_km"],
                    "range_km_min": m["range_km_min"],
                    "range_km_max": m["range_km_max"],
                    "efficiency_wh_per_km": m["efficiency_wh_per_km"],
                    "efficiency_source": m["efficiency_source"],
                    "max_dc_charge_kw": m["max_dc_charge_kw"],
                    "fast_charge_port": m["fast_charge_port"],
                    "price_range": m["price_range"],
                    "charging_time_minutes": m["charging_time_minutes"],
                    "source_url": m["source_url"],
                    "source_datasets": m["source_datasets"],
                    "source_payload": payload_json,
                    "match_method": m["match_method"],
                    "match_confidence": m["match_confidence"],
                })
                count += 1
        print(f"[Importer] Successfully upserted {count} records into PostgreSQL ev_models table.")
        return count
    except Exception as e:
        print(f"[Importer] DB upsert skipped or failed: {e}")
        return 0


def main():
    rows_2026, rows_2025 = read_zip_csvs()
    print(f"[Importer] Loaded {len(rows_2026)} local 2026 records and {len(rows_2025)} global 2025 spec records.")

    enriched_models, stats = build_enriched_models(rows_2026, rows_2025)
    print(f"[Importer] Import summary stats: {stats}")

    save_to_json(enriched_models)
    save_to_db(enriched_models)


if __name__ == "__main__":
    main()

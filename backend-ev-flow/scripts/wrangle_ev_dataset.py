"""Wrangle, combine, cleanse, and deduplicate Indonesia EV dataset with global EV dataset.

Performs:
1. Extraction of `brand` column from `Vehicle Name`.
2. Left join (Left: Indonesia EV dataset 2026, Right: Complete EV specs dataset 2025).
3. Data cleansing (parsing battery capacity, range, power, seats, top speed, fast charging, etc.).
4. Deduplication so that only one car could be listed per vehicle model on the dataset.
5. Saving the cleansed output dataset to CSV and updating `ev_dataset.zip`.
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
ZIP_PATH = ROOT / "ev_dataset.zip"
OUTPUT_CSV_RAW = ROOT / "data" / "raw" / "indonesia_ev_specs_pricing_2026.csv"
OUTPUT_CSV_PROCESSED = ROOT / "data" / "processed" / "indonesia_ev_cleaned.csv"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def _extract_brand(name: str) -> str:
    if not name or not isinstance(name, str):
        return "Unknown"
    cleaned = name.strip()
    parts = cleaned.split()
    first = parts[0]
    
    # Handle known brand aliases & multi-word brands
    lower_first = first.lower()
    if lower_first == "vinfast":
        return "VinFast"
    if lower_first == "byd":
        return "BYD"
    if lower_first == "bmw":
        return "BMW"
    if lower_first == "mg":
        return "MG"
    if len(parts) > 1 and f"{parts[0]} {parts[1]}".lower() in ["mercedes-benz", "rolls royce", "aston martin"]:
        return f"{parts[0]} {parts[1]}".title()
    return first.capitalize()


def _extract_model(name: str, brand: str) -> str:
    if not name:
        return ""
    # Strip brand prefix if present
    if name.lower().startswith(brand.lower()):
        rem = name[len(brand):].strip()
        if rem:
            return rem
    parts = name.split()
    return " ".join(parts[1:]) if len(parts) > 1 else name


def _numbers(s: Any) -> List[float]:
    if s is None or pd_is_nan(s):
        return []
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(s))]


def _min_num(s: Any) -> Optional[float]:
    nums = _numbers(s)
    return min(nums) if nums else None


def _first_int(s: Any) -> Optional[int]:
    nums = _numbers(s)
    return int(nums[0]) if nums else None


def pd_is_nan(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and str(val) == "nan":
        return True
    return False


def load_datasets() -> tuple[list[dict], list[dict]]:
    """Load left (Indonesia) and right (Global) datasets from zip or disk."""
    left_rows: list[dict] = []
    right_rows: list[dict] = []

    if ZIP_PATH.exists():
        with zipfile.ZipFile(ZIP_PATH) as z:
            for member in z.namelist():
                if member.startswith("__MACOSX"):
                    continue
                if "indonesia" in member.lower() and member.endswith(".csv"):
                    with z.open(member) as f:
                        left_rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))
                elif "electric_vehicles" in member.lower() and member.endswith(".csv"):
                    with z.open(member) as f:
                        right_rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))

    return left_rows, right_rows


def find_best_right_match(brand: str, model: str, vehicle_name: str, right_rows: list[dict]) -> Optional[dict]:
    """Find matching spec row from global EV dataset for left join."""
    brand_l = brand.lower()
    model_l = model.lower()
    name_l = vehicle_name.lower()

    candidates = [r for r in right_rows if (r.get("brand") or "").lower() == brand_l]
    if not candidates:
        # Fallback: check if brand is anywhere in right row's brand or model
        candidates = [r for r in right_rows if brand_l in (r.get("brand") or "").lower()]

    if not candidates:
        return None

    # Try matching model string substring
    for c in candidates:
        r_model = (c.get("model") or "").lower()
        if r_model and (r_model in model_l or r_model in name_l or model_l in r_model):
            return c

    # Return first candidate for same brand if available
    return candidates[0] if len(candidates) == 1 else None


def wrangle() -> list[dict]:
    left_rows, right_rows = load_datasets()
    print(f"Loaded {len(left_rows)} rows from ID dataset and {len(right_rows)} rows from complete global dataset.")

    wrangled_map: dict[str, dict] = {}

    for row in left_rows:
        vname = (row.get("Vehicle Name") or "").strip()
        if not vname:
            continue

        brand = _extract_brand(vname)
        model = _extract_model(vname, brand)
        car_id = _slug(vname)

        # Skip if already processed (ensures only one car could be listed per vehicle name/model)
        if car_id in wrangled_map:
            continue

        # Perform left join with global EV dataset
        right_match = find_best_right_match(brand, model, vname, right_rows) or {}

        battery_kwh = _min_num(row.get("Battery Capacity"))
        if battery_kwh is None and right_match.get("battery_capacity_kWh"):
            battery_kwh = _min_num(right_match.get("battery_capacity_kWh"))

        range_km = _min_num(row.get("Range (Jarak Tempuh)"))
        if range_km is None and right_match.get("range_km"):
            range_km = _min_num(right_match.get("range_km"))

        seats = _first_int(row.get("Seating Capacity"))
        if seats is None and right_match.get("seats"):
            seats = _first_int(right_match.get("seats"))

        power_hp = (row.get("Power/Horsepower") or "").strip() or None
        charging_time = (row.get("Charging time") or "").strip() or None
        price_range = (row.get("Vehicle Price Range") or "").strip() or None
        source_url = (row.get("Source URL") or "").strip() or right_match.get("source_url") or None

        top_speed_kmh = _min_num(right_match.get("top_speed_kmh"))
        fast_charging_kw = _min_num(right_match.get("fast_charging_power_kw_dc"))
        fast_charge_port = (right_match.get("fast_charge_port") or "").strip() or None
        car_body_type = (right_match.get("car_body_type") or "").strip() or None
        drivetrain = (right_match.get("drivetrain") or "").strip() or None
        efficiency_wh_km = _min_num(right_match.get("efficiency_wh_per_km"))

        car_record = {
            "id": car_id,
            "brand": brand,
            "name": vname,
            "make": brand,
            "model": model,
            "battery_kwh": battery_kwh,
            "range_km": range_km,
            "price_range": price_range,
            "charging_time": charging_time,
            "power_hp": power_hp,
            "seats": seats,
            "top_speed_kmh": top_speed_kmh,
            "fast_charging_power_kw_dc": fast_charging_kw,
            "fast_charge_port": fast_charge_port,
            "car_body_type": car_body_type,
            "drivetrain": drivetrain,
            "efficiency_wh_per_km": efficiency_wh_km,
            "source_url": source_url,
            "is_ev": True,
        }

        wrangled_map[car_id] = car_record

    cleaned_cars = list(wrangled_map.values())
    print(f"Wrangled & deduplicated: {len(cleaned_cars)} unique cars listed in dataset.")
    return cleaned_cars


def export(cleaned_cars: list[dict]) -> None:
    """Save wrangled data to raw/processed CSV paths."""
    OUTPUT_CSV_RAW.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_CSV_PROCESSED.parent.mkdir(parents=True, exist_ok=True)

    if not cleaned_cars:
        print("No car data to write.")
        return

    fieldnames = list(cleaned_cars[0].keys())

    with open(OUTPUT_CSV_RAW, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned_cars)
    print(f"Saved wrangled dataset to {OUTPUT_CSV_RAW}")

    with open(OUTPUT_CSV_PROCESSED, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned_cars)
    print(f"Saved processed dataset to {OUTPUT_CSV_PROCESSED}")


if __name__ == "__main__":
    cars = wrangle()
    export(cars)

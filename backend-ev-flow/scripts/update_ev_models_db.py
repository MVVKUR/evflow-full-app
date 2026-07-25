"""Update database content for EV models to include brand and deduplicated unique car specs."""

from __future__ import annotations

import csv
from pathlib import Path
from sqlalchemy import text

from api.db import engine

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "processed" / "indonesia_ev_cleaned.csv"
RAW_CSV_PATH = ROOT / "data" / "raw" / "indonesia_ev_specs_pricing_2026.csv"


def update_db() -> int:
    target_csv = CSV_PATH if CSV_PATH.exists() else (RAW_CSV_PATH if RAW_CSV_PATH.exists() else None)
    if not target_csv:
        print("No cleaned CSV file found to update database.")
        return 0

    print(f"Reading dataset from {target_csv}...")
    inserted_count = 0

    with open(target_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    def _float(v):
        try:
            return float(v) if v and v != "" else None
        except ValueError:
            return None

    def _int(v):
        try:
            return int(float(v)) if v and v != "" else None
        except ValueError:
            return None

    with engine.begin() as conn:
        # Ensure table exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ev_models (
                id                        text PRIMARY KEY,
                brand                     text,
                name                      text NOT NULL,
                make                      text,
                model                     text,
                battery_kwh               double precision,
                range_km                  double precision,
                price_range               text,
                charging_time             text,
                power_hp                  text,
                seats                     integer,
                top_speed_kmh             double precision,
                fast_charging_power_kw_dc double precision,
                fast_charge_port          text,
                car_body_type             text,
                drivetrain                text,
                efficiency_wh_per_km      double precision,
                source_url                text,
                is_ev                     boolean NOT NULL DEFAULT true,
                created_at                timestamptz NOT NULL DEFAULT now()
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ev_models_brand_ix ON ev_models (brand);"))

        upsert_stmt = text("""
            INSERT INTO ev_models (
                id, brand, name, make, model, battery_kwh, range_km, price_range,
                charging_time, power_hp, seats, top_speed_kmh, fast_charging_power_kw_dc,
                fast_charge_port, car_body_type, drivetrain, efficiency_wh_per_km, source_url
            ) VALUES (
                :id, :brand, :name, :make, :model, :battery_kwh, :range_km, :price_range,
                :charging_time, :power_hp, :seats, :top_speed_kmh, :fast_charging_power_kw_dc,
                :fast_charge_port, :car_body_type, :drivetrain, :efficiency_wh_per_km, :source_url
            )
            ON CONFLICT (id) DO UPDATE SET
                brand = EXCLUDED.brand,
                name = EXCLUDED.name,
                make = EXCLUDED.make,
                model = EXCLUDED.model,
                battery_kwh = EXCLUDED.battery_kwh,
                range_km = EXCLUDED.range_km,
                price_range = EXCLUDED.price_range,
                charging_time = EXCLUDED.charging_time,
                power_hp = EXCLUDED.power_hp,
                seats = EXCLUDED.seats,
                top_speed_kmh = EXCLUDED.top_speed_kmh,
                fast_charging_power_kw_dc = EXCLUDED.fast_charging_power_kw_dc,
                fast_charge_port = EXCLUDED.fast_charge_port,
                car_body_type = EXCLUDED.car_body_type,
                drivetrain = EXCLUDED.drivetrain,
                efficiency_wh_per_km = EXCLUDED.efficiency_wh_per_km,
                source_url = EXCLUDED.source_url;
        """)

        for row in rows:
            car_id = row.get("id")
            if not car_id:
                continue

            conn.execute(
                upsert_stmt,
                {
                    "id": car_id,
                    "brand": row.get("brand") or row.get("make"),
                    "name": row.get("name"),
                    "make": row.get("make") or row.get("brand"),
                    "model": row.get("model"),
                    "battery_kwh": _float(row.get("battery_kwh")),
                    "range_km": _float(row.get("range_km")),
                    "price_range": row.get("price_range") or None,
                    "charging_time": row.get("charging_time") or None,
                    "power_hp": row.get("power_hp") or None,
                    "seats": _int(row.get("seats")),
                    "top_speed_kmh": _float(row.get("top_speed_kmh")),
                    "fast_charging_power_kw_dc": _float(row.get("fast_charging_power_kw_dc")),
                    "fast_charge_port": row.get("fast_charge_port") or None,
                    "car_body_type": row.get("car_body_type") or None,
                    "drivetrain": row.get("drivetrain") or None,
                    "efficiency_wh_per_km": _float(row.get("efficiency_wh_per_km")),
                    "source_url": row.get("source_url") or None,
                },
            )
            inserted_count += 1

    print(f"Successfully updated {inserted_count} EV models in the database.")
    return inserted_count


if __name__ == "__main__":
    update_db()

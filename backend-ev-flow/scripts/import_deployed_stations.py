"""Import station records from a deployed EV-FLOW API into the local database.

Usage:
    python -m scripts.import_deployed_stations

The deployed API exposes the normalized Station shape. This script maps that
shape back into the local PostGIS-backed stations table used by api/stations_repo.py.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db import engine  # noqa: E402


API_BASE_URL = os.getenv("EVFLOW_DEPLOYED_API_BASE_URL", "https://ev-flow-api.opensoft.id")
PAGE_SIZE = int(os.getenv("EVFLOW_IMPORT_PAGE_SIZE", "1000"))

_INSERT = text("""
    INSERT INTO stations
      (id, geom, name, address, province, city, operator, power_kw, speed_tier,
       connector_types, connector_inferred, connectors, sources, status, date_verified)
    VALUES
      (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, :address, :province,
       :city, :operator, :power_kw, :speed_tier, :connector_types, :connector_inferred,
       CAST(:connectors AS jsonb), :sources, :status, :date_verified)
    ON CONFLICT (id) DO UPDATE SET
       geom = EXCLUDED.geom,
       name = EXCLUDED.name,
       address = EXCLUDED.address,
       province = EXCLUDED.province,
       city = EXCLUDED.city,
       operator = EXCLUDED.operator,
       power_kw = EXCLUDED.power_kw,
       speed_tier = EXCLUDED.speed_tier,
       connector_types = EXCLUDED.connector_types,
       connector_inferred = EXCLUDED.connector_inferred,
       connectors = EXCLUDED.connectors,
       sources = EXCLUDED.sources,
       status = EXCLUDED.status,
       date_verified = EXCLUDED.date_verified
""")


def fetch_page(offset: int) -> dict:
    query = urlencode({"limit": PAGE_SIZE, "offset": offset})
    url = f"{API_BASE_URL.rstrip('/')}/api/v1/stations?{query}"
    request = Request(url, headers={"User-Agent": "EV-FLOW local station importer"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def station_params(station: dict) -> dict:
    return {
        "id": station["id"],
        "lat": station["latitude"],
        "lon": station["longitude"],
        "name": station.get("name"),
        "address": station.get("address"),
        "province": station.get("province"),
        "city": station.get("city"),
        "operator": station.get("operator"),
        "power_kw": station.get("power_kw"),
        "speed_tier": station.get("speed_tier"),
        "connector_types": list(station.get("connector_types") or []),
        "connector_inferred": bool(station.get("connector_inferred", True)),
        "connectors": json.dumps(station.get("connectors") or []),
        "sources": list(station.get("sources") or []),
        "status": station.get("status"),
        "date_verified": station.get("date_verified"),
    }


def main() -> None:
    first = fetch_page(0)
    total = int(first["total"])
    stations = list(first["items"])

    for offset in range(PAGE_SIZE, total, PAGE_SIZE):
        page = fetch_page(offset)
        stations.extend(page["items"])
        print(f"fetched {len(stations)}/{total}")

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE stations;"))
        conn.execute(_INSERT, [station_params(station) for station in stations])

    print(f"imported {len(stations)} stations from {API_BASE_URL}")


if __name__ == "__main__":
    main()

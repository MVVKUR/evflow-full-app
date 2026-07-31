import sys
import json
import urllib.request
from pathlib import Path

# Add the parent directory to sys.path so we can import `api`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from api.db import engine

_INSERT = text("""
    INSERT INTO stations
      (id, geom, name, address, province, city, operator, power_kw, speed_tier,
       connector_types, connector_inferred, connectors, sources, status, date_verified)
    VALUES
      (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, :address, :province,
       :city, :operator, :power_kw, :speed_tier, :connector_types, :connector_inferred,
       CAST(:connectors AS jsonb), :sources, :status, :date_verified)
""")

_EXPLODE_CONNECTORS = text("""
    INSERT INTO connectors (id, station_id, type, power_kw, speed_tier, type_inferred)
    SELECT gen_random_uuid(), s.id, c->>'type', (c->>'power_kw')::double precision,
           c->>'speed_tier', COALESCE((c->>'type_inferred')::boolean, false)
    FROM stations s,
         LATERAL jsonb_array_elements(s.connectors) AS c,
         LATERAL generate_series(1, GREATEST(COALESCE((c->>'count')::int, 1), 1)) AS n
    WHERE jsonb_typeof(s.connectors) = 'array'
""")

def main():
    url = "https://ev-flow.opensoft.id/api/v1/stations?limit=1000"
    print(f"Fetching data from {url}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())

    items = data.get("items", [])
    print(f"Fetched {len(items)} stations from API.")

    with engine.begin() as conn:
        print("Clearing existing stations and connectors...")
        # DELETE on stations will cascade to connectors because of FK constraints
        conn.execute(text("DELETE FROM stations;"))

        print("Inserting stations into the database...")
        for s in items:
            conn.execute(_INSERT, {
                "id": s["id"],
                "lat": s["latitude"],
                "lon": s["longitude"],
                "name": s.get("name"),
                "address": s.get("address"),
                "province": s.get("province"),
                "city": s.get("city"),
                "operator": s.get("operator"),
                "power_kw": s.get("power_kw"),
                "speed_tier": s.get("speed_tier"),
                "connector_types": list(s.get("connector_types") or []),
                "connector_inferred": bool(s.get("connector_inferred", True)),
                "connectors": json.dumps(s.get("connectors") or []),
                "sources": list(s.get("sources") or []),
                "status": s.get("status"),
                "date_verified": s.get("date_verified"),
            })

        print("Exploding connectors mapping...")
        n_connectors = conn.execute(_EXPLODE_CONNECTORS).rowcount

    print(f"Successfully imported {len(items)} stations and {n_connectors} connectors to PostGIS.")

if __name__ == "__main__":
    main()

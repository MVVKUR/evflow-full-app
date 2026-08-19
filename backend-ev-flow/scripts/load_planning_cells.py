"""Load the offline 500 m siting grid into planning_cells, then derive supply.

    python -m scripts.load_planning_cells --grid ../ev-planner-study/grid_jabodetabek_500m.gpkg
    python -m scripts.load_planning_cells --refresh-supply-only

Two halves, deliberately separable.

The FEATURE half comes from the GeoPackage the offline pipeline produced: land
use, points of interest, roads and population. Those change only when the OSM
extract or the population raster is refreshed, which is rare and slow.

The SUPPLY half (station_count, connector_count, nearest_station_m, stations_2km)
is computed in SQL from the live stations and connectors tables, never carried in
the file. Stations are re-seeded far more often than the grid is rebuilt, and a
figure copied from a months-old file would quietly contradict the map the same
API serves. `--refresh-supply-only` exists for exactly that case.

No geopandas, fiona or pyproj. A GeoPackage is SQLite, and its geometry column is
a small header followed by ordinary WKB, so the blob is handed straight to
PostGIS, which also does the projection. The heavy geospatial stack stays out of
the API image (requirements-api.txt) as designed.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import text

from api.db import engine

# Grid column -> planning_cells column. The grid names POI categories bare
# (`restaurant`); the table prefixes them (`poi_restaurant`) so a category can
# never collide with a structural column.
POI = ["parking", "parking_space", "restaurant", "park", "school", "university",
       "cinema", "library", "community_centre", "place_of_worship", "townhall",
       "government", "civic", "fuel", "mall", "hospital", "rest_area"]
LANDUSE = ["lu_commercial_share", "lu_retail_share", "lu_residential_share",
           "lu_industrial_share"]

GRID_SRID = 32748          # UTM 48S, the CRS the offline pipeline measures in
DB_SRID = 4326             # what stations.geom uses, so joins need no transform


def _gpkg_wkb(blob: bytes) -> bytes:
    """Strip the GeoPackage envelope header, leaving plain WKB.

    Layout is 'GP', version, flags, srs_id, an optional envelope whose size is
    encoded in bits 1-3 of the flags, then the WKB.
    """
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry blob")
    envelope_bytes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 0b111]
    return bytes(blob[8 + envelope_bytes:])


def load_features(grid_path: Path, batch: int = 500) -> int:
    cols = ["cell_id", "kota", "overlap_frac", "lon", "lat",
            *POI, *LANDUSE, "node", "edge_len_m", "population", "geom"]
    con = sqlite3.connect(grid_path)
    rows = con.execute(f"SELECT {','.join(cols)} FROM grid").fetchall()
    con.close()

    insert = text(f"""
        INSERT INTO planning_cells (
            cell_id, kota, overlap_frac,
            geom, centroid,
            {', '.join('poi_' + p for p in POI)}, poi_total,
            {', '.join(LANDUSE)},
            road_nodes, road_length_m, population
        ) VALUES (
            :cell_id, :kota, :overlap_frac,
            ST_Transform(ST_GeomFromWKB(:wkb, {GRID_SRID}), {DB_SRID}),
            ST_SetSRID(ST_MakePoint(:lon, :lat), {DB_SRID}),
            {', '.join(':' + p for p in POI)}, :poi_total,
            {', '.join(':' + c for c in LANDUSE)},
            :node, :edge_len_m, :population
        )
        ON CONFLICT (cell_id) DO UPDATE SET
            kota = EXCLUDED.kota, overlap_frac = EXCLUDED.overlap_frac,
            geom = EXCLUDED.geom, centroid = EXCLUDED.centroid,
            {', '.join(f'poi_{p} = EXCLUDED.poi_{p}' for p in POI)},
            poi_total = EXCLUDED.poi_total,
            {', '.join(f'{c} = EXCLUDED.{c}' for c in LANDUSE)},
            road_nodes = EXCLUDED.road_nodes, road_length_m = EXCLUDED.road_length_m,
            population = EXCLUDED.population, built_at = now()
    """)

    payload = []
    for r in rows:
        d = dict(zip(cols, r))
        d["wkb"] = _gpkg_wkb(d.pop("geom"))
        d["poi_total"] = sum(int(d[p] or 0) for p in POI)
        # A share above 1 means overlapping polygons were double counted upstream.
        # The table CHECKs this, so fail here with a readable message rather than
        # letting Postgres reject the batch with a constraint name.
        for c in LANDUSE:
            if (d[c] or 0) > 1.0:
                raise SystemExit(
                    f"{d['cell_id']}: {c} = {d[c]:.4f}, above 1.0. The land-use "
                    f"polygons were not dissolved before intersection; re-run the "
                    f"offline landuse step before loading."
                )
        payload.append(d)

    with engine.begin() as c:
        for i in range(0, len(payload), batch):
            c.execute(insert, payload[i:i + batch])
    return len(payload)


def refresh_supply() -> dict:
    """Derive the supply columns from the live stations and connectors tables."""
    with engine.begin() as c:
        c.execute(text("""
            UPDATE planning_cells p
               SET station_count = 0, connector_count = 0, stations_2km = 0,
                   nearest_station_m = NULL
        """))
        c.execute(text("""
            UPDATE planning_cells p
               SET station_count   = s.n_stations,
                   connector_count = s.n_connectors
              FROM (
                    SELECT p2.cell_id,
                           count(DISTINCT st.id)  AS n_stations,
                           count(cn.id)           AS n_connectors
                      FROM planning_cells p2
                      JOIN stations   st ON ST_Within(st.geom, p2.geom)
                 LEFT JOIN connectors cn ON cn.station_id = st.id
                  GROUP BY p2.cell_id
                   ) s
             WHERE s.cell_id = p.cell_id
        """))
        # Distance and neighbour count are measured from the CENTROID in metres,
        # which is why both cast to geography rather than trusting degrees.
        c.execute(text("""
            UPDATE planning_cells p
               SET nearest_station_m = (
                       SELECT ST_Distance(p.centroid::geography, st.geom::geography)
                         FROM stations st
                     ORDER BY p.centroid <-> st.geom
                        LIMIT 1),
                   stations_2km = (
                       SELECT count(*)
                         FROM stations st
                        WHERE ST_DWithin(p.centroid::geography, st.geom::geography, 2000))
        """))
        row = c.execute(text("""
            SELECT count(*)                                    AS cells,
                   count(*) FILTER (WHERE station_count > 0)    AS cells_with_station,
                   COALESCE(sum(station_count), 0)              AS stations_binned,
                   COALESCE(sum(connector_count), 0)            AS connectors_binned
              FROM planning_cells
        """)).mappings().one()
    return dict(row)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", type=Path, help="path to grid_jabodetabek_500m.gpkg")
    ap.add_argument("--refresh-supply-only", action="store_true",
                    help="recompute supply columns from the live stations table")
    a = ap.parse_args()

    if not a.refresh_supply_only:
        if not a.grid or not a.grid.exists():
            sys.exit("--grid is required unless --refresh-supply-only is given")
        print(f"loaded {load_features(a.grid):,} cells from {a.grid.name}")

    stats = refresh_supply()
    print(f"supply refreshed: {stats['cells']:,} cells, "
          f"{stats['cells_with_station']:,} with a station, "
          f"{stats['stations_binned']:,} stations and "
          f"{stats['connectors_binned']:,} connectors binned")


if __name__ == "__main__":
    main()

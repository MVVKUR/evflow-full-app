"""The route-planning prefilter must be spatial, never lexicographic (AC 2.2.9).

`list_stations({'bbox': ...}, limit=150)` is `ORDER BY id LIMIT 150`. Station ids
sort lexicographically, so that slice returned `open_charge_map-*` rows only and
hid the entire `pln_spklu-*` network -- the product's primary dataset -- from
every route plan. These tests pin the replacement.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from api.db import engine
from api.stations_repo import along_corridor, list_stations
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

# A synthetic corridor well away from the seeded Indonesian data.
ORIGIN = (-2.0000, 120.0000)
DESTINATION = (-2.0000, 121.0000)   # ~111 km due east
_PREFIX_NEAR = "aaa-corridor"       # sorts FIRST  -> what ORDER BY id returns
_PREFIX_FAR = "zzz-corridor"        # sorts LAST   -> what ORDER BY id drops
_OFF_CORRIDOR_ID = "zzz-corridor-off"
_N = 20


def _cleanup(c) -> None:
    c.execute(text("DELETE FROM stations WHERE id LIKE 'aaa-corridor%' OR id LIKE 'zzz-corridor%'"))


@pytest.fixture
def seeded_corridor():
    with engine.begin() as c:
        _cleanup(c)
        for i in range(_N):
            frac = i / float(_N - 1)
            lon = 120.0 + frac
            # First half of the corridor gets the lexicographically-first ids.
            prefix = _PREFIX_NEAR if frac < 0.5 else _PREFIX_FAR
            c.execute(text("""
                INSERT INTO stations (id, geom, name, power_kw, connector_types, sources, status)
                VALUES (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, 50.0,
                        ARRAY['CCS2'], ARRAY['pln_spklu'], 'operational')
            """), {"id": f"{prefix}-{i:03d}", "lon": lon, "lat": -2.0,
                   "name": f"Corridor {i}"})

        # 60 km off the line: inside any bbox, outside the corridor.
        c.execute(text("""
            INSERT INTO stations (id, geom, name, power_kw, connector_types, sources, status)
            VALUES (:id, ST_SetSRID(ST_MakePoint(120.5, -2.55), 4326), 'Off corridor', 50.0,
                    ARRAY['CCS2'], ARRAY['pln_spklu'], 'operational')
        """), {"id": _OFF_CORRIDOR_ID})

    yield

    with engine.begin() as c:
        _cleanup(c)


def test_corridor_query_covers_the_whole_route_not_a_lexicographic_slice(seeded_corridor):
    rows = along_corridor(ORIGIN, DESTINATION, corridor_km=10.0, limit=10, buckets=10)
    ids = [r["id"] for r in rows]

    assert len(ids) == 10
    assert any(i.startswith(_PREFIX_FAR) for i in ids), ids   # the far end survives
    assert any(i.startswith(_PREFIX_NEAR) for i in ids), ids

    # The old prefilter, same limit, over the same corridor: id order only.
    bbox = (119.9, -2.6, 121.1, -1.9)
    _, legacy = list_stations({"bbox": bbox}, limit=10, offset=0)
    legacy_ids = [r["id"] for r in legacy if r["id"].endswith(tuple("0123456789"))]
    assert all(not i.startswith(_PREFIX_FAR) for i in legacy_ids), legacy_ids


def test_corridor_query_excludes_stations_off_the_route(seeded_corridor):
    ids = [r["id"] for r in along_corridor(ORIGIN, DESTINATION, corridor_km=10.0, limit=50)]
    assert _OFF_CORRIDOR_ID not in ids

    # Widen the corridor and it comes back: it was distance, not id, that decided.
    wide = [r["id"] for r in along_corridor(ORIGIN, DESTINATION, corridor_km=80.0, limit=50)]
    assert _OFF_CORRIDOR_ID in wide


def test_corridor_rows_carry_their_distance_to_the_route(seeded_corridor):
    rows = along_corridor(ORIGIN, DESTINATION, corridor_km=80.0, limit=50)
    by_id = {r["id"]: r for r in rows}

    on_line = by_id[f"{_PREFIX_NEAR}-000"]["corridor_distance_km"]
    off_line = by_id[_OFF_CORRIDOR_ID]["corridor_distance_km"]
    assert on_line < 1.0
    assert off_line > 50.0

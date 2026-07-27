"""Live connector availability: ONE set-based query over many stations (AC 2.2.9)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.db import engine
from api.services.station_availability import availability_or_empty, fetch_availability
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

_STATIONS = ("avail-test-a", "avail-test-b", "avail-test-c")


@pytest.fixture
def seeded_stations():
    with engine.begin() as c:
        c.execute(text("DELETE FROM stations WHERE id = ANY(:ids)"), {"ids": list(_STATIONS)})
        for i, sid in enumerate(_STATIONS):
            c.execute(text("""
                INSERT INTO stations (id, geom, name, power_kw, connector_types, sources, status)
                VALUES (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, 50.0,
                        ARRAY['CCS2'], ARRAY['pln_spklu'], 'operational')
            """), {"id": sid, "lon": 106.8 + i * 0.01, "lat": -6.2, "name": f"Avail {sid}"})

        rows = [
            ("avail-test-a", "CCS2", 150.0, "available"),
            ("avail-test-a", "CCS2", 50.0, "available"),
            ("avail-test-a", "AC Type 2", 22.0, "in_use"),
            ("avail-test-b", "CCS2", 150.0, "in_use"),
            ("avail-test-b", "CCS2", 150.0, "out_of_service"),
            # avail-test-c intentionally has NO connector rows.
        ]
        for sid, ctype, power, status in rows:
            c.execute(text("""
                INSERT INTO connectors (id, station_id, type, power_kw, speed_tier, type_inferred, status)
                VALUES (:id, :sid, :t, :p, 'fast', false, :st)
            """), {"id": str(uuid.uuid4()), "sid": sid, "t": ctype, "p": power, "st": status})

    yield

    with engine.begin() as c:
        c.execute(text("DELETE FROM stations WHERE id = ANY(:ids)"), {"ids": list(_STATIONS)})


def test_fetch_availability_batches_every_station(seeded_stations):
    result = fetch_availability(_STATIONS)

    a = result["avail-test-a"]
    assert a.available == 2
    assert a.total == 3
    assert a.in_use == 1
    assert a.available_by_type == {"CCS2": 2, "AC Type 2": 0}
    assert a.available_types == ["CCS2"]
    assert a.best_available_power_kw == 150.0

    b = result["avail-test-b"]
    assert b.available == 0
    assert b.total == 2
    assert b.best_available_power_kw is None

    # No connector rows at all => absent from the map, never "unknown, allow it".
    assert "avail-test-c" not in result
    assert availability_or_empty(result, "avail-test-c").available == 0


def test_best_power_for_only_considers_usable_types(seeded_stations):
    a = fetch_availability(_STATIONS)["avail-test-a"]

    assert a.available_count_for(["CCS2"]) == 2
    assert a.available_count_for(["AC Type 2"]) == 0
    assert a.available_count_for(["CHAdeMO"]) == 0
    assert a.best_power_for(["CCS2"]) == 150.0


def test_fetch_availability_with_no_ids_is_a_no_op():
    assert fetch_availability([]) == {}

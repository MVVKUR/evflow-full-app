"""The product serves Jabodetabek (AC 2.2.6 scopes the corridor there), so
stations outside the visible service area must disappear from EVERY read path
-- list, nearby, single get, aggregates, and the routing nearest-station scan
-- without deleting the rows. Hiding is a WHERE clause, not a data migration:
widening the area later is an env change, not a re-import.

The enforcement flag is ON by default in production code and switched OFF for
this test suite by an autouse fixture in conftest.py, because the legacy DB
fixtures seed synthetic stations across the whole archipelago. Tests here opt
back in explicitly.
"""
import pytest
from sqlalchemy import text

from api.services import service_area
from tests.conftest import requires_db

IN_ID = "zzz-visarea-in"      # Monas: the heart of the served area
OUT_ID = "zzz-visarea-out"    # Bandung: real city, definitely outside


@pytest.fixture
def enforced():
    prev = service_area.STATION_AREA_ENFORCED
    service_area.STATION_AREA_ENFORCED = True
    yield
    service_area.STATION_AREA_ENFORCED = prev


def test_default_bounds_describe_jabodetabek():
    # The five metro anchors are inside...
    assert service_area.station_visible(-6.2088, 106.8456)   # Jakarta (Monas)
    assert service_area.station_visible(-6.5950, 106.8166)   # Bogor
    assert service_area.station_visible(-6.4025, 106.7942)   # Depok
    assert service_area.station_visible(-6.1783, 106.6319)   # Tangerang
    assert service_area.station_visible(-6.2383, 107.0011)   # Bekasi
    # ...and the nearest big non-member cities are not.
    assert not service_area.station_visible(-6.9147, 107.6098)  # Bandung
    assert not service_area.station_visible(-6.1200, 106.1503)  # Serang
    assert not service_area.station_visible(-6.9932, 110.4203)  # Semarang


def test_visibility_clause_is_empty_when_not_enforced():
    from api import stations_repo
    assert service_area.STATION_AREA_ENFORCED is False  # conftest default for tests
    clauses, params = stations_repo._visibility_clauses()
    assert clauses == []
    assert params == {}


def test_visibility_clause_binds_the_configured_bounds(enforced):
    from api import stations_repo
    clauses, params = stations_repo._visibility_clauses()
    assert len(clauses) == 1
    assert "geom" in clauses[0]
    west, south, east, north = service_area.station_area_bounds()
    assert params == {"vis_w": west, "vis_s": south, "vis_e": east, "vis_n": north}
    assert params["vis_w"] < params["vis_e"]
    assert params["vis_s"] < params["vis_n"]


@pytest.fixture
def seeded_visibility():
    from api.db import engine
    with engine.begin() as c:
        c.execute(text("DELETE FROM stations WHERE id LIKE 'zzz-visarea%'"))
        for sid, lat, lon, prov, city in (
            (IN_ID, -6.2088, 106.8456, "DKI Jakarta", "Jakarta Pusat"),
            (OUT_ID, -6.9147, 107.6098, "Jawa Barat", "Bandung"),
        ):
            c.execute(text("""
                INSERT INTO stations (id, geom, name, power_kw, connector_types,
                                      sources, status, province, city)
                VALUES (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :id, 50.0,
                        ARRAY['CCS2'], ARRAY['pln_spklu'], 'operational', :prov, :city)
            """), {"id": sid, "lat": lat, "lon": lon, "prov": prov, "city": city})
    yield
    with engine.begin() as c:
        c.execute(text("DELETE FROM stations WHERE id LIKE 'zzz-visarea%'"))


@requires_db
def test_every_read_path_hides_the_out_of_area_station(seeded_visibility, enforced):
    from api import stations_repo as repo

    # list: the q filter isolates this test's rows from the real dataset.
    total, rows = repo.list_stations({"q": "zzz-visarea"}, limit=10, offset=0)
    ids = {r["id"] for r in rows}
    assert IN_ID in ids
    assert OUT_ID not in ids
    assert total == 1

    # nearby: a 300 km radius from Monas covers Bandung, so only the area
    # filter can be what excludes it.
    near_ids = {r["id"] for r in repo.nearby(-6.2088, 106.8456, 300.0, 50, {"q": "zzz-visarea"})}
    assert IN_ID in near_ids
    assert OUT_ID not in near_ids

    # single get: a hidden station has no detail page either.
    assert repo.get_station(IN_ID) is not None
    assert repo.get_station(OUT_ID) is None

    # the routing nearest-station scan must not offer what the map hides.
    routing_ids = {r["id"] for r in repo.routing_coords()}
    assert IN_ID in routing_ids
    assert OUT_ID not in routing_ids

    # aggregates shrink consistently.
    assert repo.stats()["total"] == repo.count()


@requires_db
def test_aggregates_and_toggle(seeded_visibility, enforced):
    from api import stations_repo as repo

    on_count = repo.count()
    on_cities = [city for city, _ in repo.cities("Jawa Barat")]
    assert "Bandung" not in on_cities

    service_area.STATION_AREA_ENFORCED = False
    off_count = repo.count()
    off_cities = [city for city, _ in repo.cities("Jawa Barat")]
    service_area.STATION_AREA_ENFORCED = True

    # Turning enforcement off reveals strictly more of the same data --
    # nothing was deleted, only hidden.
    assert off_count > on_count
    assert "Bandung" in off_cities
    assert repo.get_station(OUT_ID) is None
    service_area.STATION_AREA_ENFORCED = False
    assert repo.get_station(OUT_ID) is not None
    service_area.STATION_AREA_ENFORCED = True

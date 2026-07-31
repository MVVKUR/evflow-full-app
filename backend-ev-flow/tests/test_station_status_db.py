"""DB-backed tests for get_station_realtime_status: the SQL, not the Python.

Every case here is one the previous query could not express or got wrong:
per-status counts collapsed into total, an unknown wait silently rendered as 0
by GREATEST(0, NULL), two connector groups made indistinguishable by grouping on
power_kw without selecting it, and counts inflated by joining charging_sessions
directly.

Each test seeds its own station with a unique id and drops it afterwards, so
nothing depends on the dataset seed or on another test.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from api.connectors_repo import get_station_realtime_status
from api.db import engine
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]

# 20 kWh at 50 kW is 0.4 h. A session started now frees its connector in 24 min.
_ENERGY_KWH = 20.0
_POWER_KW = 50.0
_MINUTES = 24.0


@pytest.fixture
def seed():
    """Build a throwaway station from (type, power_kw, speed_tier, status) tuples.

    Returns (station_id, connector_ids) so a test can hang charging sessions off a
    specific connector. Sessions are removed by hand on teardown: dropping the
    station cascades to connectors, but charging_sessions.connector_id is
    ON DELETE SET NULL, so the session rows would survive as orphans.
    """
    stations: list[str] = []
    sessions: list[str] = []

    def make(connectors: list[tuple], with_sessions: list[dict] | None = None) -> tuple[str, list[str]]:
        sid = "status-test-" + uuid.uuid4().hex[:10]
        stations.append(sid)
        connector_ids = [str(uuid.uuid4()) for _ in connectors]
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO stations (id, geom, name, connector_types, sources, status)
                VALUES (:id, ST_SetSRID(ST_MakePoint(106.8, -6.2), 4326), :name,
                        ARRAY['CCS2'], ARRAY['pln_spklu'], 'operational')
            """), {"id": sid, "name": f"Status {sid}"})
            for cid, (ctype, power, tier, status) in zip(connector_ids, connectors):
                c.execute(text("""
                    INSERT INTO connectors (id, station_id, type, power_kw, speed_tier,
                                            type_inferred, status)
                    VALUES (:id, :sid, :t, :p, :tier, false, :st)
                """), {"id": cid, "sid": sid, "t": ctype, "p": power, "tier": tier, "st": status})
            for spec in with_sessions or []:
                session_id = str(uuid.uuid4())
                sessions.append(session_id)
                c.execute(text("""
                    INSERT INTO charging_sessions
                        (id, station_id, connector_id, power_kw, energy_kwh,
                         base_rate_idr, admin_fee_idr, deposit_idr, status, created_at)
                    VALUES (:id, :sid, :cid, :power, :energy, 2466, 2500, 0, :st,
                            now() - make_interval(mins => :age))
                """), {"id": session_id, "sid": sid,
                       "cid": connector_ids[spec.get("connector", 0)],
                       "power": spec.get("power_kw", _POWER_KW),
                       "energy": spec.get("energy_kwh", _ENERGY_KWH),
                       "st": spec.get("status", "active"),
                       "age": spec.get("minutes_ago", 0)})
        return sid, connector_ids

    yield make

    with engine.begin() as c:
        if sessions:
            c.execute(text("DELETE FROM charging_sessions WHERE id = ANY(:ids)"), {"ids": sessions})
        c.execute(text("DELETE FROM stations WHERE id = ANY(:ids)"), {"ids": stations})


def test_a_broken_plug_is_counted_out_of_service_not_in_use(seed):
    """total - available said 1 occupied. It is 1 dead plug, and it is not coming back."""
    sid, _ = seed([("CCS2", 50.0, "fast", "available"),
                   ("CCS2", 50.0, "fast", "out_of_service")])

    result = get_station_realtime_status(sid)

    assert result["total"] == 2
    assert result["available"] == 1
    assert result["in_use"] == 0
    assert result["out_of_service"] == 1
    assert result["station_status"] == 1
    # the driver's own types, straight out of psycopg, satisfy the contract
    for field in ("available", "total", "in_use", "out_of_service"):
        assert isinstance(result[field], int), field
        assert isinstance(result["connectors"][0][field], int), field


def test_a_station_of_only_broken_plugs_is_unavailable_with_no_estimate(seed):
    sid, _ = seed([("CCS2", 50.0, "fast", "out_of_service"),
                   ("CCS2", 50.0, "fast", "out_of_service")])

    result = get_station_realtime_status(sid)

    assert result["station_status"] == 0
    assert result["available"] == 0
    assert result["in_use"] == 0
    assert result["out_of_service"] == 2
    assert result["waiting_time"] is None
    assert result["connectors"][0]["waiting_time"] is None


def test_a_full_station_with_no_active_session_has_no_estimate(seed):
    """The GREATEST(0, NULL) trap: SQL used to turn 'unknown' into 0 before Python saw it."""
    sid, _ = seed([("CCS2", 50.0, "fast", "in_use"), ("CCS2", 50.0, "fast", "in_use")])

    result = get_station_realtime_status(sid)

    assert result["available"] == 0
    assert result["in_use"] == 2
    assert result["waiting_time"] is None
    assert result["connectors"][0]["waiting_time"] is None


def test_a_free_plug_means_a_wait_of_exactly_zero(seed):
    sid, _ = seed([("CCS2", 50.0, "fast", "available"), ("CCS2", 50.0, "fast", "in_use")],
                  with_sessions=[{"connector": 1}])

    result = get_station_realtime_status(sid)

    assert result["waiting_time"] == 0
    assert result["station_status"] == 1
    assert result["connectors"][0]["waiting_time"] == 0


def test_a_full_station_with_an_active_session_reports_the_minutes_left(seed):
    sid, _ = seed([("CCS2", _POWER_KW, "fast", "in_use")], with_sessions=[{"connector": 0}])

    result = get_station_realtime_status(sid)

    assert isinstance(result["waiting_time"], float)
    # 24 minutes minus however long the insert and the query took
    assert _MINUTES - 1.0 < result["waiting_time"] <= _MINUTES
    assert result["connectors"][0]["waiting_time"] == result["waiting_time"]


@pytest.mark.parametrize("power_kw", [None, 0.0])
def test_a_session_with_no_usable_power_yields_unknown_not_zero(seed, power_kw):
    """No power means no finish time. That is 'we cannot tell', not 'any moment now'."""
    sid, _ = seed([("CCS2", 50.0, "fast", "in_use")],
                  with_sessions=[{"connector": 0, "power_kw": power_kw}])

    assert get_station_realtime_status(sid)["waiting_time"] is None


def test_an_overdue_session_is_clamped_to_zero_never_negative(seed):
    """A session past its estimate must not report a wait in the past."""
    sid, _ = seed([("CCS2", _POWER_KW, "fast", "in_use")],
                  with_sessions=[{"connector": 0, "minutes_ago": 120}])

    assert get_station_realtime_status(sid)["waiting_time"] == 0


def test_a_completed_session_does_not_count_as_an_estimate(seed):
    """Only 'active' sessions say anything about when a plug frees up."""
    sid, _ = seed([("CCS2", _POWER_KW, "fast", "in_use")],
                  with_sessions=[{"connector": 0, "status": "completed"}])

    assert get_station_realtime_status(sid)["waiting_time"] is None


def test_two_groups_of_the_same_type_and_tier_are_separated_by_power(seed):
    """GROUP BY power_kw without SELECTing it produced identical-looking duplicates."""
    sid, _ = seed([("CCS2", 50.0, "fast", "available"),
                   ("CCS2", 50.0, "fast", "available"),
                   ("CCS2", 120.0, "fast", "available"),
                   ("CCS2", 120.0, "fast", "out_of_service")])

    groups = get_station_realtime_status(sid)["connectors"]

    assert len(groups) == 2
    assert [g["power_kw"] for g in groups] == [50.0, 120.0]
    assert [g["available"] for g in groups] == [2, 1]
    assert [g["out_of_service"] for g in groups] == [0, 1]
    # same type and tier, so power_kw is the only thing telling them apart
    assert {(g["type"], g["speed_tier"]) for g in groups} == {("CCS2", "fast")}


def test_a_second_active_session_on_one_connector_does_not_inflate_the_counts(seed):
    """Joining charging_sessions directly multiplied the connector row per session."""
    sid, _ = seed([("CCS2", _POWER_KW, "fast", "in_use")],
                  with_sessions=[{"connector": 0, "energy_kwh": 20.0},    # 24 min
                                 {"connector": 0, "energy_kwh": 5.0}])    # 6 min

    result = get_station_realtime_status(sid)

    assert result["total"] == 1
    assert result["in_use"] == 1
    assert len(result["connectors"]) == 1
    # and the estimate is the session finishing soonest, not the last one joined
    assert 5.0 < result["waiting_time"] <= 6.0


def test_the_station_wait_is_the_soonest_estimate_across_groups(seed):
    """A group with no estimate must not erase a group that has one."""
    sid, _ = seed([("CCS2", _POWER_KW, "fast", "in_use"),
                   ("AC Type 2", 22.0, "medium", "in_use")],
                  with_sessions=[{"connector": 0, "energy_kwh": 5.0}])   # 6 min, CCS2 only

    result = get_station_realtime_status(sid)

    by_type = {g["type"]: g for g in result["connectors"]}
    assert by_type["AC Type 2"]["waiting_time"] is None
    assert 5.0 < by_type["CCS2"]["waiting_time"] <= 6.0
    assert result["waiting_time"] == by_type["CCS2"]["waiting_time"]


def test_a_station_with_no_connector_rows_is_zeroed_and_unknown(seed):
    sid, _ = seed([])

    assert get_station_realtime_status(sid) == {
        "station_id": sid, "station_status": 0,
        "available": 0, "total": 0, "in_use": 0, "out_of_service": 0,
        "waiting_time": None, "connectors": [],
    }


def test_the_endpoint_serializes_ints_and_a_real_null(seed):
    """End to end: nothing between the SQL and the wire re-introduces a string."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api import main

    sid, _ = seed([("CCS2", 50.0, "fast", "in_use"),
                   ("CCS2", 50.0, "fast", "out_of_service")])

    with TestClient(main.app) as c:
        response = c.get(f"/api/v1/stations/{sid}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["station_id"] == sid
    for field in ("available", "total", "in_use", "out_of_service"):
        assert isinstance(body[field], int), field
        assert isinstance(body["connectors"][0][field], int), field
    assert body["in_use"] == 1 and body["out_of_service"] == 1
    assert body["waiting_time"] is None
    assert body["connectors"][0]["waiting_time"] is None
    assert body["connectors"][0]["power_kw"] == 50.0

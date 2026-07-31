"""GET /api/v1/stations/{id}/status: the response contract, without a database.

These lock the four defects the old shape shipped with:

  1. counts arrived as strings, so the client's comparisons and sums were
     string operations ("17" > "9" is false, "17" + 1 is "171");
  2. waiting_time was a string inside connectors[] and a float at station level;
  3. only available/total were exposed, so the client derived occupancy as
     total - available and showed a BROKEN charger as "in use, ~0 mins left";
  4. waiting_time 0 meant both "a plug is free now" and "we cannot tell", and
     the unknown case was rendered to the driver as a promise.

The SQL is exercised separately in test_station_status_db.py; here the query
result is fabricated so the Python contract is asserted on every run, including
on machines with no DATABASE_URL.
"""
from decimal import Decimal

import pytest

from api import connectors_repo

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402

pytestmark = pytest.mark.unit

_COUNT_FIELDS = ("available", "total", "in_use", "out_of_service")


def _group_row(type_: str = "CCS2", speed_tier: str = "fast", power_kw: float = 50.0, *,
               available: int = 0, in_use: int = 0, out_of_service: int = 0,
               waiting_time=None) -> dict:
    """One row shaped like _REALTIME_STATUS_SQL's output.

    Counts are Decimal and waiting_time is Decimal on purpose: that is what psycopg
    hands back for a numeric-typed aggregate (the waiting_time branch really is
    `round(...)::numeric`). Feeding the raw driver types is what makes the int/float
    assertions below able to fail -- with plain ints they would pass even if the
    coercion were deleted.
    """
    return {
        "type": type_,
        "speed_tier": speed_tier,
        "power_kw": power_kw,
        "total": Decimal(available + in_use + out_of_service),
        "available": Decimal(available),
        "in_use": Decimal(in_use),
        "out_of_service": Decimal(out_of_service),
        "waiting_time": waiting_time,
    }


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self):
        return self

    def all(self) -> list[dict]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def execute(self, statement, params=None) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeEngine:
    """Stands in for api.db.engine and replays a canned set of group rows."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self._rows)


@pytest.fixture
def status_for(monkeypatch):
    """Run get_station_realtime_status over fabricated group rows.

    connectors_repo does `from .db import engine`, so the module's own binding is
    the one that has to be replaced -- patching api.db.engine would miss it.
    """
    def run(rows: list[dict], station_id: str = "test-station") -> dict:
        monkeypatch.setattr(connectors_repo, "engine", _FakeEngine(rows))
        return connectors_repo.get_station_realtime_status(station_id)
    return run


# ---- defect 3: out_of_service is its own count, never folded into "occupied" ----

def test_a_broken_plug_is_reported_out_of_service_not_as_occupied(status_for):
    """total - available counted a dead charger as busy. Both counts now ship."""
    result = status_for([_group_row(available=1, out_of_service=1, waiting_time=0)])

    assert result["out_of_service"] == 1
    assert result["in_use"] == 0
    # The reason the extra fields exist: the old client-side subtraction still
    # says 1, and it is 1 *broken* plug, not 1 driver who will be done shortly.
    assert result["total"] - result["available"] == 1
    assert result["in_use"] != result["total"] - result["available"]
    assert result["connectors"][0]["out_of_service"] == 1
    assert result["connectors"][0]["in_use"] == 0


def test_a_station_whose_every_plug_is_broken_is_not_a_station_with_a_short_wait(status_for):
    """The worst case of defect 3+4 together: nothing works and nothing will free up."""
    result = status_for([_group_row(out_of_service=2, waiting_time=None)])

    assert result["station_status"] == 0
    assert result["available"] == 0
    assert result["in_use"] == 0
    assert result["out_of_service"] == 2
    # Not 0. A driver told "~0 mins left" would drive there and find two dead plugs.
    assert result["waiting_time"] is None
    assert result["connectors"][0]["waiting_time"] is None


def test_total_always_equals_the_three_status_counts(status_for):
    result = status_for([
        _group_row(power_kw=50.0, available=2, in_use=1, out_of_service=1, waiting_time=0),
        _group_row("AC Type 2", "medium", 22.0, in_use=3, waiting_time=Decimal("8.00")),
    ])

    assert result["total"] == result["available"] + result["in_use"] + result["out_of_service"]
    assert result["total"] == 7
    for group in result["connectors"]:
        assert group["total"] == group["available"] + group["in_use"] + group["out_of_service"]


def test_station_counts_are_the_sum_of_the_group_counts(status_for):
    result = status_for([
        _group_row(power_kw=50.0, available=2, out_of_service=1, waiting_time=0),
        _group_row(power_kw=120.0, available=1, in_use=4, waiting_time=0),
    ])

    assert result["available"] == 3
    assert result["in_use"] == 4
    assert result["out_of_service"] == 1
    assert result["total"] == 8


# ---- defect 1 + 2: the wire types ----

def test_every_count_is_an_int_at_both_levels(status_for):
    result = status_for([
        _group_row(available=2, in_use=1, out_of_service=1, waiting_time=0),
        _group_row("CHAdeMO", "medium", 22.0, available=1, waiting_time=0),
    ])

    for field in _COUNT_FIELDS:
        value = result[field]
        assert isinstance(value, int) and not isinstance(value, bool), (field, type(value))
        assert not isinstance(value, str), field
    for group in result["connectors"]:
        for field in _COUNT_FIELDS:
            value = group[field]
            assert isinstance(value, int) and not isinstance(value, bool), (field, type(value))
            assert not isinstance(value, str), field


def test_waiting_time_is_a_float_or_none_at_both_levels_never_a_string(status_for):
    """Same field, same type everywhere: it used to be str in a group, float on the station."""
    result = status_for([_group_row(in_use=2, waiting_time=Decimal("12.40"))])

    assert isinstance(result["waiting_time"], float)
    assert result["waiting_time"] == pytest.approx(12.4)
    assert isinstance(result["connectors"][0]["waiting_time"], float)
    assert result["connectors"][0]["waiting_time"] == pytest.approx(12.4)


# ---- defect 5: power_kw is part of the group's identity ----

def test_power_kw_is_exposed_so_same_type_groups_are_not_duplicates(status_for):
    """Two CCS2/fast groups used to come back as indistinguishable twins."""
    result = status_for([
        _group_row(power_kw=50.0, available=2, waiting_time=0),
        _group_row(power_kw=120.0, available=4, waiting_time=0),
    ])

    groups = result["connectors"]
    assert len(groups) == 2
    assert [g["power_kw"] for g in groups] == [50.0, 120.0]
    assert all(isinstance(g["power_kw"], float) for g in groups)
    # ...and identical (type, speed_tier) no longer makes them the same row.
    assert {(g["type"], g["speed_tier"]) for g in groups} == {("CCS2", "fast")}
    assert len({(g["type"], g["speed_tier"], g["power_kw"]) for g in groups}) == 2


def test_power_kw_survives_as_null_when_the_source_never_reported_one(status_for):
    result = status_for([_group_row(power_kw=None, available=1, waiting_time=0)])
    assert result["connectors"][0]["power_kw"] is None


# ---- defect 4: waiting_time is three-state ----

def test_a_free_plug_means_a_wait_of_zero(status_for):
    result = status_for([_group_row(available=2, in_use=1, waiting_time=0)])

    assert result["waiting_time"] == 0
    assert result["waiting_time"] is not None
    assert result["station_status"] == 1


def test_a_full_station_with_no_active_session_means_unknown_not_zero(status_for):
    """Nothing free and nothing to estimate from is not the same answer as 'no wait'."""
    result = status_for([_group_row(in_use=2, waiting_time=None)])

    assert result["waiting_time"] is None
    assert result["station_status"] == 0


def test_every_group_unknown_does_not_raise_from_min_over_an_empty_sequence(status_for):
    """min([]) raises ValueError; a full station nobody has a session at is routine."""
    result = status_for([
        _group_row(power_kw=50.0, in_use=2, waiting_time=None),
        _group_row("AC Type 2", "medium", 22.0, in_use=1, out_of_service=1, waiting_time=None),
    ])

    assert result["waiting_time"] is None
    assert all(g["waiting_time"] is None for g in result["connectors"])


def test_the_station_wait_is_the_soonest_estimate_that_is_known(status_for):
    """One unknown group must not swallow another group's real estimate."""
    result = status_for([
        _group_row(power_kw=50.0, in_use=2, waiting_time=None),
        _group_row(power_kw=120.0, in_use=1, waiting_time=Decimal("9.50")),
        _group_row("AC Type 2", "medium", 22.0, in_use=1, waiting_time=Decimal("31.00")),
    ])

    assert result["waiting_time"] == pytest.approx(9.5)


def test_a_free_plug_wins_over_another_group_still_waiting(status_for):
    """Somewhere to plug in right now is a 0 wait for the station as a whole."""
    result = status_for([
        _group_row(power_kw=50.0, available=1, waiting_time=0),
        _group_row(power_kw=120.0, in_use=2, waiting_time=Decimal("44.00")),
    ])

    assert result["waiting_time"] == 0
    assert result["station_status"] == 1
    assert result["connectors"][1]["waiting_time"] == pytest.approx(44.0)


# ---- the empty station ----

def test_a_station_with_no_connector_rows_is_zeroed_and_unknown(status_for):
    result = status_for([], station_id="no-connectors")

    assert result == {
        "station_id": "no-connectors", "station_status": 0,
        "available": 0, "total": 0, "in_use": 0, "out_of_service": 0,
        "waiting_time": None, "connectors": [],
    }


# ---- the HTTP boundary: what actually reaches the client ----

@pytest.fixture
def stub_status(monkeypatch):
    """Serve a canned repo payload through the real route + response_model."""
    from api import main

    def run(payload, station=None):
        monkeypatch.setattr(main.repo, "get_station", lambda sid: station)
        monkeypatch.setattr(main.connectors_repo, "get_station_realtime_status",
                            lambda sid: payload)
        with TestClient(main.app) as c:
            return c.get("/api/v1/stations/some-station/status")
    return run


@pytest.mark.integration
def test_the_serialized_body_carries_ints_and_a_real_null(stub_status):
    payload = {
        "station_id": "some-station", "station_status": 0,
        "available": 0, "total": 3, "in_use": 1, "out_of_service": 2,
        "waiting_time": None,
        "connectors": [{"type": "CCS2", "speed_tier": "fast", "power_kw": 50.0,
                        "available": 0, "total": 3, "in_use": 1, "out_of_service": 2,
                        "waiting_time": None}],
    }
    response = stub_status(payload, station={"id": "some-station"})
    assert response.status_code == 200

    body = response.json()
    for field in _COUNT_FIELDS:
        assert isinstance(body[field], int) and not isinstance(body[field], bool), field
        assert isinstance(body["connectors"][0][field], int), field
    # response_model must not coerce the unknown wait into a number on the way out
    assert body["waiting_time"] is None
    assert body["connectors"][0]["waiting_time"] is None
    assert body["connectors"][0]["power_kw"] == 50.0
    # the fields the client needs to stop deriving occupancy by subtraction
    assert body["in_use"] == 1 and body["out_of_service"] == 2


@pytest.mark.integration
def test_an_unknown_station_is_404_not_an_empty_status(stub_status):
    response = stub_status({}, station=None)
    assert response.status_code == 404

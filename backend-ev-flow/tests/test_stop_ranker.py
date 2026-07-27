"""Unit tests for the candidate filter/rank pipeline (AC 2.2.9)."""
from __future__ import annotations

import asyncio

import pytest

from api.services import stop_ranker as stop_ranker_module
from api.services.energy_estimator import EnergyEstimator
from api.services.routing_service import RoutingService
from api.services.station_availability import StationConnectorAvailability
from api.services.stop_ranker import StopRanker, choose_target_soc_pct, required_target_soc_pct

pytestmark = pytest.mark.unit

ORIGIN = (-6.2088, 106.8456)
DEST = (-6.9175, 107.6191)


def _station(sid: str, lat: float, lon: float, power_kw: float = 50.0) -> dict:
    return {
        "id": sid, "name": sid, "latitude": lat, "longitude": lon, "address": None,
        "province": None, "city": None, "operator": "PLN", "power_kw": power_kw,
        "speed_tier": "fast", "connector_types": ["CCS2"], "connector_inferred": False,
        "connectors": [], "sources": ["pln_spklu"], "status": "operational",
        "date_verified": None,
    }


def _avail(sid: str, available: dict, total: dict = None, power: dict = None):
    total = total or dict(available)
    power = power or {}
    return StationConnectorAvailability(
        station_id=sid, total=sum(total.values()), available=sum(available.values()),
        in_use=sum(total.values()) - sum(available.values()), out_of_service=0,
        available_by_type=available, total_by_type=total,
        best_available_power_kw=max([p for p in power.values() if p is not None], default=None),
        power_by_type=power,
    )


def _ranker(monkeypatch, stations, availabilities) -> StopRanker:
    monkeypatch.setattr(StopRanker, "_fetch_stations",
                        lambda self, o, d, forced, **kw: list(stations))
    monkeypatch.setattr(stop_ranker_module, "fetch_availability", lambda ids: dict(availabilities))
    return StopRanker(EnergyEstimator(), RoutingService())


def _rank(ranker, **kwargs):
    params = dict(
        origin=ORIGIN, destination=DEST, direct_distance_km=110.0,
        battery_kwh=58.0, efficiency_wh_per_km=160.0, current_soc_pct=45.0,
        minimum_arrival_soc_pct=20.0, maximum_detour_km=15.0,
        vehicle_connector="CCS", max_dc_charge_kw=185.0,
    )
    params.update(kwargs)
    return asyncio.run(ranker.rank_stops(**params))


# --------------------------------------------------------------------------
# defect 2: the magic 5-point slack is gone
# --------------------------------------------------------------------------
def test_a_reserve_intact_station_always_beats_a_below_reserve_one(monkeypatch):
    """The old filter was `< reserve - 5.0`, which shipped drivers below reserve.

    The strict AC 2.2.9 floor still governs whenever ANY station passes it: a
    station reached below the reserve is never offered alongside one reached
    with the reserve intact.
    """
    near = _station("st-near", -6.56, 107.23, power_kw=150.0)   # reachable, reserve intact
    far = _station("st-far", -6.85, 107.55, power_kw=150.0)     # ~100 km, arrival ~13%
    ranker = _ranker(monkeypatch, [near, far], {
        "st-near": _avail("st-near", {"CCS2": 2}, power={"CCS2": 150.0}),
        "st-far": _avail("st-far", {"CCS2": 2}, power={"CCS2": 150.0}),
    })

    stops = _rank(ranker, current_soc_pct=45.0)
    assert [s.station.id for s in stops] == ["st-near"]
    assert stops[0].reserve_intact_on_arrival is True


def test_below_reserve_station_is_offered_only_as_a_flagged_fallback(monkeypatch):
    """AC 2.1.1: never leave the driver with an empty list -- but never lie either."""
    far = _station("st-far", -6.85, 107.55, power_kw=150.0)   # ~100 km along the route
    ranker = _ranker(monkeypatch, [far], {"st-far": _avail("st-far", {"CCS2": 2}, power={"CCS2": 150.0})})

    # 45% start, ~100 km leg costs ~31.7% => arrival ~13%: below the 20% reserve.
    stops = _rank(ranker, current_soc_pct=45.0)
    assert len(stops) == 1
    assert stops[0].arrival_soc_pct < 20.0
    assert stops[0].reserve_intact_on_arrival is False

    # Lower the reserve and the very same station clears the STRICT pass.
    relaxed = _rank(ranker, current_soc_pct=45.0, minimum_arrival_soc_pct=5.0)
    assert len(relaxed) == 1
    assert relaxed[0].reserve_intact_on_arrival is True


def test_candidate_list_is_monotonic_in_starting_soc(monkeypatch):
    """No SoC dead zone: more charge never yields a worse answer (findings 1 + 7)."""
    mid = _station("st-mid", -6.30, 106.92, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid], {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})

    offered = {soc: len(_rank(ranker, current_soc_pct=soc)) for soc in
               (30.0, 26.0, 24.0, 22.0, 21.0, 20.1, 20.0, 19.0, 14.0)}
    assert all(n >= 1 for n in offered.values()), offered


def test_station_reached_exactly_at_the_reserve_is_accepted(monkeypatch):
    mid = _station("st-mid", -6.56, 107.23, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid], {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})

    stops = _rank(ranker, current_soc_pct=45.0)
    assert len(stops) == 1
    assert stops[0].arrival_soc_pct >= 20.0
    assert stops[0].reserve_intact_on_arrival is True


# --------------------------------------------------------------------------
# defect 3: live connector availability, not stations.status
# --------------------------------------------------------------------------
def test_operational_station_with_no_free_connector_is_rejected(monkeypatch):
    """`stations.status = 'operational'` no longer implies "available_now"."""
    mid = _station("st-mid", -6.56, 107.23)
    ranker = _ranker(monkeypatch, [mid],
                     {"st-mid": _avail("st-mid", {"CCS2": 0}, total={"CCS2": 4})})
    assert mid["status"] == "operational"
    assert _rank(ranker) == []


def test_station_absent_from_the_connectors_table_is_rejected(monkeypatch):
    mid = _station("st-mid", -6.56, 107.23)
    ranker = _ranker(monkeypatch, [mid], {})
    assert _rank(ranker) == []


def test_free_connector_of_the_wrong_type_is_rejected(monkeypatch):
    mid = _station("st-mid", -6.56, 107.23)
    ranker = _ranker(monkeypatch, [mid],
                     {"st-mid": _avail("st-mid", {"CHAdeMO": 3}, power={"CHAdeMO": 50.0})})
    # A CCS2 vehicle also accepts AC Type 2, but never CHAdeMO.
    assert _rank(ranker, vehicle_connector="CCS") == []


# --------------------------------------------------------------------------
# defect 6: detour never mixes measures
# --------------------------------------------------------------------------
def test_detour_is_non_negative_under_road_scaling(monkeypatch):
    mid = _station("st-mid", -6.56, 107.23, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid], {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})

    # Direct road distance 1.25x the straight line; legs scale by the same factor.
    stops = _rank(ranker, direct_distance_km=137.5, distance_scale_factor=1.25,
                  distance_basis="road", current_soc_pct=60.0)
    assert len(stops) == 1
    assert stops[0].detour_km >= 0.0
    assert stops[0].distance_basis == "road"


# --------------------------------------------------------------------------
# defect 7: the stop must complete the trip
# --------------------------------------------------------------------------
def test_required_target_soc_covers_the_remaining_leg_plus_reserve():
    est = EnergyEstimator(route_adjustment_factor=1.0, auxiliary_energy_kwh=0.0)
    # 50 km at 160 Wh/km on a 58 kWh pack = 8 kWh = 13.79%.
    required = required_target_soc_pct(est, 58.0, 160.0, 50.0, 20.0)
    assert required == pytest.approx(33.79, abs=0.01)


def test_choose_target_soc_prefers_80_but_never_less_than_needed():
    assert choose_target_soc_pct(30.0) == 80.0     # comfortable trip -> the 80% cap
    assert choose_target_soc_pct(92.0) == 92.0     # trip needs more -> raise it
    assert choose_target_soc_pct(100.0) == 100.0   # exactly a full pack still works
    assert choose_target_soc_pct(104.0) is None    # not even 100% is enough -> reject


def test_candidate_that_cannot_finish_the_trip_is_rejected(monkeypatch):
    """Reachable, free connector, small detour -- but too far from the destination."""
    near = _station("st-near", -6.25, 106.90, power_kw=50.0)
    ranker = _ranker(monkeypatch, [near],
                     {"st-near": _avail("st-near", {"CCS2": 2}, power={"CCS2": 50.0})})
    # 12 kWh pack at 160 Wh/km: ~104 km remain from the stop; a full charge is not enough.
    stops = _rank(ranker, battery_kwh=12.0, current_soc_pct=90.0, maximum_detour_km=50.0)
    assert stops == []


def test_accepted_candidate_reaches_the_destination_above_the_reserve(monkeypatch):
    mid = _station("st-mid", -6.56, 107.23, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid], {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})

    stop = _rank(ranker, current_soc_pct=45.0)[0]
    assert stop.completes_trip is True
    assert stop.projected_destination_soc_pct >= 20.0
    assert stop.recommended_target_soc_pct >= stop.required_target_soc_pct


# --------------------------------------------------------------------------
# ranking determinism
# --------------------------------------------------------------------------
def test_ranking_is_deterministic_for_identical_candidates(monkeypatch):
    a = _station("st-b", -6.56, 107.23, power_kw=150.0)
    b = _station("st-a", -6.56, 107.23, power_kw=150.0)
    avail = {
        "st-a": _avail("st-a", {"CCS2": 1}, power={"CCS2": 150.0}),
        "st-b": _avail("st-b", {"CCS2": 1}, power={"CCS2": 150.0}),
    }
    ranker = _ranker(monkeypatch, [a, b], avail)

    ids = [s.station.id for s in _rank(ranker, current_soc_pct=45.0)]
    assert ids == ["st-a", "st-b"]  # equal score -> station id breaks the tie


def test_select_recommended_stop_returns_the_best_candidate(monkeypatch):
    slow = _station("st-slow", -6.56, 107.23, power_kw=50.0)
    fast = _station("st-fast", -6.56, 107.23, power_kw=150.0)
    ranker = _ranker(monkeypatch, [slow, fast], {
        "st-slow": _avail("st-slow", {"CCS2": 1}, power={"CCS2": 50.0}),
        "st-fast": _avail("st-fast", {"CCS2": 1}, power={"CCS2": 150.0}),
    })

    stop = asyncio.run(ranker.select_recommended_stop(
        origin=ORIGIN, destination=DEST, direct_distance_km=110.0, battery_kwh=58.0,
        efficiency_wh_per_km=160.0, current_soc_pct=45.0, minimum_arrival_soc_pct=20.0,
        vehicle_connector="CCS", max_dc_charge_kw=185.0))
    assert stop is not None
    assert stop.station.id == "st-fast"


def test_no_stations_returns_no_stop(monkeypatch):
    ranker = _ranker(monkeypatch, [], {})
    assert _rank(ranker) == []


# --------------------------------------------------------------------------
# the candidate prefilter is SPATIAL, never `ORDER BY id LIMIT n`
# --------------------------------------------------------------------------
def test_fetch_stations_uses_the_corridor_query_not_an_id_ordered_page(monkeypatch):
    """`ORDER BY id LIMIT 150` hid the whole `pln_spklu-*` network from planning."""
    import api.stations_repo as stations_repo

    seen = {}

    def fake_along_corridor(**kwargs):
        seen.update(kwargs)
        return [_station("pln_spklu-1", -6.56, 107.23)]

    def fail_list_stations(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("route planning must not page stations by id")

    monkeypatch.setattr(stations_repo, "along_corridor", fake_along_corridor)
    monkeypatch.setattr(stations_repo, "list_stations", fail_list_stations)

    ranker = StopRanker(EnergyEstimator(), RoutingService())
    rows = ranker._fetch_stations(ORIGIN, DEST, None, corridor_km=8.0)

    assert [r["id"] for r in rows] == ["pln_spklu-1"]
    assert seen["origin"] == ORIGIN and seen["destination"] == DEST
    assert seen["corridor_km"] >= 8.0
    assert seen["limit"] == stop_ranker_module.CANDIDATE_FETCH_LIMIT


def test_fetch_stations_falls_back_to_a_bbox_page_when_the_corridor_query_fails(monkeypatch):
    import api.stations_repo as stations_repo

    def boom(**kwargs):
        raise RuntimeError("no PostGIS here")

    monkeypatch.setattr(stations_repo, "along_corridor", boom)
    monkeypatch.setattr(stations_repo, "list_stations",
                        lambda filters, limit, offset: (1, [_station("fallback", -6.5, 107.0)]))

    ranker = StopRanker(EnergyEstimator(), RoutingService())
    assert [r["id"] for r in ranker._fetch_stations(ORIGIN, DEST, None)] == ["fallback"]


# --------------------------------------------------------------------------
# a driver-forced waypoint skips the detour PREFERENCE, never the physics
# --------------------------------------------------------------------------
def test_forced_station_keeps_its_blocking_reasons(monkeypatch):
    far = _station("st-forced", -4.00, 109.50, power_kw=150.0)   # far beyond range
    ranker = _ranker(monkeypatch, [far],
                     {"st-forced": _avail("st-forced", {"CHAdeMO": 1}, power={"CHAdeMO": 50.0})})

    stops = _rank(ranker, current_soc_pct=45.0, forced_station_id="st-forced",
                  maximum_detour_km=1.0)

    assert len(stops) == 1            # honoured: the driver asked for it
    assert stops[0].completes_trip is False
    assert "unreachable" in stops[0].blocking_reasons
    assert "no_free_compatible_connector" in stops[0].blocking_reasons


def test_revalidate_on_road_rejects_a_stop_whose_real_tail_leg_breaks_the_reserve(monkeypatch):
    mid = _station("st-mid", -6.56, 107.23, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid], {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})
    stop = _rank(ranker, current_soc_pct=45.0)[0]

    kwargs = dict(
        stop=stop, road_leg_to_station_km=60.0, road_direct_distance_km=110.0,
        battery_kwh=58.0, efficiency_wh_per_km=160.0, current_soc_pct=45.0,
        reserve_pct=20.0, max_dc_charge_kw=185.0,
    )
    # A 55 km tail leg is fine; the same leg at 2.5x road winding is not.
    assert ranker.revalidate_on_road(road_leg_to_destination_km=55.0, **kwargs) is not None
    assert ranker.revalidate_on_road(road_leg_to_destination_km=300.0, **kwargs) is None


def test_revalidate_on_road_restates_every_distance_on_the_road_basis(monkeypatch):
    mid = _station("st-mid", -6.56, 107.23, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid], {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})
    stop = _rank(ranker, current_soc_pct=45.0)[0]

    validated = ranker.revalidate_on_road(
        stop=stop, road_leg_to_station_km=60.0, road_leg_to_destination_km=80.0,
        road_direct_distance_km=110.0, battery_kwh=58.0, efficiency_wh_per_km=160.0,
        current_soc_pct=45.0, reserve_pct=20.0, max_dc_charge_kw=185.0)

    assert validated.distance_from_origin_km == 60.0
    assert validated.distance_to_destination_km == 80.0
    assert validated.detour_km == 30.0            # (60 + 80) - 110, one basis throughout
    assert validated.distance_basis == "road"
    assert validated.station.distance_km == 60.0
    tail_soc = (80.0 * 160.0 / 1000.0) * 1.15 / 58.0 * 100.0
    assert validated.projected_destination_soc_pct == pytest.approx(
        validated.recommended_target_soc_pct - tail_soc, abs=0.1)

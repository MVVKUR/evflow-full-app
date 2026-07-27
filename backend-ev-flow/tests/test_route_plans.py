"""Tests for the route-plans endpoints (Epic 2.0 -- AC 2.1.1 / 2.1.2 / 2.1.3 / 2.2.9).

Auth note: `Depends(security.current_user)` captured the ORIGINAL function object
when `api.main` was imported, so `monkeypatch.setattr(security, "current_user", ...)`
never reached the dependency and every request 401'd. FastAPI's supported hook is
`app.dependency_overrides`, which the `as_user` fixture below installs and clears.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api import evmodels, security
from api.main import app
from api.services.routing_service import RouteUnavailable, RoutingService, haversine_distance_km
from api.services import stop_ranker as stop_ranker_module
from api.services.station_availability import StationConnectorAvailability
from api.services.stop_ranker import StopRanker

client = TestClient(app)

JAKARTA = (-6.2088, 106.8456)
BOGOR = (-6.5971, 106.7996)
BANDUNG = (-6.9175, 107.6191)
MIDPOINT = (-6.5600, 107.2300)  # roughly halfway Jakarta -> Bandung


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------
@pytest.fixture
def as_user():
    """Install a fake authenticated user via dependency_overrides, then clear it."""
    def _install(**overrides):
        user = {
            "id": "user-123",
            "username": "testuser",
            "ev_model_id": "hyundai-ioniq-5",
            "main_connector_type": "CCS2",
        }
        user.update(overrides)
        app.dependency_overrides[security.current_user] = lambda: user
        return user

    yield _install
    app.dependency_overrides.pop(security.current_user, None)


@pytest.fixture
def offline_routing(monkeypatch):
    """Deterministic, network-free routing: road distance == straight-line distance."""
    async def fake_get_route(self, origin, destination, waypoints=None):
        coords = [origin, *(waypoints or []), destination]
        total = sum(
            haversine_distance_km(a[0], a[1], b[0], b[1])
            for a, b in zip(coords, coords[1:])
        )
        return {
            "distance_km": round(total, 2),
            "duration_minutes": round((total / 50.0) * 60.0, 1),
            "geometry": {"type": "LineString",
                         "coordinates": [[c[1], c[0]] for c in coords]},
            "steps": [],
            "provider": "osrm",
        }

    monkeypatch.setattr(RoutingService, "get_route", fake_get_route)


def make_station(station_id: str, lat: float, lon: float, power_kw: float = 50.0,
                 connector_types=None) -> dict:
    """A station row shaped like `stations_repo.list_stations` returns."""
    return {
        "id": station_id,
        "name": f"SPKLU {station_id}",
        "latitude": lat,
        "longitude": lon,
        "address": "Jl. Test",
        "province": "Jawa Barat",
        "city": "Test City",
        "operator": "PLN",
        "power_kw": power_kw,
        "speed_tier": "fast",
        "connector_types": connector_types or ["CCS2"],
        "connector_inferred": False,
        "connectors": [],
        "sources": ["pln_spklu"],
        "status": "operational",
        "date_verified": None,
    }


def availability(station_id: str, available_by_type: dict, total_by_type: dict = None,
                 power_by_type: dict = None) -> StationConnectorAvailability:
    total_by_type = total_by_type or dict(available_by_type)
    power_by_type = power_by_type or {}
    available = sum(available_by_type.values())
    return StationConnectorAvailability(
        station_id=station_id,
        total=sum(total_by_type.values()),
        available=available,
        in_use=sum(total_by_type.values()) - available,
        out_of_service=0,
        available_by_type=available_by_type,
        total_by_type=total_by_type,
        best_available_power_kw=max([p for p in power_by_type.values() if p is not None], default=None),
        power_by_type=power_by_type,
    )


def use_stations(monkeypatch, stations: list[dict], availabilities: dict):
    """Stub the corridor query and the ONE availability query (no DB needed)."""
    monkeypatch.setattr(StopRanker, "_fetch_stations",
                        lambda self, origin, destination, forced, **kw: list(stations))
    monkeypatch.setattr(stop_ranker_module, "fetch_availability",
                        lambda ids: dict(availabilities))


IONIQ_5 = {
    "id": "hyundai-ioniq-5",
    "name": "Hyundai Ioniq 5 Standard Range",
    "battery_kwh": 58.0,
    "range_km": 384.0,
    "efficiency_wh_per_km": 160.0,
    "efficiency_source": "dataset",
    "max_dc_charge_kw": 185.0,
    "fast_charge_port": "CCS",  # catalogue spells it 'CCS'; live plugs say 'CCS2'
}


def plan_body(origin=JAKARTA, destination=BANDUNG, soc=60.0, **extra) -> dict:
    body = {
        "origin": {"latitude": origin[0], "longitude": origin[1], "label": "Origin"},
        "destination": {"latitude": destination[0], "longitude": destination[1], "label": "Destination"},
        "current_soc_pct": soc,
    }
    body.update(extra)
    return body


# --------------------------------------------------------------------------
# existing behaviour (kept green)
# --------------------------------------------------------------------------
def test_route_plan_unauthenticated():
    res = client.post("/api/v1/route-plans", json=plan_body(soc=72))
    assert res.status_code == 401


def test_route_plan_missing_ev_model(as_user):
    as_user(ev_model_id=None, main_connector_type=None)
    res = client.post("/api/v1/route-plans", json=plan_body(soc=72))
    assert res.status_code == 409
    assert "select an EV model" in res.json()["detail"]


def test_route_plan_does_not_return_synthetic_geometry_when_road_routing_fails(
        as_user, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))

    async def fail_get_route(self, origin, destination, waypoints=None):
        raise RouteUnavailable("no drivable road route found between the selected points")

    monkeypatch.setattr(RoutingService, "get_route", fail_get_route)

    res = client.post("/api/v1/route-plans", json=plan_body(soc=72))

    assert res.status_code == 503
    assert "no drivable road route" in res.json()["detail"]


def test_route_plan_direct_comfortably(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5, fast_charge_port="CCS2"))

    res = client.post("/api/v1/route-plans", json=plan_body(
        origin=JAKARTA, destination=BOGOR, soc=80.0, minimum_arrival_soc_pct=15.0))

    assert res.status_code == 200
    data = res.json()
    assert data["directly_reachable"] is True
    assert data["recommended_stop"] is None
    assert data["vehicle"]["battery_kwh"] == 58.0
    assert data["summary"]["estimated_arrival_soc_pct"] >= 15.0
    assert "geometry" in data["route"]


def test_route_plan_client_battery_override_ignored(as_user, offline_routing, monkeypatch):
    as_user(ev_model_id="wuling-air-ev", main_connector_type="Type 2")
    monkeypatch.setattr(evmodels, "get", lambda mid: {
        "id": "wuling-air-ev",
        "name": "Wuling Air EV",
        "battery_kwh": 26.7,
        "range_km": 200.0,
        "efficiency_wh_per_km": 133.5,
        "efficiency_source": "derived_local_specs",
        "max_dc_charge_kw": 30.0,
        "fast_charge_port": "Type 2",
    })
    use_stations(monkeypatch, [], {})

    res = client.post("/api/v1/route-plans", json=plan_body(
        origin=JAKARTA, destination=BOGOR, soc=50.0, battery_kwh=100.0))

    assert res.status_code == 200
    # battery_kwh stays 26.7 from the profile EV model, the client value is ignored
    assert res.json()["vehicle"]["battery_kwh"] == 26.7


# --------------------------------------------------------------------------
# AC 2.1.2 -- enough battery => green direct route, NO charging stops
# --------------------------------------------------------------------------
def test_ac_212_direct_route_available_omits_charging_stops(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    # A station IS available nearby -- it must still be omitted.
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    res = client.post("/api/v1/route-plans", json=plan_body(soc=95.0))

    assert res.status_code == 200
    data = res.json()
    assert data["route_status"] == "direct_route_available"
    assert data["charging_stops"] == []
    assert data["recommended_stop"] is None
    assert data["directly_reachable"] is True
    assert data["warning"] is None
    assert data["summary"]["estimated_arrival_soc_pct"] >= data["summary"]["minimum_arrival_soc_pct"]


def test_ac_212_tight_margin_is_still_a_direct_route(as_user, offline_routing, monkeypatch):
    """A snug-but-safe arrival stays 'direct_route_available' with zero stops."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    direct_km = haversine_distance_km(*JAKARTA, *BANDUNG)
    trip_soc = (direct_km * 160.0 / 1000.0) * 1.15 / 58.0 * 100.0
    soc = trip_soc + 22.0  # lands ~2 points above the 20% reserve

    data = client.post("/api/v1/route-plans", json=plan_body(soc=round(soc, 1))).json()

    assert data["route_status"] == "direct_route_available"
    assert data["margin_is_tight"] is True
    assert data["charging_stops"] == []


# --------------------------------------------------------------------------
# AC 2.1.3 -- reserve defaults to 20% and marks the route unsafe below it
# --------------------------------------------------------------------------
def test_ac_213_default_reserve_is_20_pct(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=60.0)).json()
    assert data["summary"]["minimum_arrival_soc_pct"] == 20.0
    assert data["assumptions"]["reserve_soc_pct"] == 20.0


def test_ac_213_arrival_below_20_marks_unsafe_and_recommends_a_stop(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    direct_km = haversine_distance_km(*JAKARTA, *BANDUNG)
    trip_soc = (direct_km * 160.0 / 1000.0) * 1.15 / 58.0 * 100.0
    soc = trip_soc + 17.0  # projected arrival ~17%: fine under a 15% rule, unsafe under 20%

    data = client.post("/api/v1/route-plans", json=plan_body(soc=round(soc, 1))).json()

    assert data["route_status"] == "charging_required"
    assert data["directly_reachable"] is False
    assert data["warning"]["triggered"] is True
    assert data["warning"]["code"] == "battery_below_reserve"
    assert data["warning"]["can_dismiss"] is True
    assert data["recommended_stop"] is not None
    assert len(data["charging_stops"]) == 1
    # 17% would have passed the OLD 15% default -- pin that it no longer does
    assert 15.0 < data["summary"]["direct_arrival_soc_pct"] < 20.0


def test_ac_213_no_suitable_station_is_explicit(as_user, offline_routing, monkeypatch):
    """Better an explicit outcome than a plan that fails partway."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-busy", *MIDPOINT)],
                 {"st-busy": availability("st-busy", {"CCS2": 0}, total_by_type={"CCS2": 2})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()

    assert data["route_status"] == "no_suitable_station"
    assert data["charging_stops"] == []
    assert data["recommended_stop"] is None
    assert data["warning"]["code"] == "no_suitable_station"


# --------------------------------------------------------------------------
# AC 2.2.9 -- free connector the vehicle can use, ranked by detour + power
# --------------------------------------------------------------------------
def test_ac_229_station_with_only_in_use_connectors_is_excluded(
        as_user, offline_routing, monkeypatch):
    """Two identical stations: the one whose plugs are all in_use must lose."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    busy = make_station("st-busy", MIDPOINT[0], MIDPOINT[1], power_kw=150.0)
    free = make_station("st-free", MIDPOINT[0], MIDPOINT[1], power_kw=150.0)
    use_stations(monkeypatch, [busy, free], {
        "st-busy": availability("st-busy", {"CCS2": 0}, total_by_type={"CCS2": 2}),
        "st-free": availability("st-free", {"CCS2": 1}, total_by_type={"CCS2": 2},
                                power_by_type={"CCS2": 150.0}),
    })

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()

    assert data["route_status"] == "charging_required"
    assert data["recommended_stop"]["station"]["id"] == "st-free"
    assert data["recommended_stop"]["available_connector_count"] == 1
    assert data["recommended_stop"]["availability"] == "available_now"
    picked = [s["station"]["id"] for s in data["charging_stops"] + data["alternative_stops"]]
    assert "st-busy" not in picked


def test_ac_229_ranks_by_detour_when_power_is_equal(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    on_route = make_station("st-on-route", MIDPOINT[0], MIDPOINT[1], power_kw=50.0)
    detoured = make_station("st-detour", MIDPOINT[0] - 0.20, MIDPOINT[1], power_kw=50.0)
    use_stations(monkeypatch, [detoured, on_route], {
        "st-on-route": availability("st-on-route", {"CCS2": 1}, power_by_type={"CCS2": 50.0}),
        "st-detour": availability("st-detour", {"CCS2": 1}, power_by_type={"CCS2": 50.0}),
    })

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()

    assert data["recommended_stop"]["station"]["id"] == "st-on-route"
    assert data["recommended_stop"]["detour_km"] < data["alternative_stops"][0]["detour_km"]
    assert data["recommended_stop"]["rank_score"] < data["alternative_stops"][0]["rank_score"]


def test_ac_229_ranks_by_power_when_detour_is_equal(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    slow = make_station("st-slow", MIDPOINT[0], MIDPOINT[1], power_kw=50.0)
    fast = make_station("st-fast", MIDPOINT[0], MIDPOINT[1], power_kw=150.0)
    use_stations(monkeypatch, [slow, fast], {
        "st-slow": availability("st-slow", {"CCS2": 1}, power_by_type={"CCS2": 50.0}),
        "st-fast": availability("st-fast", {"CCS2": 1}, power_by_type={"CCS2": 150.0}),
    })

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()

    assert data["recommended_stop"]["station"]["id"] == "st-fast"
    assert data["recommended_stop"]["detour_km"] == data["alternative_stops"][0]["detour_km"]
    assert data["recommended_stop"]["best_available_power_kw"] == 150.0


def test_ac_229_indonesia_only_model_without_port_matches_ac_type_2(
        as_user, offline_routing, monkeypatch):
    """fast_charge_port IS NULL for ~31 models -- they must still match AC Type 2."""
    as_user(ev_model_id="local-only-ev", main_connector_type=None)
    monkeypatch.setattr(evmodels, "get", lambda mid: {
        "id": "local-only-ev",
        "name": "Indonesia-only EV",
        "battery_kwh": 58.0,
        "efficiency_wh_per_km": 160.0,
        "efficiency_source": "derived_local_specs",
        "max_dc_charge_kw": None,
        "fast_charge_port": None,
    })
    use_stations(monkeypatch,
                 [make_station("st-ac", *MIDPOINT, power_kw=22.0, connector_types=["AC Type 2"])],
                 {"st-ac": availability("st-ac", {"AC Type 2": 2}, power_by_type={"AC Type 2": 22.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()

    assert data["recommended_stop"] is not None
    assert data["recommended_stop"]["station"]["id"] == "st-ac"
    assert data["recommended_stop"]["matched_connector_type"] == "AC Type 2"
    assert data["recommended_stop"]["connector_match_inferred"] is True
    assert data["assumptions"]["vehicle_connector_types"] == ["AC Type 2"]
    assert data["assumptions"]["connector_source"] == "default"


def test_ac_229_ccs_catalogue_port_matches_live_ccs2_plugs(
        as_user, offline_routing, monkeypatch):
    """Catalogue stores 'CCS'; the live connectors table stores 'CCS2'."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5, fast_charge_port="CCS"))
    use_stations(monkeypatch,
                 [make_station("st-ccs", *MIDPOINT, power_kw=150.0)],
                 {"st-ccs": availability("st-ccs", {"CCS2": 1}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()

    assert data["recommended_stop"]["station"]["id"] == "st-ccs"
    assert data["recommended_stop"]["matched_connector_type"] == "CCS2"
    assert data["assumptions"]["vehicle_connector_types"] == ["CCS2", "AC Type 2"]


def test_ac_229_stop_must_complete_the_trip(as_user, offline_routing, monkeypatch):
    """A station reachable but too far from the destination to finish is rejected."""
    as_user()
    # 20 kWh pack, thirsty: even a 100% charge at the midpoint cannot finish.
    monkeypatch.setattr(evmodels, "get", lambda mid: {
        "id": "tiny-ev", "name": "Tiny EV", "battery_kwh": 12.0,
        "efficiency_wh_per_km": 160.0, "efficiency_source": "dataset",
        "max_dc_charge_kw": 30.0, "fast_charge_port": "CCS2",
    })
    near = make_station("st-near", JAKARTA[0] - 0.05, JAKARTA[1] + 0.05, power_kw=50.0)
    use_stations(monkeypatch, [near],
                 {"st-near": availability("st-near", {"CCS2": 2}, power_by_type={"CCS2": 50.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=90.0)).json()

    assert data["route_status"] == "no_suitable_station"
    assert data["recommended_stop"] is None


def test_decimal_max_dc_charge_kw_does_not_raise(as_user, offline_routing, monkeypatch):
    """numeric(8,2) arrives as Decimal; min(Decimal, float) used to 500."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5, max_dc_charge_kw=Decimal("185.00")))
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    res = client.post("/api/v1/route-plans", json=plan_body(soc=45.0))

    assert res.status_code == 200
    stop = res.json()["recommended_stop"]
    assert stop is not None
    assert stop["effective_charging_power_kw"] == 150.0


def test_detour_is_never_negative(as_user, offline_routing, monkeypatch):
    """Legs and the direct distance share one basis, so the subtraction is sound."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()

    assert data["recommended_stop"]["detour_km"] >= 0.0
    assert data["recommended_stop"]["distance_basis"] in ("road", "straight_line")
    assert data["assumptions"]["distance_basis"] == data["recommended_stop"]["distance_basis"]


# --------------------------------------------------------------------------
# AC 2.1.1 -- warn on an ACTIVE route and offer stations to add as a stop
# --------------------------------------------------------------------------
def active_body(position=MIDPOINT, destination=BANDUNG, soc=25.0, **extra) -> dict:
    body = {
        "current_position": {"latitude": position[0], "longitude": position[1]},
        "destination": {"latitude": destination[0], "longitude": destination[1]},
        "current_soc_pct": soc,
    }
    body.update(extra)
    return body


def test_ac_211_requires_auth():
    assert client.post("/api/v1/route-plans/active/evaluate", json=active_body()).status_code == 401


def test_ac_211_active_route_warns_and_offers_stations(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    near_mid = (MIDPOINT[0] - 0.05, MIDPOINT[1] + 0.05)
    use_stations(monkeypatch,
                 [make_station("st-free", *near_mid, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    res = client.post("/api/v1/route-plans/active/evaluate",
                      json=active_body(soc=30.0, route_plan_id="plan-abc"))

    assert res.status_code == 200
    data = res.json()
    assert data["route_plan_id"] == "plan-abc"
    assert data["route_status"] == "charging_required"
    assert data["warning"]["triggered"] is True
    assert data["warning"]["can_dismiss"] is True          # AC 2.1.1 "dismiss and continue"
    assert data["reserve_soc_pct"] == 20.0
    assert data["projected_arrival_soc_pct"] < 20.0
    assert len(data["candidate_stops"]) >= 1               # AC 2.1.1 "view available stations"
    assert data["candidate_stops"][0]["station"]["id"] == "st-free"
    assert data["candidate_stops"][0]["available_connector_count"] >= 1
    assert data["candidate_stops"][0]["reserve_intact_on_arrival"] is True


def test_ac_211_already_below_reserve_still_offers_reachable_stations(
        as_user, offline_routing, monkeypatch):
    """Reserve already breached: demanding it stay intact would strand the driver."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    near_mid = (MIDPOINT[0] - 0.03, MIDPOINT[1] + 0.03)
    use_stations(monkeypatch,
                 [make_station("st-free", *near_mid, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans/active/evaluate",
                       json=active_body(soc=14.0)).json()

    assert data["route_status"] == "charging_required"
    assert len(data["candidate_stops"]) == 1
    assert data["candidate_stops"][0]["reserve_intact_on_arrival"] is False


def test_ac_211_active_route_no_warning_when_comfortable(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans/active/evaluate",
                       json=active_body(soc=95.0)).json()

    assert data["route_status"] == "direct_route_available"
    assert data["candidate_stops"] == []
    assert data["warning"] is None


def test_active_evaluation_derives_current_soc_from_travelled_distance(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    start = client.post("/api/v1/route-plans/active/evaluate", json=active_body(
        soc=72.0, navigation_start_soc_pct=72.0,
        cumulative_distance_travelled_km=0.0)).json()
    moved = client.post("/api/v1/route-plans/active/evaluate", json=active_body(
        soc=72.0, navigation_start_soc_pct=72.0,
        cumulative_distance_travelled_km=20.0)).json()
    repeated = client.post("/api/v1/route-plans/active/evaluate", json=active_body(
        soc=72.0, navigation_start_soc_pct=72.0,
        cumulative_distance_travelled_km=20.0)).json()

    assert moved["estimated_current_soc_pct"] < start["estimated_current_soc_pct"]
    assert moved["estimated_current_soc_pct"] == repeated["estimated_current_soc_pct"]
    assert moved["estimated_current_soc_pct"] <= 72.0
    assert moved["current_soc_source"] == "distance_estimate"
    assert moved["energy_assumptions"]["route_adjustment_method"] == "fixed_fallback"
    assert moved["energy_assumptions"]["traffic_factor"] == 1.0


def test_active_evaluation_uses_measured_soc_without_exceeding_start(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})
    data = client.post("/api/v1/route-plans/active/evaluate", json=active_body(
        soc=72.0, navigation_start_soc_pct=72.0,
        cumulative_distance_travelled_km=10.0,
        measured_current_soc_pct=90.0)).json()
    assert data["estimated_current_soc_pct"] == 72.0
    assert data["current_soc_source"] == "vehicle_telemetry"


def test_ac_211_no_soc_dead_zone_just_above_the_reserve(as_user, offline_routing, monkeypatch):
    """A driver at 24% must not be told "nothing is reachable" when 20% offers five.

    The reach floor used to be a step function of the CURRENT SoC, so a band of
    values immediately above the reserve returned a critical warning with an
    empty candidate list while both higher and lower SoC returned stations.
    """
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    ahead = (MIDPOINT[0] - 0.03, MIDPOINT[1] + 0.03)  # ~4.7 km along the route
    use_stations(monkeypatch,
                 [make_station("st-free", *ahead, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    for soc in (30.0, 26.0, 24.0, 22.0, 21.0, 20.1, 20.0, 19.0, 14.0):
        data = client.post("/api/v1/route-plans/active/evaluate",
                           json=active_body(soc=soc)).json()
        assert data["route_status"] == "charging_required", (soc, data["route_status"])
        assert len(data["candidate_stops"]) >= 1, (soc, data["candidate_stops"])
        assert data["candidate_stops"][0]["station"]["id"] == "st-free"


def test_ac_211_warning_never_arrives_without_stations_to_offer(
        as_user, offline_routing, monkeypatch):
    """AC 2.1.1 pairs the alert with stations the driver can add as a stop."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    ahead = (MIDPOINT[0] - 0.03, MIDPOINT[1] + 0.03)
    use_stations(monkeypatch,
                 [make_station("st-free", *ahead, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    for soc in (24.0, 22.0, 21.0):
        data = client.post("/api/v1/route-plans/active/evaluate",
                           json=active_body(soc=soc)).json()
        assert data["warning"]["code"] == "battery_below_reserve"
        assert data["candidate_stops"], soc


# --------------------------------------------------------------------------
# driver-forced waypoints: honest warnings, honest summary
# --------------------------------------------------------------------------
def test_driver_waypoint_on_a_safe_route_emits_no_false_below_reserve_warning(
        as_user, offline_routing, monkeypatch):
    """AC 2.1.2: adding a stop by hand must not fabricate a below-reserve alert."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans",
                       json=plan_body(soc=95.0, waypoint_station_id="st-free")).json()

    assert data["route_status"] == "direct_route_available"
    assert data["summary"]["direct_arrival_soc_pct"] > data["summary"]["minimum_arrival_soc_pct"]
    assert data["warning"]["triggered"] is False
    assert data["warning"]["code"] == "stop_added_by_driver"
    # AC 2.1.2: the green state omits charging-stop RECOMMENDATIONS ...
    assert data["charging_stops"] == []
    assert data["recommended_stop"] is None
    assert data["directly_reachable"] is True
    # ... while still honouring what the driver asked for, in its own field.
    assert data["user_requested_stop"]["station"]["id"] == "st-free"
    assert data["user_requested_stop"]["completes_trip"] is True


def test_forced_stop_beyond_range_is_not_dressed_up_as_a_safe_trip(
        as_user, offline_routing, monkeypatch):
    """A forced waypoint may skip the detour budget -- never the physics."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    unreachable = (JAKARTA[0], JAKARTA[1] + 3.0)  # ~330 km away, range is ~190 km
    use_stations(monkeypatch,
                 [make_station("st-unreach", *unreachable, power_kw=150.0)],
                 {"st-unreach": availability("st-unreach", {"CCS2": 2},
                                             power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans",
                       json=plan_body(soc=60.0, waypoint_station_id="st-unreach")).json()

    stop = data["user_requested_stop"]
    assert stop is not None
    assert stop["completes_trip"] is False
    assert "unreachable" in stop["blocking_reasons"]
    assert data["warning"]["code"] == "forced_stop_unreachable"
    assert data["warning"]["triggered"] is True
    # No post-charge figures for a charge that can never happen.
    assert data["recommended_stop"] is None
    assert data["charging_stops"] == []
    assert data["summary"]["estimated_arrival_soc_pct"] == 0.0
    assert data["summary"]["soc_margin_pct"] < 0


def test_forced_stop_without_a_usable_free_connector_is_flagged(
        as_user, offline_routing, monkeypatch):
    """Only connector is CHAdeMO and it is in_use: the plan must say so."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-bad", *MIDPOINT, power_kw=50.0,
                               connector_types=["CHAdeMO"])],
                 {"st-bad": availability("st-bad", {"CHAdeMO": 0},
                                         total_by_type={"CHAdeMO": 1})})

    data = client.post("/api/v1/route-plans",
                       json=plan_body(soc=45.0, waypoint_station_id="st-bad")).json()

    stop = data["user_requested_stop"]
    assert stop is not None
    assert stop["completes_trip"] is False
    assert "no_free_compatible_connector" in stop["blocking_reasons"]
    assert stop["available_connector_count"] == 0
    assert stop["connector_compatible"] is False
    assert data["warning"]["code"] == "forced_stop_unavailable"
    assert data["recommended_stop"] is None
    assert data["charging_stops"] == []
    # Arrival is the no-charge projection over the detoured route, not a fiction.
    assert data["summary"]["estimated_arrival_soc_pct"] < data["summary"]["minimum_arrival_soc_pct"]


# --------------------------------------------------------------------------
# the SoC guarantee holds on the ROAD, not on a scaled straight line
# --------------------------------------------------------------------------
@pytest.fixture
def winding_tail_routing(monkeypatch):
    """Routing where only the legs LEAVING `stop_pos` are more winding than the corridor.

    The corridor itself stays at 1.0x, so `distance_scale_factor` is 1.0 and the
    ranker's straight-line estimate for the stop->destination leg is optimistic
    by exactly `tail_factor` -- the situation that used to break the SoC promise.
    """
    def _install(stop_pos, tail_factor: float):
        async def fake_get_route(self, origin, destination, waypoints=None):
            coords = [origin, *(waypoints or []), destination]
            total = 0.0
            for a, b in zip(coords, coords[1:]):
                straight = haversine_distance_km(a[0], a[1], b[0], b[1])
                winding = tail_factor if tuple(a) == tuple(stop_pos) else 1.0
                total += straight * winding
            return {
                "distance_km": round(total, 2),
                "duration_minutes": round((total / 50.0) * 60.0, 1),
                "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in coords]},
                "steps": [],
                "provider": "osrm",
            }

        monkeypatch.setattr(RoutingService, "get_route", fake_get_route)

    return _install


def test_stop_soc_guarantee_uses_the_real_road_leg(as_user, winding_tail_routing, monkeypatch):
    """The stop->destination leg is 2x the corridor average: the plan must notice."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    winding_tail_routing(MIDPOINT, 2.0)
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()
    stop = data["recommended_stop"]
    assert stop is not None

    real_tail_km = haversine_distance_km(*MIDPOINT, *BANDUNG) * 2.0
    real_head_km = haversine_distance_km(*JAKARTA, *MIDPOINT)

    # The leg the SoC math used IS the leg the driver drives.
    assert stop["distance_to_destination_km"] == pytest.approx(real_tail_km, rel=0.02)
    assert stop["distance_from_origin_km"] == pytest.approx(real_head_km, rel=0.02)
    assert data["summary"]["distance_km"] == pytest.approx(real_head_km + real_tail_km, rel=0.02)

    # And the promise still holds when recomputed from scratch on that leg.
    tail_soc = (real_tail_km * 160.0 / 1000.0) * 1.15 / 58.0 * 100.0
    assert stop["projected_destination_soc_pct"] == pytest.approx(
        stop["recommended_target_soc_pct"] - tail_soc, abs=0.2)
    assert stop["projected_destination_soc_pct"] >= data["summary"]["minimum_arrival_soc_pct"]
    assert data["summary"]["estimated_arrival_soc_pct"] >= data["summary"]["minimum_arrival_soc_pct"]


def test_stop_whose_real_tail_leg_breaks_the_reserve_is_not_offered(
        as_user, winding_tail_routing, monkeypatch):
    """A candidate that only worked on the straight line must be dropped, not shipped."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: {
        "id": "citroen-e-c3", "name": "Citroen e-C3", "battery_kwh": 29.2,
        "efficiency_wh_per_km": 135.0, "efficiency_source": "dataset",
        "max_dc_charge_kw": 45.0, "fast_charge_port": "CCS",
    })
    winding_tail_routing(MIDPOINT, 3.0)
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=60.0)).json()

    assert data["route_status"] == "no_suitable_station"
    assert data["recommended_stop"] is None
    assert data["charging_stops"] == []

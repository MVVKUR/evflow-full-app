"""Epic 2 acceptance criteria that an empirical audit found unimplemented.

Each test pins the AC WORDING it exists to defend, so a future refactor that
re-breaks the criterion fails here rather than in a demo:

  AC 2.2.1  route input is only valid INSIDE the configured route service area
  AC 2.2.2  outside it (or battery outside 0-100) => field-specific error, NO route
  AC 2.2.3  the projection may come from a vehicle profile OR an entered range
  AC 2.2.4  charging preferences must actually re-prioritise the stops shown
  AC 2.2.6  no suitable station => advise another route / preferences / charge first
  AC 2.4.1  navigation needs an arrival TIME and real turn-by-turn instructions

Fixtures and station stubs are shared with `test_route_plans.py` so both files
describe the same simulated world.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api import evmodels
from api.main import app
from api.services import service_area
from api.services.routing_service import RoutingService
from tests.test_route_plans import (  # noqa: F401  (fixtures are used by injection)
    BANDUNG,
    BOGOR,
    IONIQ_5,
    JAKARTA,
    MIDPOINT,
    active_body,
    as_user,
    availability,
    make_station,
    offline_routing,
    plan_body,
    use_stations,
)

client = TestClient(app)

# Well outside the configured service area, in several different directions.
SYDNEY = (-33.8688, 151.2093)      # 5,500 km away
SYDNEY_NORTH = (-33.7000, 151.1000)
PACIFIC_A = (0.0, -160.0)
PACIFIC_B = (1.0, -160.0)
PERTH = (-31.9523, 115.8613)       # south of the archipelago
SINGAPORE = (1.3521, 103.8198)     # close by, but not Indonesia

# INSIDE the default area but far outside the Jabodetabek narrative: these are
# real seeded stations' provinces (Sumatera Utara 99 stations, Bali 110, Jawa
# Timur 230). They exist to pin HIGH-2 -- the shipped dataset is national, so
# the default boundary must not refuse half of what the app already offers.
MEDAN = (3.5952, 98.6722)          # Sumatra
DENPASAR = (-8.6705, 115.2126)     # Bali
SURABAYA = (-7.2575, 112.7521)     # East Java


def _locs(body: dict) -> list[list]:
    return [d["loc"] for d in body["detail"]]


# --------------------------------------------------------------------------
# AC 2.2.1 -- "Given the driver is within the configured route service area
#              and the battery level is between 0 and 100 ..."
# --------------------------------------------------------------------------
def test_ac_221_service_area_is_configured_and_echoed_back(as_user, offline_routing, monkeypatch):
    """The Given clause is only verifiable if the area is a real, observable thing."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans",
                       json=plan_body(origin=JAKARTA, destination=BOGOR, soc=72.0)).json()

    area = data["assumptions"]["service_area"]
    assert area["enforced"] is True
    assert area["name"]
    # The canonical Jakarta -> Bogor demo route must lie INSIDE it. (The old
    # api.routing.BBOX, the only bounded region that existed, did not contain
    # Bogor at all -- proof it was a graph-download extent, not a service area.)
    for lat, lon in (JAKARTA, BOGOR):
        assert area["south"] <= lat <= area["north"]
        assert area["west"] <= lon <= area["east"]
    assert service_area.contains(*JAKARTA) and service_area.contains(*BOGOR)


@pytest.mark.parametrize("soc", [0.0, 100.0])
def test_ac_221_battery_boundaries_0_and_100_are_valid(as_user, offline_routing, monkeypatch, soc):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    res = client.post("/api/v1/route-plans",
                      json=plan_body(origin=JAKARTA, destination=BOGOR, soc=soc))
    assert res.status_code == 200


# --------------------------------------------------------------------------
# AC 2.2.2 -- "... when the origin or destination is outside the configured
#              route service area, or the battery is outside 0-100, then a
#              field-specific validation error is returned and no route is
#              generated."
# --------------------------------------------------------------------------
@pytest.mark.parametrize("soc", [150.0, -5.0])
def test_ac_222_battery_outside_range_is_field_specific(as_user, soc):
    as_user()
    res = client.post("/api/v1/route-plans", json=plan_body(soc=soc))
    assert res.status_code == 422
    assert ["body", "current_soc_pct"] in _locs(res.json())


@pytest.mark.parametrize("origin,destination,bad_fields", [
    (JAKARTA, PERTH, ["destination"]),
    (JAKARTA, SYDNEY, ["destination"]),
    (SYDNEY, SYDNEY_NORTH, ["origin", "destination"]),
    (PACIFIC_A, PACIFIC_B, ["origin", "destination"]),
])
def test_ac_222_out_of_service_area_is_rejected_and_no_route_is_generated(
        as_user, origin, destination, bad_fields):
    """Every one of these used to return HTTP 200 with a full route simulation."""
    as_user()
    res = client.post("/api/v1/route-plans", json=plan_body(origin=origin, destination=destination))

    assert res.status_code == 422
    body = res.json()
    locs = _locs(body)
    for field in bad_fields:
        assert ["body", field] in locs, (field, locs)
    # "no route is generated": the response is a validation error, full stop.
    assert set(body) == {"detail"}


def test_high2_rectangle_admits_some_neighbours_and_says_so(
        as_user, offline_routing, monkeypatch):
    """The accepted cost of a four-number boundary, pinned so it stays deliberate.

    A rectangle over the archipelago also contains Singapore, peninsular
    Malaysia, Brunei and Timor-Leste. Those are ACCEPTED -- but there is no
    seeded station there, so the plan comes back honestly reporting that rather
    than inventing a charging stop. The docstring commits to this trade; this
    test makes sure nobody "fixes" it by shrinking the box back under the data.
    """
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    res = client.post("/api/v1/route-plans",
                      json=plan_body(origin=JAKARTA, destination=SINGAPORE, soc=10.0))

    assert res.status_code == 200
    assert service_area.contains(*SINGAPORE) is True
    assert "rectangle" in (service_area.__doc__ or "").lower()
    data = res.json()
    # No station data there, so it must say so instead of simulating one.
    assert data["route_status"] == "no_suitable_station"
    assert data["warning"] is not None
    assert data["charging_stops"] == []


@pytest.mark.parametrize("destination", [MEDAN, DENPASAR, SURABAYA])
def test_high2_a_destination_the_app_ships_stations_for_is_routable(
        as_user, offline_routing, monkeypatch, destination):
    """HIGH-2: the planner must not refuse half the dataset the app advertises.

    The seeded dataset is national (2,900+ stations; Sumatera Utara, Bali and
    Jawa Timur alone hold 439 of them), so a Jabodetabek-sized default box made
    ~49% of the stations un-routable while /api/v1/stations,
    /api/v1/stations/nearby and /api/v1/geocoding/search went on offering them.
    """
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    res = client.post("/api/v1/route-plans",
                      json=plan_body(origin=JAKARTA, destination=destination, soc=100.0))

    assert res.status_code != 422, res.text


@pytest.mark.parametrize("destination", [MEDAN, DENPASAR, SURABAYA])
def test_high2_narrowing_the_area_still_rejects_and_discovery_follows(
        as_user, monkeypatch, destination):
    """The boundary is still real: narrow it and the same places are refused.

    Discovery follows automatically because `in_service_area` is computed from
    these same constants -- so the picker can never be left offering a
    destination the planner now refuses.
    """
    as_user()
    monkeypatch.setattr(service_area, "SERVICE_AREA_SOUTH", -7.35)
    monkeypatch.setattr(service_area, "SERVICE_AREA_WEST", 105.90)
    monkeypatch.setattr(service_area, "SERVICE_AREA_NORTH", -5.60)
    monkeypatch.setattr(service_area, "SERVICE_AREA_EAST", 108.30)

    res = client.post("/api/v1/route-plans",
                      json=plan_body(origin=JAKARTA, destination=destination))

    assert res.status_code == 422
    assert ["body", "destination"] in _locs(res.json())
    assert service_area.contains(*destination) is False


def test_ac_222_out_of_area_message_names_the_configured_area(as_user):
    as_user()
    res = client.post("/api/v1/route-plans", json=plan_body(origin=JAKARTA, destination=SYDNEY))
    msg = next(d["msg"] for d in res.json()["detail"] if d["loc"] == ["body", "destination"])
    assert "route service area" in msg
    assert service_area.SERVICE_AREA_NAME in msg


def test_ac_222_gate_is_planning_only_not_the_active_route(
        as_user, offline_routing, monkeypatch):
    """HIGH-1: the boundary must NOT become a mid-journey kill switch.

    AC 2.2.2 is about PLANNING a route. AC 2.1.1 and AC 2.4.2 are about a driver
    who is ALREADY TRAVELLING and must keep receiving battery re-evaluations.
    Applying the planning gate to `current_position` hard-failed the second the
    driver crossed the boundary -- silencing warnings at exactly the moment the
    other two ACs exist to cover. Planning still rejects; evaluating still
    answers.
    """
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    # Planning from out of area: still a field-specific 422, no route.
    planned = client.post("/api/v1/route-plans",
                          json=plan_body(origin=SYDNEY, destination=SYDNEY_NORTH))
    assert planned.status_code == 422

    # Mid-journey from the SAME out-of-area position: a usable evaluation.
    res = client.post("/api/v1/route-plans/active/evaluate",
                      json=active_body(position=SYDNEY, destination=SYDNEY_NORTH, soc=40.0))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["route_status"]
    assert data["projected_arrival_soc_pct"] is not None
    assert data["reserve_soc_pct"] is not None


def test_ac_222_active_route_reports_out_of_area_instead_of_refusing(
        as_user, offline_routing, monkeypatch):
    """Not silently dropped either: flagged, named per field, and advised."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans/active/evaluate",
                       json=active_body(position=SYDNEY, destination=BANDUNG,
                                        soc=40.0)).json()

    assert data["out_of_service_area"] is True
    assert data["out_of_service_area_fields"] == ["current_position"]
    assert data["service_area"]["name"] == service_area.SERVICE_AREA_NAME
    codes = [a["code"] for a in data["advisories"]]
    assert "out_of_service_area" in codes
    advisory = next(a for a in data["advisories"] if a["code"] == "out_of_service_area")
    assert advisory["can_dismiss"] is True
    assert "return_to_service_area" in advisory["suggested_actions"]


def test_ac_222_in_area_active_route_carries_no_advisory(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans/active/evaluate",
                       json=active_body(position=JAKARTA, destination=BOGOR,
                                        soc=40.0)).json()

    assert data["out_of_service_area"] is False
    assert data["out_of_service_area_fields"] == []
    assert [a for a in data["advisories"] if a["code"] == "out_of_service_area"] == []


def test_ac_241_battery_warning_survives_crossing_the_boundary(
        as_user, offline_routing, monkeypatch):
    """AC 2.4.2: the battery warning must still fire when the driver is outside.

    The advisory rides in `advisories`, never in `warning`, so it cannot displace
    the projection the driver actually needs.
    """
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans/active/evaluate",
                       json=active_body(position=SYDNEY, destination=SYDNEY_NORTH,
                                        soc=3.0)).json()

    assert data["out_of_service_area"] is True
    assert data["warning"] is not None, "battery warnings must not stop at the boundary"
    assert data["warning"]["code"] != "out_of_service_area"
    assert data["warning"]["projected_arrival_soc_pct"] is not None


def test_ac_222_service_area_edges_are_configurable(as_user, offline_routing, monkeypatch):
    """The boundary is env-driven, not a magic number frozen into the endpoint."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})
    # Shrink the area so Bogor falls outside it; the same request must now 422.
    monkeypatch.setattr(service_area, "SERVICE_AREA_SOUTH", -6.30)

    res = client.post("/api/v1/route-plans", json=plan_body(origin=JAKARTA, destination=BOGOR))
    assert res.status_code == 422
    assert ["body", "destination"] in _locs(res.json())


def test_ac_222_enforcement_can_be_switched_off(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})
    monkeypatch.setattr(service_area, "SERVICE_AREA_ENFORCED", False)

    res = client.post("/api/v1/route-plans", json=plan_body(origin=JAKARTA, destination=SYDNEY))
    assert res.status_code == 200


# --------------------------------------------------------------------------
# AC 2.2.3 -- "Given the driver has selected a vehicle profile OR entered a
#              valid vehicle range ..."
# --------------------------------------------------------------------------
def test_ac_223_entered_range_plans_without_any_profile(as_user, offline_routing, monkeypatch):
    """The 'OR entered a valid vehicle range' arm: this used to be a hard 409."""
    as_user(ev_model_id=None, main_connector_type=None)
    use_stations(monkeypatch, [], {})

    res = client.post("/api/v1/route-plans", json=plan_body(
        origin=JAKARTA, destination=BOGOR, soc=100.0,
        vehicle={"usable_range_km": 350.0}))

    assert res.status_code == 200
    data = res.json()
    assert data["vehicle"]["efficiency_source"] == "manual_range"
    # A full pack is worth exactly the range the driver entered, so a ~50 km trip
    # leaves roughly 1 - 50/350 of it.
    assert data["summary"]["estimated_arrival_soc_pct"] > 80.0


def test_ac_223_entered_range_actually_drives_the_projection(
        as_user, offline_routing, monkeypatch):
    as_user(ev_model_id=None, main_connector_type=None)
    use_stations(monkeypatch, [], {})

    def arrival(range_km):
        return client.post("/api/v1/route-plans", json=plan_body(
            origin=JAKARTA, destination=BOGOR, soc=50.0,
            vehicle={"usable_range_km": range_km})).json()["summary"]["estimated_arrival_soc_pct"]

    short, long = arrival(120.0), arrival(400.0)
    assert long > short, "a bigger entered range must project a healthier arrival"


def test_ac_223_entered_battery_kwh_is_honoured(as_user, offline_routing, monkeypatch):
    as_user(ev_model_id=None, main_connector_type=None)
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans", json=plan_body(
        origin=JAKARTA, destination=BOGOR, soc=80.0,
        vehicle={"usable_range_km": 400.0, "battery_kwh": 58.0, "name": "My EV"})).json()

    assert data["vehicle"]["battery_kwh"] == 58.0
    assert data["vehicle"]["name"] == "My EV"
    # 58 kWh over 400 km == 145 Wh/km.
    assert data["vehicle"]["efficiency_wh_per_km"] == pytest.approx(145.0, abs=0.5)


def test_ac_223_request_ev_model_id_overrides_the_profile(as_user, offline_routing, monkeypatch):
    """A client can name the vehicle per request instead of being pinned to the profile."""
    as_user(ev_model_id="wuling-air-ev")
    catalogue = {"hyundai-ioniq-5": dict(IONIQ_5),
                 "wuling-air-ev": {"id": "wuling-air-ev", "name": "Wuling Air EV",
                                   "battery_kwh": 26.7, "efficiency_wh_per_km": 115.0,
                                   "efficiency_source": "dataset", "max_dc_charge_kw": 30.0,
                                   "fast_charge_port": "Type 2"}}
    monkeypatch.setattr(evmodels, "get", lambda mid: catalogue.get(mid))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans", json=plan_body(
        origin=JAKARTA, destination=BOGOR, soc=72.0,
        ev_model_id="hyundai-ioniq-5")).json()

    assert data["vehicle"]["id"] == "hyundai-ioniq-5"
    assert data["vehicle"]["battery_kwh"] == 58.0


def test_ac_223_unknown_request_ev_model_id_is_404_not_a_silent_fallback(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: None)
    res = client.post("/api/v1/route-plans",
                      json=plan_body(origin=JAKARTA, destination=BOGOR, ev_model_id="no-such-ev"))
    assert res.status_code == 404
    assert "no-such-ev" in res.json()["detail"]


def test_ac_223_no_profile_and_no_range_still_explains_itself(as_user):
    """409 is now reserved for the case where ALL vehicle sources are absent."""
    as_user(ev_model_id=None, main_connector_type=None)
    res = client.post("/api/v1/route-plans", json=plan_body(soc=72.0))
    assert res.status_code == 409
    assert "vehicle range" in res.json()["detail"]


def test_ac_223_entered_range_must_be_valid(as_user):
    as_user(ev_model_id=None)
    res = client.post("/api/v1/route-plans",
                      json=plan_body(vehicle={"usable_range_km": 0.0}))
    assert res.status_code == 422
    assert ["body", "vehicle", "usable_range_km"] in _locs(res.json())


def test_ac_223_active_evaluation_accepts_an_entered_range_too(
        as_user, offline_routing, monkeypatch):
    as_user(ev_model_id=None, main_connector_type=None)
    use_stations(monkeypatch, [], {})

    res = client.post("/api/v1/route-plans/active/evaluate",
                      json=active_body(soc=90.0, vehicle={"usable_range_km": 400.0}))
    assert res.status_code == 200
    assert res.json()["vehicle"]["efficiency_source"] == "manual_range"


# --------------------------------------------------------------------------
# AC 2.2.4 -- "Given the driver has set charging preferences, when the route is
#              planned, then the system shows compatible SPKLU locations and
#              PRIORITIZES them based on the selected preference."
# --------------------------------------------------------------------------
@pytest.fixture
def slow_on_route_and_fast_off_route(monkeypatch):
    """A 22 kW station on the corridor and a 150 kW one ~3 km of detour away.

    Exactly the situation the audit found mishandled: with
    prefer_fast_charging=true the plan still recommended the 22 kW station.
    """
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    slow = make_station("st-slow-22kw", MIDPOINT[0], MIDPOINT[1], power_kw=22.0)
    fast = make_station("st-fast-150kw", MIDPOINT[0] - 0.12, MIDPOINT[1], power_kw=150.0)
    use_stations(monkeypatch, [slow, fast], {
        "st-slow-22kw": availability("st-slow-22kw", {"CCS2": 2}, power_by_type={"CCS2": 22.0}),
        "st-fast-150kw": availability("st-fast-150kw", {"CCS2": 2}, power_by_type={"CCS2": 150.0}),
    })


def _recommendation(**prefs) -> dict:
    return client.post("/api/v1/route-plans", json=plan_body(
        soc=45.0, preferences={"maximum_detour_km": 8.0, **prefs})).json()


def test_ac_224_prefer_fast_charging_changes_which_stop_is_recommended(
        as_user, offline_routing, slow_on_route_and_fast_off_route):
    """The whole AC: flipping the preference used to produce byte-identical plans."""
    as_user()

    fast_first = _recommendation(prefer_fast_charging=True)
    detour_first = _recommendation(prefer_fast_charging=False)

    assert fast_first["route_status"] == "charging_required"
    assert detour_first["route_status"] == "charging_required"

    assert fast_first["recommended_stop"]["station"]["id"] == "st-fast-150kw"
    assert detour_first["recommended_stop"]["station"]["id"] == "st-slow-22kw"

    # ... and the preferred one really is the faster/closer one respectively.
    assert fast_first["recommended_stop"]["best_available_power_kw"] == 150.0
    assert detour_first["recommended_stop"]["detour_km"] <= \
        fast_first["recommended_stop"]["detour_km"]


def test_ac_224_both_stations_are_still_shown_only_the_order_changes(
        as_user, offline_routing, slow_on_route_and_fast_off_route):
    """'shows compatible SPKLU locations AND prioritizes them' -- not filters them out."""
    as_user()
    for prefer in (True, False):
        data = _recommendation(prefer_fast_charging=prefer)
        shown = {s["station"]["id"] for s in
                 data["charging_stops"] + data["alternative_stops"]}
        assert shown == {"st-slow-22kw", "st-fast-150kw"}, prefer


def test_ac_224_route_type_changes_the_weighting(as_user, offline_routing,
                                                 slow_on_route_and_fast_off_route):
    """route_type was accepted, never read, and never validated."""
    as_user()
    fastest = _recommendation(route_type="fastest", prefer_fast_charging=True)
    shortest = _recommendation(route_type="shortest", prefer_fast_charging=True)

    assert fastest["assumptions"]["route_type"] == "fastest"
    assert shortest["assumptions"]["route_type"] == "shortest"
    assert (shortest["assumptions"]["rank_detour_weight"]
            > fastest["assumptions"]["rank_detour_weight"])


@pytest.mark.parametrize("sent", ["banana-split", "", "eco", 7, None])
def test_ac_224_unknown_route_type_degrades_to_the_default_and_says_so(
        as_user, offline_routing, monkeypatch, sent):
    """LOW-6: validate the value, but do not break a client over it.

    `route_type` shipped as a free-form `str` and the web client declares it
    `route_type?: string`, so narrowing it to an enum turned a request that used
    to work into a 422. An unrecognised value is applied as the DEFAULT instead,
    and `assumptions.route_type` reports what was actually used -- so the
    behaviour is still validated and still observable, without breaking a
    teammate's frontend on deploy.
    """
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    res = client.post("/api/v1/route-plans", json=plan_body(
        origin=JAKARTA, destination=BOGOR, preferences={"route_type": sent}))

    assert res.status_code == 200, res.text
    assert res.json()["assumptions"]["route_type"] == "fastest"


def test_ac_224_known_route_types_survive_case_and_padding(
        as_user, offline_routing, monkeypatch):
    """Degrading to the default must not swallow a value we DO understand."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans", json=plan_body(
        origin=JAKARTA, destination=BOGOR,
        preferences={"route_type": "  SHORTEST "})).json()
    assert data["assumptions"]["route_type"] == "shortest"


def test_ac_224_applied_preferences_are_echoed_in_assumptions(
        as_user, offline_routing, slow_on_route_and_fast_off_route):
    """The contract has to be observable, or 'applied' is unverifiable."""
    as_user()
    data = client.post("/api/v1/route-plans", json=plan_body(
        soc=45.0,
        preferences={"route_type": "fastest", "maximum_detour_km": 6.0,
                     "prefer_fast_charging": False})).json()

    a = data["assumptions"]
    assert a["prefer_fast_charging"] is False
    assert a["maximum_detour_km"] == 6.0
    assert a["rank_power_weight_km_per_kw"] == 0.0     # detour-only ranking


def test_ac_224_recommended_detour_reports_the_budget_it_was_ranked_against(
        as_user, offline_routing, slow_on_route_and_fast_off_route):
    as_user()
    data = _recommendation(prefer_fast_charging=True)
    stop = data["recommended_stop"]
    assert stop["detour_budget_km"] == 8.0
    assert stop["detour_within_budget"] is True
    assert stop["detour_km"] <= stop["detour_budget_km"]


def test_ac_224_road_detour_over_budget_is_flagged_not_hidden(
        as_user, monkeypatch, winding_routing):
    """The budget was a straight-line-only filter, so the ROAD detour could blow past it."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    winding_routing(MIDPOINT, 2.0)
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    stop = client.post("/api/v1/route-plans", json=plan_body(
        soc=45.0, preferences={"maximum_detour_km": 8.0})).json()["recommended_stop"]

    assert stop is not None, "the only viable stop is still offered"
    assert stop["detour_km"] > stop["detour_budget_km"]
    assert stop["detour_within_budget"] is False, "and the driver is told it busts their budget"


@pytest.fixture
def winding_routing(monkeypatch):
    """Legs leaving `stop_pos` are `factor` times more winding than the corridor."""
    def _install(stop_pos, factor: float):
        from api.services.routing_service import haversine_distance_km

        async def fake_get_route(self, origin, destination, waypoints=None):
            coords = [origin, *(waypoints or []), destination]
            total = 0.0
            for a, b in zip(coords, coords[1:]):
                straight = haversine_distance_km(a[0], a[1], b[0], b[1])
                total += straight * (factor if tuple(a) == tuple(stop_pos) else 1.0)
            return {
                "distance_km": round(total, 2),
                "duration_minutes": round((total / 50.0) * 60.0, 1),
                "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in coords]},
                "steps": [],
                "provider": "osrm",
            }

        monkeypatch.setattr(RoutingService, "get_route", fake_get_route)

    return _install


# --------------------------------------------------------------------------
# AC 2.2.6 -- "... then the system informs the driver and suggests selecting
#              another route, adjusting preferences, or charging before departure."
# --------------------------------------------------------------------------
NO_STATION_ACTIONS = {"choose_another_route", "adjust_preferences", "charge_before_departure"}


def test_ac_226_no_suitable_station_offers_all_three_remedies(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-busy", *MIDPOINT)],
                 {"st-busy": availability("st-busy", {"CCS2": 0}, total_by_type={"CCS2": 2})})

    warning = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()["warning"]

    assert warning["code"] == "no_suitable_station"
    assert warning["triggered"] is True
    assert set(warning["suggested_actions"]) == NO_STATION_ACTIONS
    # "selecting another route" was never suggested anywhere in the codebase.
    assert "another route" in warning["message"]


def test_ac_226_mid_route_no_station_also_advises_instead_of_only_stating_the_fact(
        as_user, offline_routing, monkeypatch):
    """The /active/evaluate variant carried NO advice at all."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans/active/evaluate",
                       json=active_body(soc=8.0)).json()

    assert data["route_status"] == "no_suitable_station"
    warning = data["warning"]
    assert set(warning["suggested_actions"]) == NO_STATION_ACTIONS
    assert "another route" in warning["message"]


def test_ac_226_suggested_actions_use_a_fixed_machine_readable_vocabulary(
        as_user, offline_routing, monkeypatch):
    """The client must be able to render buttons without string-matching prose."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    warning = client.post("/api/v1/route-plans", json=plan_body(soc=25.0)).json()["warning"]
    assert all(a.islower() and " " not in a for a in warning["suggested_actions"])


# --------------------------------------------------------------------------
# AC 2.4.1 -- "... displays the active route, next instruction, remaining
#              distance, ESTIMATED ARRIVAL TIME and projected arrival battery."
# --------------------------------------------------------------------------
def test_ac_241_plan_returns_an_arrival_TIME_not_only_a_duration(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    summary = client.post("/api/v1/route-plans",
                          json=plan_body(soc=95.0)).json()["summary"]

    computed = datetime.fromisoformat(summary["computed_at"])
    eta = datetime.fromisoformat(summary["estimated_arrival_at"])
    assert eta > computed
    assert eta - computed == timedelta(minutes=summary["duration_minutes"])


def test_ac_241_eta_includes_charging_time(as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()
    summary = data["summary"]
    charging_min = data["recommended_stop"]["estimated_charging_minutes"]
    assert charging_min > 0

    delta_min = (datetime.fromisoformat(summary["estimated_arrival_at"])
                 - datetime.fromisoformat(summary["computed_at"])).total_seconds() / 60.0
    assert delta_min == pytest.approx(summary["duration_minutes"], abs=0.2)
    assert summary["duration_minutes"] > charging_min


def test_ac_241_active_evaluation_also_returns_an_arrival_time(
        as_user, offline_routing, monkeypatch):
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    data = client.post("/api/v1/route-plans/active/evaluate",
                       json=active_body(soc=95.0)).json()

    delta_min = (datetime.fromisoformat(data["estimated_arrival_at"])
                 - datetime.fromisoformat(data["computed_at"])).total_seconds() / 60.0
    assert delta_min == pytest.approx(data["remaining_duration_minutes"], abs=0.2)


@pytest.fixture
def routing_with_real_steps(monkeypatch):
    """Routing that returns OSRM-shaped turn-by-turn steps across two legs."""
    from api.services.routing_service import haversine_distance_km

    async def fake_get_route(self, origin, destination, waypoints=None):
        coords = [origin, *(waypoints or []), destination]
        total = sum(haversine_distance_km(a[0], a[1], b[0], b[1])
                    for a, b in zip(coords, coords[1:]))
        steps = []
        for leg_index in range(len(coords) - 1):
            steps.append({"instruction": "depart", "name": "Jalan Medan Merdeka Utara",
                          "distance_m": 782.5, "duration_s": 45.6,
                          "location": [coords[leg_index][1], coords[leg_index][0]],
                          "leg_index": leg_index})
            steps.append({"instruction": "turn slight left", "name": "",
                          "distance_m": 120.0, "duration_s": 12.0,
                          "location": [coords[leg_index][1], coords[leg_index][0]],
                          "leg_index": leg_index})
        return {"distance_km": round(total, 2),
                "duration_minutes": round((total / 50.0) * 60.0, 1),
                "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in coords]},
                "steps": steps, "provider": "osrm"}

    monkeypatch.setattr(RoutingService, "get_route", fake_get_route)


def test_ac_241_next_instruction_is_typed_and_carries_a_leg_index(
        as_user, routing_with_real_steps, monkeypatch):
    """`steps` was an untyped list[dict] with no leg boundary, so a client could not
    tell which instruction is the charging stop."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch,
                 [make_station("st-free", *MIDPOINT, power_kw=150.0)],
                 {"st-free": availability("st-free", {"CCS2": 2}, power_by_type={"CCS2": 150.0})})

    data = client.post("/api/v1/route-plans", json=plan_body(soc=45.0)).json()
    steps = data["route"]["steps"]

    assert len(steps) > 1
    assert steps[0]["instruction"] == "depart"
    assert steps[0]["name"]
    assert set(steps[0]) >= {"instruction", "name", "distance_m", "duration_s",
                             "location", "leg_index"}
    # Two legs, because the plan routes via a charging stop.
    assert {s["leg_index"] for s in steps} == {0, 1}
    assert data["assumptions"]["turn_by_turn_available"] is True
    assert data["assumptions"]["routing_provider"] == "osrm"


def test_ac_241_degraded_routing_is_advertised_not_disguised(as_user, monkeypatch):
    """OSRM down: still 200, but the client can SEE that navigation degraded."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})
    monkeypatch.setattr(RoutingService, "_fetch_osrm_route",
                        lambda self, coords: (_ for _ in ()).throw(RuntimeError("upstream down")))

    data = client.post("/api/v1/route-plans", json=plan_body(soc=95.0)).json()

    assert data["assumptions"]["turn_by_turn_available"] is False
    assert data["assumptions"]["routing_provider"] == "haversine_fallback"
    assert len(data["route"]["steps"]) == 1


def test_ac_241_osrm_step_parsing_populates_leg_index(monkeypatch):
    """Unit-level: a real OSRM payload must survive into typed, leg-tagged steps."""
    import asyncio

    payload = {
        "code": "Ok",
        "routes": [{
            "distance": 150000.0, "duration": 7200.0,
            "geometry": {"type": "LineString", "coordinates": [[106.8, -6.2], [107.6, -6.9]]},
            "legs": [
                {"steps": [{"name": "Jalan Sudirman", "distance": 800.0, "duration": 50.0,
                            "maneuver": {"type": "depart", "location": [106.8, -6.2]}}]},
                {"steps": [{"name": "Tol Cipularang", "distance": 900.0, "duration": 40.0,
                            "maneuver": {"type": "turn", "modifier": "slight left",
                                         "location": [107.2, -6.5]}}]},
            ],
        }],
    }

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return payload

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp()

    import api.services.routing_service as rs
    monkeypatch.setattr(rs.httpx, "AsyncClient", _Client)

    result = asyncio.run(rs.RoutingService()._fetch_osrm_route(
        [(-6.2, 106.8), (-6.5, 107.2), (-6.9, 107.6)]))

    assert result["provider"] == "osrm"
    assert [s["leg_index"] for s in result["steps"]] == [0, 1]
    assert result["steps"][0]["instruction"] == "depart"
    assert result["steps"][1]["instruction"] == "turn slight left"
    assert result["steps"][1]["name"] == "Tol Cipularang"


def test_degenerate_provider_answer_is_discarded_not_published(monkeypatch):
    """A 0 km route between points 111 km apart used to be reported as healthy."""
    import asyncio

    payload = {
        "code": "Ok",
        "routes": [{
            "distance": 0.0, "duration": 0.0,
            "geometry": {"type": "LineString",
                         "coordinates": [[-160.003118, -0.368267], [-160.003118, -0.368267]]},
            "legs": [],
        }],
    }

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return payload

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp()

    import api.services.routing_service as rs
    monkeypatch.setattr(rs.httpx, "AsyncClient", _Client)

    assert asyncio.run(rs.RoutingService()._fetch_osrm_route([(0.0, -160.0), (1.0, -160.0)])) is None

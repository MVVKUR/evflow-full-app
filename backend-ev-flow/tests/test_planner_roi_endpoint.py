"""The ROI endpoint's job is to keep the planner's numbers and ours apart.

Every figure in the response is either something measured, something read from
the tariff the charging flow bills at, or something the planner assumed. Those
are worth wildly different amounts of trust, and once they are printed side by
side in a dashboard nothing distinguishes them again. So the endpoint labels
each one at the source, and these tests are what keep the labels truthful.
"""
import pytest
from fastapi.testclient import TestClient

from api import planner_repo
from api.main import app, require_planner

CELL = {
    "cell_id": "JBDTBK_00001", "kota": "Bekasi", "score": 0.83,
    "population": 2729.0, "poi_total": 6, "station_count": 0,
    "nearest_station_m": 9292, "stations_2km": 0,
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(planner_repo, "get_cell",
                        lambda cell_id, *a, **k: CELL if cell_id == CELL["cell_id"] else None)
    app.dependency_overrides[require_planner] = lambda: {"id": "u", "account_type": "business_planner"}
    yield TestClient(app)
    app.dependency_overrides.pop(require_planner, None)


def _body(**over):
    body = {"cell_id": CELL["cell_id"], "capex_per_connector_idr": 250_000_000,
            "opex_monthly_idr": 15_000_000, "utilisation_target": 0.2}
    body.update(over)
    return body


def test_planner_supplied_values_are_labelled_as_theirs(client):
    r = client.post("/api/v1/planner/roi", json=_body(connectors=4))
    src = r.json()["input_sources"]
    assert src["connectors"] == "planner"
    assert src["capex_per_connector_idr"] == "planner"
    assert src["opex_monthly_idr"] == "planner"
    assert src["utilisation_target"] == "planner"


def test_values_the_endpoint_chose_are_not_passed_off_as_the_planners(client):
    # connectors was not sent, so calling it "planner" would credit them with a
    # decision they never made and never had a chance to disagree with.
    r = client.post("/api/v1/planner/roi", json=_body())
    src = r.json()["input_sources"]
    assert src["connectors"] == "default"
    assert src["power_kw"] == "default"
    assert src["energy_per_session_kwh"] == "default"


def test_the_tariff_is_credited_to_the_charging_configuration(client):
    # It is neither a guess nor the planner's: it is the price the product
    # really bills, which is the whole reason it is trustworthy.
    r = client.post("/api/v1/planner/roi", json=_body())
    assert r.json()["input_sources"]["tariff_idr_per_kwh"] == "charging tariff configuration"


def test_an_overridden_tariff_becomes_the_planners_again(client):
    r = client.post("/api/v1/planner/roi", json=_body(tariff_idr_per_kwh=3000))
    assert r.json()["input_sources"]["tariff_idr_per_kwh"] == "planner"
    assert r.json()["inputs"]["tariff_idr_per_kwh"] == 3000


def test_the_demand_basis_says_the_number_is_an_assumption(client):
    body = client.post("/api/v1/planner/roi", json=_body()).json()["demand_basis"]
    assert "assumption" in body.lower()
    assert "not a forecast" in body.lower()
    assert "simulation" in body.lower()


def test_zero_energy_cost_warns_that_the_payback_is_too_short(client):
    note = client.post("/api/v1/planner/roi", json=_body()).json()["cost_basis"]
    assert "too short" in note
    # The prose must survive the thousands-separator formatting applied to the
    # other branch; a blanket comma swap turns every clause break into a stop.
    assert ", so this projection" in note


def test_a_priced_energy_cost_reports_the_spread(client):
    note = client.post("/api/v1/planner/roi",
                       json=_body(energy_cost_idr_per_kwh=1450)).json()["cost_basis"]
    assert "1.450" in note and "spread" in note
    assert "1,450" not in note


def test_buying_energy_lengthens_the_payback(client):
    free = client.post("/api/v1/planner/roi", json=_body()).json()
    paid = client.post("/api/v1/planner/roi", json=_body(energy_cost_idr_per_kwh=1450)).json()
    assert paid["payback_years"] > free["payback_years"]
    assert paid["revenue_monthly_idr"] == free["revenue_monthly_idr"]


def test_an_unprofitable_site_returns_no_payback_rather_than_a_negative_one(client):
    r = client.post("/api/v1/planner/roi", json=_body(energy_cost_idr_per_kwh=3000)).json()
    assert r["payback_years"] is None
    assert r["breaks_even"] is False
    assert r["net_at_horizon_idr"] < 0


def test_demand_beyond_the_hardware_is_refused_with_the_ceiling_named(client):
    r = client.post("/api/v1/planner/roi",
                    json=_body(utilisation_target=None, sessions_per_day=500, connectors=2))
    assert r.status_code == 422
    assert "capacity" in r.json()["detail"]


def test_two_demand_figures_are_refused(client):
    r = client.post("/api/v1/planner/roi",
                    json=_body(sessions_per_day=10, utilisation_target=0.2))
    assert r.status_code == 422


def test_no_demand_figure_is_refused(client):
    r = client.post("/api/v1/planner/roi", json=_body(utilisation_target=None))
    assert r.status_code == 422


def test_an_unknown_cell_is_404_not_a_projection_of_nothing(client):
    r = client.post("/api/v1/planner/roi", json=_body(cell_id="NOPE"))
    assert r.status_code == 404


def test_the_cell_is_described_so_the_assumption_can_be_sanity_checked(client):
    # A planner assuming heavy demand next to a cell with 2,729 people and no
    # nearby station should be able to see that from the same response.
    r = client.post("/api/v1/planner/roi", json=_body()).json()
    assert r["population"] == CELL["population"]
    assert r["nearest_station_m"] == CELL["nearest_station_m"]
    assert r["station_count"] == CELL["station_count"]

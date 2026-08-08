"""A destination outside the served area must not be planned as if it were
inside it.

The catalogue only carries Jabodetabek stations, so a Jakarta -> Bandung trip
would be answered with a Jabodetabek stop and `completes_trip: True` -- the
physics work out, but the moment the driver leaves the area the app shows no
stations at all. Promising a trip we cannot support past the boundary is worse
than declining it: the driver finds out at 20% SoC in a city we have no data
for. This routes such trips into the existing "no suitable charging station"
answer (AC 2.2.6) with a reason that names the real cause.
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import service_area

client = TestClient(app)

JAKARTA = {"latitude": -6.2088, "longitude": 106.8456}
BOGOR = {"latitude": -6.5950, "longitude": 106.8166}
BANDUNG = {"latitude": -6.9147, "longitude": 107.6098}


@pytest.fixture
def area_enforced():
    prev = service_area.STATION_AREA_ENFORCED
    service_area.STATION_AREA_ENFORCED = True
    yield
    service_area.STATION_AREA_ENFORCED = prev


def test_endpoints_outside_the_area_are_detected(area_enforced):
    from api.main import _route_endpoints_outside_area

    assert _route_endpoints_outside_area(
        (JAKARTA["latitude"], JAKARTA["longitude"]),
        (BOGOR["latitude"], BOGOR["longitude"])) == []

    # Destination outside: named so the driver learns which end is the problem.
    assert _route_endpoints_outside_area(
        (JAKARTA["latitude"], JAKARTA["longitude"]),
        (BANDUNG["latitude"], BANDUNG["longitude"])) == ["destination"]

    # Origin outside: the driver is already somewhere we cannot help.
    assert _route_endpoints_outside_area(
        (BANDUNG["latitude"], BANDUNG["longitude"]),
        (JAKARTA["latitude"], JAKARTA["longitude"])) == ["origin"]

    assert _route_endpoints_outside_area(
        (BANDUNG["latitude"], BANDUNG["longitude"]),
        (BANDUNG["latitude"], BANDUNG["longitude"])) == ["origin", "destination"]


def test_detection_is_disabled_with_the_area_filter(area_enforced):
    from api.main import _route_endpoints_outside_area

    service_area.STATION_AREA_ENFORCED = False
    # A deployment serving everywhere must not decline anything.
    assert _route_endpoints_outside_area(
        (BANDUNG["latitude"], BANDUNG["longitude"]),
        (BANDUNG["latitude"], BANDUNG["longitude"])) == []


def test_out_of_area_message_names_the_endpoint_and_the_served_area():
    from api.main import _out_of_area_message

    dest = _out_of_area_message(["destination"])
    assert "destination" in dest.lower()
    assert "jabodetabek" in dest.lower()

    both = _out_of_area_message(["origin", "destination"])
    assert "origin" in both.lower() and "destination" in both.lower()

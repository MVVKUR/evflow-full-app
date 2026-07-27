"""The configured route service area (AC 2.2.1 / AC 2.2.2).

AC 2.2.1 says a route may only be planned "within the configured route service
area"; AC 2.2.2 says an origin or destination outside it is INVALID INPUT and
must be rejected with a field-specific error, with no route generated.

Before this module the only bounded region in the codebase was
``api.routing.BBOX`` -- the extent OSMnx downloads the road graph for. That is a
graph-download extent, not a product boundary: it is never consulted by
``POST /api/v1/route-plans`` and it does not even contain Bogor, the canonical
demo destination. So the planning endpoints accepted every coordinate on Earth
and cheerfully "simulated" a Sydney-to-Sydney trip 5,500 km outside the served
data.

This module is the single source of truth for that boundary. It is a bounding
box because a rectangle is the cheapest shape that can be expressed entirely in
environment variables, so a deployment can widen or narrow it without a code
change.

Why the DEFAULT is the whole Indonesian archipelago
---------------------------------------------------
The product narrative is Jabodetabek-focused, but the dataset this repository
actually seeds is national: 2,900+ PLN/OCM/OSM stations reaching Sumatra,
Kalimantan, Sulawesi, Bali and Papua. A Jabodetabek-sized default box left
roughly half of the shipped stations un-routable while ``/api/v1/stations``,
``/api/v1/stations/nearby`` and ``/api/v1/geocoding/search`` went on offering
them, so the destination picker suggested places the planner then refused with
a 422 -- the app contradicting itself.

The honest default is therefore "serve what you ship": the box below covers the
seeded dataset with a margin, and is named for what it is. Concretely it reaches
Sabang and the tip of Aceh in the north-west, Merauke in the east, and Rote and
Sabu in the south -- and, on the way, Bandung, Cirebon, Surabaya, Denpasar and
Medan, all of which have seeded stations. AC 2.2.2 still bites: Sydney, Perth and
the Pacific are rejected with a field-specific 422 and no route.

Known and accepted imprecision: a RECTANGLE over the archipelago also contains
some neighbouring territory -- Singapore, peninsular Malaysia, Brunei, Timor-Leste
and part of Papua New Guinea. Those are accepted as origins/destinations even
though no station is seeded there. That is the deliberate trade for a boundary
that is four numbers in the environment; the alternative is a polygon nobody can
configure without a code change. The consequence is a plan with no reachable
charging stop, which the response already reports honestly as
``route_status = 'no_suitable_station'`` with a warning -- not a silently wrong
route. Tighten this only by replacing the shape, not by shrinking the box below
the data.

Those place names and the four numbers below are checked against each other by
``test_medium5_docstring_claims_match_the_constants``: an earlier revision of
this file claimed coverage "out to Bandung/Cirebon" while its own EAST edge
(108.30) cut Cirebon (108.55) off. Prose and constants must be edited together.

A deployment that genuinely only serves Jabodetabek narrows the box via the
``ROUTE_SERVICE_AREA_*`` variables. That stays safe because discovery agrees
with planning at runtime rather than by coincidence: ``Station`` and
``GeocodingItem`` both carry ``in_service_area``, computed from THESE constants,
and ``/api/v1/geocoding/search`` can filter on it. Narrow the box and the picker
labels or drops the destinations the planner would refuse.

Mid-journey is NOT planning
---------------------------
This boundary is a PLANNING-TIME gate. ``POST /api/v1/route-plans`` rejects an
out-of-area origin/destination outright (AC 2.2.2). The active-route evaluation
endpoint deliberately does NOT: AC 2.1.1 and AC 2.4.2 exist to keep warning a
driver who is already travelling, so a driver who crosses the boundary
mid-trip keeps getting battery re-evaluations and gets the condition back as an
advisory instead of a 422.
"""
from __future__ import annotations

import os
from typing import Dict, Iterable, List, Sequence, Tuple


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


# Human-readable name, echoed in the API response so the contract is observable.
SERVICE_AREA_NAME = os.getenv("ROUTE_SERVICE_AREA_NAME", "Indonesia (national SPKLU coverage)")

# Edges of the served region, in WGS84 degrees.
#
# These four numbers and the docstring above MUST agree. They currently describe
# the Indonesian archipelago: Rote/Sabu in the south, Sabang in the north, west
# of Aceh, east of Merauke -- a superset of every seeded station (observed
# extent: latitude -10.21..5.88, longitude 95.32..140.70) with a small margin.
SERVICE_AREA_SOUTH = _env_float("ROUTE_SERVICE_AREA_SOUTH", -11.20)
SERVICE_AREA_WEST = _env_float("ROUTE_SERVICE_AREA_WEST", 94.60)
SERVICE_AREA_NORTH = _env_float("ROUTE_SERVICE_AREA_NORTH", 6.30)
SERVICE_AREA_EAST = _env_float("ROUTE_SERVICE_AREA_EAST", 141.30)

# Escape hatch for a deployment that genuinely serves everywhere. Enforcement is
# ON by default: silently planning a route through data we do not have is worse
# than a 422 that names the offending field.
SERVICE_AREA_ENFORCED = _env_bool("ROUTE_SERVICE_AREA_ENFORCED", True)


def contains(latitude: float, longitude: float) -> bool:
    """True when the point lies inside the configured route service area.

    Reads the module globals on every call (not captured defaults) so tests and
    runtime reconfiguration can monkeypatch a single edge.
    """
    if not SERVICE_AREA_ENFORCED:
        return True
    return (
        SERVICE_AREA_SOUTH <= float(latitude) <= SERVICE_AREA_NORTH
        and SERVICE_AREA_WEST <= float(longitude) <= SERVICE_AREA_EAST
    )


def outside_fields(named_points: Sequence[Tuple[str, float, float]]) -> List[str]:
    """Names of the ``(name, latitude, longitude)`` triples that fall outside.

    Used by the active-route evaluation, which reports the condition instead of
    refusing to answer (AC 2.1.1 / AC 2.4.2).
    """
    return [name for name, lat, lon in named_points if not contains(lat, lon)]


def describe() -> Dict[str, object]:
    """The area as a plain dict, for echoing back in ``assumptions``."""
    return {
        "name": SERVICE_AREA_NAME,
        "south": SERVICE_AREA_SOUTH,
        "west": SERVICE_AREA_WEST,
        "north": SERVICE_AREA_NORTH,
        "east": SERVICE_AREA_EAST,
        "enforced": SERVICE_AREA_ENFORCED,
    }


def rejection_message() -> str:
    """Why the point was rejected, including the bounds the caller must respect."""
    return (
        f"outside the configured route service area '{SERVICE_AREA_NAME}' "
        f"(latitude {SERVICE_AREA_SOUTH} to {SERVICE_AREA_NORTH}, "
        f"longitude {SERVICE_AREA_WEST} to {SERVICE_AREA_EAST})"
    )


def advisory_message(fields: Iterable[str]) -> str:
    """Mid-journey wording: state the fact, do not pretend the request was invalid.

    The planning endpoints reject; this endpoint keeps evaluating and says so,
    because a driver who has left the served area still needs battery warnings.
    """
    listed = " and ".join(f.replace("_", " ") for f in fields) or "this route"
    return (
        f"Your {listed} is {rejection_message()}. Battery warnings continue, but "
        f"charging-station coverage and travel-time estimates are unreliable here."
    )

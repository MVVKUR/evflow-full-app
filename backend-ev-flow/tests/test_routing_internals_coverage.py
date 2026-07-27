"""Routing internals: graph loading, Dijkstra plumbing, provider fallback,
candidate ranking, connector normalisation and the service-area gate.

Everything here is offline. The road graph is a hand-built 5-node GraphML in a
tmp_path; OSRM is either a closed port (127.0.0.1:9) or an injected fake client;
the station repository is monkeypatched. Nothing sleeps and nothing dials out --
see the module-wide `_never_spawn_curl` guard, which stops the routing service's
curl fallback from turning a fake-client mistake into a real outbound request.

Scope (the gaps the Epic 2 suites did not reach):
  * api/routing.py            -- GraphUnavailable, the OSMnx build branch,
                                 nearest_node, unreachable/degenerate routes,
                                 station snapping + nearest_station_route.
  * api/services/routing_service.py -- the OSRM(httpx) -> OSRM(curl) -> local
                                 Dijkstra chain, the RouteUnavailable refusal at
                                 the end of it, and the distance_basis each
                                 provider yields.
  * api/services/stop_ranker.py     -- candidate fetching fallbacks, empty and
                                 fully-filtered candidate sets, ranking ties.
  * api/services/connector_compat.py -- every normalisation-map entry, every
                                 substring fallback, unknown vocabulary.
  * api/services/service_area.py    -- malformed env values, enforcement toggle.
"""
from __future__ import annotations

import asyncio
import sys
import types

import pytest

from tests.conftest import requires_db

nx = pytest.importorskip("networkx")

from api import routing  # noqa: E402
from api.services import connector_compat, service_area  # noqa: E402
from api.services import routing_service as rs_module  # noqa: E402
from api.services import stop_ranker as sr_module  # noqa: E402
from api.services.energy_estimator import EnergyEstimator  # noqa: E402
from api.services.routing_service import RoutingService, haversine_distance_km  # noqa: E402
from api.services.station_availability import StationConnectorAvailability  # noqa: E402
from api.services.stop_ranker import StopRanker  # noqa: E402

# ---------------------------------------------------------------------------
# The tiny road network used by every graph-backed test.
#
#   node 1 ---- 2 ---- 3 ---- 4          (1 km / 60 s per hop, bidirectional)
#   node 5                                (isolated: on the map, off the road)
#
# Node 5 sits ~110 m from node 1, so it is the CROW-FLIES nearest node to the
# origin while being unreachable by road. That is what separates "nearest" from
# "nearest by road" in the assertions below.
# ---------------------------------------------------------------------------
NODE_XY = {
    1: (106.80, -6.20),
    2: (106.81, -6.20),
    3: (106.82, -6.20),
    4: (106.83, -6.20),
    5: (106.8005, -6.2010),
}
ORIGIN_NEAR_NODE_1 = (-6.2000, 106.8003)


def _write_tiny_graph(tmp_path, *, include_isolated_node: bool = True):
    g = nx.MultiDiGraph()
    for n, (x, y) in NODE_XY.items():
        if n == 5 and not include_isolated_node:
            continue
        g.add_node(n, x=x, y=y)
    for u, v in [(1, 2), (2, 3), (3, 4)]:
        g.add_edge(u, v, length=1000.0, travel_time=60.0)
        g.add_edge(v, u, length=1000.0, travel_time=60.0)
    path = tmp_path / "tiny.graphml"
    nx.write_graphml(g, path)
    return path


@pytest.fixture
def tiny_graph(tmp_path, monkeypatch):
    """Point the routing module at the tiny graph and reset its module cache.

    `api.routing` caches the adjacency map, the node arrays and the station-snap
    result in module globals, so the cache is dropped on the way IN and on the
    way OUT -- otherwise a graph from one test leaks into the next.
    """
    path = _write_tiny_graph(tmp_path)
    monkeypatch.setattr(routing, "GRAPH_PATH", path)
    routing.reload()
    yield path
    routing.reload()


@pytest.fixture
def no_graph(tmp_path, monkeypatch):
    """A GRAPH_PATH that does not exist, with the cache cleared."""
    monkeypatch.setattr(routing, "GRAPH_PATH", tmp_path / "missing" / "nope.graphml")
    routing.reload()
    yield
    routing.reload()


# ===========================================================================
# api/routing.py -- graph loading and GraphUnavailable
# ===========================================================================
@pytest.mark.unit
def test_graph_unavailable_when_no_file_and_no_builder(no_graph, monkeypatch):
    """No cached GraphML and no osmnx to build one -> a named, actionable error."""
    monkeypatch.setitem(sys.modules, "osmnx", None)  # force `import osmnx` to fail
    with pytest.raises(routing.GraphUnavailable) as exc:
        routing.nearest_node(-6.20, 106.80)
    assert "build_road_graph" in str(exc.value)
    assert routing._ADJ is None  # a failed load must not half-populate the cache


@pytest.mark.unit
def test_graph_with_no_nodes_is_rejected(tmp_path, monkeypatch):
    """An empty GraphML loads fine but is useless; it must not snap to nothing."""
    empty = tmp_path / "empty.graphml"
    nx.write_graphml(nx.MultiDiGraph(), empty)
    monkeypatch.setattr(routing, "GRAPH_PATH", empty)
    routing.reload()
    try:
        with pytest.raises(routing.GraphUnavailable, match="no nodes"):
            routing.nearest_node(-6.20, 106.80)
    finally:
        routing.reload()


def _fake_osmnx(monkeypatch, tmp_path, *, legacy_signature: bool):
    """An `osmnx` stand-in that records how it was called and saves a real file."""
    calls = {"bbox": None, "speeds": 0, "travel_times": 0, "saved": None}

    def graph_from_bbox(*args, **kwargs):
        if legacy_signature and "bbox" in kwargs:
            raise TypeError("graph_from_bbox() got an unexpected keyword argument 'bbox'")
        calls["bbox"] = kwargs
        g = nx.MultiDiGraph()
        for n, (x, y) in list(NODE_XY.items())[:2]:
            g.add_node(n, x=x, y=y)
        g.add_edge(1, 2, length=1000.0)
        return g

    def add_edge_speeds(g):
        calls["speeds"] += 1
        return g

    def add_edge_travel_times(g):
        calls["travel_times"] += 1
        return g

    def save_graphml(g, path):
        calls["saved"] = path
        nx.write_graphml(g, path)

    mod = types.SimpleNamespace(
        graph_from_bbox=graph_from_bbox,
        add_edge_speeds=add_edge_speeds,
        add_edge_travel_times=add_edge_travel_times,
        save_graphml=save_graphml,
    )
    monkeypatch.setitem(sys.modules, "osmnx", mod)
    return calls


@pytest.mark.unit
def test_graph_is_built_and_cached_when_the_file_is_missing(tmp_path, monkeypatch):
    """The build branch: download, add speeds/travel times, persist, then use it."""
    target = tmp_path / "built" / "jakarta.graphml"
    monkeypatch.setattr(routing, "GRAPH_PATH", target)
    routing.reload()
    calls = _fake_osmnx(monkeypatch, tmp_path, legacy_signature=False)
    try:
        node, km = routing.nearest_node(-6.20, 106.8005)
        assert str(node) == "1"
        assert km == pytest.approx(0.055, abs=0.05)
        # the modern (osmnx >= 2) signature is tried first, with OUR bbox
        assert calls["bbox"]["network_type"] == "drive"
        assert calls["bbox"]["bbox"] == (
            routing.BBOX["west"], routing.BBOX["south"],
            routing.BBOX["east"], routing.BBOX["north"],
        )
        assert calls["speeds"] == 1 and calls["travel_times"] == 1
        # and it is written to disk so the next process never rebuilds it
        assert target.exists() and calls["saved"] == target
    finally:
        routing.reload()


@pytest.mark.unit
def test_graph_build_falls_back_to_the_osmnx_1x_signature(tmp_path, monkeypatch):
    """osmnx 1.x has no `bbox=` kwarg; the TypeError must be retried, not raised."""
    target = tmp_path / "built1x" / "jakarta.graphml"
    monkeypatch.setattr(routing, "GRAPH_PATH", target)
    routing.reload()
    calls = _fake_osmnx(monkeypatch, tmp_path, legacy_signature=True)
    try:
        routing.nearest_node(-6.20, 106.80)
        assert calls["bbox"]["north"] == routing.BBOX["north"]
        assert calls["bbox"]["south"] == routing.BBOX["south"]
        assert calls["bbox"]["east"] == routing.BBOX["east"]
        assert calls["bbox"]["west"] == routing.BBOX["west"]
        assert target.exists()
    finally:
        routing.reload()


@pytest.mark.unit
def test_edges_without_travel_time_get_a_default_speed_estimate():
    """GraphML edges may carry only `length`; the time must be derived, not zero."""
    g = nx.MultiDiGraph()
    g.add_node("a", x=106.80, y=-6.20)
    g.add_node("b", x=106.81, y=-6.20)
    g.add_edge("a", "b", length=2000.0)            # no travel_time
    g.add_edge("b", "a", length=2000.0, travel_time="120.0")  # GraphML strings

    adj, nodes = routing._build_adjacency(g)
    assert nodes["a"] == (-6.20, 106.80)           # (lat, lon), coerced to float
    (_, length, derived, geom), = adj["a"]
    assert length == 2000.0
    assert derived == pytest.approx(2.0 / routing.DEFAULT_SPEED_KMH * 3600.0)
    assert derived > 0                              # never silently zero
    assert geom is None                             # no geometry attribute on this edge
    (_, _, stated, _), = adj["b"]
    assert stated == 120.0                          # the stated value wins


@pytest.mark.unit
def test_edge_geometry_is_parsed_off_the_graphml_wkt_string():
    """OSMnx writes edge geometry as a WKT LINESTRING; it must survive the round trip."""
    g = nx.MultiDiGraph()
    g.add_node("a", x=106.80, y=-6.20)
    g.add_node("b", x=106.81, y=-6.20)
    g.add_edge("a", "b", length=1200.0, travel_time=90.0,
               geometry="LINESTRING (106.80 -6.20, 106.805 -6.2005, 106.81 -6.20)")

    adj, _ = routing._build_adjacency(g)
    (_, _, _, geom), = adj["a"]
    assert geom == [[106.80, -6.20], [106.805, -6.2005], [106.81, -6.20]]


@pytest.mark.unit
def test_edge_geometry_is_read_off_a_shapely_style_object():
    """In-memory OSMnx graphs carry shapely LineStrings, not WKT strings."""
    shapely_like = types.SimpleNamespace(coords=[(106.80, -6.20), (106.81, -6.2005)])
    assert routing._parse_edge_geometry(shapely_like) == [[106.80, -6.20], [106.81, -6.2005]]


@pytest.mark.unit
def test_edge_geometry_already_given_as_coordinate_pairs_is_coerced_to_float():
    assert routing._parse_edge_geometry([("106.80", "-6.20"), (106.81, -6.20)]) == [
        [106.80, -6.20], [106.81, -6.20]]


@pytest.mark.unit
@pytest.mark.parametrize("value", [
    None,
    "",
    "not a linestring",
    "LINESTRING (106.80)",            # a pair with only one ordinate
    "LINESTRING (106.80 -6.20)",      # a single point is not a line
    "LINESTRING (a b, c d)",          # non-numeric ordinates
    123,                              # not a string at all
    [(106.80,), (106.81,)],           # pairs missing an ordinate
    [("east", "south")],              # non-numeric pairs
    [1, 2],                           # scalars where pairs were expected
])
def test_unusable_edge_geometry_degrades_to_none_rather_than_exploding(value):
    """A malformed geometry attribute must not take the whole graph load down."""
    assert routing._parse_edge_geometry(value) is None


# ===========================================================================
# api/routing.py -- nearest node / shortest path
# ===========================================================================
@pytest.mark.unit
def test_nearest_node_returns_the_closest_node_and_its_distance(tiny_graph):
    node, km = routing.nearest_node(-6.2010, 106.8004)
    assert str(node) == "5"                 # the isolated node really is nearest
    assert 0.0 < km < 0.05

    node, km = routing.nearest_node(-6.20, 106.8299)
    assert str(node) == "4"
    assert km < 0.2


@pytest.mark.unit
def test_shortest_path_traverses_the_whole_chain(tiny_graph):
    r = routing.shortest_path(-6.20, 106.8003, -6.20, 106.8297)
    assert r["node_count"] == 4                       # 1 -> 2 -> 3 -> 4
    assert r["distance_m"] == 3000.0
    assert r["duration_s"] == 180.0
    assert r["weight"] == "length"
    assert r["origin"]["snapped_node"] == "1"
    assert r["destination"]["snapped_node"] == "4"
    assert r["origin"]["snap_distance_km"] < 0.1
    coords = r["geometry"]["coordinates"]
    assert r["geometry"]["type"] == "LineString"
    # GeoJSON order is [lon, lat] -- getting this backwards puts Jakarta in Antarctica
    assert coords[0] == [106.80, -6.20]
    assert coords[-1] == [106.83, -6.20]


@pytest.mark.unit
def test_shortest_path_by_travel_time_reports_the_time_basis(tiny_graph):
    r = routing.shortest_path(-6.20, 106.8003, -6.20, 106.8297, weight="travel_time")
    assert r["weight"] == "travel_time"
    assert r["duration_s"] == 180.0
    assert r["distance_m"] == 3000.0    # both metrics are summed, not just the minimised one


@pytest.mark.unit
def test_shortest_path_is_none_when_the_destination_is_off_the_road_network(tiny_graph):
    """Node 5 is on the map but has no edges: there is no drivable route to it."""
    assert routing.shortest_path(-6.20, 106.8003, -6.2010, 106.8005) is None


@pytest.mark.unit
def test_zero_length_route_still_yields_a_two_point_linestring(tiny_graph):
    """Origin and destination snapping to the same node must not emit a 1-point
    LineString -- that is invalid GeoJSON and every map client rejects it."""
    r = routing.shortest_path(-6.20, 106.8001, -6.2001, 106.8002)
    assert r["origin"]["snapped_node"] == r["destination"]["snapped_node"]
    assert r["node_count"] == 1
    assert r["distance_m"] == 0.0
    assert r["duration_s"] == 0.0
    coords = r["geometry"]["coordinates"]
    assert len(coords) == 2 and coords[0] == coords[1]


# ===========================================================================
# api/routing.py -- station snapping and nearest_station_route
# ===========================================================================
STATION_IDS = ["st-offroad", "st-mid", "st-end"]
STATION_LATS = [-6.2010, -6.20, -6.20]
STATION_LONS = [106.8005, 106.8102, 106.8301]


@pytest.mark.unit
def test_nearest_station_route_ignores_the_crow_flies_nearest_when_it_is_unreachable(tiny_graph):
    """st-offroad is 100 m away in a straight line but has no road to it."""
    r = routing.nearest_station_route(
        ORIGIN_NEAR_NODE_1[0], ORIGIN_NEAR_NODE_1[1],
        STATION_IDS, STATION_LATS, STATION_LONS)
    assert r["station_id"] == "st-mid"
    assert r["candidates_considered"] == 2      # st-offroad snapped to the isolated node
    assert r["within_range"] is True            # no max_range_km given
    route = r["route"]
    assert route["distance_m"] == 1000.0
    assert route["node_count"] == 2
    assert route["destination"]["station_id"] == "st-mid"
    assert route["destination"]["snapped_node"] == "2"
    assert route["destination"]["snap_distance_km"] < 0.1
    assert route["geometry"]["coordinates"] == [[106.80, -6.20], [106.81, -6.20]]


@pytest.mark.unit
@pytest.mark.parametrize("max_range_km,expected", [
    (0.5, False),   # nearest charger is 1 km away by road -> out of reach
    (1.0, True),    # exactly at the limit counts as reachable
    (25.0, True),
    (None, True),
])
def test_nearest_station_route_within_range_flag(tiny_graph, max_range_km, expected):
    r = routing.nearest_station_route(
        ORIGIN_NEAR_NODE_1[0], ORIGIN_NEAR_NODE_1[1],
        STATION_IDS, STATION_LATS, STATION_LONS, max_range_km=max_range_km)
    assert r["within_range"] is expected
    assert r["route"]["distance_m"] == 1000.0   # the flag never changes the choice


@pytest.mark.unit
def test_nearest_station_route_by_travel_time_may_pick_a_different_station(tiny_graph):
    r = routing.nearest_station_route(
        ORIGIN_NEAR_NODE_1[0], ORIGIN_NEAR_NODE_1[1],
        STATION_IDS, STATION_LATS, STATION_LONS, weight="travel_time")
    assert r["route"]["weight"] == "travel_time"
    assert r["route"]["duration_s"] == 60.0
    assert r["station_id"] == "st-mid"


@pytest.mark.unit
def test_a_station_on_the_origin_node_still_yields_a_two_point_linestring(tiny_graph):
    """Zero-length route: a 1-point LineString is invalid GeoJSON."""
    r = routing.nearest_station_route(
        -6.2000, 106.8001, ["st-at-origin"], [-6.2000], [106.8000])
    assert r["station_id"] == "st-at-origin"
    assert r["route"]["node_count"] == 1
    assert r["route"]["distance_m"] == 0.0
    assert r["route"]["duration_s"] == 0.0
    coords = r["route"]["geometry"]["coordinates"]
    assert len(coords) == 2 and coords[0] == coords[1] == [106.80, -6.20]
    assert r["within_range"] is True


@pytest.mark.unit
def test_nearest_station_route_is_none_when_nothing_is_reachable_by_road(tiny_graph):
    assert routing.nearest_station_route(
        ORIGIN_NEAR_NODE_1[0], ORIGIN_NEAR_NODE_1[1],
        ["st-offroad"], [-6.2010], [106.8005]) is None


@pytest.mark.unit
def test_station_snapping_is_cached_across_calls(tiny_graph):
    first = routing._snap_stations(STATION_IDS, STATION_LATS, STATION_LONS)
    assert [str(n) for n in first] == ["5", "2", "4"]
    second = routing._snap_stations(STATION_IDS, STATION_LATS, STATION_LONS)
    assert second is first                       # same object: the cache was reused
    routing.reload()
    assert routing._STATION_SNAP is None         # and reload() drops it


@pytest.mark.unit
@pytest.mark.xfail(
    strict=True,
    reason="BUG: _snap_stations keys its cache on (len, first id, last id) only. "
           "Two station sets with the same size and the same first/last id return "
           "the FIRST set's snapped nodes, so a moved or replaced station is routed "
           "to the wrong road node until the process restarts.",
)
def test_snap_cache_must_not_serve_stale_nodes_for_relocated_stations(tiny_graph):
    ids = ["a", "b", "c"]
    first = list(routing._snap_stations(ids, [-6.20, -6.20, -6.20], [106.80, 106.81, 106.83]))
    assert [str(n) for n in first] == ["1", "2", "4"]
    # 'b' has moved to the far end of the corridor; same ids, same count.
    second = list(routing._snap_stations(ids, [-6.20, -6.20, -6.20], [106.80, 106.83, 106.83]))
    assert [str(n) for n in second] == ["1", "4", "4"]


# ===========================================================================
# api/routing.py -- haversine helpers
# ===========================================================================
@pytest.mark.unit
def test_haversine_helpers_agree_and_are_metrically_sane():
    from api.data import haversine_km

    jakarta = (-6.2088, 106.8456)
    bandung = (-6.9175, 107.6191)

    vec = float(haversine_km(*jakarta, *bandung))
    scalar = haversine_distance_km(*jakarta, *bandung)
    assert vec == pytest.approx(118.0, abs=3.0)         # real-world ~119 km
    assert scalar == pytest.approx(vec, rel=1e-4)       # 6371.0088 vs 6371.0 radius

    # identity, symmetry
    assert float(haversine_km(*jakarta, *jakarta)) == pytest.approx(0.0, abs=1e-9)
    assert haversine_distance_km(*jakarta, *jakarta) == pytest.approx(0.0, abs=1e-9)
    assert haversine_distance_km(*bandung, *jakarta) == pytest.approx(scalar, rel=1e-12)


@pytest.mark.unit
def test_haversine_km_is_vectorised_over_arrays():
    import numpy as np

    from api.data import haversine_km

    lats = np.array([-6.20, -6.20, -6.20])
    lons = np.array([106.80, 106.81, 106.83])
    d = haversine_km(-6.20, 106.80, lats, lons)
    assert d.shape == (3,)
    assert d[0] == pytest.approx(0.0, abs=1e-9)
    assert d[1] < d[2]
    assert d[2] == pytest.approx(3.0 * d[1], rel=1e-3)  # equally spaced along a parallel


# ===========================================================================
# api/routing.py -- HTTP surface
# ===========================================================================
@pytest.fixture
def client(tiny_graph):
    from fastapi.testclient import TestClient

    from api import main
    with TestClient(main.app) as c:
        yield c


@pytest.mark.integration
def test_route_endpoint_reports_503_when_the_graph_is_unavailable(no_graph, monkeypatch):
    from fastapi.testclient import TestClient

    from api import main
    monkeypatch.setitem(sys.modules, "osmnx", None)
    with TestClient(main.app) as c:
        r = c.get("/api/v1/route", params={"lat": -6.20, "lon": 106.80,
                                           "dest_lat": -6.20, "dest_lon": 106.83})
    assert r.status_code == 503
    assert "routing unavailable" in r.json()["detail"]


@pytest.mark.integration
def test_route_endpoint_reports_404_when_no_drivable_route_exists(client):
    r = client.get("/api/v1/route", params={"lat": -6.20, "lon": 106.8003,
                                            "dest_lat": -6.2010, "dest_lon": 106.8005})
    assert r.status_code == 404
    assert "no drivable route" in r.json()["detail"]


@pytest.mark.integration
def test_route_endpoint_requires_an_origin(client):
    r = client.get("/api/v1/route", params={"dest_lat": -6.20, "dest_lon": 106.83})
    assert r.status_code == 422


@pytest.mark.integration
def test_nearest_station_endpoint_404s_when_no_stations_are_loaded(client, monkeypatch):
    from api import main
    monkeypatch.setattr(main.repo, "routing_coords", lambda *a, **k: [])
    r = client.get("/api/v1/route/nearest-station", params={"lat": -6.20, "lon": 106.80})
    assert r.status_code == 404
    assert "no charging stations loaded" in r.json()["detail"]


@pytest.mark.integration
def test_nearest_station_endpoint_requires_an_origin(client):
    assert client.get("/api/v1/route/nearest-station").status_code == 422


@requires_db
@pytest.mark.integration
def test_nearest_station_endpoint_returns_a_station_and_its_route(client, monkeypatch):
    """Full stack: DB station rows -> road snapping -> Dijkstra -> response model."""
    from api import main
    subset = main.repo.routing_coords()[:3]
    assert subset, "seeded database expected"
    monkeypatch.setattr(main.repo, "routing_coords", lambda *a, **k: list(subset))

    r = client.get("/api/v1/route/nearest-station",
                   params={"lat": -6.20, "lon": 106.8003, "max_range_km": 500})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["station"]["id"] in {s["id"] for s in subset}
    assert body["candidates_considered"] == len(subset)
    assert body["within_range"] is True
    assert body["range_used_km"] == 500
    assert body["route"]["geometry"]["type"] == "LineString"
    assert len(body["route"]["geometry"]["coordinates"]) >= 2
    # the station distance echoed on the station model is the ROUTE distance
    assert body["station"]["distance_km"] == pytest.approx(
        body["route"]["distance_m"] / 1000.0, abs=0.05)

    tight = client.get("/api/v1/route/nearest-station",
                       params={"lat": -6.20, "lon": 106.8003, "max_range_km": 0.0001})
    assert tight.status_code == 200
    assert tight.json()["within_range"] is False


# ===========================================================================
# api/services/routing_service.py -- provider fallback chain
# ===========================================================================
class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _never_spawn_curl(monkeypatch):
    """Hard guard: the curl fallback must never reach a subprocess or the network.

    `_request_osrm_json` catches EVERY httpx failure and falls through to
    `_request_osrm_json_with_curl`, which shells out to a real curl against the
    real URL -- so a fake client with the wrong signature silently turns into an
    outbound DNS lookup. Stubbing the module-local `shutil` makes the helper
    short-circuit on `which("curl") is None` before it can spawn anything, so no
    test in this module can dial out even by accident.
    """
    monkeypatch.setattr(rs_module, "shutil", types.SimpleNamespace(which=lambda _name: None))


def _spy_curl_fallback(monkeypatch, result=None):
    """Record calls to the curl fallback (and keep it offline) without disabling it."""
    calls: list = []

    async def _fake_curl(self, url):
        calls.append(url)
        return result

    monkeypatch.setattr(rs_module.RoutingService, "_request_osrm_json_with_curl", _fake_curl)
    return calls


def _fake_httpx(monkeypatch, response, recorder: list):
    class _Client:
        # HEAD constructs this with timeout= AND headers=; accepting **kwargs keeps
        # the fake from throwing a TypeError that would be mistaken for a transport
        # error and silently divert the call to the curl path.
        def __init__(self, **kwargs):
            recorder.append(("client_kwargs", kwargs))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            recorder.append(("url", url))
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setattr(rs_module.httpx, "AsyncClient", _Client)
    return recorder


def _stub_local_router(monkeypatch, *, per_leg_km: float = 25.0,
                       legs_before_failure: int | None = None):
    """Make the local Dijkstra fallback deterministic without loading a graph.

    `_local_fallback_route` imports `shortest_path` from `api.routing` on every
    call, so patching the module attribute is enough.
    """
    from api import routing as routing_mod

    calls: list = []

    def fake_shortest_path(o_lat, o_lon, d_lat, d_lon, weight="length"):
        calls.append((o_lat, o_lon, d_lat, d_lon))
        if legs_before_failure is not None and len(calls) > legs_before_failure:
            return None
        return {
            "distance_m": per_leg_km * 1000.0,
            "duration_s": 1800.0,
            "geometry": {"type": "LineString",
                         "coordinates": [[o_lon, o_lat], [d_lon, d_lat]]},
        }

    monkeypatch.setattr(routing_mod, "shortest_path", fake_shortest_path)
    return calls


def _osrm_payload(distance_m: float, duration_s: float, legs=None):
    return {
        "code": "Ok",
        "routes": [{
            "distance": distance_m,
            "duration": duration_s,
            "geometry": {"type": "LineString",
                         "coordinates": [[106.80, -6.20], [106.83, -6.20]]},
            "legs": legs if legs is not None else [{
                "steps": [{"name": "Jl. Sudirman", "distance": distance_m,
                           "duration": duration_s,
                           "maneuver": {"type": "depart", "modifier": "",
                                        "location": [106.80, -6.20]}}]
            }],
        }],
    }


@pytest.mark.unit
def test_osrm_success_is_used_verbatim_and_labels_every_step_with_its_leg(monkeypatch):
    calls: list = []
    _fake_httpx(monkeypatch, _FakeResponse(200, _osrm_payload(
        120000.0, 7200.0,
        legs=[
            {"steps": [{"name": "A", "distance": 60000.0, "duration": 3600.0,
                        "maneuver": {"type": "depart", "location": [106.8, -6.2]}}]},
            {"steps": [{"name": "B", "distance": 60000.0, "duration": 3600.0,
                        "maneuver": {"type": "arrive", "modifier": "right",
                                     "location": [107.6, -6.9]}}]},
        ])), calls)
    curl = _spy_curl_fallback(monkeypatch)

    svc = RoutingService(osrm_base_url="http://osrm.invalid", timeout=7.5)
    res = asyncio.run(svc.get_route((-6.2088, 106.8456), (-6.9175, 107.6191),
                                    waypoints=[(-6.5, 107.2)]))

    assert res["provider"] == "osrm"
    assert res["distance_km"] == 120.0
    assert res["duration_minutes"] == 120.0
    assert [s["leg_index"] for s in res["steps"]] == [0, 1]
    assert res["steps"][1]["instruction"] == "arrive right"
    assert res["steps"][0]["instruction"] == "depart"    # empty modifier is stripped
    assert res["steps"][0]["name"] == "A" and res["steps"][1]["name"] == "B"
    assert res["geometry"]["type"] == "LineString"
    assert curl == []                       # a healthy httpx reply never touches curl

    # the waypoint really was threaded into the request, in lon,lat order
    url = [v for k, v in calls if k == "url"][0]
    coord_part = url.split("/driving/")[1].split("?")[0]
    assert coord_part == "106.845600,-6.208800;107.200000,-6.500000;107.619100,-6.917500"
    assert "geometries=geojson" in url and "steps=true" in url

    # the configured timeout and a real User-Agent are handed to the client
    kwargs = [v for k, v in calls if k == "client_kwargs"][0]
    assert kwargs["timeout"] == 7.5
    assert kwargs["headers"]["User-Agent"]


@pytest.mark.unit
@pytest.mark.parametrize("response", [
    _FakeResponse(500, {}),                                    # upstream error
    _FakeResponse(404, {}),
    _FakeResponse(200, {"code": "NoRoute", "routes": []}),     # OSRM said no
    _FakeResponse(200, {"code": "Ok", "routes": []}),          # Ok but empty
])
def test_unusable_osrm_replies_fall_through_to_the_next_provider(monkeypatch, response):
    """An unusable reply must be discarded and the local road router consulted."""
    _fake_httpx(monkeypatch, response, [])
    _spy_curl_fallback(monkeypatch)
    local = _stub_local_router(monkeypatch, per_leg_km=88.0)

    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    res = asyncio.run(svc.get_route((-6.2088, 106.8456), (-6.9175, 107.6191)))

    assert res["provider"] == "local_dijkstra"
    assert res["distance_km"] == 88.0        # the local answer, not the OSRM one
    assert len(local) == 1                   # the local router really was asked


@pytest.mark.unit
def test_a_transport_error_tries_curl_then_falls_through_without_propagating(monkeypatch, caplog):
    """httpx blowing up must degrade to curl, then to the local router -- never raise."""
    import httpx

    _fake_httpx(monkeypatch, httpx.ConnectError("connection refused"), [])
    curl = _spy_curl_fallback(monkeypatch, result=None)   # curl fails too
    local = _stub_local_router(monkeypatch, per_leg_km=42.0)

    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    with caplog.at_level("WARNING"):
        res = asyncio.run(svc.get_route((-6.2088, 106.8456), (-6.9175, 107.6191)))

    assert res["provider"] == "local_dijkstra"
    assert res["distance_km"] == 42.0
    assert len(curl) == 1                     # the curl fallback was attempted once
    assert len(local) == 1
    assert any("curl fallback" in r.getMessage() for r in caplog.records)


@pytest.mark.unit
def test_curl_rescues_the_route_when_httpx_cannot_reach_osrm(monkeypatch):
    """The curl fallback exists to salvage the request, not just to be logged."""
    import httpx

    _fake_httpx(monkeypatch, httpx.ConnectError("connection refused"), [])
    _spy_curl_fallback(monkeypatch, result=_osrm_payload(30000.0, 1800.0))
    local = _stub_local_router(monkeypatch, per_leg_km=99.0)

    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    res = asyncio.run(svc.get_route((-6.2088, 106.8456), (-6.9175, 107.6191)))

    assert res["provider"] == "osrm"
    assert res["distance_km"] == 30.0
    assert local == []                        # the local router was never needed


@pytest.mark.unit
def test_the_curl_fallback_is_a_no_op_when_curl_is_not_installed(monkeypatch):
    """`shutil.which` returning None must short-circuit before any subprocess spawn."""
    def _explode(*a, **k):                    # pragma: no cover - must never run
        raise AssertionError("a subprocess was spawned even though curl is missing")

    monkeypatch.setattr(rs_module.asyncio, "create_subprocess_exec", _explode)
    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    assert asyncio.run(svc._request_osrm_json_with_curl("http://osrm.invalid/x")) is None


# --- the curl subprocess branches -----------------------------------------
# No curl is ever spawned: `create_subprocess_exec` is replaced by a fake that
# hands back a scripted process object. Nothing here sleeps -- the timeout case
# raises `asyncio.TimeoutError` out of the inner coroutine, which `wait_for`
# propagates just as a real expiry would.
class _FakeProc:
    def __init__(self, stdout=b"", stderr=b"", returncode=0, timeout_first_call=False):
        self._stdout, self._stderr = stdout, stderr
        self.returncode = returncode
        self._timeout_first_call = timeout_first_call
        self.communicate_calls = 0
        self.killed = False

    async def communicate(self):
        self.communicate_calls += 1
        if self._timeout_first_call and self.communicate_calls == 1:
            raise asyncio.TimeoutError()
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


def _fake_curl_process(monkeypatch, proc: _FakeProc) -> list:
    argv: list = []
    monkeypatch.setattr(rs_module, "shutil",
                        types.SimpleNamespace(which=lambda _n: "/usr/bin/curl"))

    async def _spawn(*args, **kwargs):
        argv.append(args)
        return proc

    monkeypatch.setattr(rs_module.asyncio, "create_subprocess_exec", _spawn)
    return argv


@pytest.mark.unit
def test_curl_output_is_parsed_and_the_request_is_bounded_and_safe(monkeypatch):
    proc = _FakeProc(stdout=b'{"code": "Ok", "routes": []}')
    argv = _fake_curl_process(monkeypatch, proc)

    svc = RoutingService(osrm_base_url="http://osrm.invalid", timeout=4.0)
    assert asyncio.run(svc._request_osrm_json_with_curl("http://osrm.invalid/x?a=1;b=2")) == {
        "code": "Ok", "routes": []}

    flags = list(argv[0])
    # --fail so an HTTP error is a non-zero exit, --max-time so it cannot hang
    # forever, --globoff so the `;` separating OSRM coordinates is not treated
    # as a curl URL glob.
    assert "--fail" in flags and "--globoff" in flags
    assert flags[flags.index("--max-time") + 1] == "4"
    assert flags[-1] == "http://osrm.invalid/x?a=1;b=2"


@pytest.mark.unit
def test_a_hanging_curl_is_killed_and_reaped_rather_than_left_behind(monkeypatch):
    proc = _FakeProc(timeout_first_call=True)
    _fake_curl_process(monkeypatch, proc)

    svc = RoutingService(osrm_base_url="http://osrm.invalid", timeout=0.01)
    assert asyncio.run(svc._request_osrm_json_with_curl("http://osrm.invalid/x")) is None
    assert proc.killed, "a timed-out curl was left running"
    assert proc.communicate_calls == 2, "the killed process was never reaped"


@pytest.mark.unit
def test_a_failing_curl_exit_code_yields_no_route_and_is_logged(monkeypatch, caplog):
    proc = _FakeProc(stdout=b"", stderr=b"curl: (22) HTTP 502", returncode=22)
    _fake_curl_process(monkeypatch, proc)

    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    with caplog.at_level("WARNING"):
        assert asyncio.run(svc._request_osrm_json_with_curl("http://osrm.invalid/x")) is None
    assert any("502" in r.getMessage() for r in caplog.records)


@pytest.mark.unit
def test_curl_returning_html_instead_of_json_is_rejected_not_crashed(monkeypatch):
    """A captive portal or proxy error page must not raise out of the router."""
    proc = _FakeProc(stdout=b"<html>503 Service Unavailable</html>")
    _fake_curl_process(monkeypatch, proc)

    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    assert asyncio.run(svc._request_osrm_json_with_curl("http://osrm.invalid/x")) is None


@pytest.mark.unit
def test_a_degenerate_zero_km_answer_is_discarded_not_published(monkeypatch, caplog):
    """OSRM off its map snaps both ends to one node and answers 0 km for 118 km."""
    _fake_httpx(monkeypatch, _FakeResponse(200, _osrm_payload(12.0, 3.0)), [])
    _spy_curl_fallback(monkeypatch)
    _stub_local_router(monkeypatch, per_leg_km=137.0)

    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    with caplog.at_level("WARNING"):
        res = asyncio.run(svc.get_route((-6.2088, 106.8456), (-6.9175, 107.6191)))

    assert res["provider"] == "local_dijkstra"
    assert res["distance_km"] == 137.0       # NOT the bogus 0.01 km OSRM reported
    assert any("degenerate" in r.getMessage() for r in caplog.records)


@pytest.mark.unit
def test_a_genuinely_short_trip_is_not_mistaken_for_a_degenerate_answer(monkeypatch):
    """Two points 200 m apart legitimately route in under DEGENERATE_ROUTE_KM."""
    _fake_httpx(monkeypatch, _FakeResponse(200, _osrm_payload(210.0, 40.0)), [])
    _spy_curl_fallback(monkeypatch)
    local = _stub_local_router(monkeypatch)

    svc = RoutingService(osrm_base_url="http://osrm.invalid")
    res = asyncio.run(svc.get_route((-6.2000, 106.8000), (-6.2000, 106.8018)))

    assert res["provider"] == "osrm"
    assert res["distance_km"] == 0.21
    assert local == []                       # the short answer was accepted, not discarded


@pytest.mark.unit
def test_osrm_is_skipped_entirely_when_no_base_url_is_configured(monkeypatch):
    calls: list = []
    _fake_httpx(monkeypatch, _FakeResponse(200, _osrm_payload(1.0, 1.0)), calls)
    curl = _spy_curl_fallback(monkeypatch)
    _stub_local_router(monkeypatch, per_leg_km=60.0)

    svc = RoutingService(osrm_base_url="")
    res = asyncio.run(svc.get_route((-6.2088, 106.8456), (-6.9175, 107.6191)))

    assert res["provider"] == "local_dijkstra"
    assert res["distance_km"] == 60.0
    assert calls == []          # no client was ever constructed
    assert curl == []           # and no subprocess path was entered either


@pytest.mark.unit
def test_local_dijkstra_serves_the_route_when_osrm_is_down(tiny_graph):
    """OSRM pointed at a closed port; the local graph answers with real geometry."""
    svc = RoutingService(osrm_base_url="http://127.0.0.1:9", timeout=0.25)
    res = asyncio.run(svc.get_route((-6.20, 106.8003), (-6.20, 106.8297)))
    assert res["provider"] == "local_dijkstra"
    assert res["distance_km"] == 3.0
    assert res["duration_minutes"] == pytest.approx(4.5)     # 3 km at the 40 km/h estimate
    assert res["geometry"]["coordinates"][0] == [106.80, -6.20]
    assert res["geometry"]["coordinates"][-1] == [106.83, -6.20]
    assert len(res["steps"]) == 1 and res["steps"][0]["leg_index"] == 0


@pytest.mark.unit
def test_local_dijkstra_joins_legs_without_duplicating_the_shared_vertex(tiny_graph):
    svc = RoutingService(osrm_base_url="")
    res = asyncio.run(svc.get_route((-6.20, 106.8003), (-6.20, 106.8297),
                                    waypoints=[(-6.20, 106.8102)]))
    assert res["provider"] == "local_dijkstra"
    assert res["distance_km"] == 3.0
    coords = res["geometry"]["coordinates"]
    assert coords == [[106.80, -6.20], [106.81, -6.20], [106.82, -6.20], [106.83, -6.20]]


@pytest.mark.unit
def test_an_unreachable_destination_raises_instead_of_faking_a_straight_line(tiny_graph):
    """Node 5 is on the map but off the road network.

    The service must refuse rather than hand the map a straight line dressed up
    as a route: every published geometry has to come from a road provider.
    """
    svc = RoutingService(osrm_base_url="")
    with pytest.raises(rs_module.RouteUnavailable) as exc:
        asyncio.run(svc.get_route((-6.20, 106.8003), (-6.2010, 106.8005)))
    assert "no drivable road route" in str(exc.value)


@pytest.mark.unit
def test_a_missing_road_graph_raises_and_says_so_distinctly(no_graph, monkeypatch):
    """`graph unavailable` and `no route found` are different operator problems.

    One means "the deployment is broken, go build the graph"; the other means
    "these two points genuinely do not connect". They must not collapse into
    one message, and neither may produce a fabricated route.
    """
    monkeypatch.setitem(sys.modules, "osmnx", None)
    svc = RoutingService(osrm_base_url="")
    with pytest.raises(rs_module.RouteUnavailable) as exc:
        asyncio.run(svc.get_route((-6.2088, 106.8456), (-6.9175, 107.6191)))
    assert "road routing is unavailable" in str(exc.value)
    assert isinstance(exc.value.__cause__, routing.GraphUnavailable)


@pytest.mark.unit
@pytest.mark.parametrize("provider,expected_basis", [
    ("osrm", "road"),
    ("local_dijkstra", "road"),
    # Anything that is not a known road provider must be treated as straight-line,
    # including a provider added later that nobody remembered to whitelist.
    ("some_future_estimator", "straight_line"),
    (None, "straight_line"),
])
def test_distance_basis_is_road_only_for_real_road_providers(provider, expected_basis):
    """`detour = leg1 + leg2 - direct` is only meaningful in ONE measure."""
    from api.main import _distance_basis

    origin, dest = (-6.2088, 106.8456), (-6.9175, 107.6191)
    basis, scale = _distance_basis({"provider": provider, "distance_km": 150.0}, origin, dest)
    assert basis == expected_basis
    assert scale == pytest.approx(150.0 / haversine_distance_km(*origin, *dest))
    assert (provider in rs_module.ROAD_PROVIDERS) is (expected_basis == "road")


@pytest.mark.unit
def test_distance_basis_scale_is_neutral_for_a_degenerate_pair():
    from api.main import _distance_basis

    _, scale = _distance_basis({"provider": "osrm", "distance_km": 0.0},
                               (-6.2088, 106.8456), (-6.2088, 106.8456))
    assert scale == 1.0


@pytest.mark.unit
def test_a_partial_local_route_is_never_published_as_a_whole_trip(monkeypatch):
    """Leg 1 solves, leg 2 does not: the half-route must not escape.

    `_local_fallback_route` banks distance and geometry into locals as it walks
    the legs. If a later leg fails, everything accumulated so far has to be
    discarded -- returning it would quote the driver a trip that stops at the
    waypoint while claiming to reach the destination, and the battery plan
    derived from that distance would be wrong.
    """
    local = _stub_local_router(monkeypatch, per_leg_km=20.0, legs_before_failure=1)

    origin, waypoint, dest = (-6.2, 106.8), (-6.3, 106.9), (-6.4, 107.0)
    svc = RoutingService(osrm_base_url="")
    with pytest.raises(rs_module.RouteUnavailable) as exc:
        asyncio.run(svc.get_route(origin, dest, waypoints=[waypoint]))

    assert "no drivable road route" in str(exc.value)
    assert len(local) == 2          # it did try leg 2 before giving up


# ===========================================================================
# api/services/stop_ranker.py -- candidate fetching
# ===========================================================================
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
    monkeypatch.setattr(sr_module, "fetch_availability", lambda ids: dict(availabilities))
    return StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))


def _rank(ranker, **kwargs):
    params = dict(
        origin=ORIGIN, destination=DEST, direct_distance_km=110.0,
        battery_kwh=58.0, efficiency_wh_per_km=160.0, current_soc_pct=45.0,
        minimum_arrival_soc_pct=20.0, maximum_detour_km=15.0,
        vehicle_connector="CCS", max_dc_charge_kw=185.0,
    )
    params.update(kwargs)
    return asyncio.run(ranker.rank_stops(**params))


@pytest.fixture
def repo_stub(monkeypatch):
    """Replace every stations_repo entry point the ranker may reach for."""
    import api.stations_repo as repo

    state = {"corridor": [], "nearby": [], "list": [], "get": None,
             "corridor_raises": False, "list_raises": False, "get_raises": False,
             "calls": []}

    def along_corridor(**kwargs):
        state["calls"].append(("along_corridor", kwargs))
        if state["corridor_raises"]:
            raise RuntimeError("PostGIS unavailable")
        return list(state["corridor"])

    def nearby(lat, lon, radius_km, limit, filters=None):
        state["calls"].append(("nearby", (lat, lon, radius_km, limit)))
        return list(state["nearby"])

    def list_stations(filters, limit, offset):
        state["calls"].append(("list_stations", (filters, limit, offset)))
        if state["list_raises"]:
            raise RuntimeError("database down")
        return len(state["list"]), list(state["list"])

    def get_station(sid):
        state["calls"].append(("get_station", sid))
        if state["get_raises"]:
            raise RuntimeError("database down")
        return state["get"]

    monkeypatch.setattr(repo, "along_corridor", along_corridor)
    monkeypatch.setattr(repo, "nearby", nearby)
    monkeypatch.setattr(repo, "list_stations", list_stations)
    monkeypatch.setattr(repo, "get_station", get_station)
    return state


@pytest.mark.unit
def test_a_forced_station_is_fetched_by_id_and_nothing_else(repo_stub):
    forced = _station("st-forced", -6.5, 107.2)
    repo_stub["get"] = forced
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))

    got = ranker._fetch_stations(ORIGIN, DEST, "st-forced")
    assert got == [forced]
    assert [c[0] for c in repo_stub["calls"]] == ["get_station"]


@pytest.mark.unit
def test_a_forced_station_that_does_not_exist_yields_no_candidates(repo_stub):
    repo_stub["get"] = None
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))
    assert ranker._fetch_stations(ORIGIN, DEST, "st-missing") == []


@pytest.mark.unit
def test_a_database_error_while_fetching_a_forced_station_is_not_fatal(repo_stub):
    repo_stub["get_raises"] = True
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))
    assert ranker._fetch_stations(ORIGIN, DEST, "st-forced") == []


@pytest.mark.unit
def test_a_degenerate_corridor_uses_a_radius_search_not_a_line_projection(repo_stub):
    """ST_LineLocatePoint has nothing to project onto when origin == destination."""
    repo_stub["nearby"] = [_station("st-here", -6.2088, 106.8456)]
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))

    got = ranker._fetch_stations(ORIGIN, (-6.2088, 106.84561), None)
    assert [s["id"] for s in got] == ["st-here"]
    kinds = [c[0] for c in repo_stub["calls"]]
    assert "nearby" in kinds and "along_corridor" not in kinds


@pytest.mark.unit
def test_the_corridor_search_is_the_primary_prefilter(repo_stub):
    repo_stub["corridor"] = [_station("st-a", -6.5, 107.2)]
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))

    got = ranker._fetch_stations(ORIGIN, DEST, None, corridor_km=40.0)
    assert [s["id"] for s in got] == ["st-a"]
    kind, kwargs = repo_stub["calls"][0]
    assert kind == "along_corridor"
    assert kwargs["corridor_km"] == 40.0
    assert kwargs["limit"] == sr_module.CANDIDATE_FETCH_LIMIT
    assert kwargs["buckets"] == sr_module.CORRIDOR_BUCKETS


@pytest.mark.unit
def test_the_corridor_radius_never_shrinks_below_the_configured_minimum(repo_stub):
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))
    ranker._fetch_stations(ORIGIN, DEST, None, corridor_km=0.5)
    assert repo_stub["calls"][0][1]["corridor_km"] == sr_module.CORRIDOR_MIN_KM


@pytest.mark.unit
def test_a_failed_corridor_query_falls_back_to_a_bounding_box(repo_stub):
    repo_stub["corridor_raises"] = True
    repo_stub["list"] = [_station("st-bbox", -6.5, 107.2)]
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))

    got = ranker._fetch_stations(ORIGIN, DEST, None)
    assert [s["id"] for s in got] == ["st-bbox"]
    (_, (filters, limit, offset)), = [c for c in repo_stub["calls"] if c[0] == "list_stations"]
    margin = sr_module.CORRIDOR_MARGIN_DEG
    assert filters["bbox"] == pytest.approx((
        min(ORIGIN[1], DEST[1]) - margin, min(ORIGIN[0], DEST[0]) - margin,
        max(ORIGIN[1], DEST[1]) + margin, max(ORIGIN[0], DEST[0]) + margin))
    assert limit == sr_module.CANDIDATE_FETCH_LIMIT and offset == 0


@pytest.mark.unit
def test_a_total_repository_outage_yields_an_empty_candidate_list(repo_stub):
    repo_stub["corridor_raises"] = True
    repo_stub["list_raises"] = True
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))
    assert ranker._fetch_stations(ORIGIN, DEST, None) == []


# ===========================================================================
# api/services/stop_ranker.py -- filtering and ranking
# ===========================================================================
@pytest.mark.unit
def test_no_candidates_means_no_stops_and_no_availability_query(monkeypatch):
    """An empty prefilter must short-circuit before the availability round trip."""
    queried: list = []
    monkeypatch.setattr(StopRanker, "_fetch_stations", lambda self, o, d, forced, **kw: [])
    monkeypatch.setattr(sr_module, "fetch_availability",
                        lambda ids: queried.append(ids) or {})
    ranker = StopRanker(EnergyEstimator(), RoutingService(osrm_base_url=""))
    assert _rank(ranker) == []
    assert queried == []


@pytest.mark.unit
def test_every_candidate_filtered_out_returns_an_empty_list_not_a_bad_stop(monkeypatch):
    """No free compatible connector anywhere -> no offer, at any reach floor."""
    a = _station("st-a", -6.56, 107.23)
    b = _station("st-b", -6.60, 107.30)
    ranker = _ranker(monkeypatch, [a, b], {
        "st-a": _avail("st-a", {"CCS2": 0}, total={"CCS2": 2}),   # all occupied
        "st-b": _avail("st-b", {"CHAdeMO": 3}, power={"CHAdeMO": 50.0}),  # wrong type
    })
    assert _rank(ranker) == []


@pytest.mark.unit
def test_a_station_missing_from_the_availability_map_is_treated_as_unusable(monkeypatch):
    """"Absent" must mean "cannot prove a free connector", never "allow it"."""
    a = _station("st-a", -6.56, 107.23)
    ranker = _ranker(monkeypatch, [a], {})
    assert _rank(ranker) == []


@pytest.mark.unit
def test_a_candidate_outside_the_detour_budget_is_dropped_and_the_budget_admits_it(monkeypatch):
    """The detour filter must be the ONLY reason this station is rejected."""
    mid = _station("st-mid", -6.5632, 107.2324, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid],
                     {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})

    # legs sum to ~116 km; declaring the direct route 90 km makes the detour ~26 km
    assert _rank(ranker, direct_distance_km=90.0, maximum_detour_km=15.0) == []

    admitted = _rank(ranker, direct_distance_km=90.0, maximum_detour_km=40.0)
    assert [s.station.id for s in admitted] == ["st-mid"]
    assert admitted[0].detour_km == pytest.approx(
        admitted[0].distance_from_origin_km + admitted[0].distance_to_destination_km - 90.0,
        abs=0.2)
    assert 15.0 < admitted[0].detour_km < 40.0
    assert admitted[0].detour_within_budget is True
    assert admitted[0].detour_budget_km == 40.0


@pytest.mark.unit
def test_a_driver_forced_stop_may_break_the_detour_budget_but_is_flagged(monkeypatch):
    """A forced waypoint skips the SOFT preference filter -- and says so."""
    mid = _station("st-mid", -6.5632, 107.2324, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid],
                     {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})

    stops = _rank(ranker, direct_distance_km=90.0, maximum_detour_km=1.0,
                  forced_station_id="st-mid")
    assert len(stops) == 1
    assert stops[0].detour_within_budget is False
    assert stops[0].detour_km > 1.0
    assert stops[0].completes_trip is True       # the physics still hold


@pytest.mark.unit
def test_a_forced_stop_with_no_free_connector_is_returned_with_a_blocking_reason(monkeypatch):
    mid = _station("st-mid", -6.5632, 107.2324, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid],
                     {"st-mid": _avail("st-mid", {"CCS2": 0}, total={"CCS2": 2})})

    stops = _rank(ranker, forced_station_id="st-mid")
    assert len(stops) == 1
    assert stops[0].completes_trip is False
    assert "no_free_compatible_connector" in stops[0].blocking_reasons
    assert stops[0].availability == "unavailable"
    assert stops[0].available_connector_count == 0
    # the plug still FITS even though none is free -- those are different facts
    assert stops[0].connector_compatible is True


@pytest.mark.unit
def test_a_forced_stop_too_far_from_the_destination_reports_cannot_complete_trip(monkeypatch):
    """Even a 100% charge at this stop cannot cover the remaining leg."""
    near_origin = _station("st-near", -6.2100, 106.8460, power_kw=150.0)
    ranker = _ranker(monkeypatch, [near_origin],
                     {"st-near": _avail("st-near", {"CCS2": 2}, power={"CCS2": 150.0})})

    stops = _rank(ranker, destination=(-15.0, 115.0), direct_distance_km=1500.0,
                  forced_station_id="st-near", maximum_detour_km=5000.0)
    assert len(stops) == 1
    assert stops[0].completes_trip is False
    assert "cannot_complete_trip" in stops[0].blocking_reasons
    assert stops[0].required_target_soc_pct > 100.0
    assert stops[0].recommended_target_soc_pct == 100.0


@pytest.mark.unit
def test_a_malformed_station_row_is_skipped_instead_of_killing_the_whole_plan(monkeypatch):
    good = _station("st-good", -6.5632, 107.2324, power_kw=150.0)
    broken = dict(_station("st-broken", -6.56, 107.23), latitude=None)
    missing_key = {"id": "st-nokey"}
    ranker = _ranker(monkeypatch, [broken, missing_key, good], {
        "st-good": _avail("st-good", {"CCS2": 2}, power={"CCS2": 150.0}),
        "st-broken": _avail("st-broken", {"CCS2": 2}, power={"CCS2": 150.0}),
        "st-nokey": _avail("st-nokey", {"CCS2": 2}, power={"CCS2": 150.0}),
    })
    stops = _rank(ranker)
    assert [s.station.id for s in stops] == ["st-good"]


@pytest.mark.unit
def test_a_ranking_tie_is_broken_deterministically_by_station_id(monkeypatch):
    """Two identical stations must not depend on the order the database returned."""
    lat, lon = -6.5632, 107.2324
    b = _station("st-b", lat, lon, power_kw=150.0)
    a = _station("st-a", lat, lon, power_kw=150.0)
    c = _station("st-c", lat, lon, power_kw=150.0)
    ranker = _ranker(monkeypatch, [b, c, a], {
        sid: _avail(sid, {"CCS2": 2}, power={"CCS2": 150.0}) for sid in ("st-a", "st-b", "st-c")
    })
    stops = _rank(ranker)
    assert len({s.rank_score for s in stops}) == 1        # a genuine tie
    assert [s.station.id for s in stops] == ["st-a", "st-b", "st-c"]


@pytest.mark.unit
def test_the_limit_is_applied_after_ranking_not_before(monkeypatch):
    near = _station("st-near", -6.40, 107.05, power_kw=50.0)
    far = _station("st-far", -6.30, 106.60, power_kw=50.0)
    ranker = _ranker(monkeypatch, [far, near], {
        "st-near": _avail("st-near", {"CCS2": 2}, power={"CCS2": 50.0}),
        "st-far": _avail("st-far", {"CCS2": 2}, power={"CCS2": 50.0}),
    })
    all_stops = _rank(ranker, maximum_detour_km=200.0, direct_distance_km=110.0)
    assert len(all_stops) == 2
    assert all_stops[0].rank_score <= all_stops[1].rank_score
    top = _rank(ranker, maximum_detour_km=200.0, direct_distance_km=110.0, limit=1)
    assert [s.station.id for s in top] == [all_stops[0].station.id]


@pytest.mark.unit
def test_select_recommended_stop_returns_none_when_nothing_qualifies(monkeypatch):
    ranker = _ranker(monkeypatch, [], {})
    got = asyncio.run(ranker.select_recommended_stop(
        origin=ORIGIN, destination=DEST, direct_distance_km=110.0, battery_kwh=58.0,
        efficiency_wh_per_km=160.0, current_soc_pct=45.0, minimum_arrival_soc_pct=20.0,
        vehicle_connector="CCS", max_dc_charge_kw=185.0))
    assert got is None


# ===========================================================================
# api/services/stop_ranker.py -- road re-validation
# ===========================================================================
def _one_stop(monkeypatch):
    mid = _station("st-mid", -6.5632, 107.2324, power_kw=150.0)
    ranker = _ranker(monkeypatch, [mid],
                     {"st-mid": _avail("st-mid", {"CCS2": 2}, power={"CCS2": 150.0})})
    stops = _rank(ranker)
    assert stops, "fixture expected one viable stop"
    return ranker, stops[0]


@pytest.mark.unit
def test_revalidation_drops_a_stop_the_real_road_legs_cannot_reach(monkeypatch):
    """A detour leg more winding than the corridor average breaks the guarantee."""
    ranker, stop = _one_stop(monkeypatch)
    assert stop.reserve_intact_on_arrival is True

    dropped = ranker.revalidate_on_road(
        stop=stop, road_leg_to_station_km=400.0, road_leg_to_destination_km=60.0,
        road_direct_distance_km=140.0, battery_kwh=58.0, efficiency_wh_per_km=160.0,
        current_soc_pct=45.0, reserve_pct=20.0, max_dc_charge_kw=185.0)
    assert dropped is None


@pytest.mark.unit
def test_revalidation_drops_a_stop_that_can_no_longer_finish_the_trip(monkeypatch):
    ranker, stop = _one_stop(monkeypatch)
    dropped = ranker.revalidate_on_road(
        stop=stop, road_leg_to_station_km=50.0, road_leg_to_destination_km=900.0,
        road_direct_distance_km=940.0, battery_kwh=58.0, efficiency_wh_per_km=160.0,
        current_soc_pct=45.0, reserve_pct=20.0, max_dc_charge_kw=185.0)
    assert dropped is None


@pytest.mark.unit
def test_a_forced_stop_survives_revalidation_but_carries_its_blocking_reasons(monkeypatch):
    ranker, stop = _one_stop(monkeypatch)
    kept = ranker.revalidate_on_road(
        stop=stop, road_leg_to_station_km=400.0, road_leg_to_destination_km=900.0,
        road_direct_distance_km=1300.0, battery_kwh=58.0, efficiency_wh_per_km=160.0,
        current_soc_pct=45.0, reserve_pct=20.0, max_dc_charge_kw=185.0, forced=True)
    assert kept is not None
    assert kept.completes_trip is False
    assert "unreachable" in kept.blocking_reasons
    assert "cannot_complete_trip" in kept.blocking_reasons
    assert kept.reserve_intact_on_arrival is False


@pytest.mark.unit
def test_revalidation_restates_every_distance_on_the_road_basis(monkeypatch):
    ranker, stop = _one_stop(monkeypatch)
    assert stop.distance_basis == sr_module.DISTANCE_BASIS_STRAIGHT_LINE

    road = ranker.revalidate_on_road(
        stop=stop, road_leg_to_station_km=70.0, road_leg_to_destination_km=60.0,
        road_direct_distance_km=120.0, battery_kwh=58.0, efficiency_wh_per_km=160.0,
        current_soc_pct=90.0, reserve_pct=20.0, max_dc_charge_kw=185.0,
        maximum_detour_km=15.0)
    assert road is not None
    assert road.distance_basis == sr_module.DISTANCE_BASIS_ROAD
    assert road.distance_from_origin_km == 70.0
    assert road.distance_to_destination_km == 60.0
    assert road.station.distance_km == 70.0
    assert road.detour_km == 10.0
    assert road.detour_within_budget is True
    assert road.completes_trip is True
    assert road.station.id == stop.station.id


@pytest.mark.unit
def test_revalidation_reports_an_over_budget_road_detour_honestly(monkeypatch):
    """The budget was only ever a straight-line prefilter; the road detour may exceed it."""
    ranker, stop = _one_stop(monkeypatch)
    road = ranker.revalidate_on_road(
        stop=stop, road_leg_to_station_km=70.0, road_leg_to_destination_km=80.0,
        road_direct_distance_km=120.0, battery_kwh=58.0, efficiency_wh_per_km=160.0,
        current_soc_pct=90.0, reserve_pct=20.0, max_dc_charge_kw=185.0,
        maximum_detour_km=15.0)
    assert road is not None
    assert road.detour_km == 30.0
    assert road.detour_within_budget is False    # reported, not silently swallowed
    assert road.detour_budget_km == 15.0


@pytest.mark.unit
def test_ranking_weights_follow_the_drivers_preferences():
    from api.models import ROUTE_TYPE_FASTEST, ROUTE_TYPE_SHORTEST

    fast = sr_module.ranking_weights_for(ROUTE_TYPE_FASTEST, prefer_fast_charging=True)
    shortest = sr_module.ranking_weights_for(ROUTE_TYPE_SHORTEST, prefer_fast_charging=True)
    no_pref = sr_module.ranking_weights_for(ROUTE_TYPE_FASTEST, prefer_fast_charging=False)

    assert shortest.detour_weight > fast.detour_weight
    assert fast.power_weight_km_per_kw > no_pref.power_weight_km_per_kw
    assert no_pref.power_weight_km_per_kw == 0.0


@pytest.mark.unit
def test_preferring_fast_charging_can_outrank_a_shorter_detour(monkeypatch):
    """AC 2.2.4 is meaningless unless the preference actually moves the order."""
    close_slow = _station("st-close-slow", -6.5632, 107.2324, power_kw=22.0)
    far_fast = _station("st-far-fast", -6.5432, 107.2124, power_kw=200.0)
    ranker = _ranker(monkeypatch, [close_slow, far_fast], {
        "st-close-slow": _avail("st-close-slow", {"CCS2": 2}, power={"CCS2": 22.0}),
        "st-far-fast": _avail("st-far-fast", {"CCS2": 2}, power={"CCS2": 200.0}),
    })
    fast = _rank(ranker, weights=sr_module.ranking_weights_for(prefer_fast_charging=True))
    minimal = _rank(ranker, weights=sr_module.ranking_weights_for(prefer_fast_charging=False))

    assert fast[0].station.id == "st-far-fast"
    assert minimal[0].detour_km <= minimal[1].detour_km
    assert minimal[0].station.id == "st-close-slow"


# ===========================================================================
# api/services/connector_compat.py
# ===========================================================================
@pytest.mark.unit
@pytest.mark.parametrize("raw_key", sorted(connector_compat._NORMALIZATION_MAP))
def test_every_normalisation_map_entry_lands_on_the_live_vocabulary(raw_key):
    """The map IS the spec: the live `connectors` table only stores canonical types.

    NOTE the deliberate collapse of the CCS family (CCS / CCS1 / Combo 1 ...) onto
    CCS2 -- see the module docstring: the catalogue writes a bare 'CCS' for every
    CCS car and Indonesia deploys CCS2 exclusively.
    """
    expected = connector_compat._NORMALIZATION_MAP[raw_key]
    assert expected in connector_compat.CANONICAL_TYPES
    assert connector_compat.normalize_connector_type(raw_key) == expected
    # the key is reached through the SAME punctuation/case scrubbing users type
    spaced = " ".join(raw_key.lower())
    assert connector_compat.normalize_connector_type(spaced) == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    # substring fallbacks, most specific first
    ("Fast CHAdeMO (50 kW)", connector_compat.CHADEMO),
    ("chademo-1.2 protocol", connector_compat.CHADEMO),
    ("DC CCS plug, 150kW", connector_compat.CCS2),
    ("EU Combo connector", connector_compat.CCS2),
    ("Chinese GB/T 20234.3", connector_compat.GBT),
    ("Wall box Type 2 socket", connector_compat.AC_TYPE_2),
    ("Mennekes wallbox", connector_compat.AC_TYPE_2),
    ("Type 1 inlet", connector_compat.TYPE_1),
    ("SAE J1772 (US)", connector_compat.TYPE_1),
    # CHAdeMO wins over CCS when both words appear -- most specific first
    ("CHAdeMO / CCS dual head", connector_compat.CHADEMO),
])
def test_substring_fallbacks_recognise_free_text_spellings(raw, expected):
    assert connector_compat.normalize_connector_type(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw", [
    None, "", "   ", "-", "???",
    "Tesla Supercharger", "NACS", "Schuko", "unknown", "n/a", 0,
])
def test_unknown_vocabulary_normalises_to_none_rather_than_being_guessed(raw):
    assert connector_compat.normalize_connector_type(raw) is None


@pytest.mark.unit
def test_normalize_many_dedupes_drops_unknowns_and_keeps_first_seen_order():
    assert connector_compat.normalize_many(
        ["Type 2", "CCS", "ccs combo 2", "Tesla", None, "", "CHAdeMO", "Mennekes"]
    ) == [connector_compat.AC_TYPE_2, connector_compat.CCS2, connector_compat.CHADEMO]
    assert connector_compat.normalize_many(None) == []
    assert connector_compat.normalize_many([]) == []
    assert connector_compat.normalize_many(["Tesla", "Schuko"]) == []


@pytest.mark.unit
def test_a_vehicle_with_no_port_on_file_still_has_to_match_a_plug():
    """The old "unknown port -> compatible with everything" pass is gone."""
    profile = connector_compat.vehicle_connector_profile(None, None)
    assert profile.source == "default"
    assert profile.types == (connector_compat.AC_TYPE_2,)
    assert profile.is_fully_inferred is True
    assert profile.accepts("CCS2") is False
    assert connector_compat.connector_is_compatible(None, station_types=["CCS2"]) is False
    assert connector_compat.connector_is_compatible(None, station_types=["Type 2"]) is True


@pytest.mark.unit
def test_disabling_the_universal_ac_assumption_still_yields_a_usable_default():
    """include_universal_ac=False with nothing known must not produce an EMPTY profile."""
    profile = connector_compat.vehicle_connector_profile(
        None, None, include_universal_ac=False)
    assert profile.types == (connector_compat.AC_TYPE_2,)
    assert profile.inferred_types == (connector_compat.AC_TYPE_2,)
    assert profile.source == "default"
    assert profile.is_fully_inferred is True


@pytest.mark.unit
def test_disabling_the_universal_ac_assumption_keeps_a_known_dc_port_alone():
    profile = connector_compat.vehicle_connector_profile(
        "CCS", None, include_universal_ac=False)
    assert profile.types == (connector_compat.CCS2,)
    assert profile.inferred_types == ()
    assert profile.source == "ev_model"
    assert profile.is_fully_inferred is False
    assert profile.accepts("AC Type 2") is False


@pytest.mark.unit
def test_the_catalogue_port_beats_the_user_profile_and_ac_is_marked_inferred():
    profile = connector_compat.vehicle_connector_profile("CHAdeMO", "CCS2")
    assert profile.types == (connector_compat.CHADEMO, connector_compat.AC_TYPE_2)
    assert profile.source == "ev_model"
    assert profile.is_inferred("AC Type 2") is True
    assert profile.is_inferred("CHAdeMO") is False
    assert profile.is_inferred("Tesla") is False        # unknown is never "inferred"

    fallback = connector_compat.vehicle_connector_profile(None, "GB/T")
    assert fallback.source == "user_profile"
    assert fallback.types == (connector_compat.GBT, connector_compat.AC_TYPE_2)


@pytest.mark.unit
def test_an_ac_only_vehicle_does_not_get_ac_type_2_marked_as_inferred():
    profile = connector_compat.vehicle_connector_profile("Type 2")
    assert profile.types == (connector_compat.AC_TYPE_2,)
    assert profile.inferred_types == ()          # stated by the catalogue, not assumed
    assert profile.is_fully_inferred is False


@pytest.mark.unit
def test_connector_is_compatible_reads_both_object_and_dict_connector_rows():
    class _Row:
        type = "CCS2"

    assert connector_compat.connector_is_compatible("CCS", station_connectors=[_Row()]) is True
    assert connector_compat.connector_is_compatible(
        "CCS", station_connectors=[{"type": "ccs combo 2"}]) is True
    assert connector_compat.connector_is_compatible(
        "CHAdeMO", station_connectors=[{"type": "CCS2"}]) is False
    assert connector_compat.connector_is_compatible("CCS") is False   # nothing to match


# ===========================================================================
# api/services/service_area.py
# ===========================================================================
@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    (None, 12.5),          # unset
    ("", 12.5),
    ("   ", 12.5),
    ("not-a-number", 12.5),  # malformed: fall back, never crash at import time
    ("-6.5deg", 12.5),
    ("-6.5", -6.5),
    ("  7  ", 7.0),
    ("1e2", 100.0),
])
def test_env_float_falls_back_to_the_default_for_anything_unparseable(
        monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("ROUTE_SERVICE_AREA_TEST", raising=False)
    else:
        monkeypatch.setenv("ROUTE_SERVICE_AREA_TEST", raw)
    assert service_area._env_float("ROUTE_SERVICE_AREA_TEST", 12.5) == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    (None, True), ("", True), ("   ", True),          # unset -> default
    ("1", True), ("true", True), ("TRUE", True), ("Yes", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("off", False),
    ("maybe", False), ("2", False),
])
def test_env_bool_only_accepts_the_documented_truthy_spellings(
        monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("ROUTE_SERVICE_AREA_TEST_BOOL", raising=False)
    else:
        monkeypatch.setenv("ROUTE_SERVICE_AREA_TEST_BOOL", raw)
    assert service_area._env_bool("ROUTE_SERVICE_AREA_TEST_BOOL", True) is expected
    assert service_area._env_bool("ROUTE_SERVICE_AREA_TEST_BOOL_MISSING", False) is False


@pytest.mark.unit
@pytest.mark.parametrize("lat,lon,inside", [
    (-6.2088, 106.8456, True),    # Jakarta
    (-6.9175, 107.6191, True),    # Bandung
    (-8.6500, 115.2167, True),    # Denpasar
    (3.5952, 98.6722, True),      # Medan
    (-33.8688, 151.2093, False),  # Sydney
    (-31.9523, 115.8613, False),  # Perth
    (35.6762, 139.6503, False),   # Tokyo -- inside the longitude band, north of it
])
def test_the_service_area_gate_accepts_indonesia_and_rejects_the_rest(lat, lon, inside):
    assert service_area.contains(lat, lon) is inside


@pytest.mark.unit
def test_the_service_area_edges_are_inclusive():
    assert service_area.contains(service_area.SERVICE_AREA_SOUTH,
                                 service_area.SERVICE_AREA_WEST) is True
    assert service_area.contains(service_area.SERVICE_AREA_NORTH,
                                 service_area.SERVICE_AREA_EAST) is True
    assert service_area.contains(service_area.SERVICE_AREA_SOUTH - 0.001,
                                 service_area.SERVICE_AREA_WEST) is False
    assert service_area.contains(service_area.SERVICE_AREA_NORTH,
                                 service_area.SERVICE_AREA_EAST + 0.001) is False


@pytest.mark.unit
def test_disabling_enforcement_accepts_every_coordinate_on_earth(monkeypatch):
    """The documented escape hatch for a deployment that genuinely serves everywhere."""
    assert service_area.contains(-33.8688, 151.2093) is False
    monkeypatch.setattr(service_area, "SERVICE_AREA_ENFORCED", False)
    assert service_area.contains(-33.8688, 151.2093) is True
    assert service_area.contains(89.0, -179.0) is True
    assert service_area.outside_fields([("origin", -33.8, 151.2)]) == []
    assert service_area.describe()["enforced"] is False


@pytest.mark.unit
def test_a_narrowed_box_is_honoured_edge_by_edge(monkeypatch):
    monkeypatch.setattr(service_area, "SERVICE_AREA_EAST", 107.0)
    assert service_area.contains(-6.2088, 106.8456) is True    # Jakarta survives
    assert service_area.contains(-6.9175, 107.6191) is False   # Bandung is cut off
    assert service_area.rejection_message().endswith("94.6 to 107.0)")


@pytest.mark.unit
def test_outside_fields_names_only_the_offending_points():
    named = [("origin_location", -6.2088, 106.8456),
             ("destination_location", -33.8688, 151.2093),
             ("current_location", 35.6762, 139.6503)]
    assert service_area.outside_fields(named) == ["destination_location", "current_location"]
    assert service_area.outside_fields([]) == []


@pytest.mark.unit
def test_the_advisory_wording_states_a_fact_and_never_claims_invalid_input():
    msg = service_area.advisory_message(["current_location", "destination_location"])
    assert "current location and destination location" in msg
    assert "Battery warnings continue" in msg
    assert "invalid" not in msg.lower()
    assert service_area.advisory_message([]).startswith("Your this route is outside")


@pytest.mark.unit
def test_describe_echoes_exactly_the_constants_the_gate_uses():
    d = service_area.describe()
    assert d == {
        "name": service_area.SERVICE_AREA_NAME,
        "south": service_area.SERVICE_AREA_SOUTH,
        "west": service_area.SERVICE_AREA_WEST,
        "north": service_area.SERVICE_AREA_NORTH,
        "east": service_area.SERVICE_AREA_EAST,
        "enforced": service_area.SERVICE_AREA_ENFORCED,
    }
    assert service_area.contains(d["south"], d["west"]) is True

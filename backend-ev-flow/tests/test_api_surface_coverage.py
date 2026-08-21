"""HTTP-surface tests for api/main.py: the endpoints and error branches that the
existing suite never reaches.

Scope on purpose: station lookup / GeoJSON / paging, the meta look-ups, the two
Dijkstra endpoints (including their 404/422/503 branches), the EV-model
catalogue and the CORS policy. Money, auth and route-planning have their own
files and are not duplicated here.

No test here touches the network: routing runs against a 4-node synthetic
GraphML written to tmp_path, and the geocoding upstream is never called (the
service methods are replaced by ones that raise).

Three tests are xfail: they assert what the API *should* answer and currently
document real defects (see the reasons on each).
"""
import uuid

import pytest

from tests.conftest import requires_db

pytest.importorskip("fastapi")
nx = pytest.importorskip("networkx")

from fastapi.testclient import TestClient   # noqa: E402
from sqlalchemy import text                 # noqa: E402

BBOX_HINT = "bbox must be 'minLon,minLat,maxLon,maxLat'"

# A line of four nodes ~1 km apart through Jakarta. Mirrors the real deployment,
# where the graph covers Jabodetabek only.
GRAPH_NODES = {1: (106.80, -6.20), 2: (106.81, -6.20), 3: (106.82, -6.20),
               4: (106.83, -6.20)}
GRAPH_EDGES = [(1, 2), (2, 3), (3, 4)]

# Same graph plus an edgeless island node next to Jambi: anything snapping there
# is genuinely unreachable by road.
ISLAND_NODES = {**GRAPH_NODES, 9: (103.60, -1.63)}

FAR_AWAY_LAT, FAR_AWAY_LON = -1.628243, 103.60583   # Jambi, ~1050 km from Jakarta


def _write_graph(path, nodes, edges):
    g = nx.MultiDiGraph()
    for n, (x, y) in nodes.items():
        g.add_node(n, x=x, y=y)
    for u, v in edges:
        g.add_edge(u, v, length=1000.0, travel_time=60.0)
        g.add_edge(v, u, length=1000.0, travel_time=60.0)
    nx.write_graphml(g, path)
    return path


@pytest.fixture
def client():
    from api import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def road_graph(tmp_path, monkeypatch):
    """Point the routing module at a tiny synthetic graph, and drop it afterwards."""
    from api import routing
    monkeypatch.setattr(routing, "GRAPH_PATH",
                        _write_graph(tmp_path / "tiny.graphml", GRAPH_NODES, GRAPH_EDGES))
    routing.reload()
    yield routing
    routing.reload()          # never leak a cached toy graph into another test


@pytest.fixture
def road_graph_with_island(tmp_path, monkeypatch):
    """Same toy graph plus an unconnected node, so 'unreachable' is reproducible."""
    from api import routing
    monkeypatch.setattr(routing, "GRAPH_PATH",
                        _write_graph(tmp_path / "island.graphml", ISLAND_NODES, GRAPH_EDGES))
    routing.reload()
    yield routing
    routing.reload()


@pytest.fixture
def empty_road_graph(tmp_path, monkeypatch):
    """A GraphML with no nodes: exactly what an un-built road graph looks like."""
    from api import routing
    monkeypatch.setattr(routing, "GRAPH_PATH",
                        _write_graph(tmp_path / "empty.graphml", {}, []))
    routing.reload()
    yield routing
    routing.reload()


def _insert_station(lat: float, lon: float, name: str | None = None, power_kw=None) -> str:
    """Insert a throwaway station row; returns its id."""
    from api.db import engine
    sid = "test-surface-" + uuid.uuid4().hex[:10]
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO stations (id, geom, name, sources, power_kw)
            VALUES (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, ARRAY['osm'], :power)
        """), {"id": sid, "lat": lat, "lon": lon,
               "name": name or f"Surface Test {sid}", "power": power_kw})
    return sid


def _delete_stations(*ids: str) -> None:
    from api.db import engine
    with engine.begin() as c:
        c.execute(text("DELETE FROM stations WHERE id = ANY(:ids)"), {"ids": list(ids)})


# --------------------------------------------------------------------- /health
def test_health_reports_version_and_station_count(client):
    from api import __version__
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert isinstance(body["stations_loaded"], int) and body["stations_loaded"] >= 0


def test_health_stays_up_and_reports_zero_when_the_station_count_fails(client, monkeypatch):
    """Liveness must not depend on the database (DEPLOY.md: 'stations_loaded: 0')."""
    from api import stations_repo

    def boom():
        raise RuntimeError("database is down")

    monkeypatch.setattr(stations_repo, "count", boom)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["stations_loaded"] == 0
    assert r.json()["status"] == "ok"


# ----------------------------------------------------------------------- bbox
@pytest.mark.parametrize("bad", ["1,2,3", "1,2,3,4,5", "a,b,c,d", "106.5,-6.6,107.1,"])
@pytest.mark.parametrize("path", ["/api/v1/stations", "/api/v1/stations.geojson"])
def test_malformed_bbox_is_rejected_with_the_expected_hint(client, path, bad):
    r = client.get(path, params={"bbox": bad})
    assert r.status_code == 422
    assert r.json()["detail"] == BBOX_HINT


@requires_db
def test_empty_bbox_is_ignored_rather_than_rejected(client):
    """`?bbox=` (the picker cleared the map filter) must behave like no bbox."""
    unfiltered = client.get("/api/v1/stations", params={"limit": 1}).json()
    blank = client.get("/api/v1/stations", params={"limit": 1, "bbox": ""}).json()
    assert blank["total"] == unfiltered["total"]


# ------------------------------------------------------- /api/v1/stations/{id}
@requires_db
def test_get_station_by_id_matches_the_list_representation(client):
    listed = client.get("/api/v1/stations", params={"limit": 1}).json()["items"][0]
    one = client.get(f"/api/v1/stations/{listed['id']}")
    assert one.status_code == 200
    body = one.json()
    assert body["id"] == listed["id"]
    assert body["name"] == listed["name"]
    assert body["latitude"] == listed["latitude"]
    assert body["longitude"] == listed["longitude"]
    assert body["sources"] == listed["sources"]
    assert body["connectors"] == listed["connectors"]
    # distance_km is a /nearby-only field and must not leak into a direct fetch
    assert body["distance_km"] is None


@requires_db
def test_get_station_unknown_id_is_404_and_names_the_id(client):
    r = client.get("/api/v1/stations/no-such-station-id")
    assert r.status_code == 404
    assert r.json()["detail"] == "station 'no-such-station-id' not found"


# -------------------------------------------------- /api/v1/stations paging
@requires_db
def test_station_paging_is_stable_and_offset_past_the_end_is_empty(client):
    page1 = client.get("/api/v1/stations", params={"limit": 5, "offset": 0}).json()
    page2 = client.get("/api/v1/stations", params={"limit": 5, "offset": 5}).json()
    assert page1["limit"] == 5 and page1["offset"] == 0
    assert page2["offset"] == 5
    assert page1["total"] == page2["total"]
    ids1 = [s["id"] for s in page1["items"]]
    ids2 = [s["id"] for s in page2["items"]]
    assert ids1 == sorted(ids1)                       # documented ORDER BY id
    assert set(ids1).isdisjoint(ids2)                 # no overlap between pages
    assert ids1[-1] < ids2[0]

    past_end = client.get("/api/v1/stations",
                          params={"limit": 5, "offset": page1["total"] + 10}).json()
    assert past_end["items"] == []
    assert past_end["total"] == page1["total"]        # total is the unpaged count


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1001}, {"offset": -1},
                                    {"min_power": -1}])
def test_station_paging_bounds_are_enforced(client, params):
    r = client.get("/api/v1/stations", params=params)
    assert r.status_code == 422
    bad_field = next(iter(params))
    assert any(bad_field in d["loc"] for d in r.json()["detail"])


# ------------------------------------------------ /api/v1/stations.geojson
@requires_db
def test_geojson_features_are_rfc7946_and_carry_station_properties(client):
    body = client.get("/api/v1/stations.geojson", params={"limit": 3}).json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 3
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        lon, lat = feature["geometry"]["coordinates"]      # GeoJSON is [lon, lat]
        assert -180 <= lon <= 180 and -90 <= lat <= 90
        assert 90 < lon < 145 and -12 < lat < 7            # Indonesia, so lon >> lat
        props = feature["properties"]
        # coordinates live in `geometry`; duplicating them in properties was the bug
        assert "latitude" not in props and "longitude" not in props
        assert "distance_km" not in props
        assert props["id"] and "sources" in props and "connector_types" in props

    # geometry agrees with the same station fetched through the JSON endpoint
    first = body["features"][0]
    station = client.get(f"/api/v1/stations/{first['properties']['id']}").json()
    assert first["geometry"]["coordinates"] == [station["longitude"], station["latitude"]]


@requires_db
def test_geojson_honours_the_bbox_and_name_filters(client):
    minlon, minlat, maxlon, maxlat = 106.80, -6.25, 106.85, -6.20
    body = client.get("/api/v1/stations.geojson",
                      params={"bbox": f"{minlon},{minlat},{maxlon},{maxlat}", "limit": 200}).json()
    assert body["features"], "expected seeded Jakarta stations inside this bbox"
    for feature in body["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert minlon <= lon <= maxlon and minlat <= lat <= maxlat

    named = client.get("/api/v1/stations.geojson", params={"q": "SPKLU", "limit": 50}).json()
    assert named["features"]
    assert all("spklu" in f["properties"]["name"].casefold() for f in named["features"])


@requires_db
def test_geojson_limit_caps_the_feature_count(client):
    total = client.get("/api/v1/stations", params={"limit": 1}).json()["total"]
    assert total > 2
    body = client.get("/api/v1/stations.geojson", params={"limit": 2}).json()
    assert len(body["features"]) == 2


# ------------------------------------------------------------ meta look-ups
@requires_db
def test_stats_agrees_with_the_individual_lookup_endpoints(client):
    stats = client.get("/api/v1/stats").json()
    assert stats["total"] == client.get("/health").json()["stations_loaded"]
    assert stats["total"] == client.get("/api/v1/stations", params={"limit": 1}).json()["total"]

    sources = client.get("/api/v1/sources").json()
    assert stats["by_source"] == sources
    assert {s["source"] for s in sources} <= {"pln_spklu", "open_charge_map", "osm"}
    # a station may appear in several sources, so the per-source counts over-count
    assert sum(s["count"] for s in sources) >= stats["total"]
    assert all(s["count"] > 0 for s in sources)

    provinces = client.get("/api/v1/provinces").json()
    assert stats["by_province"] == provinces[:40]      # stats truncates the tail
    counts = [p["count"] for p in provinces]
    assert counts == sorted(counts, reverse=True)
    assert sum(counts) <= stats["total"]               # province is nullable

    assert stats["with_power_kw"] <= stats["total"]
    assert stats["power_kw_min"] <= stats["power_kw_mean"] <= stats["power_kw_max"]


@requires_db
def test_cities_lookup_filters_by_province(client):
    provinces = client.get("/api/v1/provinces").json()
    top = provinces[0]["name"]
    all_cities = client.get("/api/v1/cities").json()
    in_province = client.get("/api/v1/cities", params={"province": top}).json()
    assert in_province, f"expected cities in {top}"

    all_by_name = {c["name"]: c["count"] for c in all_cities}
    for city in in_province:
        assert city["name"] in all_by_name
        assert city["count"] <= all_by_name[city["name"]]
    assert sum(c["count"] for c in in_province) <= provinces[0]["count"]

    # province match is case-insensitive, and an unknown one is empty (not a 500)
    assert client.get("/api/v1/cities", params={"province": top.lower()}).json() == in_province
    assert client.get("/api/v1/cities", params={"province": "Atlantis"}).json() == []


@requires_db
def test_connector_lookup_counts_match_what_the_filter_returns(client):
    """The dropdown counts drive the UI; a mismatch mislabels every filter chip."""
    for entry in client.get("/api/v1/connectors").json():
        filtered = client.get("/api/v1/stations",
                              params={"connector_type": entry["name"], "limit": 1}).json()
        assert filtered["total"] == entry["count"], entry["name"]


@requires_db
def test_speed_tier_definitions_are_complete(client):
    tiers = client.get("/api/v1/speed-tiers").json()
    assert [t["id"] for t in tiers] == ["slow", "medium", "fast", "ultra_fast"]
    assert [t["label"] for t in tiers] == ["Slow", "Medium", "Fast", "Ultra-fast"]
    # contiguous, ascending power bands; only the top tier is open-ended
    assert [t["min_kw"] for t in tiers] == [0.0, 7.0, 50.0, 150.0]
    assert [t["max_kw"] for t in tiers] == [7.0, 50.0, 150.0, None]
    assert all(t["count"] >= 0 for t in tiers)


@requires_db
@pytest.mark.xfail(reason=(
    "BUG: /api/v1/speed-tiers counts stations by the station-level speed_tier "
    "(derived from peak power) while /api/v1/stations?speed_tier= filters on the "
    "per-connector speed_tier inside the connectors JSONB. The dropdown therefore "
    "advertises a different number from what selecting it returns "
    "(seeded data: slow 310 vs 394, medium 1891 vs 2054, fast 585 vs 627)."),
    strict=False)
def test_speed_tier_counts_match_what_the_filter_returns(client):
    for tier in client.get("/api/v1/speed-tiers").json():
        filtered = client.get("/api/v1/stations",
                              params={"speed_tier": tier["id"], "limit": 1}).json()
        assert filtered["total"] == tier["count"], tier["id"]


@requires_db
@pytest.mark.xfail(reason=(
    "BUG: stations_repo._filter_clauses interpolates `q` (and `city`) straight into "
    "an ILIKE pattern, so SQL LIKE wildcards typed by the user are honoured instead "
    "of matched literally: searching for 'a_b' also matches 'axb', and a bare '_' or "
    "'%' matches every named station in the table."),
    strict=False)
def test_name_search_treats_like_wildcards_as_literal_text(client):
    token = uuid.uuid4().hex[:8]
    literal = _insert_station(-6.20, 106.80, name=f"Wild_card {token}")
    decoy = _insert_station(-6.21, 106.81, name=f"WildXcard {token}")
    try:
        body = client.get("/api/v1/stations",
                          params={"q": f"Wild_card {token}", "limit": 10}).json()
        assert [s["id"] for s in body["items"]] == [literal]
        assert body["total"] == 1
        # a lone wildcard is a literal character, not "everything"
        assert client.get("/api/v1/stations",
                          params={"q": "_", "limit": 1}).json()["total"] == 0
    finally:
        _delete_stations(literal, decoy)


# -------------------------------------------------------------- /api/v1/route
def test_route_requires_both_origin_coordinates(client):
    for params in ({"dest_lat": -6.2, "dest_lon": 106.8},
                   {"lat": -6.2, "dest_lat": -6.2, "dest_lon": 106.8},
                   {"lon": 106.8, "dest_lat": -6.2, "dest_lon": 106.8}):
        r = client.get("/api/v1/route", params=params)
        assert r.status_code == 422
        assert r.json()["detail"] == "origin 'lat' and 'lon' are required"


def test_route_requires_a_destination_and_says_which_options_exist(client):
    r = client.get("/api/v1/route", params={"lat": -6.2, "lon": 106.8, "dest_lat": -6.2})
    assert r.status_code == 422
    assert r.json()["detail"] == ("provide either 'station_id' or both "
                                  "'dest_lat' and 'dest_lon'")


def test_route_rejects_an_unknown_weight(client):
    r = client.get("/api/v1/route", params={"lat": -6.2, "lon": 106.801,
                                            "dest_lat": -6.2, "dest_lon": 106.829,
                                            "weight": "cheapest"})
    assert r.status_code == 422
    assert any("weight" in d["loc"] for d in r.json()["detail"])


def test_route_returns_404_when_the_destination_is_not_reachable_by_road(
        client, road_graph_with_island):
    r = client.get("/api/v1/route", params={"lat": -6.20, "lon": 106.801,
                                            "dest_lat": FAR_AWAY_LAT, "dest_lon": FAR_AWAY_LON})
    assert r.status_code == 404
    assert r.json()["detail"] == "no drivable route found between the two points"


def test_route_returns_503_when_the_road_graph_is_unavailable(client, empty_road_graph):
    r = client.get("/api/v1/route", params={"lat": -6.20, "lon": 106.801,
                                            "dest_lat": -6.20, "dest_lon": 106.829})
    assert r.status_code == 503
    assert r.json()["detail"].startswith("routing unavailable:")
    assert "road graph has no nodes" in r.json()["detail"]


@requires_db
def test_route_to_a_station_id_uses_the_station_coordinates(client, road_graph):
    sid = _insert_station(-6.20, 106.829)
    try:
        r = client.get("/api/v1/route", params={"lat": -6.20, "lon": 106.801, "station_id": sid})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["destination"]["station_id"] == sid
        assert body["destination"]["lat"] == pytest.approx(-6.20)
        assert body["destination"]["lon"] == pytest.approx(106.829)
        assert body["origin"]["station_id"] is None
        assert body["distance_m"] == pytest.approx(3000.0)     # nodes 1->2->3->4
        assert body["node_count"] == 4
        assert body["geometry"]["coordinates"][0] == [106.80, -6.20]
        assert body["geometry"]["coordinates"][-1] == [106.83, -6.20]
    finally:
        _delete_stations(sid)


@requires_db
def test_route_to_an_unknown_station_id_is_404(client, road_graph):
    r = client.get("/api/v1/route", params={"lat": -6.20, "lon": 106.801,
                                            "station_id": "no-such-station"})
    assert r.status_code == 404
    assert r.json()["detail"] == "station 'no-such-station' not found"


# ------------------------------------------- /api/v1/route/nearest-station
def test_nearest_station_requires_both_origin_coordinates(client):
    r = client.get("/api/v1/route/nearest-station", params={"lat": -6.2})
    assert r.status_code == 422
    assert r.json()["detail"] == "origin 'lat' and 'lon' are required"


def test_nearest_station_ev_model_needs_a_state_of_charge(client):
    r = client.get("/api/v1/route/nearest-station",
                   params={"lat": -6.2, "lon": 106.8, "ev_model_id": "wuling-air-ev"})
    assert r.status_code == 422
    assert r.json()["detail"] == "current_soc is required when ev_model_id is given"


@requires_db   # DB-only catalogue: without ev_models there is no 404, only 503
def test_nearest_station_unknown_ev_model_is_404(client):
    r = client.get("/api/v1/route/nearest-station",
                   params={"lat": -6.2, "lon": 106.8,
                           "ev_model_id": "not-a-real-model", "current_soc": 50})
    assert r.status_code == 404
    assert r.json()["detail"] == "ev model 'not-a-real-model' not found"


def test_nearest_station_model_without_a_range_asks_for_max_range_km(client, monkeypatch):
    from api import evmodels
    monkeypatch.setattr(evmodels, "get",
                        lambda mid: {"id": mid, "name": "Rangeless", "range_km": None})
    r = client.get("/api/v1/route/nearest-station",
                   params={"lat": -6.2, "lon": 106.8,
                           "ev_model_id": "rangeless", "current_soc": 50})
    assert r.status_code == 422
    assert r.json()["detail"] == ("range unknown for ev model 'rangeless'; "
                                  "pass max_range_km instead")


def test_nearest_station_with_no_stations_loaded_is_404(client, monkeypatch):
    from api import stations_repo
    monkeypatch.setattr(stations_repo, "routing_coords", lambda *a, **k: [])
    r = client.get("/api/v1/route/nearest-station", params={"lat": -6.2, "lon": 106.8})
    assert r.status_code == 404
    assert r.json()["detail"] == "no charging stations loaded"


def test_nearest_station_returns_503_when_the_road_graph_is_unavailable(
        client, monkeypatch, empty_road_graph):
    from api import stations_repo
    monkeypatch.setattr(stations_repo, "routing_coords",
                        lambda *a, **k: [{"id": "s1", "latitude": -6.20, "longitude": 106.80}])
    r = client.get("/api/v1/route/nearest-station", params={"lat": -6.2, "lon": 106.8})
    assert r.status_code == 503
    assert "road graph has no nodes" in r.json()["detail"]


def test_nearest_station_404s_when_no_station_is_reachable_by_road(
        client, monkeypatch, road_graph_with_island):
    """Every candidate sits on the isolated node 9, so nothing is road-reachable."""
    from api import stations_repo
    monkeypatch.setattr(stations_repo, "routing_coords",
                        lambda *a, **k: [{"id": "far-1", "latitude": FAR_AWAY_LAT,
                                          "longitude": FAR_AWAY_LON}])
    r = client.get("/api/v1/route/nearest-station", params={"lat": -6.20, "lon": 106.801})
    assert r.status_code == 404
    assert r.json()["detail"] == "no charging station reachable by road from this point"


@requires_db
def test_nearest_station_404s_when_the_resolved_station_row_is_missing(
        client, monkeypatch, road_graph):
    """Routing knows an id the station table does not: a 404 beats a 500."""
    from api import stations_repo
    monkeypatch.setattr(stations_repo, "routing_coords",
                        lambda *a, **k: [{"id": "ghost-station",
                                          "latitude": -6.20, "longitude": 106.829}])
    r = client.get("/api/v1/route/nearest-station", params={"lat": -6.20, "lon": 106.801})
    assert r.status_code == 404
    assert r.json()["detail"] == "nearest station resolved by routing but not found"


@requires_db
def test_nearest_station_response_is_self_consistent(client, road_graph):
    """Runs against the real station table (repo.routing_coords), toy road graph."""
    total = client.get("/api/v1/stations", params={"limit": 1}).json()["total"]
    r = client.get("/api/v1/route/nearest-station",
                   params={"lat": -6.20, "lon": 106.801, "weight": "travel_time"})
    assert r.status_code == 200, r.text
    body = r.json()

    assert 0 < body["candidates_considered"] <= total
    assert body["range_used_km"] is None
    assert body["within_range"] is True             # no range given -> unconstrained
    route = body["route"]
    assert route["weight"] == "travel_time"
    assert route["distance_m"] >= 0 and route["duration_s"] >= 0
    # one node means origin and station snapped to the same road node -> zero-length
    assert (route["duration_s"] > 0) == (route["node_count"] > 1)
    assert route["geometry"]["type"] == "LineString"
    assert len(route["geometry"]["coordinates"]) >= 2
    assert route["destination"]["station_id"] == body["station"]["id"]

    station = body["station"]
    # distance_km on the station mirrors the road distance, rounded to 3 dp
    assert station["distance_km"] == pytest.approx(round(route["distance_m"] / 1000.0, 3))
    assert route["destination"]["lat"] == pytest.approx(station["latitude"])
    assert route["destination"]["lon"] == pytest.approx(station["longitude"])
    # and it is a real row, not something routing invented
    assert client.get(f"/api/v1/stations/{station['id']}").status_code == 200


@requires_db
def test_nearest_station_flags_a_station_beyond_the_remaining_range(
        client, monkeypatch, road_graph):
    sid = _insert_station(-6.20, 106.829)
    from api import stations_repo
    coords = [{"id": sid, "latitude": -6.20, "longitude": 106.829}]
    try:
        monkeypatch.setattr(stations_repo, "routing_coords", lambda *a, **k: coords)
        r = client.get("/api/v1/route/nearest-station",
                       params={"lat": -6.20, "lon": 106.801, "max_range_km": 1.0})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["station"]["id"] == sid
        assert body["range_used_km"] == 1.0
        assert body["route"]["distance_m"] == pytest.approx(3000.0)   # 3 km > 1 km
        assert body["within_range"] is False

        generous = client.get("/api/v1/route/nearest-station",
                              params={"lat": -6.20, "lon": 106.801, "max_range_km": 50.0}).json()
        assert generous["within_range"] is True
        assert generous["range_used_km"] == 50.0
    finally:
        _delete_stations(sid)


@requires_db
def test_nearest_station_derives_the_range_from_ev_model_and_soc(
        client, monkeypatch, road_graph):
    sid = _insert_station(-6.20, 106.829)
    from api import evmodels, stations_repo
    coords = [{"id": sid, "latitude": -6.20, "longitude": 106.829}]
    monkeypatch.setattr(stations_repo, "routing_coords", lambda *a, **k: coords)
    try:
        model = next(m for m in evmodels.load() if m.get("range_km"))
        expected = evmodels.remaining_range_km(model["range_km"], 50.0)
        body = client.get("/api/v1/route/nearest-station",
                          params={"lat": -6.20, "lon": 106.801, "max_range_km": 999.0,
                                  "ev_model_id": model["id"], "current_soc": 50}).json()
        # the derived range overrides max_range_km, as documented
        assert body["range_used_km"] == pytest.approx(expected)
        assert body["within_range"] is (3.0 <= expected)
    finally:
        _delete_stations(sid)


@requires_db
@pytest.mark.xfail(reason=(
    "BUG: routing.nearest_station_route ranks candidates by road cost to the node "
    "each station SNAPS to and ignores how far the station is from that node. The "
    "road graph covers Jabodetabek only while stations_repo.routing_coords() returns "
    "the national dataset, so a station ~1000 km outside the graph is reported as the "
    "nearest one 'reachable by road' and within_range compares the range against the "
    "road leg alone -- a driver with 10 km left is told a Jambi charger is in reach. "
    "route.destination.snap_distance_km exposes the gap but nothing acts on it."),
    strict=False)
def test_nearest_station_does_not_claim_an_unreachable_station_is_within_range(
        client, monkeypatch, road_graph):
    sid = _insert_station(FAR_AWAY_LAT, FAR_AWAY_LON, name="Far away charger")
    from api import stations_repo
    coords = [{"id": sid, "latitude": FAR_AWAY_LAT, "longitude": FAR_AWAY_LON}]
    monkeypatch.setattr(stations_repo, "routing_coords", lambda *a, **k: coords)
    try:
        r = client.get("/api/v1/route/nearest-station",
                       params={"lat": -6.20, "lon": 106.801, "max_range_km": 10.0})
        if r.status_code == 404:
            return                       # refusing to answer is a valid fix too
        body = r.json()
        assert body["route"]["destination"]["snap_distance_km"] > 100
        assert body["within_range"] is False
    finally:
        _delete_stations(sid)


# ------------------------------------------------------------- /api/v1/ev-models
@requires_db
def test_ev_model_paging_slices_a_stable_catalogue(client):
    everything = client.get("/api/v1/ev-models", params={"limit": 500}).json()
    total = everything["total"]
    assert total > 1 and len(everything["items"]) == min(total, 500)

    first = client.get("/api/v1/ev-models", params={"limit": 1, "offset": 0}).json()
    second = client.get("/api/v1/ev-models", params={"limit": 1, "offset": 1}).json()
    assert first["total"] == second["total"] == total
    assert first["limit"] == 1 and second["offset"] == 1
    assert first["items"][0]["id"] == everything["items"][0]["id"]
    assert second["items"][0]["id"] == everything["items"][1]["id"]
    assert first["items"][0]["id"] != second["items"][0]["id"]

    past_end = client.get("/api/v1/ev-models", params={"limit": 5, "offset": total}).json()
    assert past_end["items"] == []
    assert past_end["total"] == total          # total is the unpaged count


@requires_db
def test_ev_model_search_is_case_insensitive_and_narrows_the_total(client):
    everything = client.get("/api/v1/ev-models", params={"limit": 500}).json()
    name = everything["items"][0]["name"]
    term = name.split()[0]

    hits = client.get("/api/v1/ev-models", params={"q": term.lower(), "limit": 500}).json()
    assert 0 < hits["total"] <= everything["total"]
    assert all(term.casefold() in m["name"].casefold() for m in hits["items"])
    # total must describe the FILTERED set, not the whole catalogue
    assert hits["total"] == len(hits["items"])
    assert client.get("/api/v1/ev-models",
                      params={"q": term.upper(), "limit": 500}).json()["total"] == hits["total"]

    assert client.get("/api/v1/ev-models",
                      params={"q": "zzz-no-such-vehicle"}).json() == {
        "total": 0, "limit": 100, "offset": 0, "items": []}


@requires_db
def test_ev_model_unknown_id_is_404_and_names_it(client):
    r = client.get("/api/v1/ev-models/not-a-real-model")
    assert r.status_code == 404
    assert r.json()["detail"] == "ev model 'not-a-real-model' not found"


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
def test_ev_model_paging_bounds_are_enforced(client, params):
    r = client.get("/api/v1/ev-models", params=params)
    assert r.status_code == 422
    assert any(next(iter(params)) in d["loc"] for d in r.json()["detail"])


# --------------------------------------------------------------------- CORS
# These three used to be skipped unless CORS_ALLOW_ORIGINS was unset, because the
# API defaulted to "*" and they asserted that wildcard verbatim. The default is
# now an explicit allow-list (api/cors_policy.py), so that guard would have
# skipped them permanently and quietly dropped preflight from the suite. They are
# rewritten against whatever origin the running configuration actually allows,
# which keeps them meaningful in every deployment -- wildcard included.
def _cors_probe_origin() -> str:
    """An origin this deployment allows, so a preflight can be exercised at all."""
    from api import main
    origins = main._allow_origins
    return "https://app.example" if origins == ["*"] else origins[0]


def _expected_allow_origin(origin: str) -> str:
    """What CORSMiddleware echoes back: the wildcard, or the caller's own origin."""
    from api import main
    return "*" if main._allow_origins == ["*"] else origin


def test_cors_allows_the_browser_verbs_the_frontend_uses(client):
    origin = _cors_probe_origin()
    r = client.options("/api/v1/stations",
                       headers={"Origin": origin,
                                "Access-Control-Request-Method": "PATCH"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == _expected_allow_origin(origin)
    allowed = {m.strip() for m in r.headers["access-control-allow-methods"].split(",")}
    assert allowed == {"GET", "POST", "PUT", "PATCH", "DELETE"}


def test_cors_rejects_a_verb_the_api_does_not_expose(client):
    r = client.options("/api/v1/stations",
                       headers={"Origin": _cors_probe_origin(),
                                "Access-Control-Request-Method": "TRACE"})
    assert r.status_code == 400
    assert "Disallowed CORS method" in r.text


def test_cors_preflight_from_an_unvetted_origin_is_refused(client):
    """Only meaningful once the default stopped being "*"."""
    from api import main
    if main._allow_origins == ["*"]:
        pytest.skip("this deployment deliberately allows every origin")
    r = client.options("/api/v1/stations",
                       headers={"Origin": "https://evil.example",
                                "Access-Control-Request-Method": "PATCH"})
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_cors_header_is_present_on_a_plain_get(client):
    origin = _cors_probe_origin()
    r = client.get("/health", headers={"Origin": origin})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == _expected_allow_origin(origin)


# ------------------------------------------------------- geocoding failure mapping
def test_geocoding_search_maps_an_upstream_failure_to_502(client, monkeypatch):
    from api import rate_limit
    from api.services import geocoding_service

    async def boom(self, **kwargs):
        raise RuntimeError("nominatim exploded")

    rate_limit.reset()
    monkeypatch.setattr(geocoding_service.GeocodingService, "search", boom)
    try:
        r = client.get("/api/v1/geocoding/search", params={"q": "Bandung"})
        assert r.status_code == 502
        assert r.json()["detail"] == "geocoding provider unavailable"
    finally:
        rate_limit.reset()


def test_geocoding_reverse_maps_an_upstream_failure_to_502(client, monkeypatch):
    from api import rate_limit
    from api.services import geocoding_service

    async def boom(self, **kwargs):
        raise RuntimeError("nominatim exploded")

    rate_limit.reset()
    monkeypatch.setattr(geocoding_service.GeocodingService, "reverse_search", boom)
    try:
        r = client.get("/api/v1/geocoding/reverse", params={"lat": -6.2088, "lon": 106.8456})
        assert r.status_code == 502
        assert r.json()["detail"] == "geocoding provider unavailable"
    finally:
        rate_limit.reset()


@pytest.mark.parametrize("path,method,params", [
    ("/api/v1/geocoding/search", "search", {"q": "Bandung"}),
    ("/api/v1/geocoding/reverse", "reverse_search", {"lat": -6.2088, "lon": 106.8456}),
])
def test_geocoding_passes_a_deliberate_http_error_through_untouched(
        client, monkeypatch, path, method, params):
    """A 4xx the service raised on purpose must not be rewritten as a 502."""
    from fastapi import HTTPException

    from api import rate_limit
    from api.services import geocoding_service

    async def refuse(self, **kwargs):
        raise HTTPException(429, "too many geocoding requests; try again in 60s")

    rate_limit.reset()
    monkeypatch.setattr(geocoding_service.GeocodingService, method, refuse)
    try:
        r = client.get(path, params=params)
        assert r.status_code == 429
        assert r.json()["detail"] == "too many geocoding requests; try again in 60s"
    finally:
        rate_limit.reset()


def test_geocoding_search_validates_the_query_length(client):
    from api import rate_limit
    rate_limit.reset()
    try:
        r = client.get("/api/v1/geocoding/search", params={"q": "a"})
        assert r.status_code == 422
        assert any("q" in d["loc"] for d in r.json()["detail"])
    finally:
        rate_limit.reset()


def test_station_response_carries_every_column_the_repo_selects():
    """_row_to_station names each field by hand, so a new column in
    stations_repo._COLS is silently dropped unless it is added there too. That
    is how total_connectors/available_connectors shipped as None after the query
    was already returning them."""
    import re
    from api import stations_repo
    from api.models import Station

    selected = set(re.findall(r"AS (\w+)", stations_repo._COLS))
    selected |= {c.strip() for line in stations_repo._COLS.splitlines()
                 for c in line.split(",")
                 if c.strip() and c.strip().isidentifier()}
    known = set(Station.model_fields)
    missing = {c for c in selected if c in known} - _station_fields_passed_by_the_mapper()
    assert not missing, f"_row_to_station drops columns the query returns: {sorted(missing)}"


def _station_fields_passed_by_the_mapper() -> set:
    import inspect, re
    from api.main import _row_to_station
    src = inspect.getsource(_row_to_station)
    return set(re.findall(r"^\s*(\w+)=", src, re.M)) | set(re.findall(r"[( ](\w+)=", src))

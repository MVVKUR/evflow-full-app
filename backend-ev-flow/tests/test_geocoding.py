"""Tests for the geocoding destination-search endpoints.

Both endpoints proxy nominatim.openstreetmap.org. They are deliberately
UNAUTHENTICATED: EVFlow is a permanent demo whose demo password ships in the web
bundle, so a token proves nothing and would only break the destination picker.
What protects the deployment is volume control, because the real failure mode is
OpenStreetMap banning our egress IP and silently killing destination search for
everyone: a per-IP budget, a global budget, a response cache, and a minimum
interval between outbound calls. They must also never let a full-precision user
coordinate reach an upstream URL or a log line (AC 2.3.2).
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from tests.conftest import requires_db

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402

from api import rate_limit                  # noqa: E402
from api.main import app                    # noqa: E402
from api.services import geocoding_service, service_area  # noqa: E402

client = TestClient(app)

JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"          # >= 32 chars

# Closed port: the upstream call fails fast, so tests never touch the network
# and we still exercise the failure path.
UNREACHABLE_UPSTREAM = "http://127.0.0.1:9"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    geocoding_service._CACHE.clear()
    geocoding_service._REVERSE_CACHE.clear()
    geocoding_service._SESSION_KEYS.clear()
    rate_limit.reset()
    monkeypatch.setattr(geocoding_service, "NOMINATIM_BASE_URL", UNREACHABLE_UPSTREAM)
    yield
    geocoding_service._CACHE.clear()
    geocoding_service._REVERSE_CACHE.clear()
    geocoding_service._SESSION_KEYS.clear()
    rate_limit.reset()


class FakeClock:
    """Stand-in for the `time` module, so a test can advance time instead of sleeping."""

    def __init__(self, start: float = 1_700_000_000.0):
        self.now = float(start)

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


# ------------------------------------------------------- open by design, not by accident
def test_geocoding_endpoints_are_public():
    """No token required: a demo password in the bundle makes auth theatre here."""
    assert client.get("/api/v1/geocoding/search?q=Bandung&limit=5").status_code == 200
    assert client.get("/api/v1/geocoding/reverse?lat=-6.2088&lon=106.8456").status_code == 200


def test_geocoding_ignores_a_bogus_bearer_rather_than_rejecting_it():
    """A stale or malformed token must not lock a driver out of destination search."""
    for header in ({"Authorization": "Basic abc"}, {"Authorization": "Bearer not-a-jwt"}):
        assert client.get("/api/v1/geocoding/search?q=Bandung",
                          headers=header).status_code == 200
        assert client.get("/api/v1/geocoding/reverse?lat=-6.2&lon=106.8",
                          headers=header).status_code == 200


# --------------------------------------------------------------- behaviour
@requires_db
def test_geocoding_search_endpoint(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    from api import main
    with TestClient(main.app) as c:
        response = c.get("/api/v1/geocoding/search?q=Bandung&lat=-6.2088&lon=106.8456&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "items" in data
        assert len(data["items"]) <= 5
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "label" in item
            assert "latitude" in item
            assert "longitude" in item
            assert "type" in item


@requires_db
def test_reverse_geocoding_degrades_cleanly_when_upstream_is_down(monkeypatch):
    """An unreachable Nominatim must not surface as a traceback/500."""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    from api import main
    with TestClient(main.app) as c:
        # far from every known place and (on a seeded DB) from every station
        resp = c.get("/api/v1/geocoding/reverse?lat=-8.9&lon=115.9")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"label", "address", "city"}


def test_geocoding_rate_limited_per_caller(monkeypatch):
    monkeypatch.setattr(rate_limit, "GEOCODING_RATE_LIMIT_REQUESTS", 3)
    codes = [client.get("/api/v1/geocoding/reverse?lat=-6.2088&lon=106.8456").status_code
             for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429]


def test_geocoding_global_budget_caps_every_caller_combined(monkeypatch):
    """The per-IP budget alone is not enough: many callers must not add up."""
    monkeypatch.setattr(rate_limit, "GEOCODING_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "GEOCODING_GLOBAL_RATE_LIMIT_REQUESTS", 2)
    codes = [client.get("/api/v1/geocoding/reverse?lat=-6.2088&lon=106.8456").status_code
             for _ in range(4)]
    assert codes[:2] == [200, 200]
    assert codes[2:] == [429, 429], "global budget must bite even under the per-IP limit"


def test_outbound_calls_are_spaced_to_respect_nominatim_policy(monkeypatch):
    """We must throttle what we SEND, not just what callers may ask of us."""
    monkeypatch.setattr(geocoding_service, "NOMINATIM_MIN_INTERVAL_SECONDS", 0.05)
    geocoding_service._last_upstream_call = 0.0

    async def _three_slots():
        import time as _t
        start = _t.monotonic()
        for _ in range(3):
            await geocoding_service._await_upstream_slot()
        return _t.monotonic() - start

    # three slots at 50 ms apart: the first is free, the next two must wait
    assert asyncio.run(_three_slots()) >= 0.09


# --------------------------------------------------------------- privacy (AC 2.3.2)
def test_round_coord_matches_route_plan_precision():
    assert geocoding_service.round_coord(-6.20881234) == -6.2088
    assert geocoding_service.round_coord(106.84561234) == 106.8456
    assert geocoding_service.round_coord(
        -6.20881234, geocoding_service.REVERSE_COORD_PRECISION_DP) == -6.209


def test_reverse_search_never_logs_raw_coordinates(caplog):
    raw_lat, raw_lon = -8.987654321, 115.123456789
    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(
            geocoding_service.GeocodingService().reverse_search(raw_lat, raw_lon))

    logged = "\n".join(r.getMessage() for r in caplog.records)
    for fragment in ("8.987654", "115.123456", str(raw_lat), str(raw_lon)):
        assert fragment not in logged
    # the fallback label is coarsened too
    assert "8.987654" not in result["label"]


def test_upstream_request_carries_contact_user_agent_and_rounded_coords(monkeypatch):
    monkeypatch.setenv("NOMINATIM_CONTACT_EMAIL", "ops@example.test")
    seen: dict = {}

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"address": {"road": "Jl. Test", "city": "Denpasar"},
                    "display_name": "Jl. Test, Denpasar"}

    class _FakeClient:
        def __init__(self, *a, **kw):
            seen["timeout"] = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            seen["url"] = url
            seen["params"] = params
            seen["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(geocoding_service.httpx, "AsyncClient", _FakeClient)

    asyncio.run(
        geocoding_service.GeocodingService().reverse_search(-8.987654321, 115.123456789))

    assert seen["timeout"] is not None, "outbound call must set an explicit timeout"
    ua = seen["headers"]["User-Agent"]
    assert "EVFLOW" in ua and "ops@example.test" in ua
    # rounded before it leaves the process, and never in the query string raw
    assert seen["params"]["lat"] == "-8.988"
    assert seen["params"]["lon"] == "115.123"
    assert "8.987654" not in seen["url"]


def test_user_agent_falls_back_without_contact_env(monkeypatch):
    monkeypatch.delenv("NOMINATIM_CONTACT_EMAIL", raising=False)
    ua = geocoding_service._nominatim_user_agent()
    assert geocoding_service.DEFAULT_NOMINATIM_CONTACT in ua


def test_reverse_cache_serves_repeat_lookups_without_upstream(monkeypatch):
    calls = {"n": 0}

    class _Boom:
        def __init__(self, *a, **kw):
            calls["n"] += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            raise AssertionError("unreachable")

    svc = geocoding_service.GeocodingService()
    first = asyncio.run(svc.reverse_search(-8.9876, 115.1234))
    monkeypatch.setattr(geocoding_service.httpx, "AsyncClient", _Boom)
    second = asyncio.run(svc.reverse_search(-8.9876, 115.1234))

    assert first == second
    assert calls["n"] == 0, "repeat lookup must be served from the cache"


def test_cache_is_bounded():
    geocoding_service._CACHE.clear()
    for i in range(geocoding_service.CACHE_MAX_ENTRIES + 50):
        geocoding_service._cache_put(geocoding_service._CACHE, f"k{i}", [])
    assert len(geocoding_service._CACHE) == geocoding_service.CACHE_MAX_ENTRIES


# --------------------------------------------------------------- rate limiter unit
def test_rate_limiter_allows_up_to_limit_then_blocks():
    rate_limit.reset()
    ns = "unit-test"
    assert all(rate_limit.allow(ns, "subject", 3, 60.0) for _ in range(3))
    assert rate_limit.allow(ns, "subject", 3, 60.0) is False
    assert rate_limit.allow(ns, "other-subject", 3, 60.0) is True


def test_rate_limiter_window_expires():
    rate_limit.reset()
    ns = "unit-test-window"
    assert rate_limit.allow(ns, "subject", 1, 0.0) is True
    # zero-length window: the previous hit is already outside it
    assert rate_limit.allow(ns, "subject", 1, 0.0) is True


# --------------------------------------------------------------- access-log masking
def test_access_log_masking_coarsens_query_coordinates():
    from api import log_privacy

    line = 'GET /api/v1/geocoding/reverse?lat=-6.20881234&lon=106.84561234 HTTP/1.1'
    masked = log_privacy.mask_coordinates(line)
    assert "-6.20881234" not in masked
    assert "106.84561234" not in masked
    assert "lat=-6.2088" in masked
    assert "lon=106.8456" in masked


def test_access_log_filter_rewrites_uvicorn_record():
    import logging as _logging
    from api import log_privacy

    record = _logging.LogRecord(
        name="uvicorn.access", level=_logging.INFO, pathname=__file__, lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1", "GET",
              "/api/v1/stations/nearby?lat=-6.2088123&lon=106.8456123", "1.1", 200),
        exc_info=None,
    )
    assert log_privacy.CoordinateMaskingFilter().filter(record) is True
    assert "-6.2088123" not in record.getMessage()
    assert "lat=-6.2088" in record.getMessage()


def test_access_log_masking_leaves_other_params_alone():
    from api import log_privacy

    line = "GET /api/v1/geocoding/search?q=Bandung&limit=5 HTTP/1.1"
    assert log_privacy.mask_coordinates(line) == line


# --------------------------------------------- AC 2.2.7 distances without a GPS fix
def test_ac_227_every_suggestion_carries_a_distance_when_an_origin_is_given():
    items = client.get(
        "/api/v1/geocoding/search?q=Bandung&lat=-6.2088&lon=106.8456&limit=5").json()["items"]

    assert items, "the local place set must still answer with upstream down"
    assert all(i["distance_km"] is not None for i in items)
    assert all(i["distance_from"] == "origin" for i in items)


def test_ac_227_distances_survive_a_session_with_no_gps_fix():
    """AC 2.2.7 promises 'estimated distances'. Without lat/lon every item used to
    come back with distance_km=null -- precisely the AC 2.2.8 no-GPS case, and
    every first-launch or permission-denied session."""
    body = client.get("/api/v1/geocoding/search?q=Bandung&limit=5").json()
    items = body["items"]

    assert items
    assert all(i["distance_from_reference_km"] is not None for i in items), \
        "a picker that can only show names is not 'estimated distances'"
    # The estimate must NOT arrive in distance_km. That field means 'distance from
    # the caller's own position', and a client rendering it as such would show a
    # confident, wrong number for a driver who never gave a position.
    assert all(i["distance_km"] is None for i in items), \
        "a reference-point estimate must never pose as the user's own distance"
    # ... and the client is told where the estimate is measured from, so it can
    # label it "~X km from Jakarta" instead of implying a GPS fix.
    assert body["distance_from"] == "reference_point"
    assert body["distance_reference_label"]
    assert all(i["distance_from"] == "reference_point" for i in items)
    assert all(i["distance_reference_label"] == body["distance_reference_label"] for i in items)


def test_ac_227_distance_km_still_means_distance_from_the_caller():
    """With a real fix, the pre-existing contract is untouched."""
    body = client.get("/api/v1/geocoding/search?q=Bandung&lat=-6.2088&lon=106.8456&limit=5").json()
    items = body["items"]

    assert items
    assert body["distance_from"] == "origin"
    assert all(i["distance_km"] is not None for i in items)
    assert all(i["distance_from_reference_km"] is None for i in items)


def test_ac_227_fallback_reference_point_is_configurable(monkeypatch):
    geocoding_service._CACHE.clear()
    monkeypatch.setattr(geocoding_service, "FALLBACK_ORIGIN_LAT", -6.9175)
    monkeypatch.setattr(geocoding_service, "FALLBACK_ORIGIN_LON", 107.6191)
    monkeypatch.setattr(geocoding_service, "FALLBACK_ORIGIN_LABEL", "Bandung")

    body = client.get("/api/v1/geocoding/search?q=Bandung&limit=5").json()
    assert body["distance_reference_label"] == "Bandung"
    # Measured from Bandung, not from the default Jakarta reference: every
    # Bandung suggestion is now local (tens of km) rather than ~115 km away.
    assert body["items"]
    assert all(i["distance_from_reference_km"] < 50.0 for i in body["items"]), body["items"]


# ------------------------------------- AC 2.3.2 masking beyond lat=/lon= parameters
def test_ac_232_bbox_query_parameter_is_masked():
    """A tight viewport bbox on /api/v1/stations IS the user's position at 9 dp."""
    from api import log_privacy

    line = ("GET /api/v1/stations?bbox=106.845612345,-6.208812345,"
            "106.846612345,-6.207812345&limit=1 HTTP/1.1")
    masked = log_privacy.mask_coordinates(line)

    for raw in ("106.845612345", "-6.208812345", "106.846612345", "-6.207812345"):
        assert raw not in masked
    assert "bbox=106.8456,-6.2088,106.8466,-6.2078" in masked
    assert "limit=1" in masked


def test_ac_232_a_coordinate_typed_into_q_is_masked():
    from api import log_privacy

    masked = log_privacy.mask_coordinates(
        "GET /api/v1/geocoding/search?q=-6.208812345,106.845612345 HTTP/1.1")
    assert "6.208812345" not in masked
    assert "q=-6.2088,106.8456" in masked


def test_ac_232_geojson_bbox_is_masked_too():
    from api import log_privacy

    masked = log_privacy.mask_coordinates(
        "GET /api/v1/stations.geojson?bbox=106.845612345,-6.208812345,106.8466,-6.2078 HTTP/1.1")
    assert "106.845612345" not in masked


def test_ac_232_filter_is_attached_without_the_asgi_lifespan():
    """Masking used to install only in the lifespan, so `--lifespan off` or a bare
    TestClient silently logged raw coordinates. Importing api.main is enough now."""
    import logging as _logging
    import api.main  # noqa: F401  (import is the thing under test)
    from api.log_privacy import CoordinateMaskingFilter

    for name in ("uvicorn.access", "gunicorn.access"):
        logger = _logging.getLogger(name)
        assert any(isinstance(f, CoordinateMaskingFilter) for f in logger.filters), name


def test_ac_232_wiring_masks_a_record_end_to_end(caplog):
    """Covers the WIRING, not just mask_coordinates(): a filter that was defined but
    never attached passed every previous test."""
    import logging as _logging
    import api.main  # noqa: F401

    with caplog.at_level(_logging.INFO, logger="uvicorn.access"):
        _logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d', "127.0.0.1:54028", "GET",
            "/api/v1/stations/nearby?lat=-6.20881234567&lon=106.84561234567&limit=1", "1.1", 200)

    emitted = "\n".join(r.getMessage() for r in caplog.records)
    assert "20881234567" not in emitted
    assert "84561234567" not in emitted
    assert "lat=-6.2088" in emitted and "lon=106.8456" in emitted


# ------------------------- AC 2.3.3 temporary location data deleted within 30 seconds
def test_ac_233_position_keyed_cache_window_is_within_the_30_second_budget():
    """The reverse cache key IS the caller's position; it lived for 300 s."""
    assert geocoding_service.REVERSE_CACHE_TTL_SECONDS <= 30.0


def test_ac_233_position_entry_is_unreadable_after_the_window():
    import time as _t

    svc = geocoding_service.GeocodingService()
    asyncio.run(svc.reverse_search(-6.20881234, 106.84561234))
    assert len(geocoding_service._REVERSE_CACHE) == 1
    key = next(iter(geocoding_service._REVERSE_CACHE))

    # age the entry past the window without sleeping through it
    _, value = geocoding_service._REVERSE_CACHE[key]
    stale_ts = _t.time() - geocoding_service.REVERSE_CACHE_TTL_SECONDS - 1.0
    geocoding_service._REVERSE_CACHE[key] = (stale_ts, value)

    assert geocoding_service._cache_get(
        geocoding_service._REVERSE_CACHE, key,
        geocoding_service.REVERSE_CACHE_TTL_SECONDS) is None
    assert key not in geocoding_service._REVERSE_CACHE


def test_ac_233_expiry_still_happens_on_the_next_cache_write():
    """The cheap opportunistic sweep, kept as a belt alongside the real one."""
    import time as _t

    stale = _t.time() - geocoding_service.REVERSE_CACHE_TTL_SECONDS - 1.0
    geocoding_service._REVERSE_CACHE["-6.209:106.846"] = (stale, {"label": "x"})

    # writing ANY other key sweeps the expired one; nothing ever reads it again
    geocoding_service._cache_put(
        geocoding_service._REVERSE_CACHE, "other:key", {"label": "y"},
        geocoding_service.REVERSE_CACHE_TTL_SECONDS)

    assert "-6.209:106.846" not in geocoding_service._REVERSE_CACHE


# --------- HIGH-4: the 30 s bound must hold on a process with NO traffic at all
def test_ac_233_ttl_is_not_enforced_by_traffic_alone(monkeypatch):
    """Pins the flaw: nothing else touching the cache means no sweep ever ran.

    Expiry lived inside `_cache_put`, so "active, not lazy" was only true while
    somebody kept performing reverse lookups. With no further traffic the entry
    sat there indefinitely -- which is what the next test has to fix.
    """
    clock = FakeClock()
    monkeypatch.setattr(geocoding_service, "time", clock)

    geocoding_service._cache_put(
        geocoding_service._REVERSE_CACHE, "-6.209:106.846", {"label": "x"},
        geocoding_service.REVERSE_CACHE_TTL_SECONDS)

    # A full hour passes. Nobody calls the API, so nothing writes to the cache.
    clock.advance(3600.0)

    assert "-6.209:106.846" in geocoding_service._REVERSE_CACHE, (
        "the entry is still THERE -- only the background sweeper deletes it")


def test_ac_233_idle_process_deletes_the_entry_within_thirty_seconds(monkeypatch):
    """HIGH-4: drive the real sweeper on a fake clock; no sleeping, no traffic.

    `sweep_forever` is the only thing running: it never reads or writes a cache
    entry, it only purges. So whatever it deletes here, it deletes on a process
    that received exactly zero requests after the lookup.
    """
    clock = FakeClock()
    monkeypatch.setattr(geocoding_service, "time", clock)
    start = clock.now

    geocoding_service._cache_put(
        geocoding_service._REVERSE_CACHE, "-6.209:106.846", {"label": "x"},
        geocoding_service.REVERSE_CACHE_TTL_SECONDS)

    emptied_at: list[float] = []

    async def fake_sleep(delay):
        # Checked BEFORE advancing, so the recorded time is when the previous
        # purge actually emptied the cache.
        if not geocoding_service._REVERSE_CACHE:
            emptied_at.append(clock.now)
            raise asyncio.CancelledError
        assert clock.now - start <= 300.0, "sweeper never deleted the entry"
        assert delay > 0, "a zero delay would spin the event loop"
        clock.advance(delay)

    async def drive():
        try:
            await geocoding_service.sweep_forever(sleep=fake_sleep)
        except asyncio.CancelledError:
            pass

    asyncio.run(drive())

    assert emptied_at, "sweeper exited without ever emptying the cache"
    assert emptied_at[0] - start <= 30.0, (
        f"deleted after {emptied_at[0] - start:.1f}s; AC 2.3.3 allows 30")


def test_ac_233_sweeper_never_sleeps_past_an_entrys_deadline(monkeypatch):
    """The bound is exact because the sweeper wakes ON the deadline, not on a poll.

    A fixed poll interval would make worst-case retention TTL + interval, i.e.
    over budget. `seconds_until_next_expiry` clamps DOWN to the nearest deadline.
    """
    clock = FakeClock()
    monkeypatch.setattr(geocoding_service, "time", clock)
    monkeypatch.setattr(geocoding_service, "CACHE_SWEEP_IDLE_POLL_SECONDS", 5.0)

    # Empty process: it still wakes, but no more often than the idle poll.
    assert geocoding_service.seconds_until_next_expiry() == 5.0

    geocoding_service._cache_put(
        geocoding_service._REVERSE_CACHE, "-6.209:106.846", {"label": "x"},
        geocoding_service.REVERSE_CACHE_TTL_SECONDS)

    # 2 s before the deadline the sweeper sleeps 2 s, not the 5 s poll interval.
    clock.advance(geocoding_service.REVERSE_CACHE_TTL_SECONDS - 2.0)
    assert geocoding_service.seconds_until_next_expiry() == pytest.approx(2.0)

    # Already overdue: sweep immediately rather than going negative.
    clock.advance(10.0)
    assert geocoding_service.seconds_until_next_expiry() == 0.0


def test_ac_233_purge_expired_clears_both_caches():
    import time as _t

    old = _t.time() - 10_000.0
    geocoding_service._REVERSE_CACHE["-6.209:106.846"] = (old, {"label": "x"})
    geocoding_service._CACHE["bandung:-6.21:106.85:origin:5"] = (old, [])

    removed = geocoding_service.purge_expired()

    assert removed == 2
    assert not geocoding_service._REVERSE_CACHE
    assert not geocoding_service._CACHE


@pytest.fixture
def signed_in():
    from api import security
    app.dependency_overrides[security.current_user] = lambda: {"id": "u-1"}
    yield
    app.dependency_overrides.pop(security.current_user, None)


def _reverse(lat, lon, session_id=None):
    svc = geocoding_service.GeocodingService()
    return asyncio.run(svc.reverse_search(lat, lon, session_id=session_id))


# --------- HIGH-3: the endpoint must delete the ENDING session's own live data
def test_ac_233_purge_expired_alone_cannot_end_a_session():
    """Pins the flaw the endpoint used to have.

    `purge_expired()` drops entries whose TTL has ALREADY elapsed. The
    coordinates belonging to the session that just ended are, by definition, the
    ones still inside their TTL -- so sweeping expired entries is precisely the
    wrong tool for the "session ends -> deleted" trigger.
    """
    _reverse(-6.20881234, 106.84561234, session_id="plan-abc123")
    assert len(geocoding_service._REVERSE_CACHE) == 1

    assert geocoding_service.purge_expired() == 0
    assert len(geocoding_service._REVERSE_CACHE) == 1, (
        "a still-live entry survives purge_expired -- that is the whole bug")


def test_ac_233_delete_route_plan_deletes_the_ending_sessions_live_data(signed_in):
    """AC 2.3.3's actual trigger: end the session, the location data is gone NOW."""
    _reverse(-6.20881234, 106.84561234, session_id="plan-abc123")
    assert len(geocoding_service._REVERSE_CACHE) == 1

    res = client.delete("/api/v1/route-plans/plan-abc123")

    assert res.status_code == 204
    assert geocoding_service._REVERSE_CACHE == {}, "the session's own entry must go"
    assert geocoding_service._SESSION_KEYS == {}


def test_ac_233_delete_route_plan_targets_only_the_ending_session(signed_in):
    """It must honour its path parameter, which it previously ignored entirely."""
    _reverse(-6.2088, 106.8456, session_id="plan-mine")
    _reverse(-6.9175, 107.6191, session_id="plan-someone-else")
    assert len(geocoding_service._REVERSE_CACHE) == 2

    assert client.delete("/api/v1/route-plans/plan-mine").status_code == 204

    assert len(geocoding_service._REVERSE_CACHE) == 1
    assert list(geocoding_service._SESSION_KEYS) == ["plan-someone-else"]


def test_ac_233_reverse_endpoint_tags_the_session_for_deletion(signed_in):
    """End to end over HTTP, the way the client actually wires it up."""
    assert client.get("/api/v1/geocoding/reverse"
                      "?lat=-6.2088&lon=106.8456&route_plan_id=plan-xyz").status_code == 200
    assert len(geocoding_service._REVERSE_CACHE) == 1

    assert client.delete("/api/v1/route-plans/plan-xyz").status_code == 204
    assert geocoding_service._REVERSE_CACHE == {}


def test_ac_233_a_cache_hit_is_still_deletable_by_the_session_that_hit_it(signed_in):
    """The key is shared between sessions, so a HIT must also be indexed.

    Otherwise session B reads A's cached entry, ends its trip, and its own
    position lingers because only A was ever recorded against that key.
    """
    _reverse(-6.2088, 106.8456, session_id="plan-a")
    _reverse(-6.2088, 106.8456, session_id="plan-b")     # served from cache

    assert client.delete("/api/v1/route-plans/plan-b").status_code == 204
    assert geocoding_service._REVERSE_CACHE == {}


def test_ac_233_session_index_never_outlives_the_data_it_points_at(monkeypatch):
    """The index maps a session to coarsened POSITIONS, so it is a location record too."""
    clock = FakeClock()
    monkeypatch.setattr(geocoding_service, "time", clock)

    geocoding_service._cache_put(
        geocoding_service._REVERSE_CACHE, "-6.209:106.846", {"label": "x"},
        geocoding_service.REVERSE_CACHE_TTL_SECONDS)
    geocoding_service._remember_session_key("plan-abc", "-6.209:106.846")
    assert geocoding_service._SESSION_KEYS

    clock.advance(geocoding_service.REVERSE_CACHE_TTL_SECONDS)
    geocoding_service.purge_expired()

    assert geocoding_service._REVERSE_CACHE == {}
    assert geocoding_service._SESSION_KEYS == {}, "the index outlived the entries"


def test_ac_233_delete_route_plan_is_idempotent(signed_in):
    """Teardown must never make the client handle an error it cannot act on."""
    _reverse(-6.2088, 106.8456, session_id="plan-abc123")
    assert client.delete("/api/v1/route-plans/plan-abc123").status_code == 204
    assert client.delete("/api/v1/route-plans/plan-abc123").status_code == 204
    assert client.delete("/api/v1/route-plans/plan-never-existed").status_code == 204


def test_ac_233_delete_route_plan_still_sweeps_whatever_else_expired(signed_in):
    import time as _t

    stale = _t.time() - geocoding_service.REVERSE_CACHE_TTL_SECONDS - 1.0
    geocoding_service._REVERSE_CACHE["-6.209:106.846"] = (stale, {"label": "x"})

    assert client.delete("/api/v1/route-plans/plan-abc123").status_code == 204
    assert "-6.209:106.846" not in geocoding_service._REVERSE_CACHE


def test_ac_233_delete_route_plan_requires_auth():
    assert client.delete("/api/v1/route-plans/plan-abc123").status_code == 401


def test_ac_233_route_plans_are_never_persisted():
    """The mitigating half of the AC: there is no route-plan store to delete."""
    import pathlib
    import re as _re

    migrations = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    sql = "\n".join(p.read_text() for p in migrations.glob("*.py"))
    tables = set(_re.findall(r"create_table\(\s*[\"']([a-z_]+)[\"']", sql))

    assert not {t for t in tables if "route" in t or "plan" in t}, tables


# ---------------------------------------------------------------------------
# HIGH-2 -- the destination picker must never offer a destination that
# POST /api/v1/route-plans would then reject with a 422. Discovery and planning
# read the SAME configured area, so they cannot drift apart.
# ---------------------------------------------------------------------------
JABODETABEK = {"SERVICE_AREA_SOUTH": -7.35, "SERVICE_AREA_WEST": 105.90,
               "SERVICE_AREA_NORTH": -5.60, "SERVICE_AREA_EAST": 108.30}

SURABAYA = (-7.2575, 112.7521)     # East Java: 230 seeded stations
DENPASAR = (-8.6705, 115.2126)     # Bali: 110 seeded stations
MEDAN = (3.5952, 98.6722)          # North Sumatra: 99 seeded stations
BOGOR = (-6.5971, 106.7996)        # inside even the narrow box


def _narrow_to_jabodetabek(monkeypatch):
    """Simulate a deployment that really does only serve Jabodetabek."""
    for name, value in JABODETABEK.items():
        monkeypatch.setattr(service_area, name, value)


def test_high2_default_area_covers_every_place_the_picker_offers():
    """The shipped suggestion list is national, so the default area must be too.

    A Jabodetabek-sized default rejected roughly half the dataset while these
    very entries were still being suggested -- the app contradicting itself.
    """
    outside = [p["label"] for p in geocoding_service.KNOWN_INDONESIA_PLACES
               if not service_area.contains(p["latitude"], p["longitude"])]
    assert outside == [], f"suggested but not routable: {outside}"


@pytest.mark.parametrize("lat,lon", [SURABAYA, DENPASAR, MEDAN])
def test_high2_default_area_covers_the_seeded_provinces(lat, lon):
    assert service_area.contains(lat, lon)


@requires_db
def test_high2_no_seeded_station_falls_outside_the_configured_area():
    """The measurable form of the finding: 49% of stations used to be un-routable."""
    from sqlalchemy import text
    from api.db import engine

    with engine.connect() as conn:
        total = conn.execute(text("select count(*) from stations")).scalar()
        outside = conn.execute(text(
            "select count(*) from stations "
            "where ST_Y(geom) not between :s and :n or ST_X(geom) not between :w and :e"
        ), {"s": service_area.SERVICE_AREA_SOUTH, "n": service_area.SERVICE_AREA_NORTH,
            "w": service_area.SERVICE_AREA_WEST, "e": service_area.SERVICE_AREA_EAST}).scalar()

    assert total > 0
    assert outside == 0, f"{outside}/{total} shipped stations cannot be routed to"


def test_high2_search_flags_every_suggestion_the_planner_would_refuse(monkeypatch):
    """Narrowing the box stays safe: the picker follows it automatically."""
    _narrow_to_jabodetabek(monkeypatch)

    body = client.get("/api/v1/geocoding/search?q=Surabaya&limit=5").json()

    item = next(i for i in body["items"] if i["label"] == "Surabaya")
    assert item["in_service_area"] is False
    # And the client is told WHERE the app does work, not just that this fails.
    assert body["service_area"]["name"] == service_area.SERVICE_AREA_NAME
    assert body["service_area"]["north"] == JABODETABEK["SERVICE_AREA_NORTH"]


def test_high2_in_service_area_matches_the_planners_verdict_exactly(monkeypatch):
    """The invariant, checked against the real endpoint rather than restated.

    Every suggestion is offered to POST /api/v1/route-plans as a destination; a
    flagged-routable item must be accepted and a flagged-unroutable item must be
    the one field the planner names.
    """
    from api import evmodels, security
    from tests.test_route_plans import IONIQ_5

    _narrow_to_jabodetabek(monkeypatch)
    app.dependency_overrides[security.current_user] = lambda: {
        "id": "u-1", "ev_model_id": "hyundai-ioniq-5", "main_connector_type": "CCS2"}
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    try:
        for query, (lat, lon) in (("Surabaya", SURABAYA), ("Bogor", BOGOR)):
            body = client.get(f"/api/v1/geocoding/search?q={query}&limit=5").json()
            item = next(i for i in body["items"] if i["label"] == query)

            res = client.post("/api/v1/route-plans", json={
                "origin": {"latitude": -6.2088, "longitude": 106.8456},
                "destination": {"latitude": item["latitude"], "longitude": item["longitude"]},
                "current_soc_pct": 80.0,
            })

            planner_accepts = res.status_code != 422
            assert item["in_service_area"] is planner_accepts, (
                f"{query}: picker says routable={item['in_service_area']} "
                f"but planner returned {res.status_code}")
            if not planner_accepts:
                assert ["body", "destination"] in [d["loc"] for d in res.json()["detail"]]
    finally:
        app.dependency_overrides.pop(security.current_user, None)


def test_high2_search_can_drop_unroutable_suggestions_entirely(monkeypatch):
    """For a picker that would rather show nothing than something un-routable."""
    _narrow_to_jabodetabek(monkeypatch)

    body = client.get(
        "/api/v1/geocoding/search?q=Surabaya&limit=5&in_service_area_only=true").json()

    assert [i["label"] for i in body["items"] if i["label"] == "Surabaya"] == []
    assert all(i["in_service_area"] for i in body["items"])
    assert body["filtered_out_of_service_area"] >= 1


def test_high2_filtering_is_off_by_default_so_browsing_still_works(monkeypatch):
    """The data is national; browsing outside the routing area is legitimate."""
    _narrow_to_jabodetabek(monkeypatch)

    body = client.get("/api/v1/geocoding/search?q=Surabaya&limit=5").json()

    assert any(i["label"] == "Surabaya" for i in body["items"])
    assert body["filtered_out_of_service_area"] == 0


def test_high2_filtered_and_unfiltered_results_do_not_share_a_cache_entry(monkeypatch):
    _narrow_to_jabodetabek(monkeypatch)

    filtered = client.get(
        "/api/v1/geocoding/search?q=Surabaya&limit=5&in_service_area_only=true").json()
    unfiltered = client.get("/api/v1/geocoding/search?q=Surabaya&limit=5").json()

    assert len(unfiltered["items"]) > len(filtered["items"])


def test_high2_station_payloads_carry_the_same_flag(monkeypatch):
    """/api/v1/stations and /nearby return Station objects, so they follow too."""
    from api.models import Station

    _narrow_to_jabodetabek(monkeypatch)
    inside = Station(id="s-1", latitude=BOGOR[0], longitude=BOGOR[1])
    outside = Station(id="s-2", latitude=DENPASAR[0], longitude=DENPASAR[1])

    assert inside.in_service_area is True
    assert outside.in_service_area is False


# ---------------------------------------------------------------------------
# MEDIUM-5 -- the module docstring and its own constants must agree.
# ---------------------------------------------------------------------------
# Places the service_area docstring explicitly claims coverage for. If the
# constants are narrowed without rewriting the prose (or vice versa), this fails.
DOCUMENTED_ANCHORS = [
    ("Sabang", 5.8894, 95.3238),
    ("Aceh", 5.5483, 95.3238),
    ("Merauke", -8.4932, 140.4017),
    ("Rote", -10.7500, 123.1200),
    ("Sabu", -10.5167, 121.8500),
    # The exact pair the original docstring got wrong: it claimed coverage "out
    # to Bandung/Cirebon" while EAST=108.30 excluded Cirebon at 108.55.
    ("Bandung", -6.9175, 107.6191),
    ("Cirebon", -6.7320, 108.5523),
    ("Surabaya", -7.2575, 112.7521),
    ("Denpasar", -8.6705, 115.2126),
    ("Medan", 3.5952, 98.6722),
]


@pytest.mark.parametrize("name,lat,lon", DOCUMENTED_ANCHORS)
def test_medium5_docstring_claims_match_the_constants(name, lat, lon):
    assert name.lower() in (service_area.__doc__ or "").lower(), \
        f"docstring no longer mentions {name}; update the anchors or the prose"
    assert service_area.contains(lat, lon), \
        f"docstring claims {name} is covered but the constants exclude it"


def test_medium5_env_example_documents_the_actual_defaults():
    """No magic numbers: the shipped example must not drift from the code."""
    import pathlib
    import re as _re

    env = (pathlib.Path(__file__).resolve().parents[1] / ".env.example").read_text()
    documented = {k: v for k, v in _re.findall(
        r"^(ROUTE_SERVICE_AREA_(?:SOUTH|WEST|NORTH|EAST))=(-?[\d.]+)", env, _re.M)}

    assert documented, "the service-area bounds are undocumented"
    for key, raw in documented.items():
        attr = key.replace("ROUTE_", "")
        assert float(raw) == getattr(service_area, attr), key


def test_medium5_every_tunable_is_reachable_from_the_environment(monkeypatch):
    """The boundary stays configuration, not a constant frozen into the code."""
    import importlib

    monkeypatch.setenv("ROUTE_SERVICE_AREA_SOUTH", "-1.5")
    monkeypatch.setenv("ROUTE_SERVICE_AREA_NAME", "Test Area")
    monkeypatch.setenv("GEOCODING_CACHE_SWEEP_IDLE_POLL_SECONDS", "0.25")
    try:
        reloaded = importlib.reload(service_area)
        assert reloaded.SERVICE_AREA_SOUTH == -1.5
        assert reloaded.SERVICE_AREA_NAME == "Test Area"
        reloaded_geo = importlib.reload(geocoding_service)
        assert reloaded_geo.CACHE_SWEEP_IDLE_POLL_SECONDS == 0.25
    finally:
        monkeypatch.undo()
        importlib.reload(service_area)
        importlib.reload(geocoding_service)


def test_ac_233_sweeper_is_actually_wired_into_the_app_lifespan():
    """Defined-but-never-attached is exactly how coordinate masking broke once.

    A guarantee that lives in an unstarted coroutine is not a guarantee, so the
    wiring itself is asserted: running the app starts the sweeper, and shutting
    it down leaves no pending task behind.
    """
    from api import main

    assert not geocoding_service.sweeper_is_running()
    with TestClient(main.app):
        assert geocoding_service.sweeper_is_running(), \
            "the app started without the AC 2.3.3 sweeper"
    assert not geocoding_service.sweeper_is_running(), \
        "shutdown left the sweeper task pending"


def test_ac_233_start_sweeper_is_idempotent():
    async def _twice():
        first = geocoding_service.start_sweeper()
        second = geocoding_service.start_sweeper()
        try:
            assert first is second, "a second call must not spawn a rival sweeper"
        finally:
            await geocoding_service.stop_sweeper()

    asyncio.run(_twice())
    assert not geocoding_service.sweeper_is_running()

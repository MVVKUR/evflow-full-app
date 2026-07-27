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
from api.services import geocoding_service  # noqa: E402

client = TestClient(app)

JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"          # >= 32 chars

# Closed port: the upstream call fails fast, so tests never touch the network
# and we still exercise the failure path.
UNREACHABLE_UPSTREAM = "http://127.0.0.1:9"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    geocoding_service._CACHE.clear()
    geocoding_service._REVERSE_CACHE.clear()
    rate_limit.reset()
    monkeypatch.setattr(geocoding_service, "NOMINATIM_BASE_URL", UNREACHABLE_UPSTREAM)
    yield
    geocoding_service._CACHE.clear()
    geocoding_service._REVERSE_CACHE.clear()
    rate_limit.reset()


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
    key = "unit-test-key"
    assert all(rate_limit.allow(key, 3, 60.0) for _ in range(3))
    assert rate_limit.allow(key, 3, 60.0) is False
    assert rate_limit.allow("other-key", 3, 60.0) is True


def test_rate_limiter_window_expires():
    rate_limit.reset()
    key = "unit-test-window"
    assert rate_limit.allow(key, 1, 0.0) is True
    # zero-length window: the previous hit is already outside it
    assert rate_limit.allow(key, 1, 0.0) is True


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

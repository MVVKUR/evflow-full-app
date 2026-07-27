"""The TOTAL wall-clock budget one request may spend on road routing.

Why this file exists
--------------------
`ROUTING_TIMEOUT_SECONDS` bounds a single provider attempt, not a request. A
plan makes up to 1 + 2*ROUTE_MAX_ROAD_VALIDATION_CANDIDATES routing calls, and
each call tries httpx and then a curl retry, so the attempts STACK. With the
per-attempt timeout at its 10s default a single plan was measured burning 60s
of routing against a slow-failing OSRM. Production sits behind nginx with a 30s
limit, so a response that long is returned to nobody: it just burns a worker and
fails. `ROUTING_TOTAL_BUDGET_SECONDS` is the cap that actually holds.

These tests drive a SIMULATED clock. Nothing here sleeps: the fake providers
advance the clock by exactly the timeout they were handed, so the assertions are
about the wall clock the request WOULD have spent, and the suite still runs in
milliseconds.

Contract note: degrading on an exhausted budget must change only the WAIT.
POST /api/v1/route-plans still refuses rather than fabricate a route, and
POST /api/v1/route-plans/active/evaluate still answers with the labelled
straight-line estimate. Both are asserted below.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

import api.services.routing_service as rs
from api import evmodels
from api.main import app
from tests.test_route_plans import (  # noqa: F401  (fixtures are used by injection)
    BANDUNG,
    IONIQ_5,
    JAKARTA,
    MIDPOINT,
    active_body,
    as_user,
    availability,
    make_station,
    plan_body,
    use_stations,
)

client = TestClient(app)

# Pinned here rather than read from the environment so the numbers below mean
# the same thing whatever a developer has in their .env.
PER_ATTEMPT = 3.0
BUDGET = 12.0


class SimulatedRouting:
    """A slow-failing OSRM that costs simulated seconds instead of real ones."""

    def __init__(self):
        self.elapsed = 0.0
        self.httpx_timeouts: list[float] = []
        self.curl_max_times: list[float] = []

    def now(self) -> float:
        return self.elapsed


@pytest.fixture
def slow_osrm(monkeypatch):
    """Every OSRM attempt burns its whole allowance and then fails."""
    sim = SimulatedRouting()

    class _SlowClient:
        def __init__(self, *a, **kw):
            self._timeout = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            allowance = float(self._timeout)
            sim.httpx_timeouts.append(allowance)
            sim.elapsed += allowance
            raise RuntimeError("simulated slow OSRM failure")

    class _TimedOutCurl:
        returncode = 28  # curl's own "operation timed out"

        async def communicate(self):
            return b"", b"curl: (28) Operation timed out"

        def kill(self):
            pass

    async def _fake_exec(*args, **kwargs):
        allowance = float(args[list(args).index("--max-time") + 1])
        sim.curl_max_times.append(allowance)
        sim.elapsed += allowance
        return _TimedOutCurl()

    monkeypatch.setattr(rs, "_monotonic", sim.now)
    monkeypatch.setattr(rs, "ROUTING_TIMEOUT_SECONDS", PER_ATTEMPT)
    monkeypatch.setattr(rs, "ROUTING_TOTAL_BUDGET_SECONDS", BUDGET)
    monkeypatch.setattr(rs.httpx, "AsyncClient", _SlowClient)
    monkeypatch.setattr(rs.shutil, "which", lambda n: "/usr/bin/curl" if n == "curl" else None)
    monkeypatch.setattr(rs.asyncio, "create_subprocess_exec", _fake_exec)
    return sim


@pytest.fixture
def local_graph_answers(monkeypatch):
    """The local Dijkstra provider works, so the plan keeps making OSRM calls.

    Without this the very first failure ends the request and the stacking that
    this budget exists to bound never happens.
    """
    def _fake_local(self, coords):
        total = sum(
            rs.haversine_distance_km(a[0], a[1], b[0], b[1])
            for a, b in zip(coords, coords[1:])
        )
        return {
            "distance_km": round(total, 2),
            "duration_minutes": round(total / 40.0 * 60.0, 1),
            "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in coords]},
            "steps": [],
            "provider": "local_dijkstra",
        }

    monkeypatch.setattr(rs.RoutingService, "_local_fallback_route", _fake_local)


def _corridor_stations(monkeypatch):
    """Three candidates, so road validation makes 2 routing calls per candidate."""
    stations = [
        make_station("st-1", MIDPOINT[0], MIDPOINT[1], 150.0),
        make_station("st-2", MIDPOINT[0] + 0.02, MIDPOINT[1] + 0.02, 120.0),
        make_station("st-3", MIDPOINT[0] - 0.02, MIDPOINT[1] - 0.02, 100.0),
    ]
    use_stations(monkeypatch, stations,
                 {s["id"]: availability(s["id"], {"CCS2": 2}) for s in stations})


# ---------------------------------------------------------------------------
# the regression this file exists for
# ---------------------------------------------------------------------------
def test_plan_against_slow_osrm_stays_inside_the_total_budget(
        as_user, slow_osrm, local_graph_answers, monkeypatch):
    """A multi-call plan used to cost ~7 stacked attempts. Now it costs one budget.

    Before the budget existed this same scenario spent 18s at a 3s per-attempt
    timeout and 60s at the shipped 10s default -- past the 30s proxy limit, so
    the answer reached nobody.
    """
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    _corridor_stations(monkeypatch)

    started = time.monotonic()
    res = client.post("/api/v1/route-plans", json=plan_body(soc=25.0))
    real_seconds = time.monotonic() - started

    # More than one routing call was made, so this really is the stacking case.
    assert len(slow_osrm.httpx_timeouts) > 1

    assert slow_osrm.elapsed <= BUDGET, (
        f"routing spent {slow_osrm.elapsed}s against a {BUDGET}s budget")
    assert res.status_code in (200, 503)
    # The clock is simulated: the suite must not actually wait any of this out.
    assert real_seconds < 5.0


def test_evaluate_against_slow_osrm_stays_inside_the_total_budget(
        as_user, slow_osrm, monkeypatch):
    """A driver already under way is answered inside the budget, not at 60s."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})

    started = time.monotonic()
    res = client.post("/api/v1/route-plans/active/evaluate", json=active_body(soc=12.0))
    real_seconds = time.monotonic() - started

    assert slow_osrm.elapsed <= BUDGET
    assert real_seconds < 5.0
    # AC 2.1.1 / AC 2.4.2: still answered, still labelled degraded. Unchanged.
    assert res.status_code == 200
    assumptions = res.json()["assumptions"]
    assert assumptions["routing_provider"] == rs.HAVERSINE_FALLBACK_PROVIDER
    assert assumptions["turn_by_turn_available"] is False
    assert assumptions["distance_basis"] == "straight_line"


def test_plan_still_refuses_rather_than_fabricate_when_the_budget_runs_out(
        as_user, slow_osrm, monkeypatch):
    """Running out of time degrades down the SAME path as a provider outage."""
    as_user()
    monkeypatch.setattr(evmodels, "get", lambda mid: dict(IONIQ_5))
    use_stations(monkeypatch, [], {})
    # One attempt eats the entire budget, so the budget -- not a provider error
    # -- is what ends the request, and the local graph is never reached.
    monkeypatch.setattr(rs, "ROUTING_TIMEOUT_SECONDS", BUDGET)
    monkeypatch.setattr(
        rs.RoutingService, "_local_fallback_route",
        lambda self, coords: pytest.fail("the local graph must not be attempted"))

    res = client.post("/api/v1/route-plans", json=plan_body(soc=95.0))

    assert slow_osrm.elapsed == BUDGET
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert "road routing is unavailable" in detail and "budget" in detail
    # No fabricated geometry anywhere in the refusal.
    assert "geometry" not in res.text
    # A budget exhaustion is a RouteUnavailable, which is why every existing
    # caller degrades correctly without being taught about the budget.
    assert issubclass(rs.RoutingBudgetExhausted, rs.RouteUnavailable)


# ---------------------------------------------------------------------------
# the curl retry fits INSIDE the budget rather than extending it
# ---------------------------------------------------------------------------
def test_curl_retry_gets_the_time_that_is_left_not_a_fresh_full_timeout(slow_osrm):
    """The stacking bug in miniature: curl used to re-arm the whole timeout."""
    service = rs.RoutingService(timeout=10.0, total_budget_seconds=BUDGET)

    asyncio.run(service._request_osrm_json("https://osrm.test/route"))

    assert slow_osrm.httpx_timeouts == [10.0]
    # 12 budget - 10 spent by httpx = 2 left. Not another 10.
    assert slow_osrm.curl_max_times == [2.0]
    assert slow_osrm.elapsed == 12.0


def test_curl_retry_is_skipped_when_no_budget_remains(slow_osrm):
    service = rs.RoutingService(timeout=BUDGET, total_budget_seconds=BUDGET)

    result = asyncio.run(service._request_osrm_json("https://osrm.test/route"))

    assert result is None
    assert slow_osrm.httpx_timeouts == [BUDGET]
    assert slow_osrm.curl_max_times == []  # nothing left, so it never forked
    assert slow_osrm.elapsed == BUDGET


def test_a_later_call_is_clamped_by_what_an_earlier_one_already_spent(slow_osrm):
    """One RoutingService is one request: the budget is shared across its calls."""
    service = rs.RoutingService(timeout=5.0, total_budget_seconds=BUDGET)

    asyncio.run(service._request_osrm_json("https://osrm.test/a"))  # 5 + 5 = 10
    asyncio.run(service._request_osrm_json("https://osrm.test/b"))  # only 2 left

    assert slow_osrm.httpx_timeouts == [5.0, 2.0]
    assert slow_osrm.curl_max_times == [5.0]  # after b's httpx, nothing remained
    assert slow_osrm.elapsed == BUDGET


def test_osrm_is_skipped_entirely_once_the_budget_is_spent(slow_osrm, monkeypatch):
    service = rs.RoutingService(timeout=BUDGET, total_budget_seconds=BUDGET)
    asyncio.run(service._request_osrm_json("https://osrm.test/a"))
    assert service.budget_remaining_seconds() <= 0

    monkeypatch.setattr(
        rs.RoutingService, "_local_fallback_route",
        lambda self, coords: pytest.fail("the local graph must not be attempted"))

    with pytest.raises(rs.RoutingBudgetExhausted):
        asyncio.run(service.get_route(JAKARTA, BANDUNG))

    # No further attempt was made against either provider.
    assert slow_osrm.httpx_timeouts == [BUDGET]
    assert slow_osrm.elapsed == BUDGET


# ---------------------------------------------------------------------------
# budget bookkeeping
# ---------------------------------------------------------------------------
def test_the_budget_clock_starts_at_the_first_attempt_not_at_construction(monkeypatch):
    """Time spent in the database is not routing time."""
    fake_now = [100.0]
    monkeypatch.setattr(rs, "_monotonic", lambda: fake_now[0])

    service = rs.RoutingService(total_budget_seconds=BUDGET)
    fake_now[0] += 30.0  # a slow station query happens before any routing

    assert service.budget_remaining_seconds() == BUDGET


def test_a_zero_budget_disables_the_cap(monkeypatch):
    """The documented escape hatch, for anyone not sitting behind a proxy."""
    monkeypatch.setattr(rs, "_monotonic", lambda: 10_000.0)
    service = rs.RoutingService(timeout=7.0, total_budget_seconds=0.0)

    assert service.budget_remaining_seconds() == float("inf")
    assert service._attempt_timeout() == 7.0  # clamped by the per-attempt value only


def test_defaults_are_read_at_construction_so_config_stays_overridable(monkeypatch):
    """Bound as default arguments these were frozen at import and untunable."""
    monkeypatch.setattr(rs, "ROUTING_TIMEOUT_SECONDS", 4.0)
    monkeypatch.setattr(rs, "ROUTING_TOTAL_BUDGET_SECONDS", 9.0)

    service = rs.RoutingService()

    assert service.timeout == 4.0
    assert service.total_budget_seconds == 9.0


def test_shipped_budget_default_leaves_headroom_under_the_proxy_limit():
    """A budget at or above the nginx limit would be no budget at all.

    Asserts the SHIPPED DEFAULT, not the env-resolved value: tuning the env var
    is a legitimate deployment choice and must not fail the suite.
    """
    assert 0 < rs.DEFAULT_ROUTING_TOTAL_BUDGET_SECONDS <= rs.NGINX_PROXY_LIMIT_SECONDS / 2
    # Room for at least one full provider attempt inside the budget.
    assert rs.DEFAULT_ROUTING_TOTAL_BUDGET_SECONDS >= rs.ROUTING_MIN_ATTEMPT_SECONDS


def test_env_example_documents_the_same_default_the_code_ships():
    """The stale ROUTING_TIMEOUT_SECONDS (code 10.0 vs .env.example 3.0) is how
    this class of bug hid. The budget's two copies are pinned together here."""
    from pathlib import Path

    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    documented = [
        line.split("=", 1)[1].strip()
        for line in env_example.read_text().splitlines()
        if line.startswith("ROUTING_TOTAL_BUDGET_SECONDS=")
    ]
    assert documented, "ROUTING_TOTAL_BUDGET_SECONDS must be documented in .env.example"
    assert float(documented[0]) == rs.DEFAULT_ROUTING_TOTAL_BUDGET_SECONDS

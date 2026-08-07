"""Tests for api/rate_limit.py itself.

The limiter is small, but five money and auth endpoints now depend on properties
it did not have until recently, and every one of them fails silently:

* it is called from up to 40 AnyIO threadpool threads at once (every sync `def`
  handler in main.py), where a read-then-append without a lock grants about 2x
  the limit, and OrderedDict.move_to_end can raise KeyError mid-eviction --
  surfacing as a 500 rather than a 429, i.e. invisible in any 429 metric;
* deployment-wide ceilings used to be ordinary evictable entries, so unrelated
  traffic could reset a ceiling while it was holding a lockout;
* eviction used to be one shared table, so N requests to any endpoint reset every
  other endpoint's counters -- which is exactly what decides whether keying on
  caller-supplied input (the hashed email on /auth/forgot-password) is safe.

Nothing here sleeps: window expiry is driven by a fake clock substituted for the
`time` module inside rate_limit.
"""
from __future__ import annotations

import threading

import pytest

from api import rate_limit


# =========================================================== the sliding window
@pytest.mark.unit
def test_it_allows_exactly_the_limit_and_then_refuses():
    verdicts = [rate_limit.allow("ns", "subject", 3, 60.0) for _ in range(5)]
    assert verdicts == [True, True, True, False, False]


@pytest.mark.unit
def test_the_window_slides_rather_than_resetting_on_a_boundary(rate_limit_clock):
    """A fixed bucket would let 2x the limit through across a boundary."""
    for _ in range(5):
        assert rate_limit.allow("ns", "s", 5, 60.0) is True

    rate_limit_clock.advance(59.9)
    assert rate_limit.allow("ns", "s", 5, 60.0) is False, \
        "still inside the window: a fixed-bucket implementation would allow this"

    rate_limit_clock.advance(0.2)          # now 60.1s after the first five
    assert rate_limit.allow("ns", "s", 5, 60.0) is True


@pytest.mark.unit
def test_no_sixty_second_stretch_ever_holds_more_than_the_limit(rate_limit_clock):
    """Sweep the whole window one second at a time and watch the running count."""
    granted: list[float] = []
    for _ in range(240):
        if rate_limit.allow("ns", "s", 5, 60.0):
            granted.append(rate_limit_clock.now)
        rate_limit_clock.advance(1.0)

    for start in granted:
        in_window = [t for t in granted if start <= t < start + 60.0]
        assert len(in_window) <= 5, f"{len(in_window)} hits inside one 60s window"


@pytest.mark.unit
def test_refused_attempts_do_not_extend_the_lockout(rate_limit_clock):
    """Hammering while locked out must not push the release further away."""
    for _ in range(3):
        rate_limit.allow("ns", "s", 3, 60.0)
    for _ in range(50):                      # bang on the door for 50 seconds
        assert rate_limit.allow("ns", "s", 3, 60.0) is False
        rate_limit_clock.advance(1.0)

    rate_limit_clock.advance(10.1)           # 60.1s after the last allowed hit
    assert rate_limit.allow("ns", "s", 3, 60.0) is True


@pytest.mark.unit
def test_the_window_expires_on_its_own(rate_limit_clock):
    for _ in range(2):
        rate_limit.allow("ns", "s", 2, 300.0)
    assert rate_limit.allow("ns", "s", 2, 300.0) is False

    rate_limit_clock.advance(301.0)
    assert rate_limit.allow("ns", "s", 2, 300.0) is True


# ================================================================ key isolation
@pytest.mark.unit
def test_one_subject_cannot_spend_another_subjects_budget():
    for _ in range(3):
        rate_limit.allow("ns", "attacker", 3, 60.0)
    assert rate_limit.allow("ns", "attacker", 3, 60.0) is False
    assert rate_limit.allow("ns", "victim", 3, 60.0) is True


@pytest.mark.unit
def test_namespaces_do_not_share_a_budget():
    """The same caller on two endpoints has two budgets, not one."""
    for _ in range(3):
        rate_limit.allow("login:fail:ip", "10.0.0.1", 3, 60.0)
    assert rate_limit.allow("login:fail:ip", "10.0.0.1", 3, 60.0) is False
    assert rate_limit.allow("register:ip", "10.0.0.1", 3, 60.0) is True


@pytest.mark.unit
def test_the_ceiling_is_separate_from_every_subject():
    assert rate_limit.allow("ns:global", None, 1, 60.0) is True
    assert rate_limit.allow("ns:global", None, 1, 60.0) is False
    assert rate_limit.allow("ns:global", "a-subject", 1, 60.0) is True


# ============================================== check-without-charging (login)
@pytest.mark.unit
def test_exceeded_reports_without_spending_the_budget():
    """What lets /auth/login charge failures only: a successful sign-in checks the
    budget and must leave it untouched."""
    for _ in range(100):
        assert rate_limit.exceeded("ns", "s", 3, 60.0) is False

    assert [rate_limit.allow("ns", "s", 3, 60.0) for _ in range(4)] == \
        [True, True, True, False]


@pytest.mark.unit
def test_exceeded_creates_no_bucket_for_an_unknown_subject():
    """Otherwise a flood of read-only checks would fill the table it is checked
    against, and evict live counters on the way."""
    for i in range(50):
        rate_limit.exceeded("ns", f"subject-{i}", 3, 60.0)
    assert rate_limit.tracked_subjects("ns") == 0


@pytest.mark.unit
def test_record_charges_the_bucket_that_exceeded_reads():
    for _ in range(3):
        rate_limit.record("ns", "s", 60.0)
    assert rate_limit.exceeded("ns", "s", 3, 60.0) is True
    assert rate_limit.exceeded("ns", "s", 4, 60.0) is False


@pytest.mark.unit
def test_record_charges_the_ceiling_too():
    rate_limit.record("ns:global", None, 60.0)
    assert rate_limit.exceeded("ns:global", None, 1, 60.0) is True


# ==================================================================== eviction
@pytest.mark.unit
def test_a_refused_request_buys_no_table_slot():
    """A denied call must not insert its subject: otherwise the flood that fills
    the table is not itself throttled by the limiter it is attacking."""
    assert rate_limit.allow("ns", "brand-new", 0, 60.0) is False
    assert rate_limit.tracked_subjects("ns") == 0


@pytest.mark.unit
def test_a_namespace_cannot_grow_without_bound(monkeypatch):
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_SUBJECTS_PER_NAMESPACE", 8)
    for i in range(60):
        rate_limit.allow("ns", f"subject-{i}", 3, 60.0)
    assert rate_limit.tracked_subjects("ns") == 8


@pytest.mark.unit
def test_eviction_cannot_reach_across_namespaces(monkeypatch):
    """Traffic on one endpoint must not reset another endpoint's counters.

    This is the property that makes it safe for /auth/forgot-password to key on a
    value the caller supplies: flooding any other endpoint cannot flush it, and
    flooding this one is bounded by its own (unevictable) ceiling.
    """
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_SUBJECTS_PER_NAMESPACE", 8)
    for _ in range(3):
        rate_limit.allow("forgot:email", "victim-hash", 3, 3600.0)
    assert rate_limit.allow("forgot:email", "victim-hash", 3, 3600.0) is False

    for i in range(500):                     # flood a different namespace
        rate_limit.allow("geocoding:ip", f"10.0.0.{i}", 30, 60.0)

    assert rate_limit.allow("forgot:email", "victim-hash", 3, 3600.0) is False, \
        "unrelated traffic flushed a live counter"


@pytest.mark.unit
def test_a_ceiling_survives_any_amount_of_eviction(monkeypatch):
    """A ceiling that traffic can flush is not a ceiling. It used to be an
    ordinary LRU entry, and the least recently touched one exactly while it was
    holding a lockout."""
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_SUBJECTS_PER_NAMESPACE", 8)
    for _ in range(2):
        rate_limit.allow("support:global", None, 2, 3600.0)
    assert rate_limit.allow("support:global", None, 2, 3600.0) is False

    for i in range(500):
        rate_limit.allow("support:ip", f"10.0.0.{i}", 5, 3600.0)
        rate_limit.allow("geocoding:ip", f"10.0.0.{i}", 30, 60.0)

    assert rate_limit.allow("support:global", None, 2, 3600.0) is False


@pytest.mark.unit
def test_eviction_drops_the_least_recently_touched_subject_first(monkeypatch):
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_SUBJECTS_PER_NAMESPACE", 3)
    for name in ("a", "b", "c"):
        rate_limit.allow("ns", name, 1, 60.0)
    rate_limit.allow("ns", "a", 1, 60.0)     # refused, but touches nothing new
    rate_limit.record("ns", "b", 60.0)       # b is now the most recent
    rate_limit.allow("ns", "d", 1, 60.0)     # forces one eviction

    assert rate_limit.tracked_subjects("ns") == 3
    assert rate_limit.allow("ns", "a", 1, 60.0) is True, "'a' should have been evicted"
    assert rate_limit.allow("ns", "b", 1, 60.0) is False, "'b' was touched most recently"


# ============================================================== thread safety
@pytest.mark.unit
def test_concurrent_callers_never_get_more_than_the_limit():
    """Every endpoint being budgeted here is a sync `def`, so FastAPI runs it on
    the AnyIO threadpool (40 threads). Unlocked, the read-then-append granted up
    to 2x the limit -- 2x the brute-force budget on /auth/login, 2x the invoice
    rate on /wallet/topup."""
    limit, threads = 5, 40
    for trial in range(30):
        rate_limit.reset()
        granted: list[bool] = []
        lock = threading.Lock()
        start = threading.Barrier(threads)

        def hammer() -> None:
            start.wait()
            verdict = rate_limit.allow("ns", "hot", limit, 60.0)
            with lock:
                granted.append(verdict)

        workers = [threading.Thread(target=hammer) for _ in range(threads)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()

        assert sum(granted) == limit, f"trial {trial}: granted {sum(granted)}"


@pytest.mark.unit
def test_concurrent_eviction_never_raises(monkeypatch):
    """`_HITS.get(key)` and `move_to_end(key)` were not atomic together: another
    thread's eviction between them raised KeyError, which reaches the client as a
    500 rather than a 429 and never shows up in a 429 metric."""
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_SUBJECTS_PER_NAMESPACE", 4)
    errors: list[BaseException] = []
    start = threading.Barrier(24)

    def churn(worker: int) -> None:
        try:
            start.wait()
            for i in range(400):
                rate_limit.allow("ns", f"subject-{(worker * 7 + i) % 32}", 3, 60.0)
                rate_limit.exceeded("ns", f"subject-{i % 32}", 3, 60.0)
                rate_limit.record("ns:global", None, 60.0)
        except BaseException as exc:         # noqa: BLE001 - the point is to see any
            errors.append(exc)

    workers = [threading.Thread(target=churn, args=(n,)) for n in range(24)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    assert errors == []


# ================================================================ housekeeping
@pytest.mark.unit
def test_reset_drops_subjects_and_ceilings():
    rate_limit.allow("ns", "s", 1, 60.0)
    rate_limit.allow("ns:global", None, 1, 60.0)
    rate_limit.reset()
    assert rate_limit.tracked_subjects("ns") == 0
    assert rate_limit.allow("ns:global", None, 1, 60.0) is True


@pytest.mark.unit
def test_the_per_process_caveat_is_written_down():
    """Every number in this module is per worker, and the shipped default is
    `--workers ${WEB_CONCURRENCY:-2}`. If that sentence disappears, someone will
    read the constants as deployment-wide figures."""
    doc = rate_limit.__doc__ or ""
    assert "WEB_CONCURRENCY" in doc
    assert "PER-PROCESS" in doc


# --- which address a limit is bucketed by ------------------------------------
#
# This is the regression that matters most in this file. Before the fix,
# _client_ip returned the socket peer, which behind Cloudflare -> cloudflared ->
# nginx is always loopback. Every per-IP limit was therefore ONE bucket shared by
# every user, and a single caller could lock everyone else out of login, top-up
# and charging. Proven on the deployed staging host: budget exhausted from one
# public IP, then refused 429 on the first request from a different public IP.

def _request_with(headers: dict, peer: str = "127.0.0.1"):
    from starlette.requests import Request
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 12345)})


def test_two_callers_behind_the_same_proxy_get_different_buckets():
    from api.main import _client_ip
    a = _client_ip(_request_with({"CF-Connecting-IP": "203.0.113.10"}))
    b = _client_ip(_request_with({"CF-Connecting-IP": "198.51.100.20"}))
    assert a != b, "callers sharing a proxy must not share a rate-limit bucket"
    assert (a, b) == ("203.0.113.10", "198.51.100.20")


def test_socket_peer_is_used_when_there_is_no_edge_header():
    from api.main import _client_ip
    assert _client_ip(_request_with({}, peer="192.0.2.5")) == "192.0.2.5"


def test_blank_edge_header_does_not_collapse_every_caller_into_one_bucket():
    from api.main import _client_ip
    assert _client_ip(_request_with({"CF-Connecting-IP": "   "}, peer="192.0.2.9")) == "192.0.2.9"

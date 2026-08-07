"""Rate limits on /wallet/topup and /charging/sessions, and the deliberate
absence of one on /webhooks/xendit.

What each of the two budgeted endpoints is actually protecting:

* /wallet/topup creates a REAL invoice in the production Xendit merchant account
  and spends the merchant's API quota, and it does so from a synchronous outbound
  POST whose timeout defaults to 30 seconds -- so each in-flight request also
  pins one of the ~40 shared threadpool threads that every other endpoint needs;
* /charging/sessions flips connectors.status to 'in_use', and nothing expires an
  abandoned session: there is no sweeper and no operator-side release. The seeded
  demo wallet (500,000 IDR) covers 200 minimum-cost sessions at the 2,500 IDR
  flat admin fee, and the demo password ships in the public web bundle.

Both are keyed on the authenticated user id rather than the address, because
these are the only two endpoints in the set where a real caller identity exists.

The webhook is the interesting negative case, and it has tests precisely so that
nobody adds a limiter there by symmetry: a bucket on that path would be shared
between an attacker's flood and Xendit's genuine deliveries, converting a
harmless flood into a customer who paid and was never credited.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient          # noqa: E402

from api import charging_repo, rate_limit, security, xendit   # noqa: E402
from api import wallet_repo as wallet                          # noqa: E402
from api.main import app                                       # noqa: E402

TOPUP = "/api/v1/wallet/topup"
SESSIONS = "/api/v1/charging/sessions"
WEBHOOK = "/api/v1/webhooks/xendit"

CALLBACK_TOKEN = "a-callback-token-long-enough"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _as_user(user_id: str) -> None:
    """Pretend the caller presented a valid token for `user_id`, without a token."""
    app.dependency_overrides[security.current_user] = lambda: {"id": user_id}


# ========================================================= POST /wallet/topup
@pytest.fixture
def topup_backend(monkeypatch):
    """Count invoices instead of creating them in a live merchant account."""
    invoices: list[tuple] = []

    def create_invoice(external_id, amount, description, **kwargs):
        invoices.append((external_id, amount))
        return {"id": f"inv-{len(invoices)}", "invoice_url": f"https://pay.test/{len(invoices)}"}

    def create_topup(user_id, amount_idr, external_id, invoice_id, invoice_url, topup_id=None):
        return {"topup_id": topup_id, "amount_idr": amount_idr, "status": "pending",
                "invoice_url": invoice_url}

    monkeypatch.setattr(xendit, "create_invoice", create_invoice)
    monkeypatch.setattr(wallet, "create_topup", create_topup)
    _as_user("user-a")
    return invoices


def _topup(amount: int = 50000):
    return client.post(TOPUP, json={"amount_idr": amount})


@pytest.mark.integration
def test_topup_permits_the_retries_a_real_checkout_produces(topup_backend):
    """A driver tops up maybe weekly, and the frontend polls a DIFFERENT endpoint
    while waiting, so ordinary polling never touches this counter. The budget
    covers opening checkout, abandoning it, and trying again."""
    codes = [_topup().status_code for _ in range(rate_limit.WALLET_TOPUP_RATE_LIMIT_REQUESTS)]

    assert codes == [200] * rate_limit.WALLET_TOPUP_RATE_LIMIT_REQUESTS


@pytest.mark.integration
def test_topup_blocks_an_invoice_flood(topup_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_GLOBAL_RATE_LIMIT_REQUESTS", 100)

    codes = [_topup().status_code for _ in range(6)]

    assert codes == [200, 200, 200, 429, 429, 429]


@pytest.mark.integration
def test_no_invoice_reaches_xendit_once_the_limit_is_hit(topup_backend, monkeypatch):
    """Each accepted call is a real invoice in the merchant dashboard and 30
    seconds of a shared threadpool thread in the worst case, so a shed request
    must not get as far as the provider."""
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_RATE_LIMIT_REQUESTS", 2)
    for _ in range(2):
        _topup()

    for _ in range(20):
        assert _topup().status_code == 429

    assert len(topup_backend) == 2


@pytest.mark.integration
def test_one_users_topups_do_not_spend_anothers(topup_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    for _ in range(2):
        _topup()
    assert _topup().status_code == 429

    _as_user("user-b")

    assert _topup().status_code == 200


@pytest.mark.integration
def test_the_deployment_wide_topup_ceiling_bounds_the_merchant_quota(topup_backend, monkeypatch):
    """The resource being protected -- Xendit's API quota and the merchant
    dashboard -- belongs to the deployment, not to one user."""
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_GLOBAL_RATE_LIMIT_REQUESTS", 3)

    codes = []
    for n in range(5):
        _as_user(f"user-{n}")
        codes.append(_topup().status_code)

    assert codes == [200, 200, 200, 429, 429]


@pytest.mark.integration
def test_the_topup_limit_expires(topup_backend, monkeypatch, rate_limit_clock):
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_RATE_LIMIT_REQUESTS", 1)
    _topup()
    assert _topup().status_code == 429

    rate_limit_clock.advance(rate_limit.WALLET_TOPUP_RATE_LIMIT_WINDOW_SECONDS + 1)

    assert _topup().status_code == 200


@pytest.mark.integration
def test_the_topup_429_may_be_specific_because_the_caller_owns_the_limit(topup_backend, monkeypatch):
    """Contrast with the auth endpoints: here the caller is authenticated and the
    budget is their own, so naming the wait leaks nothing about anyone else."""
    monkeypatch.setattr(rate_limit, "WALLET_TOPUP_RATE_LIMIT_REQUESTS", 1)
    _topup()

    r = _topup()

    minutes = int(rate_limit.WALLET_TOPUP_RATE_LIMIT_WINDOW_SECONDS // 60)
    assert f"{minutes} minutes" in r.json()["detail"]
    assert r.headers["Retry-After"] == \
        str(int(rate_limit.WALLET_TOPUP_RATE_LIMIT_WINDOW_SECONDS))


# ==================================================== POST /charging/sessions
@pytest.fixture
def session_backend(monkeypatch):
    """Count session starts instead of occupying connectors in the database."""
    started: list[str] = []

    def start_session(user_id, station_id, energy_kwh, station_name=None,
                      connector_type=None, power_kw=None):
        started.append(station_id)
        return {"id": f"sess-{len(started)}", "station_id": station_id,
                "energy_kwh": energy_kwh, "base_rate_idr": 2500, "admin_fee_idr": 2500,
                "deposit_idr": 5000, "status": "active", "connector_id": "conn-1",
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "wallet_balance_idr": 495000}

    monkeypatch.setattr(charging_repo, "start_session", start_session)
    _as_user("user-a")
    return started


def _start_session(station: str = "pln_spklu-1"):
    return client.post(SESSIONS, json={"station_id": station, "energy_kwh": 20})


@pytest.mark.integration
def test_sessions_permit_more_than_a_heavy_driver_needs(session_backend):
    """One session per charging stop; a heavy fleet user does 3-4 a day."""
    codes = [_start_session().status_code
             for _ in range(rate_limit.CHARGING_SESSION_RATE_LIMIT_REQUESTS)]

    assert codes == [201] * rate_limit.CHARGING_SESSION_RATE_LIMIT_REQUESTS


@pytest.mark.integration
def test_sessions_block_connector_squatting(session_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_GLOBAL_RATE_LIMIT_REQUESTS", 100)

    codes = [_start_session(f"station-{i}").status_code for i in range(6)]

    assert codes == [201, 201, 201, 429, 429, 429]


@pytest.mark.integration
def test_no_connector_is_occupied_once_the_limit_is_hit(session_backend, monkeypatch):
    """Nothing releases a connector this endpoint claims, so every start that
    gets through is state that stays wrong until the same user settles it."""
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_RATE_LIMIT_REQUESTS", 2)
    for i in range(2):
        _start_session(f"station-{i}")

    for i in range(2, 40):
        assert _start_session(f"station-{i}").status_code == 429

    assert len(session_backend) == 2


@pytest.mark.integration
def test_one_users_sessions_do_not_spend_anothers(session_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    for _ in range(2):
        _start_session()
    assert _start_session().status_code == 429

    _as_user("user-b")

    assert _start_session().status_code == 201


@pytest.mark.integration
def test_sessions_are_not_bucketed_per_station(session_backend, monkeypatch):
    """Deliberate: a per-station bucket would let one caller deny a PHYSICAL
    connector to everyone else, and it would buy nothing, because
    connectors_repo.occupy already returns None when none is free."""
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    for i in range(2):
        _start_session(f"station-{i}")

    assert _start_session("a-completely-different-station").status_code == 429, \
        "the budget follows the caller, not the station"


@pytest.mark.integration
def test_the_deployment_wide_session_ceiling_bounds_total_churn(session_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_GLOBAL_RATE_LIMIT_REQUESTS", 3)

    codes = []
    for n in range(5):
        _as_user(f"user-{n}")
        codes.append(_start_session().status_code)

    assert codes == [201, 201, 201, 429, 429]


@pytest.mark.integration
def test_the_session_limit_expires(session_backend, monkeypatch, rate_limit_clock):
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_RATE_LIMIT_REQUESTS", 1)
    _start_session()
    assert _start_session().status_code == 429

    rate_limit_clock.advance(rate_limit.CHARGING_SESSION_RATE_LIMIT_WINDOW_SECONDS + 1)

    assert _start_session().status_code == 201


@pytest.mark.integration
def test_the_session_429_carries_a_retry_after(session_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "CHARGING_SESSION_RATE_LIMIT_REQUESTS", 1)
    _start_session()

    r = _start_session()

    assert r.headers["Retry-After"] == \
        str(int(rate_limit.CHARGING_SESSION_RATE_LIMIT_WINDOW_SECONDS))


# ====================================== POST /webhooks/xendit -- NOT limited
@pytest.fixture
def webhook_backend(monkeypatch):
    credited: list[str] = []
    monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", CALLBACK_TOKEN)
    monkeypatch.setattr(wallet, "mark_paid_and_credit", lambda invoice_id: credited.append(invoice_id))
    return credited


def _deliver(token: str, invoice_id: str = "inv-1"):
    return client.post(WEBHOOK, json={"id": invoice_id, "status": "PAID"},
                       headers={"X-Callback-Token": token})


@pytest.mark.integration
def test_a_flood_of_bad_tokens_is_rejected_but_never_throttled(webhook_backend):
    """A 429 here would be a bug, not a defence: the 401 path touches no database,
    runs no bcrypt and makes no outbound call, so the flood costs nothing to
    reject."""
    codes = {_deliver("wrong-token").status_code for _ in range(200)}

    assert codes == {401}


@pytest.mark.integration
def test_a_genuine_delivery_still_credits_after_a_flood(webhook_backend):
    """The reason the webhook is left open. Any bucket here is effectively global
    (Xendit's egress is one address), so an attacker's flood would exhaust the
    same budget a real callback needs -- and a dropped callback is money the user
    paid and was never credited, recovered only if they happen to return to the
    polling screen. There is no reconciliation job."""
    for _ in range(200):
        _deliver("wrong-token")

    r = _deliver(CALLBACK_TOKEN, "inv-real")

    assert r.status_code == 200
    assert webhook_backend == ["inv-real"]


@pytest.mark.integration
def test_the_webhook_creates_no_limiter_state_at_all(webhook_backend):
    """Not even a counter that is never enforced: a bucket recorded here is one
    refactor away from being checked."""
    for _ in range(50):
        _deliver("wrong-token")
    _deliver(CALLBACK_TOKEN)

    assert rate_limit._SUBJECTS == {}
    assert rate_limit._CEILINGS == {}


@pytest.mark.integration
def test_repeated_genuine_deliveries_are_never_throttled(webhook_backend):
    """Xendit retries, and after a provider outage the queued callbacks arrive in
    a burst -- exactly the traffic shape a limiter sheds, carrying exactly the
    backlog of real payments."""
    codes = {_deliver(CALLBACK_TOKEN, f"inv-{i}").status_code for i in range(100)}

    assert codes == {200}
    assert len(webhook_backend) == 100

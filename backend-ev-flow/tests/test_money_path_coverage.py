"""Behaviour tests for the money path: wallet, Xendit top-ups, charging sessions.

Everything here is about money moving (or provably NOT moving). Assertions use
real numbers derived from api/pricing.py's tariff, which the tests pin via env
(CHARGING_BASE_RATE_IDR=2466, CHARGING_ADMIN_FEE_IDR=2500) so a silent tariff
change cannot make a wrong number look right.

Conventions:
  - DB-backed tests carry @requires_db and create their own user, station and
    connectors so they never share state with another test.
  - No test makes a real network call. Xendit is either injected as a fake or
    pointed at a closed port (127.0.0.1:9).
  - Tests marked xfail document a defect that was found while writing them; the
    assertion is what SHOULD happen, never what the code currently does. See the
    reason string on each for the bug being tracked.
"""
from __future__ import annotations

import contextlib
import threading
import uuid

import pytest
from sqlalchemy import text

from tests.conftest import requires_db

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
import httpx                                 # noqa: E402
from fastapi.testclient import TestClient    # noqa: E402

from api import pricing, xendit              # noqa: E402

JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"   # >= 32 chars
CALLBACK_TOKEN = "money-path-callback-token-0123"      # >= 16 chars
CLOSED_PORT_URL = "http://127.0.0.1:9"                 # nothing listens here

RATE = 2466
FEE = 2500
# 20 kWh at the pinned tariff. Recomputed from pricing so the constant and the
# implementation can never disagree silently.
DEPOSIT_20 = 20 * RATE + FEE            # 51_820


def _setup_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", str(RATE))
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", str(FEE))
    monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", CALLBACK_TOKEN)
    monkeypatch.delenv("FRONTEND_URL", raising=False)


def _fake_xendit(monkeypatch, captured=None, status="PENDING"):
    """Invoice id derives from external_id so the webhook can address it."""
    def create_invoice(ext, amt, desc, **kw):
        if captured is not None:
            captured.append({"external_id": ext, "amount": amt, "description": desc, **kw})
        return {"id": f"inv-{ext}", "invoice_url": f"https://checkout.test/{ext}", "status": status}
    monkeypatch.setattr(xendit, "create_invoice", create_invoice)


def _register(client) -> tuple[dict, str]:
    """Create a fresh user; return (auth header, user_id)."""
    uname = "money-" + uuid.uuid4().hex[:10]
    reg = client.post("/api/v1/auth/register", json={"username": uname, "password": "s3cret123"})
    assert reg.status_code == 201, reg.text
    body = reg.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def _fund(client, auth, amount_idr: int) -> str:
    """Top up through the real invoice -> webhook credit path. Returns invoice id."""
    created = client.post("/api/v1/wallet/topup", json={"amount_idr": amount_idr}, headers=auth)
    assert created.status_code == 200, created.text
    inv_id = client.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]
    hook = client.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                       headers={"x-callback-token": CALLBACK_TOKEN})
    assert hook.status_code == 200
    return inv_id


# ----------------------------------------------------------------- DB helpers
def _balance(user_id: str) -> int:
    from api.db import engine
    with engine.connect() as c:
        return int(c.execute(text("SELECT balance_idr FROM wallet WHERE user_id = :u"),
                             {"u": user_id}).scalar())


def _session_count(user_id: str) -> int:
    from api.db import engine
    with engine.connect() as c:
        return int(c.execute(text("SELECT count(*) FROM charging_sessions WHERE user_id = :u"),
                             {"u": user_id}).scalar())


def _connector_statuses(station_id: str) -> dict:
    from api.db import engine
    with engine.connect() as c:
        rows = c.execute(text("SELECT status, count(*) FROM connectors WHERE station_id = :s GROUP BY status"),
                         {"s": station_id}).all()
    return {status: int(n) for status, n in rows}


@contextlib.contextmanager
def _temp_station(n_connectors: int = 2, ctype: str = "CCS2"):
    """A private station + connectors, torn down afterwards (CASCADE)."""
    from api.db import engine
    station_id = "test_money-" + uuid.uuid4().hex[:12]
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO stations (id, geom, name, operator, power_kw, speed_tier, connector_types)
                VALUES (:id, ST_SetSRID(ST_MakePoint(106.8, -6.2), 4326), 'Money Path Test', 'TEST',
                        150, 'fast', ARRAY[:ct])
            """), {"id": station_id, "ct": ctype})
            for _ in range(n_connectors):
                c.execute(text("""
                    INSERT INTO connectors (id, station_id, type, power_kw, speed_tier, status)
                    VALUES (gen_random_uuid(), :sid, :ct, 150, 'fast', 'available')
                """), {"sid": station_id, "ct": ctype})
        yield station_id
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM stations WHERE id = :id"), {"id": station_id})


# =============================================================== xendit client
# Pure unit tests: no DB, no network (closed port for the transport failures).
@pytest.mark.unit
def test_create_invoice_forwards_redirect_urls(monkeypatch):
    monkeypatch.setenv("XENDIT_SECRET_KEY", "sk_test")
    monkeypatch.setenv("XENDIT_BASE_URL", "https://api.xendit.co")
    monkeypatch.setenv("XENDIT_TIMEOUT_SECONDS", "7.5")
    captured = {}

    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {"id": "inv_9", "invoice_url": "https://checkout/inv_9", "status": "PENDING"}

    monkeypatch.setattr(xendit.httpx, "post", lambda url, **kw: (captured.update(url=url, **kw) or _Resp()))
    out = xendit.create_invoice("ext-9", 50000, "Top up",
                                success_redirect_url="https://app/ok",
                                failure_redirect_url="https://app/fail")
    assert out["id"] == "inv_9"
    assert captured["json"]["success_redirect_url"] == "https://app/ok"
    assert captured["json"]["failure_redirect_url"] == "https://app/fail"
    assert captured["timeout"] == 7.5


@pytest.mark.unit
def test_create_invoice_omits_redirect_urls_when_not_given(monkeypatch):
    monkeypatch.setenv("XENDIT_SECRET_KEY", "sk_test")
    captured = {}

    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {"id": "i", "invoice_url": "u", "status": "PENDING"}

    monkeypatch.setattr(xendit.httpx, "post", lambda url, **kw: (captured.update(**kw) or _Resp()))
    xendit.create_invoice("ext", 10000, "d")
    assert "success_redirect_url" not in captured["json"]
    assert "failure_redirect_url" not in captured["json"]


@pytest.mark.unit
def test_create_invoice_unreachable_provider_raises_xendit_error(monkeypatch):
    """A dead payment provider must surface as XenditError, not a raw httpx error:
    main.py only maps XenditError to 502."""
    monkeypatch.setenv("XENDIT_SECRET_KEY", "sk_test")
    monkeypatch.setenv("XENDIT_BASE_URL", CLOSED_PORT_URL)
    monkeypatch.setenv("XENDIT_TIMEOUT_SECONDS", "2")
    with pytest.raises(xendit.XenditError) as e:
        xendit.create_invoice("ext", 10000, "d")
    assert "Xendit request failed" in str(e.value)


@pytest.mark.unit
def test_get_invoice_parses_id_and_status(monkeypatch):
    monkeypatch.setenv("XENDIT_SECRET_KEY", "sk_test")
    monkeypatch.setenv("XENDIT_BASE_URL", "https://api.xendit.co")
    monkeypatch.setenv("XENDIT_TIMEOUT_SECONDS", "11")
    captured = {}

    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {"id": "inv_1", "status": "PAID", "amount": 999999, "ignored": True}

    monkeypatch.setattr(xendit.httpx, "get", lambda url, **kw: (captured.update(url=url, **kw) or _Resp()))
    # Only id+status are trusted from the provider; the amount is never read back
    # (the wallet credits the amount stored at top-up creation).
    assert xendit.get_invoice("inv_1") == {"id": "inv_1", "status": "PAID"}
    assert captured["url"] == "https://api.xendit.co/v2/invoices/inv_1"
    assert captured["auth"] == ("sk_test", "")
    assert captured["timeout"] == 11.0


@pytest.mark.unit
def test_get_invoice_requires_secret_key(monkeypatch):
    monkeypatch.delenv("XENDIT_SECRET_KEY", raising=False)
    monkeypatch.setattr(xendit.httpx, "get",
                        lambda *a, **k: pytest.fail("must not call out without a key"))
    with pytest.raises(xendit.XenditError, match="XENDIT_SECRET_KEY"):
        xendit.get_invoice("inv_1")


@pytest.mark.unit
def test_get_invoice_error_status_raises_with_body(monkeypatch):
    monkeypatch.setenv("XENDIT_SECRET_KEY", "sk_test")

    class _Err:
        status_code = 404
        text = "INVOICE_NOT_FOUND"
        def json(self):  # must never be reached
            raise AssertionError("body parsed despite error status")

    monkeypatch.setattr(xendit.httpx, "get", lambda url, **kw: _Err())
    with pytest.raises(xendit.XenditError) as e:
        xendit.get_invoice("inv_missing")
    assert "404" in str(e.value) and "INVOICE_NOT_FOUND" in str(e.value)


@pytest.mark.unit
def test_get_invoice_unreachable_provider_raises_xendit_error(monkeypatch):
    monkeypatch.setenv("XENDIT_SECRET_KEY", "sk_test")
    monkeypatch.setenv("XENDIT_BASE_URL", CLOSED_PORT_URL)
    monkeypatch.setenv("XENDIT_TIMEOUT_SECONDS", "2")
    with pytest.raises(xendit.XenditError, match="Xendit request failed"):
        xendit.get_invoice("inv_1")


@pytest.mark.unit
def test_xendit_error_is_catchable_as_runtime_error():
    """main.py catches xendit.XenditError; connect() failures inside httpx are
    httpx.HTTPError subclasses, so the except clause in xendit.py really covers them."""
    assert issubclass(xendit.XenditError, RuntimeError)
    assert issubclass(httpx.ConnectError, httpx.HTTPError)
    assert issubclass(httpx.TimeoutException, httpx.HTTPError)


# ============================================================ topup + webhook
@requires_db
def test_topup_sends_redirect_urls_pointing_at_the_created_topup(monkeypatch):
    """The success URL must carry the SAME topup_id that was persisted, otherwise
    the frontend polls a top-up that does not exist and never credits."""
    _setup_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com/")
    captured = []
    _fake_xendit(monkeypatch, captured)
    from api import main
    with TestClient(main.app) as c:
        auth, _ = _register(c)
        created = c.post("/api/v1/wallet/topup", json={"amount_idr": 25000}, headers=auth).json()
        assert len(captured) == 1
        call = captured[0]
        assert call["amount"] == 25000
        assert call["success_redirect_url"] == \
            f"https://app.example.com/ev-driver/wallet/topup/success?topup_id={created['topup_id']}"
        assert call["failure_redirect_url"] == "https://app.example.com/ev-driver/wallet/topup"
        # and the topup really is retrievable under that id
        assert c.get(f"/api/v1/wallet/topups/{created['topup_id']}",
                     headers=auth).json()["amount_idr"] == 25000


@requires_db
def test_provider_failure_creates_no_topup_row(monkeypatch):
    """A 502 from the provider must leave no phantom pending top-up behind."""
    _setup_env(monkeypatch)

    def boom(*a, **k):
        raise xendit.XenditError("provider down")

    monkeypatch.setattr(xendit, "create_invoice", boom)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        before = _balance(uid)
        resp = c.post("/api/v1/wallet/topup", json={"amount_idr": 50000}, headers=auth)
        assert resp.status_code == 502
        assert "provider down" in resp.json()["detail"]
        assert c.get("/api/v1/wallet/topups", headers=auth).json() == []
        assert _balance(uid) == before


@requires_db
def test_poll_survives_provider_outage_without_crediting(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)

    def boom(_inv):
        raise xendit.XenditError("provider unreachable")

    monkeypatch.setattr(xendit, "get_invoice", boom)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        created = c.post("/api/v1/wallet/topup", json={"amount_idr": 40000}, headers=auth).json()
        polled = c.get(f"/api/v1/wallet/topups/{created['topup_id']}", headers=auth)
        assert polled.status_code == 200
        assert polled.json()["status"] == "pending"
        assert polled.json()["paid_at"] is None
        assert _balance(uid) == 0


@requires_db
def test_webhook_with_wrong_or_missing_token_credits_nothing(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        created = c.post("/api/v1/wallet/topup", json={"amount_idr": 50000}, headers=auth).json()
        inv_id = c.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]

        wrong = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                       headers={"x-callback-token": "not-the-right-token-at-all"})
        assert wrong.status_code == 401
        missing = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"})
        assert missing.status_code == 401
        # a token that is a strict PREFIX of the real one must not pass either
        prefix = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                        headers={"x-callback-token": CALLBACK_TOKEN[:-1]})
        assert prefix.status_code == 401

        assert _balance(uid) == 0
        assert c.get(f"/api/v1/wallet/topups/{created['topup_id']}",
                     headers=auth).json()["status"] == "pending"


@requires_db
def test_webhook_fails_closed_when_token_is_unset_or_weak(monkeypatch):
    """Without a strong configured token anyone could credit wallets, so the
    endpoint must refuse to run at all rather than accept the call."""
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        inv_id = f"inv-{uuid.uuid4()}"
        c.post("/api/v1/wallet/topup", json={"amount_idr": 50000}, headers=auth)
        inv_id = c.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]

        monkeypatch.delenv("XENDIT_CALLBACK_TOKEN", raising=False)
        unset = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                       headers={"x-callback-token": CALLBACK_TOKEN})
        assert unset.status_code == 503

        monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", "short")   # < 16 chars
        weak = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                      headers={"x-callback-token": "short"})
        assert weak.status_code == 503

        assert _balance(uid) == 0


@requires_db
def test_webhook_for_unknown_invoice_credits_nothing(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 50000)
        assert _balance(uid) == 50000

        # 200 so Xendit stops retrying, but no money may move.
        unknown = c.post("/api/v1/webhooks/xendit",
                         json={"id": f"inv-does-not-exist-{uuid.uuid4()}", "status": "PAID"},
                         headers={"x-callback-token": CALLBACK_TOKEN})
        assert unknown.status_code == 200
        assert _balance(uid) == 50000


@requires_db
def test_duplicate_webhook_neither_double_credits_nor_moves_paid_at(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        created = c.post("/api/v1/wallet/topup", json={"amount_idr": 75000}, headers=auth).json()
        inv_id = c.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]

        c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
               headers={"x-callback-token": CALLBACK_TOKEN})
        first = c.get(f"/api/v1/wallet/topups/{created['topup_id']}", headers=auth).json()
        assert first["status"] == "paid" and first["paid_at"] is not None
        assert _balance(uid) == 75000

        for _ in range(3):
            dup = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                         headers={"x-callback-token": CALLBACK_TOKEN})
            assert dup.status_code == 200
        again = c.get(f"/api/v1/wallet/topups/{created['topup_id']}", headers=auth).json()
        assert _balance(uid) == 75000
        assert again["paid_at"] == first["paid_at"]


@requires_db
def test_wallet_endpoints_require_auth(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        assert c.get("/api/v1/wallet").status_code == 401
        assert c.get("/api/v1/wallet/topups").status_code == 401
        assert c.post("/api/v1/wallet/topup", json={"amount_idr": 50000}).status_code == 401
        assert c.get(f"/api/v1/wallet/topups/{uuid.uuid4()}").status_code == 401


@requires_db
def test_topups_and_balances_are_scoped_to_their_owner(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth_a, uid_a = _register(c)
        auth_b, uid_b = _register(c)
        created_a = c.post("/api/v1/wallet/topup", json={"amount_idr": 60000}, headers=auth_a).json()
        inv_a = c.get("/api/v1/wallet/topups", headers=auth_a).json()[0]["xendit_invoice_id"]
        c.post("/api/v1/webhooks/xendit", json={"id": inv_a, "status": "PAID"},
               headers={"x-callback-token": CALLBACK_TOKEN})

        # B sees neither A's top-up nor A's money
        assert c.get("/api/v1/wallet/topups", headers=auth_b).json() == []
        assert c.get(f"/api/v1/wallet/topups/{created_a['topup_id']}", headers=auth_b).status_code == 404
        assert c.get("/api/v1/wallet", headers=auth_b).json()["balance_idr"] == 0
        assert _balance(uid_a) == 60000
        assert _balance(uid_b) == 0


# ================================================= charging session money path
@requires_db
def test_deposit_debit_is_atomic_with_the_session_insert(monkeypatch):
    """If the session row cannot be written the deposit must not leave the wallet.

    energy_kwh=0 passes pricing (deposit = the flat admin fee) but violates the
    charging_sessions CHECK (energy_kwh > 0), so the insert fails AFTER the
    conditional debit has already run. Nothing may survive that.
    """
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main, charging_repo
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 100000)
        before_balance, before_sessions = _balance(uid), _session_count(uid)
        assert before_balance == 100000

        with pytest.raises(Exception):
            charging_repo.start_session(user_id=uid, station_id="pln_spklu-1", energy_kwh=0.0)

        assert _balance(uid) == before_balance
        assert _session_count(uid) == before_sessions


@requires_db
def test_insufficient_balance_changes_absolutely_nothing(monkeypatch):
    """One rupiah short of the deposit: 402, and balance, session count and
    connector inventory must all be byte-identical afterwards."""
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with _temp_station(2) as station_id, TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, DEPOSIT_20 - 1)
        before_balance = _balance(uid)
        before_connectors = _connector_statuses(station_id)
        assert before_balance == DEPOSIT_20 - 1
        assert before_connectors == {"available": 2}

        resp = c.post("/api/v1/charging/sessions",
                      json={"station_id": station_id, "energy_kwh": 20, "connector_type": "CCS2"},
                      headers=auth)
        assert resp.status_code == 402
        assert str(DEPOSIT_20) in resp.json()["detail"]

        assert _balance(uid) == before_balance
        assert _session_count(uid) == 0
        assert c.get("/api/v1/charging/sessions", headers=auth).json() == []
        assert _connector_statuses(station_id) == before_connectors


@requires_db
def test_delivered_above_purchased_is_capped_at_the_deposit(monkeypatch):
    """A client claiming more kWh than it bought must not be billed for them."""
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 200000)
        before = _balance(uid)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20}, headers=auth).json()
        assert session["deposit_idr"] == DEPOSIT_20

        settled = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                         json={"delivered_kwh": 499}, headers=auth)
        assert settled.status_code == 200
        s = settled.json()
        assert s["delivered_kwh"] == 20.0                     # clamped to what was purchased
        assert s["actual_cost_idr"] == DEPOSIT_20             # never more than the deposit
        assert s["refund_idr"] == 0
        assert s["wallet_balance_idr"] == before - DEPOSIT_20
        assert _balance(uid) == before - DEPOSIT_20


@requires_db
def test_negative_delivered_kwh_is_rejected_and_never_inflates_the_refund(monkeypatch):
    """The API rejects a negative reading outright (session untouched), and the
    repo clamps it to 0 so it can never refund more than the energy portion."""
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main, charging_repo
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 200000)
        before = _balance(uid)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20}, headers=auth).json()

        bad = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                     json={"delivered_kwh": -5}, headers=auth)
        assert bad.status_code == 422
        assert c.get(f"/api/v1/charging/sessions/{session['id']}",
                     headers=auth).json()["status"] == "active"
        assert _balance(uid) == before - DEPOSIT_20

        too_big = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                         json={"delivered_kwh": 501}, headers=auth)
        assert too_big.status_code == 422

        # Repo level (an internal caller bypassing the schema) clamps to 0:
        # billed only the admin fee, refund = the whole energy portion, no more.
        out = charging_repo.settle_session(uid, session["id"], -5.0)
        assert out["delivered_kwh"] == 0.0
        assert out["actual_cost_idr"] == FEE
        assert out["refund_idr"] == DEPOSIT_20 - FEE == 20 * RATE
        assert _balance(uid) == before - FEE


@requires_db
def test_settle_releases_the_connector_exactly_once(monkeypatch):
    """The connector goes back to 'available' on settle, and a repeat settle must
    not release whatever connector is in use by then (it would free someone
    else's live session)."""
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with _temp_station(1) as station_id, TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 300000)

        first = c.post("/api/v1/charging/sessions",
                       json={"station_id": station_id, "energy_kwh": 20, "connector_type": "CCS2"},
                       headers=auth).json()
        assert first["connector_id"] is not None
        assert _connector_statuses(station_id) == {"in_use": 1}

        c.post(f"/api/v1/charging/sessions/{first['id']}/settle",
               json={"delivered_kwh": 16.5}, headers=auth)
        assert _connector_statuses(station_id) == {"available": 1}
        balance_after_first = _balance(uid)

        # a second session grabs the same (only) connector
        second = c.post("/api/v1/charging/sessions",
                        json={"station_id": station_id, "energy_kwh": 20, "connector_type": "CCS2"},
                        headers=auth).json()
        assert second["connector_id"] == first["connector_id"]
        assert _connector_statuses(station_id) == {"in_use": 1}

        # re-settling the FIRST session must not free the second session's connector
        repeat = c.post(f"/api/v1/charging/sessions/{first['id']}/settle",
                        json={"delivered_kwh": 16.5}, headers=auth)
        assert repeat.status_code == 200
        assert _connector_statuses(station_id) == {"in_use": 1}
        assert _balance(uid) == balance_after_first - DEPOSIT_20   # only the 2nd deposit moved


@requires_db
def test_settle_racing_another_settle_credits_the_refund_once(monkeypatch):
    """Two settles interleaved so both read the session while it is still active.

    The loser's conditional UPDATE matches no row; it must re-read and return the
    stored settlement rather than crediting a second refund.
    """
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main, charging_repo
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 200000)
        before = _balance(uid)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20}, headers=auth).json()

        real_settlement = pricing.settlement
        parked = threading.Event()
        resume = threading.Event()
        lock = threading.Lock()
        seen = []

        def hooked(energy_kwh, delivered_kwh):
            out = real_settlement(energy_kwh, delivered_kwh)
            with lock:
                first_caller = not seen
                seen.append(1)
            if first_caller:            # park the loser mid-transaction
                parked.set()
                assert resume.wait(20)
            return out

        monkeypatch.setattr(charging_repo.pricing, "settlement", hooked)

        loser: dict = {}

        def run_loser():
            loser["result"] = charging_repo.settle_session(uid, session["id"], 16.5)

        t = threading.Thread(target=run_loser)
        t.start()
        assert parked.wait(20), "loser thread never reached the settlement hook"
        winner = charging_repo.settle_session(uid, session["id"], 16.5)   # commits first
        resume.set()
        t.join(20)
        assert not t.is_alive()

        expected_cost = round(16.5 * RATE) + FEE
        expected_refund = DEPOSIT_20 - expected_cost
        assert winner["refund_idr"] == expected_refund
        assert loser["result"]["refund_idr"] == expected_refund
        assert loser["result"]["status"] == "completed"
        assert loser["result"]["id"] == winner["id"]
        # the refund landed exactly once
        assert _balance(uid) == before - expected_cost
        assert loser["result"]["wallet_balance_idr"] == before - expected_cost


@requires_db
def test_concurrent_starts_cannot_overdraw_the_wallet(monkeypatch):
    """Wallet funded for exactly one deposit; two simultaneous starts must yield
    one session and one InsufficientBalance, never two sessions or a negative
    balance."""
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main, charging_repo
    with _temp_station(4) as station_id, TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, DEPOSIT_20)
        assert _balance(uid) == DEPOSIT_20

        barrier = threading.Barrier(2)
        results: list = []

        def start():
            barrier.wait(20)
            try:
                results.append(("ok", charging_repo.start_session(
                    user_id=uid, station_id=station_id, energy_kwh=20, connector_type="CCS2")))
            except charging_repo.InsufficientBalance as e:
                results.append(("rejected", str(e)))

        threads = [threading.Thread(target=start) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)

        kinds = sorted(k for k, _ in results)
        assert kinds == ["ok", "rejected"], results
        assert _balance(uid) == 0
        assert _session_count(uid) == 1
        assert _connector_statuses(station_id) == {"available": 3, "in_use": 1}


@requires_db
def test_connector_claim_failure_rolls_back_only_the_claim(monkeypatch):
    """The connector claim runs in a SAVEPOINT: if it explodes AFTER marking a
    connector in_use, that write must be undone while the deposit debit and the
    session row survive."""
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main, charging_repo, connectors_repo
    real_occupy = connectors_repo.occupy
    with _temp_station(2) as station_id, TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 200000)
        before = _balance(uid)

        def occupy_then_explode(conn, sid, ctype=None):
            real_occupy(conn, sid, ctype)          # really flips a row to in_use
            raise RuntimeError("simulated connector-inventory failure")

        monkeypatch.setattr(charging_repo.connectors_repo, "occupy", occupy_then_explode)
        started = c.post("/api/v1/charging/sessions",
                         json={"station_id": station_id, "energy_kwh": 20, "connector_type": "CCS2"},
                         headers=auth)
        assert started.status_code == 201
        session = started.json()
        assert session["status"] == "active"
        assert session["connector_id"] is None            # no connector was claimed
        assert session["deposit_idr"] == DEPOSIT_20
        assert session["wallet_balance_idr"] == before - DEPOSIT_20
        assert _balance(uid) == before - DEPOSIT_20       # charging is not blocked on inventory
        assert _connector_statuses(station_id) == {"available": 2}   # claim fully rolled back


@requires_db
def test_connector_release_failure_never_blocks_the_refund(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main, charging_repo
    calls: list = []
    with _temp_station(1) as station_id, TestClient(main.app) as c:
        auth, uid = _register(c)
        _fund(c, auth, 200000)
        before = _balance(uid)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": station_id, "energy_kwh": 20, "connector_type": "CCS2"},
                         headers=auth).json()
        assert session["connector_id"] is not None

        def release_explodes(conn, connector_id):
            calls.append(connector_id)
            raise RuntimeError("simulated release failure")

        monkeypatch.setattr(charging_repo.connectors_repo, "release", release_explodes)
        settled = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                         json={"delivered_kwh": 16.5}, headers=auth)
        assert settled.status_code == 200
        s = settled.json()
        expected_cost = round(16.5 * RATE) + FEE
        assert calls == [session["connector_id"]]        # release really was attempted
        assert s["status"] == "completed"
        assert s["refund_idr"] == DEPOSIT_20 - expected_cost
        assert _balance(uid) == before - expected_cost   # the money is correct regardless


@requires_db
def test_wallet_row_is_created_on_demand_for_a_user_without_one(monkeypatch):
    """Reads must not 500 for a user whose wallet row was never written (a user
    created outside the register endpoint, e.g. by an import or a migration)."""
    _setup_env(monkeypatch)
    from api import charging_repo, users_repo, security, wallet_repo
    from api.db import engine
    user = users_repo.create_user(username="orphan-" + uuid.uuid4().hex[:10],
                                  password_hash=security.hash_password("s3cret123"))
    uid = user["id"]
    try:
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM wallet WHERE user_id = :u"),
                             {"u": uid}).scalar() == 0
        # Read paths must report an empty, zero-balance wallet rather than 500.
        assert charging_repo.list_sessions(uid) == []
        assert charging_repo.get_session(uid, str(uuid.uuid4())) is None
        # The first write-path touch is what actually persists the wallet at 0.
        assert wallet_repo.get_wallet(uid)["balance_idr"] == 0
        assert _balance(uid) == 0
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM wallet WHERE user_id = :u"), {"u": uid})
            c.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})


@requires_db
def test_another_users_session_is_invisible_and_unsettleable(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main, charging_repo
    with TestClient(main.app) as c:
        auth_a, uid_a = _register(c)
        auth_b, uid_b = _register(c)
        _fund(c, auth_a, 200000)
        _fund(c, auth_b, 200000)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20}, headers=auth_a).json()
        balance_a, balance_b = _balance(uid_a), _balance(uid_b)

        assert c.get(f"/api/v1/charging/sessions/{session['id']}", headers=auth_b).status_code == 404
        assert c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                      json={"delivered_kwh": 20}, headers=auth_b).status_code == 404
        assert charging_repo.settle_session(uid_b, session["id"], 20) is None
        assert c.get("/api/v1/charging/sessions", headers=auth_b).json() == []

        # neither wallet moved, and A's session is still settleable
        assert _balance(uid_a) == balance_a
        assert _balance(uid_b) == balance_b
        assert c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                      json={"delivered_kwh": 20}, headers=auth_a).status_code == 200
        assert _balance(uid_a) == balance_a          # 20 kWh delivered -> refund 0
        assert _balance(uid_b) == balance_b


# =================================================================== bug xfails
# Each of these asserts the behaviour the money path SHOULD have. They fail today.
@requires_db
@pytest.mark.xfail(reason="BUG: the webhook only credits on status=='PAID'. The polling "
                          "path in main.wallet_topup_status treats SETTLED as paid too, so a "
                          "SETTLED callback silently leaves the user's money uncredited.",
                   strict=True)
def test_webhook_credits_on_settled_status(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth, uid = _register(c)
        c.post("/api/v1/wallet/topup", json={"amount_idr": 50000}, headers=auth)
        inv_id = c.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]
        resp = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "SETTLED"},
                      headers={"x-callback-token": CALLBACK_TOKEN})
        assert resp.status_code == 200
        assert _balance(uid) == 50000


@requires_db
@pytest.mark.xfail(reason="BUG: topups.user_id is 'ON DELETE SET NULL', so a NULL user_id is a "
                          "state the schema produces. mark_paid_and_credit interpolates str(None) "
                          "into a uuid comparison and raises DataError, so the webhook 500s and "
                          "Xendit retries the callback forever.",
                   strict=True)
def test_credit_of_an_orphaned_topup_does_not_explode():
    from api import wallet_repo
    from api.db import engine
    topup_id, inv_id = str(uuid.uuid4()), "inv-orphan-" + uuid.uuid4().hex
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO topups (id, user_id, external_id, xendit_invoice_id, amount_idr, status)
                VALUES (:id, NULL, :ext, :inv, 50000, 'pending')
            """), {"id": topup_id, "ext": "orphan-" + topup_id, "inv": inv_id})
        # There is no wallet to credit, so this must report "nothing credited",
        # not raise. Raising turns every retry into a 500.
        assert wallet_repo.mark_paid_and_credit(inv_id) is False
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM topups WHERE id = :id"), {"id": topup_id})


@requires_db
@pytest.mark.xfail(reason="BUG: wallet rows pick their PK with (SELECT MAX(id)+1 FROM wallet) "
                          "instead of a sequence. Concurrent first-wallet creations read the same "
                          "MAX and collide on wallet_pkey, so simultaneous registrations 500.",
                   strict=False)
def test_concurrent_first_wallet_creation_does_not_collide():
    from api import wallet_repo, users_repo, security
    from api.db import engine
    users = [users_repo.create_user(username="race-" + uuid.uuid4().hex[:10],
                                    password_hash=security.hash_password("s3cret123"))["id"]
             for _ in range(6)]
    errors: list = []
    try:
        barrier = threading.Barrier(len(users))

        def make(uid):
            barrier.wait(20)
            try:
                wallet_repo.get_wallet(uid)
            except Exception as e:            # noqa: BLE001 - recording, not swallowing
                errors.append(f"{type(e).__name__}: {e}")

        threads = [threading.Thread(target=make, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert errors == []
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM wallet WHERE user_id = ANY(:u)"),
                             {"u": users}).scalar() == len(users)
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM wallet WHERE user_id = ANY(:u)"), {"u": users})
            c.execute(text("DELETE FROM users WHERE id = ANY(:u)"), {"u": users})


@requires_db
@pytest.mark.xfail(reason="BUG: wallet.id is smallint and is assigned as MAX(id)+1, so the "
                          "32768th wallet cannot be created: every new user from then on gets a "
                          "'smallint out of range' 500 on registration.",
                   strict=True)
def test_wallet_creation_is_not_capped_at_32767_users():
    """The 32767th wallet must be creatable.

    The sentinel row this test inserts occupies the top of the smallint range,
    so while it exists NO wallet can be created anywhere in this database. The
    window is kept to a single call and the row is owned by `holder`, so the
    per-user cleanup below removes it; nothing outside the two users this test
    creates is ever touched.
    """
    from api import wallet_repo, users_repo, security
    from api.db import engine

    with engine.connect() as c:
        squatter = c.execute(text("SELECT count(*) FROM wallet WHERE id >= 32767")).scalar()
    if squatter:
        pytest.skip("this database already has a wallet at the smallint ceiling; "
                    "refusing to touch rows this test does not own")

    holder = users_repo.create_user(username="cap1-" + uuid.uuid4().hex[:10],
                                    password_hash=security.hash_password("s3cret123"))["id"]
    newcomer = users_repo.create_user(username="cap2-" + uuid.uuid4().hex[:10],
                                      password_hash=security.hash_password("s3cret123"))["id"]
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO wallet (id, user_id, balance_idr) VALUES (32767, :u, 0)"),
                      {"u": holder})
        assert wallet_repo.get_wallet(newcomer)["balance_idr"] == 0
    finally:
        with engine.begin() as c:
            # The sentinel IS holder's wallet, so this removes it too. Deleting by
            # user_id only guarantees we never delete a row we did not create.
            c.execute(text("DELETE FROM wallet WHERE user_id = ANY(:u)"), {"u": [holder, newcomer]})
            c.execute(text("DELETE FROM users WHERE id = ANY(:u)"), {"u": [holder, newcomer]})
        with engine.connect() as c:
            leaked = c.execute(text("SELECT count(*) FROM wallet WHERE id = 32767")).scalar()
        if leaked:
            raise AssertionError(
                "the id=32767 sentinel outlived this test; wallet creation is now bricked "
                "for this database until that row is deleted")


@requires_db
@pytest.mark.xfail(reason="BUG: TopupRequest.amount_idr has ge=10000 but no upper bound, so an "
                          "absurd amount reaches the bigint column and 500s (a DB DataError) "
                          "instead of being rejected as bad input at the boundary.",
                   strict=True)
def test_absurd_topup_amount_is_rejected_as_bad_input(monkeypatch):
    _setup_env(monkeypatch)
    _fake_xendit(monkeypatch)
    from api import main
    with TestClient(main.app, raise_server_exceptions=False) as c:
        auth, uid = _register(c)
        resp = c.post("/api/v1/wallet/topup", json={"amount_idr": 10 ** 19}, headers=auth)
        assert resp.status_code in (400, 422), resp.status_code
        assert _balance(uid) == 0

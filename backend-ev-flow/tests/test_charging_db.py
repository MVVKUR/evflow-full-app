"""DB-backed tests for the charging-session flow against the real wallet.

Charging endpoints are user-scoped: each test registers a fresh user and sends
its Bearer token, so tests never share wallet or session state.
"""
import uuid

import pytest

from tests.conftest import requires_db

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402

JWT_SECRET = "unit-test-jwt-secret-0123456789abcdef"          # >= 32 chars
CALLBACK_TOKEN = "unit-test-callback-token"                   # >= 16 chars


def _setup_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", CALLBACK_TOKEN)


def _mock_xendit(monkeypatch):
    from api import xendit
    monkeypatch.setattr(xendit, "create_invoice",
                        lambda ext, amt, desc, *a, **k: {"id": f"inv-{ext}", "invoice_url": f"https://c/{ext}",
                                                         "status": "PENDING"})


def _register(client) -> dict:
    """Create a fresh user and return its Authorization header."""
    uname = "charge-" + uuid.uuid4().hex[:8]
    reg = client.post("/api/v1/auth/register",
                      json={"username": uname, "password": "s3cret123"})
    assert reg.status_code == 201
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _credit_wallet(client, auth, amount):
    """Top up this user's wallet via the Xendit webhook path so tests have funds."""
    client.post("/api/v1/wallet/topup", json={"amount_idr": amount}, headers=auth)
    # invoice id derives from external_id in the mocked create_invoice
    inv_id = client.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]
    client.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                headers={"x-callback-token": CALLBACK_TOKEN})


@requires_db
def test_quote_matches_pricing(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth = _register(c)
        q = c.post("/api/v1/charging/quote", json={"energy_kwh": 20}, headers=auth).json()
        assert q["total_due_idr"] == 51820


@requires_db
def test_charging_requires_auth(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        assert c.post("/api/v1/charging/quote",
                      json={"energy_kwh": 20}).status_code == 401
        assert c.post("/api/v1/charging/sessions",
                      json={"station_id": "pln_spklu-1", "energy_kwh": 20}).status_code == 401
        assert c.get("/api/v1/charging/sessions").status_code == 401


@requires_db
def test_start_debits_deposit_then_settle_refunds(monkeypatch):
    _setup_env(monkeypatch)
    _mock_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth = _register(c)
        _credit_wallet(c, auth, 100000)
        before = c.get("/api/v1/wallet", headers=auth).json()["balance_idr"]

        started = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20,
                               "station_name": "SPKLU Test", "connector_type": "CCS2", "power_kw": 150},
                         headers=auth)
        assert started.status_code == 201
        session = started.json()
        assert session["status"] == "active"
        assert session["deposit_idr"] == 51820
        # deposit really left the wallet
        assert session["wallet_balance_idr"] == before - 51820
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == before - 51820

        settled = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                         json={"delivered_kwh": 16.5}, headers=auth)
        assert settled.status_code == 200
        s = settled.json()
        assert s["status"] == "completed"
        assert s["actual_cost_idr"] == round(16.5 * 2466) + 2500     # 43189
        assert s["refund_idr"] == 51820 - s["actual_cost_idr"]       # 8631
        # refund credited back: net spend == actual cost
        assert s["wallet_balance_idr"] == before - s["actual_cost_idr"]
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == before - s["actual_cost_idr"]


@requires_db
def test_settle_is_idempotent(monkeypatch):
    _setup_env(monkeypatch)
    _mock_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth = _register(c)
        _credit_wallet(c, auth, 100000)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20}, headers=auth).json()
        first = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                       json={"delivered_kwh": 16.5}, headers=auth).json()
        after_first = c.get("/api/v1/wallet", headers=auth).json()["balance_idr"]
        # second settle must NOT credit again
        second = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                        json={"delivered_kwh": 16.5}, headers=auth).json()
        assert second["refund_idr"] == first["refund_idr"]
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == after_first


@requires_db
def test_insufficient_balance_is_402_and_no_session(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth = _register(c)  # fresh user: wallet starts at 0
        resp = c.post("/api/v1/charging/sessions",
                      json={"station_id": "pln_spklu-1", "energy_kwh": 20}, headers=auth)
        assert resp.status_code == 402
        assert c.get("/api/v1/charging/sessions", headers=auth).json() == []  # nothing created


@requires_db
def test_settle_unknown_session_is_404(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth = _register(c)
        resp = c.post("/api/v1/charging/sessions/00000000-0000-0000-0000-000000000000/settle",
                      json={"delivered_kwh": 5}, headers=auth)
        assert resp.status_code == 404


@requires_db
def test_settling_another_users_session_is_404(monkeypatch):
    """User B must not be able to settle (or even see) user A's session."""
    _setup_env(monkeypatch)
    _mock_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth_a = _register(c)
        auth_b = _register(c)
        _credit_wallet(c, auth_a, 100000)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20}, headers=auth_a).json()

        # B settling A's session: 404, indistinguishable from a nonexistent id
        stolen = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                        json={"delivered_kwh": 1}, headers=auth_b)
        assert stolen.status_code == 404
        assert c.get(f"/api/v1/charging/sessions/{session['id']}", headers=auth_b).status_code == 404

        # A's session is untouched and A can still settle it
        assert c.get(f"/api/v1/charging/sessions/{session['id']}",
                     headers=auth_a).json()["status"] == "active"
        assert c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                      json={"delivered_kwh": 16.5}, headers=auth_a).status_code == 200

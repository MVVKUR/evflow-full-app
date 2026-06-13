"""DB-backed tests for the charging-session flow against the real wallet."""
import pytest

from tests.conftest import requires_db

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402


def _credit_wallet(client, amount):
    """Top up the shared wallet via the Xendit webhook path so tests have funds."""
    created = client.post("/api/v1/wallet/topup", json={"amount_idr": amount}).json()
    # invoice id derives from external_id in the mocked create_invoice
    inv_id = client.get("/api/v1/wallet/topups").json()[0]["xendit_invoice_id"]
    client.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                headers={"x-callback-token": "tok123"})


@requires_db
def test_quote_matches_pricing(monkeypatch):
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    from api import main
    with TestClient(main.app) as c:
        q = c.post("/api/v1/charging/quote", json={"energy_kwh": 20}).json()
        assert q["total_due_idr"] == 51820


@requires_db
def test_start_debits_deposit_then_settle_refunds(monkeypatch):
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", "tok123")
    from api import main, xendit
    monkeypatch.setattr(xendit, "create_invoice",
                        lambda ext, amt, desc: {"id": f"inv-{ext}", "invoice_url": f"https://c/{ext}",
                                                "status": "PENDING"})
    with TestClient(main.app) as c:
        _credit_wallet(c, 100000)
        before = c.get("/api/v1/wallet").json()["balance_idr"]

        started = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20,
                               "station_name": "SPKLU Test", "connector_type": "CCS2", "power_kw": 150})
        assert started.status_code == 201
        session = started.json()
        assert session["status"] == "active"
        assert session["deposit_idr"] == 51820
        # deposit really left the wallet
        assert session["wallet_balance_idr"] == before - 51820
        assert c.get("/api/v1/wallet").json()["balance_idr"] == before - 51820

        settled = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                         json={"delivered_kwh": 16.5})
        assert settled.status_code == 200
        s = settled.json()
        assert s["status"] == "completed"
        assert s["actual_cost_idr"] == round(16.5 * 2466) + 2500     # 43189
        assert s["refund_idr"] == 51820 - s["actual_cost_idr"]       # 8631
        # refund credited back: net spend == actual cost
        assert s["wallet_balance_idr"] == before - s["actual_cost_idr"]
        assert c.get("/api/v1/wallet").json()["balance_idr"] == before - s["actual_cost_idr"]


@requires_db
def test_settle_is_idempotent(monkeypatch):
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", "tok123")
    from api import main, xendit
    monkeypatch.setattr(xendit, "create_invoice",
                        lambda ext, amt, desc: {"id": f"inv-{ext}", "invoice_url": f"https://c/{ext}",
                                                "status": "PENDING"})
    with TestClient(main.app) as c:
        _credit_wallet(c, 100000)
        session = c.post("/api/v1/charging/sessions",
                         json={"station_id": "pln_spklu-1", "energy_kwh": 20}).json()
        first = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                       json={"delivered_kwh": 16.5}).json()
        after_first = c.get("/api/v1/wallet").json()["balance_idr"]
        # second settle must NOT credit again
        second = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                        json={"delivered_kwh": 16.5}).json()
        assert second["refund_idr"] == first["refund_idr"]
        assert c.get("/api/v1/wallet").json()["balance_idr"] == after_first


@requires_db
def test_insufficient_balance_is_402_and_no_session(monkeypatch):
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    from api import main, charging_repo
    from api.db import engine
    from sqlalchemy import text
    with TestClient(main.app) as c:
        # drain the wallet to 0
        with engine.begin() as conn:
            conn.execute(text("UPDATE wallet SET balance_idr = 0 WHERE id = 1"))
        sessions_before = len(charging_repo.list_sessions(1000))
        resp = c.post("/api/v1/charging/sessions",
                      json={"station_id": "pln_spklu-1", "energy_kwh": 20})
        assert resp.status_code == 402
        assert len(charging_repo.list_sessions(1000)) == sessions_before  # nothing created


@requires_db
def test_settle_unknown_session_is_404(monkeypatch):
    from api import main
    with TestClient(main.app) as c:
        resp = c.post("/api/v1/charging/sessions/00000000-0000-0000-0000-000000000000/settle",
                      json={"delivered_kwh": 5})
        assert resp.status_code == 404

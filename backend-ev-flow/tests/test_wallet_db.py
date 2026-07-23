"""DB-backed tests for the wallet top-up flow (Xendit mocked, no network).

Wallet endpoints are user-scoped: each test registers a fresh user and sends
its Bearer token, so tests never share wallet state. Webhook calls stay
unauthenticated on purpose — they carry only the x-callback-token header.
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
    monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", CALLBACK_TOKEN)


def _register(client) -> dict:
    """Create a fresh user and return its Authorization header."""
    uname = "wallet-" + uuid.uuid4().hex[:8]
    reg = client.post("/api/v1/auth/register",
                      json={"username": uname, "password": "s3cret123"})
    assert reg.status_code == 201
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@requires_db
def test_topup_creates_pending_and_webhook_credits(monkeypatch):
    _setup_env(monkeypatch)
    from api import main, xendit
    # mock Xendit so no network; invoice id derives from external_id so it is retrievable
    monkeypatch.setattr(xendit, "create_invoice",
                        lambda ext, amt, desc, **kw: {"id": f"inv-{ext}",
                                                      "invoice_url": f"https://checkout/{ext}",
                                                      "status": "PENDING"})
    with TestClient(main.app) as c:
        auth = _register(c)
        before = c.get("/api/v1/wallet", headers=auth).json()["balance_idr"]

        created = c.post("/api/v1/wallet/topup", json={"amount_idr": 50000}, headers=auth).json()
        assert created["status"] == "pending"
        assert created["invoice_url"].startswith("https://checkout/")

        inv_id = c.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]
        ok = c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                    headers={"x-callback-token": CALLBACK_TOKEN})
        assert ok.status_code == 200
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == before + 50000

        # idempotent: duplicate delivery does not double-credit
        c.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
               headers={"x-callback-token": CALLBACK_TOKEN})
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == before + 50000


@requires_db
def test_webhook_rejects_bad_token_and_ignores_unknown(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        bad = c.post("/api/v1/webhooks/xendit", json={"id": "x", "status": "PAID"},
                     headers={"x-callback-token": "wrong"})
        assert bad.status_code == 401
        unknown = c.post("/api/v1/webhooks/xendit", json={"id": "inv-unknown", "status": "PAID"},
                         headers={"x-callback-token": CALLBACK_TOKEN})
        assert unknown.status_code == 200


@requires_db
def test_topup_amount_below_min_is_422(monkeypatch):
    _setup_env(monkeypatch)
    from api import main, xendit
    monkeypatch.setattr(xendit, "create_invoice", lambda *a, **k: {"id": "x", "invoice_url": "u", "status": "PENDING"})
    with TestClient(main.app) as c:
        auth = _register(c)
        assert c.post("/api/v1/wallet/topup", json={"amount_idr": 5000}, headers=auth).status_code == 422


@requires_db
def test_topup_status_poll_credits_when_xendit_reports_paid(monkeypatch):
    _setup_env(monkeypatch)
    from api import main, xendit
    monkeypatch.setattr(xendit, "create_invoice",
                        lambda ext, amt, desc, **kw: {"id": f"inv-{ext}",
                                                      "invoice_url": f"https://checkout/{ext}",
                                                      "status": "PENDING"})
    invoice_status = {"status": "PENDING"}
    monkeypatch.setattr(xendit, "get_invoice",
                        lambda inv_id: {"id": inv_id, "status": invoice_status["status"]})
    with TestClient(main.app) as c:
        auth = _register(c)
        before = c.get("/api/v1/wallet", headers=auth).json()["balance_idr"]
        created = c.post("/api/v1/wallet/topup", json={"amount_idr": 25000}, headers=auth).json()
        topup_id = created["topup_id"]

        # still pending at Xendit: poll reports pending, no credit
        polled = c.get(f"/api/v1/wallet/topups/{topup_id}", headers=auth).json()
        assert polled["status"] == "pending"
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == before

        # Xendit flips to PAID: poll self-heals (credits without a webhook)
        invoice_status["status"] = "PAID"
        polled = c.get(f"/api/v1/wallet/topups/{topup_id}", headers=auth).json()
        assert polled["status"] == "paid"
        assert polled["paid_at"] is not None
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == before + 25000

        # subsequent polls stay paid and do not double-credit
        polled = c.get(f"/api/v1/wallet/topups/{topup_id}", headers=auth).json()
        assert polled["status"] == "paid"
        assert c.get("/api/v1/wallet", headers=auth).json()["balance_idr"] == before + 25000

        assert c.get("/api/v1/wallet/topups/00000000-0000-0000-0000-000000000000",
                     headers=auth).status_code == 404

"""DB-backed tests for the connectors table + availability tracking.

Each test seeds its own station (unique id) with two connector rows, so tests
are self-contained and never depend on the dataset seed. Charging tests follow
the test_charging_db.py pattern: fresh user, Bearer token, wallet credited via
the mocked Xendit webhook path.
"""
import uuid

import pytest

from tests.conftest import requires_db

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402
from sqlalchemy import text                 # noqa: E402

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
    uname = "conn-" + uuid.uuid4().hex[:8]
    reg = client.post("/api/v1/auth/register",
                      json={"username": uname, "password": "s3cret123"})
    assert reg.status_code == 201
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _credit_wallet(client, auth, amount):
    client.post("/api/v1/wallet/topup", json={"amount_idr": amount}, headers=auth)
    inv_id = client.get("/api/v1/wallet/topups", headers=auth).json()[0]["xendit_invoice_id"]
    client.post("/api/v1/webhooks/xendit", json={"id": inv_id, "status": "PAID"},
                headers={"x-callback-token": CALLBACK_TOKEN})


def _seed_station_with_connectors() -> str:
    """Insert a throwaway station + 2 connector rows (CCS2 + AC Type 2); return its id."""
    from api.db import engine
    sid = "test-conn-" + uuid.uuid4().hex[:10]
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO stations (id, geom, name, connector_types, connector_inferred, connectors, sources)
            VALUES (:id, ST_SetSRID(ST_MakePoint(106.8, -6.2), 4326), :name,
                    ARRAY['CCS2','AC Type 2'], false, CAST(:connectors AS jsonb), ARRAY['osm'])
        """), {"id": sid, "name": f"Test Station {sid}",
               "connectors": '[{"type": "CCS2", "count": 1, "power_kw": 150.0,'
                             ' "speed_tier": "fast", "type_inferred": false},'
                             '{"type": "AC Type 2", "count": 1, "power_kw": 22.0,'
                             ' "speed_tier": "medium", "type_inferred": false}]'})
        c.execute(text("""
            INSERT INTO connectors (id, station_id, type, power_kw, speed_tier, type_inferred)
            VALUES (gen_random_uuid(), :sid, 'CCS2', 150, 'fast', false),
                   (gen_random_uuid(), :sid, 'AC Type 2', 22, 'medium', false)
        """), {"sid": sid})
    return sid


@requires_db
def test_station_connectors_and_availability(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    sid = _seed_station_with_connectors()
    with TestClient(main.app) as c:
        rows = c.get(f"/api/v1/stations/{sid}/connectors")
        assert rows.status_code == 200
        connectors = rows.json()
        assert len(connectors) == 2
        assert {r["type"] for r in connectors} == {"CCS2", "AC Type 2"}
        assert all(r["status"] == "available" for r in connectors)
        assert all(r["station_id"] == sid for r in connectors)

        avail = c.get(f"/api/v1/stations/{sid}/availability")
        assert avail.status_code == 200
        assert avail.json() == {"station_id": sid, "total": 2, "available": 2,
                                "in_use": 0, "out_of_service": 0}

        # unknown station -> 404 (both endpoints)
        assert c.get("/api/v1/stations/no-such-station/connectors").status_code == 404
        assert c.get("/api/v1/stations/no-such-station/availability").status_code == 404


@requires_db
def test_start_session_occupies_connector_and_settle_releases(monkeypatch):
    _setup_env(monkeypatch)
    _mock_xendit(monkeypatch)
    from api import main
    sid = _seed_station_with_connectors()
    with TestClient(main.app) as c:
        auth = _register(c)
        _credit_wallet(c, auth, 100000)

        started = c.post("/api/v1/charging/sessions",
                         json={"station_id": sid, "energy_kwh": 20, "connector_type": "CCS2"},
                         headers=auth)
        assert started.status_code == 201
        session = started.json()
        assert session["connector_id"] is not None

        # the claimed connector is the matching CCS2 one, now in_use
        occupied = [r for r in c.get(f"/api/v1/stations/{sid}/connectors").json()
                    if r["id"] == session["connector_id"]]
        assert occupied and occupied[0]["type"] == "CCS2" and occupied[0]["status"] == "in_use"
        assert c.get(f"/api/v1/stations/{sid}/availability").json() == {
            "station_id": sid, "total": 2, "available": 1, "in_use": 1, "out_of_service": 0}

        # settle -> connector released
        settled = c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                         json={"delivered_kwh": 16.5}, headers=auth)
        assert settled.status_code == 200
        assert settled.json()["status"] == "completed"
        assert c.get(f"/api/v1/stations/{sid}/availability").json()["available"] == 2


@requires_db
def test_start_with_all_connectors_busy_still_succeeds(monkeypatch):
    """The money path must never be blocked by connector inventory."""
    _setup_env(monkeypatch)
    _mock_xendit(monkeypatch)
    from api import main
    from api.db import engine
    sid = _seed_station_with_connectors()
    with engine.begin() as db:
        db.execute(text("UPDATE connectors SET status = 'in_use' WHERE station_id = :sid"), {"sid": sid})
    with TestClient(main.app) as c:
        auth = _register(c)
        _credit_wallet(c, auth, 100000)
        started = c.post("/api/v1/charging/sessions",
                         json={"station_id": sid, "energy_kwh": 20}, headers=auth)
        assert started.status_code == 201
        session = started.json()
        assert session["status"] == "active"
        assert session["connector_id"] is None
        # deposit was still debited normally
        assert session["deposit_idr"] == 51820
        # settle still works with no connector attached
        assert c.post(f"/api/v1/charging/sessions/{session['id']}/settle",
                      json={"delivered_kwh": 10}, headers=auth).status_code == 200


@requires_db
def test_start_on_station_without_connector_rows_succeeds(monkeypatch):
    """Stations that predate the connectors table (or unknown ids) charge fine."""
    _setup_env(monkeypatch)
    _mock_xendit(monkeypatch)
    from api import main
    with TestClient(main.app) as c:
        auth = _register(c)
        _credit_wallet(c, auth, 100000)
        started = c.post("/api/v1/charging/sessions",
                         json={"station_id": "no-connector-rows-station", "energy_kwh": 20},
                         headers=auth)
        assert started.status_code == 201
        assert started.json()["connector_id"] is None


@requires_db
def test_patch_connector_status(monkeypatch):
    _setup_env(monkeypatch)
    from api import main
    sid = _seed_station_with_connectors()
    with TestClient(main.app) as c:
        auth = _register(c)
        cid = c.get(f"/api/v1/stations/{sid}/connectors").json()[0]["id"]

        # requires auth
        assert c.patch(f"/api/v1/connectors/{cid}/status",
                       json={"status": "out_of_service"}).status_code == 401

        updated = c.patch(f"/api/v1/connectors/{cid}/status",
                          json={"status": "out_of_service"}, headers=auth)
        assert updated.status_code == 200
        assert updated.json()["status"] == "out_of_service"
        assert c.get(f"/api/v1/stations/{sid}/availability").json()["out_of_service"] == 1

        # invalid status -> 422
        assert c.patch(f"/api/v1/connectors/{cid}/status",
                       json={"status": "broken"}, headers=auth).status_code == 422
        # unknown uuid -> 404; non-uuid id -> 404 (not a 500)
        unknown = "00000000-0000-0000-0000-000000000000"
        assert c.patch(f"/api/v1/connectors/{unknown}/status",
                       json={"status": "available"}, headers=auth).status_code == 404
        assert c.patch("/api/v1/connectors/not-a-uuid/status",
                       json={"status": "available"}, headers=auth).status_code == 404

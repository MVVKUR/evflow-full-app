"""Tests for route plans endpoint (Epic 2.0)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from api import security, evmodels
from api.main import app

client = TestClient(app)


def test_route_plan_unauthenticated():
    res = client.post("/api/v1/route-plans", json={
        "origin": {"latitude": -6.2088, "longitude": 106.8456, "label": "Current Location"},
        "destination": {"latitude": -6.9175, "longitude": 107.6191, "label": "Bandung"},
        "current_soc_pct": 72,
    })
    assert res.status_code == 401


def test_route_plan_missing_ev_model(monkeypatch):
    # Mock current_user with no ev_model_id
    monkeypatch.setattr(security, "current_user", lambda: {
        "id": "user-123",
        "username": "testuser",
        "ev_model_id": None,
        "main_connector_type": None,
    })

    res = client.post("/api/v1/route-plans", json={
        "origin": {"latitude": -6.2088, "longitude": 106.8456, "label": "Current Location"},
        "destination": {"latitude": -6.9175, "longitude": 107.6191, "label": "Bandung"},
        "current_soc_pct": 72,
    })
    assert res.status_code == 409
    assert "select an EV model" in res.json()["detail"]


def test_route_plan_direct_comfortably(monkeypatch):
    # Mock current_user with a valid EV model
    monkeypatch.setattr(security, "current_user", lambda: {
        "id": "user-123",
        "username": "testuser",
        "ev_model_id": "hyundai-ioniq-5",
        "main_connector_type": "CCS2",
    })

    # Mock evmodels.get to return valid EV model
    monkeypatch.setattr(evmodels, "get", lambda mid: {
        "id": "hyundai-ioniq-5",
        "name": "Hyundai Ioniq 5 Standard Range",
        "battery_kwh": 58.0,
        "range_km": 384.0,
        "efficiency_wh_per_km": 160.0,
        "efficiency_source": "dataset",
        "max_dc_charge_kw": 185.0,
        "fast_charge_port": "CCS2",
    })

    # Direct short route (Jakarta to Bogor ~58km) starting at 80% battery => no stop needed
    res = client.post("/api/v1/route-plans", json={
        "origin": {"latitude": -6.2088, "longitude": 106.8456, "label": "Jakarta Pusat"},
        "destination": {"latitude": -6.5971, "longitude": 106.7996, "label": "Bogor"},
        "current_soc_pct": 80.0,
        "minimum_arrival_soc_pct": 15.0,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["directly_reachable"] is True
    assert data["recommended_stop"] is None
    assert data["vehicle"]["battery_kwh"] == 58.0
    assert data["summary"]["estimated_arrival_soc_pct"] >= 15.0
    assert "geometry" in data["route"]


def test_route_plan_client_battery_override_ignored(monkeypatch):
    monkeypatch.setattr(security, "current_user", lambda: {
        "id": "user-123",
        "username": "testuser",
        "ev_model_id": "wuling-air-ev",
        "main_connector_type": "Type 2",
    })

    monkeypatch.setattr(evmodels, "get", lambda mid: {
        "id": "wuling-air-ev",
        "name": "Wuling Air EV",
        "battery_kwh": 26.7,
        "range_km": 200.0,
        "efficiency_wh_per_km": 133.5,
        "efficiency_source": "derived_local_specs",
        "max_dc_charge_kw": 30.0,
        "fast_charge_port": "Type 2",
    })

    # Send client payload attempting to override battery_kwh to 100.0
    res = client.post("/api/v1/route-plans", json={
        "origin": {"latitude": -6.2088, "longitude": 106.8456, "label": "Jakarta Pusat"},
        "destination": {"latitude": -6.5971, "longitude": 106.7996, "label": "Bogor"},
        "current_soc_pct": 50.0,
        "battery_kwh": 100.0,  # Client override attempt
    })

    assert res.status_code == 200
    data = res.json()

    # Verify battery_kwh remains 26.7 from the user's profile EV model
    assert data["vehicle"]["battery_kwh"] == 26.7

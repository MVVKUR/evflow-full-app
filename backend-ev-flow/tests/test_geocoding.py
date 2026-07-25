"""Unit tests for geocoding destination search API endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_geocoding_search_endpoint():
    response = client.get("/api/v1/geocoding/search?q=Bandung&lat=-6.2088&lon=106.8456&limit=5")
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

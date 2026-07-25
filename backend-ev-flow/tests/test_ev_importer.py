"""Unit tests for EV importer data parsing and lineage."""
from __future__ import annotations

from scripts.import_ev_models import _parse_numbers, _parse_range_bounds, build_enriched_models


def test_parse_numbers_decimal_comma():
    assert _parse_numbers("26,7 kWh") == [26.7]
    assert _parse_numbers("200 - 300 km") == [200.0, 300.0]
    assert _parse_numbers(None) == []


def test_parse_range_bounds():
    val, min_v, max_v = _parse_range_bounds("200 - 300 km")
    assert val == 200.0
    assert min_v == 200.0
    assert max_v == 300.0


def test_derived_efficiency_calculation():
    r2026 = [{
        "Vehicle Name": "Test Local EV",
        "Vehicle Price Range": "Rp 300 Juta",
        "Battery Capacity": "50 kWh",
        "Range (Jarak Tempuh)": "250 km",
        "Charging time": "6 Jam",
        "Source URL": "https://example.com/ev",
        "Is EV": "TRUE",
    }]
    r2025 = []  # No direct match in 2025 specs

    enriched, stats = build_enriched_models(r2026, r2025)
    assert len(enriched) == 1
    rec = enriched[0]

    # 50 kWh * 1000 / 250 km = 200 Wh/km
    assert rec["battery_kwh"] == 50.0
    assert rec["range_km"] == 250.0
    assert rec["efficiency_wh_per_km"] == 200.0
    assert rec["efficiency_source"] == "derived_local_specs"
    assert stats["derived_local_specs"] == 1

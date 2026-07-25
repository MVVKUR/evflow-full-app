"""Unit tests for energy estimator calculations."""
from __future__ import annotations

import pytest
from api.services.energy_estimator import EnergyEstimator


def test_energy_estimator_direct_reachable():
    estimator = EnergyEstimator(route_adjustment_factor=1.0, auxiliary_energy_kwh=0.0)

    # 50 kWh battery, 150 Wh/km efficiency, 100 km trip => 15 kWh used.
    # Starting at 80% SoC (40 kWh) => 25 kWh remaining => 50% arrival SoC.
    res = estimator.estimate_trip_energy(
        battery_kwh=50.0,
        efficiency_wh_per_km=150.0,
        distance_km=100.0,
        current_soc_pct=80.0,
        minimum_arrival_soc_pct=15.0,
    )

    assert res.available_energy_kwh == 40.0
    assert res.base_trip_energy_kwh == 15.0
    assert res.estimated_trip_energy_kwh == 15.0
    assert res.estimated_arrival_soc_pct == 50.0
    assert res.directly_reachable is True


def test_energy_estimator_charging_required():
    estimator = EnergyEstimator(route_adjustment_factor=1.0, auxiliary_energy_kwh=0.0)

    # 50 kWh battery, 200 Wh/km efficiency, 200 km trip => 40 kWh used.
    # Starting at 50% SoC (25 kWh) => -15 kWh remaining => 0% clamped (raw -30%).
    res = estimator.estimate_trip_energy(
        battery_kwh=50.0,
        efficiency_wh_per_km=200.0,
        distance_km=200.0,
        current_soc_pct=50.0,
        minimum_arrival_soc_pct=15.0,
    )

    assert res.available_energy_kwh == 25.0
    assert res.estimated_trip_energy_kwh == 40.0
    assert res.raw_arrival_soc_pct == -30.0
    assert res.estimated_arrival_soc_pct == 0.0
    assert res.directly_reachable is False


def test_calculate_charging_minutes():
    estimator = EnergyEstimator(charging_adjustment_factor=1.0)

    # 60 kWh battery, charging from 10% to 80% (delta 70% => 42 kWh needed)
    # Effective power = min(100 kW vehicle, 50 kW station) = 50 kW
    # 42 kWh / 50 kW * 60 = 50.4 minutes
    info = estimator.calculate_charging_minutes(
        battery_kwh=60.0,
        arrival_soc_pct=10.0,
        target_soc_pct=80.0,
        vehicle_max_dc_charge_kw=100.0,
        station_power_kw=50.0,
    )

    assert info["energy_to_add_kwh"] == 42.0
    assert info["effective_charging_power_kw"] == 50.0
    assert info["estimated_charging_minutes"] == 50.4

"""Unit tests for energy estimator calculations."""
from __future__ import annotations

from decimal import Decimal

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


def test_default_minimum_arrival_soc_is_20_pct():
    """AC 2.1.3: the configured minimum arrival battery is 20%."""
    from api.services.energy_estimator import DEFAULT_MINIMUM_ARRIVAL_SOC_PCT

    assert DEFAULT_MINIMUM_ARRIVAL_SOC_PCT == 20.0

    estimator = EnergyEstimator(route_adjustment_factor=1.0, auxiliary_energy_kwh=0.0)
    # 50 kWh, 150 Wh/km, 200 km => 30 kWh used. From 65% (32.5 kWh) => 5% arrival.
    res = estimator.estimate_trip_energy(
        battery_kwh=50.0, efficiency_wh_per_km=150.0, distance_km=200.0, current_soc_pct=65.0)
    assert res.raw_arrival_soc_pct == 5.0
    assert res.directly_reachable is False

    # 18% arrival passes a 15% rule but must fail the 20% one.
    res = estimator.estimate_trip_energy(
        battery_kwh=50.0, efficiency_wh_per_km=150.0, distance_km=200.0, current_soc_pct=78.0)
    assert res.raw_arrival_soc_pct == 18.0
    assert res.directly_reachable is False


def test_effective_reserve_uses_percentage_when_it_beats_the_km_floor():
    from api.services.energy_estimator import effective_reserve_soc_pct

    # 20% of 58 kWh at 160 Wh/km is ~72 km, far above the 15 km floor.
    assert effective_reserve_soc_pct(58.0, 160.0) == 20.0
    assert effective_reserve_soc_pct(58.0, 160.0, minimum_arrival_soc_pct=25.0) == 25.0


def test_effective_reserve_is_raised_by_the_absolute_km_floor():
    from api.services.energy_estimator import effective_reserve_soc_pct, reserve_km_for_soc_pct

    # Tiny thirsty pack: 5% of 10 kWh at 200 Wh/km is only 2.5 km.
    raised = effective_reserve_soc_pct(10.0, 200.0, minimum_arrival_soc_pct=5.0)
    assert raised > 5.0
    # The raised reserve is worth exactly the 15 km floor.
    assert reserve_km_for_soc_pct(10.0, 200.0, raised) == pytest.approx(15.0, abs=0.1)


def test_effective_reserve_is_capped():
    from api.services.energy_estimator import MAX_RESERVE_SOC_PCT, effective_reserve_soc_pct

    # Absurdly small pack: the km floor must not demand the whole battery.
    assert effective_reserve_soc_pct(2.0, 300.0) == MAX_RESERVE_SOC_PCT


def test_calculate_charging_minutes_accepts_decimal_without_raising():
    """numeric(8,2) columns arrive as Decimal; min(Decimal, float) used to 500."""
    estimator = EnergyEstimator(charging_adjustment_factor=1.0)

    info = estimator.calculate_charging_minutes(
        battery_kwh=Decimal("60.00"),
        arrival_soc_pct=Decimal("10.0"),
        target_soc_pct=80.0,
        vehicle_max_dc_charge_kw=Decimal("100.00"),
        station_power_kw=Decimal("50.00"),
    )
    assert info["energy_to_add_kwh"] == 42.0
    assert info["effective_charging_power_kw"] == 50.0
    assert info["estimated_charging_minutes"] == 50.4


def test_default_charging_power_constant_replaces_the_bare_literal():
    from api.services.energy_estimator import DEFAULT_CHARGING_POWER_KW

    estimator = EnergyEstimator(charging_adjustment_factor=1.0)
    info = estimator.calculate_charging_minutes(
        battery_kwh=60.0, arrival_soc_pct=10.0, target_soc_pct=80.0,
        vehicle_max_dc_charge_kw=None, station_power_kw=None)
    assert info["effective_charging_power_kw"] == DEFAULT_CHARGING_POWER_KW


def test_current_soc_uses_only_cumulative_travelled_distance_and_never_increases():
    estimator = EnergyEstimator(route_adjustment_factor=1.0, auxiliary_energy_kwh=0.0)
    at_start = estimator.estimate_current_soc(60.0, 150.0, 80.0, 0.0)
    after_20_km = estimator.estimate_current_soc(60.0, 150.0, 80.0, 20.0)
    repeated = estimator.estimate_current_soc(60.0, 150.0, 80.0, 20.0)

    assert at_start.estimated_current_soc_pct == 80.0
    assert after_20_km.travelled_energy_kwh == 3.0
    assert after_20_km.remaining_energy_kwh == 45.0
    assert after_20_km.estimated_current_soc_pct == 75.0
    assert repeated == after_20_km
    assert after_20_km.estimated_current_soc_pct <= 80.0

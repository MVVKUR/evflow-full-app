"""Energy consumption estimator service for EV-FLOW (Epic 2.0).

Calculates EV trip energy usage and arrival State of Charge (SoC) based on:
- Usable battery capacity (kWh)
- Energy efficiency rating (Wh/km)
- Route adjustment factors (traffic, urban driving, road grade)
- Auxiliary electrical loads (HVAC, cabin electronics)

Formula Citation:
Ebrahimi et al. (2026), "Autonomous electric vehicle, EV charging and routing",
Journal of Energy & Transportation Systems / ScienceDirect (S254266052600123X).
"""
from __future__ import annotations

import os
from typing import Dict, NamedTuple, Optional

# Named, configurable environment variables and safety coefficients
DEFAULT_ROUTE_ADJUSTMENT_FACTOR = float(os.getenv("ENERGY_ROUTE_ADJUSTMENT_FACTOR", "1.15"))
DEFAULT_AUXILIARY_ENERGY_KWH = float(os.getenv("ENERGY_AUXILIARY_KWH", "0.0"))
DEFAULT_CHARGING_ADJUSTMENT_FACTOR = float(os.getenv("ENERGY_CHARGING_ADJUSTMENT_FACTOR", "1.10"))


class EnergyEstimateResult(NamedTuple):
    available_energy_kwh: float
    base_trip_energy_kwh: float
    estimated_trip_energy_kwh: float
    estimated_arrival_soc_pct: float
    raw_arrival_soc_pct: float
    directly_reachable: bool


class EnergyEstimator:
    """Pure, unit-testable energy calculation engine."""

    def __init__(
        self,
        route_adjustment_factor: float = DEFAULT_ROUTE_ADJUSTMENT_FACTOR,
        auxiliary_energy_kwh: float = DEFAULT_AUXILIARY_ENERGY_KWH,
        charging_adjustment_factor: float = DEFAULT_CHARGING_ADJUSTMENT_FACTOR,
    ):
        self.route_adjustment_factor = route_adjustment_factor
        self.auxiliary_energy_kwh = auxiliary_energy_kwh
        self.charging_adjustment_factor = charging_adjustment_factor

    def estimate_trip_energy(
        self,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        distance_km: float,
        current_soc_pct: float,
        minimum_arrival_soc_pct: float = 15.0,
    ) -> EnergyEstimateResult:
        """Estimate energy consumption and arrival SoC for a given trip distance."""
        available_energy_kwh = (battery_kwh * current_soc_pct) / 100.0
        base_trip_energy_kwh = (distance_km * efficiency_wh_per_km) / 1000.0
        estimated_trip_energy_kwh = (
            base_trip_energy_kwh * self.route_adjustment_factor
        ) + self.auxiliary_energy_kwh

        remaining_energy_kwh = available_energy_kwh - estimated_trip_energy_kwh
        raw_arrival_soc_pct = (remaining_energy_kwh / battery_kwh) * 100.0

        # Clamped SoC for UI presentation while retaining raw values
        clamped_arrival_soc_pct = max(0.0, min(100.0, raw_arrival_soc_pct))

        directly_reachable = raw_arrival_soc_pct >= minimum_arrival_soc_pct

        return EnergyEstimateResult(
            available_energy_kwh=round(available_energy_kwh, 2),
            base_trip_energy_kwh=round(base_trip_energy_kwh, 2),
            estimated_trip_energy_kwh=round(estimated_trip_energy_kwh, 2),
            estimated_arrival_soc_pct=round(clamped_arrival_soc_pct, 1),
            raw_arrival_soc_pct=round(raw_arrival_soc_pct, 2),
            directly_reachable=directly_reachable,
        )

    def calculate_charging_minutes(
        self,
        battery_kwh: float,
        arrival_soc_pct: float,
        target_soc_pct: float,
        vehicle_max_dc_charge_kw: Optional[float],
        station_power_kw: Optional[float],
    ) -> Dict[str, float]:
        """Calculate required charging energy and duration to reach target SoC."""
        if target_soc_pct <= arrival_soc_pct:
            return {
                "energy_to_add_kwh": 0.0,
                "estimated_charging_minutes": 0.0,
                "effective_charging_power_kw": 50.0,
            }

        delta_soc_pct = target_soc_pct - arrival_soc_pct
        energy_to_add_kwh = (battery_kwh * delta_soc_pct) / 100.0

        v_kw = vehicle_max_dc_charge_kw if (vehicle_max_dc_charge_kw and vehicle_max_dc_charge_kw > 0) else 50.0
        s_kw = station_power_kw if (station_power_kw and station_power_kw > 0) else 50.0

        effective_power_kw = min(v_kw, s_kw)

        charging_hours = (energy_to_add_kwh / effective_power_kw) * self.charging_adjustment_factor
        charging_minutes = charging_hours * 60.0

        return {
            "energy_to_add_kwh": round(energy_to_add_kwh, 2),
            "estimated_charging_minutes": round(charging_minutes, 1),
            "effective_charging_power_kw": round(effective_power_kw, 1),
        }

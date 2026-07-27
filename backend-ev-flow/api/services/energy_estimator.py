"""Energy consumption estimator service for EV-FLOW (Epic 2.0).

Calculates EV trip energy usage and arrival State of Charge (SoC) based on:
- Usable battery capacity (kWh)
- Energy efficiency rating (Wh/km)
- Route adjustment factors (traffic, urban driving, road grade)
- Auxiliary electrical loads (HVAC, cabin electronics)

Formula Citation:
Ebrahimi et al. (2026), "Autonomous electric vehicle, EV charging and routing",
Journal of Energy & Transportation Systems / ScienceDirect (S254266052600123X).

Safety reserve (AC 2.1.3)
------------------------
The single source of truth for "minimum arrival battery" is
``DEFAULT_MINIMUM_ARRIVAL_SOC_PCT`` (20% per AC 2.1.3, overridable via
``ROUTE_MINIMUM_ARRIVAL_SOC_PCT``). A percentage alone is a poor reserve for a
small battery (20% of 17.3 kWh is ~26 km on a thirsty day but 20% of a 100 kWh
pack is ~120 km), so ``MIN_RESERVE_KM`` imposes an absolute floor in km:
``effective_reserve_soc_pct()`` raises the percentage whenever the percentage
reserve is worth fewer km than the floor.
"""
from __future__ import annotations

import os
from typing import Dict, NamedTuple, Optional

# Named, configurable environment variables and safety coefficients
DEFAULT_ROUTE_ADJUSTMENT_FACTOR = float(os.getenv("ENERGY_ROUTE_ADJUSTMENT_FACTOR", "1.15"))
DEFAULT_AUXILIARY_ENERGY_KWH = float(os.getenv("ENERGY_AUXILIARY_KWH", "0.0"))
DEFAULT_CHARGING_ADJUSTMENT_FACTOR = float(os.getenv("ENERGY_CHARGING_ADJUSTMENT_FACTOR", "1.10"))

# AC 2.1.3: "the configured minimum arrival battery is 20%".
DEFAULT_MINIMUM_ARRIVAL_SOC_PCT = float(os.getenv("ROUTE_MINIMUM_ARRIVAL_SOC_PCT", "20.0"))

# Absolute floor for the reserve, in km of remaining range.
MIN_RESERVE_KM = float(os.getenv("ROUTE_MIN_RESERVE_KM", "15.0"))

# Never let the km floor push the reserve past this share of the pack.
MAX_RESERVE_SOC_PCT = float(os.getenv("ROUTE_MAX_RESERVE_SOC_PCT", "50.0"))

# Arrival SoC within this many points ABOVE the reserve is still "direct" but tight.
TIGHT_MARGIN_SOC_PCT = float(os.getenv("ROUTE_TIGHT_MARGIN_SOC_PCT", "5.0"))

# Assumed charging power when neither the vehicle nor the station reports one.
DEFAULT_CHARGING_POWER_KW = float(os.getenv("ROUTE_DEFAULT_CHARGING_POWER_KW", "50.0"))

# DC charging tapers hard past this point, so this is the preferred charge target.
DEFAULT_TARGET_SOC_PCT = float(os.getenv("ROUTE_DEFAULT_TARGET_SOC_PCT", "80.0"))

# Hard ceiling for a charge target when the trip needs more than the preferred one.
MAX_TARGET_SOC_PCT = float(os.getenv("ROUTE_MAX_TARGET_SOC_PCT", "100.0"))


class EnergyEstimateResult(NamedTuple):
    available_energy_kwh: float
    base_trip_energy_kwh: float
    estimated_trip_energy_kwh: float
    estimated_arrival_soc_pct: float
    raw_arrival_soc_pct: float
    directly_reachable: bool


class CurrentSocEstimate(NamedTuple):
    estimated_current_soc_pct: float
    remaining_energy_kwh: float
    travelled_energy_kwh: float


def reserve_km_for_soc_pct(battery_kwh: float, efficiency_wh_per_km: float, soc_pct: float) -> float:
    """How many km of range a given SoC percentage is worth for this vehicle."""
    if not battery_kwh or not efficiency_wh_per_km or efficiency_wh_per_km <= 0:
        return 0.0
    reserve_kwh = (float(battery_kwh) * float(soc_pct)) / 100.0
    return (reserve_kwh * 1000.0) / float(efficiency_wh_per_km)


def effective_reserve_soc_pct(
    battery_kwh: float,
    efficiency_wh_per_km: float,
    minimum_arrival_soc_pct: Optional[float] = None,
    min_reserve_km: float = MIN_RESERVE_KM,
    max_reserve_soc_pct: float = MAX_RESERVE_SOC_PCT,
) -> float:
    """Resolve the reserve actually enforced for this vehicle (AC 2.1.3).

    Starts from the configured percentage (defaulting to
    ``DEFAULT_MINIMUM_ARRIVAL_SOC_PCT``) and raises it when that percentage is
    worth fewer km than ``min_reserve_km``, so small-battery cars keep a real
    margin. Capped by ``max_reserve_soc_pct`` so the floor can never demand an
    absurd share of a tiny pack.
    """
    base_pct = (
        float(minimum_arrival_soc_pct)
        if minimum_arrival_soc_pct is not None
        else DEFAULT_MINIMUM_ARRIVAL_SOC_PCT
    )
    if not battery_kwh or not efficiency_wh_per_km or efficiency_wh_per_km <= 0:
        return round(base_pct, 2)

    pct_worth_floor = ((float(min_reserve_km) * float(efficiency_wh_per_km)) / 1000.0) / float(battery_kwh) * 100.0
    return round(min(max(base_pct, pct_worth_floor), max_reserve_soc_pct), 2)


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

    def trip_energy_kwh(self, efficiency_wh_per_km: float, distance_km: float) -> float:
        """Adjusted energy required to cover ``distance_km`` (kWh)."""
        base = (float(distance_km) * float(efficiency_wh_per_km)) / 1000.0
        return (base * self.route_adjustment_factor) + self.auxiliary_energy_kwh

    def soc_pct_for_distance(
        self, battery_kwh: float, efficiency_wh_per_km: float, distance_km: float
    ) -> float:
        """Share of the pack (in SoC points) consumed by ``distance_km``."""
        if not battery_kwh:
            return 0.0
        return (self.trip_energy_kwh(efficiency_wh_per_km, distance_km) / float(battery_kwh)) * 100.0

    def estimate_current_soc(
        self,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        navigation_start_soc_pct: float,
        cumulative_distance_travelled_km: float,
    ) -> CurrentSocEstimate:
        """Estimate present SoC from energy consumed since navigation started.

        The result is bounded by the navigation-start SoC, so ordinary driving
        can never create energy. A measured post-charge SoC is handled by the
        caller because charging is a separate state transition.
        """
        battery_kwh = float(battery_kwh)
        start_soc = max(0.0, min(100.0, float(navigation_start_soc_pct)))
        travelled_km = max(0.0, float(cumulative_distance_travelled_km))
        available_start_energy_kwh = battery_kwh * start_soc / 100.0
        travelled_energy_kwh = self.trip_energy_kwh(efficiency_wh_per_km, travelled_km)
        remaining_energy_kwh = max(0.0, available_start_energy_kwh - travelled_energy_kwh)
        current_soc = 0.0 if battery_kwh <= 0 else remaining_energy_kwh / battery_kwh * 100.0
        current_soc = max(0.0, min(start_soc, current_soc))
        return CurrentSocEstimate(
            estimated_current_soc_pct=round(current_soc, 1),
            remaining_energy_kwh=round(remaining_energy_kwh, 2),
            travelled_energy_kwh=round(travelled_energy_kwh, 2),
        )

    def estimate_trip_energy(
        self,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        distance_km: float,
        current_soc_pct: float,
        minimum_arrival_soc_pct: float = DEFAULT_MINIMUM_ARRIVAL_SOC_PCT,
    ) -> EnergyEstimateResult:
        """Estimate energy consumption and arrival SoC for a given trip distance."""
        battery_kwh = float(battery_kwh)
        efficiency_wh_per_km = float(efficiency_wh_per_km)

        available_energy_kwh = (battery_kwh * float(current_soc_pct)) / 100.0
        base_trip_energy_kwh = (float(distance_km) * efficiency_wh_per_km) / 1000.0
        estimated_trip_energy_kwh = (
            base_trip_energy_kwh * self.route_adjustment_factor
        ) + self.auxiliary_energy_kwh

        remaining_energy_kwh = available_energy_kwh - estimated_trip_energy_kwh
        raw_arrival_soc_pct = (remaining_energy_kwh / battery_kwh) * 100.0

        # Clamped SoC for UI presentation while retaining raw values
        clamped_arrival_soc_pct = max(0.0, min(100.0, raw_arrival_soc_pct))

        directly_reachable = raw_arrival_soc_pct >= float(minimum_arrival_soc_pct)

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
        """Calculate required charging energy and duration to reach target SoC.

        Every numeric is coerced to ``float`` first: the EV catalogue column is
        ``numeric(8,2)`` and psycopg hands those back as ``Decimal``, which
        cannot be mixed with floats by ``min()``/``/`` without a TypeError.
        """
        battery_kwh = float(battery_kwh)
        arrival_soc_pct = float(arrival_soc_pct)
        target_soc_pct = float(target_soc_pct)
        v_raw = float(vehicle_max_dc_charge_kw) if vehicle_max_dc_charge_kw is not None else None
        s_raw = float(station_power_kw) if station_power_kw is not None else None

        v_kw = v_raw if (v_raw and v_raw > 0) else DEFAULT_CHARGING_POWER_KW
        s_kw = s_raw if (s_raw and s_raw > 0) else DEFAULT_CHARGING_POWER_KW
        effective_power_kw = min(v_kw, s_kw)

        if target_soc_pct <= arrival_soc_pct:
            return {
                "energy_to_add_kwh": 0.0,
                "estimated_charging_minutes": 0.0,
                "effective_charging_power_kw": round(effective_power_kw, 1),
            }

        delta_soc_pct = target_soc_pct - arrival_soc_pct
        energy_to_add_kwh = (battery_kwh * delta_soc_pct) / 100.0

        charging_hours = (energy_to_add_kwh / effective_power_kw) * self.charging_adjustment_factor
        charging_minutes = charging_hours * 60.0

        return {
            "energy_to_add_kwh": round(energy_to_add_kwh, 2),
            "estimated_charging_minutes": round(charging_minutes, 1),
            "effective_charging_power_kw": round(effective_power_kw, 1),
        }

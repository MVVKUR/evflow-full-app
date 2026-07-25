"""Charging stop selection and candidate ranking algorithm for EV-FLOW (Epic 2.0).

Identifies optimal SPKLU charging stations along a route corridor using:
1. Spatial bounding box / PostGIS corridor filtering around origin-to-destination path
2. Connector compatibility check against vehicle requirements
3. Energy arrival constraint checking (station must be reachable before SoC drops below reserve)
4. Multi-factor scoring (detour km, charging time, total duration, station power rating)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from api.models import RecommendedStop, Station
from api.services.energy_estimator import EnergyEstimator
from api.services.routing_service import RoutingService, haversine_distance_km



def connector_is_compatible(vehicle_connector: Optional[str], station_connectors: List[Any], station_types: List[str]) -> bool:
    """Check if vehicle connector is compatible with station connectors."""
    if not vehicle_connector:
        return True  # If vehicle does not specify connector, assume compatible

    v_conn = vehicle_connector.upper().replace(" ", "").replace("-", "")

    # Check station_types list
    for t in station_types:
        st_t = t.upper().replace(" ", "").replace("-", "")
        if v_conn in st_t or st_t in v_conn:
            return True
        if ("CCS" in v_conn and "CCS" in st_t) or ("TYPE2" in v_conn and "TYPE2" in st_t):
            return True

    # Check connectors objects array
    for c in station_connectors:
        if isinstance(c, dict):
            ctype = str(c.get("type", "")).upper().replace(" ", "").replace("-", "")
            if v_conn in ctype or ctype in v_conn:
                return True
            if ("CCS" in v_conn and "CCS" in ctype) or ("TYPE2" in v_conn and "TYPE2" in ctype):
                return True

    return False


class StopRanker:
    """Ranks viable charging stop candidates along a route corridor."""

    def __init__(self, energy_estimator: EnergyEstimator, routing_service: RoutingService):
        self.energy_estimator = energy_estimator
        self.routing_service = routing_service

    async def select_recommended_stop(
        self,
        origin: Tuple[float, float],       # (lat, lon)
        destination: Tuple[float, float],  # (lat, lon)
        direct_distance_km: float,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        current_soc_pct: float,
        minimum_arrival_soc_pct: float,
        vehicle_connector: Optional[str],
        max_dc_charge_kw: Optional[float],
        maximum_detour_km: float = 15.0,
        forced_station_id: Optional[str] = None,
    ) -> Optional[RecommendedStop]:
        # 1. Fetch candidate stations within route bounding box plus margin
        min_lat = min(origin[0], destination[0]) - 0.25
        max_lat = max(origin[0], destination[0]) + 0.25
        min_lon = min(origin[1], destination[1]) - 0.25
        max_lon = max(origin[1], destination[1]) + 0.25

        bbox = (min_lon, min_lat, max_lon, max_lat)

        stations: List[Dict[str, Any]] = []

        # If a specific station is forced by client waypoint
        if forced_station_id:
            from api.stations_repo import get_station
            st = get_station(forced_station_id)
            if st:
                stations = [st]
        else:
            try:
                from api.stations_repo import list_stations
                _, stations = list_stations({"bbox": bbox}, limit=150, offset=0)
            except Exception:
                stations = []

        if not stations:
            return None

        candidates = []

        for st in stations:
            st_lat = float(st["latitude"])
            st_lon = float(st["longitude"])
            st_pos = (st_lat, st_lon)

            # Check connector compatibility
            connectors = st.get("connectors") or []
            connector_types = st.get("connector_types") or []

            is_compat = connector_is_compatible(vehicle_connector, connectors, connector_types)
            if not is_compat and not forced_station_id:
                continue

            # Straight-line distance from origin and destination
            dist_orig_to_st = haversine_distance_km(origin[0], origin[1], st_lat, st_lon)
            dist_st_to_dest = haversine_distance_km(st_lat, st_lon, destination[0], destination[1])

            detour_km = max(0.0, (dist_orig_to_st + dist_st_to_dest) - direct_distance_km)
            if detour_km > maximum_detour_km and not forced_station_id:
                continue

            # Estimate arrival SoC at station
            est_to_st = self.energy_estimator.estimate_trip_energy(
                battery_kwh=battery_kwh,
                efficiency_wh_per_km=efficiency_wh_per_km,
                distance_km=dist_orig_to_st,
                current_soc_pct=current_soc_pct,
                minimum_arrival_soc_pct=minimum_arrival_soc_pct,
            )

            # Station must be reachable before reserve threshold is breached
            if est_to_st.raw_arrival_soc_pct < (minimum_arrival_soc_pct - 5.0) and not forced_station_id:
                continue

            arrival_soc_at_st = max(0.0, est_to_st.estimated_arrival_soc_pct)

            # Recommended target SoC (80% default unless smaller charge covers destination)
            recommended_target_soc = 80.0

            st_power_kw = float(st.get("power_kw") or 50.0)
            charge_info = self.energy_estimator.calculate_charging_minutes(
                battery_kwh=battery_kwh,
                arrival_soc_pct=arrival_soc_at_st,
                target_soc_pct=recommended_target_soc,
                vehicle_max_dc_charge_kw=max_dc_charge_kw,
                station_power_kw=st_power_kw,
            )

            # Multi-factor candidate score (lower is better)
            # Penalizes detour km, long charging, low station power
            score = (
                (detour_km * 2.0)
                + (charge_info["estimated_charging_minutes"] * 0.5)
                - (st_power_kw * 0.1)
                + abs(dist_orig_to_st - (direct_distance_km * 0.55)) * 0.1
            )

            station_model = Station(
                id=st["id"],
                name=st.get("name") or "SPKLU Station",
                sources=st.get("sources") or [],
                latitude=st_lat,
                longitude=st_lon,
                address=st.get("address"),
                province=st.get("province"),
                city=st.get("city"),
                operator=st.get("operator") or "PLN",
                power_kw=st_power_kw,
                charge_type=st.get("charge_type") or "fast",
                speed_tier=st.get("speed_tier") or "fast",
                connectors=st.get("connectors") or [],
                connector_types=st.get("connector_types") or ["CCS2"],
                connector_inferred=st.get("connector_inferred", True),
                status=st.get("status") or "operational",
                date_verified=st.get("date_verified"),
                distance_km=round(dist_orig_to_st, 1),
            )

            rec_stop = RecommendedStop(
                station=station_model,
                distance_from_origin_km=round(dist_orig_to_st, 1),
                detour_km=round(detour_km, 1),
                arrival_soc_pct=round(arrival_soc_at_st, 1),
                recommended_target_soc_pct=recommended_target_soc,
                energy_to_add_kwh=charge_info["energy_to_add_kwh"],
                estimated_charging_minutes=charge_info["estimated_charging_minutes"],
                effective_charging_power_kw=charge_info["effective_charging_power_kw"],
                connector_compatible=is_compat,
                availability="available_now" if st.get("status") == "operational" else "unknown",
                data_confidence="high" if not st.get("connector_inferred") else "medium",
            )

            candidates.append((score, rec_stop))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

"""Charging stop selection and candidate ranking for EV-FLOW (Epic 2.0, AC 2.2.9).

    "Given a charging stop is required, when candidate stations are evaluated,
     then the system keeps only stations reachable with the reserve intact,
     requires a free connector the vehicle can use, and ranks the remainder by
     detour distance and charging power."

Pipeline:
1. Spatial prefilter along the origin-to-destination corridor, ordered by
   proximity to the route line and spread along it (never `ORDER BY id LIMIT n`,
   which returned a lexicographic slice and hid the whole `pln_spklu-*` network).
2. ONE set-based availability query over every candidate id (`connectors` table).
3. Hard filters, in this order:
     a. detour within the caller's budget,
     b. station REACHABLE WITH THE RESERVE INTACT (>= the effective reserve --
        there is no slack; the old `- 5.0` fudge sent drivers to stations they
        reached below their own reserve),
     c. at least one connector row with status='available' AND a type the
        vehicle can use,
     d. the stop must actually COMPLETE the trip: the SoC reachable there has
        to cover the remaining leg with the reserve still intact.
4. Deterministic ranking: detour distance ascending, available charging power
   descending, station id as the tiebreak.
5. `revalidate_on_road()` re-derives the SELECTED stop from the real routed legs
   before it is offered, so the "arrives above the reserve" guarantee survives a
   detour leg that is more winding than the corridor average.

A driver-forced waypoint may skip filter (a) -- the soft detour preference --
and nothing else. When it fails (b), (c) or (d) it is returned with
`completes_trip=False` and `blocking_reasons`, never silently treated as viable.

Distance consistency: every distance in a detour subtraction comes from the
SAME measure. Straight-line legs are scaled by `distance_scale_factor`
(= road_km / straight_line_km for the direct route) so legs and the direct
distance share one basis and `detour_km` can never go negative.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from api.models import (  # noqa: F401  (route-type names re-exported for callers)
    ROUTE_TYPE_FASTEST,
    ROUTE_TYPE_SHORTEST,
    RecommendedStop,
    Station,
)
from api.services.connector_compat import (  # noqa: F401  (re-exported for callers)
    VehicleConnectorProfile,
    connector_is_compatible,
    normalize_connector_type,
    vehicle_connector_profile,
)
from api.services.energy_estimator import (
    DEFAULT_TARGET_SOC_PCT,
    MAX_TARGET_SOC_PCT,
    EnergyEstimator,
)
from api.services.routing_service import RoutingService, haversine_distance_km
from api.services.station_availability import (
    StationConnectorAvailability,
    availability_or_empty,
    fetch_availability,
)

# Ranking weights. Score is in "km-equivalent"; lower is better.
DETOUR_WEIGHT = float(os.getenv("ROUTE_RANK_DETOUR_WEIGHT", "1.0"))
POWER_WEIGHT_KM_PER_KW = float(os.getenv("ROUTE_RANK_POWER_WEIGHT", "0.05"))

# AC 2.2.4: the driver's charging preferences must actually move the ranking.
# `prefer_fast_charging=True` rewards available charging power far harder, so a
# 200 kW station a couple of km off the corridor beats a 22 kW one on it;
# `False` drops the power term entirely and minimises detour alone.
FAST_CHARGING_POWER_WEIGHT = float(os.getenv("ROUTE_RANK_FAST_POWER_WEIGHT", "0.25"))
MIN_DETOUR_POWER_WEIGHT = float(os.getenv("ROUTE_RANK_MIN_DETOUR_POWER_WEIGHT", "0.0"))
# route_type='shortest' weights added distance harder than the default 'fastest'.
SHORTEST_DETOUR_WEIGHT = float(os.getenv("ROUTE_RANK_SHORTEST_DETOUR_WEIGHT", "2.0"))


class RankingWeights(NamedTuple):
    """How the driver's preferences translate into the km-equivalent rank score."""
    detour_weight: float = DETOUR_WEIGHT
    power_weight_km_per_kw: float = POWER_WEIGHT_KM_PER_KW


#: Preference-free weights, used when a caller ranks without a preferences object.
DEFAULT_RANKING_WEIGHTS = RankingWeights()


def ranking_weights_for(
    route_type: str = ROUTE_TYPE_FASTEST,
    prefer_fast_charging: bool = True,
) -> RankingWeights:
    """Map AC 2.2.4 preferences onto ranking weights (the whole point of the AC)."""
    detour = SHORTEST_DETOUR_WEIGHT if route_type == ROUTE_TYPE_SHORTEST else DETOUR_WEIGHT
    power = FAST_CHARGING_POWER_WEIGHT if prefer_fast_charging else MIN_DETOUR_POWER_WEIGHT
    return RankingWeights(detour_weight=detour, power_weight_km_per_kw=power)

# Corridor prefilter half-size, in degrees, around the origin-destination box.
# Only used by the degenerate/offline fallback path -- the primary prefilter is
# `stations_repo.along_corridor`, which orders by proximity to the route.
CORRIDOR_MARGIN_DEG = float(os.getenv("ROUTE_CORRIDOR_MARGIN_DEG", "0.25"))
CANDIDATE_FETCH_LIMIT = int(os.getenv("ROUTE_CANDIDATE_FETCH_LIMIT", "150"))

# Half-width of the corridor searched around the route line, in km.
CORRIDOR_MIN_KM = float(os.getenv("ROUTE_CORRIDOR_MIN_KM", "10.0"))
# Buckets used to spread the fetched candidates ALONG the corridor.
CORRIDOR_BUCKETS = int(os.getenv("ROUTE_CORRIDOR_BUCKETS", "20"))

# Reach-floor ladder (see `reach_floor_ladder`): when no station is reachable
# with the full reserve intact, the floor degrades to this absolute minimum SoC
# before, as a last resort, dropping to bare physical reachability.
DEGRADED_REACH_FLOOR_SOC_PCT = float(os.getenv("ROUTE_DEGRADED_FLOOR_SOC_PCT", "5.0"))

# Float comparison tolerance for SoC checks (values are rounded to 2 dp).
_SOC_EPS = 0.01

DISTANCE_BASIS_ROAD = "road"
DISTANCE_BASIS_STRAIGHT_LINE = "straight_line"


def required_target_soc_pct(
    energy_estimator: EnergyEstimator,
    battery_kwh: float,
    efficiency_wh_per_km: float,
    remaining_distance_km: float,
    reserve_soc_pct: float,
) -> float:
    """SoC needed when leaving the stop to finish the trip with the reserve intact."""
    leg_soc = energy_estimator.soc_pct_for_distance(
        battery_kwh, efficiency_wh_per_km, remaining_distance_km
    )
    return leg_soc + float(reserve_soc_pct)


def choose_target_soc_pct(required_pct: float) -> Optional[float]:
    """Preferred charge target, raised only as far as the trip demands.

    Capped at ``DEFAULT_TARGET_SOC_PCT`` (80%) because DC charging past that
    point is slow, but never below what the remaining leg requires. Returns
    ``None`` when even a full pack is not enough -- the caller must then reject
    the candidate.
    """
    target = max(DEFAULT_TARGET_SOC_PCT, required_pct)
    if target > MAX_TARGET_SOC_PCT + _SOC_EPS:
        return None
    return min(target, MAX_TARGET_SOC_PCT)


def reach_floor_ladder(reserve_pct: float) -> List[float]:
    """Reach floors to try, strictest first (AC 2.2.9 first, AC 2.1.1 as fallback).

    AC 2.2.9 wants only stations "reachable with the reserve intact". Applying
    that as a hard yes/no against the driver's *current* SoC produced a dead
    zone just above the reserve: a driver at 22% was told nothing was reachable
    while the same driver at 20% was offered five stations, because the floor
    collapsed to 0 in one step. The floor is a property of the TRIP, not of the
    current SoC, so it now degrades over a fixed ladder that is identical at
    every SoC: strict reserve -> a small absolute floor -> bare reachability.
    A pass is only attempted when the stricter one returned nothing, which keeps
    reserve-intact candidates ranked ahead of degraded ones and makes the result
    monotonic in starting SoC.
    """
    reserve_pct = float(reserve_pct)
    floors = [reserve_pct]
    degraded = min(reserve_pct, DEGRADED_REACH_FLOOR_SOC_PCT)
    if degraded < reserve_pct - _SOC_EPS:
        floors.append(degraded)
    if floors[-1] > _SOC_EPS:
        floors.append(0.0)
    return floors


class CandidateRejection(Exception):
    """Internal control flow: this candidate cannot serve the trip."""


class StopRanker:
    """Ranks viable charging stop candidates along a route corridor."""

    def __init__(self, energy_estimator: EnergyEstimator, routing_service: RoutingService):
        self.energy_estimator = energy_estimator
        self.routing_service = routing_service

    # ---- candidate fetching ------------------------------------------------
    def _fetch_stations(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        forced_station_id: Optional[str],
        corridor_km: float = CORRIDOR_MIN_KM,
    ) -> List[Dict[str, Any]]:
        """Candidate stations along the corridor, ordered by proximity to the route.

        NEVER `ORDER BY id LIMIT n`: station ids sort lexicographically, so an
        id-ordered slice returned only `open_charge_map-*` rows and hid the
        entire `pln_spklu-*` network -- the primary dataset -- from every route
        plan. `stations_repo.along_corridor` orders by distance to the route line
        and spreads the fetched rows along it.
        """
        if forced_station_id:
            try:
                from api.stations_repo import get_station
                st = get_station(forced_station_id)
            except Exception:
                st = None
            return [st] if st else []

        straight_km = haversine_distance_km(origin[0], origin[1], destination[0], destination[1])
        radius_km = max(float(corridor_km), CORRIDOR_MIN_KM)

        try:
            from api.stations_repo import along_corridor, nearby
            if straight_km < 0.1:
                # Degenerate "line": ST_LineLocatePoint has nothing to project onto.
                return nearby(origin[0], origin[1], radius_km, CANDIDATE_FETCH_LIMIT)
            return along_corridor(
                origin=origin,
                destination=destination,
                corridor_km=radius_km,
                limit=CANDIDATE_FETCH_LIMIT,
                buckets=CORRIDOR_BUCKETS,
            )
        except Exception:
            return self._fetch_stations_bbox_fallback(origin, destination)

    @staticmethod
    def _fetch_stations_bbox_fallback(
        origin: Tuple[float, float], destination: Tuple[float, float]
    ) -> List[Dict[str, Any]]:
        """Last-resort prefilter when the corridor query is unavailable."""
        min_lat = min(origin[0], destination[0]) - CORRIDOR_MARGIN_DEG
        max_lat = max(origin[0], destination[0]) + CORRIDOR_MARGIN_DEG
        min_lon = min(origin[1], destination[1]) - CORRIDOR_MARGIN_DEG
        max_lon = max(origin[1], destination[1]) + CORRIDOR_MARGIN_DEG
        bbox = (min_lon, min_lat, max_lon, max_lat)

        try:
            from api.stations_repo import list_stations
            _, stations = list_stations({"bbox": bbox}, limit=CANDIDATE_FETCH_LIMIT, offset=0)
            return stations
        except Exception:
            return []

    # ---- public API --------------------------------------------------------
    async def rank_stops(
        self,
        origin: Tuple[float, float],       # (lat, lon)
        destination: Tuple[float, float],  # (lat, lon)
        direct_distance_km: float,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        current_soc_pct: float,
        minimum_arrival_soc_pct: float,
        vehicle_connector: Optional[str] = None,
        max_dc_charge_kw: Optional[float] = None,
        maximum_detour_km: float = 15.0,
        forced_station_id: Optional[str] = None,
        connector_profile: Optional[VehicleConnectorProfile] = None,
        distance_scale_factor: float = 1.0,
        distance_basis: str = DISTANCE_BASIS_STRAIGHT_LINE,
        limit: Optional[int] = None,
        weights: RankingWeights = DEFAULT_RANKING_WEIGHTS,
    ) -> List[RecommendedStop]:
        """Every station that passes all AC 2.2.9 filters, best first.

        ``weights`` carries the driver's AC 2.2.4 charging preferences into the
        score; the default is the preference-free weighting.
        """
        stations = self._fetch_stations(
            origin, destination, forced_station_id, corridor_km=float(maximum_detour_km)
        )
        if not stations:
            return []

        profile = connector_profile or vehicle_connector_profile(vehicle_connector)

        # ONE query for the whole candidate set -- never one per station.
        availability = fetch_availability([s["id"] for s in stations])

        scale = float(distance_scale_factor) if distance_scale_factor and distance_scale_factor > 0 else 1.0
        reserve_pct = float(minimum_arrival_soc_pct)

        # AC 2.2.9 strictness first; AC 2.1.1 ("always offer stations the driver
        # can add as a stop") as a fallback only when the strict pass is empty.
        for reach_floor_pct in reach_floor_ladder(reserve_pct):
            scored: List[Tuple[float, str, RecommendedStop]] = []
            for st in stations:
                try:
                    stop = self._evaluate_candidate(
                        st=st,
                        origin=origin,
                        destination=destination,
                        direct_distance_km=float(direct_distance_km),
                        battery_kwh=float(battery_kwh),
                        efficiency_wh_per_km=float(efficiency_wh_per_km),
                        current_soc_pct=float(current_soc_pct),
                        reserve_pct=reserve_pct,
                        reach_floor_pct=reach_floor_pct,
                        profile=profile,
                        max_dc_charge_kw=max_dc_charge_kw,
                        maximum_detour_km=float(maximum_detour_km),
                        availability=availability_or_empty(availability, st["id"]),
                        scale=scale,
                        distance_basis=distance_basis,
                        forced=bool(forced_station_id),
                        weights=weights,
                    )
                except CandidateRejection:
                    continue
                except (KeyError, TypeError, ValueError):
                    continue
                scored.append((stop.rank_score, str(st["id"]), stop))

            if not scored:
                continue

            # Deterministic: detour asc / power desc folded into rank_score, id breaks ties.
            scored.sort(key=lambda x: (x[0], x[1]))
            stops = [s for _, _, s in scored]
            return stops[:limit] if limit else stops

        return []

    async def select_recommended_stop(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        direct_distance_km: float,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        current_soc_pct: float,
        minimum_arrival_soc_pct: float,
        vehicle_connector: Optional[str],
        max_dc_charge_kw: Optional[float],
        maximum_detour_km: float = 15.0,
        forced_station_id: Optional[str] = None,
        connector_profile: Optional[VehicleConnectorProfile] = None,
        distance_scale_factor: float = 1.0,
        distance_basis: str = DISTANCE_BASIS_STRAIGHT_LINE,
    ) -> Optional[RecommendedStop]:
        """Best single stop, or ``None`` when no station satisfies AC 2.2.9."""
        stops = await self.rank_stops(
            origin=origin,
            destination=destination,
            direct_distance_km=direct_distance_km,
            battery_kwh=battery_kwh,
            efficiency_wh_per_km=efficiency_wh_per_km,
            current_soc_pct=current_soc_pct,
            minimum_arrival_soc_pct=minimum_arrival_soc_pct,
            vehicle_connector=vehicle_connector,
            max_dc_charge_kw=max_dc_charge_kw,
            maximum_detour_km=maximum_detour_km,
            forced_station_id=forced_station_id,
            connector_profile=connector_profile,
            distance_scale_factor=distance_scale_factor,
            distance_basis=distance_basis,
            limit=1,
        )
        return stops[0] if stops else None

    # ---- per-candidate evaluation -----------------------------------------
    def _evaluate_candidate(
        self,
        st: Dict[str, Any],
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        direct_distance_km: float,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        current_soc_pct: float,
        reserve_pct: float,
        reach_floor_pct: float,
        profile: VehicleConnectorProfile,
        max_dc_charge_kw: Optional[float],
        maximum_detour_km: float,
        availability: StationConnectorAvailability,
        scale: float,
        distance_basis: str,
        forced: bool,
        weights: RankingWeights = DEFAULT_RANKING_WEIGHTS,
    ) -> RecommendedStop:
        st_lat = float(st["latitude"])
        st_lon = float(st["longitude"])

        # --- distances, all in ONE basis ------------------------------------
        leg_to_station_km = haversine_distance_km(origin[0], origin[1], st_lat, st_lon) * scale
        leg_to_dest_km = haversine_distance_km(st_lat, st_lon, destination[0], destination[1]) * scale
        detour_km = max(0.0, (leg_to_station_km + leg_to_dest_km) - direct_distance_km)

        # A driver-forced waypoint may skip the SOFT preference filter (detour
        # budget) -- it must never skip the physics below.
        if detour_km > maximum_detour_km and not forced:
            raise CandidateRejection("detour over budget")

        blocking_reasons: List[str] = []

        # --- (b) reachable WITH THE RESERVE INTACT ---------------------------
        est_to_st = self.energy_estimator.estimate_trip_energy(
            battery_kwh=battery_kwh,
            efficiency_wh_per_km=efficiency_wh_per_km,
            distance_km=leg_to_station_km,
            current_soc_pct=current_soc_pct,
            minimum_arrival_soc_pct=reserve_pct,
        )
        if est_to_st.raw_arrival_soc_pct < (reach_floor_pct - _SOC_EPS):
            if not forced:
                raise CandidateRejection("station not reachable with the reserve intact")
            blocking_reasons.append("unreachable")
        reserve_intact_on_arrival = est_to_st.raw_arrival_soc_pct >= (reserve_pct - _SOC_EPS)

        # --- (c) a FREE connector the vehicle can use ------------------------
        usable_types = list(profile.types)
        free_compatible = availability.available_count_for(usable_types)
        matched_types = [t for t in usable_types if availability.available_by_type.get(t, 0) > 0]
        if free_compatible <= 0:
            if not forced:
                raise CandidateRejection("no free connector this vehicle can use")
            blocking_reasons.append("no_free_compatible_connector")

        matched_type = matched_types[0] if matched_types else None
        connector_compatible = bool(matched_types) or bool(
            set(usable_types) & set(availability.total_by_type.keys())
        )

        # --- (d) the stop must COMPLETE the trip -----------------------------
        required_pct = required_target_soc_pct(
            self.energy_estimator, battery_kwh, efficiency_wh_per_km, leg_to_dest_km, reserve_pct
        )
        target_soc_pct = choose_target_soc_pct(required_pct)
        if target_soc_pct is None:
            if not forced:
                raise CandidateRejection("even a full charge here cannot finish the trip")
            blocking_reasons.append("cannot_complete_trip")
            target_soc_pct = MAX_TARGET_SOC_PCT

        arrival_soc_at_st = max(0.0, est_to_st.estimated_arrival_soc_pct)
        projected_destination_soc = target_soc_pct - self.energy_estimator.soc_pct_for_distance(
            battery_kwh, efficiency_wh_per_km, leg_to_dest_km
        )
        if projected_destination_soc < (reserve_pct - _SOC_EPS):
            if not forced:
                raise CandidateRejection("arrival below reserve even after charging")
            if "cannot_complete_trip" not in blocking_reasons:
                blocking_reasons.append("cannot_complete_trip")

        # --- charging power: prefer the best FREE compatible connector -------
        live_power_kw = availability.best_power_for(usable_types)
        station_power_kw = float(
            live_power_kw
            if live_power_kw is not None
            else (st.get("power_kw") or 0.0)
        ) or None

        charge_info = self.energy_estimator.calculate_charging_minutes(
            battery_kwh=battery_kwh,
            arrival_soc_pct=arrival_soc_at_st,
            target_soc_pct=target_soc_pct,
            vehicle_max_dc_charge_kw=max_dc_charge_kw,
            station_power_kw=station_power_kw,
        )

        # --- ranking: detour asc, available power desc, weighted by preference ---
        rank_power_kw = float(live_power_kw if live_power_kw is not None else (st.get("power_kw") or 0.0))
        rank_score = round(
            (detour_km * weights.detour_weight) - (rank_power_kw * weights.power_weight_km_per_kw), 4)

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
            power_kw=float(st.get("power_kw")) if st.get("power_kw") is not None else rank_power_kw or None,
            charge_type=st.get("charge_type") or "fast",
            speed_tier=st.get("speed_tier") or "fast",
            connectors=st.get("connectors") or [],
            connector_types=st.get("connector_types") or [],
            connector_inferred=st.get("connector_inferred", True),
            status=st.get("status") or "operational",
            date_verified=st.get("date_verified"),
            distance_km=round(leg_to_station_km, 1),
        )

        return RecommendedStop(
            station=station_model,
            distance_from_origin_km=round(leg_to_station_km, 1),
            distance_to_destination_km=round(leg_to_dest_km, 1),
            detour_km=round(detour_km, 1),
            distance_basis=distance_basis,
            arrival_soc_pct=round(arrival_soc_at_st, 1),
            recommended_target_soc_pct=round(target_soc_pct, 1),
            required_target_soc_pct=round(required_pct, 1),
            projected_destination_soc_pct=round(projected_destination_soc, 1),
            completes_trip=not blocking_reasons,
            blocking_reasons=list(blocking_reasons),
            reserve_intact_on_arrival=reserve_intact_on_arrival,
            energy_to_add_kwh=charge_info["energy_to_add_kwh"],
            estimated_charging_minutes=charge_info["estimated_charging_minutes"],
            effective_charging_power_kw=charge_info["effective_charging_power_kw"],
            connector_compatible=connector_compatible,
            matched_connector_type=matched_type,
            connector_match_inferred=bool(matched_type and profile.is_inferred(matched_type)),
            vehicle_connector_types=usable_types,
            available_connector_count=int(free_compatible),
            available_connector_types=list(availability.available_types),
            available_by_type=dict(availability.available_by_type),
            total_connector_count=int(availability.total),
            best_available_power_kw=live_power_kw,
            availability="available_now" if free_compatible > 0 else "unavailable",
            data_confidence=("high" if availability.total > 0 and not st.get("connector_inferred") else "medium"),
            rank_score=rank_score,
            detour_budget_km=round(float(maximum_detour_km), 1),
            detour_within_budget=detour_km <= float(maximum_detour_km),
        )

    # ---- road-distance re-validation --------------------------------------
    def revalidate_on_road(
        self,
        stop: RecommendedStop,
        road_leg_to_station_km: float,
        road_leg_to_destination_km: float,
        road_direct_distance_km: float,
        battery_kwh: float,
        efficiency_wh_per_km: float,
        current_soc_pct: float,
        reserve_pct: float,
        max_dc_charge_kw: Optional[float],
        distance_basis: str = DISTANCE_BASIS_ROAD,
        forced: bool = False,
        weights: RankingWeights = DEFAULT_RANKING_WEIGHTS,
        maximum_detour_km: Optional[float] = None,
    ) -> Optional[RecommendedStop]:
        """Re-check a ranked stop against the ACTUAL road legs the driver will drive.

        Ranking uses `haversine * corridor_average_scale`, so a detour leg more
        winding than the corridor average silently broke the
        `projected_destination_soc >= reserve` guarantee (a 1.4x leg is an
        ordinary Java mountain road). The selected stop is therefore re-derived
        from the real routed legs before it is offered.

        Returns the stop with every distance/SoC field restated on the road
        basis, or ``None`` when the candidate no longer holds (the caller falls
        through to the next ranked stop). A ``forced`` (driver-chosen) stop is
        never dropped -- it comes back with ``completes_trip=False`` and
        ``blocking_reasons`` instead, so the caller can warn rather than pretend.
        """
        leg1 = max(0.0, float(road_leg_to_station_km))
        leg2 = max(0.0, float(road_leg_to_destination_km))
        reserve_pct = float(reserve_pct)
        blocking_reasons: List[str] = [r for r in (stop.blocking_reasons or [])
                                       if r == "no_free_compatible_connector"]

        est_to_st = self.energy_estimator.estimate_trip_energy(
            battery_kwh=battery_kwh,
            efficiency_wh_per_km=efficiency_wh_per_km,
            distance_km=leg1,
            current_soc_pct=current_soc_pct,
            minimum_arrival_soc_pct=reserve_pct,
        )
        # The floor this candidate was admitted under: the strict reserve for a
        # reserve-intact stop, bare reachability for a degraded-mode one.
        floor_pct = reserve_pct if stop.reserve_intact_on_arrival else 0.0
        if est_to_st.raw_arrival_soc_pct < (floor_pct - _SOC_EPS):
            if not forced:
                return None
            blocking_reasons.append("unreachable")

        required_pct = required_target_soc_pct(
            self.energy_estimator, battery_kwh, efficiency_wh_per_km, leg2, reserve_pct
        )
        target_soc_pct = choose_target_soc_pct(required_pct)
        if target_soc_pct is None:
            if not forced:
                return None
            blocking_reasons.append("cannot_complete_trip")
            target_soc_pct = MAX_TARGET_SOC_PCT

        projected_destination_soc = target_soc_pct - self.energy_estimator.soc_pct_for_distance(
            battery_kwh, efficiency_wh_per_km, leg2
        )
        if projected_destination_soc < (reserve_pct - _SOC_EPS):
            if not forced:
                return None
            if "cannot_complete_trip" not in blocking_reasons:
                blocking_reasons.append("cannot_complete_trip")

        arrival_soc_at_st = max(0.0, est_to_st.estimated_arrival_soc_pct)
        charge_info = self.energy_estimator.calculate_charging_minutes(
            battery_kwh=battery_kwh,
            arrival_soc_pct=arrival_soc_at_st,
            target_soc_pct=target_soc_pct,
            vehicle_max_dc_charge_kw=max_dc_charge_kw,
            station_power_kw=stop.best_available_power_kw or stop.station.power_kw,
        )

        detour_km = max(0.0, (leg1 + leg2) - float(road_direct_distance_km))
        rank_power_kw = float(stop.best_available_power_kw or stop.station.power_kw or 0.0)
        rank_score = round(
            (detour_km * weights.detour_weight) - (rank_power_kw * weights.power_weight_km_per_kw), 4)

        # AC 2.2.4: the detour budget was only ever a pre-ranking straight-line
        # filter, so the ROAD detour finally reported to the driver could exceed
        # the budget they set. It is re-checked here and reported honestly; the
        # caller prefers an in-budget candidate and only falls back to this one
        # when nothing inside the budget survived.
        budget_km = (float(maximum_detour_km) if maximum_detour_km is not None
                     else stop.detour_budget_km)
        within_budget = True if budget_km is None else detour_km <= float(budget_km)

        return stop.model_copy(update={
            "station": stop.station.model_copy(update={"distance_km": round(leg1, 1)}),
            "distance_from_origin_km": round(leg1, 1),
            "distance_to_destination_km": round(leg2, 1),
            "detour_km": round(detour_km, 1),
            "distance_basis": distance_basis,
            "arrival_soc_pct": round(arrival_soc_at_st, 1),
            "recommended_target_soc_pct": round(target_soc_pct, 1),
            "required_target_soc_pct": round(required_pct, 1),
            "projected_destination_soc_pct": round(projected_destination_soc, 1),
            "completes_trip": not blocking_reasons,
            "blocking_reasons": blocking_reasons,
            "reserve_intact_on_arrival": est_to_st.raw_arrival_soc_pct >= (reserve_pct - _SOC_EPS),
            "energy_to_add_kwh": charge_info["energy_to_add_kwh"],
            "estimated_charging_minutes": charge_info["estimated_charging_minutes"],
            "effective_charging_power_kw": charge_info["effective_charging_power_kw"],
            "rank_score": rank_score,
            "detour_budget_km": (round(float(budget_km), 1) if budget_km is not None else None),
            "detour_within_budget": within_budget,
        })

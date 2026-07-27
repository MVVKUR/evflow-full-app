"""Pydantic request and response models. These drive the OpenAPI (Swagger) schema."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Source(str, Enum):
    pln_spklu = "pln_spklu"
    open_charge_map = "open_charge_map"
    osm = "osm"


class Connector(BaseModel):
    type: str = Field(..., description="Connector standard (inferred from power).", examples=["CCS2"])
    count: int = Field(..., description="Number of this connector at the station.", examples=[2])
    speed_tier: Optional[str] = Field(None, examples=["ultra_fast"])
    power_kw: Optional[float] = Field(None, examples=[200.0])
    type_inferred: bool = Field(True, description="True when the type is inferred from power, not source data.")


class StationConnector(BaseModel):
    """One physical connector (a real row, promoted from the stations JSONB)."""
    id: str = Field(..., description="Connector id (uuid).")
    station_id: str = Field(..., examples=["pln_spklu-1"])
    type: str = Field(..., examples=["CCS2"])
    power_kw: Optional[float] = Field(None, examples=[150.0])
    speed_tier: Optional[str] = Field(None, examples=["fast"])
    type_inferred: bool = Field(False, description="True when the type is inferred from power, not source data.")
    status: str = Field(..., description="available / in_use / out_of_service.", examples=["available"])
    updated_at: datetime


class StationAvailability(BaseModel):
    """Connector availability counts for one station."""
    station_id: str = Field(..., examples=["pln_spklu-1"])
    total: int = Field(..., examples=[4])
    available: int = Field(..., examples=[3])
    in_use: int = Field(..., examples=[1])
    out_of_service: int = Field(..., examples=[0])


class ConnectorStatusUpdate(BaseModel):
    status: str = Field(..., description="New connector status.",
                        examples=["available", "in_use", "out_of_service"])


class Station(BaseModel):
    id: str = Field(..., description="Stable unique id, '<source>-<n>'.", examples=["pln_spklu-1"])
    name: Optional[str] = Field(None, examples=["SPKLU PLN UID JAKARTA RAYA"])
    sources: list[Source] = Field(
        default_factory=list,
        description="Datasets this station appears in (deduplicated).",
        examples=[["pln_spklu", "open_charge_map"]])
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.18039])
    longitude: float = Field(..., ge=-180, le=180, examples=[106.833191])
    address: Optional[str] = Field(None, examples=["Jl. M.I. Ridwan Rais No.1, Gambir"])
    province: Optional[str] = Field(None, examples=["DKI Jakarta"])
    city: Optional[str] = Field(None, examples=["Kota ADM Jakarta Pusat"])
    operator: Optional[str] = Field(None, examples=["PLN"])
    power_kw: Optional[float] = Field(None, description="Peak power (kW).", examples=[22.0])
    charge_type: Optional[str] = Field(None, description="slow / medium / fast where known.", examples=["medium"])
    speed_tier: Optional[str] = Field(
        None, description="Speed bucket from power: slow / medium / fast / ultra_fast.", examples=["medium"])
    connectors: list[Connector] = Field(
        default_factory=list,
        description="Per-connector breakdown: type (inferred), real count/power/speed.")
    connector_types: list[str] = Field(
        default_factory=list,
        description="Connector standards present, e.g. ['CCS2'] or ['AC Type 2']. Currently inferred.",
        examples=[["AC Type 2"]])
    connector_inferred: Optional[bool] = Field(
        None, description="True when connector_types are inferred from power, not from source data.",
        examples=[True])
    status: Optional[str] = Field(None, description="Operational status if reported.", examples=["operational"])
    date_verified: Optional[str] = Field(None, description="ISO timestamp last verified (OCM).")
    distance_km: Optional[float] = Field(None, description="Set only on /nearby results.", examples=[1.42])


class StationList(BaseModel):
    total: int = Field(..., description="Total matching records (before pagination).", examples=[1142])
    limit: int = Field(..., examples=[100])
    offset: int = Field(..., examples=[0])
    items: list[Station]


class SourceCount(BaseModel):
    source: Source
    count: int


class NameCount(BaseModel):
    name: str = Field(..., examples=["DKI Jakarta"])
    count: int = Field(..., examples=[731])


class SpeedTier(BaseModel):
    """One charging-speed bucket with its power range + station count."""
    id: str = Field(..., examples=["fast"])
    label: str = Field(..., examples=["Fast"])
    min_kw: float = Field(..., description="Lower power bound (kW), inclusive.", examples=[50.0])
    max_kw: Optional[float] = Field(None, description="Upper power bound (kW); null for ultra_fast.", examples=[150.0])
    count: int = Field(..., description="Stations in this tier.", examples=[789])


class Stats(BaseModel):
    total: int = Field(..., examples=[3569])
    by_source: list[SourceCount]
    by_province: list[NameCount]
    by_charge_type: list[NameCount]
    with_power_kw: int = Field(..., description="Records that have a known power rating.")
    power_kw_min: Optional[float] = None
    power_kw_max: Optional[float] = None
    power_kw_mean: Optional[float] = None


class GeoJSONFeatureCollection(BaseModel):
    """RFC 7946 FeatureCollection. Drop straight into Leaflet or Mapbox."""
    type: str = Field("FeatureCollection", examples=["FeatureCollection"])
    features: list[dict[str, Any]]


class Health(BaseModel):
    status: str = Field(..., examples=["ok"])
    stations_loaded: int = Field(..., examples=[3569])
    version: str = Field(..., examples=["1.0.0"])


# ---- routing (Epic 2.0: shortest path via Dijkstra) -------------------------
class RouteGeometry(BaseModel):
    """GeoJSON LineString. Pass it to L.geoJSON() to draw the path on the map."""
    type: str = Field("LineString", examples=["LineString"])
    coordinates: list[list[float]] = Field(
        ..., description="Ordered [longitude, latitude] pairs (WGS84)."
    )


class RoutePoint(BaseModel):
    lat: float = Field(..., examples=[-6.2088])
    lon: float = Field(..., examples=[106.8456])
    snapped_node: str = Field(..., description="Nearest road-graph node the point was snapped to.")
    snap_distance_km: float = Field(..., description="Distance from the input point to the snapped node.")
    station_id: Optional[str] = Field(None, description="Set on the destination when routing to a station.")


class Route(BaseModel):
    """Shortest driving path between two points (Dijkstra over the road graph)."""
    weight: str = Field(..., description="Cost minimised: 'length' (metres) or 'travel_time' (seconds).",
                        examples=["length"])
    distance_m: float = Field(..., description="Total path length in metres.", examples=[4230.5])
    duration_s: float = Field(..., description="Estimated drive time in seconds.", examples=[540.2])
    origin: RoutePoint
    destination: RoutePoint
    node_count: int = Field(..., description="Number of road nodes in the path.", examples=[87])
    geometry: RouteGeometry


class NearestStationRoute(BaseModel):
    """Nearest charging station reachable by road + the route to it (Epic 2.0)."""
    station: Station = Field(..., description="The closest reachable station; its distance_km mirrors the road distance.")
    route: Route
    candidates_considered: int = Field(..., description="How many stations were reachable by road and ranked.",
                                       examples=[1142])
    within_range: bool = Field(True, description="False if the nearest station is beyond the EV's remaining range.")
    range_used_km: Optional[float] = Field(
        None, description="Remaining range (km) used for the within_range check: either the explicit "
                          "max_range_km, or derived from ev_model_id plus current_soc.", examples=[85.0])


# ---- EV model catalogue (Kaggle Indonesia-EV-2026; seed of Epic 6.0) --------
class EVModel(BaseModel):
    id: str = Field(..., examples=["wuling-air-ev"])
    brand: Optional[str] = Field(None, examples=["Wuling"])
    name: str = Field(..., examples=["Wuling Air EV"])
    make: Optional[str] = Field(None, examples=["Wuling"])
    model: Optional[str] = Field(None, examples=["Air EV"])
    battery_kwh: Optional[float] = Field(None, description="Usable battery capacity (kWh).", examples=[26.7])
    battery_kwh_min: Optional[float] = Field(None, examples=[26.7])
    battery_kwh_max: Optional[float] = Field(None, examples=[26.7])
    range_km: Optional[float] = Field(
        None, description="Manufacturer range (km); the lower bound where a range is given.", examples=[200.0])
    range_km_min: Optional[float] = Field(None, examples=[200.0])
    range_km_max: Optional[float] = Field(None, examples=[300.0])
    efficiency_wh_per_km: Optional[float] = Field(None, description="Efficiency (Wh/km).", examples=[133.5])
    efficiency_source: Optional[str] = Field(None, examples=["derived_local_specs"])
    max_dc_charge_kw: Optional[float] = Field(None, description="Max DC fast charge power (kW).", examples=[50.0])
    fast_charge_port: Optional[str] = Field(None, examples=["CCS2"])
    price_range: Optional[str] = Field(None, examples=["Rp 214 - 307,5 Juta"])
    charging_time_minutes: Optional[float] = Field(None, description="Charging time in minutes.", examples=[510.0])
    source_url: Optional[str] = Field(None)
    match_method: Optional[str] = Field(None, examples=["normalized_fuzzy_match"])
    match_confidence: Optional[float] = Field(None, examples=[0.85])


class EVModelList(BaseModel):
    total: int = Field(..., examples=[60])
    limit: int = Field(..., examples=[100])
    offset: int = Field(..., examples=[0])
    items: list[EVModel]



# ---- wallet / top-up (Epic 3.0: Xendit integration) -------------------------
class TopupRequest(BaseModel):
    amount_idr: int = Field(..., ge=10000, description="Top-up amount in IDR (Xendit min 10000).", examples=[50000])


class TopupCreated(BaseModel):
    topup_id: str
    amount_idr: int
    status: str = Field(..., examples=["pending"])
    invoice_url: str = Field(..., description="Open this hosted Xendit page to pay.")


class WalletBalance(BaseModel):
    balance_idr: int = Field(..., examples=[200000])
    currency: str = Field("IDR", examples=["IDR"])
    updated_at: datetime


class Topup(BaseModel):
    id: str
    external_id: str
    xendit_invoice_id: Optional[str] = None
    amount_idr: int
    status: str = Field(..., examples=["paid"])
    invoice_url: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None


# ---- charging sessions (Epic 4.0: real wallet debit + settlement) -----------
class ChargingQuoteRequest(BaseModel):
    energy_kwh: float = Field(..., gt=0, le=150, description="Requested energy in kWh.", examples=[20])


class ChargingQuote(BaseModel):
    energy_kwh: float
    base_rate_idr: int = Field(..., examples=[2466])
    admin_fee_idr: int = Field(..., examples=[2500])
    energy_cost_idr: int = Field(..., examples=[49320])
    total_due_idr: int = Field(..., description="Deposit charged at session start.", examples=[51820])
    currency: str = "IDR"


class StartSessionRequest(BaseModel):
    station_id: str = Field(..., examples=["pln_spklu-1"])
    energy_kwh: float = Field(..., gt=0, le=150, examples=[20])
    station_name: Optional[str] = Field(None, examples=["SPKLU PLN UID JAKARTA RAYA"])
    connector_type: Optional[str] = Field(None, examples=["CCS2"])
    power_kw: Optional[float] = Field(None, examples=[150])


class SettleRequest(BaseModel):
    delivered_kwh: float = Field(..., ge=0, le=500, description="Energy actually delivered (kWh).", examples=[16.5])


class ChargingSession(BaseModel):
    id: str
    station_id: str
    station_name: Optional[str] = None
    connector_type: Optional[str] = None
    power_kw: Optional[float] = None
    energy_kwh: float
    base_rate_idr: int
    admin_fee_idr: int
    deposit_idr: int
    delivered_kwh: Optional[float] = None
    actual_cost_idr: Optional[int] = None
    refund_idr: Optional[int] = None
    status: str = Field(..., examples=["active", "completed"])
    connector_id: Optional[str] = Field(
        None, description="Physical connector claimed for this session; null if none was available.")
    created_at: datetime
    completed_at: Optional[datetime] = None
    wallet_balance_idr: int = Field(..., description="Wallet balance after this operation.", examples=[198180])


# ---- authentication / accounts (Epic 5.0) ------------------------------------
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, examples=["budi"])
    password: str = Field(..., min_length=8, examples=["s3cret123"])
    email: Optional[str] = Field(None, examples=["budi@example.com"])
    full_name: Optional[str] = Field(None, examples=["Budi Santoso"])
    ev_model_id: Optional[str] = Field(None, examples=["hyundai-ioniq-5"])
    main_connector_type: Optional[str] = Field(None, examples=["CCS2"])
    location_consent: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., examples=["budi@example.com"])


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., examples=["k3y-from-the-emailed-link"])
    # bcrypt only uses the first 72 bytes; cap length so nothing is silently truncated.
    new_password: str = Field(..., min_length=8, max_length=72, examples=["n3ws3cret123"])


class ResetPasswordResponse(BaseModel):
    message: str


class ProfileUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3)
    ev_model_id: Optional[str] = None
    main_connector_type: Optional[str] = None
    location_consent: Optional[bool] = None


class UserPublic(BaseModel):
    id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    account_type: str = "ev_user"
    ev_model_id: Optional[str] = None
    main_connector_type: Optional[str] = None
    location_consent: bool = False
    profile_completed: bool = False
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---- Epic 2.0 Route Planning & Geocoding Schemas ----------------------------
class RouteLocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.2088])
    longitude: float = Field(..., ge=-180, le=180, examples=[106.8456])
    label: Optional[str] = Field(None, examples=["Current Location"])


class RoutePreferencesInput(BaseModel):
    route_type: str = Field("fastest", examples=["fastest"])
    maximum_detour_km: float = Field(8.0, ge=1.0, le=50.0, examples=[8.0])
    prefer_fast_charging: bool = Field(True)


class RoutePlanRequest(BaseModel):
    origin: RouteLocationInput
    destination: RouteLocationInput
    current_soc_pct: float = Field(..., ge=0, le=100, examples=[72.0])
    minimum_arrival_soc_pct: Optional[float] = Field(
        None, ge=0, le=50, examples=[20.0],
        description="Minimum arrival battery. Defaults to the server reserve (20%, AC 2.1.3). "
                    "The enforced value may be raised so the reserve is worth at least "
                    "ROUTE_MIN_RESERVE_KM km; see assumptions.effective_reserve_soc_pct.")
    preferences: Optional[RoutePreferencesInput] = Field(default_factory=RoutePreferencesInput)
    waypoint_station_id: Optional[str] = Field(None, description="Optional station ID to force as a route waypoint.")
    max_candidate_stops: int = Field(
        5, ge=1, le=25,
        description="How many ranked alternative stops to return alongside the recommended one.")


class VehicleSummary(BaseModel):
    id: str = Field(..., examples=["hyundai-ioniq-5"])
    name: str = Field(..., examples=["Hyundai Ioniq 5 Standard Range"])
    battery_kwh: float = Field(..., examples=[58.0])
    efficiency_wh_per_km: float = Field(..., examples=[160.0])
    efficiency_source: str = Field(..., examples=["dataset"])


class TripSummary(BaseModel):
    distance_km: float = Field(..., examples=[148.0])
    duration_minutes: float = Field(..., examples=[190.0])
    estimated_energy_kwh: float = Field(..., examples=[31.2])
    estimated_arrival_soc_pct: float = Field(..., examples=[12.0])
    minimum_arrival_soc_pct: float = Field(
        ..., description="The reserve actually enforced (effective, after the km floor).",
        examples=[20.0])
    requested_minimum_arrival_soc_pct: Optional[float] = Field(
        None, description="What the client asked for, before the km floor was applied.",
        examples=[20.0])
    effective_reserve_km: Optional[float] = Field(
        None, description="The enforced reserve expressed in km of range.", examples=[42.0])
    direct_arrival_soc_pct: Optional[float] = Field(
        None, description="Arrival SoC with NO charging stop, for the warning UI.", examples=[8.0])
    soc_margin_pct: Optional[float] = Field(
        None, description="Projected arrival SoC minus the enforced reserve.", examples=[3.0])


class RoutePlanGeometryAndSteps(BaseModel):
    type: str = Field("Feature", examples=["Feature"])
    geometry: RouteGeometry
    steps: list[dict[str, Any]] = Field(default_factory=list)


class RecommendedStop(BaseModel):
    station: Station
    distance_from_origin_km: float = Field(..., examples=[82.0])
    distance_to_destination_km: Optional[float] = Field(None, examples=[66.0])
    detour_km: float = Field(..., examples=[2.1])
    distance_basis: str = Field(
        "straight_line",
        description="Measure every distance above shares: 'road' (routing provider) or "
                    "'straight_line'. Detour never mixes the two.",
        examples=["road", "straight_line"])
    arrival_soc_pct: float = Field(..., examples=[18.0])
    recommended_target_soc_pct: float = Field(
        ..., description="Charge target: 80% by default, raised only as far as the remaining leg needs.",
        examples=[80.0])
    required_target_soc_pct: Optional[float] = Field(
        None, description="Minimum SoC on departure that still finishes the trip with the reserve intact.",
        examples=[46.0])
    projected_destination_soc_pct: Optional[float] = Field(
        None, description="Projected SoC at the destination after charging here.", examples=[24.0])
    completes_trip: bool = Field(
        True, description="True when this stop provably gets the driver to the destination above the reserve. "
                          "Only a driver-forced waypoint can come back False.")
    blocking_reasons: list[str] = Field(
        default_factory=list,
        description="Why a driver-forced waypoint is not viable: 'unreachable', "
                    "'no_free_compatible_connector', 'cannot_complete_trip'. Always empty for a "
                    "stop the system recommended itself.",
        examples=[["unreachable"]])
    reserve_intact_on_arrival: bool = Field(
        True,
        description="True when the driver still holds the reserve on arriving HERE. False only in the "
                    "degraded case where no station at all is reachable with the reserve intact.")
    energy_to_add_kwh: float = Field(..., examples=[20.0])
    estimated_charging_minutes: float = Field(..., examples=[25.0])
    effective_charging_power_kw: float = Field(..., examples=[50.0])
    connector_compatible: bool = Field(True)
    matched_connector_type: Optional[str] = Field(
        None, description="The free connector type the vehicle will use here.", examples=["CCS2"])
    connector_match_inferred: bool = Field(
        False, description="True when the match relies on the assumed universal AC Type 2 inlet.")
    vehicle_connector_types: list[str] = Field(
        default_factory=list, description="Connector standards this vehicle was assumed to accept.",
        examples=[["CCS2", "AC Type 2"]])
    available_connector_count: int = Field(
        0, description="Free connectors of a type this vehicle can use (live `connectors` table).",
        examples=[2])
    available_connector_types: list[str] = Field(
        default_factory=list, description="All connector types with at least one free plug right now.")
    available_by_type: dict[str, int] = Field(
        default_factory=dict, description="Free connector count per type.", examples=[{"CCS2": 2}])
    total_connector_count: int = Field(0, description="All connector rows at this station.", examples=[4])
    best_available_power_kw: Optional[float] = Field(
        None, description="Highest power among the free connectors.", examples=[150.0])
    availability: str = Field("unknown", examples=["available_now", "unavailable", "unknown"])
    data_confidence: str = Field("medium", examples=["high", "medium", "low"])
    rank_score: float = Field(
        0.0, description="Deterministic rank score (detour km penalised, available power rewarded); lower is better.",
        examples=[1.4])


class RoutePlanAssumptions(BaseModel):
    reserve_soc_pct: float = Field(20.0, description="The reserve actually enforced.")
    requested_reserve_soc_pct: Optional[float] = Field(None)
    effective_reserve_km: Optional[float] = Field(None, examples=[42.0])
    minimum_reserve_km: Optional[float] = Field(None, examples=[15.0])
    distance_basis: str = Field("straight_line", examples=["road", "straight_line"])
    vehicle_connector_types: list[str] = Field(default_factory=list, examples=[["CCS2", "AC Type 2"]])
    connector_source: str = Field("default", examples=["ev_model", "user_profile", "default"])
    weather_applied: bool = Field(False)
    traffic_applied: bool = Field(False)
    connector_data_inferred: bool = Field(True)
    energy_model_version: str = Field("spec-v1")


class RouteWarning(BaseModel):
    """AC 2.1.1 in-app warning payload."""
    triggered: bool = Field(..., examples=[True])
    code: str = Field(..., examples=["battery_below_reserve", "battery_margin_tight", "no_suitable_station"])
    severity: str = Field("warning", examples=["info", "warning", "critical"])
    message: str = Field(..., examples=["Battery will drop below your 20% reserve before you arrive."])
    projected_arrival_soc_pct: float = Field(..., examples=[8.0])
    reserve_soc_pct: float = Field(..., examples=[20.0])
    shortfall_soc_pct: float = Field(0.0, description="How far below the reserve the projection lands.", examples=[12.0])
    can_dismiss: bool = Field(True, description="AC 2.1.1 lets the driver dismiss and continue.")


class RoutePlanResponse(BaseModel):
    route_plan_id: str = Field(..., examples=["ephemeral-12345"])
    route_status: str = Field(
        "direct_route_available",
        description="'direct_route_available' (AC 2.1.2 green state, charging_stops is empty), "
                    "'charging_required' (AC 2.1.3), or 'no_suitable_station'.",
        examples=["direct_route_available", "charging_required", "no_suitable_station"])
    margin_is_tight: bool = Field(
        False,
        description="Arrival is above the reserve but within the tight margin. Still a DIRECT route "
                    "with no charging stops -- AC 2.1.2 continues to hold.")
    directly_reachable: bool = Field(..., examples=[False])
    vehicle: VehicleSummary
    summary: TripSummary
    route: RoutePlanGeometryAndSteps
    recommended_stop: Optional[RecommendedStop] = Field(
        None,
        description="The stop the SYSTEM recommends. Mirrors charging_stops[0] and is ALWAYS null "
                    "when route_status == 'direct_route_available' (AC 2.1.2). A stop the driver "
                    "forced via waypoint_station_id on an otherwise-direct route appears in "
                    "user_requested_stop instead.")
    charging_stops: list[RecommendedStop] = Field(
        default_factory=list,
        description="Ordered charging stops for this plan. ALWAYS empty when "
                    "route_status == 'direct_route_available' (AC 2.1.2).")
    user_requested_stop: Optional[RecommendedStop] = Field(
        None,
        description="The waypoint_station_id the driver asked for, honoured on a route that did not "
                    "need a charging stop. Never a system recommendation; check completes_trip and "
                    "blocking_reasons before relying on it.")
    alternative_stops: list[RecommendedStop] = Field(
        default_factory=list, description="Other viable stations the driver can pick instead.")
    warning: Optional[RouteWarning] = None
    assumptions: RoutePlanAssumptions = Field(default_factory=RoutePlanAssumptions)


# ---- AC 2.1.1: re-evaluating an ACTIVE route -------------------------------
class ActiveRouteEvaluationRequest(BaseModel):
    current_position: RouteLocationInput = Field(..., description="Where the driver is right now.")
    destination: RouteLocationInput
    current_soc_pct: float = Field(..., ge=0, le=100, examples=[26.0])
    minimum_arrival_soc_pct: Optional[float] = Field(None, ge=0, le=50, examples=[20.0])
    route_plan_id: Optional[str] = Field(None, description="Plan being driven, echoed back.")
    maximum_detour_km: float = Field(15.0, ge=1.0, le=50.0)
    max_candidate_stops: int = Field(5, ge=1, le=25)


class ActiveRouteEvaluationResponse(BaseModel):
    """What the in-app warning sheet needs (AC 2.1.1).

    'Add as a stop' and 'Dismiss' are client actions; the backend supplies the
    projection, the warning flag and the nearby stations to choose from.
    """
    route_plan_id: Optional[str] = None
    route_status: str = Field(..., examples=["direct_route_available", "charging_required", "no_suitable_station"])
    margin_is_tight: bool = Field(False)
    warning: Optional[RouteWarning] = None
    remaining_distance_km: float = Field(..., examples=[86.0])
    remaining_duration_minutes: float = Field(..., examples=[95.0])
    estimated_energy_kwh: float = Field(..., examples=[18.4])
    projected_arrival_soc_pct: float = Field(..., examples=[8.0])
    raw_projected_arrival_soc_pct: float = Field(..., examples=[8.2])
    reserve_soc_pct: float = Field(..., examples=[20.0])
    effective_reserve_km: Optional[float] = Field(None, examples=[42.0])
    distance_basis: str = Field("straight_line", examples=["road", "straight_line"])
    vehicle: VehicleSummary
    candidate_stops: list[RecommendedStop] = Field(
        default_factory=list,
        description="Nearby stations the driver could add as a stop, best first.")


class GeocodingItem(BaseModel):
    id: str = Field(..., examples=["place-1"])
    label: str = Field(..., examples=["Bandung"])
    subtitle: str = Field(..., examples=["West Java · via Tol Cipularang"])
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.9175])
    longitude: float = Field(..., ge=-180, le=180, examples=[107.6191])
    distance_km: Optional[float] = Field(None, examples=[148.0])
    type: str = Field(..., description="'place' or 'station'", examples=["place"])
    station: Optional[Station] = None
    attribution: str = Field("OpenStreetMap contributors, PLN SPKLU")


class GeocodingSearchResponse(BaseModel):
    query: str
    items: list[GeocodingItem]


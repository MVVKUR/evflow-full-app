"""Pydantic request and response models. These drive the OpenAPI (Swagger) schema."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from api.services import service_area

# Route-type vocabulary. Declared here (not in the ranker) so the request model
# can validate against it without importing a service that imports this module.
ROUTE_TYPE_FASTEST = "fastest"
ROUTE_TYPE_SHORTEST = "shortest"
SUPPORTED_ROUTE_TYPES = (ROUTE_TYPE_FASTEST, ROUTE_TYPE_SHORTEST)


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
    total_connectors: Optional[int] = Field(
        None, description="Physical connectors at this station, every status included.",
        examples=[8])
    available_connectors: Optional[int] = Field(
        None,
        description="Connectors free to plug into right now. Together with total_connectors "
                    "this is what colours a station pin on the map: 0 free means the driver "
                    "cannot charge here at all, which is a different answer from 'busy'.",
        examples=[3])
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
    in_service_area: bool = Field(
        True,
        description="False when this station lies OUTSIDE the configured route service area, "
                    "i.e. POST /api/v1/route-plans would reject it as an origin or "
                    "destination. Computed from the station's own coordinates, so discovery "
                    "(/api/v1/stations, /api/v1/stations/nearby, /api/v1/geocoding/search) and "
                    "planning can never disagree. The station dataset is national while a "
                    "deployment's service area may be narrower.")

    @model_validator(mode="after")
    def _set_in_service_area(self) -> "Station":
        object.__setattr__(self, "in_service_area",
                           service_area.contains(self.latitude, self.longitude))
        return self


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
def _validated_password(value: str) -> str:
    """Reject a password bcrypt cannot hash, at the boundary, in BYTES.

    A `max_length` on the field would count CHARACTERS; bcrypt's 72 limit counts
    UTF-8 BYTES. 72 accented characters passed a character check and then raised
    inside bcrypt, which surfaced as an unhandled 500 on the public,
    unauthenticated POST /api/v1/auth/register. Raising here instead makes it a
    422 that names the offending field.
    """
    from api import security

    problem = security.password_length_problem(value)
    if problem:
        raise ValueError(problem)
    return value


# `max_length` below is a published, client-usable hint only. It is NOT the real
# limit: JSON Schema cannot express "72 UTF-8 bytes", and 72 characters is always
# >= 72 bytes' worth, so it can only ever reject input the byte check rejects too.
# The authoritative check is _validated_password.
PASSWORD_MAX_CHARS_HINT = 72
_PASSWORD_BYTE_LIMIT_NOTE = (
    "Capped at 72 UTF-8 BYTES (bcrypt's limit), not 72 characters: accented and "
    "non-Latin characters cost more than one byte each, so a 40-character "
    "password can still be too long.")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, examples=["budi"])
    password: str = Field(..., min_length=8, max_length=PASSWORD_MAX_CHARS_HINT,
                          examples=["s3cret123"], description=_PASSWORD_BYTE_LIMIT_NOTE)
    email: Optional[str] = Field(None, examples=["budi@example.com"])
    full_name: Optional[str] = Field(None, examples=["Budi Santoso"])
    ev_model_id: Optional[str] = Field(None, examples=["hyundai-ioniq-5"])
    main_connector_type: Optional[str] = Field(None, examples=["CCS2"])
    location_consent: bool = False

    _check_password = field_validator("password")(_validated_password)


class LoginRequest(BaseModel):
    username: str
    # DELIBERATELY no length cap. Accounts created before the byte cap existed
    # may hold a hash of only the first 72 bytes of a longer password (older
    # bcrypt truncated silently); refusing the full password here would lock
    # those users out for good. security.verify_password truncates instead, so
    # such a login still succeeds and can never 500.
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., examples=["budi@example.com"])


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., examples=["k3y-from-the-emailed-link"])
    # bcrypt only uses the first 72 BYTES. max_length is kept as the published
    # client hint it always was; the real cap is the byte check below.
    new_password: str = Field(..., min_length=8, max_length=PASSWORD_MAX_CHARS_HINT,
                              examples=["n3ws3cret123"], description=_PASSWORD_BYTE_LIMIT_NOTE)

    _check_new_password = field_validator("new_password")(_validated_password)


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


# ---- help desk / support ----------------------------------------------------
# Bounds are the point of these constants: this endpoint is reachable without a
# token and every accepted request costs one outbound email. Big enough for a
# real bug report with a pasted stack trace, small enough that nobody can push a
# megabyte through our SMTP relay one POST at a time.
SUPPORT_SUBJECT_MAX_CHARS = 200
SUPPORT_MESSAGE_MAX_CHARS = 5000
SUPPORT_REPLY_TO_MAX_CHARS = 254   # RFC 5321 cap on a forward-path address


def _validated_email_header_value(value: Optional[str]) -> Optional[str]:
    """Reject a value that would be smuggled into an email header.

    `subject` and `reply_to` are written into MIME headers. A carriage return or
    newline in either is the classic SMTP header-injection primitive: it ends the
    header and starts one the caller chose (Bcc:, say). Rejecting at the boundary
    is cheaper and clearer than sanitising downstream, and api/mailer.py refuses
    the same thing again as a belt.
    """
    if value is None:
        return None
    if any(ch in value for ch in ("\r", "\n")):
        raise ValueError("line breaks are not allowed here")
    return value


def _validated_reply_to(value: Optional[str]) -> Optional[str]:
    """A usable reply address, or None. Deliberately not a full RFC 5322 parser.

    The address is only ever handed back to a human in the support inbox, so the
    check that matters is the header-injection one above; beyond that we only
    insist it looks like an address at all, so an obvious typo is caught while
    the request is still in front of the user.
    """
    value = _validated_email_header_value(value)
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    local, _, domain = trimmed.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("enter a valid email address")
    return trimmed


class SupportTicketRequest(BaseModel):
    """One Help Desk message, delivered to the support inbox by email."""
    subject: str = Field(..., min_length=3, max_length=SUPPORT_SUBJECT_MAX_CHARS,
                         description="What the ticket is about. Becomes the email subject line.",
                         examples=["Charging session stuck at 'starting'"])
    message: str = Field(..., min_length=10, max_length=SUPPORT_MESSAGE_MAX_CHARS,
                         description="The problem in full: what you did, what happened, "
                                     "and any station or session id involved.",
                         examples=["I started a session at pln_spklu-1 twenty minutes ago and "
                                   "the app still shows 'starting'. My wallet was debited."])
    reply_to: Optional[str] = Field(None, max_length=SUPPORT_REPLY_TO_MAX_CHARS,
                                    description="Where support should reply. Optional, but "
                                                "without it an anonymous ticket cannot be "
                                                "answered at all.",
                                    examples=["budi@example.com"])

    _check_subject = field_validator("subject")(_validated_email_header_value)
    _check_reply_to = field_validator("reply_to")(_validated_reply_to)


class SupportTicketResponse(BaseModel):
    """Confirmation that the ticket was handed to the mail server."""
    ticket_id: str = Field(..., description="Quote this when following up.",
                           examples=["4f9c2b1e7a0d4c8e"])
    message: str = Field(..., examples=["Your message has been sent to the EVFlow help desk."])


# ---- Epic 2.0 Route Planning & Geocoding Schemas ----------------------------
class RouteLocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.2088])
    longitude: float = Field(..., ge=-180, le=180, examples=[106.8456])
    label: Optional[str] = Field(None, examples=["Current Location"])


class RoutePreferencesInput(BaseModel):
    route_type: str = Field(
        ROUTE_TYPE_FASTEST,
        description="'fastest' balances detour against charging power; 'shortest' weights "
                    "detour distance harder. Applied to stop ranking and echoed in "
                    "assumptions.route_type (AC 2.2.4). Kept a free-form string rather than "
                    "an enum: this field shipped untyped, the web client declares it "
                    "`route_type?: string`, and turning an already-accepted request into a "
                    "422 would break it. An unrecognised value falls back to 'fastest' and "
                    "the value ACTUALLY applied comes back in assumptions.route_type, so a "
                    "client can detect the fallback without guessing.",
        examples=list(SUPPORTED_ROUTE_TYPES))
    maximum_detour_km: float = Field(8.0, ge=1.0, le=50.0, examples=[8.0])
    prefer_fast_charging: bool = Field(
        True,
        description="True rewards high available charging power when ranking stops; False "
                    "ranks on detour distance alone (AC 2.2.4).")

    @field_validator("route_type", mode="before")
    @classmethod
    def _known_route_type(cls, v: Any) -> str:
        """Accept the known values; degrade anything else to the default."""
        if not isinstance(v, str):
            return ROUTE_TYPE_FASTEST
        normalised = v.strip().lower()
        return normalised if normalised in SUPPORTED_ROUTE_TYPES else ROUTE_TYPE_FASTEST


class ManualVehicleInput(BaseModel):
    """A range entered by hand, for a driver with no saved vehicle profile (AC 2.2.3)."""
    usable_range_km: float = Field(
        ..., gt=0, le=2000,
        description="Remaining/usable range at 100% battery, in km.", examples=[350.0])
    battery_kwh: Optional[float] = Field(
        None, gt=0, le=500,
        description="Usable pack size. When omitted, one consistent with the entered range "
                    "and the configured default efficiency is assumed.", examples=[58.0])
    name: Optional[str] = Field(None, examples=["My EV"])
    max_dc_charge_kw: Optional[float] = Field(None, gt=0, le=1000, examples=[150.0])
    connector_type: Optional[str] = Field(None, examples=["CCS2"])


def _require_service_area(point: "RouteLocationInput") -> "RouteLocationInput":
    """AC 2.2.1 / AC 2.2.2: reject a point outside the configured route service area.

    Raised as a Pydantic ValueError so FastAPI answers 422 with
    ``detail[].loc == ["body", "origin"|"destination"|"current_position"]`` and
    the endpoint body never runs -- no route is generated.
    """
    if not service_area.contains(point.latitude, point.longitude):
        raise ValueError(service_area.rejection_message())
    return point


class RoutePlanRequest(BaseModel):
    origin: RouteLocationInput
    destination: RouteLocationInput
    current_soc_pct: float = Field(..., ge=0, le=100, examples=[72.0])
    ev_model_id: Optional[str] = Field(
        None,
        description="Plan for this catalogue vehicle instead of the saved profile (AC 2.2.3). "
                    "404 when unknown. Overridden by `vehicle`.",
        examples=["hyundai-ioniq-5"])
    vehicle: Optional[ManualVehicleInput] = Field(
        None,
        description="Manually entered vehicle range (AC 2.2.3). Takes precedence over "
                    "ev_model_id and over the saved profile, so a driver with no profile "
                    "can still simulate a trip.")
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

    @field_validator("origin", "destination")
    @classmethod
    def _within_service_area(cls, v: RouteLocationInput) -> RouteLocationInput:
        return _require_service_area(v)


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
    computed_at: Optional[datetime] = Field(
        None,
        description="Server clock when this plan was computed (UTC). The reference point for "
                    "estimated_arrival_at, so two clients reading the same plan agree (AC 2.4.1).")
    estimated_arrival_at: Optional[datetime] = Field(
        None,
        description="Estimated arrival TIME (UTC) = computed_at + duration_minutes, charging "
                    "time included (AC 2.4.1).")

    @field_serializer("computed_at", "estimated_arrival_at")
    def serialize_route_time(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None


class RouteStep(BaseModel):
    """One turn-by-turn instruction (AC 2.4.1 'next instruction').

    Every field has a default so a provider that omits one still serialises, and
    so the legacy untyped `steps: []` payload keeps validating unchanged.
    """
    instruction: str = Field("", examples=["turn slight left"])
    name: str = Field("", description="Road name, may be empty.",
                      examples=["Jalan Medan Merdeka Utara"])
    distance_m: float = Field(0.0, examples=[782.5])
    duration_s: float = Field(0.0, examples=[45.6])
    location: list[float] = Field(default_factory=list,
                                  description="[longitude, latitude] where the manoeuvre starts.")
    leg_index: int = Field(
        0,
        description="Which leg this step belongs to. 0 is origin -> first waypoint, so the "
                    "charging stop is the boundary between leg 0 and leg 1.", examples=[0])


class RoutePlanGeometryAndSteps(BaseModel):
    type: str = Field("Feature", examples=["Feature"])
    geometry: RouteGeometry
    steps: list[RouteStep] = Field(default_factory=list)


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
    detour_budget_km: Optional[float] = Field(
        None, description="The maximum_detour_km this stop was ranked against.", examples=[8.0])
    detour_within_budget: bool = Field(
        True,
        description="False when the ROAD detour finally reported exceeds detour_budget_km. "
                    "Only possible when nothing inside the budget was viable, or for a "
                    "driver-forced waypoint (AC 2.2.4).")


class ServiceAreaSummary(BaseModel):
    """The route service area the request was validated against (AC 2.2.1)."""
    name: str = Field(..., examples=["Indonesia (national SPKLU coverage)"])
    south: float = Field(..., examples=[-11.2])
    west: float = Field(..., examples=[94.6])
    north: float = Field(..., examples=[6.3])
    east: float = Field(..., examples=[141.3])
    enforced: bool = Field(True)


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
    service_area: Optional[ServiceAreaSummary] = Field(
        None, description="The area origin/destination were validated against (AC 2.2.1).")
    route_type: Optional[str] = Field(
        None, description="The route_type preference actually applied.", examples=["fastest"])
    prefer_fast_charging: Optional[bool] = Field(
        None, description="The prefer_fast_charging preference actually applied (AC 2.2.4).")
    maximum_detour_km: Optional[float] = Field(
        None, description="The detour budget actually applied.", examples=[8.0])
    rank_detour_weight: Optional[float] = Field(
        None, description="Weight the applied preferences gave to detour km.", examples=[1.0])
    rank_power_weight_km_per_kw: Optional[float] = Field(
        None, description="Weight the applied preferences gave to available charging power.",
        examples=[0.25])
    routing_provider: Optional[str] = Field(
        None, description="Which provider produced the geometry: 'osrm', 'local_dijkstra' or "
                          "'haversine_fallback' (AC 2.4.1).", examples=["osrm"])
    turn_by_turn_available: bool = Field(
        False,
        description="False when the routing provider degraded and route.steps is a single "
                    "synthetic placeholder rather than real navigation instructions (AC 2.4.1).")


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
    suggested_actions: list[str] = Field(
        default_factory=list,
        description="Machine-readable remedies the client can render as buttons and localise, "
                    "instead of string-matching `message`. Vocabulary: "
                    "'choose_another_route', 'adjust_preferences', 'charge_before_departure' "
                    "(AC 2.2.6), 'return_to_service_area' (advisory only).",
        examples=[["choose_another_route", "adjust_preferences", "charge_before_departure"]])


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
    current_soc_pct: Optional[float] = Field(
        None, ge=0, le=100,
        description="Legacy caller-supplied current SoC. Navigation clients should send "
                    "navigation_start_soc_pct and cumulative_distance_travelled_km instead.",
        examples=[26.0])
    navigation_start_soc_pct: Optional[float] = Field(None, ge=0, le=100, examples=[72.0])
    cumulative_distance_travelled_km: float = Field(0.0, ge=0, examples=[12.4])
    measured_current_soc_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Optional trusted vehicle telemetry reading.")
    minimum_arrival_soc_pct: Optional[float] = Field(None, ge=0, le=50, examples=[20.0])
    route_plan_id: Optional[str] = Field(None, description="Plan being driven, echoed back.")
    maximum_detour_km: float = Field(15.0, ge=1.0, le=50.0)
    max_candidate_stops: int = Field(5, ge=1, le=25)
    active_waypoint_station_id: Optional[str] = Field(
        None, description="Accepted charging stop that the remaining road route must preserve.")
    ev_model_id: Optional[str] = Field(
        None, description="Catalogue vehicle to evaluate against instead of the saved profile "
                          "(AC 2.2.3).", examples=["hyundai-ioniq-5"])
    vehicle: Optional[ManualVehicleInput] = Field(
        None, description="Manually entered vehicle range (AC 2.2.3). Takes precedence over "
                          "ev_model_id and over the saved profile.")

    # NOTE: deliberately NO service-area validator here, unlike RoutePlanRequest.
    # The planning-time boundary (AC 2.2.2) must not become a mid-journey kill
    # switch: AC 2.1.1 and AC 2.4.2 exist precisely to keep warning a driver who
    # is already travelling, and a driver on an active route may legitimately be
    # outside the box. The condition is reported on the RESPONSE instead --
    # out_of_service_area / out_of_service_area_fields / advisories.


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
    estimated_current_soc_pct: float = Field(..., examples=[61.2])
    current_soc_source: str = Field(..., examples=["distance_estimate", "vehicle_telemetry"])
    remaining_energy_kwh: float = Field(..., examples=[35.5])
    energy_model_version: str = Field("spec-v2")
    energy_assumptions: dict = Field(default_factory=dict)
    raw_projected_arrival_soc_pct: float = Field(..., examples=[8.2])
    reserve_soc_pct: float = Field(..., examples=[20.0])
    effective_reserve_km: Optional[float] = Field(None, examples=[42.0])
    distance_basis: str = Field("straight_line", examples=["road", "straight_line"])
    vehicle: VehicleSummary
    candidate_stops: list[RecommendedStop] = Field(
        default_factory=list,
        description="Nearby stations the driver could add as a stop, best first.")
    computed_at: Optional[datetime] = Field(
        None, description="Server clock when this evaluation ran (UTC) (AC 2.4.1).")
    estimated_arrival_at: Optional[datetime] = Field(
        None, description="Estimated arrival TIME (UTC) = computed_at + "
                          "remaining_duration_minutes (AC 2.4.1).")
    service_area: Optional[ServiceAreaSummary] = Field(
        None, description="The configured route service area this evaluation was measured "
                          "against (AC 2.2.1).")
    out_of_service_area: bool = Field(
        False,
        description="True when current_position and/or destination lies outside the "
                    "configured route service area. ADVISORY ONLY: unlike "
                    "POST /api/v1/route-plans, this endpoint keeps evaluating, because a "
                    "driver already on an active route must keep receiving battery warnings "
                    "(AC 2.1.1 / AC 2.4.2). Station coverage and ETA are unreliable while "
                    "this is true.")
    out_of_service_area_fields: list[str] = Field(
        default_factory=list,
        description="Which request fields fell outside: any of 'current_position', "
                    "'destination'. Empty when out_of_service_area is false.",
        examples=[["current_position"]])
    advisories: list[RouteWarning] = Field(
        default_factory=list,
        description="Non-blocking notices that do not displace `warning` (which stays "
                    "reserved for the battery projection). Carries the "
                    "'out_of_service_area' notice and the 'routing_degraded' notice "
                    "(road routing was unavailable, so distance/ETA are a straight-line "
                    "approximation -- see assumptions.routing_provider). Both can be "
                    "present alongside a triggered battery `warning`.")
    assumptions: RoutePlanAssumptions = Field(
        default_factory=RoutePlanAssumptions,
        description="Same shape POST /api/v1/route-plans returns, so a client can read "
                    "routing_provider / turn_by_turn_available / distance_basis the same "
                    "way on both endpoints. Additive: no pre-existing field changed.")

    @field_serializer("computed_at", "estimated_arrival_at")
    def serialize_route_time(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None


DISTANCE_FROM_ORIGIN = "origin"
DISTANCE_FROM_REFERENCE_POINT = "reference_point"


class GeocodingItem(BaseModel):
    id: str = Field(..., examples=["place-1"])
    label: str = Field(..., examples=["Bandung"])
    subtitle: str = Field(..., examples=["West Java · via Tol Cipularang"])
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.9175])
    longitude: float = Field(..., ge=-180, le=180, examples=[107.6191])
    distance_km: Optional[float] = Field(
        None,
        description="Distance from the caller's OWN position, and null when the caller sent "
                    "none. This meaning is deliberately unchanged: a client that renders it as "
                    "'distance from you' stays correct, and never silently shows a distance "
                    "measured from somewhere the user has never been.",
        examples=[148.0])
    distance_from_reference_km: Optional[float] = Field(
        None,
        description="AC 2.2.7 estimate for the no-GPS-fix case, measured from the configured "
                    "reference point named in distance_reference_label. Populated only when "
                    "distance_km is null, so a client must label it ('~X km from Jakarta') "
                    "rather than present it as the user's own distance.",
        examples=[148.0])
    distance_from: str = Field(
        DISTANCE_FROM_ORIGIN,
        description="Which of the two distance fields is populated: 'origin' -> distance_km, "
                    "'reference_point' -> distance_from_reference_km (AC 2.2.7).",
        examples=["origin", "reference_point"])
    distance_reference_label: Optional[str] = Field(
        None,
        description="Name of the reference point when distance_from == 'reference_point', so "
                    "the picker can say '~X km from Jakarta'.", examples=["Jakarta"])

    @model_validator(mode="after")
    def _reference_distance_never_poses_as_the_users_own(self):
        """Keep distance_km meaning exactly what it meant before AC 2.2.7 landed.

        The fallback estimate is real and useful, but it is measured from a fixed
        reference point, not from the driver. Serving it in distance_km would make
        an unmodified client display a confident, wrong 'distance from you'. So it
        moves to its own field and distance_km goes back to null.
        """
        if self.distance_from == DISTANCE_FROM_REFERENCE_POINT and self.distance_km is not None:
            self.distance_from_reference_km = self.distance_km
            self.distance_km = None
        return self
    type: str = Field(..., description="'place' or 'station'", examples=["place"])
    station: Optional[Station] = None
    attribution: str = Field("OpenStreetMap contributors, PLN SPKLU")
    in_service_area: bool = Field(
        True,
        description="False when picking this suggestion as an origin or destination would be "
                    "REJECTED by POST /api/v1/route-plans with a 422 (AC 2.2.2). The picker "
                    "must label or disable such an entry rather than offering it as routable; "
                    "pass ?in_service_area_only=true to have the server drop them instead. "
                    "Computed from the suggestion's own coordinates against the same "
                    "configured area the planner uses, so the two can never disagree.")

    @model_validator(mode="after")
    def _set_in_service_area(self) -> "GeocodingItem":
        object.__setattr__(self, "in_service_area",
                           service_area.contains(self.latitude, self.longitude))
        return self


class GeocodingSearchResponse(BaseModel):
    query: str
    items: list[GeocodingItem]
    distance_from: str = Field(
        DISTANCE_FROM_ORIGIN,
        description="Applies to every item: 'origin' or 'reference_point' (AC 2.2.7).",
        examples=["origin", "reference_point"])
    distance_reference_label: Optional[str] = Field(None, examples=["Jakarta"])
    service_area: Optional[ServiceAreaSummary] = Field(
        None,
        description="The configured route service area every item's `in_service_area` was "
                    "computed against -- the SAME area POST /api/v1/route-plans enforces, so "
                    "the picker can explain why a suggestion is not routable (AC 2.2.1).")
    filtered_out_of_service_area: int = Field(
        0,
        description="How many otherwise-matching suggestions were dropped because "
                    "in_service_area_only=true. Always 0 when the flag is off.",
        examples=[0])


# <Aidil> 2026-07-29
class StationConnectorStatus(BaseModel):
    """Live counts for one group of interchangeable connectors at a station.

    A group is one (type, speed_tier, power_kw) combination, so power_kw is part of the
    group's identity: two groups can share type and speed_tier and differ only in power.
    """
    type: str = Field(..., description="Connector standard/type.", examples=["CCS2"])
    speed_tier: Optional[str] = Field(
        None, description="Connector speed tier: slow / medium / fast / ultra_fast.", examples=["fast"])
    power_kw: Optional[float] = Field(
        None,
        description="Rated power (kW) every connector in this group delivers. Two groups with the same "
                    "type and speed_tier are told apart by this value, so show it. Null when the source "
                    "data never reported a power for these connectors.",
        examples=[50.0])
    available: int = Field(
        ..., description="Connectors in this group free to plug into right now.", examples=[2])
    total: int = Field(
        ...,
        description="Connectors in this group, every status included. "
                    "Always equals available + in_use + out_of_service.",
        examples=[5])
    in_use: int = Field(
        ..., description="Connectors in this group busy with an active charging session.", examples=[2])
    out_of_service: int = Field(
        ...,
        description="Connectors in this group that are broken or offline. Present them as unusable, never "
                    "as busy: they are not going to free up, so do not fold them into an occupied count "
                    "derived from total - available.",
        examples=[1])
    waiting_time: Optional[float] = Field(
        ...,
        description="Minutes until a connector in this group is expected to free up. 0 = at least one is "
                    "free right now. A positive number = none free, and this is the estimate from the "
                    "active session finishing soonest. Null = UNKNOWN: none free and no estimate can be "
                    "computed (no active session on record, missing power, ...). Null must never be "
                    "rendered as '~0 minutes' -- say the wait is unknown.",
        examples=[0, 12.4, None])

class StationStatusResponse(BaseModel):
    station_id: str = Field(..., description="ID of the station.", examples=["pln_spklu-1"])
    station_status: int = Field(
        ...,
        description="Whole-station availability flag: 1 = at least one connector is free to plug into "
                    "right now, 0 = none is (all connectors in use or out of service, or the station has "
                    "no connectors on record).",
        examples=[1])
    available: int = Field(
        ..., description="Connectors free to plug into right now across the whole station.", examples=[3])
    total: int = Field(
        ...,
        description="Connectors at the station, every status included. "
                    "Always equals available + in_use + out_of_service.",
        examples=[8])
    in_use: int = Field(
        ..., description="Connectors at the station busy with an active charging session.", examples=[4])
    out_of_service: int = Field(
        ...,
        description="Connectors at the station that are broken or offline. Exposed so the client stops "
                    "inferring occupancy as total - available, which reported a broken charger as busy.",
        examples=[1])
    waiting_time: Optional[float] = Field(
        ...,
        description="Minutes until any connector at the station is expected to free up. 0 = at least one "
                    "is free right now. A positive number = none free, and this is the soonest estimate "
                    "across the station. Null = UNKNOWN: none free and no estimate can be computed. Null "
                    "must never be rendered as '~0 minutes' -- say the wait is unknown.",
        examples=[0, 12.4, None])
    connectors: list[StationConnectorStatus] = Field(
        ...,
        description="Per-group breakdown of the same counts, one entry per "
                    "(type, speed_tier, power_kw) combination.")

class StationOccupancyHour(BaseModel):
    hour_of_day: int = Field(..., description="Hour of day (0 to 23).", examples=[14])
    avg_occupancy: float = Field(
        ..., description="Average share of the station's connectors busy in this hour, percent (0-100).",
        examples=[45.5])
    occupancy_level: str = Field(
        ...,
        description="How busy this hour is, classified server-side from avg_occupancy at the 20 / 50 / 80 "
                    "percent thresholds: 'LOW', 'MODERATE', 'BUSY', 'PEAK'. Display this rather than "
                    "re-deriving the buckets, so client labels cannot drift from the backend's.",
        examples=["MODERATE"])

class StationOccupancyDay(BaseModel):
    day_of_week: int = Field(..., description="Day of week (1=Monday, ..., 7=Sunday).", examples=[1])
    day_name: str = Field(..., description="Day name.", examples=["Monday"])
    hours: list[StationOccupancyHour]

class StationOccupancyResponse(BaseModel):
    station_id: str = Field(..., description="ID of the station.", examples=["pln_spklu-6"])
    days: list[StationOccupancyDay]
# </Aidil> 2026-07-29

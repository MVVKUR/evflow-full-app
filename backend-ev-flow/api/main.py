"""FastAPI app exposing combined Jakarta/Indonesia EV charging-station data.

Run:  uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs   (Swagger UI)
Spec: http://localhost:8000/openapi.json
"""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import __version__, evmodels
from . import connectors as conn
from . import stations_repo as repo
from . import xendit
from . import wallet_repo as wallet
from . import pricing
from . import charging_repo
from . import security
from . import google_oauth
from . import users_repo
from . import mailer
from . import password_reset_repo
from .models import (
    EVModel, EVModelList, GeoJSONFeatureCollection, Health, NameCount,
    NearestStationRoute, Route, SourceCount, SpeedTier, Station,
    StationList, Stats,
    Topup, TopupCreated, TopupRequest, WalletBalance,
    ChargingQuote, ChargingQuoteRequest, ChargingSession, StartSessionRequest, SettleRequest,
    ForgotPasswordRequest, ForgotPasswordResponse, LoginRequest, ProfileUpdate, RegisterRequest,
    ResetPasswordRequest, ResetPasswordResponse, TokenResponse, UserPublic,
)


TAGS = [
    {"name": "stations", "description": "Query and fetch charging stations."},
    {"name": "geo", "description": "GeoJSON output for direct map rendering."},
    {"name": "meta", "description": "Stats and filter look-ups (sources, provinces, cities)."},
    {"name": "ev-models", "description": "EV model catalogue (battery / range) for range-aware routing."},
    {"name": "wallet", "description": "Wallet balance + Xendit top-up (payment)."},
    {"name": "charging", "description": "Charging sessions: real wallet deposit debit + settlement refund."},
    {"name": "auth", "description": "Accounts + authentication (username/password + Google)."},
    {"name": "system", "description": "Health/diagnostics."},
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Jakarta EV Charging Stations API",
    version=__version__,
    openapi_tags=TAGS,
    license_info={"name": "Data: PLN, OCM (CC-BY-SA), OSM (ODbL)"},
    lifespan=lifespan,
)

# Frontend calls this from a browser, so allow CORS. Auth/write endpoints are now live, so set
# CORS_ALLOW_ORIGINS (comma-separated) to the frontend origin(s) in production; it defaults to "*"
# (open) only for local/dev convenience.
_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
_allow_origins = ["*"] if _origins_env in ("", "*") else [o.strip() for o in _origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------- helpers
def _row_to_station(row: dict, distance_km: Optional[float] = None) -> Station:
    return Station(
        id=row["id"], name=row.get("name"), sources=row.get("sources") or [],
        latitude=float(row["latitude"]), longitude=float(row["longitude"]),
        address=row.get("address"), province=row.get("province"), city=row.get("city"),
        operator=row.get("operator"), power_kw=row.get("power_kw"),
        charge_type=row.get("charge_type"), speed_tier=row.get("speed_tier"),
        connectors=row.get("connectors") or [], connector_types=row.get("connector_types") or [],
        connector_inferred=row.get("connector_inferred"),
        status=row.get("status"), date_verified=row.get("date_verified"),
        distance_km=(round(distance_km, 3) if distance_km is not None else
                     (round(row["distance_km"], 3) if row.get("distance_km") is not None else None)),
    )


def _bbox(bbox: Optional[str]):
    if not bbox:
        return None
    try:
        mnlon, mnlat, mxlon, mxlat = (float(x) for x in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be 'minLon,minLat,maxLon,maxLat'")
    return (mnlon, mnlat, mxlon, mxlat)


# ----------------------------------------------------------------------------- endpoints
@app.get("/health", response_model=Health, tags=["system"], summary="Liveness + dataset size")
def health() -> Health:
    try:
        n = repo.count()
    except Exception:
        n = 0
    return Health(status="ok", stations_loaded=n, version=__version__)


@app.get("/api/v1/stations", response_model=StationList, tags=["stations"],
         summary="List / filter charging stations")
def list_stations(
    province: Optional[str] = Query(None, description="Exact province match (case-insensitive), e.g. 'DKI Jakarta'."),
    city: Optional[str] = Query(None, description="City/kabupaten substring match."),
    q: Optional[str] = Query(None, description="Case-insensitive search on station name."),
    min_power: Optional[float] = Query(None, ge=0, description="Min power (kW)."),
    max_power: Optional[float] = Query(None, ge=0, description="Max power (kW)."),
    connector_type: Optional[list[str]] = Query(None, description="Connector standard(s); repeatable for multi-select (OR), e.g. ?connector_type=CCS2&connector_type=AC%20Type%202 (see /api/v1/connectors)."),
    speed_tier: Optional[list[str]] = Query(None, description="Speed tier(s); repeatable for multi-select (OR): slow / medium / fast / ultra_fast (see /api/v1/speed-tiers)."),
    bbox: Optional[str] = Query(None, description="Bounding box 'minLon,minLat,maxLon,maxLat'.",
                                examples=["106.55,-6.65,107.10,-5.95"]),
    limit: int = Query(100, ge=1, le=1000, description="Page size."),
    offset: int = Query(0, ge=0, description="Page offset."),
) -> StationList:
    filters = {"province": province, "city": city, "q": q,
               "min_power": min_power, "max_power": max_power,
               "connector_type": connector_type, "speed_tier": speed_tier, "bbox": _bbox(bbox)}
    total, rows = repo.list_stations(filters, limit, offset)
    return StationList(total=total, limit=limit, offset=offset,
                       items=[_row_to_station(r) for r in rows])


@app.get("/api/v1/stations/nearby", response_model=list[Station], tags=["stations"],
         summary="Nearest stations to a point ('near me')")
def nearby(lat: Optional[float] = Query(None, ge=-90, le=90, description="Origin latitude. Omit (with lon) if location is denied."),
           lon: Optional[float] = Query(None, ge=-180, le=180, description="Origin longitude. Omit (with lat) if location is denied."),
           radius_km: float = Query(5.0, gt=0, le=500), limit: int = Query(20, ge=1, le=200),
           connector_type: Optional[list[str]] = Query(None),
           speed_tier: Optional[list[str]] = Query(None),
           min_power: Optional[float] = Query(None, ge=0),
           max_power: Optional[float] = Query(None, ge=0)) -> list[Station]:
    filters = {"connector_type": connector_type, "speed_tier": speed_tier,
               "min_power": min_power, "max_power": max_power}
    if lat is not None and lon is not None:
        rows = repo.nearby(lat, lon, radius_km, limit, filters)      # sorted by distance
    elif lat is None and lon is None:
        _, rows = repo.list_stations(filters, limit, 0)              # no location: filter only
    else:
        raise HTTPException(422, "provide both lat and lon, or neither")
    return [_row_to_station(r) for r in rows]


@app.get("/api/v1/stations/{station_id}", response_model=Station, tags=["stations"],
         summary="Fetch one station by id", responses={404: {"description": "Not found"}})
def get_station(station_id: str) -> Station:
    row = repo.get_station(station_id)
    if row is None:
        raise HTTPException(404, f"station '{station_id}' not found")
    return _row_to_station(row)


@app.get("/api/v1/stations.geojson", response_model=GeoJSONFeatureCollection, tags=["geo"],
         summary="Stations as a GeoJSON FeatureCollection")
def stations_geojson(
    province: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    min_power: Optional[float] = Query(None, ge=0),
    max_power: Optional[float] = Query(None, ge=0),
    connector_type: Optional[list[str]] = Query(None),
    speed_tier: Optional[list[str]] = Query(None),
    bbox: Optional[str] = Query(None), limit: int = Query(5000, ge=1, le=20000),
) -> GeoJSONFeatureCollection:
    filters = {"province": province, "city": city, "q": q,
               "min_power": min_power, "max_power": max_power,
               "connector_type": connector_type, "speed_tier": speed_tier, "bbox": _bbox(bbox)}
    _, rows = repo.list_stations(filters, limit, 0)
    features = []
    for r in rows:
        st = _row_to_station(r)
        props = st.model_dump(exclude={"latitude", "longitude", "distance_km"})
        features.append({"type": "Feature",
                         "geometry": {"type": "Point", "coordinates": [float(r["longitude"]), float(r["latitude"])]},
                         "properties": props})
    return GeoJSONFeatureCollection(type="FeatureCollection", features=features)


@app.get("/api/v1/route", response_model=Route, tags=["geo"],
         summary="Shortest driving path (Dijkstra) to a point or station",
         responses={404: {"description": "Station not found / no drivable route"},
                    422: {"description": "Destination not provided"},
                    503: {"description": "Road graph unavailable (not built yet)"}})
def route(
    lat: Optional[float] = Query(None, ge=-90, le=90, description="Origin latitude (needed to route).", examples=[-6.2088]),
    lon: Optional[float] = Query(None, ge=-180, le=180, description="Origin longitude (needed to route).", examples=[106.8456]),
    station_id: Optional[str] = Query(None, description="Destination = this station's coordinates."),
    dest_lat: Optional[float] = Query(None, ge=-90, le=90, description="Destination latitude (if no station_id)."),
    dest_lon: Optional[float] = Query(None, ge=-180, le=180, description="Destination longitude (if no station_id)."),
    weight: str = Query("length", pattern="^(length|travel_time)$",
                        description="Minimise 'length' (shortest) or 'travel_time' (fastest)."),
) -> Route:
    if lat is None or lon is None:
        raise HTTPException(422, "origin 'lat' and 'lon' are required")
    if station_id:
        row = repo.get_station(station_id)
        if row is None:
            raise HTTPException(404, f"station '{station_id}' not found")
        dest_lat, dest_lon = float(row["latitude"]), float(row["longitude"])
    elif dest_lat is None or dest_lon is None:
        raise HTTPException(422, "provide either 'station_id' or both 'dest_lat' and 'dest_lon'")

    from . import routing  # deferred: pulls in networkx/the road graph only when routing is used
    try:
        result = routing.shortest_path(lat, lon, dest_lat, dest_lon, weight=weight)
    except routing.GraphUnavailable as e:
        raise HTTPException(503, f"routing unavailable: {e}")
    if result is None:
        raise HTTPException(404, "no drivable route found between the two points")
    if station_id:
        result["destination"]["station_id"] = station_id
    return result


@app.get("/api/v1/route/nearest-station", response_model=NearestStationRoute, tags=["geo"],
         summary="Nearest charging station reachable by road (Dijkstra) + route to it",
         responses={404: {"description": "No stations loaded / none reachable by road"},
                    503: {"description": "Road graph unavailable (not built yet)"}})
def nearest_station(
    lat: Optional[float] = Query(None, ge=-90, le=90, description="Origin latitude (needed to route).", examples=[-6.2088]),
    lon: Optional[float] = Query(None, ge=-180, le=180, description="Origin longitude (needed to route).", examples=[106.8456]),
    weight: str = Query("length", pattern="^(length|travel_time)$",
                        description="Rank by 'length' (nearest) or 'travel_time' (quickest)."),
    max_range_km: Optional[float] = Query(
        None, gt=0,
        description="EV remaining range (km). Flags whether the nearest charger is within reach (Route & Battery)."),
    ev_model_id: Optional[str] = Query(
        None, description="EV model id (see /api/v1/ev-models). With current_soc the backend derives the "
                          "remaining range, overriding max_range_km."),
    current_soc: Optional[float] = Query(
        None, ge=0, le=100, description="Current state of charge (%); required when ev_model_id is given."),
) -> NearestStationRoute:
    if lat is None or lon is None:
        raise HTTPException(422, "origin 'lat' and 'lon' are required")
    range_used = max_range_km
    if ev_model_id is not None:
        if current_soc is None:
            raise HTTPException(422, "current_soc is required when ev_model_id is given")
        model = evmodels.get(ev_model_id)
        if model is None:
            raise HTTPException(404, f"ev model '{ev_model_id}' not found")
        range_used = evmodels.remaining_range_km(model["range_km"], current_soc)
        if range_used is None:
            raise HTTPException(422, f"range unknown for ev model '{ev_model_id}'; pass max_range_km instead")

    coords = repo.routing_coords()
    if not coords:
        raise HTTPException(404, "no charging stations loaded")

    from . import routing  # deferred: pulls in networkx/the road graph only when routing is used
    try:
        result = routing.nearest_station_route(
            lat, lon,
            [c["id"] for c in coords], [c["latitude"] for c in coords], [c["longitude"] for c in coords],
            weight=weight, max_range_km=range_used)
    except routing.GraphUnavailable as e:
        raise HTTPException(503, f"routing unavailable: {e}")
    if result is None:
        raise HTTPException(404, "no charging station reachable by road from this point")
    row = repo.get_station(result["station_id"])
    if row is None:
        raise HTTPException(404, "nearest station resolved by routing but not found")
    return NearestStationRoute(
        station=_row_to_station(row, distance_km=result["route"]["distance_m"] / 1000.0),
        route=result["route"], candidates_considered=result["candidates_considered"],
        within_range=result["within_range"], range_used_km=range_used)


@app.get("/api/v1/ev-models", response_model=EVModelList, tags=["ev-models"],
         summary="List EV models (catalogue from the Kaggle Indonesia-EV-2026 dataset)")
def ev_models(
    q: Optional[str] = Query(None, description="Case-insensitive search on vehicle name."),
    limit: int = Query(100, ge=1, le=500, description="Page size."),
    offset: int = Query(0, ge=0, description="Page offset."),
) -> EVModelList:
    total, items = evmodels.search(q, limit, offset)
    return EVModelList(total=total, limit=limit, offset=offset, items=[EVModel(**m) for m in items])


@app.get("/api/v1/ev-models/{model_id}", response_model=EVModel, tags=["ev-models"],
         summary="Fetch one EV model by id", responses={404: {"description": "Not found"}})
def ev_model(model_id: str) -> EVModel:
    m = evmodels.get(model_id)
    if m is None:
        raise HTTPException(404, f"ev model '{model_id}' not found")
    return EVModel(**m)


@app.post("/api/v1/wallet/topup", response_model=TopupCreated, tags=["wallet"],
          summary="Create a Xendit invoice to top up the wallet",
          responses={502: {"description": "Payment provider error"}})
def wallet_topup(body: TopupRequest, user: dict = Depends(security.current_user)) -> TopupCreated:
    external_id = f"topup-{uuid.uuid4()}"
    topup_id = str(uuid.uuid4())
    # After paying (or cancelling) on the Xendit page the browser is sent back to the app.
    frontend = (os.getenv("FRONTEND_URL", "") or "").rstrip("/")
    success_url = f"{frontend}/ev-driver/wallet/topup/success?topup_id={topup_id}" if frontend else None
    failure_url = f"{frontend}/ev-driver/wallet/topup" if frontend else None
    try:
        inv = xendit.create_invoice(external_id, body.amount_idr, "EV-FLOW wallet top-up",
                                    success_redirect_url=success_url,
                                    failure_redirect_url=failure_url)
    except xendit.XenditError as e:
        raise HTTPException(502, f"payment provider error: {e}")
    row = wallet.create_topup(user["id"], body.amount_idr, external_id, inv["id"], inv["invoice_url"], topup_id=topup_id)
    return TopupCreated(**row)


@app.get("/api/v1/wallet/topups/{topup_id}", response_model=Topup, tags=["wallet"],
         summary="One top-up's status (refreshes from Xendit while pending)",
         responses={404: {"description": "Not found"}})
def wallet_topup_status(topup_id: str, user: dict = Depends(security.current_user)) -> Topup:
    """The frontend polls this after sending the user to the Xendit checkout.

    While the top-up is pending we ask Xendit for the invoice status directly, so the
    wallet is credited even when the webhook cannot reach this deployment (local dev).
    The credit path is the same idempotent one the webhook uses.
    """
    row = wallet.get_topup(topup_id, user["id"])
    if row is None:
        raise HTTPException(404, f"topup '{topup_id}' not found")
    if row["status"] == "pending" and row.get("xendit_invoice_id"):
        try:
            inv = xendit.get_invoice(row["xendit_invoice_id"])
        except xendit.XenditError:
            inv = None  # provider hiccup: report the stored status, poller will retry
        if inv and inv["status"] in ("PAID", "SETTLED"):
            wallet.mark_paid_and_credit(row["xendit_invoice_id"])
            row = wallet.get_topup(topup_id, user["id"])
    return Topup(**row)


@app.get("/api/v1/wallet", response_model=WalletBalance, tags=["wallet"], summary="Wallet balance")
def wallet_balance(user: dict = Depends(security.current_user)) -> WalletBalance:
    w = wallet.get_wallet(user["id"])
    return WalletBalance(balance_idr=w["balance_idr"], updated_at=w["updated_at"])


@app.post("/api/v1/webhooks/xendit", tags=["wallet"],
          summary="Xendit invoice webhook (credits the wallet on PAID)",
          responses={401: {"description": "Invalid callback token"}})
def xendit_webhook(payload: dict, x_callback_token: Optional[str] = Header(None)):
    expected = os.getenv("XENDIT_CALLBACK_TOKEN", "")
    if not expected or x_callback_token != expected:
        raise HTTPException(401, "invalid callback token")
    if payload.get("status") == "PAID" and payload.get("id"):
        wallet.mark_paid_and_credit(payload["id"])
    return {"ok": True}


@app.get("/api/v1/wallet/topups", response_model=list[Topup], tags=["wallet"],
         summary="Recent top-ups")
def wallet_topups(limit: int = Query(20, ge=1, le=100), user: dict = Depends(security.current_user)) -> list[Topup]:
    return [Topup(**t) for t in wallet.list_topups(user["id"], limit)]


# ----------------------------------------------------------------------------- charging sessions
@app.post("/api/v1/charging/quote", response_model=ChargingQuote, tags=["charging"],
          summary="Price a charging session before paying")
def charging_quote(body: ChargingQuoteRequest) -> ChargingQuote:
    return ChargingQuote(**pricing.quote(body.energy_kwh))


@app.post("/api/v1/charging/sessions", response_model=ChargingSession, status_code=201,
          tags=["charging"], summary="Start a session (debits the deposit from the wallet)",
          responses={402: {"description": "Insufficient wallet balance"}})
def start_charging_session(body: StartSessionRequest, user: dict = Depends(security.current_user)) -> ChargingSession:
    try:
        session = charging_repo.start_session(
            user_id=user["id"], station_id=body.station_id, energy_kwh=body.energy_kwh,
            station_name=body.station_name, connector_type=body.connector_type,
            power_kw=body.power_kw)
    except charging_repo.InsufficientBalance as e:
        raise HTTPException(402, str(e))
    return ChargingSession(**session)


@app.post("/api/v1/charging/sessions/{session_id}/settle", response_model=ChargingSession,
          tags=["charging"], summary="Settle a session (refunds unused kWh to the wallet)",
          responses={404: {"description": "Session not found"}})
def settle_charging_session(session_id: str, body: SettleRequest, user: dict = Depends(security.current_user)) -> ChargingSession:
    session = charging_repo.settle_session(user["id"], session_id, body.delivered_kwh)
    if session is None:
        raise HTTPException(404, f"charging session '{session_id}' not found")
    return ChargingSession(**session)


@app.get("/api/v1/charging/sessions/{session_id}", response_model=ChargingSession,
         tags=["charging"], summary="Session detail",
         responses={404: {"description": "Session not found"}})
def get_charging_session(session_id: str, user: dict = Depends(security.current_user)) -> ChargingSession:
    session = charging_repo.get_session(user["id"], session_id)
    if session is None:
        raise HTTPException(404, f"charging session '{session_id}' not found")
    return ChargingSession(**session)


@app.get("/api/v1/charging/sessions", response_model=list[ChargingSession],
         tags=["charging"], summary="Recent charging sessions")
def list_charging_sessions(limit: int = Query(20, ge=1, le=100), user: dict = Depends(security.current_user)) -> list[ChargingSession]:
    return [ChargingSession(**s) for s in charging_repo.list_sessions(user["id"], limit)]


# ----------------------------------------------------------------------------- auth endpoints
@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201, tags=["auth"],
          responses={409: {"description": "username taken"}})
def register(body: RegisterRequest) -> TokenResponse:
    if users_repo.get_by_username(body.username):
        raise HTTPException(409, "username already taken")
    completed = bool(body.ev_model_id and body.main_connector_type and body.location_consent)
    user = users_repo.create_user(
        username=body.username, password_hash=security.hash_password(body.password),
        email=body.email, full_name=body.full_name, ev_model_id=body.ev_model_id,
        main_connector_type=body.main_connector_type, location_consent=body.location_consent,
        profile_completed=completed)
    wallet.get_wallet(user["id"])
    return TokenResponse(access_token=security.create_access_token(user["id"]), user=UserPublic(**user))


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["auth"],
          responses={401: {"description": "bad credentials"}})
def login(body: LoginRequest) -> TokenResponse:
    user = users_repo.get_by_username_or_email(body.username.strip())
    if not user or not user.get("password_hash") or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "invalid username/email or password")
    return TokenResponse(access_token=security.create_access_token(user["id"]), user=UserPublic(**user))


def _send_reset_email(user_id: str, email: str) -> None:
    """Create a reset token and email the link. Runs in a background task so the
    request latency does not depend on whether the account exists (anti-enumeration)
    or on the SMTP round-trip. Errors are logged, never surfaced to the caller."""
    try:
        raw_token = password_reset_repo.create_token(user_id)
        frontend = (os.getenv("FRONTEND_URL", "") or "").rstrip("/")
        link = f"{frontend}/reset-password?token={raw_token}"
        ttl = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "60"))
        mailer.send_email(
            to=email,
            subject="Reset your EVFlow password",
            text_body=(
                "We received a request to reset your EVFlow password.\n\n"
                f"Open this link to choose a new password (valid for {ttl} minutes):\n{link}\n\n"
                "If you didn't request this, you can ignore this email."),
            html_body=(
                "<p>We received a request to reset your EVFlow password.</p>"
                f"<p><a href=\"{link}\">Click here to choose a new password</a> "
                f"(valid for {ttl} minutes).</p>"
                "<p>If you didn't request this, you can ignore this email.</p>"),
        )
    except Exception:
        logging.exception("failed to send password reset email")


@app.post("/api/v1/auth/forgot-password", response_model=ForgotPasswordResponse, tags=["auth"],
          responses={404: {"description": "no account with that email"},
                     400: {"description": "account has no password (Google sign-in)"}})
def forgot_password(body: ForgotPasswordRequest, background_tasks: BackgroundTasks) -> ForgotPasswordResponse:
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "enter a valid email address")
    # Honest, non-misleading responses: tell the user when no account matches so a
    # typo'd email isn't wrongly reported as sent. (Tradeoff: this reveals which
    # emails are registered — account enumeration — which the caller has accepted.)
    user = users_repo.get_by_email(email)
    if not user:
        raise HTTPException(404, "No account found with that email address.")
    if not user.get("password_hash"):
        raise HTTPException(400, "This account uses Google sign-in, so there is no password to reset.")
    # Token creation + SMTP send run after the response so the user isn't kept
    # waiting for the mail server.
    background_tasks.add_task(_send_reset_email, user["id"], email)
    return ForgotPasswordResponse(message="A password reset link has been sent to your email address.")


@app.post("/api/v1/auth/reset-password", response_model=ResetPasswordResponse, tags=["auth"],
          responses={400: {"description": "invalid or expired reset link"}})
def reset_password(body: ResetPasswordRequest) -> ResetPasswordResponse:
    user_id = password_reset_repo.consume_token(body.token)
    if not user_id:
        raise HTTPException(400, "this reset link is invalid or has expired")
    users_repo.update_password(user_id, security.hash_password(body.new_password))
    return ResetPasswordResponse(message="Your password has been reset. You can now log in.")


@app.get("/api/v1/auth/google/login", tags=["auth"], summary="Redirect to Google sign-in")
def google_login():
    return RedirectResponse(google_oauth.build_auth_url(security.sign_state()))


@app.get("/api/v1/auth/google/callback", tags=["auth"], summary="Google OAuth callback")
def google_callback(code: str, state: str):
    if not security.verify_state(state):
        raise HTTPException(400, "invalid state")
    try:
        info = google_oauth.exchange_code(code)
    except google_oauth.GoogleOAuthError as e:
        raise HTTPException(502, f"google error: {e}")
    user = users_repo.get_by_google_sub(info["sub"]) or users_repo.create_user(
        google_sub=info["sub"], email=info.get("email"), full_name=info.get("name"))
    token = security.create_access_token(user["id"])
    return RedirectResponse(f"{os.getenv('FRONTEND_URL', '')}/auth/callback#token={token}")


@app.get("/api/v1/users/me", response_model=UserPublic, tags=["auth"], summary="Current user")
def get_me(user: dict = Depends(security.current_user)) -> UserPublic:
    return UserPublic(**user)


@app.patch("/api/v1/users/me", response_model=UserPublic, tags=["auth"],
           responses={409: {"description": "username taken"}})
def patch_me(body: ProfileUpdate, user: dict = Depends(security.current_user)) -> UserPublic:
    fields: dict = {}
    if body.username is not None and body.username != user.get("username"):
        if users_repo.get_by_username(body.username):
            raise HTTPException(409, "username already taken")
        fields["username"] = body.username
    if body.ev_model_id is not None:
        fields["ev_model_id"] = body.ev_model_id
    if body.main_connector_type is not None:
        fields["main_connector_type"] = body.main_connector_type
    if body.location_consent is not None:
        fields["location_consent"] = body.location_consent
    merged = {**user, **fields}
    completed = bool(merged.get("ev_model_id") and merged.get("main_connector_type")
                     and merged.get("location_consent"))
    updated = users_repo.update_profile(user["id"], fields, completed)
    return UserPublic(**updated)


@app.get("/api/v1/stats", response_model=Stats, tags=["meta"], summary="Aggregate statistics")
def stats() -> Stats:
    s = repo.stats()
    by_source = [SourceCount(source=src, count=c) for src, c in repo.source_counts()]
    by_prov = [NameCount(name=n, count=c) for n, c in repo.provinces()[:40]]
    by_type = [NameCount(name=k, count=v) for k, v in repo.speed_tier_counts().items()]
    return Stats(total=s["total"], by_source=by_source, by_province=by_prov,
                 by_charge_type=by_type, with_power_kw=s["with_power_kw"],
                 power_kw_min=s["power_kw_min"], power_kw_max=s["power_kw_max"],
                 power_kw_mean=s["power_kw_mean"])


@app.get("/api/v1/sources", response_model=list[SourceCount], tags=["meta"])
def sources_lookup() -> list[SourceCount]:
    return [SourceCount(source=s, count=c) for s, c in repo.source_counts()]


@app.get("/api/v1/provinces", response_model=list[NameCount], tags=["meta"])
def provinces_lookup() -> list[NameCount]:
    return [NameCount(name=n, count=c) for n, c in repo.provinces()]


@app.get("/api/v1/cities", response_model=list[NameCount], tags=["meta"])
def cities_lookup(province: Optional[str] = Query(None)) -> list[NameCount]:
    return [NameCount(name=n, count=c) for n, c in repo.cities(province)]


@app.get("/api/v1/connectors", response_model=list[NameCount], tags=["meta"],
         summary="Connector types with counts for the filter dropdown (inferred)")
def connectors_lookup() -> list[NameCount]:
    return [NameCount(name=n, count=c) for n, c in repo.connector_counts()]


@app.get("/api/v1/speed-tiers", response_model=list[SpeedTier], tags=["meta"],
         summary="Speed tier definitions with counts")
def speed_tiers_lookup() -> list[SpeedTier]:
    counts = repo.speed_tier_counts()
    return [SpeedTier(id=t["id"], label=t["label"], min_kw=t["min_kw"], max_kw=t["max_kw"],
                      count=counts.get(t["id"], 0)) for t in conn.SPEED_TIERS]

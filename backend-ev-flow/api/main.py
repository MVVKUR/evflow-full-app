"""FastAPI app exposing combined Jakarta/Indonesia EV charging-station data.

Run:  uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs   (Swagger UI)
Spec: http://localhost:8000/openapi.json
"""
from __future__ import annotations

import hmac
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from . import __version__, evmodels
from . import connectors as conn
from . import connectors_repo
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
from . import log_privacy
from . import rate_limit
from .models import (
    EVModel, EVModelList, GeoJSONFeatureCollection, Health, NameCount,
    NearestStationRoute, Route, SourceCount, SpeedTier, Station,
    StationAvailability, StationConnector, ConnectorStatusUpdate,
    StationList, Stats,
    Topup, TopupCreated, TopupRequest, WalletBalance,
    ChargingQuote, ChargingQuoteRequest, ChargingSession, StartSessionRequest, SettleRequest,
    ForgotPasswordRequest, ForgotPasswordResponse, LoginRequest, ProfileUpdate, RegisterRequest,
    ResetPasswordRequest, ResetPasswordResponse, TokenResponse, UserPublic,
    RoutePlanRequest, RoutePlanResponse, GeocodingSearchResponse, VehicleSummary,
    TripSummary, RoutePlanGeometryAndSteps, RecommendedStop, RoutePlanAssumptions, GeocodingItem,
    RouteWarning, ActiveRouteEvaluationRequest, ActiveRouteEvaluationResponse,
    ManualVehicleInput, RoutePreferencesInput, ServiceAreaSummary,
    StationStatusResponse, StationOccupancyResponse,
)
from .services import service_area

# Coordinate masking must not depend on the ASGI lifespan running: with
# `--lifespan off`, or under a bare TestClient, the filter used to be defined but
# never attached and raw coordinates reached the access log (AC 2.3.2).
# `install()` is idempotent, so the lifespan hook below is kept as a belt.
log_privacy.install()



TAGS = [
    {"name": "routing", "description":
        "Trip planning and active navigation (Epic 2). `POST /route-plans` answers whether the "
        "destination is reachable and, when it is not, which charging stop to take. "
        "`POST /route-plans/active/evaluate` re-checks a trip already under way. Destination "
        "search lives here too.\n\n"
        "Read `route_status` first: it is the single field that decides what the screen shows. "
        "See [ROUTE_PLANNING_API.md](https://github.com/MVVKUR/evflow-full-app/blob/main/"
        "backend-ev-flow/ROUTE_PLANNING_API.md) for worked examples."},
    {"name": "stations", "description":
        "Query and fetch charging stations, including per-connector live status. "
        "`/stations/{id}/availability` counts plugs by status; `/stations/{id}/connectors` lists "
        "them individually."},
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
    # Endpoints that take coordinates as GET query params (the frontend contract)
    # would otherwise put a raw GPS fix into the access log verbatim.
    log_privacy.install()

    # AC 2.3.3: the temporary-location TTL must hold on an IDLE process. Expiry
    # used to run only inside the cache's own writer, so with no further traffic
    # a cached position outlived its 30 s deadline indefinitely. This task sleeps
    # until the next entry is actually due and deletes it then.
    from api.services.geocoding_service import start_sweeper, stop_sweeper
    start_sweeper()
    try:
        yield
    finally:
        await stop_sweeper()


# Rendered as the intro panel in ReDoc and above the operations in Swagger UI.
# Markdown, so keep it scannable: what the data is, how to authenticate, how
# errors look, and the handful of things clients get wrong.
API_DESCRIPTION = """
EV charging station discovery, trip planning and charging for Indonesia.

Station data is fused from three sources: the PLN SPKLU map, Open Charge Map and
OpenStreetMap. Records within 75 m of each other are treated as one physical site,
which is why a station can list several `sources`.

## Two ways to read this

* **ReDoc** (`/redoc`) is the reference. Three panes, every schema expanded, good for
  reading a model end to end.
* **Swagger UI** (`/docs`) is the workbench. Same spec, but you can authorise once and
  fire real requests from the browser.

Both are generated from `/openapi.json`, so they never disagree with the server.

## Authentication

Most write endpoints take `Authorization: Bearer <token>` from `POST /api/v1/auth/login`
or `/auth/register`. In Swagger UI, use **Authorize** and paste the token.

The geocoding endpoints are deliberately open. This deployment is a demo whose demo
password ships inside the web bundle, so a token there would prove nothing while
breaking the destination picker. They are bounded by rate limits and a cache instead.

## Errors

Validation failures return `422` with a `detail` array, and every entry names the field
in `loc`:

```json
{"detail": [{"loc": ["body", "current_soc_pct"],
             "msg": "Input should be less than or equal to 100"}]}
```

Attach the message to that input rather than showing one general error.

## Worth knowing before you build

* Route planning enforces a **configured service area**. An origin or destination outside
  it is rejected with a `422`, and no route is generated. A trip already under way is
  never refused; `/route-plans/active/evaluate` reports it as an advisory instead.
* Connector availability comes from live per-connector rows, not from a station-level
  flag. `available_connector_count` already excludes plugs this vehicle cannot use.
* Connector types are frequently **inferred** from power rather than stated by the source.
  Anything carrying `*_inferred: true` is an educated guess and should be labelled as one.
* Coordinates are coarsened before they reach logs or any third party.
"""

app = FastAPI(
    title="EV-FLOW API",
    summary="Charging station discovery, trip planning and charging for Indonesia.",
    description=API_DESCRIPTION,
    version=__version__,
    openapi_tags=TAGS,
    contact={"name": "EV-FLOW", "url": "https://github.com/MVVKUR/evflow-full-app"},
    license_info={"name": "Data: PLN, OCM (CC-BY-SA), OSM (ODbL)"},
    servers=[
        {"url": "/", "description": "This server"},
        {"url": "https://ev-flow-api.opensoft.id", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Local development"},
    ],
    lifespan=lifespan,
)


# Field names whose submitted value must never travel back to the caller. FastAPI's
# default validation handler echoes the offending input in detail[].input, which for
# a rejected password means the plaintext lands in the response body, and from there
# in browser consoles, proxy logs and error-tracking tools.
_REDACTED_INPUT_FIELDS = frozenset({"password", "new_password", "current_password", "token"})


@app.exception_handler(RequestValidationError)
async def _validation_error_without_echoing_secrets(request: Request, exc: RequestValidationError):
    """Standard 422 body, minus any echoed secret.

    detail[].loc is preserved exactly, because the frontend attaches each message
    to the field it names (AC 2.2.2). Only the echoed value is dropped.
    """
    detail = []
    for err in exc.errors():
        item = {k: v for k, v in err.items() if k != "ctx"}
        loc = item.get("loc") or ()
        if any(str(part) in _REDACTED_INPUT_FIELDS for part in loc):
            item.pop("input", None)
        detail.append(jsonable_encoder(item))
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(evmodels.CatalogueUnavailable)
async def _ev_catalogue_unavailable(request: Request, exc: evmodels.CatalogueUnavailable):
    """503, not 404 and not an empty list.

    `api/evmodels` is database-only now. When the table is unreachable or has
    never been ingested, the honest answer is "this dependency is down, retry" —
    NOT `200 {"total": 0}` (we sell no cars) and NOT `404 unknown EV model`
    (your car is not real), both of which blame the caller for an operator
    problem. The remedy — run the ingest — travels in the message.
    """
    logging.error("ev model catalogue unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": str(exc)})

# Frontend calls this from a browser, so allow CORS. Auth/write endpoints are now live, so set
# CORS_ALLOW_ORIGINS (comma-separated) to the frontend origin(s) in production; it defaults to "*"
# (open) only for local/dev convenience.
_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
_allow_origins = ["*"] if _origins_env in ("", "*") else [o.strip() for o in _origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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


@app.get("/api/v1/stations/{station_id}/connectors", response_model=list[StationConnector],
         tags=["stations"], summary="Physical connectors at a station (with live status)",
         responses={404: {"description": "Station not found"}})
def station_connectors(station_id: str) -> list[StationConnector]:
    if repo.get_station(station_id) is None:
        raise HTTPException(404, f"station '{station_id}' not found")
    return [StationConnector(**r) for r in connectors_repo.list_by_station(station_id)]


@app.get("/api/v1/stations/{station_id}/availability", response_model=StationAvailability,
         tags=["stations"], summary="Connector availability counts for a station",
         responses={404: {"description": "Station not found"}})
def station_availability(station_id: str) -> StationAvailability:
    if repo.get_station(station_id) is None:
        raise HTTPException(404, f"station '{station_id}' not found")
    return StationAvailability(**connectors_repo.availability(station_id))


@app.patch("/api/v1/connectors/{connector_id}/status", response_model=StationConnector,
           tags=["stations"], summary="Set a connector's status (available / in_use / out_of_service)",
           responses={404: {"description": "Connector not found"},
                      422: {"description": "Invalid status"}})
def update_connector_status(connector_id: str, body: ConnectorStatusUpdate,
                            user: dict = Depends(security.current_user)) -> StationConnector:
    try:
        row = connectors_repo.set_status(connector_id, body.status)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if row is None:
        raise HTTPException(404, f"connector '{connector_id}' not found")
    return StationConnector(**row)


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
          responses={401: {"description": "Invalid callback token"},
                     503: {"description": "Webhook not configured"}})
def xendit_webhook(payload: dict, x_callback_token: Optional[str] = Header(None)):
    expected = os.getenv("XENDIT_CALLBACK_TOKEN", "")
    # Fail closed: an unset or short token would let anyone credit wallets.
    if not expected or len(expected) < 16:
        raise HTTPException(503, "webhook not configured")
    # Constant-time comparison (consistent with security.py's state check).
    if not hmac.compare_digest(x_callback_token or "", expected):
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
def charging_quote(body: ChargingQuoteRequest, user: dict = Depends(security.current_user)) -> ChargingQuote:
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
    # delivered_kwh is client-reported pending charger-hardware integration;
    # pricing.settlement() clamps it server-side to [0, purchased energy_kwh].
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


# ---- Epic 2.0 Route Planning & Geocoding Endpoints -------------------------
ROUTE_STATUS_DIRECT = "direct_route_available"
ROUTE_STATUS_CHARGING_REQUIRED = "charging_required"
ROUTE_STATUS_NO_STATION = "no_suitable_station"

# How many ranked candidates may be re-checked against real routed legs before
# the plan gives up. Each attempt costs two routing calls.
MAX_ROAD_VALIDATION_CANDIDATES = int(os.getenv("ROUTE_MAX_ROAD_VALIDATION_CANDIDATES", "3"))

# AC 2.2.6: machine-readable remedies, so the client can render buttons and
# localise them instead of string-matching the English in `warning.message`.
SUGGEST_ANOTHER_ROUTE = "choose_another_route"
SUGGEST_ADJUST_PREFERENCES = "adjust_preferences"
SUGGEST_CHARGE_BEFORE_DEPARTURE = "charge_before_departure"
NO_STATION_SUGGESTED_ACTIONS = [
    SUGGEST_ANOTHER_ROUTE,
    SUGGEST_ADJUST_PREFERENCES,
    SUGGEST_CHARGE_BEFORE_DEPARTURE,
]

# Advisory-only, never blocking: the driver is mid-journey outside the configured
# service area (AC 2.1.1 / AC 2.4.2 keep the evaluation running regardless).
WARNING_OUT_OF_SERVICE_AREA = "out_of_service_area"
SUGGEST_RETURN_TO_SERVICE_AREA = "return_to_service_area"

# Advisory-only, never blocking: every road-routing provider is down, so the
# ACTIVE-route evaluation fell back to a straight-line estimate. Reported next to
# (never instead of) the battery warning -- they are different conditions and both
# must be able to fire at once.
WARNING_ROUTING_DEGRADED = "routing_degraded"
ROUTING_DEGRADED_MESSAGE = (
    "Road routing is unavailable right now, so distance and arrival time are a "
    "straight-line approximation and turn-by-turn navigation is off. Your battery "
    "projection is still being updated; treat the distance as a best case.")

# AC 2.2.3 manual-range branch: a bare range says nothing about pack size, so a
# pack consistent with the entered range is assumed at this efficiency. Same
# 180 Wh/km already used when a catalogue model has no efficiency figure.
MANUAL_VEHICLE_ID = "manual-range"
MANUAL_VEHICLE_EFFICIENCY_WH_PER_KM = float(
    os.getenv("ROUTE_MANUAL_EFFICIENCY_WH_PER_KM", "180.0"))
MANUAL_EFFICIENCY_SOURCE = "manual_range"


def _manual_vehicle(manual: ManualVehicleInput) -> tuple[str, dict]:
    """Build a planning vehicle from a hand-entered range (AC 2.2.3).

    With a pack size, efficiency is derived from it so the entered range is what
    a full pack actually delivers. Without one, a pack consistent with the range
    at ``MANUAL_VEHICLE_EFFICIENCY_WH_PER_KM`` is assumed -- self-consistent
    either way, so 100% SoC is exactly ``usable_range_km``.
    """
    range_km = float(manual.usable_range_km)
    if manual.battery_kwh:
        battery_kwh = float(manual.battery_kwh)
        efficiency_wh_per_km = (battery_kwh * 1000.0) / range_km
    else:
        efficiency_wh_per_km = MANUAL_VEHICLE_EFFICIENCY_WH_PER_KM
        battery_kwh = (range_km * efficiency_wh_per_km) / 1000.0

    return MANUAL_VEHICLE_ID, {
        "id": MANUAL_VEHICLE_ID,
        "name": manual.name or f"Manual range ({range_km:.0f} km)",
        "battery_kwh": round(battery_kwh, 2),
        "efficiency_wh_per_km": round(efficiency_wh_per_km, 1),
        "efficiency_source": MANUAL_EFFICIENCY_SOURCE,
        "max_dc_charge_kw": manual.max_dc_charge_kw,
        "fast_charge_port": manual.connector_type,
    }


def _planning_vehicle(
    user: dict,
    ev_model_id: Optional[str] = None,
    manual: Optional[ManualVehicleInput] = None,
) -> tuple[str, dict]:
    """Resolve the vehicle this plan is simulated for (AC 2.2.3).

    Precedence: a range entered on the request > an EV model named on the
    request > the saved profile. The AC allows EITHER a selected vehicle profile
    OR an entered range, so a driver with no profile who supplies a range is
    planned for -- 409 is reserved for the case where all three sources are
    absent.
    """
    if manual is not None:
        return _manual_vehicle(manual)

    requested_id = ev_model_id or user.get("ev_model_id")
    if not requested_id:
        raise HTTPException(
            409,
            "Please select an EV model in your profile, or send a vehicle range, "
            "before simulating route energy consumption."
        )

    ev_model = evmodels.get(requested_id)
    if not ev_model:
        if ev_model_id:
            raise HTTPException(404, f"Unknown EV model '{ev_model_id}'.")
        raise HTTPException(
            409,
            f"The selected vehicle '{requested_id}' lacks usable battery capacity data. Please select another vehicle model in your profile."
        )
    if not ev_model.get("battery_kwh"):
        raise HTTPException(
            409,
            f"The selected vehicle '{requested_id}' lacks usable battery capacity data. Please select another vehicle model in your profile."
        )
    return requested_id, ev_model


def _eta(computed_at: datetime, duration_minutes: float) -> datetime:
    """AC 2.4.1 estimated arrival TIME, anchored to a server clock the client sees."""
    return computed_at + timedelta(minutes=float(duration_minutes or 0.0))


def _vehicle_summary(ev_model_id: str, ev_model: dict, battery_kwh: float,
                     efficiency_wh_per_km: float, efficiency_source: str) -> VehicleSummary:
    return VehicleSummary(
        id=ev_model.get("id") or ev_model_id,
        name=ev_model.get("name") or "Selected EV",
        battery_kwh=battery_kwh,
        efficiency_wh_per_km=efficiency_wh_per_km,
        efficiency_source=efficiency_source,
    )


def _distance_basis(route: dict, origin: tuple[float, float],
                    destination: tuple[float, float]) -> tuple[str, float]:
    """Pick ONE distance measure for the whole plan and the factor that maps onto it.

    `detour_km = (leg1 + leg2) - direct` is only meaningful when all three come
    from the same measure. Straight-line legs are therefore scaled by
    `road_km / straight_line_km` so they live in the same units as the direct
    distance the routing provider returned; the subtraction stays consistent and
    (by the triangle inequality) can never go negative.
    """
    from api.services.routing_service import haversine_distance_km
    from api.services.stop_ranker import DISTANCE_BASIS_ROAD, DISTANCE_BASIS_STRAIGHT_LINE

    straight_km = haversine_distance_km(origin[0], origin[1], destination[0], destination[1])
    route_km = float(route.get("distance_km") or 0.0)
    scale = (route_km / straight_km) if straight_km > 0.01 and route_km > 0 else 1.0
    basis = (DISTANCE_BASIS_ROAD
             if route.get("provider") in ("osrm", "local_dijkstra")
             else DISTANCE_BASIS_STRAIGHT_LINE)
    return basis, scale


def _classify_route(raw_arrival_soc_pct: float, reserve_pct: float,
                    tight_margin_pct: float) -> tuple[str, bool]:
    """AC 2.1.2 / AC 2.1.3 route status.

    At or above the reserve the route is DIRECT and carries no charging stops.
    `margin_is_tight` is a separate advisory flag so a snug-but-safe trip is
    still reported as 'direct_route_available' (AC 2.1.2 keeps holding).
    """
    if raw_arrival_soc_pct >= reserve_pct:
        return ROUTE_STATUS_DIRECT, raw_arrival_soc_pct < (reserve_pct + tight_margin_pct)
    return ROUTE_STATUS_CHARGING_REQUIRED, False


def _below_reserve_warning(projected_soc_pct: float, reserve_pct: float) -> RouteWarning:
    shortfall = max(0.0, reserve_pct - projected_soc_pct)
    return RouteWarning(
        triggered=True,
        code="battery_below_reserve",
        severity="critical" if projected_soc_pct <= 0 else "warning",
        message=(
            f"Projected arrival battery is {projected_soc_pct:.0f}%, below your "
            f"{reserve_pct:.0f}% reserve. Add a charging stop to reach your destination safely."
        ),
        projected_arrival_soc_pct=round(projected_soc_pct, 1),
        reserve_soc_pct=round(reserve_pct, 1),
        shortfall_soc_pct=round(shortfall, 1),
        can_dismiss=True,
    )


def _driver_stop_warning(stop: RecommendedStop, reserve_pct: float,
                         projected_soc_pct: float) -> RouteWarning:
    """Explain a driver-forced waypoint: honoured, or honoured-but-impossible.

    A forced waypoint used to skip every AC 2.2.9 filter and still be folded
    into the summary as though the charge had succeeded, so an unreachable or
    unusable station produced a comfortably safe-looking trip. It is now
    surfaced explicitly.
    """
    reasons = list(stop.blocking_reasons or [])
    if not reasons:
        return RouteWarning(
            triggered=False,
            code="stop_added_by_driver",
            severity="info",
            message=(
                f"{stop.station.name} was added to your route as you asked. This trip did not "
                f"need a charging stop."
            ),
            projected_arrival_soc_pct=round(projected_soc_pct, 1),
            reserve_soc_pct=round(reserve_pct, 1),
            shortfall_soc_pct=0.0,
            can_dismiss=True,
        )

    if "unreachable" in reasons:
        code = "forced_stop_unreachable"
        detail = (f"{stop.station.name} is beyond your remaining range: you would run out of "
                  f"charge before reaching it.")
    elif "no_free_compatible_connector" in reasons:
        code = "forced_stop_unavailable"
        detail = (f"{stop.station.name} has no free connector your vehicle can use right now.")
    else:
        code = "forced_stop_cannot_complete"
        detail = (f"Even a full charge at {stop.station.name} does not get you to your "
                  f"destination with your reserve intact.")

    return RouteWarning(
        triggered=True,
        code=code,
        severity="critical",
        message=f"{detail} Pick another charging stop.",
        projected_arrival_soc_pct=round(projected_soc_pct, 1),
        reserve_soc_pct=round(reserve_pct, 1),
        shortfall_soc_pct=round(max(0.0, reserve_pct - projected_soc_pct), 1),
        can_dismiss=True,
    )


async def _road_validated_stop(
    routing_service,
    stop_ranker,
    ranked: list[RecommendedStop],
    origin_pos: tuple[float, float],
    dest_pos: tuple[float, float],
    direct_distance_km: float,
    battery_kwh: float,
    efficiency_wh_per_km: float,
    current_soc_pct: float,
    reserve_pct: float,
    max_dc_charge_kw,
    distance_basis: str,
    forced: bool,
    weights=None,
    maximum_detour_km: Optional[float] = None,
) -> tuple[Optional[RecommendedStop], Optional[dict], list[RecommendedStop]]:
    """Pick the best ranked stop that still holds on the ACTUAL routed legs.

    Ranking works on `haversine * corridor_average_scale`; the driver is then
    routed over real roads. A stop->destination leg more winding than the
    corridor average used to break the "arrive above the reserve" promise
    silently, so the chosen candidate is re-derived from the routed legs here
    and the next candidate is tried when it no longer holds.

    AC 2.2.4: the detour budget was only ever applied to the straight-line
    estimate, so a stop whose ROAD detour blew past the driver's budget could
    still be recommended. A candidate that fits the budget on the road is now
    preferred over one that does not; an over-budget candidate is used only when
    nothing inside the budget survived, and it comes back flagged
    (`detour_within_budget=False`) rather than silently.

    Returns ``(stop, route_through_stop, remaining_alternatives)``.
    """
    if weights is None:
        from api.services.stop_ranker import DEFAULT_RANKING_WEIGHTS
        weights = DEFAULT_RANKING_WEIGHTS

    from api.services.routing_service import RouteUnavailable

    rejected_ids: set[str] = set()
    over_budget: Optional[tuple[RecommendedStop, dict]] = None

    for candidate in ranked[:MAX_ROAD_VALIDATION_CANDIDATES]:
        st_pos = (candidate.station.latitude, candidate.station.longitude)
        try:
            via_route = await routing_service.get_route(origin_pos, dest_pos, waypoints=[st_pos])
            tail_route = await routing_service.get_route(st_pos, dest_pos)
        except RouteUnavailable:
            rejected_ids.add(candidate.station.id)
            continue

        leg_to_dest_km = float(tail_route["distance_km"])
        leg_to_stop_km = max(0.0, float(via_route["distance_km"]) - leg_to_dest_km)

        validated = stop_ranker.revalidate_on_road(
            stop=candidate,
            road_leg_to_station_km=leg_to_stop_km,
            road_leg_to_destination_km=leg_to_dest_km,
            road_direct_distance_km=direct_distance_km,
            battery_kwh=battery_kwh,
            efficiency_wh_per_km=efficiency_wh_per_km,
            current_soc_pct=current_soc_pct,
            reserve_pct=reserve_pct,
            max_dc_charge_kw=max_dc_charge_kw,
            distance_basis=distance_basis,
            forced=forced,
            weights=weights,
            maximum_detour_km=maximum_detour_km,
        )
        if validated is not None:
            if validated.detour_within_budget or forced:
                alternatives = [s for s in ranked
                                if s.station.id != validated.station.id
                                and s.station.id not in rejected_ids]
                return validated, via_route, alternatives
            if over_budget is None:
                over_budget = (validated, via_route)
            continue

        rejected_ids.add(candidate.station.id)

    if over_budget is not None:
        stop, via_route = over_budget
        alternatives = [s for s in ranked
                        if s.station.id != stop.station.id and s.station.id not in rejected_ids]
        return stop, via_route, alternatives

    return None, None, [s for s in ranked if s.station.id not in rejected_ids]


@app.post("/api/v1/route-plans", response_model=RoutePlanResponse, tags=["routing"],
          summary="Simulate trip energy consumption and recommend optimal SPKLU charging stop")
async def create_route_plan(
    body: RoutePlanRequest,
    user: dict = Depends(security.current_user)
) -> RoutePlanResponse:
    ev_model_id, ev_model = _planning_vehicle(user, body.ev_model_id, body.vehicle)

    battery_kwh = float(ev_model["battery_kwh"])
    efficiency_wh_per_km = float(ev_model.get("efficiency_wh_per_km") or 180.0)
    efficiency_source = ev_model.get("efficiency_source") or "dataset"
    max_dc_charge_kw = ev_model.get("max_dc_charge_kw")

    from api.services.routing_service import ROAD_PROVIDERS, RouteUnavailable, RoutingService
    from api.services.energy_estimator import (
        MIN_RESERVE_KM, TIGHT_MARGIN_SOC_PCT, EnergyEstimator,
        effective_reserve_soc_pct, reserve_km_for_soc_pct,
    )
    from api.services.connector_compat import vehicle_connector_profile
    from api.services.stop_ranker import StopRanker, ranking_weights_for

    connector_profile = vehicle_connector_profile(
        ev_model.get("fast_charge_port"), user.get("main_connector_type")
    )

    # Round coordinates according to DMP (privacy and caching)
    origin_pos = (round(body.origin.latitude, 4), round(body.origin.longitude, 4))
    dest_pos = (round(body.destination.latitude, 4), round(body.destination.longitude, 4))

    routing_service = RoutingService()
    energy_estimator = EnergyEstimator()
    stop_ranker = StopRanker(energy_estimator, routing_service)

    # AC 2.1.3: one reserve, resolved once, used everywhere below.
    reserve_pct = effective_reserve_soc_pct(
        battery_kwh, efficiency_wh_per_km, body.minimum_arrival_soc_pct
    )
    reserve_km = reserve_km_for_soc_pct(battery_kwh, efficiency_wh_per_km, reserve_pct)

    try:
        direct_route = await routing_service.get_route(origin_pos, dest_pos)
    except RouteUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    distance_km = direct_route["distance_km"]
    duration_mins = direct_route["duration_minutes"]
    basis, scale = _distance_basis(direct_route, origin_pos, dest_pos)

    est_direct = energy_estimator.estimate_trip_energy(
        battery_kwh=battery_kwh,
        efficiency_wh_per_km=efficiency_wh_per_km,
        distance_km=distance_km,
        current_soc_pct=body.current_soc_pct,
        minimum_arrival_soc_pct=reserve_pct,
    )

    # AC 2.2.4: the driver's charging preferences drive the ranking. They used to
    # be validated, published in OpenAPI and then dropped on the floor -- flipping
    # prefer_fast_charging produced byte-identical plans.
    preferences = body.preferences or RoutePreferencesInput()
    max_detour_km = preferences.maximum_detour_km
    rank_weights = ranking_weights_for(
        route_type=preferences.route_type,
        prefer_fast_charging=preferences.prefer_fast_charging,
    )

    route_status, margin_is_tight = _classify_route(
        est_direct.raw_arrival_soc_pct, reserve_pct, TIGHT_MARGIN_SOC_PCT
    )
    forced_station_id = body.waypoint_station_id
    stop_required = (route_status == ROUTE_STATUS_CHARGING_REQUIRED) or (forced_station_id is not None)

    recommended_stop: Optional[RecommendedStop] = None
    user_requested_stop: Optional[RecommendedStop] = None
    alternative_stops: list[RecommendedStop] = []
    warning: Optional[RouteWarning] = None
    final_route = direct_route
    final_distance_km = distance_km
    final_duration_mins = duration_mins
    final_arrival_soc = est_direct.estimated_arrival_soc_pct
    final_energy_kwh = est_direct.estimated_trip_energy_kwh

    if stop_required:
        # The below-reserve alert belongs to the PROJECTION, never to the mere
        # presence of a driver-chosen waypoint: a safe route used to come back
        # with "arrival 79%, below your 20% reserve" and shortfall 0.0.
        if route_status == ROUTE_STATUS_CHARGING_REQUIRED:
            warning = _below_reserve_warning(est_direct.raw_arrival_soc_pct, reserve_pct)

        ranked = await stop_ranker.rank_stops(
            origin=origin_pos,
            destination=dest_pos,
            direct_distance_km=distance_km,
            battery_kwh=battery_kwh,
            efficiency_wh_per_km=efficiency_wh_per_km,
            current_soc_pct=body.current_soc_pct,
            minimum_arrival_soc_pct=reserve_pct,
            max_dc_charge_kw=max_dc_charge_kw,
            maximum_detour_km=max_detour_km,
            forced_station_id=forced_station_id,
            connector_profile=connector_profile,
            distance_scale_factor=scale,
            distance_basis=basis,
            limit=body.max_candidate_stops,
            weights=rank_weights,
        )

        selected, stop_route, alternative_stops = await _road_validated_stop(
            routing_service=routing_service,
            stop_ranker=stop_ranker,
            ranked=ranked,
            origin_pos=origin_pos,
            dest_pos=dest_pos,
            direct_distance_km=distance_km,
            battery_kwh=battery_kwh,
            efficiency_wh_per_km=efficiency_wh_per_km,
            current_soc_pct=body.current_soc_pct,
            reserve_pct=reserve_pct,
            max_dc_charge_kw=max_dc_charge_kw,
            distance_basis=basis,
            forced=bool(forced_station_id),
            weights=rank_weights,
            maximum_detour_km=max_detour_km,
        )

        if selected is not None and stop_route is not None:
            final_route = stop_route
            final_distance_km = stop_route["distance_km"]
            final_energy_kwh = round(
                est_direct.estimated_trip_energy_kwh * (final_distance_km / max(1.0, distance_km)), 2)

            if selected.completes_trip:
                # The driver charges here, so the arrival projection starts from
                # the charge target and covers the REAL remaining road leg.
                est_from_stop = energy_estimator.estimate_trip_energy(
                    battery_kwh=battery_kwh,
                    efficiency_wh_per_km=efficiency_wh_per_km,
                    distance_km=selected.distance_to_destination_km or 0.0,
                    current_soc_pct=selected.recommended_target_soc_pct,
                    minimum_arrival_soc_pct=reserve_pct,
                )
                final_arrival_soc = est_from_stop.estimated_arrival_soc_pct
                final_duration_mins = (stop_route["duration_minutes"]
                                       + selected.estimated_charging_minutes)
            else:
                # A forced stop that cannot be reached or cannot be used charges
                # nothing: report the physics of driving the detour, not a
                # fictional post-charge SoC.
                est_via = energy_estimator.estimate_trip_energy(
                    battery_kwh=battery_kwh,
                    efficiency_wh_per_km=efficiency_wh_per_km,
                    distance_km=final_distance_km,
                    current_soc_pct=body.current_soc_pct,
                    minimum_arrival_soc_pct=reserve_pct,
                )
                final_arrival_soc = est_via.estimated_arrival_soc_pct
                final_duration_mins = stop_route["duration_minutes"]

            if selected.completes_trip and route_status == ROUTE_STATUS_CHARGING_REQUIRED:
                recommended_stop = selected
            else:
                # Either the green direct state, which recommends NO charging
                # stop (AC 2.1.2), or a forced stop that failed the physics.
                # `recommended_stop`/`charging_stops` stay reserved for stops the
                # system can actually stand behind.
                user_requested_stop = selected

            if forced_station_id:
                warning = _driver_stop_warning(selected, reserve_pct, final_arrival_soc)

        elif route_status == ROUTE_STATUS_CHARGING_REQUIRED:
            # Better an explicit "nothing works" than a plan that fails partway.
            # Nothing survived, so nothing is offered: no contradictory list.
            route_status = ROUTE_STATUS_NO_STATION
            alternative_stops = []
            warning = RouteWarning(
                triggered=True,
                code="no_suitable_station",
                severity="critical",
                message=(
                    "No charging station on this corridor is reachable with your reserve intact, "
                    "has a free connector your vehicle can use, and can get you to the destination. "
                    "Try charging before departure, choosing another route, or widening the "
                    "detour allowance."
                ),
                projected_arrival_soc_pct=round(est_direct.raw_arrival_soc_pct, 1),
                reserve_soc_pct=round(reserve_pct, 1),
                shortfall_soc_pct=round(max(0.0, reserve_pct - est_direct.raw_arrival_soc_pct), 1),
                can_dismiss=True,
                suggested_actions=list(NO_STATION_SUGGESTED_ACTIONS),
            )
        elif forced_station_id:
            warning = RouteWarning(
                triggered=True,
                code="forced_stop_not_found",
                severity="warning",
                message=("The station you asked to add could not be found, so your original route "
                         "was kept."),
                projected_arrival_soc_pct=round(est_direct.raw_arrival_soc_pct, 1),
                reserve_soc_pct=round(reserve_pct, 1),
                shortfall_soc_pct=0.0,
                can_dismiss=True,
            )

    # AC 2.1.2: a direct route carries NO charging stops.
    charging_stops = [recommended_stop] if recommended_stop else []
    if route_status == ROUTE_STATUS_DIRECT:
        charging_stops = []
        recommended_stop = None

    plan_id = f"plan-{uuid.uuid4().hex[:12]}"

    # AC 2.4.1: an arrival TIME, not just a duration. Anchored to a server clock
    # the client also receives, so two clients reading the same plan at different
    # moments agree instead of each adding duration to their own "now".
    computed_at = datetime.now(timezone.utc)
    steps = final_route.get("steps") or []
    provider = final_route.get("provider")

    return RoutePlanResponse(
        route_plan_id=plan_id,
        route_status=route_status,
        margin_is_tight=margin_is_tight,
        directly_reachable=est_direct.directly_reachable and recommended_stop is None,
        vehicle=_vehicle_summary(ev_model_id, ev_model, battery_kwh,
                                 efficiency_wh_per_km, efficiency_source),
        summary=TripSummary(
            distance_km=final_distance_km,
            duration_minutes=round(final_duration_mins, 1),
            estimated_energy_kwh=final_energy_kwh,
            estimated_arrival_soc_pct=final_arrival_soc,
            minimum_arrival_soc_pct=reserve_pct,
            requested_minimum_arrival_soc_pct=body.minimum_arrival_soc_pct,
            effective_reserve_km=round(reserve_km, 1),
            direct_arrival_soc_pct=est_direct.estimated_arrival_soc_pct,
            soc_margin_pct=round(final_arrival_soc - reserve_pct, 1),
            computed_at=computed_at,
            estimated_arrival_at=_eta(computed_at, final_duration_mins),
        ),
        route=RoutePlanGeometryAndSteps(
            type="Feature",
            geometry=final_route["geometry"],
            steps=steps,
        ),
        recommended_stop=recommended_stop,
        charging_stops=charging_stops,
        user_requested_stop=user_requested_stop,
        alternative_stops=alternative_stops,
        warning=warning,
        assumptions=RoutePlanAssumptions(
            reserve_soc_pct=reserve_pct,
            requested_reserve_soc_pct=body.minimum_arrival_soc_pct,
            effective_reserve_km=round(reserve_km, 1),
            minimum_reserve_km=MIN_RESERVE_KM,
            distance_basis=basis,
            vehicle_connector_types=list(connector_profile.types),
            connector_source=connector_profile.source,
            weather_applied=False,
            traffic_applied=False,
            connector_data_inferred=bool(connector_profile.inferred_types),
            energy_model_version="spec-v2",
            service_area=ServiceAreaSummary(**service_area.describe()),
            route_type=preferences.route_type,
            prefer_fast_charging=preferences.prefer_fast_charging,
            maximum_detour_km=max_detour_km,
            rank_detour_weight=rank_weights.detour_weight,
            rank_power_weight_km_per_kw=rank_weights.power_weight_km_per_kw,
            routing_provider=provider,
            turn_by_turn_available=bool(provider in ROAD_PROVIDERS and len(steps) > 1),
        )
    )


@app.post("/api/v1/route-plans/active/evaluate", response_model=ActiveRouteEvaluationResponse,
          tags=["routing"],
          summary="Re-evaluate an in-progress route from the driver's current position and SoC (AC 2.1.1)")
async def evaluate_active_route(
    body: ActiveRouteEvaluationRequest,
    user: dict = Depends(security.current_user)
) -> ActiveRouteEvaluationResponse:
    """AC 2.1.1: warn mid-route and offer nearby stations to add as a stop.

    Given the driver is on an active route, this recomputes the projection from
    where they actually are and how much charge they actually have. When the
    projection drops below the reserve it returns a triggered warning plus the
    ranked stations that could be added as a stop. Adding the stop and
    dismissing the alert are client actions.
    """
    ev_model_id, ev_model = _planning_vehicle(user, body.ev_model_id, body.vehicle)

    battery_kwh = float(ev_model["battery_kwh"])
    efficiency_wh_per_km = float(ev_model.get("efficiency_wh_per_km") or 180.0)
    efficiency_source = ev_model.get("efficiency_source") or "dataset"
    max_dc_charge_kw = ev_model.get("max_dc_charge_kw")

    from api.services.routing_service import (
        ROAD_PROVIDERS, RouteUnavailable, RoutingService, straight_line_route,
    )
    from api.services.energy_estimator import (
        MIN_RESERVE_KM, TIGHT_MARGIN_SOC_PCT, EnergyEstimator,
        effective_reserve_soc_pct, reserve_km_for_soc_pct,
    )
    from api.services.connector_compat import vehicle_connector_profile
    from api.services.stop_ranker import StopRanker

    connector_profile = vehicle_connector_profile(
        ev_model.get("fast_charge_port"), user.get("main_connector_type")
    )

    current_pos = (round(body.current_position.latitude, 4), round(body.current_position.longitude, 4))
    dest_pos = (round(body.destination.latitude, 4), round(body.destination.longitude, 4))

    routing_service = RoutingService()
    energy_estimator = EnergyEstimator()
    stop_ranker = StopRanker(energy_estimator, routing_service)

    reserve_pct = effective_reserve_soc_pct(
        battery_kwh, efficiency_wh_per_km, body.minimum_arrival_soc_pct
    )
    reserve_km = reserve_km_for_soc_pct(battery_kwh, efficiency_wh_per_km, reserve_pct)

    navigation_start_soc = (
        body.navigation_start_soc_pct
        if body.navigation_start_soc_pct is not None
        else body.current_soc_pct
    )
    if navigation_start_soc is None:
        raise HTTPException(
            status_code=422,
            detail="navigation_start_soc_pct or current_soc_pct is required",
        )
    estimated_current = energy_estimator.estimate_current_soc(
        battery_kwh=battery_kwh,
        efficiency_wh_per_km=efficiency_wh_per_km,
        navigation_start_soc_pct=navigation_start_soc,
        cumulative_distance_travelled_km=body.cumulative_distance_travelled_km,
    )
    if body.measured_current_soc_pct is not None:
        current_soc_pct = min(float(navigation_start_soc), float(body.measured_current_soc_pct))
        remaining_energy_kwh = battery_kwh * current_soc_pct / 100.0
        current_soc_source = "vehicle_telemetry"
    elif body.navigation_start_soc_pct is not None:
        current_soc_pct = estimated_current.estimated_current_soc_pct
        remaining_energy_kwh = estimated_current.remaining_energy_kwh
        current_soc_source = "distance_estimate"
    else:
        current_soc_pct = float(body.current_soc_pct)
        remaining_energy_kwh = battery_kwh * current_soc_pct / 100.0
        current_soc_source = "legacy_current_soc"

    active_waypoints = None
    if body.active_waypoint_station_id:
        waypoint = repo.get_station(body.active_waypoint_station_id)
        if waypoint:
            active_waypoints = [(float(waypoint["latitude"]), float(waypoint["longitude"]))]

    # AC 2.1.1 / AC 2.4.2: a driver ALREADY ON THE ROAD must keep being evaluated.
    # Letting RouteUnavailable out of here turns a routing outage into a 503 that
    # withholds the remaining distance, the arrival projection, the below-reserve
    # warning AND the candidate stops from a driver at 12% -- precisely the moment
    # those two ACs exist to cover. A straight-line estimate is used instead, and
    # is LABELLED as degraded (assumptions.routing_provider / turn_by_turn_available
    # plus a 'routing_degraded' advisory) so the client can tell the driver that
    # navigation is approximate. POST /api/v1/route-plans keeps its 503: refusing
    # to PLAN is honest, refusing to keep watching a trip already under way is not.
    routing_degraded = False
    try:
        remaining_route = await routing_service.get_route(
            current_pos, dest_pos, waypoints=active_waypoints)
    except RouteUnavailable:
        logging.warning(
            "active route evaluation: road routing unavailable, falling back to a "
            "straight-line estimate", exc_info=True)
        routing_degraded = True
        remaining_route = straight_line_route(current_pos, dest_pos, waypoints=active_waypoints)
    remaining_km = remaining_route["distance_km"]
    routing_provider = remaining_route.get("provider")
    basis, scale = _distance_basis(remaining_route, current_pos, dest_pos)

    projection = energy_estimator.estimate_trip_energy(
        battery_kwh=battery_kwh,
        efficiency_wh_per_km=efficiency_wh_per_km,
        distance_km=remaining_km,
        current_soc_pct=current_soc_pct,
        minimum_arrival_soc_pct=reserve_pct,
    )

    route_status, margin_is_tight = _classify_route(
        projection.raw_arrival_soc_pct, reserve_pct, TIGHT_MARGIN_SOC_PCT
    )

    warning: Optional[RouteWarning] = None
    candidate_stops: list[RecommendedStop] = []

    if route_status == ROUTE_STATUS_CHARGING_REQUIRED:
        warning = _below_reserve_warning(projection.raw_arrival_soc_pct, reserve_pct)
        candidate_stops = await stop_ranker.rank_stops(
            origin=current_pos,
            destination=dest_pos,
            direct_distance_km=remaining_km,
            battery_kwh=battery_kwh,
            efficiency_wh_per_km=efficiency_wh_per_km,
            current_soc_pct=current_soc_pct,
            minimum_arrival_soc_pct=reserve_pct,
            max_dc_charge_kw=max_dc_charge_kw,
            maximum_detour_km=body.maximum_detour_km,
            connector_profile=connector_profile,
            distance_scale_factor=scale,
            distance_basis=basis,
            limit=body.max_candidate_stops,
        )
        if not candidate_stops:
            route_status = ROUTE_STATUS_NO_STATION
            warning = RouteWarning(
                triggered=True,
                code="no_suitable_station",
                severity="critical",
                message=(
                    "Battery will drop below your reserve before arrival and no reachable station "
                    "ahead has a free connector your vehicle can use. Choose another route, widen "
                    "your detour allowance, or charge before continuing."
                ),
                projected_arrival_soc_pct=round(projection.raw_arrival_soc_pct, 1),
                reserve_soc_pct=round(reserve_pct, 1),
                shortfall_soc_pct=round(max(0.0, reserve_pct - projection.raw_arrival_soc_pct), 1),
                can_dismiss=True,
                suggested_actions=list(NO_STATION_SUGGESTED_ACTIONS),
            )
    elif margin_is_tight:
        warning = RouteWarning(
            triggered=False,
            code="battery_margin_tight",
            severity="info",
            message=(
                f"You should arrive with about {projection.estimated_arrival_soc_pct:.0f}%, "
                f"just above your {reserve_pct:.0f}% reserve."
            ),
            projected_arrival_soc_pct=round(projection.estimated_arrival_soc_pct, 1),
            reserve_soc_pct=round(reserve_pct, 1),
            shortfall_soc_pct=0.0,
            can_dismiss=True,
        )

    computed_at = datetime.now(timezone.utc)

    # AC 2.1.1 / AC 2.4.2: a driver ALREADY ON AN ACTIVE ROUTE must keep getting
    # battery re-evaluations. The planning-time service-area gate (AC 2.2.2)
    # therefore must NOT run here -- it would turn a boundary into a mid-journey
    # kill switch and 422 the driver the moment they crossed it, which is exactly
    # the moment those two ACs exist to cover. The condition is surfaced as an
    # advisory instead: flagged, named per field, and carried in `advisories` so
    # it cannot displace the battery `warning`.
    out_of_area_fields = service_area.outside_fields([
        ("current_position", body.current_position.latitude, body.current_position.longitude),
        ("destination", body.destination.latitude, body.destination.longitude),
    ])
    advisories = []
    # Degraded routing is an advisory, NEVER the `warning` slot: `warning` stays
    # reserved for the battery projection so both can fire at the same time.
    if routing_degraded:
        advisories.append(RouteWarning(
            triggered=True,
            code=WARNING_ROUTING_DEGRADED,
            severity="warning",
            message=ROUTING_DEGRADED_MESSAGE,
            projected_arrival_soc_pct=round(projection.estimated_arrival_soc_pct, 1),
            reserve_soc_pct=round(reserve_pct, 1),
            shortfall_soc_pct=0.0,
            can_dismiss=True,
        ))
    if out_of_area_fields:
        advisories.append(RouteWarning(
            triggered=True,
            code=WARNING_OUT_OF_SERVICE_AREA,
            severity="info",
            message=service_area.advisory_message(out_of_area_fields),
            projected_arrival_soc_pct=round(projection.estimated_arrival_soc_pct, 1),
            reserve_soc_pct=round(reserve_pct, 1),
            shortfall_soc_pct=0.0,
            can_dismiss=True,
            suggested_actions=[SUGGEST_RETURN_TO_SERVICE_AREA],
        ))

    return ActiveRouteEvaluationResponse(
        route_plan_id=body.route_plan_id,
        route_status=route_status,
        margin_is_tight=margin_is_tight,
        warning=warning,
        service_area=ServiceAreaSummary(**service_area.describe()),
        out_of_service_area=bool(out_of_area_fields),
        out_of_service_area_fields=out_of_area_fields,
        advisories=advisories,
        remaining_distance_km=remaining_km,
        remaining_duration_minutes=remaining_route["duration_minutes"],
        estimated_energy_kwh=projection.estimated_trip_energy_kwh,
        estimated_current_soc_pct=round(current_soc_pct, 1),
        current_soc_source=current_soc_source,
        remaining_energy_kwh=round(remaining_energy_kwh, 2),
        energy_model_version="spec-v2",
        energy_assumptions={
            "efficiency_wh_per_km": efficiency_wh_per_km,
            "efficiency_source": efficiency_source,
            "traffic_factor": 1.0,
            "traffic_source": "unavailable_default",
            "elevation_factor": 1.0,
            "elevation_source": "unavailable_default",
            "weather_factor": 1.0,
            "weather_source": "unavailable_default",
            "auxiliary_power_kw": None,
            "auxiliary_source": "configured_trip_energy",
            "auxiliary_energy_kwh": energy_estimator.auxiliary_energy_kwh,
            "route_adjustment_factor": energy_estimator.route_adjustment_factor,
            "route_adjustment_method": "fixed_fallback",
            "reserve_soc_pct": reserve_pct,
        },
        projected_arrival_soc_pct=projection.estimated_arrival_soc_pct,
        raw_projected_arrival_soc_pct=projection.raw_arrival_soc_pct,
        reserve_soc_pct=reserve_pct,
        effective_reserve_km=round(reserve_km, 1),
        distance_basis=basis,
        vehicle=_vehicle_summary(ev_model_id, ev_model, battery_kwh,
                                 efficiency_wh_per_km, efficiency_source),
        candidate_stops=candidate_stops,
        computed_at=computed_at,
        estimated_arrival_at=_eta(computed_at, remaining_route["duration_minutes"]),
        assumptions=RoutePlanAssumptions(
            reserve_soc_pct=reserve_pct,
            requested_reserve_soc_pct=body.minimum_arrival_soc_pct,
            effective_reserve_km=round(reserve_km, 1),
            minimum_reserve_km=MIN_RESERVE_KM,
            distance_basis=basis,
            vehicle_connector_types=list(connector_profile.types),
            connector_source=connector_profile.source,
            weather_applied=False,
            traffic_applied=False,
            connector_data_inferred=bool(connector_profile.inferred_types),
            energy_model_version="spec-v2",
            service_area=ServiceAreaSummary(**service_area.describe()),
            maximum_detour_km=body.maximum_detour_km,
            routing_provider=routing_provider,
            turn_by_turn_available=bool(
                routing_provider in ROAD_PROVIDERS
                and len(remaining_route.get("steps") or []) > 1),
        ),
    )


@app.delete("/api/v1/route-plans/{route_plan_id}", status_code=204, tags=["routing"],
            summary="End a route session and delete its temporary location data (AC 2.3.3)")
async def delete_route_plan(
    route_plan_id: str,
    user: dict = Depends(security.current_user),
) -> None:
    """AC 2.3.3: the trigger for "the session ended, delete the temporary history".

    Route plans are never persisted -- ``route_plan_id`` is an ephemeral string,
    there is no route-plan table and no user-position column anywhere in the
    schema -- so there is no stored trip to delete. What DOES briefly hold a
    location is the reverse-geocoding cache, whose key is the caller's own
    (coarsened) position.

    This used to call ``purge_expired()`` and nothing else, which was a no-op for
    the session that just ended: that call drops entries whose TTL has ALREADY
    elapsed, and the ending session's coordinates are precisely the ones still
    inside it. It now deletes this session's OWN entries, via the index the
    ``route_plan_id`` query parameter on ``/api/v1/geocoding/reverse`` builds up,
    and then sweeps anything else that has expired.

    Deleting is fail-safe in the privacy direction, so an unknown or already-torn
    -down ``route_plan_id`` is a successful 204 rather than a 404 -- the client
    must be able to call this on teardown without handling an error.

    Independently of this endpoint, the same entries are deleted no later than
    ``GEOCODING_REVERSE_CACHE_TTL_SECONDS`` (30 s) by the background sweeper
    started in the app lifespan, so the AC's bound does not depend on the client
    remembering to call it.
    """
    from api.services.geocoding_service import purge_expired, purge_session
    purge_session(route_plan_id)
    purge_expired()


def _enforce_geocoding_rate_limit(request: Request) -> None:
    """Budget the endpoints that proxy Nominatim, per caller AND overall.

    These endpoints are deliberately unauthenticated: EVFlow is a permanent demo
    whose demo password ships in the web bundle, so requiring a token would only
    add a step for an abuser while breaking the destination picker. The control
    that actually matters is volume, because the real failure mode is
    OpenStreetMap banning our egress IP and silently killing destination search.

    Two budgets, because either alone is easy to slip past: per client IP stops
    one caller looping, and a global budget caps what the whole deployment can
    send upstream no matter how many callers there are.
    """
    client_ip = request.client.host if request.client else "unknown"
    checks = (
        (f"geocoding:ip:{client_ip}", rate_limit.GEOCODING_RATE_LIMIT_REQUESTS),
        ("geocoding:global", rate_limit.GEOCODING_GLOBAL_RATE_LIMIT_REQUESTS),
    )
    for key, limit in checks:
        if not rate_limit.allow(key, limit, rate_limit.GEOCODING_RATE_LIMIT_WINDOW_SECONDS):
            # Neither the query nor any coordinate appears here: this line lands
            # in access/error logs (AC 2.3.2).
            logging.warning("geocoding rate limit hit (%s)", key.rsplit(":", 1)[0])
            raise HTTPException(
                429,
                f"too many geocoding requests; try again in "
                f"{int(rate_limit.GEOCODING_RATE_LIMIT_WINDOW_SECONDS)}s",
            )


@app.get("/api/v1/geocoding/search", response_model=GeocodingSearchResponse, tags=["routing"],
         summary="Search places and SPKLU stations for destination picker")
async def search_geocoding(
    request: Request,
    q: str = Query(..., min_length=2, description="Place or station search term"),
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    limit: int = Query(5, ge=1, le=10),
    in_service_area_only: bool = Query(
        False,
        description="Drop suggestions that POST /api/v1/route-plans would reject with a 422. "
                    "Off by default, because the station dataset is national and browsing "
                    "outside the configured service area is legitimate; every item carries "
                    "`in_service_area` either way, so a picker that cannot label them can "
                    "filter instead (AC 2.2.1 / AC 2.2.2)."),
) -> GeocodingSearchResponse:
    """Destination suggestions that never contradict the planner.

    Every item says whether the planner will accept it (`in_service_area`), and
    the response echoes the area itself (`service_area`), so the picker can never
    offer a destination that POST /api/v1/route-plans then refuses.
    """
    _enforce_geocoding_rate_limit(request)
    from api.services.geocoding_service import GeocodingService, round_coord
    # Round before the service sees them (privacy + caching, same as
    # /api/v1/route-plans). Raw coordinates are never logged.
    origin_lat = None if lat is None else round_coord(lat)
    origin_lon = None if lon is None else round_coord(lon)
    service = GeocodingService()
    try:
        return await service.search(query=q, origin_lat=origin_lat, origin_lon=origin_lon,
                                    limit=limit, in_service_area_only=in_service_area_only)
    except HTTPException:
        raise
    except Exception:
        logging.exception("geocoding search failed")
        raise HTTPException(502, "geocoding provider unavailable")


@app.get("/api/v1/geocoding/reverse", tags=["routing"],
         summary="Reverse geocode coordinates to location name")
async def reverse_geocoding(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    route_plan_id: Optional[str] = Query(
        None,
        description="The route session this lookup belongs to. Supply it and "
                    "DELETE /api/v1/route-plans/{route_plan_id} deletes the temporary "
                    "location data this session created, at once rather than at TTL "
                    "(AC 2.3.3). Omit it and the data still expires on the 30-second "
                    "deadline, it just cannot be deleted early by session."),
) -> dict[str, str]:
    _enforce_geocoding_rate_limit(request)
    from api.services.geocoding_service import GeocodingService, REVERSE_COORD_PRECISION_DP, round_coord
    # The caller's live GPS fix: coarsen it here, before anything downstream can
    # see or record it.
    safe_lat = round_coord(lat, REVERSE_COORD_PRECISION_DP)
    safe_lon = round_coord(lon, REVERSE_COORD_PRECISION_DP)
    service = GeocodingService()
    try:
        return await service.reverse_search(lat=safe_lat, lon=safe_lon,
                                            session_id=route_plan_id)
    except HTTPException:
        raise
    except Exception:
        logging.exception("reverse geocoding failed")
        raise HTTPException(502, "geocoding provider unavailable")


# <Aidil> 2026-07-29
@app.get("/api/v1/stations/{station_id}/status", response_model=StationStatusResponse,
         tags=["stations"], summary="Get station real-time status and waiting time",
         responses={404: {"description": "Station not found"}})
def get_station_status(station_id: str) -> StationStatusResponse:
    if repo.get_station(station_id) is None:
        raise HTTPException(404, f"station '{station_id}' not found")
    return StationStatusResponse(**connectors_repo.get_station_realtime_status(station_id))


@app.get("/api/v1/stations/{station_id}/occupancy", response_model=StationOccupancyResponse,
         tags=["stations"], summary="Get station hourly occupancy data",
         responses={404: {"description": "Station not found"}})
def get_station_occupancy(station_id: str) -> StationOccupancyResponse:
    if repo.get_station(station_id) is None:
        raise HTTPException(404, f"station '{station_id}' not found")
    return StationOccupancyResponse(**repo.get_hourly_occupancy(station_id))
# </Aidil> 2026-07-29
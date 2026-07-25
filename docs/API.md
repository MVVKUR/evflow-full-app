# API Guide

The FastAPI application is defined in `backend-ev-flow/api/main.py`. Pydantic
models in `api/models.py` define request and response bodies.

For exact schemas and validation rules from a running instance, use:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

The default direct base URL is `http://localhost:8000`. The containerized web app
uses same-origin URLs such as `http://localhost:8080/api/v1/stations` through
nginx.

## Conventions

- API resources use the `/api/v1` prefix; `/health` is unversioned.
- JSON fields and query parameters use `snake_case`.
- Dates are ISO 8601 strings.
- Currency values are integer Indonesian rupiah (`*_idr`).
- Geographic inputs use `lat`, `lon`; GeoJSON coordinates use
  `[longitude, latitude]` as required by RFC 7946.
- Pagination responses use `limit` and `offset`.
- Repeated `connector_type` and `speed_tier` query parameters implement
  multi-select filters.
- Validation failures use FastAPI's HTTP 422 response format.

## Authentication

Protected endpoints require:

```http
Authorization: Bearer <access_token>
```

Tokens are returned by register and login. There is no refresh-token endpoint.
Password changes invalidate tokens issued before the change.

The Xendit webhook is a separate trust boundary and requires:

```http
X-Callback-Token: <XENDIT_CALLBACK_TOKEN>
```

## Current Operations

The source currently defines 33 route operations.

### System, Stations, And Metadata

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness, API version, and best-effort station count |
| `GET` | `/api/v1/stations` | Public | Filtered, paginated station list |
| `GET` | `/api/v1/stations/nearby` | Public | Distance-sorted stations or filter-only fallback |
| `GET` | `/api/v1/stations/{station_id}` | Public | One station by ID |
| `GET` | `/api/v1/stations.geojson` | Public | Station FeatureCollection for maps |
| `GET` | `/api/v1/stats` | Public | Station totals, source/province/tier counts, power summary |
| `GET` | `/api/v1/sources` | Public | Source counts |
| `GET` | `/api/v1/provinces` | Public | Province counts |
| `GET` | `/api/v1/cities` | Public | City counts, optionally filtered by province |
| `GET` | `/api/v1/connectors` | Public | Inferred connector-type counts |
| `GET` | `/api/v1/speed-tiers` | Public | Speed-tier definitions and counts |

`/health` always reports `status: "ok"`; it catches database errors and returns
`stations_loaded: 0`. Use a station query or `/stats` plus a database check for
readiness.

### Routing And Vehicle Catalogue

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/route` | Public | Shortest or fastest route to a station or coordinate |
| `GET` | `/api/v1/route/nearest-station` | Public | Nearest road-reachable station and optional range check |
| `GET` | `/api/v1/ev-models` | Public | Search and paginate the EV catalogue |
| `GET` | `/api/v1/ev-models/{model_id}` | Public | One EV model |

Route endpoints return 503 when the configured GraphML file is absent. Other API
groups do not depend on the routing graph.

### Authentication And Profile

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Public | Create a password account and return a bearer token |
| `POST` | `/api/v1/auth/login` | Public | Login by username or email |
| `POST` | `/api/v1/auth/forgot-password` | Public | Queue reset email for an eligible account |
| `POST` | `/api/v1/auth/reset-password` | Public | Consume a reset token and replace the password |
| `GET` | `/api/v1/auth/google/login` | Public | Redirect to Google authorization |
| `GET` | `/api/v1/auth/google/callback` | Public | Exchange Google code, create/find user, redirect with JWT |
| `GET` | `/api/v1/users/me` | Bearer | Fetch the current user profile |
| `PATCH` | `/api/v1/users/me` | Bearer | Update username, EV, connector, or location consent |

Registering or logging in requires `JWT_SECRET` to be configured. Forgot-password
returns 404 for an unknown email and 400 for a Google-only account; this behavior
reveals account existence and should be considered in threat modeling.

### Wallet And Xendit

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/wallet` | Bearer | Current user's wallet balance |
| `POST` | `/api/v1/wallet/topup` | Bearer | Create a hosted Xendit invoice |
| `GET` | `/api/v1/wallet/topups` | Bearer | Current user's recent top-ups |
| `GET` | `/api/v1/wallet/topups/{topup_id}` | Bearer | Top-up status; polls Xendit while pending |
| `POST` | `/api/v1/webhooks/xendit` | Callback token | Credit a paid invoice idempotently |

The minimum top-up request is 10,000 IDR. Status polling can credit a paid invoice
when a webhook cannot reach a local deployment. Both paths use the same
conditional update, so duplicate provider notifications do not double-credit.

### Charging

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/charging/quote` | Public | Price requested energy using backend tariff settings |
| `POST` | `/api/v1/charging/sessions` | Bearer | Debit the deposit and create an active session |
| `GET` | `/api/v1/charging/sessions` | Bearer | Current user's recent sessions |
| `GET` | `/api/v1/charging/sessions/{session_id}` | Bearer | Current user's session detail |
| `POST` | `/api/v1/charging/sessions/{session_id}/settle` | Bearer | Finalize and refund unused energy |

Starting a session returns 402 if the user's wallet cannot cover the quote. The
start transaction either debits the wallet and inserts the session together or
does neither. Settlement is idempotent and caps delivered energy at the purchased
amount.

## Station Queries

### List And GeoJSON Filters

`GET /api/v1/stations` accepts:

| Parameter | Meaning |
|---|---|
| `province` | Exact match, case-insensitive |
| `city` | Case-insensitive substring |
| `q` | Case-insensitive station-name substring |
| `min_power`, `max_power` | Inclusive kW bounds |
| `connector_type` | Repeatable connector selection |
| `speed_tier` | Repeatable `slow`, `medium`, `fast`, or `ultra_fast` selection |
| `bbox` | `minLon,minLat,maxLon,maxLat` |
| `limit` | 1 to 1,000; default 100 |
| `offset` | Non-negative page offset |

`GET /api/v1/stations.geojson` uses the same filters and a larger `limit` range.
Despite older documentation, the current routes do not expose a `source` query
parameter.

Repeated values are OR within one category. When both connector and speed are
present, the SQL requires one connector object at the station to satisfy both
conditions.

Example:

```bash
curl -G http://localhost:8000/api/v1/stations \
  --data-urlencode 'province=DKI Jakarta' \
  --data-urlencode 'connector_type=CCS2' \
  --data-urlencode 'speed_tier=fast' \
  --data-urlencode 'speed_tier=ultra_fast' \
  --data-urlencode 'limit=100'
```

### Nearby

`GET /api/v1/stations/nearby` accepts both `lat` and `lon`, or neither. Supplying
only one returns 422.

- With coordinates, PostGIS filters by `radius_km` and sorts by geographic
  distance.
- Without coordinates, it returns a regular filtered list without distance.
- Nearby filters are connector type, speed tier, minimum/maximum power, radius,
  and limit. Province, city, name, and bounding box are not accepted.

## Routing Queries

`GET /api/v1/route` requires `lat` and `lon`, plus either `station_id` or both
`dest_lat` and `dest_lon`. `weight=length` minimizes metres; `travel_time`
minimizes estimated seconds.

`GET /api/v1/route/nearest-station` requires origin coordinates. Range can be
provided in either form:

- `max_range_km=<remaining range>`; or
- `ev_model_id=<id>&current_soc=<0..100>`, which derives a safety-adjusted range.

The endpoint reports `within_range`; it does not suppress a station that is beyond
range.

## Workflow Examples

### Register And Fetch Profile

```bash
TOKEN=$(curl -fsS http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"developer","password":"development-only"}' \
  | jq -r .access_token)

curl -fsS http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN"
```

### Quote And Start Charging

```bash
curl -fsS http://localhost:8000/api/v1/charging/quote \
  -H 'Content-Type: application/json' \
  -d '{"energy_kwh":20}'

curl -fsS http://localhost:8000/api/v1/charging/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"station_id":"pln_spklu-1","energy_kwh":20}'
```

The second call requires a funded wallet.

## Error Semantics

| Status | Typical meaning |
|---|---|
| `400` | Invalid OAuth state, reset token, or account mode |
| `401` | Missing/invalid bearer token or invalid Xendit callback token |
| `402` | Wallet cannot cover a charging deposit |
| `404` | Resource or drivable route not found |
| `409` | Username conflict |
| `422` | Request validation or incompatible query parameters |
| `502` | Xendit or Google provider failure |
| `503` | Routing graph unavailable |

## Contract Maintenance

The dynamic OpenAPI document generated by the running app is authoritative. As of
the review date, the checked-in JSON/YAML snapshots contain 25 operations and omit
eight current operations: top-up detail, five charging operations, and two
password-reset operations.

Regenerate after any route or schema change:

```bash
cd backend-ev-flow
.venv/bin/python -m api.export_openapi
git diff -- openapi.json openapi.yaml
```

Frontend contracts under `frontend-evflow-app/packages/shared/src` are handwritten.
OpenAPI regeneration does not update them, so their request and response types must
be reviewed separately.

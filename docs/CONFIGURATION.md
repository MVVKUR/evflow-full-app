# Configuration Reference

EVFlow uses environment variables rather than a settings object. Backend modules
read most values at call time with `os.getenv`; the database engine and some file
paths are resolved when their modules are imported.

Never commit real secrets. Repository `.gitignore` excludes `.env` and `.env.*`
while retaining example files.

## Environment File Behavior

There are two distinct locations:

| File | Consumer |
|---|---|
| `backend-ev-flow/.env` | FastAPI container through `env_file`, or native Uvicorn through `--env-file` |
| root `.env` | Compose interpolation for `${...}` values only |

The root `compose.yaml` requires `backend-ev-flow/.env`. A root `.env` does not
replace it and does not automatically pass API secrets into the container.

For native Alembic, scripts, or pytest, explicitly export the backend file because
those commands do not load it:

```bash
cd backend-ev-flow
set -a
source .env
set +a
```

## Backend Core

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://evflow:evflow@localhost:5432/evflow` | Yes for useful API behavior | SQLAlchemy database URL; missing from current example files |
| `CORS_ALLOW_ORIGINS` | `*` | Production | Comma-separated browser origins; exact origins are safer for auth/write endpoints |
| `RAW_DIR` | `backend-ev-flow/data/raw` | Seed only | Directory containing the three active station snapshots |
| `EV_DATASET_CSV` | `data/raw/indonesia_ev_specs_pricing_2026.csv` | No | Preferred EV catalogue CSV; code falls back to `ev_dataset.zip` when needed |

`DATA_DIR`, `PROCESSED_DIR`, `OUTPUT_DIR`, and `FIGURES_DIR` appear in
`.env.example` for analysis work but are not read by the serving API.

## Authentication And Frontend Links

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `JWT_SECRET` | empty | Yes for register, login, bearer auth, and OAuth state | HS256 signing and OAuth state HMAC key |
| `JWT_EXPIRE_MINUTES` | `10080` | No | Access-token lifetime; default is seven days |
| `FRONTEND_URL` | empty | Required for complete integration flows | Base URL for password reset, Xendit redirects, and Google callback redirect |
| `GOOGLE_CLIENT_ID` | empty | Google only | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | empty | Google only | OAuth client secret |
| `GOOGLE_REDIRECT_URI` | empty | Google only | Backend callback URL registered with Google |

Use a long random `JWT_SECRET` in every environment. An empty secret fails token
creation or bearer validation; a placeholder shared across environments is not a
safe default.

The current frontend does not implement the Google callback route even when these
values are configured.

## Password Reset And SMTP

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `PASSWORD_RESET_TTL_MINUTES` | `60` | No | Reset token lifetime |
| `SMTP_HOST` | empty | Email only | Unset means delivery is disabled and the background task logs an error |
| `SMTP_PORT` | `587` | Email only | SMTP port |
| `SMTP_USER` | empty | Provider dependent | SMTP login |
| `SMTP_PASSWORD` | empty | Provider dependent | SMTP password, app password, or API key |
| `SMTP_FROM` | `SMTP_USER`, then `no-reply@localhost` | No | Message From address |
| `SMTP_SSL` | true on port 465, otherwise false | No | Force implicit TLS when truthy |
| `SMTP_STARTTLS` | true unless SSL is active | No | Enable STARTTLS when truthy |

Boolean values accept `1`, `true`, `yes`, or `on`, case-insensitively.

## Xendit And Wallet

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `XENDIT_SECRET_KEY` | empty | Top-up creation/status | Server-side Invoice API credential |
| `XENDIT_BASE_URL` | `https://api.xendit.co` | No | Provider base URL; useful for a mock service |
| `XENDIT_TIMEOUT_SECONDS` | `30` | No | Provider request timeout |
| `XENDIT_CALLBACK_TOKEN` | empty | Webhook | Expected `X-Callback-Token`; empty causes all webhook requests to be rejected |

`XENDIT_PUBLIC_KEY` appears in examples but is not read by current backend or
frontend source. Do not expose the secret key to any `VITE_` or `EXPO_PUBLIC_`
variable.

## Charging Pricing

| Variable | Default | Purpose |
|---|---|---|
| `CHARGING_BASE_RATE_IDR` | `2466` | Integer energy price per kWh |
| `CHARGING_ADMIN_FEE_IDR` | `2500` | Integer flat fee per charging session |

Quotes and settlement read these values at request time. Each session stores its
original quote fields, but the current settlement calculation recomputes the rate,
fee, and deposit from the environment. Do not change pricing while sessions are
active; this should be corrected before tariffs are updated dynamically.

## Routing

| Variable | Default | Purpose |
|---|---|---|
| `ROAD_GRAPH_PATH` | `data/processed/jakarta_drive.graphml` | Cached drivable road graph |
| `ROUTING_DEFAULT_SPEED_KMH` | `40` | Fallback edge speed used to estimate travel time |
| `ROUTING_RANGE_SAFETY_FACTOR` | `0.85` | Discount applied to manufacturer range |
| `JAKARTA_BBOX_SOUTH` | `-6.3760` | Graph/query area south bound |
| `JAKARTA_BBOX_WEST` | `106.6894` | Graph/query area west bound |
| `JAKARTA_BBOX_NORTH` | `-6.0890` | Graph/query area north bound |
| `JAKARTA_BBOX_EAST` | `106.9710` | Graph/query area east bound |

The module resolves graph path and numeric defaults at import. Restart API workers
after changing them. Callers can reload the graph cache in tests, but there is no
administrative reload endpoint.

`JAKARTA_CENTER_LAT`, `JAKARTA_CENTER_LON`, `OSRM_BASE_URL`, and `OSRM_PROFILE`
are present in the broad analysis template but are not used by the current serving
or routing code.

## Station And Analysis Inputs

The seed path consumes these files under `RAW_DIR`:

```text
_petaspklu_all.json
ocm_jakarta.json
osm_charging_jakarta.json
```

The following `.env.example` variables support historical or notebook acquisition
work and are not read by the serving API or current seed modules:

- `OCM_API_KEY`, `OCM_API_URL`, `OCM_COUNTRY_CODE`, `OCM_MAX_RESULTS`
- `OVERPASS_API_URL`
- `GEOFABRIK_JAVA_PBF_URL`, `GEOFABRIK_JAVA_PBF_PATH`
- `SPKLU_JAKARTA_PATH`, `BPS_JAKARTA_PATH`
- `KAGGLE_USERNAME`, `KAGGLE_KEY`, `KAGGLE_DATASET`, `KAGGLE_DATA_PATH`
- `REQUEST_TIMEOUT_SECONDS`, `USER_AGENT`

Keep analysis configuration separate from production secrets when the templates
are eventually split.

## Import Script

| Variable | Default | Purpose |
|---|---|---|
| `EVFLOW_DEPLOYED_API_BASE_URL` | `https://ev-flow-api.opensoft.id` | Source API used by `scripts.import_deployed_stations` |
| `EVFLOW_IMPORT_PAGE_SIZE` | `1000` | Page size for deployed station import |

The importer truncates local stations before inserting fetched rows. Point it only
at a trusted API with a compatible station schema.

## Frontend API URL

### Web

| Variable | Priority | Purpose |
|---|---|---|
| `VITE_EVFLOW_API_BASE_URL` | Canonical | Web API base URL at Vite build/start time |
| `VITE_API_BASE_URL` | Legacy alias | Backward-compatible fallback |
| `VITE_API_BASE` | Legacy alias | Backward-compatible fallback |

Resolution:

- Vite development with no override: `http://localhost:8000`.
- Production build with no override: `https://ev-flow-api.opensoft.id`.
- Value `/`: empty base string, producing same-origin `/api/v1/...` calls.

`VITE_` values are compiled into the browser bundle. They are public and changing
them requires a rebuild.

### Mobile

| Variable | Priority | Purpose |
|---|---|---|
| `EXPO_PUBLIC_EVFLOW_API_BASE_URL` | Canonical | Expo API base URL |
| `EXPO_PUBLIC_API_BASE_URL` | Legacy alias | Backward-compatible fallback |
| `EVFLOW_API_BASE_URL` | Legacy alias | Backward-compatible fallback |

In development with no override, the client extracts a local/LAN/emulator host
from Metro's bundle URL and uses port 8000. Non-local hosts, including Expo tunnel
hosts, fall back to the deployed API. Release builds also default to the deployed
API.

`EXPO_PUBLIC_` values are bundled and visible to users. Never place backend
secrets in them.

## Container Controls

| Variable | Default | Scope |
|---|---|---|
| `WEB_CONCURRENCY` | `2` | Uvicorn workers in both API Compose variants |
| `WEB_PORT` | `8080` | nginx host listen port in host-network Compose only |
| `NGINX_LISTEN_PORT` | `80` | nginx container listen port; Compose sets it where needed |
| `EVFLOW_API_UPSTREAM` | `http://api:8000` | nginx proxy target; host stack uses `127.0.0.1:8000` |

In root `compose.yaml`, explicit `DATABASE_URL`, `CORS_ALLOW_ORIGINS`, and
`WEB_CONCURRENCY` service values override the same keys from
`backend-ev-flow/.env`. Compose substitution for the last two reads root `.env`
or the invoking shell.

The host-network file enumerates variables into the API service rather than using
the full backend environment. Review it when adding runtime variables; SMTP,
pricing, and several routing/script settings are not currently forwarded there.

## Recommended Environment Profiles

**Local public-data development**

- Database URL, backend env file, and station seed.
- JWT secret if using demo login or any authenticated screen.
- No provider credentials required for station discovery.

**Full local product flow**

- All of the above.
- Xendit development secret and callback token.
- `FRONTEND_URL` matching Vite or nginx.
- SMTP credentials for password-reset delivery.

**Production**

- Unique high-entropy JWT and callback secrets.
- Exact CORS origins instead of `*`.
- Production provider credentials in a secret manager or protected env file.
- Same public origin or mutually consistent frontend, redirect, callback, and
  CORS URLs.
- Restricted database and API network exposure.

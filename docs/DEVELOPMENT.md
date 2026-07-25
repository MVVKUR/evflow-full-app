# Development Guide

This guide covers a clean checkout through a working API, web app, and mobile
development environment. Commands assume the repository root unless a preceding
`cd` changes it.

## Prerequisites

- Python 3.12, matching the backend runtime image and Sonar configuration.
- Node.js `20.19.4+` on the Node 20 line, or `22.12+`. Vite 8 and React Native
  impose these lower bounds.
- npm. The frontend manifest names Yarn, but the repository lockfiles, scripts,
  CI-related commands, and container builds currently use npm.
- PostgreSQL 16 with PostGIS, or Podman/Docker with Compose support.
- Android Studio for Android emulator work and Xcode on macOS for iOS work.

## Install Dependencies

The root and frontend are separate npm installations. The root install contains
only orchestration tooling; it does not install frontend workspaces.

```bash
npm ci
npm --prefix frontend-evflow-app ci

cd backend-ev-flow
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-api.txt "pytest>=8"
cp .env.example .env
cd ..
```

`requirements-api.txt` is the serving API dependency set. Install the larger
analysis set in addition to it only for notebooks, geospatial analysis, or road
graph generation:

```bash
backend-ev-flow/.venv/bin/python -m pip install -r backend-ev-flow/requirements.txt
```

Do not use `requirements.txt` alone for the current API; it omits auth runtime
packages such as bcrypt and PyJWT.

## Configure The Backend

Edit `backend-ev-flow/.env` before using authenticated flows. At minimum:

```dotenv
DATABASE_URL=postgresql+psycopg://evflow:evflow@localhost:5432/evflow
JWT_SECRET=replace-with-a-long-random-secret
FRONTEND_URL=http://localhost:5173
```

Generate a suitable development JWT secret with `openssl rand -hex 32`. Xendit,
Google, and SMTP values are optional until those integrations are exercised. See
[Configuration](CONFIGURATION.md) for the complete inventory.

Application modules read `os.getenv`; they do not load `.env` themselves.
Uvicorn receives the file through `--env-file`, while Alembic, seed scripts, and
pytest need variables exported into their process:

```bash
cd backend-ev-flow
set -a
source .env
set +a
```

Run that export in each new shell used for migrations, data scripts, or DB-backed
tests.

## Option A: Full Stack In Containers

This is the shortest path to PostGIS, the API, and the web app. The root Compose
file explicitly requires `backend-ev-flow/.env`, even for values that remain
optional.

```bash
cp backend-ev-flow/.env.example backend-ev-flow/.env  # once, if not already done
# Edit backend-ev-flow/.env and replace JWT_SECRET.

podman compose -f compose.yaml build
podman compose -f compose.yaml up -d db
until podman compose -f compose.yaml exec -T db pg_isready -U evflow -d evflow; do sleep 2; done
podman compose -f compose.yaml run --rm api alembic upgrade head
podman compose -f compose.yaml run --rm api python -m scripts.seed_db
podman compose -f compose.yaml up -d api web
```

Docker Compose can be used with the same file by replacing `podman compose` with
`docker compose`.

Services:

| URL or port | Service |
|---|---|
| `http://localhost:8080` | nginx-served web app |
| `http://localhost:8080/api/v1/...` | API through nginx |
| `http://localhost:8000` | Direct FastAPI service |
| `http://localhost:8000/docs` | Swagger UI |
| internal `5432` | PostGIS; not published by the root stack |

Check both liveness and database-backed behavior:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8080/api/v1/stats
bash backend-ev-flow/scripts/smoke_test.sh http://localhost:8080
```

`/health` is liveness only. It still returns HTTP 200 with
`stations_loaded: 0` when the database query fails.

## Option B: Native Development

Start only the database in a container:

```bash
podman compose -f compose.yaml up -d db
```

Export `backend-ev-flow/.env`, migrate, and seed:

```bash
cd backend-ev-flow
set -a; source .env; set +a
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_db
cd ..
```

Then use the root convenience command:

```bash
npm run dev
```

It starts Uvicorn on port 8000 and Vite on its default port, normally 5173. The
root scripts hardcode `backend-ev-flow/.venv`, so creating that exact virtualenv
path is required.

The services can also be run independently:

```bash
cd backend-ev-flow
.venv/bin/python -m uvicorn api.main:app \
  --reload --env-file .env --host 0.0.0.0 --port 8000
```

```bash
npm --prefix frontend-evflow-app run web
```

## Mobile Development

```bash
npm --prefix frontend-evflow-app run mobile
npm --prefix frontend-evflow-app run mobile:lan
npm --prefix frontend-evflow-app run mobile:tunnel
npm --prefix frontend-evflow-app run mobile:android
npm --prefix frontend-evflow-app run mobile:ios
```

In development, the native API client derives the Metro bundle host and uses port
8000. This lets a physical device on the same LAN reach the development machine.
Tunnel mode cannot route back to that machine and therefore falls back to the
deployed API unless `EXPO_PUBLIC_EVFLOW_API_BASE_URL` is set explicitly.

Browser camera and geolocation access require HTTPS or localhost. A web app opened
over plain LAN HTTP is not a secure browser context even when the API is reachable.

## Database And Data Workflows

Migrations are hand-written because Alembic has no ORM metadata configured for
autogeneration.

```bash
cd backend-ev-flow
.venv/bin/alembic current
.venv/bin/alembic heads
.venv/bin/alembic upgrade head
```

Station seeding is destructive only to the `stations` table. It normalizes the
three raw JSON sources, infers connectors, merges points within 75 metres, then
truncates and reloads the table:

```bash
.venv/bin/python -m scripts.seed_db
```

The current committed inputs contain 3,569 normalized rows and produce 2,931
deduplicated stations. Treat this as a snapshot, not an invariant; use `/health`
or `/api/v1/stats` for the active database count.

To replace local stations from a deployed API, use the importer. It also truncates
the local station table before inserting fetched rows:

```bash
.venv/bin/python -m scripts.import_deployed_stations
```

Routing is optional. Building the graph needs the heavy requirements and network
access to OpenStreetMap:

```bash
.venv/bin/python scripts/build_road_graph.py
```

The output is `data/processed/jakarta_drive.graphml`. Without it, route endpoints
return 503 while station, auth, wallet, and charging endpoints continue to work.

## Quality Commands

```bash
npm run frontend:typecheck
npm run frontend:build
npm run backend:test
npm test
```

Backend DB tests run only when `DATABASE_URL` is present in pytest's process
environment. Without it they are skipped, not failed. Use a disposable migrated
database because integration tests write users, wallets, top-ups, sessions, and
station state.

The frontend currently has typecheck and production-build verification but no
unit, integration, E2E, lint, or formatter command. The smoke script covers public
discovery and routing endpoints only; it does not cover authenticated or write
flows. See [Project Status](PROJECT_STATUS.md) for current gaps.

## Change Workflows

When adding a backend endpoint:

1. Add or update Pydantic models in `backend-ev-flow/api/models.py`.
2. Keep SQL in the appropriate `*_repo.py` module.
3. Add the route in `api/main.py` with its access rule and response model.
4. Add focused tests, including an authenticated DB test for protected writes.
5. Update `docs/API.md` and regenerate static OpenAPI snapshots.
6. Update handwritten client types/functions under `packages/shared/src/`.

When changing the database:

1. Add the next linear migration under `backend-ev-flow/alembic/versions/`.
2. Write both upgrade and downgrade paths where rollback is safe.
3. Test against an empty database and one upgraded from the previous revision.
4. Document any required seed, backfill, backup, or deployment ordering.

When adding frontend functionality:

1. Keep platform entrypoints thin; product flows belong in `packages/features`.
2. Put API/session/domain helpers in `packages/shared` and reusable primitives in
   `packages/ui`.
3. Use `.web.tsx` and `.native.tsx` only when platform APIs truly differ.
4. Update `AppRoutes.tsx` and document reload/deep-link behavior for new routes.
5. Run typecheck and the web build; verify both Expo and browser behavior for a
   platform-specific change.

## Troubleshooting

**Root `npm run dev` cannot find Python**

Create `backend-ev-flow/.venv`; root scripts call `.venv/bin/python` directly.

**Alembic or pytest uses the wrong database**

Export `.env` into the current shell. Copying it is insufficient for commands that
do not use Uvicorn's `--env-file` option.

**`/health` is green but station endpoints fail**

Check `pg_isready`, `/api/v1/stats`, migrations, and seed state. `/health` masks DB
query failures as a zero station count.

**Frontend calls the deployed API unexpectedly**

Check the console's resolved URL and set the canonical web or mobile override from
[Configuration](CONFIGURATION.md). Expo tunnel mode intentionally falls back to
the deployed API.

**Web requests fail with CORS errors**

Set `CORS_ALLOW_ORIGINS` to the exact frontend origin, or use the same-origin nginx
stack at port 8080.

**Routing returns 503**

Build or mount the GraphML file at `ROAD_GRAPH_PATH`. This is independent from
PostGIS station seeding.

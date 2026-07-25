# EVFlow Fullstack

[![Quality Gate Status](https://sonarcube.opensoft.id/api/project_badges/measure?project=evflow-full-app&metric=alert_status)](https://sonarcube.opensoft.id/dashboard?id=evflow-full-app)

EVFlow combines an Indonesia EV charging-station API with shared web and mobile
driver experiences. The repository includes PostGIS station discovery, optional
road routing, account/profile management, user wallets, Xendit top-ups, charging
accounting, a Vite web app, and an Expo mobile app.

## Repository

```text
backend-ev-flow/        FastAPI, PostgreSQL/PostGIS, Alembic, data pipeline, tests
frontend-evflow-app/    React, React Native, Expo, Vite, shared workspaces
docs/                   Current developer and operational documentation
sonarqube/              Optional local SonarQube stack
compose.yaml            PostGIS + API + nginx web stack
```

## Documentation

Start with [the documentation index](docs/README.md).

- [Development setup](docs/DEVELOPMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API guide](docs/API.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [Operations](docs/OPERATIONS.md)
- [Project status and known gaps](docs/PROJECT_STATUS.md)

## Container Quickstart

Prerequisites are Podman or Docker with Compose support. Create the backend env
file because the root Compose stack explicitly loads it:

```bash
cp backend-ev-flow/.env.example backend-ev-flow/.env
# Edit backend-ev-flow/.env and replace JWT_SECRET before using login flows.

podman compose -f compose.yaml build
podman compose -f compose.yaml up -d db
until podman compose -f compose.yaml exec -T db pg_isready -U evflow -d evflow; do sleep 2; done
podman compose -f compose.yaml run --rm api alembic upgrade head
podman compose -f compose.yaml run --rm api python -m scripts.seed_db
podman compose -f compose.yaml up -d api web
```

Open:

- Web app: `http://localhost:8080`
- Direct API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

Verify database-backed behavior, not only liveness:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8080/api/v1/stats
```

`/health` returns HTTP 200 even when its database query fails, with a zero station
count. See [Operations](docs/OPERATIONS.md) for readiness and deployment checks.

## Native Development Summary

Use Python 3.12 and Node `20.19.4+` or `22.12+`.

```bash
npm ci
npm --prefix frontend-evflow-app ci

cd backend-ev-flow
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt "pytest>=8"
cp .env.example .env
```

Add `DATABASE_URL`, replace `JWT_SECRET`, start or connect to PostGIS, then export
the env file before migration and seeding:

```bash
set -a; source .env; set +a
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_db
cd ..
npm run dev
```

The root development command starts Uvicorn on port 8000 and Vite on its default
port. Full clean-checkout instructions and mobile commands are in
[Development](docs/DEVELOPMENT.md).

## Root Commands

```bash
npm run dev
npm run backend:test
npm run frontend:typecheck
npm run frontend:build
npm test
npm run build
```

Root backend commands assume `backend-ev-flow/.venv` already exists. Root frontend
commands assume dependencies were installed under `frontend-evflow-app`.

## Current Scope

The station, auth, wallet, and charging accounting backends are implemented. Some
user-facing areas remain prototypes: Google OAuth lacks its frontend callback,
route planning is not connected to the backend, charger/QR telemetry is simulated,
and most business-planner metrics are static. See
[Project Status](docs/PROJECT_STATUS.md) before planning work from historical
specifications.

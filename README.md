# EVFlow Fullstack

Monorepo for the EVFlow backend and frontend. The folders remain separate deployable apps, but they now live in one Git repository so API/frontend changes can be versioned together.

## Structure

```text
backend-ev-flow/        FastAPI + PostGIS backend
frontend-evflow-app/    React, React Native, and Vite frontend
```

## Backend

The backend is a FastAPI app. See `backend-ev-flow/API_README.md` and `backend-ev-flow/FRONTEND_API.md` for the API contract.

```bash
cd backend-ev-flow
pip install -r requirements-api.txt
uvicorn api.main:app --reload --port 8000
```

Local backend station endpoints require a PostGIS database, migrations, and seed data:

```bash
cd backend-ev-flow
alembic upgrade head
python -m scripts.seed_db
```

## Frontend

API base URL resolution:

- **Dev** (`npm run web`, `expo start`): defaults to the local backend — `http://localhost:8000` on web; on mobile the dev-machine host is derived from the Metro bundle URL, so physical devices use your LAN IP automatically (the dev backend listens on `0.0.0.0` for this). In `expo start --tunnel` mode the bundle host is a public tunnel that cannot reach your machine, so mobile falls back to the deployed API unless the override below is set. The resolved URL is logged to the console.
- **Production builds**: default to the deployed API at `https://ev-flow-api.opensoft.id`.
- **Override** (either direction, e.g. to use the deployed API in dev without a local backend):

```bash
VITE_EVFLOW_API_BASE_URL=https://ev-flow-api.opensoft.id          # web
EXPO_PUBLIC_EVFLOW_API_BASE_URL=https://ev-flow-api.opensoft.id   # mobile
```

Install and run:

```bash
cd frontend-evflow-app
npm install
npm run web
```

## Run with Podman (full stack in containers)

`compose.yaml` at the repo root builds and runs PostGIS, the FastAPI backend, and the nginx-served web frontend:

```bash
podman compose up -d --build
podman compose exec api alembic upgrade head        # once: schema
podman compose exec api python -m scripts.seed_db   # once: station data
open http://localhost:8080                          # web UI
curl http://localhost:8080/api/v1/stats             # API via the nginx proxy
```

The web bundle is built with `VITE_EVFLOW_API_BASE_URL=/`, meaning same-origin: the browser calls `/api/v1/...` on the web origin and nginx forwards it to the `api` container, so no CORS configuration or hardcoded API host is needed. Secrets/tuning are optional — copy `backend-ev-flow/.env.deploy.example` to `.env` next to `compose.yaml`.

For LXC/OpenVZ VPSes where Podman's bridge networking fails with `ip_tables`, use
`backend-ev-flow/podman-compose.yml`; it runs the API and web frontend with host networking
(see `backend-ev-flow/DEPLOY.md`).

## Root Commands

```bash
npm install            # once: installs root tooling (concurrently)
npm run dev            # start backend (uvicorn :8000) + web frontend together
npm run backend:test
npm run frontend:typecheck
npm run frontend:build
npm test
```

These root scripts are conveniences only; backend and frontend can still be run directly from their own folders.

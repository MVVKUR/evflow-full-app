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

The frontend defaults to the deployed API at `https://ev-flow-api.opensoft.id`.

For local backend testing, set one of:

```bash
VITE_EVFLOW_API_BASE_URL=http://localhost:8000
EXPO_PUBLIC_EVFLOW_API_BASE_URL=http://localhost:8000
```

Install and run:

```bash
cd frontend-evflow-app
npm install
npm run web
```

## Root Commands

```bash
npm run backend:test
npm run frontend:typecheck
npm run frontend:build
npm test
```

These root scripts are conveniences only; backend and frontend can still be run directly from their own folders.

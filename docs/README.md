# EVFlow Documentation

This directory is the current developer documentation for the EVFlow full-stack
repository. It was reviewed against the source at commit `247b89b` on 2026-07-22.

## Start Here

| Document | Use it for |
|---|---|
| [Development](DEVELOPMENT.md) | Clean-checkout setup, local services, common workflows, and troubleshooting |
| [Architecture](ARCHITECTURE.md) | Runtime components, module boundaries, persistence, and end-to-end data flows |
| [API](API.md) | Current HTTP operations, authentication rules, filters, and workflow contracts |
| [Configuration](CONFIGURATION.md) | Backend, frontend, script, and container environment variables |
| [Operations](OPERATIONS.md) | Container topology, deployment, migrations, backups, logging, and readiness checks |
| [Project Status](PROJECT_STATUS.md) | Implemented features, prototypes, known gaps, verification, and recommended priorities |

## Repository Map

```text
evflow-fullstack/
  backend-ev-flow/       FastAPI, PostGIS access, Alembic, data tooling, tests
  frontend-evflow-app/   Vite web app, Expo mobile app, shared TypeScript packages
  docs/                  Current cross-project developer documentation
  sonarqube/             Optional local SonarQube stack and scanner wrapper
  compose.yaml           PostGIS + API + nginx web stack
  package.json           Root convenience commands
```

## Sources Of Truth

When documentation and implementation disagree, use this order:

1. `backend-ev-flow/api/main.py` and `api/models.py` for the live HTTP contract.
2. `backend-ev-flow/alembic/versions/` for the database schema history.
3. `frontend-evflow-app/package.json` and workspace manifests for frontend commands
   and dependencies.
4. `compose.yaml` and the two `Containerfile` files for container behavior.
5. The documents in this directory for developer and operational guidance.

The API process exposes its generated contract at `/openapi.json`, `/docs`, and
`/redoc`. The checked-in `backend-ev-flow/openapi.json` and `openapi.yaml` are
snapshots and must be regenerated after endpoint or schema changes.

## Older Material

- `backend-ev-flow/FRONTEND_API.md` contains useful, detailed map examples, but it
  predates the current auth, wallet, charging, and connector implementations.
- `backend-ev-flow/API_README.md` is a legacy station-focused overview.
- `backend-ev-flow/DEPLOY.md` describes the older host-network VPS deployment.
  Use [Operations](OPERATIONS.md) for the current procedure and risks.
- `backend-ev-flow/docs/superpowers/` contains historical plans and design records.
  It explains past decisions but is not current runtime documentation.
- `backend-ev-flow/document.yaml` is the third-party Open Charge Map API
  specification, not the EVFlow API.
- `docs/INTERVIEW_PREP.md` is presentation material, not an operational guide.

## Documentation Maintenance

Update the relevant document in the same change when you:

- add or change an endpoint, request model, response model, or auth requirement;
- add an Alembic migration or change seed behavior;
- introduce an environment variable or external integration;
- add a frontend route, workspace, or platform-specific implementation;
- change a Compose service, port, health check, deployment step, or root command;
- replace a prototype flow with production behavior.

After an API contract change, regenerate and review the static snapshots:

```bash
cd backend-ev-flow
.venv/bin/python -m api.export_openapi
git diff -- openapi.json openapi.yaml
```

# Operations Guide

This guide covers the repository's two container topologies and the operational
steps missing from older deployment notes. Commands use Podman; Docker Compose can
use the root stack with equivalent syntax.

## Topologies

### Root Bridge Stack

`compose.yaml` is the preferred general-purpose topology.

| Service | Container behavior | Host exposure |
|---|---|---|
| `db` | PostGIS `16-3.4`, named volume, `pg_isready` health check | Not published |
| `api` | FastAPI/Uvicorn, waits for healthy DB, read-only data bind mount | `8000` |
| `web` | nginx SPA, proxies `/api/` and `/health` to `api` | `8080` |

The built web bundle uses `VITE_EVFLOW_API_BASE_URL=/`, so browser API calls stay
on the web origin and nginx proxies them internally.

### Host-Network VPS Stack

`backend-ev-flow/podman-compose.yml` exists for LXC/OpenVZ environments that block
container bridge/NAT setup.

| Service | Host port |
|---|---|
| PostgreSQL/PostGIS | `5432` |
| FastAPI | `8000` |
| nginx | `${WEB_PORT:-8080}` |

Host networking removes Compose DNS and network isolation. nginx therefore uses
`127.0.0.1:8000`. The file has no DB health check or API startup dependency.

Host networking does not guarantee that PostgreSQL or FastAPI is bound only to
loopback. Apply host firewall rules explicitly; a Cloudflare Tunnel does not close
directly reachable ports.

## Initial Root-Stack Deployment

```bash
git clone <repository-url>
cd evflow-fullstack

cp backend-ev-flow/.env.example backend-ev-flow/.env
# Replace JWT_SECRET and configure integrations required by this environment.

podman compose -f compose.yaml build
podman compose -f compose.yaml up -d db
until podman compose -f compose.yaml exec -T db pg_isready -U evflow -d evflow; do sleep 2; done
podman compose -f compose.yaml run --rm api alembic upgrade head
podman compose -f compose.yaml run --rm api python -m scripts.seed_db
podman compose -f compose.yaml up -d api web
```

The three active raw station inputs are currently tracked. The road GraphML is not
tracked and must be built or supplied separately if routing is required.

Confirm service state:

```bash
podman compose -f compose.yaml ps
podman compose -f compose.yaml exec db pg_isready -U evflow -d evflow
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8080/api/v1/stats
bash backend-ev-flow/scripts/smoke_test.sh http://localhost:8080
```

The smoke script covers public discovery, catalogue, and routing behavior only.
Run explicit authenticated tests for login, profile, wallet, top-up, and charging
before a product release.

## Host-Network Deployment

Run from the backend directory because build contexts are relative to that file:

```bash
cd backend-ev-flow
cp .env.deploy.example .env
# Add every required secret and setting; the example is not complete.

podman compose -f podman-compose.yml build
podman compose -f podman-compose.yml up -d db
until podman compose -f podman-compose.yml exec -T db pg_isready -U evflow -d evflow; do sleep 2; done
podman compose -f podman-compose.yml run --rm api alembic upgrade head
podman compose -f podman-compose.yml run --rm api python -m scripts.seed_db
podman compose -f podman-compose.yml up -d api web
```

The host-network Compose file passes an enumerated environment list. It currently
does not forward SMTP, pricing, password-reset TTL, and several routing/import
settings. Compare it with [Configuration](CONFIGURATION.md) before deploying a
feature that needs those variables.

Verify firewall policy for 5432, 8000, and 8080. Only the intended reverse-proxy or
tunnel entrypoint should be public.

## Updating

Use this order for routine deployments:

```bash
git pull --ff-only
podman compose -f compose.yaml build
podman compose -f compose.yaml up -d db
until podman compose -f compose.yaml exec -T db pg_isready -U evflow -d evflow; do sleep 2; done
podman compose -f compose.yaml run --rm api alembic upgrade head
podman compose -f compose.yaml up -d api web
```

Because the current API does not migrate on startup, every deployment must check
and apply Alembic head. Review new migrations before production rollout.

Run station seeding only when raw inputs or normalization/deduplication behavior
changed:

```bash
podman compose -f compose.yaml exec api python -m scripts.seed_db
```

Seeding truncates and replaces `stations`. It does not clear users, wallets,
top-ups, sessions, or password-reset tokens.

After updating:

```bash
podman compose -f compose.yaml exec api alembic current
curl -fsS http://localhost:8080/api/v1/stats
bash backend-ev-flow/scripts/smoke_test.sh http://localhost:8080
```

## Database Backup And Restore

The named Postgres volume is the only durable application state in the root stack.
Back it up before migrations, credential changes, or destructive maintenance.

Logical backup:

```bash
podman compose -f compose.yaml exec -T db \
  pg_dump -U evflow -d evflow --format=custom > evflow-$(date +%Y%m%d-%H%M%S).dump
```

Inspect a backup before relying on it:

```bash
pg_restore --list evflow-YYYYMMDD-HHMMSS.dump | head
```

Restore into an empty, disposable database first. A production restore is
destructive and should be run only with an explicit maintenance plan:

```bash
podman compose -f compose.yaml exec -T db \
  pg_restore -U evflow -d evflow --clean --if-exists < evflow-YYYYMMDD-HHMMSS.dump
```

Do not use `podman compose down -v` during normal operations. The `-v` flag deletes
the database volume.

## Rollback

Application rollback and schema rollback are separate decisions.

1. Keep the previous API and web image tags until the new release is verified.
2. Back up the database before upgrading.
3. Prefer an application rollback that remains compatible with the upgraded
   schema.
4. Run `alembic downgrade` only after reviewing the exact migration's data-loss
   behavior. Several migrations drop tables or columns on downgrade.
5. Restore a verified database backup when a safe downgrade does not exist.

The current Compose files use `latest` image tags. For repeatable releases, publish
immutable version or commit tags and deploy those tags.

## Logs And Diagnostics

```bash
podman compose -f compose.yaml logs --tail=200 api
podman compose -f compose.yaml logs --tail=200 web
podman compose -f compose.yaml logs --tail=200 db
podman compose -f compose.yaml logs -f api
```

Useful checks:

```bash
podman compose -f compose.yaml exec api alembic current
podman compose -f compose.yaml exec db pg_isready -U evflow -d evflow
curl -i http://localhost:8000/health
curl -i http://localhost:8000/api/v1/stats
curl -i http://localhost:8080/api/v1/stats
```

Interpretation:

- `/health` returning 200 proves that the process can answer, not that Postgres is
  ready.
- `pg_isready` proves the server accepts connections, not that migrations or seed
  data exist.
- `/api/v1/stats` exercises the API-to-database path and fails if the station table
  is unavailable.
- A route 503 normally means the GraphML file is missing, not that PostGIS is down.

## OpenAPI Drift Check

Generate the API snapshots in the native backend environment so the output is
written to tracked host files:

```bash
cd backend-ev-flow
.venv/bin/python -m api.export_openapi
cd ..
git diff --exit-code -- backend-ev-flow/openapi.json backend-ev-flow/openapi.yaml
```

## SonarQube

Local SonarQube is independent from the application stack:

```bash
podman compose -f sonarqube/compose.yaml up -d
curl -fsS http://localhost:9000/api/system/status
SONAR_TOKEN=<token> ./sonarqube/scan.sh
```

The scanner reads `sonar-project.properties`. Current GitHub Actions performs only
Sonar analysis; it does not run pytest, frontend typecheck/build, smoke tests, or
an OpenAPI drift check.

## Production Checklist

- Replace development JWT, callback, database, SMTP, Google, and Xendit secrets.
- Restrict `CORS_ALLOW_ORIGINS` to deployed browser origins.
- Restrict direct database and API ports with firewall policy.
- Put HTTPS in front of browser traffic; camera and geolocation require a secure
  context.
- Verify `FRONTEND_URL`, Google redirect URI, Xendit redirects, and webhook URL as
  one consistent public-origin design.
- Apply and verify Alembic head.
- Confirm station seed count and routing graph availability.
- Exercise an authenticated account, top-up sandbox payment, charging start, and
  settlement.
- Verify password-reset email delivery and expiry.
- Create and restore-test a database backup.
- Define rate limiting at the edge; the application currently has none.
- Pin deployable images and document the rollback target.

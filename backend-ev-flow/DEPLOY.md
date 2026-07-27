# Deploying EV-FLOW (Podman)

> **Legacy host-network deployment notes.** Use the current
> [operations guide](../docs/OPERATIONS.md) for monorepo paths, migration ordering,
> backups, readiness, environment behavior, and host-network exposure risks.

Runs PostGIS, the FastAPI backend, and the nginx-served web frontend with
**host networking**, fronted by a **Cloudflare Tunnel** for HTTPS.

## What the frontend hits

Once the tunnel is up, the public base URL is your tunnel hostname:

```
https://<your-domain>/                 web frontend
https://<your-domain>/api/v1/...      e.g. https://ev-flow-api.opensoft.id/api/v1/stations.geojson
https://<your-domain>/docs            Swagger UI
https://<your-domain>/openapi.json    machine-readable contract
```

Full endpoint contract + examples: [FRONTEND_API.md](FRONTEND_API.md).

## Why host networking

Many cheap VPSes are **LXC/OpenVZ containers**, not full VMs. Their kernel blocks the
iptables NAT that Podman's default bridge network needs, so `compose up` fails with an
`ip_tables: Operation not permitted` error. `network_mode: host` (in `podman-compose.yml`)
skips the bridge entirely. Postgres binds `localhost:5432`, the API binds `:8000`, and the
web UI binds `:8080` by default. Works on LXC and normal VMs alike. (Check your box with
`systemd-detect-virt`.)

## Prerequisites (on the VPS)

```bash
sudo dnf install -y podman podman-compose        # Fedora/RHEL
# sudo apt install -y podman podman-compose       # Ubuntu/Debian
```

## Deploy

> ## The deploy order is **migrate → ingest → seed**. All three, in that order.
>
> `alembic upgrade head` creates empty tables. **`python -m scripts.ingest_raw`
> is what puts the datasets into them** — it is the only place a dataset file is
> ever read. `python -m scripts.seed_db` then works purely database-to-database.
>
> Skipping the ingest does not fail quietly:
> * `scripts.seed_db` **refuses to run** ("raw_station_records is empty") rather
>   than delete every station and replace it with nothing, and
> * every `/api/v1/ev-models` request answers **503** naming the missing step,
>   because `api/evmodels.py` has no file fallback any more.

```bash
git clone <repo> && cd backend-ev-flow

# 1. Provide the dataset files (they stay on disk as the immutable source)
mkdir -p data/raw data/processed
#   put the 3 station snapshots in data/raw/:
#     _petaspklu_all.json   ocm_jakarta.json   osm_charging_jakarta.json
#   the 2 EV datasets ship inside the committed ev_dataset.zip:
#     indonesia_ev_specs_pricing_2026.csv   electric_vehicles_spec_2025.csv
#     (override either with EV_SPECS_LOCAL_CSV / EV_SPECS_GLOBAL_CSV)
#   (optional, for /route) build the road graph once on a machine with osmnx:
#     python scripts/build_road_graph.py   -> data/processed/jakarta_drive.graphml

# 2. (optional) configure
cp .env.deploy.example .env        # CORS_ALLOW_ORIGINS, WEB_CONCURRENCY

# 3. Build + run, then MIGRATE -> INGEST -> SEED (in this order)
podman compose up -d --build db api web
podman compose exec api alembic upgrade head          # 1/3 schema only, no data
podman compose exec api python -m scripts.ingest_raw  # 2/3 files -> tables
podman compose exec api python -m scripts.seed_db     # 3/3 tables -> stations
```

`ingest_raw` prints exactly what it loaded, and the expected numbers are:

```
raw_station_records   pln_spklu 3029, open_charge_map 527, osm 13   (3569 rows)
ev_models             60 local + 478 global - 3 shared ids = 535 models
seed_db               seeded 2931 stations, 6733 connectors
```

`seed_db` touches stations/connectors only. Demo logins and demo wallet balance
are opt-in: see `DEMO_USER_PASSWORD` / `SEED_DEMO_WALLET` in `.env.example`.
Leave them unset in production — the seeder then creates no login and no money.

```bash
# 4. Check it locally on the VPS
curl -s http://localhost:8000/health        # direct API
curl -s http://localhost:8080/health        # via web nginx proxy
curl -I http://localhost:8080               # web UI
podman logs -f ev-flow-api
```

> Security note: ports 5432 and 8000 should remain closed to the public. Expose the web
> service through the Cloudflare Tunnel on 8080; nginx forwards `/api/` to the API locally.

> Manage it with `podman compose up -d` / `down` / `ps`, or directly:
> `podman logs -f ev-flow-api`, `podman restart ev-flow-api`.

## HTTPS via Cloudflare Tunnel

No open ports, no iptables, ideal for LXC. In the Cloudflare Zero Trust dashboard
(Networks → Tunnels), create a tunnel, install its connector on the VPS, then add a
**Public Hostname**:

| Field | Value |
|---|---|
| Subdomain / Domain | e.g. `ev-flow-api` / `opensoft.id` |
| Path | **leave empty** (so all routes pass through) |
| Service Type | **HTTP** |
| Service URL | **`localhost:8080`** |

The frontend and API then share the same public origin, e.g. `https://ev-flow-api.opensoft.id`.
If you host the frontend somewhere else, run only `db api` and point the tunnel at
`localhost:8000` as an API-only deployment.

## Updating

```bash
git pull
podman compose up -d --build       # rebuilds + restarts
podman compose exec api alembic upgrade head          # 1/3 if there are new migrations

# refresh dataset data: replace the files, then re-run BOTH steps, in order
podman compose exec api python -m scripts.ingest_raw  # 2/3 re-reads the files
podman compose exec api python -m scripts.seed_db     # 3/3 re-dedupes into stations
```

Both are idempotent and safe to re-run:

* `ingest_raw` replaces each staged snapshot in one transaction, so running it
  twice leaves the same rows in the same order. It upserts `ev_models` by id and
  prunes models that left the datasets — **except** any model a user still
  references (`users.ev_model_id` has a real FK), which it keeps and reports.
* `seed_db` never resets an existing demo password and never re-grants wallet
  balance (a grant is written once, together with its topups ledger row).

## Keep it running after a reboot

```bash
loginctl enable-linger $USER       # lets the restart=unless-stopped container come back
```

## Pre-public checklist

- [x] Slim image, runs as non-root.
- [x] HTTPS via Cloudflare Tunnel.
- [x] CORS configurable (`CORS_ALLOW_ORIGINS`); `*` is OK for read-only public data.
- [x] ReDoS fixed: `q`/`city` searches are literal (no regex injection / 500s).
- [ ] Station snapshots present in `data/raw/` **and** `python -m scripts.ingest_raw`
      run after `alembic upgrade head` (else `seed_db` refuses and `/health` shows
      `stations_loaded: 0`).
- [ ] `python -m scripts.ingest_raw` reports 535 EV models (else `/api/v1/ev-models`
      answers 503 — the catalogue is the `ev_models` table, with no file fallback).
- [ ] Rate limiting: the API has none; Cloudflare (in front of the tunnel) can add it.
- [ ] Routing graph in `data/processed/` if you want `/route` (otherwise it returns 503).

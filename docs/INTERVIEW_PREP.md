# EVFlow — Technical Interview Prep

> Study guide for explaining EVFlow to a mentor, emphasizing data engineering and architecture.
> Every fact below is grounded in the actual code (file names, functions, tables, endpoints are real).

## 30-second pitch

EVFlow is an EV charging-station discovery, routing, and top-up payment app for Indonesia, focused on the Jabodetabek (Greater Jakarta) metro. Its core engineering value is **data fusion**: it unifies three heterogeneous, messy public sources — PLN's official SPKLU registry, the crowd-sourced Open Charge Map, and OpenStreetMap — into a single deduplicated inventory of **1,147 physical stations** stored in PostGIS, then serves them over a versioned FastAPI REST surface that does nearby search, GeoJSON for maps, and battery-aware shortest-path routing over an offline-built road graph. It ships as three containers (PostGIS, FastAPI, nginx+Vite build) feeding a cross-platform React/React Native frontend from one shared API client.

**Stack**
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy Core (`text()`, no ORM), Alembic migrations
- **Data/DB:** PostgreSQL + **PostGIS** (`geometry(Point,4326)`, GiST + GIN indexes, JSONB connectors)
- **Geo/routing:** OSMnx (offline graph build) → GraphML → NetworkX + hand-rolled Dijkstra; numpy haversine snapping
- **Integrations:** Xendit (top-ups/webhooks), Google OAuth, JWT (HS256) + bcrypt
- **Frontend:** npm workspaces monorepo — Vite + React 19 (web), Expo 54 + React Native 0.81 (mobile), shared `@evflow/shared` `fetch`-based API client
- **Deploy:** Podman/Docker Compose, nginx reverse proxy, Cloudflare Tunnel + host networking on a cheap LXC VPS

---

## System architecture at a glance

```
   DATA SOURCES (static JSON in /data/raw/)                OFFLINE BUILD (one-time)
 ┌─────────────────────────────────────────┐         ┌──────────────────────────────┐
 │ PLN SPKLU      _petaspklu_all.json  3029 │         │ scripts/build_road_graph.py  │
 │ Open ChargeMap ocm_jakarta.json      527 │         │   OSMnx fetch Jabodetabek    │
 │ OpenStreetMap  osm_charging_*.json    13 │         │   + add_edge_speeds/times    │
 └──────────────┬──────────────────────────┘         │         ↓                    │
                │  api/sources.py  (normalize loaders)│  jakarta_drive.graphml       │
                ▼                                      └──────────────┬───────────────┘
   api/connectors.py  infer type from power_kw                       │ (NetworkX loads
   (AC Type 2 ≤22kW / CCS2 >22kW) + speed_tier                       │  at 1st request)
                │                                                     │
                ▼                                                     │
   api/dedup.py  greedy haversine cluster (75 m radius),             │
   PLN-anchored priority, merge connectors (MAX count)               │
                │   3569 raw  →  1147 stations                        │
                ▼                                                     │
   scripts/seed_db.py  →  INSERT ST_MakePoint(lon,lat),4326          │
                │                                                     │
                ▼                                                     │
   ┌───────────────────────────────────────────┐                    │
   │ PostGIS  stations(geom GiST, connectors    │                    │
   │ JSONB, sources/connector_types GIN text[]) │◄───────────────────┘
   │ + wallet(id=1), topups, users              │   api/routing.py Dijkstra
   └───────────────┬───────────────────────────┘     (weight = length | travel_time)
                   │  *_repo.py raw parameterized SQL
                   ▼
   ┌───────────────────────────────────────────────────────────────┐
   │ FastAPI  /api/v1/*                                             │
   │  stations · stations/nearby (ST_DWithin) · stations.geojson    │
   │  route · route/nearest-station · ev-models · auth · wallet     │
   └───────────────┬───────────────────────────────────────────────┘
                   │  Xendit ⇄ webhook   Google OAuth ⇄ callback
                   ▼
        nginx  ( /api/* → api:8000 ;  /* → SPA )      [same-origin, no CORS]
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
   Web (Vite/React)     Mobile (Expo/React Native)
        └──── shared @evflow/shared fetch client ────┘
                   ▲
          Cloudflare Tunnel (TLS) → localhost:8080 on LXC VPS
```

---

## 1. Data: sourcing, dedup & quality

**This is the heart of the project.** The pipeline turns three incompatible public datasets into one clean, queryable inventory through five deterministic, pure-function stages (no I/O in the logic — fully unit-testable).

### Sources (raw, in `/data/raw/`)
| Source | File | Rows | Notes |
|---|---|---|---|
| PLN SPKLU (official registry) | `_petaspklu_all.json` | 3,029 | `nama_lokasi`, `latitude`, `longitude`, `watt`, `type_charge`, `total_konektor` |
| Open Charge Map (crowd-sourced) | `ocm_jakarta.json` | 527 | nested `Connections[]` with `PowerKW`+`Quantity`; `ConnectionType` empty for Indonesia |
| OpenStreetMap (Overpass) | `osm_charging_jakarta.json` | 13 | sparse `capacity`, `socket:*` tags |

Each loader in `api/sources.py` validates coordinates (non-null, finite, not `0,0`), skips invalid rows, and assigns a stable source-prefixed id: `pln_spklu-{id}`, `open_charge_map-{id}`, `osm-{type}-{id}`.

### Connector inference — the honest shortcut (`api/connectors.py`)
Source data has **no reliable connector-standard field**, and scraping Google for ground truth is paid + ToS-risky. So connector type is **inferred from power** using Indonesia's de-facto public-charging standard: `AC_DC_SPLIT_KW = 22.0` → `["AC Type 2"]` at/below 22 kW, `["CCS2"]` above. It falls back to PLN's `charge_type` label (`fast`/`ultrafast` → DC, `slow`/`medium` → AC) and returns `[]` when both signals are unknown (those connectors are dropped). Speed tiers are derived deterministically:

```python
SPEED_TIERS = [slow 0–7, medium 7–50, fast 50–150, ultra_fast >150]  # kW
```

Every station carries `connector_inferred: True` so the UI can render an "estimated" badge. **The schema is identical to what a real Google Places enrichment would populate, so inferred values can be swapped in 1:1 with no schema change.**

### Deduplication — greedy spatial clustering (`api/dedup.py`)
Rows are sorted by **source priority** (`{"pln_spklu":0, "open_charge_map":1, "osm":2}`) then id, so PLN always anchors a cluster and the result is **deterministic regardless of input order**. A greedy haversine pass merges any point within **`MERGE_RADIUS_M = 75.0`** metres of an existing cluster:

```python
ordered = sorted(rows, key=lambda r: (_priority(r), str(r.get("id"))))
for r in ordered:
    anchor = first cluster within 75 m (haversine, r=6371008.8 m)
    if anchor is None: clusters.append(_new_cluster(r))
    else:              _merge_into(anchor, r)   # union sources, fill empty descriptive fields
```

When merging connector lists across sources, `merge_connectors()` groups by `(type, power_kw)` and takes the **MAX count**, not the sum — so a shared bay reported by two sources isn't double-counted, while the union of all observed types is preserved.

**Result: 3,569 raw rows → 1,147 deduplicated stations (~68% reduction).** Cross-source overlap: PLN-only 631 (55%), OCM+PLN 357 (31%), OCM-only 146 (13%), all-three only 7 (0.6%); ~86.7% of clusters include PLN. This is the quantitative proof that multi-source fusion adds real coverage.

### Load (`scripts/seed_db.py`)
Batch insert into PostGIS, geometry built server-side:
```sql
INSERT INTO stations (id, geom, ..., connectors, sources, connector_types)
VALUES (:id, ST_SetSRID(ST_MakePoint(:lon,:lat),4326), ..., CAST(:connectors AS jsonb), :sources, :connector_types)
```

### Honest limitations
- 75 m is a **hand-tuned heuristic** — good for dense Jakarta, can false-merge two distinct adjacent sites or false-split a fragmented campus. No name/operator/address consensus matching yet.
- Inference tags only a site's **primary** connector; mixed AC+DC sites lose the secondary type at station level.
- Pipeline is **batch and manual** (`python -m scripts.seed_db`); sources are static cached files, so the inventory goes stale. The notebook (`ev_charging_jakarta_analysis.ipynb`) re-fetches live OCM for analysis, but nothing schedules a re-seed.

---

## 2. Database design (PostGIS)

### Schema & migration chain (Alembic `0001`→`0004`)
- **0001_stations** — `CREATE EXTENSION postgis`; `stations` with `geom geometry(Point,4326)`, plus `name/address/province/city/operator`, `power_kw double precision`, `speed_tier text`, `connector_types text[] DEFAULT '{}'`, `connector_inferred bool`, `sources text[]`, `status`, `date_verified`. Five indexes: **GiST** on `geom`, B-tree on `province`/`speed_tier`, **GIN** on `sources` and `connector_types`.
- **0002_wallet_topups** — singleton `wallet` (`id=1`, `balance_idr bigint CHECK >= 0`); `topups` ledger (`id uuid`, `external_id` unique, `xendit_invoice_id` unique, `amount_idr`, `status`, `invoice_url`, `created_at`, `paid_at`).
- **0003_station_connectors** — adds `connectors JSONB` (per-connector breakdown) as a **backward-compatible append** alongside the legacy `connector_types text[]`.
- **0004_users** — `users` (`id uuid`, `username`, `password_hash`, `google_sub`, `email`, `full_name`, `account_type`, `ev_model_id`, `main_connector_type`, `location_consent` + timestamp, `profile_completed`).

`connectors` JSONB looks like `[{"type":"CCS2","count":2,"power_kw":150,"speed_tier":"fast","type_inferred":false}, ...]`, deserialized straight into the Pydantic `Connector` model.

### Spatial query mechanics (`api/stations_repo.py`)
`geom` is stored as planar **geometry** (cheap to insert/index) but every distance query casts to **geography** so the math is true great-circle — at Jakarta's latitude (~-6°) planar would be ~1.5% off:
```sql
ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :r)   -- radius (m)
ST_Distance(geom::geography, ...)/1000.0 AS distance_km                                 -- exact km
geom && ST_MakeEnvelope(:mnlon,:mnlat,:mxlon,:mxlat,4326)                              -- bbox, index-backed
ST_Y(geom) AS latitude, ST_X(geom) AS longitude                                        -- decompose on read
```
Array filters use the GIN-backed overlap operator: `connector_types && :cts` (OR within a filter), with clauses ANDed across filters. `unnest(sources)`/`unnest(connector_types)` power the `/connectors` and `/sources` count endpoints.

### Repository pattern
Three repos (`stations_repo`, `wallet_repo`, `users_repo`) follow one pattern: **raw SQL via SQLAlchemy `text()` with named bind params** — never string interpolation, so SQL injection is structurally impossible. `engine.connect()` for reads, `engine.begin()` for write transactions (auto-commit / auto-rollback). Raw SQL was chosen over the ORM because PostGIS functions and array/JSONB ops are clearer and faster expressed directly; the tradeoff is no compile-time column-type safety, mitigated by the shared `_COLS` constant.

**Honest tradeoffs:** no foreign keys (faster inserts, looser integrity — `users.ev_model_id` is unenforced); `connector_types` and `connectors` partially duplicate data; the global singleton wallet (`id=1`) doesn't scale to per-user balances.

---

## 3. API & geospatial features

Versioned `/api/v1` FastAPI surface; responses are Pydantic models, so OpenAPI/`/docs` is always in sync.

### Stations
- `GET /stations` — offset/limit pagination (default 100/0, max 1000), filters: `province`, `city`, `q`, `min_power`/`max_power`, repeatable `connector_type`/`speed_tier`, and `bbox=minLon,minLat,maxLon,maxLat`.
- `GET /stations/nearby` — `ST_DWithin` radius search (`radius_km` default 5, max 500), distance-sorted with `distance_km` per row. Both `lat`+`lon` or neither (provide one → 422; neither → falls back to filtered list).
- `GET /stations/{id}` — 404 if missing.
- `GET /stations.geojson` — RFC 7946 `FeatureCollection`, `Point` coords as `[lon, lat]`, drops straight into Leaflet/Mapbox; max 20,000 features.
- Lookup endpoints `/provinces`, `/cities`, `/connectors`, `/speed-tiers`, `/stats` populate UI dropdowns from `count(*)` aggregates.

### Routing (Epic 2.0)
**Offline graph build** (`scripts/build_road_graph.py`, run once): OSMnx fetches the Jabodetabek drivable network (`BBOX` south -6.376 / west 106.6894 / north -6.089 / east 106.971), `add_edge_speeds()` + `add_edge_travel_times()` enrich edges, serialized to `data/processed/jakarta_drive.graphml`. **At runtime the API only needs NetworkX to read GraphML; OSMnx is never imported again** (heavy imports are deferred into functions). Missing graph → 503.

**At request time** (`api/routing.py`): snap origin/destination to nearest road node by numpy haversine, run a **pure hand-rolled Dijkstra** over an adjacency map `{node: [(neighbour, length_m, travel_time_s), ...]}`. `weight_idx=0` minimizes distance, `1` minimizes travel time; it returns `(dist, prev, edge_used)` so a caller can sum *both* metrics along the reconstructed path. Output is a GeoJSON `LineString` — graph internals never leak.

- `GET /route` — origin → `station_id` (or `dest_lat`/`dest_lon`); returns `distance_m`, `duration_s`, snapped node ids + snap distance, `node_count`, geometry.
- `GET /route/nearest-station` — one single-source Dijkstra finds the reachable nearest station; supports battery range via explicit `max_range_km` or `ev_model_id` + `current_soc`. Usable range = `range_km × (soc/100) × 0.85` (real-world safety buffer). Returns `within_range` as an **informational flag**, not a hard block, plus `candidates_considered`. No route → 404.

**Why this over OSRM/Mapbox:** zero external runtime dependency, runs in any container, self-contained for a hackathon budget. Tradeoff: no live traffic, hardcoded bbox (routing outside Jabodetabek 404s), and per-request Dijkstra scales worse than a precomputed routing service at large graph sizes.

---

## 4. Integrations & auth

### Auth (`api/security.py`)
- **Passwords:** bcrypt with per-password random salt (`bcrypt.gensalt()`), `~100 ms`/hash — deliberately expensive for attackers; min 8 chars at registration.
- **Sessions:** stateless **JWT HS256**, payload `{"sub": user_id, "exp": now + JWT_EXPIRE_MINUTES*60}` (default `10080` min = 7 days), signed with `JWT_SECRET`. `current_user` dependency decodes the bearer token **and re-fetches the user from the DB** — fail-closed if the user no longer exists.
- **Google OAuth:** redirect to Google with scope `openid email profile`, `prompt=select_account`; CSRF protection via a **signed state** = `nonce.HMAC_SHA256(nonce, JWT_SECRET)`, verified on callback with `hmac.compare_digest()` (timing-safe) and **fail-closed if `JWT_SECRET` is empty**. Server-side code exchange (secret never reaches the client); accounts are keyed/linked on the stable Google `sub` (not email), auto-created on first sign-in. Token returned in the URL **fragment** `FRONTEND_URL/auth/callback#token=<jwt>` (never sent to servers, but JS-readable).

### Payments — Xendit (`api/xendit.py`, `api/wallet_repo.py`)
1. `POST /wallet/topup` (min 10,000 IDR) → `create_invoice()` posts to Xendit with HTTP Basic Auth (secret key as username) and a unique `external_id`; hosted invoice URL stored in `topups` (status `pending`).
2. User pays on Xendit's hosted page.
3. `POST /webhooks/xendit` verifies the `X-Callback-Token` header against `XENDIT_CALLBACK_TOKEN` (**fail-closed if empty**), then `mark_paid_and_credit()` runs **one atomic, idempotent transaction**:
```sql
UPDATE topups SET status='paid', paid_at=now()
WHERE xendit_invoice_id=:inv AND status='pending' RETURNING amount_idr;
-- then, only if a row returned:
UPDATE wallet SET balance_idr = balance_idr + :amt, updated_at=now() WHERE id=1;
```
A duplicate webhook matches zero `pending` rows → returns `False` → **no double-credit**. This is exactly-once crediting without distributed consensus, leaning on the unique `xendit_invoice_id` constraint.

`GET /wallet` reads the singleton balance; `GET /wallet/topups` lists the last 20 for payment history.

---

## 5. Frontend & deployment

### Cross-platform monorepo (npm workspaces)
`apps/web` (Vite + React 19) and `apps/mobile` (Expo 54 + RN 0.81) both consume `packages/shared` (the `fetch`-based API client + types), `packages/features`, `packages/maps`, `packages/ui`. Platform-specific code uses **`.web.tsx` / `.native.tsx` extensions** that Vite (`resolve.extensions`) and Metro resolve automatically — e.g. `PlatformSlider.web.tsx` (HTML `<input type=range>`) vs `.native.tsx` (`@react-native-community/slider`). One business-logic codebase, two platforms.

### Smart API base-URL resolution (`baseUrl*.ts`)
- Web dev: `http://localhost:8000` (via `VITE_EVFLOW_API_BASE_URL`).
- Mobile dev: **auto-derives the dev host from the Expo Metro bundle URL** (LAN IP for physical devices, `10.0.2.2:8000` for emulators); tunnel mode falls back to prod.
- Prod: `https://ev-flow-api.opensoft.id`; if base is `"/"` → relative paths → **same-origin (no CORS)**.

The `fetch` client is dependency-free (easy to mock in tests). `toQueryString()` flattens array params (`connector_type=Type2&connector_type=CCS2`) and omits null/undefined; FastAPI's repeatable query params reassemble the list.

### Container topology
`compose.yaml` runs three containers: **db** (PostGIS 16-3.4) → **api** (FastAPI `:8000`) → **web** (nginx serving the Vite build, built with `VITE_EVFLOW_API_BASE_URL=/`, proxying `/api/` → `http://api:8000`). nginx (`nginx.conf.template`) immutable-caches `/assets/*` (hashed), no-caches `index.html`, SPA-falls-back to `/index.html`, and substitutes `EVFLOW_API_UPSTREAM` at container start so one image works in compose (`api:8000`) and on VPS (`localhost:8000`). Production VPS uses **host networking** (LXC blocks iptables NAT) with **Cloudflare Tunnel** terminating TLS to `localhost:8080` — no open ports, no cert renewal, everything same-origin.

---

## Cross-cutting design decisions

- **Infer connectors from power over scraping Google Places** — deterministic, free, ToS-safe, schema-identical for future 1:1 replacement; flagged `connector_inferred` for honesty.
- **PostGIS in-database over Elasticsearch/a geo microservice** — one source of truth, O(log n) GiST queries, no extra service to operate for a few-thousand-row, rarely-updated dataset.
- **Store `geometry`, query as `geography`** — cheap planar storage + index, correct spherical distance per query (~1.5% error avoided at Jakarta's latitude) at negligible CPU vs ~2× storage if cached as geography.
- **Offline GraphML + runtime NetworkX over OSRM/Mapbox** — zero external runtime dependency, self-contained container, deterministic topology; accept no live traffic and a hardcoded bbox.
- **Hand-rolled pure Dijkstra over precomputed all-pairs** — single-source per request is fast enough for an ~80k-node metro graph and trivial to unit-test; all-pairs would blow up storage.
- **Raw parameterized SQL over an ORM** — clearer PostGIS/array/JSONB expressions, no injection surface, no eager-load surprises; tradeoff is manual column/type discipline.
- **Stateless JWT over server sessions** — any API instance verifies without a DB session table; accept coarse 7-day expiry and client-side-only logout.
- **Idempotent webhook crediting via a unique-constraint + `WHERE status='pending'`** — exactly-once payments without distributed locks.
- **Same-origin nginx proxy + Cloudflare Tunnel over public API + CORS** — eliminates CORS entirely and needs no open ports or TLS cert management.

---

## Known limitations & what I'd do next

- **Dedup is a 75 m distance heuristic** — no name/operator/address consensus; can false-merge adjacent sites or false-split campuses. Next: weighted similarity matching + a review queue using `cluster_source_presence.csv`.
- **Connector types are inferred, not ground truth** — primary type only; mixed AC+DC sites under-report. Next: enrich from user corrections / OCM updates (schema already fits).
- **Batch, manual ingestion** — static cached JSON, no scheduled refresh → stale inventory. Next: nightly cron/Airflow re-fetch → re-dedup → re-seed with versioning/rollback.
- **CORS defaults to `*`** — fine for public read endpoints, dangerous once `/wallet/topup` is live. Next: lock `CORS_ALLOW_ORIGINS` to the frontend origin in prod.
- **JWT in the OAuth callback URL fragment** — JS-readable and in browser history. Next: httpOnly + SameSite=Strict secure cookie.
- **No server-side token revocation** — a stolen JWT is valid up to 7 days. Next: short access tokens + refresh, or a `jti` blacklist.
- **Top-up endpoint is unauthenticated** and the wallet is a **global singleton (`id=1`)**. Next: `Depends(current_user)`, per-user wallet, topups FK'd to user.
- **No rate limiting / no FKs / single-region** — anyone can crawl the API; no per-app quotas. Next: rate limiting, FK constraints, and a routing service if it scales beyond Jabodetabek.
- **Per-request Dijkstra + ~10–50 MB graph in memory** — fine now, a bottleneck at national scale. Next: cache hot routes (Redis) or move to OSRM.
- **Frontend `VITE_EVFLOW_API_BASE_URL` is baked at build time** — multi-env needs separate builds. Next: a runtime `/config.json` if true env portability is needed.

---

## Likely interview questions (with answers)

### Data engineering
**Q: Walk me through how 3,569 raw records become 1,147 stations.**
Three loaders normalize PLN/OCM/OSM to a common schema in `sources.py`; `connectors.py` infers connector type and speed tier from `power_kw`; `dedup.py` sorts by source priority (PLN first) and greedily clusters any point within 75 m of an existing cluster's anchor via haversine. Cross-source connectors are merged by `(type, power_kw)` taking the MAX count to avoid double-counting shared bays, then `seed_db.py` bulk-inserts with `ST_MakePoint`. That's a ~68% reduction, and ~86.7% of final clusters contain PLN data.

**Q: How do you handle conflicting data when sources describe the same station?**
Descriptive fields (name, address, operator) fill from the first non-null value in source-priority order, so PLN — the official registry — wins ties and anchors the cluster deterministically. Power resolves to the max observed value; connectors merge by `(type, power_kw)` with `count = max`. Genuine conflicts would need a field survey; the `cluster_source_presence.csv` artifact flags suspicious merges for manual review.

**Q: Why 75 metres, and what breaks?**
GPS is ±5–10 m in good urban conditions but multi-bay hubs span 30–50 m, so 75 m balances missing same-site duplicates against merging distinct sites. It works on dense Jakarta with no reported mis-merges but can false-split a fragmented campus or false-merge two malls on adjacent blocks — a known hackathon-stage heuristic I'd refine with name/operator/address similarity.

**Q: A station has no power data — can you still classify it?**
Partially. If `charge_type` (PLN's label) is present we infer from that (`fast`/`ultrafast` → CCS2, `slow`/`medium` → AC Type 2); if both power and label are missing, `infer_connectors()` returns `[]` and that connector is dropped. The station still appears in the API but is excluded from connector-type filters — a deliberate trade of recall for avoiding false positives.

### Database & geospatial
**Q: Why cast to geography if geometry is cheaper to store?**
Planar geometry math is ~1.5% off at Jakarta's latitude; geography gives true great-circle distance. I store planar (cheap insert + GiST index) and cast `::geography` per query — negligible CPU versus ~2× storage if I cached geography. At thousands of QPS I'd profile, but for a discovery app it's the right trade.

**Q: What happens on `/nearby` if the user denies location?**
`lat`/`lon` are optional; with neither, `nearby` falls back to `list_stations()` and returns results from the other filters only. Providing exactly one returns a 422. Privacy-wise the client can round GPS to ~100 m before sending since the read endpoints are public anyway.

**Q: Can this scale to millions of stations?**
GiST keeps `ST_DWithin`/bbox at O(log n) and GIN keeps array filters fast, so the spatial path scales. The bottleneck is `list_stations()` doing a filtered scan; at 1M+ rows I'd partition by province or add a materialized view of hot filters. At ~1,147 rows it's trivial.

**Q: Why raw SQL instead of an ORM?**
PostGIS functions (`ST_DWithin`, `ST_Distance`, `ST_Y/ST_X`) and array/JSONB ops (`unnest`, `&&`, `:x = ANY(...)`) are clearer and faster expressed directly, with no eager-load surprises. Everything goes through SQLAlchemy `text()` with named bind params, so injection is structurally impossible — the tradeoff is manual column/type discipline, which I centralize in a `_COLS` constant.

### API & routing
**Q: Why build the road graph offline instead of OSRM/Mapbox?**
Cost and self-containment — a hosted routing service means a server or paid keys. I build the Jabodetabek drivable graph once with OSMnx, serialize to GraphML, and at runtime only NetworkX reads it; OSMnx is never imported again. Tradeoff: no live traffic and a hardcoded bbox, so routing outside Jabodetabek 404s — acceptable for the MVP.

**Q: How does battery-aware routing decide reachability, and is the buffer too aggressive?**
Usable range = `range_km × (soc/100) × 0.85`, where 0.85 buffers real-world vs. lab figures. The buffer applies only when deriving range from an EV model + SoC; explicit `max_range_km` is trusted as-is. Crucially `within_range` is informational — we return the station with a warning so the user decides, rather than hard-blocking a tight-but-makeable route.

**Q: What if no route exists between two points?**
Dijkstra never adds the target to its `dist` map, `reconstruct()` returns `None`, and the endpoint returns 404. In a connected city this is rare; it mainly happens outside the bbox or on a transient OSM data gap that the community fixes quickly.

### Security & integrations
**Q: A webhook fires twice — do you double-credit?**
No. `mark_paid_and_credit()` runs `UPDATE topups SET status='paid' ... WHERE xendit_invoice_id=:inv AND status='pending' RETURNING amount_idr`, and only credits the wallet if a row returned, all in one transaction. The second webhook matches zero pending rows, returns `False`, and is a no-op — exactly-once via the unique invoice-id constraint, no distributed locking.

**Q: The OAuth token sits in the URL fragment — isn't that exposed?**
It's JS-readable and in browser history, yes — that's the known MVP trade. Fragments are never sent to servers per the HTTP spec, so it doesn't leak to proxies/referrers, but for production I'd switch to an httpOnly + SameSite=Strict cookie to also defend against XSS/CSRF.

**Q: Why bcrypt and HMAC-signed OAuth state rather than alternatives?**
bcrypt's adaptive cost + per-password salt makes offline cracking ~100 ms/guess, prohibitively expensive if the DB leaks. For CSRF I sign `nonce.HMAC_SHA256(nonce, JWT_SECRET)` and verify with `hmac.compare_digest()` (timing-safe), fail-closed when `JWT_SECRET` is empty — no session store needed. The tradeoff is that a leaked `JWT_SECRET` would forge state, so it must be rotated carefully.

**Q: If a JWT is stolen, what's the blast radius?**
Up to the 7-day expiry — there's no server-side revocation, which is the cost of stateless JWT. I'd mitigate with httpOnly cookies (kills XSS theft), short access tokens plus refresh tokens, or a `jti` blacklist if instant revocation is required.

### Frontend & deployment
**Q: One API client for web and mobile — how does platform-specific UI work?**
`packages/shared` holds the `fetch` client and business logic both platforms import; platform splits use `.web.tsx`/`.native.tsx` files that Vite and Metro resolve automatically (e.g. `PlatformSlider`). The same JWT and JSON contract work everywhere, so charger filtering, route building, and auth flows are written once.

**Q: How does the app find the backend across dev, prod, and containers?**
Three resolvers: web dev hits `localhost:8000`; mobile dev auto-derives the dev host from the Expo Metro bundle URL (LAN IP or `10.0.2.2`); prod uses `ev-flow-api.opensoft.id`, and a `"/"` base means relative paths → same-origin via the nginx proxy, eliminating CORS. If the local backend is down, dev gracefully falls back to prod.

**Q: Why same-origin nginx + Cloudflare Tunnel instead of a separate API domain with CORS?**
The Vite build bakes `VITE_EVFLOW_API_BASE_URL=/`, so the browser only ever calls relative paths; nginx proxies `/api/` to the API (target substituted from `EVFLOW_API_UPSTREAM` at container start, so one image works locally and on the VPS). On a cheap LXC VPS, host networking sidesteps blocked iptables NAT and Cloudflare Tunnel gives HTTPS with no open ports or cert renewal — at the cost of Cloudflare dependency.

# Project Status And Analysis

This is a point-in-time engineering analysis of commit `247b89b`, reviewed on
2026-07-22. It distinguishes persisted product behavior from prototypes and
scaffolding so future work starts from the current implementation, not from older
plans.

## Capability Matrix

| Area | Current state | Notes |
|---|---|---|
| Station ingestion | Implemented | Three committed raw sources, normalization, connector inference, deterministic 75 m deduplication, destructive station reseed |
| Station discovery | Implemented | PostGIS list, nearby, bbox, connector/speed/power filters, GeoJSON and aggregates |
| Driver map | Implemented with caveats | Leaflet on web; Leaflet-in-WebView on native; native assets and tiles need internet |
| EV catalogue | Implemented | Cached CSV/ZIP catalogue and range calculation |
| Road routing | Backend implemented, deployment optional | Custom Dijkstra over an untracked GraphML file; frontend route planner is a placeholder |
| Password accounts | Implemented | Register, login, bearer JWT, profile update, password-change invalidation |
| Google OAuth | Partial | Backend flow exists; frontend login control and `/auth/callback` handler do not |
| Password reset | Implemented with operational dependency | Single-use hashed tokens and SMTP background delivery; no direct persistence/mailer tests |
| Wallet | Implemented | User-scoped balance, Xendit invoice, webhook/status-poll credit, history |
| Charging accounting | Implemented | Server quote, atomic deposit debit, idempotent settlement and refund |
| Charger interaction | Prototype | QR content ignored, station/connector can be randomly selected, plug detection and progress are simulated |
| Receipts | Implemented client-side | html2pdf on web; Expo print plus WebView viewer on native |
| Business planner | Prototype | Live station total only; remaining KPIs, heatmap, candidates and insights are static; most actions are no-ops |
| Demo login | Implemented for demonstrations | Public persona password; login then auto-register on 401 |
| Web deployment | Implemented | Vite build, nginx SPA fallback, same-origin API proxy |
| Mobile deployment | Development-ready | Expo configuration exists; no tracked `eas.json`, store workflow, or verified deep links |

## What Is Authoritative

- Backend monetary state and pricing requests are authoritative at the API and DB.
- PostGIS is the active station store; old descriptions of a startup DataFrame are
  obsolete.
- Alembic revision `0008_user_password_changed_at` is the current schema head.
- Frontend API contracts are handwritten and can drift from Pydantic/OpenAPI.
- Historical specifications under `backend-ev-flow/docs/superpowers/` are design
  records, not an implementation backlog.

## Verified During This Review

| Check | Result |
|---|---|
| Frontend TypeScript typecheck | Passed |
| Frontend production web build | Passed |
| Web build size | Main minified chunk about 1.99 MB, about 582 KB gzip; Vite emitted a large-chunk warning |
| Raw station normalization | 3,569 rows: PLN 3,029, Open Charge Map 527, OSM 13 |
| Current 75 m deduplication | 2,931 stations |
| Repository worktree before docs | Clean |
| Full backend suite | Not verified in the shared checkout: `backend-ev-flow/.venv` and global API dependencies are absent |
| DB integration suite | Not verified: no accessible migrated test PostGIS instance in this environment |
| Running container stack | Not verified: the local Podman machine/socket was inaccessible |

The repository has 61 backend tests. DB-backed tests are skipped unless
`DATABASE_URL` is explicitly exported. External Google and Xendit unit tests mock
network calls.

## Highest-Priority Gaps

### 1. Make CI A Real Quality Gate

GitHub Actions currently runs SonarQube scanning only. Add jobs for:

- backend isolated tests;
- migrated disposable PostGIS integration tests;
- frontend typecheck and production build;
- OpenAPI snapshot drift;
- frontend unit tests, then browser E2E coverage for core flows.

This is the main protection against contract drift across the two applications.

### 2. Repair Authenticated Backend Tests

Wallet and charging DB tests still call bearer-protected endpoints without tokens.
Introduce an authenticated user/client fixture and isolate each test's user and
wallet. Keep provider clients mocked, but execute the real repository transactions.

Also add coverage for password-reset token persistence, SMTP dispatch behavior,
migration upgrade paths, and deployed station import.

### 3. Finish Or Remove Google OAuth From The Product Surface

The backend redirects to `/auth/callback#token=...`, but the frontend has neither
that route nor a Google sign-in control. A complete implementation needs secure
token-fragment consumption, session save, fragment removal, navigation, mobile
deep-link behavior, and tests. Until then, do not advertise it as a working login
method.

### 4. Replace Simulated Charger Behavior

The client currently ignores QR payload data, may choose a random station and
connector, waits a fixed time for plug detection, and simulates charging progress.
Before real-world use, define and validate a QR contract, charger identity and
authorization, telemetry/status APIs, cancellation semantics, and reconciliation
for interrupted sessions.

### 5. Complete Route Planning

The backend already exposes point/station routing and range-aware nearest-station
operations. The `/ev-driver/plan_route` screen is a placeholder and shared route
helpers are unused. Decide the product input model, add a typed route client, render
the returned GeoJSON, and handle the optional-graph 503 state.

### 6. Make Product Routes Recoverable

Charging screens depend on transient router state. Reloading a payment, status, or
success route loses its station/session context. Persist only stable identifiers in
URLs or storage and re-fetch server state. Native sessions are memory-only and
should use an appropriate secure persistence mechanism before production.

### 7. Align Environment And Deployment Contracts

`DATABASE_URL`, charging price variables, Xendit timeout, and importer settings are
missing from current example coverage. Root and host-network Compose load/pass
different variable sets. Consolidate the backend template, explicitly separate
root interpolation from API secrets, and make startup fail clearly for required
production values.

Avoid changing charging price environment values while sessions are active. The
session stores the original quote fields, but current settlement code recomputes
cost and deposit using the current environment tariff.

### 8. Restore Contract And Documentation Drift Checks

The checked-in OpenAPI snapshots contain 25 operations while source defines 33.
Older API guides describe a nonexistent station `source` filter, in-memory station
loading, earlier counts, and no current auth/charging surface. Regenerate snapshots
and fail CI when generation produces a diff.

### 9. Add Frontend Test, Lint, And Formatting Tooling

The frontend has only typecheck/build scripts. Prioritize tests around:

- API URL resolution for web, LAN mobile, tunnel, and same-origin builds;
- auth session and 401 behavior;
- station filter query generation;
- wallet top-up polling and idempotent display;
- charging state recovery and settlement;
- platform-specific scanner, receipt, and location fallbacks.

The normal login screen also contains raw `<ul>`/`<li>` DOM elements even though
the screen is shared with native. Add a native render test and replace browser-only
markup when that route must work on mobile.

### 10. Harden Operations

- Add database backup/restore and migration verification to release runbooks.
- Pin deployable image tags instead of `latest` and floating Sonar images.
- Add API/readiness health checks distinct from liveness.
- Restrict host-network ports with firewall rules.
- Replace hardcoded development database credentials for production.
- Add edge rate limiting and observability for auth and payment endpoints.

## Other Known Inconsistencies

| Item | Current reality |
|---|---|
| Root UI | Opens demo-persona login; normal login exists only at `/login` |
| Profile selection | Role state is not passed into registration; registration sends no account type |
| Map radius | Default view can show all stations while displaying an 8 km circle; nearby query starts only after relevant filter/radius changes |
| `@evflow/maps` | Declared workspace with placeholder components; product map lives in `@evflow/ui` |
| Shared scaffolding | `createApiClient`, charger transform/filter helpers, route request builder, and `HomeScreen` are unused |
| Package manager | Frontend metadata says Yarn; lockfile, docs, scripts and container use npm |
| Expo dependencies | Versions are duplicated and not fully aligned across mobile, web and features manifests |
| API health | Returns 200 and `status: ok` even when its station query fails |
| Smoke test | Claims every endpoint but covers only public read/discovery routes |
| Business report | Download and most navigation actions are not implemented |
| Route graph | Optional and untracked; deployment must provide it |
| API static spec | Generated snapshot is stale and does not drive frontend types |
| `document.yaml` | Open Charge Map's external specification, not EVFlow's API |

## Suggested Delivery Sequence

1. Stabilize CI, authenticated fixtures, env templates, and OpenAPI drift checks.
2. Make login/session and charging routes recoverable across refresh and native
   process restarts.
3. Finish one incomplete product vertical at a time: Google OAuth, route planning,
   or real charger integration.
4. Add frontend tests alongside each completed vertical.
5. Harden backups, readiness, secrets, image versioning, firewall policy, and
   observability before production expansion.

## Review Checklist For Future Updates

- Re-run normalized and deduplicated station counts when source snapshots or
  algorithms change.
- Compare route operations in `api/main.py` with dynamic and static OpenAPI.
- Compare every `os.getenv` and frontend public env read with
  [Configuration](CONFIGURATION.md) and Compose pass-through.
- Run backend isolated and DB suites, frontend typecheck/build/tests, and smoke
  checks.
- Exercise web and native variants for any file with platform suffixes.
- Update the capability matrix when a prototype becomes persisted product
  behavior.

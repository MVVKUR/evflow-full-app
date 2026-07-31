"""Import stations from a deployed EV-FLOW API into the database this process points at.

Usage:
    python -m scripts.import_api_data                        # additive: upsert only
    python -m scripts.import_api_data --dry-run              # fetch + report, write nothing
    python -m scripts.import_api_data --prune                # destructive, see below
    python -m scripts.import_api_data --rebuild-connectors   # destructive, see below

READ BEFORE RUNNING
  * Target: whatever DATABASE_URL (or the POSTGRES_* parts) resolves to in this
    shell. The script prints host/port/database before it touches anything --
    read that line. It is the only thing between a local refresh and an
    overwrite of production.
  * Source: EVFLOW_SOURCE_API_BASE_URL, default https://ev-flow.opensoft.id,
    overridable with --base-url. It is a *deployed* API, never a local file.
  * A plain run is additive. Stations are upserted by id; connector rows are
    created only for stations that have none. Nothing is deleted, so a run
    against the wrong database is recoverable. The cost of that safety: a
    station whose connector list changed keeps its old connector rows (a re-run
    must not double them) -- use --rebuild-connectors to resync those.
  * --prune deletes stations the source no longer serves. That cascades to
    connectors and SET NULLs charging_sessions.connector_id for them.
  * --rebuild-connectors deletes and re-explodes connector rows for every
    imported station, losing the same charging_sessions.connector_id links.
  * Both destructive flags require typing the target database name, or --yes
    for a non-interactive run.
  * The run aborts if the number of fetched stations does not equal the total
    the API reports. /api/v1/stations caps limit at 1000 while production holds
    thousands of rows, so a single unpaginated request looks successful and is
    silently short -- the earlier version of this script combined that with
    DELETE FROM stations and would have destroyed every station past the first
    page.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import text
from sqlalchemy.engine import Connection

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db import engine  # noqa: E402


DEFAULT_API_BASE_URL = os.getenv("EVFLOW_SOURCE_API_BASE_URL", "https://ev-flow.opensoft.id")
# /api/v1/stations declares limit as Query(le=1000); a larger page is a 422, not
# a bigger page, so clamp instead of letting the run die mid-pagination.
API_MAX_PAGE_SIZE = 1000
PAGE_SIZE = min(int(os.getenv("EVFLOW_IMPORT_PAGE_SIZE", "1000")), API_MAX_PAGE_SIZE)
HTTP_TIMEOUT_SECONDS = float(os.getenv("EVFLOW_IMPORT_HTTP_TIMEOUT", "30"))

_UPSERT_STATION = text("""
    INSERT INTO stations
      (id, geom, name, address, province, city, operator, power_kw, speed_tier,
       connector_types, connector_inferred, connectors, sources, status, date_verified)
    VALUES
      (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, :address, :province,
       :city, :operator, :power_kw, :speed_tier, :connector_types, :connector_inferred,
       CAST(:connectors AS jsonb), :sources, :status, :date_verified)
    ON CONFLICT (id) DO UPDATE SET
       geom = EXCLUDED.geom,
       name = EXCLUDED.name,
       address = EXCLUDED.address,
       province = EXCLUDED.province,
       city = EXCLUDED.city,
       operator = EXCLUDED.operator,
       power_kw = EXCLUDED.power_kw,
       speed_tier = EXCLUDED.speed_tier,
       connector_types = EXCLUDED.connector_types,
       connector_inferred = EXCLUDED.connector_inferred,
       connectors = EXCLUDED.connectors,
       sources = EXCLUDED.sources,
       status = EXCLUDED.status,
       date_verified = EXCLUDED.date_verified
""")

# One row per PHYSICAL connector, exploding the JSONB 'count' (same shape as
# migration 0009). Restricted to the stations just imported, and skipping any
# station that already has connector rows: without that guard a second run
# would double every station's connectors instead of being idempotent.
# --rebuild-connectors deletes first, which makes the NOT EXISTS trivially true.
_EXPLODE_CONNECTORS = text("""
    INSERT INTO connectors (id, station_id, type, power_kw, speed_tier, type_inferred)
    SELECT gen_random_uuid(), s.id, c->>'type', (c->>'power_kw')::double precision,
           c->>'speed_tier', COALESCE((c->>'type_inferred')::boolean, false)
    FROM stations s,
         LATERAL jsonb_array_elements(s.connectors) AS c,
         LATERAL generate_series(1, GREATEST(COALESCE((c->>'count')::int, 1), 1)) AS n
    WHERE jsonb_typeof(s.connectors) = 'array'
      AND s.id = ANY(CAST(:ids AS text[]))
      AND NOT EXISTS (SELECT 1 FROM connectors k WHERE k.station_id = s.id)
""")

_DELETE_CONNECTORS = text("DELETE FROM connectors WHERE station_id = ANY(CAST(:ids AS text[]))")

_PRUNE_STATIONS = text("DELETE FROM stations WHERE id <> ALL(CAST(:ids AS text[]))")

_COUNT_KNOWN = text("SELECT count(*) FROM stations WHERE id = ANY(CAST(:ids AS text[]))")

_COUNT_PRUNABLE = text("SELECT count(*) FROM stations WHERE id <> ALL(CAST(:ids AS text[]))")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_API_BASE_URL,
                        help=f"source API base URL (default: {DEFAULT_API_BASE_URL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and report what would change; write nothing")
    parser.add_argument("--prune", action="store_true",
                        help="DESTRUCTIVE: delete stations the source no longer serves "
                             "(cascades to connectors, SET NULLs charging_sessions.connector_id)")
    parser.add_argument("--rebuild-connectors", action="store_true",
                        help="DESTRUCTIVE: delete and re-explode connector rows for every "
                             "imported station (same charging_sessions.connector_id loss)")
    parser.add_argument("--yes", action="store_true",
                        help="skip the typed confirmation a destructive flag otherwise requires")
    return parser.parse_args()


def target_database() -> str:
    url = engine.url
    return f"{url.database} on {url.host or 'localhost'}:{url.port or 5432} as {url.username}"


def fetch_page(base_url: str, offset: int) -> dict:
    query = urlencode({"limit": PAGE_SIZE, "offset": offset})
    url = f"{base_url.rstrip('/')}/api/v1/stations?{query}"
    request = Request(url, headers={"User-Agent": "EV-FLOW station importer"})
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise SystemExit(f"cannot reach {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{url} did not return JSON (wrong host or an error page?)") from exc
    if "items" not in payload or "total" not in payload:
        raise SystemExit(f"{url} returned an unexpected shape: expected 'items' and 'total'")
    return payload


def fetch_all_stations(base_url: str) -> list[dict]:
    first = fetch_page(base_url, 0)
    total = int(first["total"])
    if total <= 0:
        raise SystemExit(f"{base_url} reports total={total}: refusing to import an empty dataset")

    stations = list(first["items"])
    print(f"fetched {len(stations)}/{total}")
    for offset in range(PAGE_SIZE, total, PAGE_SIZE):
        items = list(fetch_page(base_url, offset)["items"])
        # An empty page while the API still claims more rows means pagination
        # stopped early; break and let the count check below fail loudly rather
        # than spin forever or import a partial dataset.
        if not items:
            break
        stations.extend(items)
        print(f"fetched {len(stations)}/{total}")

    if len(stations) != total:
        raise SystemExit(
            f"fetched {len(stations)} stations but {base_url} reports {total}. "
            "Importing a partial dataset would understate coverage -- aborting."
        )
    return stations


def dedupe_by_id(stations: list[dict]) -> list[dict]:
    # Offset pagination is not a stable snapshot: a row written between two page
    # requests can shift a station into a later page and repeat it. Postgres also
    # rejects an ON CONFLICT DO UPDATE that hits the same row twice in one
    # statement, so collapse duplicates here; last occurrence wins.
    return list({station["id"]: station for station in stations}.values())


def station_params(station: dict) -> dict:
    return {
        "id": station["id"],
        "lat": station["latitude"],
        "lon": station["longitude"],
        "name": station.get("name"),
        "address": station.get("address"),
        "province": station.get("province"),
        "city": station.get("city"),
        "operator": station.get("operator"),
        "power_kw": station.get("power_kw"),
        "speed_tier": station.get("speed_tier"),
        "connector_types": list(station.get("connector_types") or []),
        "connector_inferred": bool(station.get("connector_inferred", True)),
        "connectors": json.dumps(station.get("connectors") or []),
        "sources": list(station.get("sources") or []),
        "status": station.get("status"),
        "date_verified": station.get("date_verified"),
    }


def preview(conn: Connection, ids: list[str]) -> tuple[int, int]:
    known = conn.execute(_COUNT_KNOWN, {"ids": ids}).scalar_one()
    prunable = conn.execute(_COUNT_PRUNABLE, {"ids": ids}).scalar_one()
    return int(known), int(prunable)


def confirm(args: argparse.Namespace, prunable: int) -> None:
    if not (args.prune or args.rebuild_connectors):
        return
    warnings = []
    if args.prune:
        warnings.append(f"--prune will DELETE {prunable} station(s) not present in the source, "
                        "cascading to their connectors")
    if args.rebuild_connectors:
        warnings.append("--rebuild-connectors will DELETE and recreate connector rows for every "
                        "imported station")
    for warning in warnings:
        print(f"  ! {warning}")
    print("  ! charging_sessions.connector_id is SET NULL for every connector removed")
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("aborted: destructive run with no terminal to confirm on; pass --yes")
    database = engine.url.database or ""
    if input(f"Type the target database name ({database}) to continue: ").strip() != database:
        raise SystemExit("aborted: confirmation did not match")


def main() -> None:
    args = parse_args()
    print(f"target database: {target_database()}")
    print(f"source API:      {args.base_url}")
    print(f"mode:            {'dry-run (no writes)' if args.dry_run else 'write'}"
          f"{', prune' if args.prune else ''}"
          f"{', rebuild-connectors' if args.rebuild_connectors else ''}")

    stations = dedupe_by_id(fetch_all_stations(args.base_url))
    ids = [station["id"] for station in stations]

    with engine.connect() as conn:
        known, prunable = preview(conn, ids)
    print(f"{len(stations)} stations fetched: {known} already present (update), "
          f"{len(stations) - known} new; {prunable} row(s) in the database are not in the source")

    if args.dry_run:
        print("dry run: nothing was written")
        return

    confirm(args, prunable)

    with engine.begin() as conn:
        conn.execute(_UPSERT_STATION, [station_params(station) for station in stations])
        removed_connectors = (conn.execute(_DELETE_CONNECTORS, {"ids": ids}).rowcount
                              if args.rebuild_connectors else 0)
        added_connectors = conn.execute(_EXPLODE_CONNECTORS, {"ids": ids}).rowcount
        pruned = conn.execute(_PRUNE_STATIONS, {"ids": ids}).rowcount if args.prune else 0

    print(f"upserted {len(stations)} stations into {target_database()}; "
          f"+{added_connectors} connector rows, -{removed_connectors} removed, "
          f"{pruned} station(s) pruned")


if __name__ == "__main__":
    main()

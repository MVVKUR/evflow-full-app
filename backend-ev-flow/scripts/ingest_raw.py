"""Load every dataset file into its table. THE ONLY PLACE A DATASET IS READ.

    python -m alembic upgrade head
    python -m scripts.ingest_raw          <-- here
    python -m scripts.seed_db

Five sources, all of them file-in / table-out:

    data/raw/_petaspklu_all.json        -> raw_station_records (source pln_spklu)
    data/raw/ocm_jakarta.json           -> raw_station_records (source open_charge_map)
    data/raw/osm_charging_jakarta.json  -> raw_station_records (source osm)
    indonesia_ev_specs_pricing_2026.csv -\
                                          >-- UNION --> ev_models
    electric_vehicles_spec_2025.csv     -/

Everything downstream is database-to-database: `api/sources.py` reads the staging
table, `scripts/seed_db.py` reads `api/sources.py`, and `api/evmodels.py` reads
`ev_models` and nothing else.

IDEMPOTENT. Staging is replaced per source inside one transaction, so a second
run leaves exactly the same rows, in the same order, with no duplicates.
`ev_models` is upserted by id and then pruned -- see `prune_ev_models` for the
foreign key that makes pruning dangerous and how it is handled.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text                       # noqa: E402

from scripts.ev_union import (COLUMNS, GLOBAL_DATASET, LOCAL_DATASET,  # noqa: E402
                              build_union)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = Path(os.getenv("RAW_DIR", ROOT / "data" / "raw"))
ZIP_PATH = Path(os.getenv("EV_DATASET_ZIP", ROOT / "ev_dataset.zip"))

PLN_SOURCE, OCM_SOURCE, OSM_SOURCE = "pln_spklu", "open_charge_map", "osm"

STATION_FEEDS: Tuple[Tuple[str, str], ...] = (
    (PLN_SOURCE, "_petaspklu_all.json"),
    (OCM_SOURCE, "ocm_jakarta.json"),
    (OSM_SOURCE, "osm_charging_jakarta.json"),
)

#: Header that identifies the raw (Kaggle-shaped) local CSV. `data/raw` also
#: holds an already-normalised copy under the same file name, which is NOT what
#: the union wants -- it has lost the price ranges and the "8.5 Jam" charging
#: times. Checking the header picks the right one instead of trusting the path.
LOCAL_CSV_MARKER = "Vehicle Name"
GLOBAL_CSV_MARKER = "battery_capacity_kWh"


# =============================================================================
# reading the files
# =============================================================================

def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def osm_elements(payload: Any) -> List[dict]:
    """The Overpass envelope unwrapped to its elements, in file order.

    A payload with no `elements` key (or a non-list one) is an empty snapshot,
    not an error: that is what an Overpass query returning nothing looks like.
    """
    if not isinstance(payload, dict):
        return []
    elements = payload.get("elements")
    return list(elements) if isinstance(elements, list) else []


def _rows_from_csv_bytes(blob: bytes) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.TextIOWrapper(
        io.BytesIO(blob), encoding="utf-8-sig", newline="")))


def read_ev_csv(member: str, marker: str, env_var: str) -> Tuple[List[Dict[str, str]], str]:
    """One EV dataset, plus where it was read from (for the summary).

    Resolution order, most explicit first:
      1. $<env_var>, when set -- an operator pointing at a refreshed extract.
      2. data/raw/<member>, when it carries `marker` in its header.
      3. the member of ev_dataset.zip, the committed immutable snapshot.
    """
    override = os.getenv(env_var, "").strip()
    if override:
        path = Path(override)
        if not path.exists():
            raise SystemExit(f"{env_var}={override} does not exist")
        return _rows_from_csv_bytes(path.read_bytes()), str(path)

    loose = RAW_DIR / member
    if loose.exists():
        rows = _rows_from_csv_bytes(loose.read_bytes())
        if rows and marker in rows[0]:
            return rows, str(loose)

    if ZIP_PATH.exists():
        with zipfile.ZipFile(ZIP_PATH) as archive:
            if member in archive.namelist():
                return _rows_from_csv_bytes(archive.read(member)), f"{ZIP_PATH}::{member}"

    raise SystemExit(
        f"cannot find {member}: set {env_var}, put a raw copy in {RAW_DIR}, "
        f"or restore {ZIP_PATH}")


# =============================================================================
# staging the three station feeds
# =============================================================================

def staging_rows(source: str, payload: Any) -> List[dict]:
    """(source, ordinal, source_id, payload) for one snapshot, in file order.

    `ordinal` is the record's index in the file and is the primary key together
    with `source`. It is what reproduces file order for `api/dedup`, and it is
    what keeps the four Open Charge Map records that share an `ID` from
    collapsing into each other.
    """
    if source == OSM_SOURCE:
        records = osm_elements(payload)
    elif isinstance(payload, list):
        records = payload
    else:
        records = []

    out: List[dict] = []
    for ordinal, record in enumerate(records):
        if not isinstance(record, dict):
            record = {"_raw": record}
        out.append({
            "source": source,
            "ordinal": ordinal,
            "source_id": _source_id(source, record),
            "payload": json.dumps(record),
        })
    return out


def _source_id(source: str, record: dict) -> Optional[str]:
    if source == PLN_SOURCE:
        raw = record.get("id")
    elif source == OCM_SOURCE:
        raw = record.get("ID")
    else:
        kind, ident = record.get("type"), record.get("id")
        raw = f"{kind}-{ident}" if kind is not None and ident is not None else ident
    return None if raw is None else str(raw)


_DELETE_SOURCE = text("DELETE FROM raw_station_records WHERE source = :source")
_INSERT_STAGING = text("""
    INSERT INTO raw_station_records (source, ordinal, source_id, payload, ingested_at)
    VALUES (:source, :ordinal, :source_id, CAST(:payload AS jsonb), now())
""")


def stage_stations(conn) -> List[Tuple[str, str, int]]:
    """Replace the staged snapshot of every station feed. Returns per-source counts."""
    summary: List[Tuple[str, str, int]] = []
    for source, filename in STATION_FEEDS:
        path = RAW_DIR / filename
        if not path.exists():
            raise SystemExit(
                f"missing raw snapshot {path}. The three station feeds are the "
                f"immutable source; ingest cannot invent them.")
        rows = staging_rows(source, read_json(path))
        # Replace, do not upsert: a shrinking snapshot must not leave orphaned
        # ordinals behind, and nothing references these rows, so a clean sweep
        # inside the transaction is both safe and exactly idempotent.
        conn.execute(_DELETE_SOURCE, {"source": source})
        if rows:
            conn.execute(_INSERT_STAGING, rows)
        summary.append((source, str(path), len(rows)))
    return summary


# =============================================================================
# the ev_models union
# =============================================================================

def _upsert_sql() -> Any:
    cols = ", ".join(COLUMNS)
    values = ", ".join(
        "CAST(:source_payload AS jsonb)" if c == "source_payload" else f":{c}"
        for c in COLUMNS)
    updates = ",\n            ".join(
        f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "id")
    return text(f"""
        INSERT INTO ev_models ({cols}, is_ev, updated_at)
        VALUES ({values}, true, now())
        ON CONFLICT (id) DO UPDATE SET
            {updates},
            is_ev = true,
            updated_at = now()
    """)


_UPSERT_EV_MODEL = _upsert_sql()


def _bind(record: Dict[str, Any]) -> Dict[str, Any]:
    params = {c: record.get(c) for c in COLUMNS}
    params["source_payload"] = json.dumps(record.get("source_payload") or {})
    return params


def upsert_ev_models(conn, records: Sequence[Dict[str, Any]]) -> int:
    if not records:
        return 0
    conn.execute(_UPSERT_EV_MODEL, [_bind(r) for r in records])
    return len(records)


# `users.ev_model_id` carries a REAL foreign key to `ev_models(id)`
# (fk_users_ev_model_id, added by migration 0011, ON DELETE SET NULL). Production
# rows point at 'byd-m6', 'byd-seal' and 'wuling-air-ev'. Deleting a referenced
# model would not raise -- ON DELETE SET NULL means Postgres would silently blank
# the driver's chosen vehicle, and the route planner would start answering 409
# "select an EV model in your profile" to somebody who already had.
#
# So the prune is guarded by NOT EXISTS against `users`: a stale model that
# nobody drives is removed, a stale model somebody drives is KEPT and reported.
# All three production ids are in the local dataset and therefore in the union
# anyway; the guard is what makes that a fact rather than a hope.
_PRUNE_UNREFERENCED = text("""
    DELETE FROM ev_models e
     WHERE NOT (e.id = ANY(:keep))
       AND NOT EXISTS (SELECT 1 FROM users u WHERE u.ev_model_id = e.id)
""")

_COUNT_PROTECTED = text("""
    SELECT e.id FROM ev_models e
     WHERE NOT (e.id = ANY(:keep))
       AND EXISTS (SELECT 1 FROM users u WHERE u.ev_model_id = e.id)
     ORDER BY e.id
""")


class EmptyUnion(SystemExit):
    """`build_union` produced nothing, so there is nothing to prune against."""


def prune_ev_models(conn, keep_ids: Sequence[str]) -> Tuple[int, List[str]]:
    """Drop models no longer in the union, except any a user still references.

    REFUSES on an empty keep list. "Keep nothing" and "the union came back
    empty" are the same argument here, and only one of them is ever intended: an
    unreadable CSV, a changed header or a bad filter would otherwise delete the
    entire catalogue in a step whose job is to load it, and the `users` guard
    below would not save it -- it only spares the two or three models somebody
    happens to drive. An ingest that found no models has failed; it has not
    discovered that the world has no EVs in it.
    """
    keep = list(keep_ids)
    if not keep:
        raise EmptyUnion(
            "refusing to prune ev_models: the union produced 0 models, which "
            "would delete the whole catalogue. Check that both EV datasets are "
            "readable (EV_SPECS_LOCAL_CSV / EV_SPECS_GLOBAL_CSV, data/raw, "
            "ev_dataset.zip) and re-run `python -m scripts.ingest_raw`.")
    protected = [r[0] for r in conn.execute(_COUNT_PROTECTED, {"keep": keep})]
    deleted = conn.execute(_PRUNE_UNREFERENCED, {"keep": keep}).rowcount
    return deleted, protected


def ingest_ev_models(conn) -> Dict[str, Any]:
    local_rows, local_src = read_ev_csv(LOCAL_DATASET, LOCAL_CSV_MARKER, "EV_SPECS_LOCAL_CSV")
    global_rows, global_src = read_ev_csv(GLOBAL_DATASET, GLOBAL_CSV_MARKER, "EV_SPECS_GLOBAL_CSV")

    records, stats = build_union(local_rows, global_rows)
    upsert_ev_models(conn, records)
    deleted, protected = prune_ev_models(conn, [r["id"] for r in records])

    return {**stats, "local_source": local_src, "global_source": global_src,
            "pruned": deleted, "protected_by_users": protected}


# =============================================================================
# entry point
# =============================================================================

def _print_summary(staged: Iterable[Tuple[str, str, int]], ev: Dict[str, Any]) -> None:
    print("raw_station_records")
    total = 0
    for source, path, count in staged:
        total += count
        print(f"  {source:<16} {count:>6} rows   <- {path}")
    print(f"  {'TOTAL':<16} {total:>6} rows")

    print("ev_models")
    print(f"  {LOCAL_DATASET:<38} {ev['local_rows']:>4} models  <- {ev['local_source']}")
    print(f"  {GLOBAL_DATASET:<38} {ev['global_rows']:>4} models  <- {ev['global_source']}")
    print(f"  collisions merged                      {ev['collisions_merged']:>4}"
          f"  {', '.join(ev['collision_ids']) or '-'}")
    if ev["local_duplicate_ids_dropped"] or ev["global_duplicate_ids_dropped"]:
        print(f"  duplicate ids dropped within a dataset  "
              f"local={ev['local_duplicate_ids_dropped']} "
              f"global={ev['global_duplicate_ids_dropped']}")
    print(f"  UNION                                  {ev['union_total']:>4} models"
          f"  ({ev['measured_efficiency']} measured efficiency, "
          f"{ev['enriched_efficiency']} enriched, {ev['derived_efficiency']} derived)")
    print(f"  pruned (no longer in either dataset)   {ev['pruned']:>4}")
    kept = ev["protected_by_users"]
    print(f"  kept because a user drives them        {len(kept):>4}"
          f"  {', '.join(kept) or '-'}")
    print("\nnext: python -m scripts.seed_db")


def main() -> None:
    from api.db import engine

    with engine.begin() as conn:
        staged = stage_stations(conn)
        ev = ingest_ev_models(conn)
    _print_summary(staged, ev)


if __name__ == "__main__":
    main()

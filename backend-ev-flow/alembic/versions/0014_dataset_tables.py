"""dataset tables: raw station staging + the global EV spec columns

Every DATASET now lives in a table. The raw JSON snapshots stay on disk as the
immutable source of truth, but they are loaded into `raw_station_records` by one
explicit ingest step (`python -m scripts.ingest_raw`) and everything downstream
-- `api/sources.py`, `scripts/seed_db.py` -- is database-to-database.

SCHEMA ONLY. No data is loaded here, deliberately: migration 0010 embedded a CSV
load and silently produced an empty `ev_models` whenever the CSV was absent,
which is exactly the failure mode the earlier review flagged. A migration that
only creates structure either succeeds or fails loudly; the data step is a
separate, re-runnable script whose summary you can read.

WHY ONE STAGING TABLE WITH A SOURCE DISCRIMINATOR, NOT THREE TABLES
-------------------------------------------------------------------
All three feeds have the same shape at this layer: an opaque JSON document, the
source's own identifier, and a position in the snapshot. Nothing downstream ever
joins them -- `normalized_rows()` simply concatenates PLN, then OCM, then OSM --
so three tables would buy no referential integrity and would triple the DDL, the
ingest path and the summary query. One table also means a fourth feed needs a
new ingest entry, not a new migration.

The primary key is (source, ordinal), NOT (source, source_id). `ordinal` is the
record's zero-based index in its snapshot file and it is load-bearing twice:

  * it reproduces file order exactly, which `api/dedup.cluster_stations` depends
    on (the first row of a cluster seeds it), and
  * `ocm_jakarta.json` holds 527 records under only 523 distinct `ID` values.
    Keying on the source identifier would silently collapse four stations and
    change the seeded totals.

`source_id` is still stored on every row -- it is the source's own identity and
the only way to trace a staged row back to the feed -- it is just not the key.

Revision ID: 0014_dataset_tables
Revises: 0013_backfill_max_dc_charge_kw
Create Date: 2026-07-27
"""
from alembic import op

revision = "0014_dataset_tables"
down_revision = "0013_backfill_max_dc_charge_kw"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- (a) staging for the three raw station feeds ------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_station_records (
            source      text        NOT NULL,
            ordinal     integer     NOT NULL,
            source_id   text,
            payload     jsonb       NOT NULL,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (source, ordinal)
        );
    """)

    # The seeder reads `WHERE source = :source ORDER BY ordinal` and nothing
    # else, which the primary key serves end to end (leading column + sort
    # order). A separate index on `source` alone would be redundant with it.
    # The one lookup the PK does NOT serve is "find the staged row behind
    # station open_charge_map-101", which is how you audit a seeded station
    # back to its feed, so that gets its own index.
    op.execute("""
        CREATE INDEX IF NOT EXISTS raw_station_records_source_id_ix
            ON raw_station_records (source, source_id);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS raw_station_records_ingested_at_ix
            ON raw_station_records (ingested_at DESC);
    """)

    # ---- (b) the spec columns the global dataset carries --------------------
    #
    # Types are matched to the observed range of electric_vehicles_spec_2025.csv
    # (478 rows):
    #   torque_nm             0 .. 1350, integral in the feed but numeric(8,2)
    #                         so a future half-Nm figure is not truncated.
    #   acceleration_0_100_s  1.9 .. 19.1, always one decimal -> numeric(5,2).
    #   number_of_cells       up to 7920, integral, 276/478 populated.
    #   towing_capacity_kg    0 .. 2500, integral.
    #   length/width/height   3673 .. 5908 mm etc, integral -> integer.
    #   battery_type          single-valued today ('Lithium-ion'); text, not an
    #                         enum, because the next feed will not be.
    #   segment               EV-database codes such as 'B - Compact'.
    #
    #   cargo_volume_l        INTEGER, and this one is a judgement call. Three
    #                         of the 478 rows read "10 Banana Boxes" /
    #                         "13 Banana Boxes" / "31 Banana Boxes" -- a count of
    #                         boxes, not litres. Parsing the leading number would
    #                         publish "10 litres of boot space" for a car, which
    #                         is a wrong number wearing the costume of a right
    #                         one. Those three rows therefore land as NULL
    #                         ("unknown"), and the verbatim source string is
    #                         still recoverable from ev_models.source_payload,
    #                         which the ingest fills with the whole CSV row.
    #                         Storing the column as text instead would keep the
    #                         string but make the other 475 rows unusable in any
    #                         comparison, which is the worse trade.
    op.execute("""
        ALTER TABLE ev_models
            ADD COLUMN IF NOT EXISTS torque_nm            numeric(8,2),
            ADD COLUMN IF NOT EXISTS acceleration_0_100_s numeric(5,2),
            ADD COLUMN IF NOT EXISTS battery_type         text,
            ADD COLUMN IF NOT EXISTS number_of_cells      integer,
            ADD COLUMN IF NOT EXISTS towing_capacity_kg   integer,
            ADD COLUMN IF NOT EXISTS cargo_volume_l       integer,
            ADD COLUMN IF NOT EXISTS segment              text,
            ADD COLUMN IF NOT EXISTS length_mm            integer,
            ADD COLUMN IF NOT EXISTS width_mm             integer,
            ADD COLUMN IF NOT EXISTS height_mm            integer;
    """)

    # Columns 0010 creates but 0011's CREATE TABLE IF NOT EXISTS would skip on a
    # database that reached 0011 by another route. The union ingest writes all of
    # them, so guarantee they exist rather than let the INSERT fail at deploy.
    op.execute("""
        ALTER TABLE ev_models
            ADD COLUMN IF NOT EXISTS brand                     text,
            ADD COLUMN IF NOT EXISTS power_hp                  text,
            ADD COLUMN IF NOT EXISTS seats                     integer,
            ADD COLUMN IF NOT EXISTS top_speed_kmh             double precision,
            ADD COLUMN IF NOT EXISTS fast_charging_power_kw_dc double precision,
            ADD COLUMN IF NOT EXISTS car_body_type             text,
            ADD COLUMN IF NOT EXISTS drivetrain                text,
            ADD COLUMN IF NOT EXISTS is_ev                     boolean NOT NULL DEFAULT true;
    """)

    # The catalogue is listed and searched by name and filtered by segment in
    # the UI; both are sequential scans over 535 rows without these.
    op.execute("CREATE INDEX IF NOT EXISTS ev_models_name_ix ON ev_models (lower(name));")
    op.execute("CREATE INDEX IF NOT EXISTS ev_models_segment_ix ON ev_models (segment);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ev_models_segment_ix;")
    op.execute("DROP INDEX IF EXISTS ev_models_name_ix;")
    op.execute("""
        ALTER TABLE ev_models
            DROP COLUMN IF EXISTS torque_nm,
            DROP COLUMN IF EXISTS acceleration_0_100_s,
            DROP COLUMN IF EXISTS battery_type,
            DROP COLUMN IF EXISTS number_of_cells,
            DROP COLUMN IF EXISTS towing_capacity_kg,
            DROP COLUMN IF EXISTS cargo_volume_l,
            DROP COLUMN IF EXISTS segment,
            DROP COLUMN IF EXISTS length_mm,
            DROP COLUMN IF EXISTS width_mm,
            DROP COLUMN IF EXISTS height_mm;
    """)
    # The 0010/0011 columns above are NOT dropped here: they predate this
    # migration and dropping them would take data 0014 never created.
    op.execute("DROP TABLE IF EXISTS raw_station_records;")

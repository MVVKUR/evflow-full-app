"""station_hourly_occupancy table + its refresh procedure

The occupancy feature shipped straight into the production database by hand: the
table and the procedure exist on the VPS but nothing in this repository creates
them. Anywhere else -- CI, a teammate's laptop, a rebuilt server -- the endpoint
at api/main.py `GET /api/v1/stations/{station_id}/occupancy` raises

    UndefinedTable: relation "station_hourly_occupancy" does not exist

and returns an unhandled 500. This revision closes that gap by reproducing what
production actually runs today, so a fresh `alembic upgrade head` yields the
same schema the deployed API was written against.

Both statements are written to be no-ops against the existing production
database: CREATE TABLE IF NOT EXISTS leaves the populated table (491,400 rows at
the time of writing) untouched, and CREATE OR REPLACE PROCEDURE rewrites the
body with the identical source that is already installed there.

What is deliberately NOT here: process_charging_simulation() and
run_charging_simulation_batch(). Those fabricate charging_sessions rows and
write connectors.status directly, which is how 3,669 connectors ended up stuck
showing as occupied to real users on 2026-07-29. Installing them everywhere by
migration would hand every environment, production included, a loaded gun. They
live in scripts/sql/charging_simulation.sql instead, to be applied deliberately
and only where fabricated data is wanted.

The refresh procedure aggregates the last 28 days of charging_sessions into one
row per station per weekday-hour, classifying each at 20 / 50 / 80 percent into
LOW / MODERATE / BUSY / PEAK. day_of_week follows ISO numbering (EXTRACT(ISODOW),
1 = Monday), which does NOT line up with JavaScript's Date.getDay().

Revision ID: 0016_station_hourly_occupancy
Revises: 0015_charging_sessions_conn_ix

Keep revision ids at 32 characters or fewer: alembic_version.version_num is
varchar(32).
"""

from alembic import op

revision = "0016_station_hourly_occupancy"
down_revision = "0015_charging_sessions_conn_ix"
branch_labels = None
depends_on = None


_TABLE = """
CREATE TABLE IF NOT EXISTS station_hourly_occupancy (
    id              SERIAL PRIMARY KEY,
    -- text, not uuid: station ids are source-derived strings like 'pln_spklu-1'
    station_id      TEXT        NOT NULL,
    day_of_week     SMALLINT    NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    hour_of_day     SMALLINT    NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    avg_occupancy   NUMERIC(5,2) NOT NULL CHECK (avg_occupancy BETWEEN 0 AND 100),
    occupancy_level VARCHAR(10) NOT NULL
                    CHECK (occupancy_level IN ('LOW', 'MODERATE', 'BUSY', 'PEAK')),
    last_updated    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    -- one row per station per weekday-hour; the refresh procedure upserts on it
    CONSTRAINT uq_station_day_hour UNIQUE (station_id, day_of_week, hour_of_day)
)
"""


# No foreign key to stations(id) on purpose: seeding rebuilds the stations table
# wholesale, and a FK here would either cascade this aggregate away or block the
# re-seed. Station ids are deterministic, so rows stay addressable across seeds.
_REFRESH_PROCEDURE = """
CREATE OR REPLACE PROCEDURE refresh_station_hourly_occupancy()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO station_hourly_occupancy (
        station_id, day_of_week, hour_of_day,
        avg_occupancy, occupancy_level, last_updated
    )
    WITH station_capacity AS (
        SELECT station_id, COUNT(*)::NUMERIC AS total_connectors
        FROM connectors
        GROUP BY station_id
    ),
    hourly_slots AS (
        -- every station x 7 days x 24 hours, so quiet slots are recorded as 0
        -- rather than simply missing
        SELECT sc.station_id, sc.total_connectors,
               d.dow AS day_of_week, h.hour_val AS hour_of_day
        FROM station_capacity sc
        CROSS JOIN generate_series(1, 7)  AS d(dow)
        CROSS JOIN generate_series(0, 23) AS h(hour_val)
    ),
    session_overlaps AS (
        SELECT
            cs.station_id,
            EXTRACT(ISODOW FROM cs.created_at)::INT AS day_of_week,
            EXTRACT(HOUR  FROM cs.created_at)::INT  AS hour_of_day,
            LEAST(
                EXTRACT(EPOCH FROM (COALESCE(cs.completed_at, NOW()) - cs.created_at)) / 60.0,
                60.0
            ) AS active_minutes
        FROM charging_sessions cs
        WHERE cs.created_at IS NOT NULL
          AND cs.created_at >= (NOW() - INTERVAL '28 days')
    ),
    aggregated_occupancy AS (
        SELECT
            hs.station_id, hs.day_of_week, hs.hour_of_day,
            ROUND(
                LEAST(
                    COALESCE(
                        (AVG(so.active_minutes) / NULLIF(hs.total_connectors * 60.0, 0)) * 100.0,
                        0.0
                    ),
                    100.0
                )::NUMERIC,
                2
            ) AS calculated_avg_occupancy
        FROM hourly_slots hs
        LEFT JOIN session_overlaps so
               ON hs.station_id  = so.station_id
              AND hs.day_of_week = so.day_of_week
              AND hs.hour_of_day = so.hour_of_day
        GROUP BY hs.station_id, hs.day_of_week, hs.hour_of_day, hs.total_connectors
    )
    SELECT
        station_id, day_of_week, hour_of_day,
        calculated_avg_occupancy,
        CASE
            WHEN calculated_avg_occupancy >= 80 THEN 'PEAK'
            WHEN calculated_avg_occupancy >= 50 THEN 'BUSY'
            WHEN calculated_avg_occupancy >= 20 THEN 'MODERATE'
            ELSE 'LOW'
        END,
        NOW()
    FROM aggregated_occupancy
    ON CONFLICT (station_id, day_of_week, hour_of_day)
    DO UPDATE SET
        avg_occupancy   = EXCLUDED.avg_occupancy,
        occupancy_level = EXCLUDED.occupancy_level,
        last_updated    = EXCLUDED.last_updated;
END;
$$
"""


def upgrade() -> None:
    op.execute(_TABLE)
    op.execute(_REFRESH_PROCEDURE)


def downgrade() -> None:
    op.execute("DROP PROCEDURE IF EXISTS refresh_station_hourly_occupancy()")
    op.execute("DROP TABLE IF EXISTS station_hourly_occupancy")

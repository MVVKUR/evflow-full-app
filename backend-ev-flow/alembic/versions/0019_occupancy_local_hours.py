"""Bucket occupancy by Jakarta hours, not UTC hours.

charging_sessions.created_at is timestamptz. EXTRACT on a timestamptz converts
to the session's TimeZone setting before pulling the field out, and this
database runs Etc/UTC, so every bucket in station_hourly_occupancy was a UTC
hour wearing a local label.

The size of it: the peak-hours chart reported 15:00 to 19:00 as the busiest
window and 00:00 to 04:00 as the quietest. Read as Jakarta time, which is how
the chart is labelled and how a driver reads it, that says the network is
busiest from 22:00 to 02:00 and emptiest during the morning commute. Both
statements are the truth shifted seven hours.

Three expressions had to move, not two. day_of_week and hour_of_day are the
visible ones. occurred_on is the denominator's day count, and leaving it on the
UTC date splits a single Jakarta day across two of them, so hours either side of
local midnight are divided by one day too many and read quieter than they were.

Nothing else changes. Same aggregation, same thresholds, same conflict handling
as 0017; only the timezone the timestamps are read in.

The alternative, setting the database TimeZone to Asia/Jakarta, was rejected. It
would silently change every other timestamptz comparison in the application,
including the ones that are correct to reason in UTC.

Existing rows are corrected by running CALL refresh_station_hourly_occupancy();
after this migration. The procedure recomputes the whole 28 day window, so the
mislabelled buckets are overwritten rather than left to age out.

Revision ID: 0019_occupancy_local_hours
Revises: 0018_planning_cells
"""
from alembic import op

revision = "0019_occupancy_local_hours"
down_revision = "0018_planning_cells"
branch_labels = None
depends_on = None


_LOCAL_HOUR_PROCEDURE = """
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
        SELECT sc.station_id, sc.total_connectors,
               d.dow AS day_of_week, h.hour_val AS hour_of_day
        FROM station_capacity sc
        CROSS JOIN generate_series(1, 7)  AS d(dow)
        CROSS JOIN generate_series(0, 23) AS h(hour_val)
    ),
    session_overlaps AS (
        SELECT
            cs.station_id,
            EXTRACT(ISODOW FROM cs.created_at AT TIME ZONE 'Asia/Jakarta')::INT AS day_of_week,
            EXTRACT(HOUR  FROM cs.created_at AT TIME ZONE 'Asia/Jakarta')::INT  AS hour_of_day,
            -- occurred_on is the denominator's day count, so it has to roll
            -- over on the same boundary as the buckets above. Left as a UTC
            -- date it splits one Jakarta day across two, and every hour near
            -- midnight is divided by one day too many.
            (cs.created_at AT TIME ZONE 'Asia/Jakarta')::date  AS occurred_on,
            -- GREATEST floors a negative span. Without it a row whose
            -- completed_at precedes created_at drives the sum below zero and the
            -- column's CHECK aborts the whole refresh.
            GREATEST(LEAST(
                EXTRACT(EPOCH FROM (COALESCE(cs.completed_at, NOW()) - cs.created_at)) / 60.0,
                60.0
            ), 0) AS active_minutes
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
                        SUM(so.active_minutes)
                          / NULLIF(hs.total_connectors * 60.0
                                   * GREATEST(COUNT(DISTINCT so.occurred_on), 1), 0)
                        * 100.0,
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

_UTC_HOUR_PROCEDURE = """
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
            cs.created_at::date                     AS occurred_on,
            -- GREATEST floors a negative span. Without it a row whose
            -- completed_at precedes created_at drives the sum below zero and the
            -- column's CHECK aborts the whole refresh.
            GREATEST(LEAST(
                EXTRACT(EPOCH FROM (COALESCE(cs.completed_at, NOW()) - cs.created_at)) / 60.0,
                60.0
            ), 0) AS active_minutes
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
                        SUM(so.active_minutes)
                          / NULLIF(hs.total_connectors * 60.0
                                   * GREATEST(COUNT(DISTINCT so.occurred_on), 1), 0)
                        * 100.0,
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
    op.execute(_LOCAL_HOUR_PROCEDURE)


def downgrade() -> None:
    # Safe to reverse: this is a procedure definition, not data. Reverting puts
    # the UTC-hour reading back, which is wrong but is what 0017 shipped.
    op.execute(_UTC_HOUR_PROCEDURE)

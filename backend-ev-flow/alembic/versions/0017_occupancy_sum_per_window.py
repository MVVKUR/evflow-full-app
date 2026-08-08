"""correct the occupancy formula: sum over the window, not average per session

refresh_station_hourly_occupancy divided AVG(active_minutes) by the station's
capacity for one hour. AVG is per session; the denominator is whole-station, so
the two were different units and a station's reading was capped at
100 / connector_count. Measured before this change: 1 connector reached 100%,
2 reached 50, 4 reached 25, 8 reached 12.5, 17 reached 5.88. Any station with
three or more plugs could never cross the 20% MODERATE threshold, so the map's
peak-hours colours were green everywhere by construction.

Two further signs it was unintended: the LEAST(..., 100) clamp and the column's
CHECK (0..100) are both unreachable under AVG, and dividing by the session count
means MORE demand can LOWER the reading -- one 60-minute session at a
1-connector station reads 100, adding a second 6-minute session drops it to 55.

Swapping AVG for SUM alone would have been wrong in the other direction. A
28-day window holds four occurrences of each weekday-hour, so the sum would
over-report by roughly 4x and saturate at the clamp: every popular hour a flat
100 wall. The denominator therefore also divides by the number of dates actually
observed in that slot, COUNT(DISTINCT occurred_on), which is self-correcting for
a partial or shortened window rather than assuming four.

Also adds a GREATEST(..., 0) floor on the per-session span. AVG diluted a
negative duration; SUM would not, and a row whose completed_at precedes its
created_at would drive the value below zero and abort the whole refresh on the
column CHECK.

Verified on staging against 1.1M sessions: the cap is gone (8 connectors now
reach 98.02, 17 reach 57.05), the level mix spreads across all four bands
instead of collapsing into LOW, and no row violates the 0..100 CHECK. The
procedure takes about 30 seconds.

This rewrites stored values for every station. Nothing is lost that cannot be
recomputed: the aggregate is derived entirely from charging_sessions.

Revision ID: 0017_occupancy_sum_per_window
Revises: 0016_station_hourly_occupancy
"""

from alembic import op

revision = "0017_occupancy_sum_per_window"
down_revision = "0016_station_hourly_occupancy"
branch_labels = None
depends_on = None


_CORRECTED_PROCEDURE = """
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
    op.execute(_CORRECTED_PROCEDURE)
    # Recompute immediately: leaving the old capped values in place would mean
    # the fix only takes effect the next time something happens to call it.
    op.execute("CALL refresh_station_hourly_occupancy()")


def downgrade() -> None:
    # Intentionally not restoring the AVG version. It produced values that were
    # wrong by a factor of the connector count, and a downgrade that reinstates
    # a known-bad formula is not a safety net.
    raise NotImplementedError(
        "0017 corrects a formula; reverting would restore readings capped at "
        "100/connector_count. Recompute from charging_sessions instead."
    )

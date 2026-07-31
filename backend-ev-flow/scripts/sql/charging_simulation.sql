-- Charging-session simulation, by M Aidil Akbar, 2026-07-29.
--
-- Generates synthetic charging_sessions so refresh_station_hourly_occupancy()
-- has history to aggregate into the peak-hours chart. Kept in the repository so
-- the logic is not lost, but deliberately NOT installed by any migration.
--
-- WHY IT IS NOT A MIGRATION
--
-- process_charging_simulation() writes connectors.status = 'in_use' directly,
-- and only frees a connector again once the simulated session's duration has
-- elapsed. That is the same column the live Epic 2 availability path reads
-- (api/connectors_repo.py, api/services/station_availability.py), so simulated
-- state is indistinguishable from reality to a driver looking at the map.
--
-- A batch that stops before its sessions finish leaves connectors occupied
-- forever. On 2026-07-29 this left 3,669 of 6,733 connectors stuck as occupied
-- in production: for a week the map showed roughly half the SPKLU in Indonesia
-- as full, and route planning skipped stations that were actually free. It was
-- only cleared by re-seeding on 2026-07-30.
--
-- BEFORE YOU RUN THIS
--
--   1. Never against production. Point DATABASE_URL at a scratch database.
--   2. Run one extra step past your end_time so in-flight sessions complete and
--      release their connectors, or reset them afterwards with
--      UPDATE connectors SET status = 'available' WHERE status = 'in_use';
--   3. Afterwards, CALL refresh_station_hourly_occupancy(); to build the
--      aggregate the /occupancy endpoint reads.
--
-- Install:  psql "$DATABASE_URL" -f scripts/sql/charging_simulation.sql
-- Use:      CALL run_charging_simulation_batch(
--               '2026-06-01'::timestamptz, '2026-07-01'::timestamptz, '15 minutes');

CREATE OR REPLACE PROCEDURE process_charging_simulation(input_time TIMESTAMPTZ)
LANGUAGE plpgsql
AS $$
DECLARE
    conn RECORD;
    active_session RECORD;
    random_int INT;
    rand_user_id UUID;
    req_threshold INT;
    is_weekend BOOLEAN;
    hour_val INT;
    rand_energy FLOAT8;
    remain_minutes FLOAT8;
    session_created_at TIMESTAMPTZ;
    min_energy NUMERIC;
    max_energy NUMERIC;
BEGIN
    is_weekend := EXTRACT(ISODOW FROM input_time) IN (6, 7);
    hour_val := EXTRACT(HOUR FROM input_time);

    -- 1. Walk every free connector and decide whether a session starts in this
    --    15-minute window. Thresholds are per-window, derived from an hourly
    --    demand curve (the comments give the original hourly figure).
    FOR conn IN
        SELECT id, station_id, type, power_kw
        FROM connectors
        WHERE status = 'available'
    LOOP
        random_int := floor(random() * 100)::INT;

        IF is_weekend THEN
            IF hour_val BETWEEN 0 AND 5 THEN
                req_threshold := 3;   -- 10%/hr
            ELSIF hour_val BETWEEN 6 AND 10 THEN
                req_threshold := 10;  -- 35%/hr
            ELSIF hour_val BETWEEN 11 AND 15 THEN
                req_threshold := 23;  -- 65%/hr
            ELSIF hour_val BETWEEN 16 AND 21 THEN
                req_threshold := 38;  -- 85%/hr
            ELSE
                req_threshold := 9;   -- 30%/hr
            END IF;
        ELSE
            IF hour_val BETWEEN 0 AND 5 THEN
                req_threshold := 4;   -- 15%/hr
            ELSIF hour_val BETWEEN 6 AND 9 THEN
                req_threshold := 29;  -- 75%/hr
            ELSIF hour_val BETWEEN 10 AND 14 THEN
                req_threshold := 18;  -- 55%/hr
            ELSIF hour_val BETWEEN 15 AND 20 THEN
                req_threshold := 44;  -- 90%/hr
            ELSE
                req_threshold := 10;  -- 35%/hr
            END IF;
        END IF;

        IF random_int < req_threshold THEN
            SELECT id INTO rand_user_id FROM users ORDER BY random() LIMIT 1;

            -- Energy drawn is bounded by charger class, so simulated dwell
            -- times stay plausible for the hardware.
            IF conn.power_kw < 20.0 THEN
                min_energy := 5.0;   max_energy := 35.0;  -- slow AC, 1-5 h
            ELSIF conn.power_kw < 50.0 THEN
                min_energy := 12.0;  max_energy := 45.0;  -- medium DC, 45 m - 2 h
            ELSIF conn.power_kw <= 150.0 THEN
                min_energy := 18.0;  max_energy := 60.0;  -- fast DC, 25-45 m
            ELSE
                min_energy := 25.0;  max_energy := 75.0;  -- ultra-fast, 15-35 m
            END IF;

            rand_energy := ROUND((min_energy + (random() * (max_energy - min_energy)))::NUMERIC, 2);

            session_created_at := input_time
                - (floor(random() * 14) || ' minutes')::INTERVAL
                - (floor(random() * 59) || ' seconds')::INTERVAL;

            INSERT INTO charging_sessions (
                id, station_id, station_name, connector_type, power_kw,
                energy_kwh, base_rate_idr, admin_fee_idr, deposit_idr,
                status, created_at, user_id, connector_id
            ) VALUES (
                gen_random_uuid(), conn.station_id,
                concat(conn.station_id, ':', random_int),
                conn.type, conn.power_kw, rand_energy,
                2467, 5000, 50000,
                'active', session_created_at, rand_user_id, conn.id
            );

            UPDATE connectors
            SET status = 'in_use', updated_at = session_created_at
            WHERE id = conn.id;
        END IF;
    END LOOP;

    -- 2. Close any session whose charge would have finished by now, and hand
    --    the connector back. Sessions still in flight when the batch ends keep
    --    their connector marked in_use -- see the header.
    FOR active_session IN
        SELECT id, power_kw, energy_kwh, created_at, connector_id,
               base_rate_idr, admin_fee_idr
        FROM charging_sessions
        WHERE status = 'active'
    LOOP
        IF active_session.power_kw > 0 THEN
            remain_minutes := (active_session.energy_kwh / active_session.power_kw) * 60.0;

            IF (active_session.created_at + (remain_minutes || ' minutes')::INTERVAL) < input_time THEN
                UPDATE charging_sessions
                SET completed_at    = active_session.created_at
                                      + (remain_minutes || ' minutes')::INTERVAL,
                    delivered_kwh   = active_session.energy_kwh,
                    actual_cost_idr = (active_session.energy_kwh
                                       * COALESCE(active_session.base_rate_idr, 2467))
                                      + COALESCE(active_session.admin_fee_idr, 0),
                    status          = 'completed'
                WHERE id = active_session.id;

                UPDATE connectors
                SET status = 'available', updated_at = input_time
                WHERE id = active_session.connector_id;
            END IF;
        END IF;
    END LOOP;
END;
$$;


CREATE OR REPLACE PROCEDURE run_charging_simulation_batch(
    start_time TIMESTAMPTZ,
    end_time   TIMESTAMPTZ,
    step       INTERVAL
)
LANGUAGE plpgsql
AS $$
DECLARE
    curr_time TIMESTAMPTZ := start_time;
BEGIN
    WHILE curr_time < end_time LOOP
        CALL process_charging_simulation(curr_time);

        -- Commit each step: one month at 15-minute resolution is ~2,900 steps
        -- and millions of rows, which is not something to hold in a single
        -- transaction.
        COMMIT;

        curr_time := curr_time + step;
    END LOOP;
END;
$$;

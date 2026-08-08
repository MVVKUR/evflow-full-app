#!/bin/bash
# One tick of the live charging simulation, for STAGING ONLY.
#
# Calling Aidil's process_charging_simulation with now() makes it a live
# simulation rather than a backfill: it starts sessions on connectors that are
# free right now, and closes the ones whose charge has finished, freeing their
# connectors again. Measured on staging: 1.7 s per tick, settling at roughly
# 13-16% of 6733 connectors busy. It does not run away.
#
# Why this is gated on the database NAME rather than a comment:
# on 2026-08-07 the simulation was run against PRODUCTION and left 435
# connectors stuck showing as occupied on the live map, because the run stopped
# mid-flight. The map cannot tell simulated occupancy from real.
set -u
DB="${SIM_DB:-evflow_staging}"
P="${PODMAN:-/usr/bin/podman}"

case "$DB" in
  *staging*) ;;
  *) echo "refusing: '$DB' is not a staging database" >&2; exit 1 ;;
esac

psql() { $P exec evflow-db psql -U evflow -d "$DB" -tAq "$@"; }

psql -c "CALL process_charging_simulation(now());" >/dev/null || exit 1

# Safety net for the case the tick loop stops entirely: without this, whatever
# was in flight stays 'active' forever and its connector stays occupied. Each
# tick already closes what it can, so this only ever catches strays.
psql -c "
UPDATE charging_sessions
   SET completed_at    = created_at + ((energy_kwh / NULLIF(power_kw,0)) * 60 || ' minutes')::interval,
       delivered_kwh   = energy_kwh,
       actual_cost_idr = (energy_kwh * COALESCE(base_rate_idr, 2467)) + COALESCE(admin_fee_idr, 0),
       status          = 'completed'
 WHERE status = 'active'
   AND power_kw > 0
   AND created_at + ((energy_kwh / NULLIF(power_kw,0)) * 60 || ' minutes')::interval < now() - interval '10 minutes';
UPDATE connectors c SET status = 'available', updated_at = now()
 WHERE c.status = 'in_use'
   AND NOT EXISTS (SELECT 1 FROM charging_sessions s
                    WHERE s.connector_id = c.id AND s.status = 'active');" >/dev/null

busy=$(psql -c "SELECT count(*) FILTER (WHERE status='in_use') || '/' || count(*) FROM connectors")
echo "$(date -Is) $DB tick ok, connectors busy: $busy"

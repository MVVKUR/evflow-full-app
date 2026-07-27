"""backfill ev_models.max_dc_charge_kw from fast_charging_power_kw_dc

`max_dc_charge_kw` (numeric(8,2), added by 0011) is what the route planner reads
to cap charging power, but the importer only ever populated
`fast_charging_power_kw_dc` (double precision, added by 0010). The planner
therefore always saw NULL and silently fell back to a 50 kW assumption.

This copies the populated column into the one the planner reads, for rows where
it is still NULL. Idempotent; safe to re-run.

Revision ID: 0013_backfill_max_dc_charge_kw
Revises: 0012_charging_time_minutes
Create Date: 2026-07-27
"""
from alembic import op

revision = "0013_backfill_max_dc_charge_kw"
down_revision = "0012_charging_time_minutes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Both columns are guaranteed present so the UPDATE below cannot fail on a
    # partially-migrated database.
    op.execute("""
        ALTER TABLE ev_models
            ADD COLUMN IF NOT EXISTS max_dc_charge_kw numeric(8,2),
            ADD COLUMN IF NOT EXISTS fast_charging_power_kw_dc double precision;
    """)

    op.execute("""
        UPDATE ev_models
           SET max_dc_charge_kw = ROUND(fast_charging_power_kw_dc::numeric, 2)
         WHERE max_dc_charge_kw IS NULL
           AND fast_charging_power_kw_dc IS NOT NULL
           AND fast_charging_power_kw_dc > 0;
    """)


def downgrade() -> None:
    # Non-destructive by design: the backfilled values are indistinguishable
    # from importer-supplied ones, so clearing them would lose real data.
    pass

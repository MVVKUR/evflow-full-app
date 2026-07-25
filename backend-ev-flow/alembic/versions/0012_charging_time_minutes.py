"""rename charging_time to charging_time_minutes and standardize to numeric minutes

Revision ID: 0012_charging_time_minutes
Revises: 0011_enrich_ev_models
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_charging_time_minutes"
down_revision = "0011_enrich_ev_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if charging_time column exists and rename it if so
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ev_models' AND column_name = 'charging_time'
            ) THEN
                ALTER TABLE ev_models RENAME COLUMN charging_time TO charging_time_minutes;
            END IF;
        END $$;
    """)

    # Ensure charging_time_minutes exists
    op.execute("""
        ALTER TABLE ev_models
            ADD COLUMN IF NOT EXISTS charging_time_minutes double precision;
    """)

    # Convert any existing text values in charging_time_minutes if column type is text/varchar
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ev_models' AND column_name = 'charging_time_minutes'
                  AND data_type IN ('text', 'character varying', 'character')
            ) THEN
                ALTER TABLE ev_models
                    ALTER COLUMN charging_time_minutes TYPE double precision
                    USING CASE
                        WHEN charging_time_minutes ~* 'jam|hour|hr' THEN
                            NULLIF(regexp_replace(charging_time_minutes, '[^0-9.]', '', 'g'), '')::double precision * 60.0
                        ELSE
                            NULLIF(regexp_replace(charging_time_minutes, '[^0-9.]', '', 'g'), '')::double precision
                    END;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ev_models' AND column_name = 'charging_time_minutes'
            ) THEN
                ALTER TABLE ev_models RENAME COLUMN charging_time_minutes TO charging_time;
                ALTER TABLE ev_models ALTER COLUMN charging_time TYPE text USING charging_time::text;
            END IF;
        END $$;
    """)

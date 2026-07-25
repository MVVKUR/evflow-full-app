-- Raw SQL reference script for Epic 2.0 EV Models schema enrichment

CREATE TABLE IF NOT EXISTS ev_models (
  id text PRIMARY KEY,
  name text NOT NULL,
  make text,
  model text,
  battery_kwh numeric(8,2),
  battery_kwh_min numeric(8,2),
  battery_kwh_max numeric(8,2),
  range_km numeric(8,2),
  range_km_min numeric(8,2),
  range_km_max numeric(8,2),
  efficiency_wh_per_km numeric(8,2),
  efficiency_source text,
  max_dc_charge_kw numeric(8,2),
  fast_charge_port text,
  price_range text,
  charging_time text,
  source_url text,
  source_datasets text[] NOT NULL DEFAULT '{}',
  source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  match_method text,
  match_confidence numeric(5,4),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ev_models
  ADD COLUMN IF NOT EXISTS battery_kwh_min numeric(8,2),
  ADD COLUMN IF NOT EXISTS battery_kwh_max numeric(8,2),
  ADD COLUMN IF NOT EXISTS range_km_min numeric(8,2),
  ADD COLUMN IF NOT EXISTS range_km_max numeric(8,2),
  ADD COLUMN IF NOT EXISTS efficiency_wh_per_km numeric(8,2),
  ADD COLUMN IF NOT EXISTS efficiency_source text,
  ADD COLUMN IF NOT EXISTS max_dc_charge_kw numeric(8,2),
  ADD COLUMN IF NOT EXISTS fast_charge_port text,
  ADD COLUMN IF NOT EXISTS source_datasets text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS match_method text,
  ADD COLUMN IF NOT EXISTS match_confidence numeric(5,4),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS ix_ev_models_make_model
  ON ev_models (lower(make), lower(model));

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_ev_model_id'
  ) THEN
    ALTER TABLE users
      ADD CONSTRAINT fk_users_ev_model_id
      FOREIGN KEY (ev_model_id) REFERENCES ev_models(id)
      ON DELETE SET NULL NOT VALID;
  END IF;
END $$;

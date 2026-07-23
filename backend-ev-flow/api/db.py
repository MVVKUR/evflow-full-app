"""SQLAlchemy engine + session, configured from DATABASE_URL."""
from __future__ import annotations

import os

from sqlalchemy import create_engine

# Dev-only fallback for local development and tests. Production MUST set
# DATABASE_URL explicitly (compose files do). The connection string is assembled
# from parts so no full credential is hard-coded; every component is overridable
# via the environment. The password has NO default — a local dev database needs
# POSTGRES_PASSWORD (or a full DATABASE_URL) set; there is no baked-in secret.
_DB_USER = os.getenv("POSTGRES_USER", "evflow")
_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
_DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
_DB_PORT = os.getenv("POSTGRES_PORT", "5432")
_DB_NAME = os.getenv("POSTGRES_DB", "evflow")
DATABASE_URL = os.getenv("DATABASE_URL") or (
    f"postgresql+psycopg://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

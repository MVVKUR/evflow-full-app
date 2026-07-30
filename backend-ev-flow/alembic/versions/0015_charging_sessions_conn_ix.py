"""index charging_sessions.connector_id

charging_sessions.connector_id carries an ON DELETE SET NULL foreign key, but
had no supporting index. Postgres does not index the referencing side of a
foreign key automatically, so every connector deletion had to sequentially scan
charging_sessions to find the rows it needed to null out.

That stayed invisible while the table was small. Once the table reached ~2.2M
rows / 817 MB, re-seeding stations (which cascades to ~6.7k connectors) implied
roughly 6.7k full scans of the table -- multiple hours holding locks on the
session history.

Plain CREATE INDEX, not CONCURRENTLY: Alembic wraps each migration in a
transaction and CONCURRENTLY cannot run inside one. IF NOT EXISTS keeps this a
no-op where the index was already created by hand against a live database.

Revision ID: 0015_charging_sessions_conn_ix
Revises: 0014_dataset_tables

Keep revision ids at 32 characters or fewer: alembic_version.version_num is
varchar(32), and a longer id only fails at the very end of the upgrade, after
the migration's own DDL has run.
"""

from alembic import op

revision = "0015_charging_sessions_conn_ix"
down_revision = "0014_dataset_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS charging_sessions_connector_ix "
        "ON charging_sessions (connector_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS charging_sessions_connector_ix;")

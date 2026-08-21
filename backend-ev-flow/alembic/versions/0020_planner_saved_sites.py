"""Planner bookmarks for real planning cells.

Revision ID: 0020_planner_saved_sites
Revises: 0019_occupancy_local_hours
"""
from alembic import op

revision = "0020_planner_saved_sites"
down_revision = "0019_occupancy_local_hours"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE planner_saved_sites (
            user_id uuid NOT NULL,
            cell_id text NOT NULL,
            saved_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, cell_id),
            CONSTRAINT fk_planner_saved_sites_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_planner_saved_sites_cell
                FOREIGN KEY (cell_id) REFERENCES planning_cells(cell_id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE INDEX planner_saved_sites_user_saved_at_ix
        ON planner_saved_sites (user_id, saved_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE planner_saved_sites")

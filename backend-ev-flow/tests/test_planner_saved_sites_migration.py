from pathlib import Path


def test_saved_sites_migration_integrity_contract():
    source = (Path(__file__).parents[1] / "alembic/versions/0020_planner_saved_sites.py").read_text()
    assert 'down_revision = "0019_occupancy_local_hours"' in source
    assert "PRIMARY KEY (user_id, cell_id)" in source
    assert "REFERENCES users(id) ON DELETE CASCADE" in source
    assert "REFERENCES planning_cells(cell_id) ON DELETE CASCADE" in source
    assert "planner_saved_sites_user_saved_at_ix" in source
    assert "user_id, saved_at DESC" in source
    assert 'op.execute("DROP TABLE planner_saved_sites")' in source

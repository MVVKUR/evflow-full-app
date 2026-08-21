"""Saved Sites endpoint boundaries and user isolation."""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import main


PLANNER_A = {"id": "00000000-0000-0000-0000-00000000000a", "account_type": "business_planner"}
PLANNER_B = {"id": "00000000-0000-0000-0000-00000000000b", "account_type": "business_planner"}


def test_save_is_idempotent_and_uses_authenticated_user(monkeypatch):
    calls = []
    monkeypatch.setattr(main.planner_repo, "get_cell", lambda cell_id: {"cell_id": cell_id})
    monkeypatch.setattr(main.planner_repo, "save_site", lambda user_id, cell_id: calls.append((user_id, cell_id)))
    assert main.planner_save_site("CELL-1", PLANNER_A).saved is True
    assert main.planner_save_site("CELL-1", PLANNER_A).saved is True
    assert calls == [(PLANNER_A["id"], "CELL-1"), (PLANNER_A["id"], "CELL-1")]


def test_unknown_cell_is_404(monkeypatch):
    monkeypatch.setattr(main.planner_repo, "get_cell", lambda _cell_id: None)
    with pytest.raises(HTTPException) as error:
        main.planner_save_site("missing", PLANNER_A)
    assert error.value.status_code == 404


def test_status_true_and_false_are_scoped_to_current_user(monkeypatch):
    saved = {(PLANNER_A["id"], "CELL-1")}
    monkeypatch.setattr(main.planner_repo, "is_site_saved", lambda user_id, cell_id: (user_id, cell_id) in saved)
    assert main.planner_saved_site_status("CELL-1", PLANNER_A).saved is True
    assert main.planner_saved_site_status("CELL-1", PLANNER_B).saved is False


def test_remove_is_safe_and_cannot_remove_another_planners_site(monkeypatch):
    calls = []
    monkeypatch.setattr(main.planner_repo, "unsave_site", lambda user_id, cell_id: calls.append((user_id, cell_id)))
    assert main.planner_unsave_site("CELL-1", PLANNER_A).saved is False
    assert main.planner_unsave_site("CELL-1", PLANNER_A).saved is False
    assert calls == [(PLANNER_A["id"], "CELL-1"), (PLANNER_A["id"], "CELL-1")]


def test_list_returns_only_rows_selected_for_authenticated_user(monkeypatch):
    seen = []
    row = {
        "cell_id": "CELL-1", "kota": "Kota Jakarta Timur", "score": 0.74,
        "latitude": -6.22, "longitude": 106.90,
        "poi_total": 4, "nearest_station_m": 500, "road_nodes": 9,
        "lu_residential_share": 0.4, "saved_at": datetime.now(timezone.utc),
    }
    monkeypatch.setattr(main.planner_repo, "list_saved_sites", lambda user_id: seen.append(user_id) or [row])
    response = main.planner_saved_sites(PLANNER_A)
    assert seen == [PLANNER_A["id"]]
    assert response.total == 1 and response.items[0].cell_id == "CELL-1"


def test_driver_is_forbidden_before_saved_site_handler_runs():
    with pytest.raises(HTTPException) as error:
        main.require_planner({"id": "driver", "account_type": "ev_user"})
    assert error.value.status_code == 403


def test_signed_out_saved_sites_request_is_401():
    main.app.dependency_overrides.pop(main.require_planner, None)
    response = TestClient(main.app).get("/api/v1/planner/saved-sites")
    assert response.status_code == 401


def test_saved_site_models_preserve_api_order(monkeypatch):
    now = datetime.now(timezone.utc)
    def row(cell_id):
        return {"cell_id": cell_id, "kota": None, "score": .5, "poi_total": 0,
                "latitude": -6.2, "longitude": 106.8,
                "nearest_station_m": None, "road_nodes": 0, "lu_residential_share": 0,
                "saved_at": now}
    monkeypatch.setattr(main.planner_repo, "list_saved_sites", lambda _user_id: [row("B"), row("A")])
    assert [item.cell_id for item in main.planner_saved_sites(PLANNER_A).items] == ["B", "A"]

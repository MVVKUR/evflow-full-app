"""A cell must carry one score, whichever endpoint a planner meets it through.

The score is a percentile rank, which is a position within a set. Rank a cell
against all 28,176 in the detail panel while the map ranks it against the 27,219
that survive the filter, and the same cell reads 0.8390 on the map and 0.8374 in
the panel. Nothing errors, nothing logs, and the planner simply stops trusting
the number. These tests pin the defaults together so the two cannot drift apart
again without a failure saying so.
"""
import inspect

from api import planner_repo
from api.models import PlannerCellDetail


def _defaults(fn):
    return {name: p.default for name, p in inspect.signature(fn).parameters.items()
            if p.default is not inspect.Parameter.empty}


def test_get_cell_filters_on_the_same_basis_as_the_ranked_list():
    listed = _defaults(planner_repo.score_cells)
    detail = _defaults(planner_repo.get_cell)
    for key in ("min_overlap", "excluded_kota"):
        assert key in detail, f"get_cell must take {key} so it can match the list"
        assert detail[key] == listed[key], (
            f"get_cell defaults {key}={detail[key]!r} but score_cells uses "
            f"{listed[key]!r}; the same cell would score differently in each")


def test_candidates_filter_on_the_same_basis_too():
    listed = _defaults(planner_repo.score_cells)
    cand = _defaults(planner_repo.candidate_sites)
    assert cand["min_overlap"] == listed["min_overlap"]
    assert cand["excluded_kota"] == listed["excluded_kota"]


def test_an_unranked_cell_is_representable():
    # A cell the filter excludes is still on the map, so clicking it must explain
    # itself rather than 404 or borrow a score computed on another basis.
    detail = PlannerCellDetail(
        cell_id="JBDTBK_00001", latitude=-6.2, longitude=106.8,
        score=None, rank_overall=None, cells_total=27219, in_scored_set=False,
        population=0.0, poi={"total": 0}, land_use={"residential": 0.0},
        road_nodes=0, road_length_m=0.0, station_count=0, connector_count=0,
        stations_2km=0,
    )
    assert detail.score is None and detail.rank_overall is None
    assert detail.in_scored_set is False


def test_a_ranked_cell_still_defaults_to_being_in_the_set():
    # Callers that never look at the flag must not read an excluded cell as
    # included, so the safe reading is the default.
    detail = PlannerCellDetail(
        cell_id="JBDTBK_00002", latitude=-6.2, longitude=106.8,
        score=0.5, rank_overall=10, cells_total=27219,
        population=1.0, poi={"total": 0}, land_use={"residential": 0.0},
        road_nodes=0, road_length_m=0.0, station_count=0, connector_count=0,
        stations_2km=0,
    )
    assert detail.in_scored_set is True

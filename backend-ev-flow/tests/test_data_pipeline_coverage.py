"""Data ingestion + EV catalogue + station query coverage.

Three layers of the data pipeline are exercised here:

* ``api.sources``      -- the PLN SPKLU / Open Charge Map / OpenStreetMap loaders
                          and their normalisation into one row schema. Every test
                          feeds a hand-built fixture file rather than the 3029-row
                          production dump, so the messy branches (string
                          coordinates, Null Island, free-text power, OSM elements
                          with no ``name`` or no ``tags`` at all) are reachable and
                          deterministic.
* ``api.evmodels``      -- the DB-backed catalogue load, the Decimal->float
                          coercion at the repository boundary, the JSON/CSV/zip
                          fallbacks, ``get``/``search``/paging and the range maths.
* ``api.stations_repo`` -- the filter combinations the endpoints expose and the
                          corridor query used by route planning, against a small
                          synthetic set of stations parked far away from the
                          seeded Indonesian data so assertions are exact.

Tests marked ``xfail`` document behaviour the pipeline SHOULD have; see the
reason string on each for the defect it pins.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from api import evmodels, sources
from tests.conftest import requires_db

# =============================================================================
# api/sources.py
# =============================================================================


@pytest.fixture
def write_raw(tmp_path, monkeypatch):
    """Point the three loaders at empty tmp paths; return a writer for fixtures.

    A source file that is never written simply does not exist, which is the
    "missing file" branch of every loader.
    """
    paths = {
        "pln": tmp_path / "_petaspklu_all.json",
        "ocm": tmp_path / "ocm_jakarta.json",
        "osm": tmp_path / "osm_charging_jakarta.json",
    }
    monkeypatch.setattr(sources, "PLN_PATH", paths["pln"])
    monkeypatch.setattr(sources, "OCM_PATH", paths["ocm"])
    monkeypatch.setattr(sources, "OSM_PATH", paths["osm"])

    def write(kind: str, payload) -> Path:
        paths[kind].write_text(json.dumps(payload), encoding="utf-8")
        return paths[kind]

    return write


def _pln_record(**overrides) -> dict:
    """A PLN SPKLU record shaped exactly like the production dump."""
    rec = {
        "id": 1,
        "provinsi": "DKI Jakarta ",          # the real feed has trailing spaces
        "kabupaten_kota": "Kota ADM Jakarta Pusat",
        "nama_lokasi": "SPKLU PLN UID JAKARTA RAYA",
        "alamat": "Jl. M.I. Ridwan Rais No.1",
        "latitude": "-6.1803900",            # coordinates arrive as STRINGS
        "longitude": "106.8331910",
        "status": 1,
        "type_charge": "medium",
        "watt": "22 kW",                     # power is free text
        "total_charger": 0,
        "total_konektor": 0,
    }
    rec.update(overrides)
    return rec


# ---- _num / _clean_power ----------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("22 kW", 22.0),
    ("7 kW", 7.0),
    ("150", 150.0),
    (60, 60.0),
    (47.5, 47.5),
])
def test_num_extracts_the_leading_number_from_free_text(raw, expected):
    assert sources._num(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw", [None, "", "   ", "unknown", "kW 22", [], {}])
def test_num_returns_nan_for_anything_unparseable(raw):
    assert math.isnan(sources._num(raw))


@pytest.mark.unit
def test_clean_power_maps_nan_and_none_to_none_and_keeps_numbers():
    assert sources._clean_power(None) is None
    assert sources._clean_power(math.nan) is None
    assert sources._clean_power(22) == 22.0
    assert sources._clean_power("50") == 50.0


# ---- PLN --------------------------------------------------------------------

@pytest.mark.unit
def test_pln_missing_file_returns_empty(write_raw):
    assert sources._load_pln() == []       # nothing written -> file absent


@pytest.mark.unit
def test_pln_normalises_string_coordinates_and_free_text_power(write_raw):
    write_raw("pln", [_pln_record()])
    (row,) = sources._load_pln()
    assert row["id"] == "pln_spklu-1"
    assert row["source"] == "pln_spklu"
    assert (row["latitude"], row["longitude"]) == (-6.18039, 106.833191)
    assert isinstance(row["latitude"], float)
    assert row["power_kw"] == 22.0                     # "22 kW" -> 22.0
    assert row["province"] == "DKI Jakarta"            # trailing space stripped
    assert row["city"] == "Kota ADM Jakarta Pusat"
    assert row["operator"] == "PLN"
    assert row["charge_type"] == "medium"
    assert row["status"] == "operational"              # status == 1
    assert row["connectors"] is None                   # total_konektor 0 -> unknown
    assert row["date_verified"] is None


@pytest.mark.unit
@pytest.mark.parametrize("lat,lon,why", [
    (None, "106.8", "latitude missing"),
    ("-6.2", None, "longitude missing"),
    ("", "106.8", "latitude empty string"),
    ("n/a", "106.8", "latitude not a number"),
    ("0", "0", "Null Island sentinel"),
    (0.0, 0.0, "Null Island sentinel, numeric"),
    ("NaN", "106.8", "non-finite latitude"),
    ("-6.2", "Infinity", "non-finite longitude"),
])
def test_pln_drops_records_without_usable_coordinates(write_raw, lat, lon, why):
    write_raw("pln", [_pln_record(latitude=lat, longitude=lon)])
    assert sources._load_pln() == [], why


@pytest.mark.unit
def test_pln_keeps_the_good_record_when_a_neighbour_is_unusable(write_raw):
    write_raw("pln", [
        _pln_record(id=1, latitude="rusak"),
        _pln_record(id=2),
    ])
    assert [r["id"] for r in sources._load_pln()] == ["pln_spklu-2"]


@pytest.mark.unit
@pytest.mark.parametrize("status,expected", [
    (1, "operational"),
    (0, "0"),
    (2, "2"),
    (None, None),
])
def test_pln_status_flag_becomes_a_label(write_raw, status, expected):
    write_raw("pln", [_pln_record(status=status)])
    assert sources._load_pln()[0]["status"] == expected


@pytest.mark.unit
def test_pln_blank_province_becomes_none_and_unparseable_power_becomes_nan(write_raw):
    write_raw("pln", [_pln_record(provinsi="   ", watt="tidak diketahui", total_konektor=3)])
    (row,) = sources._load_pln()
    assert row["province"] is None
    assert math.isnan(row["power_kw"])
    assert row["connectors"] == 3


@pytest.mark.unit
def test_pln_station_flows_through_normalisation_to_one_ac_connector(write_raw):
    write_raw("pln", [_pln_record(watt="22 kW", total_konektor=2)])
    (row,) = sources.normalized_rows()
    assert row["connectors"] == [{
        "type": "AC Type 2", "count": 2, "speed_tier": "medium",
        "power_kw": 22.0, "type_inferred": True,
    }]
    assert row["connector_types"] == ["AC Type 2"]
    assert row["power_kw"] == 22.0
    assert row["speed_tier"] == "medium"
    assert row["connector_inferred"] is True


@pytest.mark.unit
def test_pln_station_with_no_power_and_no_charge_type_yields_no_connectors(write_raw):
    write_raw("pln", [_pln_record(watt="", type_charge=None)])
    (row,) = sources.normalized_rows()
    assert row["connectors"] == []
    assert row["connector_types"] == []
    assert row["power_kw"] is None
    assert row["speed_tier"] is None


@pytest.mark.unit
def test_pln_expands_chargerboxes_into_per_connector_rows(write_raw):
    """Real record id=6 (SPKLU PLN ULP Medan Kota).

    `total_konektor` is 0 for all 3029 records in the production dump, so the
    per-chargerbox array is the only real inventory. Four boxes -- 22 kW and
    7 kW AC plus 25 kW and 30 kW DC -- must not collapse into the single CCS2
    connector at the station-level `watt` that used to be published, or the AC
    Type 2 plugs stay invisible to connector filtering and compatibility checks.
    """
    write_raw("pln", [_pln_record(id=6, watt="30 kW", total_konektor=0, chargerboxes=[
        {"type_charge": "medium", "watt": "22 kW", "jumlah_charger": 4, "jumlah_konektor": "1"},
        {"type_charge": "standard", "watt": "7 kW", "jumlah_charger": 4, "jumlah_konektor": "1"},
        {"type_charge": "medium", "watt": "25 kW", "jumlah_charger": 4, "jumlah_konektor": "2"},
        {"type_charge": "medium", "watt": "30 kW", "jumlah_charger": 4, "jumlah_konektor": "2"},
    ])])
    (row,) = sources.normalized_rows()
    # Both standards are physically present at this site.
    assert set(row["connector_types"]) == {"AC Type 2", "CCS2"}
    # One entry per distinct (type, power), in chargerbox order, counts intact.
    assert [(c["type"], c["power_kw"], c["count"]) for c in row["connectors"]] == [
        ("AC Type 2", 22.0, 1),
        ("AC Type 2", 7.0, 1),
        ("CCS2", 25.0, 2),
        ("CCS2", 30.0, 2),
    ]
    assert sum(c["count"] for c in row["connectors"]) == 6
    # The station still reports its strongest plug.
    assert row["power_kw"] == 30.0
    assert row["speed_tier"] == "medium"


@pytest.mark.unit
def test_pln_boxes_at_different_powers_produce_distinct_connector_types(write_raw):
    """A 22 kW AC box next to a 120 kW DC box is two standards, not one."""
    write_raw("pln", [_pln_record(watt="120 kW", type_charge="fast", chargerboxes=[
        {"type_charge": "medium", "watt": "22 kW", "jumlah_konektor": "2"},
        {"type_charge": "ultrafast", "watt": "120 kW", "jumlah_konektor": "3"},
    ])])
    (row,) = sources.normalized_rows()
    assert [(c["type"], c["power_kw"], c["count"], c["speed_tier"]) for c in row["connectors"]] == [
        ("AC Type 2", 22.0, 2, "medium"),
        ("CCS2", 120.0, 3, "fast"),
    ]
    assert row["connector_types"] == ["AC Type 2", "CCS2"]
    assert row["power_kw"] == 120.0
    assert row["speed_tier"] == "fast"


@pytest.mark.unit
def test_pln_boxes_sharing_a_power_are_merged_and_their_counts_summed(write_raw):
    write_raw("pln", [_pln_record(watt="22 kW", chargerboxes=[
        {"type_charge": "medium", "watt": "22 kW", "jumlah_konektor": "1"},
        {"type_charge": "medium", "watt": "22 kW", "jumlah_konektor": "2"},
        {"type_charge": "standard", "watt": "7 kW", "jumlah_konektor": 3},
    ])])
    (row,) = sources.normalized_rows()
    assert [(c["type"], c["power_kw"], c["count"]) for c in row["connectors"]] == [
        ("AC Type 2", 22.0, 3),          # 1 + 2, one entry not two
        ("AC Type 2", 7.0, 3),           # same type, different power -> its own entry
    ]
    assert row["connector_types"] == ["AC Type 2"]


@pytest.mark.unit
def test_pln_box_charge_type_overrides_the_station_label(write_raw):
    """A DC box at a station labelled `medium` is still DC.

    `build_connectors` only takes one station-level charge_type, so this is the
    case that proves per-box `type_charge` reaches the inference.
    """
    write_raw("pln", [_pln_record(watt="22 kW", type_charge="medium", chargerboxes=[
        {"type_charge": "medium", "watt": "tidak diketahui", "jumlah_konektor": "1"},
        {"type_charge": "ultrafast", "watt": "belum diisi", "jumlah_konektor": "1"},
    ])])
    (row,) = sources.normalized_rows()
    # Neither box has a readable power, so both fall back to the station's 22 kW;
    # the ultrafast box is DC anyway because of its own type_charge.
    assert [(c["type"], c["power_kw"]) for c in row["connectors"]] == [
        ("AC Type 2", 22.0), ("CCS2", 22.0)]


@pytest.mark.unit
@pytest.mark.parametrize("jumlah_konektor,why", [
    ("0", "zero connectors is a data gap, not an empty bay"),
    (0, "same, as a number"),
    (None, "null"),
    ("", "blank string"),
    ("banyak", "free text"),
    ("__absent__", "key missing entirely"),
])
def test_pln_box_without_a_usable_connector_count_still_counts_as_one(
        write_raw, jumlah_konektor, why):
    box = {"type_charge": "fast", "watt": "50 kW"}
    if jumlah_konektor != "__absent__":
        box["jumlah_konektor"] = jumlah_konektor
    write_raw("pln", [_pln_record(watt="50 kW", chargerboxes=[box])])
    (row,) = sources.normalized_rows()
    assert row["connectors"] == [{
        "type": "CCS2", "count": 1, "speed_tier": "medium",
        "power_kw": 50.0, "type_inferred": True,
    }], why


@pytest.mark.unit
def test_pln_box_with_unreadable_power_falls_back_to_the_station_power(write_raw):
    write_raw("pln", [_pln_record(watt="60 kW", chargerboxes=[
        {"type_charge": "fast", "watt": None, "jumlah_konektor": "2"},
    ])])
    (row,) = sources.normalized_rows()
    assert row["connectors"] == [{
        "type": "CCS2", "count": 2, "speed_tier": "fast",
        "power_kw": 60.0, "type_inferred": True,
    }]


@pytest.mark.unit
@pytest.mark.parametrize("chargerboxes,why", [
    ("__absent__", "no chargerboxes key at all"),
    (None, "null chargerboxes"),
    ([], "empty chargerboxes"),
    ({"watt": "22 kW"}, "chargerboxes is not a list"),
    ([None, "rubbish"], "chargerboxes holds no usable objects"),
])
def test_pln_without_usable_chargerboxes_keeps_the_station_level_behaviour(
        write_raw, chargerboxes, why):
    overrides = {"watt": "22 kW", "total_konektor": 2}
    if chargerboxes != "__absent__":
        overrides["chargerboxes"] = chargerboxes
    write_raw("pln", [_pln_record(**overrides)])
    (row,) = sources.normalized_rows()
    assert row["connectors"] == [{
        "type": "AC Type 2", "count": 2, "speed_tier": "medium",
        "power_kw": 22.0, "type_inferred": True,
    }], why
    assert row["power_kw"] == 22.0


# ---- Open Charge Map --------------------------------------------------------

def _ocm_record(**overrides) -> dict:
    rec = {
        "ID": 101,
        "AddressInfo": {
            "Title": "Plaza Indonesia", "Latitude": -6.1935, "Longitude": 106.8221,
            "AddressLine1": "Jl. M.H. Thamrin", "Town": "Jakarta Pusat",
            "StateOrProvince": "DKI Jakarta",
        },
        "OperatorInfo": {"Title": "PLN"},
        "StatusType": {"IsOperational": True},
        "Connections": [
            {"PowerKW": 50.0, "Quantity": 2},
            {"PowerKW": 7.4, "Quantity": None},
        ],
        "NumberOfPoints": 3,
        "DateLastVerified": "2024-05-01T00:00:00Z",
    }
    rec.update(overrides)
    return rec


@pytest.mark.unit
def test_ocm_missing_file_returns_empty(write_raw):
    assert sources._load_ocm() == []


@pytest.mark.unit
def test_ocm_normalises_address_operator_and_per_connection_power(write_raw):
    write_raw("ocm", [_ocm_record()])
    (row,) = sources._load_ocm()
    assert row["id"] == "open_charge_map-101"
    assert row["source"] == "open_charge_map"
    assert row["name"] == "Plaza Indonesia"
    assert row["address"] == "Jl. M.H. Thamrin"
    assert row["city"] == "Jakarta Pusat"
    assert row["province"] == "DKI Jakarta"
    assert row["operator"] == "PLN"
    assert row["power_kw"] == 50.0                  # max over the connections
    assert row["connectors"] == 3
    assert row["status"] == "operational"
    assert row["date_verified"] == "2024-05-01T00:00:00Z"
    # a Quantity of null means "one plug", not "zero plugs"
    assert row["_connections"] == [{"power_kw": 50.0, "count": 2},
                                   {"power_kw": 7.4, "count": 1}]


@pytest.mark.unit
@pytest.mark.parametrize("status,expected", [
    ({"IsOperational": True}, "operational"),
    ({"IsOperational": False}, "non-operational"),
    ({"IsOperational": None}, None),
    ({}, None),
    (None, None),
])
def test_ocm_operational_flag_becomes_a_label(write_raw, status, expected):
    write_raw("ocm", [_ocm_record(StatusType=status)])
    assert sources._load_ocm()[0]["status"] == expected


@pytest.mark.unit
def test_ocm_without_connections_or_address_falls_back_safely(write_raw):
    write_raw("ocm", [{"AddressInfo": {"Latitude": -6.2, "Longitude": 106.8},
                       "Connections": [], "NumberOfPoints": 0}])
    (row,) = sources._load_ocm()
    assert row["id"] == "open_charge_map-0"          # no ID -> list index
    assert row["name"] is None and row["operator"] is None
    assert math.isnan(row["power_kw"])
    assert row["connectors"] is None                 # 0 points -> unknown
    assert row["_connections"] == []


@pytest.mark.unit
@pytest.mark.parametrize("address_info", [
    {},                                              # no AddressInfo at all
    {"Latitude": -6.2},                              # longitude missing
    {"Longitude": 106.8},                            # latitude missing
    {"Latitude": None, "Longitude": None},
])
def test_ocm_drops_records_without_coordinates(write_raw, address_info):
    write_raw("ocm", [_ocm_record(AddressInfo=address_info)])
    assert sources._load_ocm() == []


@pytest.mark.unit
def test_ocm_zero_power_connections_are_ignored_for_station_power(write_raw):
    write_raw("ocm", [_ocm_record(Connections=[{"PowerKW": 0, "Quantity": 1},
                                               {"PowerKW": None, "Quantity": 1}])])
    (row,) = sources._load_ocm()
    assert math.isnan(row["power_kw"])


@pytest.mark.unit
def test_ocm_row_builds_one_connector_entry_per_distinct_power(write_raw):
    write_raw("ocm", [_ocm_record()])
    (row,) = sources.normalized_rows()
    assert {(c["type"], c["power_kw"], c["count"]) for c in row["connectors"]} == {
        ("CCS2", 50.0, 2), ("AC Type 2", 7.4, 1)}
    assert row["connector_types"] == ["AC Type 2", "CCS2"]
    assert row["power_kw"] == 50.0
    assert row["speed_tier"] == "medium"      # 50 kW sits on the medium/fast boundary


# ---- OpenStreetMap ----------------------------------------------------------

@pytest.mark.unit
def test_osm_missing_file_returns_empty(write_raw):
    assert sources._load_osm() == []


@pytest.mark.unit
def test_osm_node_is_normalised_with_tags_and_free_text_power(write_raw):
    write_raw("osm", {"elements": [{
        "type": "node", "id": 4242, "lat": -6.2, "lon": 106.81,
        "tags": {"name": "SPKLU Senayan", "operator": "PLN",
                 "addr:full": "Jl. Asia Afrika", "addr:city": "Jakarta Selatan",
                 "charging_station:output": "22 kW", "capacity": "4", "access": "yes"},
    }]})
    (row,) = sources._load_osm()
    assert row["id"] == "osm-node-4242"
    assert row["source"] == "osm"
    assert row["name"] == "SPKLU Senayan"
    assert row["operator"] == "PLN"
    assert row["address"] == "Jl. Asia Afrika"
    assert row["city"] == "Jakarta Selatan"
    assert row["province"] is None
    assert row["power_kw"] == 22.0
    assert row["connectors"] == 4
    assert row["status"] == "yes"


@pytest.mark.unit
def test_osm_way_uses_its_center_and_a_way_without_center_is_dropped(write_raw):
    write_raw("osm", {"elements": [
        {"type": "way", "id": 7, "center": {"lat": -6.3, "lon": 106.9}, "tags": {"name": "Mall"}},
        {"type": "way", "id": 8, "tags": {"name": "No centre"}},
    ]})
    rows = sources._load_osm()
    assert [r["id"] for r in rows] == ["osm-way-7"]
    assert (rows[0]["latitude"], rows[0]["longitude"]) == (-6.3, 106.9)


@pytest.mark.unit
@pytest.mark.parametrize("tags,expected_name,expected_operator", [
    ({"name": "N", "name:en": "EN", "brand": "B"}, "N", "B"),
    ({"name:en": "EN", "brand": "B"}, "EN", "B"),
    ({"brand": "B", "operator": "O"}, "B", "O"),
    ({"operator": "O", "network": "NW"}, "O", "O"),
    ({"network": "NW", "ref": "R"}, "NW", "NW"),
    ({"ref": "R"}, "R", None),
    ({}, None, None),
])
def test_osm_name_falls_back_through_the_identity_tags(write_raw, tags, expected_name,
                                                       expected_operator):
    write_raw("osm", {"elements": [
        {"type": "node", "id": 1, "lat": -6.2, "lon": 106.8, "tags": tags}]})
    (row,) = sources._load_osm()
    assert row["name"] == expected_name
    assert row["operator"] == expected_operator


@pytest.mark.unit
@pytest.mark.parametrize("tags_key", ["absent", "null"])
def test_osm_element_without_tags_still_yields_a_located_row(write_raw, tags_key):
    element = {"type": "node", "id": 55, "lat": -6.2, "lon": 106.8}
    if tags_key == "null":
        element["tags"] = None
    write_raw("osm", {"elements": [element]})
    (row,) = sources._load_osm()
    assert row["id"] == "osm-node-55"
    assert row["name"] is None
    assert row["operator"] is None
    assert row["address"] is None
    assert row["city"] is None
    assert row["connectors"] is None
    assert row["status"] is None
    assert math.isnan(row["power_kw"])
    # ...and normalisation turns the unknown power into no connectors at all.
    (norm,) = sources.normalized_rows()
    assert norm["connectors"] == []
    assert norm["power_kw"] is None


@pytest.mark.unit
def test_osm_power_falls_back_to_the_socket_tag_and_bad_capacity_is_dropped(write_raw):
    write_raw("osm", {"elements": [{
        "type": "node", "id": 9, "lat": -6.2, "lon": 106.8,
        "tags": {"socket:type2_combo:output": "150 kW", "capacity": "banyak"},
    }]})
    (row,) = sources._load_osm()
    assert row["power_kw"] == 150.0
    assert row["connectors"] is None


@pytest.mark.unit
def test_osm_empty_payload_and_missing_elements_key(write_raw):
    write_raw("osm", {})
    assert sources._load_osm() == []
    write_raw("osm", {"elements": []})
    assert sources._load_osm() == []


# ---- cross-source normalisation --------------------------------------------

@pytest.mark.unit
def test_normalized_rows_merges_all_three_sources(write_raw):
    write_raw("pln", [_pln_record(id=1, watt="120 kW", type_charge="fast")])
    write_raw("ocm", [_ocm_record(ID=2)])
    write_raw("osm", {"elements": [{
        "type": "node", "id": 3, "lat": -6.25, "lon": 106.85,
        "tags": {"brand": "PLN", "charging_station:output": "7 kW"}}]})
    rows = sources.normalized_rows()
    assert [r["id"] for r in rows] == ["pln_spklu-1", "open_charge_map-2", "osm-node-3"]
    assert [r["source"] for r in rows] == ["pln_spklu", "open_charge_map", "osm"]
    # every row leaves normalisation with the derived station fields populated
    for r in rows:
        assert set(r) >= {"connectors", "connector_types", "speed_tier", "power_kw",
                          "connector_inferred"}
        assert isinstance(r["connectors"], list)
    by_id = {r["id"]: r for r in rows}
    assert by_id["pln_spklu-1"]["speed_tier"] == "fast"
    assert by_id["osm-node-3"]["speed_tier"] == "slow"
    assert by_id["osm-node-3"]["connector_types"] == ["AC Type 2"]


@pytest.mark.unit
def test_normalized_rows_skips_rows_whose_coordinates_are_none(monkeypatch):
    monkeypatch.setattr(sources, "_load_pln", lambda: [
        {"id": "x", "latitude": None, "longitude": 106.8, "power_kw": 22.0},
        {"id": "y", "latitude": -6.2, "longitude": None, "power_kw": 22.0},
        {"id": "z", "latitude": -6.2, "longitude": 106.8, "power_kw": 22.0},
    ])
    monkeypatch.setattr(sources, "_load_ocm", lambda: [])
    monkeypatch.setattr(sources, "_load_osm", lambda: [])
    assert [r["id"] for r in sources.normalized_rows()] == ["z"]


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["ocm", "osm"])
@pytest.mark.xfail(strict=True, reason=(
    "BUG: only _load_pln guards coordinates. _load_ocm/_load_osm accept (0,0) -- the "
    "Null Island sentinel a feed emits for 'location unknown' -- and publish it as a real "
    "station in the Gulf of Guinea, where it becomes a route-planning candidate."))
def test_null_island_coordinates_are_rejected_by_every_source(write_raw, kind):
    if kind == "ocm":
        write_raw("ocm", [_ocm_record(AddressInfo={"Latitude": 0, "Longitude": 0,
                                                   "Title": "unknown"})])
        assert sources._load_ocm() == []
    else:
        write_raw("osm", {"elements": [
            {"type": "node", "id": 1, "lat": 0, "lon": 0, "tags": {"name": "unknown"}}]})
        assert sources._load_osm() == []


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["ocm", "osm"])
@pytest.mark.xfail(strict=True, reason=(
    "BUG: _load_ocm/_load_osm call float(lat) outside any try/except, so ONE malformed "
    "coordinate in an upstream feed raises ValueError and aborts the whole ingest -- no "
    "stations at all instead of n-1. _load_pln catches exactly this and skips the record."))
def test_one_malformed_coordinate_does_not_abort_the_whole_source(write_raw, kind):
    if kind == "ocm":
        write_raw("ocm", [
            _ocm_record(ID=1, AddressInfo={"Latitude": "rusak", "Longitude": 106.8}),
            _ocm_record(ID=2),
        ])
        assert [r["id"] for r in sources._load_ocm()] == ["open_charge_map-2"]
    else:
        write_raw("osm", {"elements": [
            {"type": "node", "id": 1, "lat": "rusak", "lon": 106.8, "tags": {}},
            {"type": "node", "id": 2, "lat": -6.2, "lon": 106.8, "tags": {}},
        ]})
        assert [r["id"] for r in sources._load_osm()] == ["osm-node-2"]


# =============================================================================
# api/evmodels.py
# =============================================================================


@pytest.fixture
def catalogue(monkeypatch, tmp_path):
    """Isolate the module-level catalogue cache and every on-disk fallback.

    ``monkeypatch.setattr`` restores the previous cache on teardown, so the rest
    of the suite keeps whatever catalogue it had loaded.
    """
    monkeypatch.setattr(evmodels, "_MODELS_CACHE", None)
    monkeypatch.setattr(evmodels, "JSON_PATH", tmp_path / "nope.json")
    monkeypatch.setattr(evmodels, "CSV_PATH", tmp_path / "nope.csv")
    monkeypatch.setattr(evmodels, "ZIP_PATH", tmp_path / "nope.zip")
    monkeypatch.setattr(evmodels, "_load_from_db", lambda: [])
    return tmp_path


class _ExplodingEngine:
    def connect(self):
        raise RuntimeError("connection refused")


# ---- numeric coercion (the Decimal barrier) ---------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    (None, None),
    (True, None),                 # bools are not numbers here
    (False, None),
    ("not a number", None),
    ("", None),
    (Decimal("136.00"), 136.0),
    ("12.5", 12.5),
    (7, 7.0),
    (7.5, 7.5),
])
def test_to_float_coerces_or_gives_up(raw, expected):
    assert evmodels._to_float(raw) == expected


@pytest.mark.unit
def test_coerce_numerics_lets_no_decimal_escape():
    model = evmodels.coerce_numerics({
        "id": "x", "name": "X",
        "battery_kwh": Decimal("81.20"), "range_km": Decimal("516"),
        "max_dc_charge_kw": Decimal("136.00"), "match_confidence": Decimal("0.85"),
        "charging_time_minutes": Decimal("30"), "seats": 5, "power_hp": "340",
        "fast_charge_port": "CCS2",
    })
    numeric = {k: v for k, v in model.items() if k in evmodels._NUMERIC_FIELDS}
    assert not any(isinstance(v, Decimal) for v in numeric.values()), numeric
    assert all(isinstance(v, float) for v in numeric.values()), numeric
    # the arithmetic that used to blow up with "unsupported operand" now works
    assert min(model["max_dc_charge_kw"], 60.0) == 60.0
    assert model["battery_kwh"] / 2 == 40.6
    # non-numeric fields are untouched, and the input is not mutated
    assert model["fast_charge_port"] == "CCS2"
    assert model["power_hp"] == 340.0


@pytest.mark.unit
def test_coerce_numerics_does_not_mutate_its_argument():
    original = {"id": "x", "name": "X", "range_km": Decimal("400")}
    evmodels.coerce_numerics(original)
    assert original["range_km"] == Decimal("400")


@pytest.mark.unit
@pytest.mark.parametrize("max_dc,fast_dc,expected", [
    (None, Decimal("94.00"), 94.0),      # column never populated -> use the DC column
    (0, 94.0, 94.0),                     # zero is not a real charge rate either
    (Decimal("150"), 94.0, 150.0),       # a real value wins
    (None, None, None),                  # nothing known
])
def test_coerce_numerics_backfills_max_dc_charge_kw(max_dc, fast_dc, expected):
    model = evmodels.coerce_numerics({"id": "x", "name": "X",
                                      "max_dc_charge_kw": max_dc,
                                      "fast_charging_power_kw_dc": fast_dc})
    assert model["max_dc_charge_kw"] == expected


@pytest.mark.unit
def test_coerce_numerics_leaves_absent_fields_absent():
    model = evmodels.coerce_numerics({"id": "x", "name": "X"})
    assert "battery_kwh" not in model
    assert "max_dc_charge_kw" not in model      # nothing invented out of thin air


# ---- load() and its fallback chain ------------------------------------------

@pytest.mark.unit
def test_load_from_db_returns_empty_when_the_database_is_unreachable(monkeypatch):
    import api.db
    monkeypatch.setattr(api.db, "engine", _ExplodingEngine())
    assert evmodels._load_from_db() == []


@pytest.mark.unit
def test_load_falls_back_to_json_when_the_database_yields_nothing(catalogue):
    json_path = catalogue / "models.json"
    json_path.write_text(json.dumps([
        {"id": "wuling-air-ev", "name": "Wuling Air EV", "range_km": "200",
         "battery_kwh": "26.7", "fast_charging_power_kw_dc": "40"},
    ]), encoding="utf-8")
    evmodels.JSON_PATH = json_path

    models = evmodels.load()
    assert [m["id"] for m in models] == ["wuling-air-ev"]
    assert models[0]["range_km"] == 200.0            # coerced, not left as "200"
    assert models[0]["max_dc_charge_kw"] == 40.0     # backfilled from the DC column
    assert evmodels.load() is models                 # second call is cached


@pytest.mark.unit
def test_load_from_json_survives_a_corrupt_file(catalogue):
    json_path = catalogue / "models.json"
    json_path.write_text("{not json", encoding="utf-8")
    evmodels.JSON_PATH = json_path
    assert evmodels._load_from_json() == []
    assert evmodels.load() == []                     # no CSV/zip either


@pytest.mark.unit
def test_load_falls_back_to_the_raw_csv_and_dedupes_by_id(catalogue):
    csv_path = catalogue / "specs.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Vehicle Name", "Battery Capacity",
                                          "Range (Jarak Tempuh)", "Vehicle Price Range"])
        w.writeheader()
        w.writerow({"Vehicle Name": "Wuling Air EV", "Battery Capacity": "26.7 kWh",
                    "Range (Jarak Tempuh)": "200 - 300 km",
                    "Vehicle Price Range": "Rp 214 - 307,5 Juta"})
        w.writerow({"Vehicle Name": "Wuling Air EV", "Battery Capacity": "99 kWh",
                    "Range (Jarak Tempuh)": "900 km", "Vehicle Price Range": ""})
        w.writerow({"Vehicle Name": "", "Battery Capacity": "10 kWh",
                    "Range (Jarak Tempuh)": "10 km", "Vehicle Price Range": ""})
    evmodels.CSV_PATH = csv_path

    models = evmodels.load()
    assert [m["id"] for m in models] == ["wuling-air-ev"]     # nameless row dropped,
    assert models[0]["battery_kwh"] == 26.7                   # first row wins
    assert models[0]["range_km"] == 200.0                     # conservative lower bound
    assert models[0]["price_range"] == "Rp 214 - 307,5 Juta"


@pytest.mark.unit
def test_read_raw_rows_reads_the_zip_when_no_csv_is_present(catalogue):
    zip_path = catalogue / "ev.zip"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["name", "battery_kwh", "range_km"])
    w.writeheader()
    w.writerow({"name": "BYD Dolphin", "battery_kwh": "44.9", "range_km": "410"})
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("some/other/name.csv", buf.getvalue())     # not ZIP_MEMBER
    evmodels.ZIP_PATH = zip_path

    rows = evmodels._read_raw_rows()
    assert [r["name"] for r in rows] == ["BYD Dolphin"]


@pytest.mark.unit
def test_read_raw_rows_returns_empty_for_a_zip_without_a_csv(catalogue):
    zip_path = catalogue / "ev.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("readme.txt", "no data here")
    evmodels.ZIP_PATH = zip_path
    assert evmodels._read_raw_rows() == []


@pytest.mark.unit
def test_read_raw_rows_returns_empty_when_nothing_exists(catalogue):
    assert evmodels._read_raw_rows() == []


@pytest.mark.unit
def test_parse_fallback_splits_the_name_and_derives_efficiency():
    m = evmodels._parse_fallback({"Vehicle Name": "Hyundai Ioniq 5",
                                  "Battery Capacity": "72.6 kWh",
                                  "Range (Jarak Tempuh)": "481 km"})
    assert m["id"] == "hyundai-ioniq-5"
    assert (m["brand"], m["make"], m["model"]) == ("Hyundai", "Hyundai", "Ioniq 5")
    assert m["battery_kwh"] == 72.6 and m["range_km"] == 481.0
    assert m["efficiency_wh_per_km"] == round(72.6 * 1000 / 481, 2)
    assert m["efficiency_source"] == "derived_local_specs"


@pytest.mark.unit
def test_parse_fallback_keeps_a_supplied_efficiency_and_single_word_names():
    m = evmodels._parse_fallback({"name": "Zeekr", "efficiency_wh_per_km": "155",
                                 "battery_kwh": "100", "range_km": "600"})
    assert m["model"] == "Zeekr"                     # single word: model == name
    assert m["efficiency_wh_per_km"] == 155.0
    assert m["efficiency_source"] == "dataset"


@pytest.mark.unit
def test_parse_fallback_cannot_derive_efficiency_without_a_range():
    m = evmodels._parse_fallback({"name": "Mystery EV", "battery_kwh": "50"})
    assert m["range_km"] is None
    assert m["efficiency_wh_per_km"] is None
    assert m["efficiency_source"] == "dataset"


@pytest.mark.unit
@pytest.mark.parametrize("row", [{}, {"name": "   "}, {"Vehicle Name": ""}])
def test_parse_fallback_rejects_a_nameless_row(row):
    assert evmodels._parse_fallback(row) is None


@pytest.mark.unit
def test_reload_picks_up_a_changed_catalogue(catalogue):
    json_path = catalogue / "models.json"
    json_path.write_text(json.dumps([{"id": "a", "name": "A"}]), encoding="utf-8")
    evmodels.JSON_PATH = json_path
    assert [m["id"] for m in evmodels.load()] == ["a"]

    json_path.write_text(json.dumps([{"id": "b", "name": "B"}]), encoding="utf-8")
    assert [m["id"] for m in evmodels.load()] == ["a"]        # still cached
    assert [m["id"] for m in evmodels.reload()] == ["b"]      # cache cleared


# ---- get / search / paging --------------------------------------------------

@pytest.fixture
def small_catalogue(catalogue):
    models = [
        {"id": "byd-atto-3", "name": "BYD Atto 3", "range_km": 410.0},
        {"id": "hyundai-ioniq-5", "name": "Hyundai Ioniq 5", "range_km": 481.0},
        {"id": "hyundai-kona", "name": "Hyundai Kona Electric", "range_km": 305.0},
        {"id": "wuling-air-ev", "name": "Wuling Air EV", "range_km": None},
    ]
    json_path = catalogue / "models.json"
    json_path.write_text(json.dumps(models), encoding="utf-8")
    evmodels.JSON_PATH = json_path
    evmodels.load()
    return models


@pytest.mark.unit
def test_get_returns_the_model_and_none_for_an_unknown_id(small_catalogue):
    assert evmodels.get("hyundai-kona")["name"] == "Hyundai Kona Electric"
    assert evmodels.get("no-such-model") is None
    assert evmodels.get("") is None
    assert evmodels.get("HYUNDAI-KONA") is None      # ids are exact, not folded


@pytest.mark.unit
def test_search_without_a_query_returns_the_whole_catalogue(small_catalogue):
    total, items = evmodels.search(None, limit=100, offset=0)
    assert total == 4 and len(items) == 4
    total, items = evmodels.search("", limit=100, offset=0)
    assert total == 4 and len(items) == 4


@pytest.mark.unit
@pytest.mark.parametrize("q,expected", [
    ("hyundai", ["hyundai-ioniq-5", "hyundai-kona"]),
    ("HYUNDAI", ["hyundai-ioniq-5", "hyundai-kona"]),     # case-insensitive
    ("air ev", ["wuling-air-ev"]),                        # substring, not prefix
    ("zzz", []),
])
def test_search_filters_on_the_vehicle_name(small_catalogue, q, expected):
    total, items = evmodels.search(q, limit=100, offset=0)
    assert [m["id"] for m in items] == expected
    assert total == len(expected)


@pytest.mark.unit
def test_search_total_counts_matches_not_the_returned_page(small_catalogue):
    total, page = evmodels.search(None, limit=2, offset=0)
    assert total == 4 and [m["id"] for m in page] == ["byd-atto-3", "hyundai-ioniq-5"]

    total, page2 = evmodels.search(None, limit=2, offset=2)
    assert total == 4 and [m["id"] for m in page2] == ["hyundai-kona", "wuling-air-ev"]

    total, beyond = evmodels.search(None, limit=2, offset=99)
    assert total == 4 and beyond == []


@pytest.mark.unit
def test_search_paging_applies_after_the_query_filter(small_catalogue):
    total, page = evmodels.search("hyundai", limit=1, offset=1)
    assert total == 2
    assert [m["id"] for m in page] == ["hyundai-kona"]


# ---- range maths ------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("range_km,soc,factor,expected", [
    (400.0, 100, 0.85, 340.0),
    (400.0, 50, 0.85, 170.0),
    (400.0, 0, 0.85, 0.0),
    (481.0, 37, 0.85, 151.27),        # rounded to 2dp
    (400.0, 50, 1.0, 200.0),
])
def test_remaining_range_km(range_km, soc, factor, expected):
    assert evmodels.remaining_range_km(range_km, soc, factor) == expected


@pytest.mark.unit
def test_remaining_range_is_unknown_when_the_model_has_no_range(small_catalogue):
    model = evmodels.get("wuling-air-ev")
    assert model["range_km"] is None
    # A model with no published range must not silently become "0 km of range";
    # the caller has to be told the range is unknown.
    assert evmodels.remaining_range_km(model["range_km"], 80.0) is None


@pytest.mark.unit
def test_remaining_range_default_factor_is_the_module_constant():
    # The default is bound at import time from ROUTING_RANGE_SAFETY_FACTOR.
    assert evmodels.remaining_range_km(400.0, 100) == round(
        400.0 * evmodels.RANGE_SAFETY_FACTOR, 2)


# ---- the DB-backed load -----------------------------------------------------

@requires_db
@pytest.mark.integration
def test_catalogue_loads_from_the_database_with_no_decimal_left(monkeypatch):
    monkeypatch.setattr(evmodels, "_MODELS_CACHE", None)
    models = evmodels.reload()
    assert len(models) > 0
    assert all(m["id"] and m["name"] for m in models)

    offenders = [(m["id"], k, v) for m in models for k, v in m.items()
                 if isinstance(v, Decimal)]
    assert offenders == [], f"Decimal escaped the repository boundary: {offenders[:5]}"

    # max_dc_charge_kw is numeric(*) in Postgres; it must arrive usable in the
    # energy math (min()/division against floats), not as a Decimal.
    powered = [m for m in models if m.get("max_dc_charge_kw") is not None]
    assert powered, "no model carries a DC charge power"
    for m in powered:
        assert isinstance(m["max_dc_charge_kw"], float)
        assert min(m["max_dc_charge_kw"], 60.0) <= 60.0

    ranged = [m for m in models if m.get("range_km") is not None]
    assert ranged
    assert evmodels.remaining_range_km(ranged[0]["range_km"], 50.0) > 0


@requires_db
@pytest.mark.integration
def test_db_catalogue_is_served_through_the_endpoints(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api import main

    monkeypatch.setattr(evmodels, "_MODELS_CACHE", None)
    evmodels.reload()
    with TestClient(main.app) as c:
        body = c.get("/api/v1/ev-models?limit=3").json()
        assert body["total"] > 3 and len(body["items"]) == 3
        assert body["limit"] == 3 and body["offset"] == 0

        page2 = c.get("/api/v1/ev-models?limit=3&offset=3").json()
        assert {m["id"] for m in page2["items"]}.isdisjoint({m["id"] for m in body["items"]})
        assert page2["total"] == body["total"]

        first = body["items"][0]["id"]
        one = c.get(f"/api/v1/ev-models/{first}")
        assert one.status_code == 200 and one.json()["id"] == first
        assert c.get("/api/v1/ev-models/definitely-not-a-model").status_code == 404


# =============================================================================
# api/stations_repo.py
# =============================================================================

# Parked in the Coral Sea: far from every seeded Indonesian station, so a bbox
# around it isolates exactly the rows this module inserts. 1 degree of longitude
# at this latitude is ~96 km, which the distance assertions below rely on.
_LAT = -30.0
_PREFIX = "pipecov"
_STATIONS = [
    # id,  lon,     lat,    name,                          province,   city,             kW,    tier,        connector,   sources
    ("a", 150.00, _LAT, "Pipecov Alpha Charging Hub", "Testland", "North Testville", 22.0, "medium", "AC Type 2", ["pln_spklu"]),
    ("b", 150.50, _LAT, "Pipecov Beta Fast Charger", "Testland", "South Testville", 120.0, "fast", "CCS2", ["open_charge_map"]),
    ("c", 151.00, _LAT, "Pipecov Gamma Ultra Point", "Otherland", "North Testville", 250.0, "ultra_fast", "CCS2", ["osm", "pln_spklu"]),
    ("d", 150.25, -30.90, "Pipecov Delta Off Corridor", "Testland", "Far City", 50.0, "medium", "CCS2", ["osm"]),
    ("e", 160.00, _LAT, "Pipecov Epsilon Outside Box", "Edgeland", "Outer City", 43.0, "medium", "AC Type 2", ["pln_spklu"]),
]
_BBOX = (149.5, -31.5, 151.5, -29.5)     # holds a, b, c, d -- not e


def _sid(suffix: str) -> str:
    return f"{_PREFIX}-{suffix}"


@pytest.fixture(scope="module")
def synthetic_stations():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from sqlalchemy import text

    from api.db import engine

    delete = text(f"DELETE FROM stations WHERE id LIKE '{_PREFIX}-%'")
    insert = text("""
        INSERT INTO stations (id, geom, name, address, province, city, operator, power_kw,
                              speed_tier, connector_types, connector_inferred, connectors,
                              sources, status, date_verified)
        VALUES (:id, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name, :address, :province,
                :city, 'Testing Co', :kw, :tier, :ctypes, false, CAST(:conns AS jsonb),
                :sources, 'operational', NULL)
    """)
    with engine.begin() as c:
        c.execute(delete)
        for sid, lon, lat, name, province, city, kw, tier, ctype, srcs in _STATIONS:
            c.execute(insert, {
                "id": _sid(sid), "lon": lon, "lat": lat, "name": name,
                "address": f"{name} Road", "province": province, "city": city,
                "kw": kw, "tier": tier, "ctypes": [ctype],
                "conns": json.dumps([{"type": ctype, "count": 2, "power_kw": kw,
                                      "speed_tier": tier, "type_inferred": False}]),
                "sources": srcs,
            })
    yield
    with engine.begin() as c:
        c.execute(delete)


def _ids(rows) -> set:
    return {r["id"] for r in rows if r["id"].startswith(_PREFIX)}


@requires_db
@pytest.mark.integration
@pytest.mark.parametrize("filters,expected", [
    ({}, {"a", "b", "c", "d"}),
    ({"province": "Testland"}, {"a", "b", "d"}),
    ({"province": "testland"}, {"a", "b", "d"}),              # case-insensitive exact
    ({"province": "Test"}, set()),                            # exact, not prefix
    ({"city": "North Test"}, {"a", "c"}),                     # substring, any case
    ({"city": "north test"}, {"a", "c"}),
    ({"q": "ultra"}, {"c"}),                                  # name search, any case
    ({"q": "Charg"}, {"a", "b"}),
    ({"q": "Pipecov"}, {"a", "b", "c", "d"}),
    ({"min_power": 100}, {"b", "c"}),
    ({"max_power": 100}, {"a", "d"}),
    ({"min_power": 30, "max_power": 200}, {"b", "d"}),
    ({"min_power": 60, "max_power": 200}, {"b"}),
    ({"min_power": 22, "max_power": 22}, {"a"}),               # inclusive bounds
    ({"connector_type": ["AC Type 2"]}, {"a"}),
    ({"connector_type": ["CCS2"]}, {"b", "c", "d"}),
    ({"connector_type": ["CCS2", "AC Type 2"]}, {"a", "b", "c", "d"}),
    ({"speed_tier": ["fast", "ultra_fast"]}, {"b", "c"}),
    ({"connector_type": ["CCS2"], "speed_tier": ["medium"]}, {"d"}),
    ({"source": "osm"}, {"c", "d"}),
    ({"source": "pln_spklu"}, {"a", "c"}),
    ({"province": "Testland", "min_power": 100}, {"b"}),       # c is >100 kW but Otherland
    ({"province": "Otherland", "connector_type": ["AC Type 2"]}, set()),
])
def test_list_stations_filter_combinations(synthetic_stations, filters, expected):
    from api.stations_repo import list_stations
    _, rows = list_stations({**filters, "bbox": _BBOX}, limit=100, offset=0)
    assert _ids(rows) == {_sid(s) for s in expected}


@requires_db
@pytest.mark.integration
def test_bbox_excludes_what_is_outside_it(synthetic_stations):
    from api.stations_repo import list_stations
    _, inside = list_stations({"bbox": _BBOX, "q": "Pipecov"}, limit=100, offset=0)
    assert _ids(inside) == {_sid(s) for s in "abcd"}
    assert _sid("e") not in _ids(inside)

    wide = (149.5, -31.5, 161.0, -29.5)
    _, rows = list_stations({"bbox": wide, "q": "Pipecov"}, limit=100, offset=0)
    assert _ids(rows) == {_sid(s) for s in "abcde"}     # only the box had excluded it


@requires_db
@pytest.mark.integration
def test_list_stations_total_is_the_match_count_and_paging_walks_it(synthetic_stations):
    from api.stations_repo import list_stations
    filters = {"bbox": _BBOX}
    total, first = list_stations(filters, limit=2, offset=0)
    total2, second = list_stations(filters, limit=2, offset=2)

    assert total == total2 == 4                          # not the page size
    assert len(first) == len(second) == 2
    assert _ids(first).isdisjoint(_ids(second))
    assert _ids(first) | _ids(second) == {_sid(s) for s in "abcd"}
    ids = [r["id"] for r in first + second]
    assert ids == sorted(ids)                            # deterministic ORDER BY id

    _, past_end = list_stations(filters, limit=2, offset=99)
    assert past_end == []


@requires_db
@pytest.mark.integration
def test_list_stations_returns_the_decomposed_geometry_and_arrays(synthetic_stations):
    from api.stations_repo import get_station, list_stations
    _, rows = list_stations({"bbox": _BBOX, "q": "Alpha"}, limit=10, offset=0)
    (row,) = rows
    assert (round(row["latitude"], 6), round(row["longitude"], 6)) == (_LAT, 150.0)
    assert row["connector_types"] == ["AC Type 2"]
    assert row["sources"] == ["pln_spklu"]
    assert row["connectors"][0]["power_kw"] == 22.0
    assert row["speed_tier"] == "medium"

    assert get_station(_sid("a")) == row
    assert get_station("pipecov-does-not-exist") is None


@requires_db
@pytest.mark.integration
def test_nearby_orders_by_distance_and_honours_filters(synthetic_stations):
    from api.stations_repo import nearby
    rows = nearby(_LAT, 150.0, radius_km=60.0, limit=50)
    ours = [r for r in rows if r["id"].startswith(_PREFIX)]
    assert [r["id"] for r in ours] == [_sid("a"), _sid("b")]     # c/d are >90 km away
    assert [r["distance_km"] for r in ours] == sorted(r["distance_km"] for r in ours)
    assert ours[0]["distance_km"] < 0.001                       # standing on it
    assert 40.0 < ours[1]["distance_km"] < 55.0                 # ~48 km east

    filtered = nearby(_LAT, 150.0, radius_km=60.0, limit=50,
                      filters={"connector_type": ["CCS2"]})
    assert _ids(filtered) == {_sid("b")}

    tight = nearby(_LAT, 150.0, radius_km=1.0, limit=50)
    assert _ids(tight) == {_sid("a")}


@requires_db
@pytest.mark.integration
def test_corridor_spans_the_route_and_respects_filters(synthetic_stations):
    from api.stations_repo import along_corridor
    origin, destination = (_LAT, 150.0), (_LAT, 151.0)

    rows = along_corridor(origin, destination, corridor_km=20.0, limit=50)
    assert _ids(rows) == {_sid("a"), _sid("b"), _sid("c")}      # d is ~100 km off-line
    for r in rows:
        if r["id"].startswith(_PREFIX):
            assert r["corridor_distance_km"] < 20.0
            assert 0.0 <= r["along_fraction"] <= 1.0

    by_id = {r["id"]: r for r in rows}
    assert by_id[_sid("a")]["along_fraction"] < by_id[_sid("b")]["along_fraction"] \
        < by_id[_sid("c")]["along_fraction"]

    filtered = along_corridor(origin, destination, corridor_km=20.0, limit=50,
                              filters={"speed_tier": ["ultra_fast"]})
    assert _ids(filtered) == {_sid("c")}

    wide = along_corridor(origin, destination, corridor_km=150.0, limit=50)
    assert _sid("d") in _ids(wide)                              # distance, not id, decides


@requires_db
@pytest.mark.integration
def test_corridor_limit_still_reaches_the_far_end_of_the_route(synthetic_stations):
    from api.stations_repo import along_corridor
    # One station per bucket, limit 1: the single row returned must be a real
    # corridor member and must carry its position along the line.
    rows = along_corridor((_LAT, 150.0), (_LAT, 151.0), corridor_km=20.0, limit=1,
                          buckets=3, filters={"q": "Pipecov"})
    assert len(rows) == 1
    assert "along_fraction" in rows[0] and "corridor_distance_km" in rows[0]


@requires_db
@pytest.mark.integration
def test_aggregate_lookups_see_the_synthetic_rows(synthetic_stations):
    from api.stations_repo import (cities, connector_counts, count, provinces,
                                   source_counts, speed_tier_counts, stats)

    total = count()
    assert total >= len(_STATIONS)

    by_source = dict(source_counts())
    assert by_source["pln_spklu"] >= 3 and by_source["osm"] >= 2
    counts = [c for _, c in source_counts()]
    assert counts == sorted(counts, reverse=True)

    by_prov = dict(provinces())
    assert by_prov["Testland"] == 3 and by_prov["Otherland"] == 1 and by_prov["Edgeland"] == 1
    assert None not in by_prov

    all_cities = dict(cities(None))
    assert all_cities["North Testville"] == 2          # a (Testland) + c (Otherland)
    in_testland = dict(cities("Testland"))
    assert in_testland["North Testville"] == 1         # c is filtered out
    assert "Outer City" not in in_testland
    assert dict(cities("testland")) == in_testland     # case-insensitive

    assert dict(connector_counts())["AC Type 2"] >= 2
    assert speed_tier_counts()["ultra_fast"] >= 1

    s = stats()
    assert s["total"] == total
    assert s["with_power_kw"] <= total
    assert s["power_kw_max"] >= 250.0
    assert all(isinstance(s[k], float)
               for k in ("power_kw_min", "power_kw_max", "power_kw_mean"))


@requires_db
@pytest.mark.integration
def test_routing_coords_returns_every_station_and_can_be_narrowed_by_source(
        synthetic_stations):
    from api.stations_repo import count, routing_coords

    coords = routing_coords()
    assert len(coords) == count()
    ours = {c["id"]: c for c in coords if c["id"].startswith(_PREFIX)}
    assert set(ours) == {_sid(s) for s in "abcde"}
    assert round(ours[_sid("a")]["latitude"], 6) == _LAT
    assert round(ours[_sid("a")]["longitude"], 6) == 150.0
    assert set(coords[0]) == {"id", "latitude", "longitude"}

    osm_only = {c["id"] for c in routing_coords("osm") if c["id"].startswith(_PREFIX)}
    assert osm_only == {_sid("c"), _sid("d")}

    assert routing_coords("no_such_source") == []


@requires_db
@pytest.mark.integration
def test_station_filters_reach_the_endpoints(synthetic_stations):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from api import main

    bbox = ",".join(str(x) for x in _BBOX)
    with TestClient(main.app) as c:
        body = c.get(f"/api/v1/stations?bbox={bbox}&province=Testland&limit=50").json()
        assert {s["id"] for s in body["items"]} == {_sid(s) for s in "abd"}
        assert body["total"] == 3

        typed = c.get(f"/api/v1/stations?bbox={bbox}&connector_type=AC%20Type%202").json()
        assert {s["id"] for s in typed["items"]} == {_sid("a")}

        powered = c.get(f"/api/v1/stations?bbox={bbox}&min_power=100&limit=50").json()
        assert {s["id"] for s in powered["items"]} == {_sid(s) for s in "bc"}

        named = c.get(f"/api/v1/stations?bbox={bbox}&q=Gamma").json()["items"]
        assert [s["id"] for s in named] == [_sid("c")]
        assert named[0]["latitude"] == pytest.approx(_LAT)

        assert c.get("/api/v1/stations?bbox=not-a-bbox").status_code == 422
        assert c.get("/api/v1/stations?bbox=1,2,3").status_code == 422

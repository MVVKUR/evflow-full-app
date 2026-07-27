"""The ev_models UNION and the raw-station staging shape (no database needed).

`scripts/ev_union.py` is where the two EV datasets become one catalogue, and
`scripts/ingest_raw.staging_rows` is where a snapshot file becomes staged rows.
Both are pure, so everything here runs without Postgres.
"""
from __future__ import annotations

import pytest

from scripts import ev_union
from scripts.ev_union import (GLOBAL_DATASET, LOCAL_DATASET, build_union,
                              global_record, local_record, merge, slug)
from scripts.ingest_raw import (OCM_SOURCE, OSM_SOURCE, PLN_SOURCE, EmptyUnion,
                                osm_elements, prune_ev_models, staging_rows)

LOCAL_ROW = {
    "Vehicle Name": "Wuling Air EV",
    "Vehicle Price Range": "Rp 214 - 307,5 Juta",
    "Battery Capacity": "26.7 kWh",
    "Range (Jarak Tempuh)": "200 - 300 km",
    "Power/Horsepower": "40 hp",
    "Seating Capacity": "4 Kursi",
    "Charging time": "8.5 Jam",
    "Source URL": "https://www.oto.com/mobil-baru/wuling/ev",
    "Is EV": "TRUE",
}

GLOBAL_ROW = {
    "brand": "Wuling", "model": "Air EV", "top_speed_kmh": "100",
    "battery_capacity_kWh": "30.0", "battery_type": "Lithium-ion",
    "number_of_cells": "192", "torque_nm": "110", "efficiency_wh_per_km": "150",
    "range_km": "300", "acceleration_0_100_s": "12.5",
    "fast_charging_power_kw_dc": "40", "fast_charge_port": "CCS",
    "towing_capacity_kg": "0", "cargo_volume_l": "185", "seats": "4",
    "drivetrain": "RWD", "segment": "B - Compact", "length_mm": "3673",
    "width_mm": "1683", "height_mm": "1518", "car_body_type": "Hatchback",
    "source_url": "https://ev-database.org/car/1904/Wuling-Air-EV",
}


# ---- ids --------------------------------------------------------------------

@pytest.mark.unit
def test_slug_matches_the_ids_already_in_production():
    # users.ev_model_id holds these three; a slug change would orphan real rows.
    assert slug("Wuling Air EV") == "wuling-air-ev"
    assert slug("BYD M6") == "byd-m6"
    assert slug("BYD Seal") == "byd-seal"


@pytest.mark.unit
def test_a_plus_trim_gets_its_own_id_instead_of_colliding():
    """"EQA 250" and "EQA 250+" are different cars: different battery, range, price.

    A slug that drops '+' silently maps them onto one row and one of the two
    disappears from the catalogue.
    """
    assert slug("Mercedes-Benz EQA 250") == "mercedes-benz-eqa-250"
    assert slug("Mercedes-Benz EQA 250+") == "mercedes-benz-eqa-250-plus"
    assert slug("Smart #1 Pro") != slug("Smart #1 Pro+")


# ---- local records ----------------------------------------------------------

@pytest.mark.unit
def test_local_record_keeps_the_conservative_bounds_and_the_local_parsing():
    r = local_record(LOCAL_ROW)
    assert r["id"] == "wuling-air-ev"
    assert (r["brand"], r["make"], r["model"]) == ("Wuling", "Wuling", "Air EV")
    assert (r["battery_kwh"], r["battery_kwh_min"], r["battery_kwh_max"]) == (26.7, 26.7, 26.7)
    assert (r["range_km"], r["range_km_min"], r["range_km_max"]) == (200.0, 200.0, 300.0)
    assert r["charging_time_minutes"] == 510.0          # "8.5 Jam" -> minutes
    assert r["seats"] == 4                              # "4 Kursi"
    assert r["price_range"] == "Rp 214 - 307,5 Juta"
    assert r["source_datasets"] == [LOCAL_DATASET]
    assert r["source_payload"][LOCAL_DATASET] == LOCAL_ROW


@pytest.mark.unit
def test_local_record_serves_the_enrichment_production_already_publishes():
    """The union may add rows; it may not restate an existing model's specs.

    `fast_charge_port` is what `api/services/connector_compat` reads to decide
    which plugs a car can use, and `max_dc_charge_kw` is what caps charging
    power in the energy estimator. Deriving these from battery/range instead of
    taking `wrangle_ev_dataset`'s values demotes every Indonesian model to AC
    Type 2 and makes a 20 kW car look like a 50 kW one.
    """
    r = local_record(LOCAL_ROW)
    assert r["efficiency_wh_per_km"] == 115.0           # NOT 26.7*1000/200 = 133.5
    assert r["fast_charge_port"] == "GB/T"
    assert r["fast_charging_power_kw_dc"] == 20.0
    assert r["max_dc_charge_kw"] == 20.0                # what the planner reads
    assert r["top_speed_kmh"] == 100.0
    assert (r["car_body_type"], r["drivetrain"]) == ("Hatchback", "RWD")
    # Production stores no efficiency_source for local models; inventing one
    # would change what every route plan reports for every Indonesian car.
    assert r["efficiency_source"] is ev_union.EFFICIENCY_ENRICHED_SOURCE is None
    assert r["match_method"] == ev_union.MATCH_LOCAL_CURATED


@pytest.mark.unit
def test_local_record_derives_efficiency_only_when_nothing_enriches_it():
    r = local_record({**LOCAL_ROW, "Vehicle Name": "Wuling Air EV Unknown Trim"})
    assert r["efficiency_wh_per_km"] == round(26.7 * 1000 / 200.0, 2)
    assert r["efficiency_source"] == ev_union.EFFICIENCY_DERIVED
    assert r["match_method"] == ev_union.MATCH_LOCAL_ONLY
    assert r["fast_charge_port"] is None


@pytest.mark.unit
def test_local_record_normalises_brand_casing_the_way_production_does():
    """11 of the 60 local models differ if brand is the raw first token.

    `users.ev_model_id` is unaffected (the id is slugged from the whole name),
    but `brand` is what the catalogue groups and filters by, so 'GAC' vs 'Gac'
    splits one manufacturer into two.
    """
    for name, brand in [("CHERY E5", "Chery"), ("GWM Ora 03 BEV", "Gwm"),
                        ("DFSK Seres E1", "Dfsk"), ("GAC Aion Y Plus", "Gac"),
                        ("Mercedes Benz EQS", "Mercedes-Benz"),
                        ("Rolls Royce Spectre", "Rolls-Royce"),
                        ("BYD M6", "BYD"), ("VinFast VF 5", "VinFast")]:
        r = local_record({**LOCAL_ROW, "Vehicle Name": name})
        assert (r["brand"], r["make"]) == (brand, brand), name


@pytest.mark.unit
def test_local_record_enriches_from_a_matching_global_spec_row():
    r = local_record({**LOCAL_ROW, "Vehicle Name": "Wuling Air EV"}, [GLOBAL_ROW])
    # the global spec row wins over the curated table, field by field
    assert r["fast_charge_port"] == "CCS"
    assert r["fast_charging_power_kw_dc"] == r["max_dc_charge_kw"] == 40.0
    assert r["efficiency_wh_per_km"] == 150.0
    assert r["match_method"] == ev_union.MATCH_LOCAL_GLOBAL_SPEC


@pytest.mark.unit
@pytest.mark.parametrize("row", [{}, {"Vehicle Name": ""}, {"Vehicle Name": "   "}])
def test_local_record_rejects_a_nameless_row(row):
    assert local_record(row) is None


# ---- global records ---------------------------------------------------------

@pytest.mark.unit
def test_global_record_carries_the_spec_columns_the_table_used_to_lack():
    r = global_record(GLOBAL_ROW)
    assert r["id"] == "wuling-air-ev"
    assert r["efficiency_wh_per_km"] == 150.0
    assert r["efficiency_source"] == ev_union.EFFICIENCY_MEASURED
    assert r["torque_nm"] == 110.0
    assert r["acceleration_0_100_s"] == 12.5
    assert r["battery_type"] == "Lithium-ion"
    assert r["number_of_cells"] == 192
    assert r["towing_capacity_kg"] == 0
    assert r["cargo_volume_l"] == 185
    assert r["segment"] == "B - Compact"
    assert (r["length_mm"], r["width_mm"], r["height_mm"]) == (3673, 1683, 1518)
    # the DC power lands in both the planner's column and the raw one
    assert r["max_dc_charge_kw"] == r["fast_charging_power_kw_dc"] == 40.0


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("185", 185),
    ("0", 0),
    ("", None),
    ("10 Banana Boxes", None),      # a count of boxes is not a litre figure
    ("31 Banana Boxes", None),
])
def test_cargo_volume_is_null_rather_than_a_wrong_number(raw, expected):
    assert global_record({**GLOBAL_ROW, "cargo_volume_l": raw})["cargo_volume_l"] == expected


@pytest.mark.unit
def test_global_record_rejects_a_row_with_neither_brand_nor_model():
    assert global_record({"brand": "", "model": ""}) is None


# ---- the merge --------------------------------------------------------------

#: A local row whose brand matches no global row and no curated entry, so
#: `local_record` has to fall back to `battery * 1000 / range` and every
#: enrichment field stays empty.
UNENRICHED_LOCAL_ROW = {**LOCAL_ROW, "Vehicle Name": "Zzz Unknown Trim"}


@pytest.mark.unit
def test_merge_prefers_the_measured_efficiency_over_a_derived_one():
    merged = merge(local_record(UNENRICHED_LOCAL_ROW), global_record(GLOBAL_ROW))
    assert merged["efficiency_wh_per_km"] == 150.0            # measured, not 133.5
    assert merged["efficiency_source"] == ev_union.EFFICIENCY_MEASURED


@pytest.mark.unit
def test_merge_does_not_overwrite_an_enriched_efficiency_with_the_global_one():
    """Adding 478 global rows must not restate a car already in the catalogue.

    Three local ids collide with the global feed. If the global figure won
    there, three Indonesian models would silently change range and charging
    estimates for every driver of them as a side effect of a bigger catalogue.
    """
    merged = merge(local_record(LOCAL_ROW), global_record(GLOBAL_ROW))
    assert merged["efficiency_wh_per_km"] == 115.0            # production's value
    assert merged["efficiency_source"] is None
    assert merged["fast_charge_port"] == "GB/T"
    assert merged["max_dc_charge_kw"] == 20.0


@pytest.mark.unit
def test_merge_keeps_both_sides_instead_of_overwriting_either():
    merged = merge(local_record(LOCAL_ROW), global_record(GLOBAL_ROW))
    # local-only fields survive
    assert merged["price_range"] == "Rp 214 - 307,5 Juta"
    assert merged["charging_time_minutes"] == 510.0
    assert merged["power_hp"] == "40 hp"
    # the Indonesian trim's own battery/range win over the global figures
    assert merged["battery_kwh"] == 26.7 and merged["range_km"] == 200.0
    # global-only spec columns survive
    assert merged["torque_nm"] == 110.0 and merged["segment"] == "B - Compact"
    # and where both carry a value, the local (published) one wins
    assert merged["drivetrain"] == "RWD" and merged["max_dc_charge_kw"] == 20.0
    # provenance names both datasets and keeps both raw rows
    assert merged["source_datasets"] == [LOCAL_DATASET, GLOBAL_DATASET]
    assert set(merged["source_payload"]) == {LOCAL_DATASET, GLOBAL_DATASET}
    assert merged["match_method"] == "union_merge_local_and_global"


@pytest.mark.unit
def test_merge_fills_local_gaps_from_the_global_row():
    local = local_record(UNENRICHED_LOCAL_ROW)
    assert local["top_speed_kmh"] is None and local["fast_charge_port"] is None
    merged = merge(local, global_record(GLOBAL_ROW))
    assert merged["top_speed_kmh"] == 100.0
    assert merged["fast_charge_port"] == "CCS"


# ---- the union --------------------------------------------------------------

@pytest.mark.unit
def test_build_union_merges_shared_ids_and_keeps_everything_else():
    records, stats = build_union(
        [LOCAL_ROW, {**LOCAL_ROW, "Vehicle Name": "BYD M6"}],
        [GLOBAL_ROW, {**GLOBAL_ROW, "brand": "Tesla", "model": "Model 3"}])

    by_id = {r["id"]: r for r in records}
    assert set(by_id) == {"wuling-air-ev", "byd-m6", "tesla-model-3"}
    assert stats["collisions_merged"] == 1
    assert stats["collision_ids"] == ["wuling-air-ev"]
    assert stats["union_total"] == 3
    assert stats["local_rows"] == 2 and stats["global_rows"] == 2
    # 2 local + 2 global - 1 shared
    assert stats["union_total"] == stats["local_rows"] + stats["global_rows"] - 1
    assert by_id["wuling-air-ev"]["source_datasets"] == [LOCAL_DATASET, GLOBAL_DATASET]
    assert by_id["byd-m6"]["source_datasets"] == [LOCAL_DATASET]
    assert by_id["tesla-model-3"]["source_datasets"] == [GLOBAL_DATASET]


@pytest.mark.unit
def test_build_union_is_deterministic_and_local_models_come_first():
    records, _ = build_union([LOCAL_ROW], [{**GLOBAL_ROW, "brand": "Aaa", "model": "Zzz"}])
    assert [r["id"] for r in records] == ["wuling-air-ev", "aaa-zzz"]
    again, _ = build_union([LOCAL_ROW], [{**GLOBAL_ROW, "brand": "Aaa", "model": "Zzz"}])
    assert [r["id"] for r in again] == [r["id"] for r in records]


@pytest.mark.unit
def test_build_union_drops_a_duplicate_id_within_one_dataset_and_says_so():
    _, stats = build_union([LOCAL_ROW, dict(LOCAL_ROW)], [])
    assert stats["local_rows"] == 1
    assert stats["local_duplicate_ids_dropped"] == 1


@pytest.mark.unit
def test_build_union_counts_measured_enriched_and_derived_efficiency():
    _, stats = build_union(
        [{**LOCAL_ROW, "Vehicle Name": "BYD M6"}, UNENRICHED_LOCAL_ROW], [GLOBAL_ROW])
    assert stats["measured_efficiency"] == 1        # the global row
    assert stats["enriched_efficiency"] == 1        # BYD M6, from the curated table
    assert stats["derived_efficiency"] == 1         # the unmatched local one


@pytest.mark.unit
def test_build_union_enriches_every_local_row_not_just_the_first():
    """`global_rows` is consumed once per local model, so it must be a list.

    Handed a one-shot iterator the enrichment would see the whole global feed
    for the first car and an empty feed for the other 59 -- the same silent
    data loss this fix is about, in a different disguise.
    """
    records, _ = build_union(
        iter([LOCAL_ROW, {**LOCAL_ROW, "Vehicle Name": "Wuling Air EV"}]),
        iter([GLOBAL_ROW]))
    by_id = {r["id"]: r for r in records}
    assert by_id["wuling-air-ev"]["fast_charge_port"] == "CCS"   # from the global row


# =============================================================================
# staging shape
# =============================================================================

@pytest.mark.unit
def test_staging_rows_number_records_in_file_order():
    rows = staging_rows(PLN_SOURCE, [{"id": 7}, {"id": 8}, {"id": 9}])
    assert [r["ordinal"] for r in rows] == [0, 1, 2]
    assert [r["source_id"] for r in rows] == ["7", "8", "9"]
    assert all(r["source"] == PLN_SOURCE for r in rows)


@pytest.mark.unit
def test_two_open_charge_map_records_sharing_an_id_both_survive():
    """`ocm_jakarta.json` holds 527 records under 523 distinct `ID`s.

    Keying staging on the source identifier would collapse four stations and
    change the seeded totals, which is why `ordinal` is the key.
    """
    rows = staging_rows(OCM_SOURCE, [{"ID": 101}, {"ID": 101}])
    assert len(rows) == 2
    assert [r["ordinal"] for r in rows] == [0, 1]
    assert [r["source_id"] for r in rows] == ["101", "101"]


@pytest.mark.unit
def test_a_record_without_an_identifier_still_stages():
    (row,) = staging_rows(OCM_SOURCE, [{"AddressInfo": {}}])
    assert row["source_id"] is None
    assert row["ordinal"] == 0


@pytest.mark.unit
def test_osm_records_are_staged_as_elements_keyed_by_type_and_id():
    rows = staging_rows(OSM_SOURCE, {"elements": [
        {"type": "node", "id": 4242}, {"type": "way", "id": 7}]})
    assert [r["source_id"] for r in rows] == ["node-4242", "way-7"]


@pytest.mark.unit
@pytest.mark.parametrize("payload", [{}, {"elements": []}, {"elements": None}, [], "nonsense"])
def test_an_empty_overpass_envelope_stages_nothing(payload):
    assert osm_elements(payload) == []
    assert staging_rows(OSM_SOURCE, payload) == []


@pytest.mark.unit
def test_a_non_object_record_is_still_preserved_verbatim():
    import json
    (row,) = staging_rows(PLN_SOURCE, ["not an object"])
    assert json.loads(row["payload"]) == {"_raw": "not an object"}


# =============================================================================
# pruning
# =============================================================================

class _RecordingConn:
    """Just enough of a SQLAlchemy connection to see whether a DELETE ran."""

    def __init__(self, protected=()):
        self.protected = [(p,) for p in protected]
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        text = str(statement)
        if text.strip().upper().startswith("DELETE"):
            return _Result(rowcount=7)
        return _Result(rows=self.protected)


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)


@pytest.mark.unit
def test_prune_refuses_to_delete_the_whole_catalogue_on_an_empty_union():
    """An ingest that found no models has failed, not discovered an empty world.

    `NOT (id = ANY('{}'))` is true for every row, so an unreadable CSV or a
    changed header would turn the step that LOADS the catalogue into the step
    that deletes it. The `users` guard is no defence: it only spares the two or
    three models somebody happens to be driving.
    """
    conn = _RecordingConn()
    with pytest.raises(EmptyUnion) as err:
        prune_ev_models(conn, [])
    assert conn.executed == []                      # nothing reached the database
    assert "refusing to prune" in str(err.value)
    assert "ingest_raw" in str(err.value)


@pytest.mark.unit
def test_prune_still_deletes_and_reports_protected_models_when_the_union_is_real():
    conn = _RecordingConn(protected=["byd-m6"])
    deleted, protected = prune_ev_models(conn, ["wuling-air-ev", "byd-seal"])
    assert deleted == 7
    assert protected == ["byd-m6"]
    assert any(sql.strip().upper().startswith("DELETE") for sql, _ in conn.executed)

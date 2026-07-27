import pytest

from api.dedup import cluster_stations


def _row(id, source, lat, lon, power=None, name=None, conns=None):
    return {"id": id, "source": source, "latitude": lat, "longitude": lon,
            "power_kw": power, "name": name, "address": None, "province": None,
            "city": None, "operator": None, "charge_type": None, "status": None,
            "date_verified": None, "connectors": conns or []}


@pytest.mark.unit
def test_two_points_within_75m_merge():
    a = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000,
             conns=[{"type": "AC Type 2", "count": 1, "speed_tier": "medium",
                     "power_kw": 22, "type_inferred": True}])
    b = _row("open_charge_map-9", "open_charge_map", -6.20020, 106.8000,
             conns=[{"type": "CCS2", "count": 2, "speed_tier": "fast",
                     "power_kw": 150, "type_inferred": True}])
    out = cluster_stations([a, b])
    assert len(out) == 1
    s = out[0]
    assert s["id"] == "pln_spklu-1"
    assert sorted(s["sources"]) == ["open_charge_map", "pln_spklu"]
    assert s["power_kw"] == 150
    assert sorted(s["connector_types"]) == ["AC Type 2", "CCS2"]
    assert {c["type"] for c in s["connectors"]} == {"AC Type 2", "CCS2"}


@pytest.mark.unit
def test_points_over_75m_stay_separate():
    a = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000)
    b = _row("pln_spklu-2", "pln_spklu", -6.2050, 106.8050)
    out = cluster_stations([a, b])
    assert len(out) == 2


@pytest.mark.unit
def test_descriptive_fields_fill_from_first_nonnull_by_priority():
    a = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000, name="PLN Gambir")
    b = _row("open_charge_map-9", "open_charge_map", -6.20010, 106.8000, name="OCM name")
    a["address"] = None
    b["address"] = "Jl. Test 1"
    out = cluster_stations([a, b])
    assert out[0]["name"] == "PLN Gambir"
    assert out[0]["address"] == "Jl. Test 1"


@pytest.mark.unit
def test_deterministic_pln_anchors_regardless_of_input_order():
    a = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000)
    b = _row("osm-node-5", "osm", -6.20010, 106.8000)
    assert cluster_stations([b, a])[0]["id"] == "pln_spklu-1"
    assert cluster_stations([a, b])[0]["id"] == "pln_spklu-1"


# --- how connector COUNTS combine inside a cluster ---------------------------
#
# Three situations, three answers. See api/listing_identity.py for the evidence.

def _ccs2(count, power=120):
    return {"type": "CCS2", "count": count, "speed_tier": "fast",
            "power_kw": power, "type_inferred": True}


def _counts(station):
    out = {}
    for c in station["connectors"]:
        out[(c["type"], c["power_kw"])] = c["count"]
    return out


@pytest.mark.unit
def test_same_source_distinct_cabinets_sum_their_connectors():
    """Real shape of cluster 87 (UP3 Bulungan): three different charger vendors
    at one PLN address. MAX would keep 4 of the 8 real @120 plugs."""
    hvt = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000,
               name="SPKLU CENTER HVT PLN UP3 BULUNGAN", conns=[_ccs2(2)])
    daya = _row("pln_spklu-2", "pln_spklu", -6.20005, 106.8000,
                name="SPKLU CENTER DAYA+ PLN UP3 BULUNGAN",
                conns=[_ccs2(2), _ccs2(2, 180)])
    evcity = _row("pln_spklu-3", "pln_spklu", -6.20010, 106.8000,
                  name="SPKLU CENTER EVCITY PLN UP3 BULUNGAN", conns=[_ccs2(4)])
    out = cluster_stations([hvt, daya, evcity])
    assert len(out) == 1
    assert _counts(out[0]) == {("CCS2", 120): 8, ("CCS2", 180): 2}


@pytest.mark.unit
def test_same_source_duplicate_listing_takes_max_not_sum():
    """Real shape of cluster 207: one site imported twice with a typo, at an
    identical coordinate. Summing would invent five plugs that do not exist."""
    a = _row("pln_spklu-1", "pln_spklu", -7.294079, 112.676155,
             name="SPKLU Utomo Charge+ Loop Graha Familly",
             conns=[_ccs2(5, 180)])
    b = _row("pln_spklu-2", "pln_spklu", -7.294079, 112.676155,
             name="SPKLU Utomo Charge+ Loop Graha Family",
             conns=[_ccs2(5, 180)])
    out = cluster_stations([a, b])
    assert len(out) == 1
    assert _counts(out[0]) == {("CCS2", 180): 5}


@pytest.mark.unit
def test_cross_source_rows_for_one_site_still_take_max():
    """Two sources describing the same physical station. Unchanged behaviour:
    the within-source rule must never leak across the source boundary."""
    pln = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000,
               name="SPKLU PLN Kantor Gambir", conns=[_ccs2(4)])
    ocm = _row("open_charge_map-9", "open_charge_map", -6.20020, 106.8000,
               name="Gambir PLN Office", conns=[_ccs2(4)])
    out = cluster_stations([pln, ocm])
    assert len(out) == 1
    assert sorted(out[0]["sources"]) == ["open_charge_map", "pln_spklu"]
    assert _counts(out[0]) == {("CCS2", 120): 4}


@pytest.mark.unit
def test_cross_source_max_applies_after_within_source_sum():
    """A PLN venue with two cabinets (4+4) that OCM also lists as 8. The site has
    8 plugs, not 16: SUM within PLN, then MAX against OCM."""
    a = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000,
             name="SPKLU HVT Plaza Selatan", conns=[_ccs2(4)])
    b = _row("pln_spklu-2", "pln_spklu", -6.20005, 106.8000,
             name="SPKLU EVCITY Plaza Selatan", conns=[_ccs2(4)])
    ocm = _row("open_charge_map-9", "open_charge_map", -6.20010, 106.8000,
               name="Plaza Selatan Charging Hub", conns=[_ccs2(8)])
    out = cluster_stations([a, b, ocm])
    assert len(out) == 1
    assert _counts(out[0]) == {("CCS2", 120): 8}


@pytest.mark.unit
def test_max_still_applies_when_a_source_lists_one_row_only():
    """The common case: a single row per source must be untouched by the rule."""
    a = _row("pln_spklu-1", "pln_spklu", -6.2000, 106.8000,
             name="SPKLU PLN Gambir", conns=[_ccs2(3)])
    assert _counts(cluster_stations([a])[0]) == {("CCS2", 120): 3}


@pytest.mark.unit
def test_duplicate_listings_join_transitively():
    """McD Kelapa Gading appears three times in the PLN batch; the three rows
    must collapse into ONE listing, not two."""
    rows = [_row(f"pln_spklu-{i}", "pln_spklu", -6.2000, 106.8000 + i * 1e-5,
                 name=n, conns=[_ccs2(2)])
            for i, n in enumerate(["(VOLTRON) McD Kelapa Gading",
                                   "(VOLTRON) McD Kelapa Gading",
                                   "(VOLTRON) McD Kelapa Gading Jakarta"])]
    assert _counts(cluster_stations(rows)[0]) == {("CCS2", 120): 2}


# --- the two signals the rule is built on ------------------------------------
#
# `tests/test_listing_identity.py` holds the full 23-group audit oracle. These
# two cover the same ground end-to-end, through `cluster_stations`, because the
# connector arithmetic is where the mistake would actually be paid for.

@pytest.mark.unit
def test_enumerated_units_at_one_venue_sum_rather_than_collapse():
    """"TRANSMART PEKANBARU A" and "B" are two real chargers. The unit letter is
    an enumerator, so the rows are distinct however similar the rest reads."""
    a = _row("pln_spklu-1", "pln_spklu", 0.5000, 101.4500,
             name="SPKLU TRANSMART PEKANBARU A", conns=[_ccs2(2)])
    b = _row("pln_spklu-2", "pln_spklu", 0.50005, 101.4500,
             name="SPKLU TRANSMART PEKANBARU B", conns=[_ccs2(2)])
    assert _counts(cluster_stations([a, b])[0]) == {("CCS2", 120): 4}


@pytest.mark.unit
def test_one_site_under_two_different_names_takes_max():
    """One Surabaya building listed under its two real names. Token overlap is
    weak, but the rows are co-located, carry no enumerator and offer the same
    plug kinds, so summing them would invent connectors."""
    a = _row("pln_spklu-1", "pln_spklu", -7.2500, 112.7500,
             name="SPKLU Gedung Pemkot Surabaya", conns=[_ccs2(2)])
    b = _row("pln_spklu-2", "pln_spklu", -7.25005, 112.7500,
             name="SPKLU BALAI KOTA SURABAYA", conns=[_ccs2(2)])
    assert _counts(cluster_stations([a, b])[0]) == {("CCS2", 120): 2}


@pytest.mark.unit
def test_sublocation_marker_splits_a_warehouse_from_its_office():
    """"GUDANG" (warehouse) names a part of the venue, not the venue, so the
    warehouse cabinet is separate hardware from the office one."""
    office = _row("pln_spklu-1", "pln_spklu", -6.283431, 106.930197,
                  name="SPKLU PLN UP3 PONDOK GEDE", conns=[_ccs2(2)])
    gudang = _row("pln_spklu-2", "pln_spklu", -6.283279, 106.930390,
                  name="SPKLU GUDANG PLN UP3 PONDOK GEDE", conns=[_ccs2(1)])
    assert _counts(cluster_stations([office, gudang])[0]) == {("CCS2", 120): 3}


@pytest.mark.unit
def test_an_acronym_and_its_expansion_are_one_listing():
    """The worst duplicates are abbreviations: "(VOLTRON) TKDN" is the same
    cabinet as "(VOLTRON) Teknologi Karya Digital Nusa"."""
    a = _row("pln_spklu-1", "pln_spklu", -6.159257, 106.668431,
             name="(VOLTRON) TKDN", conns=[_ccs2(1)])
    b = _row("pln_spklu-2", "pln_spklu", -6.159257, 106.668431,
             name="(VOLTRON) Teknologi Karya Digital Nusa", conns=[_ccs2(1)])
    assert _counts(cluster_stations([a, b])[0]) == {("CCS2", 120): 1}


@pytest.mark.unit
def test_ambiguous_group_different_venues_same_brand_are_kept_apart():
    """Cluster 176, hand-labelled AMBIGUOUS: (HVT) Mediterania Garden 1 and
    (HVT) Central Park Residence sit at an identical coordinate with identical
    connector sets. They are adjacent Jakarta developments that may or may not
    share one charger. Same brand but zero token overlap, so the rule treats them
    as distinct and sums. Recorded here as a judgement call, not a proven fact."""
    a = _row("pln_spklu-1", "pln_spklu", -6.1780, 106.7900,
             name="SPKLU (HVT) Mediterania Garden 1",
             conns=[{"type": "CCS2", "count": 3, "speed_tier": "medium",
                     "power_kw": 50, "type_inferred": True}])
    b = _row("pln_spklu-2", "pln_spklu", -6.1780, 106.7900,
             name="SPKLU (HVT) Central Park Residence",
             conns=[{"type": "CCS2", "count": 3, "speed_tier": "medium",
                     "power_kw": 50, "type_inferred": True}])
    out = cluster_stations([a, b])
    assert len(out) == 1
    assert _counts(out[0]) == {("CCS2", 50): 6}

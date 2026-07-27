"""Unit tests for the same-source duplicate-listing heuristic.

Every name below is a real row from the PLN / OCM feeds, taken from the
hand-labelled audit of the 117 groups where MAX actually discards connectors.

The two parametrised blocks at the bottom (``AUDIT_DUPLICATES`` /
``AUDIT_DISTINCT``) ARE the audit oracle. They are the acceptance criterion for
any future change to `api.listing_identity`: a duplicate that gets summed
invents connectors that do not exist, which is the one failure the rule is not
allowed to make.
"""
import itertools

import pytest

from api import listing_identity as li


# --- the audit oracle --------------------------------------------------------
#
# Real duplicates. Each of these was summed by the old brand+Jaccard rule and
# each summing invented plugs. They must all be judged ONE listing.
#
# ``coloc``/``profile`` mirror what dedup passes as corroboration: the distance
# between the two rows and their connector lists. Where they are omitted the
# names alone must be enough.
_AC22 = [{"type": "AC Type 2", "power_kw": 22.0, "count": 2}]
_TRIMODAL = [{"type": "AC Type 2", "power_kw": 11.0, "count": 6},
             {"type": "AC Type 2", "power_kw": 22.0, "count": 6},
             {"type": "AC Type 2", "power_kw": 7.0, "count": 4}]
_BELLEZZA = [{"type": "AC Type 2", "power_kw": 22.0, "count": 1},
             {"type": "AC Type 2", "power_kw": 7.0, "count": 1}]

AUDIT_DUPLICATES = [
    # id, name a, name b, corroboration kwargs
    ("thamrin-nine",
     "SPKLU Utomo Charge+ Thamrin Nine - UoB Plaza, Jakarta",
     "SPKLU Utomo Charge+ Thamrinine - UOB Chub Square",
     {"distance_m": 0.0, "connectors_a": _TRIMODAL, "connectors_b": _TRIMODAL}),
    ("voltron-tkdn-acronym",
     "(VOLTRON) TKDN", "(VOLTRON) Teknologi Karya Digital Nusa", {}),
    ("voltron-mkg-acronym",
     "(VOLTRON) MKG Kemayoran", "(VOLTRON) Mega Glodok Kemayoran", {}),
    ("surabaya-city-hall",
     "SPKLU Gedung Pemkot Surabaya", "SPKLU BALAI KOTA SURABAYA",
     {"distance_m": 0.0, "connectors_a": _AC22, "connectors_b": _AC22}),
    ("springhill-spelling",
     "(VOLTRON) Springhill Terrace Residences",
     "(VOLTRON) Springhills Terrace Residence", {}),
    ("bellezza",
     "(VOLTRON) The Bellezza Retail & Apartment",
     "(VOLTRON) The Bellezza Shopping Arcade",
     {"distance_m": 0.0, "connectors_a": _BELLEZZA, "connectors_b": _BELLEZZA}),
    ("by-the-sea-word-order",
     "(VOLTRON) By The Sea Shopping District at Golf Island PIK",
     "(VOLTRON) PIK By The Sea", {}),
    ("mcd-simatupang-abbrev",
     "(VOLTRON) McD TB Simatupang",
     "(VOLTRON) McDonald's Simatupang Tanjung Barat", {}),
    ("kompas-gramedia-acronym",
     "SPKLU Utomo Charge+ Kompas Gramedia Palmerah Barat",
     "SPKLU Utomo Charge+ KG Property Palmerah", {}),
    ("lepolonia-unbranded-vs-branded",
     "Hotel LePolonia - Medan", "(STARVO) LePolonia Hotel & Convention", {}),
    ("citereup-spelling",
     "SPKLU ULP Citereup", "PLN ULP Citeureup", {}),
]

# Genuinely distinct hardware. Each of these was collapsed by the old rule and
# each collapse silently deleted real plugs. Every PAIR inside a group must be
# judged distinct, otherwise the transitive join in dedup merges the group.
AUDIT_DISTINCT = [
    ("transmart-a-b", ["SPKLU TRANSMART PEKANBARU A",
                       "SPKLU TRANSMART PEKANBARU B"]),
    ("gringging-lombok", ["Resto Ayam Goreng Gringging Lombok",
                          "Resto Ayam Goreng Gringging Lombok 2",
                          "Resto Ayam Goreng Gringging Lombok 3"]),
    ("puri-beta", ["SPKLU PLN Kawasan Puri Beta 1",
                   "SPKLU PLN Kawasan Puri Beta 2"]),
    ("denso", ["(STARVO) DENSO Indonesia 1", "(STARVO) DENSO Indonesia 2"]),
    ("batavia-towers", ["(Terra Charge) Batavia Apartment Tower 1",
                        "(Terra Charge) Batavia Apartment Tower 2"]),
    ("world-trade-center", ["(TERRA CHARGE) World Trade Center DC",
                            "(TERRA CHARGE) World Trade Center 6 A",
                            "(TERRA CHARGE) World Trade Center 6 B",
                            "(TERRA CHARGE) World Trade Center 1"]),
    ("mth-27-floors", ["(TERRA CHARGE) MTH 27 Office Suites (B1)",
                       "(TERRA CHARGE) MTH 27 Office Suites (GF)"]),
    ("west-vista", ["(TERRA CHARGE) West Vista Shop House",
                    "(TERRA CHARGE) West Vista Apartment"]),
    ("royal-tulip", ["(STROOM PPI) Royal Tulip Gunung Geulis Parking Area",
                     "(STROOM PPI) Royal Tulip Gunung Geulis Wing C"]),
    ("aloha-pik-2", ["SPKLU ALOHA PIK 2",
                     "SPKLU HVT ALOHA PIK 2",
                     "SPKLU Center HVT Aloha PIK 2",
                     "SPKLU Center Daya+ Aloha PIK 2"]),
    ("rest-area-km-229b",
     ["SPKLU Center Amanah Raharjo Rest Area KM 229 B Ruas Kanci - Pejagan",
      "SPKLU Center Niscala Rest Area KM 229 B Ruas Kanci - Pejagan",
      "SPKLU ALVACHARGE 60 kW RA KM 229 B RUAS KANCI - PEJAGAN",
      "SPKLU HVT Rest Area KM 229B",
      "SPKLU REST AREA KM 229 B RUAS KANCI - PEJAGAN"]),
    ("up3-pondok-gede", ["SPKLU EVCITY PLN UP3 PONDOK GEDE",
                         "SPKLU PLN UP3 PONDOK GEDE",
                         "SPKLU GUDANG PLN UP3 PONDOK GEDE"]),
]


@pytest.mark.unit
@pytest.mark.parametrize("a,b,kwargs",
                         [c[1:] for c in AUDIT_DUPLICATES],
                         ids=[c[0] for c in AUDIT_DUPLICATES])
def test_audit_duplicates_are_one_listing(a, b, kwargs):
    """HARD CONSTRAINT: a confirmed duplicate must never be summed."""
    assert li.same_listing(a, b, **kwargs) is True
    assert li.same_listing(b, a, **_swap(kwargs)) is True


def _swap(kwargs):
    out = dict(kwargs)
    if "connectors_a" in out:
        out["connectors_a"], out["connectors_b"] = out["connectors_b"], out["connectors_a"]
    return out


@pytest.mark.unit
@pytest.mark.parametrize("names", [c[1] for c in AUDIT_DISTINCT],
                         ids=[c[0] for c in AUDIT_DISTINCT])
def test_audit_distinct_groups_never_collapse(names):
    """OBJECTIVE: enumerated / sub-located units are real, separate hardware.

    Corroboration is handed in at its most favourable (0 m apart, identical
    connector profile) to prove the distinctness veto really does outrank it.
    """
    same_profile = {"distance_m": 0.0, "connectors_a": _AC22, "connectors_b": _AC22}
    for a, b in itertools.combinations(names, 2):
        assert li.same_listing(a, b, **same_profile) is False, f"{a!r} vs {b!r}"


# --- the pieces the oracle rests on ------------------------------------------

@pytest.mark.unit
def test_normalize_name_lowercases_and_strips_punctuation():
    assert li.normalize_name("(VOLTRON) Menara Era!") == "voltron menara era"
    assert li.normalize_name("  Utomo   Charge+  ") == "utomo charge+"
    assert li.normalize_name(None) == ""
    assert li.normalize_name("") == ""


@pytest.mark.unit
def test_normalize_name_drops_possessives_so_they_are_not_read_as_unit_letters():
    """"McDonald's" must not leave a bare "s" behind: a lone letter is an
    enumerator, and one would veto a real duplicate."""
    assert li.normalize_name("McDonald's Simatupang") == "mcdonald simatupang"
    assert "s" not in li.enumerator_signature("McDonald's Simatupang")


@pytest.mark.unit
def test_core_tokens_drop_noise_words_and_bare_digits():
    assert li.core_tokens("SPKLU PLN Kawasan Puri Beta 1") == {"kawasan", "puri", "beta"}
    # a name made only of noise has no identity left
    assert li.core_tokens("SPKLU PLN CHARGING STATION") == set()


@pytest.mark.unit
def test_brand_token_finds_the_network_and_prefers_the_longer_match():
    assert li.brand_token("SPKLU Utomo Charge+ Loop Graha Family") == "utomo charge+"
    assert li.brand_token("SPKLU Utomo Binus University") == "utomo"
    assert li.brand_token("(VOLTRON) AIA Central") == "voltron"
    assert li.brand_token("SPKLU PLN Kantor Pusat") == ""


@pytest.mark.unit
def test_identity_tokens_drop_the_brand_and_keep_reading_order():
    assert li.identity_tokens("(VOLTRON) Mega Glodok Kemayoran") == \
        ["mega", "glodok", "kemayoran"]
    assert li.identity_tokens("SPKLU Utomo Charge+ KG Property Palmerah") == \
        ["kg", "property", "palmerah"]


@pytest.mark.unit
@pytest.mark.parametrize("name,expected", [
    ("SPKLU TRANSMART PEKANBARU A", {"a"}),
    ("(Terra Charge) Batavia Apartment Tower 2", {"tower", "2"}),
    ("(TERRA CHARGE) MTH 27 Office Suites (B1)", {"27", "b1"}),
    ("(TERRA CHARGE) MTH 27 Office Suites (GF)", {"27", "gf"}),
    ("(STROOM PPI) Royal Tulip Gunung Geulis Wing C", {"wing", "c"}),
    ("(TERRA CHARGE) West Vista Shop House", {"shophouse"}),
    ("SPKLU GUDANG PLN UP3 PONDOK GEDE", {"gudang", "up3"}),
    ("SPKLU Center HVT Aloha PIK 2", {"center", "2"}),
    ("(VOLTRON) Springhill Terrace Residences", set()),
])
def test_enumerator_signature_picks_up_unit_markers_only(name, expected):
    assert li.enumerator_signature(name) == expected


@pytest.mark.unit
def test_name_jaccard_bounds():
    assert li.name_jaccard("Menara Era", "Menara Era") == 1.0
    assert li.name_jaccard("Menara Era", "Pakubuwono View") == 0.0
    # two all-noise names share nothing identifying, so 0.0 rather than 1.0
    assert li.name_jaccard("SPKLU PLN", "SPKLU PLN CHARGING") == 0.0
    assert li.name_jaccard(None, None) == 0.0


@pytest.mark.unit
def test_fuzzy_overlap_credits_acronyms_abbreviations_and_spellings():
    assert li.fuzzy_overlap("(VOLTRON) TKDN",
                            "(VOLTRON) Teknologi Karya Digital Nusa") == 1.0
    # transposed initials: the feed writes Mega Glodok Kemayoran as "MKG"
    assert li.fuzzy_overlap("(VOLTRON) MKG Kemayoran",
                            "(VOLTRON) Mega Glodok Kemayoran") == 1.0
    assert li.fuzzy_overlap("SPKLU ULP Citereup", "PLN ULP Citeureup") == 1.0
    assert li.fuzzy_overlap("(VOLTRON) Pakubuwono View",
                            "(VOLTRON) Plaza Slipi Jaya") == 0.0
    assert li.fuzzy_overlap(None, None) == 0.0


@pytest.mark.unit
@pytest.mark.parametrize("a,b", [
    ("SPKLU Utomo Charge+ Loop Graha Familly", "SPKLU Utomo Charge+ Loop Graha Family"),
    ("(VOLTRON) Menara Era", "(VOLTRON) Menara Era"),
    ("Siloam Hospital Cikarang", "Siloam Hospitals Cikarang"),
    ("Utomo Oakwood Premier Cozmo", "Utomo Oakwood"),
    ("Bez Walk", "BEZ Walk"),
])
def test_true_duplicates_are_detected(a, b):
    assert li.same_listing(a, b) is True


@pytest.mark.unit
@pytest.mark.parametrize("a,b", [
    # different cabinet vendors at one PLN venue -> different brand token
    ("SPKLU CENTER HVT PLN UP3 BULUNGAN", "SPKLU CENTER EVCITY PLN UP3 BULUNGAN"),
    ("(VOLTRON) Menara Era", "(HVT) Menara Era"),
    # a brand bolted onto an otherwise identical name is a SECOND cabinet
    ("SPKLU ALOHA PIK 2", "SPKLU HVT ALOHA PIK 2"),
    ("SPKLU PLN UP3 PONDOK GEDE", "SPKLU EVCITY PLN UP3 PONDOK GEDE"),
    # different venues under one brand -> no token overlap
    ("(VOLTRON) Pakubuwono View", "(VOLTRON) Plaza Slipi Jaya"),
    ("SPKLU (HVT) Mediterania Garden 1", "SPKLU (HVT) Central Park Residence"),
    # two different PLN service units that share a (wrong) coordinate
    ("SPKLU PLN KANTOR ULP PANIKI", "SPKLU PLN ULP RATAHAN"),
])
def test_distinct_chargers_are_not_collapsed(a, b):
    assert li.same_listing(a, b) is False


@pytest.mark.unit
def test_corroboration_cannot_decide_on_its_own():
    """Identical coordinates and an identical connector profile must not merge
    two names that share nothing. 47 of the audited groups sit at exactly 0 m
    and split roughly evenly between duplicates and multi-cabinet venues."""
    assert li.same_listing("SPKLU (HVT) Mediterania Garden 1",
                           "SPKLU (HVT) Central Park Residence",
                           distance_m=0.0,
                           connectors_a=_AC22, connectors_b=_AC22) is False


@pytest.mark.unit
def test_corroboration_cannot_override_the_distinctness_veto():
    """Two enumerated units at one address, at 0 m, with byte-identical
    connector lists, are still two units."""
    assert li.same_listing("(TERRA CHARGE) MTH 27 Office Suites (B1)",
                           "(TERRA CHARGE) MTH 27 Office Suites (GF)",
                           distance_m=0.0,
                           connectors_a=_AC22, connectors_b=_AC22) is False


@pytest.mark.unit
def test_corroboration_needs_both_colocation_and_a_matching_profile():
    """The Bellezza pair only clears the bar because BOTH corroborate; drop
    either one and the answer falls back to DISTINCT (i.e. SUM)."""
    a = "(VOLTRON) The Bellezza Retail & Apartment"
    b = "(VOLTRON) The Bellezza Shopping Arcade"
    assert li.same_listing(a, b) is False
    assert li.same_listing(a, b, distance_m=0.0,
                           connectors_a=_BELLEZZA, connectors_b=_BELLEZZA) is True
    assert li.same_listing(a, b, distance_m=60.0,
                           connectors_a=_BELLEZZA, connectors_b=_BELLEZZA) is False
    assert li.same_listing(a, b, distance_m=0.0,
                           connectors_a=_BELLEZZA, connectors_b=_AC22) is False


@pytest.mark.unit
def test_same_listing_is_symmetric_and_reflexive():
    a, b = "(VOLTRON) McD Kelapa Gading", "(VOLTRON) McD Kelapa Gading Jakarta"
    assert li.same_listing(a, b) == li.same_listing(b, a) is True
    assert li.same_listing(a, a) is True


@pytest.mark.unit
def test_unnamed_rows_are_treated_as_distinct_rather_than_merged():
    """Two rows with no usable name have no identity tokens at all, so they are
    NOT collapsed -- the safe direction, since collapsing on no evidence would
    silently delete plugs."""
    assert li.same_listing(None, None) is False
    assert li.same_listing("SPKLU PLN", "SPKLU PLN") is False
    assert li.same_listing("SPKLU PLN", "SPKLU PLN", distance_m=0.0,
                           connectors_a=_AC22, connectors_b=_AC22) is False


@pytest.mark.unit
def test_thresholds_are_the_documented_ones():
    assert li.NAME_JACCARD_THRESHOLD == 0.5
    assert li.FUZZY_MATCH_THRESHOLD == 0.5
    assert li.CORROBORATED_MATCH_THRESHOLD == 0.2
    assert li.COLOCATED_M == 20.0

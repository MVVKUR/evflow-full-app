"""Connector normalisation and vehicle compatibility (AC 2.2.9 "the vehicle can use")."""
from __future__ import annotations

import pytest

from api.services.connector_compat import (
    AC_TYPE_2,
    CCS2,
    CHADEMO,
    GBT,
    connector_is_compatible,
    normalize_connector_type,
    vehicle_connector_profile,
)


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("CCS", CCS2),
    ("CCS2", CCS2),
    ("ccs-2", CCS2),
    ("Combo", CCS2),
    ("CCS Combo 2", CCS2),
    ("Type 2", AC_TYPE_2),
    ("TYPE2", AC_TYPE_2),
    ("AC Type 2", AC_TYPE_2),
    ("Mennekes", AC_TYPE_2),
    ("CHAdeMO", CHADEMO),
    ("chademo", CHADEMO),
    ("GB/T", GBT),
    ("gbt", GBT),
    (None, None),
    ("", None),
    ("something else", None),
])
def test_normalize_connector_type(raw, expected):
    assert normalize_connector_type(raw) == expected


@pytest.mark.unit
def test_catalogue_ccs_matches_live_ccs2():
    """The catalogue stores 'CCS'; the live connectors table only has 'CCS2'."""
    profile = vehicle_connector_profile("CCS")
    assert profile.accepts("CCS2")
    assert profile.types[0] == CCS2
    assert profile.source == "ev_model"


@pytest.mark.unit
def test_every_vehicle_also_gets_the_universal_ac_inlet_marked_inferred():
    profile = vehicle_connector_profile("CCS")
    assert AC_TYPE_2 in profile.types
    assert profile.is_inferred(AC_TYPE_2) is True
    assert profile.is_inferred(CCS2) is False


@pytest.mark.unit
def test_null_port_falls_back_to_ac_type_2_not_to_everything():
    """~31 Indonesia-only models have fast_charge_port IS NULL."""
    profile = vehicle_connector_profile(None)
    assert profile.types == (AC_TYPE_2,)
    assert profile.source == "default"
    assert profile.is_fully_inferred is True
    # The old code returned True for ANY connector here.
    assert profile.accepts(CCS2) is False
    assert profile.accepts(CHADEMO) is False
    assert profile.accepts(AC_TYPE_2) is True


@pytest.mark.unit
def test_null_port_falls_back_to_the_user_profile_first():
    profile = vehicle_connector_profile(None, main_connector_type="CCS2")
    assert profile.source == "user_profile"
    assert profile.accepts(CCS2) is True
    assert profile.accepts(AC_TYPE_2) is True


@pytest.mark.unit
def test_ac_type_2_vehicle_does_not_double_count_the_universal_inlet():
    profile = vehicle_connector_profile("Type 2")
    assert profile.types == (AC_TYPE_2,)
    # Stated by the catalogue, so NOT inferred.
    assert profile.inferred_types == ()


@pytest.mark.unit
def test_connector_is_compatible_never_blanket_passes_an_unknown_port():
    assert connector_is_compatible(None, station_types=["CCS2"]) is False
    assert connector_is_compatible(None, station_types=["AC Type 2"]) is True
    assert connector_is_compatible("CCS", station_types=["CCS2"]) is True
    assert connector_is_compatible("CHAdeMO", station_types=["CCS2"]) is False
    assert connector_is_compatible("CCS", station_connectors=[{"type": "CCS2"}]) is True

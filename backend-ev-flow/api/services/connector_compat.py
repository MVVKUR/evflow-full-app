"""Connector-type normalisation and vehicle compatibility (AC 2.2.9).

Two vocabularies have to meet here:

* the EV catalogue (``ev_models.fast_charge_port``) stores raw dataset strings
  such as ``'CCS'``, ``'CHAdeMO'``, ``'GB/T'``, and is NULL for ~31
  Indonesia-only models;
* the live ``connectors`` table stores only ``'CCS2'`` and ``'AC Type 2'``.

A literal string match between the two yields zero rows for every CCS car, so
both sides are normalised to the live vocabulary before comparison.

The old behaviour ("no port on file -> compatible with everything") is gone: an
unknown port now resolves to a *conservative inferred* set rather than to a
blanket pass.
"""
from __future__ import annotations

import re
from typing import Iterable, List, NamedTuple, Optional, Sequence

# Canonical types, spelled exactly as the live `connectors` table stores them.
CCS2 = "CCS2"
AC_TYPE_2 = "AC Type 2"
CHADEMO = "CHAdeMO"
GBT = "GB/T"
TYPE_1 = "Type 1"

# AC Type 2 is the de-facto universal inlet in Indonesia and 53.9% of live plugs
# are that type, so every vehicle is assumed to be able to use one.
UNIVERSAL_CONNECTOR_TYPE = AC_TYPE_2

CANONICAL_TYPES = (CCS2, AC_TYPE_2, CHADEMO, GBT, TYPE_1)

# Normalised key (uppercase, alphanumerics only) -> canonical type.
_NORMALIZATION_MAP = {
    # --- CCS family -------------------------------------------------------
    "CCS": CCS2,
    "CCS1": CCS2,
    "CCS2": CCS2,
    "CCSCOMBO": CCS2,
    "CCSCOMBO2": CCS2,
    "CCSTYPE2": CCS2,
    "COMBO": CCS2,
    "COMBO1": CCS2,
    "COMBO2": CCS2,
    "IEC621963": CCS2,
    "TYPE2CCS": CCS2,
    "DCCCS": CCS2,
    # --- AC Type 2 family -------------------------------------------------
    "TYPE2": AC_TYPE_2,
    "ACTYPE2": AC_TYPE_2,
    "AC2": AC_TYPE_2,
    "MENNEKES": AC_TYPE_2,
    "IEC621962": AC_TYPE_2,
    "TYPE2MENNEKES": AC_TYPE_2,
    "ACMENNEKES": AC_TYPE_2,
    # --- CHAdeMO ----------------------------------------------------------
    "CHADEMO": CHADEMO,
    "CHADEMO2": CHADEMO,
    "JEVSG105": CHADEMO,
    # --- GB/T -------------------------------------------------------------
    "GBT": GBT,
    "GBT20234": GBT,
    "GB": GBT,
    "CHINAGBT": GBT,
    # --- Type 1 -----------------------------------------------------------
    "TYPE1": TYPE_1,
    "J1772": TYPE_1,
    "SAEJ1772": TYPE_1,
    "IEC621961": TYPE_1,
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _key(raw: Optional[str]) -> str:
    return _NON_ALNUM.sub("", str(raw or "").upper())


def normalize_connector_type(raw: Optional[str]) -> Optional[str]:
    """Map any spelling of a connector standard onto the live vocabulary.

    Returns ``None`` for empty/unrecognisable input rather than guessing.
    """
    key = _key(raw)
    if not key:
        return None
    if key in _NORMALIZATION_MAP:
        return _NORMALIZATION_MAP[key]
    # Substring fallbacks, most specific first.
    if "CHADEMO" in key:
        return CHADEMO
    if "CCS" in key or "COMBO" in key:
        return CCS2
    if "GBT" in key:
        return GBT
    if "TYPE2" in key or "MENNEKES" in key:
        return AC_TYPE_2
    if "TYPE1" in key or "J1772" in key:
        return TYPE_1
    return None


def normalize_many(raws: Optional[Iterable[Optional[str]]]) -> List[str]:
    """Normalise a collection, dropping unknowns and preserving first-seen order."""
    out: List[str] = []
    for raw in raws or []:
        norm = normalize_connector_type(raw)
        if norm and norm not in out:
            out.append(norm)
    return out


class VehicleConnectorProfile(NamedTuple):
    """The connector standards a vehicle can actually plug into."""

    types: tuple            # canonical types, most-preferred (DC) first
    inferred_types: tuple   # subset of `types` that was assumed, not stated
    source: str             # 'ev_model' | 'user_profile' | 'default'

    @property
    def is_fully_inferred(self) -> bool:
        return len(self.inferred_types) == len(self.types)

    def accepts(self, connector_type: Optional[str]) -> bool:
        norm = normalize_connector_type(connector_type)
        return bool(norm) and norm in self.types

    def is_inferred(self, connector_type: Optional[str]) -> bool:
        norm = normalize_connector_type(connector_type)
        return bool(norm) and norm in self.inferred_types


def vehicle_connector_profile(
    fast_charge_port: Optional[str] = None,
    main_connector_type: Optional[str] = None,
    include_universal_ac: bool = True,
) -> VehicleConnectorProfile:
    """Derive the usable connector set for a vehicle (AC 2.2.9 "can use").

    Precedence: the catalogue's ``fast_charge_port`` when known, else the user's
    ``main_connector_type``, else the universal AC inlet. ``AC Type 2`` is added
    to every profile as an *inferred* entry so the response can label it.
    """
    dc_type = normalize_connector_type(fast_charge_port)
    source = "ev_model"

    if dc_type is None:
        dc_type = normalize_connector_type(main_connector_type)
        source = "user_profile" if dc_type else "default"

    types: List[str] = []
    inferred: List[str] = []

    if dc_type:
        types.append(dc_type)

    if include_universal_ac and UNIVERSAL_CONNECTOR_TYPE not in types:
        types.append(UNIVERSAL_CONNECTOR_TYPE)
        # Stated by the catalogue only when the port itself IS AC Type 2.
        inferred.append(UNIVERSAL_CONNECTOR_TYPE)

    if not types:  # include_universal_ac=False and nothing known
        types.append(UNIVERSAL_CONNECTOR_TYPE)
        inferred.append(UNIVERSAL_CONNECTOR_TYPE)
        source = "default"

    return VehicleConnectorProfile(
        types=tuple(types), inferred_types=tuple(inferred), source=source
    )


def connector_is_compatible(
    vehicle_connector: Optional[str],
    station_connectors: Optional[Sequence] = None,
    station_types: Optional[Sequence[str]] = None,
) -> bool:
    """Back-compatible helper: can this vehicle plug in anywhere at this station?

    Unlike the original implementation this NEVER returns ``True`` merely
    because the vehicle's port is unknown -- an unknown port falls back to the
    universal AC inlet and still has to be matched.
    """
    profile = vehicle_connector_profile(vehicle_connector)

    for t in station_types or []:
        if profile.accepts(t):
            return True

    for c in station_connectors or []:
        ctype = c.get("type") if isinstance(c, dict) else getattr(c, "type", None)
        if profile.accepts(ctype):
            return True

    return False

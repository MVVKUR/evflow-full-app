"""Deduplicate charging stations: merge points within a radius into one station.

Pure functions, no I/O. Rows are processed in source-priority order (PLN, then
Open Charge Map, then OSM) so a PLN row anchors each cluster, making the result
deterministic. Each input row is a normalized dict with at least: id, source,
name, latitude, longitude, power_kw, connector_types, and the descriptive fields.

Connector COUNTS combine per `_finalize`: MAX across sources, and within a source
MAX only for rows judged to be one listing imported twice, SUM otherwise. See
`listing_identity` for that judgement and its measured accuracy.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from . import connectors, listing_identity

MERGE_RADIUS_M = 75.0
SOURCE_PRIORITY = {"pln_spklu": 0, "open_charge_map": 1, "osm": 2}
_DESC_FIELDS = ("name", "address", "province", "city", "operator",
                "charge_type", "status", "date_verified")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8  # mean earth radius, metres
    p1, p2 = radians(lat1), radians(lat2)
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _priority(row: dict) -> int:
    return SOURCE_PRIORITY.get(row.get("source"), 99)


def cluster_stations(rows: list[dict], radius_m: float = MERGE_RADIUS_M) -> list[dict]:
    """Merge rows whose coordinates are within radius_m of a cluster's anchor."""
    ordered = sorted(rows, key=lambda r: (_priority(r), str(r.get("id"))))
    clusters: list[dict] = []
    for r in ordered:
        anchor = None
        for c in clusters:
            if _haversine_m(r["latitude"], r["longitude"], c["latitude"], c["longitude"]) <= radius_m:
                anchor = c
                break
        if anchor is None:
            clusters.append(_new_cluster(r))
        else:
            _merge_into(anchor, r)
    for c in clusters:
        _finalize(c)
    return clusters


def _new_cluster(r: dict) -> dict:
    c = dict(r)
    c["sources"] = [r["source"]]
    # Keep whole rows, not just their connector lists: combining counts needs to
    # know which source each row came from and what it was called (see _finalize).
    c["_members"] = [r]
    return c


def _merge_into(c: dict, r: dict) -> None:
    if r["source"] not in c["sources"]:
        c["sources"].append(r["source"])
    for f in _DESC_FIELDS:
        if not c.get(f) and r.get(f):
            c[f] = r[f]
    c["_members"].append(r)


def _group_by_source(members: list[dict]) -> list[list[dict]]:
    """Partition members by source, preserving first-seen source order."""
    groups: dict = {}
    order: list = []
    for m in members:
        s = m.get("source")
        if s not in groups:
            groups[s] = []
            order.append(s)
        groups[s].append(m)
    return [groups[s] for s in order]


def _same_listing(x: dict, y: dict) -> bool:
    """`listing_identity.same_listing` with this cluster's corroborating facts.

    The distance and the two connector profiles are passed as corroboration
    only: they can lift a weak name match over the line, never create one, and
    never beat the name-based distinctness veto. See `listing_identity`.
    """
    return listing_identity.same_listing(
        x.get("name"), y.get("name"),
        distance_m=_haversine_m(x["latitude"], x["longitude"],
                                y["latitude"], y["longitude"]),
        connectors_a=x.get("connectors"),
        connectors_b=y.get("connectors"),
    )


def _distinct_listings(members: list[dict]) -> list[list[dict]]:
    """Split ONE source's rows in a cluster into groups of distinct hardware.

    Rows whose names pass `listing_identity.same_listing` are transitively joined
    into one listing (the same site imported twice); everything else stays apart
    (separate charger cabinets at one venue).

    The judgement is name-shape-driven and ordered: an enumerator or
    sub-location marker ("A"/"B", "Tower 1"/"Tower 2", "(B1)"/"(GF)", "Wing C",
    "Gudang", a different vendor brand) makes two rows DISTINCT and nothing can
    override it; only then do the duplicate detectors (containment, acronym,
    abbreviation, edit distance, token overlap) get to fire. Ambiguity resolves
    to DISTINCT, i.e. SUM -- over-counting is the accepted direction, summing a
    duplicate is not. `listing_identity` documents the evidence and the score
    against the 117-group hand-labelled audit.
    """
    n = len(members)
    if n < 2:
        return [list(members)]
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _same_listing(members[i], members[j]):
                parent[find(i)] = find(j)

    buckets: dict = {}
    order: list = []
    for i, m in enumerate(members):
        root = find(i)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        buckets[root].append(m)
    return [buckets[r] for r in order]


def _source_connectors(members: list[dict]) -> list[dict]:
    """Combine one source's rows: MAX inside a listing, SUM across listings."""
    listings = [connectors.merge_connectors([m.get("connectors") or [] for m in group])
                for group in _distinct_listings(members)]
    return connectors.sum_connectors(listings)


def _finalize(c: dict) -> None:
    # Counts combine at two levels, because the two situations are different:
    #   * WITHIN one source, two rows are either one listing imported twice (MAX,
    #     or we invent plugs) or two separate cabinets at one venue (SUM, or we
    #     silently drop plugs). `_distinct_listings` decides which.
    #   * ACROSS sources, two rows describe the same site seen twice, so MAX --
    #     the contract `connectors.merge_connectors` already documents.
    per_source = [_source_connectors(g) for g in _group_by_source(c.pop("_members"))]
    merged = connectors.merge_connectors(per_source)
    c["connectors"] = merged
    c.update(connectors.derive_station_fields(merged))

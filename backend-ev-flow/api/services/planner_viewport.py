"""Validation for the two untrusted inputs the planner map sends.

The layer name decides which column the heatmap is coloured by. A column name
cannot be a bound parameter, so it reaches SQL as text no matter how it is
handled; the only safe handling is to refuse to build it from user input at all
and look it up in a fixed table instead. METRIC_COLUMNS is that table.

The viewport decides how much of the grid is read. Every cell it covers becomes
a polygon in the response, so bounds are checked before the query runs rather
than left to the row limit to absorb.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict

#: Layer name as the map asks for it -> the column that carries it.
#: Values are bare identifiers on purpose. An expression here would be an
#: injection point wearing the costume of a lookup table, and a test enforces it.
METRIC_COLUMNS: Dict[str, str] = {
    "score": "score",
    "population": "population",
    "poi_total": "poi_total",
    "road_nodes": "road_nodes",
    "nearest_station_m": "nearest_station_m",
    "station_count": "station_count",
    "connector_count": "connector_count",
    "stations_2km": "stations_2km",
    "residential": "lu_residential_share",
    "commercial": "lu_commercial_share",
    "retail": "lu_retail_share",
    "industrial": "lu_industrial_share",
}


@dataclass(frozen=True)
class Viewport:
    """A map viewport in EPSG:4326, west/south/east/north."""
    west: float
    south: float
    east: float
    north: float


def metric_column(name: str) -> str:
    """Resolve a layer name to its column, or refuse.

    Refusing rather than falling back to a default matters: a typo that silently
    coloured the map by population while the legend said land use would look
    entirely plausible and be wrong everywhere.
    """
    try:
        return METRIC_COLUMNS[name]
    except KeyError:
        raise ValueError(
            f"unknown layer '{name}'; expected one of {', '.join(sorted(METRIC_COLUMNS))}"
        ) from None


def parse_bbox(raw: str) -> Viewport:
    """Parse 'minLon,minLat,maxLon,maxLat' into a checked viewport."""
    parts = [p.strip() for p in (raw or "").split(",")]
    if len(parts) != 4 or any(p == "" for p in parts):
        raise ValueError("bbox needs four comma separated values: minLon,minLat,maxLon,maxLat")

    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError:
        raise ValueError("every bbox value must be a number") from None

    # Before any comparison. NaN fails every comparison it takes part in, so an
    # inverted-viewport check would pass it through rather than catch it.
    for label, value in (("minLon", west), ("minLat", south),
                         ("maxLon", east), ("maxLat", north)):
        if not math.isfinite(value):
            raise ValueError(f"bbox value {label} must be finite, got {value}")

    for label, value in (("minLon", west), ("maxLon", east)):
        if not -180.0 <= value <= 180.0:
            raise ValueError(f"bbox longitude {label} must be between -180 and 180, got {value}")
    for label, value in (("minLat", south), ("maxLat", north)):
        if not -90.0 <= value <= 90.0:
            raise ValueError(f"bbox latitude {label} must be between -90 and 90, got {value}")

    if west >= east:
        raise ValueError(f"bbox west ({west}) must be less than east ({east})")
    if south >= north:
        raise ValueError(f"bbox south ({south}) must be less than north ({north})")

    return Viewport(west=west, south=south, east=east, north=north)

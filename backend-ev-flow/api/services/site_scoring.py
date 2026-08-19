"""Weights for the site suitability score (Epic 4).

The score is a weighted sum of four features, each first converted to its
percentile rank across the grid. Percentile rank rather than min-max scaling,
because the raw features are heavily skewed: population runs from 0 to about
10,700 with a median near 440, so min-max would flatten almost every cell against
the floor and let a handful of dense cells decide the map. Ranking spreads cells
evenly and makes a weight mean the same thing for every feature.

The weights are a planner-facing control, not a constant, which is what makes the
dashboard interactive. That also makes them untrusted input, so they are
validated here rather than interpolated into SQL and hoped for.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Dict

#: Feature -> the ordering used for its percentile rank in planner_repo.
#: Every key must appear in DEFAULT_WEIGHTS, and the test suite enforces that;
#: a feature scored in SQL but absent from the weights would be silently off.
SCORABLE_FEATURES = ("coverage", "population", "activity", "roads")


@dataclass(frozen=True)
class SiteWeights:
    """How much each signal counts. Relative size is what matters, not scale.

    The defaults lean on coverage and population: an underserved place with
    people in it is the ordinary case a planner is looking for, while activity
    and road access refine the ordering among candidates that already qualify.
    """
    coverage: float = 0.35
    population: float = 0.35
    activity: float = 0.20
    roads: float = 0.10


DEFAULT_WEIGHTS: Dict[str, float] = asdict(SiteWeights())


def normalised_weights(weights: SiteWeights) -> Dict[str, float]:
    """Validate and rescale to sum to 1.

    Rescaling keeps the resulting score inside 0..1 whatever magnitudes the
    planner types, so two scenarios remain comparable and the map's colour scale
    never has to be rebuilt between them.
    """
    raw = asdict(weights)

    for name, value in raw.items():
        if not math.isfinite(value):
            raise ValueError(f"weight '{name}' must be finite, got {value!r}")
        if value < 0:
            # A negative weight inverts the feature: the map would start
            # recommending places because they are already well served.
            raise ValueError(f"weight '{name}' must not be negative, got {value}")

    total = sum(raw.values())
    if total <= 0:
        # Every cell would score zero and the ranking would fall back to whatever
        # order the database returned, which is arbitrary but looks like a result.
        raise ValueError("at least one weight must be greater than zero")

    return {name: value / total for name, value in raw.items()}

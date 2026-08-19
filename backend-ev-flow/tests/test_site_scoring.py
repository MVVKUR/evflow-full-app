"""The planner sends the weights, so the weights are untrusted input.

A weight vector that silently misbehaves is worse than one that is rejected: the
map still renders, the ranking still looks authoritative, and nothing says the
numbers behind it were nonsense.
"""
import pytest

from api.services.site_scoring import (
    DEFAULT_WEIGHTS,
    SCORABLE_FEATURES,
    SiteWeights,
    normalised_weights,
)


def test_default_weights_cover_every_scorable_feature():
    # A feature present in the SQL but missing from the defaults would be scored
    # with an implicit zero, i.e. silently switched off.
    assert set(DEFAULT_WEIGHTS) == set(SCORABLE_FEATURES)


def test_weights_are_rescaled_to_sum_to_one():
    # Keeps the score inside 0..1 whatever magnitudes the planner types, so two
    # scenarios stay comparable and the colour scale never has to be rebuilt.
    w = normalised_weights(SiteWeights(coverage=2, population=2, activity=2, roads=2))
    assert pytest.approx(sum(w.values())) == 1.0
    assert all(pytest.approx(v) == 0.25 for v in w.values())


def test_relative_proportions_survive_rescaling():
    w = normalised_weights(SiteWeights(coverage=3, population=1, activity=0, roads=0))
    assert pytest.approx(w["coverage"]) == 0.75
    assert pytest.approx(w["population"]) == 0.25
    assert w["activity"] == 0.0


def test_a_single_feature_is_allowed():
    # "Rank purely by how underserved a place is" is a legitimate question.
    w = normalised_weights(SiteWeights(coverage=1, population=0, activity=0, roads=0))
    assert w["coverage"] == 1.0


def test_all_zero_weights_are_rejected():
    # Every cell would score 0 and the ranking would be database order, which is
    # arbitrary but looks exactly like a real answer.
    with pytest.raises(ValueError, match="at least one weight"):
        normalised_weights(SiteWeights(coverage=0, population=0, activity=0, roads=0))


def test_negative_weights_are_rejected():
    # A negative weight inverts a feature's meaning: the map would recommend
    # places BECAUSE they are already well served.
    with pytest.raises(ValueError, match="negative"):
        normalised_weights(SiteWeights(coverage=-1, population=1, activity=1, roads=1))


def test_non_finite_weights_are_rejected():
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite"):
            normalised_weights(SiteWeights(coverage=bad, population=1, activity=1, roads=1))


def test_defaults_are_normalised_already():
    assert pytest.approx(sum(normalised_weights(SiteWeights()).values())) == 1.0

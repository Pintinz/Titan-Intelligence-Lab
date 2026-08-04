from __future__ import annotations

import math

import pytest

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.infrastructure.predictors.poisson_score_predictor import (
    MissingExpectedGoalsFeatureError,
    PoissonScorePredictor,
    UnsupportedMarketKindError,
    _poisson_pmf,
)

HOME_KEY = "football.fixture.expected_home_goals"
AWAY_KEY = "football.fixture.expected_away_goals"


def test_poisson_pmf_matches_known_values():
    # P(X=0) for lambda=1 is e^-1
    assert _poisson_pmf(0, 1.0) == pytest.approx(math.exp(-1))
    # pmf sums to ~1 across a wide enough range for a small lambda
    total = sum(_poisson_pmf(k, 2.0) for k in range(30))
    assert total == pytest.approx(1.0, abs=1e-6)


@pytest.mark.asyncio
async def test_predicts_a_low_scoreline_for_low_expected_goals():
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 0.5, AWAY_KEY: 0.4}, mapping_weights={}
    )

    assert output.value == "0-0"
    assert 0.0 < output.probability < 1.0


@pytest.mark.asyncio
async def test_predicts_a_higher_scoreline_for_higher_expected_goals():
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 2.5, AWAY_KEY: 0.8}, mapping_weights={}
    )

    home_goals, away_goals = (int(x) for x in output.value.split("-"))
    assert home_goals > away_goals  # a much stronger home rate should favor a home-leaning score


@pytest.mark.asyncio
async def test_value_is_a_real_scoreline_string_not_a_raw_number():
    """The exact regression this predictor exists to fix — WeightedLinearPredictor used to emit
    e.g. "-0.3000" for this market, meaningless for a scoreline."""
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 1.2, AWAY_KEY: 1.1}, mapping_weights={}
    )

    home_goals, away_goals = output.value.split("-")
    assert home_goals.isdigit() and away_goals.isdigit()


@pytest.mark.asyncio
async def test_feature_contributions_report_both_lambdas():
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 1.8, AWAY_KEY: 0.9}, mapping_weights={}
    )

    assert output.feature_contributions[HOME_KEY] == pytest.approx(1.8)
    assert output.feature_contributions[AWAY_KEY] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_applies_mapping_weight_to_each_lambda():
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 2.0, AWAY_KEY: 2.0},
        mapping_weights={HOME_KEY: 0.5, AWAY_KEY: 1.5},
    )

    assert output.feature_contributions[HOME_KEY] == pytest.approx(1.0)
    assert output.feature_contributions[AWAY_KEY] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_rejects_unsupported_market_kind():
    predictor = PoissonScorePredictor()

    with pytest.raises(UnsupportedMarketKindError):
        await predictor.predict(MarketKind.BINARY, features={HOME_KEY: 1.0, AWAY_KEY: 1.0}, mapping_weights={})


@pytest.mark.asyncio
async def test_raises_when_a_required_feature_is_missing():
    predictor = PoissonScorePredictor()

    with pytest.raises(MissingExpectedGoalsFeatureError):
        await predictor.predict(MarketKind.CORRECT_SCORE, features={HOME_KEY: 1.0}, mapping_weights={})


@pytest.mark.asyncio
async def test_distribution_grid_matches_catalog_shape_and_sums_to_one():
    """Matches `market_outcome_registry._correct_score_grid(max_goals=5)` exactly: 36 scorelines
    (0-0 through 5-5) plus "OTHER" — every `Prediction.probability_distribution` key for a
    CORRECT_SCORE market must be one of the market's own real `allowed_values`."""
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 1.4, AWAY_KEY: 1.1}, mapping_weights={}
    )

    assert len(output.distribution) == 37
    assert "OTHER" in output.distribution
    for home in range(6):
        for away in range(6):
            assert f"{home}-{away}" in output.distribution
    assert sum(output.distribution.values()) == pytest.approx(1.0, abs=1e-6)
    assert all(probability >= 0.0 for probability in output.distribution.values())


@pytest.mark.asyncio
async def test_distribution_modal_scoreline_matches_value_for_low_lambdas():
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 0.5, AWAY_KEY: 0.4}, mapping_weights={}
    )

    assert output.value in output.distribution
    assert output.distribution[output.value] == pytest.approx(output.probability)


@pytest.mark.asyncio
async def test_distribution_other_bucket_grows_with_higher_expected_goals():
    predictor = PoissonScorePredictor()

    low = await predictor.predict(MarketKind.CORRECT_SCORE, features={HOME_KEY: 0.5, AWAY_KEY: 0.5}, mapping_weights={})
    high = await predictor.predict(MarketKind.CORRECT_SCORE, features={HOME_KEY: 4.0, AWAY_KEY: 4.0}, mapping_weights={})

    assert high.distribution["OTHER"] > low.distribution["OTHER"]


@pytest.mark.asyncio
async def test_zero_or_negative_expected_goals_does_not_crash():
    """A team with zero recorded goals scored (a real, if unlucky, historical average) must not
    blow up math.factorial/math.exp — floored to a tiny positive lambda instead of zero."""
    predictor = PoissonScorePredictor()

    output = await predictor.predict(
        MarketKind.CORRECT_SCORE, features={HOME_KEY: 0.0, AWAY_KEY: 0.0}, mapping_weights={}
    )

    assert output.value == "0-0"

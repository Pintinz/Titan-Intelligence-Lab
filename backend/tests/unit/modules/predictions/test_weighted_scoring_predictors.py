from __future__ import annotations

import pytest

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.infrastructure.predictors.weighted_scoring import (
    UnsupportedMarketKindError,
    WeightedLinearPredictor,
    WeightedLogisticPredictor,
)


@pytest.mark.asyncio
async def test_logistic_predictor_positive_score_is_positive_value():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(
        MarketKind.BINARY,
        features={"team_form": 0.8, "head_to_head": 0.5},
        mapping_weights={"team_form": 1.0, "head_to_head": 1.0},
    )

    assert output.raw_score == pytest.approx(1.3)
    assert output.value == "positive"
    assert 0.0 < output.probability < 1.0
    assert output.probability > 0.5
    assert output.feature_contributions == {"team_form": 0.8, "head_to_head": 0.5}


@pytest.mark.asyncio
async def test_logistic_predictor_negative_score_is_negative_value():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(
        MarketKind.SEGMENT_WINNER, features={"team_form": -1.5}, mapping_weights={"team_form": 1.0}
    )

    assert output.value == "negative"
    assert output.probability < 0.5


@pytest.mark.asyncio
async def test_logistic_predictor_zero_score_is_calibrated_to_half():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(MarketKind.BINARY, features={}, mapping_weights={})

    assert output.raw_score == 0.0
    assert output.probability == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_logistic_predictor_rejects_unsupported_market_kind():
    predictor = WeightedLogisticPredictor()

    with pytest.raises(UnsupportedMarketKindError):
        await predictor.predict(MarketKind.TOTAL, features={}, mapping_weights={})


@pytest.mark.asyncio
async def test_logistic_predictor_applies_mapping_weight():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(
        MarketKind.BINARY, features={"team_form": 2.0}, mapping_weights={"team_form": 0.5}
    )

    assert output.raw_score == pytest.approx(1.0)
    assert output.feature_contributions == {"team_form": 1.0}


@pytest.mark.asyncio
async def test_linear_predictor_raw_score_is_predicted_value():
    predictor = WeightedLinearPredictor()

    output = await predictor.predict(
        MarketKind.PLAYER_PROP, features={"points_per_game_avg": 24.5, "pace_adjustment": 1.5}, mapping_weights={}
    )

    assert output.raw_score == pytest.approx(26.0)
    assert output.value == "26.0000"


@pytest.mark.asyncio
async def test_linear_predictor_supports_total_spread_team_total_race_to_correct_score():
    predictor = WeightedLinearPredictor()

    for kind in (
        MarketKind.SPREAD,
        MarketKind.TOTAL,
        MarketKind.TEAM_TOTAL,
        MarketKind.RACE_TO,
        MarketKind.CORRECT_SCORE,
    ):
        output = await predictor.predict(kind, features={"x": 1.0}, mapping_weights={"x": 2.0})
        assert output.raw_score == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_linear_predictor_rejects_unsupported_market_kind():
    predictor = WeightedLinearPredictor()

    with pytest.raises(UnsupportedMarketKindError):
        await predictor.predict(MarketKind.BINARY, features={}, mapping_weights={})

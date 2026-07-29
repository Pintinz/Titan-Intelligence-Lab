from __future__ import annotations

import pytest

from modules.predictions.application.predictor_registry import NoPredictorRegisteredError, PredictorRegistry
from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.infrastructure.predictors.weighted_scoring import (
    WeightedLinearPredictor,
    WeightedLogisticPredictor,
)


def test_get_unregistered_kind_raises():
    registry = PredictorRegistry()

    with pytest.raises(NoPredictorRegisteredError):
        registry.get(MarketKind.BINARY)


def test_register_many_binds_every_kind():
    registry = PredictorRegistry()
    logistic = WeightedLogisticPredictor()

    registry.register_many(WeightedLogisticPredictor.SUPPORTED_KINDS, logistic)

    assert registry.get(MarketKind.BINARY) is logistic
    assert registry.get(MarketKind.SEGMENT_WINNER) is logistic


def test_register_binds_a_single_kind():
    registry = PredictorRegistry()
    linear = WeightedLinearPredictor()

    registry.register(MarketKind.TOTAL, linear)

    assert registry.get(MarketKind.TOTAL) is linear


def test_two_predictors_cover_disjoint_kinds():
    registry = PredictorRegistry()
    logistic = WeightedLogisticPredictor()
    linear = WeightedLinearPredictor()

    registry.register_many(WeightedLogisticPredictor.SUPPORTED_KINDS, logistic)
    registry.register_many(WeightedLinearPredictor.SUPPORTED_KINDS, linear)

    assert registry.get(MarketKind.BINARY) is logistic
    assert registry.get(MarketKind.PLAYER_PROP) is linear


def test_market_specific_predictor_takes_precedence_over_kind_default():
    registry = PredictorRegistry()
    fallback = WeightedLogisticPredictor()
    champion = WeightedLogisticPredictor()

    registry.register(MarketKind.BINARY, fallback)
    registry.register_for_market("football.match_result", champion)

    assert registry.get(MarketKind.BINARY, "football.match_result") is champion
    assert registry.get(MarketKind.BINARY, "basketball.match_winner") is fallback
    assert registry.get(MarketKind.BINARY) is fallback


def test_market_key_none_uses_kind_default_only():
    registry = PredictorRegistry()
    fallback = WeightedLogisticPredictor()
    registry.register(MarketKind.BINARY, fallback)
    registry.register_for_market("football.match_result", WeightedLogisticPredictor())

    assert registry.get(MarketKind.BINARY, market_key=None) is fallback


def test_unregistered_market_key_falls_back_to_kind_default_not_error():
    registry = PredictorRegistry()
    fallback = WeightedLogisticPredictor()
    registry.register(MarketKind.BINARY, fallback)

    assert registry.get(MarketKind.BINARY, "some.unregistered.market") is fallback

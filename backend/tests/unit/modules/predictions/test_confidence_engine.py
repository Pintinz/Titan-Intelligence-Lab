from __future__ import annotations

import pytest

from modules.predictions.application.confidence_engine import (
    ConfidenceEngine,
    ConfidenceInputs,
    FeatureConfidenceInput,
)


def _inputs(**overrides) -> ConfidenceInputs:
    defaults = dict(
        features=(
            FeatureConfidenceInput(feature_key="a", quality_score=0.8, freshness_score=0.9, is_present=True),
            FeatureConfidenceInput(feature_key="b", quality_score=0.6, freshness_score=0.7, is_present=True),
        ),
        historical_accuracy=0.7,
        knowledge_graph_completeness=0.5,
        news_reliability=0.6,
        community_reliability=0.4,
        model_reliability=0.75,
        prediction_stability=0.85,
    )
    defaults.update(overrides)
    return ConfidenceInputs(**defaults)


def test_feature_quality_and_freshness_are_averaged_across_features():
    engine = ConfidenceEngine()

    breakdown = engine.compute(_inputs())

    assert breakdown.feature_quality == pytest.approx(0.7)
    assert breakdown.feature_freshness == pytest.approx(0.8)


def test_data_completeness_is_presence_ratio():
    engine = ConfidenceEngine()
    inputs = _inputs(
        features=(
            FeatureConfidenceInput(feature_key="a", quality_score=0.8, freshness_score=0.9, is_present=True),
            FeatureConfidenceInput(feature_key="b", quality_score=0.0, freshness_score=0.0, is_present=False),
        )
    )

    breakdown = engine.compute(inputs)

    assert breakdown.data_completeness == pytest.approx(0.5)


def test_pass_through_factors_are_preserved():
    engine = ConfidenceEngine()

    breakdown = engine.compute(_inputs())

    assert breakdown.historical_accuracy == pytest.approx(0.7)
    assert breakdown.knowledge_graph_completeness == pytest.approx(0.5)
    assert breakdown.news_reliability == pytest.approx(0.6)
    assert breakdown.community_reliability == pytest.approx(0.4)
    assert breakdown.model_reliability == pytest.approx(0.75)
    assert breakdown.prediction_stability == pytest.approx(0.85)


def test_no_features_at_all_yields_zero_not_a_default_midpoint():
    engine = ConfidenceEngine()
    inputs = _inputs(features=())

    breakdown = engine.compute(inputs)

    assert breakdown.feature_quality == 0.0
    assert breakdown.feature_freshness == 0.0
    assert breakdown.data_completeness == 0.0


def test_out_of_range_pass_through_values_are_clamped():
    engine = ConfidenceEngine()
    inputs = _inputs(historical_accuracy=1.5, model_reliability=-0.3)

    breakdown = engine.compute(inputs)

    assert breakdown.historical_accuracy == 1.0
    assert breakdown.model_reliability == 0.0


def test_composite_reflects_all_nine_factors():
    engine = ConfidenceEngine()

    breakdown = engine.compute(_inputs())

    manual_mean = (
        breakdown.feature_quality
        + breakdown.feature_freshness
        + breakdown.historical_accuracy
        + breakdown.knowledge_graph_completeness
        + breakdown.news_reliability
        + breakdown.community_reliability
        + breakdown.data_completeness
        + breakdown.model_reliability
        + breakdown.prediction_stability
    ) / 9
    assert breakdown.composite == pytest.approx(manual_mean)

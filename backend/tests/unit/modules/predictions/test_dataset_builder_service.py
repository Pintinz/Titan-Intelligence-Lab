from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.dataset_builder_service import DatasetBuilder, MarketNotFoundError
from modules.predictions.domain.dataset import DatasetQualityIssue, DatasetStatus
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


async def _market(market_repo, target_type=TargetType.CLASSIFICATION, market_kind=MarketKind.BINARY):
    market = MarketDefinition(
        id=MarketId(uuid4()),
        market_key="football.dataset_market",
        sport_code="football",
        name="Test",
        category="match_outcome",
        market_kind=market_kind,
        target_type=target_type,
        status=MarketStatus.PRODUCTION,
    )
    return await market_repo.upsert(market)


def _prediction(market_id, feature_snapshot, value="positive"):
    return Prediction(
        id=PredictionId(uuid4()),
        market_id=market_id,
        model_id=ModelId(uuid4()),
        subject_ref="fixture-1",
        value=value,
        probability=0.6,
        confidence=ConfidenceBreakdown(*([0.7] * 9)),
        explanation=ExplanationBundle(),
        feature_snapshot=feature_snapshot,
        model_version="1",
        status=PredictionStatus.PUBLISHED,
        generated_at=T0,
    )


@pytest.fixture
def builder(market_repo, prediction_repo, prediction_outcome_repo):
    return DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo)


async def _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n, actual_value_fn):
    for i in range(n):
        prediction = await prediction_repo.record(
            _prediction(market.id, {"feature_a": float(i), "feature_b": float(i) * 2})
        )
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()),
                prediction_id=prediction.id,
                actual_value=actual_value_fn(i),
                error=0.0,
                evaluated_at=T0,
            )
        )


async def test_build_produces_dataset_with_samples_and_lineage(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, 40, lambda i: "positive" if i % 2 == 0 else "negative")

    dataset = await builder.build(market.id, now=T0)

    assert dataset.market_id == market.id
    assert dataset.version == 1
    assert dataset.status is DatasetStatus.DRAFT
    assert dataset.statistics.sample_count == 40
    assert dataset.statistics.feature_count == 2
    assert dataset.lineage.market_id == market.id
    assert len(dataset.lineage.source_prediction_ids) == 40
    assert set(dataset.lineage.feature_keys) == {"feature_a", "feature_b"}


async def test_classification_label_uses_positive_negative_convention(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, 30, lambda i: "positive" if i < 15 else "negative")

    dataset = await builder.build(market.id, now=T0)

    labels = [s.label for s in dataset.samples]
    assert labels.count(1.0) == 15
    assert labels.count(0.0) == 15
    assert dataset.statistics.positive_rate == pytest.approx(0.5)


async def test_regression_label_parses_actual_value_as_float(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo, target_type=TargetType.REGRESSION, market_kind=MarketKind.TOTAL)
    await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, 35, lambda i: f"{float(i) * 1.5:.4f}")

    dataset = await builder.build(market.id, now=T0)

    assert dataset.statistics.positive_rate is None
    assert dataset.samples[0].label == pytest.approx(0.0)


async def test_too_few_samples_flagged_as_quality_issue(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, 5, lambda i: "positive")

    dataset = await builder.build(market.id, now=T0)

    assert DatasetQualityIssue.TOO_FEW_SAMPLES in dataset.quality_issues
    assert not dataset.is_usable_for_training()


async def test_severe_class_imbalance_flagged(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, 40, lambda i: "positive" if i < 38 else "negative")

    dataset = await builder.build(market.id, now=T0)

    assert DatasetQualityIssue.SEVERE_CLASS_IMBALANCE in dataset.quality_issues


async def test_content_hash_is_reproducible_for_identical_data(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, 30, lambda i: "positive" if i % 2 == 0 else "negative")

    dataset_a = await builder.build(market.id, now=T0)
    dataset_b = await builder.build(market.id, now=T0)

    assert dataset_a.content_hash == dataset_b.content_hash


async def test_build_raises_for_unknown_market(builder):
    with pytest.raises(MarketNotFoundError):
        await builder.build(MarketId(uuid4()), now=T0)

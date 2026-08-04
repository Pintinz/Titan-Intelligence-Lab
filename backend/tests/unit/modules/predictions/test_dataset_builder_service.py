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

# A market this module's outcome_label_mapper.MARKET_OUTCOME_LABELS actually recognizes — the
# dataset builder recovers a classification label via real_label_is_positive(market_key, ...), so
# an unrecognized synthetic market_key would make every sample unresolvable (see the dedicated
# unresolvable-market test below for that behavior on purpose).
CLASSIFICATION_MARKET_KEY = "football.both_teams_to_score"


async def _market(market_repo, target_type=TargetType.CLASSIFICATION, market_kind=MarketKind.BINARY, market_key=None):
    market = MarketDefinition(
        id=MarketId(uuid4()),
        market_key=market_key or (CLASSIFICATION_MARKET_KEY if target_type is TargetType.CLASSIFICATION else "football.dataset_regression_market"),
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


async def _seed_classification_outcomes(market, prediction_repo, prediction_outcome_repo, n, error_fn):
    """Every prediction claims "positive" (real_label_is_positive resolves this to True via the
    legacy-generic-value fallback). `error_fn(i)` (0.0 or 1.0) then determines the recovered real
    training label: error=0.0 -> the claim matched -> label 1.0; error=1.0 -> it didn't -> label 0.0.
    `actual_value` is set to a real BTTS fact for realism but is never itself read for the label."""
    for i in range(n):
        prediction = await prediction_repo.record(
            _prediction(market.id, {"feature_a": float(i), "feature_b": float(i) * 2}, value="positive")
        )
        error = error_fn(i)
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()),
                prediction_id=prediction.id,
                actual_value="btts_yes" if error == 0.0 else "btts_no",
                error=error,
                evaluated_at=T0,
            )
        )


async def _seed_regression_outcomes(market, prediction_repo, prediction_outcome_repo, n, actual_value_fn):
    for i in range(n):
        prediction = await prediction_repo.record(
            _prediction(market.id, {"feature_a": float(i), "feature_b": float(i) * 2}, value=f"{float(i):.4f}")
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
    await _seed_classification_outcomes(market, prediction_repo, prediction_outcome_repo, 40, lambda i: 0.0 if i % 2 == 0 else 1.0)

    dataset = await builder.build(market.id, now=T0)

    assert dataset.market_id == market.id
    assert dataset.version == 1
    assert dataset.status is DatasetStatus.DRAFT
    assert dataset.statistics.sample_count == 40
    assert dataset.statistics.feature_count == 2
    assert dataset.lineage.market_id == market.id
    assert len(dataset.lineage.source_prediction_ids) == 40
    assert set(dataset.lineage.feature_keys) == {"feature_a", "feature_b"}


async def test_classification_label_recovers_real_polarity_from_prediction_value_and_error(
    builder, market_repo, prediction_repo, prediction_outcome_repo
):
    """The real bug this guards against: PredictionOutcome.actual_value is a fact string like
    "btts_yes", never literally "positive"/"negative" — the label must come from whether the
    prediction's own claim (real_label_is_positive) matched the real outcome (error), not from
    string-matching actual_value directly."""
    market = await _market(market_repo)
    await _seed_classification_outcomes(market, prediction_repo, prediction_outcome_repo, 30, lambda i: 0.0 if i < 15 else 1.0)

    dataset = await builder.build(market.id, now=T0)

    labels = [s.label for s in dataset.samples]
    assert labels.count(1.0) == 15
    assert labels.count(0.0) == 15
    assert dataset.statistics.positive_rate == pytest.approx(0.5)


async def test_unresolvable_market_skips_samples_instead_of_mislabeling(
    builder, market_repo, prediction_repo, prediction_outcome_repo
):
    """A CLASSIFICATION market with no binary-polarity mapping (e.g. a 3-way market, or any
    market_key outcome_label_mapper doesn't cover) must never silently mislabel every sample as
    negative — every outcome is skipped instead, and the resulting dataset is correctly flagged
    as not usable for training rather than looking deceptively "built"."""
    market = await _market(market_repo, market_key="football.match_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
    for i in range(30):
        prediction = await prediction_repo.record(
            _prediction(market.id, {"feature_a": float(i)}, value="HOME_WIN")
        )
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                actual_value="HOME_WIN", error=0.0, evaluated_at=T0,
            )
        )

    dataset = await builder.build(market.id, now=T0)

    assert dataset.samples == []
    assert dataset.statistics.sample_count == 0
    assert DatasetQualityIssue.TOO_FEW_SAMPLES in dataset.quality_issues


async def test_regression_label_parses_actual_value_as_float(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo, target_type=TargetType.REGRESSION, market_kind=MarketKind.TOTAL)
    await _seed_regression_outcomes(market, prediction_repo, prediction_outcome_repo, 35, lambda i: f"{float(i) * 1.5:.4f}")

    dataset = await builder.build(market.id, now=T0)

    assert dataset.statistics.positive_rate is None
    assert dataset.samples[0].label == pytest.approx(0.0)


async def test_too_few_samples_flagged_as_quality_issue(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_classification_outcomes(market, prediction_repo, prediction_outcome_repo, 5, lambda i: 0.0)

    dataset = await builder.build(market.id, now=T0)

    assert DatasetQualityIssue.TOO_FEW_SAMPLES in dataset.quality_issues
    assert not dataset.is_usable_for_training()


async def test_severe_class_imbalance_flagged(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_classification_outcomes(market, prediction_repo, prediction_outcome_repo, 40, lambda i: 0.0 if i < 38 else 1.0)

    dataset = await builder.build(market.id, now=T0)

    assert DatasetQualityIssue.SEVERE_CLASS_IMBALANCE in dataset.quality_issues


async def test_content_hash_is_reproducible_for_identical_data(builder, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo)
    await _seed_classification_outcomes(market, prediction_repo, prediction_outcome_repo, 30, lambda i: 0.0 if i % 2 == 0 else 1.0)

    dataset_a = await builder.build(market.id, now=T0)
    dataset_b = await builder.build(market.id, now=T0)

    assert dataset_a.content_hash == dataset_b.content_hash


async def test_build_raises_for_unknown_market(builder):
    with pytest.raises(MarketNotFoundError):
        await builder.build(MarketId(uuid4()), now=T0)

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.dataset_builder_service import MarketNotFoundError
from modules.predictions.application.error_memory_service import ErrorMemoryService
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    ModelDefinition,
    ModelEvaluation,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelEvaluationId,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)

T0 = datetime(2026, 8, 8, tzinfo=timezone.utc)
CONFIDENCE = ConfidenceBreakdown(*([0.7] * 9))


def _market(market_key="football.both_teams_to_score", target_type=TargetType.CLASSIFICATION) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=market_key, sport_code="football", name="Test",
        category="goals", market_kind=MarketKind.BINARY, target_type=target_type, status=MarketStatus.PRODUCTION,
    )


async def _record_prediction_outcome(
    prediction_repo, outcome_repo, market_id, value: str, probability: float, error: float,
    feature_snapshot: dict, model_id=None,
):
    prediction = Prediction(
        id=PredictionId(uuid4()), market_id=market_id, model_id=model_id or ModelId(uuid4()),
        subject_ref=f"fx-{uuid4()}", value=value, probability=probability, confidence=CONFIDENCE,
        explanation=ExplanationBundle(), feature_snapshot=feature_snapshot, model_version="1",
        status=PredictionStatus.PUBLISHED, generated_at=T0,
    )
    await prediction_repo.record(prediction)
    await outcome_repo.record(
        PredictionOutcome(
            id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
            actual_value="btts_yes" if error == 0.0 else "btts_no", error=error, evaluated_at=T0,
        )
    )
    return prediction


@dataclass
class _MarketAwarePredictionOutcomeRepository:
    """The shared `conftest.py` `InMemoryPredictionOutcomeRepository.list_by_market` doesn't
    actually filter by market (returns every outcome regardless) — a gap that's never mattered to
    any single-market test elsewhere in this directory, but does here, where multi-market
    isolation is exactly what's under test. Overrides `prediction_outcome_repo` locally rather
    than touching the shared fake other tests depend on."""

    predictions: object
    store: list = field(default_factory=list)

    async def record(self, outcome):
        self.store.append(outcome)
        return outcome

    async def get_for_prediction(self, prediction_id):
        return next((o for o in self.store if o.prediction_id == prediction_id), None)

    async def list_by_market(self, market_id, limit=500):
        matches = []
        for outcome in self.store:
            prediction = await self.predictions.get(outcome.prediction_id)
            if prediction is not None and prediction.market_id == market_id:
                matches.append(outcome)
        return matches[:limit]


@pytest.fixture
def prediction_outcome_repo(prediction_repo):
    return _MarketAwarePredictionOutcomeRepository(predictions=prediction_repo)


@pytest.fixture
def service(market_repo, model_repo, prediction_repo, prediction_outcome_repo, model_evaluation_repo):
    return ErrorMemoryService(
        markets=market_repo, models=model_repo, predictions=prediction_repo,
        outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
    )


class TestMarketPerformanceRanking:
    async def test_ranks_higher_accuracy_market_first(self, service, market_repo, prediction_repo, prediction_outcome_repo):
        good_market = await market_repo.upsert(_market("football.both_teams_to_score"))
        bad_market = await market_repo.upsert(_market("football.correct_score"))

        for i in range(10):
            await _record_prediction_outcome(
                prediction_repo, prediction_outcome_repo, good_market.id, "YES", 0.7,
                error=0.0 if i < 9 else 1.0, feature_snapshot={"x": float(i)},
            )
        for i in range(10):
            await _record_prediction_outcome(
                prediction_repo, prediction_outcome_repo, bad_market.id, "YES", 0.7,
                error=0.0 if i < 2 else 1.0, feature_snapshot={"x": float(i)},
            )

        ranking = await service.market_performance_ranking()

        assert ranking[0].market_key == "football.both_teams_to_score"
        assert ranking[0].accuracy == pytest.approx(0.9)
        assert ranking[-1].market_key == "football.correct_score"
        assert ranking[-1].accuracy == pytest.approx(0.2)

    async def test_market_with_no_outcomes_has_none_metrics(self, service, market_repo):
        await market_repo.upsert(_market("football.no_data_market"))

        ranking = await service.market_performance_ranking()

        summary = next(s for s in ranking if s.market_key == "football.no_data_market")
        assert summary.sample_count == 0
        assert summary.mean_error is None
        assert summary.accuracy is None

    async def test_filters_by_sport_code(self, service, market_repo):
        await market_repo.upsert(_market("football.both_teams_to_score"))

        ranking = await service.market_performance_ranking(sport_code="basketball")

        assert ranking == []


class TestFeatureFailureAssociation:
    async def test_finds_the_feature_that_diverges_between_correct_and_incorrect(
        self, service, market_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())

        # "suspicious_feature" is high (90+) whenever the prediction was wrong, low (0-9) when right.
        for i in range(10):
            await _record_prediction_outcome(
                prediction_repo, prediction_outcome_repo, market.id, "YES", 0.7, error=0.0,
                feature_snapshot={"suspicious_feature": float(i), "stable_feature": 5.0},
            )
        for i in range(10):
            await _record_prediction_outcome(
                prediction_repo, prediction_outcome_repo, market.id, "YES", 0.7, error=1.0,
                feature_snapshot={"suspicious_feature": float(90 + i), "stable_feature": 5.0},
            )

        associations = await service.feature_failure_association(market.id)

        top = associations[0]
        assert top.feature_key == "suspicious_feature"
        assert top.correct_mean == pytest.approx(4.5)
        assert top.incorrect_mean == pytest.approx(94.5)
        assert top.divergence == pytest.approx(90.0)

        stable = next(a for a in associations if a.feature_key == "stable_feature")
        assert stable.divergence == pytest.approx(0.0)

    async def test_no_outcomes_returns_empty_list(self, service, market_repo):
        market = await market_repo.upsert(_market("football.empty_market"))

        assert await service.feature_failure_association(market.id) == []

    async def test_regression_market_normalizes_raw_magnitude_error_before_bucketing(
        self, service, market_repo, prediction_repo, prediction_outcome_repo
    ):
        """Phase 6 fix (2026-08-25): a regression market's `PredictionOutcome.error` is a raw
        magnitude (e.g. 8 points off a ~220-point total), never bounded to [0, 1]. Before the fix,
        the raw `error < 0.5` check would bucket EVERY regression outcome as "incorrect"
        regardless of how good the prediction actually was, making this analysis meaningless for
        regression markets. A tight relative miss (8/220) must land in `correct`, a huge one
        (150/220) in `incorrect` — proving the bucketing is now relative-error-aware."""
        market = await market_repo.upsert(_market("basketball.points_regression_market", target_type=TargetType.REGRESSION))

        for i in range(10):
            prediction = Prediction(
                id=PredictionId(uuid4()), market_id=market.id, model_id=ModelId(uuid4()),
                subject_ref=f"fx-tight-{uuid4()}", value="212.0", probability=0.7, confidence=CONFIDENCE,
                explanation=ExplanationBundle(), feature_snapshot={"suspicious_feature": float(i), "stable_feature": 5.0},
                model_version="1", status=PredictionStatus.PUBLISHED, generated_at=T0,
            )
            await prediction_repo.record(prediction)
            await prediction_outcome_repo.record(
                PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                    actual_value="220.0", error=8.0, evaluated_at=T0,  # tight: 8/220 ≈ 3.6%
                )
            )
        for i in range(10):
            prediction = Prediction(
                id=PredictionId(uuid4()), market_id=market.id, model_id=ModelId(uuid4()),
                subject_ref=f"fx-wild-{uuid4()}", value="70.0", probability=0.7, confidence=CONFIDENCE,
                explanation=ExplanationBundle(), feature_snapshot={"suspicious_feature": float(90 + i), "stable_feature": 5.0},
                model_version="1", status=PredictionStatus.PUBLISHED, generated_at=T0,
            )
            await prediction_repo.record(prediction)
            await prediction_outcome_repo.record(
                PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                    actual_value="220.0", error=150.0, evaluated_at=T0,  # wild: 150/220 ≈ 68%
                )
            )

        associations = await service.feature_failure_association(market.id)

        top = associations[0]
        assert top.feature_key == "suspicious_feature"
        assert top.correct_mean == pytest.approx(4.5)
        assert top.incorrect_mean == pytest.approx(94.5)


class TestOverconfidenceSummary:
    async def test_detects_systematic_overconfidence(self, service, market_repo, prediction_repo, prediction_outcome_repo):
        market = await market_repo.upsert(_market())

        # Stated probability 0.9 every time, but only right half the time -> badly overconfident.
        for i in range(10):
            await _record_prediction_outcome(
                prediction_repo, prediction_outcome_repo, market.id, "YES", 0.9,
                error=0.0 if i < 5 else 1.0, feature_snapshot={"x": 1.0},
            )

        summary = await service.overconfidence_summary(market.id, now=T0)

        assert summary.sample_count == 10
        assert summary.mean_predicted_probability == pytest.approx(0.9)
        assert summary.mean_actual_positive_rate == pytest.approx(0.5)
        assert summary.overconfidence_score == pytest.approx(0.4)
        assert summary.expected_calibration_error is not None and summary.expected_calibration_error > 0

    async def test_unknown_market_raises(self, service):
        with pytest.raises(MarketNotFoundError):
            await service.overconfidence_summary(MarketId(uuid4()), now=T0)

    async def test_no_outcomes_returns_honest_empty_summary(self, service, market_repo):
        market = await market_repo.upsert(_market("football.empty_market2"))

        summary = await service.overconfidence_summary(market.id, now=T0)

        assert summary.sample_count == 0
        assert summary.overconfidence_score is None


class TestModelVersionRanking:
    async def test_ranks_newest_version_first_with_its_latest_evaluation(
        self, service, market_repo, model_repo, model_evaluation_repo
    ):
        market = await market_repo.upsert(_market())
        v1 = await model_repo.upsert(
            ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m", version=1, algorithm="a", status=ModelStatus.RETIRED)
        )
        v2 = await model_repo.upsert(
            ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m", version=2, algorithm="a", status=ModelStatus.CHAMPION)
        )
        await model_evaluation_repo.record(
            ModelEvaluation(id=ModelEvaluationId(uuid4()), model_id=v2.id, evaluated_at=T0, metrics={"accuracy": 0.8})
        )

        ranking = await service.model_version_ranking(market.id)

        assert [s.version for s in ranking] == [2, 1]
        assert ranking[0].latest_metrics == {"accuracy": 0.8}
        assert ranking[1].latest_metrics is None

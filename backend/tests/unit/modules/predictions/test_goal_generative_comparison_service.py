"""Goal-Generative vs Direct-Classifier Comparison (spec §9) — `GoalGenerativeComparisonService`
tests, using real held-out outcome history (not a fresh training run) to compare the derived
Poisson baseline against a market's direct-classifier Champion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.goal_generative_comparison_service import (
    GoalGenerativeComparisonService,
    MarketNotEligibleError,
)
from modules.predictions.domain.contextual_reasoning import StatisticalBaseline
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    ModelDefinition,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    MarketId,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
)

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _champion(market_id) -> ModelDefinition:
    return ModelDefinition(
        id=ModelId(uuid4()), market_id=market_id, model_key="football.match_winner.logistic_regression",
        version=3, algorithm="logistic_regression", status=ModelStatus.CHAMPION, framework="sklearn",
        artifact_ref="real-artifact-ref",
    )


def _prediction(market_id, model_id, value, probability_distribution) -> Prediction:
    return Prediction(
        id=PredictionId(uuid4()), market_id=market_id, model_id=model_id, subject_ref=f"fixture-{uuid4()}",
        value=value, probability=probability_distribution[value], confidence=ConfidenceBreakdown(*([0.7] * 9)),
        explanation=ExplanationBundle(), feature_snapshot={"a": 1.0}, model_version="3",
        status=PredictionStatus.PUBLISHED, probability_distribution=probability_distribution, generated_at=T0,
    )


def _outcome(prediction_id, actual_value) -> PredictionOutcome:
    return PredictionOutcome(
        id=PredictionOutcomeId(uuid4()), prediction_id=prediction_id, actual_value=actual_value, error=0.0,
        evaluated_at=T0,
    )


@dataclass
class _FakeBaselineProvider:
    """Returns a fixed baseline distribution regardless of features — real enough for these
    tests, which only need the derived side of the comparison to be a real, distinct number from
    the classifier side."""

    probabilities: dict | None
    applicable: bool = True
    available: bool = True

    async def get(self, market_id, market_key, features):
        return StatisticalBaseline(
            applicable=self.applicable, available=self.available,
            algorithm="poisson_goals_model", probabilities=self.probabilities,
        )


def _service(model_repo, prediction_repo, outcome_repo, experiment_repo, baseline_probabilities, min_samples=3):
    return GoalGenerativeComparisonService(
        models=model_repo, predictions=prediction_repo, outcomes=outcome_repo,
        baseline_provider=_FakeBaselineProvider(baseline_probabilities), experiments=experiment_repo,
        min_samples=min_samples,
    )


@pytest.mark.asyncio
async def test_ineligible_market_raises():
    service = GoalGenerativeComparisonService(
        models=None, predictions=None, outcomes=None,
        baseline_provider=_FakeBaselineProvider({}), experiments=None,
    )
    with pytest.raises(MarketNotEligibleError):
        await service.compare(MarketId(uuid4()), "football.correct_score", T0)


@pytest.mark.asyncio
async def test_no_champion_returns_honest_zero(model_repo, prediction_repo, prediction_outcome_repo, experiment_repo):
    market_id = MarketId(uuid4())
    service = _service(model_repo, prediction_repo, prediction_outcome_repo, experiment_repo, {"HOME_WIN": 0.5})

    result = await service.compare(market_id, "football.match_winner", T0)

    assert result.sample_count == 0
    assert result.goal_generative_wins is None
    assert result.reason == "no champion model"


@pytest.mark.asyncio
async def test_classifier_wins_when_it_assigns_higher_probability_to_real_outcomes(
    model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
):
    market_id = MarketId(uuid4())
    champion = await model_repo.upsert(_champion(market_id))

    # The classifier confidently and correctly calls HOME_WIN every time (0.8); the baseline is
    # muted (0.4) on the same real outcome — classifier must win this comparison.
    for _ in range(5):
        prediction = await prediction_repo.record(
            _prediction(market_id, champion.id, "HOME_WIN", {"HOME_WIN": 0.8, "DRAW": 0.1, "AWAY_WIN": 0.1})
        )
        await prediction_outcome_repo.record(_outcome(prediction.id, "HOME_WIN"))

    service = _service(
        model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
        baseline_probabilities={"HOME_WIN": 0.4, "DRAW": 0.3, "AWAY_WIN": 0.3},
    )

    result = await service.compare(market_id, "football.match_winner", T0)

    assert result.sample_count == 5
    assert result.classifier_log_loss < result.goal_generative_log_loss
    assert result.goal_generative_wins is False
    assert len(experiment_repo.store) == 1
    experiment = next(iter(experiment_repo.store.values()))
    assert experiment.config["kind"] == "goal_generative_vs_classifier"
    assert experiment.metrics["classifier_log_loss"] == result.classifier_log_loss


@pytest.mark.asyncio
async def test_goal_generative_wins_when_it_assigns_higher_probability_to_real_outcomes(
    model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
):
    market_id = MarketId(uuid4())
    champion = await model_repo.upsert(_champion(market_id))

    for _ in range(5):
        prediction = await prediction_repo.record(
            _prediction(market_id, champion.id, "HOME_WIN", {"HOME_WIN": 0.3, "DRAW": 0.3, "AWAY_WIN": 0.4})
        )
        await prediction_outcome_repo.record(_outcome(prediction.id, "HOME_WIN"))

    service = _service(
        model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
        baseline_probabilities={"HOME_WIN": 0.7, "DRAW": 0.15, "AWAY_WIN": 0.15},
    )

    result = await service.compare(market_id, "football.match_winner", T0)

    assert result.goal_generative_log_loss < result.classifier_log_loss
    assert result.goal_generative_wins is True


@pytest.mark.asyncio
async def test_below_min_samples_returns_honest_reason_without_persisting_experiment(
    model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
):
    market_id = MarketId(uuid4())
    champion = await model_repo.upsert(_champion(market_id))
    prediction = await prediction_repo.record(
        _prediction(market_id, champion.id, "HOME_WIN", {"HOME_WIN": 0.6, "DRAW": 0.2, "AWAY_WIN": 0.2})
    )
    await prediction_outcome_repo.record(_outcome(prediction.id, "HOME_WIN"))

    service = _service(
        model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
        baseline_probabilities={"HOME_WIN": 0.5, "DRAW": 0.25, "AWAY_WIN": 0.25}, min_samples=20,
    )

    result = await service.compare(market_id, "football.match_winner", T0)

    assert result.sample_count == 1
    assert result.goal_generative_wins is None
    assert "fewer than 20" in result.reason
    assert len(experiment_repo.store) == 0


@pytest.mark.asyncio
async def test_baseline_unavailable_skips_sample_and_reports_honest_zero(
    model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
):
    market_id = MarketId(uuid4())
    champion = await model_repo.upsert(_champion(market_id))
    prediction = await prediction_repo.record(
        _prediction(market_id, champion.id, "HOME_WIN", {"HOME_WIN": 0.6, "DRAW": 0.2, "AWAY_WIN": 0.2})
    )
    await prediction_outcome_repo.record(_outcome(prediction.id, "HOME_WIN"))

    service = GoalGenerativeComparisonService(
        models=model_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo,
        baseline_provider=_FakeBaselineProvider(None, available=False), experiments=experiment_repo, min_samples=1,
    )

    result = await service.compare(market_id, "football.match_winner", T0)

    assert result.sample_count == 0
    assert "skipped for no baseline" in result.reason


@pytest.mark.asyncio
async def test_ignores_predictions_from_a_different_model(
    model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
):
    """Only outcomes for the CURRENT Champion's own predictions count — a retired predecessor's
    predictions must not pollute the comparison."""
    market_id = MarketId(uuid4())
    champion = await model_repo.upsert(_champion(market_id))
    retired_model_id = ModelId(uuid4())

    prediction = await prediction_repo.record(
        _prediction(market_id, retired_model_id, "HOME_WIN", {"HOME_WIN": 0.9, "DRAW": 0.05, "AWAY_WIN": 0.05})
    )
    await prediction_outcome_repo.record(_outcome(prediction.id, "HOME_WIN"))

    service = _service(
        model_repo, prediction_repo, prediction_outcome_repo, experiment_repo,
        baseline_probabilities={"HOME_WIN": 0.5, "DRAW": 0.25, "AWAY_WIN": 0.25}, min_samples=1,
    )

    result = await service.compare(market_id, "football.match_winner", T0)

    assert result.sample_count == 0

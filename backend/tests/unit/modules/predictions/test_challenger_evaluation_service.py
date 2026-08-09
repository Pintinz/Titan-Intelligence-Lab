from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.challenger_evaluation_service import (
    MIN_RELATIVE_IMPROVEMENT,
    ChallengerEvaluationService,
)
from modules.predictions.domain.model_comparison import ComparisonVerdict
from modules.predictions.domain.value_objects import MarketId, ModelId, TargetType
from modules.predictions.ports.ml_model import ModelPrediction, TrainingSample

T0 = datetime(2026, 8, 8, tzinfo=timezone.utc)


@dataclass
class _FakeModel:
    """A `PredictionModelPort` test double whose `predict_one` returns a fixed probability per
    call, driven by an index cursor — lets a test dictate exactly what each model "believes" about
    each holdout sample without any real fitting."""

    probabilities: list[float]
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    target_type: TargetType = TargetType.CLASSIFICATION
    _i: int = 0

    def predict_one(self, features: dict) -> ModelPrediction:
        p = self.probabilities[self._i % len(self.probabilities)]
        self._i += 1
        if self.class_labels:
            # Multiclass path: distribution weighted toward class 0 by `p`, spreading the rest.
            remaining = 1.0 - p
            other = remaining / (len(self.class_labels) - 1) if len(self.class_labels) > 1 else 0.0
            distribution = {label: other for label in self.class_labels}
            distribution[self.class_labels[0]] = p
            return ModelPrediction(raw_score=p, probability=p, value=self.class_labels[0], distribution=distribution)
        return ModelPrediction(raw_score=p, probability=p, value="positive" if p >= 0.5 else "negative")


@dataclass
class _FakeRegressionModel:
    target_type: TargetType = TargetType.REGRESSION
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    offset: float = 0.0

    def predict_one(self, features: dict) -> ModelPrediction:
        return ModelPrediction(raw_score=features["x"] + self.offset, probability=0.0, value="")


def _binary_samples(n: int = 20) -> list[TrainingSample]:
    return [TrainingSample(features={"x": float(i)}, label=1.0 if i % 2 == 0 else 0.0) for i in range(n)]


@pytest.fixture
def service():
    return ChallengerEvaluationService()


class TestEvaluate:
    async def test_no_champion_is_inconclusive(self, service):
        challenger = _FakeModel(probabilities=[0.9] * 20)
        result = service.evaluate(
            market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
            challenger_model_id=ModelId(uuid4()), challenger=challenger,
            champion_model_id=None, champion=None,
            holdout_samples=_binary_samples(), now=T0,
        )
        assert result.verdict is ComparisonVerdict.INCONCLUSIVE
        assert result.decisive_metric == "none"
        assert result.champion_metrics is None

    async def test_challenger_with_meaningfully_lower_log_loss_wins(self, service):
        samples = _binary_samples(20)
        # Perfectly confident and correct every time -> log loss ~0; champion is a coin flip.
        challenger = _FakeModel(probabilities=[0.999, 0.001] * 10)
        champion = _FakeModel(probabilities=[0.5] * 20)

        result = service.evaluate(
            market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
            challenger_model_id=ModelId(uuid4()), challenger=challenger,
            champion_model_id=ModelId(uuid4()), champion=champion,
            holdout_samples=samples, now=T0,
        )

        assert result.verdict is ComparisonVerdict.CHALLENGER_BETTER
        assert result.decisive_metric == "log_loss"
        assert result.challenger_metrics.log_loss < result.champion_metrics.log_loss

    async def test_champion_with_meaningfully_lower_log_loss_wins(self, service):
        samples = _binary_samples(20)
        challenger = _FakeModel(probabilities=[0.5] * 20)
        champion = _FakeModel(probabilities=[0.999, 0.001] * 10)

        result = service.evaluate(
            market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
            challenger_model_id=ModelId(uuid4()), challenger=challenger,
            champion_model_id=ModelId(uuid4()), champion=champion,
            holdout_samples=samples, now=T0,
        )

        assert result.verdict is ComparisonVerdict.CHAMPION_BETTER
        assert result.decisive_metric == "log_loss"

    async def test_near_identical_models_are_inconclusive_not_a_coin_flip(self, service):
        samples = _binary_samples(20)
        challenger = _FakeModel(probabilities=[0.6, 0.4] * 10)
        # Same shape, offset by less than MIN_RELATIVE_IMPROVEMENT's worth of log loss.
        champion = _FakeModel(probabilities=[0.601, 0.401] * 10)

        result = service.evaluate(
            market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
            challenger_model_id=ModelId(uuid4()), challenger=challenger,
            champion_model_id=ModelId(uuid4()), champion=champion,
            holdout_samples=samples, now=T0,
        )

        assert result.verdict is ComparisonVerdict.INCONCLUSIVE

    async def test_regression_ranks_by_mae(self, service):
        samples = [TrainingSample(features={"x": float(i)}, label=float(i)) for i in range(10)]
        challenger = _FakeRegressionModel(offset=0.0)  # perfect
        champion = _FakeRegressionModel(offset=5.0)  # off by 5 every time

        result = service.evaluate(
            market_id=MarketId(uuid4()), target_type=TargetType.REGRESSION,
            challenger_model_id=ModelId(uuid4()), challenger=challenger,
            champion_model_id=ModelId(uuid4()), champion=champion,
            holdout_samples=samples, now=T0,
        )

        assert result.verdict is ComparisonVerdict.CHALLENGER_BETTER
        assert result.decisive_metric == "mae"
        assert result.challenger_metrics.mae == pytest.approx(0.0)
        assert result.champion_metrics.mae == pytest.approx(5.0)

    async def test_multiclass_scores_log_loss_only_no_brier_or_calibration(self, service):
        labels = ("HOME_WIN", "DRAW", "AWAY_WIN")
        samples = [TrainingSample(features={"x": float(i)}, label=0.0) for i in range(15)]  # always class 0
        challenger = _FakeModel(probabilities=[0.9] * 15, class_labels=labels)
        champion = _FakeModel(probabilities=[0.34] * 15, class_labels=labels)

        result = service.evaluate(
            market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
            challenger_model_id=ModelId(uuid4()), challenger=challenger,
            champion_model_id=ModelId(uuid4()), champion=champion,
            holdout_samples=samples, now=T0,
        )

        assert result.challenger_metrics.brier_score is None
        assert result.challenger_metrics.expected_calibration_error is None
        assert result.challenger_metrics.log_loss is not None
        assert result.verdict is ComparisonVerdict.CHALLENGER_BETTER
        assert result.decisive_metric == "log_loss"

    async def test_holdout_sample_count_and_ids_are_recorded(self, service):
        samples = _binary_samples(7)
        challenger_id, champion_id, market_id = ModelId(uuid4()), ModelId(uuid4()), MarketId(uuid4())

        result = service.evaluate(
            market_id=market_id, target_type=TargetType.CLASSIFICATION,
            challenger_model_id=challenger_id, challenger=_FakeModel(probabilities=[0.7] * 7),
            champion_model_id=champion_id, champion=_FakeModel(probabilities=[0.6] * 7),
            holdout_samples=samples, now=T0,
        )

        assert result.holdout_sample_count == 7
        assert result.market_id == market_id
        assert result.challenger_model_id == challenger_id
        assert result.champion_model_id == champion_id
        assert result.evaluated_at == T0


def test_min_relative_improvement_is_a_small_positive_fraction():
    assert 0.0 < MIN_RELATIVE_IMPROVEMENT < 0.1

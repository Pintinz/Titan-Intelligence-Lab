from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.backtest_service import BacktestService, InsufficientBacktestSamplesError
from modules.predictions.application.challenger_evaluation_service import ChallengerEvaluationService
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.ports.ml_model import ModelPrediction, TrainingMetrics, TrainingSample

T0 = datetime(2026, 8, 8, tzinfo=timezone.utc)


@dataclass
class _RecencyAwareModel:
    """A `PredictionModelPort` test double that isolates exactly the variable a walk-forward
    backtest is meant to measure — how RECENT a model's training data is relative to what it's
    now being asked to predict — without needing a hand-rolled "real" classifier. The true label
    rule (``round % 2``) is fixed and known; what varies is how confidently the model applies it,
    decaying sharply once the sample it's scoring is more than one round newer than anything it
    was trained on. A model retrained every round (the "continuous" column) is always exactly one
    round stale; a model frozen after round 0 (the "static" column) grows staler every round —
    the exact real-world gap this backtest exists to detect."""

    target_type: TargetType = TargetType.CLASSIFICATION
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    _max_round_seen: int = -1

    async def fit(self, samples: list[TrainingSample], validation_samples=None) -> TrainingMetrics:
        self._max_round_seen = max(int(s.features["round"]) for s in samples)
        return TrainingMetrics(sample_count=len(samples), metric_name="fit", metric_value=1.0)

    def predict_one(self, features: dict) -> ModelPrediction:
        round_ = int(features["round"])
        distance = max(0, round_ - self._max_round_seen)
        confidence = 0.95 if distance <= 1 else 0.5
        correct_label_positive = round_ % 2 == 0
        p = confidence if correct_label_positive else 1.0 - confidence
        return ModelPrediction(raw_score=p, probability=p, value="positive" if p >= 0.5 else "negative")


def _drifting_samples(n: int, round_size: int = 20) -> list[TrainingSample]:
    """Every ``round_size`` samples forms one "round" (matching the backtest's own ``step``);
    the real label alternates by round parity. Built oldest-first, then reversed by the caller to
    emulate `evaluated_at.desc()` ordering. Milestone 18: `BacktestService.run()` reverses back to
    chronological order and then calls `dataset_splitter.split(..., WALK_FORWARD, ...)`, which now
    requires a real `reference_time` on every sample (the real production caller,
    `ml_platform_router.run_backtest`, always has one — it passes `DatasetBuilder`'s own
    `dataset.samples` straight through, and `DatasetBuilder` now populates `reference_time` from
    `PredictionOutcome.evaluated_at`)."""
    return [
        TrainingSample(
            features={"round": float(i // round_size)}, label=1.0 if (i // round_size) % 2 == 0 else 0.0,
            reference_time=T0 + timedelta(hours=i),
        )
        for i in range(n)
    ]


@pytest.fixture
def service():
    return BacktestService(evaluator=ChallengerEvaluationService())


class TestBacktestService:
    async def test_continuous_retraining_tracks_drift_better_than_a_frozen_model(self, service):
        samples_oldest_first = _drifting_samples(200)
        samples_newest_first = list(reversed(samples_oldest_first))

        report = await service.run(
            market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
            samples_newest_first=samples_newest_first,
            model_factory=lambda: _RecencyAwareModel(),
            now=T0, min_train_size=60, step=20,
        )

        assert len(report.rounds) > 1
        assert report.decisive_metric == "log_loss"
        assert report.continuous_mean_metric is not None
        assert report.static_mean_metric is not None
        # The whole point of the harness: retraining each round should out-perform a model frozen
        # after round 0 once the underlying relationship has visibly drifted.
        assert report.continuous_learning_improved is True
        assert report.continuous_mean_metric < report.static_mean_metric

    async def test_rounds_grow_the_training_window_each_time(self, service):
        samples_newest_first = list(reversed(_drifting_samples(150)))

        report = await service.run(
            market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
            samples_newest_first=samples_newest_first,
            model_factory=lambda: _RecencyAwareModel(),
            now=T0, min_train_size=50, step=25,
        )

        train_sizes = [r.train_size for r in report.rounds]
        assert train_sizes == sorted(train_sizes)  # strictly non-decreasing — WALK_FORWARD grows, never shrinks
        assert train_sizes[0] == 50

    async def test_too_few_samples_raises_an_honest_error(self, service):
        with pytest.raises(InsufficientBacktestSamplesError):
            await service.run(
                market_id=MarketId(uuid4()), target_type=TargetType.CLASSIFICATION,
                samples_newest_first=list(reversed(_drifting_samples(40))),
                model_factory=lambda: _RecencyAwareModel(),
                now=T0, min_train_size=60, step=20,
            )

    async def test_regression_uses_mae_as_the_decisive_metric(self, service):
        @dataclass
        class _RegressionModel:
            target_type: TargetType = TargetType.REGRESSION
            class_labels: tuple[str, ...] = field(default_factory=tuple)
            _mean_label: float = 0.0

            async def fit(self, samples, validation_samples=None) -> TrainingMetrics:
                self._mean_label = sum(s.label for s in samples) / len(samples)
                return TrainingMetrics(sample_count=len(samples), metric_name="fit", metric_value=1.0)

            def predict_one(self, features: dict) -> ModelPrediction:
                return ModelPrediction(raw_score=self._mean_label, probability=0.0, value="")

        samples_oldest_first = [
            TrainingSample(features={"x": float(i)}, label=float(i) * 2.0, reference_time=T0 + timedelta(hours=i))
            for i in range(150)
        ]
        samples_newest_first = list(reversed(samples_oldest_first))

        report = await service.run(
            market_id=MarketId(uuid4()), target_type=TargetType.REGRESSION,
            samples_newest_first=samples_newest_first,
            model_factory=lambda: _RegressionModel(),
            now=T0, min_train_size=50, step=25,
        )

        assert report.decisive_metric == "mae"
        assert all(r.continuous_metrics.log_loss is None for r in report.rounds)

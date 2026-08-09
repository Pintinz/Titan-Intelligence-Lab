"""Chronological backtest harness (Continuous Outcome Learning Engine, 2026-08-08, spec §18) —
the check this whole engine is meant to pass before anyone trusts it: does retraining as new
completed matches accumulate actually improve out-of-sample performance, measured, not assumed?

Walks `dataset_splitter`'s existing WALK_FORWARD folds (growing chronological train window, fixed
test window right after it — exactly the "Train 1..N / Predict N+1..N+k, roll forward" shape the
spec names) and scores two models per round with the identical `ChallengerEvaluationService.score`
both `ChallengerEvaluationService.evaluate` and `AutomaticModelSelectionService` already use:

- ``continuous``: retrained fresh on that round's own (growing) training window — what this
  engine's scheduled retraining actually does.
- ``static``: fitted once on round 0's window and never touched again — the "existing
  architecture" baseline, i.e. what TitanIQ looked like before this engine existed.

Both are scored on the SAME held-out test window per round, so the only variable between the two
columns is whether retraining happened — a fair, apples-to-apples comparison, not a strawman.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from modules.predictions.application.challenger_evaluation_service import ChallengerEvaluationService
from modules.predictions.application.dataset_splitter import split
from modules.predictions.domain.backtest import BacktestReport, BacktestRound
from modules.predictions.domain.dataset import SplitStrategy
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.ports.ml_model import PredictionModelPort, TrainingSample


class InsufficientBacktestSamplesError(ValueError):
    """Raised when there isn't enough history for even one WALK_FORWARD round — an honest "not
    enough accumulated outcomes to backtest yet," never a fabricated report."""


@dataclass
class BacktestService:
    evaluator: ChallengerEvaluationService

    async def run(
        self,
        market_id: MarketId,
        target_type: TargetType,
        samples_newest_first: list[TrainingSample],
        model_factory: Callable[[], PredictionModelPort],
        now: datetime,
        min_train_size: int = 60,
        step: int = 20,
    ) -> BacktestReport:
        """``model_factory`` is called once per round (plus once for the static baseline) to get
        a fresh, unfitted `PredictionModelPort` — the caller decides algorithm/framework/
        ``class_labels`` exactly as `AutomaticModelSelectionService` already does, this service
        stays framework-agnostic. ``samples_newest_first`` mirrors
        `PredictionOutcomeRepositoryPort.list_by_market`'s `evaluated_at.desc()` ordering; this
        reverses it before splitting, since WALK_FORWARD only means anything in ascending
        chronological order (`dataset_splitter.py`'s own docstring)."""
        samples = list(reversed(samples_newest_first))
        if len(samples) < min_train_size + step:
            raise InsufficientBacktestSamplesError(
                f"need at least {min_train_size + step} samples for one backtest round "
                f"(min_train_size={min_train_size} + step={step}), got {len(samples)}"
            )

        split_result = split(samples, SplitStrategy.WALK_FORWARD, min_train_size=min_train_size, step=step)

        static_model = model_factory()
        static_train_fold, _ = split_result.folds[0]
        await static_model.fit(list(static_train_fold))

        rounds = []
        for round_index, (train_fold, test_fold) in enumerate(split_result.folds):
            continuous_model = model_factory()
            await continuous_model.fit(list(train_fold))

            continuous_metrics = self.evaluator.score(continuous_model, target_type, list(test_fold), now)
            static_metrics = self.evaluator.score(static_model, target_type, list(test_fold), now)

            rounds.append(
                BacktestRound(
                    round_index=round_index, train_size=len(train_fold), test_size=len(test_fold),
                    continuous_metrics=continuous_metrics, static_metrics=static_metrics,
                )
            )

        decisive_metric = "log_loss" if target_type is TargetType.CLASSIFICATION else "mae"
        continuous_mean = _mean(getattr(r.continuous_metrics, decisive_metric) for r in rounds)
        static_mean = _mean(getattr(r.static_metrics, decisive_metric) for r in rounds)
        improved = continuous_mean is not None and static_mean is not None and continuous_mean < static_mean

        return BacktestReport(
            market_id=market_id, target_type=target_type, rounds=tuple(rounds),
            decisive_metric=decisive_metric,
            continuous_mean_metric=continuous_mean, static_mean_metric=static_mean,
            continuous_learning_improved=improved, generated_at=now,
        )


def _mean(values) -> float | None:
    real_values = [v for v in values if v is not None]
    return sum(real_values) / len(real_values) if real_values else None

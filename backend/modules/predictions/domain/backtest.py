"""Continuous Outcome Learning Engine — chronological backtest domain (2026-08-08, spec §18:
"Train: Matches 1-N / Predict: N+1..N+k, roll forward. Compare: Existing architecture vs.
Existing architecture + Outcome Learning Engine"). `BacktestService` (application layer) is the
harness; this module is only its result shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.predictions.domain.model_comparison import ComparisonMetrics
from modules.predictions.domain.value_objects import MarketId, TargetType


@dataclass(frozen=True)
class BacktestRound:
    """One WALK_FORWARD fold: a growing training window, a fixed-size held-out test window right
    after it. ``continuous_metrics`` is a model retrained on THIS round's own training window
    (the Continuous Outcome Learning Engine's own behavior); ``static_metrics`` is the SAME
    fitted model from round 0, never retrained, scored on this round's test window too — the
    "existing architecture" baseline the spec asks the learning engine be measured against."""

    round_index: int
    train_size: int
    test_size: int
    continuous_metrics: ComparisonMetrics
    static_metrics: ComparisonMetrics


@dataclass(frozen=True)
class BacktestReport:
    market_id: MarketId
    target_type: TargetType
    rounds: tuple[BacktestRound, ...]
    decisive_metric: str
    """``"log_loss"`` for classification, ``"mae"`` for regression — the same per-target-type
    metric `AutomaticModelSelectionService`/`ChallengerEvaluationService` already rank by."""
    continuous_mean_metric: float | None
    static_mean_metric: float | None
    continuous_learning_improved: bool
    """`True` only when both means were computable and the continuously-retrained model's mean
    decisive metric beat the static model's — never assumed, always measured round by round."""
    generated_at: datetime

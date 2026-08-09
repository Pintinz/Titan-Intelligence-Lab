"""Error Memory domain (Continuous Outcome Learning Engine, 2026-08-08, spec §12) — "an
analytical layer that maintains historical model performance," answering real, computed questions
("which market performs best," "is the model overconfident," "which features are associated with
failures") from `Prediction`/`PredictionOutcome`/`ModelEvaluation` history that already exists.
Never a fabricated AI memory — every field here traces back to a stored real fact.

Deliberately does NOT hardcode domain hypotheses the spec lists as examples ("overestimated home
advantage," "recent form overvalued") — the spec itself says "Do not manually hard-code
conclusions. Allow the historical dataset and validation process to determine which features are
useful." `FeatureFailureAssociation` generalizes over whatever feature keys a market's real
`feature_snapshot`s happen to contain; if one of them is named ``home_advantage`` or similar, its
divergence score will surface on its own, exactly like any other feature — no special-casing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.predictions.domain.value_objects import MarketId, ModelId, ModelStatus


@dataclass(frozen=True)
class MarketPerformanceSummary:
    market_id: MarketId
    market_key: str
    sample_count: int
    mean_error: float | None
    """Average `PredictionOutcome.error` across resolved outcomes — lower is better, `None` when
    no outcome has been resolved yet for this market."""
    accuracy: float | None
    """Classification markets only: fraction of resolved outcomes with `error < 0.5`. `None` for
    a regression market (no binary "correct" to count) or a market with zero resolved outcomes."""


@dataclass(frozen=True)
class FeatureFailureAssociation:
    feature_key: str
    correct_mean: float | None
    incorrect_mean: float | None
    divergence: float | None
    """`abs(correct_mean - incorrect_mean)` — the real, measured gap between this feature's
    average value on predictions that turned out right vs. wrong. A large divergence means this
    feature's value differs meaningfully between TitanIQ's correct and incorrect calls on this
    market; it does not by itself claim which direction is "the bug," only that this feature is
    worth a human looking at."""
    correct_sample_count: int
    incorrect_sample_count: int


@dataclass(frozen=True)
class OverconfidenceSummary:
    market_id: MarketId
    sample_count: int
    mean_predicted_probability: float | None
    mean_actual_positive_rate: float | None
    overconfidence_score: float | None
    """`mean_predicted_probability - mean_actual_positive_rate`. Positive means TitanIQ's stated
    probabilities have on average run higher than what actually happened (systematically
    overconfident); negative means underconfident; near zero means well-calibrated on average —
    though a market can average near zero while still being badly miscalibrated in the tails,
    which is what `expected_calibration_error` (bucketed, not averaged) is for."""
    expected_calibration_error: float | None


@dataclass(frozen=True)
class ModelVersionSummary:
    model_id: ModelId
    model_key: str
    version: int
    status: ModelStatus
    latest_metrics: dict | None
    evaluated_at: datetime | None

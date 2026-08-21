"""Automatic Model Selection domain (Milestone 9.1): "Never hardcode algorithm selection" — a
market's champion algorithm is decided by benchmarking a configurable candidate roster against
real held-out metrics, not by picking a favorite in code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.ports.ml_model import PredictionModelPort, TrainingMetrics


@dataclass(frozen=True)
class CandidateSpec:
    algorithm: MLAlgorithm
    framework: MLFramework
    params: dict = field(default_factory=dict)
    # Statistical-baseline charter ("every trainable market should have a simple statistical
    # baseline before an ML Champion can be promoted"): marks which roster entries are the
    # designated baseline family (LogisticRegression/Ridge/Poisson/Tweedie) so a market's
    # `Experiment` record can show whether ML actually beat the baseline, not just who won.
    is_baseline: bool = False


class NoViableCandidateError(ValueError):
    """Raised when every candidate either raised `InsufficientTrainingDataError` or
    `UnsupportedAlgorithmForTargetTypeError` — the honest "nothing trainable yet" outcome, distinct
    from a single candidate's own failure."""


@dataclass(frozen=True)
class ModelSelectionResult:
    winning_candidate: CandidateSpec
    winning_model: PredictionModelPort
    ranking_metric: str
    ranking_value: float
    all_candidates: tuple[CandidateSpec, ...]
    skipped_candidates: tuple[tuple[CandidateSpec, str], ...] = field(default_factory=tuple)
    # Every non-skipped candidate's own ranking-metric score (not just the winner's) — closes the
    # audit gap where a losing baseline's score was previously discarded, making "did ML actually
    # beat the baseline, and by how much" reconstructable from the persisted `Experiment` later.
    candidate_scores: tuple[tuple[CandidateSpec, float], ...] = field(default_factory=tuple)
    # Training Run audit trail (the record behind `ModelDefinition.training_run_ref`) — the
    # winning candidate's own `TrainingRunResult` detail, carried as plain domain-safe fields
    # (not the `training_pipeline_service.TrainingRunResult` dataclass itself, which is
    # application-layer) so `select_and_register_challenger` can persist a `TrainingRun` row
    # without this domain object depending on the application layer.
    winning_train_metrics: TrainingMetrics | None = None
    winning_test_metrics: dict = field(default_factory=dict)
    winning_feature_order: tuple[str, ...] = field(default_factory=tuple)
    winning_selected_features: tuple[str, ...] = field(default_factory=tuple)
    winning_samples_used: int = 0
    winning_outliers_removed: int = 0

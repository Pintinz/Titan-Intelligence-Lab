"""Automatic Model Selection domain (Milestone 9.1): "Never hardcode algorithm selection" — a
market's champion algorithm is decided by benchmarking a configurable candidate roster against
real held-out metrics, not by picking a favorite in code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.ports.ml_model import PredictionModelPort


@dataclass(frozen=True)
class CandidateSpec:
    algorithm: MLAlgorithm
    framework: MLFramework
    params: dict = field(default_factory=dict)


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

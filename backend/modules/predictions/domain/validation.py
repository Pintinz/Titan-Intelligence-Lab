"""Validation Strategy + Hyperparameter Optimization domain (Milestone 9.1). Distinct from
`modules.predictions.domain.dataset.SplitStrategy` — that produces a *Dataset artifact* (a
versioned, registered, lineage-tracked snapshot); `ValidationStrategy` governs how a single
already-loaded training run is *evaluated* (cross-validation folds for model selection/HPO), a
narrower, more model-fitting-centric concern that doesn't need dataset-registry-level bookkeeping.
Some fold-generation logic is intentionally shared (`ROLLING_WINDOW`/`WALK_FORWARD`/
`TIME_SERIES_SPLIT` reuse `dataset_splitter`'s helpers) since the underlying windowing math is
identical either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ValidationStrategy(str, Enum):
    """The 9 validation strategies named by the Milestone 9.1 spec."""

    HOLDOUT = "holdout"
    K_FOLD = "k_fold"
    STRATIFIED_K_FOLD = "stratified_k_fold"
    TIME_SERIES_SPLIT = "time_series_split"
    ROLLING_WINDOW = "rolling_window"
    WALK_FORWARD = "walk_forward"
    LEAVE_ONE_OUT = "leave_one_out"
    REPEATED_K_FOLD = "repeated_k_fold"
    NESTED_CV = "nested_cv"


class HPOStrategy(str, Enum):
    """The 5 hyperparameter optimization strategies named by the Milestone 9.1 spec."""

    GRID_SEARCH = "grid_search"
    RANDOM_SEARCH = "random_search"
    BAYESIAN_OPTIMIZATION = "bayesian_optimization"
    SUCCESSIVE_HALVING = "successive_halving"
    OPTUNA = "optuna"


@dataclass(frozen=True)
class FoldResult:
    fold_index: int
    metric_name: str
    metric_value: float
    sample_count: int


@dataclass(frozen=True)
class CrossValidationResult:
    strategy: ValidationStrategy
    fold_results: tuple[FoldResult, ...]
    mean_metric: float
    std_metric: float


@dataclass(frozen=True)
class HPOTrial:
    trial_index: int
    params: dict
    metric_value: float


@dataclass(frozen=True)
class HPOResult:
    strategy: HPOStrategy
    trials: tuple[HPOTrial, ...]
    best_params: dict
    best_metric_value: float

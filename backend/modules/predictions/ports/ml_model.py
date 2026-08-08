"""Prediction Model port (Milestone 9.1 "Enterprise Machine Learning Platform") — the framework-
independence seam every LightGBM/XGBoost/CatBoost/scikit-learn adapter is written against.

Deliberately a *lower*-level port than `PredictorPort` (modules.predictions.ports.predictor),
which stays completely unchanged per the Milestone 9.1 mandate ("Prediction Engine interfaces
must NEVER change. Only the predictor implementations may change."). The relationship:

    PredictorPort (unchanged)
        `TrainedModelPredictor` (infrastructure/predictors/ml_predictor.py) — a PredictorPort
        implementation that wraps ONE fitted PredictionModelPort instance and adapts its
        single-row `ModelPrediction` into the `PredictorOutput` shape every other predictor
        already returns (raw_score/probability/value/feature_contributions).

`PredictionModelPort` itself only knows about feature vectors and a scalar label — no
`MarketKind`, no `FeatureMarketMapping` — those stay `PredictorPort`/context-builder concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from modules.predictions.domain.value_objects import TargetType

MIN_TRAINING_SAMPLES = 30


class InsufficientTrainingDataError(ValueError):
    """Raised by `fit()` when fewer than `MIN_TRAINING_SAMPLES` are supplied — the honest "not
    enough real historical outcomes yet" signal (docs/decisions.md ADR-044/046/048 posture), not
    a fabricated fit on too little data. Callers (Training Platform) catch this and leave the
    weighted predictor as the market's fallback, per the Milestone 9.1 Definition of Done:
    "Weighted predictors remain only as fallback/debug implementations."""


class ModelNotFittedError(RuntimeError):
    """Raised by `predict_one()`/`feature_importance()`/`serialize()` before `fit()` or
    `deserialize()` has populated the underlying framework model."""


class UnsupportedAlgorithmForTargetTypeError(ValueError):
    """Raised when an algorithm has no sensible mapping for a `TargetType` (e.g. GaussianNB,
    inherently a classifier, requested for a REGRESSION-shaped market)."""


@dataclass(frozen=True)
class TrainingSample:
    """One (feature snapshot, realized label) pair drawn from `PredictionOutcome` history — label
    is 1.0/0.0 for a binary CLASSIFICATION target, the continuous realized value for REGRESSION, or
    (multiclass classification support, 2026-08-06) the float index of the real class label within
    the market's own `class_labels` ordering (see `PredictionModelPort.class_labels` below) for a
    market with more than two outcomes (e.g. `football.correct_score`'s 37-cell scoreline grid,
    `football.match_winner`'s HOME_WIN/DRAW/AWAY_WIN)."""

    features: dict[str, float]
    label: float


@dataclass(frozen=True)
class ModelPrediction:
    """A `PredictionModelPort.predict_one()` result — mirrors `PredictorOutput`'s
    raw_score/probability/value/distribution shape so `TrainedModelPredictor` can pass them
    through directly. ``distribution`` (multiclass classification support, 2026-08-06) is only
    populated for a multiclass classification model (keyed by the market's own real labels, e.g.
    "2-1"/"OTHER") — empty for every binary-classification or regression model, exactly as before."""

    raw_score: float
    probability: float
    value: str
    distribution: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingMetrics:
    sample_count: int
    metric_name: str
    metric_value: float
    extra: dict[str, float] = field(default_factory=dict)


class PredictionModelPort(Protocol):
    target_type: TargetType
    feature_order: list[str]
    class_labels: tuple[str, ...]
    """(Multiclass classification support, 2026-08-06) The market's real label space in a fixed
    order, e.g. ``("HOME_WIN", "DRAW", "AWAY_WIN")`` or the 37-cell correct-score grid — set by the
    caller (`AutomaticModelSelectionService`, from `Dataset.lineage.class_labels`) before `fit()`
    for any classification market with more than two outcomes. Empty (the default) for every
    binary-classification or regression model, which keep encoding/decoding 0.0/1.0 and a raw
    continuous value exactly as before this support was added — this field only changes behavior
    when a caller populates it."""

    async def fit(
        self, samples: list[TrainingSample], validation_samples: list[TrainingSample] | None = None
    ) -> TrainingMetrics:
        """Fits the underlying framework model. Raises `InsufficientTrainingDataError` if
        ``len(samples) < MIN_TRAINING_SAMPLES``. Derives and stores ``feature_order`` from the
        union of feature keys across ``samples`` (sorted, for reproducibility). When
        ``validation_samples`` is supplied, the LightGBM/XGBoost/CatBoost gradient-boosting
        adapters use it for native early stopping (Milestone 9.1 Training Platform "Early
        Stopping" requirement); other adapters accept and ignore it for interface consistency."""
        ...

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        """Single-row inference — mirrors `PredictorPort.predict()`'s single-subject shape.
        Raises `ModelNotFittedError` if called before `fit()`/`deserialize()`."""
        ...

    def feature_importance(self) -> dict[str, float]:
        """Normalized (sums to 1.0) global feature importance from the fitted model."""
        ...

    def is_fitted(self) -> bool: ...

    def underlying_estimator(self):
        """Returns the raw fitted framework estimator (a `lightgbm`/`xgboost`/`catboost` model,
        or an `sklearn` estimator/`Pipeline`) for SHAP introspection (Milestone 9.1 task #166) —
        `None` if not yet fitted. Not every consumer needs this; it exists so
        `SHAPExplainerService` doesn't have to reach into a private attribute."""
        ...

    def serialize(self) -> bytes:
        """Returns the fitted model + feature_order as opaque bytes — persistence location is a
        `ModelArtifactStorePort` concern, not this adapter's (docs/decisions.md ADR-008)."""
        ...

    def deserialize(self, payload: bytes) -> None:
        """Restores a previously `serialize()`-d model, making `predict_one()`/
        `feature_importance()` usable again without re-fitting."""
        ...


class ModelArtifactStorePort(Protocol):
    """Where a serialized `PredictionModelPort` payload physically lives — swappable independently
    of any framework adapter (local filesystem for dev, Supabase Storage `ai-reports`-style bucket
    for production), same adapter-swap posture as every other capability port."""

    async def save(self, key: str, payload: bytes) -> str:
        """Persists ``payload`` under ``key``, returning the ref a later `load()` call needs
        (may just be ``key`` itself, or a richer URI depending on the implementation)."""
        ...

    async def load(self, ref: str) -> bytes: ...

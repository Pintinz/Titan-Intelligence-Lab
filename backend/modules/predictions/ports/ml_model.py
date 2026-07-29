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
    """One (feature snapshot, realized label) pair drawn from `PredictionOutcome` history —
    label is 1.0/0.0 for a CLASSIFICATION target, the continuous realized value for REGRESSION."""

    features: dict[str, float]
    label: float


@dataclass(frozen=True)
class ModelPrediction:
    """A `PredictionModelPort.predict_one()` result — mirrors `PredictorOutput`'s
    raw_score/probability/value triad so `TrainedModelPredictor` can pass them through directly."""

    raw_score: float
    probability: float
    value: str


@dataclass(frozen=True)
class TrainingMetrics:
    sample_count: int
    metric_name: str
    metric_value: float
    extra: dict[str, float] = field(default_factory=dict)


class PredictionModelPort(Protocol):
    target_type: TargetType
    feature_order: list[str]

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

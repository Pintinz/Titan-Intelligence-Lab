"""CatBoost `PredictionModelPort` adapter (Milestone 9.1 "Gradient Boosting" family) — same
honest fit-refusal posture as `lightgbm_adapter.py`, see that module's docstring. `verbose=False`
is fixed (not user-configurable via ``params``) so training never spams stdout inside a service
process.

Passing ``validation_samples`` to `fit()` enables CatBoost's native early stopping via
``eval_set``/``early_stopping_rounds``.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor

from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml._math import feature_union, logit, sigmoid, vectorize
from modules.predictions.ports.ml_model import (
    MIN_TRAINING_SAMPLES,
    InsufficientTrainingDataError,
    ModelNotFittedError,
    ModelPrediction,
    TrainingMetrics,
    TrainingSample,
)


@dataclass
class CatBoostAdapter:
    target_type: TargetType = TargetType.CLASSIFICATION
    params: dict = field(default_factory=dict)
    early_stopping_rounds: int = 20
    feature_order: list[str] = field(default_factory=list)
    _model: object | None = field(default=None, repr=False)

    async def fit(
        self, samples: list[TrainingSample], validation_samples: list[TrainingSample] | None = None
    ) -> TrainingMetrics:
        if len(samples) < MIN_TRAINING_SAMPLES:
            raise InsufficientTrainingDataError(
                f"CatBoostAdapter requires >= {MIN_TRAINING_SAMPLES} samples, got {len(samples)}"
            )
        self.feature_order = feature_union(samples)
        X = np.array([vectorize(s.features, self.feature_order) for s in samples])
        y = np.array([s.label for s in samples])

        fit_kwargs: dict = {}
        if validation_samples:
            X_val = np.array([vectorize(s.features, self.feature_order) for s in validation_samples])
            y_val = np.array([s.label for s in validation_samples])
            fit_kwargs = {"eval_set": (X_val, y_val), "early_stopping_rounds": self.early_stopping_rounds}

        if self.target_type is TargetType.CLASSIFICATION:
            model = CatBoostClassifier(verbose=False, **self.params)
            model.fit(X, y, **fit_kwargs)
            predictions = model.predict(X)
            metric_name, metric_value = "train_accuracy", float(np.mean(predictions.flatten() == y))
        else:
            model = CatBoostRegressor(verbose=False, **self.params)
            model.fit(X, y, **fit_kwargs)
            predictions = model.predict(X)
            metric_name, metric_value = "train_mae", float(np.mean(np.abs(predictions - y)))

        self._model = model
        return TrainingMetrics(sample_count=len(samples), metric_name=metric_name, metric_value=metric_value)

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        if self._model is None:
            raise ModelNotFittedError("CatBoostAdapter.predict_one called before fit()/deserialize()")
        x = np.array([vectorize(features, self.feature_order)])
        if self.target_type is TargetType.CLASSIFICATION:
            probability = float(self._model.predict_proba(x)[0][1])
            return ModelPrediction(
                raw_score=logit(probability),
                probability=probability,
                value="positive" if probability >= 0.5 else "negative",
            )
        raw_value = float(self._model.predict(x)[0])
        return ModelPrediction(raw_score=raw_value, probability=sigmoid(raw_value), value=f"{raw_value:.4f}")

    def feature_importance(self) -> dict[str, float]:
        if self._model is None:
            raise ModelNotFittedError("CatBoostAdapter.feature_importance called before fit()/deserialize()")
        importances = self._model.get_feature_importance()
        total = float(sum(importances)) or 1.0
        return {key: float(value) / total for key, value in zip(self.feature_order, importances)}

    def is_fitted(self) -> bool:
        return self._model is not None

    def underlying_estimator(self):
        """Raw fitted `CatBoostClassifier`/`CatBoostRegressor` — for SHAP `TreeExplainer` use
        (Milestone 9.1 task #166). Returns ``None`` if not yet fitted."""
        return self._model

    def serialize(self) -> bytes:
        if self._model is None:
            raise ModelNotFittedError("CatBoostAdapter.serialize called before fit()/deserialize()")
        return pickle.dumps(
            {
                "model": self._model,
                "feature_order": self.feature_order,
                "target_type": self.target_type,
                "params": self.params,
                "early_stopping_rounds": self.early_stopping_rounds,
            }
        )

    def deserialize(self, payload: bytes) -> None:
        state = pickle.loads(payload)
        self._model = state["model"]
        self.feature_order = state["feature_order"]
        self.target_type = state["target_type"]
        self.params = state["params"]
        self.early_stopping_rounds = state.get("early_stopping_rounds", 20)

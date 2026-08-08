"""LightGBM `PredictionModelPort` adapter (Milestone 9.1 "Gradient Boosting" family).

Real, framework-native gradient boosting — `lightgbm.LGBMClassifier`/`LGBMRegressor` chosen by
`target_type`. Honestly scoped exactly like every other v1 capability in this codebase
(docs/decisions.md ADR-008/044/046/048): `fit()` refuses fewer than `MIN_TRAINING_SAMPLES` real
labeled outcomes rather than fabricate a fit, so until a market accumulates enough
`PredictionOutcome` history, its champion stays a weighted predictor (Milestone 9.1 Definition of
Done: "Weighted predictors remain only as fallback/debug implementations").

Passing ``validation_samples`` to `fit()` enables LightGBM's native early stopping
(`early_stopping_rounds`, Milestone 9.1 Training Platform requirement) — training halts once the
validation metric stops improving, rather than always running the full configured round count.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np

from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml._math import feature_union, logit, multiclass_prediction, sigmoid, vectorize
from modules.predictions.ports.ml_model import (
    MIN_TRAINING_SAMPLES,
    InsufficientTrainingDataError,
    ModelNotFittedError,
    ModelPrediction,
    TrainingMetrics,
    TrainingSample,
)


@dataclass
class LightGBMAdapter:
    target_type: TargetType = TargetType.CLASSIFICATION
    params: dict = field(default_factory=dict)
    early_stopping_rounds: int = 20
    feature_order: list[str] = field(default_factory=list)
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    _model: object | None = field(default=None, repr=False)

    async def fit(
        self, samples: list[TrainingSample], validation_samples: list[TrainingSample] | None = None
    ) -> TrainingMetrics:
        if len(samples) < MIN_TRAINING_SAMPLES:
            raise InsufficientTrainingDataError(
                f"LightGBMAdapter requires >= {MIN_TRAINING_SAMPLES} samples, got {len(samples)}"
            )
        self.feature_order = feature_union(samples)
        X = np.array([vectorize(s.features, self.feature_order) for s in samples])
        y = np.array([s.label for s in samples])

        fit_kwargs: dict = {}
        if validation_samples:
            X_val = np.array([vectorize(s.features, self.feature_order) for s in validation_samples])
            y_val = np.array([s.label for s in validation_samples])
            fit_kwargs = {
                "eval_X": X_val,
                "eval_y": y_val,
                "callbacks": [lgb.early_stopping(self.early_stopping_rounds, verbose=False)],
            }

        if self.target_type is TargetType.CLASSIFICATION:
            model = lgb.LGBMClassifier(**self.params)
            model.fit(X, y, **fit_kwargs)
            predictions = model.predict(X)
            metric_name, metric_value = "train_accuracy", float(np.mean(predictions == y))
        else:
            model = lgb.LGBMRegressor(**self.params)
            model.fit(X, y, **fit_kwargs)
            predictions = model.predict(X)
            metric_name, metric_value = "train_mae", float(np.mean(np.abs(predictions - y)))

        self._model = model
        return TrainingMetrics(sample_count=len(samples), metric_name=metric_name, metric_value=metric_value)

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        if self._model is None:
            raise ModelNotFittedError("LightGBMAdapter.predict_one called before fit()/deserialize()")
        x = np.array([vectorize(features, self.feature_order)])
        if self.target_type is TargetType.CLASSIFICATION:
            if self.class_labels:  # multiclass (2026-08-06) — see _math.multiclass_prediction
                probabilities = self._model.predict_proba(x)[0]
                return multiclass_prediction(probabilities, self._model.classes_, self.class_labels)
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
            raise ModelNotFittedError("LightGBMAdapter.feature_importance called before fit()/deserialize()")
        importances = self._model.feature_importances_
        total = float(sum(importances)) or 1.0
        return {key: float(value) / total for key, value in zip(self.feature_order, importances)}

    def is_fitted(self) -> bool:
        return self._model is not None

    def underlying_estimator(self):
        """Raw fitted `lightgbm.LGBMClassifier`/`LGBMRegressor` — for SHAP `TreeExplainer` use
        (Milestone 9.1 task #166). Returns ``None`` if not yet fitted."""
        return self._model

    def serialize(self) -> bytes:
        if self._model is None:
            raise ModelNotFittedError("LightGBMAdapter.serialize called before fit()/deserialize()")
        return pickle.dumps(
            {
                "model": self._model,
                "feature_order": self.feature_order,
                "target_type": self.target_type,
                "params": self.params,
                "early_stopping_rounds": self.early_stopping_rounds,
                "class_labels": self.class_labels,
            }
        )

    def deserialize(self, payload: bytes) -> None:
        state = pickle.loads(payload)
        self._model = state["model"]
        self.feature_order = state["feature_order"]
        self.target_type = state["target_type"]
        self.params = state["params"]
        self.early_stopping_rounds = state.get("early_stopping_rounds", 20)
        self.class_labels = state.get("class_labels", ())

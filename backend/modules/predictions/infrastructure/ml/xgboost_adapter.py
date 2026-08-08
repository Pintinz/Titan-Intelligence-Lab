"""XGBoost `PredictionModelPort` adapter (Milestone 9.1 "Gradient Boosting" family) — same
honest fit-refusal posture as `lightgbm_adapter.py`, see that module's docstring.

Passing ``validation_samples`` to `fit()` enables native early stopping — XGBoost 2.x+ takes
``early_stopping_rounds`` as a constructor argument (not a `fit()` kwarg like LightGBM/CatBoost),
so it's only added to the estimator when validation data is actually supplied.

Dense label re-encoding (multiclass classification support, 2026-08-06): confirmed live against
football.correct_score's real training data — XGBoost's sklearn-wrapper `XGBClassifier` (unlike
LightGBM/CatBoost/every sklearn estimator, which all accept arbitrary discrete label values) raises
if `y` isn't exactly ``range(0, num_class)``. Our class-index label encoding
(`dataset_builder_service.py`) indexes into a market's full canonical label ordering, which
legitimately has gaps whenever a rare class (e.g. a scoreline with only 1-2 historical occurrences)
doesn't land in a given training split. `fit()` re-encodes to XGBoost's required dense range and
`predict_one()` decodes back through the same mapping before handing off to `multiclass_prediction`
— transparent to every other adapter and to `class_labels` itself, which still refers to the
market's real (un-gapped) label space throughout.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field

import numpy as np
import xgboost as xgb

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
class XGBoostAdapter:
    target_type: TargetType = TargetType.CLASSIFICATION
    params: dict = field(default_factory=dict)
    early_stopping_rounds: int = 20
    feature_order: list[str] = field(default_factory=list)
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    _model: object | None = field(default=None, repr=False)
    _dense_to_original: np.ndarray | None = field(default=None, repr=False)

    async def fit(
        self, samples: list[TrainingSample], validation_samples: list[TrainingSample] | None = None
    ) -> TrainingMetrics:
        if len(samples) < MIN_TRAINING_SAMPLES:
            raise InsufficientTrainingDataError(
                f"XGBoostAdapter requires >= {MIN_TRAINING_SAMPLES} samples, got {len(samples)}"
            )
        self.feature_order = feature_union(samples)
        X = np.array([vectorize(s.features, self.feature_order) for s in samples])
        y_raw = np.array([s.label for s in samples])
        y = y_raw

        estimator_params = dict(self.params)
        fit_kwargs: dict = {}
        y_val = None
        if validation_samples:
            X_val = np.array([vectorize(s.features, self.feature_order) for s in validation_samples])
            y_val = np.array([s.label for s in validation_samples])
            estimator_params["early_stopping_rounds"] = self.early_stopping_rounds

        if self.target_type is TargetType.CLASSIFICATION:
            # See module docstring — dense re-encode over the full (train + validation) label set
            # so a class present only in validation still maps correctly.
            combined = y_raw if y_val is None else np.concatenate([y_raw, y_val])
            self._dense_to_original = np.unique(combined)
            y = np.searchsorted(self._dense_to_original, y_raw)
            if y_val is not None:
                y_val = np.searchsorted(self._dense_to_original, y_val)

        if y_val is not None:
            fit_kwargs = {"eval_set": [(X_val, y_val)], "verbose": False}

        if self.target_type is TargetType.CLASSIFICATION:
            model = xgb.XGBClassifier(**estimator_params)
            model.fit(X, y, **fit_kwargs)
            predictions = model.predict(X)
            metric_name, metric_value = "train_accuracy", float(np.mean(predictions == y))
        else:
            model = xgb.XGBRegressor(**estimator_params)
            model.fit(X, y, **fit_kwargs)
            predictions = model.predict(X)
            metric_name, metric_value = "train_mae", float(np.mean(np.abs(predictions - y)))

        self._model = model
        return TrainingMetrics(sample_count=len(samples), metric_name=metric_name, metric_value=metric_value)

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        if self._model is None:
            raise ModelNotFittedError("XGBoostAdapter.predict_one called before fit()/deserialize()")
        x = np.array([vectorize(features, self.feature_order)])
        if self.target_type is TargetType.CLASSIFICATION:
            if self.class_labels:  # multiclass (2026-08-06) — see _math.multiclass_prediction
                probabilities = self._model.predict_proba(x)[0]
                # self._model.classes_ are dense-encoded (0..k-1) — decode back through the same
                # mapping fit() built before resolving against the market's real label space.
                classes_seen = self._dense_to_original[self._model.classes_.astype(int)]
                return multiclass_prediction(probabilities, classes_seen, self.class_labels)
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
            raise ModelNotFittedError("XGBoostAdapter.feature_importance called before fit()/deserialize()")
        importances = self._model.feature_importances_
        total = float(sum(importances)) or 1.0
        return {key: float(value) / total for key, value in zip(self.feature_order, importances)}

    def is_fitted(self) -> bool:
        return self._model is not None

    def underlying_estimator(self):
        """Raw fitted `xgboost.XGBClassifier`/`XGBRegressor` — for SHAP `TreeExplainer` use
        (Milestone 9.1 task #166). Returns ``None`` if not yet fitted."""
        return self._model

    def serialize(self) -> bytes:
        if self._model is None:
            raise ModelNotFittedError("XGBoostAdapter.serialize called before fit()/deserialize()")
        return pickle.dumps(
            {
                "model": self._model,
                "feature_order": self.feature_order,
                "target_type": self.target_type,
                "params": self.params,
                "early_stopping_rounds": self.early_stopping_rounds,
                "class_labels": self.class_labels,
                "dense_to_original": self._dense_to_original,
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
        self._dense_to_original = state.get("dense_to_original")

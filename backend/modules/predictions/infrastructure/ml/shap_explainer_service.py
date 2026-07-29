"""SHAP Explainability (Milestone 9.1) — real Shapley-value-based feature attribution for a
fitted `PredictionModelPort`, layered on top of (never replacing) the existing Explainability
Engine's lightweight `PredictorOutput.feature_contributions` approximation (Milestone 9).

Explainer selection is duck-typed, not framework-isinstance-checked, so this stays independent of
which of the 4 ML frameworks actually produced the model:
- Bare tree ensembles (``hasattr(estimator, "feature_importances_")`` and not wrapped in an
  `sklearn.pipeline.Pipeline`) get `shap.TreeExplainer` — fast, exact, and the only path that
  supports interaction values.
- Everything else (scale-sensitive sklearn algorithms wrapped in a `Pipeline` by
  `SklearnAdapter`, plus bare `GaussianNB`) gets `shap.KernelExplainer` over the estimator's own
  `predict_proba`/`predict` — model-agnostic, slower, but correct for anything callable, and it
  transparently handles a `Pipeline`'s internal scaling since it only ever calls the pipeline as
  a black-box function.

Every method here needs an explicit ``background`` sample list — a small, representative set of
real `TrainingSample.features` dicts (e.g. from the model's own training/validation split) — SHAP
values are always relative to *some* reference distribution, there's no framework-free way around
supplying one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shap

from modules.predictions.domain.explainability import (
    CounterfactualExplanation,
    DependencePlotData,
    DependencePoint,
    ShapExplanation,
)
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml._math import vectorize
from modules.predictions.ports.ml_model import ModelNotFittedError, PredictionModelPort

_TOP_K_DECISION_PATH = 3


class UnsupportedModelForShapError(ValueError):
    pass


def _is_pipeline(estimator) -> bool:
    return hasattr(estimator, "named_steps")


def _uses_tree_explainer(estimator) -> bool:
    return hasattr(estimator, "feature_importances_") and not _is_pipeline(estimator)


def _predict_fn(estimator, target_type: TargetType):
    if target_type is TargetType.CLASSIFICATION:
        return lambda x: estimator.predict_proba(x)[:, 1]
    return lambda x: estimator.predict(x)


@dataclass
class SHAPExplainerService:
    def _build_explainer(self, model: PredictionModelPort, background_matrix: np.ndarray):
        estimator = model.underlying_estimator()
        if estimator is None:
            raise ModelNotFittedError("SHAPExplainerService requires a fitted model")

        if _uses_tree_explainer(estimator):
            return shap.TreeExplainer(estimator), True
        return shap.KernelExplainer(_predict_fn(estimator, model.target_type), background_matrix), False

    def _matrix(self, model: PredictionModelPort, rows: list[dict]) -> np.ndarray:
        return np.array([vectorize(row, model.feature_order) for row in rows])

    def _local_values(self, explainer, is_tree: bool, x_row: np.ndarray) -> np.ndarray:
        raw = explainer.shap_values(x_row.reshape(1, -1))
        if is_tree and isinstance(raw, list):
            raw = raw[1]  # binary classifier TreeExplainer returns [class_0_values, class_1_values]
        values = np.asarray(raw)
        if values.ndim == 3:  # some TreeExplainer versions return (n_samples, n_features, n_classes)
            values = values[:, :, 1]
        return values[0]

    def explain_instance(
        self, model: PredictionModelPort, features: dict[str, float], background: list[dict[str, float]]
    ) -> ShapExplanation:
        background_matrix = self._matrix(model, background)
        explainer, is_tree = self._build_explainer(model, background_matrix)
        x_row = np.array(vectorize(features, model.feature_order))

        local_values = self._local_values(explainer, is_tree, x_row)
        local_shap_values = dict(zip(model.feature_order, (float(v) for v in local_values)))

        base_value = explainer.expected_value
        if isinstance(base_value, (list, np.ndarray)):
            base_value = float(np.asarray(base_value).reshape(-1)[-1])
        else:
            base_value = float(base_value)

        global_importance = self._global_importance(explainer, is_tree, background_matrix, model.feature_order)

        interaction_values: dict = {}
        if is_tree and hasattr(explainer, "shap_interaction_values"):
            try:
                interactions = explainer.shap_interaction_values(x_row.reshape(1, -1))
                if isinstance(interactions, list):
                    interactions = interactions[1]  # per-class list — take the positive class
                arr = np.asarray(interactions)
                if arr.ndim == 4:
                    matrix = arr[0, :, :, -1]  # (n_samples, n_features, n_features, n_classes) — positive class
                else:
                    matrix = arr[0]  # (n_samples, n_features, n_features) — regression, no class dim
                for i, feature_a in enumerate(model.feature_order):
                    for j, feature_b in enumerate(model.feature_order):
                        if j <= i:
                            continue
                        interaction_values[(feature_a, feature_b)] = float(matrix[i, j])
            except Exception:  # noqa: BLE001 — interaction values are a bonus, never fatal to explain_instance
                interaction_values = {}

        decision_path = self._decision_path(local_shap_values)

        return ShapExplanation(
            local_shap_values=local_shap_values,
            global_importance=global_importance,
            base_value=base_value,
            interaction_values=interaction_values,
            decision_path=decision_path,
        )

    def _global_importance(self, explainer, is_tree: bool, background_matrix: np.ndarray, feature_order: list[str]) -> dict:
        raw = explainer.shap_values(background_matrix)
        if is_tree and isinstance(raw, list):
            raw = raw[1]
        values = np.asarray(raw)
        if values.ndim == 3:
            values = values[:, :, 1]
        mean_abs = np.abs(values).mean(axis=0)
        total = float(mean_abs.sum()) or 1.0
        return {key: float(v) / total for key, v in zip(feature_order, mean_abs)}

    def _decision_path(self, local_shap_values: dict) -> tuple:
        ranked = sorted(local_shap_values.items(), key=lambda kv: abs(kv[1]), reverse=True)
        top = ranked[:_TOP_K_DECISION_PATH]
        return tuple(
            f"{key} {'increased' if value >= 0 else 'decreased'} the prediction by {abs(value):.4f}"
            for key, value in top
        )

    def counterfactual(
        self,
        model: PredictionModelPort,
        features: dict[str, float],
        background: list[dict[str, float]],
        max_iterations: int = 20,
        step_fraction: float = 0.25,
    ) -> CounterfactualExplanation:
        """Greedily perturbs the SHAP-ranked top feature(s) toward the opposite side of
        ``background``'s own observed range until the model's predicted label flips, or
        ``max_iterations`` is exhausted — a real, bounded search, not a static canned answer."""
        original = model.predict_one(features)
        explanation = self.explain_instance(model, features, background)
        ranked_features = [key for key, _ in sorted(explanation.local_shap_values.items(), key=lambda kv: abs(kv[1]), reverse=True)]

        background_matrix = self._matrix(model, background)
        spans = {
            key: float(background_matrix[:, i].max() - background_matrix[:, i].min()) or 1.0
            for i, key in enumerate(model.feature_order)
        }

        working = dict(features)
        changed: dict = {}
        for _ in range(max_iterations):
            candidate = ranked_features[0] if ranked_features else None
            if candidate is None:
                break
            direction = -1.0 if explanation.local_shap_values.get(candidate, 0.0) >= 0 else 1.0
            step = direction * spans[candidate] * step_fraction
            original_value = working.get(candidate, 0.0)
            working[candidate] = original_value + step
            changed[candidate] = (features.get(candidate, 0.0), working[candidate])

            attempt = model.predict_one(working)
            if attempt.value != original.value:
                return CounterfactualExplanation(
                    changed_features=changed, original_value=original.value, counterfactual_value=attempt.value, found=True
                )

        return CounterfactualExplanation(changed_features=changed, original_value=original.value, counterfactual_value=None, found=False)

    def dependence_data(
        self, model: PredictionModelPort, feature_key: str, features: dict[str, float], background: list[dict[str, float]], n_points: int = 10
    ) -> DependencePlotData:
        if feature_key not in model.feature_order:
            raise UnsupportedModelForShapError(f"'{feature_key}' is not one of this model's features")

        index = model.feature_order.index(feature_key)
        background_matrix = self._matrix(model, background)
        low, high = float(background_matrix[:, index].min()), float(background_matrix[:, index].max())
        if low == high:
            grid = [low]
        else:
            grid = list(np.linspace(low, high, n_points))

        points = []
        for value in grid:
            variant = dict(features)
            variant[feature_key] = float(value)
            explanation = self.explain_instance(model, variant, background)
            points.append(DependencePoint(feature_value=float(value), shap_value=explanation.local_shap_values[feature_key]))

        return DependencePlotData(feature_key=feature_key, points=tuple(points))

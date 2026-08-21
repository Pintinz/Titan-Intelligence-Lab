"""Phase 3 (Sports-Analyst Explainability, Workstream B) — real per-instance model attribution.

Distinct from, and does not replace, `ExplainabilityEngine`'s existing `PredictorOutput.
feature_contributions` (a lightweight `value * global_importance` approximation used for every
prediction's `ai_explanation` today — see that module's own docstring). This service answers a
narrower, stricter question: for *this one* prediction, which features actually pushed the
model's decision, and by how much — grounded in the model's own fitted parameters, not a
heuristic proxy.

Two real attribution paths, chosen by what the fitted estimator actually supports (never SHAP
"because it's fancier" when a cheaper, exact answer already exists):
- `coef_`-based linear models (logistic_regression, ridge, elastic_net) — the exact per-instance
  decomposition of the model's own linear decision function, `coef_i * feature_value_i`. This is
  not an approximation; it *is* what the fitted linear model computes, term by term.
- Everything else (gaussian_nb, svm, mlp) has no linear decomposition — real Shapley-value
  attribution via the existing (previously unwired) `SHAPExplainerService.explain_instance()` is
  the only honest option; requires a real background sample (SHAP values are always relative to
  some reference distribution — there is no framework-free way around supplying one).

**v1 scope limitation, documented rather than silently wrong**: multiclass markets
(football.match_winner, football.correct_score, football.first_half_winner,
football.second_half_winner) have no single "positive direction" a linear decomposition or a
binary SHAP explanation can attribute against without inventing a convention this service isn't
prepared to claim is correct — `attribute()` raises `UnsupportedForMulticlassError` rather than
fabricate a one-vs-rest attribution no one has verified is the right framing. Real work, not
undertaken here (same posture as every other honestly-scoped v1 boundary in this codebase).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.pipeline import Pipeline

from modules.predictions.infrastructure.ml.shap_explainer_service import SHAPExplainerService
from modules.predictions.ports.ml_model import ModelNotFittedError, PredictionModelPort


class UnsupportedForMulticlassError(ValueError):
    pass


class BackgroundSampleRequiredError(ValueError):
    pass


@dataclass(frozen=True)
class AttributedFeature:
    feature_key: str
    value: float
    contribution: float  # signed — positive pushes toward the model's published side
    direction: str  # "supports" | "opposes"
    method: str  # "linear_coefficient" | "shap"


def _final_estimator(estimator):
    if isinstance(estimator, Pipeline):
        return estimator.named_steps["model"]
    return estimator


def _has_usable_coefficients(estimator) -> bool:
    final = _final_estimator(estimator)
    if not hasattr(final, "coef_"):
        return False
    coef = np.asarray(final.coef_, dtype=float)
    return coef.ndim == 1 or coef.shape[0] == 1  # binary only — see module docstring


@dataclass
class ModelAttributionService:
    shap: SHAPExplainerService = field(default_factory=SHAPExplainerService)

    def attribute(
        self,
        model: PredictionModelPort,
        features: dict[str, float],
        background: list[dict[str, float]] | None = None,
    ) -> tuple[AttributedFeature, ...]:
        if model.class_labels:
            raise UnsupportedForMulticlassError(
                "ModelAttributionService v1 only attributes binary-classification models — "
                f"this model has {len(model.class_labels)} classes ({', '.join(model.class_labels)})"
            )
        estimator = model.underlying_estimator()
        if estimator is None:
            raise ModelNotFittedError("ModelAttributionService requires a fitted model")

        if _has_usable_coefficients(estimator):
            return self._linear_attribution(model, estimator, features)
        if not background:
            raise BackgroundSampleRequiredError(
                f"'{model.__class__.__name__}' has no linear coefficients — real per-instance "
                "attribution requires a SHAP background sample"
            )
        return self._shap_attribution(model, features, background)

    def _linear_attribution(self, model: PredictionModelPort, estimator, features: dict[str, float]) -> tuple[AttributedFeature, ...]:
        final = _final_estimator(estimator)
        coef = np.asarray(final.coef_, dtype=float).reshape(-1)
        attributed = []
        for key, weight in zip(model.feature_order, coef):
            value = float(features.get(key, 0.0))
            contribution = float(weight) * value
            attributed.append(
                AttributedFeature(
                    feature_key=key, value=value, contribution=contribution,
                    direction="supports" if contribution >= 0 else "opposes", method="linear_coefficient",
                )
            )
        return tuple(sorted(attributed, key=lambda a: abs(a.contribution), reverse=True))

    def _shap_attribution(self, model: PredictionModelPort, features: dict[str, float], background: list[dict[str, float]]) -> tuple[AttributedFeature, ...]:
        explanation = self.shap.explain_instance(model, features, background)
        attributed = [
            AttributedFeature(
                feature_key=key, value=float(features.get(key, 0.0)), contribution=float(contribution),
                direction="supports" if contribution >= 0 else "opposes", method="shap",
            )
            for key, contribution in explanation.local_shap_values.items()
        ]
        return tuple(sorted(attributed, key=lambda a: abs(a.contribution), reverse=True))

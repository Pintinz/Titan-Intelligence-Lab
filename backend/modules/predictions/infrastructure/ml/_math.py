"""Shared numeric helpers for ML adapters — same overflow-safe sigmoid/logit shape already used by
`infrastructure/predictors/weighted_scoring.py` and `infrastructure/calibration/platt_scaling_calibrator.py`,
kept here once rather than re-copied a fourth/fifth time.
"""

from __future__ import annotations

import math

from modules.predictions.ports.ml_model import ModelPrediction


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def logit(p: float, eps: float = 1e-6) -> float:
    clamped = min(max(p, eps), 1.0 - eps)
    return math.log(clamped / (1.0 - clamped))


def vectorize(features: dict[str, float], feature_order: list[str]) -> list[float]:
    return [float(features.get(key, 0.0)) for key in feature_order]


def feature_union(samples) -> list[str]:
    keys: set[str] = set()
    for sample in samples:
        keys.update(sample.features.keys())
    return sorted(keys)


def multiclass_prediction(probabilities, classes_seen, class_labels: tuple[str, ...]) -> ModelPrediction:
    """Shared multiclass decode for every classifier adapter's `predict_one()` (2026-08-06).
    ``probabilities`` is one `predict_proba()` row; ``classes_seen`` is the fitted model's own
    ``classes_`` — the float label indices it actually saw during `fit()`, not necessarily every
    index in ``class_labels`` nor contiguous (a rare scoreline missing entirely from the training
    split simply never becomes one of the model's known classes). Every label in ``class_labels``
    the model never saw gets an honest 0.0 rather than a missing key, so callers always see the
    market's complete, stable label space regardless of what a given training run happened to
    observe."""
    seen = {class_labels[int(class_index)]: float(p) for class_index, p in zip(classes_seen, probabilities)}
    distribution = {label: seen.get(label, 0.0) for label in class_labels}
    best_label = max(distribution, key=distribution.get)
    best_probability = distribution[best_label]
    return ModelPrediction(
        raw_score=logit(best_probability), probability=best_probability, value=best_label, distribution=distribution
    )

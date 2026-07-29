"""Shared numeric helpers for ML adapters — same overflow-safe sigmoid/logit shape already used by
`infrastructure/predictors/weighted_scoring.py` and `infrastructure/calibration/platt_scaling_calibrator.py`,
kept here once rather than re-copied a fourth/fifth time.
"""

from __future__ import annotations

import math


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

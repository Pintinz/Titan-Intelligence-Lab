"""Platt-scaling Probability Calibration adapter (Milestone 9 Part 4 "Probability Calibration
Engine"). Fits a 2-parameter logistic regression — calibrated = sigmoid(A * logit(raw) + B) —
per model, from that model's own `PredictionOutcome` history. Pure-Python gradient descent, no
ML framework dependency (docs/architecture.md §2 framework-independence rule — same posture as
Milestone 7's heuristic Similarity Engine, which also avoided an ML library dependency).

Until `fit()` has been called for a model (no outcome history yet), `calibrate()` returns the
identity mapping (A=1, B=0) — an honestly-scoped "no calibration data yet" default, not a faked
result (docs/decisions.md ADR-008 mock-first posture applied to "insufficient data" exactly as it
applies to "no adapter yet").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from modules.predictions.domain.value_objects import ModelId


def _logit(p: float, eps: float = 1e-6) -> float:
    clamped = min(max(p, eps), 1.0 - eps)
    return math.log(clamped / (1.0 - clamped))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass(frozen=True)
class PlattParameters:
    a: float = 1.0
    b: float = 0.0


@dataclass
class PlattScalingCalibrator:
    learning_rate: float = 0.1
    iterations: int = 500
    _params: dict[ModelId, PlattParameters] = field(default_factory=dict)

    async def calibrate(self, model_id: ModelId, raw_probability: float) -> float:
        params = self._params.get(model_id, PlattParameters())
        x = _logit(raw_probability)
        return _sigmoid(params.a * x + params.b)

    async def fit(self, model_id: ModelId, samples: list[tuple[float, bool]]) -> None:
        """Batch gradient descent on the logistic-regression log-loss over
        ``(logit(raw_probability), actual_outcome)`` pairs — the standard Platt-scaling fit."""
        if not samples:
            return

        xs = [_logit(raw) for raw, _ in samples]
        ys = [1.0 if outcome else 0.0 for _, outcome in samples]
        n = len(samples)

        a, b = 1.0, 0.0
        for _ in range(self.iterations):
            grad_a = 0.0
            grad_b = 0.0
            for x, y in zip(xs, ys):
                error = _sigmoid(a * x + b) - y
                grad_a += error * x
                grad_b += error
            a -= self.learning_rate * grad_a / n
            b -= self.learning_rate * grad_b / n

        self._params[model_id] = PlattParameters(a=a, b=b)

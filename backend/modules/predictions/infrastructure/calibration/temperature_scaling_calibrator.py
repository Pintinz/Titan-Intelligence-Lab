"""Temperature Scaling Probability Calibration adapter (Milestone 9.1) — a single learned scalar
``T`` per model: ``calibrated = sigmoid(logit(raw) / T)``. The simplest possible calibration map
(one parameter, monotonic by construction — it can only sharpen/soften confidence, never reorder
predictions), a lighter-weight alternative to `PlattScalingCalibrator`'s 2-parameter fit. Pure-
Python gradient descent, same no-framework-dependency posture as the Platt adapter. Until `fit()`
has been called for a model, `calibrate()` uses ``T=1.0`` — the identity mapping.

Gradient derivation for one sample ``(x=logit(raw), y=outcome)`` with ``p = sigmoid(x/T)``:
``dL/dT = x*(y - p) / T**2`` (chain rule through the standard binary cross-entropy dL/dp and the
sigmoid derivative dp/dT — the ``p*(1-p)`` factors cancel). Averaged over the batch, this is the
same batch-gradient-descent shape `PlattScalingCalibrator.fit()` already uses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from modules.predictions.domain.calibration import CalibrationMetadata
from modules.predictions.domain.value_objects import ModelId

_MIN_TEMPERATURE = 1e-3


def _logit(p: float, eps: float = 1e-6) -> float:
    clamped = min(max(p, eps), 1.0 - eps)
    return math.log(clamped / (1.0 - clamped))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class TemperatureScalingCalibrator:
    learning_rate: float = 0.05
    iterations: int = 300
    _temperatures: dict = field(default_factory=dict)  # ModelId -> float
    _metadata: dict[ModelId, CalibrationMetadata] = field(default_factory=dict)

    async def calibrate(self, model_id: ModelId, raw_probability: float) -> float:
        temperature = self._temperatures.get(model_id, 1.0)
        return _sigmoid(_logit(raw_probability) / temperature)

    async def fit(self, model_id: ModelId, samples: list[tuple[float, bool]]) -> None:
        if not samples:
            return

        logits = [_logit(raw) for raw, _ in samples]
        ys = [1.0 if outcome else 0.0 for _, outcome in samples]
        n = len(samples)

        temperature = 1.0
        for _ in range(self.iterations):
            gradient_sum = sum(x * (y - _sigmoid(x / temperature)) for x, y in zip(logits, ys))
            dl_dt = gradient_sum / (n * temperature**2)
            temperature = max(temperature - self.learning_rate * dl_dt, _MIN_TEMPERATURE)

        self._temperatures[model_id] = temperature
        self._metadata[model_id] = CalibrationMetadata(sample_count=n, fitted_at=datetime.now(timezone.utc))

    async def is_fitted(self, model_id: ModelId) -> bool:
        return model_id in self._temperatures

    async def get_metadata(self, model_id: ModelId) -> CalibrationMetadata | None:
        return self._metadata.get(model_id)

"""Isotonic Regression Probability Calibration adapter (Milestone 9.1) —
`sklearn.isotonic.IsotonicRegression`, fit per model from that model's own (raw_probability,
actual_outcome) history. Non-parametric, unlike `PlattScalingCalibrator`'s 2-parameter logistic
fit: it learns an arbitrary monotonic step function, which fits better when a model's
miscalibration isn't a simple sigmoid distortion. Until `fit()` has been called for a model,
`calibrate()` returns the identity mapping — the same honest "no calibration data yet" default
every other calibrator in this codebase uses (docs/decisions.md ADR-008).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression

from modules.predictions.domain.value_objects import ModelId


@dataclass
class IsotonicRegressionCalibrator:
    _models: dict = field(default_factory=dict)  # ModelId -> fitted IsotonicRegression

    async def calibrate(self, model_id: ModelId, raw_probability: float) -> float:
        model = self._models.get(model_id)
        if model is None:
            return raw_probability
        return float(model.predict([raw_probability])[0])

    async def fit(self, model_id: ModelId, samples: list[tuple[float, bool]]) -> None:
        if not samples:
            return
        x = np.array([raw for raw, _ in samples])
        y = np.array([1.0 if outcome else 0.0 for _, outcome in samples])
        model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(x, y)
        self._models[model_id] = model

    async def is_fitted(self, model_id: ModelId) -> bool:
        return model_id in self._models

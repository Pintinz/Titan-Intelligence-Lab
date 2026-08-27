"""Platt-scaling Probability Calibration adapter (Milestone 9 Part 4 "Probability Calibration
Engine"). Fits a 2-parameter logistic regression — calibrated = sigmoid(A * logit(raw) + B) —
per model, from that model's own `PredictionOutcome` history. Pure-Python gradient descent, no
ML framework dependency (docs/architecture.md §2 framework-independence rule — same posture as
Milestone 7's heuristic Similarity Engine, which also avoided an ML library dependency).

Until `fit()` has been called for a model (no outcome history yet), `calibrate()` returns the
identity mapping (A=1, B=0) — an honestly-scoped "no calibration data yet" default, not a faked
result (docs/decisions.md ADR-008 mock-first posture applied to "insufficient data" exactly as it
applies to "no adapter yet").

Phase 3 audit fix: `_params` alone is an in-memory, per-process cache — a `fit()` call in one
process (e.g. a Celery worker) never reached `calibrate()` in another process (e.g. the API
server), silently leaving that process's live inference on the unfitted identity transform. The
optional `repository` now backs both: `fit()` persists the newly-fitted parameters, and
`calibrate()` reads through the repository on a cache miss before falling back to identity —
so a fit reaches every process regardless of which one ran it. `repository=None` (the default)
preserves the exact previous in-memory-only behavior for any caller/test that doesn't wire one.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from modules.predictions.domain.calibration import CalibrationMetadata, PlattCalibrationParameters
from modules.predictions.domain.value_objects import ModelId
from modules.predictions.ports.calibration_parameters_repository import CalibrationParametersRepositoryPort

logger = logging.getLogger("titaniq.predictions")


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
    repository: CalibrationParametersRepositoryPort | None = None
    _params: dict[ModelId, PlattParameters] = field(default_factory=dict)
    # Section 31 audit fix (2026-08-23): tracks which models `fit()` has genuinely run gradient
    # descent for in THIS process, for the `repository=None` fallback path only — `_params` alone
    # can't answer "is_fitted" because `calibrate()`'s own cache-fill (below) caches the identity
    # default on a miss too, making a never-fitted model indistinguishable from a fitted one by
    # cache presence alone.
    _fitted_model_ids: set[ModelId] = field(default_factory=set)
    # Phase 4 (Calibration Integrity) — `get_metadata()`'s in-memory-mode source (`repository=None`
    # callers/tests). Populated alongside `_fitted_model_ids` in `fit()`, never separately.
    _metadata: dict[ModelId, CalibrationMetadata] = field(default_factory=dict)

    async def calibrate(self, model_id: ModelId, raw_probability: float) -> float:
        params = self._params.get(model_id)
        if params is None and self.repository is not None:
            persisted = await self.repository.get(model_id)
            params = PlattParameters(a=persisted.a, b=persisted.b) if persisted is not None else PlattParameters()
            self._params[model_id] = params
        params = params or PlattParameters()
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

        if not (math.isfinite(a) and math.isfinite(b)):
            # A degenerate sample set (e.g. every outcome the same class) can send gradient
            # descent to +/-inf or NaN. Persisting/caching that would make every future
            # `calibrate()` call for this model return NaN (`sigmoid(nan)` is NaN) — silently
            # corrupting every prediction's published probability. Treat as a failed fit instead:
            # leave whatever parameters (or identity default) were already active untouched.
            logger.error(
                "platt_scaling_calibrator.fit_diverged",
                extra={"model_id": str(model_id.value), "sample_count": n, "a": a, "b": b},
            )
            return

        self._params[model_id] = PlattParameters(a=a, b=b)
        self._fitted_model_ids.add(model_id)
        # Real wall-clock time, not a caller-supplied `now` (unlike this codebase's usual explicit
        # `now`-threading convention) — `CalibratorPort.fit()` takes no `now` parameter. Harmless
        # in production (a fit's "when it happened" genuinely is wall-clock time); only a
        # testability wrinkle for a caller trying to fix `now` to a historical value.
        fitted_at = datetime.now(timezone.utc)
        self._metadata[model_id] = CalibrationMetadata(sample_count=n, fitted_at=fitted_at)
        if self.repository is not None:
            await self.repository.upsert(
                PlattCalibrationParameters(model_id=model_id, a=a, b=b, sample_count=n, fitted_at=fitted_at)
            )

    async def is_fitted(self, model_id: ModelId) -> bool:
        if self.repository is not None:
            return await self.repository.get(model_id) is not None
        return model_id in self._fitted_model_ids

    async def get_metadata(self, model_id: ModelId) -> CalibrationMetadata | None:
        if self.repository is not None:
            persisted = await self.repository.get(model_id)
            if persisted is None:
                return None
            return CalibrationMetadata(sample_count=persisted.sample_count, fitted_at=persisted.fitted_at)
        return self._metadata.get(model_id)

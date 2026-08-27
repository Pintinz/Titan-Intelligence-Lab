"""Probability Calibration port (Milestone 9 Part 4 "Probability Calibration Engine").

Kept separate from `PredictorPort`: a predictor scores a market; a calibrator maps that
predictor's raw output onto a well-calibrated probability using that *model's own* observed
outcome history (docs/prediction_markets.md — "Probability Calibration Method" per market
record). Swappable independently — e.g. a future isotonic-regression adapter implements this
same port without touching any `PredictorPort` implementation.
"""

from __future__ import annotations

from typing import Protocol

from modules.predictions.domain.calibration import CalibrationMetadata
from modules.predictions.domain.value_objects import ModelId


class CalibratorPort(Protocol):
    async def calibrate(self, model_id: ModelId, raw_probability: float) -> float:
        """Maps a predictor's raw [0, 1] probability estimate onto a calibrated probability for
        ``model_id``, using whatever calibration parameters `fit()` has previously produced for
        that model. Returns ``raw_probability`` unchanged if no calibration has been fitted yet
        (identity mapping is itself a valid, honestly-scoped calibration — docs/decisions.md
        ADR-008 mock-first/adapter-swap posture applies equally to "no data yet")."""
        ...

    async def fit(self, model_id: ModelId, samples: list[tuple[float, bool]]) -> None:
        """Fits/refits ``model_id``'s calibration parameters from ``samples`` — each a
        (raw_probability, actual_outcome) pair drawn from `PredictionOutcome` history. Called by
        `ModelRegistryService` whenever enough new outcomes have accumulated to re-calibrate."""
        ...

    async def is_fitted(self, model_id: ModelId) -> bool:
        """Whether `fit()` has ever actually produced real parameters for ``model_id`` — never
        inferred from whether `calibrate()` has been called (its identity-mapping default for an
        unfitted model is itself a valid return value, indistinguishable from a genuine fit unless
        this is tracked separately). Lets a caller (Section 31 audit fix) refuse to present a
        pass-through probability as "calibrated" when no calibration has actually happened yet."""
        ...

    async def get_metadata(self, model_id: ModelId) -> CalibrationMetadata | None:
        """Phase 4 (Calibration Integrity) — how much evidence backed ``model_id``'s currently
        active fit and when it was fitted, or `None` if `is_fitted(model_id)` would return
        `False`. Lets a caller distinguish FITTED from STALE (parameters exist but haven't been
        refit in too long) without the calibrator exposing its internal (a, b)/step-function
        parameters — the same "report the fact, not the internals" posture `is_fitted()` already
        established."""
        ...

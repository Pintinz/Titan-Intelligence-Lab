"""Calibration Reporting domain (Milestone 9.1 "Calibration Reports"/"Reliability Curves").
Distinct from `modules.predictions.ports.calibrator.CalibratorPort` (which only maps a raw
probability to a calibrated one) — this is the *evaluation* of how well-calibrated a model's
output already is, computed from the same ``(probability, actual_outcome)`` sample shape
`CalibratorPort.fit()` consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CalibrationMethod(str, Enum):
    NONE = "none"  # identity mapping — no calibrator has been fit for this model yet
    PLATT_SCALING = "platt_scaling"
    ISOTONIC_REGRESSION = "isotonic_regression"
    TEMPERATURE_SCALING = "temperature_scaling"


@dataclass(frozen=True)
class ReliabilityBin:
    """One bucket of a reliability diagram — predicted-probability range vs. observed frequency."""

    bin_index: int
    predicted_mean: float
    actual_rate: float
    sample_count: int


@dataclass(frozen=True)
class ReliabilityCurve:
    bins: tuple[ReliabilityBin, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CalibrationReport:
    """"Only calibrated probabilities may be returned" (Milestone 9.1) is a policy this report
    lets a human *verify* — Expected Calibration Error near 0 and a reliability curve hugging the
    diagonal both indicate the policy is actually being honored, not just declared."""

    method: CalibrationMethod
    sample_count: int
    expected_calibration_error: float
    brier_score: float
    reliability_curve: ReliabilityCurve
    generated_at: datetime

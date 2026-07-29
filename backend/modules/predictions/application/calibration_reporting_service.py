"""Builds `CalibrationReport`s (Milestone 9.1) from a model's own (calibrated_probability,
actual_outcome) sample history — pure computation, no persistence. A `calibration_report_ref`
pointer on `ModelDefinition` (task #163) is where a report gets stored once the Model Registry
migration (task #169) adds a table for it; this service only computes the report itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.predictions.domain.calibration import CalibrationMethod, CalibrationReport, ReliabilityBin, ReliabilityCurve

Sample = tuple[float, bool]


def build_reliability_curve(samples: list[Sample], n_bins: int = 10) -> ReliabilityCurve:
    if not samples:
        return ReliabilityCurve(bins=())

    buckets: list[list[Sample]] = [[] for _ in range(n_bins)]
    for probability, outcome in samples:
        index = min(int(probability * n_bins), n_bins - 1)
        buckets[index].append((probability, outcome))

    bins = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        predicted_mean = sum(p for p, _ in bucket) / len(bucket)
        actual_rate = sum(1 for _, o in bucket if o) / len(bucket)
        bins.append(ReliabilityBin(bin_index=i, predicted_mean=predicted_mean, actual_rate=actual_rate, sample_count=len(bucket)))
    return ReliabilityCurve(bins=tuple(bins))


def _expected_calibration_error(curve: ReliabilityCurve, total_samples: int) -> float:
    if total_samples == 0:
        return 0.0
    return sum(abs(b.predicted_mean - b.actual_rate) * (b.sample_count / total_samples) for b in curve.bins)


def _brier_score(samples: list[Sample]) -> float:
    if not samples:
        return 0.0
    return sum((probability - (1.0 if outcome else 0.0)) ** 2 for probability, outcome in samples) / len(samples)


@dataclass
class CalibrationReportBuilder:
    n_bins: int = 10

    def build(self, method: CalibrationMethod, samples: list[Sample], now: datetime) -> CalibrationReport:
        curve = build_reliability_curve(samples, n_bins=self.n_bins)
        return CalibrationReport(
            method=method,
            sample_count=len(samples),
            expected_calibration_error=_expected_calibration_error(curve, len(samples)),
            brier_score=_brier_score(samples),
            reliability_curve=curve,
            generated_at=now,
        )

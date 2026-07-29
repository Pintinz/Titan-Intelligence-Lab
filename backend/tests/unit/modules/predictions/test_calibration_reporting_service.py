from __future__ import annotations

from datetime import datetime, timezone

import pytest

from modules.predictions.application.calibration_reporting_service import (
    CalibrationReportBuilder,
    build_reliability_curve,
)
from modules.predictions.domain.calibration import CalibrationMethod

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


class TestBuildReliabilityCurve:
    def test_empty_samples_produces_no_bins(self):
        curve = build_reliability_curve([])
        assert curve.bins == ()

    def test_perfectly_calibrated_samples_have_matching_predicted_and_actual(self):
        # 10 samples all at raw probability 0.9, 9 correct, 1 wrong -> actual_rate == 0.9 exactly.
        samples = [(0.9, True)] * 9 + [(0.9, False)] * 1
        curve = build_reliability_curve(samples, n_bins=10)

        assert len(curve.bins) == 1
        bucket = curve.bins[0]
        assert bucket.predicted_mean == pytest.approx(0.9)
        assert bucket.actual_rate == pytest.approx(0.9)
        assert bucket.sample_count == 10

    def test_samples_split_across_bins(self):
        samples = [(0.05, False)] * 5 + [(0.95, True)] * 5
        curve = build_reliability_curve(samples, n_bins=10)
        assert len(curve.bins) == 2

    def test_probability_of_exactly_one_falls_in_last_bin(self):
        curve = build_reliability_curve([(1.0, True)], n_bins=10)
        assert curve.bins[0].bin_index == 9


class TestCalibrationReportBuilder:
    def test_well_calibrated_samples_have_low_ece_and_brier(self):
        builder = CalibrationReportBuilder()
        samples = [(0.9, True)] * 90 + [(0.9, False)] * 10  # exactly 90% actual rate at 0.9 predicted

        report = builder.build(CalibrationMethod.PLATT_SCALING, samples, T0)

        assert report.method is CalibrationMethod.PLATT_SCALING
        assert report.sample_count == 100
        assert report.expected_calibration_error == pytest.approx(0.0, abs=1e-6)
        assert report.brier_score < 0.1
        assert report.generated_at == T0

    def test_badly_calibrated_samples_have_high_ece(self):
        builder = CalibrationReportBuilder()
        # predicts 0.95 confidence but is only right half the time — badly overconfident.
        samples = [(0.95, True)] * 50 + [(0.95, False)] * 50

        report = builder.build(CalibrationMethod.NONE, samples, T0)

        assert report.expected_calibration_error == pytest.approx(0.45, abs=0.01)
        assert report.brier_score > 0.4

    def test_empty_samples_produce_zeroed_report(self):
        builder = CalibrationReportBuilder()
        report = builder.build(CalibrationMethod.ISOTONIC_REGRESSION, [], T0)

        assert report.sample_count == 0
        assert report.expected_calibration_error == 0.0
        assert report.brier_score == 0.0
        assert report.reliability_curve.bins == ()

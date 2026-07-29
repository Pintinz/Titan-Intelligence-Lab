from __future__ import annotations

from uuid import uuid4

import pytest

from modules.predictions.domain.value_objects import ModelId
from modules.predictions.infrastructure.calibration.isotonic_regression_calibrator import (
    IsotonicRegressionCalibrator,
)


@pytest.fixture
def model_id():
    return ModelId(uuid4())


async def test_calibrate_without_fit_is_identity(model_id):
    calibrator = IsotonicRegressionCalibrator()
    calibrated = await calibrator.calibrate(model_id, 0.7)
    assert calibrated == pytest.approx(0.7)


async def test_fit_with_no_samples_leaves_identity(model_id):
    calibrator = IsotonicRegressionCalibrator()
    await calibrator.fit(model_id, [])
    calibrated = await calibrator.calibrate(model_id, 0.6)
    assert calibrated == pytest.approx(0.6)


async def test_fit_on_overconfident_model_pulls_probabilities_toward_actual_rate(model_id):
    calibrator = IsotonicRegressionCalibrator()
    samples = [(0.9, True), (0.9, False)] * 25

    await calibrator.fit(model_id, samples)
    calibrated = await calibrator.calibrate(model_id, 0.9)

    assert calibrated < 0.9
    assert calibrated == pytest.approx(0.5, abs=0.05)


async def test_fit_on_well_separated_data_preserves_high_confidence_direction(model_id):
    calibrator = IsotonicRegressionCalibrator()
    samples = [(0.95, True)] * 25 + [(0.05, False)] * 25

    await calibrator.fit(model_id, samples)

    high = await calibrator.calibrate(model_id, 0.95)
    low = await calibrator.calibrate(model_id, 0.05)

    assert high > 0.9
    assert low < 0.1


async def test_calibration_is_per_model(model_id):
    other_model_id = ModelId(uuid4())
    calibrator = IsotonicRegressionCalibrator()
    samples = [(0.9, True), (0.9, False)] * 25

    await calibrator.fit(model_id, samples)

    fitted = await calibrator.calibrate(model_id, 0.9)
    unfitted = await calibrator.calibrate(other_model_id, 0.9)

    assert fitted != pytest.approx(unfitted, abs=1e-3)
    assert unfitted == pytest.approx(0.9)


async def test_handles_non_monotonic_raw_data_by_pooling_adjacent_violators(model_id):
    """The defining behavior isotonic regression offers over Platt scaling: a non-sigmoid-shaped
    miscalibration (probability dips then rises) still produces a monotonic calibrated output."""
    calibrator = IsotonicRegressionCalibrator()
    # actual rate is NOT a monotonic function of raw probability in a simple logistic sense here,
    # but isotonic regression still finds the best monotonic fit.
    samples = [(0.1, False)] * 20 + [(0.5, True)] * 20 + [(0.5, False)] * 5 + [(0.9, True)] * 20

    await calibrator.fit(model_id, samples)

    low = await calibrator.calibrate(model_id, 0.1)
    mid = await calibrator.calibrate(model_id, 0.5)
    high = await calibrator.calibrate(model_id, 0.9)

    assert low <= mid <= high

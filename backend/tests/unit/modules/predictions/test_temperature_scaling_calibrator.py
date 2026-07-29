from __future__ import annotations

from uuid import uuid4

import pytest

from modules.predictions.domain.value_objects import ModelId
from modules.predictions.infrastructure.calibration.temperature_scaling_calibrator import (
    TemperatureScalingCalibrator,
)


@pytest.fixture
def model_id():
    return ModelId(uuid4())


async def test_calibrate_without_fit_is_identity(model_id):
    calibrator = TemperatureScalingCalibrator()
    calibrated = await calibrator.calibrate(model_id, 0.7)
    assert calibrated == pytest.approx(0.7, abs=1e-4)


async def test_fit_with_no_samples_leaves_identity(model_id):
    calibrator = TemperatureScalingCalibrator()
    await calibrator.fit(model_id, [])
    calibrated = await calibrator.calibrate(model_id, 0.6)
    assert calibrated == pytest.approx(0.6, abs=1e-4)


async def test_fit_on_overconfident_model_pulls_probabilities_toward_actual_rate(model_id):
    """Unlike Platt/isotonic (which fit a bias term too), temperature scaling has exactly one
    global parameter and is symmetric around 0.5 — for data this uninformative (0.9 raw
    confidence, 50/50 actual outcome) the true MLE temperature is infinite, so gradient descent
    only asymptotically approaches (not reaches) 0.5 within a finite iteration budget. The
    meaningful, honestly-testable property is direction and magnitude, not exact convergence."""
    calibrator = TemperatureScalingCalibrator()
    samples = [(0.9, True), (0.9, False)] * 25

    await calibrator.fit(model_id, samples)
    calibrated = await calibrator.calibrate(model_id, 0.9)

    assert calibrated < 0.75  # meaningfully softened from the original 0.9 overconfidence


async def test_calibration_is_monotonic_in_raw_probability(model_id):
    calibrator = TemperatureScalingCalibrator()
    samples = [(0.95, True)] * 25 + [(0.05, False)] * 25
    await calibrator.fit(model_id, samples)

    low = await calibrator.calibrate(model_id, 0.2)
    mid = await calibrator.calibrate(model_id, 0.5)
    high = await calibrator.calibrate(model_id, 0.8)

    assert low < mid < high

    # Temperature scaling is always symmetric around 0.5, unlike Platt/isotonic — 0.5 always maps
    # to 0.5 regardless of what was fit, since logit(0.5) == 0 and 0/T == 0 for any T.
    assert mid == pytest.approx(0.5, abs=1e-4)


async def test_calibration_is_per_model(model_id):
    other_model_id = ModelId(uuid4())
    calibrator = TemperatureScalingCalibrator()
    samples = [(0.9, True), (0.9, False)] * 25

    await calibrator.fit(model_id, samples)

    fitted = await calibrator.calibrate(model_id, 0.9)
    unfitted = await calibrator.calibrate(other_model_id, 0.9)

    assert fitted != pytest.approx(unfitted, abs=1e-3)
    assert unfitted == pytest.approx(0.9, abs=1e-4)


async def test_well_calibrated_model_keeps_temperature_near_one(model_id):
    """A model whose raw probabilities already match observed frequency shouldn't need much
    correction — temperature should stay close to 1.0."""
    calibrator = TemperatureScalingCalibrator()
    samples = [(0.9, True)] * 9 + [(0.9, False)] * 1 + [(0.1, False)] * 9 + [(0.1, True)] * 1

    await calibrator.fit(model_id, samples)
    temperature = calibrator._temperatures[model_id]

    assert temperature == pytest.approx(1.0, abs=0.3)

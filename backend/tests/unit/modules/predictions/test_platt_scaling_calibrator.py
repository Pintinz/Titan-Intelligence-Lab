from __future__ import annotations

from uuid import uuid4

import pytest

from modules.predictions.domain.value_objects import ModelId
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator


@pytest.fixture
def model_id():
    return ModelId(uuid4())


@pytest.mark.asyncio
async def test_calibrate_without_fit_is_identity(model_id):
    calibrator = PlattScalingCalibrator()

    calibrated = await calibrator.calibrate(model_id, 0.7)

    assert calibrated == pytest.approx(0.7, abs=1e-4)


@pytest.mark.asyncio
async def test_fit_with_no_samples_leaves_identity(model_id):
    calibrator = PlattScalingCalibrator()

    await calibrator.fit(model_id, [])
    calibrated = await calibrator.calibrate(model_id, 0.6)

    assert calibrated == pytest.approx(0.6, abs=1e-4)


@pytest.mark.asyncio
async def test_fit_on_overconfident_model_pulls_probabilities_toward_actual_rate(model_id):
    """A model that always outputs 0.9 raw probability but is only actually right half the time
    is overconfident — Platt scaling should pull its calibrated output down toward 0.5."""
    calibrator = PlattScalingCalibrator()
    samples = [(0.9, True), (0.9, False)] * 25

    await calibrator.fit(model_id, samples)
    calibrated = await calibrator.calibrate(model_id, 0.9)

    assert calibrated < 0.9
    assert calibrated == pytest.approx(0.5, abs=0.05)


@pytest.mark.asyncio
async def test_fit_on_well_separated_data_preserves_high_confidence_direction(model_id):
    calibrator = PlattScalingCalibrator()
    samples = [(0.95, True)] * 25 + [(0.05, False)] * 25

    await calibrator.fit(model_id, samples)

    high = await calibrator.calibrate(model_id, 0.95)
    low = await calibrator.calibrate(model_id, 0.05)

    assert high > 0.9
    assert low < 0.1


@pytest.mark.asyncio
async def test_calibration_is_monotonic_in_raw_probability(model_id):
    calibrator = PlattScalingCalibrator()
    samples = [(0.95, True)] * 25 + [(0.05, False)] * 25
    await calibrator.fit(model_id, samples)

    low = await calibrator.calibrate(model_id, 0.2)
    mid = await calibrator.calibrate(model_id, 0.5)
    high = await calibrator.calibrate(model_id, 0.8)

    assert low < mid < high


@pytest.mark.asyncio
async def test_calibration_is_per_model(model_id):
    other_model_id = ModelId(uuid4())
    calibrator = PlattScalingCalibrator()
    samples = [(0.9, True), (0.9, False)] * 25

    await calibrator.fit(model_id, samples)

    fitted = await calibrator.calibrate(model_id, 0.9)
    unfitted = await calibrator.calibrate(other_model_id, 0.9)

    assert fitted != pytest.approx(unfitted, abs=1e-3)
    assert unfitted == pytest.approx(0.9, abs=1e-4)

from __future__ import annotations

from uuid import uuid4

import pytest

from modules.predictions.domain.value_objects import ModelId
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyCalibrationParametersRepository


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


# --- Phase 3 audit fix: cross-process durability via a real DB-backed repository -------------


@pytest.mark.asyncio
async def test_fit_persists_to_repository(model_id, sqlite_session):
    repo = SqlAlchemyCalibrationParametersRepository(session=sqlite_session)
    calibrator = PlattScalingCalibrator(repository=repo)
    samples = [(0.9, True), (0.9, False)] * 25

    await calibrator.fit(model_id, samples)
    await sqlite_session.commit()

    persisted = await repo.get(model_id)
    assert persisted is not None
    assert persisted.sample_count == 50
    assert persisted.a != 1.0 or persisted.b != 0.0  # actually fitted, not the identity default


@pytest.mark.asyncio
async def test_calibrate_reads_through_repository_on_cache_miss(model_id, sqlite_session):
    """The exact bug this fix closes: a `fit()` in one process (simulated here by a first
    `PlattScalingCalibrator` instance) must reach `calibrate()` in a completely separate instance
    with its own empty in-memory `_params` cache (simulating a different OS process) — proving a
    fit reaches every process via the shared DB-backed repository, not just the process that ran
    it."""
    fitting_instance = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))
    samples = [(0.95, True)] * 25 + [(0.05, False)] * 25
    await fitting_instance.fit(model_id, samples)
    await sqlite_session.commit()

    serving_instance = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))
    calibrated_high = await serving_instance.calibrate(model_id, 0.95)
    calibrated_low = await serving_instance.calibrate(model_id, 0.05)

    # If the fit never reached this instance, both would fall back to the identity default.
    assert calibrated_high > 0.9
    assert calibrated_low < 0.1


@pytest.mark.asyncio
async def test_calibrate_falls_back_to_identity_when_repository_has_no_row(model_id, sqlite_session):
    calibrator = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))

    calibrated = await calibrator.calibrate(model_id, 0.7)

    assert calibrated == pytest.approx(0.7, abs=1e-4)

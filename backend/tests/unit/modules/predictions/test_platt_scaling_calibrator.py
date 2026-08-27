from __future__ import annotations

import math
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


# --- Section 31 audit fix: is_fitted() must never be inferred from calibrate()'s own cache -----


@pytest.mark.asyncio
async def test_is_fitted_is_false_before_any_fit_in_memory(model_id):
    calibrator = PlattScalingCalibrator()

    assert await calibrator.is_fitted(model_id) is False


@pytest.mark.asyncio
async def test_is_fitted_stays_false_after_calibrate_caches_the_identity_default(model_id):
    """The exact bug this fix closes: `calibrate()` caches SOMETHING into `_params` even for a
    never-fitted model (the identity default), so `is_fitted` must not be derived from cache
    presence alone — only `fit()` genuinely running should flip it."""
    calibrator = PlattScalingCalibrator()

    await calibrator.calibrate(model_id, 0.7)

    assert await calibrator.is_fitted(model_id) is False


@pytest.mark.asyncio
async def test_is_fitted_is_true_in_memory_after_a_real_fit(model_id):
    calibrator = PlattScalingCalibrator()

    await calibrator.fit(model_id, [(0.9, True), (0.9, False)] * 25)

    assert await calibrator.is_fitted(model_id) is True


@pytest.mark.asyncio
async def test_is_fitted_with_no_samples_stays_false(model_id):
    """`fit([])` returns early without ever fitting anything — must not be reported as fitted."""
    calibrator = PlattScalingCalibrator()

    await calibrator.fit(model_id, [])

    assert await calibrator.is_fitted(model_id) is False


@pytest.mark.asyncio
async def test_is_fitted_reads_through_repository_across_processes(model_id, sqlite_session):
    fitting_instance = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))
    await fitting_instance.fit(model_id, [(0.9, True), (0.9, False)] * 25)
    await sqlite_session.commit()

    serving_instance = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))

    assert await serving_instance.is_fitted(model_id) is True


@pytest.mark.asyncio
async def test_is_fitted_false_with_repository_but_no_persisted_row(model_id, sqlite_session):
    calibrator = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))

    assert await calibrator.is_fitted(model_id) is False


# --- Phase 4 (Calibration Integrity): get_metadata() ------------------------------------------


@pytest.mark.asyncio
async def test_get_metadata_is_none_before_any_fit_in_memory(model_id):
    calibrator = PlattScalingCalibrator()

    assert await calibrator.get_metadata(model_id) is None


@pytest.mark.asyncio
async def test_get_metadata_reports_sample_count_and_fitted_at_after_a_real_fit(model_id):
    calibrator = PlattScalingCalibrator()

    await calibrator.fit(model_id, [(0.9, True), (0.9, False)] * 25)
    metadata = await calibrator.get_metadata(model_id)

    assert metadata is not None
    assert metadata.sample_count == 50
    assert metadata.fitted_at is not None


@pytest.mark.asyncio
async def test_get_metadata_reads_through_repository_across_processes(model_id, sqlite_session):
    fitting_instance = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))
    await fitting_instance.fit(model_id, [(0.9, True), (0.9, False)] * 25)
    await sqlite_session.commit()

    serving_instance = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))
    metadata = await serving_instance.get_metadata(model_id)

    assert metadata is not None
    assert metadata.sample_count == 50


@pytest.mark.asyncio
async def test_get_metadata_is_none_with_repository_but_no_persisted_row(model_id, sqlite_session):
    calibrator = PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session))

    assert await calibrator.get_metadata(model_id) is None


# --- Phase 4: fit() must never persist/cache a diverged (non-finite) result --------------------


@pytest.mark.asyncio
async def test_fit_on_degenerate_all_one_class_data_never_produces_non_finite_parameters(model_id):
    """A sample set where every outcome is the same class is the classic logistic-regression
    divergence case — gradient descent pushes toward +/-infinity chasing perfect separation.
    Whatever `fit()` does here, `calibrate()` must never return NaN/Inf afterward (that would
    poison every future prediction's published probability with an unusable number)."""
    calibrator = PlattScalingCalibrator()
    samples = [(0.5 + i * 1e-6, True) for i in range(30)]  # every outcome positive — degenerate

    await calibrator.fit(model_id, samples)
    calibrated = await calibrator.calibrate(model_id, 0.7)

    assert math.isfinite(calibrated)

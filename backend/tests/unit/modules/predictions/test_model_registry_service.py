from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.model_registry_service import (
    InvalidDeploymentModeError,
    InvalidModelLifecycleTransitionError,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    ModelRegistryService,
)
from modules.predictions.domain.value_objects import MarketId, ModelId, ModelStatus
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def service(model_repo):
    return ModelRegistryService(models=model_repo)


@pytest.fixture
def model_loader():
    # `artifact_store=None` is safe here — these tests only ever seed/inspect `_cache` directly,
    # never call `.load()`, so the artifact store is never actually touched.
    return ModelLoaderService(artifact_store=None)


@pytest.fixture
def service_with_loader(model_repo, model_loader):
    return ModelRegistryService(models=model_repo, model_loader=model_loader)


@pytest.fixture
def market_id():
    return MarketId(uuid4())


async def _register(service, market_id, key="football.match_result.heuristic_logistic", version=1, **overrides):
    kwargs = dict(market_id=market_id, model_key=key, version=version, algorithm="heuristic_logistic_v1", now=T0)
    kwargs.update(overrides)
    return await service.register(**kwargs)


@pytest.mark.asyncio
async def test_register_creates_candidate(service, market_id):
    model = await _register(service, market_id)

    assert model.status is ModelStatus.CANDIDATE


@pytest.mark.asyncio
async def test_register_duplicate_key_version_raises(service, market_id):
    await _register(service, market_id)

    with pytest.raises(ModelAlreadyRegisteredError):
        await _register(service, market_id)


@pytest.mark.asyncio
async def test_unknown_model_id_raises_not_found(service):
    with pytest.raises(ModelNotFoundError):
        await service.retire(ModelId(uuid4()), now=T0)


@pytest.mark.asyncio
async def test_cannot_promote_candidate_directly_to_champion(service, market_id):
    model = await _register(service, market_id)

    with pytest.raises(InvalidModelLifecycleTransitionError):
        await service.promote_to_champion(model.id, approved_by="cto", now=T0)


@pytest.mark.asyncio
async def test_promote_candidate_to_challenger_to_champion(service, market_id):
    model = await _register(service, market_id)
    challenger = await service.promote_to_challenger(model.id)
    assert challenger.status is ModelStatus.CHALLENGER

    champion = await service.promote_to_champion(challenger.id, approved_by="cto", now=T0)

    assert champion.status is ModelStatus.CHAMPION
    assert champion.approved_by == "cto"
    assert champion.promoted_at == T0


@pytest.mark.asyncio
async def test_promoting_new_champion_retires_old_one(service, market_id, model_repo):
    first = await _register(service, market_id, key="model.v1", version=1)
    await service.promote_to_challenger(first.id)
    first_champion = await service.promote_to_champion(first.id, approved_by="cto", now=T0)

    second = await _register(service, market_id, key="model.v2", version=1)
    await service.promote_to_challenger(second.id)
    second_champion = await service.promote_to_champion(second.id, approved_by="cto", now=T0 + timedelta(days=1))

    retired_first = await model_repo.get(first_champion.id)
    assert retired_first.status is ModelStatus.RETIRED
    assert retired_first.retired_at == T0 + timedelta(days=1)

    current_champion = await model_repo.get_champion(market_id)
    assert current_champion.id == second_champion.id


@pytest.mark.asyncio
async def test_only_one_champion_per_market_at_a_time(service, market_id, model_repo):
    first = await _register(service, market_id, key="model.v1", version=1)
    await service.promote_to_challenger(first.id)
    await service.promote_to_champion(first.id, approved_by="cto", now=T0)

    second = await _register(service, market_id, key="model.v2", version=1)
    await service.promote_to_challenger(second.id)
    await service.promote_to_champion(second.id, approved_by="cto", now=T0 + timedelta(days=1))

    champions = await model_repo.list_by_status(market_id, ModelStatus.CHAMPION)
    assert len(champions) == 1


@pytest.mark.asyncio
async def test_rollback_reinstates_previous_champion(service, market_id, model_repo):
    first = await _register(service, market_id, key="model.v1", version=1)
    await service.promote_to_challenger(first.id)
    await service.promote_to_champion(first.id, approved_by="cto", now=T0)

    second = await _register(service, market_id, key="model.v2", version=1)
    await service.promote_to_challenger(second.id)
    await service.promote_to_champion(second.id, approved_by="cto", now=T0 + timedelta(days=1))

    rolled_back = await service.rollback(market_id, now=T0 + timedelta(days=2))

    assert rolled_back.id == first.id
    assert rolled_back.status is ModelStatus.CHAMPION

    demoted_second = await model_repo.get(second.id)
    assert demoted_second.status is ModelStatus.RETIRED


# --- Section 30 audit fix: promotion/rollback must invalidate the model loader's cache ---------


@pytest.mark.asyncio
async def test_promote_to_champion_invalidates_both_the_new_and_retired_models(
    service_with_loader, market_id, model_repo, model_loader,
):
    """`ModelLoaderService.invalidate()` has documented this exact call site since Milestone 9.1
    but was never actually wired to it (audit finding, 2026-08-23) — a stale cached artifact could
    keep serving under either the newly-promoted or the just-retired model id."""
    first = await _register(service_with_loader, market_id, key="model.v1", version=1)
    await service_with_loader.promote_to_challenger(first.id)
    await service_with_loader.promote_to_champion(first.id, approved_by="cto", now=T0)
    model_loader._cache[first.id] = object()  # simulates a real prediction having cached it

    second = await _register(service_with_loader, market_id, key="model.v2", version=1)
    await service_with_loader.promote_to_challenger(second.id)
    model_loader._cache[second.id] = object()  # a pre-promotion warm/test load, also stale after
    await service_with_loader.promote_to_champion(second.id, approved_by="cto", now=T0 + timedelta(days=1))

    assert first.id not in model_loader._cache
    assert second.id not in model_loader._cache


@pytest.mark.asyncio
async def test_promote_to_champion_without_a_loader_wired_does_not_error(service, market_id):
    """`model_loader=None` (the default) must behave exactly as before this fix — every existing
    caller/test that doesn't wire a loader is unaffected."""
    model = await _register(service, market_id)
    await service.promote_to_challenger(model.id)

    champion = await service.promote_to_champion(model.id, approved_by="cto", now=T0)

    assert champion.status is ModelStatus.CHAMPION


@pytest.mark.asyncio
async def test_rollback_invalidates_both_the_retired_and_reinstated_models(
    service_with_loader, market_id, model_repo, model_loader,
):
    first = await _register(service_with_loader, market_id, key="model.v1", version=1)
    await service_with_loader.promote_to_challenger(first.id)
    await service_with_loader.promote_to_champion(first.id, approved_by="cto", now=T0)

    second = await _register(service_with_loader, market_id, key="model.v2", version=1)
    await service_with_loader.promote_to_challenger(second.id)
    await service_with_loader.promote_to_champion(second.id, approved_by="cto", now=T0 + timedelta(days=1))
    model_loader._cache[first.id] = object()
    model_loader._cache[second.id] = object()

    await service_with_loader.rollback(market_id, now=T0 + timedelta(days=2))

    assert first.id not in model_loader._cache
    assert second.id not in model_loader._cache


@pytest.mark.asyncio
async def test_rollback_without_champion_raises(service, market_id):
    with pytest.raises(ModelNotFoundError):
        await service.rollback(market_id, now=T0)


@pytest.mark.asyncio
async def test_rollback_without_retired_history_raises(service, market_id):
    model = await _register(service, market_id)
    await service.promote_to_challenger(model.id)
    await service.promote_to_champion(model.id, approved_by="cto", now=T0)

    with pytest.raises(ModelNotFoundError):
        await service.rollback(market_id, now=T0)


@pytest.mark.asyncio
async def test_retire_champion_directly(service, market_id):
    model = await _register(service, market_id)
    await service.promote_to_challenger(model.id)
    champion = await service.promote_to_champion(model.id, approved_by="cto", now=T0)

    retired = await service.retire(champion.id, now=T0 + timedelta(days=1))

    assert retired.status is ModelStatus.RETIRED


@pytest.mark.asyncio
async def test_retire_already_retired_raises(service, market_id):
    model = await _register(service, market_id)
    await service.retire(model.id, now=T0)

    with pytest.raises(InvalidModelLifecycleTransitionError):
        await service.retire(model.id, now=T0)


@pytest.mark.asyncio
async def test_register_defaults_ml_fields_to_empty(service, market_id):
    model = await _register(service, market_id)

    assert model.framework is None
    assert model.dataset_version is None
    assert model.feature_versions == {}
    assert model.training_run_ref is None
    assert model.calibration_report_ref is None
    assert model.feature_importance_ref is None
    assert model.artifact_ref is None
    assert model.deployment_mode is None
    assert model.trained_at is None


@pytest.mark.asyncio
async def test_register_accepts_ml_metadata(service, market_id):
    model = await _register(
        service,
        market_id,
        key="football.match_result.lightgbm",
        framework="lightgbm",
        dataset_version=3,
        feature_versions={"football.shots_on_target": 2},
        training_run_ref="run-123",
        calibration_report_ref="calib-ref-1",
        feature_importance_ref="importance-ref-1",
        artifact_ref="artifacts/football/match_result/v1.bin",
        trained_at=T0,
    )

    assert model.framework == "lightgbm"
    assert model.dataset_version == 3
    assert model.feature_versions == {"football.shots_on_target": 2}
    assert model.training_run_ref == "run-123"
    assert model.calibration_report_ref == "calib-ref-1"
    assert model.feature_importance_ref == "importance-ref-1"
    assert model.artifact_ref == "artifacts/football/match_result/v1.bin"
    assert model.trained_at == T0


@pytest.mark.asyncio
async def test_set_deployment_mode_updates_model(service, market_id):
    model = await _register(service, market_id)

    updated = await service.set_deployment_mode(model.id, "shadow")

    assert updated.deployment_mode == "shadow"


@pytest.mark.asyncio
async def test_set_deployment_mode_to_none_clears_it(service, market_id):
    model = await _register(service, market_id)
    await service.set_deployment_mode(model.id, "canary")

    cleared = await service.set_deployment_mode(model.id, None)

    assert cleared.deployment_mode is None


@pytest.mark.asyncio
async def test_set_deployment_mode_rejects_invalid_value(service, market_id):
    model = await _register(service, market_id)

    with pytest.raises(InvalidDeploymentModeError):
        await service.set_deployment_mode(model.id, "invalid-mode")


@pytest.mark.asyncio
async def test_set_deployment_mode_unknown_model_raises(service):
    with pytest.raises(ModelNotFoundError):
        await service.set_deployment_mode(ModelId(uuid4()), "live")

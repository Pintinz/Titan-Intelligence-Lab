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
    PromotionPolicyViolationError,
    TrainingIntegrityError,
)
from modules.predictions.domain.model_comparison import ChallengerEvaluation, ComparisonMetrics, ComparisonVerdict
from modules.predictions.domain.value_objects import ChallengerEvaluationId, MarketId, ModelId, ModelStatus
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.persistence.in_memory_model_comparison_repository import (
    InMemoryModelComparisonRepository,
)

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


@pytest.fixture
def comparisons():
    return InMemoryModelComparisonRepository()


@pytest.fixture
def service_with_comparisons(model_repo, comparisons):
    return ModelRegistryService(models=model_repo, comparisons=comparisons)


def _comparison(market_id, challenger_id, champion_id, verdict, evaluated_at) -> ChallengerEvaluation:
    return ChallengerEvaluation(
        id=ChallengerEvaluationId(uuid4()), market_id=market_id, challenger_model_id=challenger_id,
        champion_model_id=champion_id, challenger_metrics=ComparisonMetrics(log_loss=0.4),
        champion_metrics=ComparisonMetrics(log_loss=0.5), verdict=verdict, decisive_metric="log_loss",
        holdout_sample_count=200, evaluated_at=evaluated_at,
    )


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


# --- Forensic audit §10: Contaminated Model Policy ----------------------------------------------


@pytest.mark.asyncio
async def test_promote_to_champion_refuses_a_compromised_challenger(service, market_id, model_repo):
    """A model `scripts/assess_training_integrity.py` flagged PROVENANCE_COMPROMISED (confirmed
    point-in-time leakage in its training data) must never become Champion — promoting it would
    silently reintroduce the exact contamination Critical Fix #1 closed at the data layer."""
    model = await _register(service, market_id)
    challenger = await service.promote_to_challenger(model.id)
    challenger.provenance_status = "PROVENANCE_COMPROMISED"
    await model_repo.upsert(challenger)

    with pytest.raises(TrainingIntegrityError):
        await service.promote_to_champion(challenger.id, approved_by="cto", now=T0)

    # And the challenger must genuinely still be a CHALLENGER — the rejected promotion must not
    # have partially applied (no champion, no retirement of anything, no status mutation at all).
    still_challenger = await model_repo.get(challenger.id)
    assert still_challenger.status is ModelStatus.CHALLENGER
    assert await model_repo.get_champion(market_id) is None


@pytest.mark.asyncio
async def test_promote_to_champion_allows_an_unverified_challenger(service, market_id):
    """PROVENANCE_UNVERIFIED (the honest default — "never checked", not "checked and compromised")
    must not be blocked by the same guard; only a model actively flagged compromised is refused."""
    model = await _register(service, market_id)
    challenger = await service.promote_to_challenger(model.id)
    assert challenger.provenance_status == "PROVENANCE_UNVERIFIED"

    champion = await service.promote_to_champion(challenger.id, approved_by="cto", now=T0)

    assert champion.status is ModelStatus.CHAMPION


@pytest.mark.asyncio
async def test_is_training_compromised_reflects_provenance_status(service, market_id, model_repo):
    model = await _register(service, market_id)
    assert model.is_training_compromised() is False

    model.provenance_status = "PROVENANCE_COMPROMISED"
    saved = await model_repo.upsert(model)
    assert saved.is_training_compromised() is True


# --- Forensic audit §11/§12: Champion Promotion Safety / ModelPromotionPolicy ------------------


@pytest.mark.asyncio
async def test_first_ever_promotion_for_a_market_skips_the_comparison_gate(
    service_with_comparisons, market_id,
):
    """Bootstrap case: nothing to compare a market's very first Champion against — the gate must
    not block this the way it would a second/third promotion."""
    model = await _register(service_with_comparisons, market_id)
    challenger = await service_with_comparisons.promote_to_challenger(model.id)

    champion = await service_with_comparisons.promote_to_champion(challenger.id, approved_by="cto", now=T0)

    assert champion.status is ModelStatus.CHAMPION


@pytest.mark.asyncio
async def test_promotion_with_no_wired_comparisons_repo_is_unaffected(service, market_id):
    """`comparisons=None` (the default) must behave exactly as before this fix — every existing
    caller/test/backfill script that doesn't wire one is unaffected, same posture as `model_loader`."""
    first = await _register(service, market_id, key="model.v1", version=1)
    await service.promote_to_challenger(first.id)
    await service.promote_to_champion(first.id, approved_by="cto", now=T0)

    second = await _register(service, market_id, key="model.v2", version=1)
    await service.promote_to_challenger(second.id)
    champion = await service.promote_to_champion(second.id, approved_by="cto", now=T0 + timedelta(days=1))

    assert champion.status is ModelStatus.CHAMPION


async def _promote_first_champion(service, market_id, now):
    first = await _register(service, market_id, key="model.v1", version=1)
    await service.promote_to_challenger(first.id)
    return await service.promote_to_champion(first.id, approved_by="cto", now=now)


@pytest.mark.asyncio
async def test_second_promotion_with_no_comparison_recorded_is_rejected(
    service_with_comparisons, market_id,
):
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)

    with pytest.raises(PromotionPolicyViolationError) as exc_info:
        await service_with_comparisons.promote_to_champion(challenger.id, approved_by="cto", now=T0 + timedelta(days=1))

    assert exc_info.value.reason_code == "COMPARISON_MISSING"


@pytest.mark.asyncio
async def test_second_promotion_with_champion_better_verdict_is_rejected(
    service_with_comparisons, market_id, comparisons,
):
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)
    await comparisons.record(_comparison(
        market_id, challenger.id, champion.id, ComparisonVerdict.CHAMPION_BETTER, T0 + timedelta(hours=1),
    ))

    with pytest.raises(PromotionPolicyViolationError) as exc_info:
        await service_with_comparisons.promote_to_champion(challenger.id, approved_by="cto", now=T0 + timedelta(days=1))

    assert exc_info.value.reason_code == "CANDIDATE_NOT_BETTER"


@pytest.mark.asyncio
async def test_second_promotion_with_inconclusive_verdict_is_rejected(
    service_with_comparisons, market_id, comparisons,
):
    """INCONCLUSIVE is deliberately treated the same as CHAMPION_BETTER for promotion purposes —
    "we couldn't tell" is not evidence the candidate is actually better."""
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)
    await comparisons.record(_comparison(
        market_id, challenger.id, champion.id, ComparisonVerdict.INCONCLUSIVE, T0 + timedelta(hours=1),
    ))

    with pytest.raises(PromotionPolicyViolationError) as exc_info:
        await service_with_comparisons.promote_to_champion(challenger.id, approved_by="cto", now=T0 + timedelta(days=1))

    assert exc_info.value.reason_code == "CANDIDATE_NOT_BETTER"


@pytest.mark.asyncio
async def test_second_promotion_with_stale_comparison_is_rejected(
    service_with_comparisons, market_id, comparisons,
):
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)
    # Favorable verdict, but recorded 10 days before the promotion attempt — past the default 7d
    # freshness window.
    await comparisons.record(_comparison(
        market_id, challenger.id, champion.id, ComparisonVerdict.CHALLENGER_BETTER, T0,
    ))

    with pytest.raises(PromotionPolicyViolationError) as exc_info:
        await service_with_comparisons.promote_to_champion(
            challenger.id, approved_by="cto", now=T0 + timedelta(days=10),
        )

    assert exc_info.value.reason_code == "COMPARISON_STALE"


@pytest.mark.asyncio
async def test_second_promotion_with_a_comparison_for_a_different_challenger_is_rejected(
    service_with_comparisons, market_id, comparisons,
):
    """A favorable comparison exists for the market, but not for THIS challenger — e.g. left over
    from an earlier Challenger that was never promoted. Must not be accepted as if it validates a
    different model just because it's the market's most recent recorded comparison."""
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    stale_challenger_id = ModelId(uuid4())
    await comparisons.record(_comparison(
        market_id, stale_challenger_id, champion.id, ComparisonVerdict.CHALLENGER_BETTER, T0 + timedelta(hours=1),
    ))
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)

    with pytest.raises(PromotionPolicyViolationError) as exc_info:
        await service_with_comparisons.promote_to_champion(challenger.id, approved_by="cto", now=T0 + timedelta(days=1))

    assert exc_info.value.reason_code == "COMPARISON_MISSING"


@pytest.mark.asyncio
async def test_second_promotion_with_fresh_favorable_comparison_succeeds(
    service_with_comparisons, market_id, comparisons, model_repo,
):
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)
    await comparisons.record(_comparison(
        market_id, challenger.id, champion.id, ComparisonVerdict.CHALLENGER_BETTER, T0 + timedelta(hours=1),
    ))

    new_champion = await service_with_comparisons.promote_to_champion(
        challenger.id, approved_by="cto", now=T0 + timedelta(days=1),
    )

    assert new_champion.status is ModelStatus.CHAMPION
    retired_first = await model_repo.get(champion.id)
    assert retired_first.status is ModelStatus.RETIRED


@pytest.mark.asyncio
async def test_naive_evaluated_at_from_a_real_db_round_trip_does_not_crash_the_staleness_check(
    service_with_comparisons, market_id, comparisons,
):
    """Regression: `SqlAlchemyModelComparisonRepository` round-trips a comparison through real
    SQLite, which drops tzinfo on read-back (ADR-007) — `InMemoryModelComparisonRepository` (every
    other test in this file) never exercises that, so this reproduces it directly by seeding a
    naive `evaluated_at`, exactly like a real fetched-from-SQLite row would have. Caught live by
    the forensic-audit brief's own "verify beyond unit tests" API-level test before this fix."""
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)
    naive_evaluation = _comparison(
        market_id, challenger.id, champion.id, ComparisonVerdict.CHALLENGER_BETTER,
        (T0 + timedelta(hours=1)).replace(tzinfo=None),
    )
    await comparisons.record(naive_evaluation)

    new_champion = await service_with_comparisons.promote_to_champion(
        challenger.id, approved_by="cto", now=T0 + timedelta(days=1),
    )

    assert new_champion.status is ModelStatus.CHAMPION


@pytest.mark.asyncio
async def test_rejected_promotion_does_not_retire_the_current_champion(
    service_with_comparisons, market_id, model_repo,
):
    """A rejected promotion attempt must leave production exactly as it was — the existing Champion
    still serving, nothing retired, nothing partially applied."""
    champion = await _promote_first_champion(service_with_comparisons, market_id, T0)
    second = await _register(service_with_comparisons, market_id, key="model.v2", version=1)
    challenger = await service_with_comparisons.promote_to_challenger(second.id)

    with pytest.raises(PromotionPolicyViolationError):
        await service_with_comparisons.promote_to_champion(challenger.id, approved_by="cto", now=T0 + timedelta(days=1))

    still_champion = await model_repo.get(champion.id)
    assert still_champion.status is ModelStatus.CHAMPION
    still_challenger = await model_repo.get(challenger.id)
    assert still_challenger.status is ModelStatus.CHALLENGER

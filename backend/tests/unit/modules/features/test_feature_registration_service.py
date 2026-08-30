from datetime import datetime, timedelta, timezone

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureNotFoundError,
    FeatureRegistrationService,
    InvalidFeatureDefinitionError,
    InvalidLifecycleTransitionError,
)
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureStatus

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.fixture
def lineage_service(lineage_repo, definition_repo):
    return FeatureLineageService(lineage=lineage_repo, definitions=definition_repo)


@pytest.fixture
def service(definition_repo, version_repo, lineage_service):
    return FeatureRegistrationService(definitions=definition_repo, versions=version_repo, lineage=lineage_service)


async def _register(service, key="football.team.form_index_last5", **overrides):
    kwargs = dict(
        feature_key=key,
        name="Form index (last 5)",
        description="Weighted recent form",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="weighted_avg(results, weights=[5,4,3,2,1])",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.TEAM,
    )
    kwargs.update(overrides)
    return await service.register(**kwargs)


@pytest.mark.asyncio
async def test_register_creates_draft_version_1(service):
    definition = await _register(service)

    assert definition.status is FeatureStatus.DRAFT
    assert definition.version == 1
    assert not definition.is_consumable()


@pytest.mark.asyncio
async def test_register_duplicate_key_raises(service):
    await _register(service)

    with pytest.raises(FeatureAlreadyRegisteredError):
        await _register(service)


@pytest.mark.asyncio
async def test_register_requires_nonempty_formula(service):
    with pytest.raises(InvalidFeatureDefinitionError):
        await _register(service, formula="   ")


@pytest.mark.asyncio
async def test_register_rejects_unregistered_dependency(service):
    with pytest.raises(InvalidFeatureDefinitionError):
        await _register(service, dependencies=("does.not.exist",))


@pytest.mark.asyncio
async def test_register_does_not_yet_create_a_version_history_entry(service, version_repo):
    """Version history holds *superseded* versions — v1 is simply the live definition until
    something changes it, so there's nothing to snapshot yet at registration."""
    definition = await _register(service)

    snapshots = await version_repo.list_by_feature(definition.feature_key)
    assert snapshots == []


@pytest.mark.asyncio
async def test_full_lifecycle_draft_to_active(service):
    definition = await _register(service)

    await service.submit_for_review(definition.feature_key.value)
    approved = await service.approve(definition.feature_key.value, reviewer="alice@titanintel.com", now=T0)

    assert approved.status is FeatureStatus.ACTIVE
    assert approved.leakage_reviewed is True
    assert approved.reviewed_by == "alice@titanintel.com"
    assert approved.is_consumable()


@pytest.mark.asyncio
async def test_cannot_approve_without_submitting_first(service):
    definition = await _register(service)

    with pytest.raises(InvalidLifecycleTransitionError):
        await service.approve(definition.feature_key.value, reviewer="alice", now=T0)


@pytest.mark.asyncio
async def test_reject_returns_feature_to_draft_with_reason(service):
    definition = await _register(service)
    await service.submit_for_review(definition.feature_key.value)

    rejected = await service.reject(
        definition.feature_key.value, reviewer="bob", reason="formula looks leaky", now=T0
    )

    assert rejected.status is FeatureStatus.DRAFT
    assert rejected.rejection_reason == "formula looks leaky"
    assert not rejected.is_consumable()


@pytest.mark.asyncio
async def test_deprecate_requires_active_status(service):
    definition = await _register(service)

    with pytest.raises(InvalidLifecycleTransitionError):
        await service.deprecate(definition.feature_key.value, now=T0)


@pytest.mark.asyncio
async def test_deprecate_then_remove(service):
    definition = await _register(service)
    await service.submit_for_review(definition.feature_key.value)
    await service.approve(definition.feature_key.value, reviewer="alice", now=T0)

    deprecated = await service.deprecate(definition.feature_key.value, now=T0 + timedelta(days=30))
    assert deprecated.status is FeatureStatus.DEPRECATED
    assert deprecated.deprecated_at == T0 + timedelta(days=30)

    removed = await service.remove(definition.feature_key.value)
    assert removed.status is FeatureStatus.REMOVED


@pytest.mark.asyncio
async def test_cannot_remove_before_deprecating(service):
    definition = await _register(service)

    with pytest.raises(InvalidLifecycleTransitionError):
        await service.remove(definition.feature_key.value)


@pytest.mark.asyncio
async def test_update_formula_bumps_version_and_resets_to_draft(service):
    definition = await _register(service)
    await service.submit_for_review(definition.feature_key.value)
    await service.approve(definition.feature_key.value, reviewer="alice", now=T0)

    updated = await service.update_formula(
        definition.feature_key.value, "new_weighted_avg(...)", (), now=T0 + timedelta(days=1)
    )

    assert updated.version == 2
    assert updated.status is FeatureStatus.DRAFT
    assert updated.leakage_reviewed is False
    assert updated.reviewed_by is None


@pytest.mark.asyncio
async def test_update_formula_snapshots_previous_version(service, version_repo):
    definition = await _register(service)

    await service.update_formula(definition.feature_key.value, "v2 formula", (), now=T0 + timedelta(days=1))

    snapshots = await version_repo.list_by_feature(definition.feature_key)
    assert [s.version for s in snapshots] == [1]  # v1 snapshot taken before bumping to v2
    assert snapshots[0].snapshot.formula != "v2 formula"


@pytest.mark.asyncio
async def test_reclassify_leakage_corrects_classification_without_touching_version_or_status(service):
    """Real production incident (2026-08-30): a calculator-registered feature can end up on the
    UNKNOWN_PROVENANCE default if it was first registered before a fix adding an explicit
    leakage_classification landed — reclassify_leakage corrects exactly that metadata, unlike
    update_formula (which would wrongly reset an already-ACTIVE, never-actually-wrong-behavior
    feature back to DRAFT for a change that never touched its formula)."""
    definition = await _register(service)
    await service.submit_for_review(definition.feature_key.value)
    await service.approve(definition.feature_key.value, reviewer="alice", now=T0)
    assert definition.leakage_classification == "UNKNOWN_PROVENANCE"

    corrected = await service.reclassify_leakage(
        definition.feature_key.value, "PRE_MATCH_SAFE", reviewer="prediction-platform", now=T0 + timedelta(hours=1)
    )

    assert corrected.leakage_classification == "PRE_MATCH_SAFE"
    assert corrected.is_market_safe() is True
    assert corrected.version == 1  # unchanged — this is a metadata correction, not a new version
    assert corrected.status is FeatureStatus.ACTIVE  # unchanged — still consumable throughout
    assert corrected.leakage_reviewed is True
    assert corrected.reviewed_by == "prediction-platform"


@pytest.mark.asyncio
async def test_operations_on_unknown_feature_raise_not_found(service):
    with pytest.raises(FeatureNotFoundError):
        await service.submit_for_review("does.not.exist")

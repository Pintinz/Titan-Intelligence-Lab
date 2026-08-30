from __future__ import annotations

from uuid import uuid4

import pytest

from modules.features.domain.entities import FeatureDefinition
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
)
from modules.predictions.application.feature_market_mapping_service import (
    FeatureLeakageRiskError,
    FeatureMarketMappingService,
    FeatureNotApprovedError,
    MappingAlreadyExistsError,
    MarketNotFoundError,
    MissingRequiredFeatureError,
)
from modules.predictions.application.market_registry_service import MarketRegistryService
from modules.predictions.domain.value_objects import MarketKind, TargetType


@pytest.fixture
def service(feature_mapping_repo, market_repo, feature_definition_repo):
    return FeatureMarketMappingService(
        mappings=feature_mapping_repo, markets=market_repo, feature_definitions=feature_definition_repo
    )


@pytest.fixture
def registry(market_repo, feature_mapping_repo):
    return MarketRegistryService(markets=market_repo, feature_mappings=feature_mapping_repo)


async def _market(registry, key="football.match_result"):
    return await registry.register(
        market_key=key,
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
    )


async def _active_feature(
    feature_definition_repo, key="football.team.form_index_last5", leakage_classification="PRE_MATCH_SAFE"
):
    definition = FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(key),
        name="Form index (last 5)",
        description="Weighted recent form",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="weighted_avg(results, weights=[5,4,3,2,1])",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.TEAM,
        status=FeatureStatus.ACTIVE,
        leakage_classification=leakage_classification,
    )
    await feature_definition_repo.upsert(definition)
    return definition


@pytest.mark.asyncio
async def test_map_feature_requires_existing_market(service):
    with pytest.raises(MarketNotFoundError):
        await service.map_feature(market_key="does.not.exist", feature_key="football.team.form_index_last5")


@pytest.mark.asyncio
async def test_map_feature_requires_active_feature(service, registry, feature_definition_repo):
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo)
    definition.status = FeatureStatus.DRAFT
    await feature_definition_repo.upsert(definition)

    with pytest.raises(FeatureNotApprovedError):
        await service.map_feature(market_key=market.market_key, feature_key=str(definition.feature_key))


@pytest.mark.asyncio
async def test_map_feature_rejects_unregistered_feature(service, registry):
    market = await _market(registry)

    with pytest.raises(FeatureNotApprovedError):
        await service.map_feature(market_key=market.market_key, feature_key="does.not.exist")


@pytest.mark.asyncio
async def test_map_feature_succeeds_for_active_feature(service, registry, feature_definition_repo):
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo)

    mapping = await service.map_feature(
        market_key=market.market_key, feature_key=str(definition.feature_key), is_required=True, weight=2.0
    )

    assert mapping.market_id == market.id
    assert mapping.feature_key == str(definition.feature_key)
    assert mapping.weight == 2.0


@pytest.mark.asyncio
async def test_map_feature_duplicate_raises(service, registry, feature_definition_repo):
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo)
    await service.map_feature(market_key=market.market_key, feature_key=str(definition.feature_key))

    with pytest.raises(MappingAlreadyExistsError):
        await service.map_feature(market_key=market.market_key, feature_key=str(definition.feature_key))


@pytest.mark.asyncio
async def test_resolve_feature_snapshot_filters_to_mapping(service, registry, feature_definition_repo):
    market = await _market(registry)
    mapped = await _active_feature(feature_definition_repo, key="football.team.form_index_last5")
    await service.map_feature(market_key=market.market_key, feature_key=str(mapped.feature_key))

    snapshot = await service.resolve_feature_snapshot(
        market.market_key, {"football.team.form_index_last5": 0.8, "football.team.unrelated_feature": 1.0}
    )

    assert snapshot == {"football.team.form_index_last5": 0.8}


@pytest.mark.asyncio
async def test_resolve_feature_snapshot_raises_on_missing_required_feature(service, registry, feature_definition_repo):
    market = await _market(registry)
    mapped = await _active_feature(feature_definition_repo, key="football.team.form_index_last5")
    await service.map_feature(market_key=market.market_key, feature_key=str(mapped.feature_key), is_required=True)

    with pytest.raises(MissingRequiredFeatureError):
        await service.resolve_feature_snapshot(market.market_key, {})


@pytest.mark.asyncio
async def test_resolve_feature_snapshot_allows_missing_optional_feature(service, registry, feature_definition_repo):
    market = await _market(registry)
    mapped = await _active_feature(feature_definition_repo, key="football.team.form_index_last5")
    await service.map_feature(market_key=market.market_key, feature_key=str(mapped.feature_key), is_required=False)

    snapshot = await service.resolve_feature_snapshot(market.market_key, {})

    assert snapshot == {}


@pytest.mark.asyncio
async def test_map_feature_rejects_unreviewed_feature_by_default(service, registry, feature_definition_repo):
    """Forensic audit finding #3 (2026-08-30): UNKNOWN_PROVENANCE — the default classification
    for every feature nobody has explicitly reviewed — must fail closed, not silently pass as
    market-safe. Only an explicit PRE_MATCH_SAFE classification may back a market."""
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo, leakage_classification="UNKNOWN_PROVENANCE")

    with pytest.raises(FeatureLeakageRiskError):
        await service.map_feature(market_key=market.market_key, feature_key=str(definition.feature_key))


@pytest.mark.asyncio
async def test_map_feature_rejects_point_in_time_required_feature(service, registry, feature_definition_repo):
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo, leakage_classification="POINT_IN_TIME_REQUIRED")

    with pytest.raises(FeatureLeakageRiskError):
        await service.map_feature(market_key=market.market_key, feature_key=str(definition.feature_key))


@pytest.mark.asyncio
async def test_reconcile_feature_creates_a_new_mapping(service, registry, feature_definition_repo):
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo)

    mapping = await service.reconcile_feature(
        market_key=market.market_key, feature_key=str(definition.feature_key), is_required=True, weight=2.0
    )

    assert mapping.market_id == market.id
    assert mapping.weight == 2.0
    assert mapping.is_required is True


@pytest.mark.asyncio
async def test_reconcile_feature_updates_an_existing_mapping_in_place(service, registry, feature_definition_repo):
    """The whole point of reconcile_feature over map_feature: re-running a market's seeder after
    a spec change (is_required flips, or a reweight) must reach an already-seeded market, not
    silently no-op like the old create-only `except MappingAlreadyExistsError: continue` did —
    see forensic audit finding #1."""
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo)
    first = await service.reconcile_feature(
        market_key=market.market_key, feature_key=str(definition.feature_key), is_required=True, weight=1.0
    )

    updated = await service.reconcile_feature(
        market_key=market.market_key, feature_key=str(definition.feature_key), is_required=False, weight=0.25
    )

    assert updated.id == first.id
    assert updated.is_required is False
    assert updated.weight == 0.25
    all_mappings = await service.list_for_market(market.market_key)
    assert len(all_mappings) == 1


@pytest.mark.asyncio
async def test_reconcile_feature_rejects_unreviewed_feature(service, registry, feature_definition_repo):
    market = await _market(registry)
    definition = await _active_feature(feature_definition_repo, leakage_classification="UNKNOWN_PROVENANCE")

    with pytest.raises(FeatureLeakageRiskError):
        await service.reconcile_feature(market_key=market.market_key, feature_key=str(definition.feature_key))

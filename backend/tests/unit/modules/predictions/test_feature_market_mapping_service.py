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


async def _active_feature(feature_definition_repo, key="football.team.form_index_last5"):
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

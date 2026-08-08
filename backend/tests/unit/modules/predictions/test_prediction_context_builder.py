from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.domain.entities import FeatureDefinition, FeatureValue
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    FeatureValueId,
    QualityFlag,
)
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.market_registry_service import MarketRegistryService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.prediction_context_builder import (
    MarketNotFoundError,
    MarketNotInProductionError,
    NoChampionModelError,
    PredictionContextBuilder,
)
from modules.predictions.domain.entities import FeatureMarketMapping
from modules.predictions.domain.value_objects import FeatureMarketMappingId, MarketKind, TargetType

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def market_registry(market_repo, feature_mapping_repo):
    return MarketRegistryService(markets=market_repo, feature_mappings=feature_mapping_repo)


@pytest.fixture
def model_registry(model_repo):
    return ModelRegistryService(models=model_repo)


@pytest.fixture
def mapping_service(feature_mapping_repo, market_repo, feature_definition_repo):
    return FeatureMarketMappingService(
        mappings=feature_mapping_repo, markets=market_repo, feature_definitions=feature_definition_repo
    )


@pytest.fixture
def builder(market_repo, model_repo, mapping_service, feature_value_repo, feature_definition_repo):
    return PredictionContextBuilder(
        markets=market_repo,
        models=model_repo,
        mapping_service=mapping_service,
        feature_values=feature_value_repo,
        definitions=feature_definition_repo,
    )


async def _production_market_with_champion(market_registry, model_registry, key="football.match_result"):
    market = await market_registry.register(
        market_key=key,
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        now=T0,
    )
    model = await model_registry.register(
        market_id=market.id, model_key=f"{key}.heuristic", version=1, algorithm="heuristic_logistic_v1", now=T0
    )
    await model_registry.promote_to_challenger(model.id)
    champion = await model_registry.promote_to_champion(model.id, approved_by="cto", now=T0)
    return market, champion


async def _active_feature(feature_definition_repo, key: str, online_ttl_seconds: int = 3600):
    definition = FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(key),
        name=key,
        description="test feature",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="n/a",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.FIXTURE,
        status=FeatureStatus.ACTIVE,
        online_ttl_seconds=online_ttl_seconds,
    )
    await feature_definition_repo.upsert(definition)
    return definition


@pytest.mark.asyncio
async def test_build_raises_for_unknown_market(builder):
    with pytest.raises(MarketNotFoundError):
        await builder.build("does.not.exist", EntityType.FIXTURE, "fixture-1", now=T0)


@pytest.mark.asyncio
async def test_build_raises_when_market_not_in_production(builder, market_registry):
    await market_registry.register(
        market_key="football.match_result",
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        now=T0,
    )

    with pytest.raises(MarketNotInProductionError):
        await builder.build("football.match_result", EntityType.FIXTURE, "fixture-1", now=T0)


@pytest.mark.asyncio
async def test_build_raises_when_no_champion_model(
    builder, market_registry, feature_mapping_repo, feature_definition_repo
):
    market = await market_registry.register(
        market_key="football.match_result",
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        now=T0,
    )
    await feature_mapping_repo.upsert(
        FeatureMarketMapping(
            id=FeatureMarketMappingId(uuid4()), market_id=market.id, feature_key="team_form", is_required=True
        )
    )
    await market_registry.submit_for_review(market.market_key)
    await market_registry.approve(market.market_key, reviewer="cto", now=T0)
    await market_registry.promote_to_production(market.market_key, now=T0)

    with pytest.raises(NoChampionModelError):
        await builder.build(market.market_key, EntityType.FIXTURE, "fixture-1", now=T0)


@pytest.mark.asyncio
async def test_build_assembles_resolved_features_weights_and_confidence_inputs(
    builder, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    market, champion = await _production_market_with_champion(market_registry, model_registry)
    definition = await _active_feature(feature_definition_repo, "football.team.form_index_last5")
    await mapping_service.map_feature(
        market_key=market.market_key, feature_key=str(definition.feature_key), is_required=True, weight=1.5
    )
    await feature_value_repo.record(
        FeatureValue(
            id=FeatureValueId(uuid4()),
            feature_key=definition.feature_key,
            entity_type=EntityType.FIXTURE,
            entity_id="fixture-1",
            as_of=T0,
            value=0.8,
            quality_flags=(QualityFlag.OK,),
        )
    )
    await market_registry.submit_for_review(market.market_key)
    await market_registry.approve(market.market_key, reviewer="cto", now=T0)
    await market_registry.promote_to_production(market.market_key, now=T0)

    context = await builder.build(market.market_key, EntityType.FIXTURE, "fixture-1", now=T0)

    assert context.market.market_key == market.market_key
    assert context.model.id == champion.id
    assert context.resolved_features == {"football.team.form_index_last5": 0.8}
    assert context.mapping_weights == {"football.team.form_index_last5": 1.5}
    assert len(context.feature_confidence_inputs) == 1
    confidence_input = context.feature_confidence_inputs[0]
    assert confidence_input.is_present is True
    assert confidence_input.quality_score == 1.0
    assert confidence_input.freshness_score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_build_reflects_stale_and_missing_features_in_confidence_inputs(
    builder, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    market, _ = await _production_market_with_champion(market_registry, model_registry, key="football.total_goals")
    required = await _active_feature(feature_definition_repo, "football.team.avg_goals_scored")
    optional = await _active_feature(feature_definition_repo, "football.team.avg_goals_conceded")
    await mapping_service.map_feature(
        market_key=market.market_key, feature_key=str(required.feature_key), is_required=True
    )
    await mapping_service.map_feature(
        market_key=market.market_key, feature_key=str(optional.feature_key), is_required=False
    )
    await feature_value_repo.record(
        FeatureValue(
            id=FeatureValueId(uuid4()),
            feature_key=required.feature_key,
            entity_type=EntityType.FIXTURE,
            entity_id="fixture-1",
            as_of=T0 - timedelta(hours=2),
            value=1.4,
            quality_flags=(QualityFlag.STALE,),
        )
    )
    await market_registry.submit_for_review(market.market_key)
    await market_registry.approve(market.market_key, reviewer="cto", now=T0)
    await market_registry.promote_to_production(market.market_key, now=T0)

    context = await builder.build(market.market_key, EntityType.FIXTURE, "fixture-1", now=T0)

    by_key = {c.feature_key: c for c in context.feature_confidence_inputs}
    assert by_key[str(required.feature_key)].quality_score == 0.5
    assert 0.0 < by_key[str(required.feature_key)].freshness_score < 1.0
    assert by_key[str(optional.feature_key)].is_present is False
    assert by_key[str(optional.feature_key)].quality_score == 0.0
    assert by_key[str(optional.feature_key)].freshness_score == 0.0
    assert context.resolved_features == {"football.team.avg_goals_scored": 1.4}


@pytest.mark.asyncio
async def test_freshness_uses_each_feature_own_registered_ttl_not_a_global_hardcoded_one(
    builder, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    """A batch-computed, slow-moving feature (team-form differential, historical rate) with a
    multi-day TTL is genuinely fresh a couple of days after it was last computed — it must not be
    scored as if it were live/streaming data going stale within an hour."""
    market, _ = await _production_market_with_champion(market_registry, model_registry, key="football.slow_moving")
    week_long_ttl = 7 * 24 * 3600
    definition = await _active_feature(feature_definition_repo, "football.team.form_index_last10", online_ttl_seconds=week_long_ttl)
    await mapping_service.map_feature(
        market_key=market.market_key, feature_key=str(definition.feature_key), is_required=True
    )
    await feature_value_repo.record(
        FeatureValue(
            id=FeatureValueId(uuid4()),
            feature_key=definition.feature_key,
            entity_type=EntityType.FIXTURE,
            entity_id="fixture-1",
            as_of=T0 - timedelta(days=2),
            value=0.6,
            quality_flags=(QualityFlag.OK,),
        )
    )
    await market_registry.submit_for_review(market.market_key)
    await market_registry.approve(market.market_key, reviewer="cto", now=T0)
    await market_registry.promote_to_production(market.market_key, now=T0)

    context = await builder.build(market.market_key, EntityType.FIXTURE, "fixture-1", now=T0)

    assert context.feature_confidence_inputs[0].freshness_score == pytest.approx(1.0)

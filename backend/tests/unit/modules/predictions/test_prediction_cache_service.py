from __future__ import annotations

from dataclasses import dataclass
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
from modules.alerts.domain.value_objects import AlertType
from modules.intelligence.application.intelligence_retrieval_service import IntelligenceRetrievalService
from modules.intelligence.ports.retrieval import IntelligenceRetrievalQuery, IntelligenceRetrievalResult
from modules.predictions.application.confidence_engine import ConfidenceEngine
from modules.predictions.application.explainability_engine import ExplainabilityEngine
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.market_registry_service import MarketRegistryService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.prediction_cache_service import (
    InvalidPredictionStatusTransitionError,
    MarketNotFoundError,
    PredictionCacheService,
)
from modules.predictions.application.prediction_context_builder import PredictionContextBuilder
from modules.predictions.application.prediction_engine import PredictionEngine
from modules.predictions.application.predictor_registry import PredictorRegistry
from modules.predictions.domain.value_objects import MarketKind, PredictionStatus, TargetType
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator
from modules.predictions.infrastructure.predictors.weighted_scoring import WeightedLogisticPredictor
from modules.watchlist.domain.value_objects import WatchlistEntityType

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@dataclass
class _EmptyRetrievalPort:
    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        return IntelligenceRetrievalResult(query=query, documents=(), truncated=False)


@dataclass
class _EmptyTeamNamesResolver:
    async def team_names_for_match(self, subject_ref: str) -> tuple[str, ...]:
        return ()


@dataclass
class _FakeTextIntelligenceProvider:
    provider_key: str = "fake"

    async def explain(self, context: dict) -> str:
        return "explained"


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
def engine(
    market_repo,
    model_repo,
    mapping_service,
    feature_value_repo,
    feature_definition_repo,
    prediction_outcome_repo,
    model_evaluation_repo,
    prediction_repo,
):
    context_builder = PredictionContextBuilder(
        markets=market_repo,
        models=model_repo,
        mapping_service=mapping_service,
        feature_values=feature_value_repo,
        definitions=feature_definition_repo,
    )
    predictors = PredictorRegistry()
    predictors.register_many(WeightedLogisticPredictor.SUPPORTED_KINDS, WeightedLogisticPredictor())
    retrieval_service = IntelligenceRetrievalService(
        news=_EmptyRetrievalPort(), community=_EmptyRetrievalPort(), knowledge_graph=_EmptyRetrievalPort(),
        ai_reports=_EmptyRetrievalPort(), team_names=_EmptyTeamNamesResolver(),
    )
    explainability_engine = ExplainabilityEngine(retrieval=retrieval_service, text_intelligence=_FakeTextIntelligenceProvider())
    return PredictionEngine(
        context_builder=context_builder,
        predictors=predictors,
        calibrator=PlattScalingCalibrator(),
        confidence_engine=ConfidenceEngine(),
        explainability_engine=explainability_engine,
        retrieval=retrieval_service,
        outcomes=prediction_outcome_repo,
        model_evaluations=model_evaluation_repo,
        predictions=prediction_repo,
    )


@pytest.fixture
def service(engine, market_repo, prediction_repo, prediction_audit_repo):
    return PredictionCacheService(engine=engine, markets=market_repo, predictions=prediction_repo, audits=prediction_audit_repo)


@dataclass
class _SpyAlertNotifier:
    calls: list = None

    def __post_init__(self):
        self.calls = []

    async def notify_watchers(self, entity_type, entity_ref, alert_type, title, body, now):
        self.calls.append((entity_type, entity_ref, alert_type, title, body))
        return []


@pytest.fixture
def alert_spy():
    return _SpyAlertNotifier()


@pytest.fixture
def service_with_alerts(engine, market_repo, prediction_repo, prediction_audit_repo, alert_spy):
    return PredictionCacheService(
        engine=engine, markets=market_repo, predictions=prediction_repo, audits=prediction_audit_repo, alerts=alert_spy
    )


async def _setup_production_market(
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, key, confidence_threshold=0.0
):
    market = await market_registry.register(
        market_key=key,
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        confidence_threshold=confidence_threshold,
        now=T0,
    )
    definition = FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(f"{key}.form_index"),
        name="Form index",
        description="test",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="n/a",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.FIXTURE,
        status=FeatureStatus.ACTIVE,
        leakage_classification="PRE_MATCH_SAFE",
    )
    await feature_definition_repo.upsert(definition)
    await mapping_service.map_feature(market_key=key, feature_key=str(definition.feature_key), is_required=True)
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
    await market_registry.submit_for_review(key)
    await market_registry.approve(key, reviewer="cto", now=T0)
    await market_registry.promote_to_production(key, now=T0)

    model = await model_registry.register(
        market_id=market.id, model_key=f"{key}.heuristic", version=1, algorithm="heuristic_logistic_v1", now=T0
    )
    await model_registry.promote_to_challenger(model.id)
    champion = await model_registry.promote_to_champion(model.id, approved_by="cto", now=T0)
    return market, champion


@pytest.mark.asyncio
async def test_get_or_generate_raises_for_unknown_market(service):
    with pytest.raises(MarketNotFoundError):
        await service.get_or_generate("does.not.exist", EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)


@pytest.mark.asyncio
async def test_get_or_generate_publishes_when_confidence_meets_threshold(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.publish_market", confidence_threshold=0.0,
    )

    prediction = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

    assert prediction.status is PredictionStatus.PUBLISHED


@pytest.mark.asyncio
async def test_get_or_generate_stays_draft_when_confidence_below_threshold(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.draft_market", confidence_threshold=1.1,
    )

    prediction = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

    assert prediction.status is PredictionStatus.DRAFT


@pytest.mark.asyncio
async def test_get_or_generate_records_audit_on_generation(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    prediction_audit_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.audit_market",
    )

    prediction = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

    audits = await prediction_audit_repo.list_by_prediction(prediction.id)
    assert len(audits) == 1
    assert audits[0].action.value == "generated"


@pytest.mark.asyncio
async def test_get_or_generate_returns_cached_prediction_within_ttl(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.cache_market",
    )

    first = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)
    second = await service.get_or_generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0 + timedelta(seconds=60)
    )

    assert second.id == first.id


@pytest.mark.asyncio
async def test_get_or_generate_regenerates_after_ttl_and_supersedes_previous(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.ttl_market",
    )
    service.cache_ttl_seconds = 60.0

    first = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)
    second = await service.get_or_generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0 + timedelta(minutes=10)
    )

    assert second.id != first.id
    refreshed_first = await service.predictions.get(first.id)
    assert refreshed_first.status is PredictionStatus.SUPERSEDED
    assert second.status is PredictionStatus.PUBLISHED


@pytest.mark.asyncio
async def test_approve_draft_prediction(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.approve_market", confidence_threshold=1.1,
    )
    prediction = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)
    assert prediction.status is PredictionStatus.DRAFT

    approved = await service.approve(prediction, actor="cto", now=T0)

    assert approved.status is PredictionStatus.PUBLISHED


@pytest.mark.asyncio
async def test_approve_already_published_prediction_raises(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.already_published_market",
    )
    prediction = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)
    assert prediction.status is PredictionStatus.PUBLISHED

    with pytest.raises(InvalidPredictionStatusTransitionError):
        await service.approve(prediction, actor="cto", now=T0)


@pytest.mark.asyncio
async def test_reject_draft_prediction_voids_it(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    prediction_audit_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.reject_market", confidence_threshold=1.1,
    )
    prediction = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

    rejected = await service.reject(prediction, actor="cto", now=T0, reason="low quality data")

    assert rejected.status is PredictionStatus.VOIDED
    audits = await prediction_audit_repo.list_by_prediction(prediction.id)
    reject_audit = next(a for a in audits if a.action.value == "rejected")
    assert reject_audit.details == {"reason": "low quality data"}


@pytest.mark.asyncio
async def test_regenerate_bypasses_cache_ttl_and_supersedes_previous(
    service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.regenerate_market",
    )
    first = await service.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

    regenerated = await service.regenerate(
        market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0 + timedelta(seconds=1), actor="admin-cto"
    )

    assert regenerated.id != first.id
    refreshed_first = await service.predictions.get(first.id)
    assert refreshed_first.status is PredictionStatus.SUPERSEDED
    assert regenerated.status is PredictionStatus.PUBLISHED


@pytest.mark.asyncio
async def test_regenerate_raises_for_unknown_market(service):
    with pytest.raises(MarketNotFoundError):
        await service.regenerate("does.not.exist", EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)


@pytest.mark.asyncio
async def test_first_publish_does_not_notify_watchers(
    service_with_alerts, alert_spy, market_registry, model_registry, mapping_service,
    feature_definition_repo, feature_value_repo,
):
    """No previous PUBLISHED prediction to supersede — nothing has "changed" yet, so no alert."""
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.alerts_first_market",
    )

    await service_with_alerts.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

    assert alert_spy.calls == []


@pytest.mark.asyncio
async def test_regenerating_a_published_prediction_notifies_watchers(
    service_with_alerts, alert_spy, market_registry, model_registry, mapping_service,
    feature_definition_repo, feature_value_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.alerts_regenerate_market",
    )
    await service_with_alerts.get_or_generate(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

    await service_with_alerts.regenerate(
        market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0 + timedelta(seconds=1), actor="cto"
    )

    assert len(alert_spy.calls) == 1
    entity_type, entity_ref, alert_type, _, _ = alert_spy.calls[0]
    assert entity_type is WatchlistEntityType.FIXTURE
    assert entity_ref == "fixture-1"
    assert alert_type is AlertType.PREDICTION_CHANGED


@pytest.mark.asyncio
async def test_regenerating_a_draft_prediction_does_not_notify_watchers(
    service_with_alerts, alert_spy, market_registry, model_registry, mapping_service,
    feature_definition_repo, feature_value_repo,
):
    """A DRAFT prediction was never published — nothing watchers saw is "changing"."""
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.alerts_draft_market", confidence_threshold=1.1,
    )
    prediction = await service_with_alerts.get_or_generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0
    )
    assert prediction.status is PredictionStatus.DRAFT

    await service_with_alerts.regenerate(
        market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0 + timedelta(seconds=1), actor="cto"
    )

    assert alert_spy.calls == []

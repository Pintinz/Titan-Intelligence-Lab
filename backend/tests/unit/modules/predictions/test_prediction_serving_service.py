from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
from modules.intelligence.application.intelligence_retrieval_service import IntelligenceRetrievalService
from modules.intelligence.ports.retrieval import IntelligenceRetrievalQuery, IntelligenceRetrievalResult
from modules.predictions.application.confidence_engine import ConfidenceEngine
from modules.predictions.application.explainability_engine import ExplainabilityEngine
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.market_registry_service import MarketRegistryService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.prediction_cache_service import PredictionCacheService
from modules.predictions.application.prediction_context_builder import PredictionContextBuilder
from modules.predictions.application.prediction_engine import PredictionEngine
from modules.predictions.application.prediction_serving_service import (
    AsyncPredictionQueueService,
    BatchPredictionService,
    RequestNotFoundError,
)
from modules.predictions.application.predictor_registry import PredictorRegistry
from modules.predictions.domain.value_objects import MarketKind, TargetType
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator
from modules.predictions.infrastructure.predictors.weighted_scoring import WeightedLogisticPredictor

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
def engine(market_repo, model_repo, mapping_service, feature_value_repo, feature_definition_repo, prediction_outcome_repo, model_evaluation_repo, prediction_repo):
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
def cache_service(engine, market_repo, prediction_repo, prediction_audit_repo):
    return PredictionCacheService(engine=engine, markets=market_repo, predictions=prediction_repo, audits=prediction_audit_repo)


@pytest.fixture
def batch_service(cache_service):
    return BatchPredictionService(cache_service=cache_service)


@pytest.fixture
def queue_service():
    return AsyncPredictionQueueService()


async def _setup_production_market(
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, key, entity_id="fixture-1"
):
    market = await market_registry.register(
        market_key=key,
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        confidence_threshold=0.0,
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
            entity_id=entity_id,
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
    await model_registry.promote_to_champion(model.id, approved_by="cto", now=T0)
    return market


class TestBatchPredictionService:
    async def test_generates_predictions_for_multiple_subjects(
        self, batch_service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
    ):
        market = await _setup_production_market(
            market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, "football.batch_market"
        )

        requests = [(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1")]
        results = await batch_service.generate_batch(requests, now=T0)

        assert len(results) == 1
        assert not isinstance(results[0], Exception)
        assert results[0].subject_ref == "fixture-1"

    async def test_one_bad_request_does_not_fail_the_whole_batch(
        self, batch_service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
    ):
        market = await _setup_production_market(
            market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, "football.batch_mixed"
        )

        requests = [
            (market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1"),
            ("does.not.exist", EntityType.FIXTURE, "fixture-2", "fixture-2"),
        ]
        results = await batch_service.generate_batch(requests, now=T0)

        assert not isinstance(results[0], Exception)
        assert isinstance(results[1], Exception)


class TestAsyncPredictionQueueService:
    async def test_enqueue_then_process_then_poll_returns_prediction(
        self, queue_service, cache_service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
    ):
        market = await _setup_production_market(
            market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, "football.queue_market"
        )

        request_id = queue_service.enqueue(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)
        assert queue_service.poll(request_id) is None  # still queued
        assert queue_service.pending_count() == 1

        processed_id = await queue_service.process_next(cache_service, now=T0)

        assert processed_id == request_id
        assert queue_service.pending_count() == 0
        result = queue_service.poll(request_id)
        assert result.subject_ref == "fixture-1"

    async def test_process_next_on_empty_queue_returns_none(self, queue_service, cache_service):
        assert await queue_service.process_next(cache_service, now=T0) is None

    async def test_poll_unknown_request_raises(self, queue_service):
        with pytest.raises(RequestNotFoundError):
            queue_service.poll("does-not-exist")

    async def test_failed_generation_is_captured_not_raised(self, queue_service, cache_service):
        request_id = queue_service.enqueue("does.not.exist", EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

        await queue_service.process_next(cache_service, now=T0)

        result = queue_service.poll(request_id)
        assert isinstance(result, Exception)

    async def test_fifo_order(
        self, queue_service, cache_service, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
    ):
        market = await _setup_production_market(
            market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, "football.fifo_market"
        )
        first_id = queue_service.enqueue(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)
        second_id = queue_service.enqueue(market.market_key, EntityType.FIXTURE, "fixture-1", "fixture-1", now=T0)

        processed_first = await queue_service.process_next(cache_service, now=T0)

        assert processed_first == first_id
        assert queue_service.poll(second_id) is None

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
from modules.intelligence.ports.retrieval import (
    IntelligenceRetrievalDocument,
    IntelligenceRetrievalQuery,
    IntelligenceRetrievalResult,
)
from modules.predictions.application.confidence_engine import ConfidenceEngine
from modules.predictions.application.explainability_engine import ExplainabilityEngine
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.market_registry_service import MarketRegistryService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.prediction_context_builder import PredictionContextBuilder
from modules.predictions.application.prediction_engine import PredictionEngine
from modules.predictions.application.predictor_registry import PredictorRegistry
from modules.predictions.domain.entities import PredictionOutcome
from modules.predictions.domain.value_objects import (
    MarketKind,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator
from modules.predictions.infrastructure.predictors.weighted_scoring import WeightedLogisticPredictor

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@dataclass
class _FakeRetrievalPort:
    documents: tuple[IntelligenceRetrievalDocument, ...] = ()

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        return IntelligenceRetrievalResult(query=query, documents=self.documents, truncated=False)


@dataclass
class _FakeTextIntelligenceProvider:
    provider_key: str = "fake"

    async def explain(self, context: dict) -> str:
        return f"explained {context['market_key']}"


def _document(modality: str, confidence: float, text: str = "fact") -> IntelligenceRetrievalDocument:
    return IntelligenceRetrievalDocument(
        modality=modality, subject_ref="fixture-1", text=text, source="src", confidence=confidence
    )


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
def context_builder(market_repo, model_repo, mapping_service, feature_value_repo):
    return PredictionContextBuilder(
        markets=market_repo, models=model_repo, mapping_service=mapping_service, feature_values=feature_value_repo
    )


@pytest.fixture
def retrieval_documents():
    return (
        _document("knowledge_graph", 0.9, "TeamA rivalry_with TeamB"),
        _document("knowledge_graph", 0.9, "TeamA plays_at VenueX"),
        _document("news", 0.9, "Star striker ruled out with injury"),
        _document("community", 0.7, "Fans expect a tight match"),
    )


@pytest.fixture
def retrieval_service(retrieval_documents):
    by_modality = {
        "knowledge_graph": tuple(d for d in retrieval_documents if d.modality == "knowledge_graph"),
        "news": tuple(d for d in retrieval_documents if d.modality == "news"),
        "community": tuple(d for d in retrieval_documents if d.modality == "community"),
        "ai_reports": (),
    }
    return IntelligenceRetrievalService(
        news=_FakeRetrievalPort(by_modality["news"]),
        community=_FakeRetrievalPort(by_modality["community"]),
        knowledge_graph=_FakeRetrievalPort(by_modality["knowledge_graph"]),
        ai_reports=_FakeRetrievalPort(by_modality["ai_reports"]),
    )


@pytest.fixture
def explainability_engine(retrieval_service):
    return ExplainabilityEngine(retrieval=retrieval_service, text_intelligence=_FakeTextIntelligenceProvider())


@pytest.fixture
def predictors():
    registry = PredictorRegistry()
    registry.register_many(WeightedLogisticPredictor.SUPPORTED_KINDS, WeightedLogisticPredictor())
    return registry


@pytest.fixture
def engine(
    context_builder,
    predictors,
    confidence_engine_dep,
    explainability_engine,
    retrieval_service,
    prediction_outcome_repo,
    model_evaluation_repo,
    prediction_repo,
):
    return PredictionEngine(
        context_builder=context_builder,
        predictors=predictors,
        calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep,
        explainability_engine=explainability_engine,
        retrieval=retrieval_service,
        outcomes=prediction_outcome_repo,
        model_evaluations=model_evaluation_repo,
        predictions=prediction_repo,
        expected_kg_facts=10,
    )


@pytest.fixture
def confidence_engine_dep():
    return ConfidenceEngine()


async def _setup_production_market(
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, key
):
    market = await market_registry.register(
        market_key=key,
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        now=T0,
    )
    definition = FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey("football.team.form_index_last5"),
        name="Form index",
        description="test",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="n/a",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.FIXTURE,
        status=FeatureStatus.ACTIVE,
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
async def test_generate_returns_draft_prediction_with_full_pipeline(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.match_result",
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.status is PredictionStatus.DRAFT
    assert prediction.market_id == market.id
    assert prediction.model_id == champion.id
    assert prediction.model_version == "1"
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.feature_snapshot == {"football.team.form_index_last5": 0.8}
    assert prediction.explanation.ai_explanation == "explained football.match_result"
    assert prediction.confidence.composite > 0.0


@pytest.mark.asyncio
async def test_generate_uses_neutral_defaults_with_no_history(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.no_history_market",
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.confidence.historical_accuracy == 0.5
    assert prediction.confidence.model_reliability == 0.5
    assert prediction.confidence.prediction_stability == 1.0


@pytest.mark.asyncio
async def test_generate_computes_historical_accuracy_from_outcomes(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    prediction_outcome_repo,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.accuracy_market",
    )
    for _ in range(3):
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()),
                prediction_id=PredictionId(uuid4()),
                actual_value="home_win",
                error=0.0,
                evaluated_at=T0,
            )
        )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.confidence.historical_accuracy == 1.0


@pytest.mark.asyncio
async def test_generate_reflects_kg_and_news_and_community_signals(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.retrieval_market",
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.confidence.knowledge_graph_completeness == pytest.approx(0.2)
    assert prediction.confidence.news_reliability == pytest.approx(0.9)
    assert prediction.confidence.community_reliability == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_generate_prediction_stability_drops_with_prior_prediction_disagreement(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    prediction_repo,
):
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.stability_market",
    )
    from modules.predictions.domain.entities import ConfidenceBreakdown, ExplanationBundle, Prediction

    def _prior(probability: float) -> Prediction:
        return Prediction(
            id=PredictionId(uuid4()),
            market_id=market.id,
            model_id=champion.id,
            subject_ref="fixture-1",
            value="positive",
            probability=probability,
            confidence=ConfidenceBreakdown(*([0.5] * 9)),
            explanation=ExplanationBundle(),
            feature_snapshot={},
            model_version="1",
        )

    await prediction_repo.record(_prior(0.0))
    await prediction_repo.record(_prior(1.0))

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.confidence.prediction_stability == 0.0

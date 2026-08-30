from __future__ import annotations

import math
from dataclasses import dataclass, replace
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
from modules.predictions.application.prediction_engine import ChampionUnavailableError, PredictionEngine, _calibrate_distribution
from modules.predictions.application.predictor_registry import PredictorRegistry
from modules.predictions.domain.calibration import CalibrationMetadata
from modules.predictions.domain.entities import PredictionOutcome
from modules.predictions.domain.value_objects import (
    MarketKind,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)
from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyCalibrationParametersRepository
from modules.predictions.infrastructure.predictors.weighted_scoring import (
    WeightedLinearPredictor,
    WeightedLogisticPredictor,
)
from modules.predictions.ports.ml_model import TrainingSample

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@dataclass
class _FakeRetrievalPort:
    documents: tuple[IntelligenceRetrievalDocument, ...] = ()

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        return IntelligenceRetrievalResult(query=query, documents=self.documents, truncated=False)


@dataclass
class _EmptyTeamNamesResolver:
    async def team_names_for_match(self, subject_ref: str) -> tuple[str, ...]:
        return ()


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
def context_builder(market_repo, model_repo, mapping_service, feature_value_repo, feature_definition_repo):
    return PredictionContextBuilder(
        markets=market_repo,
        models=model_repo,
        mapping_service=mapping_service,
        feature_values=feature_value_repo,
        definitions=feature_definition_repo,
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
        team_names=_EmptyTeamNamesResolver(),
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
    model_loader,
):
    # `model_loader` wired by default (master rebuild command §3, 2026-08-30): production
    # (composition.py's build_prediction_engine) always wires a real one, so tests using this
    # shared fixture — every one that just wants *a* real prediction, not one specifically
    # testing Champion-resolution failure modes — need the same, paired with
    # `_setup_production_market(..., artifact_store=artifact_store)` to register a genuinely-
    # trained Champion rather than a placeholder that would now raise ChampionUnavailableError.
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
        model_loader=model_loader,
    )


@pytest.fixture
def confidence_engine_dep():
    return ConfidenceEngine()


@dataclass
class _InMemoryArtifactStore:
    store: dict

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


@pytest.fixture
def artifact_store():
    return _InMemoryArtifactStore(store={})


@pytest.fixture
def model_loader(artifact_store):
    return ModelLoaderService(artifact_store=artifact_store)


async def _fit_and_store_sklearn_model(artifact_store, target_type, feature_key: str) -> tuple[str, str]:
    """A real, fitted SklearnAdapter — serialized the exact way select_and_register_challenger
    now does, so these tests exercise the genuine load-and-serve path, not a stub. Returns
    ``(artifact_ref, algorithm)`` — LOGISTIC_REGRESSION is classification-only
    (sklearn_adapter.py's own `_CLASSIFICATION_ONLY`), so a REGRESSION market needs RIDGE
    instead; the caller registers the `ModelDefinition` with whichever algorithm this actually
    used, not a hardcoded one that might not match."""
    algorithm = MLAlgorithm.LOGISTIC_REGRESSION if target_type is TargetType.CLASSIFICATION else MLAlgorithm.RIDGE
    model = SklearnAdapter(algorithm=algorithm, target_type=target_type)
    samples = [TrainingSample(features={feature_key: float(i % 10) - 5.0}, label=1.0 if i % 2 == 0 else 0.0) for i in range(40)]
    await model.fit(samples)
    artifact_ref = await artifact_store.save("test-model.bin", model.serialize())
    return artifact_ref, algorithm.value


async def _setup_production_market(
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, key,
    feature_value: float = 0.8, artifact_store=None,
):
    """Registers a genuinely-trained, loadable Champion by default (master rebuild command §3,
    2026-08-30: `PredictionEngine` no longer falls back to a formula predictor for a placeholder
    Champion, so every test that just wants *a* real prediction — not one testing the Champion-
    resolution path itself — needs a real artifact behind the Champion it sets up). Pass
    `artifact_store=None` (the old behavior) only for tests that specifically want the placeholder/
    no-artifact case."""
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
            value=feature_value,
            quality_flags=(QualityFlag.OK,),
        )
    )
    await market_registry.submit_for_review(key)
    await market_registry.approve(key, reviewer="cto", now=T0)
    await market_registry.promote_to_production(key, now=T0)

    if artifact_store is None:
        model = await model_registry.register(
            market_id=market.id, model_key=f"{key}.heuristic", version=1, algorithm="heuristic_logistic_v1", now=T0
        )
    else:
        artifact_ref, algorithm = await _fit_and_store_sklearn_model(
            artifact_store, TargetType.CLASSIFICATION, str(definition.feature_key)
        )
        model = await model_registry.register(
            market_id=market.id, model_key=f"{key}.{algorithm}", version=1,
            algorithm=algorithm, framework="sklearn", artifact_ref=artifact_ref, now=T0,
        )
    await model_registry.promote_to_challenger(model.id)
    champion = await model_registry.promote_to_champion(model.id, approved_by="cto", now=T0)
    return market, champion


async def _setup_regression_market(
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo, key,
    artifact_store=None,
):
    """Same shape as `_setup_production_market` but registers a TargetType.REGRESSION,
    MarketKind.PLAYER_PROP market — the shape a real regression-shaped market (e.g.
    `basketball.player_points_prop`) takes. Same `artifact_store` default-to-genuinely-trained
    behavior as `_setup_production_market` — see its docstring."""
    market = await market_registry.register(
        market_key=key,
        sport_code="basketball",
        name="Player Points Prop",
        category="player_prop",
        market_kind=MarketKind.PLAYER_PROP,
        target_type=TargetType.REGRESSION,
        now=T0,
    )
    definition = FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey("basketball.team.form_points_last5"),
        name="Form points",
        description="test",
        sport_code="basketball",
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
            value=24.5,
            quality_flags=(QualityFlag.OK,),
        )
    )
    await market_registry.submit_for_review(key)
    await market_registry.approve(key, reviewer="cto", now=T0)
    await market_registry.promote_to_production(key, now=T0)

    if artifact_store is None:
        model = await model_registry.register(
            market_id=market.id, model_key=f"{key}.heuristic", version=1, algorithm="heuristic_linear_v1", now=T0
        )
    else:
        artifact_ref, algorithm = await _fit_and_store_sklearn_model(
            artifact_store, TargetType.REGRESSION, str(definition.feature_key)
        )
        model = await model_registry.register(
            market_id=market.id, model_key=f"{key}.{algorithm}", version=1,
            algorithm=algorithm, framework="sklearn", artifact_ref=artifact_ref, now=T0,
        )
    await model_registry.promote_to_challenger(model.id)
    champion = await model_registry.promote_to_champion(model.id, approved_by="cto", now=T0)
    return market, champion


class TestCalibrateDistribution:
    """Pure-function unit tests for `_calibrate_distribution` — the rescale-and-renormalize policy
    `PredictionEngine._shape_outcome` applies before storing `Prediction.probability_distribution`."""

    def test_winner_takes_the_calibrated_probability(self):
        result = _calibrate_distribution(
            {"positive": 0.7, "negative": 0.3}, calibration_key="positive", raw_probability=0.7, calibrated_probability=0.6
        )
        assert result["positive"] == pytest.approx(0.6)

    def test_result_always_sums_to_one(self):
        result = _calibrate_distribution(
            {"HOME_WIN": 0.5, "DRAW": 0.3, "AWAY_WIN": 0.2},
            calibration_key="HOME_WIN", raw_probability=0.5, calibrated_probability=0.8,
        )
        assert sum(result.values()) == pytest.approx(1.0)
        # Non-winning entries keep their *relative* shape (DRAW was 1.5x AWAY_WIN before, still is).
        assert result["DRAW"] == pytest.approx(result["AWAY_WIN"] * 1.5)

    def test_empty_distribution_returns_empty(self):
        assert _calibrate_distribution({}, calibration_key="positive", raw_probability=0.5, calibrated_probability=0.5) == {}

    def test_calibration_key_not_present_returns_distribution_unchanged(self):
        distribution = {"OTHER": 1.0}
        result = _calibrate_distribution(distribution, calibration_key="5-3", raw_probability=0.01, calibrated_probability=0.02)
        assert result == distribution

    def test_degenerate_all_raw_mass_on_winner_splits_remainder_evenly(self):
        result = _calibrate_distribution(
            {"positive": 1.0, "negative": 0.0}, calibration_key="positive", raw_probability=1.0, calibrated_probability=0.9
        )
        assert result["positive"] == pytest.approx(0.9)
        assert result["negative"] == pytest.approx(0.1)

    def test_calibrating_the_non_winning_side_still_sums_to_one(self):
        """The exact bug this function exists to prevent: `WeightedLogisticPredictor.probability`
        is always P("positive") — when "negative" actually wins (raw P(positive) < 0.5),
        `_shape_outcome` must pass `calibration_key="positive"` (not the winning "negative"), or
        the two entries silently both end up carrying similar values that don't sum to 1."""
        result = _calibrate_distribution(
            {"positive": 0.44, "negative": 0.56}, calibration_key="positive", raw_probability=0.44, calibrated_probability=0.44
        )
        assert sum(result.values()) == pytest.approx(1.0)
        assert result["positive"] == pytest.approx(0.44)
        assert result["negative"] == pytest.approx(0.56)


@pytest.mark.asyncio
async def test_generate_returns_draft_prediction_with_full_pipeline(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    artifact_store,
):
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.match_result", artifact_store=artifact_store,
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
    # Milestone 9.2 Phase 2 covers six specific market_keys (outcome_label_mapper.py) —
    # "football.match_result" isn't one of them, so generate() must keep emitting the generic
    # predictor's raw output unchanged for it, exactly as before Phase 2.
    assert prediction.value in ("positive", "negative")


@pytest.mark.asyncio
async def test_generate_emits_real_domain_label_for_a_phase_2_market(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    artifact_store,
):
    """For a market Milestone 9.2 Phase 2 covers, the stored prediction value must be the market's
    real label (YES/NO), never the generic predictor's bare "positive"/"negative"."""
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.both_teams_to_score", artifact_store=artifact_store,
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.value in ("YES", "NO")


@pytest.mark.asyncio
async def test_generate_uses_neutral_defaults_with_no_history(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    artifact_store,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.no_history_market", artifact_store=artifact_store,
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
    prediction_outcome_repo, artifact_store,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.accuracy_market", artifact_store=artifact_store,
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
async def test_generate_normalizes_regression_error_for_historical_accuracy(
    context_builder, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    confidence_engine_dep, explainability_engine, retrieval_service, prediction_outcome_repo,
    model_evaluation_repo, prediction_repo, model_loader, artifact_store,
):
    """Phase 6 fix (2026-08-25): a regression market's `PredictionOutcome.error` is a raw
    magnitude (e.g. 8 points off a ~220-point total), never bounded to [0, 1] the way a
    classification outcome's already is. Before the fix, `_historical_accuracy` fed that raw
    magnitude straight into `1 - clamp(error, 0, 1)`, which always clamped to 0.0 (the worst
    possible score) for any error >= 1.0 — silently reporting ~0% historical accuracy for every
    regression market regardless of how good the predictions actually were. A tight relative
    error (8/220 ≈ 3.6%) must now produce a high, not a floored-to-zero, accuracy."""
    market, _ = await _setup_regression_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "basketball.accuracy_regression_market", artifact_store=artifact_store,
    )
    linear_predictors = PredictorRegistry()
    linear_predictors.register_many(WeightedLinearPredictor.SUPPORTED_KINDS, WeightedLinearPredictor())
    engine = PredictionEngine(
        context_builder=context_builder, predictors=linear_predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, model_loader=model_loader,
    )
    for _ in range(3):
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()),
                prediction_id=PredictionId(uuid4()),
                actual_value="220.0",
                error=8.0,  # a genuinely tight regression miss, NOT a bounded [0,1] value
                evaluated_at=T0,
            )
        )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    # Old (broken) behavior would have clamped this to 0.0. Relative error is 8/220 ≈ 0.036, so
    # accuracy should land close to 1 - 0.036 ≈ 0.964, not 0.
    assert prediction.confidence.historical_accuracy == pytest.approx(1.0 - 8.0 / 220.0, abs=1e-6)
    assert prediction.confidence.historical_accuracy > 0.9


@pytest.mark.asyncio
async def test_generate_reflects_kg_and_news_and_community_signals(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    artifact_store,
):
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.retrieval_market", artifact_store=artifact_store,
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
    prediction_repo, artifact_store,
):
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.stability_market", artifact_store=artifact_store,
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


@pytest.mark.asyncio
async def test_generate_serves_a_real_trained_model_when_champion_has_an_artifact(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    context_builder, predictors, confidence_engine_dep, explainability_engine, retrieval_service,
    prediction_outcome_repo, model_evaluation_repo, prediction_repo, model_loader, artifact_store,
):
    """The core fix: a Champion with a real artifact_ref must be loaded and served via
    TrainedModelPredictor — not silently ignored in favor of the generic formula predictor, which
    is what happened before this fix regardless of what the Model Registry said."""
    market, _placeholder_champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.trained_model_market",
    )
    feature_key = "football.team.form_index_last5"
    artifact_ref, _algorithm = await _fit_and_store_sklearn_model(artifact_store, TargetType.CLASSIFICATION, feature_key)

    trained_model = await model_registry.register(
        market_id=market.id, model_key="football.trained_model_market.logistic_regression", version=2,
        algorithm=MLAlgorithm.LOGISTIC_REGRESSION.value, framework="sklearn", artifact_ref=artifact_ref, now=T0,
    )
    await model_registry.promote_to_challenger(trained_model.id)
    real_champion = await model_registry.promote_to_champion(trained_model.id, approved_by="cto", now=T0)

    engine_with_loader = PredictionEngine(
        context_builder=context_builder, predictors=predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, model_loader=model_loader,
    )

    prediction = await engine_with_loader.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.model_id == real_champion.id
    # A real sklearn LogisticRegression's predict_one() output — never the generic
    # WeightedLogisticPredictor's "positive"/"negative" bare-formula label.
    assert prediction.value in ("positive", "negative")
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.predictor_provenance == "trained_model"
    # Forensic audit §3/§13 — no fallback occurred, so there's nothing to explain.
    assert prediction.fallback_reason is None


@pytest.mark.asyncio
async def test_generate_raises_when_champion_is_a_never_trained_placeholder(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    context_builder, predictors, confidence_engine_dep, explainability_engine, retrieval_service,
    prediction_outcome_repo, model_evaluation_repo, prediction_repo, model_loader,
):
    """Master rebuild command §3/§104 (2026-08-30): a market may only ever serve a prediction
    from its own genuinely-trained Champion — a placeholder (no artifact_ref) must now raise
    ChampionUnavailableError, never silently serve a generic formula prediction. This replaces
    the pre-rebuild `test_generate_falls_back_to_registry_for_placeholder_champion_even_with_
    loader_wired`, which asserted the exact opposite of the now-required behavior."""
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.placeholder_champion_market",
    )
    assert champion.artifact_ref is None

    engine_with_loader = PredictionEngine(
        context_builder=context_builder, predictors=predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, model_loader=model_loader,
    )

    with pytest.raises(ChampionUnavailableError) as exc_info:
        await engine_with_loader.generate(
            market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
        )

    assert exc_info.value.reason_code == "NO_ARTIFACT_REGISTERED"
    assert exc_info.value.market_key == market.market_key


@pytest.mark.asyncio
async def test_generate_reports_uncalibrated_when_the_model_has_never_been_fitted(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    artifact_store,
):
    """Section 31 audit fix (2026-08-23), extended by Phase 4: `calibrate()`'s identity
    pass-through for a never-fitted model must never be reported to the API as calibrated —
    every model starts unfitted, so a freshly generated prediction must say so honestly rather
    than implying real calibration ran. `raw_probability` must equal `probability` (identity),
    and no metadata is recorded since no fit exists."""
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.uncalibrated_market", artifact_store=artifact_store,
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.model_id == champion.id
    assert prediction.calibration_status == "UNFITTED"
    assert prediction.raw_probability == prediction.probability
    assert prediction.calibration_sample_count is None
    assert prediction.calibration_fitted_at is None


@pytest.mark.asyncio
async def test_generate_reports_calibrated_once_the_model_has_actually_been_fitted(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    artifact_store,
):
    """The other half of the same fix: once `CalibratorPort.fit()` has genuinely run for this
    model, a subsequent prediction must report the real "FITTED" status (Phase 4 taxonomy) — this
    is not a permanently-unfitted posture, just an honest one until a real fit has happened. The
    fit's sample count/fitted_at must be recorded, and `raw_probability` must differ from the
    now-calibrated `probability` (the fit is a genuine transform, not an identity)."""
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.calibrated_market", artifact_store=artifact_store,
    )
    await engine.calibrator.fit(champion.id, [(0.6, True), (0.4, False), (0.7, True), (0.3, False)])

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.model_id == champion.id
    assert prediction.calibration_status == "FITTED"
    assert prediction.calibration_sample_count == 4
    assert prediction.calibration_fitted_at is not None
    assert prediction.raw_probability != prediction.probability


@pytest.mark.asyncio
async def test_generate_reports_stale_when_the_fit_is_older_than_the_staleness_window(
    context_builder, predictors, confidence_engine_dep, explainability_engine, retrieval_service,
    prediction_outcome_repo, model_evaluation_repo, prediction_repo,
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    model_loader, artifact_store,
):
    """Phase 4 (Calibration Integrity): a fit that exists but predates the configured staleness
    window must be reported as "STALE", not "FITTED" — still applied (a stale calibration is
    still better than none), but flagged so a caller can tell the difference.

    `PlattScalingCalibrator.fit()`'s in-memory (no `repository`) mode stamps `fitted_at` with
    real wall-clock `datetime.now()`, not a caller-supplied `now` — unlike the rest of this
    codebase's explicit-`now`-threading convention, but harmless in production (a real fit's
    "when it happened" genuinely is wall-clock time) and only a testability wrinkle: this test
    anchors `generate()`'s `now` off real wall-clock time too, rather than the fixed historical
    `T0` every other test in this file uses, so the elapsed time is real and positive."""
    engine = PredictionEngine(
        context_builder=context_builder, predictors=predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, expected_kg_facts=10, calibration_staleness=timedelta(days=1),
        model_loader=model_loader,
    )
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.stale_calibration_market", artifact_store=artifact_store,
    )
    await engine.calibrator.fit(champion.id, [(0.6, True), (0.4, False), (0.7, True), (0.3, False)])

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1",
        now=datetime.now(timezone.utc) + timedelta(days=2),
    )

    assert prediction.calibration_status == "STALE"
    assert prediction.calibration_sample_count == 4
    assert prediction.raw_probability != prediction.probability  # still applied, just flagged


@pytest.mark.asyncio
async def test_generate_reports_invalid_and_uses_raw_probability_when_calibration_is_non_finite(
    context_builder, predictors, confidence_engine_dep, explainability_engine, retrieval_service,
    prediction_outcome_repo, model_evaluation_repo, prediction_repo,
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    model_loader, artifact_store,
):
    """Phase 4: a corrupt/degenerate calibration fit (NaN/Inf) must never poison the published
    probability — `generate()` must detect it, discard it, and honestly report "INVALID" rather
    than publishing a NaN or silently pretending the raw pass-through was a real calibration."""

    @dataclass
    class _NonFiniteCalibrator:
        async def calibrate(self, model_id, raw_probability: float) -> float:
            return float("nan")

        async def fit(self, model_id, samples) -> None:
            raise NotImplementedError

        async def is_fitted(self, model_id) -> bool:
            return True

        async def get_metadata(self, model_id):
            return CalibrationMetadata(sample_count=25, fitted_at=T0)

    engine = PredictionEngine(
        context_builder=context_builder, predictors=predictors, calibrator=_NonFiniteCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, expected_kg_facts=10, model_loader=model_loader,
    )
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.invalid_calibration_market", artifact_store=artifact_store,
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.calibration_status == "INVALID"
    assert prediction.probability == prediction.raw_probability  # non-finite result discarded
    assert prediction.probability == prediction.probability  # not NaN (NaN != NaN)


@pytest.mark.asyncio
async def test_generate_skips_the_post_hoc_calibrator_when_the_champions_own_artifact_is_already_calibrated(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    artifact_store,
):
    """Phase 4: `CalibrationValidationService` can promote a Champion whose own artifact already
    bakes in calibration (`ModelDefinition.calibration_ref` set). Passing that Champion's
    already-calibrated output through the separate post-hoc `PlattScalingCalibrator` layer too
    would double-calibrate every prediction — a real correctness gap between this codebase's two
    independent calibration mechanisms. Even with a genuine, non-identity Platt fit sitting right
    there for the same model_id, `generate()` must not apply it."""
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.model_baked_calibration_market", artifact_store=artifact_store,
    )
    await model_registry.models.upsert(replace(champion, calibration_ref="isotonic_regression"))
    # A real, non-identity fit for the same model_id — proves it's genuinely bypassed, not just
    # coincidentally unfitted.
    await engine.calibrator.fit(champion.id, [(0.6, True), (0.4, False), (0.7, True), (0.3, False)])

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.calibration_status == "FITTED"
    assert prediction.calibration_sample_count is None
    assert prediction.calibration_fitted_at is None
    assert prediction.raw_probability == prediction.probability


@pytest.mark.asyncio
async def test_generate_staleness_check_survives_a_real_sql_backed_naive_datetime_round_trip(
    context_builder, predictors, confidence_engine_dep, explainability_engine, retrieval_service,
    prediction_outcome_repo, model_evaluation_repo, prediction_repo,
    market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    sqlite_session, model_loader, artifact_store,
):
    """Phase 3 verification found the exact same bug shape in `model_registry_service.py`:
    `now - <a real SQL-backed timestamp>` crashes with `TypeError: can't subtract offset-naive
    and offset-aware datetimes` once SQLite/aiosqlite has dropped tzinfo on read-back (ADR-007) —
    invisible to any test using an in-memory calibrator, since only a real repository round-trip
    exhibits it. This is that same regression, reproduced for `_calibrate()`'s own
    `_ensure_aware(metadata.fitted_at, now)` staleness check via the real
    `SqlAlchemyCalibrationParametersRepository`, not an in-memory stand-in."""
    engine = PredictionEngine(
        context_builder=context_builder, predictors=predictors,
        calibrator=PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=sqlite_session)),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, expected_kg_facts=10, calibration_staleness=timedelta(days=1),
        model_loader=model_loader,
    )
    market, champion = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.sql_backed_staleness_market", artifact_store=artifact_store,
    )
    await engine.calibrator.fit(champion.id, [(0.6, True), (0.4, False), (0.7, True), (0.3, False)])
    await sqlite_session.commit()

    # `PlattScalingCalibrator.fit()` stamps `fitted_at` with real wall-clock time regardless of
    # repository mode (see its own docstring note) — anchored here off real `datetime.now()`
    # rather than the fixed historical `T0` every other test in this file uses, same reasoning as
    # `test_generate_reports_stale_when_the_fit_is_older_than_the_staleness_window` above.
    real_now = datetime.now(timezone.utc)
    fresh = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=real_now
    )
    stale = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1",
        now=real_now + timedelta(days=2),
    )

    assert fresh.calibration_status == "FITTED"
    assert stale.calibration_status == "STALE"


@pytest.mark.asyncio
async def test_generate_raises_when_artifact_cannot_be_loaded(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    context_builder, predictors, confidence_engine_dep, explainability_engine, retrieval_service,
    prediction_outcome_repo, model_evaluation_repo, prediction_repo, model_loader,
):
    """Master rebuild command §3/§104 (2026-08-30): a Champion that claims an artifact_ref
    pointing at nothing real (corrupt data, wrong framework, missing file) must never crash
    generation, but it also must never silently fall back to a generic formula predictor —
    ChampionUnavailableError is the honest outcome now. Replaces the pre-rebuild
    `test_generate_falls_back_when_artifact_cannot_be_loaded`."""
    market, _placeholder = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.broken_artifact_market",
    )
    broken_model = await model_registry.register(
        market_id=market.id, model_key="football.broken_artifact_market.lightgbm", version=2,
        algorithm="lightgbm_gbm", framework="lightgbm", artifact_ref="does-not-exist.bin", now=T0,
    )
    await model_registry.promote_to_challenger(broken_model.id)
    await model_registry.promote_to_champion(broken_model.id, approved_by="cto", now=T0)

    engine_with_loader = PredictionEngine(
        context_builder=context_builder, predictors=predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, model_loader=model_loader,
    )

    with pytest.raises(ChampionUnavailableError) as exc_info:
        await engine_with_loader.generate(
            market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
        )

    # Forensic audit §3/§13 — a genuinely missing/unreachable artifact, distinct from a checksum
    # mismatch (real file exists but doesn't hash to what was recorded) or no artifact at all.
    assert exc_info.value.reason_code == "ARTIFACT_LOAD_FAILURE"


@pytest.mark.asyncio
async def test_generate_raises_integrity_mismatch_on_checksum_mismatch(
    engine, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    context_builder, predictors, confidence_engine_dep, explainability_engine, retrieval_service,
    prediction_outcome_repo, model_evaluation_repo, prediction_repo, model_loader, artifact_store,
):
    """Forensic audit §15 "Model Artifact Integrity", updated for the master rebuild command
    §3/§104 (2026-08-30): a real, loadable artifact whose bytes don't hash to the checksum
    recorded at training time (corrupted, overwritten, or swapped out-of-band) must raise
    ChampionUnavailableError — distinguishable via reason_code from a missing artifact, but no
    longer silently served through a formula fallback either. Replaces the pre-rebuild
    `test_generate_falls_back_and_flags_integrity_mismatch_on_checksum_mismatch`."""
    market, _placeholder = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.tampered_artifact_market",
    )
    feature_key = "football.team.form_index_last5"
    artifact_ref, algorithm = await _fit_and_store_sklearn_model(artifact_store, TargetType.CLASSIFICATION, feature_key)

    tampered_model = await model_registry.register(
        market_id=market.id, model_key="football.tampered_artifact_market.logistic_regression", version=2,
        algorithm=algorithm, framework="sklearn", artifact_ref=artifact_ref, now=T0,
        artifact_checksum="0" * 64,  # deliberately wrong — cannot match the real artifact's real hash
    )
    await model_registry.promote_to_challenger(tampered_model.id)
    await model_registry.promote_to_champion(tampered_model.id, approved_by="cto", now=T0)

    engine_with_loader = PredictionEngine(
        context_builder=context_builder, predictors=predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, model_loader=model_loader,
    )

    with pytest.raises(ChampionUnavailableError) as exc_info:
        await engine_with_loader.generate(
            market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
        )

    assert exc_info.value.reason_code == "ARTIFACT_INTEGRITY_MISMATCH"


@pytest.mark.asyncio
async def test_generate_populates_probability_distribution_for_classification_market(
    engine, context_builder, market_registry, model_registry, mapping_service, feature_definition_repo,
    feature_value_repo,
):
    """Universal Probability Engine — every classification prediction stores the full probability
    distribution, not just the winning outcome, and the winning entry matches the published,
    calibrated `Prediction.probability` exactly (not the predictor's raw pre-calibration value).

    Exercises `_shape_outcome`/`_calibrate` directly against a real `WeightedLogisticPredictor`
    output rather than going through `generate()`'s Champion resolution (master rebuild command
    §3, 2026-08-30: `_resolve_predictor` no longer ever returns a formula predictor) — this test
    is genuinely about the distribution/calibration math, not which predictor served it."""
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.distribution_market",
    )
    context = await context_builder.build(market.market_key, EntityType.FIXTURE, "fixture-1", T0)
    predictor_output = await WeightedLogisticPredictor().predict(
        context.market.market_kind, context.resolved_features, context.mapping_weights
    )
    calibrated_probability, *_ = await engine._calibrate(context, predictor_output.probability, T0)
    value, probability, probability_distribution, confidence_interval, expected_error, _raw = (
        await engine._shape_outcome(context, predictor_output, calibrated_probability)
    )

    assert set(probability_distribution.keys()) == {"positive", "negative"}
    assert sum(probability_distribution.values()) == pytest.approx(1.0)
    assert probability_distribution[value] == pytest.approx(probability)
    assert confidence_interval is None
    assert expected_error is None


@pytest.mark.asyncio
async def test_generate_distribution_sums_to_one_when_the_negative_side_wins(
    engine, context_builder, market_registry, model_registry, mapping_service, feature_definition_repo,
    feature_value_repo,
):
    """Regression test for a real bug: `WeightedLogisticPredictor.probability` is always
    P("positive") regardless of which side `value` actually is — a negative feature value makes
    "negative" win with `raw_score < 0` (P(positive) < 0.5). Before the fix, `_shape_outcome`
    calibrated the *winning* key ("negative") to `predictor_output.probability` (which is P(positive),
    not P(negative)) and left "positive" at its own raw P(positive) unchanged — both entries ended
    up carrying nearly the same number and the distribution summed to well under 1.0.

    Same direct `_shape_outcome` exercise as the test above — see its own comment for why."""
    market, _ = await _setup_production_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "football.negative_side_wins_market", feature_value=-0.8,
    )
    context = await context_builder.build(market.market_key, EntityType.FIXTURE, "fixture-1", T0)
    predictor_output = await WeightedLogisticPredictor().predict(
        context.market.market_kind, context.resolved_features, context.mapping_weights
    )
    calibrated_probability, *_ = await engine._calibrate(context, predictor_output.probability, T0)
    value, probability, probability_distribution, _ci, _ee, _raw = await engine._shape_outcome(
        context, predictor_output, calibrated_probability
    )

    assert value == "negative"
    assert sum(probability_distribution.values()) == pytest.approx(1.0)
    assert probability_distribution["negative"] == pytest.approx(probability)


@pytest.mark.asyncio
async def test_generate_regression_market_stores_raw_value_not_fake_probability(
    context_builder, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    confidence_engine_dep, explainability_engine, retrieval_service, prediction_outcome_repo,
    model_evaluation_repo, prediction_repo, model_loader, artifact_store,
):
    """Universal Probability Engine — a REGRESSION-shaped market's `value` is the predicted
    continuous number itself (from the predictor's `raw_score`), and it never gets a
    `probability_distribution` (no discrete outcome space exists for it). Real Champion resolution
    (master rebuild command §3, 2026-08-30) means `prediction.value` is now whatever the real
    fitted Ridge model predicts, not the exact literal `feature_value` a formula predictor's raw
    weighted sum used to reproduce — the assertion checks it's a real finite number, not a
    specific figure a formula fallback happened to compute."""
    market, _ = await _setup_regression_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "basketball.regression_market", artifact_store=artifact_store,
    )
    linear_predictors = PredictorRegistry()
    linear_predictors.register_many(WeightedLinearPredictor.SUPPORTED_KINDS, WeightedLinearPredictor())
    engine = PredictionEngine(
        context_builder=context_builder, predictors=linear_predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, model_loader=model_loader,
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert math.isfinite(float(prediction.value))
    assert prediction.probability_distribution == {}
    # No PredictionOutcome history recorded yet for this market — an honest gap, not a fabricated
    # interval (see _regression_uncertainty's docstring).
    assert prediction.confidence_interval is None
    assert prediction.expected_error is None


@pytest.mark.asyncio
async def test_generate_regression_market_derives_confidence_interval_from_history(
    context_builder, market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
    confidence_engine_dep, explainability_engine, retrieval_service, prediction_outcome_repo,
    model_evaluation_repo, prediction_repo, model_loader, artifact_store,
):
    market, _ = await _setup_regression_market(
        market_registry, model_registry, mapping_service, feature_definition_repo, feature_value_repo,
        "basketball.regression_history_market", artifact_store=artifact_store,
    )
    for error in (2.0, 4.0):
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()), prediction_id=PredictionId(uuid4()),
                actual_value="26.0", error=error, evaluated_at=T0,
            )
        )
    linear_predictors = PredictorRegistry()
    linear_predictors.register_many(WeightedLinearPredictor.SUPPORTED_KINDS, WeightedLinearPredictor())
    engine = PredictionEngine(
        context_builder=context_builder, predictors=linear_predictors, calibrator=PlattScalingCalibrator(),
        confidence_engine=confidence_engine_dep, explainability_engine=explainability_engine,
        retrieval=retrieval_service, outcomes=prediction_outcome_repo, model_evaluations=model_evaluation_repo,
        predictions=prediction_repo, model_loader=model_loader,
    )

    prediction = await engine.generate(
        market.market_key, EntityType.FIXTURE, "fixture-1", subject_ref="fixture-1", now=T0
    )

    assert prediction.expected_error == pytest.approx(3.0)
    predicted_value = float(prediction.value)
    assert prediction.confidence_interval == pytest.approx((predicted_value - 3.0, predicted_value + 3.0))

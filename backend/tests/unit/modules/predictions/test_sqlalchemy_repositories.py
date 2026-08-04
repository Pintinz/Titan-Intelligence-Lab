from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    Experiment,
    ExplanationBundle,
    FeatureMarketMapping,
    MarketDefinition,
    ModelDefinition,
    ModelEvaluation,
    Prediction,
    PredictionAudit,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    AuditAction,
    ExperimentId,
    FeatureMarketMappingId,
    MarketId,
    MarketKind,
    MarketStatus,
    ModelEvaluationId,
    ModelId,
    ModelStatus,
    OutcomeType,
    PredictionAuditId,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyExperimentRepository,
    SqlAlchemyFeatureMarketMappingRepository,
    SqlAlchemyMarketRepository,
    SqlAlchemyModelEvaluationRepository,
    SqlAlchemyModelRepository,
    SqlAlchemyPredictionAuditRepository,
    SqlAlchemyPredictionOutcomeRepository,
    SqlAlchemyPredictionRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _market(**overrides) -> MarketDefinition:
    defaults = dict(
        id=MarketId(uuid4()),
        market_key="football.match_result",
        sport_code="football",
        name="Match Result",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )
    defaults.update(overrides)
    return MarketDefinition(**defaults)


@pytest.mark.asyncio
async def test_market_repository_round_trip(sqlite_session):
    repo = SqlAlchemyMarketRepository(session=sqlite_session)
    market = _market()

    await repo.upsert(market)
    await sqlite_session.commit()

    by_id = await repo.get(market.id)
    by_key = await repo.get_by_key(market.market_key)
    assert by_id.market_key == market.market_key
    assert by_key.market_kind is MarketKind.BINARY
    assert by_key.target_type is TargetType.CLASSIFICATION
    assert by_key.status is MarketStatus.PRODUCTION


@pytest.mark.asyncio
async def test_market_repository_round_trips_outcome_registry_fields(sqlite_session):
    """Milestone 9.2: outcome_type/allowed_values/resolver_key/gemini_prompt_template must
    survive a real DB round trip, not just live on the in-memory dataclass."""
    repo = SqlAlchemyMarketRepository(session=sqlite_session)
    market = _market(
        market_key="football.match_winner",
        outcome_type=OutcomeType.HOME_DRAW_AWAY,
        allowed_values=("HOME_WIN", "DRAW", "AWAY_WIN"),
        resolver_key="football.match_winner",
        gemini_prompt_template="Explain the {predicted_outcome} prediction.",
    )

    await repo.upsert(market)
    await sqlite_session.commit()

    reloaded = await repo.get_by_key("football.match_winner")
    assert reloaded.outcome_type is OutcomeType.HOME_DRAW_AWAY
    assert reloaded.allowed_values == ("HOME_WIN", "DRAW", "AWAY_WIN")
    assert reloaded.resolver_key == "football.match_winner"
    assert reloaded.gemini_prompt_template == "Explain the {predicted_outcome} prediction."


@pytest.mark.asyncio
async def test_market_repository_outcome_registry_fields_default_none_for_legacy_rows(sqlite_session):
    """A market registered before Milestone 9.2 (no outcome-registry kwargs supplied) must round
    trip with these fields as None/empty, not error or silently invent a value."""
    repo = SqlAlchemyMarketRepository(session=sqlite_session)
    await repo.upsert(_market())
    await sqlite_session.commit()

    reloaded = await repo.get_by_key("football.match_result")
    assert reloaded.outcome_type is None
    assert reloaded.allowed_values == ()
    assert reloaded.resolver_key is None
    assert reloaded.gemini_prompt_template is None


@pytest.mark.asyncio
async def test_market_repository_list_by_sport_and_status(sqlite_session):
    repo = SqlAlchemyMarketRepository(session=sqlite_session)
    await repo.upsert(_market(market_key="football.a", status=MarketStatus.PRODUCTION))
    await repo.upsert(_market(market_key="football.b", status=MarketStatus.DRAFT))
    await repo.upsert(_market(market_key="basketball.a", sport_code="basketball"))
    await sqlite_session.commit()

    football_markets = await repo.list_by_sport("football")
    production_markets = await repo.list_by_status(MarketStatus.PRODUCTION)

    assert {m.market_key for m in football_markets} == {"football.a", "football.b"}
    assert {m.market_key for m in production_markets} == {"football.a", "basketball.a"}


@pytest.mark.asyncio
async def test_feature_market_mapping_repository_round_trip(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    mappings = SqlAlchemyFeatureMarketMappingRepository(session=sqlite_session)
    market = _market()
    await markets.upsert(market)

    mapping = FeatureMarketMapping(
        id=FeatureMarketMappingId(uuid4()), market_id=market.id, feature_key="team_form", weight=1.5
    )
    await mappings.upsert(mapping)
    await sqlite_session.commit()

    by_market = await mappings.list_by_market(market.id)
    by_feature = await mappings.list_by_feature("team_form")
    assert len(by_market) == 1
    assert by_market[0].weight == 1.5
    assert len(by_feature) == 1


@pytest.mark.asyncio
async def test_model_repository_round_trip_and_champion_lookup(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    market = _market()
    await markets.upsert(market)

    candidate = ModelDefinition(
        id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1"
    )
    champion = ModelDefinition(
        id=ModelId(uuid4()),
        market_id=market.id,
        model_key="m2",
        version=1,
        algorithm="heuristic_logistic_v1",
        status=ModelStatus.CHAMPION,
    )
    await models.upsert(candidate)
    await models.upsert(champion)
    await sqlite_session.commit()

    fetched_champion = await models.get_champion(market.id)
    by_key_version = await models.get_by_key_version("m1", 1)
    candidates = await models.list_by_status(market.id, ModelStatus.CANDIDATE)

    assert fetched_champion.id == champion.id
    assert by_key_version.id == candidate.id
    assert len(candidates) == 1


@pytest.mark.asyncio
async def test_model_repository_round_trip_preserves_ml_platform_fields(sqlite_session):
    """Milestone 9.1 task #163/#169 additive columns."""
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    market = _market()
    await markets.upsert(market)

    model = ModelDefinition(
        id=ModelId(uuid4()),
        market_id=market.id,
        model_key="football.match_result.lightgbm",
        version=1,
        algorithm="lightgbm_gbm",
        framework="lightgbm",
        dataset_version=3,
        feature_versions={"football.shots_on_target": 2},
        training_run_ref="run-123",
        calibration_report_ref="calib-ref-1",
        feature_importance_ref="importance-ref-1",
        artifact_ref="artifacts/football/match_result/v1.bin",
        deployment_mode="shadow",
    )
    await models.upsert(model)
    await sqlite_session.commit()

    fetched = await models.get(model.id)

    assert fetched.framework == "lightgbm"
    assert fetched.dataset_version == 3
    assert fetched.feature_versions == {"football.shots_on_target": 2}
    assert fetched.training_run_ref == "run-123"
    assert fetched.calibration_report_ref == "calib-ref-1"
    assert fetched.feature_importance_ref == "importance-ref-1"
    assert fetched.artifact_ref == "artifacts/football/match_result/v1.bin"
    assert fetched.deployment_mode == "shadow"


@pytest.mark.asyncio
async def test_prediction_repository_round_trip_preserves_confidence_and_explanation(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)

    prediction = Prediction(
        id=PredictionId(uuid4()),
        market_id=market.id,
        model_id=model.id,
        subject_ref="fixture-1",
        value="positive",
        probability=0.73,
        confidence=ConfidenceBreakdown(*([0.6] * 9)),
        explanation=ExplanationBundle(
            top_positive_features=(("team_form", 0.5),),
            top_negative_features=(("injuries", -0.2),),
            feature_importance={"team_form": 0.7, "injuries": 0.3},
            knowledge_graph_evidence=("TeamA rivalry_with TeamB",),
            news_contribution=("Star striker injured",),
            community_contribution=(),
            ai_explanation="explained",
        ),
        feature_snapshot={"team_form": 0.8},
        model_version="1",
        status=PredictionStatus.PUBLISHED,
        generated_at=T0,
        data_freshness=T0,
    )
    await predictions.record(prediction)
    await sqlite_session.commit()

    fetched = await predictions.get(prediction.id)
    assert fetched.probability == pytest.approx(0.73)
    assert fetched.confidence.composite == pytest.approx(0.6)
    assert fetched.explanation.top_positive_features == (("team_form", 0.5),)
    assert fetched.explanation.feature_importance == {"team_form": 0.7, "injuries": 0.3}
    assert fetched.feature_snapshot == {"team_form": 0.8}


@pytest.mark.asyncio
async def test_prediction_repository_round_trip_preserves_probability_distribution(sqlite_session):
    """Universal Probability Engine additive fields — a classification-shaped prediction's full
    outcome distribution round-trips through the JSON column."""
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)

    prediction = Prediction(
        id=PredictionId(uuid4()),
        market_id=market.id,
        model_id=model.id,
        subject_ref="fixture-1",
        value="HOME_WIN",
        probability=0.55,
        confidence=ConfidenceBreakdown(*([0.6] * 9)),
        explanation=ExplanationBundle(),
        feature_snapshot={},
        model_version="1",
        probability_distribution={"HOME_WIN": 0.55, "DRAW": 0.25, "AWAY_WIN": 0.2},
    )
    await predictions.record(prediction)
    await sqlite_session.commit()

    fetched = await predictions.get(prediction.id)
    assert fetched.probability_distribution == {"HOME_WIN": 0.55, "DRAW": 0.25, "AWAY_WIN": 0.2}
    assert fetched.confidence_interval is None
    assert fetched.expected_error is None


@pytest.mark.asyncio
async def test_prediction_repository_round_trip_preserves_regression_uncertainty_fields(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_linear_v1")
    await markets.upsert(market)
    await models.upsert(model)

    prediction = Prediction(
        id=PredictionId(uuid4()),
        market_id=market.id,
        model_id=model.id,
        subject_ref="fixture-1",
        value="24.5000",
        probability=0.5,
        confidence=ConfidenceBreakdown(*([0.6] * 9)),
        explanation=ExplanationBundle(),
        feature_snapshot={},
        model_version="1",
        confidence_interval=(21.5, 27.5),
        expected_error=3.0,
    )
    await predictions.record(prediction)
    await sqlite_session.commit()

    fetched = await predictions.get(prediction.id)
    assert fetched.confidence_interval == pytest.approx((21.5, 27.5))
    assert fetched.expected_error == pytest.approx(3.0)
    assert fetched.probability_distribution == {}


@pytest.mark.asyncio
async def test_prediction_repository_versioning_queries(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)

    def _prediction(generated_at, status=PredictionStatus.PUBLISHED):
        return Prediction(
            id=PredictionId(uuid4()), market_id=market.id, model_id=model.id, subject_ref="fixture-1", value="positive",
            probability=0.6, confidence=ConfidenceBreakdown(*([0.5] * 9)), explanation=ExplanationBundle(),
            feature_snapshot={}, model_version="1", status=status, generated_at=generated_at, data_freshness=generated_at,
        )

    older = _prediction(T0)
    newer = _prediction(T0.replace(hour=12))
    await predictions.record(older)
    await predictions.record(newer)
    await sqlite_session.commit()

    latest = await predictions.get_latest_for_subject("fixture-1", market.id)
    ordered = await predictions.list_by_subject("fixture-1", market.id)

    assert latest.id == newer.id
    assert [p.id for p in ordered] == [newer.id, older.id]


@pytest.mark.asyncio
async def test_prediction_outcome_repository_round_trip(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    outcomes = SqlAlchemyPredictionOutcomeRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)
    prediction = Prediction(
        id=PredictionId(uuid4()), market_id=market.id, model_id=model.id, subject_ref="fixture-1", value="positive",
        probability=0.6, confidence=ConfidenceBreakdown(*([0.5] * 9)), explanation=ExplanationBundle(),
        feature_snapshot={}, model_version="1", generated_at=T0,
    )
    await predictions.record(prediction)

    outcome = PredictionOutcome(
        id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id, actual_value="home_win", error=0.0, evaluated_at=T0
    )
    await outcomes.record(outcome)
    await sqlite_session.commit()

    fetched = await outcomes.get_for_prediction(prediction.id)
    by_market = await outcomes.list_by_market(market.id)
    assert fetched.actual_value == "home_win"
    assert len(by_market) == 1


@pytest.mark.asyncio
async def test_model_evaluation_repository_get_latest(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    evaluations = SqlAlchemyModelEvaluationRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)

    older = ModelEvaluation(id=ModelEvaluationId(uuid4()), model_id=model.id, evaluated_at=T0, metrics={"reliability": 0.5})
    newer = ModelEvaluation(
        id=ModelEvaluationId(uuid4()), model_id=model.id, evaluated_at=T0.replace(hour=12), metrics={"reliability": 0.8}
    )
    await evaluations.record(older)
    await evaluations.record(newer)
    await sqlite_session.commit()

    latest = await evaluations.get_latest(model.id)
    assert latest.metrics["reliability"] == 0.8


@pytest.mark.asyncio
async def test_experiment_repository_round_trip_and_update(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    experiments = SqlAlchemyExperimentRepository(session=sqlite_session)
    market = _market()
    await markets.upsert(market)

    experiment = Experiment(id=ExperimentId(uuid4()), market_id=market.id, config={"benchmark": "v1_vs_v2"}, created_at=T0)
    await experiments.record(experiment)
    await sqlite_session.commit()

    experiment.decision = "promoted"
    await experiments.update(experiment)
    await sqlite_session.commit()

    fetched = await experiments.get(experiment.id)
    by_market = await experiments.list_by_market(market.id)
    assert fetched.decision == "promoted"
    assert len(by_market) == 1


@pytest.mark.asyncio
async def test_prediction_audit_repository_round_trip(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    audits = SqlAlchemyPredictionAuditRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)
    prediction = Prediction(
        id=PredictionId(uuid4()), market_id=market.id, model_id=model.id, subject_ref="fixture-1", value="positive",
        probability=0.6, confidence=ConfidenceBreakdown(*([0.5] * 9)), explanation=ExplanationBundle(),
        feature_snapshot={}, model_version="1", generated_at=T0,
    )
    await predictions.record(prediction)

    audit = PredictionAudit(
        id=PredictionAuditId(uuid4()), action=AuditAction.GENERATED, actor="prediction-engine", occurred_at=T0,
        prediction_id=prediction.id, market_id=market.id, model_id=model.id, details={"note": "auto"},
    )
    await audits.record(audit)
    await sqlite_session.commit()

    by_prediction = await audits.list_by_prediction(prediction.id)
    recent = await audits.list_recent()
    assert len(by_prediction) == 1
    assert by_prediction[0].details == {"note": "auto"}
    assert len(recent) == 1


@pytest.mark.asyncio
async def test_market_repository_list_all(sqlite_session):
    repo = SqlAlchemyMarketRepository(session=sqlite_session)
    await repo.upsert(_market(market_key="football.list_all_a"))
    await repo.upsert(_market(market_key="football.list_all_b"))
    await sqlite_session.commit()

    results = await repo.list_all()

    assert {m.market_key for m in results} == {"football.list_all_a", "football.list_all_b"}


@pytest.mark.asyncio
async def test_model_repository_get_and_list_by_market(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    market = _market()
    await markets.upsert(market)
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await models.upsert(model)
    await sqlite_session.commit()

    fetched = await models.get(model.id)
    by_market = await models.list_by_market(market.id)

    assert fetched.model_key == "m1"
    assert len(by_market) == 1


@pytest.mark.asyncio
async def test_prediction_repository_update_list_by_market_and_list_recent(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)
    prediction = Prediction(
        id=PredictionId(uuid4()), market_id=market.id, model_id=model.id, subject_ref="fixture-1", value="positive",
        probability=0.6, confidence=ConfidenceBreakdown(*([0.5] * 9)), explanation=ExplanationBundle(),
        feature_snapshot={}, model_version="1", status=PredictionStatus.DRAFT, generated_at=T0,
    )
    await predictions.record(prediction)
    await sqlite_session.commit()

    prediction.status = PredictionStatus.PUBLISHED
    updated = await predictions.update(prediction)
    await sqlite_session.commit()

    by_market_published = await predictions.list_by_market(market.id, status=PredictionStatus.PUBLISHED)
    by_market_draft = await predictions.list_by_market(market.id, status=PredictionStatus.DRAFT)
    recent = await predictions.list_recent()

    assert updated.status is PredictionStatus.PUBLISHED
    assert len(by_market_published) == 1
    assert len(by_market_draft) == 0
    assert len(recent) == 1


@pytest.mark.asyncio
async def test_model_evaluation_repository_list_by_model(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    evaluations = SqlAlchemyModelEvaluationRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)
    await evaluations.record(ModelEvaluation(id=ModelEvaluationId(uuid4()), model_id=model.id, evaluated_at=T0, metrics={"reliability": 0.7}))
    await sqlite_session.commit()

    results = await evaluations.list_by_model(model.id)

    assert len(results) == 1
    assert results[0].metrics["reliability"] == 0.7


@pytest.mark.asyncio
async def test_prediction_audit_repository_list_recent_with_since_filter(sqlite_session):
    markets = SqlAlchemyMarketRepository(session=sqlite_session)
    models = SqlAlchemyModelRepository(session=sqlite_session)
    predictions = SqlAlchemyPredictionRepository(session=sqlite_session)
    audits = SqlAlchemyPredictionAuditRepository(session=sqlite_session)
    market = _market()
    model = ModelDefinition(id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1")
    await markets.upsert(market)
    await models.upsert(model)
    prediction = Prediction(
        id=PredictionId(uuid4()), market_id=market.id, model_id=model.id, subject_ref="fixture-1", value="positive",
        probability=0.6, confidence=ConfidenceBreakdown(*([0.5] * 9)), explanation=ExplanationBundle(),
        feature_snapshot={}, model_version="1", generated_at=T0,
    )
    await predictions.record(prediction)
    await audits.record(
        PredictionAudit(id=PredictionAuditId(uuid4()), action=AuditAction.GENERATED, actor="x", occurred_at=T0, prediction_id=prediction.id)
    )
    await sqlite_session.commit()

    since_future = await audits.list_recent(since=T0.replace(hour=23))
    since_past = await audits.list_recent(since=T0.replace(hour=0, minute=0))

    assert since_future == []
    assert len(since_past) == 1

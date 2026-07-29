from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

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
    PredictionAuditId,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
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
    )
    defaults.update(overrides)
    return MarketDefinition(**defaults)


def test_market_definition_is_production_only_when_status_production():
    draft = _market(status=MarketStatus.DRAFT)
    production = _market(status=MarketStatus.PRODUCTION)

    assert draft.is_production() is False
    assert production.is_production() is True


def test_feature_market_mapping_defaults():
    mapping = FeatureMarketMapping(
        id=FeatureMarketMappingId(uuid4()),
        market_id=MarketId(uuid4()),
        feature_key="team_form_last_5",
    )

    assert mapping.is_required is True
    assert mapping.weight == 1.0


def test_model_definition_defaults_to_candidate():
    model = ModelDefinition(
        id=ModelId(uuid4()),
        market_id=MarketId(uuid4()),
        model_key="football.match_result.heuristic_logistic",
        version=1,
        algorithm="heuristic_logistic_v1",
    )

    assert model.status is ModelStatus.CANDIDATE


def _confidence(**overrides) -> ConfidenceBreakdown:
    defaults = dict(
        feature_quality=1.0,
        feature_freshness=1.0,
        historical_accuracy=1.0,
        knowledge_graph_completeness=1.0,
        news_reliability=1.0,
        community_reliability=1.0,
        data_completeness=1.0,
        model_reliability=1.0,
        prediction_stability=1.0,
    )
    defaults.update(overrides)
    return ConfidenceBreakdown(**defaults)


def test_confidence_breakdown_composite_is_mean_of_nine_factors():
    confidence = _confidence()

    assert confidence.composite == 1.0


def test_confidence_breakdown_composite_with_mixed_values():
    confidence = _confidence(
        feature_quality=1.0,
        feature_freshness=0.0,
        historical_accuracy=1.0,
        knowledge_graph_completeness=0.0,
        news_reliability=1.0,
        community_reliability=0.0,
        data_completeness=1.0,
        model_reliability=0.0,
        prediction_stability=1.0,
    )

    assert confidence.composite == 5.0 / 9.0


def test_explanation_bundle_defaults_are_empty():
    bundle = ExplanationBundle()

    assert bundle.top_positive_features == ()
    assert bundle.feature_importance == {}
    assert bundle.ai_explanation == ""


def _prediction(**overrides) -> Prediction:
    defaults = dict(
        id=PredictionId(uuid4()),
        market_id=MarketId(uuid4()),
        model_id=ModelId(uuid4()),
        subject_ref=str(uuid4()),
        value="home_win",
        probability=0.62,
        confidence=_confidence(),
        explanation=ExplanationBundle(),
        feature_snapshot={"team_form_last_5": 0.8},
        model_version="1",
    )
    defaults.update(overrides)
    return Prediction(**defaults)


def test_prediction_is_published_only_when_status_published():
    draft = _prediction(status=PredictionStatus.DRAFT)
    published = _prediction(status=PredictionStatus.PUBLISHED)

    assert draft.is_published() is False
    assert published.is_published() is True


def test_prediction_outcome_holds_actual_value_and_error():
    outcome = PredictionOutcome(
        id=PredictionOutcomeId(uuid4()),
        prediction_id=PredictionId(uuid4()),
        actual_value="home_win",
        error=0.0,
        evaluated_at=T0,
    )

    assert outcome.actual_value == "home_win"
    assert outcome.error == 0.0


def test_model_evaluation_defaults_to_empty_metrics():
    evaluation = ModelEvaluation(
        id=ModelEvaluationId(uuid4()),
        model_id=ModelId(uuid4()),
        evaluated_at=T0,
    )

    assert evaluation.metrics == {}
    assert evaluation.calibration_report == {}


def test_experiment_defaults_to_pending_decision_none():
    experiment = Experiment(id=ExperimentId(uuid4()), market_id=MarketId(uuid4()))

    assert experiment.decision is None
    assert experiment.config == {}


def test_prediction_audit_records_action_and_actor():
    audit = PredictionAudit(
        id=PredictionAuditId(uuid4()),
        action=AuditAction.GENERATED,
        actor="prediction-engine",
        occurred_at=T0,
        prediction_id=PredictionId(uuid4()),
    )

    assert audit.action is AuditAction.GENERATED
    assert audit.actor == "prediction-engine"

from __future__ import annotations

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
from modules.predictions.infrastructure.persistence.models import (
    ExperimentModel,
    FeatureMarketMappingModel,
    MarketDefinitionModel,
    ModelDefinitionModel,
    ModelEvaluationModel,
    PredictionAuditModel,
    PredictionModel,
    PredictionOutcomeModel,
)


def market_to_domain(model: MarketDefinitionModel) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(model.id),
        market_key=model.market_key,
        sport_code=model.sport_code,
        name=model.name,
        category=model.category,
        market_kind=MarketKind(model.market_kind),
        target_type=TargetType(model.target_type),
        description=model.description,
        min_historical_window_days=model.min_historical_window_days,
        required_data_quality=model.required_data_quality,
        explainability_required=model.explainability_required,
        confidence_threshold=model.confidence_threshold,
        status=MarketStatus(model.status),
        owner=model.owner,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        reviewed_by=model.reviewed_by,
        reviewed_at=model.reviewed_at,
        rejection_reason=model.rejection_reason,
        deprecated_at=model.deprecated_at,
        outcome_type=OutcomeType(model.outcome_type) if model.outcome_type else None,
        allowed_values=tuple(model.allowed_values) if model.allowed_values else (),
        resolver_key=model.resolver_key,
        gemini_prompt_template=model.gemini_prompt_template,
    )


def market_to_model(entity: MarketDefinition, model: MarketDefinitionModel | None = None) -> MarketDefinitionModel:
    model = model or MarketDefinitionModel(id=entity.id.value)
    model.market_key = entity.market_key
    model.sport_code = entity.sport_code
    model.name = entity.name
    model.category = entity.category
    model.market_kind = entity.market_kind.value
    model.target_type = entity.target_type.value
    model.description = entity.description
    model.min_historical_window_days = entity.min_historical_window_days
    model.required_data_quality = entity.required_data_quality
    model.explainability_required = entity.explainability_required
    model.confidence_threshold = entity.confidence_threshold
    model.status = entity.status.value
    model.owner = entity.owner
    model.version = entity.version
    model.created_at = entity.created_at
    model.updated_at = entity.updated_at
    model.reviewed_by = entity.reviewed_by
    model.reviewed_at = entity.reviewed_at
    model.rejection_reason = entity.rejection_reason
    model.deprecated_at = entity.deprecated_at
    model.outcome_type = entity.outcome_type.value if entity.outcome_type else None
    model.allowed_values = list(entity.allowed_values) if entity.allowed_values else None
    model.resolver_key = entity.resolver_key
    model.gemini_prompt_template = entity.gemini_prompt_template
    return model


def feature_mapping_to_domain(model: FeatureMarketMappingModel) -> FeatureMarketMapping:
    return FeatureMarketMapping(
        id=FeatureMarketMappingId(model.id),
        market_id=MarketId(model.market_id),
        feature_key=model.feature_key,
        is_required=model.is_required,
        importance=model.importance,
        confidence_contribution=model.confidence_contribution,
        weight=model.weight,
    )


def feature_mapping_to_model(
    entity: FeatureMarketMapping, model: FeatureMarketMappingModel | None = None
) -> FeatureMarketMappingModel:
    model = model or FeatureMarketMappingModel(id=entity.id.value)
    model.market_id = entity.market_id.value
    model.feature_key = entity.feature_key
    model.is_required = entity.is_required
    model.importance = entity.importance
    model.confidence_contribution = entity.confidence_contribution
    model.weight = entity.weight
    return model


def model_definition_to_domain(model: ModelDefinitionModel) -> ModelDefinition:
    return ModelDefinition(
        id=ModelId(model.id),
        market_id=MarketId(model.market_id),
        model_key=model.model_key,
        version=model.version,
        algorithm=model.algorithm,
        status=ModelStatus(model.status),
        training_dataset_ref=model.training_dataset_ref,
        calibration_ref=model.calibration_ref,
        approved_by=model.approved_by,
        approved_at=model.approved_at,
        promoted_at=model.promoted_at,
        retired_at=model.retired_at,
        created_at=model.created_at,
        framework=model.framework,
        dataset_version=model.dataset_version,
        feature_versions=dict(model.feature_versions or {}),
        training_run_ref=model.training_run_ref,
        calibration_report_ref=model.calibration_report_ref,
        feature_importance_ref=model.feature_importance_ref,
        artifact_ref=model.artifact_ref,
        deployment_mode=model.deployment_mode,
        trained_at=model.trained_at,
    )


def model_definition_to_model(
    entity: ModelDefinition, model: ModelDefinitionModel | None = None
) -> ModelDefinitionModel:
    model = model or ModelDefinitionModel(id=entity.id.value)
    model.market_id = entity.market_id.value
    model.model_key = entity.model_key
    model.version = entity.version
    model.algorithm = entity.algorithm
    model.status = entity.status.value
    model.training_dataset_ref = entity.training_dataset_ref
    model.calibration_ref = entity.calibration_ref
    model.approved_by = entity.approved_by
    model.approved_at = entity.approved_at
    model.promoted_at = entity.promoted_at
    model.retired_at = entity.retired_at
    model.created_at = entity.created_at
    model.framework = entity.framework
    model.dataset_version = entity.dataset_version
    model.feature_versions = dict(entity.feature_versions or {})
    model.training_run_ref = entity.training_run_ref
    model.calibration_report_ref = entity.calibration_report_ref
    model.feature_importance_ref = entity.feature_importance_ref
    model.artifact_ref = entity.artifact_ref
    model.deployment_mode = entity.deployment_mode
    model.trained_at = entity.trained_at
    return model


def _confidence_to_dict(confidence: ConfidenceBreakdown) -> dict:
    return {
        "feature_quality": confidence.feature_quality,
        "feature_freshness": confidence.feature_freshness,
        "historical_accuracy": confidence.historical_accuracy,
        "knowledge_graph_completeness": confidence.knowledge_graph_completeness,
        "news_reliability": confidence.news_reliability,
        "community_reliability": confidence.community_reliability,
        "data_completeness": confidence.data_completeness,
        "model_reliability": confidence.model_reliability,
        "prediction_stability": confidence.prediction_stability,
    }


def _confidence_from_dict(data: dict) -> ConfidenceBreakdown:
    return ConfidenceBreakdown(
        feature_quality=data["feature_quality"],
        feature_freshness=data["feature_freshness"],
        historical_accuracy=data["historical_accuracy"],
        knowledge_graph_completeness=data["knowledge_graph_completeness"],
        news_reliability=data["news_reliability"],
        community_reliability=data["community_reliability"],
        data_completeness=data["data_completeness"],
        model_reliability=data["model_reliability"],
        prediction_stability=data["prediction_stability"],
    )


def _explanation_to_dict(explanation: ExplanationBundle) -> dict:
    return {
        "top_positive_features": [list(pair) for pair in explanation.top_positive_features],
        "top_negative_features": [list(pair) for pair in explanation.top_negative_features],
        "feature_importance": dict(explanation.feature_importance),
        "knowledge_graph_evidence": list(explanation.knowledge_graph_evidence),
        "news_contribution": list(explanation.news_contribution),
        "community_contribution": list(explanation.community_contribution),
        "ai_explanation": explanation.ai_explanation,
    }


def _explanation_from_dict(data: dict) -> ExplanationBundle:
    return ExplanationBundle(
        top_positive_features=tuple((pair[0], pair[1]) for pair in data.get("top_positive_features", [])),
        top_negative_features=tuple((pair[0], pair[1]) for pair in data.get("top_negative_features", [])),
        feature_importance=dict(data.get("feature_importance", {})),
        knowledge_graph_evidence=tuple(data.get("knowledge_graph_evidence", ())),
        news_contribution=tuple(data.get("news_contribution", ())),
        community_contribution=tuple(data.get("community_contribution", ())),
        ai_explanation=data.get("ai_explanation", ""),
    )


def prediction_to_domain(model: PredictionModel) -> Prediction:
    return Prediction(
        id=PredictionId(model.id),
        market_id=MarketId(model.market_id),
        model_id=ModelId(model.model_id),
        subject_ref=model.subject_ref,
        value=model.value,
        probability=model.probability,
        confidence=_confidence_from_dict(model.confidence),
        explanation=_explanation_from_dict(model.explanation),
        feature_snapshot=dict(model.feature_snapshot or {}),
        model_version=model.model_version,
        status=PredictionStatus(model.status),
        generated_at=model.generated_at,
        data_freshness=model.data_freshness,
        probability_distribution=dict(model.probability_distribution or {}),
        confidence_interval=(
            (model.confidence_interval_low, model.confidence_interval_high)
            if model.confidence_interval_low is not None and model.confidence_interval_high is not None
            else None
        ),
        expected_error=model.expected_error,
    )


def prediction_to_model(entity: Prediction, model: PredictionModel | None = None) -> PredictionModel:
    model = model or PredictionModel(id=entity.id.value)
    model.market_id = entity.market_id.value
    model.model_id = entity.model_id.value
    model.subject_ref = entity.subject_ref
    model.value = entity.value
    model.probability = entity.probability
    model.confidence = _confidence_to_dict(entity.confidence)
    model.explanation = _explanation_to_dict(entity.explanation)
    model.feature_snapshot = dict(entity.feature_snapshot)
    model.model_version = entity.model_version
    model.status = entity.status.value
    model.generated_at = entity.generated_at
    model.data_freshness = entity.data_freshness
    model.probability_distribution = dict(entity.probability_distribution)
    model.confidence_interval_low = entity.confidence_interval[0] if entity.confidence_interval else None
    model.confidence_interval_high = entity.confidence_interval[1] if entity.confidence_interval else None
    model.expected_error = entity.expected_error
    return model


def prediction_outcome_to_domain(model: PredictionOutcomeModel) -> PredictionOutcome:
    return PredictionOutcome(
        id=PredictionOutcomeId(model.id),
        prediction_id=PredictionId(model.prediction_id),
        actual_value=model.actual_value,
        error=model.error,
        evaluated_at=model.evaluated_at,
    )


def prediction_outcome_to_model(
    entity: PredictionOutcome, model: PredictionOutcomeModel | None = None
) -> PredictionOutcomeModel:
    model = model or PredictionOutcomeModel(id=entity.id.value)
    model.prediction_id = entity.prediction_id.value
    model.actual_value = entity.actual_value
    model.error = entity.error
    model.evaluated_at = entity.evaluated_at
    return model


def model_evaluation_to_domain(model: ModelEvaluationModel) -> ModelEvaluation:
    return ModelEvaluation(
        id=ModelEvaluationId(model.id),
        model_id=ModelId(model.model_id),
        evaluated_at=model.evaluated_at,
        metrics=dict(model.metrics or {}),
        calibration_report=dict(model.calibration_report or {}),
    )


def model_evaluation_to_model(
    entity: ModelEvaluation, model: ModelEvaluationModel | None = None
) -> ModelEvaluationModel:
    model = model or ModelEvaluationModel(id=entity.id.value)
    model.model_id = entity.model_id.value
    model.evaluated_at = entity.evaluated_at
    model.metrics = dict(entity.metrics)
    model.calibration_report = dict(entity.calibration_report)
    return model


def experiment_to_domain(model: ExperimentModel) -> Experiment:
    return Experiment(
        id=ExperimentId(model.id),
        market_id=MarketId(model.market_id),
        config=dict(model.config or {}),
        metrics=dict(model.metrics or {}),
        decision=model.decision,
        created_at=model.created_at,
    )


def experiment_to_model(entity: Experiment, model: ExperimentModel | None = None) -> ExperimentModel:
    model = model or ExperimentModel(id=entity.id.value)
    model.market_id = entity.market_id.value
    model.config = dict(entity.config)
    model.metrics = dict(entity.metrics)
    model.decision = entity.decision
    model.created_at = entity.created_at
    return model


def prediction_audit_to_domain(model: PredictionAuditModel) -> PredictionAudit:
    return PredictionAudit(
        id=PredictionAuditId(model.id),
        action=AuditAction(model.action),
        actor=model.actor,
        occurred_at=model.occurred_at,
        prediction_id=PredictionId(model.prediction_id) if model.prediction_id is not None else None,
        market_id=MarketId(model.market_id) if model.market_id is not None else None,
        model_id=ModelId(model.model_id) if model.model_id is not None else None,
        details=dict(model.details or {}),
    )


def prediction_audit_to_model(
    entity: PredictionAudit, model: PredictionAuditModel | None = None
) -> PredictionAuditModel:
    model = model or PredictionAuditModel(id=entity.id.value)
    model.action = entity.action.value
    model.actor = entity.actor
    model.occurred_at = entity.occurred_at
    model.prediction_id = entity.prediction_id.value if entity.prediction_id is not None else None
    model.market_id = entity.market_id.value if entity.market_id is not None else None
    model.model_id = entity.model_id.value if entity.model_id is not None else None
    model.details = dict(entity.details)
    return model

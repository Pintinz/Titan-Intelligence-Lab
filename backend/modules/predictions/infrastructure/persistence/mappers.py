from __future__ import annotations

from datetime import datetime
from uuid import UUID

from modules.predictions.domain.calibration import (
    CalibrationMethod,
    CalibrationReport,
    PlattCalibrationParameters,
    ReliabilityBin,
    ReliabilityCurve,
)
from modules.predictions.domain.model_comparison import ChallengerEvaluation, ComparisonMetrics, ComparisonVerdict
from modules.predictions.domain.training_run import TrainingRun, TrainingRunId
from modules.predictions.domain.dataset import (
    Dataset,
    DatasetId,
    DatasetLineage,
    DatasetQualityIssue,
    DatasetStatistics,
    DatasetStatus,
)
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
    ChallengerEvaluationId,
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
    DatasetModel,
    ExperimentModel,
    FeatureMarketMappingModel,
    MarketDefinitionModel,
    ModelDefinitionModel,
    ModelEvaluationModel,
    PredictionAuditModel,
    PredictionModel,
    PredictionOutcomeModel,
)
from modules.predictions.ports.ml_model import TrainingSample


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
        provenance_status=model.provenance_status,
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
    model.provenance_status = entity.provenance_status
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
        prediction_cutoff=model.prediction_cutoff,
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
    model.prediction_cutoff = entity.prediction_cutoff
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
        raw_home_goals=model.raw_home_goals,
        raw_away_goals=model.raw_away_goals,
    )


def prediction_outcome_to_model(
    entity: PredictionOutcome, model: PredictionOutcomeModel | None = None
) -> PredictionOutcomeModel:
    model = model or PredictionOutcomeModel(id=entity.id.value)
    model.prediction_id = entity.prediction_id.value
    model.actual_value = entity.actual_value
    model.error = entity.error
    model.evaluated_at = entity.evaluated_at
    model.raw_home_goals = entity.raw_home_goals
    model.raw_away_goals = entity.raw_away_goals
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


def calibration_report_to_domain(model) -> CalibrationReport:
    curve_payload = model.reliability_curve or {}
    bins = tuple(
        ReliabilityBin(
            bin_index=b["bin_index"],
            predicted_mean=b["predicted_mean"],
            actual_rate=b["actual_rate"],
            sample_count=b["sample_count"],
        )
        for b in curve_payload.get("bins", [])
    )
    return CalibrationReport(
        method=CalibrationMethod(model.method),
        sample_count=model.sample_count,
        expected_calibration_error=model.expected_calibration_error,
        brier_score=model.brier_score,
        reliability_curve=ReliabilityCurve(bins=bins),
        generated_at=model.generated_at,
    )


def platt_calibration_parameters_to_model(params: PlattCalibrationParameters, model=None):
    from modules.predictions.infrastructure.persistence.models import CalibrationParametersModel

    model = model or CalibrationParametersModel(model_id=params.model_id.value)
    model.a = params.a
    model.b = params.b
    model.sample_count = params.sample_count
    model.fitted_at = params.fitted_at
    return model


def platt_calibration_parameters_to_domain(model) -> PlattCalibrationParameters:
    return PlattCalibrationParameters(
        model_id=ModelId(model.model_id), a=model.a, b=model.b,
        sample_count=model.sample_count, fitted_at=model.fitted_at,
    )


def _comparison_metrics_to_dict(metrics: ComparisonMetrics) -> dict:
    return {
        "log_loss": metrics.log_loss, "brier_score": metrics.brier_score,
        "expected_calibration_error": metrics.expected_calibration_error, "mae": metrics.mae,
    }


def _comparison_metrics_to_domain(payload: dict) -> ComparisonMetrics:
    return ComparisonMetrics(
        log_loss=payload.get("log_loss"), brier_score=payload.get("brier_score"),
        expected_calibration_error=payload.get("expected_calibration_error"), mae=payload.get("mae"),
    )


def challenger_evaluation_to_model(evaluation: ChallengerEvaluation):
    from modules.predictions.infrastructure.persistence.models import ChallengerEvaluationModel

    return ChallengerEvaluationModel(
        id=evaluation.id.value,
        market_id=evaluation.market_id.value,
        challenger_model_id=evaluation.challenger_model_id.value,
        champion_model_id=evaluation.champion_model_id.value if evaluation.champion_model_id else None,
        challenger_metrics=_comparison_metrics_to_dict(evaluation.challenger_metrics),
        champion_metrics=(
            _comparison_metrics_to_dict(evaluation.champion_metrics) if evaluation.champion_metrics else None
        ),
        verdict=evaluation.verdict.value,
        decisive_metric=evaluation.decisive_metric,
        holdout_sample_count=evaluation.holdout_sample_count,
        evaluated_at=evaluation.evaluated_at,
    )


def challenger_evaluation_to_domain(model) -> ChallengerEvaluation:
    return ChallengerEvaluation(
        id=ChallengerEvaluationId(model.id),
        market_id=MarketId(model.market_id),
        challenger_model_id=ModelId(model.challenger_model_id),
        champion_model_id=ModelId(model.champion_model_id) if model.champion_model_id else None,
        challenger_metrics=_comparison_metrics_to_domain(model.challenger_metrics or {}),
        champion_metrics=(
            _comparison_metrics_to_domain(model.champion_metrics) if model.champion_metrics else None
        ),
        verdict=ComparisonVerdict(model.verdict),
        decisive_metric=model.decisive_metric,
        holdout_sample_count=model.holdout_sample_count,
        evaluated_at=model.evaluated_at,
    )


def training_run_to_model(run: TrainingRun):
    from modules.predictions.infrastructure.persistence.models import TrainingRunModel

    return TrainingRunModel(
        id=run.id.value,
        market_id=run.market_id.value,
        model_id=run.model_id.value if run.model_id else None,
        dataset_id=run.dataset_id.value if run.dataset_id else None,
        algorithm=run.algorithm,
        framework=run.framework,
        train_metrics=run.train_metrics,
        test_metrics=run.test_metrics,
        feature_order=list(run.feature_order),
        selected_features=list(run.selected_features),
        samples_used=run.samples_used,
        outliers_removed=run.outliers_removed,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def training_run_to_domain(model) -> TrainingRun:
    return TrainingRun(
        id=TrainingRunId(model.id),
        market_id=MarketId(model.market_id),
        model_id=ModelId(model.model_id) if model.model_id else None,
        dataset_id=DatasetId(model.dataset_id) if model.dataset_id else None,
        algorithm=model.algorithm,
        framework=model.framework,
        train_metrics=dict(model.train_metrics or {}),
        test_metrics=dict(model.test_metrics or {}),
        feature_order=tuple(model.feature_order or []),
        selected_features=tuple(model.selected_features or []),
        samples_used=model.samples_used,
        outliers_removed=model.outliers_removed,
        started_at=model.started_at,
        completed_at=model.completed_at,
    )


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


# --- Milestone 20: Dataset Platform durable persistence (closes the M19-identified
# `dataset_provenance_persisted` gap — `DatasetModel`/the `datasets` table have existed since
# Milestone 4/9, unused until now) ------------------------------------------------------------


def _training_sample_to_dict(sample: TrainingSample) -> dict:
    return {
        "features": dict(sample.features),
        "label": sample.label,
        "reference_time": sample.reference_time.isoformat() if sample.reference_time else None,
        "raw_home_goals": sample.raw_home_goals,
        "raw_away_goals": sample.raw_away_goals,
    }


def _training_sample_from_dict(data: dict) -> TrainingSample:
    reference_time = data.get("reference_time")
    return TrainingSample(
        features=dict(data["features"]),
        label=data["label"],
        reference_time=datetime.fromisoformat(reference_time) if reference_time else None,
        raw_home_goals=data.get("raw_home_goals"),
        raw_away_goals=data.get("raw_away_goals"),
    )


def _dataset_statistics_to_dict(statistics: DatasetStatistics) -> dict:
    return {
        "sample_count": statistics.sample_count,
        "feature_count": statistics.feature_count,
        "positive_rate": statistics.positive_rate,
        "missing_rate": dict(statistics.missing_rate),
        "mean": dict(statistics.mean),
        "std": dict(statistics.std),
    }


def _dataset_statistics_from_dict(data: dict) -> DatasetStatistics:
    return DatasetStatistics(
        sample_count=data.get("sample_count", 0),
        feature_count=data.get("feature_count", 0),
        positive_rate=data.get("positive_rate"),
        missing_rate=dict(data.get("missing_rate", {})),
        mean=dict(data.get("mean", {})),
        std=dict(data.get("std", {})),
    )


def _dataset_lineage_to_dict(lineage: DatasetLineage) -> dict:
    return {
        "market_id": str(lineage.market_id),
        "source_prediction_ids": list(lineage.source_prediction_ids),
        "feature_keys": list(lineage.feature_keys),
        "built_at": lineage.built_at.isoformat() if lineage.built_at else None,
        "class_labels": list(lineage.class_labels),
    }


def _dataset_lineage_from_dict(data: dict, fallback_market_id: UUID) -> DatasetLineage:
    built_at = data.get("built_at")
    market_id_raw = data.get("market_id")
    return DatasetLineage(
        market_id=MarketId(UUID(market_id_raw) if market_id_raw else fallback_market_id),
        source_prediction_ids=tuple(data.get("source_prediction_ids", ())),
        feature_keys=tuple(data.get("feature_keys", ())),
        built_at=datetime.fromisoformat(built_at) if built_at else None,
        class_labels=tuple(data.get("class_labels", ())),
    )


def dataset_to_domain(model: DatasetModel) -> Dataset:
    return Dataset(
        id=DatasetId(model.id),
        market_id=MarketId(model.market_id),
        version=model.version,
        content_hash=model.content_hash,
        samples=[_training_sample_from_dict(s) for s in (model.samples or [])],
        statistics=_dataset_statistics_from_dict(model.statistics or {}),
        lineage=_dataset_lineage_from_dict(model.lineage or {}, fallback_market_id=model.market_id),
        quality_issues=tuple(DatasetQualityIssue(v) for v in (model.quality_issues or [])),
        status=DatasetStatus(model.status),
        created_at=model.created_at,
        approved_by=model.approved_by,
        approved_at=model.approved_at,
    )


def dataset_to_model(entity: Dataset, model: DatasetModel | None = None) -> DatasetModel:
    model = model or DatasetModel(id=entity.id.value)
    model.market_id = entity.market_id.value
    model.version = entity.version
    model.content_hash = entity.content_hash
    model.samples = [_training_sample_to_dict(s) for s in entity.samples]
    model.statistics = _dataset_statistics_to_dict(entity.statistics)
    model.lineage = _dataset_lineage_to_dict(entity.lineage)
    model.quality_issues = [issue.value for issue in entity.quality_issues]
    model.status = entity.status.value
    model.created_at = entity.created_at
    model.approved_by = entity.approved_by
    model.approved_at = entity.approved_at
    return model

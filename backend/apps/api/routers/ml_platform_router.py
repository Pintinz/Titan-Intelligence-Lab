"""Enterprise ML Platform API (Milestone 9.1) — Training, Experiment, Model Registry, Champion,
Calibration, Benchmark, Monitoring, Retraining, and Evaluation surfaces. Gated at
`Role.ADMINISTRATOR` by default, same posture as `prediction_admin_router.py` (Milestone 9): these
are operator-only views and actions, never exposed to the public prediction/market resource
routers. `prediction_admin_router.py` itself is untouched — "Prediction APIs unchanged" (Milestone
9.1 Definition of Done) — every endpoint here is new, none replace an existing one.

Four read-only endpoints (`resolve_champion`, `list_models`, `champion_feature_importance`,
`list_model_evaluations`) are the exception — they're gated at plain `get_current_user` instead,
matching the posture every other read-only router in the app already uses (sports, predictions,
knowledge graph, intelligence). This is what the end-user Learning Intelligence page
(`/app/learning`) reads: which model is live, why it weighs the features it does, and how it's
performed — real ML Platform data, not fabricated for public consumption. Every mutation
endpoint, plus the two operationally-detailed monitoring/experiment endpoints, stays
administrator-only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user, require_role
from apps.api.composition import (
    build_automatic_model_selection_service,
    build_calibration_report_builder,
    build_dataset_builder,
    build_dataset_registry_service,
    build_experiment_tracking_service,
    build_market_registry_service,
    build_model_monitoring_service,
    build_model_registry_service,
    build_model_version_resolver,
    build_retraining_scheduler,
    get_model_loader_service,
    get_session,
    get_shap_explainer_service,
)
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Role
from modules.predictions.application.dataset_builder_service import MarketNotFoundError as DatasetMarketNotFoundError
from modules.predictions.application.dataset_registry_service import (
    DatasetHasQualityIssuesError,
    DatasetNotFoundError,
    InvalidDatasetLifecycleTransitionError,
)
from modules.predictions.application.experiment_tracking_service import (
    ExperimentNotFoundError,
    InvalidExperimentDecisionError,
)
from modules.predictions.application.model_registry_service import (
    InvalidDeploymentModeError,
    InvalidModelLifecycleTransitionError,
    ModelNotFoundError,
)
from modules.predictions.domain.calibration import CalibrationMethod
from modules.predictions.domain.dataset import DatasetId
from modules.predictions.domain.model_selection import CandidateSpec, NoViableCandidateError
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.value_objects import ExperimentId, MarketId, ModelId, TargetType
from modules.predictions.application.model_version_resolver import ModelVersionNotFoundError
from modules.predictions.infrastructure.ml.model_loader import UnknownModelFrameworkError
from modules.predictions.ports.ml_model import ModelNotFittedError

router = APIRouter(prefix="/api/v1/admin/ml", tags=["admin", "ml-platform"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid_id(value: str, wrapper, label: str):
    try:
        return wrapper(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {label}: {value}") from None


async def _require_market_id(session: AsyncSession, market_key: str) -> MarketId:
    market = await build_market_registry_service(session).markets.get_by_key(market_key)
    if market is None:
        raise HTTPException(status_code=404, detail="market not found")
    return market.id


# --- Training -------------------------------------------------------------------------------


@router.post("/training/datasets/{market_key}/build")
async def build_dataset(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    market_id = await _require_market_id(session, market_key)
    builder = build_dataset_builder(session)
    registry = build_dataset_registry_service(session)
    try:
        dataset = await builder.build(market_id, now=_now())
    except DatasetMarketNotFoundError:
        raise HTTPException(status_code=404, detail="market not found") from None
    registered = await registry.register(dataset)
    return envelope(
        data={
            "id": str(registered.id),
            "version": registered.version,
            "status": registered.status.value,
            "sample_count": registered.statistics.sample_count,
            "quality_issues": [issue.value for issue in registered.quality_issues],
        }
    )


@router.post("/training/datasets/{dataset_id}/validate")
async def validate_dataset(
    dataset_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    registry = build_dataset_registry_service(session)
    try:
        dataset = await registry.validate(_parse_uuid_id(dataset_id, DatasetId, "dataset_id"))
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found") from None
    except (InvalidDatasetLifecycleTransitionError, DatasetHasQualityIssuesError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data={"id": str(dataset.id), "status": dataset.status.value})


class ApproveDatasetBody(BaseModel):
    approved_by: str


@router.post("/training/datasets/{dataset_id}/approve")
async def approve_dataset(
    dataset_id: str,
    body: ApproveDatasetBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    registry = build_dataset_registry_service(session)
    try:
        dataset = await registry.approve(_parse_uuid_id(dataset_id, DatasetId, "dataset_id"), body.approved_by, _now())
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found") from None
    except InvalidDatasetLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data={"id": str(dataset.id), "status": dataset.status.value})


class SelectChampionBody(BaseModel):
    market_key: str
    model_key_prefix: str
    next_version: int = 1
    target_type: str = "classification"


@router.post("/training/select-champion")
async def select_champion(
    body: SelectChampionBody, session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    market_id = await _require_market_id(session, body.market_key)
    dataset_registry = build_dataset_registry_service(session)
    dataset = await dataset_registry.datasets.get_latest_version(market_id)
    if dataset is None or not dataset.is_usable_for_training():
        raise HTTPException(status_code=409, detail="no APPROVED dataset available for this market — build and approve one first")

    try:
        target_type = TargetType(body.target_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unrecognized target_type '{body.target_type}'") from None

    service = build_automatic_model_selection_service(session)
    try:
        challenger, selection = await service.select_and_register_challenger(
            market_id=market_id,
            dataset=dataset,
            target_type=target_type,
            model_key_prefix=body.model_key_prefix,
            next_version=body.next_version,
            now=_now(),
        )
    except NoViableCandidateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    return envelope(
        data={
            "model_id": str(challenger.id),
            "status": challenger.status.value,
            "algorithm": challenger.algorithm,
            "framework": challenger.framework,
            "ranking_metric": selection.ranking_metric,
            "ranking_value": selection.ranking_value,
        }
    )


# --- Experiment -----------------------------------------------------------------------------


@router.get("/experiments/{market_key}")
async def list_experiments(
    market_key: str,
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    market_id = await _require_market_id(session, market_key)
    service = build_experiment_tracking_service(session)
    experiments = await service.compare(market_id, limit=limit)
    return envelope(
        data=[
            {"id": str(e.id), "config": e.config, "metrics": e.metrics, "decision": e.decision} for e in experiments
        ],
        meta={"count": len(experiments)},
    )


class DecideExperimentBody(BaseModel):
    decision: str


@router.post("/experiments/{experiment_id}/decide")
async def decide_experiment(
    experiment_id: str,
    body: DecideExperimentBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_experiment_tracking_service(session)
    try:
        experiment = await service.decide(_parse_uuid_id(experiment_id, ExperimentId, "experiment_id"), body.decision)
    except ExperimentNotFoundError:
        raise HTTPException(status_code=404, detail="experiment not found") from None
    except InvalidExperimentDecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return envelope(data={"id": str(experiment.id), "decision": experiment.decision})


# --- Model Registry ---------------------------------------------------------------------------


@router.get("/models/{market_key}")
async def list_models(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    market_id = await _require_market_id(session, market_key)
    service = build_model_registry_service(session)
    models = await service.models.list_by_market(market_id)
    return envelope(
        data=[
            {
                "id": str(m.id),
                "model_key": m.model_key,
                "version": m.version,
                "algorithm": m.algorithm,
                "framework": m.framework,
                "status": m.status.value,
                "deployment_mode": m.deployment_mode,
            }
            for m in models
        ],
        meta={"count": len(models)},
    )


class DeploymentModeBody(BaseModel):
    mode: str | None = None


@router.post("/models/{model_id}/deployment-mode")
async def set_deployment_mode(
    model_id: str,
    body: DeploymentModeBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_model_registry_service(session)
    try:
        model = await service.set_deployment_mode(_parse_uuid_id(model_id, ModelId, "model_id"), body.mode)
    except ModelNotFoundError:
        raise HTTPException(status_code=404, detail="model not found") from None
    except InvalidDeploymentModeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return envelope(data={"id": str(model.id), "deployment_mode": model.deployment_mode})


# --- Champion ---------------------------------------------------------------------------------


@router.get("/champion/{market_key}")
async def resolve_champion(
    market_key: str,
    model_key: str | None = Query(default=None),
    pinned_version: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    market_id = await _require_market_id(session, market_key)
    resolver = build_model_version_resolver(session)
    try:
        model = await resolver.resolve(market_id, model_key=model_key, pinned_version=pinned_version)
    except Exception as exc:  # noqa: BLE001 — both resolver error types map to a 404/422 the same way
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return envelope(data={"id": str(model.id), "model_key": model.model_key, "version": model.version, "status": model.status.value})


class PromoteChampionBody(BaseModel):
    approved_by: str


@router.post("/champion/{model_id}/promote")
async def promote_champion(
    model_id: str,
    body: PromoteChampionBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_model_registry_service(session)
    try:
        model = await service.promote_to_champion(_parse_uuid_id(model_id, ModelId, "model_id"), body.approved_by, _now())
    except ModelNotFoundError:
        raise HTTPException(status_code=404, detail="model not found") from None
    except InvalidModelLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data={"id": str(model.id), "status": model.status.value})


# --- Feature Importance -----------------------------------------------------------------------


@router.get("/feature-importance/{market_key}")
async def champion_feature_importance(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    """Global SHAP importance for a market's current champion (Milestone 9.1 SHAP integration,
    task #166) — only meaningful once a market's champion is an ML-backed model with a saved
    artifact (`select-champion` was run); a still-weighted-predictor champion has no fitted model
    for SHAP to introspect, so that case is a 409, not a fabricated importance breakdown."""
    market_id = await _require_market_id(session, market_key)
    resolver = build_model_version_resolver(session)
    try:
        champion = await resolver.resolve(market_id)
    except ModelVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    if not champion.artifact_ref or not champion.framework:
        raise HTTPException(status_code=409, detail="champion has no trained ML model to explain")

    dataset_registry = build_dataset_registry_service(session)
    dataset = await dataset_registry.datasets.get_latest_version(market_id)
    if dataset is None or not dataset.samples:
        raise HTTPException(status_code=409, detail="no dataset available to use as SHAP background samples")

    loader = get_model_loader_service()
    try:
        model = await loader.load(champion.id, champion.framework, champion.algorithm, TargetType.CLASSIFICATION, champion.artifact_ref)
    except UnknownModelFrameworkError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    background = [sample.features for sample in dataset.samples[:50]]
    explainer = get_shap_explainer_service()
    try:
        explanation = explainer.explain_instance(model, background[0], background)
    except ModelNotFittedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    return envelope(data={"model_id": str(champion.id), "global_importance": explanation.global_importance})


# --- Calibration ------------------------------------------------------------------------------


class CalibrationReportBody(BaseModel):
    method: str
    samples: list[tuple[float, bool]]


@router.post("/calibration/reports")
async def build_calibration_report(
    body: CalibrationReportBody, _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    try:
        method = CalibrationMethod(body.method)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unrecognized calibration method '{body.method}'") from None

    builder = build_calibration_report_builder()
    report = builder.build(method, body.samples, _now())
    return envelope(
        data={
            "method": report.method.value,
            "sample_count": report.sample_count,
            "expected_calibration_error": report.expected_calibration_error,
            "brier_score": report.brier_score,
            "reliability_curve": [
                {"predicted_mean": b.predicted_mean, "actual_rate": b.actual_rate, "sample_count": b.sample_count}
                for b in report.reliability_curve.bins
            ],
        }
    )


# --- Benchmark --------------------------------------------------------------------------------


class BenchmarkBody(BaseModel):
    market_key: str
    algorithm: str
    framework: str
    target_type: str = "classification"


@router.post("/benchmark")
async def benchmark_candidate(
    body: BenchmarkBody, session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    market_id = await _require_market_id(session, body.market_key)
    dataset_registry = build_dataset_registry_service(session)
    dataset = await dataset_registry.datasets.get_latest_version(market_id)
    if dataset is None or not dataset.is_usable_for_training():
        raise HTTPException(status_code=409, detail="no APPROVED dataset available for this market")

    try:
        target_type = TargetType(body.target_type)
        algorithm = MLAlgorithm(body.algorithm)
        framework = MLFramework(body.framework)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    service = build_automatic_model_selection_service(session)
    try:
        result = await service.select(dataset, target_type, candidates=(CandidateSpec(algorithm, framework),))
    except NoViableCandidateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    return envelope(data={"algorithm": algorithm.value, "framework": framework.value, "ranking_metric": result.ranking_metric, "ranking_value": result.ranking_value})


# --- Monitoring -------------------------------------------------------------------------------


@router.get("/monitoring/{market_key}/health")
async def model_health(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    market_id = await _require_market_id(session, market_key)
    service = build_model_monitoring_service(session)
    return envelope(data=await service.model_health(market_id, now=_now()))


@router.get("/monitoring/{market_key}/latency")
async def latency_stats(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    market_id = await _require_market_id(session, market_key)
    service = build_model_monitoring_service(session)
    return envelope(data=await service.latency_stats(market_id))


class RecordLatencyBody(BaseModel):
    duration_ms: float


@router.post("/monitoring/{market_key}/latency")
async def record_latency(
    market_key: str,
    body: RecordLatencyBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    market_id = await _require_market_id(session, market_key)
    service = build_model_monitoring_service(session)
    await service.record_latency(market_id, body.duration_ms, _now())
    return envelope(data={"recorded": True})


# --- Retraining -------------------------------------------------------------------------------


@router.post("/retraining/{market_key}/check")
async def check_retraining(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    market_id = await _require_market_id(session, market_key)
    scheduler = build_retraining_scheduler(session)
    return envelope(data=await scheduler.should_retrain(market_id, now=_now()))


# --- Evaluation -------------------------------------------------------------------------------


@router.get("/evaluation/{model_id}")
async def list_model_evaluations(
    model_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyModelEvaluationRepository

    evaluations = await SqlAlchemyModelEvaluationRepository(session=session).list_by_model(
        _parse_uuid_id(model_id, ModelId, "model_id"), limit=limit
    )
    return envelope(
        data=[
            {"id": str(e.id), "evaluated_at": e.evaluated_at.isoformat(), "metrics": e.metrics, "calibration_report": e.calibration_report}
            for e in evaluations
        ],
        meta={"count": len(evaluations)},
    )

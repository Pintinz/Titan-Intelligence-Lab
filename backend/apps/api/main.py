"""FastAPI entrypoint. Three route groups exist at this milestone: a DB-free health check, the
read side of the Provider Management System, and the Provider Health Intelligence dashboard
API — enough to prove the provider architecture end-to-end. Auth, RBAC, and the rest of
docs/api_specification.md's route groups land as their owning modules are built
(docs/roadmap.md).
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.routers import (
    billing_router,
    graph_router,
    identity_router,
    intelligence_router,
    market_router,
    ml_platform_router,
    prediction_admin_router,
    prediction_analytics_router,
    prediction_router,
    sports_router,
    tenancy_router,
    webhooks_router,
)
from apps.api.auth_deps import require_role
from apps.api.composition import (
    build_feature_flag_service,
    build_feature_quality_engine,
    build_feature_registration_service,
    build_health_intelligence_engine,
    build_kg_population_service,
    build_ingestion_quality_engine,
    build_monitoring_service,
    build_provider_management_service,
    build_sync_orchestrator,
    get_redis_client,
    get_session,
)
from modules.admin.application.feature_flag_service import FlagAlreadyExistsError, FlagNotFoundError
from modules.identity.domain.entities import User as _AuthUser
from modules.identity.domain.value_objects import Role as _Role
from modules.admin.application.health_intelligence_engine import (
    ProviderDiagnosticsReport,
    WindowMetrics,
)
from modules.admin.application.provider_management_service import ProviderNotFoundError
from modules.admin.domain.entities import FeatureFlag, ProviderIncident
from modules.admin.domain.value_objects import CredentialId, ProviderId
from modules.admin.infrastructure.persistence.repositories import SqlAlchemyProviderRepository
from modules.features.application.feature_quality_engine import (
    ComputationCostSnapshot,
    FeatureHealthReport,
    FeatureNotFoundError as FeatureQualityNotFoundError,
    FeatureQualitySnapshot,
)
from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureNotFoundError as FeatureDefNotFoundError,
    InvalidFeatureDefinitionError,
    InvalidLifecycleTransitionError,
)
from modules.features.domain.entities import FeatureConsumer, FeatureDefinition, FeatureValidationReport
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureKey
from modules.ingestion.application.sync_orchestrator import SportNotReconciledError
from modules.ingestion.domain.value_objects import EntityKind as IngestionEntityKind
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.sports.domain.value_objects import SeasonId

logger = logging.getLogger("titaniq.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TitanIQ API starting — Milestone 3 (Provider Foundation + Health Intelligence)")
    yield
    logger.info("TitanIQ API shutting down")


app = FastAPI(title="TitanIQ API", version="0.1.0", lifespan=lifespan)

# CORS: the frontend (Milestone 10) is a separate origin (Vite dev server / deployed static host),
# so the browser needs an explicit allowlist — no API route below authenticates via cookies, only
# a Bearer token in the Authorization header, so allow_credentials is not required for that path
# but is enabled for future cookie-based flows (e.g. Supabase's SSR helpers) without another change.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
_cors_origins = [origin.strip() for origin in os.environ.get("TITANIQ_CORS_ORIGINS", _default_origins).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(identity_router.router)
app.include_router(tenancy_router.router)
app.include_router(billing_router.router)
app.include_router(webhooks_router.router)
app.include_router(graph_router.router)
app.include_router(intelligence_router.router)
app.include_router(sports_router.router)
# prediction_analytics_router's literal-prefixed routes (/history/*, /monitoring/*, /statistics/*,
# /compare) must be registered before prediction_router's generic GET /{prediction_id} — Starlette
# matches path templates in registration order, so the catch-all would otherwise shadow them.
app.include_router(prediction_analytics_router.router)
app.include_router(prediction_router.router)
app.include_router(market_router.router)
app.include_router(prediction_admin_router.router)
app.include_router(ml_platform_router.router)


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_metrics(metrics: WindowMetrics) -> dict:
    return {
        "success_rate": metrics.success_rate,
        "failure_rate": metrics.failure_rate,
        "average_latency_ms": metrics.average_latency_ms,
        "p50_latency_ms": metrics.p50_latency_ms,
        "p95_latency_ms": metrics.p95_latency_ms,
        "p99_latency_ms": metrics.p99_latency_ms,
        "check_count": metrics.check_count,
    }


def _serialize_incident(incident: ProviderIncident) -> dict:
    return {
        "id": str(incident.id),
        "provider_id": str(incident.provider_id),
        "severity": incident.severity.value,
        "opened_at": incident.opened_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "trigger": incident.trigger,
        "is_open": incident.is_open,
    }


def _serialize_diagnostics(report: ProviderDiagnosticsReport) -> dict:
    return {
        "provider_id": str(report.provider_id),
        "status": report.status.value,
        "consecutive_failures": report.consecutive_failures,
        "reliability_score": report.reliability_score,
        "metrics_24h": _serialize_metrics(report.metrics_24h),
        "daily_uptime": report.daily_uptime,
        "monthly_uptime": report.monthly_uptime,
        "open_incident": _serialize_incident(report.open_incident) if report.open_incident else None,
        "recent_checks": [
            {
                "checked_at": c.checked_at.isoformat(),
                "success": c.success,
                "latency_ms": c.latency_ms,
                "message": c.message,
            }
            for c in report.recent_checks
        ],
        "recommendation": report.recommendation,
    }


@app.get("/api/v1/health")
async def health():
    return envelope(data={"status": "ok"})


@app.get("/api/v1/admin/providers")
async def list_providers(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    repo = SqlAlchemyProviderRepository(session=session)
    providers = await repo.list_all()
    return envelope(
        data=[
            {
                "id": str(p.id),
                "key": p.key,
                "name": p.name,
                "category": p.category.value,
                "status": p.status.value,
                "priority": p.priority,
            }
            for p in providers
        ]
    )


@app.post("/api/v1/admin/providers/{provider_id}/activate")
async def activate_provider(provider_id: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_provider_management_service(session)
    try:
        provider = await service.activate(ProviderId(uuid.UUID(provider_id)))
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    return envelope(data={"id": str(provider.id), "status": provider.status.value})


# -- Provider Health Intelligence dashboard API (docs/admin_center.md §2) --------------------


class RecordHealthCheckBody(BaseModel):
    success: bool
    latency_ms: float | None = None
    message: str | None = None


@app.get("/api/v1/admin/providers/{provider_id}/health/summary")
async def provider_health_summary(
    provider_id: str, window_hours: int = Query(default=24, ge=1, le=720), session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_health_intelligence_engine(session)
    pid = ProviderId(uuid.UUID(provider_id))
    now = _now()
    window = timedelta(hours=window_hours)

    metrics = await engine.window_metrics(pid, now, window)
    return envelope(
        data={
            "provider_id": provider_id,
            "window_hours": window_hours,
            "metrics": _serialize_metrics(metrics),
            "consecutive_failures": await engine.consecutive_failures(pid),
            "status": (await engine.current_status(pid)).value,
            "daily_uptime": await engine.daily_uptime(pid, now),
            "monthly_uptime": await engine.monthly_uptime(pid, now),
            "reliability_score": await engine.reliability_score(pid, now),
        }
    )


@app.get("/api/v1/admin/providers/{provider_id}/health/trend")
async def provider_health_trend(
    provider_id: str, days: int = Query(default=7, ge=1, le=90), session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_health_intelligence_engine(session)
    pid = ProviderId(uuid.UUID(provider_id))
    points = await engine.health_trend(pid, _now(), days=days)
    return envelope(
        data=[
            {
                "date": point.date,
                "success_rate": point.success_rate,
                "average_latency_ms": point.average_latency_ms,
                "check_count": point.check_count,
            }
            for point in points
        ]
    )


@app.get("/api/v1/admin/providers/{provider_id}/health/incidents")
async def provider_incident_history(provider_id: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    engine = build_health_intelligence_engine(session)
    pid = ProviderId(uuid.UUID(provider_id))
    incidents = await engine.list_incidents(pid)
    return envelope(data=[_serialize_incident(i) for i in incidents])


@app.get("/api/v1/admin/providers/{provider_id}/diagnostics")
async def provider_diagnostics(provider_id: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    engine = build_health_intelligence_engine(session)
    pid = ProviderId(uuid.UUID(provider_id))
    report = await engine.diagnostics(pid, _now())
    return envelope(data=_serialize_diagnostics(report))


@app.post("/api/v1/admin/providers/{provider_id}/health/check")
async def record_provider_health_check(
    provider_id: str, body: RecordHealthCheckBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_health_intelligence_engine(session)
    pid = ProviderId(uuid.UUID(provider_id))
    check, state = await engine.record_check(
        pid, _now(), body.success, latency_ms=body.latency_ms, message=body.message
    )
    return envelope(
        data={
            "recorded_at": check.checked_at.isoformat(),
            "success": check.success,
            "status": state.status.value,
            "consecutive_failures": state.consecutive_failures,
        }
    )


@app.get("/api/v1/admin/credentials/{credential_id}/health")
async def credential_health(
    credential_id: str, provider_id: str = Query(...), session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_health_intelligence_engine(session)
    score = await engine.credential_reliability_score(
        ProviderId(uuid.UUID(provider_id)), CredentialId(uuid.UUID(credential_id)), _now()
    )
    return envelope(data={"credential_id": credential_id, "reliability_score": score})


# -- Feature Intelligence Platform: registration workflow (docs/feature_catalog.md) ------------


def _serialize_feature(d: FeatureDefinition) -> dict:
    return {
        "feature_key": d.feature_key.value,
        "name": d.name,
        "description": d.description,
        "sport_code": d.sport_code,
        "category": d.category.value,
        "formula": d.formula,
        "data_type": d.data_type.value,
        "owner": d.owner,
        "entity_type": d.entity_type.value,
        "unit": d.unit,
        "expected_range": list(d.expected_range) if d.expected_range else None,
        "update_frequency": d.update_frequency,
        "online_ttl_seconds": d.online_ttl_seconds,
        "version": d.version,
        "status": d.status.value,
        "dependencies": [dep.value for dep in d.dependencies],
        "leakage_reviewed": d.leakage_reviewed,
        "reviewed_by": d.reviewed_by,
        "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
        "rejection_reason": d.rejection_reason,
        "deprecated_at": d.deprecated_at.isoformat() if d.deprecated_at else None,
    }


class RegisterFeatureBody(BaseModel):
    feature_key: str
    name: str
    description: str
    sport_code: str
    category: FeatureCategory
    formula: str
    data_type: FeatureDataType
    owner: str
    entity_type: EntityType
    unit: str | None = None
    expected_range: tuple[float, float] | None = None
    update_frequency: str = "unspecified"
    online_ttl_seconds: int = 3600
    dependencies: tuple[str, ...] = ()


class ReviewFeatureBody(BaseModel):
    reviewer: str
    reason: str | None = None


@app.post("/api/v1/admin/features")
async def register_feature(body: RegisterFeatureBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_registration_service(session)
    try:
        definition = await service.register(
            body.feature_key, body.name, body.description, body.sport_code, body.category,
            body.formula, body.data_type, body.owner, body.entity_type,
            unit=body.unit, expected_range=body.expected_range, update_frequency=body.update_frequency,
            online_ttl_seconds=body.online_ttl_seconds, dependencies=body.dependencies,
        )
    except FeatureAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except InvalidFeatureDefinitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return envelope(data=_serialize_feature(definition))


@app.get("/api/v1/admin/features")
async def list_features(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_registration_service(session)
    definitions = await service.definitions.list_all()
    return envelope(data=[_serialize_feature(d) for d in definitions])


@app.get("/api/v1/admin/features/{feature_key}")
async def get_feature(feature_key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_registration_service(session)
    definition = await service.definitions.get(FeatureKey(feature_key))
    if definition is None:
        raise HTTPException(status_code=404, detail="feature not found")
    return envelope(data=_serialize_feature(definition))


@app.post("/api/v1/admin/features/{feature_key}/submit")
async def submit_feature_for_review(feature_key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_registration_service(session)
    try:
        definition = await service.submit_for_review(feature_key)
    except FeatureDefNotFoundError:
        raise HTTPException(status_code=404, detail="feature not found") from None
    except InvalidLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_feature(definition))


@app.post("/api/v1/admin/features/{feature_key}/approve")
async def approve_feature(feature_key: str, body: ReviewFeatureBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_registration_service(session)
    try:
        definition = await service.approve(feature_key, body.reviewer, _now())
    except FeatureDefNotFoundError:
        raise HTTPException(status_code=404, detail="feature not found") from None
    except InvalidLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_feature(definition))


@app.post("/api/v1/admin/features/{feature_key}/reject")
async def reject_feature(feature_key: str, body: ReviewFeatureBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_registration_service(session)
    try:
        definition = await service.reject(feature_key, body.reviewer, body.reason or "", _now())
    except FeatureDefNotFoundError:
        raise HTTPException(status_code=404, detail="feature not found") from None
    except InvalidLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_feature(definition))


@app.post("/api/v1/admin/features/{feature_key}/deprecate")
async def deprecate_feature(feature_key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_registration_service(session)
    try:
        definition = await service.deprecate(feature_key, _now())
    except FeatureDefNotFoundError:
        raise HTTPException(status_code=404, detail="feature not found") from None
    except InvalidLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_feature(definition))


# -- Feature Flags (docs/admin_center.md §1) ---------------------------------------------------


class CreateFlagBody(BaseModel):
    key: str
    name: str
    description: str
    enabled: bool = False
    rollout_percentage: int = 100


class SetRolloutBody(BaseModel):
    percentage: int


def _serialize_flag(flag: FeatureFlag) -> dict:
    return {
        "id": str(flag.id),
        "key": flag.key,
        "name": flag.name,
        "description": flag.description,
        "enabled": flag.enabled,
        "rollout_percentage": flag.rollout_percentage,
        "updated_at": flag.updated_at.isoformat() if flag.updated_at else None,
    }


@app.post("/api/v1/admin/flags")
async def create_flag(body: CreateFlagBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_flag_service(session)
    try:
        flag = await service.create_flag(
            body.key, body.name, body.description, enabled=body.enabled, rollout_percentage=body.rollout_percentage
        )
    except FlagAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_flag(flag))


@app.get("/api/v1/admin/flags")
async def list_flags(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_flag_service(session)
    flags = await service.list_all()
    return envelope(data=[_serialize_flag(f) for f in flags])


@app.post("/api/v1/admin/flags/{key}/enable")
async def enable_flag(key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_flag_service(session)
    try:
        flag = await service.enable(key, _now())
    except FlagNotFoundError:
        raise HTTPException(status_code=404, detail="flag not found") from None
    return envelope(data=_serialize_flag(flag))


@app.post("/api/v1/admin/flags/{key}/disable")
async def disable_flag(key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_flag_service(session)
    try:
        flag = await service.disable(key, _now())
    except FlagNotFoundError:
        raise HTTPException(status_code=404, detail="flag not found") from None
    return envelope(data=_serialize_flag(flag))


@app.post("/api/v1/admin/flags/{key}/rollout")
async def set_flag_rollout(key: str, body: SetRolloutBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_feature_flag_service(session)
    try:
        flag = await service.set_rollout(key, body.percentage, _now())
    except FlagNotFoundError:
        raise HTTPException(status_code=404, detail="flag not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return envelope(data=_serialize_flag(flag))


@app.get("/api/v1/admin/flags/{key}/evaluate")
async def evaluate_flag(
    key: str, context_id: str | None = Query(default=None), session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    service = build_feature_flag_service(session)
    enabled = await service.is_enabled(key, context_id)
    return envelope(data={"key": key, "context_id": context_id, "enabled": enabled})


# -- Feature Quality Intelligence (docs/feature_catalog.md) -------------------------------------


def _serialize_quality(q: FeatureQualitySnapshot) -> dict:
    return {
        "sample_size": q.sample_size,
        "quality_score": q.quality_score,
        "freshness_score": q.freshness_score,
        "reliability_score": q.reliability_score,
        "completeness_score": q.completeness_score,
        "missing_pct": q.missing_pct,
        "outlier_pct": q.outlier_pct,
        "null_pct": q.null_pct,
        "invalid_pct": q.invalid_pct,
        "duplicate_pct": q.duplicate_pct,
        "coverage_pct": q.coverage_pct,
    }


def _serialize_validation_report(r: FeatureValidationReport) -> dict:
    return {
        "id": str(r.id),
        "feature_key": r.feature_key.value,
        "validated_at": r.validated_at.isoformat(),
        "status": r.status.value,
        "issues": list(r.issues),
        **_serialize_quality(
            FeatureQualitySnapshot(
                sample_size=r.sample_size, quality_score=r.quality_score, freshness_score=r.freshness_score,
                reliability_score=r.reliability_score, completeness_score=r.completeness_score,
                missing_pct=r.missing_pct, outlier_pct=r.outlier_pct, null_pct=r.null_pct,
                invalid_pct=r.invalid_pct, duplicate_pct=r.duplicate_pct, coverage_pct=r.coverage_pct,
            )
        ),
    }


def _serialize_computation_cost(c: ComputationCostSnapshot) -> dict:
    return {
        "sample_size": c.sample_size,
        "average_duration_ms": c.average_duration_ms,
        "average_memory_bytes": c.average_memory_bytes,
        "cost_score": c.cost_score,
    }


def _serialize_consumer(c: FeatureConsumer) -> dict:
    return {"feature_key": c.feature_key.value, "consumer_key": c.consumer_key, "registered_at": c.registered_at.isoformat()}


def _serialize_feature_health(h: FeatureHealthReport) -> dict:
    return {
        "feature_key": h.feature_key,
        "status": h.status,
        "quality": _serialize_quality(h.quality),
        "last_validation": _serialize_validation_report(h.last_validation) if h.last_validation else None,
        "provider_source": h.provider_source,
        "provider_reliability": h.provider_reliability,
        "computation_cost": _serialize_computation_cost(h.computation_cost),
        "storage_size_bytes": h.storage_size_bytes,
        "consumer_count": h.consumer_count,
        "usage_last_7_days": h.usage_last_7_days,
        "deprecation_warning": h.deprecation_warning,
    }


def _handle_quality_not_found():
    raise HTTPException(status_code=404, detail="feature not found")


class RecordComputationBody(BaseModel):
    duration_ms: float
    memory_bytes: int | None = None


class RegisterConsumerBody(BaseModel):
    consumer_key: str


# -- Feature Quality API --------------------------------------------------------------------------


@app.get("/api/v1/admin/features/{feature_key}/quality")
async def get_feature_quality(
    feature_key: str,
    window_days: int = Query(default=7, ge=1, le=365),
    total_expected_entities: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    engine = build_feature_quality_engine(session)
    try:
        snapshot = await engine.quality_snapshot(
            feature_key, _now(), window=timedelta(days=window_days), total_expected_entities=total_expected_entities
        )
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data=_serialize_quality(snapshot))


# -- Feature Validation API -----------------------------------------------------------------------


@app.post("/api/v1/admin/features/{feature_key}/validate")
async def validate_feature(
    feature_key: str,
    window_days: int = Query(default=7, ge=1, le=365),
    total_expected_entities: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    engine = build_feature_quality_engine(session)
    try:
        report = await engine.run_validation(
            feature_key, _now(), window=timedelta(days=window_days), total_expected_entities=total_expected_entities
        )
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data=_serialize_validation_report(report))


@app.get("/api/v1/admin/features/{feature_key}/validations")
async def list_feature_validations(
    feature_key: str, limit: int = Query(default=50, ge=1, le=200), session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_feature_quality_engine(session)
    try:
        reports = await engine.list_validation_history(feature_key, limit=limit)
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data=[_serialize_validation_report(r) for r in reports])


@app.get("/api/v1/admin/features/{feature_key}/validations/latest")
async def get_latest_feature_validation(feature_key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    engine = build_feature_quality_engine(session)
    try:
        report = await engine.get_latest_validation(feature_key)
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data=_serialize_validation_report(report) if report else None)


# -- Feature Usage API ------------------------------------------------------------------------------


@app.post("/api/v1/admin/features/{feature_key}/usage")
async def record_feature_usage(feature_key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    engine = build_feature_quality_engine(session)
    try:
        await engine.record_usage(feature_key, _now())
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data={"feature_key": feature_key, "recorded": True})


@app.get("/api/v1/admin/features/{feature_key}/usage")
async def get_feature_usage(
    feature_key: str, window_days: int = Query(default=7, ge=1, le=365), session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_feature_quality_engine(session)
    try:
        frequency = await engine.usage_frequency(feature_key, _now(), window_days=window_days)
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data={"feature_key": feature_key, "window_days": window_days, "read_count": frequency})


@app.post("/api/v1/admin/features/{feature_key}/consumers")
async def register_feature_consumer(
    feature_key: str, body: RegisterConsumerBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_feature_quality_engine(session)
    try:
        consumer = await engine.register_consumer(feature_key, body.consumer_key, _now())
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data=_serialize_consumer(consumer))


@app.get("/api/v1/admin/features/{feature_key}/consumers")
async def list_feature_consumers(feature_key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    engine = build_feature_quality_engine(session)
    try:
        consumers = await engine.list_consumers(feature_key)
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data=[_serialize_consumer(c) for c in consumers])


# -- Feature Statistics API -----------------------------------------------------------------------


@app.post("/api/v1/admin/features/{feature_key}/computation")
async def record_feature_computation(
    feature_key: str, body: RecordComputationBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    engine = build_feature_quality_engine(session)
    try:
        log = await engine.record_computation(feature_key, _now(), body.duration_ms, memory_bytes=body.memory_bytes)
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(
        data={
            "feature_key": feature_key, "recorded_at": log.recorded_at.isoformat(),
            "duration_ms": log.duration_ms, "memory_bytes": log.memory_bytes,
        }
    )


@app.get("/api/v1/admin/features/{feature_key}/statistics")
async def get_feature_statistics(feature_key: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    engine = build_feature_quality_engine(session)
    try:
        computation_cost = await engine.computation_cost(feature_key, _now())
        storage_size = await engine.storage_size_bytes(feature_key, _now())
        usage = await engine.usage_frequency(feature_key, _now(), window_days=7)
        consumers = await engine.list_consumers(feature_key)
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(
        data={
            "feature_key": feature_key,
            "computation_cost": _serialize_computation_cost(computation_cost),
            "storage_size_bytes": storage_size,
            "usage_last_7_days": usage,
            "consumer_count": len(consumers),
        }
    )


# -- Feature Health API -----------------------------------------------------------------------------


@app.get("/api/v1/admin/features/{feature_key}/health")
async def get_feature_health(
    feature_key: str,
    total_expected_entities: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    engine = build_feature_quality_engine(session)
    try:
        report = await engine.health_report(feature_key, _now(), total_expected_entities=total_expected_entities)
    except FeatureQualityNotFoundError:
        _handle_quality_not_found()
    return envelope(data=_serialize_feature_health(report))


# -- Milestone 5: Sports Data Ingestion Platform -------------------------------------------------


class TriggerSyncBody(BaseModel):
    force: bool = False


class TriggerFixtureSyncBody(BaseModel):
    season_id: str
    force: bool = False
    live: bool = False


def _serialize_sync_run(run) -> dict | None:
    if run is None:
        return None
    return {
        "run_id": str(run.id), "sport_code": run.sport_code, "entity_kind": run.entity_kind.value,
        "scope_key": run.scope_key, "trigger": run.trigger.value, "status": run.status.value,
        "started_at": run.started_at.isoformat(), "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": run.duration_seconds, "records_fetched": run.records_fetched,
        "records_created": run.records_created, "records_updated": run.records_updated,
        "records_rejected": run.records_rejected, "validation_failures": run.validation_failures,
        "error_message": run.error_message,
    }


@app.post("/api/v1/admin/sync/{sport_code}/countries")
async def trigger_sync_countries(sport_code: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    orchestrator = build_sync_orchestrator(session)
    run = await orchestrator.sync_countries(sport_code, _now(), force=body.force)
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/teams/{competition_ref}")
async def trigger_sync_teams(
    sport_code: str, competition_ref: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))
):
    orchestrator = build_sync_orchestrator(session)
    try:
        run = await orchestrator.sync_teams(sport_code, competition_ref, _now(), force=body.force)
    except SportNotReconciledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/fixtures/{competition_ref}/{season_label}")
async def trigger_sync_fixtures(
    sport_code: str, competition_ref: str, season_label: str, body: TriggerFixtureSyncBody,
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    orchestrator = build_sync_orchestrator(session)
    season_id = SeasonId(uuid.UUID(body.season_id))
    if body.live:
        run = await orchestrator.sync_live_fixtures(sport_code, competition_ref, season_label, season_id, _now())
    else:
        run = await orchestrator.sync_fixtures(sport_code, competition_ref, season_label, season_id, _now(), force=body.force)
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/standings/{competition_ref}/{season_label}")
async def trigger_sync_standings(
    sport_code: str, competition_ref: str, season_label: str, body: TriggerFixtureSyncBody,
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    orchestrator = build_sync_orchestrator(session)
    season_id = SeasonId(uuid.UUID(body.season_id))
    run = await orchestrator.sync_standings(sport_code, competition_ref, season_label, season_id, _now(), force=body.force)
    return envelope(data=_serialize_sync_run(run))


@app.get("/api/v1/admin/sync/status")
async def get_sync_status(
    sport_code: str | None = Query(default=None),
    entity_kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    monitoring = build_monitoring_service(session)
    kind = IngestionEntityKind(entity_kind) if entity_kind else None
    summaries = await monitoring.sync_status(sport_code, kind, limit=limit)
    return envelope(data=[s.__dict__ | {"started_at": s.started_at.isoformat()} for s in summaries])


@app.get("/api/v1/admin/sync/stats")
async def get_sync_stats(
    sport_code: str | None = Query(default=None),
    entity_kind: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    monitoring = build_monitoring_service(session)
    kind = IngestionEntityKind(entity_kind) if entity_kind else None
    stats = await monitoring.aggregate_stats(sport_code, kind, limit=limit)
    return envelope(data=stats)


@app.get("/api/v1/admin/ingestion/quality/{sport_code}/{entity_kind}")
async def get_ingestion_quality(sport_code: str, entity_kind: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    engine = build_ingestion_quality_engine(session)
    try:
        kind = IngestionEntityKind(entity_kind)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unrecognized entity_kind '{entity_kind}'") from None
    report = await engine.get_latest(sport_code, kind)
    if report is None:
        return envelope(data=None)
    return envelope(
        data={
            "sport_code": report.sport_code, "entity_kind": report.entity_kind.value,
            "generated_at": report.generated_at.isoformat(), "sample_size": report.sample_size,
            "completeness_pct": report.completeness_pct, "consistency_pct": report.consistency_pct,
            "freshness_score": report.freshness_score, "accuracy_pct": report.accuracy_pct,
            "validity_pct": report.validity_pct, "reliability_score": report.reliability_score,
            "coverage_pct": report.coverage_pct, "provider_quality_score": report.provider_quality_score,
            "quality_score": report.quality_score, "issues": list(report.issues),
        }
    )


@app.get("/api/v1/admin/monitoring/redis")
async def get_redis_health(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    monitoring = build_monitoring_service(session)
    report = await monitoring.redis_health(get_redis_client())
    return envelope(data={"healthy": report.healthy, "latency_ms": report.latency_ms, "error": report.error})


@app.get("/api/v1/admin/graph/nodes/{node_type}/{entity_ref}")
async def get_kg_node(node_type: str, entity_ref: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    kg = build_kg_population_service(session)
    try:
        kind = NodeType(node_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unrecognized node_type '{node_type}'") from None
    node = await kg.nodes.get_by_entity_ref(kind, entity_ref)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    edges_out = await kg.edges.list_from(node.id)
    edges_in = await kg.edges.list_to(node.id)
    return envelope(
        data={
            "id": str(node.id), "node_type": node.node_type.value, "entity_ref": node.entity_ref,
            "attributes": node.attributes,
            "edges_out": [{"edge_type": e.edge_type.value, "to_node_id": str(e.to_node_id), "attributes": e.attributes} for e in edges_out],
            "edges_in": [{"edge_type": e.edge_type.value, "from_node_id": str(e.from_node_id), "attributes": e.attributes} for e in edges_in],
        }
    )

"""FastAPI entrypoint. Three route groups exist at this milestone: a DB-free health check, the
read side of the Provider Management System, and the Provider Health Intelligence dashboard
API — enough to prove the provider architecture end-to-end. Auth, RBAC, and the rest of
docs/api_specification.md's route groups land as their owning modules are built
(docs/roadmap.md).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import os

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.rate_limit import enforce_ip_rate_limit
from modules.intelligence.infrastructure.persistence.models import NewsArticleModel as _NewsArticleModel
from modules.predictions.domain.value_objects import MarketStatus as _MarketStatus
from modules.predictions.infrastructure.ml.model_loader import (
    ArtifactIntegrityError,
    ModelLoaderService,
    UnknownModelFrameworkError,
)
from modules.predictions.infrastructure.ml.supabase_artifact_store import ArtifactStoreError
from modules.predictions.infrastructure.persistence.models import ModelDefinitionModel as _ModelDefinitionModel
from modules.predictions.infrastructure.persistence.models import PredictionModel as _PredictionModel
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository as _SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository as _SqlAlchemyModelRepository,
)
from modules.sports.infrastructure.persistence.database import Environment, get_database_settings, get_environment
from modules.sports.infrastructure.persistence.models import FixtureModel as _FixtureModel
from apps.api.routers import (
    alerts_router,
    billing_router,
    checkout_router,
    graph_router,
    identity_router,
    intelligence_router,
    market_router,
    ml_platform_router,
    prediction_admin_router,
    prediction_analytics_router,
    prediction_router,
    public_router,
    sports_router,
    tenancy_router,
    watchlist_router,
    webhooks_router,
)
from apps.api.auth_deps import require_role
from apps.api.composition import (
    build_competition_fixture_source_repository,
    build_cross_provider_team_mapping_service,
    build_feature_flag_service,
    build_feature_quality_engine,
    build_feature_registration_service,
    build_health_intelligence_engine,
    build_ingestion_quality_engine,
    build_intelligence_enrichment_orchestrator,
    build_monitoring_service,
    build_entity_reconciliation_service,
    build_news_backfill_service,
    build_news_ingestion_service,
    build_provider_management_service,
    build_sync_orchestrator,
    get_football_data_org_adapter,
    get_model_artifact_store,
    get_redis_client,
    get_session,
    PROVIDER_KEY_BY_SPORT,
)
from modules.admin.application.feature_flag_service import FlagAlreadyExistsError, FlagNotFoundError
from modules.identity.domain.entities import AuditLogEntry, User as _AuthUser
from modules.identity.domain.value_objects import AuditAction as _AuditAction, AuditEventId, Role as _Role
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyAuditLogRepository
from modules.admin.application.health_intelligence_engine import (
    ProviderDiagnosticsReport,
    WindowMetrics,
)
from modules.admin.application.provider_management_service import (
    EnvironmentVariableNotSetError,
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
    mask_credential as mask_credential_value,
)
from modules.admin.application.connection_check_service import check_provider_connection
from modules.admin.domain.entities import FeatureFlag, ProviderCredential, ProviderIncident, ProviderUsageRecord
from modules.admin.domain.value_objects import CredentialId, ProviderCategory, ProviderId, QuotaPeriod
from modules.admin.infrastructure.persistence.repositories import (
    SqlAlchemyProviderRepository,
    SqlAlchemyUsageRepository,
)
from modules.features.application.feature_quality_engine import (
    ComputationCostSnapshot,
    FeatureHealthReport,
    FeatureNotFoundError as FeatureQualityNotFoundError,
    FeatureQualitySnapshot,
)
from modules.features.domain.freshness import classify_freshness
from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureNotFoundError as FeatureDefNotFoundError,
    InvalidFeatureDefinitionError,
    InvalidLifecycleTransitionError,
)
from modules.features.domain.entities import FeatureConsumer, FeatureDefinition, FeatureValidationReport
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureKey
from modules.ingestion.application.cross_provider_team_mapping_service import ConfirmedTeamMapping, ExistingTeamRef
from modules.ingestion.application.sync_orchestrator import NoFixtureSourcePreferenceError, SportNotReconciledError
from modules.ingestion.domain.entities import CompetitionFixtureSourcePreference
from modules.ingestion.domain.value_objects import EntityKind as IngestionEntityKind
from modules.ingestion.domain.value_objects import SyncTrigger
from modules.intelligence.application.news_backfill_service import BackfillRequest, BackfillValidationError
from modules.intelligence.domain.entities import NewsSource
from modules.intelligence.domain.value_objects import NewsSourceId, NewsSourceType
from modules.intelligence.domain.value_objects import SyncTrigger as _NewsSyncTrigger
from modules.sports.domain.value_objects import CompetitionId, FixtureId, SeasonId, SportCode, TeamId
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemySportRepository,
    SqlAlchemyTeamRepository,
)
from modules.sports.infrastructure.providers.provider_router import ProviderNotConfiguredError

logger = logging.getLogger("titaniq.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TitanIQ API starting — Milestone 3 (Provider Foundation + Health Intelligence)")
    # Real incident (2026-08-29): which database a running process was actually talking to took a
    # live dashboard/log investigation to answer, because nothing printed it anywhere at startup.
    # Never logs the connection string itself — see database_status()'s _mask_db_host for the same
    # masking rule applied here.
    settings = get_database_settings()
    environment = get_environment()
    engine_kind = "sqlite" if settings.url.startswith("sqlite") else "postgresql"
    logger.info(
        "TitanIQ Environment: %s | Database: %s | Database Host: %s | SQLite fallback: %s",
        environment.value.upper(),
        engine_kind,
        _mask_db_host(settings.url),
        "DISABLED" if environment is not Environment.DEVELOPMENT else "enabled (development only)",
    )
    yield
    logger.info("TitanIQ API shutting down")


app = FastAPI(title="TitanIQ API", version="0.1.0", lifespan=lifespan)


_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


_ADMIN_PATH_PREFIX = "/api/v1/admin"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline response headers (Milestone: Enterprise Security & Compliance, Phase 11), plus a
    global IP-based rate limit on every `/api/v1/admin/*` route.

    This is a JSON API with no server-rendered HTML, so a strict `default-src 'none'` CSP costs
    nothing on every real route — there is no first-party markup/script/style for it to break.
    The one exception is FastAPI's own auto-generated `/docs`/`/redoc` pages, which load Swagger
    UI's JS/CSS from a CDN; a blanket CSP would leave those rendering blank, so they're excluded
    here rather than silently broken. HSTS is safe to send unconditionally: browsers only ever
    honor `Strict-Transport-Security` on a response actually received over HTTPS, so it's a no-op
    over the plain-HTTP connections local dev/tests use and takes effect automatically once this
    sits behind TLS in production, without another change.

    Admin routes are gated by `require_role(ADMINISTRATOR)` on every handler, but that check
    alone has no throttle against scripted credential-stuffing/brute-force traffic hitting those
    routes at volume (Production Readiness Audit §6). Admin routes are spread across `main.py`'s
    inline handlers plus `ml_platform_router`/`prediction_admin_router` — all under the shared
    `/api/v1/admin` prefix — so a single path-prefix check here covers every one of them, rather
    than editing 30+ individual route signatures. `HTTPException` raised inside a
    `@app.middleware("http")` function is NOT caught by FastAPI's own exception handlers (they
    sit closer to routing than this middleware layer), so the 429 is built directly here."""
    if request.url.path.startswith(_ADMIN_PATH_PREFIX):
        try:
            await enforce_ip_rate_limit(request, "admin_api", limit=120, window_seconds=60)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path not in _DOCS_PATHS:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# CORS: the frontend (Milestone 10) is a separate origin (Vite dev server / deployed static host),
# so the browser needs an explicit allowlist — no API route below authenticates via cookies, only
# a Bearer token in the Authorization header, so allow_credentials is not required for that path
# but is enabled for future cookie-based flows (e.g. Supabase's SSR helpers) without another change.
#
# Registered AFTER `security_headers` deliberately (real bug, 2026-08-29): Starlette wraps
# middleware in reverse registration order — the last-added middleware becomes outermost. With
# CORSMiddleware added before security_headers, security_headers wrapped OUTSIDE it, so its
# rate-limit rejection (a raw JSONResponse returned without calling call_next()) never passed
# through CORSMiddleware and shipped with no Access-Control-Allow-Origin header at all. A browser
# can't distinguish "no CORS header" from "server unreachable", so a legitimate admin exceeding
# the 120 req/60s admin-API limit saw every subsequent request reported as a CORS/network failure
# instead of the real 429. Registering CORSMiddleware last makes it the outermost layer, so its
# headers reach every response this app returns, short-circuited or not.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
_cors_origins = [origin.strip() for origin in os.environ.get("TITANIQ_CORS_ORIGINS", _default_origins).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(public_router.router)
app.include_router(identity_router.router)
app.include_router(tenancy_router.router)
app.include_router(billing_router.router)
app.include_router(checkout_router.router)
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
app.include_router(watchlist_router.router)
app.include_router(alerts_router.router)


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


def _serialize_provider(p) -> dict:
    return {
        "id": str(p.id),
        "key": p.key,
        "name": p.name,
        "category": p.category.value,
        "status": p.status.value,
        "priority": p.priority,
        "daily_quota_limit": p.daily_quota_limit,
        "monthly_quota_limit": p.monthly_quota_limit,
        "cache_ttl_seconds": p.cache_ttl_seconds,
        "poll_interval_seconds": p.poll_interval_seconds,
        "base_url": p.base_url,
        "auth_type": p.auth_type,
        "auth_header_name": p.auth_header_name,
        "region": p.region,
        "version": p.version,
        "environment": p.environment,
        "timeout_seconds": p.timeout_seconds,
        "retry_count": p.retry_count,
        "retry_delay_seconds": p.retry_delay_seconds,
        "created_by": p.created_by,
        "updated_by": p.updated_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "capability_note": p.capability_note,
        "capability_checked_at": p.capability_checked_at.isoformat() if p.capability_checked_at else None,
    }


def _serialize_credential_masked(credential: ProviderCredential, masked_value: str) -> dict:
    return {
        "id": str(credential.id),
        "provider_id": str(credential.provider_id),
        "label": credential.label,
        "masked_value": masked_value,
        "is_active": credential.is_active,
        "created_at": credential.created_at.isoformat() if credential.created_at else None,
        "rotated_at": credential.rotated_at.isoformat() if credential.rotated_at else None,
        "expires_at": credential.expires_at.isoformat() if credential.expires_at else None,
    }


def _serialize_usage(record: ProviderUsageRecord) -> dict:
    return {
        "provider_id": str(record.provider_id),
        "period": record.period.value,
        "window_key": record.window_key,
        "request_count": record.request_count,
        "error_count": record.error_count,
    }


async def _audit(
    session: AsyncSession,
    action: _AuditAction,
    actor: _AuthUser,
    request: Request | None,
    *,
    target_id: str | None,
    metadata: dict | None = None,
) -> None:
    """Writes one entry to the shared security audit trail (docs/security.md §2) — the same
    `identity.audit_log_entries` table role changes use, reused here rather than inventing a
    second admin-only audit mechanism (identity/domain/value_objects.py AuditAction is a
    cross-domain closed vocabulary, not identity-only — organization/subscription actions
    already live in it alongside user actions)."""
    entry = AuditLogEntry(
        id=AuditEventId(uuid.uuid4()),
        action=action,
        occurred_at=_now(),
        actor_user_id=actor.id,
        target_type="provider",
        target_id=target_id,
        ip_address=request.client.host if request is not None and request.client else None,
        metadata=metadata or {},
    )
    await SqlAlchemyAuditLogRepository(session=session).append(entry)


@app.get("/api/v1/health")
async def health():
    """Lightweight liveness check — "is the process up and serving requests," nothing more. This
    is the one Render's own health check / the Dockerfile's HEALTHCHECK should point at: a
    dependency outage (DB/Redis down) must not make Render conclude the API process itself is
    dead and start cycling it — that's exactly what /health/ready below is for instead."""
    return envelope(data={"status": "ok"})


@app.get("/api/v1/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)):
    """Deeper dependency check for real operator/debugging use (not Render's primary health
    check target) — verifies the database and Redis are actually reachable, without leaking a
    connection string, hostname, or any other infrastructure detail. Never fails the process:
    a broken dependency here reports "not ready" (503), not a 500 crash."""
    checks: dict[str, str] = {}

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:  # noqa: BLE001 — this endpoint's whole job is to report a failure, not raise one
        checks["database"] = "unhealthy"

    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        checks["redis"] = "healthy"
    except Exception:  # noqa: BLE001
        checks["redis"] = "unhealthy"

    all_healthy = all(status == "healthy" for status in checks.values())
    body = envelope(data={"status": "ready" if all_healthy else "not_ready", **checks})
    if not all_healthy:
        return JSONResponse(status_code=503, content=body)
    return body


@app.get("/api/v1/admin/providers")
async def list_providers(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    repo = SqlAlchemyProviderRepository(session=session)
    providers = await repo.list_all()
    return envelope(data=[_serialize_provider(p) for p in providers])


class RegisterProviderBody(BaseModel):
    key: str
    name: str
    category: str
    priority: int = 100
    daily_quota_limit: int | None = None
    monthly_quota_limit: int | None = None
    base_url: str | None = None
    auth_type: str | None = None
    auth_header_name: str | None = None
    region: str | None = None
    version: str | None = None
    environment: str = "production"
    timeout_seconds: int = 10
    retry_count: int = 2
    retry_delay_seconds: int = 1


def _parse_category(value: str) -> ProviderCategory:
    try:
        return ProviderCategory(value)
    except ValueError:
        valid = ", ".join(c.value for c in ProviderCategory)
        raise HTTPException(status_code=422, detail=f"invalid category '{value}' — must be one of: {valid}") from None


@app.post("/api/v1/admin/providers")
async def create_provider(
    body: RegisterProviderBody, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_provider_management_service(session)
    category = _parse_category(body.category)
    try:
        provider = await service.register_provider(
            body.key, body.name, category,
            priority=body.priority, daily_quota_limit=body.daily_quota_limit,
            monthly_quota_limit=body.monthly_quota_limit, base_url=body.base_url, auth_type=body.auth_type,
            auth_header_name=body.auth_header_name,
            region=body.region, version=body.version, environment=body.environment,
            timeout_seconds=body.timeout_seconds, retry_count=body.retry_count,
            retry_delay_seconds=body.retry_delay_seconds, created_by=str(_admin.id.value),
        )
    except ProviderAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await _audit(
        session, _AuditAction.PROVIDER_REGISTERED, _admin, request,
        target_id=str(provider.id), metadata={"key": provider.key, "category": provider.category.value},
    )
    return envelope(data=_serialize_provider(provider))


@app.get("/api/v1/admin/providers/categories")
async def provider_categories(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    providers = await SqlAlchemyProviderRepository(session=session).list_all()
    counts: dict[str, int] = {c.value: 0 for c in ProviderCategory}
    for p in providers:
        counts[p.category.value] = counts.get(p.category.value, 0) + 1
    return envelope(data=[{"category": category, "provider_count": count} for category, count in counts.items()])


@app.get("/api/v1/admin/providers/status")
async def provider_status_summary(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    providers = await SqlAlchemyProviderRepository(session=session).list_all()
    engine = build_health_intelligence_engine(session)
    by_status: dict[str, int] = {}
    by_health: dict[str, int] = {}
    for p in providers:
        by_status[p.status.value] = by_status.get(p.status.value, 0) + 1
        health_status = (await engine.current_status(p.id)).value
        by_health[health_status] = by_health.get(health_status, 0) + 1
    return envelope(
        data={"total_providers": len(providers), "by_status": by_status, "by_health": by_health}
    )


@app.get("/api/v1/admin/providers/{provider_id}")
async def get_provider(provider_id: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    provider = await SqlAlchemyProviderRepository(session=session).get(ProviderId(uuid.UUID(provider_id)))
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return envelope(data=_serialize_provider(provider))


class UpdateProviderBody(BaseModel):
    name: str | None = None
    priority: int | None = None
    daily_quota_limit: int | None = None
    monthly_quota_limit: int | None = None
    base_url: str | None = None
    auth_type: str | None = None
    auth_header_name: str | None = None
    region: str | None = None
    version: str | None = None
    environment: str | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None
    retry_delay_seconds: int | None = None
    cache_ttl_seconds: int | None = None
    poll_interval_seconds: int | None = None


@app.patch("/api/v1/admin/providers/{provider_id}")
async def update_provider(
    provider_id: str, body: UpdateProviderBody, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_provider_management_service(session)
    pid = ProviderId(uuid.UUID(provider_id))
    try:
        provider = await service.update_provider(pid, updated_by=str(_admin.id.value), **body.model_dump(exclude_unset=True))
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    await _audit(
        session, _AuditAction.PROVIDER_UPDATED, _admin, request,
        target_id=provider_id, metadata=body.model_dump(exclude_unset=True),
    )
    return envelope(data=_serialize_provider(provider))


@app.delete("/api/v1/admin/providers/{provider_id}")
async def delete_provider(
    provider_id: str, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_provider_management_service(session)
    pid = ProviderId(uuid.UUID(provider_id))
    try:
        await service.delete_provider(pid)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    await _audit(session, _AuditAction.PROVIDER_DELETED, _admin, request, target_id=provider_id)
    return envelope(data={"id": provider_id, "deleted": True})


@app.post("/api/v1/admin/providers/{provider_id}/activate")
async def activate_provider(
    provider_id: str, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_provider_management_service(session)
    try:
        provider = await service.activate(ProviderId(uuid.UUID(provider_id)))
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    await _audit(session, _AuditAction.PROVIDER_ACTIVATED, _admin, request, target_id=provider_id)
    return envelope(data={"id": str(provider.id), "status": provider.status.value})


@app.post("/api/v1/admin/providers/{provider_id}/disable")
async def disable_provider(
    provider_id: str, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_provider_management_service(session)
    try:
        provider = await service.deactivate(ProviderId(uuid.UUID(provider_id)))
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    await _audit(session, _AuditAction.PROVIDER_DEACTIVATED, _admin, request, target_id=provider_id)
    return envelope(data={"id": str(provider.id), "status": provider.status.value})


@app.get("/api/v1/admin/providers/{provider_id}/credentials")
async def list_provider_credentials(provider_id: str, session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    service = build_provider_management_service(session)
    pid = ProviderId(uuid.UUID(provider_id))
    pairs = await service.masked_credentials(pid)
    return envelope(data=[_serialize_credential_masked(c, masked) for c, masked in pairs])


class AddCredentialBody(BaseModel):
    label: str
    value: str
    expires_at: datetime | None = None


@app.post("/api/v1/admin/providers/{provider_id}/credentials")
async def add_provider_credential(
    provider_id: str, body: AddCredentialBody, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_provider_management_service(session)
    pid = ProviderId(uuid.UUID(provider_id))
    try:
        credential = await service.add_credential(pid, body.label, body.value, now=_now(), expires_at=body.expires_at)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    await _audit(
        session, _AuditAction.PROVIDER_CREDENTIAL_ADDED, _admin, request,
        target_id=provider_id, metadata={"credential_id": str(credential.id), "label": credential.label},
    )
    return envelope(data=_serialize_credential_masked(credential, mask_credential_value(body.value)))


class RotateCredentialBody(BaseModel):
    old_credential_id: str
    label: str
    value: str
    expires_at: datetime | None = None


@app.post("/api/v1/admin/providers/{provider_id}/rotate-key")
async def rotate_provider_credential(
    provider_id: str, body: RotateCredentialBody, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_provider_management_service(session)
    try:
        credential = await service.rotate_credential(
            CredentialId(uuid.UUID(body.old_credential_id)), body.label, body.value, now=_now(), expires_at=body.expires_at
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="credential not found") from None
    await _audit(
        session, _AuditAction.PROVIDER_CREDENTIAL_ROTATED, _admin, request,
        target_id=provider_id,
        metadata={"old_credential_id": body.old_credential_id, "new_credential_id": str(credential.id)},
    )
    return envelope(data=_serialize_credential_masked(credential, mask_credential_value(body.value)))


class ImportFromEnvBody(BaseModel):
    env_var_name: str
    key: str
    name: str
    category: str
    credential_label: str = "imported-from-env"


@app.post("/api/v1/admin/providers/import-from-env")
async def import_provider_from_env(
    body: ImportFromEnvBody, request: Request, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Migration path for a provider whose only credential today is a raw `.env` value
    (docs/admin_center.md — Milestone 11B). Reads the named env var exactly once and encrypts
    it into the vault; nothing keeps reading the env var afterwards — see
    ProviderManagementService.import_from_env's docstring for why this is a one-time import
    rather than a standing fallback."""
    service = build_provider_management_service(session)
    category = _parse_category(body.category)
    try:
        provider, credential = await service.import_from_env(
            body.env_var_name, body.key, body.name, category,
            now=_now(), credential_label=body.credential_label, created_by=str(_admin.id.value),
        )
    except EnvironmentVariableNotSetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await _audit(
        session, _AuditAction.PROVIDER_IMPORTED_FROM_ENV, _admin, request,
        target_id=str(provider.id), metadata={"env_var_name": body.env_var_name, "key": provider.key},
    )
    return envelope(
        data={
            "provider": _serialize_provider(provider),
            "credential": _serialize_credential_masked(credential, mask_credential_value(os.environ[body.env_var_name])),
        }
    )


async def _run_and_record_connection_test(provider_id: str, session: AsyncSession):
    service = build_provider_management_service(session)
    engine = build_health_intelligence_engine(session)
    pid = ProviderId(uuid.UUID(provider_id))
    return await check_provider_connection(service, engine, pid, _now())


@app.post("/api/v1/admin/providers/{provider_id}/test")
async def test_provider_connection(
    provider_id: str, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    try:
        result = await _run_and_record_connection_test(provider_id, session)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    return envelope(
        data={
            "status": result.status.value, "latency_ms": result.latency_ms,
            "http_status": result.http_status, "message": result.message,
        }
    )


@app.post("/api/v1/admin/providers/{provider_id}/refresh")
async def refresh_provider_connection(
    provider_id: str, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Same probe as `/test` — "Refresh" in the brief means re-check-now, not a distinct
    operation; kept as its own route since the Operations Center UI names it separately."""
    try:
        result = await _run_and_record_connection_test(provider_id, session)
    except ProviderNotFoundError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    return envelope(
        data={
            "status": result.status.value, "latency_ms": result.latency_ms,
            "http_status": result.http_status, "message": result.message,
        }
    )


@app.get("/api/v1/admin/providers/{provider_id}/usage")
async def provider_usage(
    provider_id: str, period: str = Query(default="daily"), limit: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    try:
        quota_period = QuotaPeriod(period)
    except ValueError:
        raise HTTPException(status_code=422, detail="period must be 'daily' or 'monthly'") from None
    pid = ProviderId(uuid.UUID(provider_id))
    provider = await SqlAlchemyProviderRepository(session=session).get(pid)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    records = await SqlAlchemyUsageRepository(session=session).list_by_provider(pid, quota_period, limit=limit)
    total_requests = sum(r.request_count for r in records)
    total_errors = sum(r.error_count for r in records)
    quota_limit = provider.daily_quota_limit if quota_period is QuotaPeriod.DAILY else provider.monthly_quota_limit
    current_window = records[0] if records else None
    return envelope(
        data={
            "provider_id": provider_id,
            "period": period,
            "quota_limit": quota_limit,
            "current_window_requests": current_window.request_count if current_window else 0,
            "remaining_requests": (quota_limit - current_window.request_count) if (quota_limit and current_window) else quota_limit,
            "success_rate": ((total_requests - total_errors) / total_requests) if total_requests else None,
            "history": [_serialize_usage(r) for r in records],
        }
    )


@app.get("/api/v1/admin/providers/{provider_id}/history")
async def provider_history(
    provider_id: str, limit: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    engine = build_health_intelligence_engine(session)
    pid = ProviderId(uuid.UUID(provider_id))
    checks = await engine.health.list_recent(pid, limit=limit)
    incidents = await engine.incidents.list_by_provider(pid)
    return envelope(
        data={
            "recent_checks": [
                {"checked_at": c.checked_at.isoformat(), "success": c.success, "latency_ms": c.latency_ms, "message": c.message}
                for c in checks
            ],
            "incidents": [_serialize_incident(i) for i in incidents],
        }
    )


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
        "freshness_status": q.freshness_status.value,
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
    season_label: str | None = None  # only meaningful for the teams endpoint — season isn't a
    # concept for countries, but reusing one body model beats a second near-identical class


class TriggerFixtureSyncBody(BaseModel):
    season_id: str
    force: bool = False
    live: bool = False


class BootstrapCompetitionBody(BaseModel):
    competition_ref: str
    competition_name: str
    season_label: str
    competition_logo_url: str | None = None


@app.post("/api/v1/admin/sync/{sport_code}/bootstrap")
async def bootstrap_competition(
    sport_code: str, body: BootstrapCompetitionBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """One-time setup before teams/fixtures/standings can sync for a competition —
    reconciles the Competition and Season rows a real provider's `competition_ref`/
    `season_label` refer to (e.g. API-Football's numeric league id and season year), so
    SyncOrchestrator has something to attach synced records to. The Sport itself must already
    be reconciled (see scripts/seed_sports.py) — nothing in the sync pipeline creates that.
    """
    try:
        code = SportCode(sport_code)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized sport_code '{sport_code}'") from None
    sport = await SqlAlchemySportRepository(session=session).get_by_code(code)
    if sport is None:
        raise HTTPException(status_code=409, detail=f"sport '{sport_code}' not reconciled yet — seed it first") from None

    provider_key = PROVIDER_KEY_BY_SPORT.get(sport_code, sport_code)
    reconciler = build_entity_reconciliation_service(session)
    now = _now()
    competition, competition_created = await reconciler.reconcile_competition(
        body.competition_ref, provider_key, sport.id, now,
        name=body.competition_name, logo_url=body.competition_logo_url,
    )
    season, season_created = await reconciler.reconcile_season(
        body.competition_ref, body.season_label, provider_key, competition.id, now
    )
    return envelope(
        data={
            "sport_id": str(sport.id.value),
            "competition_id": str(competition.id.value),
            "competition_created": competition_created,
            "season_id": str(season.id.value),
            "season_created": season_created,
        }
    )


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
        run = await orchestrator.sync_teams(sport_code, competition_ref, _now(), force=body.force, season_label=body.season_label)
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


@app.post("/api/v1/admin/sync/{sport_code}/odds/{fixture_id}")
async def trigger_sync_odds(
    sport_code: str, fixture_id: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Per-fixture, not per-competition (unlike the other trigger_sync_* endpoints above) — odds
    are a single fixture's win-market line, so the caller identifies it by our own persisted
    fixture_id rather than a competition_ref/season_label pair. Looks the fixture's own
    provider_refs up to get the ProviderRef sync_odds_for_fixture needs to call the provider."""
    fixture = await SqlAlchemyFixtureRepository(session=session).get(FixtureId(uuid.UUID(fixture_id)))
    if fixture is None or not fixture.provider_refs:
        raise HTTPException(status_code=404, detail=f"fixture '{fixture_id}' not found or has no provider reference") from None
    orchestrator = build_sync_orchestrator(session)
    run = await orchestrator.sync_odds_for_fixture(sport_code, fixture.provider_refs[0], fixture_id, _now(), force=body.force)
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/statistics/{fixture_id}")
async def trigger_sync_team_statistics(
    sport_code: str, fixture_id: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Per-fixture, same shape as trigger_sync_odds above — fetches both teams' match statistics
    for this one fixture, keyed by our own persisted fixture_id."""
    fixture = await SqlAlchemyFixtureRepository(session=session).get(FixtureId(uuid.UUID(fixture_id)))
    if fixture is None or not fixture.provider_refs:
        raise HTTPException(status_code=404, detail=f"fixture '{fixture_id}' not found or has no provider reference") from None
    orchestrator = build_sync_orchestrator(session)
    run = await orchestrator.sync_team_statistics_for_fixture(sport_code, fixture.provider_refs[0], fixture_id, _now(), force=body.force)
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/players/{team_id}")
async def trigger_sync_players(
    sport_code: str, team_id: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Per-team, same shape as trigger_sync_odds/trigger_sync_team_statistics above — fetches one
    team's real roster, keyed by our own persisted team_id."""
    team = await SqlAlchemyTeamRepository(session=session).get(TeamId(uuid.UUID(team_id)))
    if team is None or not team.provider_refs:
        raise HTTPException(status_code=404, detail=f"team '{team_id}' not found or has no provider reference") from None
    orchestrator = build_sync_orchestrator(session)
    run = await orchestrator.sync_players(sport_code, team.provider_refs[0], _now(), force=body.force, season_label=body.season_label)
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/lineups/{fixture_id}")
async def trigger_sync_lineups(
    sport_code: str, fixture_id: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Per-fixture, same shape as trigger_sync_odds/trigger_sync_team_statistics — the reconciler
    and validator side of this were already real (docs/roadmap.md Milestone 5), only the
    orchestration to actually call them was missing until now."""
    fixture = await SqlAlchemyFixtureRepository(session=session).get(FixtureId(uuid.UUID(fixture_id)))
    if fixture is None or not fixture.provider_refs:
        raise HTTPException(status_code=404, detail=f"fixture '{fixture_id}' not found or has no provider reference") from None
    orchestrator = build_sync_orchestrator(session)
    # Milestone 5 §13: trigger is always derived server-side, never from the request body
    # (TriggerSyncBody has no such field) — explicit here so it can never silently drift back to
    # a default that isn't ADMIN_MANUAL.
    run = await orchestrator.sync_lineups(
        sport_code, fixture.provider_refs[0], fixture_id, _now(), force=body.force, trigger=SyncTrigger.ADMIN_MANUAL
    )
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/injuries/{team_id}")
async def trigger_sync_injuries(
    sport_code: str, team_id: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Per-team, same shape as trigger_sync_players above."""
    team = await SqlAlchemyTeamRepository(session=session).get(TeamId(uuid.UUID(team_id)))
    if team is None or not team.provider_refs:
        raise HTTPException(status_code=404, detail=f"team '{team_id}' not found or has no provider reference") from None
    orchestrator = build_sync_orchestrator(session)
    run = await orchestrator.sync_injuries(
        sport_code, team.provider_refs[0], _now(), force=body.force, season_label=body.season_label,
        trigger=SyncTrigger.ADMIN_MANUAL,
    )
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/transfers/{team_id}")
async def trigger_sync_transfers(
    sport_code: str, team_id: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Per-team, same shape as trigger_sync_players above."""
    team = await SqlAlchemyTeamRepository(session=session).get(TeamId(uuid.UUID(team_id)))
    if team is None or not team.provider_refs:
        raise HTTPException(status_code=404, detail=f"team '{team_id}' not found or has no provider reference") from None
    orchestrator = build_sync_orchestrator(session)
    run = await orchestrator.sync_transfers(
        sport_code, team.provider_refs[0], _now(), force=body.force, trigger=SyncTrigger.ADMIN_MANUAL
    )
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/coaching-staff/{team_id}")
async def trigger_sync_coaching_staff(
    sport_code: str, team_id: str, body: TriggerSyncBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Per-team, same shape as trigger_sync_players above."""
    team = await SqlAlchemyTeamRepository(session=session).get(TeamId(uuid.UUID(team_id)))
    if team is None or not team.provider_refs:
        raise HTTPException(status_code=404, detail=f"team '{team_id}' not found or has no provider reference") from None
    orchestrator = build_sync_orchestrator(session)
    run = await orchestrator.sync_coaching_staff(sport_code, team.provider_refs[0], _now(), force=body.force)
    return envelope(data=_serialize_sync_run(run))


# -- football-data.org integration: per-competition fixture-source preference + team mapping ------


class SetFixtureSourceBody(BaseModel):
    preferred_provider_key: str
    provider_competition_ref: str
    notes: str | None = None


class TeamMappingItem(BaseModel):
    football_data_org_team_id: str
    titaniq_team_id: str


class ConfirmTeamMappingsBody(BaseModel):
    mappings: list[TeamMappingItem]


class TriggerUpcomingFixturesSyncBody(BaseModel):
    season_label: str
    season_id: str
    force: bool = False


def _serialize_fixture_source(preference: CompetitionFixtureSourcePreference) -> dict:
    return {
        "competition_id": preference.competition_id,
        "preferred_provider_key": preference.preferred_provider_key,
        "provider_competition_ref": preference.provider_competition_ref,
        "notes": preference.notes,
        "updated_at": preference.updated_at.isoformat() if preference.updated_at else None,
    }


@app.get("/api/v1/admin/competitions/{competition_id}/fixture-source")
async def get_competition_fixture_source(
    competition_id: str, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    repo = build_competition_fixture_source_repository(session)
    preference = await repo.get_by_competition(competition_id)
    return envelope(data=_serialize_fixture_source(preference) if preference else None)


@app.put("/api/v1/admin/competitions/{competition_id}/fixture-source")
async def set_competition_fixture_source(
    competition_id: str, body: SetFixtureSourceBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """The admin-curated routing rule `SyncOrchestrator.sync_upcoming_fixtures` honors
    automatically on every future call — see `CompetitionFixtureSourcePreference`'s docstring."""
    repo = build_competition_fixture_source_repository(session)
    preference = await repo.upsert(
        CompetitionFixtureSourcePreference(
            competition_id=competition_id, preferred_provider_key=body.preferred_provider_key,
            provider_competition_ref=body.provider_competition_ref, notes=body.notes, updated_at=_now(),
        )
    )
    return envelope(data=_serialize_fixture_source(preference))


@app.delete("/api/v1/admin/competitions/{competition_id}/fixture-source")
async def clear_competition_fixture_source(
    competition_id: str, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    repo = build_competition_fixture_source_repository(session)
    await repo.delete(competition_id)
    return envelope(data={"deleted": True})


@app.get("/api/v1/admin/providers/football-data-org/team-suggestions")
async def suggest_football_data_org_team_mappings(
    competition_id: str = Query(...), provider_competition_ref: str = Query(...),
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Read-only — never writes a mapping. Lists every football-data.org team in the given
    competition next to a suggested existing-TitanIQ-team match (by normalized name), for an
    admin to review before calling the confirm endpoint below. Candidate existing teams are every
    team in the competition's sport (teams aren't competition-scoped in TitanIQ's domain model),
    which is a harmless superset — normalized-name matching won't accidentally match an unrelated
    club."""
    competition = await SqlAlchemyCompetitionRepository(session=session).get(CompetitionId(uuid.UUID(competition_id)))
    if competition is None:
        raise HTTPException(status_code=404, detail=f"competition '{competition_id}' not found") from None
    existing_teams_domain = await SqlAlchemyTeamRepository(session=session).list_by_sport(competition.sport_id)
    existing_teams = [ExistingTeamRef(id=str(team.id.value), name=team.name) for team in existing_teams_domain]
    adapter = get_football_data_org_adapter(session)
    fd_teams = await adapter.fetch_teams(provider_competition_ref)
    service = build_cross_provider_team_mapping_service(session)
    suggestions = service.suggest_mappings(fd_teams, existing_teams)
    return envelope(
        data=[
            {
                "football_data_org_team_id": s.football_data_org_team_id,
                "football_data_org_team_name": s.football_data_org_team_name,
                "suggested_titaniq_team_id": s.suggested_titaniq_team_id,
                "suggested_titaniq_team_name": s.suggested_titaniq_team_name,
                "confidence": s.confidence,
            }
            for s in suggestions
        ]
    )


@app.post("/api/v1/admin/providers/football-data-org/team-mappings")
async def confirm_football_data_org_team_mappings(
    body: ConfirmTeamMappingsBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """The only write path for cross-provider team identity — see
    `CrossProviderTeamMappingService.confirm_mappings`'s docstring. Never called automatically;
    always an explicit admin action confirming (possibly editing) the suggestions above."""
    service = build_cross_provider_team_mapping_service(session)
    await service.confirm_mappings(
        [
            ConfirmedTeamMapping(
                football_data_org_team_id=item.football_data_org_team_id, titaniq_team_id=item.titaniq_team_id
            )
            for item in body.mappings
        ]
    )
    return envelope(data={"mapped": len(body.mappings)})


@app.post("/api/v1/admin/sync/{sport_code}/competitions/{competition_id}/upcoming-fixtures")
async def trigger_sync_upcoming_fixtures(
    sport_code: str, competition_id: str, body: TriggerUpcomingFixturesSyncBody,
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """`competition_id` is TitanIQ's own internal id, not a provider-specific ref — the
    per-competition `CompetitionFixtureSourcePreference` (set via the endpoint above) supplies
    whatever provider-specific ref the resolved adapter actually needs."""
    orchestrator = build_sync_orchestrator(session)
    season_id = SeasonId(uuid.UUID(body.season_id))
    try:
        run = await orchestrator.sync_upcoming_fixtures(
            sport_code, competition_id, body.season_label, season_id, _now(), force=body.force,
        )
    except NoFixtureSourcePreferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/competitions/{competition_id}/completed-fixtures")
async def trigger_sync_completed_fixtures(
    sport_code: str, competition_id: str, body: TriggerUpcomingFixturesSyncBody,
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """`sync_upcoming_fixtures`'s companion — resolves final scores for fixtures already synced
    while upcoming via this competition's `CompetitionFixtureSourcePreference`."""
    orchestrator = build_sync_orchestrator(session)
    season_id = SeasonId(uuid.UUID(body.season_id))
    try:
        run = await orchestrator.sync_completed_fixtures(
            sport_code, competition_id, body.season_label, season_id, _now(), force=body.force,
        )
    except NoFixtureSourcePreferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_sync_run(run))


@app.post("/api/v1/admin/sync/{sport_code}/competitions/{competition_id}/standings-alt")
async def trigger_sync_standings_alt(
    sport_code: str, competition_id: str, body: TriggerUpcomingFixturesSyncBody,
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """`sync_upcoming_fixtures`/`sync_completed_fixtures`'s companion for standings — routes
    through this competition's `CompetitionFixtureSourcePreference` (football-data.org, when
    api-football's free tier can't serve the current season) instead of the default provider."""
    orchestrator = build_sync_orchestrator(session)
    season_id = SeasonId(uuid.UUID(body.season_id))
    try:
        run = await orchestrator.sync_standings_alt(
            sport_code, competition_id, body.season_label, season_id, _now(), force=body.force,
        )
    except NoFixtureSourcePreferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
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


# -- Milestone 8: News Ingestion (real RSS pipe, no paid API key required) ------------------------


class RegisterNewsSourceBody(BaseModel):
    name: str
    url: str
    source_type: str = "rss_feed"
    is_official: bool = False


def _serialize_news_source(source: NewsSource) -> dict:
    return {
        "id": str(source.id.value),
        "source_type": source.source_type.value,
        "name": source.name,
        "url": source.url,
        "is_official": source.is_official,
        "created_at": source.created_at.isoformat() if source.created_at else None,
    }


def _serialize_intelligence_sync_run(run) -> dict:
    return {
        "run_id": str(run.id), "channel_type": run.channel_type.value, "channel_key": run.channel_key,
        "trigger": run.trigger.value, "status": run.status.value, "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": run.duration_seconds, "items_fetched": run.items_fetched,
        "items_created": run.items_created, "items_duplicate": run.items_duplicate,
        "items_rejected": run.items_rejected, "error_message": run.error_message,
    }


@app.post("/api/v1/admin/news/sources")
async def register_news_source(
    body: RegisterNewsSourceBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    try:
        source_type = NewsSourceType(body.source_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized source_type '{body.source_type}'") from None

    service = build_news_ingestion_service(session)
    existing = await service.sources.get_by_url(body.url)
    source = NewsSource(
        id=existing.id if existing else NewsSourceId(uuid.uuid4()),
        source_type=source_type, name=body.name, url=body.url, is_official=body.is_official,
        created_at=existing.created_at if existing else _now(),
    )
    saved = await service.sources.upsert(source)
    return envelope(data=_serialize_news_source(saved))


@app.get("/api/v1/admin/news/sources")
async def list_news_sources(
    session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    service = build_news_ingestion_service(session)
    sources = await service.sources.list_all()
    return envelope(data=[_serialize_news_source(s) for s in sources])


@app.post("/api/v1/admin/news/sources/{source_id}/sync")
async def trigger_news_sync(
    source_id: str, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    try:
        parsed_id = NewsSourceId(uuid.UUID(source_id))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid source_id '{source_id}'") from None

    service = build_news_ingestion_service(session)
    orchestrator = build_intelligence_enrichment_orchestrator(session)
    now = _now()
    try:
        # Milestone 10: an administrator's one-off click is ADMIN_MANUAL, distinct from
        # LIVE_SCHEDULED (the only trigger classify_news_availability ever honors for
        # VERIFIED_PRE_MATCH) — this endpoint can never spoof scheduled provenance.
        run = await service.sync_source(
            parsed_id, now, trigger=_NewsSyncTrigger.ADMIN_MANUAL,
            on_article_created=lambda article: orchestrator.enrich_article(
                article, now, trigger=_NewsSyncTrigger.ADMIN_MANUAL,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return envelope(data=_serialize_intelligence_sync_run(run))


class NewsBackfillRequestBody(BaseModel):
    source_id: str
    season_id: str
    since: datetime
    until: datetime | None = None
    max_articles: int | None = None
    dry_run: bool = True


def _serialize_backfill_plan(plan) -> dict:
    return {
        "source_id": str(plan.source_id.value),
        "source_name": plan.source_name,
        "requested_since": plan.requested_since.isoformat(),
        "requested_until": plan.requested_until.isoformat() if plan.requested_until else None,
        "effective_since": plan.effective_since.isoformat(),
        "effective_until": plan.effective_until.isoformat(),
        "max_articles": plan.max_articles,
        "window_clamped": plan.window_clamped,
    }


def _serialize_backfill_summary(summary) -> dict:
    return {
        "dry_run": summary.dry_run,
        "plan": _serialize_backfill_plan(summary.plan),
        "sync_run_id": summary.sync_run_id,
        "articles_seen": summary.articles_seen,
        "articles_deduplicated": summary.articles_deduplicated,
        "articles_rejected": summary.articles_rejected,
        "articles_within_window": summary.articles_within_window,
        "articles_outside_window": summary.articles_outside_window,
        "articles_relevant": summary.articles_relevant,
        "articles_skipped_by_relevance": summary.articles_skipped_by_relevance,
        "articles_sent_to_gemini": summary.articles_sent_to_gemini,
        "articles_enriched": summary.articles_enriched,
        "enrichment_failures": summary.enrichment_failures,
        "provenance_verified": summary.provenance_verified,
        "provenance_unknown": summary.provenance_unknown,
        "errors": summary.errors,
    }


@app.post("/api/v1/admin/news/backfill")
async def trigger_news_backfill(
    body: NewsBackfillRequestBody, session: AsyncSession = Depends(get_session),
    _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR)),
):
    """Milestone 12 — controlled historical catch-up sync for a single source, distinct from both
    the scheduled LIVE_SCHEDULED path and this file's own ADMIN_MANUAL sync above. `dry_run`
    defaults True (the primary verification mode): the request is validated and its bounded
    window computed, but nothing is fetched, persisted, or sent to Gemini. A real
    (``dry_run=false``) run additionally requires ``TITANIQ_NEWS_BACKFILL_ENABLED=true`` — refused
    otherwise, with the refusal recorded in the response rather than silently downgraded to a
    dry-run. BACKFILL can never produce VERIFIED_PRE_MATCH provenance (only LIVE_SCHEDULED can,
    enforced in `news_provenance.classify_news_availability`, unchanged by this endpoint)."""
    try:
        source_id = NewsSourceId(uuid.UUID(body.source_id))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid source_id '{body.source_id}'") from None
    try:
        season_id = SeasonId(uuid.UUID(body.season_id))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid season_id '{body.season_id}'") from None

    service = build_news_backfill_service(session)
    now = _now()
    request = BackfillRequest(
        source_id=source_id, season_id=season_id, since=body.since, until=body.until,
        max_articles=body.max_articles, dry_run=body.dry_run,
    )
    try:
        summary = await service.run(request, now)
    except BackfillValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return envelope(data=_serialize_backfill_summary(summary))


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
            # spec §26 "Context Freshness" — the real CURRENT/STALE/UNKNOWN verdict derived from
            # `freshness_score` (never independently invented).
            "freshness_status": classify_freshness(report.freshness_score).value,
        }
    )


@app.get("/api/v1/admin/monitoring/redis")
async def get_redis_health(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    monitoring = build_monitoring_service(session)
    report = await monitoring.redis_health(get_redis_client())
    return envelope(data={"healthy": report.healthy, "latency_ms": report.latency_ms, "error": report.error})


@app.get("/api/v1/admin/monitoring/worker")
async def get_worker_health(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    """Post-match resolution pipeline audit (2026-08-23) — `MonitoringService.worker_health()` has
    existed since Milestone 5 (real `celery_app.control.inspect()`, no fabricated heartbeat) but
    had no route exposing it; this is the missing wiring, not new monitoring logic. A real,
    connected Celery worker answers `inspect().stats()`/`.active()` within Celery's own inspect
    timeout — `workers_online: 0` here is an honest "no worker is currently reachable," never a
    guess, and is exactly what this endpoint is for: telling an operator whether the automated
    resolution pipeline has anything actually running it."""
    from modules.ingestion.infrastructure.celery.celery_app import celery_app

    monitoring = build_monitoring_service(session)
    report = monitoring.worker_health(celery_app)
    return envelope(
        data={
            "workers_online": report.workers_online,
            "worker_names": list(report.worker_names),
            "active_task_counts": report.active_task_counts,
            "error": report.error,
        }
    )


def _mask_db_host(url: str) -> str:
    """Never the credentials, never the full connection string — just enough to answer "which
    database, roughly" (Production Readiness Audit-style incident, 2026-08-29: distinguishing a
    real production Supabase host from a stale one took reading a raw connection string in a
    dashboard DOM, which is exactly the kind of ad-hoc credential exposure this endpoint exists to
    make unnecessary). Shows only the last two DNS labels, prefixed with asterisks."""
    try:
        host = urlsplit(url.replace("+asyncpg", "").replace("+aiosqlite", "")).hostname
    except ValueError:
        return "unknown"
    if not host:
        return "n/a (sqlite)"
    labels = host.split(".")
    return "*****." + ".".join(labels[-2:]) if len(labels) > 2 else host


@app.get("/api/v1/admin/system/database-status")
async def database_status(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    """Answers, in one place and without an operator ever needing to read a raw connection string,
    the exact question a 2026-08-29 incident took an hour of live dashboard/log spelunking to
    answer: which environment is this process, which real database is it talking to, and is the
    data flowing through it actually current — never exposing the connection string, password, or
    any other secret itself."""
    settings = get_database_settings()
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"

    connectivity = "healthy"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — this endpoint's job is to report a failure, not raise one
        connectivity = "unhealthy"

    migration_revision = None
    try:
        version_table = "alembic_version" if dialect == "sqlite" else "sports.alembic_version"
        row = (await session.execute(text(f"SELECT version_num FROM {version_table}"))).first()  # noqa: S608 — version_table is one of two fixed internal literals, never user input
        migration_revision = row[0] if row else None
    except Exception:  # noqa: BLE001
        migration_revision = None

    async def _latest(model, column_name: str) -> str | None:
        try:
            column = getattr(model, column_name)
            value = (await session.execute(select(func.max(column)))).scalar()
            return value.isoformat() if value else None
        except Exception:  # noqa: BLE001 — one stat's failure must never blacken the whole report
            return None

    latest_fixture, latest_prediction, latest_model, latest_news = await asyncio.gather(
        _latest(_FixtureModel, "updated_at"),
        _latest(_PredictionModel, "generated_at"),
        _latest(_ModelDefinitionModel, "created_at"),
        _latest(_NewsArticleModel, "fetched_at"),
    )

    return envelope(
        data={
            "environment": get_environment().value,
            "database_engine": "postgresql" if dialect != "sqlite" else "sqlite",
            "database_host": _mask_db_host(settings.url),
            "connectivity": connectivity,
            "migration_revision": migration_revision,
            "sqlite_fallback_disabled": get_environment() is not Environment.DEVELOPMENT,
            "latest_fixture_updated_at": latest_fixture,
            "latest_prediction_generated_at": latest_prediction,
            "latest_model_created_at": latest_model,
            "latest_news_fetched_at": latest_news,
        }
    )


@app.get("/api/v1/admin/system/model-health")
async def model_health(session: AsyncSession = Depends(get_session), _admin: _AuthUser = Depends(require_role(_Role.ADMINISTRATOR))):
    """Real-time Champion artifact audit (Production Integrity Hardening, 2026-08-29) — a
    registry row saying CHAMPION is not evidence the artifact it points at is actually loadable;
    a real production incident the same day (several football markets' artifacts silently
    missing from Supabase Storage) took manual log archaeology to even enumerate. Runs
    `ModelLoaderService.load()` — the exact same fetch/checksum/deserialize path a real
    prediction request takes — against every PRODUCTION market's Champion, through a throwaway
    loader instance (never the shared serving cache), so this is read-only: no Champion status,
    cache entry, or DB row is ever touched by running this audit.
    """
    markets_repo = _SqlAlchemyMarketRepository(session=session)
    models_repo = _SqlAlchemyModelRepository(session=session)
    loader = ModelLoaderService(artifact_store=get_model_artifact_store())

    markets = await markets_repo.list_by_status(_MarketStatus.PRODUCTION)
    champions: list[dict] = []

    for market in markets:
        champion = await models_repo.get_champion(market.id)
        if champion is None:
            champions.append({"market_key": market.market_key, "status": "NO_CHAMPION"})
            continue
        if not champion.is_genuinely_trained():
            champions.append(
                {
                    "market_key": market.market_key,
                    "model_id": str(champion.id.value),
                    "algorithm": champion.algorithm,
                    "status": "INVALID_CHAMPION",
                    "detail": "placeholder/never-trained Champion (artifact_ref is None)",
                }
            )
            continue

        entry = {
            "market_key": market.market_key,
            "model_id": str(champion.id.value),
            "version": champion.version,
            "algorithm": champion.algorithm,
            "framework": champion.framework,
            "artifact_ref": champion.artifact_ref,
            "promoted_at": champion.promoted_at.isoformat() if champion.promoted_at else None,
        }
        try:
            await loader.load(
                champion.id, champion.framework, champion.algorithm, market.target_type,
                champion.artifact_ref, champion.artifact_checksum,
            )
            entry["status"] = "HEALTHY"
        except ArtifactIntegrityError as exc:
            entry["status"], entry["error"] = "CORRUPT_ARTIFACT", str(exc)
        except ArtifactStoreError as exc:
            entry["status"], entry["error"] = "MISSING_ARTIFACT", str(exc)
        except FileNotFoundError as exc:
            entry["status"], entry["error"] = "LEGACY_LOCAL_ONLY", str(exc)
        except UnknownModelFrameworkError as exc:
            entry["status"], entry["error"] = "UNKNOWN_FAILURE", str(exc)
        except Exception as exc:  # noqa: BLE001 — this endpoint's whole job is to catalogue every failure, not raise one
            entry["status"], entry["error"] = "RUNTIME_LOAD_FAILED", str(exc)
        champions.append(entry)

    summary: dict[str, int] = {}
    for c in champions:
        summary[c["status"]] = summary.get(c["status"], 0) + 1

    return envelope(
        data={
            "checked_at": _now().isoformat(),
            "total_production_markets": len(markets),
            "summary": summary,
            "champions": champions,
        }
    )


# Knowledge-graph single-entity lookup lives at GET /api/v1/graph/entities/{node_type}/{entity_ref}
# (apps/api/routers/graph_router.py) — that endpoint now also returns edges_out/edges_in, so this
# admin-only duplicate (which resolved the exact same kg.nodes.get_by_entity_ref() call under a
# different path/auth posture) was removed rather than kept as a second source for the same data.

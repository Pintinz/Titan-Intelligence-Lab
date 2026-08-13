"""Milestone 11 — the production Celery worker composition root.

The pre-implementation audit (docs/milestone11_verification_report.md) found two compounding
gaps, both real and both fixed here, nowhere else:

1. **No task module was ever imported in a production process.** `celery_app.py` declares no
   `include=[...]` and nothing calls `app.autodiscover_tasks()`, so a real
   ``celery -A ... worker`` process would never register any ``@celery_app.task`` — every
   existing task, not just new ones, was unreachable outside tests (which import task modules
   directly and run them eagerly, in-process, bypassing registration entirely).
2. **No production caller ever invoked any of the five `set_*_factory` functions.** Every
   factory's fail-closed `RuntimeError` (already correct, unchanged here) fires on the very first
   task execution in a real deployment, since nothing upstream ever configures it.

This module is the single place that fixes both: importing every task module (so Celery's task
registry is populated) and wiring every factory to real, composed application services (so tasks
can actually run) — nothing task-specific changes; every existing task's business logic, retry
policy, and Beat schedule entry is untouched.

Entry point for a real worker process:

    celery -A apps.worker.bootstrap worker --loglevel=info

``celery_app`` is re-exported at module level for Celery's ``-A`` app-discovery. Bootstrap itself
runs via the ``worker_process_init`` signal — fired exactly once per forked worker process, which
is also the correct place to create this process's own database engine/connections (an asyncio
engine created before a prefork fork is unsafe to share across the fork boundary; this codebase's
whole `docs/decisions.md` posture on "worker builds its own state" already assumes this).
``bootstrap_worker()`` is also directly callable (and directly tested) without needing a real
Celery worker process at all.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from celery.signals import worker_process_init

from apps.api.composition import (
    build_calibration_fitting_service,
    build_engine,
    build_health_intelligence_engine,
    build_provider_management_service,
    build_scheduled_news_sync_service,
    build_scheduled_retraining_orchestrator,
    build_sync_orchestrator,
)
from modules.ingestion.infrastructure.celery.celery_app import celery_app

logger = logging.getLogger("titaniq.worker")

# Re-exported so `celery -A apps.worker.bootstrap worker` finds the shared app instance directly.
__all__ = ["celery_app", "bootstrap_worker", "validate_environment", "FACTORY_REGISTRY"]


class WorkerConfigurationError(RuntimeError):
    """Raised when required environment configuration is missing at worker startup — never a
    fabricated default, never a silent skip (spec §8: "Do not add fake defaults")."""


class FactoryRegistrationError(RuntimeError):
    """Raised by `validate_factory_registry()` when bootstrap completes without every required
    factory having registered — this is the FAIL CLOSED path: the worker must never report ready
    while a task's dependency would raise on first real invocation instead of at startup, where a
    human can actually see it."""


# Every environment variable required for at least one production factory below. Each is already
# independently required by the settings class it backs (`DatabaseSettings`/`RedisSettings`/
# `VaultSettings`, all raise a raw pydantic ValidationError if unset) — this is a friendlier,
# single, up-front check naming every missing var at once, rather than discovering them one at a
# time as each dependent service happens to get constructed.
REQUIRED_ENV_VARS: tuple[str, ...] = ("TITANIQ_DB_URL", "TITANIQ_REDIS_URL", "TITANIQ_ENCRYPTION_KEY")


def validate_environment(env: dict[str, str] | None = None) -> None:
    source = env if env is not None else os.environ
    missing = [name for name in REQUIRED_ENV_VARS if not source.get(name, "").strip()]
    if missing:
        raise WorkerConfigurationError(
            "Celery worker cannot start — missing required configuration: "
            + ", ".join(missing)
            + ". Set these environment variables before starting the worker; no fake default is substituted."
        )


@dataclass
class FactoryRecord:
    """One row of the explicit factory registry (spec §5) — a factory's identity and the tasks
    that break without it, independent of whether it has actually registered yet."""

    name: str
    module: str
    service: str
    task_names: tuple[str, ...]
    registered: bool = False


def _fresh_registry() -> dict[str, FactoryRecord]:
    return {
        "orchestrator": FactoryRecord(
            name="orchestrator", module="modules.ingestion.infrastructure.celery.tasks", service="SyncOrchestrator",
            task_names=(
                "ingestion.sync_countries", "ingestion.sync_teams", "ingestion.sync_fixtures",
                "ingestion.sync_live_fixtures", "ingestion.sync_standings", "ingestion.sync_upcoming_fixtures",
                "ingestion.sync_completed_fixtures", "ingestion.sync_standings_alt",
                "ingestion.sync_upcoming_structured_intelligence", "ingestion.sync_odds",
                "ingestion.sync_team_statistics",
            ),
        ),
        "admin_context": FactoryRecord(
            name="admin_context", module="modules.admin.infrastructure.celery.tasks",
            service="(ProviderManagementService, HealthIntelligenceEngine)",
            task_names=("admin.check_all_provider_health",),
        ),
        "retraining_orchestrator": FactoryRecord(
            name="retraining_orchestrator", module="modules.predictions.infrastructure.celery.tasks",
            service="ScheduledRetrainingOrchestrator", task_names=("predictions.check_scheduled_retraining",),
        ),
        "calibration_service": FactoryRecord(
            name="calibration_service", module="modules.predictions.infrastructure.celery.tasks",
            service="CalibrationFittingService", task_names=("predictions.check_scheduled_calibration",),
        ),
        "scheduled_news_sync": FactoryRecord(
            name="scheduled_news_sync", module="modules.intelligence.infrastructure.celery.tasks",
            service="ScheduledNewsSyncService", task_names=("intelligence.sync_scheduled_news",),
        ),
    }


# Module-level, explicit (not hidden) — a real, inspectable snapshot of this worker process's
# wiring state. Rebuilt fresh by every `bootstrap_worker()` call so tests never leak state into
# each other (spec §13's "preserve test isolation").
FACTORY_REGISTRY: dict[str, FactoryRecord] = _fresh_registry()


def _build_worker_session_factory() -> async_sessionmaker[AsyncSession]:
    """A dedicated engine, autocommit-isolated, distinct from `composition.get_session_factory()`
    (which FastAPI's per-request `get_session` dependency owns — never reused here, per spec §7).

    Every existing task's business logic is a sequence of independent, already-complete repository
    operations (`upsert`/`record`/etc.) with no cross-call atomicity requirement — the same shape
    `scripts/seed_football_markets.py` already committed once at the very end of a one-shot run.
    A long-lived worker has no equivalent single "end of request" moment to hang a final commit
    off of without changing every task module's `_get_X()` return-value contract (which this
    milestone must not do — spec §11, "do not rewrite the business logic of ... tasks"). Setting
    `isolation_level="AUTOCOMMIT"` on the connections this factory hands out makes every individual
    statement durable immediately, closing the "session is silently rolled back on GC because
    nothing ever explicitly called commit()" gap without touching any task or service code."""
    engine = build_engine().execution_options(isolation_level="AUTOCOMMIT")
    return async_sessionmaker(engine, expire_on_commit=False)


def import_task_modules() -> tuple[str, ...]:
    """The other half of the production gap: importing each module is what actually registers its
    `@celery_app.task`-decorated functions with the shared Celery app. Explicit, not
    `autodiscover_tasks()` — per the user's own direction, this architecture intentionally keeps
    task registration explicit rather than adding scanning behavior the existing design never had."""
    import modules.admin.infrastructure.celery.tasks as admin_tasks
    import modules.ingestion.infrastructure.celery.tasks as ingestion_tasks
    import modules.intelligence.infrastructure.celery.tasks as intelligence_tasks
    import modules.predictions.infrastructure.celery.tasks as predictions_tasks

    modules_imported = (
        admin_tasks.__name__, ingestion_tasks.__name__, intelligence_tasks.__name__, predictions_tasks.__name__,
    )
    logger.info("worker: task modules imported: %s", ", ".join(modules_imported))
    return modules_imported


def register_factories(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Wires all 5 production factories to real, composed application services — one fresh
    session per task invocation (never a shared mutable session, never the FastAPI request-scoped
    one), built via the existing `apps.api.composition` builders. No task-module code changes."""
    from modules.admin.infrastructure.celery.tasks import set_admin_context_factory
    from modules.ingestion.infrastructure.celery.tasks import set_orchestrator_factory
    from modules.intelligence.infrastructure.celery.tasks import set_scheduled_news_sync_service_factory
    from modules.predictions.infrastructure.celery.tasks import (
        set_calibration_service_factory,
        set_retraining_orchestrator_factory,
    )

    async def orchestrator_factory():
        return build_sync_orchestrator(session_factory())

    async def admin_context_factory():
        session = session_factory()
        return build_provider_management_service(session), build_health_intelligence_engine(session)

    async def retraining_orchestrator_factory():
        return build_scheduled_retraining_orchestrator(session_factory())

    async def calibration_service_factory():
        return build_calibration_fitting_service(session_factory())

    async def scheduled_news_sync_factory():
        return build_scheduled_news_sync_service(session_factory())

    set_orchestrator_factory(orchestrator_factory)
    FACTORY_REGISTRY["orchestrator"].registered = True

    set_admin_context_factory(admin_context_factory)
    FACTORY_REGISTRY["admin_context"].registered = True

    set_retraining_orchestrator_factory(retraining_orchestrator_factory)
    FACTORY_REGISTRY["retraining_orchestrator"].registered = True

    set_calibration_service_factory(calibration_service_factory)
    FACTORY_REGISTRY["calibration_service"].registered = True

    set_scheduled_news_sync_service_factory(scheduled_news_sync_factory)
    FACTORY_REGISTRY["scheduled_news_sync"].registered = True

    logger.info("worker: %d/%d factories registered", sum(r.registered for r in FACTORY_REGISTRY.values()), len(FACTORY_REGISTRY))


def validate_factory_registry() -> None:
    """FAIL CLOSED (spec §4/§6): a worker must never report ready while any required factory is
    still unregistered — that would silently defer the failure to the first real task execution
    instead of surfacing it clearly at startup."""
    missing = [record for record in FACTORY_REGISTRY.values() if not record.registered]
    if missing:
        detail = "; ".join(
            f"factory={m.name!r} service={m.service!r} affected_tasks={list(m.task_names)!r}" for m in missing
        )
        raise FactoryRegistrationError(
            f"Celery worker startup failed — {len(missing)} required factory(ies) did not register: {detail}"
        )
    logger.info("worker: factory registry validated — all %d factories ready", len(FACTORY_REGISTRY))


def bootstrap_worker() -> None:
    """The real production startup sequence (spec §5's ordering), directly callable and directly
    testable without a live Celery worker process. Never performs a business task, never calls an
    external API, never opens a long-lived session of its own — it only wires the dependencies
    other code will later use."""
    global FACTORY_REGISTRY
    FACTORY_REGISTRY = _fresh_registry()

    logger.info("worker: starting bootstrap")
    validate_environment()
    logger.info("worker: configuration validated")

    session_factory = _build_worker_session_factory()
    logger.info("worker: database session factory initialized")

    import_task_modules()

    register_factories(session_factory)
    validate_factory_registry()

    logger.info("worker: ready")


@worker_process_init.connect
def _on_worker_process_init(**_kwargs) -> None:  # pragma: no cover - exercised via a real worker process only
    """Fires exactly once per forked worker process (never per-task, never per-Beat-tick) — the
    correct place to create this process's own DB engine/connections, since an asyncio engine
    created before a prefork fork is unsafe to share across it."""
    bootstrap_worker()

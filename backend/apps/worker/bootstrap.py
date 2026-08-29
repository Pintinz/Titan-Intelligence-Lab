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
from sqlalchemy.pool import NullPool
from celery.signals import worker_process_init

from apps.api.composition import (
    build_calibration_fitting_service,
    build_calibration_validation_service,
    build_engine,
    build_health_intelligence_engine,
    build_provider_management_service,
    build_scheduled_news_sync_service,
    build_scheduled_prediction_generation_orchestrator,
    build_scheduled_retraining_orchestrator,
    build_scheduled_team_statistics_sync_orchestrator,
    build_sync_orchestrator,
    get_redis_client,
    get_redis_lock,
    get_redis_sync_cache,
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
                "ingestion.sync_team_statistics", "ingestion.sync_players_for_competition",
            ),
        ),
        "admin_context": FactoryRecord(
            name="admin_context", module="modules.admin.infrastructure.celery.tasks",
            service="(ProviderManagementService, HealthIntelligenceEngine)",
            task_names=("admin.check_all_provider_health",),
        ),
        "retraining_orchestrator": FactoryRecord(
            name="retraining_orchestrator", module="modules.predictions.infrastructure.celery.tasks",
            service="ScheduledRetrainingOrchestrator",
            task_names=("predictions.check_scheduled_retraining", "predictions.repair_broken_champions"),
        ),
        "prediction_generation_orchestrator": FactoryRecord(
            name="prediction_generation_orchestrator", module="modules.predictions.infrastructure.celery.tasks",
            service="ScheduledPredictionGenerationOrchestrator",
            task_names=("predictions.check_scheduled_prediction_generation",),
        ),
        "team_statistics_sync_orchestrator": FactoryRecord(
            name="team_statistics_sync_orchestrator", module="modules.ingestion.infrastructure.celery.tasks",
            service="ScheduledTeamStatisticsSyncOrchestrator",
            task_names=("ingestion.check_scheduled_team_statistics_sync",),
        ),
        "calibration_service": FactoryRecord(
            name="calibration_service", module="modules.predictions.infrastructure.celery.tasks",
            service="CalibrationFittingService", task_names=("predictions.check_scheduled_calibration",),
        ),
        "calibration_validation_service": FactoryRecord(
            name="calibration_validation_service", module="modules.predictions.infrastructure.celery.tasks",
            service="CalibrationValidationService",
            task_names=("predictions.check_scheduled_calibration_validation",),
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


def _fresh_worker_redis_client():
    """`apps.api.composition.get_redis_client()` is `@lru_cache`'d for FastAPI's single, long-lived
    event loop — the same hazard `_build_worker_session_factory()` documents for the DB engine, but
    for the async Redis client `SyncOrchestrator`'s lock/cache and `FeatureStoreService`'s online
    backend both depend on. Left as-is, the worker's first task would build one Redis client bound
    to that task's `asyncio.run()` loop and every later task (different loop) would keep reusing it
    from the process-wide cache, surfacing as `RuntimeError: Event loop is closed` on some later
    Redis command.

    `get_redis_lock()` and `get_redis_sync_cache()` are ALSO independently `@lru_cache`'d, each
    wrapping whatever `get_redis_client()` returned the first time either was called — clearing
    only `get_redis_client`'s cache is not enough, since those two would keep returning their own
    stale, already-memoized wrapper around the very first task's (long since closed) client rather
    than ever re-reading the fresh one. All three must be cleared together so the next call to any
    of them rebuilds fresh around whatever `get_redis_client()` returns this time.

    The caller must close the returned client (via the `_worker_redis_client` tag, mirroring
    `_worker_session`) before the loop closes."""
    get_redis_client.cache_clear()
    get_redis_lock.cache_clear()
    get_redis_sync_cache.cache_clear()
    return get_redis_client()


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
    nothing ever explicitly called commit()" gap without touching any task or service code.

    `poolclass=NullPool`: every task body runs its own fresh `asyncio.run()` event loop
    (`modules/ingestion/infrastructure/celery/tasks.py`'s `_run_summary(asyncio.run(_do()))`
    pattern), but this engine is built once at `worker_process_init`, outside any of them. The
    default pool hands out a DBAPI connection created inside one task's loop to the next task's
    new loop, and that connection's driver-level callbacks are bound to the loop that's already
    closed by then — surfacing as `RuntimeError: Event loop is closed`. NullPool opens a fresh
    connection per checkout and closes it on return, so no connection ever crosses a loop boundary."""
    engine = build_engine(poolclass=NullPool).execution_options(isolation_level="AUTOCOMMIT")
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
    """Wires all 6 production factories to real, composed application services — one fresh
    session per task invocation (never a shared mutable session, never the FastAPI request-scoped
    one), built via the existing `apps.api.composition` builders. No task-module code changes."""
    from modules.admin.infrastructure.celery.tasks import set_admin_context_factory
    from modules.ingestion.infrastructure.celery.tasks import (
        set_orchestrator_factory,
        set_team_statistics_sync_orchestrator_factory,
    )
    from modules.intelligence.infrastructure.celery.tasks import set_scheduled_news_sync_service_factory
    from modules.predictions.infrastructure.celery.tasks import (
        set_calibration_service_factory,
        set_calibration_validation_service_factory,
        set_prediction_generation_orchestrator_factory,
        set_retraining_orchestrator_factory,
    )

    # Milestone 24 §3/1(b): each service is tagged with the session it was built from, on a
    # `_worker_session` attribute the shared `_get_*()` context managers in each task module look
    # for and close on the way out. Doesn't change the factory Callable contracts (still `Callable[
    # [], Awaitable[Service]]`), so nothing else — including every existing test's `set_*_factory`
    # fixture, which returns a bare fake service with no such attribute — needs to change.
    # `_worker_redis_client` is the same tag-and-close pattern applied to `_fresh_worker_redis_client()`.
    # Built BEFORE the `build_*` call in every factory below: `build_sync_orchestrator` (and
    # friends) read `get_redis_client()` synchronously while constructing their lock/cache/feature
    # store wiring, so the fresh client must already be cached by the time that call runs — building
    # it after would leave the service holding the *previous* task's (about-to-be-closed) client.
    async def orchestrator_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        orchestrator = build_sync_orchestrator(session)
        orchestrator._worker_session = session
        orchestrator._worker_redis_client = redis_client
        return orchestrator

    async def admin_context_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        service = build_provider_management_service(session)
        engine = build_health_intelligence_engine(session)
        service._worker_session = session
        service._worker_redis_client = redis_client
        return service, engine

    async def retraining_orchestrator_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        orchestrator = build_scheduled_retraining_orchestrator(session)
        orchestrator._worker_session = session
        orchestrator._worker_redis_client = redis_client
        return orchestrator

    async def prediction_generation_orchestrator_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        orchestrator = build_scheduled_prediction_generation_orchestrator(session)
        orchestrator._worker_session = session
        orchestrator._worker_redis_client = redis_client
        return orchestrator

    async def team_statistics_sync_orchestrator_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        orchestrator = build_scheduled_team_statistics_sync_orchestrator(session)
        orchestrator._worker_session = session
        orchestrator._worker_redis_client = redis_client
        return orchestrator

    async def calibration_service_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        service = build_calibration_fitting_service(session)
        service._worker_session = session
        service._worker_redis_client = redis_client
        return service

    async def calibration_validation_service_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        service = build_calibration_validation_service(session)
        service._worker_session = session
        service._worker_redis_client = redis_client
        return service

    async def scheduled_news_sync_factory():
        session = session_factory()
        redis_client = _fresh_worker_redis_client()
        service = build_scheduled_news_sync_service(session)
        service._worker_session = session
        service._worker_redis_client = redis_client
        return service

    set_orchestrator_factory(orchestrator_factory)
    FACTORY_REGISTRY["orchestrator"].registered = True

    set_admin_context_factory(admin_context_factory)
    FACTORY_REGISTRY["admin_context"].registered = True

    set_retraining_orchestrator_factory(retraining_orchestrator_factory)
    FACTORY_REGISTRY["retraining_orchestrator"].registered = True

    set_prediction_generation_orchestrator_factory(prediction_generation_orchestrator_factory)
    FACTORY_REGISTRY["prediction_generation_orchestrator"].registered = True

    set_team_statistics_sync_orchestrator_factory(team_statistics_sync_orchestrator_factory)
    FACTORY_REGISTRY["team_statistics_sync_orchestrator"].registered = True

    set_calibration_service_factory(calibration_service_factory)
    FACTORY_REGISTRY["calibration_service"].registered = True

    set_calibration_validation_service_factory(calibration_validation_service_factory)
    FACTORY_REGISTRY["calibration_validation_service"].registered = True

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

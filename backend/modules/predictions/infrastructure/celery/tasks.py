"""Celery task for Scheduled Retraining (audit fix, 2026-08-02) — the periodic "Scheduled
Retraining" job the self-learning platform brief named but that was never wired up:
`RetrainingScheduler.should_retrain()` and `AutomaticModelSelectionService` both already existed
and were already composed, but only reachable via a manual Ops Center button, never a schedule.

Same pattern as `modules.ingestion.infrastructure.celery.tasks` /
`modules.admin.infrastructure.celery.tasks`: a worker process can't share the FastAPI app's
per-request DB session, so the task builds its own orchestrator via an injected factory rather
than importing apps/api's composition module directly.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.application.calibration_fitting_service import CalibrationFittingService
from modules.predictions.application.calibration_validation_service import CalibrationValidationService
from modules.predictions.application.model_health_audit_service import REPAIRABLE_STATUSES, ModelHealthAuditService
from modules.predictions.application.scheduled_prediction_generation_orchestrator import (
    ScheduledPredictionGenerationOrchestrator,
)
from modules.predictions.application.scheduled_retraining_orchestrator import ScheduledRetrainingOrchestrator

logger = logging.getLogger("titaniq.predictions.tasks")


def _logged(task_name: str):
    """See `modules.ingestion.infrastructure.celery.tasks._logged` — identical structured
    start/success/failure logging, duplicated per-module rather than centralized (same convention
    already used for `_RETRY_KWARGS` in every one of these `celery/tasks.py` files). Especially
    worth having here: retraining/calibration are high-stakes ML operations that previously left
    no log trail at all if they failed silently past their retry budget."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            task_id = getattr(self.request, "id", None)
            logger.info("celery_task.started", extra={"task": task_name, "task_id": task_id})
            try:
                result = fn(self, *args, **kwargs)
            except Exception:
                logger.error("celery_task.failed", extra={"task": task_name, "task_id": task_id}, exc_info=True)
                raise
            logger.info("celery_task.succeeded", extra={"task": task_name, "task_id": task_id})
            return result

        return wrapper

    return decorator


_RetrainingOrchestratorFactory = Callable[[], Awaitable[ScheduledRetrainingOrchestrator]]
_retraining_orchestrator_factory: _RetrainingOrchestratorFactory | None = None


def set_retraining_orchestrator_factory(factory: _RetrainingOrchestratorFactory) -> None:
    global _retraining_orchestrator_factory
    _retraining_orchestrator_factory = factory


@asynccontextmanager
async def _get_retraining_orchestrator() -> AsyncIterator[ScheduledRetrainingOrchestrator]:
    """Milestone 24 §3/1(b): closes the worker session tagged onto the orchestrator by the
    production factory (`bootstrap.py`'s `_worker_session` attribute) before this task's
    `asyncio.run()` call tears down its event loop — see
    `modules.ingestion.infrastructure.celery.tasks._get_orchestrator` for the full rationale,
    identical here."""
    if _retraining_orchestrator_factory is None:
        raise RuntimeError(
            "retraining orchestrator factory not configured — call set_retraining_orchestrator_factory() at worker startup"
        )
    orchestrator = await _retraining_orchestrator_factory()
    try:
        yield orchestrator
    finally:
        session = getattr(orchestrator, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(orchestrator, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


_CalibrationServiceFactory = Callable[[], Awaitable[CalibrationFittingService]]
_calibration_service_factory: _CalibrationServiceFactory | None = None


def set_calibration_service_factory(factory: _CalibrationServiceFactory) -> None:
    global _calibration_service_factory
    _calibration_service_factory = factory


@asynccontextmanager
async def _get_calibration_service() -> AsyncIterator[CalibrationFittingService]:
    """Milestone 24 §3/1(b): same session-closing rationale as `_get_retraining_orchestrator` above."""
    if _calibration_service_factory is None:
        raise RuntimeError(
            "calibration service factory not configured — call set_calibration_service_factory() at worker startup"
        )
    service = await _calibration_service_factory()
    try:
        yield service
    finally:
        session = getattr(service, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(service, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


_PredictionGenerationOrchestratorFactory = Callable[[], Awaitable[ScheduledPredictionGenerationOrchestrator]]
_prediction_generation_orchestrator_factory: _PredictionGenerationOrchestratorFactory | None = None


def set_prediction_generation_orchestrator_factory(factory: _PredictionGenerationOrchestratorFactory) -> None:
    global _prediction_generation_orchestrator_factory
    _prediction_generation_orchestrator_factory = factory


@asynccontextmanager
async def _get_prediction_generation_orchestrator() -> AsyncIterator[ScheduledPredictionGenerationOrchestrator]:
    """Milestone 24 §3/1(b): same session-closing rationale as `_get_retraining_orchestrator` above."""
    if _prediction_generation_orchestrator_factory is None:
        raise RuntimeError(
            "prediction generation orchestrator factory not configured — call "
            "set_prediction_generation_orchestrator_factory() at worker startup"
        )
    orchestrator = await _prediction_generation_orchestrator_factory()
    try:
        yield orchestrator
    finally:
        session = getattr(orchestrator, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(orchestrator, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


_CalibrationValidationServiceFactory = Callable[[], Awaitable[CalibrationValidationService]]
_calibration_validation_service_factory: _CalibrationValidationServiceFactory | None = None


def set_calibration_validation_service_factory(factory: _CalibrationValidationServiceFactory) -> None:
    global _calibration_validation_service_factory
    _calibration_validation_service_factory = factory


@asynccontextmanager
async def _get_calibration_validation_service() -> AsyncIterator[CalibrationValidationService]:
    """Phase 3 audit fix: same session-closing rationale as `_get_calibration_service` above —
    `CalibrationValidationService` (sklearn `CalibratedClassifierCV`-based Platt/isotonic
    comparison) previously had zero scheduled callers, reachable only via a manual script."""
    if _calibration_validation_service_factory is None:
        raise RuntimeError(
            "calibration validation service factory not configured — call "
            "set_calibration_validation_service_factory() at worker startup"
        )
    service = await _calibration_validation_service_factory()
    try:
        yield service
    finally:
        session = getattr(service, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(service, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}

# Phase 5 (Celery Worker+Beat verification, 2026-08-25) — production runs `titaniq-worker` with
# `--pool=solo` (fixed a real prefork-pool OOM: forking duplicates the already-loaded
# sklearn/shap/xgboost import weight per child). Celery's own `task_time_limit`/`soft_time_limit`
# (`celery_app.py`'s `task_time_limit=600`) are silently NOT ENFORCED under the solo pool —
# confirmed against the installed celery 5.6.3's `celery.concurrency.solo.TaskPool._get_info()`,
# whose `'timeouts': ()` is exactly the field Celery's own worker code checks before ever applying
# either limit. A hung task under solo blocks every other scheduled task indefinitely (single-
# threaded, non-preemptive) with no automatic recovery — worse for these three tasks than for the
# cheap, fast ingestion ones, since they're the heaviest work this worker does (dataset build,
# multi-algorithm training, sklearn `CalibratedClassifierCV` comparison).
#
# `asyncio.wait_for()` below is an application-level bound that works regardless of pool type —
# but it can only ever preempt at an `await` suspension point. It reliably bounds an I/O-bound
# hang (a stuck DB query, a provider API call that never returns) but CANNOT interrupt a single
# long-running *synchronous* call within one un-awaited stretch (e.g. one sklearn `.fit()` call,
# which is synchronous CPU-bound code with no async API) — an honest, documented limitation, not a
# complete guarantee, same "real but partial mitigation, not fabricated as total" posture this
# codebase already uses elsewhere (e.g. `calibration_fitting_service.py`'s own v1 scope note).
# Values are generous relative to each task's own 6-hour (retraining/validation) or 1-hour
# (calibration fitting) Beat cadence — see `beat_schedule.py` — so a legitimately slow-but-healthy
# run is never mistaken for a hang, while a genuinely stuck run still recovers well before the
# next scheduled tick.
_RETRAINING_TASK_TIMEOUT_SECONDS = 1800  # heavy: dataset build + multi-algorithm training
_CALIBRATION_FITTING_TASK_TIMEOUT_SECONDS = 300  # cheap: reads outcome history, fits one logistic regression
_CALIBRATION_VALIDATION_TASK_TIMEOUT_SECONDS = 1800  # heavy: comparably costly to a retrain
# Redis/Celery pipeline verification (2026-08-26) — real defect already fixed once in this exact
# codebase (see ingestion/beat_schedule.py's LIVE_FIXTURES_LOCK_TTL_SECONDS docstring for the full
# incident): a Beat interval shorter than a task's own worst-case runtime causes queued duplicates
# to pile up and redundantly re-run. Applying that lesson up front here rather than rediscovering
# it live — 900s comfortably bounds a sweep over a week's worth of upcoming fixtures × PRODUCTION
# markets (each generation is a feature lookup + inference, not a network-bound provider call, so
# this is generously long relative to the real expected cost), and `beat_schedule.py`'s own
# SCHEDULED_PREDICTION_GENERATION_INTERVAL_SECONDS (1 hour) leaves 4x headroom over it.
_PREDICTION_GENERATION_TASK_TIMEOUT_SECONDS = 900
# On-demand only (see repair_broken_champions_task) — a full sweep can cover every PRODUCTION
# market unconditionally (no staleness gate narrows it, unlike the regular retraining task above),
# so it's sized generously rather than against a Beat cadence it doesn't have.
_REPAIR_TASK_TIMEOUT_SECONDS = 3600


@celery_app.task(name="predictions.check_scheduled_prediction_generation", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_prediction_generation")
def check_scheduled_prediction_generation_task(self, now_iso: str | None = None) -> dict:
    """Real gap found live (2026-08-26) — `ingestion.sync_upcoming_fixtures` already syncs real
    upcoming fixtures on its own schedule, but nothing ever generated predictions for them
    automatically; every prediction that ever existed was manually/admin-triggered. Generates (or
    refreshes) a prediction, for every PRODUCTION market, for every fixture of that market's sport
    due within the orchestrator's lookahead window — the automatic half of prediction generation,
    manual/admin triggering being the other half (same shape as retraining above)."""

    async def _do() -> dict:
        async with _get_prediction_generation_orchestrator() as orchestrator:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(
                orchestrator.run(now), timeout=_PREDICTION_GENERATION_TASK_TIMEOUT_SECONDS
            )
            return {
                "pairs_checked": len(outcomes),
                "published": sum(1 for o in outcomes if o.status == "published"),
                "draft": sum(1 for o in outcomes if o.status == "draft"),
                "skipped": sum(1 for o in outcomes if o.status == "skipped"),
                "results": [
                    {
                        "fixture_id": o.fixture_id, "market_key": o.market_key, "status": o.status,
                        "reason": o.reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())


@celery_app.task(name="predictions.check_scheduled_retraining", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_retraining")
def check_scheduled_retraining_task(self, now_iso: str | None = None) -> dict:
    """Runs the same drift/staleness check the Ops Center's manual "check retraining" button
    already performs, for every PRODUCTION market, and trains + registers a Challenger wherever
    it says yes — the automatic half of retraining, manual triggering being the other half."""

    async def _do() -> dict:
        async with _get_retraining_orchestrator() as orchestrator:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(orchestrator.run(now), timeout=_RETRAINING_TASK_TIMEOUT_SECONDS)
            return {
                "markets_checked": len(outcomes),
                "retrained": sum(1 for o in outcomes if o.challenger is not None),
                "skipped": sum(1 for o in outcomes if o.should_retrain and o.challenger is None),
                "results": [
                    {
                        "market_key": o.market_key,
                        "should_retrain": o.should_retrain,
                        "reason": o.reason,
                        "challenger_model_key": o.challenger.model_key if o.challenger else None,
                        "challenger_version": o.challenger.version if o.challenger else None,
                        "skipped_reason": o.skipped_reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())


@celery_app.task(name="predictions.repair_broken_champions", bind=True, **_RETRY_KWARGS)
@_logged("predictions.repair_broken_champions")
def repair_broken_champions_task(self, now_iso: str | None = None) -> dict:
    """On-demand only — not on Beat's schedule. Real production incident, 2026-08-29:
    `GET /api/v1/admin/system/model-health` found 40 of 53 PRODUCTION markets' registered
    Champions pointed at artifacts that were never actually durable. Audits every PRODUCTION
    market fresh (never trusts a prior run's result), then repairs only what's still actually
    broken via `ScheduledRetrainingOrchestrator.repair_broken_champion` — already-healthy markets
    are never touched, so a retry after a partial run or a timeout is safe and cheap, not a
    wasteful full re-run."""

    async def _do() -> dict:
        async with _get_retraining_orchestrator() as orchestrator:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            audit_service = ModelHealthAuditService(
                markets=orchestrator.markets, models=orchestrator.models,
                artifact_store=orchestrator.model_selection.artifact_store,
            )
            entries = await audit_service.audit_all_production_markets()
            broken = [e for e in entries if e.status in REPAIRABLE_STATUSES]

            results = []
            for entry in broken:
                try:
                    outcome = await orchestrator.repair_broken_champion(entry.market, now)
                except Exception as exc:  # noqa: BLE001 — one market's failure must never stop the batch
                    results.append(
                        {"market_key": entry.market.market_key, "was_status": entry.status, "repaired": False, "error": str(exc)}
                    )
                    continue
                results.append(
                    {
                        "market_key": entry.market.market_key,
                        "was_status": entry.status,
                        "repaired": outcome.skipped_reason is None,
                        "skipped_reason": outcome.skipped_reason,
                        "new_champion_model_key": (
                            outcome.challenger.model_key if outcome.skipped_reason is None and outcome.challenger else None
                        ),
                    }
                )

            return {
                "total_production_markets": len(entries),
                "already_healthy": sum(1 for e in entries if e.status == "HEALTHY"),
                "attempted_repairs": len(broken),
                "repaired": sum(1 for r in results if r["repaired"]),
                "failed": sum(1 for r in results if not r["repaired"]),
                "results": results,
            }

    return asyncio.run(asyncio.wait_for(_do(), timeout=_REPAIR_TASK_TIMEOUT_SECONDS))


@celery_app.task(name="predictions.check_scheduled_calibration", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_calibration")
def check_scheduled_calibration_task(self, now_iso: str | None = None) -> dict:
    """Audit fix (2026-08-02) — `CalibratorPort.fit()` had zero real call sites anywhere, so every
    "calibrated" probability was actually just the unfitted identity transform. (Re)fits each
    PRODUCTION market's Champion against its real outcome history, for every market with enough
    accumulated samples."""

    async def _do() -> dict:
        async with _get_calibration_service() as service:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(
                service.fit_all_production_markets(now), timeout=_CALIBRATION_FITTING_TASK_TIMEOUT_SECONDS
            )
            return {
                "markets_checked": len(outcomes),
                "fitted": sum(1 for o in outcomes if o.fitted),
                "skipped": sum(1 for o in outcomes if not o.fitted),
                "results": [
                    {
                        "market_key": o.market_key,
                        "model_id": str(o.model_id) if o.model_id else None,
                        "sample_count": o.sample_count,
                        "fitted": o.fitted,
                        "reason": o.reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())


@celery_app.task(name="predictions.check_scheduled_calibration_validation", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_calibration_validation")
def check_scheduled_calibration_validation_task(self, now_iso: str | None = None) -> dict:
    """Phase 3 audit fix — `CalibrationValidationService` (real sklearn `CalibratedClassifierCV`
    Platt/isotonic comparison against every PRODUCTION market's Champion, persisting a
    `CalibrationReport` per candidate and registering a new CHALLENGER on a genuine win) existed
    since Phase 3 but was reachable only via a manual script, never a schedule. Never auto-promotes
    — a win only registers a CHALLENGER for the existing human `promote_to_champion` review, same
    posture as every other automated retraining path in this codebase."""

    async def _do() -> dict:
        async with _get_calibration_validation_service() as service:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(
                service.validate_all_production_markets(now), timeout=_CALIBRATION_VALIDATION_TASK_TIMEOUT_SECONDS
            )
            return {
                "markets_checked": len(outcomes),
                "validated": sum(1 for o in outcomes if o.validated),
                "skipped": sum(1 for o in outcomes if not o.validated),
                "results": [
                    {
                        "market_key": o.market_key,
                        "validated": o.validated,
                        "winner": o.result.winner.value if o.result else None,
                        "decision_reason": o.result.decision_reason if o.result else None,
                        "promoted_model_id": (
                            str(o.result.promoted_model_id) if o.result and o.result.promoted_model_id else None
                        ),
                        "reason": o.reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())

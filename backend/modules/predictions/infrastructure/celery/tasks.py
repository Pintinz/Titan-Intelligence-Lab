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
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.application.calibration_fitting_service import CalibrationFittingService
from modules.predictions.application.scheduled_retraining_orchestrator import ScheduledRetrainingOrchestrator

_RetrainingOrchestratorFactory = Callable[[], Awaitable[ScheduledRetrainingOrchestrator]]
_retraining_orchestrator_factory: _RetrainingOrchestratorFactory | None = None


def set_retraining_orchestrator_factory(factory: _RetrainingOrchestratorFactory) -> None:
    global _retraining_orchestrator_factory
    _retraining_orchestrator_factory = factory


async def _get_retraining_orchestrator() -> ScheduledRetrainingOrchestrator:
    if _retraining_orchestrator_factory is None:
        raise RuntimeError(
            "retraining orchestrator factory not configured — call set_retraining_orchestrator_factory() at worker startup"
        )
    return await _retraining_orchestrator_factory()


_CalibrationServiceFactory = Callable[[], Awaitable[CalibrationFittingService]]
_calibration_service_factory: _CalibrationServiceFactory | None = None


def set_calibration_service_factory(factory: _CalibrationServiceFactory) -> None:
    global _calibration_service_factory
    _calibration_service_factory = factory


async def _get_calibration_service() -> CalibrationFittingService:
    if _calibration_service_factory is None:
        raise RuntimeError(
            "calibration service factory not configured — call set_calibration_service_factory() at worker startup"
        )
    return await _calibration_service_factory()


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}


@celery_app.task(name="predictions.check_scheduled_retraining", bind=True, queue="default", **_RETRY_KWARGS)
def check_scheduled_retraining_task(self, now_iso: str | None = None) -> dict:
    """Runs the same drift/staleness check the Ops Center's manual "check retraining" button
    already performs, for every PRODUCTION market, and trains + registers a Challenger wherever
    it says yes — the automatic half of retraining, manual triggering being the other half."""

    async def _do() -> dict:
        orchestrator = await _get_retraining_orchestrator()
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
        outcomes = await orchestrator.run(now)
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


@celery_app.task(name="predictions.check_scheduled_calibration", bind=True, queue="default", **_RETRY_KWARGS)
def check_scheduled_calibration_task(self, now_iso: str | None = None) -> dict:
    """Audit fix (2026-08-02) — `CalibratorPort.fit()` had zero real call sites anywhere, so every
    "calibrated" probability was actually just the unfitted identity transform. (Re)fits each
    PRODUCTION market's Champion against its real outcome history, for every market with enough
    accumulated samples."""

    async def _do() -> dict:
        service = await _get_calibration_service()
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
        outcomes = await service.fit_all_production_markets(now)
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

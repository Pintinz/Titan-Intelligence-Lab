"""Milestone 10 — the Celery Beat entry point for scheduled news ingestion.

Same factory/dependency-injection architecture as `modules.ingestion.infrastructure.celery.tasks`
and `modules.predictions.infrastructure.celery.tasks`: a worker process can't share the FastAPI
app's per-request DB session, so this task builds its own `ScheduledNewsSyncService` via an
injected factory rather than importing `apps.api.composition` directly. Imports the *shared*
`celery_app` instance from `modules.ingestion.infrastructure.celery.celery_app` — established
cross-module precedent (`modules.predictions.infrastructure.celery.tasks` already does exactly
this) — the Celery application object is shared infrastructure, not a domain/application-layer
import that would violate the "modules.intelligence never imports modules.ingestion" boundary.

``sync_scheduled_news_task`` deliberately has NO ``trigger`` parameter at all — unlike every other
task in this codebase (which take a resolvable ``now_iso`` but never a caller-suppliable trigger
either), this is the one task whose entire purpose is producing `SyncTrigger.LIVE_SCHEDULED`
provenance, so accepting a trigger argument here would let a caller spoof it. The task calls
`ScheduledNewsSyncService.run`, which hardcodes the trigger internally.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.intelligence.application.scheduled_news_sync_service import ScheduledNewsSyncService
from modules.sports.domain.value_objects import SeasonId

logger = logging.getLogger("titaniq.intelligence.tasks")


def _logged(task_name: str):
    """See `modules.ingestion.infrastructure.celery.tasks._logged` — identical structured
    start/success/failure logging, duplicated per-module per this codebase's existing
    `_RETRY_KWARGS` convention."""

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


_ScheduledNewsSyncServiceFactory = Callable[[], Awaitable[ScheduledNewsSyncService]]
_scheduled_news_sync_service_factory: _ScheduledNewsSyncServiceFactory | None = None


def set_scheduled_news_sync_service_factory(factory: _ScheduledNewsSyncServiceFactory) -> None:
    global _scheduled_news_sync_service_factory
    _scheduled_news_sync_service_factory = factory


@asynccontextmanager
async def _get_scheduled_news_sync_service() -> AsyncIterator[ScheduledNewsSyncService]:
    """Milestone 24 §3/1(b): closes the worker session tagged onto the service by the production
    factory (`bootstrap.py`'s `_worker_session` attribute) before this task's `asyncio.run()` call
    tears down its event loop — see `modules.ingestion.infrastructure.celery.tasks._get_orchestrator`
    for the full rationale, identical here."""
    if _scheduled_news_sync_service_factory is None:
        raise RuntimeError(
            "scheduled news sync service factory not configured — "
            "call set_scheduled_news_sync_service_factory() at worker startup"
        )
    service = await _scheduled_news_sync_service_factory()
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


def _resolve_now(now_iso: str | None) -> datetime:
    return datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)


def _summary_dict(summary) -> dict:
    result = asdict(summary)
    result["started_at"] = summary.started_at.isoformat()
    result["completed_at"] = summary.completed_at.isoformat() if summary.completed_at else None
    return result


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}


@celery_app.task(name="intelligence.sync_scheduled_news", bind=True, **_RETRY_KWARGS)
@_logged("intelligence.sync_scheduled_news")
def sync_scheduled_news_task(self, sport_code: str, season_id_str: str, now_iso: str | None = None) -> dict:
    async def _do() -> dict:
        async with _get_scheduled_news_sync_service() as service:
            summary = await service.run(sport_code, SeasonId(UUID(season_id_str)), _resolve_now(now_iso))
            return _summary_dict(summary)

    return asyncio.run(_do())

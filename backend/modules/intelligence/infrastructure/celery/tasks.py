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
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.intelligence.application.scheduled_news_sync_service import ScheduledNewsSyncService
from modules.sports.domain.value_objects import SeasonId

_ScheduledNewsSyncServiceFactory = Callable[[], Awaitable[ScheduledNewsSyncService]]
_scheduled_news_sync_service_factory: _ScheduledNewsSyncServiceFactory | None = None


def set_scheduled_news_sync_service_factory(factory: _ScheduledNewsSyncServiceFactory) -> None:
    global _scheduled_news_sync_service_factory
    _scheduled_news_sync_service_factory = factory


async def _get_scheduled_news_sync_service() -> ScheduledNewsSyncService:
    if _scheduled_news_sync_service_factory is None:
        raise RuntimeError(
            "scheduled news sync service factory not configured — "
            "call set_scheduled_news_sync_service_factory() at worker startup"
        )
    return await _scheduled_news_sync_service_factory()


def _resolve_now(now_iso: str | None) -> datetime:
    return datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)


def _summary_dict(summary) -> dict:
    result = asdict(summary)
    result["started_at"] = summary.started_at.isoformat()
    result["completed_at"] = summary.completed_at.isoformat() if summary.completed_at else None
    return result


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}


@celery_app.task(name="intelligence.sync_scheduled_news", bind=True, queue="default", **_RETRY_KWARGS)
def sync_scheduled_news_task(self, sport_code: str, season_id_str: str, now_iso: str | None = None) -> dict:
    async def _do() -> dict:
        service = await _get_scheduled_news_sync_service()
        summary = await service.run(sport_code, SeasonId(UUID(season_id_str)), _resolve_now(now_iso))
        return _summary_dict(summary)

    return asyncio.run(_do())

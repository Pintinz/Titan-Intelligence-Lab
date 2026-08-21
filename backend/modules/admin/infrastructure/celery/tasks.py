"""Celery tasks for the Provider Registry (docs/admin_center.md §2, Milestone 11B) — the
periodic "Provider Health Checks" background job the brief and
`beat_schedule.PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS` both anticipated but that was never
wired up (docs/admin_center.md §2a: "Periodic scheduling of recovery probes ... needs Celery
beat, not wired until a later milestone — this is the method that job will call").

Same pattern as `modules.ingestion.infrastructure.celery.tasks`: a worker process can't share
the FastAPI app's per-request DB session, so the task builds its own service/engine pair via an
injected factory rather than importing apps/api's composition module directly.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from modules.admin.application.connection_check_service import check_provider_connection
from modules.admin.application.health_intelligence_engine import HealthIntelligenceEngine
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.domain.value_objects import ProviderStatus
from modules.ingestion.infrastructure.celery.celery_app import celery_app

logger = logging.getLogger("titaniq.admin.tasks")


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


_AdminContextFactory = Callable[[], Awaitable[tuple[ProviderManagementService, HealthIntelligenceEngine]]]
_admin_context_factory: _AdminContextFactory | None = None


def set_admin_context_factory(factory: _AdminContextFactory) -> None:
    global _admin_context_factory
    _admin_context_factory = factory


@asynccontextmanager
async def _get_admin_context() -> AsyncIterator[tuple[ProviderManagementService, HealthIntelligenceEngine]]:
    """Milestone 24 §3/1(b): closes the worker session tagged onto `service` by the production
    factory (`bootstrap.py`'s `_worker_session` attribute) before this task's `asyncio.run()` call
    tears down its event loop — see `modules.ingestion.infrastructure.celery.tasks._get_orchestrator`
    for the full rationale, identical here."""
    if _admin_context_factory is None:
        raise RuntimeError("admin context factory not configured — call set_admin_context_factory() at worker startup")
    service, engine = await _admin_context_factory()
    try:
        yield service, engine
    finally:
        session = getattr(service, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(service, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        # See modules.ingestion.infrastructure.celery.tasks._get_orchestrator for the full
        # rationale: gives the ProactorEventLoop one more iteration to run the transport-close
        # callback scheduled by aclose()/session.close() before asyncio.run() closes the loop.
        await asyncio.sleep(0)


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}


@celery_app.task(name="admin.check_all_provider_health", bind=True, **_RETRY_KWARGS)
@_logged("admin.check_all_provider_health")
def check_all_provider_health_task(self, now_iso: str | None = None) -> dict:
    """Runs the same connection test the Operations Center's "Test Connection" button does,
    for every ACTIVE provider, and records the result — the automatic half of health
    monitoring, manual testing being the other half."""

    async def _do() -> dict:
        async with _get_admin_context() as (service, engine):
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            providers = await service.providers.list_all()
            checked, skipped = 0, 0
            for provider in providers:
                if provider.status is not ProviderStatus.ACTIVE:
                    skipped += 1
                    continue
                await check_provider_connection(service, engine, provider.id, now)
                checked += 1
            return {"checked": checked, "skipped_inactive": skipped, "total_providers": len(providers)}

    return asyncio.run(_do())

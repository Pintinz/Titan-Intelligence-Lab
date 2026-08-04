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
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from modules.admin.application.connection_check_service import check_provider_connection
from modules.admin.application.health_intelligence_engine import HealthIntelligenceEngine
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.domain.value_objects import ProviderStatus
from modules.ingestion.infrastructure.celery.celery_app import celery_app

_AdminContextFactory = Callable[[], Awaitable[tuple[ProviderManagementService, HealthIntelligenceEngine]]]
_admin_context_factory: _AdminContextFactory | None = None


def set_admin_context_factory(factory: _AdminContextFactory) -> None:
    global _admin_context_factory
    _admin_context_factory = factory


async def _get_admin_context() -> tuple[ProviderManagementService, HealthIntelligenceEngine]:
    if _admin_context_factory is None:
        raise RuntimeError("admin context factory not configured — call set_admin_context_factory() at worker startup")
    return await _admin_context_factory()


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}


@celery_app.task(name="admin.check_all_provider_health", bind=True, queue="default", **_RETRY_KWARGS)
def check_all_provider_health_task(self, now_iso: str | None = None) -> dict:
    """Runs the same connection test the Operations Center's "Test Connection" button does,
    for every ACTIVE provider, and records the result — the automatic half of health
    monitoring, manual testing being the other half."""

    async def _do() -> dict:
        service, engine = await _get_admin_context()
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

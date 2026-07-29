"""Synchronization Monitoring (docs/roadmap.md Milestone 5 "Monitoring: Synchronization Status,
Provider Health, Synchronization Duration, Records Imported/Updated/Rejected, Validation
Failures, Queue Length, Redis Health, Worker Health").

Provider Health is deliberately *not* reimplemented here — it already exists in
``modules.admin.application.health_intelligence_engine.HealthIntelligenceEngine`` (Milestone 3);
this service exposes it alongside sync/queue/infra health rather than duplicating it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from modules.ingestion.domain.entities import SyncRun
from modules.ingestion.domain.value_objects import EntityKind, SyncStatus
from modules.ingestion.ports.repositories import SyncRunRepositoryPort


@dataclass(frozen=True)
class SyncRunSummary:
    run_id: str
    sport_code: str
    entity_kind: str
    scope_key: str
    status: str
    started_at: datetime
    duration_seconds: float | None
    records_fetched: int
    records_created: int
    records_updated: int
    records_rejected: int
    validation_failures: int
    error_message: str | None


def _summarize(run: SyncRun) -> SyncRunSummary:
    return SyncRunSummary(
        run_id=str(run.id), sport_code=run.sport_code, entity_kind=run.entity_kind.value, scope_key=run.scope_key,
        status=run.status.value, started_at=run.started_at, duration_seconds=run.duration_seconds,
        records_fetched=run.records_fetched, records_created=run.records_created,
        records_updated=run.records_updated, records_rejected=run.records_rejected,
        validation_failures=run.validation_failures, error_message=run.error_message,
    )


@dataclass(frozen=True)
class RedisHealthReport:
    healthy: bool
    latency_ms: float | None
    error: str | None = None


@dataclass(frozen=True)
class WorkerHealthReport:
    workers_online: int
    worker_names: tuple[str, ...]
    active_task_counts: dict[str, int]


@dataclass
class MonitoringService:
    sync_runs: SyncRunRepositoryPort

    async def sync_status(
        self, sport_code: str | None = None, entity_kind: EntityKind | None = None, limit: int = 20
    ) -> list[SyncRunSummary]:
        runs = await self.sync_runs.list_recent(sport_code, entity_kind, limit=limit)
        return [_summarize(r) for r in runs]

    async def aggregate_stats(
        self, sport_code: str | None = None, entity_kind: EntityKind | None = None, limit: int = 100
    ) -> dict[str, Any]:
        runs = await self.sync_runs.list_recent(sport_code, entity_kind, limit=limit)
        if not runs:
            return {
                "sample_size": 0, "succeeded": 0, "partial": 0, "failed": 0,
                "total_records_fetched": 0, "total_records_rejected": 0,
                "total_validation_failures": 0, "average_duration_seconds": None,
            }
        durations = [r.duration_seconds for r in runs if r.duration_seconds is not None]
        return {
            "sample_size": len(runs),
            "succeeded": sum(1 for r in runs if r.status is SyncStatus.SUCCEEDED),
            "partial": sum(1 for r in runs if r.status is SyncStatus.PARTIAL),
            "failed": sum(1 for r in runs if r.status is SyncStatus.FAILED),
            "total_records_fetched": sum(r.records_fetched for r in runs),
            "total_records_rejected": sum(r.records_rejected for r in runs),
            "total_validation_failures": sum(r.validation_failures for r in runs),
            "average_duration_seconds": round(sum(durations) / len(durations), 3) if durations else None,
        }

    async def redis_health(self, client) -> RedisHealthReport:
        start = time.monotonic()
        try:
            await client.ping()
        except Exception as exc:  # noqa: BLE001 — any transport failure means "unhealthy", not a crash
            return RedisHealthReport(healthy=False, latency_ms=None, error=str(exc))
        return RedisHealthReport(healthy=True, latency_ms=round((time.monotonic() - start) * 1000, 2))

    def queue_length(self, client, queue_name: str) -> int:
        """Celery's Redis transport stores a queue as a Redis list keyed by the queue name —
        this is a sync Redis client call (matching how Celery/kombu itself talks to Redis),
        not the async client used elsewhere in this codebase's request path."""
        return client.llen(queue_name)

    def worker_health(self, celery_app) -> WorkerHealthReport:
        inspector = celery_app.control.inspect()
        active = inspector.active() or {}
        stats = inspector.stats() or {}
        return WorkerHealthReport(
            workers_online=len(stats),
            worker_names=tuple(stats.keys()),
            active_task_counts={name: len(tasks) for name, tasks in active.items()},
        )

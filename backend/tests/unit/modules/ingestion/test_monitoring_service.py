from datetime import datetime, timezone
from uuid import uuid4

import fakeredis
import pytest

from modules.ingestion.application.monitoring_service import MonitoringService
from modules.ingestion.domain.entities import SyncRun
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId, SyncStatus, SyncTrigger

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _run(status=SyncStatus.SUCCEEDED, fetched=5, rejected=0, failures=0) -> SyncRun:
    return SyncRun(
        id=SyncRunId(uuid4()), sport_code="football", entity_kind=EntityKind.TEAM, scope_key="39",
        trigger=SyncTrigger.SCHEDULED, status=status, started_at=T0, finished_at=T0,
        records_fetched=fetched, records_created=fetched - rejected, records_rejected=rejected,
        validation_failures=failures,
    )


@pytest.fixture
def service(sync_run_repo):
    return MonitoringService(sync_runs=sync_run_repo)


@pytest.mark.asyncio
async def test_sync_status_returns_summaries(service, sync_run_repo):
    await sync_run_repo.record(_run())

    summaries = await service.sync_status(sport_code="football")

    assert len(summaries) == 1
    assert summaries[0].sport_code == "football"
    assert summaries[0].status == "succeeded"
    assert summaries[0].duration_seconds == 0.0


@pytest.mark.asyncio
async def test_aggregate_stats_empty_history(service):
    stats = await service.aggregate_stats()

    assert stats["sample_size"] == 0
    assert stats["average_duration_seconds"] is None


@pytest.mark.asyncio
async def test_aggregate_stats_counts_by_status(service, sync_run_repo):
    await sync_run_repo.record(_run(status=SyncStatus.SUCCEEDED))
    await sync_run_repo.record(_run(status=SyncStatus.PARTIAL, rejected=1, failures=1))
    await sync_run_repo.record(_run(status=SyncStatus.FAILED))

    stats = await service.aggregate_stats()

    assert stats["sample_size"] == 3
    assert stats["succeeded"] == 1
    assert stats["partial"] == 1
    assert stats["failed"] == 1
    assert stats["total_records_rejected"] == 1
    assert stats["total_validation_failures"] == 1


@pytest.mark.asyncio
async def test_redis_health_reports_healthy(service):
    client = fakeredis.FakeAsyncRedis(decode_responses=True)

    report = await service.redis_health(client)

    assert report.healthy is True
    assert report.latency_ms is not None
    assert report.error is None


@pytest.mark.asyncio
async def test_redis_health_reports_unhealthy_on_error(service):
    class BrokenClient:
        async def ping(self):
            raise ConnectionError("connection refused")

    report = await service.redis_health(BrokenClient())

    assert report.healthy is False
    assert report.latency_ms is None
    assert "connection refused" in report.error


def test_queue_length_reads_list_length(service):
    client = fakeredis.FakeRedis(decode_responses=True)
    client.rpush("default", "task-1", "task-2", "task-3")

    assert service.queue_length(client, "default") == 3


def test_queue_length_zero_for_empty_queue(service):
    client = fakeredis.FakeRedis(decode_responses=True)

    assert service.queue_length(client, "default") == 0


class _FakeInspector:
    def __init__(self, active=None, stats=None):
        self._active = active
        self._stats = stats

    def active(self):
        return self._active

    def stats(self):
        return self._stats


class _FakeControl:
    def __init__(self, inspector):
        self._inspector = inspector

    def inspect(self):
        return self._inspector


class _FakeCeleryApp:
    def __init__(self, inspector):
        self.control = _FakeControl(inspector)


def test_worker_health_with_no_workers_online(service):
    app = _FakeCeleryApp(_FakeInspector(active=None, stats=None))

    report = service.worker_health(app)

    assert report.workers_online == 0
    assert report.worker_names == ()
    assert report.active_task_counts == {}
    assert report.error is None


class _FakeControlUnreachableBroker:
    def inspect(self):
        raise ConnectionError("Error 10061 connecting to 127.0.0.1:6379.")


class _FakeCeleryAppUnreachableBroker:
    control = _FakeControlUnreachableBroker()


def test_worker_health_reports_honestly_when_broker_is_unreachable(service):
    """Post-match resolution pipeline audit (2026-08-23) — no worker deployed yet, or a network
    failure, must report an honest "0 workers online" rather than crash the whole admin
    monitoring surface with a raw connection exception."""
    report = service.worker_health(_FakeCeleryAppUnreachableBroker())

    assert report.workers_online == 0
    assert report.worker_names == ()
    assert report.active_task_counts == {}
    assert report.error == "ConnectionError"


def test_worker_health_with_workers_online(service):
    app = _FakeCeleryApp(_FakeInspector(
        active={"worker1@host": [{"id": "t1"}, {"id": "t2"}], "worker2@host": []},
        stats={"worker1@host": {}, "worker2@host": {}},
    ))

    report = service.worker_health(app)

    assert report.workers_online == 2
    assert set(report.worker_names) == {"worker1@host", "worker2@host"}
    assert report.active_task_counts["worker1@host"] == 2
    assert report.active_task_counts["worker2@host"] == 0

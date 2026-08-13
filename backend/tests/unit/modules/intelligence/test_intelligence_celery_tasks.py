from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.intelligence.application.scheduled_news_sync_service import ScheduledNewsSyncSummary
from modules.intelligence.infrastructure.celery import tasks as tasks_module
from modules.ingestion.infrastructure.celery.celery_app import celery_app

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


@dataclass
class FakeScheduledNewsSyncService:
    summary_to_return: ScheduledNewsSyncSummary
    calls: list = field(default_factory=list)

    async def run(self, sport_code, season_id, now):
        self.calls.append((sport_code, season_id, now))
        return self.summary_to_return


def _summary(**overrides) -> ScheduledNewsSyncSummary:
    defaults = dict(enabled=True, started_at=T0, completed_at=T0)
    defaults.update(overrides)
    return ScheduledNewsSyncSummary(**defaults)


@pytest.fixture
def fake_service():
    return FakeScheduledNewsSyncService(summary_to_return=_summary())


@pytest.fixture(autouse=True)
def wire_factory(fake_service):
    async def factory():
        return fake_service

    tasks_module.set_scheduled_news_sync_service_factory(factory)
    yield
    tasks_module.set_scheduled_news_sync_service_factory(None)


def test_task_invokes_service_run_with_resolved_now(fake_service):
    season_id = str(uuid4())

    result = tasks_module.sync_scheduled_news_task.delay("football", season_id, T0.isoformat())

    assert result.get()["enabled"] is True
    assert len(fake_service.calls) == 1
    sport_code, _season_id, now = fake_service.calls[0]
    assert sport_code == "football"
    assert now == T0


def test_task_signature_never_accepts_a_trigger_argument():
    """Milestone 10 §3: the trigger must not be supplied by the task caller. The task's own
    positional/keyword signature has no `trigger` parameter at all — the only way to invoke this
    task with a caller-chosen trigger is to not have one to choose."""
    import inspect

    params = inspect.signature(tasks_module.sync_scheduled_news_task.run).parameters
    assert "trigger" not in params


def test_task_returns_the_full_summary_dict(fake_service):
    fake_service.summary_to_return = _summary(
        enabled=True, sources_attempted=2, sources_succeeded=2, articles_relevant=1, articles_sent_to_gemini=1,
    )

    result = tasks_module.sync_scheduled_news_task.delay("football", str(uuid4()), T0.isoformat())

    payload = result.get()
    assert payload["sources_attempted"] == 2
    assert payload["articles_relevant"] == 1
    assert payload["started_at"] == T0.isoformat()


def test_task_without_factory_configured_raises():
    tasks_module.set_scheduled_news_sync_service_factory(None)

    with pytest.raises(Exception, match="factory not configured"):
        tasks_module.sync_scheduled_news_task.apply(
            kwargs={"sport_code": "football", "season_id_str": str(uuid4()), "now_iso": T0.isoformat()}
        ).get()

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.application.scheduled_retraining_orchestrator import RetrainingOutcome
from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.value_objects import MarketId, ModelId, ModelStatus
from modules.predictions.infrastructure.celery import tasks as tasks_module

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


def _challenger() -> ModelDefinition:
    return ModelDefinition(
        id=ModelId(uuid4()), market_id=MarketId(uuid4()), model_key="football.both_teams_to_score.random_forest",
        version=2, algorithm="random_forest", status=ModelStatus.CHALLENGER,
    )


class FakeRetrainingOrchestrator:
    def __init__(self, outcomes=None, raise_error=None):
        self.outcomes_to_return = outcomes or []
        self.raise_error = raise_error
        self.calls = []

    async def run(self, now):
        self.calls.append(now)
        if self.raise_error:
            raise self.raise_error
        return self.outcomes_to_return


@pytest.fixture
def fake_orchestrator():
    return FakeRetrainingOrchestrator(
        outcomes=[
            RetrainingOutcome(market_key="football.both_teams_to_score", should_retrain=True, reason="dataset stale", challenger=_challenger()),
            RetrainingOutcome(market_key="basketball.moneyline", should_retrain=False, reason="no drift"),
        ]
    )


@pytest.fixture(autouse=True)
def wire_factory(fake_orchestrator):
    async def factory():
        return fake_orchestrator

    tasks_module.set_retraining_orchestrator_factory(factory)
    yield
    tasks_module.set_retraining_orchestrator_factory(None)


def test_task_summarizes_checked_retrained_and_skipped_markets(fake_orchestrator):
    result = tasks_module.check_scheduled_retraining_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["markets_checked"] == 2
    assert result["retrained"] == 1
    assert result["skipped"] == 0  # basketball.moneyline never needed retraining, not "skipped"
    assert fake_orchestrator.calls == [T0]

    bt = next(r for r in result["results"] if r["market_key"] == "football.both_teams_to_score")
    assert bt["challenger_model_key"] == "football.both_teams_to_score.random_forest"
    assert bt["challenger_version"] == 2

    bb = next(r for r in result["results"] if r["market_key"] == "basketball.moneyline")
    assert bb["should_retrain"] is False
    assert bb["challenger_model_key"] is None


def test_task_reports_a_needed_but_skipped_retrain_separately_from_no_change_needed(fake_orchestrator):
    fake_orchestrator.outcomes_to_return = [
        RetrainingOutcome(market_key="football.both_teams_to_score", should_retrain=True, reason="dataset stale", skipped_reason="too_few_samples"),
    ]

    result = tasks_module.check_scheduled_retraining_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["markets_checked"] == 1
    assert result["retrained"] == 0
    assert result["skipped"] == 1
    assert result["results"][0]["skipped_reason"] == "too_few_samples"


def test_task_defaults_now_to_current_time_when_not_supplied(fake_orchestrator):
    tasks_module.check_scheduled_retraining_task.apply(kwargs={}).get()

    assert len(fake_orchestrator.calls) == 1
    assert fake_orchestrator.calls[0].tzinfo is not None


def test_task_raises_without_a_configured_factory():
    tasks_module.set_retraining_orchestrator_factory(None)

    # autoretry_for=(Exception,) wraps the RuntimeError in a celery.exceptions.Retry when run
    # eagerly — same shape test_celery_tasks.py's own equivalent test already asserts against.
    with pytest.raises(Exception, match="factory not configured"):
        tasks_module.check_scheduled_retraining_task.apply(kwargs={"now_iso": T0.isoformat()}).get()


class _HangingRetrainingOrchestrator:
    """Simulates a stuck run (e.g. a provider call or DB query that never returns) — an I/O-bound
    hang, the case Phase 5's `asyncio.wait_for()` bound is meant to catch."""

    async def run(self, now):
        await asyncio.sleep(3600)
        return []  # pragma: no cover — unreachable, the timeout fires first


def test_task_times_out_instead_of_hanging_forever_on_a_stuck_run(monkeypatch):
    """Phase 5 (Celery Worker+Beat verification): production runs `titaniq-worker` with
    `--pool=solo`, under which Celery's own `task_time_limit` is silently not enforced (verified
    against the installed celery package's `solo.TaskPool` — its `'timeouts': ()` is the exact
    field Celery checks). A stuck run would otherwise block the single-threaded solo worker from
    processing anything else, indefinitely, with no automatic recovery. This proves the
    `asyncio.wait_for()` bound added around `orchestrator.run()` actually fires rather than just
    existing in the source — a tiny timeout stands in for the real 1800s one so the test itself
    doesn't hang."""
    monkeypatch.setattr(tasks_module, "_RETRAINING_TASK_TIMEOUT_SECONDS", 0.05)

    async def factory():
        return _HangingRetrainingOrchestrator()

    tasks_module.set_retraining_orchestrator_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.check_scheduled_retraining_task.apply(kwargs={"now_iso": T0.isoformat()}).get()
    # `asyncio.TimeoutError` is the built-in `TimeoutError` on the Python version this repo targets
    # (3.11+). autoretry_for wraps it in a celery.exceptions.Retry (possibly nested — eager mode's
    # own retry simulation can wrap a Retry in another Retry), which carries the original exception
    # on its `.exc` attribute, not `__cause__`.
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"

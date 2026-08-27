from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.application.scheduled_prediction_generation_orchestrator import GenerationOutcome
from modules.predictions.infrastructure.celery import tasks as tasks_module

T0 = datetime(2026, 8, 26, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


class FakePredictionGenerationOrchestrator:
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
    return FakePredictionGenerationOrchestrator(
        outcomes=[
            GenerationOutcome(fixture_id="fixture-1", market_key="football.match_winner", status="published"),
            GenerationOutcome(fixture_id="fixture-2", market_key="football.both_teams_to_score", status="draft"),
            GenerationOutcome(
                fixture_id="fixture-3", market_key="football.correct_score", status="skipped",
                reason="no champion model",
            ),
        ]
    )


@pytest.fixture(autouse=True)
def wire_factory(fake_orchestrator):
    async def factory():
        return fake_orchestrator

    tasks_module.set_prediction_generation_orchestrator_factory(factory)
    yield
    tasks_module.set_prediction_generation_orchestrator_factory(None)


def test_task_summarizes_published_draft_and_skipped_pairs(fake_orchestrator):
    result = tasks_module.check_scheduled_prediction_generation_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["pairs_checked"] == 3
    assert result["published"] == 1
    assert result["draft"] == 1
    assert result["skipped"] == 1
    assert fake_orchestrator.calls == [T0]

    skipped = next(r for r in result["results"] if r["status"] == "skipped")
    assert skipped["fixture_id"] == "fixture-3"
    assert skipped["reason"] == "no champion model"


def test_task_defaults_now_to_current_time_when_not_supplied(fake_orchestrator):
    tasks_module.check_scheduled_prediction_generation_task.apply(kwargs={}).get()

    assert len(fake_orchestrator.calls) == 1
    assert fake_orchestrator.calls[0].tzinfo is not None


def test_task_raises_without_a_configured_factory():
    tasks_module.set_prediction_generation_orchestrator_factory(None)

    with pytest.raises(Exception, match="factory not configured"):
        tasks_module.check_scheduled_prediction_generation_task.apply(kwargs={"now_iso": T0.isoformat()}).get()


class _HangingPredictionGenerationOrchestrator:
    """Simulates a stuck run — the case Phase 5's `asyncio.wait_for()` bound is meant to catch,
    same rationale as `test_scheduled_retraining_celery_task.py`'s equivalent."""

    async def run(self, now):
        await asyncio.sleep(3600)
        return []  # pragma: no cover — unreachable, the timeout fires first


def test_task_times_out_instead_of_hanging_forever_on_a_stuck_run(monkeypatch):
    monkeypatch.setattr(tasks_module, "_PREDICTION_GENERATION_TASK_TIMEOUT_SECONDS", 0.05)

    async def factory():
        return _HangingPredictionGenerationOrchestrator()

    tasks_module.set_prediction_generation_orchestrator_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.check_scheduled_prediction_generation_task.apply(kwargs={"now_iso": T0.isoformat()}).get()
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"

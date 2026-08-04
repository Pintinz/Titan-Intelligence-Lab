from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.application.calibration_fitting_service import CalibrationFitOutcome
from modules.predictions.domain.value_objects import ModelId
from modules.predictions.infrastructure.celery import tasks as tasks_module

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


class FakeCalibrationService:
    def __init__(self, outcomes=None, raise_error=None):
        self.outcomes_to_return = outcomes or []
        self.raise_error = raise_error
        self.calls = []

    async def fit_all_production_markets(self, now):
        self.calls.append(now)
        if self.raise_error:
            raise self.raise_error
        return self.outcomes_to_return


@pytest.fixture
def fake_service():
    return FakeCalibrationService(
        outcomes=[
            CalibrationFitOutcome(market_key="football.both_teams_to_score", model_id=ModelId(uuid4()), sample_count=40, fitted=True),
            CalibrationFitOutcome(market_key="basketball.moneyline", model_id=None, sample_count=0, fitted=False, reason="no champion model"),
        ]
    )


@pytest.fixture(autouse=True)
def wire_factory(fake_service):
    async def factory():
        return fake_service

    tasks_module.set_calibration_service_factory(factory)
    yield
    tasks_module.set_calibration_service_factory(None)


def test_task_summarizes_checked_fitted_and_skipped_markets(fake_service):
    result = tasks_module.check_scheduled_calibration_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["markets_checked"] == 2
    assert result["fitted"] == 1
    assert result["skipped"] == 1
    assert fake_service.calls == [T0]

    bt = next(r for r in result["results"] if r["market_key"] == "football.both_teams_to_score")
    assert bt["fitted"] is True
    assert bt["sample_count"] == 40
    assert bt["model_id"] is not None

    bb = next(r for r in result["results"] if r["market_key"] == "basketball.moneyline")
    assert bb["fitted"] is False
    assert bb["reason"] == "no champion model"
    assert bb["model_id"] is None


def test_task_defaults_now_to_current_time_when_not_supplied(fake_service):
    tasks_module.check_scheduled_calibration_task.apply(kwargs={}).get()

    assert len(fake_service.calls) == 1
    assert fake_service.calls[0].tzinfo is not None


def test_task_raises_without_a_configured_factory():
    tasks_module.set_calibration_service_factory(None)

    with pytest.raises(Exception, match="factory not configured"):
        tasks_module.check_scheduled_calibration_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

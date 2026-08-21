from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

from modules.admin.infrastructure.celery import tasks as admin_tasks_module  # noqa: F401 — registers admin.* tasks on celery_app
from modules.ingestion.domain.entities import SyncRun
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId, SyncStatus, SyncTrigger
from modules.ingestion.infrastructure.celery import tasks as tasks_module
from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.intelligence.infrastructure.celery import tasks as intelligence_tasks_module  # noqa: F401 — registers intelligence.* tasks
from modules.predictions.infrastructure.celery import tasks as predictions_tasks_module  # noqa: F401 — registers predictions.* tasks
from modules.sports.domain.value_objects import SeasonId

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


class FakeOrchestrator:
    def __init__(self, run_to_return=None, raise_error=None):
        self.run_to_return = run_to_return
        self.raise_error = raise_error
        self.calls = []

    async def sync_countries(self, sport_code, now):
        self.calls.append(("sync_countries", sport_code))
        return self._respond()

    async def sync_teams(self, sport_code, competition_ref, now):
        self.calls.append(("sync_teams", sport_code, competition_ref))
        return self._respond()

    async def sync_fixtures(self, sport_code, competition_ref, season_label, season_id, now):
        self.calls.append(("sync_fixtures", sport_code, competition_ref, season_label, season_id))
        return self._respond()

    async def sync_live_fixtures(self, sport_code, competition_ref, season_label, season_id, now):
        self.calls.append(("sync_live_fixtures", sport_code, competition_ref, season_label, season_id))
        return self._respond()

    async def sync_standings(self, sport_code, competition_ref, season_label, season_id, now):
        self.calls.append(("sync_standings", sport_code, competition_ref, season_label, season_id))
        return self._respond()

    async def sync_upcoming_fixtures(self, sport_code, competition_id, season_label, season_id, now):
        self.calls.append(("sync_upcoming_fixtures", sport_code, competition_id, season_label, season_id))
        return self._respond()

    async def sync_completed_fixtures(self, sport_code, competition_id, season_label, season_id, now):
        self.calls.append(("sync_completed_fixtures", sport_code, competition_id, season_label, season_id))
        return self._respond()

    async def sync_standings_alt(self, sport_code, competition_id, season_label, season_id, now):
        self.calls.append(("sync_standings_alt", sport_code, competition_id, season_label, season_id))
        return self._respond()

    async def sync_odds_for_fixture(self, sport_code, fixture_ref, fixture_id, now):
        self.calls.append(("sync_odds_for_fixture", sport_code, fixture_ref, fixture_id))
        return self._respond()

    async def sync_team_statistics_for_fixture(self, sport_code, fixture_ref, fixture_id, now):
        self.calls.append(("sync_team_statistics_for_fixture", sport_code, fixture_ref, fixture_id))
        return self._respond()

    def _respond(self):
        if self.raise_error:
            raise self.raise_error
        return self.run_to_return


def _run(status=SyncStatus.SUCCEEDED) -> SyncRun:
    return SyncRun(
        id=SyncRunId(uuid4()), sport_code="football", entity_kind=EntityKind.TEAM, scope_key="39",
        trigger=SyncTrigger.SCHEDULED, status=status, started_at=T0, finished_at=T0,
        records_fetched=2, records_created=2,
    )


@pytest.fixture
def fake_orchestrator():
    return FakeOrchestrator(run_to_return=_run())


@pytest.fixture(autouse=True)
def wire_factory(fake_orchestrator):
    async def factory():
        return fake_orchestrator

    tasks_module.set_orchestrator_factory(factory)
    yield
    tasks_module.set_orchestrator_factory(None)


def test_sync_teams_task_returns_summary(fake_orchestrator):
    result = tasks_module.sync_teams_task.delay("football", "39", T0.isoformat())

    summary = result.get()
    assert summary["status"] == "succeeded"
    assert summary["records_fetched"] == 2
    assert fake_orchestrator.calls == [("sync_teams", "football", "39")]


def test_sync_countries_task_returns_none_when_skipped(fake_orchestrator):
    fake_orchestrator.run_to_return = None

    result = tasks_module.sync_countries_task.delay("football", T0.isoformat())

    assert result.get() is None


def test_sync_fixtures_task_parses_season_id(fake_orchestrator):
    season_id = SeasonId(uuid4())

    tasks_module.sync_fixtures_task.delay("football", "39", "2026", str(season_id.value), T0.isoformat()).get()

    assert fake_orchestrator.calls[0][:3] == ("sync_fixtures", "football", "39")
    assert fake_orchestrator.calls[0][4] == season_id


def test_sync_live_fixtures_task_calls_orchestrator(fake_orchestrator):
    season_id = SeasonId(uuid4())

    tasks_module.sync_live_fixtures_task.delay("football", "39", "2026", str(season_id.value), T0.isoformat()).get()

    assert fake_orchestrator.calls[0][:3] == ("sync_live_fixtures", "football", "39")
    assert fake_orchestrator.calls[0][4] == season_id


def test_sync_standings_task_calls_orchestrator(fake_orchestrator):
    season_id = SeasonId(uuid4())

    result = tasks_module.sync_standings_task.delay("football", "39", "2026", str(season_id.value), T0.isoformat())

    assert result.get()["status"] == "succeeded"
    assert fake_orchestrator.calls[0][:3] == ("sync_standings", "football", "39")


def test_sync_upcoming_fixtures_task_calls_orchestrator(fake_orchestrator):
    season_id = SeasonId(uuid4())

    result = tasks_module.sync_upcoming_fixtures_task.delay("football", "comp-1", "2026", str(season_id.value), T0.isoformat())

    assert result.get()["status"] == "succeeded"
    assert fake_orchestrator.calls[0][:3] == ("sync_upcoming_fixtures", "football", "comp-1")
    assert fake_orchestrator.calls[0][4] == season_id


def test_sync_completed_fixtures_task_calls_orchestrator(fake_orchestrator):
    season_id = SeasonId(uuid4())

    result = tasks_module.sync_completed_fixtures_task.delay("football", "comp-1", "2026", str(season_id.value), T0.isoformat())

    assert result.get()["status"] == "succeeded"
    assert fake_orchestrator.calls[0][:3] == ("sync_completed_fixtures", "football", "comp-1")
    assert fake_orchestrator.calls[0][4] == season_id


def test_sync_standings_alt_task_calls_orchestrator(fake_orchestrator):
    season_id = SeasonId(uuid4())

    result = tasks_module.sync_standings_alt_task.delay("football", "comp-1", "2026", str(season_id.value), T0.isoformat())

    assert result.get()["status"] == "succeeded"
    assert fake_orchestrator.calls[0][:3] == ("sync_standings_alt", "football", "comp-1")
    assert fake_orchestrator.calls[0][4] == season_id


def test_sync_odds_task_calls_orchestrator_with_reconstructed_provider_ref(fake_orchestrator):
    result = tasks_module.sync_odds_task.delay("football", "mock", "fx1", "fixture-id-1", T0.isoformat())

    assert result.get()["status"] == "succeeded"
    call = fake_orchestrator.calls[0]
    assert call[0] == "sync_odds_for_fixture"
    assert call[1] == "football"
    assert call[2].provider == "mock"
    assert call[2].external_id == "fx1"
    assert call[3] == "fixture-id-1"


def test_sync_team_statistics_task_calls_orchestrator_with_reconstructed_provider_ref(fake_orchestrator):
    result = tasks_module.sync_team_statistics_task.delay("football", "mock", "fx1", "fixture-id-1", T0.isoformat())

    assert result.get()["status"] == "succeeded"
    call = fake_orchestrator.calls[0]
    assert call[0] == "sync_team_statistics_for_fixture"
    assert call[1] == "football"
    assert call[2].provider == "mock"
    assert call[2].external_id == "fx1"
    assert call[3] == "fixture-id-1"


def test_no_task_routes_override_configured():
    """Milestone 24: `task_routes` previously sent ingestion.*/admin.* to "live"/"default" queues
    that no production worker invocation ever consumed (confirmed by a repo-wide search — the only
    consumer was a one-off manual `-Q celery,live,default` launch in M23), silently stranding those
    tasks forever. Removed rather than fixed-by-flag, so every task now resolves to the same
    `task_default_queue` a plain `celery worker` (no `-Q` argument — the only invocation this
    project has ever documented or scripted) already consumes."""
    assert celery_app.conf.task_routes is None


def test_every_registered_task_routes_to_the_worker_consumed_default_queue():
    """The actual proof: every real task name this project registers — spanning all 4 task
    modules, including the two protected tasks (calibration/retraining) that must remain
    "identifiable and controllable" per Milestone 24's own instructions — resolves through
    Celery's real dispatch path to `task_default_queue` (`celery`), with no per-task override left
    silently stranding anything.

    Milestone 24: a first pass at this test called `celery_app.amqp.router.route({}, name)` with
    an empty options dict and wrongly passed, because that bypasses a second layer of the same
    defect — each task's own `.queue` attribute (set directly on its `@celery_app.task(...)`
    decorator via a `queue=` kwarg). Celery's real `Task.apply_async()` merges `task.queue` into
    the routing options *before* calling the router (see `celery.app.base.Celery.send_task`), so a
    test that skips that merge is testing a scenario real dispatch never hits. This version
    replicates that merge explicitly."""
    task_names = [
        "ingestion.sync_countries", "ingestion.sync_teams", "ingestion.sync_fixtures",
        "ingestion.sync_live_fixtures", "ingestion.sync_standings", "ingestion.sync_standings_alt",
        "ingestion.sync_upcoming_fixtures", "ingestion.sync_completed_fixtures",
        "ingestion.sync_upcoming_structured_intelligence", "ingestion.sync_odds",
        "ingestion.sync_team_statistics", "admin.check_all_provider_health",
        "intelligence.sync_scheduled_news", "predictions.check_scheduled_calibration",
        "predictions.check_scheduled_calibration_validation",
        "predictions.check_scheduled_retraining",
    ]
    for name in task_names:
        task = celery_app.tasks[name]
        task_queue = getattr(task, "queue", None)
        options = {"queue": task_queue} if task_queue else {}
        queue = celery_app.amqp.router.route(options, name)["queue"]
        assert queue.name == celery_app.conf.task_default_queue, (
            f"{name} resolved to queue {queue.name!r}, expected the default-consumed queue "
            f"{celery_app.conf.task_default_queue!r}"
        )


def test_no_task_carries_its_own_queue_override():
    """The second layer of the same Milestone 24 defect: independent of `task_routes`, a task
    decorator can set `queue=...` directly, which `Task.apply_async()` merges into routing options
    ahead of `task_routes` (see the test above). Assert no registered task in this project's 4
    task modules carries one, so a future decorator can't silently reintroduce this bug."""
    task_names = [
        "ingestion.sync_countries", "ingestion.sync_teams", "ingestion.sync_fixtures",
        "ingestion.sync_live_fixtures", "ingestion.sync_standings", "ingestion.sync_standings_alt",
        "ingestion.sync_upcoming_fixtures", "ingestion.sync_completed_fixtures",
        "ingestion.sync_upcoming_structured_intelligence", "ingestion.sync_odds",
        "ingestion.sync_team_statistics", "admin.check_all_provider_health",
        "intelligence.sync_scheduled_news", "predictions.check_scheduled_calibration",
        "predictions.check_scheduled_calibration_validation",
        "predictions.check_scheduled_retraining",
    ]
    for name in task_names:
        assert getattr(celery_app.tasks[name], "queue", None) is None, (
            f"{name} still carries its own queue= override"
        )


def test_get_orchestrator_closes_worker_session_after_use():
    """Milestone 24 §3/1(b): the actual proof the connection-leak fix works, not just that
    existing tests still pass (they would either way — `FakeOrchestrator` never carries a
    `_worker_session` attribute, so this scenario is otherwise never exercised). Tags a spy
    session onto a fake orchestrator, the same way `apps/worker/bootstrap.py`'s real factories
    tag the real one, and asserts `_get_orchestrator`'s context manager closes it on exit."""

    class SpySession:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    orchestrator = FakeOrchestrator(run_to_return=_run())
    session = SpySession()
    orchestrator._worker_session = session

    async def factory():
        return orchestrator

    tasks_module.set_orchestrator_factory(factory)
    try:
        import asyncio

        async def _do():
            async with tasks_module._get_orchestrator() as o:
                assert session.closed is False
                return await o.sync_countries("football", T0)

        asyncio.run(_do())
    finally:
        tasks_module.set_orchestrator_factory(None)

    assert session.closed is True


def test_get_orchestrator_closes_worker_session_even_on_error():
    class SpySession:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    orchestrator = FakeOrchestrator(raise_error=RuntimeError("boom"))
    session = SpySession()
    orchestrator._worker_session = session

    async def factory():
        return orchestrator

    tasks_module.set_orchestrator_factory(factory)
    try:
        import asyncio

        async def _do():
            async with tasks_module._get_orchestrator() as o:
                return await o.sync_countries("football", T0)

        with pytest.raises(RuntimeError):
            asyncio.run(_do())
    finally:
        tasks_module.set_orchestrator_factory(None)

    assert session.closed is True


def test_task_without_factory_configured_raises():
    tasks_module.set_orchestrator_factory(None)

    with pytest.raises(Exception):
        tasks_module.sync_teams_task.delay("football", "39", T0.isoformat()).get()


def test_task_failure_handler_records_dead_letter_once_retries_exhausted():
    """Tests _on_task_failure's own logic directly rather than through Celery's eager-mode
    retry/signal pipeline — the latter's exact retry-looping behavior under `task_always_eager`
    is a Celery implementation detail this codebase shouldn't depend on for correctness."""
    from modules.ingestion.infrastructure.celery.celery_app import _on_task_failure

    class FakeRequest:
        retries = 3

    class FakeSender:
        name = "ingestion.sync_teams"
        max_retries = 3
        request = FakeRequest()

    with patch("modules.ingestion.infrastructure.celery.celery_app.record_dead_letter") as mock_record:
        _on_task_failure(
            sender=FakeSender(), task_id="abc123", exception=RuntimeError("provider down"),
            args=["football", "39"], kwargs={},
        )

    mock_record.assert_called_once()
    _, kwargs = mock_record.call_args
    assert kwargs["task_name"] == "ingestion.sync_teams"
    assert "provider down" in kwargs["error"]


def test_task_failure_handler_skips_dead_letter_when_retries_remain():
    from modules.ingestion.infrastructure.celery.celery_app import _on_task_failure

    class FakeRequest:
        retries = 1

    class FakeSender:
        name = "ingestion.sync_teams"
        max_retries = 3
        request = FakeRequest()

    with patch("modules.ingestion.infrastructure.celery.celery_app.record_dead_letter") as mock_record:
        _on_task_failure(
            sender=FakeSender(), task_id="abc123", exception=RuntimeError("transient"), args=[], kwargs={},
        )

    mock_record.assert_not_called()

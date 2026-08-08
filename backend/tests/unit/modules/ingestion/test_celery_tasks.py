from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

from modules.ingestion.domain.entities import SyncRun
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId, SyncStatus, SyncTrigger
from modules.ingestion.infrastructure.celery import tasks as tasks_module
from modules.ingestion.infrastructure.celery.celery_app import celery_app
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


def test_sync_live_fixtures_task_routes_to_live_queue():
    assert celery_app.conf.task_routes["ingestion.sync_live_fixtures"]["queue"] == "live"


def test_other_ingestion_tasks_route_to_default_queue():
    assert celery_app.conf.task_routes["ingestion.*"]["queue"] == "default"


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

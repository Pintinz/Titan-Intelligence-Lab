from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from modules.ingestion.application.scheduled_team_statistics_sync_orchestrator import (
    ScheduledTeamStatisticsSyncOrchestrator,
)
from modules.sports.domain.entities import Match, Sport, TeamStatistics
from modules.sports.domain.value_objects import EntityId, FixtureId, MatchId, ProviderRef, SportCode, SportId

T0 = datetime(2026, 8, 26, tzinfo=timezone.utc)


@dataclass
class _Fixture:
    id: FixtureId
    scheduled_at: datetime
    status: str = "completed"
    provider_refs: tuple = (ProviderRef(provider="api-sports", external_id="123"),)


@dataclass
class FakeFixtureRepository:
    by_sport: dict = field(default_factory=dict)  # sport_id -> list[_Fixture]

    async def list_by_sport(self, sport_id, *, competition_id=None, season_id=None, status=None):
        fixtures = self.by_sport.get(sport_id, [])
        if status is not None:
            fixtures = [f for f in fixtures if f.status == status]
        return fixtures


@dataclass
class FakeSportRepository:
    by_code: dict = field(default_factory=dict)  # SportCode -> Sport

    async def get_by_code(self, code):
        return self.by_code.get(code)


@dataclass
class FakeMatchRepository:
    by_fixture: dict = field(default_factory=dict)  # str(fixture_id) -> Match

    async def get_by_fixture(self, fixture_id):
        return self.by_fixture.get(str(fixture_id))


@dataclass
class FakeTeamStatisticsRepository:
    by_match: dict = field(default_factory=dict)  # str(match_id) -> list[TeamStatistics]

    async def list_by_match(self, match_id):
        return self.by_match.get(str(match_id), [])


@dataclass
class _Plugin:
    code: SportCode


@dataclass
class FakeSportPluginRegistry:
    plugins: tuple = ()

    def all(self):
        return self.plugins


@dataclass
class FakeSyncOrchestrator:
    calls: list = field(default_factory=list)
    raise_for: dict = field(default_factory=dict)  # fixture_id -> Exception
    fetched_for: dict = field(default_factory=dict)  # fixture_id -> int, default 1 (has real data)

    async def sync_team_statistics_for_fixture(self, sport_code, fixture_ref, fixture_id, now):
        self.calls.append((sport_code, fixture_ref, fixture_id))
        if fixture_id in self.raise_for:
            raise self.raise_for[fixture_id]
        return SimpleNamespace(records_fetched=self.fetched_for.get(fixture_id, 1))


def _sport(code: SportCode) -> Sport:
    return Sport(id=SportId(uuid4()), code=code, name=code.value.title())


@pytest.fixture
def sync():
    return FakeSyncOrchestrator()


@pytest.fixture
def registry_and_repos():
    football = _sport(SportCode.FOOTBALL)
    sports = FakeSportRepository(by_code={SportCode.FOOTBALL: football})
    fixtures = FakeFixtureRepository()
    matches = FakeMatchRepository()
    team_statistics = FakeTeamStatisticsRepository()
    plugins = FakeSportPluginRegistry(plugins=(_Plugin(code=SportCode.FOOTBALL),))
    return football, sports, fixtures, matches, team_statistics, plugins


def _orchestrator(sync, registry_and_repos, **overrides):
    _football, sports, fixtures, matches, team_statistics, plugins = registry_and_repos
    kwargs = dict(sync=sync, sports=sports, fixtures=fixtures, matches=matches, team_statistics=team_statistics, sport_plugins=plugins)
    kwargs.update(overrides)
    return ScheduledTeamStatisticsSyncOrchestrator(**kwargs)


def test_syncs_a_recently_completed_fixture_with_no_match_yet(sync, registry_and_repos):
    football, _sports, fixtures, _matches, _team_statistics, _plugins = registry_and_repos
    fixture = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=3))
    fixtures.by_sport[football.id] = [fixture]

    orchestrator = _orchestrator(sync, registry_and_repos)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert len(sync.calls) == 1
    assert sync.calls[0] == ("football", fixture.provider_refs[0], str(fixture.id))
    assert outcomes[0].status == "synced"


def test_reports_honestly_when_the_provider_returns_zero_records(sync, registry_and_repos):
    """Real gap found live (2026-08-26): a fixture reconciled only via a provider with no
    team-statistics endpoint (football-data.org) makes a real, non-erroring sync call that simply
    fetches nothing — this must never be reported as "synced" (implying stats now exist)."""
    football, _sports, fixtures, _matches, _team_statistics, _plugins = registry_and_repos
    fixture = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=3))
    fixtures.by_sport[football.id] = [fixture]
    sync.fetched_for[str(fixture.id)] = 0

    orchestrator = _orchestrator(sync, registry_and_repos)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert len(sync.calls) == 1
    assert outcomes[0].status == "no_data_from_provider"
    assert "no team statistics" in outcomes[0].reason


def test_skips_a_fixture_whose_match_already_has_both_sides_stats(sync, registry_and_repos):
    football, _sports, fixtures, matches, team_statistics, _plugins = registry_and_repos
    fixture = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=3))
    fixtures.by_sport[football.id] = [fixture]
    match = Match(id=MatchId(uuid4()), fixture_id=fixture.id, started_at=T0 - timedelta(hours=3), ended_at=T0 - timedelta(hours=1))
    matches.by_fixture[str(fixture.id)] = match
    team_statistics.by_match[str(match.id)] = [
        TeamStatistics(id=EntityId(uuid4()), match_id=match.id, team_id=uuid4()),
        TeamStatistics(id=EntityId(uuid4()), match_id=match.id, team_id=uuid4()),
    ]

    orchestrator = _orchestrator(sync, registry_and_repos)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert sync.calls == []
    assert outcomes[0].status == "already_present"


def test_still_syncs_when_only_one_sides_stats_are_present(sync, registry_and_repos):
    """A match with only the home team's stats recorded (the away side's provider fetch failed,
    or hasn't been picked up yet) must not be treated as complete."""
    football, _sports, fixtures, matches, team_statistics, _plugins = registry_and_repos
    fixture = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=3))
    fixtures.by_sport[football.id] = [fixture]
    match = Match(id=MatchId(uuid4()), fixture_id=fixture.id, started_at=T0 - timedelta(hours=3), ended_at=T0 - timedelta(hours=1))
    matches.by_fixture[str(fixture.id)] = match
    team_statistics.by_match[str(match.id)] = [TeamStatistics(id=EntityId(uuid4()), match_id=match.id, team_id=uuid4())]

    orchestrator = _orchestrator(sync, registry_and_repos)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert len(sync.calls) == 1
    assert outcomes[0].status == "synced"


def test_ignores_a_fixture_outside_the_lookback_window(sync, registry_and_repos):
    football, _sports, fixtures, _matches, _team_statistics, _plugins = registry_and_repos
    stale = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(days=30))
    fixtures.by_sport[football.id] = [stale]

    orchestrator = _orchestrator(sync, registry_and_repos, lookback_hours=14 * 24)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert sync.calls == []
    assert outcomes == []


def test_skips_a_fixture_with_no_provider_reference(sync, registry_and_repos):
    football, _sports, fixtures, _matches, _team_statistics, _plugins = registry_and_repos
    fixture = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=3), provider_refs=())
    fixtures.by_sport[football.id] = [fixture]

    orchestrator = _orchestrator(sync, registry_and_repos)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert sync.calls == []
    assert outcomes[0].status == "skipped"
    assert "no provider reference" in outcomes[0].reason


def test_one_fixtures_sync_failure_never_blocks_the_sweep(sync, registry_and_repos):
    football, _sports, fixtures, _matches, _team_statistics, _plugins = registry_and_repos
    failing = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=3))
    healthy = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=5))
    fixtures.by_sport[football.id] = [failing, healthy]
    sync.raise_for[str(failing.id)] = RuntimeError("provider unreachable")

    orchestrator = _orchestrator(sync, registry_and_repos)
    outcomes = asyncio.run(orchestrator.run(T0))

    by_id = {o.fixture_id: o for o in outcomes}
    assert by_id[str(failing.id)].status == "skipped"
    assert "provider unreachable" in by_id[str(failing.id)].reason
    assert by_id[str(healthy.id)].status == "synced"


def test_a_sport_the_registry_has_never_reconciled_is_skipped_not_a_failure(sync, registry_and_repos):
    _football, sports, fixtures, _matches, _team_statistics, plugins = registry_and_repos
    plugins.plugins = (_Plugin(code=SportCode.BASKETBALL),)  # never reconciled -> get_by_code returns None

    orchestrator = _orchestrator(sync, registry_and_repos)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert outcomes == []
    assert sync.calls == []

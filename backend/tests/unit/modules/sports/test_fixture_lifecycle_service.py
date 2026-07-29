from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.sports.application.fixture_lifecycle_service import (
    FixtureLifecycleService,
    UnrecognizedMatchEventError,
)
from modules.sports.domain.entities import Fixture, MatchEvent
from modules.sports.domain.value_objects import (
    FixtureId,
    FixtureStatus,
    MatchId,
    SeasonId,
    SportCode,
    TeamId,
    VenueId,
)
from modules.sports.domain.value_objects import EntityId


@dataclass
class InMemoryFixtureRepository:
    store: dict = field(default_factory=dict)

    async def get(self, fixture_id):
        return self.store.get(fixture_id)

    async def list_by_season(self, season_id):
        return [f for f in self.store.values() if f.season_id == season_id]

    async def upsert(self, fixture):
        self.store[fixture.id] = fixture
        return fixture


def _fixture() -> Fixture:
    return Fixture(
        id=FixtureId(uuid4()),
        season_id=SeasonId(uuid4()),
        home_team_id=TeamId(uuid4()),
        away_team_id=TeamId(uuid4()),
        venue_id=VenueId(uuid4()),
        scheduled_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        status=FixtureStatus.SCHEDULED,
    )


@pytest.mark.asyncio
async def test_transition_fixture_persists_the_new_status(plugin_registry):
    repo = InMemoryFixtureRepository()
    service = FixtureLifecycleService(fixtures=repo, plugins=plugin_registry)
    fixture = _fixture()

    updated = await service.transition_fixture(fixture, FixtureStatus.LIVE)

    assert updated.status is FixtureStatus.LIVE
    assert repo.store[fixture.id].status is FixtureStatus.LIVE


@pytest.mark.asyncio
async def test_transition_fixture_rejects_illegal_transition(plugin_registry):
    repo = InMemoryFixtureRepository()
    service = FixtureLifecycleService(fixtures=repo, plugins=plugin_registry)
    fixture = _fixture()

    with pytest.raises(ValueError):
        await service.transition_fixture(fixture, FixtureStatus.COMPLETED)


def test_validate_match_event_accepts_recognized_football_event(plugin_registry):
    service = FixtureLifecycleService(fixtures=InMemoryFixtureRepository(), plugins=plugin_registry)
    event = MatchEvent(id=EntityId(uuid4()), match_id=MatchId(uuid4()), period=1, event_type="goal")

    service.validate_match_event(SportCode.FOOTBALL, event)  # does not raise


def test_validate_match_event_rejects_unrecognized_event(plugin_registry):
    service = FixtureLifecycleService(fixtures=InMemoryFixtureRepository(), plugins=plugin_registry)
    event = MatchEvent(
        id=EntityId(uuid4()), match_id=MatchId(uuid4()), period=1, event_type="home_run"
    )

    with pytest.raises(UnrecognizedMatchEventError):
        service.validate_match_event(SportCode.FOOTBALL, event)

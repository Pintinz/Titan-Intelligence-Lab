from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.sports.domain.entities import Fixture, Season
from modules.sports.domain.value_objects import (
    CompetitionId,
    DateRange,
    FixtureId,
    FixtureStatus,
    SeasonId,
    SeasonStatus,
    TeamId,
    VenueId,
)


def _season(status: SeasonStatus = SeasonStatus.UPCOMING) -> Season:
    return Season(
        id=SeasonId(uuid4()),
        competition_id=CompetitionId(uuid4()),
        label="2026",
        date_range=DateRange(start=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        status=status,
    )


def _fixture(status: FixtureStatus = FixtureStatus.SCHEDULED) -> Fixture:
    return Fixture(
        id=FixtureId(uuid4()),
        season_id=SeasonId(uuid4()),
        home_team_id=TeamId(uuid4()),
        away_team_id=TeamId(uuid4()),
        venue_id=VenueId(uuid4()),
        scheduled_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        status=status,
    )


def test_season_transitions_upcoming_to_active():
    season = _season(SeasonStatus.UPCOMING)

    updated = season.transition_to(SeasonStatus.ACTIVE)

    assert updated.status is SeasonStatus.ACTIVE
    assert season.status is SeasonStatus.UPCOMING  # original untouched (immutable transition)


def test_season_cannot_skip_active_straight_to_completed_from_upcoming():
    season = _season(SeasonStatus.UPCOMING)

    with pytest.raises(ValueError):
        season.transition_to(SeasonStatus.COMPLETED)


def test_season_cannot_transition_out_of_completed():
    season = _season(SeasonStatus.COMPLETED)

    with pytest.raises(ValueError):
        season.transition_to(SeasonStatus.ACTIVE)


def test_fixture_scheduled_to_live_to_completed():
    fixture = _fixture(FixtureStatus.SCHEDULED)

    live = fixture.transition_to(FixtureStatus.LIVE)
    completed = live.transition_to(FixtureStatus.COMPLETED)

    assert completed.status is FixtureStatus.COMPLETED


def test_fixture_cannot_go_directly_from_scheduled_to_completed():
    fixture = _fixture(FixtureStatus.SCHEDULED)

    with pytest.raises(ValueError):
        fixture.transition_to(FixtureStatus.COMPLETED)


def test_fixture_cannot_transition_out_of_cancelled():
    fixture = _fixture(FixtureStatus.CANCELLED)

    with pytest.raises(ValueError):
        fixture.transition_to(FixtureStatus.LIVE)


def test_postponed_fixture_can_be_rescheduled():
    fixture = _fixture(FixtureStatus.POSTPONED)

    rescheduled = fixture.transition_to(FixtureStatus.SCHEDULED)

    assert rescheduled.status is FixtureStatus.SCHEDULED

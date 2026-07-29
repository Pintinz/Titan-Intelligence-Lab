import uuid
from datetime import datetime, timezone

import pytest

from modules.sports.domain.entities import (
    Country,
    Lineup,
    LineupSlot,
    Sport,
    Team,
    TeamStatistics,
)
from modules.sports.domain.value_objects import (
    CountryId,
    LineupId,
    LineupRole,
    MatchId,
    PlayerId,
    ProviderRef,
    SportCode,
    SportId,
    TeamId,
)
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCountryRepository,
    SqlAlchemyLineupRepository,
    SqlAlchemySportRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
)


def _lineup(role_mix=True) -> Lineup:
    slots = [
        LineupSlot(player_id=PlayerId(uuid.uuid4()), role=LineupRole.STARTER, position="GK", shirt_number=1),
        LineupSlot(player_id=PlayerId(uuid.uuid4()), role=LineupRole.STARTER, position="DF", shirt_number=2),
    ]
    if role_mix:
        slots.append(LineupSlot(player_id=PlayerId(uuid.uuid4()), role=LineupRole.SUBSTITUTE, position="FW", shirt_number=9))
    return Lineup(id=LineupId(uuid.uuid4()), match_id=MatchId(uuid.uuid4()), team_id=TeamId(uuid.uuid4()), formation="4-3-3", slots=tuple(slots))


def test_lineup_starters_and_substitutes_filter_correctly():
    lineup = _lineup()

    assert len(lineup.starters()) == 2
    assert len(lineup.substitutes()) == 1
    assert all(s.role is LineupRole.STARTER for s in lineup.starters())


def test_lineup_with_no_substitutes():
    lineup = _lineup(role_mix=False)

    assert len(lineup.starters()) == 2
    assert lineup.substitutes() == ()


def test_country_defaults_to_version_1_no_provider_refs():
    country = Country(id=CountryId(uuid.uuid4()), code="GB", name="United Kingdom")

    assert country.version == 1
    assert country.provider_refs == ()


@pytest.mark.asyncio
async def test_country_repository_round_trip(sqlite_session):
    repo = SqlAlchemyCountryRepository(session=sqlite_session)
    country = Country(
        id=CountryId(uuid.uuid4()), code="GB", name="United Kingdom",
        provider_refs=(ProviderRef(provider="api_football", external_id="4"),),
    )

    await repo.upsert(country)
    await sqlite_session.commit()

    fetched = await repo.get(country.id)
    by_code = await repo.get_by_code("GB")
    all_countries = await repo.list_all()

    assert fetched is not None and fetched.name == "United Kingdom"
    assert by_code is not None and by_code.id == country.id
    assert len(all_countries) == 1
    assert fetched.provider_refs == (ProviderRef(provider="api_football", external_id="4"),)


@pytest.mark.asyncio
async def test_country_repository_update_bumps_version(sqlite_session):
    repo = SqlAlchemyCountryRepository(session=sqlite_session)
    country = Country(id=CountryId(uuid.uuid4()), code="GB", name="United Kingdom")
    await repo.upsert(country)
    await sqlite_session.commit()

    country.name = "Great Britain"
    country.version = 2
    await repo.upsert(country)
    await sqlite_session.commit()

    fetched = await repo.get(country.id)
    assert fetched.version == 2
    assert fetched.name == "Great Britain"


@pytest.mark.asyncio
async def test_sport_repository_preserves_version_and_provider_refs(sqlite_session):
    repo = SqlAlchemySportRepository(session=sqlite_session)
    sport = Sport(
        id=SportId(uuid.uuid4()), code=SportCode.FOOTBALL, name="Football", version=3,
        provider_refs=(ProviderRef(provider="api_football", external_id="root"),),
    )

    await repo.upsert(sport)
    await sqlite_session.commit()

    fetched = await repo.get(sport.id)
    assert fetched.version == 3
    assert fetched.provider_refs == (ProviderRef(provider="api_football", external_id="root"),)


@pytest.mark.asyncio
async def test_team_statistics_repository_round_trip(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    stats_repo = SqlAlchemyTeamStatisticsRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid.uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid.uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country="England")
    await team_repo.upsert(team)

    match_id = MatchId(uuid.uuid4())
    from modules.sports.domain.value_objects import EntityId

    stats = TeamStatistics(
        id=EntityId(uuid.uuid4()), match_id=match_id, team_id=team.id,
        stat_set={"possession_pct": 55.0, "shots_total": 12},
    )
    await stats_repo.upsert(stats)
    await sqlite_session.commit()

    fetched = await stats_repo.get_for_match_team(match_id, team.id)
    by_match = await stats_repo.list_by_match(match_id)

    assert fetched is not None
    assert fetched.stat_set["possession_pct"] == pytest.approx(55.0)
    assert len(by_match) == 1


@pytest.mark.asyncio
async def test_lineup_repository_round_trip_preserves_slots(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    lineup_repo = SqlAlchemyLineupRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid.uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid.uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country="England")
    await team_repo.upsert(team)

    match_id = MatchId(uuid.uuid4())
    lineup = Lineup(
        id=LineupId(uuid.uuid4()), match_id=match_id, team_id=team.id, formation="4-4-2",
        slots=(
            LineupSlot(player_id=PlayerId(uuid.uuid4()), role=LineupRole.STARTER, position="GK", shirt_number=1),
            LineupSlot(player_id=PlayerId(uuid.uuid4()), role=LineupRole.SUBSTITUTE, position="MF", shirt_number=14),
        ),
    )
    await lineup_repo.upsert(lineup)
    await sqlite_session.commit()

    fetched = await lineup_repo.get(lineup.id)
    by_match_team = await lineup_repo.get_for_match_team(match_id, team.id)
    by_match = await lineup_repo.list_by_match(match_id)

    assert fetched is not None
    assert fetched.formation == "4-4-2"
    assert len(fetched.slots) == 2
    assert len(fetched.starters()) == 1
    assert len(fetched.substitutes()) == 1
    assert by_match_team is not None
    assert len(by_match) == 1

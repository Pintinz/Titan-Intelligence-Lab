from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.sports.domain.entities import (
    Competition,
    Fixture,
    Player,
    Season,
    Sport,
    Standing,
    Team,
    TeamStatistics,
    Venue,
)
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    DateRange,
    EntityId,
    FixtureId,
    FixtureStatus,
    MatchId,
    PlayerId,
    ProviderRef,
    SeasonId,
    SeasonStatus,
    SportCode,
    SportId,
    TeamId,
    VenueId,
)
from modules.sports.infrastructure.persistence.models import MatchModel
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyVenueRepository,
)


@pytest.mark.asyncio
async def test_sport_repository_round_trip(sqlite_session):
    repo = SqlAlchemySportRepository(session=sqlite_session)
    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")

    await repo.upsert(sport)
    await sqlite_session.commit()

    fetched = await repo.get(sport.id)
    by_code = await repo.get_by_code(SportCode.FOOTBALL)

    assert fetched is not None
    assert fetched.name == "Football"
    assert by_code is not None
    assert by_code.id == sport.id


@pytest.mark.asyncio
async def test_venue_repository_round_trip(sqlite_session):
    repo = SqlAlchemyVenueRepository(session=sqlite_session)
    venue = Venue(id=VenueId(uuid4()), name="Old Trafford", city="Manchester", country="England")

    await repo.upsert(venue)
    await sqlite_session.commit()

    fetched = await repo.get(venue.id)

    assert fetched is not None
    assert fetched.name == "Old Trafford"
    assert fetched.timezone == "UTC"


@pytest.mark.asyncio
async def test_team_repository_round_trip_preserves_provider_refs(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)

    team = Team(
        id=TeamId(uuid4()),
        sport_id=sport.id,
        name="Manchester United",
        short_name="MUN",
        country="England",
        provider_refs=(ProviderRef(provider="api_football", external_id="33"),),
    )
    await team_repo.upsert(team)
    await sqlite_session.commit()

    fetched = await team_repo.get(team.id)

    assert fetched is not None
    assert fetched.name == "Manchester United"
    assert fetched.provider_refs == (ProviderRef(provider="api_football", external_id="33"),)


@pytest.mark.asyncio
async def test_team_repository_list_by_sport(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.BASKETBALL, name="Basketball")
    await sport_repo.upsert(sport)

    for name in ("Team A", "Team B"):
        await team_repo.upsert(
            Team(id=TeamId(uuid4()), sport_id=sport.id, name=name, short_name=name[:3], country=None)
        )
    await sqlite_session.commit()

    teams = await team_repo.list_by_sport(sport.id)

    assert {t.name for t in teams} == {"Team A", "Team B"}


@pytest.mark.asyncio
async def test_player_repository_round_trip(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    player_repo = SqlAlchemyPlayerRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country="England")
    await team_repo.upsert(team)

    player = Player(
        id=PlayerId(uuid4()),
        sport_id=sport.id,
        name="Bukayo Saka",
        date_of_birth=None,
        position="forward",
        team_id=team.id,
    )
    await player_repo.upsert(player)
    await sqlite_session.commit()

    fetched = await player_repo.get(player.id)
    roster = await player_repo.list_by_team(team.id)

    assert fetched is not None
    assert fetched.position == "forward"
    assert len(roster) == 1


@pytest.mark.asyncio
async def test_player_repository_list_by_sport(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    player_repo = SqlAlchemyPlayerRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    other_sport = Sport(id=SportId(uuid4()), code=SportCode.BASKETBALL, name="Basketball")
    await sport_repo.upsert(other_sport)

    team = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country="England")
    await team_repo.upsert(team)

    for name in ("Bukayo Saka", "Declan Rice"):
        await player_repo.upsert(
            Player(id=PlayerId(uuid4()), sport_id=sport.id, name=name, date_of_birth=None, position=None, team_id=team.id)
        )
    # a player under a different sport must not leak into the football query
    await player_repo.upsert(
        Player(id=PlayerId(uuid4()), sport_id=other_sport.id, name="Off-sport Player", date_of_birth=None, position=None)
    )
    await sqlite_session.commit()

    players = await player_repo.list_by_sport(sport.id)

    assert {p.name for p in players} == {"Bukayo Saka", "Declan Rice"}


@pytest.mark.asyncio
async def test_competition_season_fixture_chain(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    competition_repo = SqlAlchemyCompetitionRepository(session=sqlite_session)
    season_repo = SqlAlchemySeasonRepository(session=sqlite_session)
    fixture_repo = SqlAlchemyFixtureRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)

    home = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Home FC", short_name="HFC", country=None)
    away = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Away FC", short_name="AFC", country=None)
    await team_repo.upsert(home)
    await team_repo.upsert(away)

    competition = Competition(
        id=CompetitionId(uuid4()),
        sport_id=sport.id,
        name="Premier League",
        type=CompetitionType.LEAGUE,
        country="England",
    )
    await competition_repo.upsert(competition)

    season = Season(
        id=SeasonId(uuid4()),
        competition_id=competition.id,
        label="2026/27",
        date_range=DateRange(start=datetime(2026, 8, 1, tzinfo=timezone.utc)),
    )
    await season_repo.upsert(season)

    fixture = Fixture(
        id=FixtureId(uuid4()),
        season_id=season.id,
        home_team_id=home.id,
        away_team_id=away.id,
        venue_id=None,
        scheduled_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    await fixture_repo.upsert(fixture)
    await sqlite_session.commit()

    fetched_competition = await competition_repo.get(competition.id)
    fetched_season = await season_repo.get(season.id)
    season_fixtures = await fixture_repo.list_by_season(season.id)

    assert fetched_competition is not None and fetched_competition.type is CompetitionType.LEAGUE
    assert fetched_season is not None and fetched_season.status is SeasonStatus.UPCOMING
    assert len(season_fixtures) == 1
    assert season_fixtures[0].status is FixtureStatus.SCHEDULED


@pytest.mark.asyncio
async def test_standing_repository_round_trip(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    competition_repo = SqlAlchemyCompetitionRepository(session=sqlite_session)
    season_repo = SqlAlchemySeasonRepository(session=sqlite_session)
    standing_repo = SqlAlchemyStandingRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Chelsea", short_name="CHE", country=None)
    await team_repo.upsert(team)
    competition = Competition(
        id=CompetitionId(uuid4()),
        sport_id=sport.id,
        name="Premier League",
        type=CompetitionType.LEAGUE,
        country="England",
    )
    await competition_repo.upsert(competition)
    season = Season(
        id=SeasonId(uuid4()),
        competition_id=competition.id,
        label="2026/27",
        date_range=DateRange(start=datetime(2026, 8, 1, tzinfo=timezone.utc)),
    )
    await season_repo.upsert(season)

    standing = Standing(
        id=EntityId(uuid4()),
        season_id=season.id,
        team_id=team.id,
        snapshot_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        rank=1,
        points=9.0,
        record={"won": 3, "drawn": 0, "lost": 0},
    )
    await standing_repo.upsert(standing)
    await sqlite_session.commit()

    standings = await standing_repo.list_by_season(season.id)

    assert len(standings) == 1
    assert standings[0].rank == 1
    assert standings[0].record["won"] == 3


@pytest.mark.asyncio
async def test_fixture_repository_list_recent_by_team(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    competition_repo = SqlAlchemyCompetitionRepository(session=sqlite_session)
    season_repo = SqlAlchemySeasonRepository(session=sqlite_session)
    fixture_repo = SqlAlchemyFixtureRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country=None)
    opponent_a = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Chelsea", short_name="CHE", country=None)
    opponent_b = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Fulham", short_name="FUL", country=None)
    await team_repo.upsert(team)
    await team_repo.upsert(opponent_a)
    await team_repo.upsert(opponent_b)

    competition = Competition(
        id=CompetitionId(uuid4()), sport_id=sport.id, name="Premier League",
        type=CompetitionType.LEAGUE, country="England",
    )
    await competition_repo.upsert(competition)
    season = Season(
        id=SeasonId(uuid4()), competition_id=competition.id, label="2026/27",
        date_range=DateRange(start=datetime(2026, 8, 1, tzinfo=timezone.utc)),
    )
    await season_repo.upsert(season)

    # team plays home vs opponent_a (earlier) and away vs opponent_b (later); a third
    # fixture not involving `team` at all must never appear in the result.
    early_fixture = Fixture(
        id=FixtureId(uuid4()), season_id=season.id, home_team_id=team.id, away_team_id=opponent_a.id,
        venue_id=None, scheduled_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    later_fixture = Fixture(
        id=FixtureId(uuid4()), season_id=season.id, home_team_id=opponent_b.id, away_team_id=team.id,
        venue_id=None, scheduled_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    unrelated_fixture = Fixture(
        id=FixtureId(uuid4()), season_id=season.id, home_team_id=opponent_a.id, away_team_id=opponent_b.id,
        venue_id=None, scheduled_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    await fixture_repo.upsert(early_fixture)
    await fixture_repo.upsert(later_fixture)
    await fixture_repo.upsert(unrelated_fixture)
    await sqlite_session.commit()

    recent = await fixture_repo.list_recent_by_team(
        team.id, before=datetime(2026, 8, 25, tzinfo=timezone.utc), limit=10
    )

    assert [f.id for f in recent] == [later_fixture.id, early_fixture.id]  # most recent first


@pytest.mark.asyncio
async def test_fixture_repository_list_recent_by_team_respects_before_cutoff(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    competition_repo = SqlAlchemyCompetitionRepository(session=sqlite_session)
    season_repo = SqlAlchemySeasonRepository(session=sqlite_session)
    fixture_repo = SqlAlchemyFixtureRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country=None)
    opponent = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Chelsea", short_name="CHE", country=None)
    await team_repo.upsert(team)
    await team_repo.upsert(opponent)
    competition = Competition(
        id=CompetitionId(uuid4()), sport_id=sport.id, name="Premier League",
        type=CompetitionType.LEAGUE, country="England",
    )
    await competition_repo.upsert(competition)
    season = Season(
        id=SeasonId(uuid4()), competition_id=competition.id, label="2026/27",
        date_range=DateRange(start=datetime(2026, 8, 1, tzinfo=timezone.utc)),
    )
    await season_repo.upsert(season)

    future_fixture = Fixture(
        id=FixtureId(uuid4()), season_id=season.id, home_team_id=team.id, away_team_id=opponent.id,
        venue_id=None, scheduled_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    await fixture_repo.upsert(future_fixture)
    await sqlite_session.commit()

    recent = await fixture_repo.list_recent_by_team(
        team.id, before=datetime(2026, 8, 25, tzinfo=timezone.utc), limit=10
    )

    assert recent == []


@pytest.mark.asyncio
async def test_team_statistics_repository_list_recent_by_team(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    stats_repo = SqlAlchemyTeamStatisticsRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country=None)
    await team_repo.upsert(team)

    early_match_id = MatchId(uuid4())
    later_match_id = MatchId(uuid4())
    sqlite_session.add(MatchModel(id=early_match_id.value, fixture_id=uuid4(), started_at=datetime(2026, 8, 10, tzinfo=timezone.utc)))
    sqlite_session.add(MatchModel(id=later_match_id.value, fixture_id=uuid4(), started_at=datetime(2026, 8, 20, tzinfo=timezone.utc)))
    await sqlite_session.flush()

    early_stats = TeamStatistics(
        id=EntityId(uuid4()), match_id=early_match_id, team_id=team.id, stat_set={"goals": 1},
    )
    later_stats = TeamStatistics(
        id=EntityId(uuid4()), match_id=later_match_id, team_id=team.id, stat_set={"goals": 3},
    )
    await stats_repo.upsert(early_stats)
    await stats_repo.upsert(later_stats)
    await sqlite_session.commit()

    recent = await stats_repo.list_recent_by_team(
        team.id, before=datetime(2026, 8, 25, tzinfo=timezone.utc), limit=10
    )

    assert [s.stat_set["goals"] for s in recent] == [3, 1]  # most recent match first


@pytest.mark.asyncio
async def test_team_statistics_repository_list_recent_by_team_respects_before_cutoff(sqlite_session):
    sport_repo = SqlAlchemySportRepository(session=sqlite_session)
    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    stats_repo = SqlAlchemyTeamStatisticsRepository(session=sqlite_session)

    sport = Sport(id=SportId(uuid4()), code=SportCode.FOOTBALL, name="Football")
    await sport_repo.upsert(sport)
    team = Team(id=TeamId(uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country=None)
    await team_repo.upsert(team)

    future_match_id = MatchId(uuid4())
    sqlite_session.add(MatchModel(id=future_match_id.value, fixture_id=uuid4(), started_at=datetime(2026, 9, 1, tzinfo=timezone.utc)))
    await sqlite_session.flush()
    await stats_repo.upsert(
        TeamStatistics(id=EntityId(uuid4()), match_id=future_match_id, team_id=team.id, stat_set={"goals": 5})
    )
    await sqlite_session.commit()

    recent = await stats_repo.list_recent_by_team(
        team.id, before=datetime(2026, 8, 25, tzinfo=timezone.utc), limit=10
    )

    assert recent == []

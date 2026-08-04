from datetime import datetime, timezone

import pytest

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def provider():
    return MockSportsDataProvider(provider_key="mock_football", sport_code="football")


@pytest.mark.asyncio
async def test_fetch_countries_returns_stable_list(provider):
    first = await provider.fetch_countries()
    second = await provider.fetch_countries()

    assert len(first) > 0
    assert first == second
    assert all(len(c.code) == 2 for c in first)


@pytest.mark.asyncio
async def test_fetch_players_returns_full_roster(provider):
    teams = await provider.fetch_teams("39")

    players = await provider.fetch_players(teams[0].external_ref)

    assert len(players) == 15
    assert all(p.team_ref == teams[0].external_ref for p in players)
    assert all(p.position in ("goalkeeper", "defender", "midfielder", "forward") for p in players)


@pytest.mark.asyncio
async def test_fetch_players_is_deterministic_per_team(provider):
    teams = await provider.fetch_teams("39")

    first = await provider.fetch_players(teams[0].external_ref)
    second = await provider.fetch_players(teams[0].external_ref)

    assert first == second


@pytest.mark.asyncio
async def test_fetch_standings_ranks_every_team_once(provider):
    teams = await provider.fetch_teams("39")

    standings = await provider.fetch_standings("39", "2026")

    assert len(standings) == len(teams)
    assert sorted(s.rank for s in standings) == list(range(1, len(teams) + 1))


@pytest.mark.asyncio
async def test_fetch_team_statistics_returns_home_and_away(provider):
    fixtures = await provider.fetch_fixtures("39", "2026", NOW)

    stats = await provider.fetch_team_statistics(fixtures[0].external_ref)

    assert len(stats) == 2
    assert stats[0].team_ref != stats[1].team_ref
    for record in stats:
        assert set(record.stat_set) == {
            "possession_pct", "shots_total", "shots_on_target", "corners", "fouls", "cards_yellow", "cards_red",
        }


@pytest.mark.asyncio
async def test_fetch_team_statistics_matches_sport_schema_for_basketball():
    provider = MockSportsDataProvider(provider_key="mock_basketball", sport_code="basketball")
    fixtures = await provider.fetch_fixtures("12", "2026", NOW)

    stats = await provider.fetch_team_statistics(fixtures[0].external_ref)

    assert set(stats[0].stat_set) == {"points", "field_goals_made", "field_goals_attempted", "rebounds", "turnovers"}


@pytest.mark.asyncio
async def test_fetch_lineups_returns_two_teams_with_14_slots_each(provider):
    fixtures = await provider.fetch_fixtures("39", "2026", NOW)

    lineups = await provider.fetch_lineups(fixtures[0].external_ref)

    assert len(lineups) == 2
    for lineup in lineups:
        assert len(lineup.slots) == 14
        starters = [s for s in lineup.slots if s.role == "starter"]
        substitutes = [s for s in lineup.slots if s.role == "substitute"]
        assert len(starters) == 11
        assert len(substitutes) == 3


@pytest.mark.asyncio
async def test_fetch_lineups_formation_only_set_for_football():
    football = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    basketball = MockSportsDataProvider(provider_key="mock_basketball", sport_code="basketball")

    football_fixtures = await football.fetch_fixtures("39", "2026", NOW)
    basketball_fixtures = await basketball.fetch_fixtures("12", "2026", NOW)

    football_lineups = await football.fetch_lineups(football_fixtures[0].external_ref)
    basketball_lineups = await basketball.fetch_lineups(basketball_fixtures[0].external_ref)

    assert football_lineups[0].formation == "4-3-3"
    assert basketball_lineups[0].formation is None


@pytest.mark.asyncio
async def test_table_tennis_mock_supports_full_expanded_protocol():
    provider = MockSportsDataProvider(provider_key="mock_table_tennis", sport_code="table_tennis")

    teams = await provider.fetch_teams("wtt")
    players = await provider.fetch_players(teams[0].external_ref)
    standings = await provider.fetch_standings("wtt", "2026")
    fixtures = await provider.fetch_fixtures("wtt", "2026", NOW)
    stats = await provider.fetch_team_statistics(fixtures[0].external_ref)

    assert len(players) == 15
    assert len(standings) == len(teams)
    assert set(stats[0].stat_set) == {"points_won", "sets_won", "unforced_errors"}

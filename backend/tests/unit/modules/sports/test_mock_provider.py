import pytest

from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider


@pytest.mark.asyncio
async def test_fetch_teams_is_deterministic_for_same_competition():
    provider_a = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    provider_b = MockSportsDataProvider(provider_key="mock_football", sport_code="football")

    teams_a = await provider_a.fetch_teams("39")
    teams_b = await provider_b.fetch_teams("39")

    assert teams_a == teams_b


@pytest.mark.asyncio
async def test_fetch_teams_differs_by_competition():
    provider = MockSportsDataProvider(provider_key="mock_football", sport_code="football")

    teams_a = await provider.fetch_teams("39")
    teams_b = await provider.fetch_teams("140")

    assert teams_a != teams_b


@pytest.mark.asyncio
async def test_fetch_fixtures_references_valid_teams():
    provider = MockSportsDataProvider(provider_key="mock_football", sport_code="football")

    teams = await provider.fetch_teams("39")
    fixtures = await provider.fetch_fixtures("39", "2026")

    team_refs = {t.external_ref for t in teams}
    assert len(fixtures) > 0
    for fixture in fixtures:
        assert fixture.home_team_ref in team_refs
        assert fixture.away_team_ref in team_refs
        assert fixture.home_team_ref != fixture.away_team_ref


@pytest.mark.asyncio
async def test_table_tennis_mock_satisfies_the_provider_protocol():
    provider = MockSportsDataProvider(provider_key="mock_table_tennis", sport_code="table_tennis")

    teams = await provider.fetch_teams("wtt-champions")

    assert len(teams) == 10
    assert all("Spinners" in t.name or "Smashers" in t.name or "Paddlers" in t.name or "Aces" in t.name for t in teams)

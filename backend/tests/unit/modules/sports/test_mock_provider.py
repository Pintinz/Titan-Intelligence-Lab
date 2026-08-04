from datetime import datetime, timedelta, timezone

import pytest

from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


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
    fixtures = await provider.fetch_fixtures("39", "2026", NOW)

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


@pytest.mark.asyncio
async def test_mock_fixture_status_is_not_started_before_kickoff():
    provider = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    fixtures = await provider.fetch_fixtures("39", "2026", NOW)  # NOW is well before every fixture's scheduled_at

    assert all(f.status == "NS" for f in fixtures)


@pytest.mark.asyncio
async def test_mock_fixture_status_is_live_shortly_after_kickoff():
    provider = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    fixtures = await provider.fetch_fixtures("39", "2026", NOW)
    kickoff = fixtures[0].scheduled_at

    mid_match = await provider.fetch_fixtures("39", "2026", kickoff + timedelta(minutes=30))

    assert mid_match[0].status == "LIVE"


@pytest.mark.asyncio
async def test_mock_fixture_status_is_finished_well_after_kickoff():
    provider = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    fixtures = await provider.fetch_fixtures("39", "2026", NOW)
    kickoff = fixtures[0].scheduled_at

    after_final_whistle = await provider.fetch_fixtures("39", "2026", kickoff + timedelta(hours=5))

    assert after_final_whistle[0].status == "FT"


@pytest.mark.asyncio
async def test_fetch_odds_is_deterministic_for_same_fixture():
    provider_a = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    provider_b = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    fixture_ref = (await provider_a.fetch_fixtures("39", "2026", NOW))[0].external_ref

    odds_a = await provider_a.fetch_odds(fixture_ref)
    odds_b = await provider_b.fetch_odds(fixture_ref)

    assert odds_a == odds_b


@pytest.mark.asyncio
async def test_fetch_odds_returns_a_realistic_overround():
    """home/draw/away implied probabilities should sum to a small bookmaker margin (~6%) above
    1.0, not exactly 1.0 (a fair/vig-free line) and not something absurd."""
    provider = MockSportsDataProvider(provider_key="mock_football", sport_code="football")
    fixture_ref = (await provider.fetch_fixtures("39", "2026", NOW))[0].external_ref

    odds = await provider.fetch_odds(fixture_ref)

    assert odds is not None
    assert odds.home_win > 1.0 and odds.draw > 1.0 and odds.away_win > 1.0
    overround = (1 / odds.home_win) + (1 / odds.draw) + (1 / odds.away_win) - 1.0
    assert overround == pytest.approx(0.06, abs=0.01)


@pytest.mark.asyncio
async def test_fetch_odds_returns_none_for_sports_without_a_modeled_line():
    provider = MockSportsDataProvider(provider_key="mock_basketball", sport_code="basketball")
    fixture_ref = (await provider.fetch_fixtures("12", "2026", NOW))[0].external_ref

    assert await provider.fetch_odds(fixture_ref) is None

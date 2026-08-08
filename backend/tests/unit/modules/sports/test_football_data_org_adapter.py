"""Tests the real football-data.org HTTP adapter against a mocked transport — the actual
adapter code (URL construction, auth header, response parsing, 429 handling) runs; only the
network is faked (same pattern as tests/unit/modules/sports/test_api_sports_adapter.py)."""

from datetime import datetime, timezone

import httpx
import pytest

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers.football_data_org_adapter import FootballDataOrgAdapter
from modules.sports.infrastructure.providers.api_sports_adapter import ProviderRequestError

NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


async def _get_key() -> str:
    return "test-fd-org-key"


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.fixture
def adapter():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Auth-Token"] == "test-fd-org-key"
        path = request.url.path

        if path == "/v4/competitions/PL/teams":
            return _json_response({
                "teams": [
                    {"id": 61, "name": "Chelsea FC", "tla": "CHE", "area": {"name": "England"}, "venue": "Stamford Bridge", "crest": "https://crests.example/chelsea.png"},
                    {"id": 65, "name": "Manchester City FC", "area": {"name": "England"}},
                ]
            })
        if path == "/v4/competitions/PL/matches":
            assert request.url.params["status"] == "SCHEDULED,TIMED"
            return _json_response({
                "matches": [
                    {
                        "id": 500, "utcDate": "2026-08-10T14:00:00Z", "status": "SCHEDULED", "venue": "Stamford Bridge",
                        "homeTeam": {"id": 61, "name": "Chelsea FC"}, "awayTeam": {"id": 65, "name": "Manchester City FC"},
                        "competition": {"id": 2021},
                    },
                    {
                        # no team assigned yet (e.g. playoff slot TBD) — must be skipped
                        "id": 501, "utcDate": "2026-08-11T14:00:00Z", "status": "SCHEDULED",
                        "homeTeam": {"id": None}, "awayTeam": {"id": 65},
                    },
                ]
            })
        raise AssertionError(f"unexpected path {path}")

    return FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))


@pytest.mark.asyncio
async def test_fetch_teams_maps_fields(adapter):
    teams = await adapter.fetch_teams("PL")

    assert teams[0].external_ref == ProviderRef(provider="football_data_org", external_id="61")
    assert teams[0].name == "Chelsea FC"
    assert teams[0].short_name == "CHE"
    assert teams[0].country == "England"
    assert teams[0].venue_name == "Stamford Bridge"
    assert teams[0].logo_url == "https://crests.example/chelsea.png"


@pytest.mark.asyncio
async def test_fetch_teams_falls_back_to_derived_short_name_when_no_tla(adapter):
    teams = await adapter.fetch_teams("PL")

    assert teams[1].short_name == "MAN"


@pytest.mark.asyncio
async def test_fetch_fixtures_requests_only_upcoming_statuses(adapter):
    fixtures = await adapter.fetch_fixtures("PL", "2026", NOW)

    assert len(fixtures) == 1  # the team-less record is skipped
    assert fixtures[0].external_ref == ProviderRef(provider="football_data_org", external_id="500")
    assert fixtures[0].home_team_ref == ProviderRef(provider="football_data_org", external_id="61")
    assert fixtures[0].away_team_ref == ProviderRef(provider="football_data_org", external_id="65")
    assert fixtures[0].status == "SCHEDULED"
    assert fixtures[0].season_label == "2026"
    assert fixtures[0].competition_ref == "2021"
    assert fixtures[0].scheduled_at == datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
    assert fixtures[0].venue_name == "Stamford Bridge"


@pytest.mark.asyncio
async def test_fetch_fixtures_skips_records_missing_a_team():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"matches": [{"id": 1, "homeTeam": {"id": None}, "awayTeam": {"id": 2}}]})

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_fixtures("PL", "2026", NOW) == []


@pytest.mark.asyncio
async def test_fetch_completed_fixtures_requests_finished_status_and_maps_scores():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["status"] == "FINISHED"
        return _json_response({
            "matches": [
                {
                    "id": 500, "utcDate": "2026-08-10T14:00:00Z", "status": "FINISHED", "venue": "Stamford Bridge",
                    "homeTeam": {"id": 61, "name": "Chelsea FC"}, "awayTeam": {"id": 65, "name": "Manchester City FC"},
                    "competition": {"id": 2021}, "score": {"fullTime": {"home": 2, "away": 1}},
                },
            ]
        })

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))
    fixtures = await adapter.fetch_completed_fixtures("PL", "2026", NOW)

    assert len(fixtures) == 1
    assert fixtures[0].status == "FINISHED"
    assert fixtures[0].home_score == 2
    assert fixtures[0].away_score == 1


@pytest.mark.asyncio
async def test_fetch_completed_fixtures_skips_records_missing_a_team():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"matches": [{"id": 1, "homeTeam": {"id": None}, "awayTeam": {"id": 2}}]})

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_completed_fixtures("PL", "2026", NOW) == []


@pytest.mark.asyncio
async def test_fetch_fixtures_leaves_score_unset_for_unplayed_matches(adapter):
    fixtures = await adapter.fetch_fixtures("PL", "2026", NOW)

    assert fixtures[0].home_score is None
    assert fixtures[0].away_score is None


@pytest.mark.asyncio
async def test_unsupported_methods_return_honest_empty_results(adapter):
    assert await adapter.fetch_countries() == []
    assert await adapter.fetch_players(ProviderRef("football_data_org", "61")) == []
    assert await adapter.fetch_team_statistics(ProviderRef("football_data_org", "500")) == []
    assert await adapter.fetch_lineups(ProviderRef("football_data_org", "500")) == []
    assert await adapter.fetch_odds(ProviderRef("football_data_org", "500")) is None


@pytest.mark.asyncio
async def test_fetch_standings_maps_total_table_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v4/competitions/PL/standings"
        return _json_response({
            "standings": [
                {
                    "type": "TOTAL",
                    "table": [
                        {
                            "position": 1, "team": {"id": 65, "name": "Manchester City FC"}, "points": 85,
                            "playedGames": 38, "won": 27, "draw": 4, "lost": 7,
                            "goalsFor": 90, "goalsAgainst": 33, "goalDifference": 57,
                        },
                        {
                            "position": 2, "team": {"id": 61, "name": "Chelsea FC"}, "points": 78,
                            "playedGames": 38, "won": 24, "draw": 6, "lost": 8,
                            "goalsFor": 75, "goalsAgainst": 40, "goalDifference": 35,
                        },
                    ],
                }
            ]
        })

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))
    standings = await adapter.fetch_standings("PL", "2026")

    assert len(standings) == 2
    assert standings[0].team_ref == ProviderRef(provider="football_data_org", external_id="65")
    assert standings[0].rank == 1
    assert standings[0].points == 85.0
    assert standings[0].record == {
        "played": 38, "won": 27, "drawn": 4, "lost": 7,
        "goals_for": 90, "goals_against": 33, "goal_difference": 57,
    }


@pytest.mark.asyncio
async def test_fetch_standings_ignores_non_total_groups_and_skips_teamless_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({
            "standings": [
                {"type": "HOME", "table": [{"position": 1, "team": {"id": 65}, "points": 40}]},
                {"type": "TOTAL", "table": [{"position": 1, "team": {"id": None}, "points": 0}]},
            ]
        })

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_standings("PL", "2026") == []


@pytest.mark.asyncio
async def test_fetch_standings_returns_empty_when_no_standings_in_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"standings": []})

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_standings("PL", "2026") == []


@pytest.mark.asyncio
async def test_rate_limit_raises_with_a_clear_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "You have exceeded your allowed requests per minute"})

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError, match="rate-limited"):
        await adapter.fetch_fixtures("PL", "2026", NOW)


@pytest.mark.asyncio
async def test_request_error_wraps_transport_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError):
        await adapter.fetch_teams("PL")


@pytest.mark.asyncio
async def test_request_error_wraps_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    adapter = FootballDataOrgAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError):
        await adapter.fetch_teams("PL")

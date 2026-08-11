"""Tests the real TheSportsDB (v1) HTTP adapter against a mocked transport — the actual adapter
code (path-segment auth, response parsing, client-side upcoming/completed filtering,
cross_provider_ref mapping) runs; only the network is faked (same pattern as
tests/unit/modules/sports/test_football_data_org_adapter.py)."""

from datetime import datetime, timezone

import httpx
import pytest

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers.api_sports_adapter import ProviderRequestError
from modules.sports.infrastructure.providers.thesportsdb_adapter import TheSportsDbAdapter

NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


async def _get_key() -> str:
    return "test-tsdb-key"


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.fixture
def adapter():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/api/v1/json/test-tsdb-key/lookup_all_teams.php":
            assert request.url.params["id"] == "4328"
            return _json_response({
                "teams": [
                    {
                        "idTeam": "133604", "strTeam": "Wigan Athletic", "strTeamShort": "WIG",
                        "strCountry": "England", "strStadium": "DW Stadium",
                        "strBadge": "https://thesportsdb.example/wigan.png", "idAPIfootball": "61",
                    },
                    {
                        "idTeam": "133632", "strTeam": "Manchester City", "strCountry": "England",
                    },
                ]
            })
        if path == "/api/v1/json/test-tsdb-key/eventsseason.php":
            assert request.url.params["id"] == "4328"
            assert request.url.params["s"] == "2026-2027"
            return _json_response({
                "events": [
                    {
                        "idEvent": "700", "idHomeTeam": "133604", "idAwayTeam": "133632",
                        "strTimestamp": "2026-08-15T14:00:00", "idLeague": "4328",
                        "strVenue": "DW Stadium", "intHomeScore": None, "intAwayScore": None,
                    },
                    {
                        "idEvent": "701", "idHomeTeam": "133632", "idAwayTeam": "133604",
                        "strTimestamp": "2026-08-01T14:00:00", "idLeague": "4328",
                        "strVenue": "Etihad Stadium", "intHomeScore": "3", "intAwayScore": "1",
                    },
                    {
                        # no team assigned — must be skipped
                        "idEvent": "702", "idHomeTeam": None, "idAwayTeam": "133604",
                    },
                ]
            })
        raise AssertionError(f"unexpected path {path}")

    return TheSportsDbAdapter(get_api_key=_get_key, client=_client_for(handler))


@pytest.mark.asyncio
async def test_fetch_teams_maps_fields_and_cross_provider_ref(adapter):
    teams = await adapter.fetch_teams("4328")

    assert teams[0].external_ref == ProviderRef(provider="thesportsdb", external_id="133604")
    assert teams[0].name == "Wigan Athletic"
    assert teams[0].short_name == "WIG"
    assert teams[0].country == "England"
    assert teams[0].venue_name == "DW Stadium"
    assert teams[0].logo_url == "https://thesportsdb.example/wigan.png"
    assert teams[0].cross_provider_ref == ProviderRef(provider="api_football", external_id="61")


@pytest.mark.asyncio
async def test_fetch_teams_leaves_cross_provider_ref_none_when_absent(adapter):
    teams = await adapter.fetch_teams("4328")

    assert teams[1].name == "Manchester City"
    assert teams[1].cross_provider_ref is None


@pytest.mark.asyncio
async def test_fetch_teams_skips_records_missing_team_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"teams": [{"strTeam": "No Id FC"}]})

    adapter = TheSportsDbAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_teams("4328") == []


@pytest.mark.asyncio
async def test_fetch_fixtures_returns_only_unplayed_events(adapter):
    fixtures = await adapter.fetch_fixtures("4328", "2026-2027", NOW)

    assert len(fixtures) == 1
    assert fixtures[0].external_ref == ProviderRef(provider="thesportsdb", external_id="700")
    assert fixtures[0].home_team_ref == ProviderRef(provider="thesportsdb", external_id="133604")
    assert fixtures[0].away_team_ref == ProviderRef(provider="thesportsdb", external_id="133632")
    assert fixtures[0].status == "NS"
    assert fixtures[0].home_score is None
    assert fixtures[0].away_score is None
    assert fixtures[0].competition_ref == "4328"
    assert fixtures[0].season_label == "2026-2027"
    assert fixtures[0].venue_name == "DW Stadium"
    assert fixtures[0].scheduled_at == datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fetch_fixtures_skips_records_missing_a_team():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"events": [{"idEvent": "1", "idHomeTeam": None, "idAwayTeam": "2"}]})

    adapter = TheSportsDbAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_fixtures("4328", "2026-2027", NOW) == []


@pytest.mark.asyncio
async def test_fetch_completed_fixtures_returns_only_scored_events_with_status_ft(adapter):
    fixtures = await adapter.fetch_completed_fixtures("4328", "2026-2027", NOW)

    assert len(fixtures) == 1
    assert fixtures[0].external_ref == ProviderRef(provider="thesportsdb", external_id="701")
    assert fixtures[0].status == "FT"
    assert fixtures[0].home_score == 3
    assert fixtures[0].away_score == 1


@pytest.mark.asyncio
async def test_fetch_fixtures_defaults_scheduled_at_to_now_when_no_timestamp():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({
            "events": [{"idEvent": "1", "idHomeTeam": "10", "idAwayTeam": "20"}]
        })

    adapter = TheSportsDbAdapter(get_api_key=_get_key, client=_client_for(handler))
    fixtures = await adapter.fetch_fixtures("4328", "2026-2027", NOW)

    assert fixtures[0].scheduled_at == NOW


@pytest.mark.asyncio
async def test_unsupported_methods_return_honest_empty_results(adapter):
    assert await adapter.fetch_countries() == []
    assert await adapter.fetch_players(ProviderRef("thesportsdb", "133604")) == []
    assert await adapter.fetch_standings("4328", "2026-2027") == []
    assert await adapter.fetch_team_statistics(ProviderRef("thesportsdb", "700")) == []
    assert await adapter.fetch_lineups(ProviderRef("thesportsdb", "700")) == []
    assert await adapter.fetch_odds(ProviderRef("thesportsdb", "700")) is None
    assert await adapter.fetch_injuries(ProviderRef("thesportsdb", "133604")) == []
    assert await adapter.fetch_transfers(ProviderRef("thesportsdb", "133604")) == []
    assert await adapter.fetch_coach(ProviderRef("thesportsdb", "133604")) is None


@pytest.mark.asyncio
async def test_request_error_wraps_transport_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    adapter = TheSportsDbAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError):
        await adapter.fetch_teams("4328")


@pytest.mark.asyncio
async def test_request_error_wraps_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    adapter = TheSportsDbAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError):
        await adapter.fetch_teams("4328")

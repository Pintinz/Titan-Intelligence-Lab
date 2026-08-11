"""Tests the real API-SPORTS HTTP adapters against a mocked transport — the actual adapter
code (URL construction, header auth, response parsing) runs; only the network is faked
(docs/decisions.md ADR-008 pattern, applied to an HTTP adapter instead of a cache)."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers.api_sports_adapter import (
    ApiBaseballAdapter,
    ApiBasketballAdapter,
    ApiFootballAdapter,
    ProviderRequestError,
)

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


async def _get_key() -> str:
    return "test-api-key"


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


# -- ApiFootballAdapter ------------------------------------------------------------------------


@pytest.fixture
def football_adapter():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-apisports-key"] == "test-api-key"
        path = request.url.path

        if path == "/countries":
            return _json_response({"response": [{"code": "GB", "name": "England"}]})
        if path == "/teams":
            return _json_response({
                "response": [
                    {"team": {"id": 42, "name": "Arsenal", "code": "ARS", "country": "England"}, "venue": {"name": "Emirates"}},
                ]
            })
        if path == "/fixtures":
            return _json_response({
                "response": [
                    {
                        "fixture": {"id": 100, "date": "2026-08-01T15:00:00+00:00", "venue": {"name": "Emirates"}},
                        "teams": {"home": {"id": 42}, "away": {"id": 43}},
                        "league": {"id": 39, "season": 2026},
                    }
                ]
            })
        if path == "/players":
            return _json_response({
                "response": [
                    {"player": {"id": 7, "name": "Alex Carter", "birth": {"date": "1998-05-01"}}, "statistics": [{"games": {"position": "Forward"}}]},
                ]
            })
        if path == "/standings":
            return _json_response({
                "response": [
                    {"league": {"standings": [[
                        {"rank": 1, "team": {"id": 42}, "points": 45, "all": {"win": 14, "draw": 3, "lose": 2}},
                    ]]}}
                ]
            })
        if path == "/fixtures/statistics":
            return _json_response({
                "response": [
                    {
                        "team": {"id": 42},
                        "statistics": [
                            {"type": "Ball Possession", "value": "55%"},
                            {"type": "Total Shots", "value": 12},
                            {"type": "Shots on Goal", "value": 6},
                            {"type": "Corner Kicks", "value": 5},
                            {"type": "Fouls", "value": 9},
                            {"type": "Yellow Cards", "value": 3},
                            {"type": "Red Cards", "value": 0},
                            {"type": "Offsides", "value": 2},  # unmapped — should be skipped
                        ],
                    }
                ]
            })
        if path == "/fixtures/lineups":
            return _json_response({
                "response": [
                    {
                        "team": {"id": 42}, "formation": "4-3-3",
                        "startXI": [{"player": {"id": 7, "pos": "F", "number": 9}}],
                        "substitutes": [{"player": {"id": 8, "pos": "M", "number": 14}}],
                    }
                ]
            })
        if path == "/odds":
            return _json_response({
                "response": [
                    {
                        "fixture": {"id": 100},
                        "bookmakers": [
                            {
                                "id": 1, "name": "Bookmaker A",
                                "bets": [
                                    {
                                        "id": 1, "name": "Match Winner",
                                        "values": [
                                            {"value": "Home", "odd": "2.10"},
                                            {"value": "Draw", "odd": "3.40"},
                                            {"value": "Away", "odd": "3.60"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            })
        raise AssertionError(f"unexpected path {path}")

    return ApiFootballAdapter(get_api_key=_get_key, client=_client_for(handler))


@pytest.mark.asyncio
async def test_football_fetch_countries(football_adapter):
    countries = await football_adapter.fetch_countries()

    assert countries[0].code == "GB"
    assert countries[0].name == "England"


@pytest.mark.asyncio
async def test_football_fetch_teams(football_adapter):
    teams = await football_adapter.fetch_teams("39")

    assert teams[0].name == "Arsenal"
    assert teams[0].external_ref == ProviderRef(provider="api_football", external_id="42")
    assert teams[0].venue_name == "Emirates"


@pytest.mark.asyncio
async def test_football_fetch_fixtures(football_adapter):
    fixtures = await football_adapter.fetch_fixtures("39", "2026", NOW)

    assert fixtures[0].home_team_ref.external_id == "42"
    assert fixtures[0].away_team_ref.external_id == "43"
    assert fixtures[0].competition_ref == "39"
    assert fixtures[0].season_label == "2026"


@pytest.mark.asyncio
async def test_football_fetch_players(football_adapter):
    players = await football_adapter.fetch_players(ProviderRef("api_football", "42"))

    assert players[0].name == "Alex Carter"
    assert players[0].position == "forward"
    assert players[0].date_of_birth.year == 1998


@pytest.mark.asyncio
async def test_football_fetch_standings(football_adapter):
    standings = await football_adapter.fetch_standings("39", "2026")

    assert standings[0].rank == 1
    assert standings[0].points == pytest.approx(45.0)
    assert standings[0].record == {"won": 14, "drawn": 3, "lost": 2}


@pytest.mark.asyncio
async def test_football_fetch_team_statistics_maps_known_types_and_skips_unknown(football_adapter):
    stats = await football_adapter.fetch_team_statistics(ProviderRef("api_football", "100"))

    assert stats[0].stat_set == {
        "possession_pct": 55.0, "shots_total": 12, "shots_on_target": 6, "corners": 5, "fouls": 9,
        "cards_yellow": 3, "cards_red": 0,
    }
    assert "Offsides" not in stats[0].stat_set


@pytest.mark.asyncio
async def test_football_fetch_lineups(football_adapter):
    lineups = await football_adapter.fetch_lineups(ProviderRef("api_football", "100"))

    assert lineups[0].formation == "4-3-3"
    assert len(lineups[0].slots) == 2
    assert lineups[0].slots[0].role == "starter"
    assert lineups[0].slots[1].role == "substitute"


@pytest.mark.asyncio
async def test_football_fetch_odds_parses_first_bookmakers_match_winner_bet(football_adapter):
    odds = await football_adapter.fetch_odds(ProviderRef("api_football", "100"))

    assert odds.home_win == pytest.approx(2.10)
    assert odds.draw == pytest.approx(3.40)
    assert odds.away_win == pytest.approx(3.60)


@pytest.mark.asyncio
async def test_football_fetch_odds_returns_none_when_no_match_winner_bet_present():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/odds":
            return _json_response({"response": [{"fixture": {"id": 101}, "bookmakers": [{"bets": [{"name": "Total Goals", "values": []}]}]}]})
        raise AssertionError(f"unexpected path {request.url.path}")

    adapter = ApiFootballAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_odds(ProviderRef("api_football", "101")) is None


@pytest.mark.asyncio
async def test_football_fetch_odds_returns_none_when_no_fixtures_in_response():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/odds":
            return _json_response({"response": []})
        raise AssertionError(f"unexpected path {request.url.path}")

    adapter = ApiFootballAdapter(get_api_key=_get_key, client=_client_for(handler))

    assert await adapter.fetch_odds(ProviderRef("api_football", "999")) is None


@pytest.mark.asyncio
async def test_football_request_error_wraps_transport_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    adapter = ApiFootballAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError):
        await adapter.fetch_teams("39")


@pytest.mark.asyncio
async def test_football_request_error_wraps_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    adapter = ApiFootballAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError):
        await adapter.fetch_teams("39")


@pytest.mark.asyncio
async def test_football_request_error_surfaces_api_level_errors():
    """API-SPORTS reports plan/parameter problems (e.g. a free plan requesting a season it
    isn't entitled to) inside a 200 response's `errors` field, not via HTTP status — this must
    raise so a bad request doesn't look identical to "genuinely zero results"."""
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"response": [], "errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."}})

    adapter = ApiFootballAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ProviderRequestError, match="Free plans do not have access"):
        await adapter.fetch_fixtures("39", "2025", NOW)


@pytest.mark.asyncio
async def test_football_aclose_closes_client():
    closed = {"value": False}

    class TrackingClient(httpx.AsyncClient):
        async def aclose(self):
            closed["value"] = True
            await super().aclose()

    adapter = ApiFootballAdapter(get_api_key=_get_key, client=TrackingClient())
    await adapter.aclose()

    assert closed["value"] is True


# -- ApiBasketballAdapter -----------------------------------------------------------------------


@pytest.fixture
def basketball_adapter():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/teams":
            return _json_response({"response": [{"id": 1, "name": "Hawks", "country": {"name": "USA"}}]})
        if path == "/games":
            return _json_response({
                "response": [{
                    "id": 200, "date": "2026-08-01T20:00:00+00:00", "teams": {"home": {"id": 1}, "away": {"id": 2}},
                    "scores": {
                        "home": {"quarter_1": 28, "quarter_2": 17, "quarter_3": 20, "quarter_4": 21, "over_time": None, "total": 86},
                        "away": {"quarter_1": 36, "quarter_2": 32, "quarter_3": 28, "quarter_4": 27, "over_time": None, "total": 123},
                    },
                }]
            })
        if path == "/players":
            return _json_response({"response": [{"id": 10, "name": "Jordan Reyes", "position": "guard", "birth": {"date": "1997-03-01"}}]})
        if path == "/standings":
            return _json_response({
                "response": [{"team": {"id": 1}, "position": 1, "games": {"win": {"total": 40}, "lose": {"total": 10}}}]
            })
        if path == "/games/statistics/teams":
            # Real shape verified live against v1.basketball.api-sports.io (2026-08-10): flat
            # per-team entries, no "statistics" wrapper, no raw "points" field.
            return _json_response({
                "response": [
                    {
                        "game": {"id": 200}, "team": {"id": 1},
                        "field_goals": {"total": 42, "attempts": 95, "percentage": 44},
                        "threepoint_goals": {"total": 11, "attempts": 35, "percentage": 31},
                        "freethrows_goals": {"total": 16, "attempts": 22, "percentage": 72},
                        "rebounds": {"total": 56, "offence": 11, "defense": 45},
                        "assists": 28, "steals": 7, "blocks": 12, "turnovers": 16, "personal_fouls": 20,
                    }
                ]
            })
        raise AssertionError(f"unexpected path {path}")

    return ApiBasketballAdapter(get_api_key=_get_key, client=_client_for(handler))


@pytest.fixture
def basketball_adapter_scheduled():
    """A not-yet-tipped-off fixture — provider reports the same score keys, all null."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/games":
            return _json_response({
                "response": [{
                    "id": 201, "date": "2026-08-05T20:00:00+00:00", "teams": {"home": {"id": 1}, "away": {"id": 2}},
                    "scores": {
                        "home": {"quarter_1": None, "quarter_2": None, "quarter_3": None, "quarter_4": None, "over_time": None, "total": None},
                        "away": {"quarter_1": None, "quarter_2": None, "quarter_3": None, "quarter_4": None, "over_time": None, "total": None},
                    },
                }]
            })
        raise AssertionError(f"unexpected path {request.url.path}")

    return ApiBasketballAdapter(get_api_key=_get_key, client=_client_for(handler))


@pytest.mark.asyncio
async def test_basketball_fetch_teams(basketball_adapter):
    teams = await basketball_adapter.fetch_teams("12")

    assert teams[0].name == "Hawks"
    assert teams[0].country == "USA"


@pytest.mark.asyncio
async def test_basketball_fetch_fixtures(basketball_adapter):
    fixtures = await basketball_adapter.fetch_fixtures("12", "2026", NOW)

    assert fixtures[0].home_team_ref.external_id == "1"
    assert fixtures[0].home_score == 86
    assert fixtures[0].away_score == 123
    assert fixtures[0].period_scores == {
        "kind": "quarter", "home": [28, 17, 20, 21], "away": [36, 32, 28, 27],
    }


@pytest.mark.asyncio
async def test_basketball_fetch_fixtures_no_period_scores_before_tipoff(basketball_adapter_scheduled):
    fixtures = await basketball_adapter_scheduled.fetch_fixtures("12", "2026", NOW)

    assert fixtures[0].period_scores is None


@pytest.mark.asyncio
async def test_basketball_fetch_players(basketball_adapter):
    players = await basketball_adapter.fetch_players(ProviderRef("api_basketball", "1"))

    assert players[0].name == "Jordan Reyes"
    assert players[0].position == "guard"


@pytest.mark.asyncio
async def test_basketball_fetch_standings(basketball_adapter):
    standings = await basketball_adapter.fetch_standings("12", "2026")

    assert standings[0].rank == 1
    assert standings[0].points == pytest.approx(40.0)
    assert standings[0].record == {"won": 40, "drawn": 0, "lost": 10}


@pytest.mark.asyncio
async def test_basketball_fetch_team_statistics(basketball_adapter):
    stats = await basketball_adapter.fetch_team_statistics(ProviderRef("api_basketball", "200"))

    # points = 2*(field_goals.total - threes.total) + 3*threes.total + free_throws.total
    #        = 2*(42-11) + 3*11 + 16 = 62 + 33 + 16 = 111
    assert stats[0].stat_set["points"] == 111
    assert stats[0].stat_set["field_goals_made"] == 42
    assert stats[0].stat_set["three_pointers_made"] == 11
    assert stats[0].stat_set["free_throws_made"] == 16
    assert stats[0].stat_set["rebounds_total"] == 56
    assert stats[0].stat_set["assists"] == 28


@pytest.mark.asyncio
async def test_basketball_fetch_lineups_returns_empty_list(basketball_adapter):
    lineups = await basketball_adapter.fetch_lineups(ProviderRef("api_basketball", "200"))

    assert lineups == []


@pytest.mark.asyncio
async def test_basketball_fetch_odds_returns_none(basketball_adapter):
    assert await basketball_adapter.fetch_odds(ProviderRef("api_basketball", "200")) is None


# -- ApiBaseballAdapter -------------------------------------------------------------------------


@pytest.fixture
def baseball_adapter():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/teams":
            return _json_response({"response": [{"id": 5, "name": "Pioneers", "country": {"name": "USA"}}]})
        if path == "/games" and request.url.params.get("id") == "300":
            # Real shape verified live (2026-08-10): API-Baseball has no per-game
            # team-statistics endpoint — the box score lives in this resource's own
            # "scores" block, which fetch_team_statistics now reads directly.
            return _json_response({
                "response": [{
                    "id": 300, "date": "2026-08-01T23:00:00+00:00",
                    "teams": {"home": {"id": 5}, "away": {"id": 6}},
                    "scores": {
                        "home": {"hits": 9, "errors": 1, "total": 4},
                        "away": {"hits": 6, "errors": 0, "total": 2},
                    },
                }]
            })
        if path == "/games":
            return _json_response({
                "response": [{
                    "id": 300, "date": "2026-08-01T23:00:00+00:00", "teams": {"home": {"id": 5}, "away": {"id": 6}},
                    "scores": {
                        "home": {"hits": 9, "errors": 1, "total": 4, "innings": {"1": 3, "2": 0, "3": 1, "4": 0, "5": 0, "6": 0, "7": None, "8": None, "9": None, "extra": None}},
                        "away": {"hits": 6, "errors": 0, "total": 2, "innings": {"1": 0, "2": 1, "3": 0, "4": 1, "5": 0, "6": 0, "7": None, "8": None, "9": None, "extra": None}},
                    },
                }]
            })
        if path == "/players":
            return _json_response({"response": [{"id": 20, "name": "Casey Novak", "position": "pitcher", "birth": {"date": "1996-02-01"}}]})
        if path == "/standings":
            return _json_response({
                "response": [{"team": {"id": 5}, "position": 2, "games": {"win": {"total": 55}, "lose": {"total": 45}}}]
            })
        raise AssertionError(f"unexpected path {path}")

    return ApiBaseballAdapter(get_api_key=_get_key, client=_client_for(handler))


@pytest.mark.asyncio
async def test_baseball_fetch_teams(baseball_adapter):
    teams = await baseball_adapter.fetch_teams("1")

    assert teams[0].name == "Pioneers"


@pytest.mark.asyncio
async def test_baseball_fetch_fixtures(baseball_adapter):
    fixtures = await baseball_adapter.fetch_fixtures("1", "2026", NOW)

    assert fixtures[0].away_team_ref.external_id == "6"
    assert fixtures[0].home_score == 4
    assert fixtures[0].away_score == 2
    assert fixtures[0].period_scores == {
        "kind": "inning",
        "home": [3, 0, 1, 0, 0, 0, None, None, None],
        "away": [0, 1, 0, 1, 0, 0, None, None, None],
    }


@pytest.mark.asyncio
async def test_baseball_fetch_players(baseball_adapter):
    players = await baseball_adapter.fetch_players(ProviderRef("api_baseball", "5"))

    assert players[0].name == "Casey Novak"
    assert players[0].position == "pitcher"


@pytest.mark.asyncio
async def test_baseball_fetch_standings(baseball_adapter):
    standings = await baseball_adapter.fetch_standings("1", "2026")

    assert standings[0].rank == 2
    assert standings[0].record == {"won": 55, "drawn": 0, "lost": 45}


@pytest.mark.asyncio
async def test_baseball_fetch_team_statistics(baseball_adapter):
    stats = await baseball_adapter.fetch_team_statistics(ProviderRef("api_baseball", "300"))

    by_team = {s.team_ref.external_id: s.stat_set for s in stats}
    assert by_team["5"] == {"runs": 4, "hits": 9, "errors": 1}
    assert by_team["6"] == {"runs": 2, "hits": 6, "errors": 0}


@pytest.mark.asyncio
async def test_baseball_fetch_lineups_returns_empty_list(baseball_adapter):
    lineups = await baseball_adapter.fetch_lineups(ProviderRef("api_baseball", "300"))

    assert lineups == []


@pytest.mark.asyncio
async def test_baseball_fetch_odds_returns_none(baseball_adapter):
    assert await baseball_adapter.fetch_odds(ProviderRef("api_baseball", "300")) is None

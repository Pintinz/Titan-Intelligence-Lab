"""Real HTTP adapters for the API-SPORTS family (API-Football, API-Basketball, API-Baseball) —
implements docs/architecture.md §5's Provider Adapter Pattern. Genuine HTTP-calling code, not a
placeholder — it just cannot be exercised against a live response until a real API key is
configured (provider configuration directive: "build the entire provider architecture to be
production-ready while allowing development using mocked providers").

Field mapping follows the documented API-SPORTS v3 response envelope
(``{"response": [...], "errors": [...]}``); verify against a live response and adjust the
`_parse_*` methods once a real key is available for each sport — the request/auth/error-handling
plumbing in the base class does not change either way.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)

ApiKeyGetter = Callable[[], Awaitable[str]]


def _as_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class ProviderRequestError(RuntimeError):
    """Wraps any transport/HTTP/parse failure so callers (ProviderRouter) have one exception
    type to catch regardless of the underlying cause."""


class _ApiSportsHttpAdapterBase:
    provider_key: str
    _base_url: str

    def __init__(self, get_api_key: ApiKeyGetter, client: httpx.AsyncClient | None = None) -> None:
        self._get_api_key = get_api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def _get(self, path: str, params: dict) -> dict:
        try:
            api_key = await self._get_api_key()
            response = await self._client.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"x-apisports-key": api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError(f"{self.provider_key} request to {path} failed: {exc}") from exc

        # API-SPORTS reports plan/parameter problems (wrong season, league not on this plan,
        # rate limit, ...) inside a 200 response's `errors` field, not via HTTP status — an
        # empty `response` array with a populated `errors` field looks identical to "genuinely
        # no results" unless this is checked explicitly, which silently produced 0-record syncs
        # with no diagnostic before this.
        errors = payload.get("errors")
        if errors:
            raise ProviderRequestError(f"{self.provider_key} request to {path} rejected by provider: {errors}")
        return payload

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_odds(self, fixture_ref: ProviderRef) -> ProviderOddsRecord | None:
        """No documented odds endpoint for this sport's API-SPORTS product yet — same honest
        gap as ``ApiBasketballAdapter``/``ApiBaseballAdapter``'s ``fetch_lineups``. Only
        ``ApiFootballAdapter`` overrides this with a real implementation."""
        return None

    async def fetch_countries(self) -> list[ProviderCountryRecord]:
        """``/countries`` is identical in shape across every API-SPORTS product
        (``{"response": [{"name":.., "code":.., "flag":..}, ...]}``) — shared here rather than
        duplicated per adapter."""
        payload = await self._get("/countries", {})
        return [
            ProviderCountryRecord(code=entry.get("code") or "", name=entry.get("name", ""))
            for entry in payload.get("response", [])
            if entry.get("code")
        ]


class ApiFootballAdapter(_ApiSportsHttpAdapterBase):
    provider_key = "api_football"
    _base_url = "https://v3.football.api-sports.io"

    async def fetch_teams(self, competition_ref: str, season_label: str | None = None) -> list[ProviderTeamRecord]:
        payload = await self._get("/teams", {"league": competition_ref, "season": season_label or str(datetime.now().year)})
        records = []
        for entry in payload.get("response", []):
            team = entry.get("team", {})
            venue = entry.get("venue", {})
            records.append(
                ProviderTeamRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    name=team.get("name", ""),
                    short_name=team.get("code") or team.get("name", "")[:3].upper(),
                    country=team.get("country"),
                    venue_name=venue.get("name"),
                    logo_url=team.get("logo"),
                )
            )
        return records

    async def fetch_fixtures(
        self, competition_ref: str, season_label: str, now: datetime
    ) -> list[ProviderFixtureRecord]:
        payload = await self._get("/fixtures", {"league": competition_ref, "season": season_label})
        records = []
        for entry in payload.get("response", []):
            fixture = entry.get("fixture", {})
            teams = entry.get("teams", {})
            league = entry.get("league", {})
            goals = entry.get("goals") or {}
            home, away = teams.get("home", {}), teams.get("away", {})
            records.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(fixture.get("id"))),
                    home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home.get("id"))),
                    away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away.get("id"))),
                    scheduled_at=datetime.fromisoformat(fixture["date"]) if fixture.get("date") else datetime.now(),
                    competition_ref=str(league.get("id", competition_ref)),
                    season_label=str(league.get("season", season_label)),
                    venue_name=(fixture.get("venue") or {}).get("name"),
                    status=(fixture.get("status") or {}).get("short"),
                    home_score=goals.get("home"),
                    away_score=goals.get("away"),
                )
            )
        return records

    async def fetch_players(self, team_ref: ProviderRef) -> list[ProviderPlayerRecord]:
        payload = await self._get("/players", {"team": team_ref.external_id, "season": datetime.now().year})
        records = []
        for entry in payload.get("response", []):
            player = entry.get("player", {})
            games = (entry.get("statistics") or [{}])[0].get("games", {})
            birth_date = player.get("birth", {}).get("date")
            records.append(
                ProviderPlayerRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(player.get("id"))),
                    team_ref=team_ref,
                    name=player.get("name", ""),
                    date_of_birth=datetime.fromisoformat(birth_date) if birth_date else None,
                    position=(games.get("position") or "").lower() or None,
                )
            )
        return records

    async def fetch_standings(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderStandingRecord]:
        payload = await self._get("/standings", {"league": competition_ref, "season": season_label})
        records = []
        for league_entry in payload.get("response", []):
            groups = league_entry.get("league", {}).get("standings", [])
            for group in groups:  # API-Football nests one array per group/conference
                for row in group:
                    team = row.get("team", {})
                    all_stats = row.get("all", {})
                    records.append(
                        ProviderStandingRecord(
                            team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                            rank=row.get("rank", 0),
                            points=float(row.get("points", 0)),
                            record={
                                "won": all_stats.get("win", 0),
                                "drawn": all_stats.get("draw", 0),
                                "lost": all_stats.get("lose", 0),
                            },
                        )
                    )
        return records

    _STAT_TYPE_MAP = {
        "Ball Possession": "possession_pct",
        "Total Shots": "shots_total",
        "Shots on Goal": "shots_on_target",
        "Corner Kicks": "corners",
        "Fouls": "fouls",
        "Yellow Cards": "cards_yellow",
        "Red Cards": "cards_red",
    }

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]:
        payload = await self._get("/fixtures/statistics", {"fixture": fixture_ref.external_id})
        records = []
        for entry in payload.get("response", []):
            team = entry.get("team", {})
            stat_set: dict = {}
            for stat in entry.get("statistics", []):
                key = self._STAT_TYPE_MAP.get(stat.get("type", ""))
                if key is None:
                    continue
                value = stat.get("value")
                if isinstance(value, str) and value.endswith("%"):
                    value = float(value.rstrip("%"))
                stat_set[key] = value
            records.append(
                ProviderTeamStatisticsRecord(
                    fixture_ref=fixture_ref,
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    stat_set=stat_set,
                )
            )
        return records

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]:
        payload = await self._get("/fixtures/lineups", {"fixture": fixture_ref.external_id})
        records = []
        for entry in payload.get("response", []):
            team = entry.get("team", {})
            team_ref = ProviderRef(provider=self.provider_key, external_id=str(team.get("id")))
            slots = []
            for item in entry.get("startXI", []):
                p = item.get("player", {})
                slots.append(
                    ProviderLineupSlotRecord(
                        player_ref=ProviderRef(provider=self.provider_key, external_id=str(p.get("id"))),
                        role="starter", position=p.get("pos"), shirt_number=p.get("number"),
                    )
                )
            for item in entry.get("substitutes", []):
                p = item.get("player", {})
                slots.append(
                    ProviderLineupSlotRecord(
                        player_ref=ProviderRef(provider=self.provider_key, external_id=str(p.get("id"))),
                        role="substitute", position=p.get("pos"), shirt_number=p.get("number"),
                    )
                )
            records.append(
                ProviderLineupRecord(
                    fixture_ref=fixture_ref, team_ref=team_ref,
                    formation=entry.get("formation"), slots=tuple(slots),
                )
            )
        return records

    async def fetch_odds(self, fixture_ref: ProviderRef) -> ProviderOddsRecord | None:
        """``/odds?fixture={id}`` returns one entry per bookmaker, each with a ``bets`` array —
        bet id/name ``"Match Winner"`` (1X2) is the standard three-way win market every
        bookmaker on this endpoint offers. Takes the first bookmaker's line rather than
        averaging across bookmakers — good enough for a market-efficiency signal, and avoids
        second-guessing which bookmaker is most liquid/representative."""
        payload = await self._get("/odds", {"fixture": fixture_ref.external_id})
        for entry in payload.get("response", []):
            for bookmaker in entry.get("bookmakers", []):
                for bet in bookmaker.get("bets", []):
                    if bet.get("name") != "Match Winner":
                        continue
                    values = {v.get("value"): v.get("odd") for v in bet.get("values", [])}
                    home, draw, away = _as_float(values.get("Home")), _as_float(values.get("Draw")), _as_float(values.get("Away"))
                    if home is None and draw is None and away is None:
                        continue
                    return ProviderOddsRecord(fixture_ref=fixture_ref, home_win=home, draw=draw, away_win=away)
        return None


class ApiBasketballAdapter(_ApiSportsHttpAdapterBase):
    provider_key = "api_basketball"
    _base_url = "https://v1.basketball.api-sports.io"

    async def fetch_teams(self, competition_ref: str, season_label: str | None = None) -> list[ProviderTeamRecord]:
        payload = await self._get("/teams", {"league": competition_ref, "season": season_label or str(datetime.now().year)})
        records = []
        for team in payload.get("response", []):
            records.append(
                ProviderTeamRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    name=team.get("name", ""),
                    short_name=(team.get("name", "") or "")[:3].upper(),
                    country=(team.get("country") or {}).get("name"),
                )
            )
        return records

    async def fetch_fixtures(
        self, competition_ref: str, season_label: str, now: datetime
    ) -> list[ProviderFixtureRecord]:
        payload = await self._get("/games", {"league": competition_ref, "season": season_label})
        records = []
        for game in payload.get("response", []):
            teams = game.get("teams", {})
            home, away = teams.get("home", {}), teams.get("away", {})
            records.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(game.get("id"))),
                    home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home.get("id"))),
                    away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away.get("id"))),
                    scheduled_at=datetime.fromisoformat(game["date"]) if game.get("date") else datetime.now(),
                    competition_ref=competition_ref,
                    season_label=season_label,
                    status=(game.get("status") or {}).get("short"),
                )
            )
        return records

    async def fetch_players(self, team_ref: ProviderRef) -> list[ProviderPlayerRecord]:
        payload = await self._get("/players", {"team": team_ref.external_id, "season": datetime.now().year})
        records = []
        for entry in payload.get("response", []):
            player = entry if "id" in entry else entry.get("player", {})
            birth = (player.get("birth") or {}).get("date")
            records.append(
                ProviderPlayerRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(player.get("id"))),
                    team_ref=team_ref,
                    name=player.get("name", ""),
                    date_of_birth=datetime.fromisoformat(birth) if birth else None,
                    position=(player.get("position") or "").lower() or None,
                )
            )
        return records

    async def fetch_standings(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderStandingRecord]:
        payload = await self._get("/standings", {"league": competition_ref, "season": season_label})
        records = []
        for row in payload.get("response", []):
            team = row.get("team", {})
            games = row.get("games", {})
            wins = ((games.get("win") or {}).get("total")) or 0
            losses = ((games.get("lose") or {}).get("total")) or 0
            records.append(
                ProviderStandingRecord(
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    rank=row.get("position", 0),
                    points=float(wins),
                    record={"won": wins, "drawn": 0, "lost": losses},
                )
            )
        return records

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]:
        """Endpoint path is a best-effort guess (``/games/statistics/teams``) — API-Basketball's
        exact statistics route is less consistently documented than API-Football's; verify
        against a live response before relying on this in production (unlike fetch_teams/
        fetch_fixtures/fetch_players/fetch_standings above, which follow well-documented
        conventions)."""
        payload = await self._get("/games/statistics/teams", {"id": fixture_ref.external_id})
        records = []
        for entry in payload.get("response", []):
            team = entry.get("team", {})
            stats = entry.get("statistics", [{}])
            row = stats[0] if isinstance(stats, list) and stats else {}
            records.append(
                ProviderTeamStatisticsRecord(
                    fixture_ref=fixture_ref,
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    stat_set={
                        "points": row.get("points", 0),
                        "field_goals_made": row.get("field_goals_made", 0),
                        "field_goals_attempted": row.get("field_goals_attempted", 0),
                        "rebounds": row.get("rebounds", 0),
                        "turnovers": row.get("turnovers", 0),
                    },
                )
            )
        return records

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]:
        """API-Basketball does not expose a dedicated pre-match lineup endpoint the way
        API-Football does — returns an empty list until a provider-confirmed source exists,
        rather than guessing at a nonexistent route. Table this for the same follow-up pass
        that resolves the remaining Entity Expansion Matrix items."""
        return []


class ApiBaseballAdapter(_ApiSportsHttpAdapterBase):
    provider_key = "api_baseball"
    _base_url = "https://v1.baseball.api-sports.io"

    async def fetch_teams(self, competition_ref: str, season_label: str | None = None) -> list[ProviderTeamRecord]:
        payload = await self._get("/teams", {"league": competition_ref, "season": season_label or str(datetime.now().year)})
        records = []
        for team in payload.get("response", []):
            records.append(
                ProviderTeamRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    name=team.get("name", ""),
                    short_name=(team.get("name", "") or "")[:3].upper(),
                    country=(team.get("country") or {}).get("name"),
                )
            )
        return records

    async def fetch_fixtures(
        self, competition_ref: str, season_label: str, now: datetime
    ) -> list[ProviderFixtureRecord]:
        payload = await self._get("/games", {"league": competition_ref, "season": season_label})
        records = []
        for game in payload.get("response", []):
            teams = game.get("teams", {})
            home, away = teams.get("home", {}), teams.get("away", {})
            records.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(game.get("id"))),
                    home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home.get("id"))),
                    away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away.get("id"))),
                    scheduled_at=datetime.fromisoformat(game["date"]) if game.get("date") else datetime.now(),
                    competition_ref=competition_ref,
                    season_label=season_label,
                    status=(game.get("status") or {}).get("short"),
                )
            )
        return records

    async def fetch_players(self, team_ref: ProviderRef) -> list[ProviderPlayerRecord]:
        payload = await self._get("/players", {"team": team_ref.external_id, "season": datetime.now().year})
        records = []
        for entry in payload.get("response", []):
            player = entry if "id" in entry else entry.get("player", {})
            birth = (player.get("birth") or {}).get("date")
            records.append(
                ProviderPlayerRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(player.get("id"))),
                    team_ref=team_ref,
                    name=player.get("name", ""),
                    date_of_birth=datetime.fromisoformat(birth) if birth else None,
                    position=(player.get("position") or "").lower() or None,
                )
            )
        return records

    async def fetch_standings(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderStandingRecord]:
        payload = await self._get("/standings", {"league": competition_ref, "season": season_label})
        records = []
        for row in payload.get("response", []):
            team = row.get("team", {})
            games = row.get("games", {})
            wins = ((games.get("win") or {}).get("total")) or 0
            losses = ((games.get("lose") or {}).get("total")) or 0
            records.append(
                ProviderStandingRecord(
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    rank=row.get("position", 0),
                    points=float(wins),
                    record={"won": wins, "drawn": 0, "lost": losses},
                )
            )
        return records

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]:
        """Same caveat as ApiBasketballAdapter.fetch_team_statistics — endpoint path is a
        best-effort guess, not verified against a live response."""
        payload = await self._get("/games/statistics/teams", {"id": fixture_ref.external_id})
        records = []
        for entry in payload.get("response", []):
            team = entry.get("team", {})
            stats = entry.get("statistics", [{}])
            row = stats[0] if isinstance(stats, list) and stats else {}
            records.append(
                ProviderTeamStatisticsRecord(
                    fixture_ref=fixture_ref,
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    stat_set={
                        "runs": row.get("runs", 0),
                        "hits": row.get("hits", 0),
                        "errors": row.get("errors", 0),
                        "left_on_base": row.get("left_on_base", 0),
                    },
                )
            )
        return records

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]:
        """API-Baseball does not expose a dedicated pre-match lineup endpoint the way
        API-Football does — same rationale as ApiBasketballAdapter.fetch_lineups."""
        return []

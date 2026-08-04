"""Real HTTP adapter for football-data.org (v4) — implements docs/architecture.md §5's Provider
Adapter Pattern as a second, narrowly-scoped football provider used only for upcoming fixture
schedules (see modules/sports/infrastructure/providers/provider_router.py's
`fixture_schedule_adapters`), while api-football continues to serve results, statistics,
lineups, and odds for every fixture regardless of which provider scheduled it. Field mapping
follows the documented API v4 response envelope (docs.football-data.org/general/v4/); the
request/auth/error-handling shape mirrors `_ApiSportsHttpAdapterBase`'s pattern in
`api_sports_adapter.py` without subclassing it — football-data.org's auth header
(``X-Auth-Token``), error envelope (HTTP status + JSON body, not API-SPORTS' 200-with-``errors``-
array), and response shape are all different enough that sharing the base class would just hide
those differences behind a leaky abstraction.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers.api_sports_adapter import ApiKeyGetter, ProviderRequestError
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)

# football-data.org's not-yet-played match statuses (docs.football-data.org/general/v4/match.html)
# — SCHEDULED/TIMED both mean "not yet played," which is the entire reason this adapter exists.
# Everything else (IN_PLAY/PAUSED/FINISHED/SUSPENDED/POSTPONED/CANCELLED/AWARDED) stays
# api-football's job to report, so fetch_fixtures below only ever requests/returns these two.
_UPCOMING_STATUSES = ("SCHEDULED", "TIMED")


class FootballDataOrgAdapter:
    """Upcoming-fixtures-only football-data.org adapter. Implements the full
    ``SportsDataProviderPort`` Protocol structurally so it plugs into ``SportsProviderRouter``
    like any other adapter, but only ``fetch_fixtures``/``fetch_teams`` do real work — the rest
    return an honest "not covered by this provider" empty result, following the exact precedent
    ``ApiBasketballAdapter.fetch_lineups``/``fetch_team_statistics`` already set in
    ``api_sports_adapter.py`` for "this provider genuinely doesn't have this data."
    """

    provider_key = "football_data_org"
    _base_url = "https://api.football-data.org/v4"

    def __init__(self, get_api_key: ApiKeyGetter, client: httpx.AsyncClient | None = None) -> None:
        self._get_api_key = get_api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def _get(self, path: str, params: dict) -> dict:
        try:
            api_key = await self._get_api_key()
            response = await self._client.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"X-Auth-Token": api_key},
            )
            if response.status_code == 429:
                raise ProviderRequestError(
                    f"{self.provider_key} request to {path} was rate-limited (free tier is 10 "
                    "req/min) — back off before retrying."
                )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError(f"{self.provider_key} request to {path} failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_teams(self, competition_ref: str, season_label: str | None = None) -> list[ProviderTeamRecord]:
        payload = await self._get(f"/competitions/{competition_ref}/teams", {})
        records = []
        for team in payload.get("teams", []):
            records.append(
                ProviderTeamRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    name=team.get("name", ""),
                    short_name=team.get("tla") or (team.get("shortName") or team.get("name", ""))[:3].upper(),
                    country=(team.get("area") or {}).get("name"),
                    venue_name=team.get("venue"),
                    logo_url=team.get("crest"),
                )
            )
        return records

    async def fetch_fixtures(
        self, competition_ref: str, season_label: str, now: datetime
    ) -> list[ProviderFixtureRecord]:
        """Requests only ``SCHEDULED``/``TIMED`` matches — this adapter's entire purpose is
        upcoming fixtures, so there's no reason to pull (and risk mis-syncing) finished/postponed
        ones api-football already owns. ``season_label`` isn't sent as a request param:
        football-data.org's ``/competitions/{ref}/matches`` scopes to the competition's *current*
        season implicitly (no historical season selector on the free tier) — the caller-supplied
        ``season_label`` is only echoed back onto each record for reconciliation's bookkeeping."""
        payload = await self._get(
            f"/competitions/{competition_ref}/matches",
            {"status": ",".join(_UPCOMING_STATUSES)},
        )
        records = []
        for match in payload.get("matches", []):
            home, away = match.get("homeTeam") or {}, match.get("awayTeam") or {}
            if home.get("id") is None or away.get("id") is None:
                continue  # a small number of fixtures (e.g. playoff slots TBD) have no team assigned yet
            competition = match.get("competition") or {}
            utc_date = match.get("utcDate")
            records.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(match.get("id"))),
                    home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home.get("id"))),
                    away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away.get("id"))),
                    scheduled_at=datetime.fromisoformat(utc_date.replace("Z", "+00:00")) if utc_date else now,
                    competition_ref=str(competition.get("id", competition_ref)),
                    season_label=season_label,
                    venue_name=match.get("venue"),
                    status=match.get("status"),
                )
            )
        return records

    async def fetch_countries(self) -> list[ProviderCountryRecord]:
        """No dedicated countries/areas listing is used by this adapter — ``fetch_teams`` already
        carries each team's ``area.name`` inline, and country data for reconciliation comes from
        api-football's own ``fetch_countries`` (the primary provider for every sport). Returns
        empty rather than adding a second, redundant countries source."""
        return []

    async def fetch_players(self, team_ref: ProviderRef) -> list[ProviderPlayerRecord]:
        """Player rosters stay api-football's job — this adapter only serves fixture schedules."""
        return []

    async def fetch_standings(self, competition_ref: str, season_label: str) -> list[ProviderStandingRecord]:
        """Standings stay api-football's job — this adapter only serves fixture schedules."""
        return []

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]:
        """Statistics stay api-football's job by design (see module docstring) — this adapter
        never syncs a fixture far enough into the past to have statistics anyway."""
        return []

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]:
        """Lineups stay api-football's job by design (see module docstring)."""
        return []

    async def fetch_odds(self, fixture_ref: ProviderRef) -> ProviderOddsRecord | None:
        """Odds stay api-football's job by design (see module docstring)."""
        return None

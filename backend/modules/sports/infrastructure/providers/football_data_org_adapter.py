"""Real HTTP adapter for football-data.org (v4) — implements docs/architecture.md §5's Provider
Adapter Pattern as a second, narrowly-scoped football provider used only for fixture scheduling
(see modules/sports/infrastructure/providers/provider_router.py's `fixture_schedule_adapters`):
`fetch_fixtures` for not-yet-played matches and `fetch_completed_fixtures` for their eventual
final scores, both confined to the current season (see `fetch_fixtures`'s docstring). api-football
continues to serve statistics, lineups, and odds for every fixture regardless of which provider
scheduled it. Field mapping
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
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
)

# football-data.org's not-yet-played match statuses (docs.football-data.org/general/v4/match.html)
# — SCHEDULED/TIMED both mean "not yet played," which is the entire reason this adapter exists.
# Everything else (IN_PLAY/PAUSED/SUSPENDED/POSTPONED/CANCELLED/AWARDED) stays api-football's job
# to report, so fetch_fixtures below only ever requests/returns these two. FINISHED is the one
# exception: fetch_completed_fixtures requests it separately so a fixture this adapter created as
# SCHEDULED/TIMED can later be updated with its final score (see that method's docstring).
_UPCOMING_STATUSES = ("SCHEDULED", "TIMED")
_COMPLETED_STATUSES = ("FINISHED",)


class FootballDataOrgAdapter:
    """Upcoming/completed-fixtures-only football-data.org adapter. Implements the full
    ``SportsDataProviderPort`` Protocol structurally so it plugs into ``SportsProviderRouter``
    like any other adapter, but only ``fetch_fixtures``/``fetch_completed_fixtures``/``fetch_teams``
    do real work — the rest return an honest "not covered by this provider" empty result,
    following the exact precedent ``ApiBasketballAdapter.fetch_lineups``/``fetch_team_statistics``
    already set in ``api_sports_adapter.py`` for "this provider genuinely doesn't have this data."
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

    def _to_fixture_record(
        self, match: dict, competition_ref: str, season_label: str, now: datetime
    ) -> ProviderFixtureRecord | None:
        home, away = match.get("homeTeam") or {}, match.get("awayTeam") or {}
        if home.get("id") is None or away.get("id") is None:
            return None  # a small number of fixtures (e.g. playoff slots TBD) have no team assigned yet
        competition = match.get("competition") or {}
        utc_date = match.get("utcDate")
        full_time = ((match.get("score") or {}).get("fullTime")) or {}
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider=self.provider_key, external_id=str(match.get("id"))),
            home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home.get("id"))),
            away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away.get("id"))),
            scheduled_at=datetime.fromisoformat(utc_date.replace("Z", "+00:00")) if utc_date else now,
            competition_ref=str(competition.get("id", competition_ref)),
            season_label=season_label,
            venue_name=match.get("venue"),
            status=match.get("status"),
            home_score=full_time.get("home"),
            away_score=full_time.get("away"),
        )

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
        records = [self._to_fixture_record(match, competition_ref, season_label, now) for match in payload.get("matches", [])]
        return [r for r in records if r is not None]

    async def fetch_completed_fixtures(
        self, competition_ref: str, season_label: str, now: datetime
    ) -> list[ProviderFixtureRecord]:
        """Companion to ``fetch_fixtures``, scoped to ``FINISHED`` matches instead of
        SCHEDULED/TIMED. Exists so a fixture this adapter created while upcoming (for a
        competition that opted into football-data.org as its fixture-schedule source via
        ``CompetitionFixtureSourcePreference``) eventually gets its final score and COMPLETED
        status — without this, such a fixture would sit at SCHEDULED forever, since api-football
        never even sees it (it wasn't the provider that scheduled it). Still subject to the same
        free-tier current-season-only scoping as ``fetch_fixtures`` — this is not a historical
        backfill path."""
        payload = await self._get(
            f"/competitions/{competition_ref}/matches",
            {"status": ",".join(_COMPLETED_STATUSES)},
        )
        records = [self._to_fixture_record(match, competition_ref, season_label, now) for match in payload.get("matches", [])]
        return [r for r in records if r is not None]

    async def fetch_countries(self) -> list[ProviderCountryRecord]:
        """No dedicated countries/areas listing is used by this adapter — ``fetch_teams`` already
        carries each team's ``area.name`` inline, and country data for reconciliation comes from
        api-football's own ``fetch_countries`` (the primary provider for every sport). Returns
        empty rather than adding a second, redundant countries source."""
        return []

    async def fetch_players(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderPlayerRecord]:
        """Player rosters stay api-football's job — this adapter only serves fixture schedules."""
        return []

    async def fetch_standings(self, competition_ref: str, season_label: str) -> list[ProviderStandingRecord]:
        """Real standings for the competition's current season (confirmed live: free tier serves
        `/competitions/{ref}/standings` with full team records, unlike statistics/lineups/odds,
        which genuinely aren't available on this provider — see module docstring). Only the
        `TOTAL` table is used; a competition split into groups (e.g. a cup's group stage) would
        have multiple `standings` entries, but every top-flight league this adapter targets has
        exactly one. `record` mirrors the shape `ApiFootballAdapter` already produces so
        `reconcile_standing` doesn't need to special-case the provider.

        CAUTION — same free-tier limitation as `fetch_fixtures`/`fetch_completed_fixtures`:
        `season_label` isn't sent as a request param, so this always returns whatever
        football-data.org considers the competition's *current* season, regardless of which
        season you asked for. Triggering `sync_standings_alt` for any season other than the
        genuinely current one (e.g. replaying it for a past season, or during the gap before a
        new season's fixtures exist) silently reconciles a mismatched — sometimes all-zero,
        not-yet-started — table under the wrong `season_id`. Confirmed live 2026-08-16: a manual
        re-run against a past season overwrote a real 20-team table with an unstarted season's
        blank one. Only call this for the season football-data.org would itself call current."""
        payload = await self._get(f"/competitions/{competition_ref}/standings", {})
        total_table = next((group.get("table", []) for group in payload.get("standings", []) if group.get("type") == "TOTAL"), [])
        records = []
        for row in total_table:
            team = row.get("team") or {}
            if team.get("id") is None or row.get("position") is None:
                continue
            records.append(
                ProviderStandingRecord(
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    rank=row.get("position"),
                    points=float(row.get("points", 0)),
                    record={
                        "played": row.get("playedGames"),
                        "won": row.get("won"),
                        "drawn": row.get("draw"),
                        "lost": row.get("lost"),
                        "goals_for": row.get("goalsFor"),
                        "goals_against": row.get("goalsAgainst"),
                        "goal_difference": row.get("goalDifference"),
                    },
                )
            )
        return records

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]:
        """Statistics stay api-football's job by design (see module docstring) — this adapter's
        `fetch_completed_fixtures` only ever supplies the final score, never box-score stats."""
        return []

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]:
        """Lineups stay api-football's job by design (see module docstring)."""
        return []

    async def fetch_odds(self, fixture_ref: ProviderRef) -> ProviderOddsRecord | None:
        """Odds stay api-football's job by design (see module docstring)."""
        return None

    async def fetch_injuries(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderInjuryRecord]:
        """Injuries stay api-football's job by design (see module docstring)."""
        return []

    async def fetch_transfers(self, team_ref: ProviderRef) -> list[ProviderTransferRecord]:
        """Transfers stay api-football's job by design (see module docstring)."""
        return []

    async def fetch_coach(self, team_ref: ProviderRef) -> ProviderCoachRecord | None:
        """Coaching staff stays api-football's job by design (see module docstring)."""
        return None

"""Real HTTP adapter for TheSportsDB (v1) — a second, supplementary football fixture-schedule
source (docs/architecture.md §5's Provider Adapter Pattern), plugged into
`SportsProviderRouter.fixture_schedule_adapters` alongside `FootballDataOrgAdapter`. Structured
identically to that adapter: only `fetch_teams`/`fetch_fixtures`/`fetch_completed_fixtures` do
real work, everything else returns an honest empty result.

Two things make this adapter different from every other one in this codebase, both verified live
(2026-08-10):

1. Auth: the API key is a URL *path segment*, not a header/query param —
   `https://www.thesportsdb.com/api/v1/json/{key}/<endpoint>`. See
   `modules/admin/infrastructure/connection_tester.py`'s `api_key_path` auth type for the same
   convention applied to the "Test Connection" button.
2. Team cross-referencing: `lookup_all_teams.php` returns each team's own `idAPIfootball` field
   — a real, provider-supplied claim that this is the same club API-Football already has under a
   different id. `fetch_teams` below threads that straight into `ProviderTeamRecord.cross_provider_ref`,
   which `EntityReconciliationService.reconcile_team` auto-merges on (see that field's docstring)
   — no fuzzy name-matching needed, unlike `CrossProviderTeamMappingService`'s football-data.org
   flow.

This account's key is scoped to Soccer only (confirmed live: `all_sports.php` returns
`['Soccer', 'Motorsport']` for this key/tier) — `competition_ref` below is always TheSportsDB's
own numeric league id (e.g. "4328" for the English Premier League), set per-competition via
`CompetitionFixtureSourcePreference`, same as `FootballDataOrgAdapter`.

Completed-fixture syncs through this adapter must be run with
`SyncOrchestrator.supplementary_provider_keys` including `"thesportsdb"` — this source is
explicitly non-authoritative (see `EntityReconciliationService.reconcile_fixture`'s
`preserve_existing_score`) and must never overwrite a score a primary provider already recorded.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


class TheSportsDbAdapter:
    """Upcoming/completed-fixtures-only TheSportsDB adapter — same narrow scope and
    ``SportsDataProviderPort`` structural conformance as ``FootballDataOrgAdapter`` (see that
    adapter's own docstring for why the port isn't fully implemented)."""

    provider_key = "thesportsdb"
    _base_url = "https://www.thesportsdb.com/api/v1/json"

    def __init__(self, get_api_key: ApiKeyGetter, client: httpx.AsyncClient | None = None) -> None:
        self._get_api_key = get_api_key
        self._client = client or httpx.AsyncClient(timeout=15.0)

    async def _get(self, path: str, params: dict) -> dict:
        try:
            api_key = await self._get_api_key()
            response = await self._client.get(f"{self._base_url}/{api_key}{path}", params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError(f"{self.provider_key} request to {path} failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_teams(self, competition_ref: str, season_label: str | None = None) -> list[ProviderTeamRecord]:
        payload = await self._get("/lookup_all_teams.php", {"id": competition_ref})
        records = []
        for team in payload.get("teams") or []:
            team_id = team.get("idTeam")
            if team_id is None:
                continue
            api_football_id = team.get("idAPIfootball")
            records.append(
                ProviderTeamRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(team_id)),
                    name=team.get("strTeam", ""),
                    short_name=(team.get("strTeamShort") or team.get("strTeam", "")[:3]).upper(),
                    country=team.get("strCountry"),
                    venue_name=team.get("strStadium"),
                    logo_url=team.get("strBadge"),
                    cross_provider_ref=(
                        ProviderRef(provider="api_football", external_id=str(api_football_id))
                        if api_football_id else None
                    ),
                )
            )
        return records

    def _to_fixture_record(self, event: dict, competition_ref: str, season_label: str, now: datetime) -> ProviderFixtureRecord | None:
        event_id = event.get("idEvent")
        home_id, away_id = event.get("idHomeTeam"), event.get("idAwayTeam")
        if event_id is None or home_id is None or away_id is None:
            return None
        timestamp = event.get("strTimestamp")
        if timestamp:
            scheduled_at = datetime.fromisoformat(timestamp)
            if scheduled_at.tzinfo is None:
                # `strTimestamp` (unlike `strTime`/`strTimeLocal`) is documented as UTC but comes
                # back with no offset — verified live (2026-08-10).
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        else:
            scheduled_at = now
        home_score_raw, away_score_raw = event.get("intHomeScore"), event.get("intAwayScore")
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider=self.provider_key, external_id=str(event_id)),
            home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home_id)),
            away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away_id)),
            scheduled_at=scheduled_at,
            competition_ref=str(event.get("idLeague") or competition_ref),
            season_label=season_label,
            venue_name=event.get("strVenue"),
            status="FT" if home_score_raw is not None and away_score_raw is not None else "NS",
            home_score=int(home_score_raw) if home_score_raw is not None else None,
            away_score=int(away_score_raw) if away_score_raw is not None else None,
        )

    async def fetch_fixtures(self, competition_ref: str, season_label: str, now: datetime) -> list[ProviderFixtureRecord]:
        """``eventsseason.php`` returns every event for the season with no server-side status
        filter (unlike football-data.org's own endpoint) — filtered client-side to events with no
        recorded score yet (real signal: `intHomeScore`/`intAwayScore` both null), which is the
        only reliable "not yet played" indicator this provider's response actually carries."""
        payload = await self._get("/eventsseason.php", {"id": competition_ref, "s": season_label})
        records = [self._to_fixture_record(e, competition_ref, season_label, now) for e in payload.get("events") or []]
        return [r for r in records if r is not None and r.home_score is None]

    async def fetch_completed_fixtures(self, competition_ref: str, season_label: str, now: datetime) -> list[ProviderFixtureRecord]:
        """Companion to ``fetch_fixtures``, filtered to events that *do* have a recorded score.
        Must be synced with ``preserve_existing_score=True`` (see module docstring) — this
        source's own score is real but non-authoritative."""
        payload = await self._get("/eventsseason.php", {"id": competition_ref, "s": season_label})
        records = [self._to_fixture_record(e, competition_ref, season_label, now) for e in payload.get("events") or []]
        return [r for r in records if r is not None and r.home_score is not None]

    async def fetch_countries(self) -> list[ProviderCountryRecord]:
        """No dedicated countries listing used — `fetch_teams` already carries each team's own
        `strCountry` inline, and country data for reconciliation comes from api-football."""
        return []

    async def fetch_players(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderPlayerRecord]:
        """Player rosters stay api-football's job — this adapter only serves fixture schedules."""
        return []

    async def fetch_standings(self, competition_ref: str, season_label: str) -> list[ProviderStandingRecord]:
        """Standings stay api-football's job by design (see module docstring)."""
        return []

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]:
        """Statistics stay api-football's job by design (see module docstring)."""
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

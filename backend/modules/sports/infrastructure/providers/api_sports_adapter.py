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
from enum import Enum

import httpx

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import (
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
)

ApiKeyGetter = Callable[[], Awaitable[str]]


def _as_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _classify_status(status_code: int) -> ProviderErrorKind:
    if status_code == 429:
        return ProviderErrorKind.RATE_LIMITED
    if status_code in (401, 403):
        return ProviderErrorKind.AUTH
    if status_code >= 500:
        return ProviderErrorKind.TRANSIENT
    return ProviderErrorKind.PERMANENT  # other 4xx: the request itself is wrong


def _retry_after_seconds(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None  # Retry-After may also be an HTTP-date, which callers fall back from


def _looks_rate_limited(errors: object) -> bool:
    text = str(errors).lower()
    return "rate limit" in text or "too many requests" in text or "quota" in text


class ProviderErrorKind(str, Enum):
    """Retry-safety classification (POST-M24 Phase 2) — lets a caller (`SportsProviderRouter`)
    decide whether bounded backoff-retry is safe without re-deriving it from the raw exception.
    `TRANSIENT`/`RATE_LIMITED`/`NETWORK` are worth a bounded retry; `AUTH`/`PERMANENT` never are
    (retrying a bad API key or a malformed request just burns quota for the same failure)."""

    TRANSIENT = "transient"  # 5xx — provider-side, may clear on its own
    RATE_LIMITED = "rate_limited"  # 429, or API-SPORTS' in-body rate-limit error
    AUTH = "auth"  # 401/403 — bad/expired credential, retrying changes nothing
    PERMANENT = "permanent"  # other 4xx / rejected params — the request itself is wrong
    NETWORK = "network"  # connection/timeout before any response was received


class ProviderRequestError(RuntimeError):
    """Wraps any transport/HTTP/parse failure so callers (ProviderRouter) have one exception
    type to catch regardless of the underlying cause. Carries enough structure for retry-safety
    decisions (`kind`, `retry_after_seconds`) without callers needing to inspect the original
    httpx exception."""

    def __init__(
        self, message: str, *, kind: ProviderErrorKind = ProviderErrorKind.TRANSIENT,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds


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
        except httpx.HTTPStatusError as exc:
            raise ProviderRequestError(
                f"{self.provider_key} request to {path} failed: {exc}",
                kind=_classify_status(exc.response.status_code),
                retry_after_seconds=_retry_after_seconds(exc.response),
            ) from exc
        except httpx.HTTPError as exc:
            # No response was ever received (connect/read timeout, DNS failure, ...) — a network
            # problem, not the provider's own fault; worth a bounded retry.
            raise ProviderRequestError(
                f"{self.provider_key} request to {path} failed: {exc}", kind=ProviderErrorKind.NETWORK,
            ) from exc
        except ValueError as exc:
            # Response received but not valid JSON — the provider itself is misbehaving, not
            # something a retry with the same params is likely to fix on the next attempt either,
            # but not confidently "this exact request is wrong" (PERMANENT) — treat as transient.
            raise ProviderRequestError(f"{self.provider_key} request to {path} failed: {exc}") from exc

        # API-SPORTS reports plan/parameter problems (wrong season, league not on this plan,
        # rate limit, ...) inside a 200 response's `errors` field, not via HTTP status — an
        # empty `response` array with a populated `errors` field looks identical to "genuinely
        # no results" unless this is checked explicitly, which silently produced 0-record syncs
        # with no diagnostic before this.
        errors = payload.get("errors")
        if errors:
            kind = ProviderErrorKind.RATE_LIMITED if _looks_rate_limited(errors) else ProviderErrorKind.PERMANENT
            raise ProviderRequestError(
                f"{self.provider_key} request to {path} rejected by provider: {errors}", kind=kind,
            )
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

    async def fetch_injuries(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderInjuryRecord]:
        """No documented injuries endpoint for this sport's API-SPORTS product yet — only
        ``ApiFootballAdapter`` overrides this with a real implementation, same posture as
        ``fetch_lineups``/``fetch_odds`` above."""
        return []

    async def fetch_transfers(self, team_ref: ProviderRef) -> list[ProviderTransferRecord]:
        """No documented transfers endpoint for this sport's API-SPORTS product yet."""
        return []

    async def fetch_coach(self, team_ref: ProviderRef) -> ProviderCoachRecord | None:
        """No documented coaches endpoint for this sport's API-SPORTS product yet."""
        return None


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
            score = entry.get("score") or {}
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
                    period_scores=self._extract_half_time_scores(score),
                )
            )
        return records

    @staticmethod
    def _extract_half_time_scores(score: dict) -> dict | None:
        """Real half-time score, from v3.football.api-sports.io's documented `/fixtures` response
        shape: `{"score": {"halftime": {"home": N, "away": N}, "fulltime": {...}, ...}}` — the
        `halftime` sub-object is present (with null home/away) even for fixtures that haven't
        reached half-time yet, so both must be non-null before this is considered reported.
        `period_scores["home"/"away"]` carries a one-element list (not a bare int) to match the
        `kind="half"` shape `_extract_half_time_scores` in entity_reconciliation_service.py already
        expects (mirrors basketball/baseball's per-period list convention)."""
        halftime = score.get("halftime") or {}
        home_ht, away_ht = halftime.get("home"), halftime.get("away")
        if home_ht is None or away_ht is None:
            return None
        return {"kind": "half", "home": [home_ht], "away": [away_ht]}

    async def fetch_players(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderPlayerRecord]:
        payload = await self._get("/players", {"team": team_ref.external_id, "season": season_label or datetime.now().year})
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
                    photo_url=player.get("photo"),
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

    async def fetch_injuries(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderInjuryRecord]:
        """``/injuries?team={id}&season={year}`` — confirmed free-tier accessible (api-football's
        public plan comparison lists Injuries alongside Fixtures/Standings, unlike the
        historical-season restriction that applies to some other endpoints). Each entry's
        ``player.type``/``player.reason`` are the provider's own raw unavailability text (see
        ``ProviderInjuryRecord``'s docstring) — no expected-return date is reported by this
        endpoint, so none is invented.

        Milestone 4 provenance finding (docs/milestone4_verification_report.md): the ``reported_at``
        populated below is ``fixture.date`` — the KICKOFF of the fixture this entry's unavailability
        refers to, not a report/publication timestamp. This endpoint reports no such timestamp at
        all. Do not treat ``reported_at`` as evidence this injury was known before that kickoff;
        `EntityReconciliationService.reconcile_injury` stores it under `Injury.reported_at` exactly
        as received, and `Injury.availability_classification` defaults to
        `UNKNOWN_AVAILABILITY_TIME` precisely because of this — see that field's own docstring."""
        payload = await self._get(
            "/injuries", {"team": team_ref.external_id, "season": season_label or str(datetime.now().year)}
        )
        records = []
        for entry in payload.get("response", []):
            player = entry.get("player", {})
            player_id = player.get("id")
            if player_id is None:
                continue
            fixture = entry.get("fixture") or {}
            reported_at = None
            if fixture.get("date"):
                try:
                    reported_at = datetime.fromisoformat(fixture["date"])
                except ValueError:
                    reported_at = None
            records.append(
                ProviderInjuryRecord(
                    player_ref=ProviderRef(provider=self.provider_key, external_id=str(player_id)),
                    team_ref=team_ref,
                    status=player.get("type") or "Unavailable",
                    reason=player.get("reason"),
                    reported_at=reported_at,
                )
            )
        return records

    async def fetch_transfers(self, team_ref: ProviderRef) -> list[ProviderTransferRecord]:
        """``/transfers?team={id}`` returns one entry per player who has ever transferred
        to/from this team, each with a ``transfers`` array of individual moves. Only moves where
        either side of the transfer is this team are kept (a player's full history includes
        transfers to/from other clubs too)."""
        payload = await self._get("/transfers", {"team": team_ref.external_id})
        records = []
        for entry in payload.get("response", []):
            player = entry.get("player", {})
            player_id = player.get("id")
            if player_id is None:
                continue
            player_ref = ProviderRef(provider=self.provider_key, external_id=str(player_id))
            for move in entry.get("transfers", []):
                teams = move.get("teams") or {}
                team_in, team_out = (teams.get("in") or {}), (teams.get("out") or {})
                in_id, out_id = team_in.get("id"), team_out.get("id")
                if str(in_id) != team_ref.external_id and str(out_id) != team_ref.external_id:
                    continue
                if not move.get("date"):
                    continue
                try:
                    effective_date = datetime.fromisoformat(move["date"])
                except ValueError:
                    continue
                records.append(
                    ProviderTransferRecord(
                        player_ref=player_ref,
                        from_team_ref=ProviderRef(provider=self.provider_key, external_id=str(out_id)) if out_id else None,
                        to_team_ref=ProviderRef(provider=self.provider_key, external_id=str(in_id)) if in_id else None,
                        effective_date=effective_date,
                        transfer_type=move.get("type"),
                    )
                )
        return records

    async def fetch_coach(self, team_ref: ProviderRef) -> ProviderCoachRecord | None:
        """``/coachs?team={id}`` returns every coach on record for this team, current and past —
        the current one is the entry with no ``career`` end date for this team."""
        payload = await self._get("/coachs", {"team": team_ref.external_id})
        for entry in payload.get("response", []):
            for spell in entry.get("career", []):
                spell_team = spell.get("team") or {}
                if str(spell_team.get("id")) == team_ref.external_id and not spell.get("end"):
                    return ProviderCoachRecord(team_ref=team_ref, person_name=entry.get("name", ""))
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
                    logo_url=team.get("logo"),
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
            # Audit fix (2026-08-10): "scores" was never read — every completed basketball
            # fixture silently kept home_score/away_score = None despite the provider reporting
            # a real final score here. Shape verified live: {"scores": {"home": {..., "total": N},
            # "away": {..., "total": N}}}, same "total" convention as API-Baseball's scores block.
            scores = game.get("scores") or {}
            home_score = (scores.get("home") or {}).get("total")
            away_score = (scores.get("away") or {}).get("total")
            period_scores = self._extract_quarter_scores(scores)
            records.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(game.get("id"))),
                    home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home.get("id"))),
                    away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away.get("id"))),
                    scheduled_at=datetime.fromisoformat(game["date"]) if game.get("date") else datetime.now(),
                    competition_ref=competition_ref,
                    season_label=season_label,
                    status=(game.get("status") or {}).get("short"),
                    home_score=home_score,
                    away_score=away_score,
                    period_scores=period_scores,
                )
            )
        return records

    @staticmethod
    def _extract_quarter_scores(scores: dict) -> dict | None:
        """Real quarter-by-quarter score breakdown — verified live against v1.basketball's
        `/games` response shape: `{"scores": {"home": {"quarter_1"..."quarter_4", "over_time",
        "total"}, "away": {...}}}`. None until at least the first quarter has been reported
        (scheduled fixtures carry the same keys, all null)."""
        home = scores.get("home") or {}
        away = scores.get("away") or {}
        quarter_keys = ("quarter_1", "quarter_2", "quarter_3", "quarter_4")
        if home.get("quarter_1") is None and away.get("quarter_1") is None:
            return None
        home_periods = [home.get(k) for k in quarter_keys]
        away_periods = [away.get(k) for k in quarter_keys]
        if home.get("over_time") is not None or away.get("over_time") is not None:
            home_periods.append(home.get("over_time"))
            away_periods.append(away.get("over_time"))
        return {"kind": "quarter", "home": home_periods, "away": away_periods}

    async def fetch_players(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderPlayerRecord]:
        payload = await self._get("/players", {"team": team_ref.external_id, "season": season_label or datetime.now().year})
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
        """Verified live against v1.basketball.api-sports.io/games/statistics/teams (2026-08-10):
        the endpoint is real, but the response is a flat list of
        ``{game, team, field_goals, threepoint_goals, freethrows_goals, rebounds, assists,
        steals, blocks, turnovers, personal_fouls}`` — no ``"statistics"`` wrapper array (the
        previous parser's assumption), and no raw ``points`` field. Points is computed from made
        field goals/threes/free-throws below, the same way a real box score derives it."""
        payload = await self._get("/games/statistics/teams", {"id": fixture_ref.external_id})
        records = []
        for entry in payload.get("response", []):
            team = entry.get("team", {})
            field_goals = entry.get("field_goals") or {}
            threes = entry.get("threepoint_goals") or {}
            free_throws = entry.get("freethrows_goals") or {}
            rebounds = entry.get("rebounds") or {}
            made_field_goals = field_goals.get("total") or 0
            made_threes = threes.get("total") or 0
            made_free_throws = free_throws.get("total") or 0
            points = 2 * (made_field_goals - made_threes) + 3 * made_threes + made_free_throws
            records.append(
                ProviderTeamStatisticsRecord(
                    fixture_ref=fixture_ref,
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team.get("id"))),
                    stat_set={
                        "points": points,
                        "field_goals_made": made_field_goals,
                        "field_goals_attempted": field_goals.get("attempts") or 0,
                        "three_pointers_made": made_threes,
                        "three_pointers_attempted": threes.get("attempts") or 0,
                        "free_throws_made": made_free_throws,
                        "free_throws_attempted": free_throws.get("attempts") or 0,
                        "rebounds_total": rebounds.get("total") or 0,
                        "rebounds_offensive": rebounds.get("offence") or 0,
                        "rebounds_defensive": rebounds.get("defense") or 0,
                        "assists": entry.get("assists") or 0,
                        "steals": entry.get("steals") or 0,
                        "blocks": entry.get("blocks") or 0,
                        "turnovers": entry.get("turnovers") or 0,
                        "personal_fouls": entry.get("personal_fouls") or 0,
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
                    logo_url=team.get("logo"),
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
            # Audit fix (2026-08-10): "scores" was never read, same class of bug as
            # ApiBasketballAdapter.fetch_fixtures — verified live, the real shape is
            # {"scores": {"home": {"hits", "errors", "total"}, "away": {...}}}, "total" is runs.
            scores = game.get("scores") or {}
            home_score = (scores.get("home") or {}).get("total")
            away_score = (scores.get("away") or {}).get("total")
            period_scores = self._extract_inning_scores(scores)
            records.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=str(game.get("id"))),
                    home_team_ref=ProviderRef(provider=self.provider_key, external_id=str(home.get("id"))),
                    away_team_ref=ProviderRef(provider=self.provider_key, external_id=str(away.get("id"))),
                    scheduled_at=datetime.fromisoformat(game["date"]) if game.get("date") else datetime.now(),
                    competition_ref=competition_ref,
                    season_label=season_label,
                    status=(game.get("status") or {}).get("short"),
                    home_score=home_score,
                    away_score=away_score,
                    period_scores=period_scores,
                )
            )
        return records

    @staticmethod
    def _extract_inning_scores(scores: dict) -> dict | None:
        """Real inning-by-inning run breakdown — verified live against v1.baseball's `/games`
        response shape: `{"scores": {"home": {"innings": {"1"..."9", "extra"}, "total"}, "away":
        {...}}}`. None until at least the first inning has been reported (scheduled fixtures
        carry the same keys, all null)."""
        home_innings = (scores.get("home") or {}).get("innings") or {}
        away_innings = (scores.get("away") or {}).get("innings") or {}
        if home_innings.get("1") is None and away_innings.get("1") is None:
            return None
        inning_keys = [str(i) for i in range(1, 10)]
        home_periods = [home_innings.get(k) for k in inning_keys]
        away_periods = [away_innings.get(k) for k in inning_keys]
        if home_innings.get("extra") is not None or away_innings.get("extra") is not None:
            home_periods.append(home_innings.get("extra"))
            away_periods.append(away_innings.get("extra"))
        return {"kind": "inning", "home": home_periods, "away": away_periods}

    async def fetch_players(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderPlayerRecord]:
        payload = await self._get("/players", {"team": team_ref.external_id, "season": season_label or datetime.now().year})
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
        """Verified live against v1.baseball.api-sports.io (2026-08-10): unlike football/
        basketball, there is no per-game team-statistics endpoint at all —
        ``/games/statistics/teams`` returns "This endpoint do not exist." The box score
        (hits/errors/runs) is embedded directly in the game resource's own ``scores`` block
        instead, so this re-fetches the game by id and reads it from there. ``left_on_base``,
        present in the old (unverified) parser, does not actually exist anywhere in this
        response and has been dropped rather than left as a permanently-zero fabricated field."""
        payload = await self._get("/games", {"id": fixture_ref.external_id})
        response = payload.get("response") or []
        if not response:
            return []
        game = response[0]
        teams = game.get("teams") or {}
        scores = game.get("scores") or {}
        records = []
        for side in ("home", "away"):
            team = teams.get(side) or {}
            score = scores.get(side) or {}
            if not team.get("id"):
                continue
            records.append(
                ProviderTeamStatisticsRecord(
                    fixture_ref=fixture_ref,
                    team_ref=ProviderRef(provider=self.provider_key, external_id=str(team["id"])),
                    stat_set={
                        "runs": score.get("total") or 0,
                        "hits": score.get("hits") or 0,
                        "errors": score.get("errors") or 0,
                    },
                )
            )
        return records

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]:
        """API-Baseball does not expose a dedicated pre-match lineup endpoint the way
        API-Football does — same rationale as ApiBasketballAdapter.fetch_lineups."""
        return []

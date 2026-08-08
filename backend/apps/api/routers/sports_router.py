"""Sports reference-data read API — Milestone 10 (frontend). Match/Competition/Team/Player
Centers need to browse fixtures, standings, teams, and players; nothing in the API surface
before this router exposed that (M2-M5 built the sports schema and ingestion pipeline, but only
admin-facing sync-trigger endpoints in apps/api/main.py ever touched it — see the M10 backend
audit). Read-only, `get_current_user`-gated with no role floor, matching the same "any
authenticated user" posture already established for prediction/market data (docs/rls.md §6a) —
this is reference/catalog data, not per-user-owned.

Composes existing M2 repositories directly (no new application service) — every method here is
already a well-formed atomic property table lookup with no ceremony to wrap; the only genuinely
new piece is `PlayerRepositoryPort.list_by_sport` (modules/sports/ports/repositories.py),
additive, mirroring `TeamRepositoryPort.list_by_sport`.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_monitoring_service, get_session
from modules.identity.domain.entities import User
from modules.ingestion.domain.value_objects import SyncStatus
from modules.sports.domain.entities import Competition, Fixture, Player, Season, Team
from modules.sports.domain.value_objects import (
    CompetitionId,
    FixtureId,
    FixtureStatus,
    PlayerId,
    SeasonStatus,
    SportCode,
    TeamId,
)
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyVenueRepository,
)

router = APIRouter(prefix="/api/v1/sports", tags=["sports"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _closeness_to_now(scheduled_at: datetime, now: datetime) -> float:
    """Absolute distance from `now`, in seconds. Sorting fixtures by this (ascending) surfaces
    whatever's happening soonest (an imminent kickoff) or most recently finished first, which is
    what a match feed's default "closest start" ordering should mean for a list that naturally
    mixes upcoming and just-finished fixtures — a plain chronological sort would otherwise bury
    next week's match under a fixture from three seasons ago (or vice versa, depending on
    direction). `scheduled_at` may be naive here (SQLite/aiosqlite drops tzinfo on read-back,
    docs/decisions.md ADR-007) — assumed to share `now`'s awareness before comparing."""
    aware_scheduled_at = scheduled_at if scheduled_at.tzinfo is not None else scheduled_at.replace(tzinfo=now.tzinfo)
    return abs((aware_scheduled_at - now).total_seconds())


def _parse_sport_code(value: str) -> SportCode:
    try:
        return SportCode(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized sport_code '{value}'") from None


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {label}: {value}") from None


def _parse_fixture_status(value: str) -> FixtureStatus:
    try:
        return FixtureStatus(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized status '{value}'") from None


def _parse_date_query(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {label}, expected YYYY-MM-DD: {value}") from None


def _fixture_in_date_range(scheduled_at: datetime, date_from: date | None, date_to: date | None, now: datetime) -> bool:
    """Inclusive day-range check against `scheduled_at`'s own tz (see `_closeness_to_now` for the
    same naive-datetime-from-SQLite caveat)."""
    aware_scheduled_at = scheduled_at if scheduled_at.tzinfo is not None else scheduled_at.replace(tzinfo=now.tzinfo)
    scheduled_date = aware_scheduled_at.astimezone(now.tzinfo).date()
    if date_from is not None and scheduled_date < date_from:
        return False
    if date_to is not None and scheduled_date > date_to:
        return False
    return True


async def _get_sport_or_404(session: AsyncSession, sport_code: str):
    sport = await SqlAlchemySportRepository(session=session).get_by_code(_parse_sport_code(sport_code))
    if sport is None:
        raise HTTPException(status_code=404, detail=f"sport '{sport_code}' not found")
    return sport


def _pick_current_season(seasons: list[Season]) -> Season | None:
    """Prefer the season marked ACTIVE; otherwise the most recently started one — there is no
    single authoritative "current season" flag in the schema, so this is a best-effort choice
    for "what should Match/Competition Center show by default," not a domain rule."""
    if not seasons:
        return None
    active = [s for s in seasons if s.status is SeasonStatus.ACTIVE]
    if active:
        return max(active, key=lambda s: s.date_range.start)
    return max(seasons, key=lambda s: s.date_range.start)


def _serialize_competition(c: Competition) -> dict:
    return {
        "id": str(c.id),
        "sport_code": None,  # filled by caller when the sport is already in scope
        "name": c.name,
        "type": c.type.value,
        "country": c.country,
        "tier": c.tier,
        "logo_url": c.logo_url,
    }


def _serialize_team_summary(t: Team, venue_name: str | None) -> dict:
    return {
        "id": str(t.id),
        "sport_code": None,
        "name": t.name,
        "short_name": t.short_name,
        "country": t.country,
        "venue_name": venue_name,
        "logo_url": t.logo_url,
    }


def _serialize_player_summary(p: Player, team_name: str | None) -> dict:
    return {
        "id": str(p.id),
        "sport_code": None,
        "name": p.name,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "position": p.position,
        "team_id": str(p.team_id) if p.team_id else None,
        "team_name": team_name,
    }


async def _serialize_fixture(session: AsyncSession, fixture: Fixture, competition: Competition | None) -> dict:
    teams = SqlAlchemyTeamRepository(session=session)
    venues = SqlAlchemyVenueRepository(session=session)
    home = await teams.get(fixture.home_team_id)
    away = await teams.get(fixture.away_team_id)
    venue = await venues.get(fixture.venue_id) if fixture.venue_id else None
    home_score, away_score = fixture.home_score, fixture.away_score
    sport = await SqlAlchemySportRepository(session=session).get(competition.sport_id) if competition else None
    return {
        "id": str(fixture.id),
        "season_id": str(fixture.season_id),
        "sport_code": sport.code.value if sport else None,
        "competition_id": str(competition.id) if competition else None,
        "competition_name": competition.name if competition else "Unknown",
        "competition_logo_url": competition.logo_url if competition else None,
        "competition_tier": competition.tier if competition else None,
        "home_team": (
            {"id": str(home.id), "name": home.name, "short_name": home.short_name, "logo_url": home.logo_url}
            if home else None
        ),
        "away_team": (
            {"id": str(away.id), "name": away.name, "short_name": away.short_name, "logo_url": away.logo_url}
            if away else None
        ),
        "venue_name": venue.name if venue else None,
        "scheduled_at": fixture.scheduled_at.isoformat(),
        "status": fixture.status.value,
        "final_state": (
            {"home": home_score, "away": away_score} if home_score is not None or away_score is not None else None
        ),
    }


# -- Competitions ------------------------------------------------------------------------------


@router.get("/{sport_code}/competitions")
async def list_competitions(
    sport_code: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    sport = await _get_sport_or_404(session, sport_code)
    competitions = await SqlAlchemyCompetitionRepository(session=session).list_by_sport(sport.id)
    data = [{**_serialize_competition(c), "sport_code": sport_code} for c in competitions]
    return envelope(data, meta={"count": len(data)})


@router.get("/competitions/{competition_id}")
async def get_competition(
    competition_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    competition = await SqlAlchemyCompetitionRepository(session=session).get(
        CompetitionId(_parse_uuid(competition_id, "competition_id"))
    )
    if competition is None:
        raise HTTPException(status_code=404, detail="competition not found")
    sport_repo = SqlAlchemySportRepository(session=session)
    sport = await sport_repo.get(competition.sport_id)
    return envelope({**_serialize_competition(competition), "sport_code": sport.code.value if sport else None})


@router.get("/competitions/{competition_id}/standings")
async def get_competition_standings(
    competition_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    cid = CompetitionId(_parse_uuid(competition_id, "competition_id"))
    seasons = await SqlAlchemySeasonRepository(session=session).list_by_competition(cid)
    season = _pick_current_season(seasons)
    if season is None:
        return envelope([], meta={"season_id": None})

    standings = await SqlAlchemyStandingRepository(session=session).list_by_season(season.id)
    teams = SqlAlchemyTeamRepository(session=session)
    rows = []
    for standing in sorted(standings, key=lambda s: s.rank):
        team = await teams.get(standing.team_id)
        rows.append(
            {
                "team_id": str(standing.team_id),
                "team_name": team.name if team else "Unknown",
                "rank": standing.rank,
                "points": standing.points,
                "record": standing.record,
            }
        )
    return envelope(rows, meta={"season_id": str(season.id)})


@router.get("/competitions/{competition_id}/fixtures")
async def get_competition_fixtures(
    competition_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    cid = CompetitionId(_parse_uuid(competition_id, "competition_id"))
    competition = await SqlAlchemyCompetitionRepository(session=session).get(cid)
    if competition is None:
        raise HTTPException(status_code=404, detail="competition not found")

    seasons = await SqlAlchemySeasonRepository(session=session).list_by_competition(cid)
    season = _pick_current_season(seasons)
    if season is None:
        return envelope([], meta={"count": 0})

    fixtures = await SqlAlchemyFixtureRepository(session=session).list_by_season(season.id)
    now = _now()
    fixtures = sorted(fixtures, key=lambda f: _closeness_to_now(f.scheduled_at, now))[:limit]
    data = [await _serialize_fixture(session, f, competition) for f in fixtures]
    return envelope(data, meta={"count": len(data), "season_id": str(season.id)})


# -- Teams --------------------------------------------------------------------------------------


@router.get("/{sport_code}/teams")
async def list_teams(sport_code: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    sport = await _get_sport_or_404(session, sport_code)
    teams = await SqlAlchemyTeamRepository(session=session).list_by_sport(sport.id)
    venues = SqlAlchemyVenueRepository(session=session)
    data = []
    for team in teams:
        venue = await venues.get(team.venue_id) if team.venue_id else None
        data.append({**_serialize_team_summary(team, venue.name if venue else None), "sport_code": sport_code})
    return envelope(data, meta={"count": len(data)})


@router.get("/teams/{team_id}")
async def get_team(team_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    venue = await SqlAlchemyVenueRepository(session=session).get(team.venue_id) if team.venue_id else None
    sport = await SqlAlchemySportRepository(session=session).get(team.sport_id)
    return envelope({**_serialize_team_summary(team, venue.name if venue else None), "sport_code": sport.code.value if sport else None})


@router.get("/teams/{team_id}/players")
async def get_team_players(team_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    players = await SqlAlchemyPlayerRepository(session=session).list_by_team(tid)
    data = [_serialize_player_summary(p, team.name) for p in players]
    return envelope(data, meta={"count": len(data)})


@router.get("/teams/{team_id}/fixtures")
async def get_team_fixtures(
    team_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    when: str = Query(default="recent", pattern="^(recent|upcoming)$"),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    fixture_repo = SqlAlchemyFixtureRepository(session=session)
    fixtures = (
        await fixture_repo.list_recent_by_team(tid, _now(), limit=limit)
        if when == "recent"
        else await fixture_repo.list_upcoming_by_team(tid, _now(), limit=limit)
    )

    competitions = SqlAlchemyCompetitionRepository(session=session)
    seasons = SqlAlchemySeasonRepository(session=session)
    data = []
    for fixture in fixtures:
        season = await seasons.get(fixture.season_id)
        competition = await competitions.get(season.competition_id) if season else None
        data.append(await _serialize_fixture(session, fixture, competition))
    return envelope(data, meta={"count": len(data)})


_TEAM_STATISTIC_KEYS = (
    "possession_pct",
    "shots_total",
    "shots_on_target",
    "corners",
    "fouls",
    "cards_yellow",
    "cards_red",
)


@router.get("/teams/{team_id}/statistics")
async def get_team_statistics(
    team_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Averages real per-match `TeamStatistics.stat_set` rows (`list_recent_by_team`, already
    populated by the API-Football stat sync — see composition.py) over the team's most recent
    matches. Never fabricated: a key with zero recorded samples across the window comes back
    `null`, and `sample_size` always reports how many matches actually had *any* stats recorded,
    so the frontend can show honest coverage instead of implying a full-season average."""
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")

    rows = await SqlAlchemyTeamStatisticsRepository(session=session).list_recent_by_team(tid, _now(), limit=limit)

    sums: dict[str, float] = {key: 0.0 for key in _TEAM_STATISTIC_KEYS}
    counts: dict[str, int] = {key: 0 for key in _TEAM_STATISTIC_KEYS}
    for row in rows:
        for key in _TEAM_STATISTIC_KEYS:
            value = row.stat_set.get(key)
            if value is None:
                continue
            sums[key] += float(value)
            counts[key] += 1

    averages = {key: (sums[key] / counts[key] if counts[key] > 0 else None) for key in _TEAM_STATISTIC_KEYS}
    return envelope({"sample_size": len(rows), **averages})


# -- Players ------------------------------------------------------------------------------------


@router.get("/{sport_code}/players")
async def list_players(
    sport_code: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    sport = await _get_sport_or_404(session, sport_code)
    players = await SqlAlchemyPlayerRepository(session=session).list_by_sport(sport.id, limit=limit)
    teams = SqlAlchemyTeamRepository(session=session)
    data = []
    for player in players:
        team = await teams.get(player.team_id) if player.team_id else None
        data.append({**_serialize_player_summary(player, team.name if team else None), "sport_code": sport_code})
    return envelope(data, meta={"count": len(data)})


@router.get("/players/{player_id}")
async def get_player(player_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    pid = PlayerId(_parse_uuid(player_id, "player_id"))
    player = await SqlAlchemyPlayerRepository(session=session).get(pid)
    if player is None:
        raise HTTPException(status_code=404, detail="player not found")
    team = await SqlAlchemyTeamRepository(session=session).get(player.team_id) if player.team_id else None
    sport = await SqlAlchemySportRepository(session=session).get(player.sport_id)
    return envelope({**_serialize_player_summary(player, team.name if team else None), "sport_code": sport.code.value if sport else None})


# -- Fixtures (cross-competition browse + single lookup) ----------------------------------------


@router.get("/fixtures/{fixture_id}")
async def get_fixture(fixture_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    fid = _parse_uuid(fixture_id, "fixture_id")
    fixture = await SqlAlchemyFixtureRepository(session=session).get(FixtureId(fid))
    if fixture is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    season = await SqlAlchemySeasonRepository(session=session).get(fixture.season_id)
    competition = await SqlAlchemyCompetitionRepository(session=session).get(season.competition_id) if season else None
    return envelope(await _serialize_fixture(session, fixture, competition))


@router.get("/fixtures/{fixture_id}/statistics")
async def get_fixture_statistics(
    fixture_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user),
):
    """Real per-fixture team stats (Milestone 9.3 "AI Match Snapshot") — genuinely different from
    `/teams/{id}/statistics` above, which is a rolling-window average across recent matches. This
    reads the exact `TeamStatistics` row(s) recorded for one specific completed match, via the
    `SqlAlchemyMatchRepository.get_by_fixture` -> `SqlAlchemyTeamStatisticsRepository.list_by_match`
    pair (both pre-existing, never previously wired to a route). Coverage is honestly sparse today
    (the sync job isn't on the Celery beat schedule yet) — a fixture with no `Match` row yet, or a
    `Match` with zero synced stat rows, both return an empty list, never a fabricated stat."""
    fid = _parse_uuid(fixture_id, "fixture_id")
    match = await SqlAlchemyMatchRepository(session=session).get_by_fixture(FixtureId(fid))
    if match is None:
        return envelope(data=[])
    stats = await SqlAlchemyTeamStatisticsRepository(session=session).list_by_match(match.id)
    return envelope(data=[{"team_id": str(s.team_id.value), "stats": s.stat_set} for s in stats])


@router.get("/{sport_code}/fixtures")
async def list_sport_fixtures(
    sport_code: str,
    competition_id: str | None = Query(default=None),
    status: str | None = Query(default=None, description="scheduled | live | completed | postponed | cancelled"),
    date_from: str | None = Query(default=None, description="Inclusive, YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="Inclusive, YYYY-MM-DD"),
    search: str | None = Query(default=None, description="Matches home/away team name or competition name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Cross-competition fixture browse for Match Center's default view and the Matches/Live
    discovery pages. Bounded N+1 (competitions -> current season -> fixtures) rather than a single
    join — acceptable at this data volume, matching the naive-composition style already used
    elsewhere (e.g. SemanticSearchService), and a caller can always scope down via
    `competition_id` to avoid it. `status`/`date_from`/`date_to` filter in-memory on the already
    -fetched season fixtures for the same reason; `meta.total` reflects the true filtered count
    (pre-pagination) so callers can build real "N of M" / has-more UI."""
    sport = await _get_sport_or_404(session, sport_code)
    competitions_repo = SqlAlchemyCompetitionRepository(session=session)
    seasons_repo = SqlAlchemySeasonRepository(session=session)
    fixtures_repo = SqlAlchemyFixtureRepository(session=session)

    if competition_id is not None:
        competitions = [await competitions_repo.get(CompetitionId(_parse_uuid(competition_id, "competition_id")))]
        competitions = [c for c in competitions if c is not None]
    else:
        competitions = await competitions_repo.list_by_sport(sport.id)

    # Every season across a competition's history, not just the "current" one — this schema has
    # no authoritative season-closed flag (dev data even has every season marked ACTIVE), so
    # scoping to one picked season would silently hide real completed fixtures that live in an
    # older season. The fixture's own `status`/`scheduled_at` are the real source of truth for
    # filtering below, not which season it happens to belong to.
    all_fixtures: list[tuple[Fixture, Competition]] = []
    for competition in competitions:
        seasons = await seasons_repo.list_by_competition(competition.id)
        for season in seasons:
            fixtures = await fixtures_repo.list_by_season(season.id)
            all_fixtures.extend((f, competition) for f in fixtures)

    parsed_status = _parse_fixture_status(status) if status is not None else None
    if parsed_status is not None:
        all_fixtures = [(f, c) for f, c in all_fixtures if f.status is parsed_status]

    parsed_date_from = _parse_date_query(date_from, "date_from") if date_from is not None else None
    parsed_date_to = _parse_date_query(date_to, "date_to") if date_to is not None else None
    now = _now()
    if parsed_date_from is not None or parsed_date_to is not None:
        all_fixtures = [
            (f, c) for f, c in all_fixtures if _fixture_in_date_range(f.scheduled_at, parsed_date_from, parsed_date_to, now)
        ]

    all_fixtures.sort(key=lambda pair: _closeness_to_now(pair[0].scheduled_at, now))

    if search:
        needle = search.strip().lower()
        teams_repo = SqlAlchemyTeamRepository(session=session)
        matched: list[tuple[Fixture, Competition]] = []
        for f, c in all_fixtures:
            home = await teams_repo.get(f.home_team_id)
            away = await teams_repo.get(f.away_team_id)
            haystack = " ".join(
                part for part in (home.name if home else None, away.name if away else None, c.name) if part
            ).lower()
            if needle in haystack:
                matched.append((f, c))
        all_fixtures = matched

    total = len(all_fixtures)
    page = all_fixtures[offset : offset + limit]
    data = await asyncio.gather(*(_serialize_fixture(session, f, c) for f, c in page))
    return envelope(
        list(data),
        meta={"count": len(data), "total": total, "offset": offset, "limit": limit, "has_more": offset + limit < total},
    )


@router.get("/sync-status")
async def get_platform_sync_status(
    session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user),
):
    """A regular-user-safe sliver of `MonitoringService.sync_status` (Milestone 5, otherwise
    admin-only under `/api/v1/admin/sync/status`): just the most recent successful-or-partial
    provider sync timestamp, with no per-run error messages or operational detail. Exists because
    Mission Control's Hero needs an honest "last synced" reading rather than deriving one from
    unrelated content timestamps (e.g. a fixture's future kickoff time)."""
    monitoring = build_monitoring_service(session)
    runs = await monitoring.sync_status(limit=50)
    completed = [r for r in runs if r.status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)]
    last_synced_at = max((r.started_at for r in completed), default=None)
    return envelope(data={"last_synced_at": last_synced_at.isoformat() if last_synced_at else None})

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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import get_session
from modules.identity.domain.entities import User
from modules.sports.domain.entities import Competition, Fixture, Player, Season, Team
from modules.sports.domain.value_objects import (
    CompetitionId,
    FixtureId,
    PlayerId,
    SeasonStatus,
    SportCode,
    TeamId,
)
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyVenueRepository,
)

router = APIRouter(prefix="/api/v1/sports", tags=["sports"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    }


def _serialize_team_summary(t: Team, venue_name: str | None) -> dict:
    return {
        "id": str(t.id),
        "sport_code": None,
        "name": t.name,
        "short_name": t.short_name,
        "country": t.country,
        "venue_name": venue_name,
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


async def _serialize_fixture(session: AsyncSession, fixture: Fixture, competition_name: str) -> dict:
    teams = SqlAlchemyTeamRepository(session=session)
    venues = SqlAlchemyVenueRepository(session=session)
    home = await teams.get(fixture.home_team_id)
    away = await teams.get(fixture.away_team_id)
    venue = await venues.get(fixture.venue_id) if fixture.venue_id else None
    return {
        "id": str(fixture.id),
        "season_id": str(fixture.season_id),
        "competition_name": competition_name,
        "home_team": {"id": str(home.id), "name": home.name, "short_name": home.short_name} if home else None,
        "away_team": {"id": str(away.id), "name": away.name, "short_name": away.short_name} if away else None,
        "venue_name": venue.name if venue else None,
        "scheduled_at": fixture.scheduled_at.isoformat(),
        "status": fixture.status.value,
        "final_state": None,
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
    fixtures = sorted(fixtures, key=lambda f: f.scheduled_at, reverse=True)[:limit]
    data = [await _serialize_fixture(session, f, competition.name) for f in fixtures]
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
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    fixtures = await SqlAlchemyFixtureRepository(session=session).list_recent_by_team(tid, _now(), limit=limit)

    competitions = SqlAlchemyCompetitionRepository(session=session)
    seasons = SqlAlchemySeasonRepository(session=session)
    data = []
    for fixture in fixtures:
        season = await seasons.get(fixture.season_id)
        competition = await competitions.get(season.competition_id) if season else None
        data.append(await _serialize_fixture(session, fixture, competition.name if competition else "Unknown"))
    return envelope(data, meta={"count": len(data)})


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
    return envelope(await _serialize_fixture(session, fixture, competition.name if competition else "Unknown"))


@router.get("/{sport_code}/fixtures")
async def list_sport_fixtures(
    sport_code: str,
    competition_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Cross-competition fixture browse for Match Center's default view. Bounded N+1 (competitions
    -> current season -> fixtures) rather than a single join — acceptable at this data volume,
    matching the naive-composition style already used elsewhere (e.g. SemanticSearchService), and
    a caller can always scope down via `competition_id` to avoid it."""
    sport = await _get_sport_or_404(session, sport_code)
    competitions_repo = SqlAlchemyCompetitionRepository(session=session)
    seasons_repo = SqlAlchemySeasonRepository(session=session)
    fixtures_repo = SqlAlchemyFixtureRepository(session=session)

    if competition_id is not None:
        competitions = [await competitions_repo.get(CompetitionId(_parse_uuid(competition_id, "competition_id")))]
        competitions = [c for c in competitions if c is not None]
    else:
        competitions = await competitions_repo.list_by_sport(sport.id)

    all_fixtures: list[tuple[Fixture, str]] = []
    for competition in competitions:
        seasons = await seasons_repo.list_by_competition(competition.id)
        season = _pick_current_season(seasons)
        if season is None:
            continue
        fixtures = await fixtures_repo.list_by_season(season.id)
        all_fixtures.extend((f, competition.name) for f in fixtures)

    all_fixtures.sort(key=lambda pair: pair[0].scheduled_at, reverse=True)
    all_fixtures = all_fixtures[:limit]
    data = await asyncio.gather(*(_serialize_fixture(session, f, name) for f, name in all_fixtures))
    return envelope(list(data), meta={"count": len(data)})

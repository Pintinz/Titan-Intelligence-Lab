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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_identity_service, build_monitoring_service, get_session
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Role
from modules.ingestion.domain.value_objects import SyncStatus
from modules.sports.domain.entities import CoachingStaffMember, Competition, Fixture, Injury, Lineup, Player, Season, Team, Transfer
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
    SqlAlchemyCoachingStaffRepository,
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyInjuryRepository,
    SqlAlchemyLineupRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyTransferRepository,
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


async def require_football_or_admin(
    request: Request, sport_code: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
) -> User:
    """Basketball/Baseball/Table Tennis are still under active development — real users only get
    Football; anything else 404s for them exactly like a sport that doesn't exist, rather than a
    403 that would confirm the other sports are there but locked. Administrators pass through
    unrestricted so the team can keep building/QA-ing the other sports against the real API.
    Denials are recorded to the audit trail, same posture and pattern as `require_role`
    (auth_deps.py) — including the same explicit commit, since the HTTPException below would
    otherwise skip `get_session`'s normal commit-on-clean-exit and silently roll the write back.

    A genuinely unrecognized sport_code (not one of the 4 real SportCode values) still reaches
    the handler's own `_parse_sport_code`/`_get_sport_or_404` and gets its normal 422/404 — this
    dependency only gates codes that ARE real sports, so a malformed request keeps reading as a
    validation error, not as "sport exists but is locked" for a sport that doesn't exist at all."""
    is_real_non_football_sport = sport_code in (SportCode.BASKETBALL.value, SportCode.BASEBALL.value, SportCode.TABLE_TENNIS.value)
    if is_real_non_football_sport and not user.is_at_least(Role.ADMINISTRATOR):
        identity_service = build_identity_service(session)
        await identity_service.record_permission_denied(
            user.id,
            datetime.now(timezone.utc),
            target_type="route",
            target_id=request.url.path,
            metadata={"sport_code": sport_code, "actual_role": user.role.value, "method": request.method},
        )
        await session.commit()
        raise HTTPException(status_code=404, detail=f"sport '{sport_code}' not found")
    return user


async def _pick_current_season(session: AsyncSession, seasons: list[Season]) -> Season | None:
    """Prefer the ACTIVE season with the most fixtures, breaking ties by the latest start date —
    over the schema's lifetime, a fixture-schedule sync (or a standings bootstrap) can create a
    new season row for a year that hasn't kicked off yet, well before any of its real fixtures
    exist, and (audit fix, 2026-08-21) a competition can also end up with more than one ACTIVE
    season row carrying real but partial data (e.g. a single team's away-leg fixtures restored
    into their own season row) — picking purely by latest start date among ACTIVE seasons favors
    either an empty stub or a sparse partial season over the one with the fuller, real dataset.
    There is still no single authoritative "current season" flag in the schema, so this stays a
    best-effort choice for "what should Match/Competition Center show by default," not a domain
    rule — falling back to the latest-by-date season when none of them have fixtures yet, since a
    genuinely new, fixture-less season is still the right thing to show once it IS the newest."""
    if not seasons:
        return None
    active = [s for s in seasons if s.status is SeasonStatus.ACTIVE]
    candidates = active or seasons
    fixture_repo = SqlAlchemyFixtureRepository(session=session)
    counts = {season.id: len(await fixture_repo.list_by_season(season.id)) for season in candidates}
    if not any(counts.values()):
        return sorted(candidates, key=lambda s: s.date_range.start, reverse=True)[0]
    return max(candidates, key=lambda s: (counts[s.id], s.date_range.start))


async def _resolve_requested_season(
    session: AsyncSession, seasons: list[Season], season_id: str | None
) -> Season | None:
    """Powers the season filter on the competition detail page: an explicit `season_id` pins the
    response to that exact season (404 if it isn't one of this competition's own), otherwise
    falls back to `_pick_current_season`'s best-effort default."""
    if season_id is None:
        return await _pick_current_season(session, seasons)
    season = next((s for s in seasons if str(s.id) == season_id), None)
    if season is None:
        raise HTTPException(status_code=404, detail="season not found for this competition")
    return season


def _serialize_season(s: Season) -> dict:
    return {
        "id": str(s.id),
        "label": s.label,
        "start_date": s.date_range.start.isoformat() if s.date_range and s.date_range.start else None,
        "status": s.status.value,
    }


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


def _serialize_injury(injury: Injury, player_name: str | None) -> dict:
    return {
        "id": str(injury.id),
        "player_id": str(injury.player_id),
        "player_name": player_name,
        "status": injury.status,
        "reason": injury.reason,
        "reported_at": injury.reported_at.isoformat(),
        "expected_return": injury.expected_return.isoformat() if injury.expected_return else None,
    }


def _serialize_lineup(lineup: Lineup, player_names: dict) -> dict:
    return {
        "id": str(lineup.id),
        "team_id": str(lineup.team_id),
        "formation": lineup.formation,
        "starters": [
            {
                "player_id": str(slot.player_id), "player_name": player_names.get(str(slot.player_id)),
                "position": slot.position, "shirt_number": slot.shirt_number,
            }
            for slot in lineup.starters()
        ],
        "substitutes": [
            {
                "player_id": str(slot.player_id), "player_name": player_names.get(str(slot.player_id)),
                "position": slot.position, "shirt_number": slot.shirt_number,
            }
            for slot in lineup.substitutes()
        ],
        "availability_classification": lineup.availability_classification,
        "information_available_at": lineup.information_available_at.isoformat() if lineup.information_available_at else None,
    }


def _serialize_transfer(
    transfer: Transfer, player_name: str | None, from_team_name: str | None, to_team_name: str | None
) -> dict:
    return {
        "id": str(transfer.id),
        "player_id": str(transfer.player_id),
        "player_name": player_name,
        "from_team_id": str(transfer.from_team_id) if transfer.from_team_id else None,
        "from_team_name": from_team_name,
        "to_team_id": str(transfer.to_team_id) if transfer.to_team_id else None,
        "to_team_name": to_team_name,
        "effective_date": transfer.effective_date.isoformat(),
        "transfer_type": transfer.transfer_type,
    }


def _serialize_coach(coach: CoachingStaffMember) -> dict:
    return {
        "id": str(coach.id),
        "team_id": str(coach.team_id) if coach.team_id else None,
        "person_name": coach.person_name,
        "role": coach.role,
        "valid_from": coach.valid_from.isoformat() if coach.valid_from else None,
        "valid_to": coach.valid_to.isoformat() if coach.valid_to else None,
    }


async def _fixture_stats(session: AsyncSession, fixture: Fixture) -> dict | None:
    """Real match-level statistics (possession/shots/corners/fouls/cards) when they exist —
    `None` when they don't, never a fabricated placeholder. Coverage is genuinely partial today
    (every English League Two fixture has it; most Premier League/DFB-Pokal history doesn't,
    since these are only ever written when a provider or historical source actually reports
    them — see backend/docs/post_m24_phase9_training_readiness_report.md's team_statistics
    coverage findings), so callers must treat this as optional."""
    if fixture.status is not FixtureStatus.COMPLETED:
        return None
    match = await SqlAlchemyMatchRepository(session=session).get_by_fixture(fixture.id)
    if match is None:
        return None
    rows = await SqlAlchemyTeamStatisticsRepository(session=session).list_by_match(match.id)
    if not rows:
        return None
    home_row = next((r for r in rows if r.team_id == fixture.home_team_id), None)
    away_row = next((r for r in rows if r.team_id == fixture.away_team_id), None)
    if home_row is None and away_row is None:
        return None
    return {
        "home": home_row.stat_set if home_row else None,
        "away": away_row.stat_set if away_row else None,
    }


async def _serialize_fixture(session: AsyncSession, fixture: Fixture, competition: Competition | None) -> dict:
    teams = SqlAlchemyTeamRepository(session=session)
    venues = SqlAlchemyVenueRepository(session=session)
    home = await teams.get(fixture.home_team_id)
    away = await teams.get(fixture.away_team_id)
    venue = await venues.get(fixture.venue_id) if fixture.venue_id else None
    home_score, away_score = fixture.home_score, fixture.away_score
    sport = await SqlAlchemySportRepository(session=session).get(competition.sport_id) if competition else None
    stats = await _fixture_stats(session, fixture)
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
        "period_scores": fixture.period_scores,
        "stats": stats,
    }


# -- Competitions ------------------------------------------------------------------------------


@router.get("/{sport_code}/competitions")
async def list_competitions(
    sport_code: str, session: AsyncSession = Depends(get_session), _user: User = Depends(require_football_or_admin)
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
    competition_id: str,
    season_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    cid = CompetitionId(_parse_uuid(competition_id, "competition_id"))
    seasons = await SqlAlchemySeasonRepository(session=session).list_by_competition(cid)
    season = await _resolve_requested_season(session, seasons, season_id)
    if season is None:
        return envelope([], meta={"season_id": None})

    standings = await SqlAlchemyStandingRepository(session=session).list_by_season(season.id)
    # Standings are point-in-time snapshots — a resync never updates a row in place, it inserts a
    # fresh one (see EntityReconciliationService.reconcile_standing), so a season with more than
    # one sync run accumulates multiple rows per team. Keep only each team's most recent snapshot.
    latest_by_team: dict = {}
    for standing in standings:
        current = latest_by_team.get(standing.team_id)
        if current is None or standing.snapshot_at > current.snapshot_at:
            latest_by_team[standing.team_id] = standing
    teams = SqlAlchemyTeamRepository(session=session)
    rows = []
    for standing in sorted(latest_by_team.values(), key=lambda s: s.rank):
        team = await teams.get(standing.team_id)
        # A standing whose team_id no longer resolves (e.g. a stale snapshot surviving a team
        # merge/dedup that never repointed it) has nothing honest to show — "Unknown" was a
        # placeholder, not a real team, and displaying it as a table row misrepresents the
        # competition's real roster. Drop it, matching sportsApi.competitionFixtures's own
        # withResolvedTeams precedent on the frontend for the identical failure mode.
        if team is None:
            continue
        rows.append(
            {
                "team_id": str(standing.team_id),
                "team_name": team.name,
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
    season_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    cid = CompetitionId(_parse_uuid(competition_id, "competition_id"))
    competition = await SqlAlchemyCompetitionRepository(session=session).get(cid)
    if competition is None:
        raise HTTPException(status_code=404, detail="competition not found")

    seasons = await SqlAlchemySeasonRepository(session=session).list_by_competition(cid)
    season = await _resolve_requested_season(session, seasons, season_id)
    if season is None:
        return envelope([], meta={"count": 0})

    fixtures = await SqlAlchemyFixtureRepository(session=session).list_by_season(season.id)
    now = _now()
    fixtures = sorted(fixtures, key=lambda f: _closeness_to_now(f.scheduled_at, now))[:limit]
    data = [await _serialize_fixture(session, f, competition) for f in fixtures]
    return envelope(data, meta={"count": len(data), "season_id": str(season.id)})


@router.get("/competitions/{competition_id}/seasons")
async def list_competition_seasons(
    competition_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    """Every season TitanIQ has a record for under this competition, most recent first — lets a
    caller (e.g. the Completed Matches browser) jump straight to a specific season's fixtures via
    `list_sport_fixtures(season_id=...)` instead of paging through newer seasons first."""
    cid = CompetitionId(_parse_uuid(competition_id, "competition_id"))
    competition = await SqlAlchemyCompetitionRepository(session=session).get(cid)
    if competition is None:
        raise HTTPException(status_code=404, detail="competition not found")
    seasons = await SqlAlchemySeasonRepository(session=session).list_by_competition(cid)
    data = [_serialize_season(s) for s in sorted(seasons, key=lambda s: s.date_range.start, reverse=True)]
    return envelope(data, meta={"count": len(data)})


# -- Teams --------------------------------------------------------------------------------------


@router.get("/{sport_code}/teams")
async def list_teams(sport_code: str, session: AsyncSession = Depends(get_session), _user: User = Depends(require_football_or_admin)):
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


@router.get("/teams/{team_id}/injuries")
async def get_team_injuries(team_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Every player on this team's roster with a currently-reported injury — an empty list is
    the honest, common case (most teams have no reported injuries at any given moment), never
    an error. See ``Injury``'s own docstring for why no expected-return date is fabricated."""
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    players_repo = SqlAlchemyPlayerRepository(session=session)
    injuries = await SqlAlchemyInjuryRepository(session=session).list_current_by_team(tid)
    data = []
    for injury in injuries:
        player = await players_repo.get(injury.player_id)
        data.append(_serialize_injury(injury, player.name if player else None))
    return envelope(data, meta={"count": len(data)})


@router.get("/teams/{team_id}/transfers")
async def get_team_transfers(team_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Confirmed transfers in and out of this team, most recent first — see ``Transfer``'s own
    docstring for why there is no rumour/negotiating staging here."""
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    players_repo = SqlAlchemyPlayerRepository(session=session)
    teams_repo = SqlAlchemyTeamRepository(session=session)
    transfers = await SqlAlchemyTransferRepository(session=session).list_by_team(tid)
    data = []
    for transfer in transfers:
        player = await players_repo.get(transfer.player_id)
        from_team = await teams_repo.get(transfer.from_team_id) if transfer.from_team_id else None
        to_team = await teams_repo.get(transfer.to_team_id) if transfer.to_team_id else None
        data.append(_serialize_transfer(
            transfer, player.name if player else None,
            from_team.name if from_team else None, to_team.name if to_team else None,
        ))
    return envelope(data, meta={"count": len(data)})


@router.get("/teams/{team_id}/coaching-staff")
async def get_team_coaching_staff(team_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    """Current head coach/manager plus full history, most recent first — a closed-out
    (``valid_to`` set) predecessor is never overwritten, only superseded by a new row."""
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    staff = await SqlAlchemyCoachingStaffRepository(session=session).list_by_team(tid)
    data = [_serialize_coach(s) for s in staff]
    current = next((s for s in staff if s.valid_to is None), None)
    return envelope(data, meta={"count": len(data), "current_coach_id": str(current.id) if current else None})


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


# Per-sport `TeamStatistics.stat_set` key vocabularies — each adapter (api_sports_adapter.py)
# persists a different shape, so this endpoint can't average one fixed key set across sports
# (audit fix 2026-08-10: this previously silently ignored every basketball/baseball key).
_TEAM_STATISTIC_KEYS_BY_SPORT: dict[str, tuple[str, ...]] = {
    "football": ("possession_pct", "shots_total", "shots_on_target", "corners", "fouls", "cards_yellow", "cards_red"),
    "basketball": (
        "points", "field_goals_made", "field_goals_attempted", "three_pointers_made", "three_pointers_attempted",
        "free_throws_made", "free_throws_attempted", "rebounds_total", "rebounds_offensive", "rebounds_defensive",
        "assists", "steals", "blocks", "turnovers", "personal_fouls",
    ),
    "baseball": ("runs", "hits", "errors"),
}
_DEFAULT_TEAM_STATISTIC_KEYS = _TEAM_STATISTIC_KEYS_BY_SPORT["football"]


@router.get("/teams/{team_id}/statistics")
async def get_team_statistics(
    team_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Averages real per-match `TeamStatistics.stat_set` rows (`list_recent_by_team`, already
    populated by each sport's stat sync — see composition.py) over the team's most recent
    matches. Never fabricated: a key with zero recorded samples across the window comes back
    `null`, and `sample_size` always reports how many matches actually had *any* stats recorded,
    so the frontend can show honest coverage instead of implying a full-season average. Which
    keys get averaged is sport-aware (`_TEAM_STATISTIC_KEYS_BY_SPORT`), since basketball/baseball
    `stat_set` rows use entirely different field names than football's."""
    tid = TeamId(_parse_uuid(team_id, "team_id"))
    team = await SqlAlchemyTeamRepository(session=session).get(tid)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    sport = await SqlAlchemySportRepository(session=session).get(team.sport_id)
    stat_keys = _TEAM_STATISTIC_KEYS_BY_SPORT.get(sport.code.value if sport else "", _DEFAULT_TEAM_STATISTIC_KEYS)

    rows = await SqlAlchemyTeamStatisticsRepository(session=session).list_recent_by_team(tid, _now(), limit=limit)

    sums: dict[str, float] = {key: 0.0 for key in stat_keys}
    counts: dict[str, int] = {key: 0 for key in stat_keys}
    for row in rows:
        for key in stat_keys:
            value = row.stat_set.get(key)
            if value is None:
                continue
            sums[key] += float(value)
            counts[key] += 1

    averages = {key: (sums[key] / counts[key] if counts[key] > 0 else None) for key in stat_keys}
    return envelope({"sample_size": len(rows), **averages})


# -- Players ------------------------------------------------------------------------------------


@router.get("/{sport_code}/players")
async def list_players(
    sport_code: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_football_or_admin),
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


@router.get("/players/{player_id}/injuries")
async def get_player_injuries(player_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    pid = PlayerId(_parse_uuid(player_id, "player_id"))
    player = await SqlAlchemyPlayerRepository(session=session).get(pid)
    if player is None:
        raise HTTPException(status_code=404, detail="player not found")
    injuries = await SqlAlchemyInjuryRepository(session=session).list_by_player(pid)
    data = [_serialize_injury(injury, player.name) for injury in injuries]
    return envelope(data, meta={"count": len(data)})


@router.get("/players/{player_id}/transfers")
async def get_player_transfers(player_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    pid = PlayerId(_parse_uuid(player_id, "player_id"))
    player = await SqlAlchemyPlayerRepository(session=session).get(pid)
    if player is None:
        raise HTTPException(status_code=404, detail="player not found")
    teams_repo = SqlAlchemyTeamRepository(session=session)
    transfers = await SqlAlchemyTransferRepository(session=session).list_by_player(pid)
    data = []
    for transfer in transfers:
        from_team = await teams_repo.get(transfer.from_team_id) if transfer.from_team_id else None
        to_team = await teams_repo.get(transfer.to_team_id) if transfer.to_team_id else None
        data.append(_serialize_transfer(
            transfer, player.name, from_team.name if from_team else None, to_team.name if to_team else None,
        ))
    return envelope(data, meta={"count": len(data)})


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


@router.get("/fixtures/{fixture_id}/lineups")
async def get_fixture_lineups(
    fixture_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user),
):
    """Phase 3 audit fix — `reconcile_lineup`/`SqlAlchemyLineupRepository` have been real and
    fully wired into the sync/reconciliation path since Milestone 5, but nothing ever read the
    data back out via any endpoint. Same `Match` resolution pattern as `/fixtures/{id}/statistics`
    above — `Lineup.match_id` is a `Match` id, not the fixture id directly. Coverage is honestly
    sparse today (`sync_lineups` only fires for football/EPL fixtures inside a pre-kickoff
    window — see `beat_schedule.py`), so a fixture with no synced lineup yet returns an empty
    list, never a fabricated one. `EXPECTED_LINEUP` vs `CONFIRMED_LINEUP` distinction is carried
    honestly via `availability_classification` (`VERIFIED_PRE_MATCH` vs `UNKNOWN_AVAILABILITY_TIME`)
    rather than guessed from timing alone."""
    fid = _parse_uuid(fixture_id, "fixture_id")
    match = await SqlAlchemyMatchRepository(session=session).get_by_fixture(FixtureId(fid))
    if match is None:
        return envelope(data=[])
    lineups = await SqlAlchemyLineupRepository(session=session).list_by_match(match.id)
    players_repo = SqlAlchemyPlayerRepository(session=session)
    data = []
    for lineup in lineups:
        player_names = {}
        for slot in lineup.slots:
            player = await players_repo.get(slot.player_id)
            if player is not None:
                player_names[str(slot.player_id)] = player.name
        data.append(_serialize_lineup(lineup, player_names))
    return envelope(data, meta={"count": len(data)})


@router.get("/{sport_code}/fixtures")
async def list_sport_fixtures(
    sport_code: str,
    competition_id: str | None = Query(default=None),
    season_id: str | None = Query(default=None, description="Restrict to one season, e.g. picked from list_competition_seasons"),
    status: str | None = Query(default=None, description="scheduled | live | completed | postponed | cancelled"),
    date_from: str | None = Query(default=None, description="Inclusive, YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="Inclusive, YYYY-MM-DD"),
    search: str | None = Query(default=None, description="Matches home/away team name or competition name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_football_or_admin),
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

    if season_id is not None:
        parsed_season_id = _parse_uuid(season_id, "season_id")
        all_fixtures = [(f, c) for f, c in all_fixtures if f.season_id.value == parsed_season_id]

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

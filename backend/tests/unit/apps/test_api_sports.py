import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator
from modules.ingestion.domain.entities import SyncRun
from modules.ingestion.domain.value_objects import EntityKind as IngestionEntityKind, SyncRunId, SyncStatus, SyncTrigger
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.ingestion.infrastructure.persistence.repositories import SqlAlchemySyncRunRepository
from modules.sports.domain.entities import (
    CoachingStaffMember,
    Competition,
    Fixture,
    Injury,
    Lineup,
    LineupSlot,
    Match,
    Player,
    Season,
    Sport,
    Standing,
    Team,
    TeamStatistics,
    Transfer,
    Venue,
)
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    DateRange,
    EntityId,
    FixtureId,
    FixtureStatus,
    LineupId,
    LineupRole,
    MatchId,
    PlayerId,
    SeasonId,
    SeasonStatus,
    SportCode,
    SportId,
    TeamId,
    VenueId,
)
from modules.sports.infrastructure.persistence.models import Base as SportsBase
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

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "sports": None, "ingestion": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(SportsBase.metadata.create_all)
        await conn.run_sync(IngestionBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    email, password = "sports-user@example.com", "correct-horse-battery"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


@pytest.fixture
def admin_headers(client, db_session_factory):
    email, password = "sports-admin@example.com", "correct-horse-battery"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})

    async def _promote():
        async with db_session_factory() as session:
            users = SqlAlchemyUserRepository(session=session)
            user = await users.get_by_email(Email(email))
            user.role = Role.ADMINISTRATOR
            await users.upsert(user)
            await session.commit()

    asyncio.run(_promote())
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


@pytest_asyncio.fixture
async def seeded(db_session_factory):
    async with db_session_factory() as session:
        sport_id = SportId(uuid.uuid4())
        sport = await SqlAlchemySportRepository(session=session).upsert(
            Sport(id=sport_id, code=SportCode.FOOTBALL, name="Football")
        )

        venue_id = VenueId(uuid.uuid4())
        venue = await SqlAlchemyVenueRepository(session=session).upsert(
            Venue(id=venue_id, name="Anfield", city="Liverpool", country="England")
        )

        home_id, away_id = TeamId(uuid.uuid4()), TeamId(uuid.uuid4())
        home = await SqlAlchemyTeamRepository(session=session).upsert(
            Team(id=home_id, sport_id=sport.id, name="Liverpool FC", short_name="LIV", country="England", venue_id=venue.id)
        )
        away = await SqlAlchemyTeamRepository(session=session).upsert(
            Team(id=away_id, sport_id=sport.id, name="Everton FC", short_name="EVE", country="England")
        )

        player = await SqlAlchemyPlayerRepository(session=session).upsert(
            Player(id=PlayerId(uuid.uuid4()), sport_id=sport.id, name="Test Striker", date_of_birth=None, position="FW", team_id=home.id)
        )

        competition = await SqlAlchemyCompetitionRepository(session=session).upsert(
            Competition(
                id=CompetitionId(uuid.uuid4()), sport_id=sport.id, name="Premier League",
                type=CompetitionType.LEAGUE, country="England", tier=1,
                logo_url="https://cdn.example.com/premier-league.png",
            )
        )

        season = await SqlAlchemySeasonRepository(session=session).upsert(
            Season(
                id=SeasonId(uuid.uuid4()), competition_id=competition.id, label="2025/26",
                date_range=DateRange(start=T0 - timedelta(days=300), end=T0 + timedelta(days=60)),
                status=SeasonStatus.ACTIVE,
            )
        )

        # Deliberately in the past relative to T0 (fixed at 2026-07-26), not the future — the
        # team-fixtures endpoint's `list_recent_by_team` filters by the REAL wall-clock "now"
        # (apps/api/routers/sports_router.py `_now()`), not T0, so this needs to be safely
        # before any real "now" the suite could ever run at, not just before T0 itself.
        fixture = await SqlAlchemyFixtureRepository(session=session).upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=season.id, home_team_id=home.id, away_team_id=away.id,
                venue_id=venue.id, scheduled_at=T0 - timedelta(days=1), status=FixtureStatus.SCHEDULED,
            )
        )

        await SqlAlchemyStandingRepository(session=session).upsert(
            Standing(id=EntityId(uuid.uuid4()), season_id=season.id, team_id=home.id, snapshot_at=T0, rank=1, points=75.0, record={"w": 22})
        )
        await SqlAlchemyStandingRepository(session=session).upsert(
            Standing(id=EntityId(uuid.uuid4()), season_id=season.id, team_id=away.id, snapshot_at=T0, rank=2, points=60.0, record={"w": 18})
        )

        await session.commit()
        return {
            "sport": sport, "competition": competition, "season": season,
            "home": home, "away": away, "player": player, "fixture": fixture, "venue": venue,
        }


def test_requires_authentication(client):
    response = client.get("/api/v1/sports/football/competitions")
    assert response.status_code == 401


def test_unrecognized_sport_code_returns_422(client, auth_headers):
    response = client.get("/api/v1/sports/curling/competitions", headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.parametrize("sport_code", ["basketball", "baseball", "table_tennis"])
@pytest.mark.parametrize(
    "endpoint", ["competitions", "teams", "players", "fixtures"],
)
def test_non_football_sports_are_404_for_regular_users(client, auth_headers, sport_code, endpoint):
    """Basketball/Baseball/Table Tennis are still under development — a regular (non-admin) user
    must see exactly the same 404 a nonexistent sport would give, not a 403 that would confirm
    the sport exists but is locked."""
    response = client.get(f"/api/v1/sports/{sport_code}/{endpoint}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.parametrize("sport_code", ["basketball", "baseball", "table_tennis"])
def test_non_football_sports_remain_reachable_for_admins(client, admin_headers, db_session_factory, sport_code):
    async def _seed_sport():
        async with db_session_factory() as session:
            await SqlAlchemySportRepository(session=session).upsert(
                Sport(id=SportId(uuid.uuid4()), code=SportCode(sport_code), name=sport_code.title())
            )
            await session.commit()

    asyncio.run(_seed_sport())

    response = client.get(f"/api/v1/sports/{sport_code}/competitions", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []  # sport exists, honestly empty — not seeded with competitions here


def test_football_remains_open_to_regular_users(client, auth_headers, seeded):
    response = client.get("/api/v1/sports/football/competitions", headers=auth_headers)
    assert response.status_code == 200


def test_list_competitions_for_sport(client, auth_headers, seeded):
    response = client.get("/api/v1/sports/football/competitions", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Premier League"
    assert data[0]["sport_code"] == "football"


def test_get_competition(client, auth_headers, seeded):
    competition_id = str(seeded["competition"].id)
    response = client.get(f"/api/v1/sports/competitions/{competition_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Premier League"


def test_get_unknown_competition_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/sports/competitions/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_competition_standings_ranked(client, auth_headers, seeded):
    competition_id = str(seeded["competition"].id)
    response = client.get(f"/api/v1/sports/competitions/{competition_id}/standings", headers=auth_headers)
    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 2
    assert rows[0]["team_name"] == "Liverpool FC"
    assert rows[0]["rank"] == 1


def test_competition_standings_returns_only_the_latest_snapshot_per_team(client, auth_headers, seeded, db_session_factory):
    """Standings are point-in-time snapshots — a resync inserts a fresh row rather than updating
    in place (EntityReconciliationService.reconcile_standing), so a team resynced more than once
    ends up with multiple rows for the same season. The endpoint must collapse to each team's most
    recent snapshot, not return every historical row."""
    competition_id = str(seeded["competition"].id)
    season_id = seeded["season"].id
    home_team_id = seeded["home"].id

    async def _insert_newer_snapshot():
        async with db_session_factory() as session:
            await SqlAlchemyStandingRepository(session=session).upsert(
                Standing(
                    id=EntityId(uuid.uuid4()), season_id=season_id, team_id=home_team_id,
                    snapshot_at=T0 + timedelta(hours=1), rank=1, points=78.0, record={"w": 23},
                )
            )
            await session.commit()

    asyncio.run(_insert_newer_snapshot())

    response = client.get(f"/api/v1/sports/competitions/{competition_id}/standings", headers=auth_headers)

    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 2  # still one row per team, not one per snapshot
    liverpool = next(r for r in rows if r["team_name"] == "Liverpool FC")
    assert liverpool["points"] == 78.0  # the newer snapshot wins, not the original 75.0
    assert rows[1]["rank"] == 2


def test_competition_fixtures(client, auth_headers, seeded):
    competition_id = str(seeded["competition"].id)
    response = client.get(f"/api/v1/sports/competitions/{competition_id}/fixtures", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["home_team"]["name"] == "Liverpool FC"
    assert data[0]["away_team"]["name"] == "Everton FC"
    assert data[0]["venue_name"] == "Anfield"
    assert data[0]["status"] == "scheduled"


def test_competition_standings_drops_rows_for_a_team_that_no_longer_resolves(client, auth_headers, seeded, db_session_factory):
    """Audit fix (2026-08-21): a standings snapshot can outlive the team it points to (e.g. a
    stale row surviving a team merge/dedup that never repointed it) — the row's team_id then
    resolves to nothing. Previously this rendered as a literal "Unknown" table row, misrepresenting
    the competition's real roster; it must be dropped instead, matching the same failure mode's
    handling on the fixtures endpoint (sportsApi.competitionFixtures's withResolvedTeams)."""
    competition_id = str(seeded["competition"].id)
    season_id = seeded["season"].id

    async def _insert_orphaned_standing():
        async with db_session_factory() as session:
            await SqlAlchemyStandingRepository(session=session).upsert(
                Standing(
                    id=EntityId(uuid.uuid4()), season_id=season_id, team_id=TeamId(uuid.uuid4()),
                    snapshot_at=T0, rank=3, points=10.0, record={"w": 2},
                )
            )
            await session.commit()

    asyncio.run(_insert_orphaned_standing())

    response = client.get(f"/api/v1/sports/competitions/{competition_id}/standings", headers=auth_headers)

    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 2  # the seeded pair only — the orphaned third row is dropped, not "Unknown"
    assert all(r["team_name"] != "Unknown" for r in rows)


def test_competition_fixtures_defaults_to_the_fuller_active_season(client, auth_headers, seeded, db_session_factory):
    """Audit fix (2026-08-21): a competition can end up with more than one ACTIVE season row —
    e.g. a sparse, later-dated season next to an earlier one carrying the real bulk of fixtures.
    The no-season_id default must pick the fuller season, not just the most recent one, or a
    Competition Overview page renders almost empty despite the competition having real data."""
    competition_id = seeded["competition"].id
    home_id, away_id, venue_id = seeded["home"].id, seeded["away"].id, seeded["venue"].id

    async def _seed_second_season():
        async with db_session_factory() as session:
            seasons = SqlAlchemySeasonRepository(session=session)
            fixtures = SqlAlchemyFixtureRepository(session=session)

            # Later start date than `seeded`'s season, but only one fixture — must lose the pick.
            sparse_season = await seasons.upsert(
                Season(
                    id=SeasonId(uuid.uuid4()), competition_id=competition_id, label="2026/27",
                    date_range=DateRange(start=T0 + timedelta(days=30), end=T0 + timedelta(days=300)),
                    status=SeasonStatus.ACTIVE,
                )
            )
            await fixtures.upsert(
                Fixture(
                    id=FixtureId(uuid.uuid4()), season_id=sparse_season.id, home_team_id=home_id,
                    away_team_id=away_id, venue_id=venue_id, scheduled_at=T0 + timedelta(days=31),
                    status=FixtureStatus.SCHEDULED,
                )
            )

            # Earlier start date, but three fixtures — must win the pick despite being older.
            fuller_season = await seasons.upsert(
                Season(
                    id=SeasonId(uuid.uuid4()), competition_id=competition_id, label="2024/25",
                    date_range=DateRange(start=T0 - timedelta(days=400), end=T0 - timedelta(days=40)),
                    status=SeasonStatus.ACTIVE,
                )
            )
            for i in range(3):
                await fixtures.upsert(
                    Fixture(
                        id=FixtureId(uuid.uuid4()), season_id=fuller_season.id, home_team_id=home_id,
                        away_team_id=away_id, venue_id=venue_id, scheduled_at=T0 - timedelta(days=100 - i),
                        status=FixtureStatus.COMPLETED, home_score=1, away_score=0,
                    )
                )
            await session.commit()
            return fuller_season.id

    fuller_season_id = asyncio.run(_seed_second_season())

    response = client.get(f"/api/v1/sports/competitions/{competition_id}/fixtures", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["season_id"] == str(fuller_season_id)
    assert len(body["data"]) == 3


def test_list_competition_seasons(client, auth_headers, seeded):
    competition_id = str(seeded["competition"].id)
    response = client.get(f"/api/v1/sports/competitions/{competition_id}/seasons", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(seeded["season"].id)
    assert data[0]["label"] == "2025/26"
    assert data[0]["status"] == "active"


def test_list_competition_seasons_unknown_competition_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/sports/competitions/{uuid.uuid4()}/seasons", headers=auth_headers)
    assert response.status_code == 404


def test_list_teams_for_sport(client, auth_headers, seeded):
    response = client.get("/api/v1/sports/football/teams", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    names = {team["name"] for team in data}
    assert names == {"Liverpool FC", "Everton FC"}
    liverpool = next(t for t in data if t["name"] == "Liverpool FC")
    assert liverpool["venue_name"] == "Anfield"


def test_get_team(client, auth_headers, seeded):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Liverpool FC"


def test_get_unknown_team_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/sports/teams/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_team_players(client, auth_headers, seeded):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/players", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Test Striker"
    assert data[0]["team_id"] == team_id


def test_team_injuries_returns_empty_when_none_reported(client, auth_headers, seeded):
    """A team with no reported injuries is a real, honest outcome — never an error."""
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/injuries", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_team_injuries_returns_real_reported_injury(client, auth_headers, seeded, db_session_factory):
    async def _seed():
        async with db_session_factory() as session:
            await SqlAlchemyInjuryRepository(session=session).upsert(
                Injury(
                    id=EntityId(uuid.uuid4()), player_id=seeded["player"].id, reported_at=T0,
                    status="Missing Fixture", reason="Hamstring",
                )
            )
            await session.commit()

    asyncio.run(_seed())
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/injuries", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "Missing Fixture"
    assert data[0]["reason"] == "Hamstring"
    assert data[0]["player_name"] == "Test Striker"
    assert data[0]["expected_return"] is None  # never fabricated


def test_team_transfers_returns_real_transfer(client, auth_headers, seeded, db_session_factory):
    async def _seed():
        async with db_session_factory() as session:
            await SqlAlchemyTransferRepository(session=session).upsert(
                Transfer(
                    id=EntityId(uuid.uuid4()), player_id=seeded["player"].id, from_team_id=None,
                    to_team_id=seeded["home"].id, effective_date=T0, transfer_type="Free",
                )
            )
            await session.commit()

    asyncio.run(_seed())
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/transfers", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["to_team_name"] == "Liverpool FC"
    assert data[0]["from_team_id"] is None
    assert data[0]["transfer_type"] == "Free"


def test_team_coaching_staff_reports_current_and_history(client, auth_headers, seeded, db_session_factory):
    async def _seed():
        async with db_session_factory() as session:
            repo = SqlAlchemyCoachingStaffRepository(session=session)
            await repo.upsert(
                CoachingStaffMember(
                    id=EntityId(uuid.uuid4()), team_id=seeded["home"].id, person_name="Former Coach",
                    role="head_coach", valid_from=T0 - timedelta(days=400), valid_to=T0 - timedelta(days=10),
                )
            )
            await repo.upsert(
                CoachingStaffMember(
                    id=EntityId(uuid.uuid4()), team_id=seeded["home"].id, person_name="Current Coach",
                    role="head_coach", valid_from=T0 - timedelta(days=10), valid_to=None,
                )
            )
            await session.commit()

    asyncio.run(_seed())
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/coaching-staff", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    current = next(c for c in body["data"] if c["person_name"] == "Current Coach")
    assert body["meta"]["current_coach_id"] == current["id"]
    assert current["valid_to"] is None


def test_player_injuries(client, auth_headers, seeded, db_session_factory):
    async def _seed():
        async with db_session_factory() as session:
            await SqlAlchemyInjuryRepository(session=session).upsert(
                Injury(id=EntityId(uuid.uuid4()), player_id=seeded["player"].id, reported_at=T0, status="Questionable", reason="Illness")
            )
            await session.commit()

    asyncio.run(_seed())
    player_id = str(seeded["player"].id)
    response = client.get(f"/api/v1/sports/players/{player_id}/injuries", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["reason"] == "Illness"


def test_player_transfers(client, auth_headers, seeded, db_session_factory):
    async def _seed():
        async with db_session_factory() as session:
            await SqlAlchemyTransferRepository(session=session).upsert(
                Transfer(
                    id=EntityId(uuid.uuid4()), player_id=seeded["player"].id, from_team_id=None,
                    to_team_id=seeded["home"].id, effective_date=T0, transfer_type="Loan",
                )
            )
            await session.commit()

    asyncio.run(_seed())
    player_id = str(seeded["player"].id)
    response = client.get(f"/api/v1/sports/players/{player_id}/transfers", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["transfer_type"] == "Loan"


def test_team_fixtures_recent(client, auth_headers, seeded):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/fixtures", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(seeded["fixture"].id)


@pytest_asyncio.fixture
async def future_fixture(db_session_factory, seeded):
    """A fixture scheduled well after real wall-clock `now`, distinct from `seeded`'s past-scheduled
    fixture — proves `when=upcoming` and `when=recent` genuinely partition on real "now", not T0."""
    async with db_session_factory() as session:
        fixture = await SqlAlchemyFixtureRepository(session=session).upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=seeded["season"].id,
                home_team_id=seeded["home"].id, away_team_id=seeded["away"].id,
                venue_id=seeded["venue"].id, scheduled_at=datetime.now(timezone.utc) + timedelta(days=7),
                status=FixtureStatus.SCHEDULED,
            )
        )
        await session.commit()
        return fixture


def test_team_fixtures_upcoming(client, auth_headers, seeded, future_fixture):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/fixtures", params={"when": "upcoming"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(future_fixture.id)


def test_team_fixtures_rejects_unrecognized_when(client, auth_headers, seeded):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/fixtures", params={"when": "nonsense"}, headers=auth_headers)
    assert response.status_code == 422


@pytest_asyncio.fixture
async def team_statistics_rows(db_session_factory, seeded):
    """Two real past matches for the home team with different (and partially overlapping)
    stat_set keys — proves averaging only counts matches that actually recorded a given key,
    rather than dividing by the full sample size and silently treating missing data as zero."""
    async with db_session_factory() as session:
        fixtures = SqlAlchemyFixtureRepository(session=session)
        matches = SqlAlchemyMatchRepository(session=session)
        stats = SqlAlchemyTeamStatisticsRepository(session=session)

        # `matches.fixture_id` is unique — one match per fixture — so each match needs its own
        # distinct fixture row, not a shared one.
        fixture_1 = await fixtures.upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=seeded["season"].id,
                home_team_id=seeded["home"].id, away_team_id=seeded["away"].id,
                venue_id=seeded["venue"].id, scheduled_at=datetime.now(timezone.utc) - timedelta(days=10),
                status=FixtureStatus.COMPLETED,
            )
        )
        match_1 = await matches.upsert(
            Match(
                id=MatchId(uuid.uuid4()), fixture_id=fixture_1.id,
                started_at=datetime.now(timezone.utc) - timedelta(days=10), ended_at=None,
            )
        )
        await stats.upsert(
            TeamStatistics(
                id=EntityId(uuid.uuid4()), match_id=match_1.id, team_id=seeded["home"].id,
                stat_set={"possession_pct": 60.0, "corners": 8.0},
            )
        )

        fixture_2 = await fixtures.upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=seeded["season"].id,
                home_team_id=seeded["home"].id, away_team_id=seeded["away"].id,
                venue_id=seeded["venue"].id, scheduled_at=datetime.now(timezone.utc) - timedelta(days=20),
                status=FixtureStatus.COMPLETED,
            )
        )
        match_2 = await matches.upsert(
            Match(
                id=MatchId(uuid.uuid4()), fixture_id=fixture_2.id,
                started_at=datetime.now(timezone.utc) - timedelta(days=20), ended_at=None,
            )
        )
        await stats.upsert(
            TeamStatistics(
                id=EntityId(uuid.uuid4()), match_id=match_2.id, team_id=seeded["home"].id,
                stat_set={"possession_pct": 50.0},
            )
        )
        await session.commit()
        return {"match_1": match_1, "match_2": match_2}


def test_team_statistics_averages_only_recorded_samples(client, auth_headers, seeded, team_statistics_rows):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/statistics", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sample_size"] == 2
    assert data["possession_pct"] == 55.0  # (60 + 50) / 2 — both matches recorded it
    assert data["corners"] == 8.0  # only match_1 recorded it — not (8 + 0) / 2
    assert data["shots_total"] is None  # never recorded — must stay null, not fabricated as 0


def test_team_statistics_empty_when_no_matches(client, auth_headers, seeded):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/statistics", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sample_size"] == 0
    assert all(data[key] is None for key in ("possession_pct", "shots_total", "corners", "fouls", "cards_yellow", "cards_red"))


def test_team_statistics_unknown_team_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/sports/teams/{uuid.uuid4()}/statistics", headers=auth_headers)
    assert response.status_code == 404


def test_fixture_statistics_empty_when_fixture_has_no_match_yet(client, auth_headers, seeded):
    """A scheduled (never-kicked-off) fixture has no `Match` row at all — real sparse coverage,
    not an error, and the endpoint must say "nothing recorded" rather than 404 or fabricate rows."""
    fixture_id = str(seeded["fixture"].id)
    response = client.get(f"/api/v1/sports/fixtures/{fixture_id}/statistics", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_fixture_statistics_empty_when_match_has_no_synced_stats(client, auth_headers, db_session_factory, seeded):
    async def _seed_match_without_stats():
        async with db_session_factory() as session:
            await SqlAlchemyMatchRepository(session=session).upsert(
                Match(id=MatchId(uuid.uuid4()), fixture_id=seeded["fixture"].id, started_at=T0, ended_at=None)
            )
            await session.commit()

    asyncio.run(_seed_match_without_stats())

    fixture_id = str(seeded["fixture"].id)
    response = client.get(f"/api/v1/sports/fixtures/{fixture_id}/statistics", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_fixture_statistics_returns_real_per_team_rows(client, auth_headers, db_session_factory, seeded):
    async def _seed_match_with_stats():
        async with db_session_factory() as session:
            match = await SqlAlchemyMatchRepository(session=session).upsert(
                Match(id=MatchId(uuid.uuid4()), fixture_id=seeded["fixture"].id, started_at=T0, ended_at=None)
            )
            stats = SqlAlchemyTeamStatisticsRepository(session=session)
            await stats.upsert(
                TeamStatistics(
                    id=EntityId(uuid.uuid4()), match_id=match.id, team_id=seeded["home"].id,
                    stat_set={"possession_pct": 58.0, "corners": 6.0},
                )
            )
            await stats.upsert(
                TeamStatistics(
                    id=EntityId(uuid.uuid4()), match_id=match.id, team_id=seeded["away"].id,
                    stat_set={"possession_pct": 42.0},
                )
            )
            await session.commit()

    asyncio.run(_seed_match_with_stats())

    fixture_id = str(seeded["fixture"].id)
    response = client.get(f"/api/v1/sports/fixtures/{fixture_id}/statistics", headers=auth_headers)
    assert response.status_code == 200
    rows = {row["team_id"]: row["stats"] for row in response.json()["data"]}
    assert rows[str(seeded["home"].id)] == {"possession_pct": 58.0, "corners": 6.0}
    assert rows[str(seeded["away"].id)] == {"possession_pct": 42.0}


def test_fixture_lineups_empty_when_fixture_has_no_match_yet(client, auth_headers, seeded):
    """Phase 3 audit fix — the lineups read endpoint. A scheduled fixture with no `Match` row yet
    (mirrors the statistics endpoint's own honest-empty posture) returns an empty list."""
    fixture_id = str(seeded["fixture"].id)
    response = client.get(f"/api/v1/sports/fixtures/{fixture_id}/lineups", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_fixture_lineups_empty_when_match_has_no_synced_lineups(client, auth_headers, db_session_factory, seeded):
    async def _seed_match_without_lineups():
        async with db_session_factory() as session:
            await SqlAlchemyMatchRepository(session=session).upsert(
                Match(id=MatchId(uuid.uuid4()), fixture_id=seeded["fixture"].id, started_at=T0, ended_at=None)
            )
            await session.commit()

    asyncio.run(_seed_match_without_lineups())

    fixture_id = str(seeded["fixture"].id)
    response = client.get(f"/api/v1/sports/fixtures/{fixture_id}/lineups", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_fixture_lineups_returns_real_starters_substitutes_with_player_names(
    client, auth_headers, db_session_factory, seeded
):
    async def _seed_match_with_lineup():
        async with db_session_factory() as session:
            match = await SqlAlchemyMatchRepository(session=session).upsert(
                Match(id=MatchId(uuid.uuid4()), fixture_id=seeded["fixture"].id, started_at=T0, ended_at=None)
            )
            sub_player = await SqlAlchemyPlayerRepository(session=session).upsert(
                Player(
                    id=PlayerId(uuid.uuid4()), sport_id=seeded["sport"].id, name="Test Sub", date_of_birth=None,
                    position="MF", team_id=seeded["home"].id,
                )
            )
            await SqlAlchemyLineupRepository(session=session).upsert(
                Lineup(
                    id=LineupId(uuid.uuid4()), match_id=match.id, team_id=seeded["home"].id, formation="4-3-3",
                    slots=(
                        LineupSlot(player_id=seeded["player"].id, role=LineupRole.STARTER, position="FW", shirt_number=9),
                        LineupSlot(player_id=sub_player.id, role=LineupRole.SUBSTITUTE, position="MF", shirt_number=14),
                    ),
                    availability_classification="VERIFIED_PRE_MATCH", information_available_at=T0,
                )
            )
            await session.commit()
            return sub_player

    sub_player = asyncio.run(_seed_match_with_lineup())

    fixture_id = str(seeded["fixture"].id)
    response = client.get(f"/api/v1/sports/fixtures/{fixture_id}/lineups", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    lineup = data[0]
    assert lineup["team_id"] == str(seeded["home"].id)
    assert lineup["formation"] == "4-3-3"
    assert lineup["availability_classification"] == "VERIFIED_PRE_MATCH"
    assert len(lineup["starters"]) == 1
    assert lineup["starters"][0]["player_id"] == str(seeded["player"].id)
    assert lineup["starters"][0]["player_name"] == "Test Striker"
    assert lineup["starters"][0]["shirt_number"] == 9
    assert len(lineup["substitutes"]) == 1
    assert lineup["substitutes"][0]["player_id"] == str(sub_player.id)
    assert lineup["substitutes"][0]["player_name"] == "Test Sub"


def test_fixture_lineups_unknown_fixture_returns_empty_not_error(client, auth_headers):
    response = client.get(f"/api/v1/sports/fixtures/{uuid.uuid4()}/lineups", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_fixture_statistics_unknown_fixture_returns_empty_not_error(client, auth_headers):
    """No fixture-existence check by design — mirrors the "empty is honest, not an error" posture
    the two tests above establish, and avoids a second DB round-trip just to 404 on a bad id."""
    response = client.get(f"/api/v1/sports/fixtures/{uuid.uuid4()}/statistics", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_list_players_for_sport(client, auth_headers, seeded):
    response = client.get("/api/v1/sports/football/players", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Test Striker"
    assert data[0]["team_name"] == "Liverpool FC"


def test_get_player(client, auth_headers, seeded):
    player_id = str(seeded["player"].id)
    response = client.get(f"/api/v1/sports/players/{player_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Test Striker"


def test_get_unknown_player_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/sports/players/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_get_fixture(client, auth_headers, seeded):
    fixture_id = str(seeded["fixture"].id)
    response = client.get(f"/api/v1/sports/fixtures/{fixture_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["home_team"]["name"] == "Liverpool FC"
    assert data["competition_name"] == "Premier League"
    assert data["sport_code"] == "football"


def test_get_unknown_fixture_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/sports/fixtures/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_list_sport_fixtures_cross_competition(client, auth_headers, seeded):
    response = client.get("/api/v1/sports/football/fixtures", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(seeded["fixture"].id)


def test_list_sport_fixtures_scoped_to_competition(client, auth_headers, seeded):
    competition_id = str(seeded["competition"].id)
    response = client.get(
        "/api/v1/sports/football/fixtures", params={"competition_id": competition_id}, headers=auth_headers
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_fixture_serialization_includes_competition_id_and_logo(client, auth_headers, seeded):
    response = client.get("/api/v1/sports/football/fixtures", headers=auth_headers)
    data = response.json()["data"]
    assert data[0]["competition_id"] == str(seeded["competition"].id)
    assert data[0]["competition_logo_url"] == "https://cdn.example.com/premier-league.png"
    assert data[0]["competition_tier"] == 1


@pytest_asyncio.fixture
async def extra_fixtures(db_session_factory, seeded):
    """A completed fixture far in the past and a live fixture at real wall-clock `now` — alongside
    `seeded`'s single SCHEDULED fixture (scheduled at T0 - 1 day) — so status/date/search/pagination
    filtering on `list_sport_fixtures` has more than one row to actually discriminate between."""
    async with db_session_factory() as session:
        completed = await SqlAlchemyFixtureRepository(session=session).upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=seeded["season"].id,
                home_team_id=seeded["home"].id, away_team_id=seeded["away"].id,
                venue_id=seeded["venue"].id, scheduled_at=T0 - timedelta(days=200),
                status=FixtureStatus.COMPLETED, home_score=2, away_score=1,
            )
        )
        live = await SqlAlchemyFixtureRepository(session=session).upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=seeded["season"].id,
                home_team_id=seeded["home"].id, away_team_id=seeded["away"].id,
                venue_id=seeded["venue"].id, scheduled_at=datetime.now(timezone.utc),
                status=FixtureStatus.LIVE,
            )
        )
        await session.commit()
        return {"completed": completed, "live": live}


def test_list_sport_fixtures_filters_by_status(client, auth_headers, seeded, extra_fixtures):
    response = client.get("/api/v1/sports/football/fixtures", params={"status": "completed"}, headers=auth_headers)
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(extra_fixtures["completed"].id)

    response = client.get("/api/v1/sports/football/fixtures", params={"status": "live"}, headers=auth_headers)
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(extra_fixtures["live"].id)


def test_list_sport_fixtures_stats_null_when_none_recorded(client, auth_headers, seeded, extra_fixtures):
    """Most completed fixtures have no `team_statistics` at all today (real, partial coverage —
    see backend/docs/post_m24_phase9_training_readiness_report.md) — `stats` must be `None`, not
    an empty-but-present object, so the card can tell "no data" apart from "zero everything"."""
    response = client.get("/api/v1/sports/football/fixtures", params={"status": "completed"}, headers=auth_headers)
    data = response.json()["data"]
    assert data[0]["id"] == str(extra_fixtures["completed"].id)
    assert data[0]["stats"] is None


def test_list_sport_fixtures_stats_null_for_scheduled_fixture(client, auth_headers, seeded):
    """A scheduled fixture can never have match statistics — skip the match/stats lookup
    entirely rather than querying for something that structurally cannot exist yet."""
    response = client.get("/api/v1/sports/football/fixtures", headers=auth_headers)
    data = response.json()["data"]
    assert data[0]["id"] == str(seeded["fixture"].id)
    assert data[0]["stats"] is None


def test_list_sport_fixtures_includes_real_stats_when_recorded(client, auth_headers, db_session_factory, seeded, extra_fixtures):
    async def _seed_match_with_stats():
        async with db_session_factory() as session:
            match = await SqlAlchemyMatchRepository(session=session).upsert(
                Match(id=MatchId(uuid.uuid4()), fixture_id=extra_fixtures["completed"].id, started_at=T0, ended_at=None)
            )
            stats = SqlAlchemyTeamStatisticsRepository(session=session)
            await stats.upsert(
                TeamStatistics(
                    id=EntityId(uuid.uuid4()), match_id=match.id, team_id=seeded["home"].id,
                    stat_set={"possession_pct": 61.0, "corners": 5, "shots_total": 14},
                )
            )
            await stats.upsert(
                TeamStatistics(
                    id=EntityId(uuid.uuid4()), match_id=match.id, team_id=seeded["away"].id,
                    stat_set={"possession_pct": 39.0, "corners": 2},
                )
            )
            await session.commit()

    asyncio.run(_seed_match_with_stats())

    response = client.get("/api/v1/sports/football/fixtures", params={"status": "completed"}, headers=auth_headers)
    data = response.json()["data"]
    stats = data[0]["stats"]
    assert stats["home"] == {"possession_pct": 61.0, "corners": 5, "shots_total": 14}
    assert stats["away"] == {"possession_pct": 39.0, "corners": 2}


def test_list_sport_fixtures_rejects_unrecognized_status(client, auth_headers, seeded):
    response = client.get("/api/v1/sports/football/fixtures", params={"status": "nonsense"}, headers=auth_headers)
    assert response.status_code == 422


def test_list_sport_fixtures_filters_by_date_range(client, auth_headers, seeded, extra_fixtures):
    target_date = (T0 - timedelta(days=1)).date().isoformat()
    response = client.get(
        "/api/v1/sports/football/fixtures",
        params={"date_from": target_date, "date_to": target_date},
        headers=auth_headers,
    )
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(seeded["fixture"].id)


def test_list_sport_fixtures_search_matches_team_name(client, auth_headers, seeded, extra_fixtures):
    response = client.get("/api/v1/sports/football/fixtures", params={"search": "everton"}, headers=auth_headers)
    data = response.json()["data"]
    assert len(data) == 3  # all three seeded fixtures share the same two teams

    response = client.get("/api/v1/sports/football/fixtures", params={"search": "nonexistent-team"}, headers=auth_headers)
    assert response.json()["data"] == []
    assert response.json()["meta"]["total"] == 0


@pytest_asyncio.fixture
async def second_season_fixture(db_session_factory, seeded):
    """A separate, older season with its own fixture under the same competition — gives
    `season_id` filtering two distinct seasons to discriminate between, mirroring how a real
    competition (e.g. Premier League) has one fixture row per season across many years."""
    async with db_session_factory() as session:
        season = await SqlAlchemySeasonRepository(session=session).upsert(
            Season(
                id=SeasonId(uuid.uuid4()), competition_id=seeded["competition"].id, label="2022/23",
                date_range=DateRange(start=T0 - timedelta(days=700), end=T0 - timedelta(days=340)),
                status=SeasonStatus.COMPLETED,
            )
        )
        fixture = await SqlAlchemyFixtureRepository(session=session).upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=season.id,
                home_team_id=seeded["home"].id, away_team_id=seeded["away"].id,
                venue_id=seeded["venue"].id, scheduled_at=T0 - timedelta(days=680),
                status=FixtureStatus.COMPLETED, home_score=1, away_score=0,
            )
        )
        await session.commit()
        return {"season": season, "fixture": fixture}


def test_list_sport_fixtures_filters_by_season_id(client, auth_headers, seeded, second_season_fixture):
    response = client.get(
        "/api/v1/sports/football/fixtures",
        params={"season_id": str(second_season_fixture["season"].id)},
        headers=auth_headers,
    )
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(second_season_fixture["fixture"].id)


def test_list_sport_fixtures_pagination_meta(client, auth_headers, seeded, extra_fixtures):
    response = client.get("/api/v1/sports/football/fixtures", params={"limit": 1, "offset": 0}, headers=auth_headers)
    body = response.json()
    assert len(body["data"]) == 1
    assert body["meta"]["total"] == 3
    assert body["meta"]["offset"] == 0
    assert body["meta"]["has_more"] is True

    response = client.get("/api/v1/sports/football/fixtures", params={"limit": 1, "offset": 2}, headers=auth_headers)
    body = response.json()
    assert len(body["data"]) == 1
    assert body["meta"]["has_more"] is False


def _sync_run(status: SyncStatus, started_at: datetime) -> SyncRun:
    return SyncRun(
        id=SyncRunId(uuid.uuid4()), sport_code="football", entity_kind=IngestionEntityKind.TEAM, scope_key="39",
        trigger=SyncTrigger.SCHEDULED, status=status, started_at=started_at, finished_at=started_at,
        records_fetched=5, records_created=5, records_rejected=0, validation_failures=0,
    )


async def _seed_sync_runs(db_session_factory, runs: list[SyncRun]) -> None:
    async with db_session_factory() as session:
        repo = SqlAlchemySyncRunRepository(session=session)
        for run in runs:
            await repo.record(run)
        await session.commit()


def test_sync_status_requires_authentication(client):
    response = client.get("/api/v1/sports/sync-status")
    assert response.status_code == 401


def test_sync_status_null_when_no_runs_recorded(client, auth_headers):
    response = client.get("/api/v1/sports/sync-status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["last_synced_at"] is None


def test_sync_status_returns_latest_succeeded_or_partial_run(client, auth_headers, db_session_factory):
    older = T0 - timedelta(hours=2)
    newest = T0 - timedelta(minutes=5)
    asyncio.run(_seed_sync_runs(db_session_factory, [_sync_run(SyncStatus.SUCCEEDED, older), _sync_run(SyncStatus.PARTIAL, newest)]))

    response = client.get("/api/v1/sports/sync-status", headers=auth_headers)

    assert response.status_code == 200
    # SQLite round-trips datetimes as naive (drops tzinfo) — matches this suite's existing convention.
    assert response.json()["data"]["last_synced_at"] == newest.replace(tzinfo=None).isoformat()


def test_sync_status_ignores_failed_only_runs(client, auth_headers, db_session_factory):
    asyncio.run(_seed_sync_runs(db_session_factory, [_sync_run(SyncStatus.FAILED, T0)]))

    response = client.get("/api/v1/sports/sync-status", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["last_synced_at"] is None

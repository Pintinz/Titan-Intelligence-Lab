import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator
from modules.sports.domain.entities import Competition, Fixture, Player, Season, Sport, Standing, Team, Venue
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    DateRange,
    EntityId,
    FixtureId,
    FixtureStatus,
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
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyVenueRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "sports": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(SportsBase.metadata.create_all)

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


def test_team_fixtures_recent(client, auth_headers, seeded):
    team_id = str(seeded["home"].id)
    response = client.get(f"/api/v1/sports/teams/{team_id}/fixtures", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(seeded["fixture"].id)


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

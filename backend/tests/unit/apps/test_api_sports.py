import asyncio
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
from modules.ingestion.domain.entities import SyncRun
from modules.ingestion.domain.value_objects import EntityKind as IngestionEntityKind, SyncRunId, SyncStatus, SyncTrigger
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.ingestion.infrastructure.persistence.repositories import SqlAlchemySyncRunRepository
from modules.sports.domain.entities import Competition, Fixture, Match, Player, Season, Sport, Standing, Team, TeamStatistics, Venue
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    DateRange,
    EntityId,
    FixtureId,
    FixtureStatus,
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

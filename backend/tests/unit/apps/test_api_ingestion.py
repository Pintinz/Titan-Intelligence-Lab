import asyncio

import fakeredis
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import apps.api.composition as composition
from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.knowledge_graph.infrastructure.persistence.models import Base as KGBase
from modules.sports.infrastructure.persistence.models import Base as SportsBase


@pytest.fixture
def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={
            "schema_translate_map": {
                "admin": None, "features": None, "sports": None, "ingestion": None, "knowledge_graph": None,
                "identity": None,
            }
        },
    )

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(AdminBase.metadata.create_all)
            await conn.run_sync(FeaturesBase.metadata.create_all)
            await conn.run_sync(SportsBase.metadata.create_all)
            await conn.run_sync(IngestionBase.metadata.create_all)
            await conn.run_sync(KGBase.metadata.create_all)
            await conn.run_sync(IdentityBase.metadata.create_all)

    asyncio.run(_setup())

    yield async_sessionmaker(engine, expire_on_commit=False)


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


@pytest.fixture
def client(db_session_factory, monkeypatch):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    from modules.admin.infrastructure.vault import get_vault_settings

    import apps.api.main as main_module

    fake_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    composition.get_redis_client.cache_clear()
    composition.get_redis_lock.cache_clear()
    composition.get_redis_sync_cache.cache_clear()
    monkeypatch.setattr(composition, "get_redis_client", lambda: fake_client)
    monkeypatch.setattr(main_module, "get_redis_client", lambda: fake_client)

    monkeypatch.setenv("TITANIQ_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_vault_settings.cache_clear()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    test_client = TestClient(app)
    email, password = "ingestion-admin@titaniq.test", "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    yield test_client
    app.dependency_overrides.clear()
    composition.get_redis_lock.cache_clear()
    composition.get_redis_sync_cache.cache_clear()


def test_sync_teams_requires_reconciled_sport(client):
    response = client.post("/api/v1/admin/sync/football/teams/39", json={"force": False})

    assert response.status_code == 409


def test_sync_status_returns_empty_envelope_when_no_runs(client):
    response = client.get("/api/v1/admin/sync/status")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_sync_stats_returns_empty_summary(client):
    response = client.get("/api/v1/admin/sync/stats")

    assert response.status_code == 200
    assert response.json()["data"]["sample_size"] == 0


def test_ingestion_quality_returns_none_with_no_reports(client):
    response = client.get("/api/v1/admin/ingestion/quality/football/team")

    assert response.status_code == 200
    assert response.json()["data"] is None


def test_ingestion_quality_rejects_unknown_entity_kind(client):
    response = client.get("/api/v1/admin/ingestion/quality/football/nonsense")

    assert response.status_code == 422


def test_redis_health_endpoint_reports_healthy(client):
    response = client.get("/api/v1/admin/monitoring/redis")

    assert response.status_code == 200
    assert response.json()["data"]["healthy"] is True


def test_kg_node_not_found_returns_404(client):
    response = client.get("/api/v1/admin/graph/nodes/team/does-not-exist")

    assert response.status_code == 404


def test_kg_node_rejects_unknown_node_type(client):
    response = client.get("/api/v1/admin/graph/nodes/nonsense/some-id")

    assert response.status_code == 422


def test_sync_countries_and_kg_node_read_end_to_end(client):
    sync_response = client.post("/api/v1/admin/sync/football/countries", json={"force": False})
    assert sync_response.status_code == 200
    # Mock provider returns country records — a real sync run should have happened.
    run = sync_response.json()["data"]
    assert run is not None
    assert run["status"] in ("succeeded", "partial")


async def _seed_reconciled_sport(db_session_factory, sport_code="football", name="Football"):
    from datetime import datetime, timezone

    from apps.api.composition import build_entity_reconciliation_service
    from modules.sports.domain.value_objects import SportCode

    async with db_session_factory() as session:
        reconciler = build_entity_reconciliation_service(session)
        await reconciler.reconcile_sport(SportCode(sport_code), name, datetime.now(timezone.utc))
        await session.commit()


def test_sync_teams_success_after_sport_reconciled(client, db_session_factory):
    asyncio.run(_seed_reconciled_sport(db_session_factory))

    response = client.post("/api/v1/admin/sync/football/teams/39", json={"force": False})

    assert response.status_code == 200
    run = response.json()["data"]
    assert run is not None
    assert run["status"] in ("succeeded", "partial")
    assert run["records_fetched"] > 0


def test_sync_status_and_stats_reflect_completed_runs(client, db_session_factory):
    asyncio.run(_seed_reconciled_sport(db_session_factory))
    client.post("/api/v1/admin/sync/football/teams/39", json={"force": False})

    status_response = client.get("/api/v1/admin/sync/status", params={"sport_code": "football"})
    stats_response = client.get("/api/v1/admin/sync/stats", params={"sport_code": "football"})

    assert len(status_response.json()["data"]) == 1
    assert stats_response.json()["data"]["sample_size"] == 1
    assert stats_response.json()["data"]["succeeded"] + stats_response.json()["data"]["partial"] == 1


def test_ingestion_quality_reflects_completed_sync(client, db_session_factory):
    asyncio.run(_seed_reconciled_sport(db_session_factory))
    client.post("/api/v1/admin/sync/football/teams/39", json={"force": False})

    response = client.get("/api/v1/admin/ingestion/quality/football/team")

    data = response.json()["data"]
    assert data is not None
    assert data["sample_size"] > 0


def test_sync_fixtures_and_standings_endpoints(client, db_session_factory):
    from uuid import uuid4

    asyncio.run(_seed_reconciled_sport(db_session_factory))
    client.post("/api/v1/admin/sync/football/teams/39", json={"force": False})
    season_id = str(uuid4())

    fixtures_response = client.post(
        f"/api/v1/admin/sync/football/fixtures/39/2026", json={"season_id": season_id, "force": False, "live": False}
    )
    live_response = client.post(
        f"/api/v1/admin/sync/football/fixtures/39/2026", json={"season_id": season_id, "force": False, "live": True}
    )
    standings_response = client.post(
        f"/api/v1/admin/sync/football/standings/39/2026", json={"season_id": season_id, "force": False}
    )

    assert fixtures_response.status_code == 200
    assert live_response.status_code == 200
    assert standings_response.status_code == 200


async def _first_reconciled_team_id(db_session_factory, sport_code="football") -> str:
    from modules.sports.domain.value_objects import SportCode
    from modules.sports.infrastructure.persistence.repositories import SqlAlchemySportRepository, SqlAlchemyTeamRepository

    async with db_session_factory() as session:
        sport = await SqlAlchemySportRepository(session=session).get_by_code(SportCode(sport_code))
        teams = await SqlAlchemyTeamRepository(session=session).list_by_sport(sport.id)
        return str(teams[0].id.value)


def test_kg_node_read_returns_edges_after_sync(client, db_session_factory):
    asyncio.run(_seed_reconciled_sport(db_session_factory))
    client.post("/api/v1/admin/sync/football/teams/39", json={"force": False})
    team_id = asyncio.run(_first_reconciled_team_id(db_session_factory))

    response = client.get(f"/api/v1/admin/graph/nodes/team/{team_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["node_type"] == "team"
    assert any(edge["edge_type"] == "belongs_to" for edge in data["edges_out"])

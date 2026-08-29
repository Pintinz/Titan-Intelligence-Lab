import asyncio

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator
from modules.sports.infrastructure.persistence.database import get_database_settings


@pytest.fixture(autouse=True)
def _real_db_url_for_display_only(monkeypatch):
    """`database_status()` reads `get_database_settings()` purely to display the (masked) host
    and dialect — the actual queries below go through the overridden `get_session`, never this
    URL. Setting it here just matches what any real running process already requires to boot at
    all; `get_database_settings` is `@lru_cache`'d, so it's cleared after each test too."""
    monkeypatch.setenv("TITANIQ_DB_URL", "sqlite+aiosqlite:///:memory:")
    get_database_settings.cache_clear()
    yield
    get_database_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session_factory():
    # Deliberately only admin/identity — the endpoint's own per-stat try/except must degrade
    # gracefully (None, not a 500) when fixtures/predictions/news tables don't exist at all,
    # matching a fresh environment that hasn't ingested anything yet.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"admin": None, "identity": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(AdminBase.metadata.create_all)
        await conn.run_sync(IdentityBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


@pytest.fixture
def client(db_session_factory):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    test_client = TestClient(app)
    email, password = "db-status-admin@titaniq.test", "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    yield test_client
    app.dependency_overrides.clear()


def test_requires_authentication(client):
    del client.headers["Authorization"]

    response = client.get("/api/v1/admin/system/database-status")

    assert response.status_code in (401, 403)


def test_reports_environment_and_engine_identity(client, monkeypatch):
    monkeypatch.delenv("TITANIQ_ENVIRONMENT", raising=False)

    response = client.get("/api/v1/admin/system/database-status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["environment"] == "development"
    assert data["database_engine"] == "sqlite"
    assert data["connectivity"] == "healthy"
    assert data["sqlite_fallback_disabled"] is False


def test_never_leaks_the_connection_string(client):
    response_text = client.get("/api/v1/admin/system/database-status").text
    assert "sqlite+aiosqlite" not in response_text
    assert "://" not in response_text


def test_degrades_gracefully_when_data_tables_do_not_exist(client):
    """The fixtures/predictions/models/news_articles tables aren't created by this fixture at
    all — each latest-timestamp stat must come back None, never a 500, exactly matching a fresh
    environment with no ingestion history yet."""
    response = client.get("/api/v1/admin/system/database-status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["latest_fixture_updated_at"] is None
    assert data["latest_prediction_generated_at"] is None
    assert data["latest_model_created_at"] is None
    assert data["latest_news_fetched_at"] is None

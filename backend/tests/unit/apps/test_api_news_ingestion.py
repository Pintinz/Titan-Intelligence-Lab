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
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase


@pytest.fixture
def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={
            "schema_translate_map": {"admin": None, "features": None, "identity": None, "intelligence": None},
        },
    )

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(AdminBase.metadata.create_all)
            await conn.run_sync(FeaturesBase.metadata.create_all)
            await conn.run_sync(IdentityBase.metadata.create_all)
            await conn.run_sync(IntelligenceBase.metadata.create_all)

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
    monkeypatch.setattr(composition, "get_redis_client", lambda: fake_client)
    monkeypatch.setattr(main_module, "get_redis_client", lambda: fake_client)

    monkeypatch.setenv("TITANIQ_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_vault_settings.cache_clear()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    test_client = TestClient(app)
    email, password = "news-admin@titaniq.test", "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    yield test_client
    app.dependency_overrides.clear()


def test_register_news_source_rejects_unknown_source_type(client):
    response = client.post(
        "/api/v1/admin/news/sources", json={"name": "Bad Source", "url": "https://example.com/feed.xml", "source_type": "carrier_pigeon"}
    )

    assert response.status_code == 422


def test_register_and_list_news_source(client):
    register_response = client.post(
        "/api/v1/admin/news/sources", json={"name": "BBC Sport", "url": "https://feeds.bbci.co.uk/sport/rss.xml"}
    )
    assert register_response.status_code == 200
    source = register_response.json()["data"]
    assert source["name"] == "BBC Sport"
    assert source["source_type"] == "rss_feed"
    assert source["is_official"] is False

    list_response = client.get("/api/v1/admin/news/sources")
    assert list_response.status_code == 200
    sources = list_response.json()["data"]
    assert len(sources) == 1
    assert sources[0]["id"] == source["id"]


def test_registering_the_same_url_twice_upserts_rather_than_duplicates(client):
    body = {"name": "BBC Sport", "url": "https://feeds.bbci.co.uk/sport/rss.xml"}
    first = client.post("/api/v1/admin/news/sources", json=body)
    second = client.post("/api/v1/admin/news/sources", json={**body, "name": "BBC Sport (renamed)"})

    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert second.json()["data"]["name"] == "BBC Sport (renamed)"

    sources = client.get("/api/v1/admin/news/sources").json()["data"]
    assert len(sources) == 1


def test_sync_unknown_source_returns_404(client):
    from uuid import uuid4

    response = client.post(f"/api/v1/admin/news/sources/{uuid4()}/sync")

    assert response.status_code == 404


def test_sync_source_rejects_malformed_id(client):
    response = client.post("/api/v1/admin/news/sources/not-a-uuid/sync")

    assert response.status_code == 422


def test_sync_source_against_unreachable_feed_marks_run_failed_not_a_crash(client):
    """Proves the real end-to-end wire — endpoint -> NewsIngestionService -> RssNewsProvider ->
    a real (failing) HTTP attempt — without depending on a live external feed: connecting to a
    closed local port fails fast and deterministically, and NewsIngestionService.sync_source
    already catches provider exceptions and records a failed run rather than raising."""
    register_response = client.post(
        "/api/v1/admin/news/sources", json={"name": "Unreachable", "url": "http://127.0.0.1:1/feed.xml"}
    )
    source_id = register_response.json()["data"]["id"]

    response = client.post(f"/api/v1/admin/news/sources/{source_id}/sync")

    assert response.status_code == 200
    run = response.json()["data"]
    assert run["status"] == "failed"
    assert run["error_message"] is not None
    assert run["channel_key"] == source_id

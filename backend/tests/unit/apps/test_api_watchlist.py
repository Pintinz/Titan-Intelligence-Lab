import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator
from modules.watchlist.infrastructure.persistence.models import Base as WatchlistBase


@pytest.fixture
def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "watchlist": None}},
    )

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(IdentityBase.metadata.create_all)
            await conn.run_sync(WatchlistBase.metadata.create_all)

    asyncio.run(_setup())

    yield async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def client(db_session_factory):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    test_client = TestClient(app)
    email, password = "watchlist-user@titaniq.test", "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    yield test_client
    app.dependency_overrides.clear()


def test_list_starts_empty(client):
    response = client.get("/api/v1/watchlist")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_follow_and_list(client):
    follow_response = client.post("/api/v1/watchlist", json={"entity_type": "team", "entity_ref": "team-1"})

    assert follow_response.status_code == 200
    entry = follow_response.json()["data"]
    assert entry["entity_type"] == "team"
    assert entry["entity_ref"] == "team-1"

    list_response = client.get("/api/v1/watchlist")
    assert list_response.status_code == 200
    entries = list_response.json()["data"]
    assert len(entries) == 1
    assert entries[0]["id"] == entry["id"]


def test_follow_rejects_unknown_entity_type(client):
    response = client.post("/api/v1/watchlist", json={"entity_type": "referee", "entity_ref": "ref-1"})

    assert response.status_code == 422


def test_follow_twice_is_idempotent(client):
    first = client.post("/api/v1/watchlist", json={"entity_type": "fixture", "entity_ref": "fx-1"})
    second = client.post("/api/v1/watchlist", json={"entity_type": "fixture", "entity_ref": "fx-1"})

    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert len(client.get("/api/v1/watchlist").json()["data"]) == 1


def test_unfollow_removes_entry(client):
    entry = client.post("/api/v1/watchlist", json={"entity_type": "competition", "entity_ref": "comp-1"}).json()["data"]

    unfollow_response = client.delete(f"/api/v1/watchlist/{entry['id']}")

    assert unfollow_response.status_code == 200
    assert client.get("/api/v1/watchlist").json()["data"] == []


def test_unfollow_unknown_entry_returns_404(client):
    from uuid import uuid4

    response = client.delete(f"/api/v1/watchlist/{uuid4()}")

    assert response.status_code == 404


def test_unfollow_malformed_id_returns_422(client):
    response = client.delete("/api/v1/watchlist/not-a-uuid")

    assert response.status_code == 422


def test_list_filters_by_entity_type(client):
    client.post("/api/v1/watchlist", json={"entity_type": "team", "entity_ref": "team-1"})
    client.post("/api/v1/watchlist", json={"entity_type": "prediction", "entity_ref": "pred-1"})

    response = client.get("/api/v1/watchlist", params={"entity_type": "team"})

    entries = response.json()["data"]
    assert len(entries) == 1
    assert entries[0]["entity_type"] == "team"


def test_watchlist_requires_authentication(client):
    client.headers.pop("Authorization", None)

    response = client.get("/api/v1/watchlist")

    assert response.status_code == 401


def test_cannot_unfollow_another_users_entry(client, db_session_factory):
    entry = client.post("/api/v1/watchlist", json={"entity_type": "team", "entity_ref": "team-1"}).json()["data"]

    other_client = TestClient(app)
    other_client.post("/api/v1/auth/register", json={"email": "other-user@titaniq.test", "password": "correct-horse-battery"})
    login = other_client.post(
        "/api/v1/auth/login", json={"email": "other-user@titaniq.test", "password": "correct-horse-battery"}
    )
    other_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"

    response = other_client.delete(f"/api/v1/watchlist/{entry['id']}")

    assert response.status_code == 404
    assert len(client.get("/api/v1/watchlist").json()["data"]) == 1

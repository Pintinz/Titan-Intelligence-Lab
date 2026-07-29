import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "tenancy": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)

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


def register_and_login(client, email="alice@example.com", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["data"]["access_token"]


def test_register_then_login(client):
    register = client.post("/api/v1/auth/register", json={"email": "bob@example.com", "password": "hunter22222"})
    assert register.status_code == 200
    assert register.json()["data"]["status"] == "pending_verification"

    login = client.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": "hunter22222"})
    assert login.status_code == 200
    assert login.json()["data"]["access_token"]


def test_login_wrong_password_returns_401(client):
    client.post("/api/v1/auth/register", json={"email": "carol@example.com", "password": "correct"})

    response = client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": "wrong"})

    assert response.status_code == 401


def test_get_me_requires_bearer_token(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_get_me_with_valid_token(client):
    token = register_and_login(client)

    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["data"]["email"] == "alice@example.com"


def test_create_and_list_personal_access_tokens(client):
    token = register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post("/api/v1/users/me/tokens", json={"name": "ci", "scopes": ["read"]}, headers=headers)
    assert create.status_code == 200
    assert create.json()["data"]["raw_token"]

    listing = client.get("/api/v1/users/me/tokens", headers=headers)
    names = [t["name"] for t in listing.json()["data"]]
    assert "ci" in names
    # the login-issued session token plus the newly created "ci" token
    assert len(listing.json()["data"]) == 2


def test_revoke_token_requires_own_token(client):
    token = register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/v1/users/me/tokens", json={"name": "temp"}, headers=headers).json()["data"]

    revoke = client.delete(f"/api/v1/users/me/tokens/{created['id']}", headers=headers)

    assert revoke.status_code == 200
    assert revoke.json()["data"]["revoked"] is True


def test_list_and_revoke_sessions(client):
    token = register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    sessions = client.get("/api/v1/users/me/sessions", headers=headers)
    assert sessions.status_code == 200
    assert len(sessions.json()["data"]) == 1

    session_id = sessions.json()["data"][0]["id"]
    revoke = client.delete(f"/api/v1/users/me/sessions/{session_id}", headers=headers)
    assert revoke.status_code == 200


def test_role_change_requires_admin(client):
    token = register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/users/me", headers=headers).json()["data"]

    response = client.post(f"/api/v1/users/{me['id']}/role", json={"role": "analyst"}, headers=headers)

    assert response.status_code == 403

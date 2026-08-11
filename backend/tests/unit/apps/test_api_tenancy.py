import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator
from modules.tenancy.infrastructure.persistence.models import Base as TenancyBase


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "tenancy": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(TenancyBase.metadata.create_all)

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


def register_and_login(client, email, password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["data"]["access_token"]


def test_create_organization(client):
    token = register_and_login(client, "owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/organizations", json={"name": "Acme Sports"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["slug"] == "acme-sports"


def test_create_team_and_list_members(client):
    token = register_and_login(client, "owner2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    org = client.post("/api/v1/organizations", json={"name": "Acme"}, headers=headers).json()["data"]

    team = client.post(f"/api/v1/organizations/{org['id']}/teams", json={"name": "Engineering"}, headers=headers)
    assert team.status_code == 200

    members = client.get(f"/api/v1/organizations/{org['id']}/members", headers=headers)
    assert len(members.json()["data"]) == 1


def test_invite_and_accept_flow(client):
    owner_token = register_and_login(client, "owner3@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    org = client.post("/api/v1/organizations", json={"name": "Acme"}, headers=owner_headers).json()["data"]

    invite = client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "invitee@example.com", "role": "member"},
        headers=owner_headers,
    )
    assert invite.status_code == 200
    raw_token = invite.json()["data"]["raw_token"]

    invitee_token = register_and_login(client, "invitee@example.com")
    invitee_headers = {"Authorization": f"Bearer {invitee_token}"}

    accept = client.post("/api/v1/organizations/invitations/accept", json={"token": raw_token}, headers=invitee_headers)
    assert accept.status_code == 200
    assert accept.json()["data"]["role"] == "member"


def test_non_member_cannot_create_team(client):
    owner_token = register_and_login(client, "owner4@example.com")
    org = client.post(
        "/api/v1/organizations", json={"name": "Acme"}, headers={"Authorization": f"Bearer {owner_token}"}
    ).json()["data"]

    outsider_token = register_and_login(client, "outsider@example.com")
    response = client.post(
        f"/api/v1/organizations/{org['id']}/teams",
        json={"name": "Engineering"},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


def test_non_member_cannot_list_members(client):
    owner_token = register_and_login(client, "owner5@example.com")
    org = client.post(
        "/api/v1/organizations", json={"name": "Acme"}, headers={"Authorization": f"Bearer {owner_token}"}
    ).json()["data"]

    outsider_token = register_and_login(client, "outsider2@example.com")
    response = client.get(
        f"/api/v1/organizations/{org['id']}/members", headers={"Authorization": f"Bearer {outsider_token}"}
    )

    assert response.status_code == 403

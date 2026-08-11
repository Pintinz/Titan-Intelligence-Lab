import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.admin.infrastructure.vault import get_vault_settings
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator
from modules.tenancy.infrastructure.persistence.models import Base as TenancyBase
from modules.webhooks.infrastructure.persistence.models import Base as WebhooksBase


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "tenancy": None, "webhooks": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(TenancyBase.metadata.create_all)
        await conn.run_sync(WebhooksBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory, monkeypatch):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    monkeypatch.setenv("TITANIQ_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_vault_settings.cache_clear()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()


def register_and_login(client, email, password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["data"]["access_token"]


def _create_org(client, headers, name="Acme"):
    return client.post("/api/v1/organizations", json={"name": name}, headers=headers).json()["data"]


def test_member_can_register_and_list_endpoints(client):
    token = register_and_login(client, "owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    org = _create_org(client, headers)

    register = client.post(
        "/api/v1/webhooks/endpoints",
        json={"organization_id": org["id"], "url": "https://example.com/hook"},
        headers=headers,
    )
    assert register.status_code == 200
    assert register.json()["data"]["signing_secret"]

    listed = client.get(f"/api/v1/webhooks/organizations/{org['id']}/endpoints", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1


def test_non_member_cannot_register_endpoint(client):
    owner_token = register_and_login(client, "owner2@example.com")
    org = _create_org(client, {"Authorization": f"Bearer {owner_token}"})

    outsider_token = register_and_login(client, "outsider@example.com")
    response = client.post(
        "/api/v1/webhooks/endpoints",
        json={"organization_id": org["id"], "url": "https://example.com/hook"},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


def test_non_member_cannot_list_endpoints(client):
    owner_token = register_and_login(client, "owner3@example.com")
    org = _create_org(client, {"Authorization": f"Bearer {owner_token}"})

    outsider_token = register_and_login(client, "outsider2@example.com")
    response = client.get(
        f"/api/v1/webhooks/organizations/{org['id']}/endpoints",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


def test_non_member_cannot_rotate_secret(client):
    owner_token = register_and_login(client, "owner4@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    org = _create_org(client, owner_headers)
    endpoint = client.post(
        "/api/v1/webhooks/endpoints",
        json={"organization_id": org["id"], "url": "https://example.com/hook"},
        headers=owner_headers,
    ).json()["data"]

    outsider_token = register_and_login(client, "outsider3@example.com")
    response = client.post(
        f"/api/v1/webhooks/endpoints/{endpoint['id']}/rotate-secret",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


def test_non_member_cannot_deactivate_endpoint(client):
    owner_token = register_and_login(client, "owner5@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    org = _create_org(client, owner_headers)
    endpoint = client.post(
        "/api/v1/webhooks/endpoints",
        json={"organization_id": org["id"], "url": "https://example.com/hook"},
        headers=owner_headers,
    ).json()["data"]

    outsider_token = register_and_login(client, "outsider4@example.com")
    response = client.delete(
        f"/api/v1/webhooks/endpoints/{endpoint['id']}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


def test_non_member_cannot_list_deliveries(client):
    owner_token = register_and_login(client, "owner6@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    org = _create_org(client, owner_headers)
    endpoint = client.post(
        "/api/v1/webhooks/endpoints",
        json={"organization_id": org["id"], "url": "https://example.com/hook"},
        headers=owner_headers,
    ).json()["data"]

    outsider_token = register_and_login(client, "outsider5@example.com")
    response = client.get(
        f"/api/v1/webhooks/endpoints/{endpoint['id']}/deliveries",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 403


def test_plain_member_cannot_register_endpoint(client):
    owner_token = register_and_login(client, "owner7@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    org = _create_org(client, owner_headers)

    invite = client.post(
        f"/api/v1/organizations/{org['id']}/invitations",
        json={"email": "member@example.com", "role": "member"},
        headers=owner_headers,
    ).json()["data"]
    member_token = register_and_login(client, "member@example.com")
    member_headers = {"Authorization": f"Bearer {member_token}"}
    client.post("/api/v1/organizations/invitations/accept", json={"token": invite["raw_token"]}, headers=member_headers)

    response = client.post(
        "/api/v1/webhooks/endpoints",
        json={"organization_id": org["id"], "url": "https://example.com/hook"},
        headers=member_headers,
    )

    assert response.status_code == 403


def test_unknown_endpoint_returns_404(client):
    token = register_and_login(client, "owner8@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/webhooks/endpoints/00000000-0000-0000-0000-000000000000/rotate-secret", headers=headers
    )

    assert response.status_code == 404

import asyncio
import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.domain.value_objects import AuditAction, Email, Role, UserId
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyAuditLogRepository, SqlAlchemyUserRepository
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


def test_cannot_revoke_another_users_token(client):
    owner_token = register_and_login(client, "token-owner@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    created = client.post("/api/v1/users/me/tokens", json={"name": "owner-token"}, headers=owner_headers).json()["data"]

    attacker_token = register_and_login(client, "token-attacker@example.com")
    attacker_headers = {"Authorization": f"Bearer {attacker_token}"}

    revoke = client.delete(f"/api/v1/users/me/tokens/{created['id']}", headers=attacker_headers)
    assert revoke.status_code == 404

    still_listed = client.get("/api/v1/users/me/tokens", headers=owner_headers).json()["data"]
    assert any(t["id"] == created["id"] and t["is_active"] for t in still_listed)


def test_cannot_revoke_another_users_session(client):
    owner_token = register_and_login(client, "session-owner@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    owner_session = client.get("/api/v1/users/me/sessions", headers=owner_headers).json()["data"][0]

    attacker_token = register_and_login(client, "session-attacker@example.com")
    attacker_headers = {"Authorization": f"Bearer {attacker_token}"}

    revoke = client.delete(f"/api/v1/users/me/sessions/{owner_session['id']}", headers=attacker_headers)
    assert revoke.status_code == 404

    still_active = client.get("/api/v1/users/me/sessions", headers=owner_headers).json()["data"]
    assert any(s["id"] == owner_session["id"] for s in still_active)


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


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


def test_administrator_cannot_self_escalate_to_super_administrator(client, db_session_factory):
    admin_email = "admin-escalation@example.com"
    admin_token = register_and_login(client, admin_email)
    asyncio.run(_promote_to_admin(db_session_factory, admin_email))
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    me = client.get("/api/v1/users/me", headers=admin_headers).json()["data"]

    response = client.post(
        f"/api/v1/users/{me['id']}/role", json={"role": "super_administrator"}, headers=admin_headers
    )

    assert response.status_code == 403
    me_after = client.get("/api/v1/users/me", headers=admin_headers).json()["data"]
    assert me_after["role"] == "administrator"


def test_administrator_cannot_grant_role_above_own(client, db_session_factory):
    admin_email = "admin-granter@example.com"
    admin_token = register_and_login(client, admin_email)
    asyncio.run(_promote_to_admin(db_session_factory, admin_email))
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    target_token = register_and_login(client, "role-target@example.com")
    target_headers = {"Authorization": f"Bearer {target_token}"}
    target = client.get("/api/v1/users/me", headers=target_headers).json()["data"]

    response = client.post(
        f"/api/v1/users/{target['id']}/role", json={"role": "super_administrator"}, headers=admin_headers
    )

    assert response.status_code == 403
    target_after = client.get("/api/v1/users/me", headers=target_headers).json()["data"]
    assert target_after["role"] == "free"


def test_administrator_can_grant_role_at_or_below_own(client, db_session_factory):
    admin_email = "admin-grants-fine@example.com"
    admin_token = register_and_login(client, admin_email)
    asyncio.run(_promote_to_admin(db_session_factory, admin_email))
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    target_token = register_and_login(client, "role-target-ok@example.com")
    target_headers = {"Authorization": f"Bearer {target_token}"}
    target = client.get("/api/v1/users/me", headers=target_headers).json()["data"]

    response = client.post(
        f"/api/v1/users/{target['id']}/role", json={"role": "analyst"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "analyst"


def test_login_records_ip_and_user_agent_on_session(client):
    client.post("/api/v1/auth/register", json={"email": "geo@example.com", "password": "correct-horse-battery"})
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "geo@example.com", "password": "correct-horse-battery"},
        headers={"User-Agent": "titaniq-test-client/1.0"},
    )
    token = login.json()["data"]["access_token"]

    sessions = client.get("/api/v1/users/me/sessions", headers={"Authorization": f"Bearer {token}"}).json()["data"]

    assert len(sessions) == 1
    assert sessions[0]["ip_address"] is not None


def test_role_gate_denial_is_audited(client, db_session_factory):
    token = register_and_login(client, "auditee@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/users/me", headers=headers).json()["data"]

    response = client.post(f"/api/v1/users/{me['id']}/role", json={"role": "analyst"}, headers=headers)
    assert response.status_code == 403

    async def _read_audit_entries():
        async with db_session_factory() as session:
            repo = SqlAlchemyAuditLogRepository(session=session)
            return await repo.list_by_actor(UserId(uuid.UUID(me["id"])))

    entries = asyncio.run(_read_audit_entries())
    assert any(e.action == AuditAction.PERMISSION_DENIED for e in entries)


def test_offline_register_returns_404_when_disabled(client, monkeypatch):
    monkeypatch.setenv("TITANIQ_ENABLE_OFFLINE_AUTH", "false")

    response = client.post("/api/v1/auth/register", json={"email": "gated@example.com", "password": "hunter22222"})

    assert response.status_code == 404


def test_self_created_token_gets_a_default_expiry(client):
    token = register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/users/me/tokens", json={"name": "ci"}, headers=headers).json()["data"]

    assert created["expires_at"] is not None


def test_self_created_token_expiry_is_capped(client):
    token = register_and_login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/users/me/tokens", json={"name": "long-lived", "expires_in_days": 10000}, headers=headers
    ).json()["data"]

    from datetime import datetime, timezone

    expires_at = datetime.fromisoformat(created["expires_at"])
    assert (expires_at - datetime.now(timezone.utc)).days <= 366


def test_offline_login_returns_404_when_disabled(client, monkeypatch):
    register_and_login(client, email="gate-login@example.com")
    monkeypatch.setenv("TITANIQ_ENABLE_OFFLINE_AUTH", "false")

    response = client.post(
        "/api/v1/auth/login", json={"email": "gate-login@example.com", "password": "correct-horse-battery"}
    )

    assert response.status_code == 404

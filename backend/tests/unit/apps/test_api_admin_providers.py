"""Endpoint tests for the Provider Registry API (Milestone 11B) — every route added to
main.py's "Provider Registry" section, exercised through a real TestClient/FastAPI dependency
override the same way tests/unit/apps/test_api_prediction_admin.py does.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.admin.infrastructure.vault import get_vault_settings
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator

T0 = datetime(2026, 7, 30, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "admin": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(AdminBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory, monkeypatch):
    # FernetCredentialVault (modules/admin/infrastructure/vault.py) requires a real key —
    # matches the pattern already used in tests/unit/apps/test_api_ingestion.py.
    monkeypatch.setenv("TITANIQ_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()
    # get_vault_settings() is process-lifetime @lru_cache'd (vault.py) — clear it so this test's
    # monkeypatched key doesn't leak into other test modules' vault-dependent tests that run
    # later in the same pytest session (full-suite run, not just this file in isolation).
    get_vault_settings.cache_clear()


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


def _admin_headers(client, db_session_factory, email="provider-admin@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _regular_headers(client, email="provider-regular@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _register_provider(client, headers, key="api_football", **overrides):
    body = {"key": key, "name": "API-Football", "category": "sports_data", "priority": 50}
    body.update(overrides)
    return client.post("/api/v1/admin/providers", json=body, headers=headers)


# -- RBAC ------------------------------------------------------------------------------------


def test_create_provider_requires_administrator_role(client, db_session_factory):
    headers = _regular_headers(client)

    response = _register_provider(client, headers)

    assert response.status_code == 403


# -- CRUD ------------------------------------------------------------------------------------


def test_create_and_get_provider(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    created = _register_provider(
        client, headers, base_url="https://v3.football.api-sports.io", auth_type="api_key_header",
    )
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["key"] == "api_football"
    assert data["status"] == "inactive"
    assert data["base_url"] == "https://v3.football.api-sports.io"
    assert data["created_by"] is not None

    fetched = client.get(f"/api/v1/admin/providers/{data['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["key"] == "api_football"


def test_create_duplicate_key_conflicts(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    _register_provider(client, headers)

    response = _register_provider(client, headers)

    assert response.status_code == 409


def test_create_invalid_category_rejected(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = _register_provider(client, headers, key="whatever", category="not_a_real_category")

    assert response.status_code == 422


def test_update_provider_patches_fields(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]

    response = client.patch(
        f"/api/v1/admin/providers/{provider_id}", json={"priority": 10, "region": "eu"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["data"]["priority"] == 10
    assert response.json()["data"]["region"] == "eu"


def test_delete_provider_removes_it(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]

    deleted = client.delete(f"/api/v1/admin/providers/{provider_id}", headers=headers)
    assert deleted.status_code == 200

    fetched = client.get(f"/api/v1/admin/providers/{provider_id}", headers=headers)
    assert fetched.status_code == 404


def test_delete_unknown_provider_404s(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.delete("/api/v1/admin/providers/00000000-0000-0000-0000-000000000000", headers=headers)

    assert response.status_code == 404


# -- Activate / disable ------------------------------------------------------------------------


def test_activate_then_disable_provider(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]

    activated = client.post(f"/api/v1/admin/providers/{provider_id}/activate", headers=headers)
    assert activated.json()["data"]["status"] == "active"

    disabled = client.post(f"/api/v1/admin/providers/{provider_id}/disable", headers=headers)
    assert disabled.json()["data"]["status"] == "inactive"


# -- Credentials -------------------------------------------------------------------------------


def test_add_credential_returns_masked_value_only(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]

    response = client.post(
        f"/api/v1/admin/providers/{provider_id}/credentials",
        json={"label": "primary", "value": "sk-live-abc123456789A4X9"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["masked_value"].endswith("A4X9")
    assert "sk-live" not in data["masked_value"]


def test_list_credentials_shows_masked_values(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]
    client.post(
        f"/api/v1/admin/providers/{provider_id}/credentials",
        json={"label": "primary", "value": "sk-live-verysecretvalue"},
        headers=headers,
    )

    response = client.get(f"/api/v1/admin/providers/{provider_id}/credentials", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert "sk-live" not in response.json()["data"][0]["masked_value"]


def test_rotate_key_deactivates_old_credential(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]
    old = client.post(
        f"/api/v1/admin/providers/{provider_id}/credentials",
        json={"label": "primary", "value": "sk-old-value"},
        headers=headers,
    ).json()["data"]

    rotated = client.post(
        f"/api/v1/admin/providers/{provider_id}/rotate-key",
        json={"old_credential_id": old["id"], "label": "primary-rotated", "value": "sk-new-value"},
        headers=headers,
    )

    assert rotated.status_code == 200
    remaining = client.get(f"/api/v1/admin/providers/{provider_id}/credentials", headers=headers).json()["data"]
    active = [c for c in remaining if c["is_active"]]
    assert len(active) == 1
    assert active[0]["label"] == "primary-rotated"


# -- Import from .env --------------------------------------------------------------------------


def test_import_from_env_creates_provider_and_credential(client, db_session_factory, monkeypatch):
    monkeypatch.setenv("TITANIQ_TEST_API_ENDPOINT_NEWSAPI_KEY", "sk-newsapi-realvalue1234")
    headers = _admin_headers(client, db_session_factory)

    response = client.post(
        "/api/v1/admin/providers/import-from-env",
        json={
            "env_var_name": "TITANIQ_TEST_API_ENDPOINT_NEWSAPI_KEY",
            "key": "newsapi",
            "name": "NewsAPI",
            "category": "news",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"]["key"] == "newsapi"
    assert data["credential"]["masked_value"].endswith("1234")


def test_import_from_env_missing_var_422s(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.post(
        "/api/v1/admin/providers/import-from-env",
        json={"env_var_name": "TITANIQ_TEST_DEFINITELY_UNSET", "key": "x", "name": "X", "category": "general"},
        headers=headers,
    )

    assert response.status_code == 422


# -- Connection test / usage / history / categories / status -----------------------------------


def test_connection_test_not_configured_without_base_url(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]

    response = client.post(f"/api/v1/admin/providers/{provider_id}/test", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "not_configured"


def test_usage_endpoint_returns_zero_for_fresh_provider(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]

    response = client.get(f"/api/v1/admin/providers/{provider_id}/usage", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["current_window_requests"] == 0


def test_history_endpoint_returns_empty_lists_for_fresh_provider(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]

    response = client.get(f"/api/v1/admin/providers/{provider_id}/history", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["recent_checks"] == []
    assert response.json()["data"]["incidents"] == []


def test_categories_endpoint_counts_registered_providers(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    _register_provider(client, headers, key="api_football", category="sports_data")
    _register_provider(client, headers, key="odds_api", category="odds")

    response = client.get("/api/v1/admin/providers/categories", headers=headers)

    assert response.status_code == 200
    by_category = {row["category"]: row["provider_count"] for row in response.json()["data"]}
    assert by_category["sports_data"] == 1
    assert by_category["odds"] == 1
    assert by_category["news"] == 0


def test_status_endpoint_aggregates_by_status(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]
    client.post(f"/api/v1/admin/providers/{provider_id}/activate", headers=headers)

    response = client.get("/api/v1/admin/providers/status", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["total_providers"] == 1
    assert response.json()["data"]["by_status"]["active"] == 1


# -- Audit trail ---------------------------------------------------------------------------------


def test_provider_actions_write_audit_entries(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    provider_id = _register_provider(client, headers).json()["data"]["id"]
    client.post(f"/api/v1/admin/providers/{provider_id}/activate", headers=headers)

    async def _fetch_audit():
        from modules.identity.infrastructure.persistence.repositories import SqlAlchemyAuditLogRepository

        async with db_session_factory() as session:
            repo = SqlAlchemyAuditLogRepository(session=session)
            return await repo.list_by_target("provider", provider_id)

    entries = asyncio.run(_fetch_audit())
    actions = {e.action.value for e in entries}
    assert "provider_registered" in actions
    assert "provider_activated" in actions

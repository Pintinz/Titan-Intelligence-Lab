"""Authorization (RBAC) dimension of the Milestone 6 integration suite (docs/security.md).

Unlike ``tests/unit/apps/test_api_identity.py`` (which overrides ``get_session``/
``get_jwt_validator`` with SQLite + ``MockJWTValidator``), this drives the REAL
``apps.api.main.app`` wiring end-to-end: a real Supabase-issued JWT, validated by the real
``SupabaseJWKSValidator``, against the real live database. This is the only tier that proves
the actual production dependency wiring works, not just each piece in isolation.

Requires ``TITANIQ_DB_URL`` (the app's own DB config) to ALSO point at the live Postgres
instance for this run — set it to the same value as ``TITANIQ_INTEGRATION_DB_URL`` when
running this file specifically (docs/supabase.md "Running the integration suite").
"""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import requires_supabase_api

TEST_PASSWORD = "Integration-Test-Passw0rd!"

requires_live_app_db = pytest.mark.skipif(
    "asyncpg" not in os.environ.get("TITANIQ_DB_URL", ""),
    reason="TITANIQ_DB_URL must point at the live Postgres instance to exercise the real app wiring",
)


@pytest.fixture
def app_client():
    from apps.api.main import app

    return TestClient(app)


@requires_supabase_api
@requires_live_app_db
def test_authenticated_user_can_read_own_profile(supabase_client: httpx.Client, app_client, unique_test_email):
    signup = supabase_client.post("/auth/v1/signup", json={"email": unique_test_email, "password": TEST_PASSWORD})
    assert signup.status_code in (200, 201), signup.text
    access_token = signup.json().get("access_token")
    if access_token is None:
        pytest.skip("Project requires email confirmation before issuing a session")

    response = app_client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json()["data"]["email"] == unique_test_email
    assert response.json()["data"]["role"] == "free"


@requires_supabase_api
@requires_live_app_db
def test_free_tier_user_cannot_change_roles(supabase_client: httpx.Client, app_client, unique_test_email):
    signup = supabase_client.post("/auth/v1/signup", json={"email": unique_test_email, "password": TEST_PASSWORD})
    assert signup.status_code in (200, 201), signup.text
    access_token = signup.json().get("access_token")
    if access_token is None:
        pytest.skip("Project requires email confirmation before issuing a session")
    headers = {"Authorization": f"Bearer {access_token}"}
    me = app_client.get("/api/v1/users/me", headers=headers).json()["data"]

    response = app_client.post(f"/api/v1/users/{me['id']}/role", json={"role": "administrator"}, headers=headers)

    assert response.status_code == 403


@requires_supabase_api
def test_missing_bearer_token_is_rejected(app_client):
    response = app_client.get("/api/v1/users/me")

    assert response.status_code == 401

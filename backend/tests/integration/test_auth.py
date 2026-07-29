"""Authentication dimension of the Milestone 6 integration suite (docs/authentication.md).

Exercises Supabase Auth's real REST API (GoTrue) — the one thing the fast offline suite
structurally cannot cover, since it only ever uses ``MockJWTValidator``. This is also the only
place ``SupabaseJWKSValidator`` gets tested against a JWT it didn't mint itself, closing the
gap between "the validator's code compiles" and "the validator can actually verify a real
Supabase-issued token."
"""

from __future__ import annotations

import httpx
import pytest

from modules.identity.infrastructure.security import SupabaseJWKSValidator
from tests.integration.conftest import SUPABASE_PROJECT_URL, requires_supabase_api

TEST_PASSWORD = "Integration-Test-Passw0rd!"


@requires_supabase_api
def test_signup_returns_access_token(supabase_client: httpx.Client, unique_test_email: str):
    response = supabase_client.post(
        "/auth/v1/signup", json={"email": unique_test_email, "password": TEST_PASSWORD}
    )

    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert "access_token" in body or body.get("id") is not None


@requires_supabase_api
async def test_real_jwt_validates_via_supabase_jwks_validator(supabase_client: httpx.Client, unique_test_email: str):
    signup = supabase_client.post("/auth/v1/signup", json={"email": unique_test_email, "password": TEST_PASSWORD})
    assert signup.status_code in (200, 201), signup.text
    body = signup.json()

    access_token = body.get("access_token")
    if access_token is None:
        pytest.skip("Project requires email confirmation before issuing a session — no token to validate yet")

    validator = SupabaseJWKSValidator(project_url=SUPABASE_PROJECT_URL)
    claims = await validator.validate(access_token)

    assert claims["email"] == unique_test_email
    assert "sub" in claims


@requires_supabase_api
def test_login_with_wrong_password_is_rejected(supabase_client: httpx.Client, unique_test_email: str):
    supabase_client.post("/auth/v1/signup", json={"email": unique_test_email, "password": TEST_PASSWORD})

    response = supabase_client.post(
        "/auth/v1/token?grant_type=password", json={"email": unique_test_email, "password": "definitely-wrong"}
    )

    assert response.status_code in (400, 401)

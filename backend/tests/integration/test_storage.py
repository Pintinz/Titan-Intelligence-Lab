"""Storage dimension of the Milestone 6 integration suite (docs/supabase.md).

Verifies the bucket/policy configuration from migration 0013 against the real Storage REST
API: an authenticated user can write into their own folder, cannot write into someone else's,
and public buckets are readable without auth.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.integration.conftest import SUPABASE_PROJECT_URL, requires_supabase_api

TEST_PASSWORD = "Integration-Test-Passw0rd!"
_PNG_BYTES = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010802000000907724")  # minimal PNG header


def _sign_up_and_get_token(supabase_client: httpx.Client, email: str) -> tuple[str, str]:
    response = supabase_client.post("/auth/v1/signup", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code in (200, 201), response.text
    body = response.json()
    token = body.get("access_token")
    user_id = (body.get("user") or body).get("id")
    return token, user_id


@requires_supabase_api
def test_user_can_upload_to_own_avatar_folder(supabase_client: httpx.Client, unique_test_email: str):
    token, user_id = _sign_up_and_get_token(supabase_client, unique_test_email)
    if token is None:
        pytest.skip("Project requires email confirmation before issuing a session")

    response = httpx.put(
        f"{SUPABASE_PROJECT_URL}/storage/v1/object/avatars/{user_id}/test-avatar.png",
        content=_PNG_BYTES,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "image/png"},
        timeout=15.0,
    )

    assert response.status_code in (200, 201), response.text


@requires_supabase_api
def test_user_cannot_upload_to_another_users_avatar_folder(supabase_client: httpx.Client, unique_test_email: str):
    token, _user_id = _sign_up_and_get_token(supabase_client, unique_test_email)
    if token is None:
        pytest.skip("Project requires email confirmation before issuing a session")
    someone_elses_folder = str(uuid.uuid4())

    response = httpx.put(
        f"{SUPABASE_PROJECT_URL}/storage/v1/object/avatars/{someone_elses_folder}/hijacked.png",
        content=_PNG_BYTES,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "image/png"},
        timeout=15.0,
    )

    assert response.status_code in (400, 401, 403)


@requires_supabase_api
def test_avatars_bucket_is_publicly_readable(supabase_client: httpx.Client, unique_test_email: str):
    token, user_id = _sign_up_and_get_token(supabase_client, unique_test_email)
    if token is None:
        pytest.skip("Project requires email confirmation before issuing a session")
    httpx.put(
        f"{SUPABASE_PROJECT_URL}/storage/v1/object/avatars/{user_id}/public-read-test.png",
        content=_PNG_BYTES,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "image/png"},
        timeout=15.0,
    )

    response = httpx.get(f"{SUPABASE_PROJECT_URL}/storage/v1/object/public/avatars/{user_id}/public-read-test.png", timeout=15.0)

    assert response.status_code == 200


@requires_supabase_api
def test_private_bucket_rejects_unauthenticated_read(unique_test_email: str):
    response = httpx.get(f"{SUPABASE_PROJECT_URL}/storage/v1/object/uploads/some-user-id/some-file.pdf", timeout=15.0)

    assert response.status_code in (400, 401, 403, 404)

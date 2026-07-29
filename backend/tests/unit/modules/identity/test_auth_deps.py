from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from apps.api.auth_deps import _authenticate_via_jwt
from modules.identity.application.identity_service import IdentityService
from modules.identity.domain.value_objects import IdentityProvider
from modules.identity.infrastructure.security import (
    BcryptPasswordHasher,
    MockJWTValidator,
    Sha256TokenHasher,
)


def now():
    return datetime.now(timezone.utc)


def _service(
    user_repo, federated_identity_repo, token_repo, session_repo, security_event_repo, account_lock_repo, audit_log_repo
):
    return IdentityService(
        users=user_repo,
        federated_identities=federated_identity_repo,
        tokens=token_repo,
        sessions=session_repo,
        security_events=security_event_repo,
        account_locks=account_lock_repo,
        audit_log=audit_log_repo,
        password_hasher=BcryptPasswordHasher(rounds=4),
        token_hasher=Sha256TokenHasher(),
    )


async def test_email_login_does_not_create_federated_identity(
    user_repo, federated_identity_repo, token_repo, session_repo, security_event_repo, account_lock_repo, audit_log_repo
):
    service = _service(
        user_repo, federated_identity_repo, token_repo, session_repo, security_event_repo, account_lock_repo, audit_log_repo
    )
    validator = MockJWTValidator()
    user_id = str(uuid4())
    validator.register("email-token", {"sub": user_id, "email": "plain@example.com", "app_metadata": {"provider": "email"}})

    user = await _authenticate_via_jwt("email-token", validator, service)

    assert user is not None
    assert federated_identity_repo.store == {}


async def test_google_oauth_login_links_federated_identity(
    user_repo, federated_identity_repo, token_repo, session_repo, security_event_repo, account_lock_repo, audit_log_repo
):
    service = _service(
        user_repo, federated_identity_repo, token_repo, session_repo, security_event_repo, account_lock_repo, audit_log_repo
    )
    validator = MockJWTValidator()
    user_id = str(uuid4())
    validator.register(
        "google-token", {"sub": user_id, "email": "oauth@example.com", "app_metadata": {"provider": "google"}}
    )

    user = await _authenticate_via_jwt("google-token", validator, service)

    assert user is not None
    linked = list(federated_identity_repo.store.values())
    assert len(linked) == 1
    assert linked[0].provider is IdentityProvider.GOOGLE
    assert linked[0].provider_user_id == user_id


async def test_repeated_google_oauth_login_does_not_duplicate_link(
    user_repo, federated_identity_repo, token_repo, session_repo, security_event_repo, account_lock_repo, audit_log_repo
):
    service = _service(
        user_repo, federated_identity_repo, token_repo, session_repo, security_event_repo, account_lock_repo, audit_log_repo
    )
    validator = MockJWTValidator()
    user_id = str(uuid4())
    validator.register(
        "google-token", {"sub": user_id, "email": "oauth2@example.com", "app_metadata": {"provider": "google"}}
    )

    await _authenticate_via_jwt("google-token", validator, service)
    await _authenticate_via_jwt("google-token", validator, service)

    assert len(federated_identity_repo.store) == 1

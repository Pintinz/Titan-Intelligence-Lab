from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.identity.application.identity_service import (
    AccountLockedError,
    IdentityService,
    InvalidCredentialsError,
)
from modules.identity.domain.value_objects import (
    AuditAction,
    Email,
    IdentityProvider,
    Role,
    SecurityEventType,
    UserId,
    UserStatus,
)


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def service(
    user_repo,
    federated_identity_repo,
    token_repo,
    session_repo,
    security_event_repo,
    account_lock_repo,
    audit_log_repo,
    password_hasher,
    token_hasher,
):
    return IdentityService(
        users=user_repo,
        federated_identities=federated_identity_repo,
        tokens=token_repo,
        sessions=session_repo,
        security_events=security_event_repo,
        account_locks=account_lock_repo,
        audit_log=audit_log_repo,
        password_hasher=password_hasher,
        token_hasher=token_hasher,
    )


async def test_register_creates_pending_user(service):
    user = await service.register(Email("alice@example.com"), "correct horse", now())

    assert user.status is UserStatus.PENDING_VERIFICATION
    assert user.role is Role.FREE
    assert user.password_hash != "correct horse"


async def test_register_duplicate_email_rejected(service):
    await service.register(Email("alice@example.com"), "pw1", now())

    with pytest.raises(ValueError):
        await service.register(Email("ALICE@example.com"), "pw2", now())


async def test_authenticate_succeeds_with_correct_password(service):
    await service.register(Email("bob@example.com"), "s3cret!", now())

    result = await service.authenticate(Email("bob@example.com"), "s3cret!", now(), ip_address="1.2.3.4")

    assert result.user.email == Email("bob@example.com")
    assert result.session.ip_address == "1.2.3.4"
    assert result.user.last_login_at is not None


async def test_authenticate_rejects_wrong_password(service):
    await service.register(Email("carol@example.com"), "correct", now())

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(Email("carol@example.com"), "wrong", now())


async def test_authenticate_rejects_unknown_email(service):
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(Email("nobody@example.com"), "whatever", now())


async def test_repeated_failures_lock_the_account(service, account_lock_repo):
    await service.register(Email("dave@example.com"), "correct", now())
    t = now()

    for _ in range(service.max_consecutive_failures):
        with pytest.raises(InvalidCredentialsError):
            await service.authenticate(Email("dave@example.com"), "wrong", t)

    with pytest.raises(AccountLockedError):
        await service.authenticate(Email("dave@example.com"), "correct", t)


async def test_successful_login_clears_prior_failures(service, account_lock_repo):
    user = await service.register(Email("erin@example.com"), "correct", now())
    t = now()
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(Email("erin@example.com"), "wrong", t)

    await service.authenticate(Email("erin@example.com"), "correct", t)

    state = await account_lock_repo.get(user.id)
    assert state.consecutive_failures == 0


async def test_brute_force_detection_fires_before_lockout(service, security_event_repo):
    await service.register(Email("frank@example.com"), "correct", now())
    t = now()
    assert service.brute_force_threshold <= service.max_consecutive_failures

    for _ in range(service.brute_force_threshold):
        with pytest.raises(InvalidCredentialsError):
            await service.authenticate(Email("frank@example.com"), "wrong", t)

    brute_force_events = [e for e in security_event_repo.events if e.event_type is SecurityEventType.BRUTE_FORCE_DETECTED]
    assert len(brute_force_events) == 1


async def test_ensure_provisioned_creates_shadow_user_once(service, user_repo):
    supabase_id = UserId(uuid4())
    email = Email("shadow@example.com")

    first = await service.ensure_provisioned(supabase_id, email, now())
    second = await service.ensure_provisioned(supabase_id, email, now())

    assert first.id == second.id == supabase_id
    assert first.status is UserStatus.ACTIVE
    assert first.email_verified is True
    assert len(user_repo.store) == 1


async def test_link_federated_identity(service, federated_identity_repo):
    user = await service.register(Email("gina@example.com"), "pw", now())

    identity = await service.link_federated_identity(user.id, IdentityProvider.GOOGLE, "google-sub-123", "gina@gmail.com", now())

    assert identity.provider is IdentityProvider.GOOGLE
    assert await federated_identity_repo.get_by_provider(IdentityProvider.GOOGLE, "google-sub-123") is not None


async def test_ensure_federated_identity_linked_is_idempotent(service, federated_identity_repo, audit_log_repo):
    user = await service.register(Email("hank2@example.com"), "pw", now())

    first = await service.ensure_federated_identity_linked(
        user.id, IdentityProvider.GITHUB, "gh-sub-1", "hank2@github.local", now()
    )
    second = await service.ensure_federated_identity_linked(
        user.id, IdentityProvider.GITHUB, "gh-sub-1", "hank2@github.local", now()
    )

    assert first.id == second.id
    assert len(federated_identity_repo.store) == 1
    link_events = [e for e in audit_log_repo.entries if e.action is AuditAction.IDENTITY_LINKED]
    assert len(link_events) == 1


async def test_session_revocation(service):
    await service.register(Email("hank@example.com"), "pw", now())
    result = await service.authenticate(Email("hank@example.com"), "pw", now())

    await service.revoke_session(result.session.id, now())

    active = await service.list_active_sessions(result.user.id)
    assert active == []


async def test_pat_lifecycle(service):
    user = await service.register(Email("iris@example.com"), "pw", now())

    token, raw = await service.create_personal_access_token(user.id, "ci-token", ["read"], now())
    authenticated = await service.authenticate_with_token(raw, now())
    assert authenticated is not None and authenticated.id == user.id

    await service.revoke_personal_access_token(token.id, now(), actor=user.id)
    assert await service.authenticate_with_token(raw, now()) is None


async def test_pat_expiry_is_enforced(service):
    user = await service.register(Email("jack@example.com"), "pw", now())
    t = now()
    _, raw = await service.create_personal_access_token(user.id, "short-lived", ["*"], t, expires_at=t + timedelta(seconds=1))

    assert await service.authenticate_with_token(raw, t + timedelta(seconds=5)) is None


async def test_change_role_emits_audit_entry(service, audit_log_repo):
    user = await service.register(Email("kate@example.com"), "pw", now())
    actor = UserId(uuid4())

    updated = await service.change_role(user.id, Role.ANALYST, now(), actor)

    assert updated.role is Role.ANALYST
    role_changes = [e for e in audit_log_repo.entries if e.action is AuditAction.ROLE_CHANGED]
    assert len(role_changes) == 1
    assert role_changes[0].metadata == {"old_role": "free", "new_role": "analyst"}


async def test_change_role_unknown_user_raises(service):
    with pytest.raises(ValueError):
        await service.change_role(UserId(uuid4()), Role.PREMIUM, now(), UserId(uuid4()))

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.identity.domain.entities import (
    AccountLockState,
    AuditLogEntry,
    FederatedIdentity,
    PersonalAccessToken,
    Profile,
    SecurityEvent,
    Session,
    User,
)
from modules.identity.domain.value_objects import (
    AuditAction,
    AuditEventId,
    Email,
    FederatedIdentityId,
    IdentityProvider,
    Role,
    SecurityEventId,
    SecurityEventType,
    SessionId,
    SessionRiskLevel,
    TokenId,
    UserId,
    UserStatus,
)
from modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyAccountLockRepository,
    SqlAlchemyAuditLogRepository,
    SqlAlchemyFederatedIdentityRepository,
    SqlAlchemyPersonalAccessTokenRepository,
    SqlAlchemyProfileRepository,
    SqlAlchemySecurityEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)


def now():
    return datetime.now(timezone.utc)


async def _make_user(session) -> User:
    repo = SqlAlchemyUserRepository(session=session)
    user = User(id=UserId(uuid4()), email=Email("test@example.com"), role=Role.FREE, status=UserStatus.ACTIVE)
    return await repo.upsert(user)


async def test_user_repository_round_trip(sqlite_session):
    repo = SqlAlchemyUserRepository(session=sqlite_session)
    user = User(id=UserId(uuid4()), email=Email("Round@Example.com"), role=Role.PREMIUM, status=UserStatus.ACTIVE)

    await repo.upsert(user)
    await sqlite_session.commit()

    fetched = await repo.get(user.id)
    assert fetched.email == Email("round@example.com")
    assert fetched.role is Role.PREMIUM

    by_email = await repo.get_by_email(Email("ROUND@example.com"))
    assert by_email.id == user.id


async def test_profile_repository_round_trip(sqlite_session):
    user = await _make_user(sqlite_session)
    repo = SqlAlchemyProfileRepository(session=sqlite_session)

    profile = Profile(user_id=user.id, display_name="Test User", timezone="Europe/London")
    await repo.upsert(profile)
    await sqlite_session.commit()

    fetched = await repo.get(user.id)
    assert fetched.display_name == "Test User"
    assert fetched.timezone == "Europe/London"


async def test_federated_identity_repository_round_trip(sqlite_session):
    user = await _make_user(sqlite_session)
    repo = SqlAlchemyFederatedIdentityRepository(session=sqlite_session)

    identity = FederatedIdentity(
        id=FederatedIdentityId(uuid4()), user_id=user.id, provider=IdentityProvider.GITHUB, provider_user_id="gh-42"
    )
    await repo.upsert(identity)
    await sqlite_session.commit()

    fetched = await repo.get_by_provider(IdentityProvider.GITHUB, "gh-42")
    assert fetched.user_id == user.id

    linked = await repo.list_by_user(user.id)
    assert len(linked) == 1

    await repo.delete(identity.id)
    await sqlite_session.commit()
    assert await repo.get(identity.id) is None


async def test_pat_repository_round_trip(sqlite_session):
    user = await _make_user(sqlite_session)
    repo = SqlAlchemyPersonalAccessTokenRepository(session=sqlite_session)

    token = PersonalAccessToken(id=TokenId(uuid4()), user_id=user.id, name="ci", token_hash="hash123", scopes=["read", "write"])
    await repo.upsert(token)
    await sqlite_session.commit()

    fetched = await repo.get_by_hash("hash123")
    assert fetched.scopes == ["read", "write"]
    assert (await repo.list_by_user(user.id))[0].id == token.id


async def test_session_repository_round_trip(sqlite_session):
    user = await _make_user(sqlite_session)
    repo = SqlAlchemySessionRepository(session=sqlite_session)

    session_entity = Session(id=SessionId(uuid4()), user_id=user.id, risk_level=SessionRiskLevel.MEDIUM)
    await repo.upsert(session_entity)
    await sqlite_session.commit()

    active = await repo.list_active_by_user(user.id)
    assert len(active) == 1
    assert active[0].risk_level is SessionRiskLevel.MEDIUM

    session_entity.revoked_at = now()
    await repo.upsert(session_entity)
    await sqlite_session.commit()
    assert await repo.list_active_by_user(user.id) == []


async def test_security_event_repository_filters_by_window(sqlite_session):
    repo = SqlAlchemySecurityEventRepository(session=sqlite_session)
    t = now()

    old_event = SecurityEvent(
        id=SecurityEventId(uuid4()), event_type=SecurityEventType.LOGIN_FAILURE, occurred_at=t, email_attempted="x@example.com"
    )
    await repo.record(old_event)
    await sqlite_session.commit()

    recent = await repo.list_recent_by_email("x@example.com", t - timedelta(minutes=1))
    assert len(recent) == 1
    too_recent = await repo.list_recent_by_email("x@example.com", t + timedelta(minutes=1))
    assert too_recent == []


async def test_account_lock_repository_round_trip(sqlite_session):
    user = await _make_user(sqlite_session)
    repo = SqlAlchemyAccountLockRepository(session=sqlite_session)

    state = AccountLockState(user_id=user.id, consecutive_failures=3)
    await repo.upsert(state)
    await sqlite_session.commit()

    fetched = await repo.get(user.id)
    assert fetched.consecutive_failures == 3


async def test_audit_log_repository_append_and_query(sqlite_session):
    user = await _make_user(sqlite_session)
    repo = SqlAlchemyAuditLogRepository(session=sqlite_session)

    entry = AuditLogEntry(
        id=AuditEventId(uuid4()),
        action=AuditAction.USER_REGISTERED,
        occurred_at=now(),
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
    )
    await repo.append(entry)
    await sqlite_session.commit()

    by_actor = await repo.list_by_actor(user.id)
    assert len(by_actor) == 1
    by_target = await repo.list_by_target("user", str(user.id))
    assert len(by_target) == 1

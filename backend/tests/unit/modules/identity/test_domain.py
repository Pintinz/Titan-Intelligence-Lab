from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.identity.domain.entities import AccountLockState, PersonalAccessToken, Session
from modules.identity.domain.value_objects import Email, Role, SessionId, TokenId, UserId


def now():
    return datetime.now(timezone.utc)


@pytest.mark.parametrize(
    "role,minimum,expected",
    [
        (Role.SUPER_ADMINISTRATOR, Role.GUEST, True),
        (Role.GUEST, Role.SUPER_ADMINISTRATOR, False),
        (Role.PREMIUM, Role.PREMIUM, True),
        (Role.FREE, Role.PREMIUM, False),
    ],
)
def test_role_at_least(role, minimum, expected):
    assert role.at_least(minimum) is expected


def test_email_normalizes_case_and_whitespace():
    assert Email("  Alice@Example.COM ") == Email("alice@example.com")


def test_email_rejects_missing_at_sign():
    with pytest.raises(ValueError):
        Email("not-an-email")


def test_pat_is_expired():
    t = now()
    token = PersonalAccessToken(
        id=TokenId(uuid4()), user_id=UserId(uuid4()), name="t", token_hash="h", expires_at=t + timedelta(hours=1)
    )
    assert token.is_expired(t + timedelta(hours=2)) is True
    assert token.is_expired(t) is False


def test_pat_has_scope_wildcard():
    token = PersonalAccessToken(id=TokenId(uuid4()), user_id=UserId(uuid4()), name="t", token_hash="h", scopes=["*"])
    assert token.has_scope("anything") is True


def test_pat_has_scope_exact():
    token = PersonalAccessToken(id=TokenId(uuid4()), user_id=UserId(uuid4()), name="t", token_hash="h", scopes=["read"])
    assert token.has_scope("read") is True
    assert token.has_scope("write") is False


def test_pat_revoked_is_not_active():
    token = PersonalAccessToken(id=TokenId(uuid4()), user_id=UserId(uuid4()), name="t", token_hash="h", revoked_at=now())
    assert token.is_active is False


def test_session_is_active_until_revoked():
    session = Session(id=SessionId(uuid4()), user_id=UserId(uuid4()))
    assert session.is_active is True
    session.revoked_at = now()
    assert session.is_active is False


def test_account_lock_state_is_locked():
    t = now()
    state = AccountLockState(user_id=UserId(uuid4()), locked_until=t + timedelta(minutes=5))
    assert state.is_locked(t) is True
    assert state.is_locked(t + timedelta(minutes=10)) is False


def test_account_lock_state_unlocked_by_default():
    state = AccountLockState(user_id=UserId(uuid4()))
    assert state.is_locked(now()) is False

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
from modules.identity.domain.value_objects import FederatedIdentityId, SessionId, TokenId, UserId
from modules.identity.infrastructure.persistence.models import Base
from modules.identity.infrastructure.security import BcryptPasswordHasher, MockJWTValidator, Sha256TokenHasher


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemoryUserRepository:
    store: dict[UserId, User] = field(default_factory=dict)

    async def get(self, user_id):
        return self.store.get(user_id)

    async def get_by_email(self, email):
        return next((u for u in self.store.values() if u.email == email), None)

    async def upsert(self, user):
        self.store[user.id] = user
        return user


@dataclass
class InMemoryProfileRepository:
    store: dict[UserId, Profile] = field(default_factory=dict)

    async def get(self, user_id):
        return self.store.get(user_id)

    async def upsert(self, profile):
        self.store[profile.user_id] = profile
        return profile


@dataclass
class InMemoryFederatedIdentityRepository:
    store: dict[FederatedIdentityId, FederatedIdentity] = field(default_factory=dict)

    async def get(self, identity_id):
        return self.store.get(identity_id)

    async def get_by_provider(self, provider, provider_user_id):
        return next(
            (i for i in self.store.values() if i.provider == provider and i.provider_user_id == provider_user_id),
            None,
        )

    async def list_by_user(self, user_id):
        return [i for i in self.store.values() if i.user_id == user_id]

    async def upsert(self, identity):
        self.store[identity.id] = identity
        return identity

    async def delete(self, identity_id):
        self.store.pop(identity_id, None)


@dataclass
class InMemoryPersonalAccessTokenRepository:
    store: dict[TokenId, PersonalAccessToken] = field(default_factory=dict)

    async def get(self, token_id):
        return self.store.get(token_id)

    async def get_by_hash(self, token_hash):
        return next((t for t in self.store.values() if t.token_hash == token_hash), None)

    async def list_by_user(self, user_id):
        return [t for t in self.store.values() if t.user_id == user_id]

    async def upsert(self, token):
        self.store[token.id] = token
        return token


@dataclass
class InMemorySessionRepository:
    store: dict[SessionId, Session] = field(default_factory=dict)

    async def get(self, session_id):
        return self.store.get(session_id)

    async def list_active_by_user(self, user_id):
        return [s for s in self.store.values() if s.user_id == user_id and s.is_active]

    async def upsert(self, session):
        self.store[session.id] = session
        return session


@dataclass
class InMemorySecurityEventRepository:
    events: list[SecurityEvent] = field(default_factory=list)

    async def record(self, event):
        self.events.append(event)
        return event

    async def list_recent_by_email(self, email, since):
        return [e for e in self.events if e.email_attempted == email and e.occurred_at >= since]

    async def list_recent_by_user(self, user_id, since):
        return [e for e in self.events if e.user_id == user_id and e.occurred_at >= since]


@dataclass
class InMemoryAccountLockRepository:
    store: dict[UserId, AccountLockState] = field(default_factory=dict)

    async def get(self, user_id):
        return self.store.get(user_id)

    async def upsert(self, state):
        self.store[state.user_id] = state
        return state


@dataclass
class InMemoryAuditLogRepository:
    entries: list[AuditLogEntry] = field(default_factory=list)

    async def append(self, entry):
        self.entries.append(entry)
        return entry

    async def list_by_actor(self, actor_user_id, limit=100):
        return [e for e in self.entries if e.actor_user_id == actor_user_id][:limit]

    async def list_by_target(self, target_type, target_id):
        return [e for e in self.entries if e.target_type == target_type and e.target_id == target_id]


@pytest.fixture
def user_repo():
    return InMemoryUserRepository()


@pytest.fixture
def profile_repo():
    return InMemoryProfileRepository()


@pytest.fixture
def federated_identity_repo():
    return InMemoryFederatedIdentityRepository()


@pytest.fixture
def token_repo():
    return InMemoryPersonalAccessTokenRepository()


@pytest.fixture
def session_repo():
    return InMemorySessionRepository()


@pytest.fixture
def security_event_repo():
    return InMemorySecurityEventRepository()


@pytest.fixture
def account_lock_repo():
    return InMemoryAccountLockRepository()


@pytest.fixture
def audit_log_repo():
    return InMemoryAuditLogRepository()


@pytest.fixture
def password_hasher():
    return BcryptPasswordHasher(rounds=4)  # low cost factor — this is a test fixture, not production config


@pytest.fixture
def token_hasher():
    return Sha256TokenHasher()


@pytest.fixture
def jwt_validator():
    return MockJWTValidator()

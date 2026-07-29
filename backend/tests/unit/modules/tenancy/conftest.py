from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.identity.domain.entities import AuditLogEntry
from modules.identity.domain.value_objects import UserId
from modules.tenancy.domain.entities import Invitation, Membership, Organization, Team
from modules.tenancy.domain.value_objects import InvitationId, MembershipId, OrganizationId, TeamId
from modules.tenancy.infrastructure.persistence.models import Base


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"tenancy": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemoryOrganizationRepository:
    store: dict[OrganizationId, Organization] = field(default_factory=dict)

    async def get(self, organization_id):
        return self.store.get(organization_id)

    async def get_by_slug(self, slug):
        return next((o for o in self.store.values() if o.slug == slug), None)

    async def list_owned_by(self, owner_user_id):
        return [o for o in self.store.values() if o.owner_user_id == owner_user_id]

    async def upsert(self, organization):
        self.store[organization.id] = organization
        return organization


@dataclass
class InMemoryTeamRepository:
    store: dict[TeamId, Team] = field(default_factory=dict)

    async def get(self, team_id):
        return self.store.get(team_id)

    async def list_by_organization(self, organization_id):
        return [t for t in self.store.values() if t.organization_id == organization_id]

    async def upsert(self, team):
        self.store[team.id] = team
        return team


@dataclass
class InMemoryMembershipRepository:
    store: dict[MembershipId, Membership] = field(default_factory=dict)

    async def get(self, membership_id):
        return self.store.get(membership_id)

    async def get_for_user(self, organization_id, user_id):
        return next(
            (m for m in self.store.values() if m.organization_id == organization_id and m.user_id == user_id), None
        )

    async def list_by_organization(self, organization_id):
        return [m for m in self.store.values() if m.organization_id == organization_id]

    async def list_by_user(self, user_id):
        return [m for m in self.store.values() if m.user_id == user_id]

    async def upsert(self, membership):
        self.store[membership.id] = membership
        return membership

    async def delete(self, membership_id):
        self.store.pop(membership_id, None)


@dataclass
class InMemoryInvitationRepository:
    store: dict[InvitationId, Invitation] = field(default_factory=dict)

    async def get(self, invitation_id):
        return self.store.get(invitation_id)

    async def get_by_token_hash(self, token_hash):
        return next((i for i in self.store.values() if i.token_hash == token_hash), None)

    async def list_by_organization(self, organization_id):
        return [i for i in self.store.values() if i.organization_id == organization_id]

    async def upsert(self, invitation):
        self.store[invitation.id] = invitation
        return invitation


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


class FakeTokenHasher:
    """Deterministic, non-cryptographic stand-in — good enough for tests that only need
    generate()/hash() to round-trip consistently."""

    def generate(self) -> str:
        import secrets

        return secrets.token_hex(16)

    def hash(self, raw_token: str) -> str:
        return f"hashed:{raw_token}"


@pytest.fixture
def organization_repo():
    return InMemoryOrganizationRepository()


@pytest.fixture
def team_repo():
    return InMemoryTeamRepository()


@pytest.fixture
def membership_repo():
    return InMemoryMembershipRepository()


@pytest.fixture
def invitation_repo():
    return InMemoryInvitationRepository()


@pytest.fixture
def audit_log_repo():
    return InMemoryAuditLogRepository()


@pytest.fixture
def token_hasher():
    return FakeTokenHasher()

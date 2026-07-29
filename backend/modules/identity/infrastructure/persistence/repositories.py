from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    Email,
    FederatedIdentityId,
    IdentityProvider,
    SessionId,
    TokenId,
    UserId,
)
from modules.identity.infrastructure.persistence import mappers
from modules.identity.infrastructure.persistence.models import (
    AccountLockStateModel,
    AuditLogEntryModel,
    FederatedIdentityModel,
    PersonalAccessTokenModel,
    ProfileModel,
    SecurityEventModel,
    SessionModel,
    UserModel,
)


@dataclass
class SqlAlchemyUserRepository:
    session: AsyncSession

    async def get(self, user_id: UserId) -> User | None:
        model = await self.session.get(UserModel, user_id.value)
        return mappers.user_to_domain(model) if model else None

    async def get_by_email(self, email: Email) -> User | None:
        result = await self.session.execute(select(UserModel).where(UserModel.email == str(email)))
        model = result.scalar_one_or_none()
        return mappers.user_to_domain(model) if model else None

    async def upsert(self, user: User) -> User:
        existing = await self.session.get(UserModel, user.id.value)
        model = mappers.user_to_model(user, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.user_to_domain(model)


@dataclass
class SqlAlchemyProfileRepository:
    session: AsyncSession

    async def get(self, user_id: UserId) -> Profile | None:
        model = await self.session.get(ProfileModel, user_id.value)
        return mappers.profile_to_domain(model) if model else None

    async def upsert(self, profile: Profile) -> Profile:
        existing = await self.session.get(ProfileModel, profile.user_id.value)
        model = mappers.profile_to_model(profile, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.profile_to_domain(model)


@dataclass
class SqlAlchemyFederatedIdentityRepository:
    session: AsyncSession

    async def get(self, identity_id: FederatedIdentityId) -> FederatedIdentity | None:
        model = await self.session.get(FederatedIdentityModel, identity_id.value)
        return mappers.federated_identity_to_domain(model) if model else None

    async def get_by_provider(self, provider: IdentityProvider, provider_user_id: str) -> FederatedIdentity | None:
        stmt = select(FederatedIdentityModel).where(
            FederatedIdentityModel.provider == provider.value,
            FederatedIdentityModel.provider_user_id == provider_user_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.federated_identity_to_domain(model) if model else None

    async def list_by_user(self, user_id: UserId) -> list[FederatedIdentity]:
        stmt = select(FederatedIdentityModel).where(FederatedIdentityModel.user_id == user_id.value)
        result = await self.session.execute(stmt)
        return [mappers.federated_identity_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, identity: FederatedIdentity) -> FederatedIdentity:
        existing = await self.session.get(FederatedIdentityModel, identity.id.value)
        model = mappers.federated_identity_to_model(identity, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.federated_identity_to_domain(model)

    async def delete(self, identity_id: FederatedIdentityId) -> None:
        model = await self.session.get(FederatedIdentityModel, identity_id.value)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()


@dataclass
class SqlAlchemyPersonalAccessTokenRepository:
    session: AsyncSession

    async def get(self, token_id: TokenId) -> PersonalAccessToken | None:
        model = await self.session.get(PersonalAccessTokenModel, token_id.value)
        return mappers.pat_to_domain(model) if model else None

    async def get_by_hash(self, token_hash: str) -> PersonalAccessToken | None:
        stmt = select(PersonalAccessTokenModel).where(PersonalAccessTokenModel.token_hash == token_hash)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.pat_to_domain(model) if model else None

    async def list_by_user(self, user_id: UserId) -> list[PersonalAccessToken]:
        stmt = select(PersonalAccessTokenModel).where(PersonalAccessTokenModel.user_id == user_id.value)
        result = await self.session.execute(stmt)
        return [mappers.pat_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, token: PersonalAccessToken) -> PersonalAccessToken:
        existing = await self.session.get(PersonalAccessTokenModel, token.id.value)
        model = mappers.pat_to_model(token, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.pat_to_domain(model)


@dataclass
class SqlAlchemySessionRepository:
    session: AsyncSession

    async def get(self, session_id: SessionId) -> Session | None:
        model = await self.session.get(SessionModel, session_id.value)
        return mappers.session_to_domain(model) if model else None

    async def list_active_by_user(self, user_id: UserId) -> list[Session]:
        stmt = select(SessionModel).where(SessionModel.user_id == user_id.value, SessionModel.revoked_at.is_(None))
        result = await self.session.execute(stmt)
        return [mappers.session_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, session: Session) -> Session:
        existing = await self.session.get(SessionModel, session.id.value)
        model = mappers.session_to_model(session, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.session_to_domain(model)


@dataclass
class SqlAlchemySecurityEventRepository:
    session: AsyncSession

    async def record(self, event: SecurityEvent) -> SecurityEvent:
        model = mappers.security_event_to_model(event)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.security_event_to_domain(model)

    async def list_recent_by_email(self, email: str, since: datetime) -> list[SecurityEvent]:
        stmt = select(SecurityEventModel).where(
            SecurityEventModel.email_attempted == email, SecurityEventModel.occurred_at >= since
        )
        result = await self.session.execute(stmt)
        return [mappers.security_event_to_domain(row) for row in result.scalars().all()]

    async def list_recent_by_user(self, user_id: UserId, since: datetime) -> list[SecurityEvent]:
        stmt = select(SecurityEventModel).where(
            SecurityEventModel.user_id == user_id.value, SecurityEventModel.occurred_at >= since
        )
        result = await self.session.execute(stmt)
        return [mappers.security_event_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyAccountLockRepository:
    session: AsyncSession

    async def get(self, user_id: UserId) -> AccountLockState | None:
        model = await self.session.get(AccountLockStateModel, user_id.value)
        return mappers.lock_state_to_domain(model) if model else None

    async def upsert(self, state: AccountLockState) -> AccountLockState:
        existing = await self.session.get(AccountLockStateModel, state.user_id.value)
        model = mappers.lock_state_to_model(state, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.lock_state_to_domain(model)


@dataclass
class SqlAlchemyAuditLogRepository:
    """No update/delete method — matches ``AuditLogRepositoryPort``'s append-only contract."""

    session: AsyncSession

    async def append(self, entry: AuditLogEntry) -> AuditLogEntry:
        model = mappers.audit_entry_to_model(entry)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.audit_entry_to_domain(model)

    async def list_by_actor(self, actor_user_id: UserId, limit: int = 100) -> list[AuditLogEntry]:
        stmt = (
            select(AuditLogEntryModel)
            .where(AuditLogEntryModel.actor_user_id == actor_user_id.value)
            .order_by(AuditLogEntryModel.occurred_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.audit_entry_to_domain(row) for row in result.scalars().all()]

    async def list_by_target(self, target_type: str, target_id: str) -> list[AuditLogEntry]:
        stmt = (
            select(AuditLogEntryModel)
            .where(AuditLogEntryModel.target_type == target_type, AuditLogEntryModel.target_id == target_id)
            .order_by(AuditLogEntryModel.occurred_at.desc())
        )
        result = await self.session.execute(stmt)
        return [mappers.audit_entry_to_domain(row) for row in result.scalars().all()]

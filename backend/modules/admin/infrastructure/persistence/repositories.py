from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.admin.domain.entities import (
    FeatureFlag,
    ProviderCredential,
    ProviderDefinition,
    ProviderHealthCheck,
    ProviderHealthState,
    ProviderIncident,
    ProviderUsageRecord,
)
from modules.admin.domain.value_objects import CredentialId, FlagId, IncidentId, ProviderId, QuotaPeriod
from modules.admin.infrastructure.persistence import mappers
from modules.admin.infrastructure.persistence.models import (
    FeatureFlagModel,
    ProviderCredentialModel,
    ProviderHealthCheckModel,
    ProviderHealthStateModel,
    ProviderIncidentModel,
    ProviderModel,
    ProviderUsageRecordModel,
)


@dataclass
class SqlAlchemyProviderRepository:
    session: AsyncSession

    async def get(self, provider_id: ProviderId) -> ProviderDefinition | None:
        model = await self.session.get(ProviderModel, provider_id.value)
        return mappers.provider_to_domain(model) if model else None

    async def get_by_key(self, key: str) -> ProviderDefinition | None:
        result = await self.session.execute(select(ProviderModel).where(ProviderModel.key == key))
        model = result.scalar_one_or_none()
        return mappers.provider_to_domain(model) if model else None

    async def list_all(self) -> list[ProviderDefinition]:
        result = await self.session.execute(select(ProviderModel))
        return [mappers.provider_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, provider: ProviderDefinition) -> ProviderDefinition:
        existing = await self.session.get(ProviderModel, provider.id.value)
        model = mappers.provider_to_model(provider, existing)
        self.session.add(model)
        await self.session.flush()
        # `updated_at` (onupdate=func.now()) is expired by the flush on an UPDATE — SQLite's
        # driver doesn't eagerly fetch onupdate-computed values the way INSERT's server_default
        # does, so reading model.updated_at below would trigger an implicit, un-awaited lazy
        # reload (SQLAlchemy's "MissingGreenlet" failure mode) unless explicitly refreshed here.
        await self.session.refresh(model)
        return mappers.provider_to_domain(model)

    async def delete(self, provider_id: ProviderId) -> None:
        model = await self.session.get(ProviderModel, provider_id.value)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()


@dataclass
class SqlAlchemyCredentialRepository:
    session: AsyncSession

    async def get(self, credential_id: CredentialId) -> ProviderCredential | None:
        model = await self.session.get(ProviderCredentialModel, credential_id.value)
        return mappers.credential_to_domain(model) if model else None

    async def list_by_provider(self, provider_id: ProviderId) -> list[ProviderCredential]:
        # Real incident, 2026-08-29: with no ORDER BY, `usable_credentials()`'s `[0]` picked
        # whichever row the database happened to return first — in practice the OLDEST one on a
        # simple unordered scan. Re-saving a provider's credential after a TITANIQ_ENCRYPTION_KEY
        # rotation added a new, working row alongside the old, now-undecryptable one, but the old
        # row kept being the one actually used — the "fix" silently never took effect. Newest
        # first makes "add a fresh credential" actually mean "use this one going forward".
        result = await self.session.execute(
            select(ProviderCredentialModel)
            .where(ProviderCredentialModel.provider_id == provider_id.value)
            .order_by(ProviderCredentialModel.created_at.desc())
        )
        return [mappers.credential_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, credential: ProviderCredential) -> ProviderCredential:
        existing = await self.session.get(ProviderCredentialModel, credential.id.value)
        model = mappers.credential_to_model(credential, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.credential_to_domain(model)

    async def delete(self, credential_id: CredentialId) -> None:
        model = await self.session.get(ProviderCredentialModel, credential_id.value)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()


@dataclass
class SqlAlchemyUsageRepository:
    session: AsyncSession

    async def get(
        self,
        provider_id: ProviderId,
        period: QuotaPeriod,
        window_key: str,
        credential_id: CredentialId | None = None,
    ) -> ProviderUsageRecord | None:
        stmt = select(ProviderUsageRecordModel).where(
            ProviderUsageRecordModel.provider_id == provider_id.value,
            ProviderUsageRecordModel.period == period.value,
            ProviderUsageRecordModel.window_key == window_key,
            ProviderUsageRecordModel.credential_id == (credential_id.value if credential_id else None),
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return mappers.usage_to_domain(model) if model else None

    async def upsert(self, record: ProviderUsageRecord) -> ProviderUsageRecord:
        existing_stmt = select(ProviderUsageRecordModel).where(
            ProviderUsageRecordModel.provider_id == record.provider_id.value,
            ProviderUsageRecordModel.period == record.period.value,
            ProviderUsageRecordModel.window_key == record.window_key,
            ProviderUsageRecordModel.credential_id
            == (record.credential_id.value if record.credential_id else None),
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        model = mappers.usage_to_model(record, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.usage_to_domain(model)

    async def list_by_provider(
        self, provider_id: ProviderId, period: QuotaPeriod, limit: int = 30
    ) -> list[ProviderUsageRecord]:
        stmt = (
            select(ProviderUsageRecordModel)
            .where(
                ProviderUsageRecordModel.provider_id == provider_id.value,
                ProviderUsageRecordModel.period == period.value,
            )
            .order_by(ProviderUsageRecordModel.window_key.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.usage_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyHealthRepository:
    session: AsyncSession

    async def record(self, check: ProviderHealthCheck) -> ProviderHealthCheck:
        model = mappers.health_check_to_model(check)
        self.session.add(model)
        await self.session.flush()
        return mappers.health_check_to_domain(model)

    async def list_recent(self, provider_id: ProviderId, limit: int = 20) -> list[ProviderHealthCheck]:
        stmt = (
            select(ProviderHealthCheckModel)
            .where(ProviderHealthCheckModel.provider_id == provider_id.value)
            .order_by(ProviderHealthCheckModel.checked_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.health_check_to_domain(row) for row in result.scalars().all()]

    async def list_since(self, provider_id: ProviderId, since: datetime) -> list[ProviderHealthCheck]:
        stmt = select(ProviderHealthCheckModel).where(
            ProviderHealthCheckModel.provider_id == provider_id.value,
            ProviderHealthCheckModel.checked_at >= since,
        )
        result = await self.session.execute(stmt)
        return [mappers.health_check_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyHealthStateRepository:
    session: AsyncSession

    async def get(self, provider_id: ProviderId) -> ProviderHealthState | None:
        model = await self.session.get(ProviderHealthStateModel, provider_id.value)
        return mappers.health_state_to_domain(model) if model else None

    async def upsert(self, state: ProviderHealthState) -> ProviderHealthState:
        existing = await self.session.get(ProviderHealthStateModel, state.provider_id.value)
        model = mappers.health_state_to_model(state, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.health_state_to_domain(model)


@dataclass
class SqlAlchemyIncidentRepository:
    session: AsyncSession

    async def get(self, incident_id: IncidentId) -> ProviderIncident | None:
        model = await self.session.get(ProviderIncidentModel, incident_id.value)
        return mappers.incident_to_domain(model) if model else None

    async def list_by_provider(self, provider_id: ProviderId) -> list[ProviderIncident]:
        stmt = (
            select(ProviderIncidentModel)
            .where(ProviderIncidentModel.provider_id == provider_id.value)
            .order_by(ProviderIncidentModel.opened_at.desc())
        )
        result = await self.session.execute(stmt)
        return [mappers.incident_to_domain(row) for row in result.scalars().all()]

    async def list_open(self, provider_id: ProviderId) -> list[ProviderIncident]:
        stmt = select(ProviderIncidentModel).where(
            ProviderIncidentModel.provider_id == provider_id.value,
            ProviderIncidentModel.resolved_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return [mappers.incident_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, incident: ProviderIncident) -> ProviderIncident:
        existing = await self.session.get(ProviderIncidentModel, incident.id.value)
        model = mappers.incident_to_model(incident, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.incident_to_domain(model)


@dataclass
class SqlAlchemyFeatureFlagRepository:
    session: AsyncSession

    async def get(self, flag_id: FlagId) -> FeatureFlag | None:
        model = await self.session.get(FeatureFlagModel, flag_id.value)
        return mappers.feature_flag_to_domain(model) if model else None

    async def get_by_key(self, key: str) -> FeatureFlag | None:
        result = await self.session.execute(select(FeatureFlagModel).where(FeatureFlagModel.key == key))
        model = result.scalar_one_or_none()
        return mappers.feature_flag_to_domain(model) if model else None

    async def list_all(self) -> list[FeatureFlag]:
        result = await self.session.execute(select(FeatureFlagModel))
        return [mappers.feature_flag_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, flag: FeatureFlag) -> FeatureFlag:
        existing = await self.session.get(FeatureFlagModel, flag.id.value)
        model = mappers.feature_flag_to_model(flag, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.feature_flag_to_domain(model)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ingestion.domain.entities import (
    DataQualityReport,
    ProviderRefIndexEntry,
    SyncCheckpoint,
    SyncRun,
    TimelineEvent,
)
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId
from modules.ingestion.infrastructure.persistence import mappers
from modules.ingestion.infrastructure.persistence.models import (
    DataQualityReportModel,
    ProviderRefIndexModel,
    SyncCheckpointModel,
    SyncRunModel,
    TimelineEventModel,
)


@dataclass
class SqlAlchemySyncRunRepository:
    session: AsyncSession

    async def record(self, run: SyncRun) -> SyncRun:
        model = mappers.sync_run_to_model(run)
        self.session.add(model)
        await self.session.flush()
        return mappers.sync_run_to_domain(model)

    async def update(self, run: SyncRun) -> SyncRun:
        existing = await self.session.get(SyncRunModel, run.id.value)
        model = mappers.sync_run_to_model(run, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.sync_run_to_domain(model)

    async def get(self, run_id: SyncRunId) -> SyncRun | None:
        model = await self.session.get(SyncRunModel, run_id.value)
        return mappers.sync_run_to_domain(model) if model else None

    async def list_recent(
        self, sport_code: str | None = None, entity_kind: EntityKind | None = None, limit: int = 50
    ) -> list[SyncRun]:
        conditions = []
        if sport_code is not None:
            conditions.append(SyncRunModel.sport_code == sport_code)
        if entity_kind is not None:
            conditions.append(SyncRunModel.entity_kind == entity_kind.value)
        stmt = select(SyncRunModel).where(*conditions).order_by(SyncRunModel.started_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.sync_run_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemySyncCheckpointRepository:
    session: AsyncSession

    async def get(self, sport_code: str, entity_kind: EntityKind, scope_key: str) -> SyncCheckpoint | None:
        stmt = select(SyncCheckpointModel).where(
            SyncCheckpointModel.sport_code == sport_code,
            SyncCheckpointModel.entity_kind == entity_kind.value,
            SyncCheckpointModel.scope_key == scope_key,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.checkpoint_to_domain(model) if model else None

    async def upsert(self, checkpoint: SyncCheckpoint) -> SyncCheckpoint:
        stmt = select(SyncCheckpointModel).where(
            SyncCheckpointModel.sport_code == checkpoint.sport_code,
            SyncCheckpointModel.entity_kind == checkpoint.entity_kind.value,
            SyncCheckpointModel.scope_key == checkpoint.scope_key,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        model = mappers.checkpoint_to_model(checkpoint, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.checkpoint_to_domain(model)


@dataclass
class SqlAlchemyTimelineEventRepository:
    session: AsyncSession

    async def record(self, event: TimelineEvent) -> TimelineEvent:
        model = mappers.timeline_event_to_model(event)
        self.session.add(model)
        await self.session.flush()
        return mappers.timeline_event_to_domain(model)

    async def list_recent(
        self,
        entity_kind: EntityKind | None = None,
        entity_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[TimelineEvent]:
        conditions = []
        if entity_kind is not None:
            conditions.append(TimelineEventModel.entity_kind == entity_kind.value)
        if entity_id is not None:
            conditions.append(TimelineEventModel.entity_id == entity_id)
        if since is not None:
            conditions.append(TimelineEventModel.occurred_at >= since)
        stmt = select(TimelineEventModel).where(*conditions).order_by(TimelineEventModel.occurred_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.timeline_event_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyDataQualityReportRepository:
    session: AsyncSession

    async def record(self, report: DataQualityReport) -> DataQualityReport:
        model = mappers.quality_report_to_model(report)
        self.session.add(model)
        await self.session.flush()
        return mappers.quality_report_to_domain(model)

    async def get_latest(self, sport_code: str, entity_kind: EntityKind) -> DataQualityReport | None:
        stmt = (
            select(DataQualityReportModel)
            .where(DataQualityReportModel.sport_code == sport_code, DataQualityReportModel.entity_kind == entity_kind.value)
            .order_by(DataQualityReportModel.generated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.quality_report_to_domain(model) if model else None

    async def list_by_entity_kind(
        self, sport_code: str, entity_kind: EntityKind, limit: int = 50
    ) -> list[DataQualityReport]:
        stmt = (
            select(DataQualityReportModel)
            .where(DataQualityReportModel.sport_code == sport_code, DataQualityReportModel.entity_kind == entity_kind.value)
            .order_by(DataQualityReportModel.generated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.quality_report_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyProviderRefIndexRepository:
    session: AsyncSession

    async def get(self, provider: str, external_id: str, entity_kind: EntityKind) -> str | None:
        stmt = select(ProviderRefIndexModel).where(
            ProviderRefIndexModel.provider == provider,
            ProviderRefIndexModel.external_id == external_id,
            ProviderRefIndexModel.entity_kind == entity_kind.value,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return model.entity_id if model else None

    async def upsert(self, entry: ProviderRefIndexEntry) -> ProviderRefIndexEntry:
        stmt = select(ProviderRefIndexModel).where(
            ProviderRefIndexModel.provider == entry.provider,
            ProviderRefIndexModel.external_id == entry.external_id,
            ProviderRefIndexModel.entity_kind == entry.entity_kind.value,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        model = mappers.ref_index_to_model(entry, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.ref_index_to_domain(model)

"""Repository ports for the ingestion module's offline (Postgres) store."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from modules.ingestion.domain.entities import (
    CompetitionFixtureSourcePreference,
    DataQualityReport,
    ProviderRefIndexEntry,
    SyncCheckpoint,
    SyncRun,
    TimelineEvent,
)
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId


class SyncRunRepositoryPort(Protocol):
    async def record(self, run: SyncRun) -> SyncRun: ...
    async def update(self, run: SyncRun) -> SyncRun: ...
    async def get(self, run_id: SyncRunId) -> SyncRun | None: ...
    async def list_recent(
        self, sport_code: str | None = None, entity_kind: EntityKind | None = None, limit: int = 50
    ) -> list[SyncRun]: ...


class SyncCheckpointRepositoryPort(Protocol):
    async def get(self, sport_code: str, entity_kind: EntityKind, scope_key: str) -> SyncCheckpoint | None: ...
    async def upsert(self, checkpoint: SyncCheckpoint) -> SyncCheckpoint: ...


class TimelineEventRepositoryPort(Protocol):
    async def record(self, event: TimelineEvent) -> TimelineEvent: ...
    async def list_recent(
        self,
        entity_kind: EntityKind | None = None,
        entity_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[TimelineEvent]: ...


class DataQualityReportRepositoryPort(Protocol):
    async def record(self, report: DataQualityReport) -> DataQualityReport: ...
    async def get_latest(self, sport_code: str, entity_kind: EntityKind) -> DataQualityReport | None: ...
    async def list_by_entity_kind(
        self, sport_code: str, entity_kind: EntityKind, limit: int = 50
    ) -> list[DataQualityReport]: ...


class ProviderRefIndexRepositoryPort(Protocol):
    async def get(self, provider: str, external_id: str, entity_kind: EntityKind) -> str | None:
        """Returns the internal entity id (as a string), or None if unseen."""
        ...

    async def upsert(self, entry: ProviderRefIndexEntry) -> ProviderRefIndexEntry: ...


class CompetitionFixtureSourceRepositoryPort(Protocol):
    async def get_by_competition(self, competition_id: str) -> CompetitionFixtureSourcePreference | None: ...
    async def upsert(self, preference: CompetitionFixtureSourcePreference) -> CompetitionFixtureSourcePreference: ...
    async def delete(self, competition_id: str) -> None: ...
    async def list_all(self) -> list[CompetitionFixtureSourcePreference]: ...

"""Repository ports for the Feature Intelligence Platform's offline (Postgres) store."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from modules.features.domain.entities import (
    FeatureComputationLog,
    FeatureConsumer,
    FeatureDefinition,
    FeatureDefinitionVersionSnapshot,
    FeatureDriftReport,
    FeatureLineageEdge,
    FeatureUsageRecord,
    FeatureValidationReport,
    FeatureValue,
)
from modules.features.domain.value_objects import EntityType, FeatureKey


class FeatureDefinitionRepositoryPort(Protocol):
    async def get(self, feature_key: FeatureKey) -> FeatureDefinition | None: ...
    async def list_by_sport(self, sport_code: str) -> list[FeatureDefinition]: ...
    async def list_all(self) -> list[FeatureDefinition]: ...
    async def upsert(self, definition: FeatureDefinition) -> FeatureDefinition: ...


class FeatureVersionRepositoryPort(Protocol):
    async def record(self, snapshot: FeatureDefinitionVersionSnapshot) -> FeatureDefinitionVersionSnapshot: ...
    async def list_by_feature(self, feature_key: FeatureKey) -> list[FeatureDefinitionVersionSnapshot]: ...


class FeatureValueRepositoryPort(Protocol):
    """Offline store — the audited historical record (docs/database_schema.md §3)."""

    async def record(self, value: FeatureValue) -> FeatureValue: ...
    async def get_latest(
        self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str
    ) -> FeatureValue | None: ...
    async def get_as_of(
        self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str, as_of: datetime
    ) -> FeatureValue | None:
        """Milestone 4 point-in-time retrieval — the value as it was known at or before `as_of`,
        never a value recorded after it. `get_latest()` above answers "what do we know right
        now"; this answers "what did we know at time T", the distinction Rule 5/§1.1 of
        docs/milestone2_market_feature_news_mapping.md identifies as previously non-existent
        anywhere in this codebase. Historical feature reconstruction must call this, never
        `get_latest()`, once a caller needs point-in-time correctness."""
        ...
    async def list_history(
        self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str, limit: int = 100
    ) -> list[FeatureValue]: ...
    async def list_all_recent(
        self, feature_key: FeatureKey, since: datetime | None = None, limit: int = 5000
    ) -> list[FeatureValue]:
        """Every value across every entity for this feature, newest first — the aggregate
        source FeatureQualityEngine computes statistics/scores from. ``since=None`` means
        unbounded (all history)."""
        ...


class FeatureLineageRepositoryPort(Protocol):
    async def add_edge(self, edge: FeatureLineageEdge) -> FeatureLineageEdge: ...
    async def list_dependencies(self, feature_key: FeatureKey) -> list[FeatureKey]: ...
    async def list_dependents(self, feature_key: FeatureKey) -> list[FeatureKey]: ...


class FeatureDriftReportRepositoryPort(Protocol):
    async def record(self, report: FeatureDriftReport) -> FeatureDriftReport: ...
    async def list_by_feature(self, feature_key: FeatureKey, limit: int = 50) -> list[FeatureDriftReport]: ...


class FeatureValidationReportRepositoryPort(Protocol):
    async def record(self, report: FeatureValidationReport) -> FeatureValidationReport: ...
    async def get_latest(self, feature_key: FeatureKey) -> FeatureValidationReport | None: ...
    async def list_by_feature(self, feature_key: FeatureKey, limit: int = 50) -> list[FeatureValidationReport]: ...


class FeatureComputationLogRepositoryPort(Protocol):
    async def record(self, log: FeatureComputationLog) -> FeatureComputationLog: ...
    async def list_since(self, feature_key: FeatureKey, since: datetime) -> list[FeatureComputationLog]: ...


class FeatureConsumerRepositoryPort(Protocol):
    async def register(self, consumer: FeatureConsumer) -> FeatureConsumer: ...
    async def list_by_feature(self, feature_key: FeatureKey) -> list[FeatureConsumer]: ...


class FeatureUsageRepositoryPort(Protocol):
    async def get(self, feature_key: FeatureKey, window_key: str) -> FeatureUsageRecord | None: ...
    async def upsert(self, record: FeatureUsageRecord) -> FeatureUsageRecord: ...
    async def list_since(self, feature_key: FeatureKey, since_window_key: str) -> list[FeatureUsageRecord]: ...

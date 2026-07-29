"""Sports Data Ingestion Engine entities (docs/roadmap.md Milestone 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.ingestion.domain.value_objects import (
    DataQualityReportId,
    EntityKind,
    SyncRunId,
    SyncStatus,
    SyncTrigger,
    TimelineEventId,
    TimelineEventType,
)


@dataclass
class SyncRun:
    """One execution of the sync orchestrator for a (sport, entity_kind, scope) — the record
    "Synchronization Monitoring" (docs/roadmap.md Milestone 5) reads from."""

    id: SyncRunId
    sport_code: str
    entity_kind: EntityKind
    scope_key: str
    trigger: SyncTrigger
    status: SyncStatus
    started_at: datetime
    finished_at: datetime | None = None
    records_fetched: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_rejected: int = 0
    validation_failures: int = 0
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def mark_succeeded(self, now: datetime) -> None:
        self.status = SyncStatus.SUCCEEDED if self.records_rejected == 0 else SyncStatus.PARTIAL
        self.finished_at = now

    def mark_failed(self, now: datetime, error_message: str) -> None:
        self.status = SyncStatus.FAILED
        self.finished_at = now
        self.error_message = error_message


@dataclass
class SyncCheckpoint:
    """Incremental-sync state for one (sport, entity_kind, scope_key) triple — "never reload
    complete datasets unnecessarily" (docs/roadmap.md Milestone 5). ``cursor`` is an opaque
    provider-specific pagination/delta token, passed through unexamined by the orchestrator."""

    sport_code: str
    entity_kind: EntityKind
    scope_key: str
    last_synced_at: datetime | None = None
    last_success_at: datetime | None = None
    cursor: str | None = None
    consecutive_failures: int = 0


@dataclass
class TimelineEvent:
    """One immutable timeline entry — never updated or deleted after creation. Doubles as the
    ingestion audit log (docs/decisions.md ADR — Event Timeline Engine / Audit Logging)."""

    id: TimelineEventId
    event_type: TimelineEventType
    occurred_at: datetime
    actor: str = "ingestion"
    sport_code: str | None = None
    entity_kind: EntityKind | None = None
    entity_id: str | None = None
    payload: dict = field(default_factory=dict)


@dataclass
class ProviderRefIndexEntry:
    """Maps (provider, external_id, entity_kind) -> internal entity id in O(1), instead of
    scanning every entity's ``provider_ref`` JSON column to find a match. This is the
    reconciliation layer's core lookup structure — every reconciler consults it before
    deciding create-vs-update (docs/decisions.md — provider ref index, avoiding a JSON scan)."""

    provider: str
    external_id: str
    entity_kind: EntityKind
    entity_id: str  # stringified UUID of the internal domain entity


@dataclass
class DataQualityReport:
    """Ingestion-level (raw sports data) quality report — distinct from
    ``modules.features.domain.entities.FeatureValidationReport``, which scores *derived ML
    features*, not raw ingested provider records (docs/decisions.md)."""

    id: DataQualityReportId
    sport_code: str
    entity_kind: EntityKind
    generated_at: datetime
    sample_size: int
    completeness_pct: float | None
    consistency_pct: float | None
    freshness_score: float | None
    accuracy_pct: float | None
    validity_pct: float | None
    reliability_score: float | None
    coverage_pct: float | None
    provider_quality_score: float | None
    quality_score: float | None
    issues: tuple[str, ...] = field(default_factory=tuple)

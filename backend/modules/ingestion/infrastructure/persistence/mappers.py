from __future__ import annotations

from modules.ingestion.domain.entities import (
    CompetitionFixtureSourcePreference,
    DataQualityReport,
    ProviderRefIndexEntry,
    SyncCheckpoint,
    SyncRun,
    TimelineEvent,
)
from modules.ingestion.domain.value_objects import (
    DataQualityReportId,
    EntityKind,
    SyncRunId,
    SyncStatus,
    SyncTrigger,
    TimelineEventId,
    TimelineEventType,
)
from modules.ingestion.infrastructure.persistence.models import (
    CompetitionFixtureSourceModel,
    DataQualityReportModel,
    ProviderRefIndexModel,
    SyncCheckpointModel,
    SyncRunModel,
    TimelineEventModel,
)


def sync_run_to_domain(model: SyncRunModel) -> SyncRun:
    return SyncRun(
        id=SyncRunId(model.id), sport_code=model.sport_code, entity_kind=EntityKind(model.entity_kind),
        scope_key=model.scope_key, trigger=SyncTrigger(model.trigger), status=SyncStatus(model.status),
        started_at=model.started_at, finished_at=model.finished_at, records_fetched=model.records_fetched,
        records_created=model.records_created, records_updated=model.records_updated,
        records_rejected=model.records_rejected, validation_failures=model.validation_failures,
        error_message=model.error_message,
    )


def sync_run_to_model(entity: SyncRun, model: SyncRunModel | None = None) -> SyncRunModel:
    model = model or SyncRunModel(id=entity.id.value)
    model.sport_code = entity.sport_code
    model.entity_kind = entity.entity_kind.value
    model.scope_key = entity.scope_key
    model.trigger = entity.trigger.value
    model.status = entity.status.value
    model.started_at = entity.started_at
    model.finished_at = entity.finished_at
    model.records_fetched = entity.records_fetched
    model.records_created = entity.records_created
    model.records_updated = entity.records_updated
    model.records_rejected = entity.records_rejected
    model.validation_failures = entity.validation_failures
    model.error_message = entity.error_message
    return model


def checkpoint_to_domain(model: SyncCheckpointModel) -> SyncCheckpoint:
    return SyncCheckpoint(
        sport_code=model.sport_code, entity_kind=EntityKind(model.entity_kind), scope_key=model.scope_key,
        last_synced_at=model.last_synced_at, last_success_at=model.last_success_at, cursor=model.cursor,
        consecutive_failures=model.consecutive_failures,
    )


def checkpoint_to_model(entity: SyncCheckpoint, model: SyncCheckpointModel | None = None) -> SyncCheckpointModel:
    model = model or SyncCheckpointModel(
        sport_code=entity.sport_code, entity_kind=entity.entity_kind.value, scope_key=entity.scope_key
    )
    model.last_synced_at = entity.last_synced_at
    model.last_success_at = entity.last_success_at
    model.cursor = entity.cursor
    model.consecutive_failures = entity.consecutive_failures
    return model


def timeline_event_to_domain(model: TimelineEventModel) -> TimelineEvent:
    return TimelineEvent(
        id=TimelineEventId(model.id), event_type=TimelineEventType(model.event_type), occurred_at=model.occurred_at,
        actor=model.actor, sport_code=model.sport_code,
        entity_kind=EntityKind(model.entity_kind) if model.entity_kind else None,
        entity_id=model.entity_id, payload=model.payload,
    )


def timeline_event_to_model(entity: TimelineEvent) -> TimelineEventModel:
    return TimelineEventModel(
        id=entity.id.value, event_type=entity.event_type.value, occurred_at=entity.occurred_at, actor=entity.actor,
        sport_code=entity.sport_code, entity_kind=entity.entity_kind.value if entity.entity_kind else None,
        entity_id=entity.entity_id, payload=entity.payload,
    )


def ref_index_to_domain(model: ProviderRefIndexModel) -> ProviderRefIndexEntry:
    return ProviderRefIndexEntry(
        provider=model.provider, external_id=model.external_id,
        entity_kind=EntityKind(model.entity_kind), entity_id=model.entity_id,
    )


def ref_index_to_model(entity: ProviderRefIndexEntry, model: ProviderRefIndexModel | None = None) -> ProviderRefIndexModel:
    model = model or ProviderRefIndexModel(provider=entity.provider, external_id=entity.external_id, entity_kind=entity.entity_kind.value)
    model.entity_id = entity.entity_id
    return model


def fixture_source_to_domain(model: CompetitionFixtureSourceModel) -> CompetitionFixtureSourcePreference:
    return CompetitionFixtureSourcePreference(
        competition_id=model.competition_id, preferred_provider_key=model.preferred_provider_key,
        provider_competition_ref=model.provider_competition_ref, notes=model.notes, updated_at=model.updated_at,
    )


def fixture_source_to_model(
    entity: CompetitionFixtureSourcePreference, model: CompetitionFixtureSourceModel | None = None
) -> CompetitionFixtureSourceModel:
    model = model or CompetitionFixtureSourceModel(competition_id=entity.competition_id)
    model.preferred_provider_key = entity.preferred_provider_key
    model.provider_competition_ref = entity.provider_competition_ref
    model.notes = entity.notes
    model.updated_at = entity.updated_at
    return model


def quality_report_to_domain(model: DataQualityReportModel) -> DataQualityReport:
    return DataQualityReport(
        id=DataQualityReportId(model.id), sport_code=model.sport_code, entity_kind=EntityKind(model.entity_kind),
        generated_at=model.generated_at, sample_size=model.sample_size, completeness_pct=model.completeness_pct,
        consistency_pct=model.consistency_pct, freshness_score=model.freshness_score, accuracy_pct=model.accuracy_pct,
        validity_pct=model.validity_pct, reliability_score=model.reliability_score, coverage_pct=model.coverage_pct,
        provider_quality_score=model.provider_quality_score, quality_score=model.quality_score,
        issues=tuple(model.issues),
    )


def quality_report_to_model(entity: DataQualityReport) -> DataQualityReportModel:
    return DataQualityReportModel(
        id=entity.id.value, sport_code=entity.sport_code, entity_kind=entity.entity_kind.value,
        generated_at=entity.generated_at, sample_size=entity.sample_size, completeness_pct=entity.completeness_pct,
        consistency_pct=entity.consistency_pct, freshness_score=entity.freshness_score,
        accuracy_pct=entity.accuracy_pct, validity_pct=entity.validity_pct,
        reliability_score=entity.reliability_score, coverage_pct=entity.coverage_pct,
        provider_quality_score=entity.provider_quality_score, quality_score=entity.quality_score,
        issues=list(entity.issues),
    )

"""SQLAlchemy models for the `ingestion` schema (docs/database_schema.md, Milestone 5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, MetaData, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="ingestion")


class Base(DeclarativeBase):
    metadata = metadata


class SyncRunModel(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sport_code: Mapped[str] = mapped_column(String(32), index=True)
    entity_kind: Mapped[str] = mapped_column(String(32), index=True)
    scope_key: Mapped[str] = mapped_column(String(200))
    trigger: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    validation_failures: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class SyncCheckpointModel(Base):
    __tablename__ = "sync_checkpoints"
    __table_args__ = (
        UniqueConstraint("sport_code", "entity_kind", "scope_key", name="uq_sync_checkpoint_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sport_code: Mapped[str] = mapped_column(String(32), index=True)
    entity_kind: Mapped[str] = mapped_column(String(32), index=True)
    scope_key: Mapped[str] = mapped_column(String(200))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class TimelineEventModel(Base):
    __tablename__ = "timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="ingestion")
    sport_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    entity_kind: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ProviderRefIndexModel(Base):
    __tablename__ = "provider_ref_index"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", "entity_kind", name="uq_provider_ref_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(200), index=True)
    entity_kind: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(64))


class DataQualityReportModel(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sport_code: Mapped[str] = mapped_column(String(32), index=True)
    entity_kind: Mapped[str] = mapped_column(String(32), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sample_size: Mapped[int] = mapped_column(Integer)
    completeness_pct: Mapped[float | None] = mapped_column(nullable=True)
    consistency_pct: Mapped[float | None] = mapped_column(nullable=True)
    freshness_score: Mapped[float | None] = mapped_column(nullable=True)
    accuracy_pct: Mapped[float | None] = mapped_column(nullable=True)
    validity_pct: Mapped[float | None] = mapped_column(nullable=True)
    reliability_score: Mapped[float | None] = mapped_column(nullable=True)
    coverage_pct: Mapped[float | None] = mapped_column(nullable=True)
    provider_quality_score: Mapped[float | None] = mapped_column(nullable=True)
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    issues: Mapped[list] = mapped_column(JSON, default=list)

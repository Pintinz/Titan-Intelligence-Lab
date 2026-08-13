"""SQLAlchemy models for the `features` schema — Feature Intelligence Platform, offline store
(docs/database_schema.md §3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, MetaData, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="features")


class Base(DeclarativeBase):
    metadata = metadata


class FeatureDefinitionModel(Base):
    __tablename__ = "feature_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    sport_code: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32))
    formula: Mapped[str] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(16))
    owner: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(16))
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expected_range_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_range_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    update_frequency: Mapped[str] = mapped_column(String(64), default="unspecified")
    online_ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    source_provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    leakage_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Milestone 4 provenance foundation (docs/milestone4_verification_report.md) — complements,
    # does not replace, `leakage_reviewed` above: "PRE_MATCH_SAFE" | "POST_MATCH_ONLY" |
    # "POINT_IN_TIME_REQUIRED" | "UNKNOWN_PROVENANCE". A feature classified POST_MATCH_ONLY must
    # never be mapped into a market's live prediction/training feature set — enforced by
    # `FeatureMarketMappingService.map_feature()` (see that method's own docstring).
    leakage_classification: Mapped[str] = mapped_column(String(32), default="UNKNOWN_PROVENANCE")
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FeatureDefinitionVersionModel(Base):
    __tablename__ = "feature_definition_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class FeatureValueModel(Base):
    __tablename__ = "feature_values_offline"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    entity_type: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[dict] = mapped_column(JSON)  # {"type": "float", "v": 0.42} — see mappers.py
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)


class FeatureLineageEdgeModel(Base):
    __tablename__ = "feature_lineage"
    __table_args__ = (UniqueConstraint("feature_key", "depends_on_feature_key", name="uq_feature_lineage_edge"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    depends_on_feature_key: Mapped[str] = mapped_column(String(200), index=True)


class FeatureDriftReportModel(Base):
    __tablename__ = "feature_drift_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    window: Mapped[str] = mapped_column(String(32))
    drift_score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class FeatureValidationReportModel(Base):
    __tablename__ = "feature_validation_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sample_size: Mapped[int] = mapped_column(Integer)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    freshness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    outlier_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    null_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    invalid_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    issues: Mapped[list] = mapped_column(JSON, default=list)


class FeatureComputationLogModel(Base):
    __tablename__ = "feature_computation_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_ms: Mapped[float] = mapped_column(Float)
    memory_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeatureConsumerModel(Base):
    __tablename__ = "feature_consumers"
    __table_args__ = (UniqueConstraint("feature_key", "consumer_key", name="uq_feature_consumer"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    consumer_key: Mapped[str] = mapped_column(String(200))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeatureUsageRecordModel(Base):
    __tablename__ = "feature_usage_records"
    __table_args__ = (UniqueConstraint("feature_key", "window_key", name="uq_feature_usage_window"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    window_key: Mapped[str] = mapped_column(String(16), index=True)
    read_count: Mapped[int] = mapped_column(Integer, default=0)

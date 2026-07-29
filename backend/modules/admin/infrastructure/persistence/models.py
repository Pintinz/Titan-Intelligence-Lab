"""SQLAlchemy models for the `admin` schema — Provider Management System
(docs/database_schema.md conventions, docs/admin_center.md §2).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="admin")


class Base(DeclarativeBase):
    metadata = metadata


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProviderModel(TimestampMixin, Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="inactive")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    daily_quota_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_quota_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)


class ProviderCredentialModel(TimestampMixin, Base):
    __tablename__ = "provider_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), index=True)
    label: Mapped[str] = mapped_column(String(128))
    encrypted_value: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderUsageRecordModel(Base):
    __tablename__ = "provider_usage_records"
    __table_args__ = (
        UniqueConstraint("provider_id", "credential_id", "period", "window_key", name="uq_provider_usage_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), index=True)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_credentials.id"), nullable=True, index=True
    )
    period: Mapped[str] = mapped_column(String(16))
    window_key: Mapped[str] = mapped_column(String(16), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProviderHealthCheckModel(Base):
    __tablename__ = "provider_health_checks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    success: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProviderHealthStateModel(Base):
    """One row per provider — see ProviderHealthState docstring for why this is materialized
    rather than derived from provider_health_checks on every read."""

    __tablename__ = "provider_health_state"

    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="healthy")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    open_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_incidents.id"), nullable=True
    )


class ProviderIncidentModel(TimestampMixin, Base):
    __tablename__ = "provider_incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str] = mapped_column(Text)


class FeatureFlagModel(Base):
    __tablename__ = "feature_flags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=100)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

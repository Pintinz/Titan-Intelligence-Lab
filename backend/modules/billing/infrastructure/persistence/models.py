"""SQLAlchemy models for the `billing` schema (Milestone 6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, MetaData, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="billing")


class Base(DeclarativeBase):
    metadata = metadata


class PlanModel(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(16))
    billing_period: Mapped[str] = mapped_column(String(16), default="monthly")
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EntitlementModel(Base):
    __tablename__ = "entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "feature_key", name="uq_entitlement_plan_feature"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"), index=True)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SubscriptionModel(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(16), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    provider_ref: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageCounterModel(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "feature_key", "window_key", name="uq_usage_counter_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(16), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    window_key: Mapped[str] = mapped_column(String(16))
    used_amount: Mapped[int] = mapped_column(Integer, default=0)

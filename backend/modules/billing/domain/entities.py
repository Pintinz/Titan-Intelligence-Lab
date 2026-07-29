"""Entities for the Subscription/Billing bounded context (Milestone 6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.billing.domain.value_objects import (
    BillingPeriod,
    EntitlementId,
    PlanId,
    PlanTier,
    SubjectType,
    SubscriptionId,
    SubscriptionStatus,
    UsageCounterId,
)


@dataclass
class Plan:
    id: PlanId
    key: str  # stable slug, e.g. "premium_monthly"
    name: str
    tier: PlanTier
    billing_period: BillingPeriod = BillingPeriod.MONTHLY
    price_cents: int = 0
    created_at: datetime | None = None


@dataclass
class Entitlement:
    """One row per (plan, feature) — ``limit_value=None`` means unlimited, ``0`` means the
    feature is fully gated off for that plan. This is what a Milestone-4 ``FeatureFlag``
    doesn't cover: a flag is on/off globally, an entitlement is a per-plan usage ceiling."""

    id: EntitlementId
    plan_id: PlanId
    feature_key: str
    limit_value: int | None = None

    def allows(self, current_usage: int) -> bool:
        return self.limit_value is None or current_usage < self.limit_value


@dataclass
class Subscription:
    id: SubscriptionId
    subject_type: SubjectType
    subject_id: str  # UserId or OrganizationId, stringified — the billing subject
    plan_id: PlanId
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    provider_ref: dict = field(default_factory=dict)  # future payment-provider linkage
    started_at: datetime | None = None
    current_period_end: datetime | None = None
    canceled_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING)


@dataclass
class UsageCounter:
    """Tracks consumption of a metered feature against its entitlement limit for one billing
    subject in one time window — same windowed-counter shape as
    ``modules.admin.domain.entities.ProviderUsageRecord``."""

    id: UsageCounterId
    subject_type: SubjectType
    subject_id: str
    feature_key: str
    window_key: str  # "2026-07" for MONTHLY-windowed features
    used_amount: int = 0

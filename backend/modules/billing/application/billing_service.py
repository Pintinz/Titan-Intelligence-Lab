"""BillingService — subscriptions, entitlement checks, and usage metering (Milestone 6).

No payment provider is called here (docs constitution: "no payment providers yet") — this
service manages the subscription/entitlement *state*; charging a card is out of scope until a
real provider adapter is wired through ``modules.webhooks``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.billing.domain.entities import Entitlement, Plan, Subscription, UsageCounter
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
from modules.billing.ports.repositories import (
    EntitlementRepositoryPort,
    PlanRepositoryPort,
    SubscriptionRepositoryPort,
    UsageCounterRepositoryPort,
)
from modules.identity.domain.entities import AuditLogEntry
from modules.identity.domain.value_objects import AuditAction, AuditEventId, UserId
from modules.identity.ports.repositories import AuditLogRepositoryPort


class EntitlementExceededError(Exception):
    pass


class NoActiveSubscriptionError(Exception):
    pass


@dataclass
class BillingService:
    plans: PlanRepositoryPort
    entitlements: EntitlementRepositoryPort
    subscriptions: SubscriptionRepositoryPort
    usage_counters: UsageCounterRepositoryPort
    audit_log: AuditLogRepositoryPort

    # -- plan/entitlement catalog management (admin-only at the API layer) ----------------------

    async def create_plan(
        self,
        key: str,
        name: str,
        tier: PlanTier,
        now: datetime,
        billing_period: BillingPeriod = BillingPeriod.MONTHLY,
        price_cents: int = 0,
    ) -> Plan:
        existing = await self.plans.get_by_key(key)
        if existing is not None:
            raise ValueError(f"Plan already exists: {key}")
        plan = Plan(
            id=PlanId(uuid4()), key=key, name=name, tier=tier, billing_period=billing_period,
            price_cents=price_cents, created_at=now,
        )
        return await self.plans.upsert(plan)

    async def set_entitlement(self, plan_id: PlanId, feature_key: str, limit_value: int | None) -> Entitlement:
        existing = await self.entitlements.get(plan_id, feature_key)
        entitlement = existing or Entitlement(id=EntitlementId(uuid4()), plan_id=plan_id, feature_key=feature_key)
        entitlement.limit_value = limit_value
        return await self.entitlements.upsert(entitlement)

    # -- subscription lifecycle -----------------------------------------------------------------

    async def subscribe(
        self,
        subject_type: SubjectType,
        subject_id: str,
        plan_id: PlanId,
        now: datetime,
        actor: UserId,
        current_period_end: datetime | None = None,
    ) -> Subscription:
        existing = await self.subscriptions.get_active_for_subject(subject_type, subject_id)
        subscription = Subscription(
            id=SubscriptionId(uuid4()),
            subject_type=subject_type,
            subject_id=subject_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            started_at=now,
            current_period_end=current_period_end,
        )
        await self.subscriptions.upsert(subscription)
        await self._audit(
            now,
            actor,
            metadata={
                "subject_type": subject_type.value,
                "subject_id": subject_id,
                "plan_id": str(plan_id),
                "previous_plan_id": str(existing.plan_id) if existing else None,
            },
        )
        return subscription

    async def cancel(self, subscription_id: SubscriptionId, now: datetime, actor: UserId) -> Subscription:
        subscription = await self.subscriptions.get(subscription_id)
        if subscription is None:
            raise ValueError("No such subscription")
        subscription.status = SubscriptionStatus.CANCELED
        subscription.canceled_at = now
        await self.subscriptions.upsert(subscription)
        await self._audit(now, actor, metadata={"subscription_id": str(subscription_id), "canceled": True})
        return subscription

    async def active_plan_for(self, subject_type: SubjectType, subject_id: str) -> PlanId | None:
        subscription = await self.subscriptions.get_active_for_subject(subject_type, subject_id)
        return subscription.plan_id if subscription and subscription.is_active else None

    # -- entitlement checks ----------------------------------------------------------------------

    async def has_feature(self, subject_type: SubjectType, subject_id: str, feature_key: str) -> bool:
        plan_id = await self.active_plan_for(subject_type, subject_id)
        if plan_id is None:
            return False
        entitlement = await self.entitlements.get(plan_id, feature_key)
        return entitlement is not None

    async def check_within_limit(
        self, subject_type: SubjectType, subject_id: str, feature_key: str, window_key: str
    ) -> bool:
        plan_id = await self.active_plan_for(subject_type, subject_id)
        if plan_id is None:
            raise NoActiveSubscriptionError(f"No active subscription for {subject_type.value}:{subject_id}")
        entitlement = await self.entitlements.get(plan_id, feature_key)
        if entitlement is None:
            return False
        counter = await self.usage_counters.get(subject_type, subject_id, feature_key, window_key)
        current = counter.used_amount if counter else 0
        return entitlement.allows(current)

    # -- usage metering --------------------------------------------------------------------------

    async def record_usage(
        self,
        subject_type: SubjectType,
        subject_id: str,
        feature_key: str,
        window_key: str,
        amount: int = 1,
    ) -> UsageCounter:
        """Raises ``EntitlementExceededError`` before incrementing if the subject has no
        subscription covering ``feature_key`` at all (a metered call from a plan that never
        had the entitlement is a bug in the caller, not a quota to silently track)."""
        plan_id = await self.active_plan_for(subject_type, subject_id)
        if plan_id is None or await self.entitlements.get(plan_id, feature_key) is None:
            raise EntitlementExceededError(f"{subject_type.value}:{subject_id} has no entitlement for {feature_key}")

        counter = await self.usage_counters.get(subject_type, subject_id, feature_key, window_key)
        counter = counter or UsageCounter(
            id=UsageCounterId(uuid4()),
            subject_type=subject_type,
            subject_id=subject_id,
            feature_key=feature_key,
            window_key=window_key,
        )
        counter.used_amount += amount
        return await self.usage_counters.upsert(counter)

    async def _audit(self, now: datetime, actor: UserId, metadata: dict) -> None:
        await self.audit_log.append(
            AuditLogEntry(
                id=AuditEventId(uuid4()),
                action=AuditAction.SUBSCRIPTION_CHANGED,
                occurred_at=now,
                actor_user_id=actor,
                target_type="subscription",
                target_id=metadata.get("subscription_id") or metadata.get("subject_id"),
                metadata=metadata,
            )
        )

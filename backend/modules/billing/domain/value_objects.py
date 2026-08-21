"""Value objects for the Subscription/Billing bounded context (Milestone 6).

No payment provider is wired yet — ``Subscription.provider_ref`` exists so Stripe/Paddle/etc.
can be slotted in later (webhook infrastructure lands alongside, see modules.webhooks) without
a schema change (docs/roadmap.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class PlanTier(str, Enum):
    FREE = "free"
    REWARDED = "rewarded"
    PRO = "pro"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class BillingPeriod(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    LIFETIME = "lifetime"  # e.g. rewarded-ad unlocks with no recurring charge


class SubjectType(str, Enum):
    """A subscription's billing subject — an individual user account or an organization
    (Enterprise-tier subscriptions are always organization-scoped)."""

    USER = "user"
    ORGANIZATION = "organization"


class ChargeStatus(str, Enum):
    """A payment-provider charge attempt's lifecycle — distinct from ``SubscriptionStatus``:
    a charge is a single payment event, a subscription is the entitlement state it unlocks.
    Only a verified webhook (never the synchronous checkout response) may move a
    ``PendingCheckout`` to SUCCEEDED/FAILED — see ``CheckoutService.handle_webhook``."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class PlanId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class EntitlementId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SubscriptionId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class UsageCounterId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PendingCheckoutId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)

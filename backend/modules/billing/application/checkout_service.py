"""CheckoutService — orchestrates a card charge attempt and its eventual confirmation.

Hard rule, straight from the product constitution: subscription state is synchronized *only*
from a verified provider webhook event — never from the synchronous charge response, and never
from anything the frontend claims. ``initiate_checkout`` never calls ``BillingService.subscribe``,
even when the provider's synchronous response already says "succeeded" — only ``handle_webhook``
does, and only after verifying the webhook's signature. This keeps exactly one code path capable
of activating a subscription, which is what makes it auditable and safe to reason about.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from modules.billing.application.billing_service import BillingService
from modules.billing.domain.payment import CardDetails, ChargeResult, CustomerInfo, PendingCheckout
from modules.billing.domain.value_objects import BillingPeriod, ChargeStatus, PendingCheckoutId, SubjectType
from modules.billing.ports.payment_provider import PaymentProviderPort
from modules.billing.ports.repositories import PendingCheckoutRepositoryPort, ProcessedPaymentEventRepositoryPort

_PROVIDER_NAME = "flutterwave"


class PlanNotFoundError(ValueError):
    pass


class WebhookSignatureInvalidError(ValueError):
    pass


def _period_end(now: datetime, period: BillingPeriod) -> datetime | None:
    if period is BillingPeriod.MONTHLY:
        return now + timedelta(days=30)
    if period is BillingPeriod.ANNUAL:
        return now + timedelta(days=365)
    return None  # LIFETIME — no expiry


@dataclass
class CheckoutService:
    billing: BillingService
    provider: PaymentProviderPort
    pending_checkouts: PendingCheckoutRepositoryPort
    processed_events: ProcessedPaymentEventRepositoryPort

    async def initiate_checkout(
        self,
        *,
        plan_key: str,
        subject_type: SubjectType,
        subject_id: str,
        card: CardDetails,
        customer: CustomerInfo,
        redirect_url: str,
        now: datetime,
    ) -> ChargeResult:
        plan = await self.billing.plans.get_by_key(plan_key)
        if plan is None:
            raise PlanNotFoundError(f"No such plan: {plan_key}")

        reference = f"titaniq_{uuid4().hex}"
        checkout = PendingCheckout(
            id=PendingCheckoutId(uuid4()),
            reference=reference,
            subject_type=subject_type.value,
            subject_id=subject_id,
            plan_id=plan.id,
            status=ChargeStatus.PENDING,
            created_at=now,
        )
        await self.pending_checkouts.upsert(checkout)

        result = await self.provider.create_charge(
            amount_cents=plan.price_cents,
            currency="USD",
            reference=reference,
            customer=customer,
            card=card,
            redirect_url=redirect_url,
        )

        checkout.provider_charge_id = result.provider_charge_id or None
        if result.status is ChargeStatus.FAILED:
            checkout.status = ChargeStatus.FAILED
            checkout.resolved_at = now
        await self.pending_checkouts.upsert(checkout)

        # Deliberately NOT calling billing.subscribe here even if result.status is SUCCEEDED —
        # see module docstring. Only handle_webhook does that, after signature verification.
        return result

    async def handle_webhook(self, *, raw_body: bytes, signature: str, now: datetime) -> None:
        if not await self.provider.verify_webhook_signature(raw_body, signature):
            raise WebhookSignatureInvalidError("Flutterwave webhook signature did not verify.")

        event = json.loads(raw_body)
        event_type = event.get("type", "")
        data = event.get("data") or {}
        provider_charge_id = data.get("id", "")
        status = data.get("status", "")

        # No distinct event-id field is documented on the payload — a redelivery of the exact
        # same event will reproduce (type, charge id, status) identically, so that triple is a
        # safe idempotency key; a genuine state change (pending -> succeeded) produces a
        # different key and is correctly treated as a new event.
        idempotency_key = f"{event_type}:{provider_charge_id}:{status}"
        if await self.processed_events.already_processed(_PROVIDER_NAME, idempotency_key):
            return
        await self.processed_events.mark_processed(_PROVIDER_NAME, idempotency_key, now)

        if event_type != "charge.completed" or not provider_charge_id:
            return

        checkout = await self.pending_checkouts.get_by_provider_charge_id(provider_charge_id)
        if checkout is None or checkout.status is ChargeStatus.SUCCEEDED:
            return  # unknown charge, or already resolved by an earlier (non-duplicate) event

        if status != "succeeded":
            # A real failure/decline delivered by the provider — recorded, not dropped, so the
            # checkout attempt reads as FAILED rather than staying PENDING forever with no signal
            # anywhere that it didn't go through.
            checkout.status = ChargeStatus.FAILED
            checkout.resolved_at = now
            await self.pending_checkouts.upsert(checkout)
            return

        plan = await self.billing.plans.get(checkout.plan_id)
        if plan is None:
            return

        await self.billing.subscribe(
            SubjectType(checkout.subject_type),
            checkout.subject_id,
            checkout.plan_id,
            now,
            current_period_end=_period_end(now, plan.billing_period),
        )

        checkout.status = ChargeStatus.SUCCEEDED
        checkout.resolved_at = now
        await self.pending_checkouts.upsert(checkout)

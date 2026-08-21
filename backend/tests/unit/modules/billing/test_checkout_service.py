from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from modules.billing.application.billing_service import BillingService
from modules.billing.application.checkout_service import (
    CheckoutService,
    PlanNotFoundError,
    WebhookSignatureInvalidError,
)
from modules.billing.domain.payment import CardDetails, ChargeResult, CustomerInfo
from modules.billing.domain.value_objects import BillingPeriod, ChargeStatus, PlanTier, SubjectType


def now():
    return datetime.now(timezone.utc)


@dataclass
class FakeFlutterwaveProvider:
    """Test double for PaymentProviderPort — lets each test dictate the synchronous charge
    result and whether webhook signatures verify, without touching real HTTP or crypto."""

    charge_result: ChargeResult
    signature_valid: bool = True
    create_charge_calls: list = field(default_factory=list)

    async def create_charge(self, *, amount_cents, currency, reference, customer, card, redirect_url):
        self.create_charge_calls.append(reference)
        return self.charge_result

    async def get_charge_status(self, provider_charge_id):
        return self.charge_result

    async def verify_webhook_signature(self, raw_body, signature):
        return self.signature_valid


def _card() -> CardDetails:
    return CardDetails(number="4242424242424242", expiry_month="12", expiry_year="2030", cvv="123")


def _customer() -> CustomerInfo:
    return CustomerInfo(
        email="jane@example.com", first_name="Jane", last_name="Doe", phone_country_code="1",
        phone_number="5551234567", address_line1="1 Main St", city="Metropolis", state="NY",
        postal_code="10001", country="US",
    )


def _webhook_body(charge_id: str, status: str = "succeeded", event_type: str = "charge.completed") -> bytes:
    return json.dumps({"type": event_type, "data": {"id": charge_id, "status": status}}).encode()


@pytest.fixture
def billing_service(plan_repo, entitlement_repo, subscription_repo, usage_counter_repo, audit_log_repo):
    return BillingService(
        plans=plan_repo, entitlements=entitlement_repo, subscriptions=subscription_repo,
        usage_counters=usage_counter_repo, audit_log=audit_log_repo,
    )


def make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo):
    return CheckoutService(
        billing=billing_service, provider=provider,
        pending_checkouts=pending_checkout_repo, processed_events=processed_payment_event_repo,
    )


async def test_initiate_checkout_raises_for_unknown_plan(billing_service, pending_checkout_repo, processed_payment_event_repo):
    provider = FakeFlutterwaveProvider(charge_result=ChargeResult(provider_charge_id="chg_1", status=ChargeStatus.SUCCEEDED))
    service = make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo)

    with pytest.raises(PlanNotFoundError):
        await service.initiate_checkout(
            plan_key="does-not-exist", subject_type=SubjectType.USER, subject_id="user-1",
            card=_card(), customer=_customer(), redirect_url="https://titaniq.test/return", now=now(),
        )


async def test_initiate_checkout_never_subscribes_even_on_synchronous_success(
    billing_service, subscription_repo, pending_checkout_repo, processed_payment_event_repo
):
    """The core security invariant: a synchronous 'succeeded' response from create_charge must
    never, by itself, activate a subscription — only a verified webhook may."""
    plan = await billing_service.create_plan("pro", "Pro", PlanTier.PRO, now(), price_cents=999)
    provider = FakeFlutterwaveProvider(charge_result=ChargeResult(provider_charge_id="chg_sync", status=ChargeStatus.SUCCEEDED))
    service = make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo)

    result = await service.initiate_checkout(
        plan_key="pro", subject_type=SubjectType.USER, subject_id="user-1",
        card=_card(), customer=_customer(), redirect_url="https://titaniq.test/return", now=now(),
    )

    assert result.status is ChargeStatus.SUCCEEDED
    assert len(subscription_repo.store) == 0  # not activated by the synchronous response

    checkout = await pending_checkout_repo.get_by_reference(provider.create_charge_calls[0])
    assert checkout.provider_charge_id == "chg_sync"
    assert checkout.status is ChargeStatus.PENDING  # still pending until the webhook confirms


async def test_handle_webhook_activates_subscription_on_verified_success(
    billing_service, subscription_repo, pending_checkout_repo, processed_payment_event_repo
):
    plan = await billing_service.create_plan("pro", "Pro", PlanTier.PRO, now(), billing_period=BillingPeriod.MONTHLY, price_cents=999)
    provider = FakeFlutterwaveProvider(charge_result=ChargeResult(provider_charge_id="chg_web", status=ChargeStatus.PENDING))
    service = make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo)

    await service.initiate_checkout(
        plan_key="pro", subject_type=SubjectType.USER, subject_id="user-42",
        card=_card(), customer=_customer(), redirect_url="https://titaniq.test/return", now=now(),
    )

    await service.handle_webhook(raw_body=_webhook_body("chg_web"), signature="sig", now=now())

    assert len(subscription_repo.store) == 1
    subscription = next(iter(subscription_repo.store.values()))
    assert subscription.subject_id == "user-42"
    assert subscription.plan_id == plan.id
    assert subscription.current_period_end is not None


async def test_handle_webhook_rejects_invalid_signature(
    billing_service, subscription_repo, pending_checkout_repo, processed_payment_event_repo
):
    provider = FakeFlutterwaveProvider(
        charge_result=ChargeResult(provider_charge_id="chg_bad_sig", status=ChargeStatus.PENDING), signature_valid=False
    )
    service = make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo)

    with pytest.raises(WebhookSignatureInvalidError):
        await service.handle_webhook(raw_body=_webhook_body("chg_bad_sig"), signature="forged", now=now())

    assert len(subscription_repo.store) == 0


async def test_handle_webhook_ignores_unknown_charge(billing_service, subscription_repo, pending_checkout_repo, processed_payment_event_repo):
    provider = FakeFlutterwaveProvider(charge_result=ChargeResult(provider_charge_id="chg_unknown", status=ChargeStatus.SUCCEEDED))
    service = make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo)

    await service.handle_webhook(raw_body=_webhook_body("chg_never_initiated"), signature="sig", now=now())

    assert len(subscription_repo.store) == 0


async def test_handle_webhook_records_failure_on_non_success_status(
    billing_service, subscription_repo, pending_checkout_repo, processed_payment_event_repo
):
    """A declined/failed charge must never activate a subscription, but it also must not be
    silently dropped — the pending checkout should read as FAILED, not stay PENDING forever with
    no signal anywhere that it didn't go through."""
    provider = FakeFlutterwaveProvider(charge_result=ChargeResult(provider_charge_id="chg_declined", status=ChargeStatus.PENDING))
    service = make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo)
    await billing_service.create_plan("pro", "Pro", PlanTier.PRO, now(), price_cents=999)
    await service.initiate_checkout(
        plan_key="pro", subject_type=SubjectType.USER, subject_id="user-1",
        card=_card(), customer=_customer(), redirect_url="https://titaniq.test/return", now=now(),
    )

    await service.handle_webhook(raw_body=_webhook_body("chg_declined", status="declined"), signature="sig", now=now())

    assert len(subscription_repo.store) == 0
    checkout = await pending_checkout_repo.get_by_provider_charge_id("chg_declined")
    assert checkout.status is ChargeStatus.FAILED
    assert checkout.resolved_at is not None


async def test_handle_webhook_is_idempotent_against_redelivery(
    billing_service, subscription_repo, pending_checkout_repo, processed_payment_event_repo
):
    plan = await billing_service.create_plan("pro", "Pro", PlanTier.PRO, now(), price_cents=999)
    provider = FakeFlutterwaveProvider(charge_result=ChargeResult(provider_charge_id="chg_redelivered", status=ChargeStatus.PENDING))
    service = make_service(billing_service, provider, pending_checkout_repo, processed_payment_event_repo)
    await service.initiate_checkout(
        plan_key="pro", subject_type=SubjectType.USER, subject_id="user-1",
        card=_card(), customer=_customer(), redirect_url="https://titaniq.test/return", now=now(),
    )

    body = _webhook_body("chg_redelivered")
    await service.handle_webhook(raw_body=body, signature="sig", now=now())
    await service.handle_webhook(raw_body=body, signature="sig", now=now())  # provider redelivers the same event

    assert len(subscription_repo.store) == 1  # not two

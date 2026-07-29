from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.billing.application.billing_service import BillingService, EntitlementExceededError, NoActiveSubscriptionError
from modules.billing.domain.value_objects import PlanTier, SubjectType
from modules.identity.domain.value_objects import AuditAction, UserId


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def service(plan_repo, entitlement_repo, subscription_repo, usage_counter_repo, audit_log_repo):
    return BillingService(
        plans=plan_repo, entitlements=entitlement_repo, subscriptions=subscription_repo,
        usage_counters=usage_counter_repo, audit_log=audit_log_repo,
    )


async def test_create_plan_and_reject_duplicate(service):
    plan = await service.create_plan("premium_monthly", "Premium", PlanTier.PREMIUM, now(), price_cents=1999)
    assert plan.tier is PlanTier.PREMIUM

    with pytest.raises(ValueError):
        await service.create_plan("premium_monthly", "Premium Again", PlanTier.PREMIUM, now())


async def test_subscribe_and_has_feature(service, audit_log_repo):
    plan = await service.create_plan("premium_monthly", "Premium", PlanTier.PREMIUM, now())
    await service.set_entitlement(plan.id, "advanced_analytics", limit_value=None)
    actor = UserId(uuid4())
    user_id = str(uuid4())

    await service.subscribe(SubjectType.USER, user_id, plan.id, now(), actor)

    assert await service.has_feature(SubjectType.USER, user_id, "advanced_analytics") is True
    assert await service.has_feature(SubjectType.USER, user_id, "nonexistent_feature") is False
    assert any(e.action is AuditAction.SUBSCRIPTION_CHANGED for e in audit_log_repo.entries)


async def test_has_feature_false_without_subscription(service):
    assert await service.has_feature(SubjectType.USER, str(uuid4()), "anything") is False


async def test_cancel_subscription(service):
    plan = await service.create_plan("free", "Free", PlanTier.FREE, now())
    actor = UserId(uuid4())
    subscription = await service.subscribe(SubjectType.USER, str(uuid4()), plan.id, now(), actor)

    canceled = await service.cancel(subscription.id, now(), actor)

    assert canceled.status.value == "canceled"
    assert await service.active_plan_for(SubjectType.USER, subscription.subject_id) is None


async def test_check_within_limit_and_record_usage(service):
    plan = await service.create_plan("premium_monthly", "Premium", PlanTier.PREMIUM, now())
    await service.set_entitlement(plan.id, "ai_reports", limit_value=2)
    actor = UserId(uuid4())
    subject_id = str(uuid4())
    await service.subscribe(SubjectType.USER, subject_id, plan.id, now(), actor)

    assert await service.check_within_limit(SubjectType.USER, subject_id, "ai_reports", "2026-07") is True

    await service.record_usage(SubjectType.USER, subject_id, "ai_reports", "2026-07")
    await service.record_usage(SubjectType.USER, subject_id, "ai_reports", "2026-07")

    assert await service.check_within_limit(SubjectType.USER, subject_id, "ai_reports", "2026-07") is False


async def test_check_within_limit_raises_without_subscription(service):
    with pytest.raises(NoActiveSubscriptionError):
        await service.check_within_limit(SubjectType.USER, str(uuid4()), "ai_reports", "2026-07")


async def test_record_usage_raises_without_entitlement(service):
    plan = await service.create_plan("free", "Free", PlanTier.FREE, now())
    actor = UserId(uuid4())
    subject_id = str(uuid4())
    await service.subscribe(SubjectType.USER, subject_id, plan.id, now(), actor)

    with pytest.raises(EntitlementExceededError):
        await service.record_usage(SubjectType.USER, subject_id, "ai_reports", "2026-07")


async def test_unlimited_entitlement_always_allows(service):
    plan = await service.create_plan("enterprise", "Enterprise", PlanTier.ENTERPRISE, now())
    await service.set_entitlement(plan.id, "api_calls", limit_value=None)
    actor = UserId(uuid4())
    subject_id = str(uuid4())
    await service.subscribe(SubjectType.ORGANIZATION, subject_id, plan.id, now(), actor)

    for _ in range(50):
        await service.record_usage(SubjectType.ORGANIZATION, subject_id, "api_calls", "2026-07")

    assert await service.check_within_limit(SubjectType.ORGANIZATION, subject_id, "api_calls", "2026-07") is True

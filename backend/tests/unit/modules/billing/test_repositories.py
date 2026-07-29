from __future__ import annotations

from datetime import datetime, timezone
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
from modules.billing.infrastructure.persistence.repositories import (
    SqlAlchemyEntitlementRepository,
    SqlAlchemyPlanRepository,
    SqlAlchemySubscriptionRepository,
    SqlAlchemyUsageCounterRepository,
)


def now():
    return datetime.now(timezone.utc)


async def test_plan_repository_round_trip(sqlite_session):
    repo = SqlAlchemyPlanRepository(session=sqlite_session)
    plan = Plan(id=PlanId(uuid4()), key="premium_monthly", name="Premium", tier=PlanTier.PREMIUM, billing_period=BillingPeriod.MONTHLY, price_cents=1999)

    await repo.upsert(plan)
    await sqlite_session.commit()

    fetched = await repo.get_by_key("premium_monthly")
    assert fetched.tier is PlanTier.PREMIUM
    assert len(await repo.list_all()) == 1


async def test_entitlement_repository_round_trip(sqlite_session):
    plan_repo = SqlAlchemyPlanRepository(session=sqlite_session)
    plan = await plan_repo.upsert(Plan(id=PlanId(uuid4()), key="premium_monthly", name="Premium", tier=PlanTier.PREMIUM))
    await sqlite_session.commit()

    entitlement_repo = SqlAlchemyEntitlementRepository(session=sqlite_session)
    await entitlement_repo.upsert(Entitlement(id=EntitlementId(uuid4()), plan_id=plan.id, feature_key="ai_reports", limit_value=5))
    await sqlite_session.commit()

    fetched = await entitlement_repo.get(plan.id, "ai_reports")
    assert fetched.limit_value == 5
    assert len(await entitlement_repo.list_by_plan(plan.id)) == 1


async def test_subscription_repository_active_lookup(sqlite_session):
    plan_repo = SqlAlchemyPlanRepository(session=sqlite_session)
    plan = await plan_repo.upsert(Plan(id=PlanId(uuid4()), key="free", name="Free", tier=PlanTier.FREE))
    await sqlite_session.commit()

    sub_repo = SqlAlchemySubscriptionRepository(session=sqlite_session)
    subject_id = str(uuid4())
    subscription = await sub_repo.upsert(
        Subscription(id=SubscriptionId(uuid4()), subject_type=SubjectType.USER, subject_id=subject_id, plan_id=plan.id, status=SubscriptionStatus.ACTIVE, started_at=now())
    )
    await sqlite_session.commit()

    fetched = await sub_repo.get_active_for_subject(SubjectType.USER, subject_id)
    assert fetched.id == subscription.id

    subscription.status = SubscriptionStatus.CANCELED
    await sub_repo.upsert(subscription)
    await sqlite_session.commit()
    assert await sub_repo.get_active_for_subject(SubjectType.USER, subject_id) is None


async def test_usage_counter_repository_round_trip(sqlite_session):
    repo = SqlAlchemyUsageCounterRepository(session=sqlite_session)
    counter = UsageCounter(id=UsageCounterId(uuid4()), subject_type=SubjectType.ORGANIZATION, subject_id="org-1", feature_key="api_calls", window_key="2026-07", used_amount=3)

    await repo.upsert(counter)
    await sqlite_session.commit()

    fetched = await repo.get(SubjectType.ORGANIZATION, "org-1", "api_calls", "2026-07")
    assert fetched.used_amount == 3

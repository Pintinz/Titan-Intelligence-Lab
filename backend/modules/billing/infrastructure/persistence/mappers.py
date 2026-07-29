from __future__ import annotations

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
from modules.billing.infrastructure.persistence.models import (
    EntitlementModel,
    PlanModel,
    SubscriptionModel,
    UsageCounterModel,
)


def plan_to_domain(model: PlanModel) -> Plan:
    return Plan(
        id=PlanId(model.id),
        key=model.key,
        name=model.name,
        tier=PlanTier(model.tier),
        billing_period=BillingPeriod(model.billing_period),
        price_cents=model.price_cents,
        created_at=model.created_at,
    )


def plan_to_model(entity: Plan, model: PlanModel | None = None) -> PlanModel:
    model = model or PlanModel(id=entity.id.value)
    model.key = entity.key
    model.name = entity.name
    model.tier = entity.tier.value
    model.billing_period = entity.billing_period.value
    model.price_cents = entity.price_cents
    return model


def entitlement_to_domain(model: EntitlementModel) -> Entitlement:
    return Entitlement(
        id=EntitlementId(model.id), plan_id=PlanId(model.plan_id), feature_key=model.feature_key, limit_value=model.limit_value
    )


def entitlement_to_model(entity: Entitlement, model: EntitlementModel | None = None) -> EntitlementModel:
    model = model or EntitlementModel(id=entity.id.value)
    model.plan_id = entity.plan_id.value
    model.feature_key = entity.feature_key
    model.limit_value = entity.limit_value
    return model


def subscription_to_domain(model: SubscriptionModel) -> Subscription:
    return Subscription(
        id=SubscriptionId(model.id),
        subject_type=SubjectType(model.subject_type),
        subject_id=model.subject_id,
        plan_id=PlanId(model.plan_id),
        status=SubscriptionStatus(model.status),
        provider_ref=dict(model.provider_ref or {}),
        started_at=model.started_at,
        current_period_end=model.current_period_end,
        canceled_at=model.canceled_at,
    )


def subscription_to_model(entity: Subscription, model: SubscriptionModel | None = None) -> SubscriptionModel:
    model = model or SubscriptionModel(id=entity.id.value)
    model.subject_type = entity.subject_type.value
    model.subject_id = entity.subject_id
    model.plan_id = entity.plan_id.value
    model.status = entity.status.value
    model.provider_ref = entity.provider_ref
    model.started_at = entity.started_at
    model.current_period_end = entity.current_period_end
    model.canceled_at = entity.canceled_at
    return model


def usage_counter_to_domain(model: UsageCounterModel) -> UsageCounter:
    return UsageCounter(
        id=UsageCounterId(model.id),
        subject_type=SubjectType(model.subject_type),
        subject_id=model.subject_id,
        feature_key=model.feature_key,
        window_key=model.window_key,
        used_amount=model.used_amount,
    )


def usage_counter_to_model(entity: UsageCounter, model: UsageCounterModel | None = None) -> UsageCounterModel:
    model = model or UsageCounterModel(
        id=entity.id.value,
        subject_type=entity.subject_type.value,
        subject_id=entity.subject_id,
        feature_key=entity.feature_key,
        window_key=entity.window_key,
    )
    model.used_amount = entity.used_amount
    return model

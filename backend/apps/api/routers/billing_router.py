"""Subscription/Billing endpoints — plans, subscriptions, entitlement checks (Milestone 6,
docs/api_specification.md `/api/v1/billing`). No payment provider is wired — these endpoints
manage subscription/entitlement *state*, not charging (docs constitution).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user, require_role
from apps.api.composition import build_billing_service, get_session
from modules.billing.domain.entities import Plan, Subscription
from modules.billing.domain.value_objects import BillingPeriod, PlanTier, SubjectType, SubscriptionId
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Role

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {value}") from None


def _serialize_plan(plan: Plan) -> dict:
    return {
        "id": str(plan.id),
        "key": plan.key,
        "name": plan.name,
        "tier": plan.tier.value,
        "billing_period": plan.billing_period.value,
        "price_cents": plan.price_cents,
    }


def _serialize_subscription(subscription: Subscription) -> dict:
    return {
        "id": str(subscription.id),
        "subject_type": subscription.subject_type.value,
        "subject_id": subscription.subject_id,
        "plan_id": str(subscription.plan_id),
        "status": subscription.status.value,
        "current_period_end": subscription.current_period_end.isoformat()
        if subscription.current_period_end
        else None,
    }


class SubscribeRequest(BaseModel):
    subject_type: SubjectType
    subject_id: str
    plan_key: str


class CreatePlanRequest(BaseModel):
    key: str
    name: str
    tier: PlanTier
    billing_period: BillingPeriod = BillingPeriod.MONTHLY
    price_cents: int = 0


class SetEntitlementRequest(BaseModel):
    feature_key: str
    limit_value: int | None = None


@router.get("/plans")
async def list_plans(session: AsyncSession = Depends(get_session)):
    service = build_billing_service(session)
    plans = await service.plans.list_all()
    return envelope([_serialize_plan(p) for p in plans])


@router.post("/plans")
async def create_plan(
    payload: CreatePlanRequest,
    session: AsyncSession = Depends(get_session),
    _actor: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_billing_service(session)
    try:
        plan = await service.create_plan(
            payload.key, payload.name, payload.tier, _now(), payload.billing_period, payload.price_cents
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(_serialize_plan(plan))


@router.post("/plans/{plan_key}/entitlements")
async def set_entitlement(
    plan_key: str,
    payload: SetEntitlementRequest,
    session: AsyncSession = Depends(get_session),
    _actor: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_billing_service(session)
    plan = await service.plans.get_by_key(plan_key)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No such plan: {plan_key}")
    entitlement = await service.set_entitlement(plan.id, payload.feature_key, payload.limit_value)
    return envelope({"plan_id": str(plan.id), "feature_key": entitlement.feature_key, "limit_value": entitlement.limit_value})


@router.post("/subscriptions")
async def subscribe(
    payload: SubscribeRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_billing_service(session)
    plan = await service.plans.get_by_key(payload.plan_key)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No such plan: {payload.plan_key}")
    subscription = await service.subscribe(payload.subject_type, payload.subject_id, plan.id, _now(), actor=user.id)
    return envelope(_serialize_subscription(subscription))


@router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_billing_service(session)
    try:
        subscription = await service.cancel(SubscriptionId(_parse_uuid(subscription_id)), _now(), actor=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return envelope(_serialize_subscription(subscription))


@router.get("/entitlements/{subject_type}/{subject_id}/{feature_key}")
async def check_entitlement(
    subject_type: SubjectType,
    subject_id: str,
    feature_key: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_billing_service(session)
    has_feature = await service.has_feature(subject_type, subject_id, feature_key)
    return envelope({"subject_id": subject_id, "feature_key": feature_key, "has_feature": has_feature})

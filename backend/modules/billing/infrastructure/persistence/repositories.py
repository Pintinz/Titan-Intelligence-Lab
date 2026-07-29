from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.domain.entities import Entitlement, Plan, Subscription, UsageCounter
from modules.billing.domain.value_objects import PlanId, SubjectType, SubscriptionId, SubscriptionStatus
from modules.billing.infrastructure.persistence import mappers
from modules.billing.infrastructure.persistence.models import (
    EntitlementModel,
    PlanModel,
    SubscriptionModel,
    UsageCounterModel,
)


@dataclass
class SqlAlchemyPlanRepository:
    session: AsyncSession

    async def get(self, plan_id: PlanId) -> Plan | None:
        model = await self.session.get(PlanModel, plan_id.value)
        return mappers.plan_to_domain(model) if model else None

    async def get_by_key(self, key: str) -> Plan | None:
        result = await self.session.execute(select(PlanModel).where(PlanModel.key == key))
        model = result.scalar_one_or_none()
        return mappers.plan_to_domain(model) if model else None

    async def list_all(self) -> list[Plan]:
        result = await self.session.execute(select(PlanModel))
        return [mappers.plan_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, plan: Plan) -> Plan:
        existing = await self.session.get(PlanModel, plan.id.value)
        model = mappers.plan_to_model(plan, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.plan_to_domain(model)


@dataclass
class SqlAlchemyEntitlementRepository:
    session: AsyncSession

    async def list_by_plan(self, plan_id: PlanId) -> list[Entitlement]:
        stmt = select(EntitlementModel).where(EntitlementModel.plan_id == plan_id.value)
        result = await self.session.execute(stmt)
        return [mappers.entitlement_to_domain(row) for row in result.scalars().all()]

    async def get(self, plan_id: PlanId, feature_key: str) -> Entitlement | None:
        stmt = select(EntitlementModel).where(
            EntitlementModel.plan_id == plan_id.value, EntitlementModel.feature_key == feature_key
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return mappers.entitlement_to_domain(model) if model else None

    async def upsert(self, entitlement: Entitlement) -> Entitlement:
        existing = await self.session.get(EntitlementModel, entitlement.id.value)
        model = mappers.entitlement_to_model(entitlement, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.entitlement_to_domain(model)


@dataclass
class SqlAlchemySubscriptionRepository:
    session: AsyncSession

    async def get(self, subscription_id: SubscriptionId) -> Subscription | None:
        model = await self.session.get(SubscriptionModel, subscription_id.value)
        return mappers.subscription_to_domain(model) if model else None

    async def get_active_for_subject(self, subject_type: SubjectType, subject_id: str) -> Subscription | None:
        stmt = (
            select(SubscriptionModel)
            .where(
                SubscriptionModel.subject_type == subject_type.value,
                SubscriptionModel.subject_id == subject_id,
                SubscriptionModel.status.in_([SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value]),
            )
            .order_by(SubscriptionModel.started_at.desc())
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return mappers.subscription_to_domain(model) if model else None

    async def upsert(self, subscription: Subscription) -> Subscription:
        existing = await self.session.get(SubscriptionModel, subscription.id.value)
        model = mappers.subscription_to_model(subscription, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.subscription_to_domain(model)


@dataclass
class SqlAlchemyUsageCounterRepository:
    session: AsyncSession

    async def get(
        self, subject_type: SubjectType, subject_id: str, feature_key: str, window_key: str
    ) -> UsageCounter | None:
        stmt = select(UsageCounterModel).where(
            UsageCounterModel.subject_type == subject_type.value,
            UsageCounterModel.subject_id == subject_id,
            UsageCounterModel.feature_key == feature_key,
            UsageCounterModel.window_key == window_key,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return mappers.usage_counter_to_domain(model) if model else None

    async def upsert(self, counter: UsageCounter) -> UsageCounter:
        existing = await self.session.get(UsageCounterModel, counter.id.value)
        model = mappers.usage_counter_to_model(counter, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.usage_counter_to_domain(model)

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.billing.domain.entities import Entitlement, Plan, Subscription, UsageCounter
from modules.billing.domain.value_objects import PlanId, SubscriptionId, SubscriptionStatus, UsageCounterId
from modules.billing.infrastructure.persistence.models import Base
from modules.identity.domain.entities import AuditLogEntry


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"billing": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemoryPlanRepository:
    store: dict[PlanId, Plan] = field(default_factory=dict)

    async def get(self, plan_id):
        return self.store.get(plan_id)

    async def get_by_key(self, key):
        return next((p for p in self.store.values() if p.key == key), None)

    async def list_all(self):
        return list(self.store.values())

    async def upsert(self, plan):
        self.store[plan.id] = plan
        return plan


@dataclass
class InMemoryEntitlementRepository:
    store: dict[tuple, Entitlement] = field(default_factory=dict)

    async def list_by_plan(self, plan_id):
        return [e for e in self.store.values() if e.plan_id == plan_id]

    async def get(self, plan_id, feature_key):
        return self.store.get((plan_id, feature_key))

    async def upsert(self, entitlement):
        self.store[(entitlement.plan_id, entitlement.feature_key)] = entitlement
        return entitlement


@dataclass
class InMemorySubscriptionRepository:
    store: dict[SubscriptionId, Subscription] = field(default_factory=dict)

    async def get(self, subscription_id):
        return self.store.get(subscription_id)

    async def get_active_for_subject(self, subject_type, subject_id):
        candidates = [
            s
            for s in self.store.values()
            if s.subject_type == subject_type
            and s.subject_id == subject_id
            and s.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING)
        ]
        return candidates[-1] if candidates else None

    async def upsert(self, subscription):
        self.store[subscription.id] = subscription
        return subscription


@dataclass
class InMemoryUsageCounterRepository:
    store: dict[tuple, UsageCounter] = field(default_factory=dict)

    def _key(self, subject_type, subject_id, feature_key, window_key):
        return (subject_type, subject_id, feature_key, window_key)

    async def get(self, subject_type, subject_id, feature_key, window_key):
        return self.store.get(self._key(subject_type, subject_id, feature_key, window_key))

    async def upsert(self, counter):
        self.store[self._key(counter.subject_type, counter.subject_id, counter.feature_key, counter.window_key)] = counter
        return counter


@dataclass
class InMemoryAuditLogRepository:
    entries: list[AuditLogEntry] = field(default_factory=list)

    async def append(self, entry):
        self.entries.append(entry)
        return entry

    async def list_by_actor(self, actor_user_id, limit=100):
        return [e for e in self.entries if e.actor_user_id == actor_user_id][:limit]

    async def list_by_target(self, target_type, target_id):
        return [e for e in self.entries if e.target_type == target_type and e.target_id == target_id]


@pytest.fixture
def plan_repo():
    return InMemoryPlanRepository()


@pytest.fixture
def entitlement_repo():
    return InMemoryEntitlementRepository()


@pytest.fixture
def subscription_repo():
    return InMemorySubscriptionRepository()


@pytest.fixture
def usage_counter_repo():
    return InMemoryUsageCounterRepository()


@pytest.fixture
def audit_log_repo():
    return InMemoryAuditLogRepository()

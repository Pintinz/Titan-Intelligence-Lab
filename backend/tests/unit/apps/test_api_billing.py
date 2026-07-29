import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.billing.application.billing_service import BillingService
from modules.billing.domain.value_objects import PlanTier
from modules.billing.infrastructure.persistence.models import Base as BillingBase
from modules.billing.infrastructure.persistence.repositories import (
    SqlAlchemyEntitlementRepository,
    SqlAlchemyPlanRepository,
    SqlAlchemySubscriptionRepository,
    SqlAlchemyUsageCounterRepository,
)
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyAuditLogRepository
from modules.identity.infrastructure.security import MockJWTValidator


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "billing": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(BillingBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()


def register_and_login(client, email, password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["data"]["access_token"]


def test_non_admin_cannot_create_plan(client):
    token = register_and_login(client, "user@example.com")

    response = client.post(
        "/api/v1/billing/plans",
        json={"key": "premium_monthly", "name": "Premium", "tier": "premium"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_subscribe_and_check_entitlement(client, db_session_factory):
    async def seed_plan():
        async with db_session_factory() as session:
            service = BillingService(
                plans=SqlAlchemyPlanRepository(session=session),
                entitlements=SqlAlchemyEntitlementRepository(session=session),
                subscriptions=SqlAlchemySubscriptionRepository(session=session),
                usage_counters=SqlAlchemyUsageCounterRepository(session=session),
                audit_log=SqlAlchemyAuditLogRepository(session=session),
            )
            plan = await service.create_plan("premium_monthly", "Premium", PlanTier.PREMIUM, datetime.now(timezone.utc))
            await service.set_entitlement(plan.id, "advanced_analytics", None)
            await session.commit()

    asyncio.run(seed_plan())

    token = register_and_login(client, "subscriber@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/users/me", headers=headers).json()["data"]

    subscribe = client.post(
        "/api/v1/billing/subscriptions",
        json={"subject_type": "user", "subject_id": me["id"], "plan_key": "premium_monthly"},
        headers=headers,
    )
    assert subscribe.status_code == 200

    entitlement = client.get(
        f"/api/v1/billing/entitlements/user/{me['id']}/advanced_analytics", headers=headers
    )
    assert entitlement.json()["data"]["has_feature"] is True


def test_list_plans_is_public_read(client):
    response = client.get("/api/v1/billing/plans")
    assert response.status_code == 200

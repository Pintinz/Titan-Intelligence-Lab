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
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyAuditLogRepository, SqlAlchemyUserRepository
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


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


def test_non_admin_cannot_create_plan(client):
    token = register_and_login(client, "user@example.com")

    response = client.post(
        "/api/v1/billing/plans",
        json={"key": "premium_monthly", "name": "Premium", "tier": "premium"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_non_admin_cannot_self_subscribe(client):
    # No payment provider is integrated (see billing_router.py's module docstring) — self-service
    # subscribe must stay admin-only, or any free user could grant themselves a paid plan for free.
    token = register_and_login(client, "free-user@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/users/me", headers=headers).json()["data"]

    response = client.post(
        "/api/v1/billing/subscriptions",
        json={"subject_type": "user", "subject_id": me["id"], "plan_key": "premium_monthly"},
        headers=headers,
    )

    assert response.status_code == 403


def test_non_admin_cannot_cancel_subscription(client):
    token = register_and_login(client, "canceler@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/billing/subscriptions/00000000-0000-0000-0000-000000000000/cancel", headers=headers)

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

    subscriber_token = register_and_login(client, "subscriber@example.com")
    subscriber_headers = {"Authorization": f"Bearer {subscriber_token}"}
    me = client.get("/api/v1/users/me", headers=subscriber_headers).json()["data"]

    admin_token = register_and_login(client, "billing-admin@example.com")
    asyncio.run(_promote_to_admin(db_session_factory, "billing-admin@example.com"))
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    subscribe = client.post(
        "/api/v1/billing/subscriptions",
        json={"subject_type": "user", "subject_id": me["id"], "plan_key": "premium_monthly"},
        headers=admin_headers,
    )
    assert subscribe.status_code == 200

    entitlement = client.get(
        f"/api/v1/billing/entitlements/user/{me['id']}/advanced_analytics", headers=subscriber_headers
    )
    assert entitlement.json()["data"]["has_feature"] is True


def test_list_plans_is_public_read(client):
    response = client.get("/api/v1/billing/plans")
    assert response.status_code == 200

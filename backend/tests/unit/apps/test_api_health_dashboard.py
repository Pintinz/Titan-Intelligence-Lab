import asyncio
import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.admin.domain.entities import ProviderDefinition
from modules.admin.domain.value_objects import ProviderCategory, ProviderId, ProviderStatus
from modules.admin.infrastructure.persistence.models import Base
from modules.admin.infrastructure.persistence.repositories import SqlAlchemyProviderRepository
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"admin": None, "identity": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(IdentityBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


@pytest.fixture
def client(db_session_factory):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    test_client = TestClient(app)
    email, password = "health-admin@titaniq.test", "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_provider_id(db_session_factory) -> str:
    async with db_session_factory() as session:
        repo = SqlAlchemyProviderRepository(session=session)
        provider = ProviderDefinition(
            id=ProviderId(uuid.uuid4()),
            key="api_football",
            name="API-Football",
            category=ProviderCategory.SPORTS_DATA,
            status=ProviderStatus.ACTIVE,
        )
        await repo.upsert(provider)
        await session.commit()
        return str(provider.id)


def test_health_summary_with_no_checks_yet(client, seeded_provider_id):
    response = client.get(f"/api/v1/admin/providers/{seeded_provider_id}/health/summary")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "healthy"
    assert data["consecutive_failures"] == 0
    assert data["metrics"]["check_count"] == 0
    assert data["reliability_score"] is None


def test_recording_checks_via_api_updates_summary(client, seeded_provider_id):
    for _ in range(3):
        response = client.post(
            f"/api/v1/admin/providers/{seeded_provider_id}/health/check",
            json={"success": True, "latency_ms": 90.0},
        )
        assert response.status_code == 200

    summary = client.get(f"/api/v1/admin/providers/{seeded_provider_id}/health/summary").json()["data"]

    assert summary["metrics"]["check_count"] == 3
    assert summary["metrics"]["success_rate"] == pytest.approx(1.0)
    assert summary["status"] == "healthy"


def test_consecutive_failures_via_api_trigger_degradation_and_incident(client, seeded_provider_id):
    for _ in range(2):
        client.post(
            f"/api/v1/admin/providers/{seeded_provider_id}/health/check",
            json={"success": False, "message": "timeout"},
        )

    summary = client.get(f"/api/v1/admin/providers/{seeded_provider_id}/health/summary").json()["data"]
    assert summary["status"] == "degraded"

    incidents = client.get(f"/api/v1/admin/providers/{seeded_provider_id}/health/incidents").json()["data"]
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "warning"
    assert incidents[0]["is_open"] is True


def test_diagnostics_endpoint_reflects_down_status(client, seeded_provider_id):
    for _ in range(5):
        client.post(f"/api/v1/admin/providers/{seeded_provider_id}/health/check", json={"success": False})

    diagnostics = client.get(f"/api/v1/admin/providers/{seeded_provider_id}/diagnostics").json()["data"]

    assert diagnostics["status"] == "down"
    assert diagnostics["open_incident"]["severity"] == "critical"
    assert "DOWN" in diagnostics["recommendation"]


def test_health_trend_endpoint_returns_requested_number_of_days(client, seeded_provider_id):
    client.post(f"/api/v1/admin/providers/{seeded_provider_id}/health/check", json={"success": True})

    trend = client.get(f"/api/v1/admin/providers/{seeded_provider_id}/health/trend?days=5").json()["data"]

    assert len(trend) == 5


def test_credential_health_endpoint_with_no_usage_returns_null_score(client, seeded_provider_id):
    credential_id = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/admin/credentials/{credential_id}/health", params={"provider_id": seeded_provider_id}
    )

    assert response.status_code == 200
    assert response.json()["data"]["reliability_score"] is None


def test_unknown_provider_health_summary_returns_defaults_not_error(client):
    unknown_id = str(uuid.uuid4())

    response = client.get(f"/api/v1/admin/providers/{unknown_id}/health/summary")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "healthy"

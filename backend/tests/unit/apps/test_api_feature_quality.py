import asyncio

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"admin": None, "features": None, "identity": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(AdminBase.metadata.create_all)
        await conn.run_sync(FeaturesBase.metadata.create_all)
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
    email, password = "quality-admin@titaniq.test", "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    yield test_client
    app.dependency_overrides.clear()


FEATURE_BODY = {
    "feature_key": "football.team.form_index_last5",
    "name": "Form index (last 5)",
    "description": "Weighted recent form",
    "sport_code": "football",
    "category": "engineered",
    "formula": "weighted_avg(results, weights=[5,4,3,2,1])",
    "data_type": "float",
    "owner": "data-team",
    "entity_type": "team",
}
KEY = FEATURE_BODY["feature_key"]


@pytest.fixture
def registered_feature(client):
    response = client.post("/api/v1/admin/features", json=FEATURE_BODY)
    assert response.status_code == 200
    return response.json()["data"]


# -- Feature Quality API --------------------------------------------------------------------


def test_quality_with_no_data_returns_zero_sample_size(client, registered_feature):
    response = client.get(f"/api/v1/admin/features/{KEY}/quality")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sample_size"] == 0
    assert data["quality_score"] is None


def test_quality_for_unknown_feature_returns_404(client):
    response = client.get("/api/v1/admin/features/does.not.exist/quality")

    assert response.status_code == 404


# -- Feature Validation API -----------------------------------------------------------------


def test_validate_with_no_data_returns_failed_report(client, registered_feature):
    response = client.post(f"/api/v1/admin/features/{KEY}/validate")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["sample_size"] == 0


def test_validations_history_accumulates(client, registered_feature):
    client.post(f"/api/v1/admin/features/{KEY}/validate")
    client.post(f"/api/v1/admin/features/{KEY}/validate")

    history = client.get(f"/api/v1/admin/features/{KEY}/validations")
    latest = client.get(f"/api/v1/admin/features/{KEY}/validations/latest")

    assert len(history.json()["data"]) == 2
    assert latest.json()["data"] is not None


def test_latest_validation_null_when_never_validated(client, registered_feature):
    response = client.get(f"/api/v1/admin/features/{KEY}/validations/latest")

    assert response.json()["data"] is None


# -- Feature Usage API -----------------------------------------------------------------------


def test_record_and_read_usage(client, registered_feature):
    client.post(f"/api/v1/admin/features/{KEY}/usage")
    client.post(f"/api/v1/admin/features/{KEY}/usage")

    response = client.get(f"/api/v1/admin/features/{KEY}/usage")

    assert response.json()["data"]["read_count"] == 2


def test_register_and_list_consumers(client, registered_feature):
    client.post(f"/api/v1/admin/features/{KEY}/consumers", json={"consumer_key": "football.match_result.v1"})

    response = client.get(f"/api/v1/admin/features/{KEY}/consumers")

    consumers = response.json()["data"]
    assert len(consumers) == 1
    assert consumers[0]["consumer_key"] == "football.match_result.v1"


# -- Feature Statistics API -----------------------------------------------------------------


def test_record_computation_and_read_statistics(client, registered_feature):
    client.post(f"/api/v1/admin/features/{KEY}/computation", json={"duration_ms": 120.5, "memory_bytes": 4096})

    response = client.get(f"/api/v1/admin/features/{KEY}/statistics")

    data = response.json()["data"]
    assert data["computation_cost"]["sample_size"] == 1
    assert data["computation_cost"]["average_duration_ms"] == pytest.approx(120.5)
    assert data["storage_size_bytes"] is None  # no feature values recorded yet
    assert data["consumer_count"] == 0


# -- Feature Health API ----------------------------------------------------------------------


def test_feature_health_composes_everything(client, registered_feature):
    client.post(f"/api/v1/admin/features/{KEY}/computation", json={"duration_ms": 50})
    client.post(f"/api/v1/admin/features/{KEY}/consumers", json={"consumer_key": "market-a"})
    client.post(f"/api/v1/admin/features/{KEY}/usage")

    response = client.get(f"/api/v1/admin/features/{KEY}/health")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["feature_key"] == KEY
    assert data["status"] == "draft"
    assert data["consumer_count"] == 1
    assert data["usage_last_7_days"] == 1
    assert data["provider_source"] is None
    assert data["provider_reliability"] is None


def test_feature_health_for_unknown_feature_returns_404(client):
    response = client.get("/api/v1/admin/features/does.not.exist/health")

    assert response.status_code == 404


def test_deprecation_warning_appears_after_deprecation(client, registered_feature):
    client.post(f"/api/v1/admin/features/{KEY}/submit")
    client.post(f"/api/v1/admin/features/{KEY}/approve", json={"reviewer": "alice"})
    client.post(f"/api/v1/admin/features/{KEY}/deprecate")

    response = client.get(f"/api/v1/admin/features/{KEY}/health")

    assert "deprecated" in response.json()["data"]["deprecation_warning"].lower()

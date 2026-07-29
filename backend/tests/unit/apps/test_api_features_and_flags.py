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
    email, password = "features-admin@titaniq.test", "correct-horse-battery"
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


def test_register_feature_starts_as_draft(client):
    response = client.post("/api/v1/admin/features", json=FEATURE_BODY)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "draft"
    assert data["version"] == 1


def test_register_duplicate_feature_returns_409(client):
    client.post("/api/v1/admin/features", json=FEATURE_BODY)

    response = client.post("/api/v1/admin/features", json=FEATURE_BODY)

    assert response.status_code == 409


def test_register_with_empty_formula_returns_422(client):
    body = {**FEATURE_BODY, "formula": "   "}

    response = client.post("/api/v1/admin/features", json=body)

    assert response.status_code == 422


def test_full_review_lifecycle_via_api(client):
    client.post("/api/v1/admin/features", json=FEATURE_BODY)
    key = FEATURE_BODY["feature_key"]

    submit = client.post(f"/api/v1/admin/features/{key}/submit")
    assert submit.status_code == 200
    assert submit.json()["data"]["status"] == "in_review"

    approve = client.post(f"/api/v1/admin/features/{key}/approve", json={"reviewer": "alice@titanintel.com"})
    assert approve.status_code == 200
    approved = approve.json()["data"]
    assert approved["status"] == "active"
    assert approved["leakage_reviewed"] is True


def test_reject_returns_feature_to_draft(client):
    client.post("/api/v1/admin/features", json=FEATURE_BODY)
    key = FEATURE_BODY["feature_key"]
    client.post(f"/api/v1/admin/features/{key}/submit")

    rejected = client.post(
        f"/api/v1/admin/features/{key}/reject", json={"reviewer": "bob", "reason": "looks leaky"}
    )

    assert rejected.status_code == 200
    data = rejected.json()["data"]
    assert data["status"] == "draft"
    assert data["rejection_reason"] == "looks leaky"


def test_approve_without_submit_returns_409(client):
    client.post("/api/v1/admin/features", json=FEATURE_BODY)
    key = FEATURE_BODY["feature_key"]

    response = client.post(f"/api/v1/admin/features/{key}/approve", json={"reviewer": "alice"})

    assert response.status_code == 409


def test_get_and_list_features(client):
    client.post("/api/v1/admin/features", json=FEATURE_BODY)

    listed = client.get("/api/v1/admin/features")
    assert len(listed.json()["data"]) == 1

    fetched = client.get(f"/api/v1/admin/features/{FEATURE_BODY['feature_key']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["feature_key"] == FEATURE_BODY["feature_key"]


def test_get_unknown_feature_returns_404(client):
    response = client.get("/api/v1/admin/features/does.not.exist")

    assert response.status_code == 404


def test_deprecate_requires_active_status(client):
    client.post("/api/v1/admin/features", json=FEATURE_BODY)
    key = FEATURE_BODY["feature_key"]

    response = client.post(f"/api/v1/admin/features/{key}/deprecate")

    assert response.status_code == 409


# -- Feature Flags --------------------------------------------------------------------------


def test_create_flag_and_evaluate(client):
    created = client.post(
        "/api/v1/admin/flags",
        json={"key": "table_tennis_predictions", "name": "TT Predictions", "description": "Gate TT markets"},
    )
    assert created.status_code == 200
    assert created.json()["data"]["enabled"] is False

    evaluated = client.get("/api/v1/admin/flags/table_tennis_predictions/evaluate")
    assert evaluated.json()["data"]["enabled"] is False


def test_enable_flag_then_evaluate_true_at_full_rollout(client):
    client.post("/api/v1/admin/flags", json={"key": "k", "name": "n", "description": "d"})

    client.post("/api/v1/admin/flags/k/enable")
    evaluated = client.get("/api/v1/admin/flags/k/evaluate")

    assert evaluated.json()["data"]["enabled"] is True


def test_set_rollout_to_zero_disables_for_everyone(client):
    client.post("/api/v1/admin/flags", json={"key": "k", "name": "n", "description": "d", "enabled": True})

    client.post("/api/v1/admin/flags/k/rollout", json={"percentage": 0})
    evaluated = client.get("/api/v1/admin/flags/k/evaluate", params={"context_id": "user-1"})

    assert evaluated.json()["data"]["enabled"] is False


def test_invalid_rollout_percentage_returns_422(client):
    client.post("/api/v1/admin/flags", json={"key": "k", "name": "n", "description": "d"})

    response = client.post("/api/v1/admin/flags/k/rollout", json={"percentage": 200})

    assert response.status_code == 422


def test_flag_operations_on_unknown_key_return_404(client):
    response = client.post("/api/v1/admin/flags/nope/enable")

    assert response.status_code == 404


def test_create_duplicate_flag_returns_409(client):
    client.post("/api/v1/admin/flags", json={"key": "k", "name": "n", "description": "d"})

    response = client.post("/api/v1/admin/flags", json={"key": "k", "name": "n2", "description": "d2"})

    assert response.status_code == 409


def test_list_flags(client):
    client.post("/api/v1/admin/flags", json={"key": "a", "name": "n", "description": "d"})
    client.post("/api/v1/admin/flags", json={"key": "b", "name": "n", "description": "d"})

    response = client.get("/api/v1/admin/flags")

    assert len(response.json()["data"]) == 2

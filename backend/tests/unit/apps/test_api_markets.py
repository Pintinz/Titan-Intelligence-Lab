from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.features.domain.entities import FeatureDefinition
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
)
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.features.infrastructure.persistence.repositories import SqlAlchemyFeatureDefinitionRepository
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator
from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.value_objects import MarketId, ModelId, ModelStatus
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyModelRepository

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "predictions": None, "features": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(PredictionsBase.metadata.create_all)
        await conn.run_sync(FeaturesBase.metadata.create_all)

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


def _auth_headers(client, db_session_factory, email="market-admin@titaniq.test", password="correct-horse-battery"):
    # Market lifecycle mutations are ADMINISTRATOR-only (C-3) — promote this test user so the
    # existing lifecycle tests keep exercising the real mutation flow, not just the 403 gate.
    client.post("/api/v1/auth/register", json={"email": email, "password": password})

    async def _promote():
        async with db_session_factory() as session:
            users = SqlAlchemyUserRepository(session=session)
            user = await users.get_by_email(Email(email))
            user.role = Role.ADMINISTRATOR
            await users.upsert(user)
            await session.commit()

    __import__("asyncio").run(_promote())

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_active_feature(db_session_factory, feature_key: str) -> None:
    async with db_session_factory() as session:
        definitions = SqlAlchemyFeatureDefinitionRepository(session=session)
        await definitions.upsert(
            FeatureDefinition(
                id=FeatureDefinitionId(uuid4()),
                feature_key=FeatureKey(feature_key),
                name="Test Feature",
                description="test",
                sport_code="football",
                category=FeatureCategory.ENGINEERED,
                formula="n/a",
                data_type=FeatureDataType.FLOAT,
                owner="test",
                entity_type=EntityType.FIXTURE,
                status=FeatureStatus.ACTIVE,
            )
        )
        await session.commit()


def _register_market(client, headers, market_key="football.router_test_market"):
    return client.post(
        "/api/v1/markets",
        json={
            "market_key": market_key,
            "sport_code": "football",
            "name": "Router Test Market",
            "category": "match_outcome",
            "market_kind": "binary",
            "target_type": "classification",
        },
        headers=headers,
    )


def test_register_and_get_market(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    created = _register_market(client, headers)
    assert created.status_code == 200
    assert created.json()["data"]["status"] == "draft"

    fetched = client.get("/api/v1/markets/football.router_test_market", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["market_key"] == "football.router_test_market"


async def _register_champion(db_session_factory, market_id: str, *, genuinely_trained: bool) -> None:
    async with db_session_factory() as session:
        models = SqlAlchemyModelRepository(session=session)
        model = ModelDefinition(
            id=ModelId(uuid4()), market_id=MarketId(UUID(market_id)), model_key="test.champion",
            version=1, algorithm="logistic_regression" if genuinely_trained else "heuristic_logistic_v1",
            status=ModelStatus.CHAMPION,
            artifact_ref="artifacts/real-model.joblib" if genuinely_trained else None,
        )
        await models.upsert(model)
        await session.commit()


def test_market_with_no_champion_reports_training_status_no_champion(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    _register_market(client, headers, market_key="football.training_status_none")

    fetched = client.get("/api/v1/markets/football.training_status_none", headers=headers)

    assert fetched.json()["data"]["training_status"] == "NO_CHAMPION"


def test_market_with_heuristic_placeholder_champion_reports_training_status_honestly(client, db_session_factory):
    """Milestone 4 status honesty (Rule 13): a market whose only Champion is a placeholder-
    heuristic (no artifact_ref) must not report the same training_status as a genuinely trained
    one — this is the real gap found in football.first_half_winner and 4 sibling markets."""
    headers = _auth_headers(client, db_session_factory)
    created = _register_market(client, headers, market_key="football.training_status_heuristic")
    market_id = created.json()["data"]["id"]
    __import__("asyncio").run(_register_champion(db_session_factory, market_id, genuinely_trained=False))

    fetched = client.get("/api/v1/markets/football.training_status_heuristic", headers=headers)
    listed = client.get("/api/v1/markets", params={"sport_code": "football"}, headers=headers)

    assert fetched.json()["data"]["training_status"] == "HEURISTIC_PLACEHOLDER"
    listed_entry = next(m for m in listed.json()["data"] if m["market_key"] == "football.training_status_heuristic")
    assert listed_entry["training_status"] == "HEURISTIC_PLACEHOLDER"


def test_market_with_trained_champion_reports_training_status_trained(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    created = _register_market(client, headers, market_key="football.training_status_trained")
    market_id = created.json()["data"]["id"]
    __import__("asyncio").run(_register_champion(db_session_factory, market_id, genuinely_trained=True))

    fetched = client.get("/api/v1/markets/football.training_status_trained", headers=headers)

    assert fetched.json()["data"]["training_status"] == "TRAINED"


def test_non_admin_cannot_register_market(client, db_session_factory):
    client.post("/api/v1/auth/register", json={"email": "free-user@titaniq.test", "password": "correct-horse-battery"})
    login = client.post("/api/v1/auth/login", json={"email": "free-user@titaniq.test", "password": "correct-horse-battery"})
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    response = _register_market(client, headers, market_key="football.non_admin_market")

    assert response.status_code == 403


def test_non_admin_cannot_promote_market(client, db_session_factory):
    admin_headers = _auth_headers(client, db_session_factory)
    market_key = "football.non_admin_promote_market"
    _register_market(client, admin_headers, market_key=market_key)

    client.post("/api/v1/auth/register", json={"email": "free-user-2@titaniq.test", "password": "correct-horse-battery"})
    login = client.post("/api/v1/auth/login", json={"email": "free-user-2@titaniq.test", "password": "correct-horse-battery"})
    free_headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    response = client.post(f"/api/v1/markets/{market_key}/promote", headers=free_headers)

    assert response.status_code == 403


def test_register_duplicate_market_returns_409(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    _register_market(client, headers)

    duplicate = _register_market(client, headers)

    assert duplicate.status_code == 409


def test_get_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.get("/api/v1/markets/does.not.exist", headers=headers)

    assert response.status_code == 404


def test_list_markets_filters_by_sport_and_status(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    _register_market(client, headers, market_key="football.list_a")
    _register_market(client, headers, market_key="football.list_b")

    all_football = client.get("/api/v1/markets", params={"sport_code": "football"}, headers=headers)
    assert all_football.json()["meta"]["count"] == 2

    draft_only = client.get("/api/v1/markets", params={"status": "draft"}, headers=headers)
    assert draft_only.json()["meta"]["count"] == 2


def test_full_lifecycle_to_production_requires_feature_mapping(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    market_key = "football.lifecycle_market"
    _register_market(client, headers, market_key=market_key)
    asyncio_run = __import__("asyncio").run
    asyncio_run(_seed_active_feature(db_session_factory, "football.lifecycle_feature"))

    client.post(f"/api/v1/markets/{market_key}/submit", headers=headers)
    approved = client.post(f"/api/v1/markets/{market_key}/approve", json={"reviewer": "cto"}, headers=headers)
    assert approved.json()["data"]["status"] == "approved"

    not_ready = client.post(f"/api/v1/markets/{market_key}/promote", headers=headers)
    assert not_ready.status_code == 409

    mapped = client.post(
        f"/api/v1/markets/{market_key}/features",
        json={"feature_key": "football.lifecycle_feature", "is_required": True},
        headers=headers,
    )
    assert mapped.status_code == 200
    assert mapped.json()["data"]["feature_key"] == "football.lifecycle_feature"

    promoted = client.post(f"/api/v1/markets/{market_key}/promote", headers=headers)
    assert promoted.status_code == 200
    assert promoted.json()["data"]["status"] == "production"

    features = client.get(f"/api/v1/markets/{market_key}/features", headers=headers)
    assert features.json()["meta"]["count"] == 1


def test_map_feature_to_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post(
        "/api/v1/markets/does.not.exist/features", json={"feature_key": "x"}, headers=headers
    )

    assert response.status_code == 404


def test_map_unapproved_feature_returns_422(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    market_key = "football.unapproved_feature_market"
    _register_market(client, headers, market_key=market_key)

    response = client.post(
        f"/api/v1/markets/{market_key}/features", json={"feature_key": "does.not.exist"}, headers=headers
    )

    assert response.status_code == 422


def test_reject_market_returns_to_draft(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    market_key = "football.reject_market"
    _register_market(client, headers, market_key=market_key)
    client.post(f"/api/v1/markets/{market_key}/submit", headers=headers)

    rejected = client.post(
        f"/api/v1/markets/{market_key}/reject", json={"reviewer": "cto", "reason": "no data"}, headers=headers
    )

    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "draft"
    assert rejected.json()["data"]["rejection_reason"] == "no data"


def test_register_market_invalid_market_kind_returns_422(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post(
        "/api/v1/markets",
        json={
            "market_key": "football.invalid_kind_market",
            "sport_code": "football",
            "name": "Test",
            "category": "match_outcome",
            "market_kind": "not-a-real-kind",
            "target_type": "classification",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_register_market_invalid_target_type_returns_422(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post(
        "/api/v1/markets",
        json={
            "market_key": "football.invalid_target_market",
            "sport_code": "football",
            "name": "Test",
            "category": "match_outcome",
            "market_kind": "binary",
            "target_type": "not-a-real-target",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_list_markets_invalid_status_returns_422(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.get("/api/v1/markets", params={"status": "not-a-real-status"}, headers=headers)

    assert response.status_code == 422


def test_submit_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post("/api/v1/markets/does.not.exist/submit", headers=headers)

    assert response.status_code == 404


def test_submit_from_wrong_state_returns_409(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    market_key = "football.wrong_state_market"
    _register_market(client, headers, market_key=market_key)
    client.post(f"/api/v1/markets/{market_key}/submit", headers=headers)

    response = client.post(f"/api/v1/markets/{market_key}/submit", headers=headers)

    assert response.status_code == 409


def test_approve_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post("/api/v1/markets/does.not.exist/approve", json={"reviewer": "cto"}, headers=headers)

    assert response.status_code == 404


def test_reject_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post("/api/v1/markets/does.not.exist/reject", json={"reviewer": "cto"}, headers=headers)

    assert response.status_code == 404


def test_promote_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post("/api/v1/markets/does.not.exist/promote", headers=headers)

    assert response.status_code == 404


def test_promote_wrong_state_returns_409(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    market_key = "football.promote_wrong_state_market"
    _register_market(client, headers, market_key=market_key)

    response = client.post(f"/api/v1/markets/{market_key}/promote", headers=headers)

    assert response.status_code == 409


def test_deprecate_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post("/api/v1/markets/does.not.exist/deprecate", headers=headers)

    assert response.status_code == 404


def test_deprecate_wrong_state_returns_409(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    market_key = "football.deprecate_wrong_state_market"
    _register_market(client, headers, market_key=market_key)

    response = client.post(f"/api/v1/markets/{market_key}/deprecate", headers=headers)

    assert response.status_code == 409


def test_archive_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post("/api/v1/markets/does.not.exist/archive", headers=headers)

    assert response.status_code == 404


def test_remove_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.post("/api/v1/markets/does.not.exist/remove", headers=headers)

    assert response.status_code == 404


def test_list_features_for_unknown_market_returns_404(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)

    response = client.get("/api/v1/markets/does.not.exist/features", headers=headers)

    assert response.status_code == 404


def test_full_lifecycle_through_archive_and_remove(client, db_session_factory):
    headers = _auth_headers(client, db_session_factory)
    market_key = "football.full_lifecycle_market"
    _register_market(client, headers, market_key=market_key)
    asyncio_run = __import__("asyncio").run
    asyncio_run(_seed_active_feature(db_session_factory, "football.full_lifecycle_feature"))
    client.post(f"/api/v1/markets/{market_key}/submit", headers=headers)
    client.post(f"/api/v1/markets/{market_key}/approve", json={"reviewer": "cto"}, headers=headers)
    client.post(
        f"/api/v1/markets/{market_key}/features",
        json={"feature_key": "football.full_lifecycle_feature", "is_required": True},
        headers=headers,
    )
    client.post(f"/api/v1/markets/{market_key}/promote", headers=headers)

    deprecated = client.post(f"/api/v1/markets/{market_key}/deprecate", headers=headers)
    assert deprecated.json()["data"]["status"] == "deprecated"

    archived = client.post(f"/api/v1/markets/{market_key}/archive", headers=headers)
    assert archived.json()["data"]["status"] == "archived"

    removed = client.post(f"/api/v1/markets/{market_key}/remove", headers=headers)
    assert removed.json()["data"]["status"] == "removed"

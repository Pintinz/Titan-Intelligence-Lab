from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.features.domain.entities import FeatureDefinition, FeatureValue
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    FeatureValueId,
    QualityFlag,
)
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.features.infrastructure.persistence.repositories import (
    SqlAlchemyFeatureDefinitionRepository,
    SqlAlchemyFeatureValueRepository,
)
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.predictions.domain.entities import FeatureMarketMapping, MarketDefinition, ModelDefinition
from modules.predictions.domain.value_objects import (
    FeatureMarketMappingId,
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    ModelStatus,
    TargetType,
)
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyFeatureMarketMappingRepository,
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
)
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.watchlist.infrastructure.persistence.models import Base as WatchlistBase
from modules.alerts.infrastructure.persistence.models import Base as AlertsBase

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={
            "schema_translate_map": {
                "identity": None,
                "predictions": None,
                "features": None,
                "sports": None,
                "intelligence": None,
                "knowledge_graph": None,
                "watchlist": None,
                "alerts": None,
            }
        },
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(PredictionsBase.metadata.create_all)
        await conn.run_sync(FeaturesBase.metadata.create_all)
        await conn.run_sync(SportsBase.metadata.create_all)
        await conn.run_sync(IntelligenceBase.metadata.create_all)
        await conn.run_sync(KnowledgeGraphBase.metadata.create_all)
        await conn.run_sync(WatchlistBase.metadata.create_all)
        await conn.run_sync(AlertsBase.metadata.create_all)

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


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


def _admin_headers(client, db_session_factory, email="admin@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _regular_headers(client, email="regular@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def _seed_production_market(db_session_factory, market_key: str, feature_key: str) -> MarketId:
    async with db_session_factory() as session:
        markets = SqlAlchemyMarketRepository(session=session)
        models = SqlAlchemyModelRepository(session=session)
        mappings = SqlAlchemyFeatureMarketMappingRepository(session=session)
        definitions = SqlAlchemyFeatureDefinitionRepository(session=session)
        values = SqlAlchemyFeatureValueRepository(session=session)

        definition = FeatureDefinition(
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
        await definitions.upsert(definition)
        await values.record(
            FeatureValue(
                id=FeatureValueId(uuid4()),
                feature_key=definition.feature_key,
                entity_type=EntityType.FIXTURE,
                entity_id="fixture-1",
                as_of=T0,
                value=0.8,
                quality_flags=(QualityFlag.OK,),
            )
        )

        market = MarketDefinition(
            id=MarketId(uuid4()),
            market_key=market_key,
            sport_code="football",
            name="Test Market",
            category="match_outcome",
            market_kind=MarketKind.BINARY,
            target_type=TargetType.CLASSIFICATION,
            status=MarketStatus.PRODUCTION,
            confidence_threshold=0.0,
        )
        await markets.upsert(market)
        await mappings.upsert(
            FeatureMarketMapping(
                id=FeatureMarketMappingId(uuid4()), market_id=market.id, feature_key=feature_key, is_required=True
            )
        )
        model = ModelDefinition(
            id=ModelId(uuid4()),
            market_id=market.id,
            model_key=f"{market_key}.heuristic",
            version=1,
            algorithm="heuristic_logistic_v1",
            status=ModelStatus.CHAMPION,
        )
        await models.upsert(model)
        await session.commit()
        return market.id


def test_market_health_requires_administrator_role(client, db_session_factory):
    headers = _regular_headers(client)

    response = client.get("/api/v1/admin/predictions/markets/health", headers=headers)

    assert response.status_code == 403


def test_market_health_reports_missing_champion(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    asyncio.run(_seed_production_market(db_session_factory, "football.admin_health_market", "football.admin_feature_a"))

    response = client.get("/api/v1/admin/predictions/markets/health", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["total_markets"] == 1
    assert response.json()["data"]["production_markets_missing_champion"] == []


def test_regenerate_forces_a_fresh_prediction(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    asyncio.run(_seed_production_market(db_session_factory, "football.admin_regen_market", "football.admin_feature_b"))
    first = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.admin_regen_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    ).json()["data"]

    response = client.post(
        "/api/v1/admin/predictions/regenerate",
        json={
            "market_key": "football.admin_regen_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] != first["id"]


def test_regenerate_unknown_market_returns_404(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.post(
        "/api/v1/admin/predictions/regenerate",
        json={"market_key": "does.not.exist", "entity_type": "fixture", "entity_id": "x", "subject_ref": "x"},
        headers=headers,
    )

    assert response.status_code == 404


def test_alerts_endpoint_returns_missing_champion_alert(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    async def _seed_no_champion_market():
        async with db_session_factory() as session:
            markets = SqlAlchemyMarketRepository(session=session)
            market = MarketDefinition(
                id=MarketId(uuid4()), market_key="football.admin_alert_market", sport_code="football", name="Test",
                category="match_outcome", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
                status=MarketStatus.PRODUCTION,
            )
            await markets.upsert(market)
            await session.commit()

    asyncio.run(_seed_no_champion_market())

    response = client.get("/api/v1/admin/predictions/alerts", headers=headers)

    assert response.status_code == 200
    alert_types = {(a["type"], a["market_key"]) for a in response.json()["data"]}
    assert ("missing_champion", "football.admin_alert_market") in alert_types


def test_export_market_predictions(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    asyncio.run(_seed_production_market(db_session_factory, "football.admin_export_market", "football.admin_feature_c"))
    client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.admin_export_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    response = client.get("/api/v1/admin/predictions/markets/football.admin_export_market/export", headers=headers)

    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 1


def test_rollback_model(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    market_id = asyncio.run(
        _seed_production_market(db_session_factory, "football.admin_rollback_market", "football.admin_feature_d")
    )

    async def _create_second_champion():
        async with db_session_factory() as session:
            models = SqlAlchemyModelRepository(session=session)
            first_champion = await models.get_champion(market_id)
            first_champion.status = ModelStatus.RETIRED
            first_champion.retired_at = T0
            await models.upsert(first_champion)

            second = ModelDefinition(
                id=ModelId(uuid4()), market_id=market_id, model_key="football.admin_rollback_market.v2", version=1,
                algorithm="heuristic_logistic_v1", status=ModelStatus.CHAMPION,
            )
            await models.upsert(second)
            await session.commit()
            return first_champion.id

    original_id = asyncio.run(_create_second_champion())

    response = client.post("/api/v1/admin/predictions/models/rollback", json={"market_id": str(market_id)}, headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(original_id)
    assert response.json()["data"]["status"] == "champion"


def test_market_confidence_accuracy_and_drift_dashboards(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)
    asyncio.run(_seed_production_market(db_session_factory, "football.admin_dashboards_market", "football.admin_feature_e"))
    client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.admin_dashboards_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    confidence = client.get("/api/v1/admin/predictions/markets/football.admin_dashboards_market/confidence", headers=headers)
    accuracy = client.get("/api/v1/admin/predictions/markets/football.admin_dashboards_market/accuracy", headers=headers)
    drift = client.get("/api/v1/admin/predictions/markets/football.admin_dashboards_market/drift", headers=headers)

    assert confidence.status_code == 200
    assert confidence.json()["data"]["sample_size"] == 1
    assert accuracy.status_code == 200
    assert accuracy.json()["data"] == {"sample_size": 0, "historical_accuracy": None}
    assert drift.status_code == 200
    assert drift.json()["data"]["sample_size"] == 1


def test_market_confidence_dashboard_unknown_market_returns_404(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.get("/api/v1/admin/predictions/markets/does.not.exist/confidence", headers=headers)

    assert response.status_code == 404


def test_market_export_unknown_market_returns_404(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.get("/api/v1/admin/predictions/markets/does.not.exist/export", headers=headers)

    assert response.status_code == 404


def test_regenerate_invalid_entity_type_returns_422(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.post(
        "/api/v1/admin/predictions/regenerate",
        json={"market_key": "x", "entity_type": "not-a-real-entity", "entity_id": "x", "subject_ref": "x"},
        headers=headers,
    )

    assert response.status_code == 422


def test_rollback_invalid_market_id_returns_422(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.post("/api/v1/admin/predictions/models/rollback", json={"market_id": "not-a-uuid"}, headers=headers)

    assert response.status_code == 422


def test_rollback_unknown_market_returns_404(client, db_session_factory):
    headers = _admin_headers(client, db_session_factory)

    response = client.post("/api/v1/admin/predictions/models/rollback", json={"market_id": str(uuid4())}, headers=headers)

    assert response.status_code == 404

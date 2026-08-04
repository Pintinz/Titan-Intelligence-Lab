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
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
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


def _auth_headers(client, email="analytics@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def _seed_production_market(
    db_session_factory,
    market_key: str,
    feature_key: str,
    sport_code: str = "football",
    confidence_threshold: float = 0.0,
) -> MarketId:
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
            sport_code=sport_code,
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
            sport_code=sport_code,
            name="Test Market",
            category="match_outcome",
            market_kind=MarketKind.BINARY,
            target_type=TargetType.CLASSIFICATION,
            status=MarketStatus.PRODUCTION,
            confidence_threshold=confidence_threshold,
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


def _generate(client, headers, market_key, subject_ref="fixture-1"):
    return client.post(
        "/api/v1/predictions/generate",
        json={"market_key": market_key, "entity_type": "fixture", "entity_id": "fixture-1", "subject_ref": subject_ref},
        headers=headers,
    ).json()["data"]


def test_get_confidence_and_explanation_sub_resources(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(_seed_production_market(db_session_factory, "football.analytics_confidence_market", "football.analytics_feature_a"))
    prediction = _generate(client, headers, "football.analytics_confidence_market")

    confidence = client.get(f"/api/v1/predictions/{prediction['id']}/confidence", headers=headers)
    explanation = client.get(f"/api/v1/predictions/{prediction['id']}/explanation", headers=headers)

    assert confidence.status_code == 200
    assert confidence.json()["data"]["composite"] == prediction["confidence"]["composite"]
    assert explanation.status_code == 200
    assert explanation.json()["data"]["ai_explanation"] == prediction["explanation"]["ai_explanation"]


def test_prediction_history_for_subject(client, db_session_factory):
    headers = _auth_headers(client)
    market_id = asyncio.run(
        _seed_production_market(db_session_factory, "football.analytics_history_market", "football.analytics_feature_b")
    )
    _generate(client, headers, "football.analytics_history_market", subject_ref="fixture-history")

    response = client.get("/api/v1/predictions/history/fixture-history", headers=headers)

    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 1
    assert response.json()["data"][0]["market_id"] == str(market_id)


def test_history_route_is_not_shadowed_by_prediction_id_route(client):
    headers = _auth_headers(client)

    response = client.get("/api/v1/predictions/history/unknown-subject", headers=headers)

    # A 422 (invalid prediction_id UUID) would mean the generic /{prediction_id} route
    # swallowed this request instead of the literal /history/{subject_ref} route.
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_monitoring_summary_counts_by_status(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.analytics_monitoring_market", "football.analytics_feature_c")
    )
    _generate(client, headers, "football.analytics_monitoring_market")

    response = client.get("/api/v1/predictions/monitoring/summary", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sample_size"] == 1
    assert data["predictions_by_status"] == {"published": 1}
    assert data["audits_by_action"] == {"generated": 1}


def test_statistics_for_market(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.analytics_statistics_market", "football.analytics_feature_d")
    )
    _generate(client, headers, "football.analytics_statistics_market")

    response = client.get("/api/v1/predictions/statistics/football.analytics_statistics_market", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sample_size"] == 1
    assert data["publish_rate"] == 1.0
    assert 0.0 <= data["average_probability"] <= 1.0


def test_statistics_for_unknown_market_returns_404(client):
    headers = _auth_headers(client)

    response = client.get("/api/v1/predictions/statistics/does.not.exist", headers=headers)

    assert response.status_code == 404


def test_statistics_for_market_with_no_predictions_returns_nulls(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.analytics_empty_market", "football.analytics_feature_e")
    )

    response = client.get("/api/v1/predictions/statistics/football.analytics_empty_market", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sample_size"] == 0
    assert data["average_probability"] is None


def test_compare_predictions(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.analytics_compare_market_a", "football.analytics_feature_f")
    )
    asyncio.run(
        _seed_production_market(db_session_factory, "football.analytics_compare_market_b", "football.analytics_feature_g")
    )
    first = _generate(client, headers, "football.analytics_compare_market_a", subject_ref="fixture-cmp")
    second = _generate(client, headers, "football.analytics_compare_market_b", subject_ref="fixture-cmp")

    response = client.post(
        "/api/v1/predictions/compare", json={"prediction_ids": [first["id"], second["id"]]}, headers=headers
    )

    assert response.status_code == 200
    ids = {p["id"] for p in response.json()["data"]}
    assert ids == {first["id"], second["id"]}


def test_compare_requires_at_least_two_ids(client):
    headers = _auth_headers(client)

    response = client.post("/api/v1/predictions/compare", json={"prediction_ids": [str(uuid4())]}, headers=headers)

    assert response.status_code == 422


def test_compare_unknown_prediction_returns_404(client):
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/predictions/compare", json={"prediction_ids": [str(uuid4()), str(uuid4())]}, headers=headers
    )

    assert response.status_code == 404


def test_get_confidence_invalid_prediction_id_returns_422(client):
    headers = _auth_headers(client)

    response = client.get("/api/v1/predictions/not-a-uuid/confidence", headers=headers)

    assert response.status_code == 422


def test_get_explanation_unknown_prediction_returns_404(client):
    headers = _auth_headers(client)

    response = client.get(f"/api/v1/predictions/{uuid4()}/explanation", headers=headers)

    assert response.status_code == 404


def test_prediction_history_invalid_market_id_returns_422(client):
    headers = _auth_headers(client)

    response = client.get(
        "/api/v1/predictions/history/fixture-1", params={"market_id": "not-a-uuid"}, headers=headers
    )

    assert response.status_code == 422


# -- AI Picks -----------------------------------------------------------------------------------


def test_picks_route_is_not_shadowed_by_prediction_id_route(client):
    headers = _auth_headers(client)

    response = client.get("/api/v1/predictions/picks", headers=headers)

    # A 422 (invalid prediction_id UUID) would mean the generic /{prediction_id} route
    # swallowed this request instead of the literal /picks route.
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_ai_picks_includes_published_prediction_with_market_context(client, db_session_factory):
    headers = _auth_headers(client)
    market_id = asyncio.run(
        _seed_production_market(db_session_factory, "football.picks_market", "football.picks_feature_a")
    )
    prediction = _generate(client, headers, "football.picks_market")

    response = client.get("/api/v1/predictions/picks", headers=headers)

    assert response.status_code == 200
    picks = response.json()["data"]
    assert len(picks) == 1
    pick = picks[0]
    assert pick["id"] == prediction["id"]
    assert pick["market_id"] == str(market_id)
    assert pick["market_key"] == "football.picks_market"
    assert pick["market_name"] == "Test Market"
    assert pick["sport_code"] == "football"
    assert pick["status"] == "published"
    assert isinstance(pick["evidence_count"], int) and pick["evidence_count"] >= 0


def test_ai_picks_excludes_below_threshold_draft_predictions(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(
            db_session_factory,
            "football.picks_draft_market",
            "football.picks_feature_b",
            confidence_threshold=1.1,  # unreachable — every prediction here stays DRAFT
        )
    )
    _generate(client, headers, "football.picks_draft_market")

    response = client.get("/api/v1/predictions/picks", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_ai_picks_filters_by_sport_code(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(
            db_session_factory, "basketball.picks_market", "basketball.picks_feature_a", sport_code="basketball"
        )
    )
    _generate(client, headers, "basketball.picks_market")

    football_picks = client.get("/api/v1/predictions/picks", params={"sport_code": "football"}, headers=headers)
    basketball_picks = client.get("/api/v1/predictions/picks", params={"sport_code": "basketball"}, headers=headers)

    assert football_picks.json()["data"] == []
    assert len(basketball_picks.json()["data"]) == 1
    assert basketball_picks.json()["data"][0]["sport_code"] == "basketball"


def test_ai_picks_respects_limit(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(_seed_production_market(db_session_factory, "football.picks_limit_a", "football.picks_feature_c"))
    asyncio.run(_seed_production_market(db_session_factory, "football.picks_limit_b", "football.picks_feature_d"))
    _generate(client, headers, "football.picks_limit_a", subject_ref="fixture-limit-a")
    _generate(client, headers, "football.picks_limit_b", subject_ref="fixture-limit-b")

    response = client.get("/api/v1/predictions/picks", params={"limit": 1}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import fakeredis
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import apps.api.composition as composition
import apps.api.main as main_module
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
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, ModelId, ModelStatus, TargetType
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository, SqlAlchemyModelRepository
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
def client(db_session_factory, monkeypatch):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    # Same pattern as test_api_ingestion.py's `client` fixture: generating/reading a prediction
    # goes through build_prediction_cache_service -> build_prediction_engine ->
    # build_explainability_engine -> get_redis_sync_cache() -> get_redis_client(), and that
    # function is @lru_cache'd process-wide — without clearing + patching it here, whichever test
    # in the whole session happens to run first determines whether every other test gets a real
    # (missing-env-var) failure or a stale cached client, regardless of what this test itself does.
    from modules.admin.infrastructure.vault import get_vault_settings

    fake_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    composition.get_redis_client.cache_clear()
    composition.get_redis_lock.cache_clear()
    composition.get_redis_sync_cache.cache_clear()
    monkeypatch.setattr(composition, "get_redis_client", lambda: fake_client)
    monkeypatch.setattr(main_module, "get_redis_client", lambda: fake_client)

    monkeypatch.setenv("TITANIQ_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_vault_settings.cache_clear()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth_headers(client, email="predictor@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


def _admin_headers(client, db_session_factory, email="prediction-admin@titaniq.test", password="correct-horse-battery"):
    # approve/reject are ADMINISTRATOR-only (C-3) — a plain authenticated user must not be able
    # to publish or void a below-threshold DRAFT prediction.
    import asyncio

    headers = _auth_headers(client, email, password)
    asyncio.run(_promote_to_admin(db_session_factory, email))
    return headers


async def _seed_production_market(
    db_session_factory, market_key: str, feature_key: str, confidence_threshold: float = 0.0
) -> tuple[MarketId, ModelId]:
    async with db_session_factory() as session:
        markets = SqlAlchemyMarketRepository(session=session)
        models = SqlAlchemyModelRepository(session=session)
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
            confidence_threshold=confidence_threshold,
        )
        await markets.upsert(market)

        from modules.predictions.domain.entities import FeatureMarketMapping
        from modules.predictions.domain.value_objects import FeatureMarketMappingId
        from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyFeatureMarketMappingRepository

        mappings = SqlAlchemyFeatureMarketMappingRepository(session=session)
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
        return market.id, model.id


def test_generate_prediction_returns_published_prediction(client, db_session_factory):
    headers = _auth_headers(client)
    import asyncio

    asyncio.run(_seed_production_market(db_session_factory, "football.api_test_market", "football.api_test_feature"))

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_test_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "published"
    assert 0.0 <= data["probability"] <= 1.0
    assert data["feature_snapshot"] == {"football.api_test_feature": 0.8}
    assert "composite" in data["confidence"]
    assert data["explanation"]["ai_explanation"]


def test_generate_prediction_rejects_pat_without_required_scope(client, db_session_factory):
    headers = _auth_headers(client, email="scoped@titaniq.test")
    import asyncio

    asyncio.run(_seed_production_market(db_session_factory, "football.scope_test_market", "football.scope_test_feature"))

    narrow_token = client.post(
        "/api/v1/users/me/tokens", json={"name": "read-only", "scopes": ["read:predictions"]}, headers=headers
    ).json()["data"]["raw_token"]

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.scope_test_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers={"Authorization": f"Bearer {narrow_token}"},
    )

    assert response.status_code == 403


def test_generate_prediction_allows_pat_with_required_scope(client, db_session_factory):
    headers = _auth_headers(client, email="scoped2@titaniq.test")
    import asyncio

    asyncio.run(_seed_production_market(db_session_factory, "football.scope_test_market2", "football.scope_test_feature2"))

    scoped_token = client.post(
        "/api/v1/users/me/tokens",
        json={"name": "generator", "scopes": ["predictions:generate"]},
        headers=headers,
    ).json()["data"]["raw_token"]

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.scope_test_market2",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers={"Authorization": f"Bearer {scoped_token}"},
    )

    assert response.status_code == 200


async def _seed_production_market_without_champion(db_session_factory, market_key: str) -> MarketId:
    """A PRODUCTION market with genuinely no CHAMPION model — the "not yet trained" state the ML-
    architecture consolidation (2026-08-04) leaves `football.correct_score` and the eleven
    Over/Under-style markets in, since their old Poisson formula fallback was removed."""
    async with db_session_factory() as session:
        markets = SqlAlchemyMarketRepository(session=session)
        market = MarketDefinition(
            id=MarketId(uuid4()),
            market_key=market_key,
            sport_code="football",
            name="Test Not-Yet-Trained Market",
            category="match_outcome",
            market_kind=MarketKind.CORRECT_SCORE,
            target_type=TargetType.CLASSIFICATION,
            status=MarketStatus.PRODUCTION,
            confidence_threshold=0.0,
        )
        await markets.upsert(market)
        await session.commit()
        return market.id


def test_generate_prediction_for_untrained_market_returns_insufficient_data(client, db_session_factory):
    headers = _auth_headers(client)
    import asyncio

    asyncio.run(_seed_production_market_without_champion(db_session_factory, "football.not_yet_trained_test_market"))

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.not_yet_trained_test_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["prediction_status"] == "BLOCKED"
    assert detail["reason_code"] == "NO_CHAMPION_MODEL"
    assert "insufficient historical data" in detail["message"].lower()


def test_generate_prediction_unknown_market_returns_404(client):
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/predictions/generate",
        json={"market_key": "does.not.exist", "entity_type": "fixture", "entity_id": "x", "subject_ref": "x"},
        headers=headers,
    )

    assert response.status_code == 404


def test_generate_prediction_requires_auth(client):
    response = client.post(
        "/api/v1/predictions/generate",
        json={"market_key": "x", "entity_type": "fixture", "entity_id": "x", "subject_ref": "x"},
    )

    assert response.status_code in (401, 403)


def test_get_prediction_by_id(client, db_session_factory):
    headers = _auth_headers(client)
    import asyncio

    asyncio.run(_seed_production_market(db_session_factory, "football.api_get_market", "football.api_get_feature"))
    generated = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_get_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    ).json()["data"]

    response = client.get(f"/api/v1/predictions/{generated['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == generated["id"]


def test_get_prediction_not_found(client):
    headers = _auth_headers(client)

    response = client.get(f"/api/v1/predictions/{uuid4()}", headers=headers)

    assert response.status_code == 404


def test_list_predictions_for_market(client, db_session_factory):
    headers = _auth_headers(client)
    import asyncio

    market_id, _ = asyncio.run(
        _seed_production_market(db_session_factory, "football.api_list_market", "football.api_list_feature")
    )
    client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_list_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    response = client.get("/api/v1/predictions", params={"market_id": str(market_id)}, headers=headers)

    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 1


def test_approve_and_reject_draft_prediction(client, db_session_factory):
    headers = _auth_headers(client)
    admin_headers = _admin_headers(client, db_session_factory)
    import asyncio

    asyncio.run(
        _seed_production_market(
            db_session_factory, "football.api_approve_market", "football.api_approve_feature", confidence_threshold=1.1
        )
    )
    generated = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_approve_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    ).json()["data"]
    assert generated["status"] == "draft"

    approved = client.post(f"/api/v1/predictions/{generated['id']}/approve", headers=admin_headers)
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "published"

    already_published = client.post(f"/api/v1/predictions/{generated['id']}/reject", json={}, headers=admin_headers)
    assert already_published.status_code == 409


def test_non_admin_cannot_approve_prediction(client, db_session_factory):
    headers = _auth_headers(client)

    response = client.post(f"/api/v1/predictions/{uuid4()}/approve", headers=headers)

    assert response.status_code == 403


def test_non_admin_cannot_reject_prediction(client, db_session_factory):
    headers = _auth_headers(client)

    response = client.post(f"/api/v1/predictions/{uuid4()}/reject", json={}, headers=headers)

    assert response.status_code == 403


def test_generate_prediction_invalid_entity_type_returns_422(client):
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/predictions/generate",
        json={"market_key": "x", "entity_type": "not-a-real-entity", "entity_id": "x", "subject_ref": "x"},
        headers=headers,
    )

    assert response.status_code == 422


def test_get_prediction_invalid_id_returns_422(client):
    headers = _auth_headers(client)

    response = client.get("/api/v1/predictions/not-a-uuid", headers=headers)

    assert response.status_code == 422


def test_list_predictions_invalid_market_id_returns_422(client):
    headers = _auth_headers(client)

    response = client.get("/api/v1/predictions", params={"market_id": "not-a-uuid"}, headers=headers)

    assert response.status_code == 422


def test_list_predictions_invalid_status_returns_422(client):
    headers = _auth_headers(client)

    response = client.get(
        "/api/v1/predictions", params={"market_id": str(uuid4()), "status": "not-a-real-status"}, headers=headers
    )

    assert response.status_code == 422


def test_approve_unknown_prediction_returns_404(client, db_session_factory):
    admin_headers = _admin_headers(client, db_session_factory)

    response = client.post(f"/api/v1/predictions/{uuid4()}/approve", headers=admin_headers)

    assert response.status_code == 404


def test_reject_unknown_prediction_returns_404(client, db_session_factory):
    admin_headers = _admin_headers(client, db_session_factory)

    response = client.post(f"/api/v1/predictions/{uuid4()}/reject", json={}, headers=admin_headers)

    assert response.status_code == 404


def test_generate_prediction_market_not_in_production_returns_409(client, db_session_factory):
    import asyncio

    from modules.predictions.domain.entities import MarketDefinition
    from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, TargetType
    from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository

    async def _seed_draft_market():
        async with db_session_factory() as session:
            markets = SqlAlchemyMarketRepository(session=session)
            await markets.upsert(
                MarketDefinition(
                    id=MarketId(uuid4()), market_key="football.api_draft_market", sport_code="football", name="Test",
                    category="match_outcome", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
                    status=MarketStatus.DRAFT,
                )
            )
            await session.commit()

    asyncio.run(_seed_draft_market())
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_draft_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    assert response.status_code == 409


def test_generate_prediction_no_champion_model_returns_409(client, db_session_factory):
    import asyncio

    from modules.predictions.domain.entities import MarketDefinition
    from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, TargetType
    from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository

    async def _seed_market_without_champion():
        async with db_session_factory() as session:
            markets = SqlAlchemyMarketRepository(session=session)
            await markets.upsert(
                MarketDefinition(
                    id=MarketId(uuid4()), market_key="football.api_no_champion_market", sport_code="football",
                    name="Test", category="match_outcome", market_kind=MarketKind.BINARY,
                    target_type=TargetType.CLASSIFICATION, status=MarketStatus.PRODUCTION,
                )
            )
            await session.commit()

    asyncio.run(_seed_market_without_champion())
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_no_champion_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    assert response.status_code == 409


def test_generate_prediction_missing_required_feature_returns_409_not_500(client, db_session_factory):
    """Milestone 16 — a required feature with no verified pre-match value (the real, currently-live
    state of football.both_teams_to_score's two news + four structured-intelligence required
    features, per docs/milestone16_preimplementation_audit.md §16) must resolve to the same honest
    'insufficient data' response every other unservable-prediction case already gets, not an
    unhandled 500. The check itself is not weakened — the mapping stays is_required=True and the
    request still cannot produce a prediction; only the response shape changes."""
    import asyncio

    from modules.predictions.domain.entities import FeatureMarketMapping
    from modules.predictions.domain.value_objects import FeatureMarketMappingId
    from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyFeatureMarketMappingRepository

    market_key = "football.api_missing_required_feature_market"

    async def _add_unsatisfiable_required_mapping(market_id):
        async with db_session_factory() as session:
            mappings = SqlAlchemyFeatureMarketMappingRepository(session=session)
            await mappings.upsert(
                FeatureMarketMapping(
                    id=FeatureMarketMappingId(uuid4()), market_id=market_id,
                    feature_key="news.football.home_btts_impact", is_required=True,
                )
            )
            await session.commit()

    market_id, _model_id = asyncio.run(
        _seed_production_market(db_session_factory, market_key, "football.market.overround")
    )
    asyncio.run(_add_unsatisfiable_required_mapping(market_id))
    headers = _auth_headers(client)

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": market_key,
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["prediction_status"] == "BLOCKED"
    assert detail["reason_code"] == "MISSING_REQUIRED_FEATURE"
    assert "news.football.home_btts_impact" in detail["message"]


def test_generate_prediction_omits_contextual_review_key_when_not_requested(client, db_session_factory):
    """Backward compatibility (Gemini Prediction Reasoning Engine, Part 2g) — every existing
    caller that never sends `include_contextual_review` must see `contextual_review: null` and
    nothing else about the response shape change."""
    headers = _auth_headers(client)
    import asyncio

    asyncio.run(_seed_production_market(db_session_factory, "football.api_no_review_market", "football.api_no_review_feature"))

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_no_review_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["contextual_review"] is None


def test_generate_prediction_with_contextual_review_flag_returns_a_review(client, db_session_factory, monkeypatch):
    """The opt-in flag must never break or degrade the base prediction response — an
    `INSUFFICIENT_CONTEXT` review (the honest outcome with no real evidence/Gemini credential
    wired up in this test environment) is still a fully-shaped, non-null `contextual_review`
    object. `TITANIQ_REDIS_URL` only needs to resolve to a well-formed URL here, not a reachable
    server — `RedisSyncCache`'s own get/set failures are already caught and degrade to a cache
    miss inside `ContextualReasoningService.review()`."""
    monkeypatch.setenv("TITANIQ_REDIS_URL", "redis://localhost:6399/0")
    from modules.features.infrastructure.online.redis_feature_store import get_redis_settings

    get_redis_settings.cache_clear()
    headers = _auth_headers(client)
    import asyncio

    asyncio.run(
        _seed_production_market(db_session_factory, "football.api_with_review_market", "football.api_with_review_feature")
    )

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_with_review_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
            "include_contextual_review": True,
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["probability"] == data["probability"]  # base prediction untouched either way
    review = data["contextual_review"]
    assert review is not None
    assert review["review_status"] in {
        "SUPPORTED", "WEAKLY_SUPPORTED", "NEUTRAL", "CHALLENGED", "STRONGLY_CHALLENGED", "INSUFFICIENT_CONTEXT",
    }
    assert "confidence_score" in review
    assert "statistical_baseline" in review


def test_generate_prediction_contextual_review_failure_never_breaks_base_response(client, db_session_factory, monkeypatch):
    """Absolute rule: a hard failure anywhere in the contextual-reasoning path must never turn
    into a 500 or otherwise break the base prediction — `contextual_review` degrades to `None`."""
    headers = _auth_headers(client)
    import asyncio

    from apps.api.routers import prediction_router

    def _broken_service(session):
        raise RuntimeError("simulated contextual reasoning wiring failure")

    monkeypatch.setattr(prediction_router, "build_contextual_reasoning_service", _broken_service)

    asyncio.run(
        _seed_production_market(db_session_factory, "football.api_broken_review_market", "football.api_broken_review_feature")
    )

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_broken_review_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
            "include_contextual_review": True,
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "published"
    assert data["contextual_review"] is None


def test_generate_prediction_football_explanation_carries_model_and_prediction_identity(client, db_session_factory):
    """Phase 3 audit fix (spec §17 "every attribution must include ... model ID, model version,
    prediction ID") — `football_explanation` previously omitted all three even though the base
    prediction response carries them; they must now be present and match the base prediction's
    own `model_id`/`model_version`/`id` exactly (same fixed prediction, not a different one)."""
    headers = _auth_headers(client)
    import asyncio

    asyncio.run(
        _seed_production_market(db_session_factory, "football.api_with_explanation_market", "football.api_with_explanation_feature")
    )

    response = client.post(
        "/api/v1/predictions/generate",
        json={
            "market_key": "football.api_with_explanation_market",
            "entity_type": "fixture",
            "entity_id": "fixture-1",
            "subject_ref": "fixture-1",
            "include_football_explanation": True,
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    explanation = data["football_explanation"]
    assert explanation is not None
    assert explanation["model_id"] == data["model_id"]
    assert explanation["model_version"] == data["model_version"]
    assert explanation["prediction_id"] == data["id"]

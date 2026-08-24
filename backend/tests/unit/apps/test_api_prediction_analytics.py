from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

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
from modules.sports.domain.entities import Fixture
from modules.sports.domain.value_objects import FixtureId, FixtureStatus, SeasonId, TeamId
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.sports.infrastructure.persistence.repositories import SqlAlchemyFixtureRepository

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

    # Same pattern as test_api_ingestion.py's `client` fixture — see test_api_predictions.py's
    # identical fixture for the full rationale (build_prediction_cache_service's composition
    # chain reaches get_redis_client(), which is @lru_cache'd process-wide).
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


def _auth_headers(client, email="analytics@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _admin_headers(client, db_session_factory, email="analytics-admin@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})

    async def _promote():
        async with db_session_factory() as session:
            users = SqlAlchemyUserRepository(session=session)
            user = await users.get_by_email(Email(email))
            user.role = Role.ADMINISTRATOR
            await users.upsert(user)
            await session.commit()

    asyncio.run(_promote())
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


async def _seed_fixture(db_session_factory, fixture_id: str, *, scheduled_at: datetime, status: FixtureStatus = FixtureStatus.SCHEDULED):
    """A real Fixture row for ai_picks' upcoming/live filter (audit fix 2026-08-24) to check
    against. season_id/home_team_id/away_team_id are random UUIDs with no backing row — this
    suite's SQLite engine never enables foreign-key enforcement, and ai_picks only ever reads
    `status`/`scheduled_at`, so a real Season/Team isn't needed to exercise that check honestly."""
    async with db_session_factory() as session:
        await SqlAlchemyFixtureRepository(session=session).upsert(
            Fixture(
                id=FixtureId(UUID(fixture_id)),
                season_id=SeasonId(uuid4()), home_team_id=TeamId(uuid4()), away_team_id=TeamId(uuid4()),
                venue_id=None, scheduled_at=scheduled_at, status=status,
            )
        )
        await session.commit()


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


async def _resolve_outcome(db_session_factory, fixture_id, home_score, away_score):
    from apps.api.composition import build_outcome_resolution_service

    async with db_session_factory() as session:
        service = build_outcome_resolution_service(session)
        recorded = await service.resolve_for_fixture(fixture_id, home_score=home_score, away_score=away_score, now=T0)
        await session.commit()
        return recorded


def test_fixture_review_reports_predicted_vs_actual(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.both_teams_to_score", "football.analytics_feature_review")
    )
    _generate(client, headers, "football.both_teams_to_score", subject_ref="fixture-review")
    asyncio.run(_resolve_outcome(db_session_factory, "fixture-review", home_score=2, away_score=1))

    response = client.get("/api/v1/predictions/review/fixture-review", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["market_key"] == "football.both_teams_to_score"
    assert data[0]["actual_value"] == "YES"
    assert data[0]["is_correct"] in (True, False)
    meta = response.json()["meta"]
    assert meta["market_count"] == 1
    assert meta["resolved_count"] == 1
    assert meta["accuracy"] in (0.0, 1.0)


def test_fixture_review_reports_unresolved_market_as_none(client, db_session_factory):
    headers = _auth_headers(client)
    # first_half_goals has a real resolver (post-M24) but no fixture completion/outcome
    # resolution ever runs in this test — no PredictionOutcome exists, so review must report
    # unresolved honestly rather than guessing.
    asyncio.run(
        _seed_production_market(db_session_factory, "football.first_half_goals", "football.analytics_feature_unresolved")
    )
    _generate(client, headers, "football.first_half_goals", subject_ref="fixture-unresolved")

    response = client.get("/api/v1/predictions/review/fixture-unresolved", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["actual_value"] is None
    assert data[0]["is_correct"] is None
    meta = response.json()["meta"]
    assert meta["resolved_count"] == 0
    assert meta["accuracy"] is None


def test_review_route_is_not_shadowed_by_prediction_id_route(client):
    headers = _auth_headers(client)

    response = client.get("/api/v1/predictions/review/unknown-fixture", headers=headers)

    # A 422 (invalid prediction_id UUID) would mean the generic /{prediction_id} route
    # swallowed this request instead of the literal /review/{fixture_id} route.
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
    fixture_id = str(uuid4())
    asyncio.run(_seed_fixture(db_session_factory, fixture_id, scheduled_at=datetime.now(timezone.utc) + timedelta(days=3)))
    prediction = _generate(client, headers, "football.picks_market", subject_ref=fixture_id)

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
    assert pick["ai_explanation"] == prediction["explanation"]["ai_explanation"]


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
    # Basketball is gated to administrators only (still under active development — see
    # sports_router.require_football_or_admin and prediction_analytics_router._visible_to), so
    # this exercises the sport_code filter as an admin, the only role that can see a basketball pick.
    headers = _admin_headers(client, db_session_factory)
    asyncio.run(
        _seed_production_market(
            db_session_factory, "basketball.picks_market", "basketball.picks_feature_a", sport_code="basketball"
        )
    )
    fixture_id = str(uuid4())
    asyncio.run(_seed_fixture(db_session_factory, fixture_id, scheduled_at=datetime.now(timezone.utc) + timedelta(days=3)))
    _generate(client, headers, "basketball.picks_market", subject_ref=fixture_id)

    football_picks = client.get("/api/v1/predictions/picks", params={"sport_code": "football"}, headers=headers)
    basketball_picks = client.get("/api/v1/predictions/picks", params={"sport_code": "basketball"}, headers=headers)

    assert football_picks.json()["data"] == []
    assert len(basketball_picks.json()["data"]) == 1
    assert basketball_picks.json()["data"][0]["sport_code"] == "basketball"


def test_ai_picks_hides_non_football_sports_from_regular_users(client, db_session_factory):
    admin_headers = _admin_headers(client, db_session_factory)
    asyncio.run(
        _seed_production_market(
            db_session_factory, "basketball.regular_user_picks_market", "basketball.regular_user_picks_feature", sport_code="basketball"
        )
    )
    fixture_id = str(uuid4())
    asyncio.run(_seed_fixture(db_session_factory, fixture_id, scheduled_at=datetime.now(timezone.utc) + timedelta(days=3)))
    _generate(client, admin_headers, "basketball.regular_user_picks_market", subject_ref=fixture_id)

    regular_headers = _auth_headers(client, email="picks-regular-user@titaniq.test")
    basketball_picks = client.get("/api/v1/predictions/picks", params={"sport_code": "basketball"}, headers=regular_headers)

    assert basketball_picks.json()["data"] == []


def test_ai_picks_excludes_completed_fixtures(client, db_session_factory):
    """The real bug this fix closes (2026-08-24): a real production example — Hull City AFC vs
    Manchester United — kept showing up in "Priority intelligence" well after football-data.org
    reported it FINISHED and TitanIQ marked it COMPLETED, because this feed never re-checked
    fixture status at all. A PUBLISHED prediction on a completed fixture is no longer a "priority
    pick" — its outcome is already known."""
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.picks_completed_market", "football.picks_feature_e")
    )
    fixture_id = str(uuid4())
    asyncio.run(
        _seed_fixture(
            db_session_factory, fixture_id,
            scheduled_at=datetime.now(timezone.utc) - timedelta(days=1), status=FixtureStatus.COMPLETED,
        )
    )
    _generate(client, headers, "football.picks_completed_market", subject_ref=fixture_id)

    response = client.get("/api/v1/predictions/picks", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_ai_picks_excludes_a_scheduled_fixture_whose_kickoff_has_already_passed(client, db_session_factory):
    """Same class of bug the landing page's featured_intelligence already guards against: a
    fixture stuck at 'scheduled' status past its real kickoff (a sync-job lag, not a genuinely
    upcoming match) must not be trusted as a live "priority pick" either."""
    headers = _auth_headers(client)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.picks_stale_market", "football.picks_feature_f")
    )
    fixture_id = str(uuid4())
    asyncio.run(
        _seed_fixture(
            db_session_factory, fixture_id,
            scheduled_at=datetime.now(timezone.utc) - timedelta(hours=2), status=FixtureStatus.SCHEDULED,
        )
    )
    _generate(client, headers, "football.picks_stale_market", subject_ref=fixture_id)

    response = client.get("/api/v1/predictions/picks", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_ai_picks_includes_a_live_fixture(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(_seed_production_market(db_session_factory, "football.picks_live_market", "football.picks_feature_g"))
    fixture_id = str(uuid4())
    asyncio.run(
        _seed_fixture(
            db_session_factory, fixture_id,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=30), status=FixtureStatus.LIVE,
        )
    )
    _generate(client, headers, "football.picks_live_market", subject_ref=fixture_id)

    response = client.get("/api/v1/predictions/picks", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_ai_picks_respects_limit(client, db_session_factory):
    headers = _auth_headers(client)
    asyncio.run(_seed_production_market(db_session_factory, "football.picks_limit_a", "football.picks_feature_c"))
    asyncio.run(_seed_production_market(db_session_factory, "football.picks_limit_b", "football.picks_feature_d"))
    fixture_a, fixture_b = str(uuid4()), str(uuid4())
    now = datetime.now(timezone.utc)
    asyncio.run(_seed_fixture(db_session_factory, fixture_a, scheduled_at=now + timedelta(days=3)))
    asyncio.run(_seed_fixture(db_session_factory, fixture_b, scheduled_at=now + timedelta(days=4)))
    _generate(client, headers, "football.picks_limit_a", subject_ref=fixture_a)
    _generate(client, headers, "football.picks_limit_b", subject_ref=fixture_b)

    response = client.get("/api/v1/predictions/picks", params={"limit": 1}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1

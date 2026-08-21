import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import fakeredis
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import apps.api.composition as composition
import apps.api.main as main_module
from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from apps.api.routers import public_router
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
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
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
from modules.sports.domain.entities import Competition, Fixture, Season, Sport, Team
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    DateRange,
    FixtureId,
    FixtureStatus,
    SeasonId,
    SeasonStatus,
    SportCode,
    SportId,
    TeamId,
)
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyTeamRepository,
)

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
                "ingestion": None,
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
        await conn.run_sync(IngestionBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory, monkeypatch):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    from cryptography.fernet import Fernet

    from modules.admin.infrastructure.vault import get_vault_settings

    # news-intelligence resolves a real/mock text-intelligence provider via
    # build_provider_management_service, which eagerly constructs a FernetCredentialVault() —
    # needs a real key present even though this test suite never stores a real credential.
    monkeypatch.setenv("TITANIQ_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_vault_settings.cache_clear()

    # platform-summary/featured-intelligence go through build_prediction_cache_service's
    # composition chain, which reaches get_redis_client() — @lru_cache'd process-wide, so this
    # must be patched the same way test_api_ingestion.py's `client` fixture already does it.
    fake_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    composition.get_redis_client.cache_clear()
    composition.get_redis_lock.cache_clear()
    composition.get_redis_sync_cache.cache_clear()
    monkeypatch.setattr(composition, "get_redis_client", lambda: fake_client)
    monkeypatch.setattr(main_module, "get_redis_client", lambda: fake_client)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_public_router_cache():
    # public_router._cache is a module-scoped global (see its own docstring) — it must not leak
    # state between tests (or between this test module and any other test hitting the same routes
    # within the 60s TTL window a single pytest process runs in).
    public_router._cache.clear()
    yield
    public_router._cache.clear()


def _auth_headers(client, email="public-router@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def _seed_production_market(
    db_session_factory,
    market_key: str,
    feature_key: str,
    subject_ref: str,
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
                entity_id=subject_ref,
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


def _generate(client, headers, market_key, subject_ref):
    response = client.post(
        "/api/v1/predictions/generate",
        json={"market_key": market_key, "entity_type": "fixture", "entity_id": subject_ref, "subject_ref": subject_ref},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest_asyncio.fixture
async def seeded_fixture(db_session_factory):
    async with db_session_factory() as session:
        sport = await SqlAlchemySportRepository(session=session).upsert(
            Sport(id=SportId(uuid.uuid4()), code=SportCode.FOOTBALL, name="Football")
        )
        home = await SqlAlchemyTeamRepository(session=session).upsert(
            Team(id=TeamId(uuid.uuid4()), sport_id=sport.id, name="Everton FC", short_name="EVE", country="England")
        )
        away = await SqlAlchemyTeamRepository(session=session).upsert(
            Team(id=TeamId(uuid.uuid4()), sport_id=sport.id, name="Arsenal FC", short_name="ARS", country="England")
        )
        competition = await SqlAlchemyCompetitionRepository(session=session).upsert(
            Competition(
                id=CompetitionId(uuid.uuid4()), sport_id=sport.id, name="Premier League",
                type=CompetitionType.LEAGUE, country="England", tier=1,
            )
        )
        season = await SqlAlchemySeasonRepository(session=session).upsert(
            Season(
                id=SeasonId(uuid.uuid4()), competition_id=competition.id, label="2025/26",
                date_range=DateRange(start=T0 - timedelta(days=300), end=T0 + timedelta(days=60)),
                status=SeasonStatus.ACTIVE,
            )
        )
        fixture = await SqlAlchemyFixtureRepository(session=session).upsert(
            Fixture(
                id=FixtureId(uuid.uuid4()), season_id=season.id, home_team_id=home.id, away_team_id=away.id,
                venue_id=None, scheduled_at=T0 + timedelta(days=3), status=FixtureStatus.SCHEDULED,
            )
        )
        await session.commit()
        return {"sport": sport, "home": home, "away": away, "competition": competition, "season": season, "fixture": fixture}


# -- No-auth-required smoke tests -----------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/v1/public/platform-summary", "/api/v1/public/featured-intelligence", "/api/v1/public/news-intelligence", "/api/v1/public/knowledge-graph-preview"],
)
def test_public_endpoints_return_200_without_auth(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["error"] is None


# -- Honest empty state -----------------------------------------------------------------------------


def test_platform_summary_honest_empty_state(client):
    response = client.get("/api/v1/public/platform-summary")
    data = response.json()["data"]

    assert data["sports_covered"] == 4
    assert len(data["sports"]) == 4
    assert data["competitions_tracked"] == 0
    assert data["live_fixtures"] == 0
    assert data["today_fixtures"] == 0
    assert data["completed_fixtures_recent"] == 0
    assert data["published_predictions_sample"] == 0
    assert data["published_predictions_sample_size"] == 0
    assert data["knowledge_graph"] == {"node_count": 0, "edge_count": 0}
    assert data["last_synced_at"] is None


def test_featured_and_news_intelligence_empty_lists(client):
    featured = client.get("/api/v1/public/featured-intelligence")
    news = client.get("/api/v1/public/news-intelligence")

    assert featured.json()["data"] == []
    assert news.json()["data"] == []


def test_knowledge_graph_preview_empty_state(client):
    response = client.get("/api/v1/public/knowledge-graph-preview")
    data = response.json()["data"]

    assert data["node_count"] == 0
    assert data["edge_count"] == 0
    assert data["preview_entity"] is None


# -- Positive path: real published prediction resolves to real team/competition data ----------------


def test_featured_intelligence_resolves_real_published_prediction(client, db_session_factory, seeded_fixture):
    headers = _auth_headers(client)
    subject_ref = str(seeded_fixture["fixture"].id)
    asyncio.run(
        _seed_production_market(db_session_factory, "football.public_router_market", "football.public_router_feature", subject_ref)
    )
    prediction = _generate(client, headers, "football.public_router_market", subject_ref)
    assert prediction["status"] == "published"

    response = client.get("/api/v1/public/featured-intelligence")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    pick = data[0]
    assert pick["prediction_id"] == prediction["id"]
    assert pick["fixture_id"] == subject_ref
    assert pick["sport_code"] == "football"
    assert pick["competition_name"] == "Premier League"
    assert pick["home_team"] == {"name": "Everton FC", "short_name": "EVE", "logo_url": None}
    assert pick["away_team"] == {"name": "Arsenal FC", "short_name": "ARS", "logo_url": None}
    assert pick["market_key"] == "football.public_router_market"
    assert pick["value"] == prediction["value"]
    assert pick["confidence_composite"] == prediction["confidence"]["composite"]


def test_featured_intelligence_caps_one_pick_per_market(client, db_session_factory, seeded_fixture):
    """Two fixtures both get a `football.public_router_market` prediction (one would naturally rank
    above the other by confidence) plus one on a second market. The diversified carousel must show
    at most one pick per market_key — never the same market repeated across every slot."""
    headers = _auth_headers(client)
    subject_ref_a = str(seeded_fixture["fixture"].id)

    async def _second_fixture():
        async with db_session_factory() as session:
            season = seeded_fixture["season"]
            home, away = seeded_fixture["home"], seeded_fixture["away"]
            fixture = await SqlAlchemyFixtureRepository(session=session).upsert(
                Fixture(
                    id=FixtureId(uuid.uuid4()), season_id=season.id, home_team_id=away.id, away_team_id=home.id,
                    venue_id=None, scheduled_at=T0 + timedelta(days=4), status=FixtureStatus.SCHEDULED,
                )
            )
            await session.commit()
            return str(fixture.id)

    subject_ref_b = asyncio.run(_second_fixture())

    async def _seed_feature_value(feature_key, subject_ref):
        async with db_session_factory() as session:
            await SqlAlchemyFeatureValueRepository(session=session).record(
                FeatureValue(
                    id=FeatureValueId(uuid4()), feature_key=FeatureKey(feature_key), entity_type=EntityType.FIXTURE,
                    entity_id=subject_ref, as_of=T0, value=0.8, quality_flags=(QualityFlag.OK,),
                )
            )
            await session.commit()

    asyncio.run(
        _seed_production_market(db_session_factory, "football.diversity_market_a", "football.diversity_feature_a", subject_ref_a)
    )
    asyncio.run(_seed_feature_value("football.diversity_feature_a", subject_ref_b))
    asyncio.run(
        _seed_production_market(db_session_factory, "football.diversity_market_b", "football.diversity_feature_b", subject_ref_a)
    )
    _generate(client, headers, "football.diversity_market_a", subject_ref_a)
    _generate(client, headers, "football.diversity_market_a", subject_ref_b)
    _generate(client, headers, "football.diversity_market_b", subject_ref_a)

    response = client.get("/api/v1/public/featured-intelligence", params={"limit": 6})
    assert response.status_code == 200
    data = response.json()["data"]

    market_keys = [pick["market_key"] for pick in data]
    assert len(market_keys) == len(set(market_keys)), f"expected no duplicate markets, got {market_keys}"
    assert set(market_keys) == {"football.diversity_market_a", "football.diversity_market_b"}


def test_platform_summary_reflects_seeded_competition(client, seeded_fixture):
    response = client.get("/api/v1/public/platform-summary")
    data = response.json()["data"]

    assert data["competitions_tracked"] == 1
    football = next(s for s in data["sports"] if s["code"] == "football")
    assert football["competitions"] == 1

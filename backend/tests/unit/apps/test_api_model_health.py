import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session, get_model_artifact_store
from apps.api.main import app
from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    ModelStatus,
    TargetType,
)
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
)
from modules.sports.infrastructure.persistence.database import get_database_settings


@pytest.fixture(autouse=True)
def _real_db_url_for_display_only(monkeypatch):
    monkeypatch.setenv("TITANIQ_DB_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.delenv("TITANIQ_SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_database_settings.cache_clear()
    get_model_artifact_store.cache_clear()
    yield
    get_database_settings.cache_clear()
    get_model_artifact_store.cache_clear()


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"admin": None, "identity": None, "predictions": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(AdminBase.metadata.create_all)
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(PredictionsBase.metadata.create_all)

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
    email, password = "model-health-admin@titaniq.test", "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    yield test_client
    app.dependency_overrides.clear()


def test_requires_authentication(client):
    del client.headers["Authorization"]
    response = client.get("/api/v1/admin/system/model-health")
    assert response.status_code in (401, 403)


def test_market_with_no_champion_is_reported_honestly(client, db_session_factory):
    async def seed():
        async with db_session_factory() as session:
            markets = SqlAlchemyMarketRepository(session=session)
            await markets.upsert(
                MarketDefinition(
                    id=MarketId(uuid4()), market_key="football.no_champion_market", sport_code="football",
                    name="Test", category="goals", market_kind=MarketKind.BINARY,
                    target_type=TargetType.CLASSIFICATION, status=MarketStatus.PRODUCTION,
                )
            )
            await session.commit()

    asyncio.run(seed())

    response = client.get("/api/v1/admin/system/model-health")

    assert response.status_code == 200
    data = response.json()["data"]
    entry = next(c for c in data["champions"] if c["market_key"] == "football.no_champion_market")
    assert entry["status"] == "NO_CHAMPION"
    assert data["summary"]["NO_CHAMPION"] >= 1


def test_placeholder_champion_is_invalid_not_healthy(client, db_session_factory):
    async def seed():
        async with db_session_factory() as session:
            markets = SqlAlchemyMarketRepository(session=session)
            models = SqlAlchemyModelRepository(session=session)
            market = await markets.upsert(
                MarketDefinition(
                    id=MarketId(uuid4()), market_key="football.placeholder_market", sport_code="football",
                    name="Test", category="goals", market_kind=MarketKind.BINARY,
                    target_type=TargetType.CLASSIFICATION, status=MarketStatus.PRODUCTION,
                )
            )
            await models.upsert(
                ModelDefinition(
                    id=ModelId(uuid4()), market_id=market.id, model_key="football.placeholder_market.heuristic",
                    version=1, algorithm="heuristic_logistic_v1", status=ModelStatus.CHAMPION,
                    artifact_ref=None,
                )
            )
            await session.commit()

    asyncio.run(seed())

    response = client.get("/api/v1/admin/system/model-health")

    assert response.status_code == 200
    data = response.json()["data"]
    entry = next(c for c in data["champions"] if c["market_key"] == "football.placeholder_market")
    assert entry["status"] == "INVALID_CHAMPION"


def test_champion_with_no_real_artifact_is_not_reported_healthy(client, db_session_factory):
    """`artifact_ref` points nowhere real — a genuine missing-model condition (the exact class of
    real production incident this endpoint exists to catch). Never asserts the precise failure
    category (LEGACY_LOCAL_ONLY vs MISSING_ARTIFACT depends on which artifact store this process
    resolves to), only that a nonexistent artifact is never reported HEALTHY."""

    async def seed():
        async with db_session_factory() as session:
            markets = SqlAlchemyMarketRepository(session=session)
            models = SqlAlchemyModelRepository(session=session)
            market = await markets.upsert(
                MarketDefinition(
                    id=MarketId(uuid4()), market_key="football.broken_market", sport_code="football",
                    name="Test", category="goals", market_kind=MarketKind.BINARY,
                    target_type=TargetType.CLASSIFICATION, status=MarketStatus.PRODUCTION,
                )
            )
            await models.upsert(
                ModelDefinition(
                    id=ModelId(uuid4()), market_id=market.id, model_key="football.broken_market.logistic_regression",
                    version=1, algorithm="logistic_regression", framework="sklearn", status=ModelStatus.CHAMPION,
                    artifact_ref="football.broken_market.logistic_regression/v1.bin",
                )
            )
            await session.commit()

    asyncio.run(seed())

    response = client.get("/api/v1/admin/system/model-health")

    assert response.status_code == 200
    data = response.json()["data"]
    entry = next(c for c in data["champions"] if c["market_key"] == "football.broken_market")
    assert entry["status"] != "HEALTHY"
    assert "error" in entry

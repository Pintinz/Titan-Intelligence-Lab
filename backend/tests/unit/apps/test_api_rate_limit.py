import fakeredis
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import apps.api.rate_limit as rate_limit_module
from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory, monkeypatch):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(rate_limit_module, "get_redis_client", lambda: fake_redis)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_is_rate_limited_after_repeated_attempts(client):
    client.post("/api/v1/auth/register", json={"email": "ratelimit-login@example.com", "password": "correct-horse-battery"})

    responses = [
        client.post("/api/v1/auth/login", json={"email": "ratelimit-login@example.com", "password": "wrong"})
        for _ in range(11)
    ]

    assert responses[-1].status_code == 429
    assert any(r.status_code == 401 for r in responses[:10])


def test_registration_is_rate_limited_after_repeated_attempts(client):
    responses = [
        client.post("/api/v1/auth/register", json={"email": f"ratelimit-reg-{i}@example.com", "password": "correct-horse-battery"})
        for i in range(6)
    ]

    assert responses[-1].status_code == 429
    assert all(r.status_code == 200 for r in responses[:5])


def test_rate_limit_is_per_endpoint_bucket(client):
    # Exhausting the login bucket must not affect registration's separate bucket.
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"email": "unrelated@example.com", "password": "wrong"})

    register = client.post(
        "/api/v1/auth/register", json={"email": "not-rate-limited@example.com", "password": "correct-horse-battery"}
    )

    assert register.status_code == 200

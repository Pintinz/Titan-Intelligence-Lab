import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.alerts.infrastructure.persistence.models import Base as AlertsBase
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator
from modules.watchlist.infrastructure.persistence.models import Base as WatchlistBase


@pytest.fixture
def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "watchlist": None, "alerts": None}},
    )

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(IdentityBase.metadata.create_all)
            await conn.run_sync(WatchlistBase.metadata.create_all)
            await conn.run_sync(AlertsBase.metadata.create_all)

    asyncio.run(_setup())

    yield async_sessionmaker(engine, expire_on_commit=False)


def _make_client(db_session_factory, email):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    test_client = TestClient(app)
    password = "correct-horse-battery"
    test_client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = test_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    test_client.headers["Authorization"] = f"Bearer {login.json()['data']['access_token']}"
    return test_client


@pytest.fixture
def client(db_session_factory):
    c = _make_client(db_session_factory, "alerts-user@titaniq.test")
    yield c
    app.dependency_overrides.clear()


def test_list_starts_empty(client):
    response = client.get("/api/v1/alerts")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_unread_count_starts_zero(client):
    response = client.get("/api/v1/alerts/unread-count")

    assert response.status_code == 200
    assert response.json()["data"]["count"] == 0


def test_follow_then_kickoff_produces_an_alert(client, db_session_factory):
    """Full stack proof: follow a fixture through the real Watchlist endpoint, fire a real
    kickoff alert through AlertService directly (the same call entity_reconciliation_service
    makes), and confirm it shows up through the real Alerts endpoint for that exact user."""
    follow = client.post("/api/v1/watchlist", json={"entity_type": "fixture", "entity_ref": "fx-alert-1"})
    assert follow.status_code == 200

    from datetime import datetime, timezone

    from modules.alerts.application.alert_service import AlertService
    from modules.alerts.domain.value_objects import AlertType
    from modules.alerts.infrastructure.persistence.repositories import SqlAlchemyAlertEventRepository
    from modules.watchlist.domain.value_objects import WatchlistEntityType
    from modules.watchlist.infrastructure.persistence.repositories import SqlAlchemyWatchlistRepository

    async def fire():
        async with db_session_factory() as session:
            alerts = AlertService(
                events=SqlAlchemyAlertEventRepository(session=session),
                watchlist=SqlAlchemyWatchlistRepository(session=session),
            )
            await alerts.notify_watchers(
                WatchlistEntityType.FIXTURE, "fx-alert-1", AlertType.KICKOFF, "Kickoff", "Match started",
                datetime.now(timezone.utc),
            )
            await session.commit()

    asyncio.run(fire())

    response = client.get("/api/v1/alerts")
    assert response.status_code == 200
    alerts_data = response.json()["data"]
    assert len(alerts_data) == 1
    assert alerts_data[0]["alert_type"] == "kickoff"
    assert alerts_data[0]["entity_ref"] == "fx-alert-1"

    unread = client.get("/api/v1/alerts/unread-count")
    assert unread.json()["data"]["count"] == 1


def test_mark_read_updates_unread_count(client, db_session_factory):
    client.post("/api/v1/watchlist", json={"entity_type": "fixture", "entity_ref": "fx-alert-2"})

    from datetime import datetime, timezone

    from modules.alerts.application.alert_service import AlertService
    from modules.alerts.domain.value_objects import AlertType
    from modules.alerts.infrastructure.persistence.repositories import SqlAlchemyAlertEventRepository
    from modules.watchlist.domain.value_objects import WatchlistEntityType
    from modules.watchlist.infrastructure.persistence.repositories import SqlAlchemyWatchlistRepository

    async def fire():
        async with db_session_factory() as session:
            alerts = AlertService(
                events=SqlAlchemyAlertEventRepository(session=session),
                watchlist=SqlAlchemyWatchlistRepository(session=session),
            )
            await alerts.notify_watchers(
                WatchlistEntityType.FIXTURE, "fx-alert-2", AlertType.FINAL_RESULT, "Full time", "Match ended",
                datetime.now(timezone.utc),
            )
            await session.commit()

    asyncio.run(fire())

    event_id = client.get("/api/v1/alerts").json()["data"][0]["id"]
    mark_response = client.post(f"/api/v1/alerts/{event_id}/read")

    assert mark_response.status_code == 200
    assert client.get("/api/v1/alerts/unread-count").json()["data"]["count"] == 0


def test_mark_unknown_alert_read_returns_404(client):
    from uuid import uuid4

    response = client.post(f"/api/v1/alerts/{uuid4()}/read")

    assert response.status_code == 404


def test_mark_alert_read_malformed_id_returns_422(client):
    response = client.post("/api/v1/alerts/not-a-uuid/read")

    assert response.status_code == 422


def test_alerts_requires_authentication(client):
    client.headers.pop("Authorization", None)

    response = client.get("/api/v1/alerts")

    assert response.status_code == 401


def test_cannot_mark_another_users_alert_read(client, db_session_factory):
    client.post("/api/v1/watchlist", json={"entity_type": "fixture", "entity_ref": "fx-alert-3"})

    from datetime import datetime, timezone

    from modules.alerts.application.alert_service import AlertService
    from modules.alerts.domain.value_objects import AlertType
    from modules.alerts.infrastructure.persistence.repositories import SqlAlchemyAlertEventRepository
    from modules.watchlist.domain.value_objects import WatchlistEntityType
    from modules.watchlist.infrastructure.persistence.repositories import SqlAlchemyWatchlistRepository

    async def fire():
        async with db_session_factory() as session:
            alerts = AlertService(
                events=SqlAlchemyAlertEventRepository(session=session),
                watchlist=SqlAlchemyWatchlistRepository(session=session),
            )
            await alerts.notify_watchers(
                WatchlistEntityType.FIXTURE, "fx-alert-3", AlertType.KICKOFF, "Kickoff", "Match started",
                datetime.now(timezone.utc),
            )
            await session.commit()

    asyncio.run(fire())
    event_id = client.get("/api/v1/alerts").json()["data"][0]["id"]

    other_client = _make_client(db_session_factory, "other-alerts-user@titaniq.test")
    response = other_client.post(f"/api/v1/alerts/{event_id}/read")

    assert response.status_code == 404
    assert client.get("/api/v1/alerts/unread-count").json()["data"]["count"] == 1

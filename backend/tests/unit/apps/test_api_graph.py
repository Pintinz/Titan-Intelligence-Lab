import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import build_kg_population_service, get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "knowledge_graph": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
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


def register_and_login(client, email, password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def seeded(db_session_factory):
    async with db_session_factory() as session:
        population = build_kg_population_service(session)
        team = await population.upsert_node(NodeType.TEAM, "liverpool", now=T0, attributes={"name": "Liverpool"})
        rival = await population.upsert_node(NodeType.TEAM, "everton", now=T0)
        player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
        await population.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
        await population.upsert_edge(team, rival, EdgeType.RIVAL_OF, T0, directed=False)
        await session.commit()
        return {"team": team, "rival": rival, "player": player}


@pytest.fixture
def auth_headers(client):
    token = register_and_login(client, "kg-user@example.com")
    return {"Authorization": f"Bearer {token}"}


def test_search_entities_by_type(client, seeded, auth_headers):
    response = client.get("/api/v1/graph/entities/team", headers=auth_headers)

    assert response.status_code == 200
    refs = {n["entity_ref"] for n in response.json()["data"]}
    assert refs == {"liverpool", "everton"}


def test_get_entity_by_ref(client, seeded, auth_headers):
    response = client.get("/api/v1/graph/entities/team/liverpool", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["attributes"]["name"] == "Liverpool"


def test_get_entity_not_found(client, seeded, auth_headers):
    response = client.get("/api/v1/graph/entities/team/nonexistent", headers=auth_headers)

    assert response.status_code == 404


def test_search_entities_rejects_unknown_node_type(client, auth_headers):
    response = client.get("/api/v1/graph/entities/not-a-real-type", headers=auth_headers)

    assert response.status_code == 422


def test_relationship_search(client, seeded, auth_headers):
    player, team = seeded["player"], seeded["team"]

    response = client.get(
        "/api/v1/graph/relationships", params={"from_id": str(player.id), "to_id": str(team.id)}, headers=auth_headers
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["edge_type"] == "plays_for"


def test_traverse(client, seeded, auth_headers):
    team = seeded["team"]

    response = client.get(
        "/api/v1/graph/traverse",
        params={"node_id": str(team.id), "edge_type": "plays_for", "reverse": True},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert {n["entity_ref"] for n in response.json()["data"]} == {"p1"}


def test_shortest_path(client, seeded, auth_headers):
    player, team = seeded["player"], seeded["team"]

    response = client.get(
        "/api/v1/graph/shortest-path", params={"from_id": str(player.id), "to_id": str(team.id)}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["meta"]["connected"] is True
    assert [n["entity_ref"] for n in response.json()["data"]] == ["p1", "liverpool"]


def test_shortest_path_no_route(client, seeded, auth_headers):
    response = client.get(
        "/api/v1/graph/shortest-path",
        params={"from_id": str(seeded["player"].id), "to_id": str(uuid.uuid4())},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["meta"]["connected"] is False


def test_timeline(client, seeded, auth_headers):
    player = seeded["player"]

    response = client.get(f"/api/v1/graph/timeline/{player.id}", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_at_time(client, seeded, auth_headers):
    player = seeded["player"]

    response = client.get(
        f"/api/v1/graph/at-time/{player.id}", params={"as_of": T0.isoformat()}, headers=auth_headers
    )

    assert response.status_code == 200
    assert len(response.json()["data"]["edges"]) == 1


def test_similar_entities(client, seeded, auth_headers):
    team = seeded["team"]

    response = client.get(
        "/api/v1/graph/similar/" + str(team.id), params={"node_type": "team"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_context(client, seeded, auth_headers):
    team = seeded["team"]

    response = client.get(f"/api/v1/graph/context/{team.id}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["subject"]["entity_ref"] == "liverpool"
    assert "team" in data["related_by_type"] or "player" in data["related_by_type"]


def test_context_not_found(client, auth_headers):
    response = client.get(f"/api/v1/graph/context/{uuid.uuid4()}", headers=auth_headers)

    assert response.status_code == 404


def test_neighborhood(client, seeded, auth_headers):
    team = seeded["team"]

    response = client.get(f"/api/v1/graph/neighborhood/{team.id}", headers=auth_headers)

    assert response.status_code == 200
    refs = {n["entity_ref"] for n in response.json()["data"]["nodes"]}
    assert "liverpool" in refs


def test_statistics(client, seeded, auth_headers):
    response = client.get("/api/v1/graph/statistics", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["node_count"] == 3
    assert data["edge_count"] == 2


def test_routes_require_authentication(client, seeded):
    response = client.get("/api/v1/graph/statistics")

    assert response.status_code == 401

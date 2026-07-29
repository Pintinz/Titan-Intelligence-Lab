from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import fakeredis
import pytest

from modules.ingestion.infrastructure.cache.redis_sync_cache import RedisSyncCache
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.infrastructure.caching.cached_node_repository import CachedKGNodeRepository
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.fixture
def redis_cache():
    return RedisSyncCache(client=fakeredis.FakeAsyncRedis(decode_responses=True))


def _cached_repo(sqlite_session, redis_cache):
    inner = SqlAlchemyKGNodeRepository(session=sqlite_session)
    return CachedKGNodeRepository(inner=inner, cache=redis_cache), inner


async def test_get_is_a_miss_then_a_hit(sqlite_session, redis_cache):
    inner_bare = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=inner_bare, edges=edges)
    node = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await sqlite_session.commit()

    cached, _ = _cached_repo(sqlite_session, redis_cache)

    first = await cached.get(node.id)
    second = await cached.get(node.id)

    assert first is not None and first.entity_ref == "t1"
    assert second is not None and second.entity_ref == "t1"
    assert cached.hits == 1
    assert cached.misses == 1
    assert cached.hit_ratio == 0.5


async def test_get_by_entity_ref_is_cached(sqlite_session, redis_cache):
    inner_bare = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=inner_bare, edges=edges)
    await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await sqlite_session.commit()

    cached, _ = _cached_repo(sqlite_session, redis_cache)

    await cached.get_by_entity_ref(NodeType.TEAM, "t1")
    await cached.get_by_entity_ref(NodeType.TEAM, "t1")

    assert cached.hits == 1
    assert cached.misses == 1


async def test_upsert_invalidates_cache(sqlite_session, redis_cache):
    cached, inner = _cached_repo(sqlite_session, redis_cache)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=cached, edges=edges)

    node = await population.upsert_node(NodeType.TEAM, "t1", now=T0, attributes={"name": "Original"})
    await sqlite_session.commit()
    await cached.get(node.id)  # populate cache
    await population.upsert_node(NodeType.TEAM, "t1", now=T0, attributes={"name": "Renamed"})
    await sqlite_session.commit()

    fetched = await cached.get(node.id)

    assert fetched.attributes["name"] == "Renamed"


async def test_missing_node_returns_none_and_counts_as_miss(sqlite_session, redis_cache):
    cached, _ = _cached_repo(sqlite_session, redis_cache)

    result = await cached.get(KGNodeId(uuid4()))

    assert result is None
    assert cached.misses == 1


async def test_hit_ratio_is_zero_with_no_activity(sqlite_session, redis_cache):
    cached, _ = _cached_repo(sqlite_session, redis_cache)

    assert cached.hit_ratio == 0.0


async def test_list_by_type_delegates_to_inner_uncached(sqlite_session, redis_cache):
    inner_bare = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=inner_bare, edges=edges)
    await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await sqlite_session.commit()

    cached, _ = _cached_repo(sqlite_session, redis_cache)

    teams = await cached.list_by_type(NodeType.TEAM)

    assert {t.entity_ref for t in teams} == {"t1"}

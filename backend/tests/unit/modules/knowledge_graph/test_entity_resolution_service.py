from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _services(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    resolution = EntityResolutionService(nodes=nodes, edges=edges, population=population)
    return resolution, population


async def test_find_by_provider_ref(sqlite_session):
    resolution, population = _services(sqlite_session)
    await population.upsert_node(NodeType.TEAM, "t1", now=T0, provider_refs={"api_football": "999"})
    await sqlite_session.commit()

    found = await resolution.find_by_provider_ref(NodeType.TEAM, "api_football", "999")

    assert found is not None
    assert found.entity_ref == "t1"


async def test_find_by_provider_ref_returns_none_when_absent(sqlite_session):
    resolution, _ = _services(sqlite_session)
    assert await resolution.find_by_provider_ref(NodeType.TEAM, "api_football", "unknown") is None


async def test_find_by_alias_case_insensitive(sqlite_session):
    resolution, population = _services(sqlite_session)
    await population.upsert_node(NodeType.TEAM, "t1", now=T0, aliases=["Man United", "MUFC"])
    await sqlite_session.commit()

    found = await resolution.find_by_alias(NodeType.TEAM, "mufc")

    assert len(found) == 1
    assert found[0].entity_ref == "t1"


async def test_detect_duplicates_by_shared_alias(sqlite_session):
    resolution, population = _services(sqlite_session)
    await population.upsert_node(NodeType.TEAM, "t1", now=T0, aliases=["Reds"])
    await population.upsert_node(NodeType.TEAM, "t2", now=T0, aliases=["Reds"])
    await sqlite_session.commit()

    duplicates = await resolution.detect_duplicates(NodeType.TEAM)

    assert len(duplicates) == 1
    assert duplicates[0].reason == "shared_alias:reds"


async def test_detect_duplicates_by_shared_provider_ref(sqlite_session):
    resolution, population = _services(sqlite_session)
    await population.upsert_node(NodeType.PLAYER, "p1", now=T0, provider_refs={"api_football": "42"})
    await population.upsert_node(NodeType.PLAYER, "p2", now=T0, provider_refs={"api_football": "42"})
    await sqlite_session.commit()

    duplicates = await resolution.detect_duplicates(NodeType.PLAYER)

    assert len(duplicates) == 1
    assert duplicates[0].reason == "shared_provider_ref:api_football:42"


async def test_detect_duplicates_ignores_already_merged_nodes(sqlite_session):
    resolution, population = _services(sqlite_session)
    a = await population.upsert_node(NodeType.TEAM, "a", now=T0, aliases=["Reds"])
    b = await population.upsert_node(NodeType.TEAM, "b", now=T0, aliases=["Reds"])
    await sqlite_session.commit()
    await resolution.merge(a, b, T0)
    await sqlite_session.commit()

    duplicates = await resolution.detect_duplicates(NodeType.TEAM)

    assert duplicates == []


async def test_merge_marks_duplicate_and_folds_aliases_into_canonical(sqlite_session):
    resolution, population = _services(sqlite_session)
    canonical = await population.upsert_node(NodeType.TEAM, "canonical", now=T0, aliases=["Alpha"])
    duplicate = await population.upsert_node(NodeType.TEAM, "duplicate", now=T0, aliases=["Beta"])
    await sqlite_session.commit()

    merged = await resolution.merge(canonical, duplicate, T0)
    await sqlite_session.commit()

    assert set(merged.aliases) >= {"alpha", "beta"} or set(merged.aliases) >= {"Alpha", "Beta", "duplicate"}
    fetched_duplicate = await resolution.nodes.get(duplicate.id)
    assert fetched_duplicate.status == "merged"
    assert fetched_duplicate.merged_into == str(canonical.id)


async def test_merge_redirects_edges_to_canonical(sqlite_session):
    resolution, population = _services(sqlite_session)
    canonical = await population.upsert_node(NodeType.TEAM, "canonical", now=T0)
    duplicate = await population.upsert_node(NodeType.TEAM, "duplicate", now=T0)
    player = await population.upsert_node(NodeType.PLAYER, "player", now=T0)
    await population.upsert_edge(player, duplicate, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    await resolution.merge(canonical, duplicate, T0)
    await sqlite_session.commit()

    redirected = await resolution.edges.get_current(player.id, canonical.id, EdgeType.PLAYS_FOR)
    assert redirected is not None
    still_on_duplicate = await resolution.edges.get_current(player.id, duplicate.id, EdgeType.PLAYS_FOR)
    assert still_on_duplicate is not None  # historical record preserved, not deleted


async def test_merge_redirects_outgoing_edges_from_duplicate(sqlite_session):
    resolution, population = _services(sqlite_session)
    canonical = await population.upsert_node(NodeType.PLAYER, "canonical", now=T0)
    duplicate = await population.upsert_node(NodeType.PLAYER, "duplicate", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "team", now=T0)
    await population.upsert_edge(duplicate, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    await resolution.merge(canonical, duplicate, T0)
    await sqlite_session.commit()

    redirected = await resolution.edges.get_current(canonical.id, team.id, EdgeType.PLAYS_FOR)
    assert redirected is not None


async def test_resolve_canonical_stops_at_dangling_merged_into_pointer(sqlite_session):
    resolution, population = _services(sqlite_session)
    node = await population.upsert_node(NodeType.TEAM, "orphan", now=T0)
    node.status = "merged"
    node.merged_into = str(uuid4())  # points at a node that doesn't exist
    await resolution.nodes.upsert(node)
    await sqlite_session.commit()

    resolved = await resolution.resolve_canonical(node)

    assert resolved.id == node.id  # stops rather than following a dead pointer


async def test_detect_duplicates_dedupes_pair_flagged_by_both_alias_and_provider_ref(sqlite_session):
    resolution, population = _services(sqlite_session)
    await population.upsert_node(
        NodeType.TEAM, "t1", now=T0, aliases=["Reds"], provider_refs={"api_football": "42"}
    )
    await population.upsert_node(
        NodeType.TEAM, "t2", now=T0, aliases=["Reds"], provider_refs={"api_football": "42"}
    )
    await sqlite_session.commit()

    duplicates = await resolution.detect_duplicates(NodeType.TEAM)

    assert len(duplicates) == 1  # same pair matched twice (alias + provider_ref), reported once


async def test_resolve_canonical_follows_merge_chain(sqlite_session):
    resolution, population = _services(sqlite_session)
    a = await population.upsert_node(NodeType.TEAM, "a", now=T0)
    b = await population.upsert_node(NodeType.TEAM, "b", now=T0)
    c = await population.upsert_node(NodeType.TEAM, "c", now=T0)
    await sqlite_session.commit()
    await resolution.merge(b, a, T0)
    await sqlite_session.commit()
    fresh_b = await resolution.nodes.get(b.id)
    await resolution.merge(c, fresh_b, T0)
    await sqlite_session.commit()

    fresh_a = await resolution.nodes.get(a.id)
    resolved = await resolution.resolve_canonical(fresh_a)

    assert resolved.entity_ref == "c"


async def test_merge_rejects_self_merge(sqlite_session):
    resolution, population = _services(sqlite_session)
    node = await population.upsert_node(NodeType.TEAM, "solo", now=T0)
    await sqlite_session.commit()

    with pytest.raises(ValueError):
        await resolution.merge(node, node, T0)

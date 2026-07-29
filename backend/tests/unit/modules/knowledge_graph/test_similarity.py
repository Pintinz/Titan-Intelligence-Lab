from __future__ import annotations

from datetime import datetime, timezone

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.application.similarity_service import SimilarityService
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.knowledge_graph.infrastructure.similarity.graph_structural import GraphStructuralSimilarity

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _services(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    query = GraphQueryService(nodes=nodes, edges=edges)
    similarity = GraphStructuralSimilarity(query=query)
    service = SimilarityService(similarity_port=similarity, population=population, nodes=nodes)
    return population, similarity, service


async def test_identical_node_has_similarity_one(sqlite_session):
    _, similarity, _ = _services(sqlite_session)
    population = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=sqlite_session), edges=SqlAlchemyKGEdgeRepository(session=sqlite_session)
    )
    node = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await sqlite_session.commit()

    score = await similarity.similarity(node.id, node.id)

    assert score == 1.0


async def test_players_sharing_all_teammates_are_similar(sqlite_session):
    population, similarity, _ = _services(sqlite_session)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_edge(p1, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(p2, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    score = await similarity.similarity(p1.id, p2.id)

    assert score == 1.0  # both share the exact same single neighbor


async def test_unrelated_nodes_have_zero_similarity(sqlite_session):
    population, similarity, _ = _services(sqlite_session)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    await sqlite_session.commit()

    score = await similarity.similarity(p1.id, p2.id)

    assert score == 0.0


async def test_most_similar_ranks_and_limits(sqlite_session):
    population, similarity, _ = _services(sqlite_session)
    target = await population.upsert_node(NodeType.PLAYER, "target", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_edge(target, team, EdgeType.PLAYS_FOR, T0)
    for i in range(3):
        peer = await population.upsert_node(NodeType.PLAYER, f"peer{i}", now=T0)
        await population.upsert_edge(peer, team, EdgeType.PLAYS_FOR, T0)
    stranger = await population.upsert_node(NodeType.PLAYER, "stranger", now=T0)
    await sqlite_session.commit()

    ranked = await similarity.most_similar(target.id, NodeType.PLAYER, limit=2)

    assert len(ranked) == 2
    assert all(score > 0 for _node, score in ranked)
    assert stranger.entity_ref not in {n.entity_ref for n, _ in ranked}


async def test_compute_and_store_writes_similar_to_edge_above_threshold(sqlite_session):
    population, similarity, service = _services(sqlite_session)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_edge(p1, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(p2, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    score = await service.compute_and_store(p1, p2, T0)
    await sqlite_session.commit()

    assert score == 1.0
    edge = await service.population.edges.get_current(p1.id, p2.id, EdgeType.SIMILAR_TO)
    assert edge is not None
    assert edge.weight == 1.0
    assert edge.directed is False


async def test_compute_and_store_skips_edge_below_threshold(sqlite_session):
    population, similarity, service = _services(sqlite_session)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    await sqlite_session.commit()

    score = await service.compute_and_store(p1, p2, T0)
    await sqlite_session.commit()

    assert score == 0.0
    edge = await service.population.edges.get_current(p1.id, p2.id, EdgeType.SIMILAR_TO)
    assert edge is None


async def test_recompute_for_type_writes_edges_for_every_node_above_threshold(sqlite_session):
    population, similarity, service = _services(sqlite_session)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    p3 = await population.upsert_node(NodeType.PLAYER, "p3", now=T0)
    await population.upsert_edge(p1, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(p2, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(p3, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    written = await service.recompute_for_type(NodeType.PLAYER, T0, limit_per_node=2)
    await sqlite_session.commit()

    assert written > 0
    edge = await service.population.edges.get_current(p1.id, p2.id, EdgeType.SIMILAR_TO)
    assert edge is not None
    assert edge.attributes["metric"] == "GraphStructuralSimilarity"


async def test_recompute_for_type_writes_nothing_when_no_nodes_of_type(sqlite_session):
    _, _, service = _services(sqlite_session)

    written = await service.recompute_for_type(NodeType.PLAYER, T0)

    assert written == 0

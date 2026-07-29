from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.knowledge_graph.application.graph_query_service import GraphQueryService, _ensure_aware
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId, NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


async def _service(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    return GraphQueryService(nodes=nodes, edges=edges), KnowledgeGraphPopulationService(nodes=nodes, edges=edges)


async def test_shortest_path_direct_edge(sqlite_session):
    query, pop = await _service(sqlite_session)
    player = await pop.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await pop.upsert_node(NodeType.TEAM, "t1", now=T0)
    await pop.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    path = await query.shortest_path(player.id, team.id)

    assert path is not None
    assert [n.entity_ref for n in path] == ["p1", "t1"]


async def test_shortest_path_multi_hop(sqlite_session):
    query, pop = await _service(sqlite_session)
    a = await pop.upsert_node(NodeType.PLAYER, "a", now=T0)
    b = await pop.upsert_node(NodeType.TEAM, "b", now=T0)
    c = await pop.upsert_node(NodeType.COMPETITION, "c", now=T0)
    await pop.upsert_edge(a, b, EdgeType.PLAYS_FOR, T0)
    await pop.upsert_edge(b, c, EdgeType.COMPETES_IN, T0)
    await sqlite_session.commit()

    path = await query.shortest_path(a.id, c.id)

    assert [n.entity_ref for n in path] == ["a", "b", "c"]


async def test_shortest_path_no_route_returns_none(sqlite_session):
    query, pop = await _service(sqlite_session)
    a = await pop.upsert_node(NodeType.PLAYER, "a", now=T0)
    b = await pop.upsert_node(NodeType.TEAM, "isolated", now=T0)
    await sqlite_session.commit()

    assert await query.shortest_path(a.id, b.id) is None


async def test_neighborhood_one_hop(sqlite_session):
    query, pop = await _service(sqlite_session)
    player = await pop.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await pop.upsert_node(NodeType.TEAM, "t1", now=T0)
    sport = await pop.upsert_node(NodeType.SPORT, "s1", now=T0)
    await pop.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await pop.upsert_edge(team, sport, EdgeType.BELONGS_TO, T0)
    await sqlite_session.commit()

    subgraph = await query.neighborhood(player.id, depth=1)

    refs = {n.entity_ref for n in subgraph.nodes}
    assert refs == {"p1", "t1"}
    assert not subgraph.truncated


async def test_neighborhood_two_hops_reaches_further(sqlite_session):
    query, pop = await _service(sqlite_session)
    player = await pop.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await pop.upsert_node(NodeType.TEAM, "t1", now=T0)
    sport = await pop.upsert_node(NodeType.SPORT, "s1", now=T0)
    await pop.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await pop.upsert_edge(team, sport, EdgeType.BELONGS_TO, T0)
    await sqlite_session.commit()

    subgraph = await query.neighborhood(player.id, depth=2)

    refs = {n.entity_ref for n in subgraph.nodes}
    assert refs == {"p1", "t1", "s1"}


async def test_neighborhood_truncates_at_max_nodes(sqlite_session):
    query, pop = await _service(sqlite_session)
    hub = await pop.upsert_node(NodeType.TEAM, "hub", now=T0)
    for i in range(10):
        player = await pop.upsert_node(NodeType.PLAYER, f"p{i}", now=T0)
        await pop.upsert_edge(player, hub, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    subgraph = await query.neighborhood(hub.id, depth=1, max_nodes=3)

    assert len(subgraph.nodes) <= 3
    assert subgraph.truncated


async def test_traverse_forward_and_reverse(sqlite_session):
    query, pop = await _service(sqlite_session)
    p1 = await pop.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await pop.upsert_node(NodeType.PLAYER, "p2", now=T0)
    team = await pop.upsert_node(NodeType.TEAM, "t1", now=T0)
    await pop.upsert_edge(p1, team, EdgeType.PLAYS_FOR, T0)
    await pop.upsert_edge(p2, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    forward = await query.traverse(p1.id, EdgeType.PLAYS_FOR, reverse=False)
    assert {n.entity_ref for n in forward} == {"t1"}

    reverse = await query.traverse(team.id, EdgeType.PLAYS_FOR, reverse=True)
    assert {n.entity_ref for n in reverse} == {"p1", "p2"}


async def test_connected_components_groups_linked_nodes(sqlite_session):
    query, pop = await _service(sqlite_session)
    a = await pop.upsert_node(NodeType.TEAM, "a", now=T0)
    b = await pop.upsert_node(NodeType.TEAM, "b", now=T0)
    c = await pop.upsert_node(NodeType.TEAM, "c", now=T0)  # isolated
    await pop.upsert_edge(a, b, EdgeType.RIVAL_OF, T0)
    await sqlite_session.commit()

    components = await query.connected_components(NodeType.TEAM, EdgeType.RIVAL_OF)

    sizes = sorted(len(group) for group in components)
    assert sizes == [1, 2]


async def test_at_time_excludes_edges_not_yet_valid(sqlite_session):
    query, pop = await _service(sqlite_session)
    player = await pop.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await pop.upsert_node(NodeType.TEAM, "t1", now=T0)
    later = T0 + timedelta(days=30)
    await pop.upsert_edge(player, team, EdgeType.PLAYS_FOR, later)
    await sqlite_session.commit()

    before = await query.at_time(player.id, T0, depth=1)
    after = await query.at_time(player.id, later + timedelta(days=1), depth=1)

    assert before.edges == ()
    assert len(after.edges) == 1


async def test_at_time_excludes_closed_edges(sqlite_session):
    query, pop = await _service(sqlite_session)
    nodes_repo = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges_repo = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    player = await pop.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await pop.upsert_node(NodeType.TEAM, "t1", now=T0)
    edge = await pop.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    closed_at = T0 + timedelta(days=10)
    await edges_repo.close(edge.id, closed_at)
    await sqlite_session.commit()

    while_active = await query.at_time(player.id, T0 + timedelta(days=5), depth=1)
    after_close = await query.at_time(player.id, closed_at + timedelta(days=1), depth=1)

    assert len(while_active.edges) == 1
    assert after_close.edges == ()


async def test_edge_history_includes_closed_edges_sorted(sqlite_session):
    query, pop = await _service(sqlite_session)
    edges_repo = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    player = await pop.upsert_node(NodeType.PLAYER, "p1", now=T0)
    old_team = await pop.upsert_node(NodeType.TEAM, "old", now=T0)
    new_team = await pop.upsert_node(NodeType.TEAM, "new", now=T0)
    old_edge = await pop.upsert_edge(player, old_team, EdgeType.PLAYS_FOR, T0)
    await edges_repo.close(old_edge.id, T0 + timedelta(days=100))
    await pop.upsert_edge(player, new_team, EdgeType.PLAYS_FOR, T0 + timedelta(days=101))
    await sqlite_session.commit()

    history = await query.edge_history(player.id, EdgeType.PLAYS_FOR)

    assert len(history) == 2
    assert history[0].valid_from < history[1].valid_from


async def test_most_connected_ranks_by_in_degree(sqlite_session):
    query, pop = await _service(sqlite_session)
    popular = await pop.upsert_node(NodeType.TEAM, "popular", now=T0)
    unpopular = await pop.upsert_node(NodeType.TEAM, "unpopular", now=T0)
    for i in range(3):
        rival = await pop.upsert_node(NodeType.TEAM, f"rival{i}", now=T0)
        await pop.upsert_edge(rival, popular, EdgeType.RIVAL_OF, T0)
    rival = await pop.upsert_node(NodeType.TEAM, "onlyrival", now=T0)
    await pop.upsert_edge(rival, unpopular, EdgeType.RIVAL_OF, T0)
    await sqlite_session.commit()

    ranked = await query.most_connected(NodeType.TEAM, EdgeType.RIVAL_OF, direction="in", limit=2)

    assert ranked[0][0].entity_ref == "popular"
    assert ranked[0][1] == 3


async def test_shortest_path_same_node_returns_single_node_path(sqlite_session):
    query, pop = await _service(sqlite_session)
    node = await pop.upsert_node(NodeType.TEAM, "solo", now=T0)
    await sqlite_session.commit()

    path = await query.shortest_path(node.id, node.id)

    assert [n.entity_ref for n in path] == ["solo"]


async def test_shortest_path_same_node_returns_none_if_missing(sqlite_session):
    query, _pop = await _service(sqlite_session)
    missing = KGNodeId(uuid4())

    assert await query.shortest_path(missing, missing) is None


async def test_shortest_path_skips_already_visited_neighbor_in_triangle(sqlite_session):
    query, pop = await _service(sqlite_session)
    a = await pop.upsert_node(NodeType.TEAM, "a", now=T0)
    b = await pop.upsert_node(NodeType.TEAM, "b", now=T0)
    c = await pop.upsert_node(NodeType.TEAM, "c", now=T0)
    await pop.upsert_edge(a, b, EdgeType.RIVAL_OF, T0, directed=False)
    await pop.upsert_edge(b, c, EdgeType.RIVAL_OF, T0, directed=False)
    await pop.upsert_edge(a, c, EdgeType.RIVAL_OF, T0, directed=False)  # closes the triangle
    await sqlite_session.commit()

    path = await query.shortest_path(a.id, c.id)

    assert [n.entity_ref for n in path] == ["a", "c"]  # direct edge found, not via b


async def test_traverse_respects_max_nodes_cap(sqlite_session):
    query, pop = await _service(sqlite_session)
    hub = await pop.upsert_node(NodeType.TEAM, "hub", now=T0)
    for i in range(10):
        player = await pop.upsert_node(NodeType.PLAYER, f"p{i}", now=T0)
        await pop.upsert_edge(player, hub, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    results = await query.traverse(hub.id, EdgeType.PLAYS_FOR, reverse=True, max_nodes=3)

    assert len(results) <= 3


async def test_most_connected_respects_limit(sqlite_session):
    query, pop = await _service(sqlite_session)
    for i in range(5):
        team = await pop.upsert_node(NodeType.TEAM, f"t{i}", now=T0)
        rival = await pop.upsert_node(NodeType.TEAM, f"r{i}", now=T0)
        await pop.upsert_edge(rival, team, EdgeType.RIVAL_OF, T0)
    await sqlite_session.commit()

    ranked = await query.most_connected(NodeType.TEAM, EdgeType.RIVAL_OF, direction="in", limit=2)

    assert len(ranked) == 2


def test_ensure_aware_returns_dt_unchanged_when_already_aware():
    aware_dt = T0
    reference = T0 + timedelta(days=1)

    assert _ensure_aware(aware_dt, reference) is aware_dt


async def test_subgraph_extraction_unions_multiple_seeds(sqlite_session):
    query, pop = await _service(sqlite_session)
    a = await pop.upsert_node(NodeType.TEAM, "a", now=T0)
    b = await pop.upsert_node(NodeType.TEAM, "b", now=T0)
    shared = await pop.upsert_node(NodeType.SPORT, "shared", now=T0)
    await pop.upsert_edge(a, shared, EdgeType.BELONGS_TO, T0)
    await pop.upsert_edge(b, shared, EdgeType.BELONGS_TO, T0)
    await sqlite_session.commit()

    subgraph = await query.subgraph_extraction([a.id, b.id], depth=1)

    refs = {n.entity_ref for n in subgraph.nodes}
    assert refs == {"a", "b", "shared"}

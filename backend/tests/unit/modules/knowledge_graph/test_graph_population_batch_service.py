from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.knowledge_graph.application.graph_population_batch_service import (
    EdgeReplayEvent,
    GraphPopulationBatchService,
    NodeReplayEvent,
    NodeSpec,
)
from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _services(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    query = GraphQueryService(nodes=nodes, edges=edges)
    batch = GraphPopulationBatchService(population=population, query=query, edges=edges)
    return population, batch


async def test_batch_upsert_nodes(sqlite_session):
    population, batch = _services(sqlite_session)

    created = await batch.batch_upsert_nodes(
        [
            NodeSpec(NodeType.TEAM, "t1"),
            NodeSpec(NodeType.TEAM, "t2", attributes={"name": "Team Two"}),
        ],
        now=T0,
    )
    await sqlite_session.commit()

    assert {n.entity_ref for n in created} == {"t1", "t2"}
    assert created[1].attributes["name"] == "Team Two"


async def test_discover_teammate_relationships(sqlite_session):
    population, batch = _services(sqlite_session)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    p3 = await population.upsert_node(NodeType.PLAYER, "p3", now=T0)
    for player in (p1, p2, p3):
        await population.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    edges = await batch.discover_teammate_relationships(team.id, T0)
    await sqlite_session.commit()

    assert len(edges) == 3  # C(3,2) pairs
    assert all(e.edge_type == EdgeType.TEAMMATE_OF for e in edges)
    assert all(not e.directed for e in edges)


async def test_delete_edge_hard_deletes(sqlite_session):
    population, batch = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    edge = await population.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    deleted = await batch.delete_edge(edge.id)
    await sqlite_session.commit()

    assert deleted is True
    remaining = await batch.query.edges.list_from(player.id)
    assert remaining == []


async def test_delete_edge_returns_false_when_missing(sqlite_session):
    _, batch = _services(sqlite_session)

    assert await batch.delete_edge(KGEdgeId(uuid4())) is False


async def test_replay_applies_events_in_chronological_order_regardless_of_input_order(sqlite_session):
    population, batch = _services(sqlite_session)
    later = T0 + timedelta(days=100)

    # Handed in out of order: the "later" edge event first, "earlier" node event second.
    events = [
        EdgeReplayEvent(
            at=later, from_type=NodeType.PLAYER, from_ref="p1",
            to_type=NodeType.TEAM, to_ref="new_team", edge_type=EdgeType.PLAYS_FOR,
        ),
        NodeReplayEvent(at=T0, node_type=NodeType.PLAYER, entity_ref="p1", attributes={"name": "Original"}),
    ]

    await batch.replay(events)
    await sqlite_session.commit()

    player = await batch.query.nodes.get_by_entity_ref(NodeType.PLAYER, "p1")
    assert player.attributes["name"] == "Original"  # T0's attributes survived the later edge event's touch

    edge = await batch.query.edges.get_current(
        player.id, (await batch.query.nodes.get_by_entity_ref(NodeType.TEAM, "new_team")).id, EdgeType.PLAYS_FOR
    )
    assert edge is not None

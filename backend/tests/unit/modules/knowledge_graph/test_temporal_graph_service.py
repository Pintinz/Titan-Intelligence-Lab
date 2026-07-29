from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.application.temporal_graph_service import TemporalGraphService
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
    temporal = TemporalGraphService(query=query, edges=edges, population=population)
    return population, temporal


async def test_close_edge_sets_valid_to(sqlite_session):
    population, temporal = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    edge = await population.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    closed = await temporal.close_edge(edge.id, T0 + timedelta(days=5))
    await sqlite_session.commit()

    assert closed is not None
    assert closed.valid_to is not None
    assert not closed.is_current


async def test_close_edge_returns_none_when_missing(sqlite_session):
    _, temporal = _services(sqlite_session)

    assert await temporal.close_edge(KGEdgeId(uuid4()), T0) is None


async def test_supersede_edge_transitions_player_between_teams(sqlite_session):
    population, temporal = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    old_team = await population.upsert_node(NodeType.TEAM, "old", now=T0)
    new_team = await population.upsert_node(NodeType.TEAM, "new", now=T0)
    old_edge = await population.upsert_edge(player, old_team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()
    transfer_at = T0 + timedelta(days=100)

    new_edge = await temporal.supersede_edge(old_edge, player, new_team, EdgeType.PLAYS_FOR, transfer_at)
    await sqlite_session.commit()

    assert new_edge.to_node_id == new_team.id
    assert new_edge.is_current
    reloaded_old = await temporal.query.edges.get_current(player.id, old_team.id, EdgeType.PLAYS_FOR)
    assert reloaded_old is None  # old edge closed, no longer "current"
    still_current_new = await temporal.query.edges.get_current(player.id, new_team.id, EdgeType.PLAYS_FOR)
    assert still_current_new is not None


async def test_entity_evolution_orders_open_and_close_events(sqlite_session):
    population, temporal = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    old_team = await population.upsert_node(NodeType.TEAM, "old", now=T0)
    new_team = await population.upsert_node(NodeType.TEAM, "new", now=T0)
    old_edge = await population.upsert_edge(player, old_team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()
    transfer_at = T0 + timedelta(days=100)
    await temporal.supersede_edge(old_edge, player, new_team, EdgeType.PLAYS_FOR, transfer_at)
    await sqlite_session.commit()

    events = await temporal.entity_evolution(player.id, EdgeType.PLAYS_FOR)

    # SQLite drops tzinfo on read-back (ADR-007) — compare naive timestamps and kinds only.
    kinds_in_order = [(e.kind, e.at.replace(tzinfo=None)) for e in events]
    assert kinds_in_order == [
        ("opened", T0.replace(tzinfo=None)),
        ("closed", transfer_at.replace(tzinfo=None)),
        ("opened", transfer_at.replace(tzinfo=None)),
    ]


async def test_entity_evolution_empty_for_untouched_node(sqlite_session):
    population, temporal = _services(sqlite_session)
    lonely = await population.upsert_node(NodeType.TEAM, "lonely", now=T0)
    await sqlite_session.commit()

    events = await temporal.entity_evolution(lonely.id)

    assert events == []

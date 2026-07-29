from __future__ import annotations

from datetime import datetime, timedelta, timezone

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.application.semantic_search_service import SemanticSearchService
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
    query = GraphQueryService(nodes=nodes, edges=edges)
    search = SemanticSearchService(query=query)
    return population, search


async def test_find_players_for_team(sqlite_session):
    population, search = _services(sqlite_session)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    other_team = await population.upsert_node(NodeType.TEAM, "t2", now=T0)
    other_player = await population.upsert_node(NodeType.PLAYER, "other", now=T0)
    await population.upsert_edge(p1, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(p2, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(other_player, other_team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    players = await search.find_players_for_team(team.id)

    assert {p.entity_ref for p in players} == {"p1", "p2"}


async def test_find_teams_and_matches_coached_by(sqlite_session):
    population, search = _services(sqlite_session)
    coach = await population.upsert_node(NodeType.COACH, "coach1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    match = await population.upsert_node(NodeType.MATCH, "m1", now=T0)
    await population.upsert_edge(team, coach, EdgeType.COACHED_BY, T0)
    await population.upsert_edge(team, match, EdgeType.INVOLVED_IN, T0)
    await sqlite_session.commit()

    teams = await search.find_teams_coached_by(coach.id)
    matches = await search.find_matches_coached_by(coach.id)

    assert {t.entity_ref for t in teams} == {"t1"}
    assert {m.entity_ref for m in matches} == {"m1"}


async def test_find_rivals(sqlite_session):
    population, search = _services(sqlite_session)
    liverpool = await population.upsert_node(NodeType.TEAM, "liverpool", now=T0)
    everton = await population.upsert_node(NodeType.TEAM, "everton", now=T0)
    await population.upsert_edge(liverpool, everton, EdgeType.RIVAL_OF, T0, directed=False)
    await sqlite_session.commit()

    rivals = await search.find_rivals(liverpool.id)

    assert {r.entity_ref for r in rivals} == {"everton"}


async def test_find_injuries_before_match(sqlite_session):
    population, search = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    match = await population.upsert_node(NodeType.MATCH, "m1", now=T0)
    early = T0 - timedelta(days=10)
    await population.upsert_edge(player, match, EdgeType.INJURED_IN, early)
    await sqlite_session.commit()

    before_kickoff = await search.find_injuries_before(match.id, T0)
    before_early = await search.find_injuries_before(match.id, early - timedelta(days=1))

    assert len(before_kickoff) == 1
    assert before_early == []


async def test_find_transfers_involving_team(sqlite_session):
    population, search = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    unrelated = await population.upsert_node(NodeType.TEAM, "unrelated", now=T0)
    await population.upsert_edge(player, team, EdgeType.TRANSFERRED_TO, T0)
    await sqlite_session.commit()

    transfers = await search.find_transfers_involving(team.id)
    none_for_unrelated = await search.find_transfers_involving(unrelated.id)

    assert len(transfers) == 1
    assert none_for_unrelated == []


async def test_find_relationships_between_two_players(sqlite_session):
    population, search = _services(sqlite_session)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    p3 = await population.upsert_node(NodeType.PLAYER, "p3", now=T0)
    await population.upsert_edge(p1, p2, EdgeType.TEAMMATE_OF, T0, directed=False)
    await sqlite_session.commit()

    relationships = await search.find_relationships_between(p1.id, p2.id)
    none_between = await search.find_relationships_between(p1.id, p3.id)

    assert len(relationships) == 1
    assert relationships[0].edge_type == EdgeType.TEAMMATE_OF
    assert none_between == []


async def test_find_context_around_fixture_delegates_to_neighborhood(sqlite_session):
    population, search = _services(sqlite_session)
    fixture = await population.upsert_node(NodeType.MATCH, "m1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_edge(team, fixture, EdgeType.INVOLVED_IN, T0)
    await sqlite_session.commit()

    subgraph = await search.find_context_around_fixture(fixture.id)

    assert {n.entity_ref for n in subgraph.nodes} == {"m1", "t1"}


async def test_find_by_node_type(sqlite_session):
    population, search = _services(sqlite_session)
    await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_node(NodeType.TEAM, "t2", now=T0)
    await sqlite_session.commit()

    teams = await search.find_by_node_type(NodeType.TEAM)

    assert {t.entity_ref for t in teams} == {"t1", "t2"}

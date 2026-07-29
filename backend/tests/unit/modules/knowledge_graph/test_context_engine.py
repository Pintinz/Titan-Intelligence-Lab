from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from modules.knowledge_graph.application.context_engine import ContextEngine
from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import EdgeType, KGNodeId, NodeType
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
    engine = ContextEngine(query=query, nodes=nodes)
    return population, engine


async def test_build_context_groups_related_nodes_by_type(sqlite_session):
    population, engine = _services(sqlite_session)
    fixture = await population.upsert_node(NodeType.MATCH, "m1", now=T0)
    home = await population.upsert_node(NodeType.TEAM, "home", now=T0)
    away = await population.upsert_node(NodeType.TEAM, "away", now=T0)
    venue = await population.upsert_node(NodeType.VENUE, "v1", now=T0)
    await population.upsert_edge(home, fixture, EdgeType.INVOLVED_IN, T0)
    await population.upsert_edge(away, fixture, EdgeType.INVOLVED_IN, T0)
    await population.upsert_edge(fixture, venue, EdgeType.SCHEDULED_AT, T0)
    await sqlite_session.commit()

    bundle = await engine.build_context(fixture.id, T0, depth=1)

    assert bundle is not None
    assert bundle.subject.entity_ref == "m1"
    assert {n.entity_ref for n in bundle.related_by_type[NodeType.TEAM]} == {"home", "away"}
    assert {n.entity_ref for n in bundle.related_by_type[NodeType.VENUE]} == {"v1"}
    assert NodeType.MATCH not in bundle.related_by_type  # subject itself excluded
    assert bundle.generated_at == T0


async def test_build_context_returns_none_for_missing_node(sqlite_session):
    _, engine = _services(sqlite_session)

    bundle = await engine.build_context(KGNodeId(uuid4()), T0)

    assert bundle is None


async def test_context_for_fixture_and_match_are_generic_wrappers(sqlite_session):
    population, engine = _services(sqlite_session)
    fixture = await population.upsert_node(NodeType.MATCH, "m1", now=T0)
    await sqlite_session.commit()

    fixture_bundle = await engine.context_for_fixture(fixture.id, T0)
    match_bundle = await engine.context_for_match(fixture.id, T0)

    assert fixture_bundle.subject.entity_ref == "m1"
    assert match_bundle.subject.entity_ref == "m1"


async def test_context_for_player_uses_deeper_expansion(sqlite_session):
    population, engine = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    sport = await population.upsert_node(NodeType.SPORT, "s1", now=T0)
    await population.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(team, sport, EdgeType.BELONGS_TO, T0)
    await sqlite_session.commit()

    bundle = await engine.context_for_player(player.id, T0)

    all_refs = {n.entity_ref for group in bundle.related_by_type.values() for n in group}
    assert all_refs == {"t1", "s1"}  # two hops deep, reaches sport via team


async def test_remaining_named_wrappers_delegate_to_build_context(sqlite_session):
    population, engine = _services(sqlite_session)
    node = await population.upsert_node(NodeType.TEAM, "subject", now=T0)
    await sqlite_session.commit()

    for method in (
        engine.context_for_team,
        engine.context_for_competition,
        engine.context_for_prediction,
        engine.context_for_news,
        engine.context_for_feature,
        engine.context_for_model,
        engine.context_for_explainability,
    ):
        bundle = await method(node.id, T0)
        assert bundle is not None
        assert bundle.subject.entity_ref == "subject"


async def test_context_for_historical_comparison_returns_pair(sqlite_session):
    population, engine = _services(sqlite_session)
    a = await population.upsert_node(NodeType.TEAM, "a", now=T0)
    b = await population.upsert_node(NodeType.TEAM, "b", now=T0)
    await sqlite_session.commit()

    bundle_a, bundle_b = await engine.context_for_historical_comparison(a.id, b.id, T0)

    assert bundle_a.subject.entity_ref == "a"
    assert bundle_b.subject.entity_ref == "b"

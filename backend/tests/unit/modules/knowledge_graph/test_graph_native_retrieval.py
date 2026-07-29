from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.entities import KGEdge
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId, NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.knowledge_graph.infrastructure.retrieval.graph_native_retrieval import GraphNativeRetrieval
from modules.knowledge_graph.ports.graph_query import Subgraph
from modules.knowledge_graph.ports.retrieval import RetrievalQuery

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _services(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    query = GraphQueryService(nodes=nodes, edges=edges)
    retrieval = GraphNativeRetrieval(query=query)
    return population, retrieval


async def test_retrieve_returns_structured_facts_around_subject(sqlite_session):
    population, retrieval = _services(sqlite_session)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0, confidence=0.9, source="ingestion")
    await sqlite_session.commit()

    result = await retrieval.retrieve(RetrievalQuery(subject_id=player.id, purpose="explainability"))

    assert len(result.documents) == 1
    doc = result.documents[0]
    assert doc.subject_ref == "p1"
    assert doc.relation == EdgeType.PLAYS_FOR.value
    assert doc.related_ref == "t1"
    assert doc.confidence == 0.9
    assert not result.truncated


async def test_retrieve_returns_empty_for_missing_subject(sqlite_session):
    _, retrieval = _services(sqlite_session)

    result = await retrieval.retrieve(RetrievalQuery(subject_id=KGNodeId(uuid4())))

    assert result.documents == ()
    assert not result.truncated


async def test_retrieve_respects_max_facts(sqlite_session):
    population, retrieval = _services(sqlite_session)
    hub = await population.upsert_node(NodeType.TEAM, "hub", now=T0)
    for i in range(5):
        player = await population.upsert_node(NodeType.PLAYER, f"p{i}", now=T0)
        await population.upsert_edge(player, hub, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    result = await retrieval.retrieve(RetrievalQuery(subject_id=hub.id, max_facts=2))

    assert len(result.documents) <= 2
    assert result.truncated


async def test_retrieve_skips_edges_referencing_a_node_missing_from_the_subgraph(sqlite_session):
    """Defensive guard: `_expand`'s BFS should never produce an edge referencing a node absent
    from `subgraph.nodes`, but the retriever still checks — this exercises that guard directly
    via a stubbed query whose `neighborhood()` returns a deliberately inconsistent Subgraph."""
    population, _ = _services(sqlite_session)
    subject = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    await sqlite_session.commit()

    dangling_edge = KGEdge(
        id=KGEdgeId(uuid4()), from_node_id=subject.id, to_node_id=KGNodeId(uuid4()),
        edge_type=EdgeType.PLAYS_FOR, valid_from=T0,
    )

    class _StubQuery:
        async def neighborhood(self, node_id, depth=1, max_nodes=200):
            return Subgraph(nodes=(subject,), edges=(dangling_edge,), truncated=False)

    retrieval = GraphNativeRetrieval(query=_StubQuery())

    result = await retrieval.retrieve(RetrievalQuery(subject_id=subject.id))

    assert result.documents == ()

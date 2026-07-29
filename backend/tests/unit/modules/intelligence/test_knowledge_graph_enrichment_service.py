from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.intelligence.application.entity_extraction_service import ResolvedEntityMention
from modules.intelligence.application.knowledge_graph_enrichment_service import (
    EnrichmentResult,
    KnowledgeGraphEnrichmentService,
    _slugify,
)
from modules.intelligence.domain.entities import NewsEvent
from modules.intelligence.domain.value_objects import NewsArticleId, NewsEventId, NewsEventType, NewsSourceId
from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.application.temporal_graph_service import TemporalGraphService
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def kg_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"knowledge_graph": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeGraphBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _services(session):
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    query = GraphQueryService(nodes=nodes, edges=edges)
    temporal = TemporalGraphService(query=query, edges=edges, population=population)
    enrichment = KnowledgeGraphEnrichmentService(population=population, temporal=temporal, nodes=nodes)
    return enrichment, population, nodes


def _event(event_type: NewsEventType, affected_entity_refs: tuple[str, ...]) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=event_type, summary="x", confidence=0.7,
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, detected_at=T0,
        affected_entity_refs=affected_entity_refs,
    )


def test_slugify_normalizes_text():
    assert _slugify("Erling Haaland") == "erling_haaland"
    assert _slugify("!!!") == "unknown"


async def test_enrich_from_mentions_creates_new_node_for_unresolved_mention(kg_session):
    enrichment, _population, nodes = _services(kg_session)
    mention = ResolvedEntityMention(text="Erling Haaland", node_type=NodeType.PLAYER, kg_node_id=None, confidence=0.6)

    result = await enrichment.enrich_from_mentions([mention], T0)
    await kg_session.commit()

    assert result.nodes_created == ("erling_haaland",)
    created = await nodes.get_by_entity_ref(NodeType.PLAYER, "erling_haaland")
    assert created is not None
    assert "Erling Haaland" in created.aliases
    assert created.source == "news_intelligence"


async def test_enrich_from_mentions_adds_alias_to_resolved_node(kg_session):
    enrichment, population, nodes = _services(kg_session)
    team = await population.upsert_node(NodeType.TEAM, "man_city", now=T0, aliases=["Manchester City"])
    await kg_session.commit()
    mention = ResolvedEntityMention(text="Man City", node_type=NodeType.TEAM, kg_node_id=team.id, confidence=0.8)

    result = await enrichment.enrich_from_mentions([mention], T0 + timedelta(days=1))
    await kg_session.commit()

    assert result.aliases_added == ("Man City",)
    updated = await nodes.get_by_entity_ref(NodeType.TEAM, "man_city")
    assert set(updated.aliases) >= {"Manchester City", "Man City"}


async def test_enrich_from_mentions_skips_mentions_without_node_type(kg_session):
    enrichment, _population, _nodes = _services(kg_session)
    mention = ResolvedEntityMention(text="Something", node_type=None, kg_node_id=None, confidence=0.5)

    result = await enrichment.enrich_from_mentions([mention], T0)

    assert result == EnrichmentResult()  # no-op result


async def test_enrich_from_mentions_does_not_duplicate_existing_alias(kg_session):
    enrichment, population, _nodes = _services(kg_session)
    team = await population.upsert_node(NodeType.TEAM, "man_city", now=T0, aliases=["Manchester City"])
    await kg_session.commit()
    mention = ResolvedEntityMention(text="Manchester City", node_type=NodeType.TEAM, kg_node_id=team.id, confidence=0.8)

    result = await enrichment.enrich_from_mentions([mention], T0 + timedelta(days=1))

    assert result.aliases_added == ()


async def test_enrich_from_event_creates_plays_for_edge_on_transfer(kg_session):
    enrichment, population, nodes = _services(kg_session)
    player = await population.upsert_node(NodeType.PLAYER, "mbappe", now=T0)
    new_team = await population.upsert_node(NodeType.TEAM, "real_madrid", now=T0)
    await kg_session.commit()
    event = _event(NewsEventType.TRANSFER, (str(player.id), str(new_team.id)))

    result = await enrichment.enrich_from_event(event, T0 + timedelta(days=1))
    await kg_session.commit()

    edge = await enrichment.temporal.query.edges.get_current(player.id, new_team.id, EdgeType.PLAYS_FOR)
    assert edge is not None
    assert result.edges_created == ("mbappe->real_madrid:plays_for",)


async def test_enrich_from_event_transfer_closes_old_plays_for_edge(kg_session):
    enrichment, population, nodes = _services(kg_session)
    player = await population.upsert_node(NodeType.PLAYER, "mbappe", now=T0)
    old_team = await population.upsert_node(NodeType.TEAM, "psg", now=T0)
    new_team = await population.upsert_node(NodeType.TEAM, "real_madrid", now=T0)
    await population.upsert_edge(player, old_team, EdgeType.PLAYS_FOR, T0)
    await kg_session.commit()
    event = _event(NewsEventType.TRANSFER, (str(player.id), str(new_team.id)))

    await enrichment.enrich_from_event(event, T0 + timedelta(days=1))
    await kg_session.commit()

    old_edge = await enrichment.temporal.query.edges.get_current(player.id, old_team.id, EdgeType.PLAYS_FOR)
    new_edge = await enrichment.temporal.query.edges.get_current(player.id, new_team.id, EdgeType.PLAYS_FOR)
    assert old_edge is None  # closed, no longer current
    assert new_edge is not None


async def test_enrich_from_event_creates_coached_by_edge_on_manager_change(kg_session):
    enrichment, population, nodes = _services(kg_session)
    team = await population.upsert_node(NodeType.TEAM, "chelsea", now=T0)
    coach = await population.upsert_node(NodeType.COACH, "new_manager", now=T0)
    await kg_session.commit()
    event = _event(NewsEventType.MANAGER_CHANGE, (str(team.id), str(coach.id)))

    result = await enrichment.enrich_from_event(event, T0)
    await kg_session.commit()

    edge = await enrichment.temporal.query.edges.get_current(team.id, coach.id, EdgeType.COACHED_BY)
    assert edge is not None
    assert result.edges_created == ("chelsea->new_manager:coached_by",)


async def test_enrich_from_event_no_edge_for_unmapped_event_type(kg_session):
    enrichment, population, nodes = _services(kg_session)
    player = await population.upsert_node(NodeType.PLAYER, "some_player", now=T0)
    await kg_session.commit()
    event = _event(NewsEventType.INJURY, (str(player.id),))

    result = await enrichment.enrich_from_event(event, T0)

    assert result.edges_created == ()


async def test_enrich_from_event_ignores_unresolvable_refs(kg_session):
    enrichment, _population, _nodes = _services(kg_session)
    event = _event(NewsEventType.TRANSFER, ("not-a-uuid", "also-not-a-uuid"))

    result = await enrichment.enrich_from_event(event, T0)

    assert result.edges_created == ()

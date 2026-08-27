"""Tests for `scripts/reresolve_news_event_entities.py`'s `reresolve_all` — the one-time catch-up
that re-attempts Knowledge Graph resolution for `NewsEvent`s whose entities failed to resolve
before the entity-resolution audit fix (`population_service.py`, 2026-08-27). See that script's
own module docstring: an `UNRESOLVED` `ResolvedNewsEntity.ref` already holds the original raw
mention text, so re-resolution needs no second Gemini call — just a fresh `find_by_alias` lookup
against the now-fixed graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.intelligence.domain.entities import NewsEvent, ResolvedNewsEntity
from modules.intelligence.domain.value_objects import (
    EntityResolutionStatus,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
)
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemyNewsEventRepository
from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.knowledge_graph.infrastructure.persistence.repositories import SqlAlchemyKGEdgeRepository, SqlAlchemyKGNodeRepository
from scripts.reresolve_news_event_entities import reresolve_all

T0 = datetime(2026, 8, 27, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def combined_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"knowledge_graph": None, "intelligence": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeGraphBase.metadata.create_all)
        await conn.run_sync(IntelligenceBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _services(session):
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    resolver = EntityResolutionService(nodes=nodes, edges=edges, population=population)
    events = SqlAlchemyNewsEventRepository(session=session)
    return events, resolver, population


def _unresolved_event(mention_text: str, node_type: str = "team") -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="A player was injured.",
        confidence=0.8, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
        occurred_at=T0, detected_at=T0,
        resolved_entities=(ResolvedNewsEntity(ref=mention_text, node_type=node_type, status=EntityResolutionStatus.UNRESOLVED),),
    )


async def test_resolves_an_entity_now_matchable_via_the_fixed_alias(combined_session):
    events, resolver, population = _services(combined_session)
    team_node = await population.populate_team("team-1", "football", T0, name="Manchester City")
    await combined_session.commit()

    event = await events.record(_unresolved_event("Manchester City"))
    await combined_session.commit()

    results = await reresolve_all(events, resolver)
    await combined_session.commit()

    assert results == {"events_checked": 1, "events_updated": 1, "entities_newly_resolved": 1}
    reloaded = await events.get(event.id)
    assert reloaded.resolved_entities[0].status is EntityResolutionStatus.RESOLVED
    assert reloaded.resolved_entities[0].ref == str(team_node.id)
    assert reloaded.affected_entity_refs == (str(team_node.id),)


async def test_leaves_a_still_unmatchable_entity_unresolved(combined_session):
    """Never fabricates a resolution — an entity that genuinely has no matching KG node stays
    honestly UNRESOLVED, and the event is correctly reported as not updated."""
    events, resolver, _population = _services(combined_session)
    event = await events.record(_unresolved_event("Some Obscure Nonexistent Club"))
    await combined_session.commit()

    results = await reresolve_all(events, resolver)

    assert results == {"events_checked": 1, "events_updated": 0, "entities_newly_resolved": 0}
    reloaded = await events.get(event.id)
    assert reloaded.resolved_entities[0].status is EntityResolutionStatus.UNRESOLVED
    assert reloaded.affected_entity_refs == ()


async def test_skips_an_event_with_no_unresolved_entities(combined_session):
    events, resolver, population = _services(combined_session)
    team_node = await population.populate_team("team-1", "football", T0, name="Arsenal")
    await combined_session.commit()

    already_resolved = NewsEvent(
        id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="A player was injured.",
        confidence=0.8, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
        occurred_at=T0, detected_at=T0,
        resolved_entities=(ResolvedNewsEntity(ref=str(team_node.id), node_type="team", status=EntityResolutionStatus.RESOLVED),),
        affected_entity_refs=(str(team_node.id),),
    )
    await events.record(already_resolved)
    await combined_session.commit()

    results = await reresolve_all(events, resolver)

    assert results == {"events_checked": 0, "events_updated": 0, "entities_newly_resolved": 0}


async def test_skips_a_mention_with_no_mapped_node_type(combined_session):
    """A mention whose original NER label never mapped to a known ontology member
    (`node_type=None`) has nothing to look up — skipped, never crashed on, never guessed."""
    events, resolver, _population = _services(combined_session)
    event = await events.record(_unresolved_event("Something Unclassified", node_type=None))
    await combined_session.commit()

    results = await reresolve_all(events, resolver)

    assert results == {"events_checked": 1, "events_updated": 0, "entities_newly_resolved": 0}


async def test_partial_resolution_updates_only_the_matchable_entities(combined_session):
    """A real event mentioning several entities (team + an unpopulated node type like coach)
    resolves whichever now-matchable entities it can, honestly leaving the rest unresolved —
    `is_feature_eligible()` still correctly requires ALL of them before it's usable downstream,
    this script's own job is only to give resolution every fair, real chance."""
    events, resolver, population = _services(combined_session)
    team_node = await population.populate_team("team-1", "football", T0, name="Chelsea")
    await combined_session.commit()

    event = NewsEvent(
        id=NewsEventId(uuid4()), event_type=NewsEventType.MANAGER_CHANGE, summary="A manager change occurred.",
        confidence=0.8, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
        occurred_at=T0, detected_at=T0,
        resolved_entities=(
            ResolvedNewsEntity(ref="Chelsea", node_type="team", status=EntityResolutionStatus.UNRESOLVED),
            ResolvedNewsEntity(ref="Some New Manager", node_type="coach", status=EntityResolutionStatus.UNRESOLVED),
        ),
    )
    await events.record(event)
    await combined_session.commit()

    results = await reresolve_all(events, resolver)
    await combined_session.commit()

    assert results == {"events_checked": 1, "events_updated": 1, "entities_newly_resolved": 1}
    reloaded = await events.get(event.id)
    statuses = {e.ref: e.status for e in reloaded.resolved_entities}
    assert statuses[str(team_node.id)] is EntityResolutionStatus.RESOLVED
    assert statuses["Some New Manager"] is EntityResolutionStatus.UNRESOLVED
    assert reloaded.affected_entity_refs == (str(team_node.id),)


async def test_running_twice_is_idempotent(combined_session):
    events, resolver, population = _services(combined_session)
    await population.populate_team("team-1", "football", T0, name="Manchester City")
    await combined_session.commit()
    await events.record(_unresolved_event("Manchester City"))
    await combined_session.commit()

    first = await reresolve_all(events, resolver)
    await combined_session.commit()
    second = await reresolve_all(events, resolver)

    assert first["events_updated"] == 1
    assert second == {"events_checked": 0, "events_updated": 0, "entities_newly_resolved": 0}

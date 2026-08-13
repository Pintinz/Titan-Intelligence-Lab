from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.intelligence.application.entity_extraction_service import EntityExtractionService
from modules.intelligence.application.event_extraction_service import EventExtractionService
from modules.intelligence.domain.value_objects import NewsArticleId, NewsEventType, NewsSourceId
from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemyNewsEventRepository
from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


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


def _service(session, adapter=None):
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    resolution = EntityResolutionService(nodes=nodes, edges=edges, population=population)
    text_intelligence = adapter or MockGeminiAdapter()
    entity_extraction = EntityExtractionService(text_intelligence=text_intelligence, entity_resolution=resolution)
    events = SqlAlchemyNewsEventRepository(session=session)
    return EventExtractionService(text_intelligence=text_intelligence, entity_extraction=entity_extraction, events=events), population


async def test_extract_and_record_persists_detected_events(combined_session):
    service, _population = _service(combined_session)

    recorded = await service.extract_and_record(
        "Star striker suffers hamstring injury in training.",
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, now=T0,
    )
    await combined_session.commit()

    assert len(recorded) == 1
    assert recorded[0].event_type == NewsEventType.INJURY
    assert recorded[0].confidence == 0.7
    assert recorded[0].detected_at == T0


async def test_extract_and_record_returns_empty_for_no_events(combined_session):
    service, _population = _service(combined_session)

    recorded = await service.extract_and_record(
        "Fans gathered outside the ground before kickoff.",
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, now=T0,
    )

    assert recorded == []


async def test_extract_and_record_keeps_affected_entity_refs_resolved_only(combined_session):
    """Milestone 9 fix: `affected_entity_refs` must never leak an unresolved provider-side entity
    mention (e.g. MockGeminiAdapter.extract_events's literal "mock_player"/"mock_team" tags,
    which come from a separate NLP call than entity resolution and were never actually resolved
    against the Knowledge Graph) — only genuinely KG-resolved refs belong there. `resolved_entities`
    is the new status-aware field, populated exclusively from `EntityExtractionService.extract_and_link`
    (real NER + alias resolution), independent of `extract_events`'s raw entity tags."""
    from modules.intelligence.domain.value_objects import EntityResolutionStatus

    service, population = _service(combined_session)
    await population.upsert_node(NodeType.TEAM, "man_city", now=T0, aliases=["Manchester City"])
    await combined_session.commit()

    recorded = await service.extract_and_record(
        "Manchester City confirms the transfer signing of a new midfielder.",
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, now=T0,
    )
    await combined_session.commit()

    transfer_event = next(e for e in recorded if e.event_type == NewsEventType.TRANSFER)
    # The raw, never-KG-resolved mock entity tags must NOT appear anywhere on the event — they
    # never enter the resolution pipeline at all now, not even as UNRESOLVED.
    assert "mock_player" not in transfer_event.affected_entity_refs
    assert "mock_team" not in transfer_event.affected_entity_refs
    assert all(e.ref not in ("mock_player", "mock_team") for e in transfer_event.resolved_entities)

    # The real NER hit ("Manchester City", resolved via alias) is the only entry, and it's RESOLVED.
    assert len(transfer_event.resolved_entities) == 1
    resolved_entity = transfer_event.resolved_entities[0]
    assert resolved_entity.status is EntityResolutionStatus.RESOLVED
    assert transfer_event.affected_entity_refs == (resolved_entity.ref,)


async def test_extract_and_record_skips_unrecognized_event_type(combined_session):
    class _WeirdEventAdapter(MockGeminiAdapter):
        async def extract_events(self, text):
            from modules.intelligence.ports.text_intelligence_provider import ExtractedEvent

            return [ExtractedEvent(event_type="not_a_real_type", summary="x", entities=(), confidence=0.5)]

    service, _population = _service(combined_session, _WeirdEventAdapter())

    recorded = await service.extract_and_record(
        "Some text.", source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, now=T0
    )

    assert recorded == []


async def test_extract_and_record_normalizes_aliased_event_type(combined_session):
    class _SigningAdapter(MockGeminiAdapter):
        async def extract_events(self, text):
            from modules.intelligence.ports.text_intelligence_provider import ExtractedEvent

            return [ExtractedEvent(event_type="signing", summary="x", entities=("mock_player",), confidence=0.6)]

    service, _population = _service(combined_session, _SigningAdapter())

    recorded = await service.extract_and_record(
        "Some text.", source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, now=T0
    )

    assert recorded[0].event_type == NewsEventType.TRANSFER

from __future__ import annotations

from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.intelligence.application.entity_extraction_service import EntityExtractionService
from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
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


def _service(kg_session, adapter=None):
    nodes = SqlAlchemyKGNodeRepository(session=kg_session)
    edges = SqlAlchemyKGEdgeRepository(session=kg_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    resolution = EntityResolutionService(nodes=nodes, edges=edges, population=population)
    return EntityExtractionService(text_intelligence=adapter or MockGeminiAdapter(), entity_resolution=resolution), population


async def test_extract_and_link_resolves_known_alias(kg_session):
    service, population = _service(kg_session)
    await population.upsert_node(NodeType.TEAM, "manchester_city", now=T0, aliases=["Manchester City"])
    await kg_session.commit()

    resolved = await service.extract_and_link("Manchester City won the match convincingly.")

    match = next(r for r in resolved if r.text == "Manchester City")
    assert match.node_type is NodeType.TEAM
    assert match.kg_node_id is not None


async def test_extract_and_link_leaves_unresolved_mention_unlinked(kg_session):
    service, _population = _service(kg_session)

    resolved = await service.extract_and_link("Erling Haaland scored for Manchester City.")

    match = next(r for r in resolved if r.text == "Erling Haaland")
    assert match.kg_node_id is None  # never populated in the graph, so no alias to match


async def test_extract_and_link_unknown_entity_type_skips_resolution(kg_session):
    class _UnknownTypeAdapter(MockGeminiAdapter):
        async def extract_entities(self, text):
            from modules.intelligence.ports.text_intelligence_provider import ExtractedEntity

            return [ExtractedEntity(text="Something", entity_type="unknown", confidence=0.5)]

    service, _population = _service(kg_session, _UnknownTypeAdapter())

    resolved = await service.extract_and_link("Something happened.")

    assert resolved[0].node_type is None
    assert resolved[0].kg_node_id is None


async def test_extract_and_link_returns_empty_for_no_entities(kg_session):
    service, _population = _service(kg_session)

    resolved = await service.extract_and_link("The weather was pleasant during the match.")

    assert resolved == []

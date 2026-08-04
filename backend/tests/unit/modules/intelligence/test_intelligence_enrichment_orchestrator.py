from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.value_objects import EntityType, FeatureKey
from modules.intelligence.application.entity_extraction_service import EntityExtractionService
from modules.intelligence.application.event_extraction_service import EventExtractionService
from modules.intelligence.application.feature_store_enrichment_service import FeatureStoreEnrichmentService
from modules.intelligence.application.intelligence_enrichment_orchestrator import IntelligenceEnrichmentOrchestrator
from modules.intelligence.application.news_impact_engine import NewsImpactEngine
from modules.intelligence.application.source_reliability_service import SourceReliabilityService
from modules.intelligence.domain.entities import NewsArticle, NewsSource
from modules.intelligence.domain.value_objects import NewsArticleId, NewsSourceId, NewsSourceType
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyImpactScoreRepository,
    SqlAlchemyNewsEventRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemySentimentResultRepository,
    SqlAlchemySourceReliabilityRepository,
)
from modules.intelligence.ports.text_intelligence_provider import ExtractedEvent
from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from tests.unit.modules.features.conftest import (
    InMemoryFeatureDefinitionRepository,
    InMemoryFeatureLineageRepository,
    InMemoryFeatureValueRepository,
    InMemoryFeatureVersionRepository,
    InMemoryOnlineFeatureStore,
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


@dataclass
class _FixedEventAdapter:
    """Returns exactly one canned event per test — real event-type/entity control that
    MockGeminiAdapter's keyword heuristic can't give (it returns fixed literal refs like
    "mock_team", never a resolvable Knowledge Graph node id)."""

    event_type: str
    entities: tuple[str, ...]
    confidence: float = 0.7
    provider_key: str = "gemini"

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        return [ExtractedEvent(event_type=self.event_type, summary=f"{self.event_type} event", entities=self.entities, confidence=self.confidence)]

    async def summarize(self, text, *, max_words=120) -> str:
        return text

    async def explain(self, context) -> str:
        return ""

    async def interpret_sentiment(self, text) -> str:
        return "neutral"

    async def extract_entities(self, text):
        return []

    async def extract_relationships(self, text):
        return []

    async def classify_topics(self, text):
        return []

    async def detect_language(self, text) -> str:
        return "en"

    async def extract_key_phrases(self, text, *, limit=5):
        return []


def _feature_store_enrichment() -> FeatureStoreEnrichmentService:
    definitions = InMemoryFeatureDefinitionRepository()
    lineage_service = FeatureLineageService(lineage=InMemoryFeatureLineageRepository(), definitions=definitions)
    registration = FeatureRegistrationService(
        definitions=definitions, versions=InMemoryFeatureVersionRepository(), lineage=lineage_service
    )
    store = FeatureStoreService(
        definitions=definitions, offline=InMemoryFeatureValueRepository(), online=InMemoryOnlineFeatureStore()
    )
    return FeatureStoreEnrichmentService(registration=registration, store=store)


async def _build_orchestrator(session, event_type: str, entity_refs: tuple[str, ...]) -> IntelligenceEnrichmentOrchestrator:
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    resolution = EntityResolutionService(nodes=nodes, edges=edges, population=population)
    adapter = _FixedEventAdapter(event_type=event_type, entities=entity_refs)
    entity_extraction = EntityExtractionService(text_intelligence=adapter, entity_resolution=resolution)
    event_extraction = EventExtractionService(
        text_intelligence=adapter, entity_extraction=entity_extraction, events=SqlAlchemyNewsEventRepository(session=session)
    )
    news_impact = NewsImpactEngine(
        impact_scores=SqlAlchemyImpactScoreRepository(session=session),
        sentiment_results=SqlAlchemySentimentResultRepository(session=session),
        kg_nodes=nodes,
    )
    source_reliability = SourceReliabilityService(reliability=SqlAlchemySourceReliabilityRepository(session=session))
    return IntelligenceEnrichmentOrchestrator(
        event_extraction=event_extraction,
        news_impact=news_impact,
        source_reliability=source_reliability,
        feature_store=_feature_store_enrichment(),
        sources=SqlAlchemyNewsSourceRepository(session=session),
    )


async def _seed_source_and_article(session, text: str) -> tuple[NewsSource, NewsArticle]:
    sources = SqlAlchemyNewsSourceRepository(session=session)
    source = await sources.upsert(
        NewsSource(id=NewsSourceId(uuid4()), source_type=NewsSourceType.RSS_FEED, name="Test Feed", url="https://example.com", created_at=T0)
    )
    article = NewsArticle(
        id=NewsArticleId(uuid4()), source_id=source.id, title="Headline", url="https://example.com/a",
        content_hash="hash", raw_text=text, published_at=T0, fetched_at=T0, version=1,
    )
    return source, article


async def test_injury_event_publishes_injury_impact_for_affected_players(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    player = await population.upsert_node(NodeType.PLAYER, "player-1", now=T0)
    await combined_session.commit()

    orchestrator = await _build_orchestrator(combined_session, "injury", (str(player.id),))
    _source, article = await _seed_source_and_article(combined_session, "Star striker suffers injury in training.")

    scores = await orchestrator.enrich_article(article, T0)
    await combined_session.commit()

    assert len(scores) == 1
    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.injury_impact"), EntityType.PLAYER, str(player.id))
    assert value is not None
    assert value.value == scores[0].impact_score


async def test_transfer_event_publishes_inverse_transfer_stability_for_affected_teams(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0)
    await combined_session.commit()

    orchestrator = await _build_orchestrator(combined_session, "transfer", (str(team.id),))
    _source, article = await _seed_source_and_article(combined_session, "Club confirms new signing.")

    scores = await orchestrator.enrich_article(article, T0)
    await combined_session.commit()

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.transfer_stability"), EntityType.TEAM, str(team.id))
    assert value is not None
    assert value.value == 1.0 - scores[0].impact_score


async def test_manager_change_event_publishes_inverse_manager_stability(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0)
    await combined_session.commit()

    orchestrator = await _build_orchestrator(combined_session, "manager_change", (str(team.id),))
    _source, article = await _seed_source_and_article(combined_session, "Manager sacked after poor run.")

    scores = await orchestrator.enrich_article(article, T0)
    await combined_session.commit()

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.manager_stability"), EntityType.TEAM, str(team.id))
    assert value is not None
    assert value.value == 1.0 - scores[0].impact_score


async def test_travel_delay_event_publishes_travel_fatigue(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0)
    await combined_session.commit()

    orchestrator = await _build_orchestrator(combined_session, "travel_delay", (str(team.id),))
    _source, article = await _seed_source_and_article(combined_session, "Squad hit by flight delay.")

    scores = await orchestrator.enrich_article(article, T0)
    await combined_session.commit()

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.travel_fatigue"), EntityType.TEAM, str(team.id))
    assert value is not None
    assert value.value == scores[0].impact_score


async def test_affected_team_receives_source_reliability_regardless_of_event_type(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0)
    await combined_session.commit()

    orchestrator = await _build_orchestrator(combined_session, "transfer", (str(team.id),))
    _source, article = await _seed_source_and_article(combined_session, "Club confirms new signing.")

    await orchestrator.enrich_article(article, T0)
    await combined_session.commit()

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.source_reliability"), EntityType.TEAM, str(team.id))
    assert value is not None
    assert value.value == 0.5  # SourceReliabilityService default before any recorded outcome


async def test_event_type_without_a_wired_feature_publishes_nothing_for_that_dimension(combined_session):
    """weather_report has no honest entity-resolution path (venue refs aren't resolved anywhere
    in this pipeline) — must publish nothing under weather_impact rather than fabricate a ref."""
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0)
    await combined_session.commit()

    orchestrator = await _build_orchestrator(combined_session, "weather_report", (str(team.id),))
    _source, article = await _seed_source_and_article(combined_session, "Heavy rain forecast for the match.")

    scores = await orchestrator.enrich_article(article, T0)
    await combined_session.commit()

    assert len(scores) == 1  # the event and its impact score are still real and recorded
    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.weather_impact"), EntityType.VENUE, str(team.id))
    assert value is None


async def test_no_extractable_event_returns_empty_and_publishes_nothing(combined_session):
    orchestrator = await _build_orchestrator(combined_session, "training_update", ())
    _source, article = await _seed_source_and_article(combined_session, "Fans gathered outside the ground.")

    class _NoEventAdapter(_FixedEventAdapter):
        async def extract_events(self, text):
            return []

    orchestrator.event_extraction.text_intelligence = _NoEventAdapter(event_type="training_update", entities=())
    orchestrator.event_extraction.entity_extraction.text_intelligence = orchestrator.event_extraction.text_intelligence

    scores = await orchestrator.enrich_article(article, T0)

    assert scores == []

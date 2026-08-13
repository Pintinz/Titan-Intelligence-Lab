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
from modules.intelligence.domain.value_objects import NewsArticleId, NewsSourceId, NewsSourceType, SyncTrigger
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyImpactScoreRepository,
    SqlAlchemyNewsEventRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemySentimentResultRepository,
    SqlAlchemySourceReliabilityRepository,
)
from modules.intelligence.ports.text_intelligence_provider import ExtractedEntity, ExtractedEvent
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
    "mock_team", never a resolvable Knowledge Graph node id).

    Milestone 9: `EventExtractionService.extract_and_record` now populates `resolved_entities`
    (and, from it, `affected_entity_refs`) exclusively from `EntityExtractionService.extract_and_link`
    — i.e. from this adapter's `extract_entities`, not from `extract_events`'s `entities` tuple.
    `mention_text`/`mention_type` let a test provide a real NER-style mention that resolves
    against a Knowledge Graph node registered with a matching alias, so `entity_refs` (used for
    Feature Store lookups) still ends up populated the same way real resolution would."""

    event_type: str
    entities: tuple[str, ...]
    confidence: float = 0.7
    provider_key: str = "gemini"
    mention_text: str | None = None
    mention_type: str | None = None

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        return [ExtractedEvent(event_type=self.event_type, summary=f"{self.event_type} event", entities=self.entities, confidence=self.confidence)]

    async def summarize(self, text, *, max_words=120) -> str:
        return text

    async def explain(self, context) -> str:
        return ""

    async def interpret_sentiment(self, text) -> str:
        return "neutral"

    async def extract_entities(self, text):
        if self.mention_text is None:
            return []
        return [ExtractedEntity(text=self.mention_text, entity_type=self.mention_type or "unknown", confidence=0.8)]

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


async def _build_orchestrator(
    session, event_type: str, entity_refs: tuple[str, ...], *,
    mention_text: str | None = None, mention_type: str | None = None,
) -> IntelligenceEnrichmentOrchestrator:
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    resolution = EntityResolutionService(nodes=nodes, edges=edges, population=population)
    adapter = _FixedEventAdapter(
        event_type=event_type, entities=entity_refs, mention_text=mention_text, mention_type=mention_type
    )
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
        events=SqlAlchemyNewsEventRepository(session=session),
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
    """Milestone 9: feature publishing is gated on `NewsEvent.is_feature_eligible()`, which
    requires VERIFIED_PRE_MATCH availability — only reachable via `SyncTrigger.LIVE_SCHEDULED`
    (a genuine, non-backfilled automatic sync). Explicitly passed here to exercise the eligible
    path this test is actually about."""
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    player = await population.upsert_node(NodeType.PLAYER, "player-1", now=T0, aliases=["Test Player"])
    await combined_session.commit()

    orchestrator = await _build_orchestrator(
        combined_session, "injury", (str(player.id),), mention_text="Test Player", mention_type="player"
    )
    _source, article = await _seed_source_and_article(combined_session, "Star striker suffers injury in training.")

    scores = await orchestrator.enrich_article(article, T0, trigger=SyncTrigger.LIVE_SCHEDULED)
    await combined_session.commit()

    assert len(scores) == 1
    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.injury_impact"), EntityType.PLAYER, str(player.id))
    assert value is not None
    assert value.value == scores[0].impact_score


async def test_transfer_event_publishes_inverse_transfer_stability_for_affected_teams(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0, aliases=["Test Team"])
    await combined_session.commit()

    orchestrator = await _build_orchestrator(
        combined_session, "transfer", (str(team.id),), mention_text="Test Team", mention_type="team"
    )
    _source, article = await _seed_source_and_article(combined_session, "Club confirms new signing.")

    scores = await orchestrator.enrich_article(article, T0, trigger=SyncTrigger.LIVE_SCHEDULED)
    await combined_session.commit()

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.transfer_stability"), EntityType.TEAM, str(team.id))
    assert value is not None
    assert value.value == 1.0 - scores[0].impact_score


async def test_manager_change_event_publishes_inverse_manager_stability(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0, aliases=["Test Team"])
    await combined_session.commit()

    orchestrator = await _build_orchestrator(
        combined_session, "manager_change", (str(team.id),), mention_text="Test Team", mention_type="team"
    )
    _source, article = await _seed_source_and_article(combined_session, "Manager sacked after poor run.")

    scores = await orchestrator.enrich_article(article, T0, trigger=SyncTrigger.LIVE_SCHEDULED)
    await combined_session.commit()

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.manager_stability"), EntityType.TEAM, str(team.id))
    assert value is not None
    assert value.value == 1.0 - scores[0].impact_score


async def test_travel_delay_event_publishes_travel_fatigue(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0, aliases=["Test Team"])
    await combined_session.commit()

    orchestrator = await _build_orchestrator(
        combined_session, "travel_delay", (str(team.id),), mention_text="Test Team", mention_type="team"
    )
    _source, article = await _seed_source_and_article(combined_session, "Squad hit by flight delay.")

    scores = await orchestrator.enrich_article(article, T0, trigger=SyncTrigger.LIVE_SCHEDULED)
    await combined_session.commit()

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.travel_fatigue"), EntityType.TEAM, str(team.id))
    assert value is not None
    assert value.value == scores[0].impact_score


async def test_affected_team_receives_source_reliability_regardless_of_event_type(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0, aliases=["Test Team"])
    await combined_session.commit()

    orchestrator = await _build_orchestrator(
        combined_session, "transfer", (str(team.id),), mention_text="Test Team", mention_type="team"
    )
    _source, article = await _seed_source_and_article(combined_session, "Club confirms new signing.")

    await orchestrator.enrich_article(article, T0, trigger=SyncTrigger.LIVE_SCHEDULED)
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


async def test_backfill_trigger_persists_unknown_availability_through_the_real_pipeline(combined_session):
    """Milestone 12 — the production-path proof, not just the isolated `classify_news_availability`
    unit tests: runs a BACKFILL-triggered article through the REAL orchestrator (real
    EventExtractionService, real EntityExtractionService, real NewsImpactEngine, real Knowledge
    Graph resolution — only the outermost Gemini-equivalent text-intelligence adapter is faked,
    same seam every other test in this file already uses) and reads the persisted `NewsEvent`
    back from the real repository to confirm its `availability_classification` genuinely landed
    at UNKNOWN_AVAILABILITY_TIME, and that no feature was published under the gated
    (VERIFIED_PRE_MATCH-only) publish path."""
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    player = await population.upsert_node(NodeType.PLAYER, "player-1", now=T0, aliases=["Test Player"])
    await combined_session.commit()

    orchestrator = await _build_orchestrator(
        combined_session, "injury", (str(player.id),), mention_text="Test Player", mention_type="player"
    )
    _source, article = await _seed_source_and_article(combined_session, "Star striker suffers injury in training.")

    scores = await orchestrator.enrich_article(article, T0, trigger=SyncTrigger.BACKFILL)
    await combined_session.commit()

    # The event and its impact score are still real and recorded (raw intelligence is never
    # discarded) — what's gated is Feature Store *publishing*, checked below.
    assert len(scores) == 1

    events = SqlAlchemyNewsEventRepository(session=combined_session)
    persisted = await events.list_for_entity(str(player.id))
    assert len(persisted) == 1
    assert persisted[0].availability_classification == "UNKNOWN_AVAILABILITY_TIME"
    assert persisted[0].information_available_at is None
    assert persisted[0].is_feature_eligible() is False

    value = await orchestrator.feature_store.store.online.get(FeatureKey("intelligence.injury_impact"), EntityType.PLAYER, str(player.id))
    assert value is None

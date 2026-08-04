"""One-off backfill: runs `IntelligenceEnrichmentOrchestrator.enrich_article()` over every
`NewsArticle` already in the database.

Audit finding (2026-08-02): the orchestrator that turns an ingested article into structured
`NewsEvent`s (and downstream Feature Store entries) was only wired into the real news-sync
endpoint (`POST /api/v1/admin/news/sources/{id}/sync`) as part of today's fix — every article
ingested by the three sync runs that happened before that wiring landed was never enriched, so
`news_events` stayed empty (0 rows) despite 94 real articles existing in `news_articles`. That in
turn kept `ConfidenceEngine`'s `news_reliability` factor pinned at its neutral 0.5 default for
every prediction (docs: `PredictionEngine`'s confidence composite). Sync is wired correctly for
every article ingested from now on; this script is only needed once, to catch up the backlog.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_news_event_extraction.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import (
    build_feature_store_enrichment_service,
    build_news_ingestion_service,
    build_news_impact_engine,
    build_source_reliability_service,
    get_engine,
)
from modules.intelligence.application.entity_extraction_service import EntityExtractionService
from modules.intelligence.application.event_extraction_service import EventExtractionService
from modules.intelligence.application.intelligence_enrichment_orchestrator import IntelligenceEnrichmentOrchestrator
from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemyNewsEventRepository, SqlAlchemyNewsSourceRepository
from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.infrastructure.persistence.repositories import SqlAlchemyKGEdgeRepository, SqlAlchemyKGNodeRepository


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        news = build_news_ingestion_service(session)
        # Uses the deterministic MockGeminiAdapter directly rather than the credentialed
        # TextIntelligenceRouter: real Gemini is currently 429 quota-exhausted (would fail every
        # call anyway after a real network round-trip), and the router would fall back to this
        # exact same mock regardless — going straight to it avoids ~94 articles worth of pointless
        # timeout latency for a one-off local backfill.
        mock = MockGeminiAdapter()
        nodes = SqlAlchemyKGNodeRepository(session=session)
        edges = SqlAlchemyKGEdgeRepository(session=session)
        entity_resolution = EntityResolutionService(
            nodes=nodes, edges=edges, population=KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
        )
        orchestrator = IntelligenceEnrichmentOrchestrator(
            event_extraction=EventExtractionService(
                text_intelligence=mock,
                entity_extraction=EntityExtractionService(text_intelligence=mock, entity_resolution=entity_resolution),
                events=SqlAlchemyNewsEventRepository(session=session),
            ),
            news_impact=build_news_impact_engine(session),
            source_reliability=build_source_reliability_service(session),
            feature_store=build_feature_store_enrichment_service(session),
            sources=SqlAlchemyNewsSourceRepository(session=session),
        )

        articles = await news.articles.list_since(now - timedelta(days=3650), limit=10_000)
        print(f"Found {len(articles)} articles to backfill.")

        total_events = 0
        for i, article in enumerate(articles, start=1):
            scores = await orchestrator.enrich_article(article, now)
            total_events += len(scores)
            if i % 20 == 0:
                print(f"...{i}/{len(articles)} processed, {total_events} events so far")

        await session.commit()
        print(f"Done. {len(articles)} articles processed, {total_events} events extracted and feature-scored.")


if __name__ == "__main__":
    asyncio.run(main())

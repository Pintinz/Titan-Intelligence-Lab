"""Intelligence -> Feature Store Enrichment Orchestrator.

Audit finding (2026-08-02): `EventExtractionService`, `NewsImpactEngine`, `SourceReliabilityService`,
and `FeatureStoreEnrichmentService` are each real, independently correct, and independently
tested — but nothing in production ever called them in sequence. `NewsImpactEngine.score()` had
zero real call sites outside its own tests; `FeatureStoreEnrichmentService.publish_*()` had zero
real call sites at all. This orchestrator is the missing wire: given a newly-ingested
`NewsArticle`, it extracts events, scores their real-world impact, and publishes exactly the
Feature Store entries that can be honestly derived from a single event — never a fabricated
entity resolution.

Deliberately scoped to four of `FeatureStoreEnrichmentService.FEATURE_CATALOG`'s ten entries —
the ones with a direct, real, one-event-to-one-feature mapping and a correctly-typed entity ref
already resolved by `NewsImpactEngine._categorize_affected` (which classifies Knowledge Graph
node refs into teams/players/competitions):

- INJURY event -> ``injury_impact`` per affected player.
- TRANSFER event -> ``transfer_stability`` (inverse of impact — high transfer disruption means
  low stability) per affected team.
- MANAGER_CHANGE event -> ``manager_stability`` (inverse, same reasoning) per affected team.
- TRAVEL_DELAY event -> ``travel_fatigue`` per affected team.

Plus ``source_reliability`` per affected team, from the article's own source (real EWMA-tracked
score, `SourceReliabilityService`).

Explicitly NOT wired here, and why: ``weather_impact``'s catalog entry is typed `EntityType.VENUE`,
but nothing in this pipeline resolves a venue ref from event text — passing a team/player ref
under a venue-typed feature key would be a real fabrication, not an honest substitution.
``squad_availability`` (fraction of a full roster without an open concern) and ``media_pressure``
(volume-weighted attention) both need aggregation across many events/articles, not one — a
different, aggregate-computing service's job, not this orchestrator's. ``community_momentum`` and
``news_momentum`` belong to `SentimentService`'s momentum output, not `NewsImpactEngine`'s impact
score — wiring those is a related but separate gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.intelligence.application.event_extraction_service import EventExtractionService
from modules.intelligence.application.feature_store_enrichment_service import FeatureStoreEnrichmentService
from modules.intelligence.application.news_impact_engine import NewsImpactEngine
from modules.intelligence.application.source_reliability_service import SourceReliabilityService
from modules.intelligence.domain.entities import ImpactScore, NewsArticle, NewsEvent
from modules.intelligence.domain.value_objects import NewsEventType
from modules.intelligence.ports.repositories import NewsSourceRepositoryPort


@dataclass
class IntelligenceEnrichmentOrchestrator:
    event_extraction: EventExtractionService
    news_impact: NewsImpactEngine
    source_reliability: SourceReliabilityService
    feature_store: FeatureStoreEnrichmentService
    sources: NewsSourceRepositoryPort

    async def enrich_article(self, article: NewsArticle, now: datetime) -> list[ImpactScore]:
        """Extracts events from a newly-ingested article, scores each event's real-world impact,
        and publishes every Feature Store entry that can be honestly derived from it. Returns the
        recorded `ImpactScore`s (empty if the article named no extractable event)."""
        events = await self.event_extraction.extract_and_record(
            article.raw_text, article.source_id, article.id, article.published_at, now
        )
        if not events:
            return []

        # Idempotent (checks existing before registering) — safe, and necessary, on every run:
        # FeatureStoreService.write() raises FeatureNotFoundError for an unregistered key.
        await self.feature_store.ensure_registered(now)

        source = await self.sources.get(article.source_id)
        reliability_score = None
        if source is not None:
            reliability_score = (await self.source_reliability.get_or_initialize(source, now)).reliability_score

        scores: list[ImpactScore] = []
        for event in events:
            score = await self.news_impact.score(event, now)
            scores.append(score)
            await self._publish_event_features(event, score, reliability_score, now)
        return scores

    async def _publish_event_features(
        self, event: NewsEvent, score: ImpactScore, reliability_score: float | None, now: datetime
    ) -> None:
        if event.event_type is NewsEventType.INJURY:
            for player_ref in score.affected_players:
                await self.feature_store.publish_injury_impact(player_ref, score.impact_score, now)
        elif event.event_type is NewsEventType.TRANSFER:
            for team_ref in score.affected_teams:
                await self.feature_store.publish_transfer_stability(team_ref, 1.0 - score.impact_score, now)
        elif event.event_type is NewsEventType.MANAGER_CHANGE:
            for team_ref in score.affected_teams:
                await self.feature_store.publish_manager_stability(team_ref, 1.0 - score.impact_score, now)
        elif event.event_type is NewsEventType.TRAVEL_DELAY:
            for team_ref in score.affected_teams:
                await self.feature_store.publish_travel_fatigue(team_ref, score.impact_score, now)

        if reliability_score is not None:
            for team_ref in score.affected_teams:
                await self.feature_store.publish_source_reliability(team_ref, reliability_score, now)

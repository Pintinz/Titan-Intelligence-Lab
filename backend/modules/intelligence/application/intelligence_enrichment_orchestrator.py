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

Milestone 9 addition: every extracted event is now classified (formal `NewsEventConfidenceTier`
taxonomy, `information_available_at`/`availability_classification` provenance) and re-persisted
*before* any feature gets published — `_publish_event_features` now only fires for an event that
passes `NewsEvent.is_feature_eligible()` (VERIFIED_PRE_MATCH provenance AND every required entity
genuinely resolved), closing the exact gap the spec names: "News features must only influence
production predictions if their provenance requirements are satisfied." `trigger` defaults to
MANUAL, matching this orchestrator's only real caller today (the admin manual-sync endpoint,
`apps/api/main.py`'s `trigger_news_sync`) — no Celery Beat schedule exists for news yet
(deliberately deferred, see docs/milestone9_verification_report.md), so every event extracted via
the real pipeline today correctly lands at `UNKNOWN_AVAILABILITY_TIME`, not fabricated as verified
merely because a real (non-mock) provider produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.intelligence.application.event_extraction_service import EventExtractionService
from modules.intelligence.application.feature_store_enrichment_service import FeatureStoreEnrichmentService
from modules.intelligence.application.news_impact_engine import NewsImpactEngine
from modules.intelligence.application.news_provenance import (
    ConfidenceInputs,
    NewsEventConfidenceClassifier,
    classify_news_availability,
)
from modules.intelligence.application.news_validity_policy import validity_window_hours
from modules.intelligence.application.source_reliability_service import SourceReliabilityService
from modules.intelligence.domain.entities import ImpactScore, NewsArticle, NewsEvent
from modules.intelligence.domain.value_objects import EntityResolutionStatus, NewsEventType, SyncTrigger, TrustLevel
from modules.intelligence.ports.repositories import NewsEventRepositoryPort, NewsSourceRepositoryPort

# A conflicting-report signal this orchestrator can honestly detect today without an NLP
# opposition model: another event of a *directly opposed* type for the same resolved entity
# within the window (e.g. an "OUT" injury report and a "returns to training" recovery report for
# the same player). Deliberately narrow — the only pair in `NewsEventType` with an unambiguous,
# real opposite; broader same-claim-conflicting-details detection needs real NLP comparison, not
# fabricated here (see docs/milestone9_verification_report.md's Known limitations).
_OPPOSED_EVENT_TYPES: dict[NewsEventType, NewsEventType] = {
    NewsEventType.INJURY: NewsEventType.RECOVERY,
    NewsEventType.RECOVERY: NewsEventType.INJURY,
}


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """Same fix as the three other duplicates in this codebase (SQLite drops tzinfo on
    read-back, docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class IntelligenceEnrichmentOrchestrator:
    event_extraction: EventExtractionService
    news_impact: NewsImpactEngine
    source_reliability: SourceReliabilityService
    feature_store: FeatureStoreEnrichmentService
    sources: NewsSourceRepositoryPort
    events: NewsEventRepositoryPort

    async def enrich_article(
        self, article: NewsArticle, now: datetime, *,
        trigger: SyncTrigger = SyncTrigger.MANUAL, sync_run_id: str | None = None,
    ) -> list[ImpactScore]:
        """Extracts events from a newly-ingested article, classifies each event's formal
        confidence tier and point-in-time provenance, scores real-world impact, and publishes
        every Feature Store entry that can be honestly derived from it — gated on
        `NewsEvent.is_feature_eligible()`. Returns the recorded `ImpactScore`s (empty if the
        article named no extractable event).

        POST-M24 Phase 2: `NewsIngestionService`'s content-hash dedup already stops the same
        article from being *ingested* twice, so this normally only ever runs once per article —
        but nothing previously stopped a second call to `enrich_article` for the same
        already-ingested article (an overlapping backfill/scheduled run, a retry after a partial
        failure downstream) from re-extracting via Gemini. Reuses this article's canonical
        identity (`NewsEvent.article_id`, already indexed) rather than inventing a second
        content-hash/dedup mechanism: if events already exist for this article, skip the Gemini
        call AND the classify/score/publish pipeline entirely, returning the already-recorded
        `ImpactScore`s instead — `ImpactScoreRepositoryPort.record` is insert-only (one row per
        `news_event_id`, enforced by a unique constraint), so re-running `_classify_and_persist`/
        `news_impact.score` a second time for an already-scored event would violate it, not
        harmlessly recompute the same values."""
        events = await self.events.list_for_article(article.id)
        if events:
            recorded = [await self.news_impact.impact_scores.get_for_event(event.id) for event in events]
            return [score for score in recorded if score is not None]

        events = await self.event_extraction.extract_and_record(
            article.raw_text, article.source_id, article.id, article.published_at, now
        )
        if not events:
            return []

        events = [
            await self._classify_and_persist(event, trigger, sync_run_id, now) for event in events
        ]

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
            if event.is_feature_eligible():
                await self._publish_event_features(event, score, reliability_score, now)
        return scores

    async def _classify_and_persist(
        self, event: NewsEvent, trigger: SyncTrigger, sync_run_id: str | None, now: datetime,
    ) -> NewsEvent:
        source = await self.sources.get(event.source_id)
        reliability = await self.source_reliability.get_or_initialize(source, now) if source is not None else None
        trust_level = reliability.trust_level if reliability is not None else TrustLevel.UNVERIFIED

        corroborating_source_count, contradicted = await self._corroboration(event)
        occurred_at = _ensure_aware(event.occurred_at, now)
        age_hours = max(0.0, (now - occurred_at).total_seconds() / 3600)
        ttl_hours = validity_window_hours(event.event_type)

        event.confidence_tier = NewsEventConfidenceClassifier.classify(
            ConfidenceInputs(
                event_type=event.event_type,
                is_official_source=source.is_official if source is not None else False,
                source_trust_level=trust_level,
                corroborating_source_count=corroborating_source_count,
                contradicted=contradicted,
                age_hours=age_hours,
                ttl_hours=float(ttl_hours),
            )
        )
        availability = classify_news_availability(
            trigger=trigger, sync_succeeded=True, validated=True,
            sync_time=now, published_at=event.occurred_at,
        )
        event.availability_classification = availability.classification.value
        event.information_available_at = availability.information_available_at
        event.validity_start = event.occurred_at
        event.validity_end = occurred_at + timedelta(hours=ttl_hours)
        event.sync_run_id = sync_run_id
        return await self.events.record(event)

    async def _corroboration(self, event: NewsEvent) -> tuple[int, bool]:
        """Real, deterministic corroboration/contradiction detection from already-persisted
        events sharing a resolved entity — no fabricated count, no NLP sentiment model."""
        opposed_type = _OPPOSED_EVENT_TYPES.get(event.event_type)
        other_source_ids: set[str] = set()
        contradicted = False
        for entity in event.resolved_entities:
            if entity.status is not EntityResolutionStatus.RESOLVED:
                continue
            related = await self.events.list_for_entity(entity.ref)
            for other in related:
                if other.id == event.id:
                    continue
                if other.event_type is event.event_type and other.source_id != event.source_id:
                    other_source_ids.add(str(other.source_id))
                if opposed_type is not None and other.event_type is opposed_type:
                    contradicted = True
        return len(other_source_ids), contradicted

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

"""Milestone 14 — connects the Milestone 13 historical news intelligence layer to real
market-specific historical feature reconstruction, at the smallest safe integration point.

The audit found that `NewsMarketImpactEngine` (Milestone 9/10) already implements almost
everything Phase 8 of this milestone asks for — event-eligible (`is_feature_eligible()`),
kickoff-gated (`is_information_available_before_kickoff`), market-specific (`MARKET_IMPACT_RULES`)
feature computation — with exactly one gap: its roster (`players.list_by_team`) was always
*current* team membership, never historically accurate. Milestone 14.1 closed that gap directly
inside `NewsMarketImpactEngine` (an additive `historical_reference_time` parameter, routed through
the Milestone 13 `HistoricalEntityResolutionService` — see that file's own docstring), so the
existing, unchanged, well-tested `compute_and_write`/`ensure_registered` machinery is already the
real publish path for a historical fixture. This module does not reimplement it.

This service adds the two things `NewsMarketImpactEngine` itself doesn't provide:

1. **Per-event auditability** (spec §8 item 7, §9, §10) — `NewsMarketImpactEngine.
   team_contributions` only ever returns an aggregate `(value, has_evidence)` per dimension; it
   cannot say *which* candidate events were considered or *why* an ineligible one was excluded.
   `audit_events_for_fixture` answers exactly that, using the Milestone 13
   `HistoricalNewsRelevanceEngine` (reused, never duplicated) for the classification and the
   unchanged `NewsEvent.is_feature_eligible()` for the authoritative provenance gate.
2. **A named publish entry point** (`publish_for_fixture`) — a thin, explicit passthrough to
   `NewsMarketImpactEngine.compute_and_write` for both sides of a historical fixture, so a future
   caller (e.g. a historical-training-data backfill script, out of this milestone's scope) has one
   obvious, safe function to call rather than needing to know `NewsMarketImpactEngine`'s internal
   parameter combination.

Neither method is wired into any live endpoint, Celery task, or training script by this milestone
— see the verification report's Known Limitations / Deferred Work sections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from modules.intelligence.application.historical_news_relevance_engine import (
    HistoricalFixtureContext,
    HistoricalNewsRelevanceEngine,
    HistoricalRelevanceClassification,
    HistoricalRelevanceResult,
)
from modules.intelligence.application.news_provenance import is_information_available_before_kickoff
from modules.intelligence.domain.entities import NewsEvent
from modules.predictions.application.news_market_impact_engine import NewsMarketImpactEngine
from modules.sports.domain.value_objects import FixtureId, TeamId


class NewsFeatureEligibility(str, Enum):
    """Milestone 14 §9's training-data-safety taxonomy — deliberately never collapsed into a
    bare boolean/None, so an ineligible event's reason stays auditable. A wholly separate
    dimension from `HistoricalRelevanceClassification` (Milestone 13) and
    `NewsAvailabilityClassification` (Milestone 9) — this one answers "would this specific event
    have contributed a published feature," folding in both of those upstream verdicts plus the
    final `is_feature_eligible()` gate, never replacing either."""

    NEWS_FEATURE_ELIGIBLE = "news_feature_eligible"
    NEWS_FEATURE_INELIGIBLE = "news_feature_ineligible"
    NEWS_ENTITY_UNRESOLVED = "news_entity_unresolved"
    NEWS_FIXTURE_UNRESOLVED = "news_fixture_unresolved"
    NEWS_MARKET_UNRESOLVED = "news_market_unresolved"


@dataclass(frozen=True)
class HistoricalFeatureReconstructionResult:
    """Full provenance for one (event, fixture) pair (spec §10) — every field traces to a real
    source, nothing fabricated. ``relevance`` embeds the complete Milestone 13
    `HistoricalRelevanceResult` (its own evidence trail, entity/membership/fixture/market
    resolution, reference_time) rather than flattening/duplicating it."""

    article_id: str
    news_event_id: str
    fixture_id: FixtureId
    availability_classification: str
    eligibility: NewsFeatureEligibility
    relevance: HistoricalRelevanceResult
    reasons: tuple[str, ...] = field(default_factory=tuple)


def _classify(
    event: NewsEvent, relevance: HistoricalRelevanceResult, fixture_context: HistoricalFixtureContext,
) -> tuple[NewsFeatureEligibility, tuple[str, ...]]:
    if relevance.classification is HistoricalRelevanceClassification.ENTITY_UNRESOLVED:
        return NewsFeatureEligibility.NEWS_ENTITY_UNRESOLVED, relevance.evidence
    if relevance.classification is HistoricalRelevanceClassification.HISTORICALLY_UNRESOLVED:
        return NewsFeatureEligibility.NEWS_FIXTURE_UNRESOLVED, relevance.evidence
    if relevance.classification is HistoricalRelevanceClassification.MARKET_UNRESOLVED:
        return NewsFeatureEligibility.NEWS_MARKET_UNRESOLVED, relevance.evidence
    if relevance.classification in (
        HistoricalRelevanceClassification.INSUFFICIENT_PROVENANCE,
        HistoricalRelevanceClassification.NOT_RELEVANT,
    ):
        return NewsFeatureEligibility.NEWS_FEATURE_INELIGIBLE, relevance.evidence

    # HISTORICALLY_RELEVANT — the M14 non-negotiable: relevance alone is never sufficient. Only
    # the existing, unchanged Milestone 9 `is_feature_eligible()` gate (VERIFIED_PRE_MATCH +
    # every entity resolved) can promote this to actually eligible.
    if not event.is_feature_eligible():
        return NewsFeatureEligibility.NEWS_FEATURE_INELIGIBLE, relevance.evidence + (
            f"historically relevant, but event.availability_classification="
            f"{event.availability_classification!r} is not VERIFIED_PRE_MATCH (or not every "
            "entity is resolved) — is_feature_eligible() is the authoritative gate, unchanged",
        )

    # Milestone 10's own fixture-specific rule, re-applied here so this audit's verdict never
    # diverges from what `NewsMarketImpactEngine.compute_and_write`'s own `kickoff` check would
    # actually publish: VERIFIED_PRE_MATCH is necessary but not sufficient — the information must
    # also genuinely predate *this* fixture's own kickoff, not just some fixture's.
    if event.information_available_at is not None and not is_information_available_before_kickoff(
        event.information_available_at, fixture_context.kickoff,
    ):
        return NewsFeatureEligibility.NEWS_FEATURE_INELIGIBLE, relevance.evidence + (
            f"information_available_at={event.information_available_at.isoformat()} is not "
            f"strictly before this fixture's kickoff ({fixture_context.kickoff.isoformat()})",
        )
    return NewsFeatureEligibility.NEWS_FEATURE_ELIGIBLE, relevance.evidence


@dataclass
class HistoricalFeatureReconstructionService:
    news_market_impact: NewsMarketImpactEngine
    relevance_engine: HistoricalNewsRelevanceEngine

    async def audit_events_for_fixture(
        self,
        fixture_context: HistoricalFixtureContext,
        candidate_events: list[NewsEvent],
        *,
        market_key: str | None = None,
    ) -> list[HistoricalFeatureReconstructionResult]:
        """Per-event auditability only — never writes to the Feature Store. Each event's own
        `information_available_at` (Milestone 9's field — `None` for every `BACKFILL`/
        `ADMIN_MANUAL` event today) is used as the historical reference time, matching Milestone
        13's documented default caller behavior; an event with no known availability time
        correctly reports `INSUFFICIENT_PROVENANCE` -> `NEWS_FEATURE_INELIGIBLE`, never guessed."""
        results = []
        for event in candidate_events:
            relevance = await self.relevance_engine.resolve_relevance(
                event, event.information_available_at, fixture_context, market_key=market_key,
            )
            eligibility, reasons = _classify(event, relevance, fixture_context)
            results.append(
                HistoricalFeatureReconstructionResult(
                    article_id=str(event.article_id.value),
                    news_event_id=str(event.id.value),
                    fixture_id=fixture_context.fixture_id,
                    availability_classification=event.availability_classification,
                    eligibility=eligibility,
                    relevance=relevance,
                    reasons=reasons,
                )
            )
        return results

    async def publish_for_fixture(
        self, fixture_id: FixtureId, home_team_id: TeamId, away_team_id: TeamId, historical_reference_time: datetime,
    ):
        """The only write path — a thin, explicit passthrough to the existing, unchanged
        `NewsMarketImpactEngine.compute_and_write` for both sides of a historical fixture.
        `historical_reference_time` is used for all three of `now`/`kickoff`/
        `historical_reference_time`: `now` so TTL/age checks are evaluated as of the historical
        moment (not today's wall clock, which would make every historical event look expired);
        `kickoff` so the existing post-kickoff exclusion applies; `historical_reference_time` so
        roster reconstruction routes through Transfer-chain resolution, never current
        `Player.team_id`. Writes nothing for a dimension with no feature-eligible evidence — the
        same "unavailable, not a fabricated zero" semantics `NewsMarketImpactEngine` already has."""
        written = []
        for side, team_id in (("home", home_team_id), ("away", away_team_id)):
            written.extend(
                await self.news_market_impact.compute_and_write(
                    str(fixture_id.value), team_id, side, historical_reference_time,
                    kickoff=historical_reference_time, historical_reference_time=historical_reference_time,
                )
            )
        return written

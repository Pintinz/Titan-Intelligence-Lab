"""Milestone 9 — News provenance + formal Event Confidence taxonomy.

Deliberately does NOT import `modules.ingestion.application.provenance` or
`modules.ingestion.domain.value_objects.SyncTrigger` — `modules.intelligence` has never depended
on `modules.ingestion` (see `IntelligenceSyncRun`'s own docstring: "Milestone 8 does not import
Milestone 5's sports-specific ingestion types"), and this milestone respects that existing
boundary rather than overriding it. What's reused is the *rule* — the exact 5-condition
"only a genuine automatic sync, with a genuine timestamp, can ever produce VERIFIED_PRE_MATCH"
logic `classify_availability` established and two milestones have already depended on — not the
type. Same deliberate-duplication posture already used for `_ensure_aware` in three other files
(`sync_orchestrator.py`, `data_quality_engine.py`, `windowed_feature_engineering_service.py`):
small, safety-critical, module-boundary-respecting duplication beats a cross-module dependency
for a handful of lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from modules.intelligence.domain.value_objects import NewsEventConfidenceTier, NewsEventType, SyncTrigger, TrustLevel


class NewsAvailabilityClassification(str, Enum):
    VERIFIED_PRE_MATCH = "VERIFIED_PRE_MATCH"
    UNKNOWN_AVAILABILITY_TIME = "UNKNOWN_AVAILABILITY_TIME"
    INVALID = "INVALID"


@dataclass(frozen=True)
class NewsAvailabilityResult:
    classification: NewsAvailabilityClassification
    information_available_at: datetime | None  # only ever non-None for VERIFIED_PRE_MATCH


def classify_news_availability(
    *,
    trigger: SyncTrigger,
    sync_succeeded: bool,
    validated: bool,
    sync_time: datetime,
    published_at: datetime,
    has_genuine_timestamp: bool = True,
) -> NewsAvailabilityResult:
    """The single choke point every news reconciliation call routes through — mirrors
    `modules.ingestion.application.provenance.classify_availability`'s exact rule, adapted to
    news's simpler shape: not fixture-bound (no kickoff/prematch-window gate, same reasoning as
    `Transfer` — a news event affects a team/player across every future fixture, not one
    specific match), so no `EXPIRED`/`POST_MATCH` classification here (those apply once real
    "no longer relevant" logic exists — see `NewsEventConfidenceTier.EXPIRED`, a distinct,
    validity-window-driven concept handled by `NewsEventConfidenceClassifier` instead).

    `has_genuine_timestamp` defaults True (RSS `published_at` is a real provider-supplied
    timestamp — same trust model Milestone 5 already applied to `Transfer.effective_date`); pass
    False for any source whose publish timestamp cannot be trusted (mirrors injuries' hardcoded
    False in `modules.ingestion.application.entity_reconciliation_service.reconcile_injury` —
    "no provider adapter supplies a real report timestamp" is the exact same failure mode this
    guards against here).

    ``information_available_at`` is always ``published_at`` when verified — never `detected_at`/
    `fetched_at`/`now` as a substitute (the spec's explicit "never fabricated" rule): the news
    became knowable the moment it was published, not the moment our pipeline happened to notice
    it, provided the sync that noticed it was itself a genuine, non-backfilled, promptly-run one.
    """
    if not validated:
        return NewsAvailabilityResult(NewsAvailabilityClassification.INVALID, None)
    if not sync_succeeded:
        return NewsAvailabilityResult(NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME, None)
    if trigger is not SyncTrigger.LIVE_SCHEDULED:
        return NewsAvailabilityResult(NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME, None)
    if not has_genuine_timestamp:
        return NewsAvailabilityResult(NewsAvailabilityClassification.UNKNOWN_AVAILABILITY_TIME, None)
    return NewsAvailabilityResult(NewsAvailabilityClassification.VERIFIED_PRE_MATCH, published_at)


def is_information_available_before_kickoff(information_available_at: datetime, kickoff: datetime) -> bool:
    """Milestone 10 §10/§26's explicit, non-negotiable rule, expressed as one small, directly
    testable comparison: information available *at or after* a fixture's kickoff must never be
    treated as pre-match-safe for that fixture, no matter how it classified otherwise. Strict
    inequality — ``available_at == kickoff`` is NOT eligible, only genuinely earlier is.

    This is additional to (never a replacement for) the existing event-type validity-window /
    `is_feature_eligible()` gating Milestone 9 already built — those answer "is this event still
    fresh enough to matter at all," this answers a narrower, fixture-specific question a TTL
    window alone can't: "was this specific piece of information already knowable before THIS
    fixture's own kickoff." See `NewsMarketImpactEngine._team_contributions`'s optional ``kickoff``
    parameter for where this is wired into the real read path."""
    return information_available_at < kickoff


@dataclass(frozen=True)
class ConfidenceInputs:
    """Everything `NewsEventConfidenceClassifier` needs — every field is computed from real,
    already-persisted data (`NewsSource.is_official`, `SourceReliabilityScore.trust_level`, a
    corroboration count derived from `NewsEventRepositoryPort.list_for_entity`, a contradiction
    flag from the same corroboration scan), never fabricated or assumed."""

    event_type: NewsEventType
    is_official_source: bool
    source_trust_level: TrustLevel
    corroborating_source_count: int  # distinct OTHER sources reporting the same event, not counting itself
    contradicted: bool
    age_hours: float
    ttl_hours: float


class NewsEventConfidenceClassifier:
    """Deterministic 6-tier taxonomy (spec §5) — confidence is never decorative here: it directly
    gates `NewsMarketImpactEngine`'s weighting (`modules.predictions.application.
    news_market_impact_registry.CONFIDENCE_WEIGHT_MULTIPLIERS`) and, via `NewsEvent.
    is_feature_eligible`, entity-resolution eligibility. Evaluation order matters — each rule is
    checked in the exact priority the spec's own six examples imply (contradiction and expiry
    override everything else; official confirmation beats corroboration; corroboration beats bare
    unverified reporting; transfer speculation with no corroboration is RUMOUR specifically,
    distinct from the spec's own separate "single unverified report -> UNCERTAIN" example for
    every other event type)."""

    @staticmethod
    def classify(inputs: ConfidenceInputs) -> NewsEventConfidenceTier:
        if inputs.contradicted:
            return NewsEventConfidenceTier.CONTRADICTED
        if inputs.age_hours > inputs.ttl_hours:
            return NewsEventConfidenceTier.EXPIRED
        if inputs.is_official_source:
            return NewsEventConfidenceTier.CONFIRMED
        if inputs.source_trust_level.level >= TrustLevel.VERIFIED.level and inputs.corroborating_source_count >= 1:
            return NewsEventConfidenceTier.PROBABLE
        if (
            inputs.event_type is NewsEventType.TRANSFER
            and inputs.source_trust_level.level <= TrustLevel.UNVERIFIED.level
            and inputs.corroborating_source_count == 0
        ):
            return NewsEventConfidenceTier.RUMOUR
        return NewsEventConfidenceTier.UNCERTAIN


# Confidence-weighted impact magnitude multipliers (spec §5's own example table: "CONFIRMED =
# full weight, PROBABLE = reduced, UNCERTAIN = minimal, RUMOUR = zero/minimal"). Consumed by
# `NewsMarketImpactEngine` — a CONTRADICTED or EXPIRED event never reaches the engine at all
# (`NewsEvent.is_feature_eligible` only checks availability/entity-resolution, but the engine
# itself skips anything not CONFIRMED/PROBABLE/UNCERTAIN/RUMOUR before computing impact).
CONFIDENCE_WEIGHT_MULTIPLIERS: dict[NewsEventConfidenceTier, float] = {
    NewsEventConfidenceTier.CONFIRMED: 1.0,
    NewsEventConfidenceTier.PROBABLE: 0.6,
    NewsEventConfidenceTier.UNCERTAIN: 0.3,
    NewsEventConfidenceTier.RUMOUR: 0.1,
    NewsEventConfidenceTier.CONTRADICTED: 0.0,
    NewsEventConfidenceTier.EXPIRED: 0.0,
}

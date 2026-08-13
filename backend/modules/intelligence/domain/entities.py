"""Entities for the News Intelligence & Community Intelligence Platform (Milestone 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.intelligence.domain.value_objects import (
    ArticleStatus,
    CommunityPlatform,
    CommunityPostId,
    CommunityTopicId,
    EntityResolutionStatus,
    ImpactScoreId,
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    NewsArticleId,
    NewsEventConfidenceTier,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    NewsSourceType,
    SentimentLabel,
    SentimentResultId,
    SourceReliabilityId,
    SummaryId,
    SummaryType,
    SyncStatus,
    SyncTrigger,
    TrustLevel,
    VerificationStatus,
)


@dataclass
class NewsSource:
    """A registered, provider-abstracted origin of news content — one row per official club
    site, league site, RSS feed, or approved publisher (Milestone 8 "NEWS INGESTION")."""

    id: NewsSourceId
    source_type: NewsSourceType
    name: str
    url: str
    is_official: bool = False
    publisher_metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class NewsArticle:
    """One ingested article. ``content_hash`` (a hash of normalized title+body) is the
    Deduplication key — the same story republished verbatim by two sources, or re-fetched on
    the next sync, resolves to the same hash rather than a duplicate row. ``version`` increments
    when a re-fetch finds the same URL with materially changed content (Versioning)."""

    id: NewsArticleId
    source_id: NewsSourceId
    title: str
    url: str
    content_hash: str
    raw_text: str
    published_at: datetime
    fetched_at: datetime
    language: str = "en"
    version: int = 1
    status: ArticleStatus = ArticleStatus.ACTIVE


@dataclass(frozen=True)
class ResolvedNewsEntity:
    """Milestone 9 — one entity mention from a `NewsEvent`, carrying its resolution status
    explicitly rather than discarding it. ``ref`` is the resolved Knowledge Graph node id (as a
    string) when ``status`` is RESOLVED, or the raw unresolved mention text otherwise — never
    both conflated into one opaque string the way the pre-Milestone-9 flat
    `affected_entity_refs` union did (see `EventExtractionService.extract_and_record`'s
    docstring for the bug this replaces). An UNRESOLVED entity is retained here for raw-audit
    storage but must never be treated as available to a prediction feature requiring that
    entity (the spec's explicit "mock_player must not enter production intelligence
    features" rule)."""

    ref: str
    node_type: str | None
    status: EntityResolutionStatus
    role: str | None = None  # normalized player role (goalkeeper/defender/midfielder/forward),
    # populated lazily by a consumer with access to the sports Player repository — never set at
    # extraction time, which has no such dependency (see `news_market_impact_engine.py`).


@dataclass
class NewsEvent:
    """A structured event detected in an article's text (Milestone 8 "EVENT EXTRACTION") —
    every event carries Confidence, Source, Timestamp, Affected Entities, and Knowledge Graph
    links, per the spec's explicit requirement.

    Milestone 9 (Temporal Validity + Market-Specific Impact) additions: ``resolved_entities`` is
    the authoritative, resolution-status-aware entity list (see `ResolvedNewsEntity`);
    ``affected_entity_refs`` stays RESOLVED-only now (its original intended contract — existing
    consumers like `NewsImpactEngine` already assumed every ref there is a real KG node id,
    which this milestone's `EventExtractionService` fix now actually honors instead of violating).
    ``confidence_tier`` is the formal 6-state taxonomy (`NewsEventConfidenceTier`) — the pre-existing
    bare ``confidence`` float stays as Gemini's own raw extraction confidence, unchanged, a
    distinct concept `NewsEventConfidenceClassifier` consumes as one input among several, not a
    value it overwrites. ``information_available_at``/``availability_classification`` follow the
    exact same "never fabricated, defaults to UNKNOWN_AVAILABILITY_TIME" contract Milestone 5
    established for structured intelligence — see `modules.intelligence.application.news_provenance`."""

    id: NewsEventId
    event_type: NewsEventType
    summary: str
    confidence: float
    source_id: NewsSourceId
    article_id: NewsArticleId
    occurred_at: datetime
    detected_at: datetime
    affected_entity_refs: tuple[str, ...] = field(default_factory=tuple)
    kg_edge_ids: tuple[str, ...] = field(default_factory=tuple)
    resolved_entities: tuple[ResolvedNewsEntity, ...] = field(default_factory=tuple)
    confidence_tier: NewsEventConfidenceTier = NewsEventConfidenceTier.UNCERTAIN
    information_available_at: datetime | None = None
    availability_classification: str = "UNKNOWN_AVAILABILITY_TIME"
    validity_start: datetime | None = None
    validity_end: datetime | None = None
    sync_run_id: str | None = None

    def is_feature_eligible(self) -> bool:
        """The single choke point every feature-writing consumer must check before using this
        event: point-in-time-safe (VERIFIED_PRE_MATCH) AND every entity the event needs is
        actually resolved. An event with even one UNRESOLVED entity is excluded — "the event may
        remain stored as raw intelligence but must not influence prediction features requiring
        that entity" (spec §6)."""
        if self.availability_classification != "VERIFIED_PRE_MATCH":
            return False
        return all(e.status is EntityResolutionStatus.RESOLVED for e in self.resolved_entities)


@dataclass
class SourceReliabilityScore:
    """Per-source trust profile (Milestone 8 "SOURCE RELIABILITY ENGINE") — consumed as a
    Feature Store input, never used to override a verified fact."""

    id: SourceReliabilityId
    source_id: NewsSourceId
    reliability_score: float  # 0-1, EWMA of past extraction/event accuracy
    historical_accuracy: float  # 0-1, fraction of past events later confirmed correct
    bias_rating: float  # -1 (strongly one-sided) .. 0 (neutral) .. 1 (strongly one-sided, other direction)
    verification_status: VerificationStatus
    trust_level: TrustLevel
    updated_at: datetime


@dataclass
class SentimentResult:
    """One sentiment reading about a target entity, derived from one article or community post
    (Milestone 8 "SENTIMENT ENGINE") — always an auxiliary signal, never authoritative fact."""

    id: SentimentResultId
    target_entity_ref: str
    target_entity_type: str
    label: SentimentLabel
    momentum: float  # rate of sentiment change over the recent window, signed
    confidence: float
    source_ref: str  # stringified NewsArticleId or CommunityPostId this reading came from
    computed_at: datetime


@dataclass
class ImpactScore:
    """News Impact Scoring output for one `NewsEvent` (Milestone 8 "NEWS IMPACT ENGINE") —
    ``factors`` holds the named sub-scores (injury_severity, transfer_importance,
    manager_influence, player_importance, competition_importance, timing, historical_impact,
    community_momentum) the spec asks the engine to evaluate; ``impact_score`` is their
    weighted composite."""

    id: ImpactScoreId
    news_event_id: NewsEventId
    impact_score: float
    confidence: float
    factors: dict = field(default_factory=dict)
    affected_teams: tuple[str, ...] = field(default_factory=tuple)
    affected_players: tuple[str, ...] = field(default_factory=tuple)
    affected_competitions: tuple[str, ...] = field(default_factory=tuple)
    computed_at: datetime | None = None


@dataclass
class Summary:
    """One generated summary (Milestone 8 "SUMMARIZATION") — ``summary_type`` selects which of
    the seven named summary kinds this is; ``subject_ref`` is the entity/match/article it's
    about."""

    id: SummaryId
    summary_type: SummaryType
    subject_ref: str
    text: str
    generated_at: datetime
    source_article_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class CommunityPost:
    """One ingested community post/comment (Milestone 8 "COMMUNITY INTELLIGENCE"). Spam/bot
    filtering happens before persistence in `CommunityIngestionService` — a post that survives
    to become a `CommunityPost` row has already cleared those checks; ``credibility_score``
    reflects the *author's* standing, not a verdict on the post's factual content."""

    id: CommunityPostId
    platform: CommunityPlatform
    external_id: str
    author_ref: str
    text: str
    posted_at: datetime
    fetched_at: datetime
    credibility_score: float = 0.5


@dataclass
class CommunityTopic:
    """A clustered discussion topic across community posts — the aggregate unit "Community
    Topics" API queries return, distinct from individual posts."""

    id: CommunityTopicId
    platform: CommunityPlatform
    topic_label: str
    related_entity_refs: tuple[str, ...] = field(default_factory=tuple)
    post_count: int = 0
    momentum: float = 0.0
    created_at: datetime | None = None


@dataclass
class IntelligenceSyncRun:
    """One execution of either the News Ingestion or Community Intelligence sync pipeline for
    one channel — the record "Monitoring" (Milestone 8) reads Ingestion Rate/Duplicate Rate/
    Processing Time from. Mirrors `modules.ingestion.domain.entities.SyncRun`'s shape
    deliberately (same problem, incremental sync of external records) but is its own entity —
    Milestone 8 does not import Milestone 5's sports-specific ingestion types."""

    id: IntelligenceSyncRunId
    channel_type: IntelligenceChannelType
    channel_key: str  # stringified NewsSourceId, or "platform:topic" for community
    trigger: SyncTrigger
    status: SyncStatus
    started_at: datetime
    finished_at: datetime | None = None
    items_fetched: int = 0
    items_created: int = 0
    items_duplicate: int = 0
    items_rejected: int = 0
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def mark_succeeded(self, now: datetime) -> None:
        self.status = SyncStatus.SUCCEEDED if self.items_rejected == 0 else SyncStatus.PARTIAL
        self.finished_at = now

    def mark_failed(self, now: datetime, error_message: str) -> None:
        self.status = SyncStatus.FAILED
        self.finished_at = now
        self.error_message = error_message


@dataclass
class IntelligenceSyncCheckpoint:
    """Incremental-sync state for one channel — "never reload complete datasets
    unnecessarily," the same rationale as `modules.ingestion.domain.entities.SyncCheckpoint`."""

    channel_type: IntelligenceChannelType
    channel_key: str
    last_synced_at: datetime | None = None
    cursor: str | None = None
    consecutive_failures: int = 0
